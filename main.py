"""
Elite Quant Trading System - Main Entry Point
Orchestrates all components for automated crypto trading

Architecture:
1. Data Feed - Fetches market data from OKX
2. Filters - Heavy filtering to reject bad trades
3. Strategy - Generates trading signals
4. Risk - Validates risk parameters
5. Execution - Places and manages orders
6. Model Learning - Trains AI rejection model

Trading Philosophy:
- Quality over quantity (3-5 trades/day max)
- Heavy filtering > high volume
- Only trade when ALL conditions are perfect
- Strict risk management always enforced
"""

import time
import signal
import sys
from datetime import datetime
from typing import Optional
import logging

# Import modules
from utils.logger import setup_logging
from data_feed import OKXClient, MarketDataFeed
from filters import FilterManager
from strategy import StrategyManager
from risk import RiskManager
from execution import OrderManager, PositionTracker
from model_learning import DataCollector

import config

# Setup logging first
setup_logging()
logger = logging.getLogger(__name__)


class EliteQuantSystem:
    """
    Main trading system coordinator
    Runs the full trading loop with all safety checks
    """

    def __init__(self):
        logger.info("🚀 Initializing Elite Quant System")

        # Initialize all components
        self.okx_client = OKXClient()
        self.market_data = MarketDataFeed(self.okx_client)
        self.filter_manager = FilterManager()
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager(self.okx_client)
        self.order_manager = OrderManager(self.okx_client)
        self.position_tracker = PositionTracker(self.okx_client)
        self.data_collector = DataCollector()

        # State
        self.running = False
        self.cycle_count = 0
        self.last_trade_time = None

        # Timeframes to analyze
        self.timeframes = [
            config.MICRO_TIMEFRAME,
            config.LTF_TIMEFRAME,
            config.MTF_TIMEFRAME,
            config.HTF_TIMEFRAME
        ]

        logger.info("✅ All components initialized")

    def run(self):
        """
        Main trading loop
        """
        self.running = True

        logger.info("\n" + "="*60)
        logger.info("🎯 ELITE QUANT SYSTEM STARTED")
        logger.info(f"Symbol: {config.TRADING_SYMBOL}")
        logger.info(f"Mode: {'SIMULATED' if config.OKX_SIMULATED else 'LIVE'}")
        logger.info(f"Max Daily Trades: {config.MAX_DAILY_TRADES}")
        logger.info(f"Risk Per Trade: {config.MAX_RISK_PER_TRADE*100}%")
        logger.info("="*60 + "\n")

        try:
            while self.running:
                self.cycle_count += 1
                logger.info(f"\n{'─'*60}")
                logger.info(f"CYCLE #{self.cycle_count} - {datetime.now()}")
                logger.info(f"{'─'*60}")

                # Run one trading cycle
                self._run_trading_cycle()

                # Wait before next cycle
                time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            logger.info("\n⚠️  Keyboard interrupt received")
            self.shutdown()
        except Exception as e:
            logger.error(f"❌ Unexpected error in main loop: {e}", exc_info=True)
            self.shutdown()

    def _run_trading_cycle(self):
        """
        Single iteration of the trading loop
        """
        try:
            # Step 1: Update existing positions
            self._update_positions()

            # Step 2: Check emergency conditions
            market_state = self.market_data.get_market_state(
                config.TRADING_SYMBOL,
                self.timeframes
            )

            emergency, reason = self.risk_manager.check_emergency_conditions(market_state)
            if emergency:
                logger.critical(f"🚨 EMERGENCY: {reason}")
                self.risk_manager.trigger_emergency_shutdown(reason)
                self.running = False
                return

            # Step 3: Check if we can trade
            open_positions = self.position_tracker.get_open_positions()
            can_trade, trade_reason = self.risk_manager.check_can_trade(len(open_positions))

            if not can_trade:
                logger.info(f"⏸️  Trading paused: {trade_reason}")
                return

            # Step 4: If we have open positions, don't look for new trades
            if len(open_positions) >= config.MAX_POSITIONS_OPEN:
                logger.info(f"📊 Max positions open ({len(open_positions)}), monitoring only")
                return

            # Step 5: Look for trading signals
            signal = self.strategy_manager.analyze_market(market_state)

            if not signal:
                logger.info("📉 No signal detected")
                return

            logger.info(f"🎯 SIGNAL DETECTED: {signal['strategy']} - {signal['direction'].upper()}")

            # Step 6: Run ALL filters (most important step!)
            filters_passed, filter_results = self.filter_manager.check_all(
                market_state,
                signal['direction'],
                signal['strategy']
            )

            if not filters_passed:
                logger.warning(f"❌ SIGNAL REJECTED BY FILTERS")
                logger.warning(f"   Failed: {', '.join(filter_results['failed_filters'])}")
                return

            logger.info(f"✅ ALL FILTERS PASSED - TRADE APPROVED")

            # Step 7: Calculate position size
            account_balance = self.risk_manager.get_account_balance()
            if not account_balance:
                logger.error("❌ Could not get account balance")
                return

            position_size, size_details = self.risk_manager.calculate_position_size(
                signal,
                account_balance
            )

            # Step 8: Execute trade
            self._execute_trade(signal, position_size)

        except Exception as e:
            logger.error(f"❌ Error in trading cycle: {e}", exc_info=True)

    def _execute_trade(self, signal: Dict, position_size: float):
        """
        Execute a trade based on signal

        Args:
            signal: Trading signal
            position_size: Position size to trade
        """
        try:
            logger.info("\n" + "="*60)
            logger.info("💰 EXECUTING TRADE")
            logger.info("="*60)

            # Place market order
            entry_order = self.order_manager.place_market_order(signal, position_size)

            if not entry_order:
                logger.error("❌ Failed to place entry order")
                return

            # Create position
            position = self.position_tracker.create_position(signal, entry_order)

            # Place stop loss
            stop_order = self.order_manager.place_stop_loss(position, signal['stop_loss'])
            if stop_order:
                position['orders']['stop_loss'] = stop_order.get('order_id')

            # Place take profits
            # TP1: Close 50% of position
            tp1_size = position_size * 0.5
            tp1_order = self.order_manager.place_take_profit(position, signal['take_profit_1'], tp1_size)
            if tp1_order:
                position['orders']['take_profit_1'] = tp1_order.get('order_id')

            # TP2: Close remaining 50%
            tp2_order = self.order_manager.place_take_profit(position, signal['take_profit_2'], tp1_size)
            if tp2_order:
                position['orders']['take_profit_2'] = tp2_order.get('order_id')

            # Save prediction for AI learning
            if config.COLLECT_TRAINING_DATA:
                self._save_prediction_for_learning(signal, position)

            # Update risk manager
            self.last_trade_time = datetime.now()

            logger.info("="*60)
            logger.info("✅ TRADE EXECUTED SUCCESSFULLY")
            logger.info(f"Position ID: {position['position_id']}")
            logger.info(f"Entry: ${signal['entry_price']:.2f}")
            logger.info(f"Stop Loss: ${signal['stop_loss']:.2f}")
            logger.info(f"Take Profit 1: ${signal['take_profit_1']:.2f}")
            logger.info(f"Take Profit 2: ${signal['take_profit_2']:.2f}")
            logger.info("="*60 + "\n")

        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}", exc_info=True)

    def _update_positions(self):
        """
        Update all open positions with current prices
        """
        open_positions = self.position_tracker.get_open_positions()

        if not open_positions:
            return

        current_price = self.market_data.get_current_price(config.TRADING_SYMBOL)
        if not current_price:
            return

        for position in open_positions:
            self.position_tracker.update_position_pnl(
                position['position_id'],
                current_price
            )

            # Log position status
            logger.info(
                f"📊 Position {position['position_id']}: "
                f"${current_price:.2f} | "
                f"PnL: {position['pnl_pct']:+.2f}%"
            )

    def _save_prediction_for_learning(self, signal: Dict, position: Dict):
        """
        Save prediction for later AI model training
        """
        try:
            # This will be labeled later when position closes
            self.data_collector.save_prediction({
                'trade_id': position['position_id'],
                'timestamp': datetime.now().isoformat(),
                'signal': signal,
                'position': position,
                'features': {},  # Features would be extracted by AI filter
                'confidence': 0,  # Confidence from AI filter
                'outcome': None  # Will be filled when position closes
            })
        except Exception as e:
            logger.error(f"Failed to save prediction: {e}")

    def shutdown(self):
        """
        Graceful shutdown
        """
        logger.info("\n" + "="*60)
        logger.info("🛑 SHUTTING DOWN ELITE QUANT SYSTEM")
        logger.info("="*60)

        self.running = False

        # Log final statistics
        self._log_final_statistics()

        logger.info("="*60)
        logger.info("✅ System shut down successfully")
        logger.info("="*60 + "\n")

    def _log_final_statistics(self):
        """Log final system statistics"""
        try:
            # Filter stats
            filter_stats = self.filter_manager.get_filter_statistics()
            logger.info(f"\n📊 Filter Statistics:")
            logger.info(f"   Total checks: {filter_stats['total_checks']}")
            logger.info(f"   Pass rate: {filter_stats['pass_rate']*100:.1f}%")

            # Position stats
            position_stats = self.position_tracker.get_statistics()
            logger.info(f"\n💰 Trading Statistics:")
            logger.info(f"   Total trades: {position_stats['total_trades']}")
            logger.info(f"   Win rate: {position_stats['win_rate']*100:.1f}%")
            logger.info(f"   Total PnL: ${position_stats['total_pnl']:.2f}")

            # Risk stats
            risk_stats = self.risk_manager.get_risk_statistics()
            logger.info(f"\n🛡️  Risk Statistics:")
            logger.info(f"   Daily PnL: ${risk_stats['daily_pnl']:.2f}")
            logger.info(f"   Daily trades: {risk_stats['daily_trades']}")

        except Exception as e:
            logger.error(f"Error logging statistics: {e}")


def signal_handler(sig, frame):
    """Handle interrupt signals"""
    logger.info("\n⚠️  Interrupt signal received")
    sys.exit(0)


def main():
    """
    Main entry point
    """
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Validate configuration
    validation_errors = config.validate_config()
    if validation_errors:
        logger.error("❌ Configuration errors detected:")
        for error in validation_errors:
            logger.error(f"   - {error}")

        if not config.OKX_SIMULATED:
            logger.error("⚠️  Cannot start in LIVE mode with configuration errors")
            sys.exit(1)

    # Create and run system
    system = EliteQuantSystem()
    system.run()


if __name__ == "__main__":
    main()
