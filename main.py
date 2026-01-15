"""
Elite Quant Trading System - Main Entry Point
Orchestrates all components for automated crypto trading

Architecture:
1. Data Feed - Fetches market data from OKX
2. Filters - Heavy filtering to reject bad trades
3. Claude AI - Learned rejection rules from past losses
4. Strategy - Generates trading signals
5. Risk - Validates risk parameters
6. Execution - Places and manages orders
7. Model Learning - Trains AI rejection model

Trading Philosophy:
- Quality over quantity (3-5 trades/day max)
- Heavy filtering > high volume
- Only trade when ALL conditions are perfect
- Strict risk management always enforced
- Learn from every loss
"""

import time
import signal
import sys
import threading
from datetime import datetime
from typing import Optional, Dict
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

# Claude AI integration (optional - won't crash if missing)
try:
    from agents.claude_autonomous_system import AutonomousTradeSystem
    CLAUDE_AVAILABLE = True
    logger.info("🤖 Claude AI gating enabled")
except ImportError as e:
    CLAUDE_AVAILABLE = False
    logger.warning(f"Claude AI not available - {e}")
    import traceback
    logger.warning(f"Import error details:")
    traceback.print_exc()
except Exception as e:
    CLAUDE_AVAILABLE = False
    logger.warning(f"Claude AI init failed: {e}")
    import traceback
    logger.warning(f"Exception details:")
    traceback.print_exc()

# Dashboard imports (optional - won't crash if missing)
try:
    from dashboard.app import (
        create_app,
        update_balance,
        update_positions,
        add_trade,
        add_signal,
        set_bot_status,
        update_prices,
        set_market_regime,
        update_filter_stats,
        add_error,
        update_daily_pnl
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False
    logger.warning("Dashboard not available - install flask to enable")


def run_dashboard():
    """Run dashboard in separate thread"""
    if not DASHBOARD_AVAILABLE:
        return
    try:
        app = create_app()
        logger.info(f"📊 Dashboard running on http://localhost:{config.DASHBOARD_PORT}")
        app.run(
            host=config.DASHBOARD_HOST,
            port=config.DASHBOARD_PORT,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


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

        # Initialize Claude AI gating (if available)
        self.claude_system = None
        self.claude_enabled = getattr(config, 'CLAUDE_GATING_ENABLED', True)
        if CLAUDE_AVAILABLE and self.claude_enabled:
            try:
                self.claude_system = AutonomousTradeSystem()
                logger.info("✅ Claude AI gating initialized")
            except Exception as e:
                logger.warning(f"Claude AI init failed: {e}")
                import traceback
                logger.warning(f"Exception details:")
                traceback.print_exc()
                self.claude_system = None

        # State
        self.running = False
        self.cycle_count = 0
        self.last_trade_time = None
        self.claude_blocks = 0  # Track how many trades Claude blocked

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
        
        if DASHBOARD_AVAILABLE:
            set_bot_status('running')

        logger.info("\n" + "="*60)
        logger.info("🎯 ELITE QUANT SYSTEM STARTED")
        logger.info(f"Symbol: {config.TRADING_SYMBOL}")
        logger.info(f"Mode: {'SIMULATED' if config.OKX_SIMULATED else 'LIVE'}")
        logger.info(f"Max Daily Trades: {config.MAX_DAILY_TRADES}")
        logger.info(f"Risk Per Trade: {config.MAX_RISK_PER_TRADE*100}%")
        logger.info(f"Claude AI Gating: {'ENABLED' if self.claude_system else 'DISABLED'}")
        if DASHBOARD_AVAILABLE:
            logger.info(f"Dashboard: http://localhost:{config.DASHBOARD_PORT}")
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
            if DASHBOARD_AVAILABLE:
                add_error(str(e))
            self.shutdown()

    def _run_trading_cycle(self):
        """
        Single iteration of the trading loop
        """
        try:
            # Step 1: Update existing positions
            self._update_positions()

            # Step 2: Fetch market data for SOL (trading) and BTC (reference)
            logger.info(f"📊 Fetching market data...")
            sol_market_state = self.market_data.get_market_state(
                config.TRADING_SYMBOL,
                self.timeframes
            )

            # Update dashboard with prices
            if DASHBOARD_AVAILABLE and sol_market_state:
                current_price = sol_market_state.get('current_price', 0)
                update_prices(current_price, 0)  # BTC price updated below

            # Fetch BTC data for correlation analysis
            btc_market_state = None
            if hasattr(config, 'REFERENCE_SYMBOL'):
                logger.info(f"📊 Fetching BTC reference data...")
                btc_market_state = self.market_data.get_market_state(
                    config.REFERENCE_SYMBOL,
                    self.timeframes
                )
                if DASHBOARD_AVAILABLE and btc_market_state:
                    btc_price = btc_market_state.get('current_price', 0)
                    sol_price = sol_market_state.get('current_price', 0) if sol_market_state else 0
                    update_prices(sol_price, btc_price)

            # Update balance on dashboard
            if DASHBOARD_AVAILABLE:
                balance = self.risk_manager.get_account_balance()
                if balance:
                    update_balance(balance, balance)

            # Step 3: Check emergency conditions
            emergency, reason = self.risk_manager.check_emergency_conditions(sol_market_state)
            if emergency:
                logger.critical(f"🚨 EMERGENCY: {reason}")
                if DASHBOARD_AVAILABLE:
                    add_error(f"EMERGENCY: {reason}")
                self.risk_manager.trigger_emergency_shutdown(reason)
                self.running = False
                return

            # Step 3: Check if we can trade
            open_positions = self.position_tracker.get_open_positions()
            can_trade, trade_reason = self.risk_manager.check_can_trade(len(open_positions))

            if not can_trade:
                logger.info(f"⏸️  Trading paused: {trade_reason}")
                if DASHBOARD_AVAILABLE:
                    add_signal({'type': 'paused', 'reason': trade_reason})
                return

            # Step 4: If we have open positions, don't look for new trades
            if len(open_positions) >= config.MAX_POSITIONS_OPEN:
                logger.info(f"📊 Max positions open ({len(open_positions)}), monitoring only")
                return

            # Step 5: Look for trading signals (on SOL)
            signal = self.strategy_manager.analyze_market(sol_market_state)

            if not signal:
                logger.info("📉 No signal detected")
                if DASHBOARD_AVAILABLE:
                    add_signal({'type': 'scan', 'reason': 'No signal detected'})
                return

            logger.info(f"🎯 SIGNAL DETECTED: {signal['strategy']} - {signal['direction'].upper()}")
            if DASHBOARD_AVAILABLE:
                add_signal({
                    'type': 'detected',
                    'direction': signal['direction'],
                    'strategy': signal['strategy'],
                    'reason': f"Raw signal from {signal['strategy']}"
                })

            # Step 6: Run ALL filters (most important step!)
            filters_passed, filter_results = self.filter_manager.check_all(
                sol_market_state,
                signal['direction'],
                signal['strategy'],
                btc_market_state  # Pass BTC data for correlation check
            )

            if DASHBOARD_AVAILABLE:
                update_filter_stats(filter_results)

            if not filters_passed:
                logger.warning(f"❌ SIGNAL REJECTED BY FILTERS")
                logger.warning(f"   Failed: {', '.join(filter_results['failed_filters'])}")
                if DASHBOARD_AVAILABLE:
                    add_signal({
                        'type': 'rejected',
                        'direction': signal['direction'],
                        'reason': f"Failed: {', '.join(filter_results['failed_filters'])}"
                    })
                return

            logger.info(f"✅ ALL FILTERS PASSED")

            # Step 7: Claude AI Gating (learned rejection rules)
            if self.claude_system:
                claude_approved = self._check_claude_approval(signal, sol_market_state)
                if not claude_approved:
                    logger.warning(f"🤖 SIGNAL REJECTED BY CLAUDE AI")
                    self.claude_blocks += 1
                    if DASHBOARD_AVAILABLE:
                        add_signal({
                            'type': 'rejected',
                            'direction': signal['direction'],
                            'reason': 'Blocked by Claude AI (learned pattern)'
                        })
                    return
                logger.info(f"🤖 Claude AI APPROVED")

            logger.info(f"✅ TRADE APPROVED - EXECUTING")
            if DASHBOARD_AVAILABLE:
                add_signal({
                    'type': 'approved',
                    'direction': signal['direction'],
                    'strategy': signal['strategy'],
                    'reason': 'All filters + Claude AI passed'
                })

            # Step 8: Calculate position size
            account_balance = self.risk_manager.get_account_balance()
            if not account_balance:
                logger.error("❌ Could not get account balance")
                return

            position_size, size_details = self.risk_manager.calculate_position_size(
                signal,
                account_balance
            )

            # Step 9: Execute trade
            self._execute_trade(signal, position_size)

        except Exception as e:
            logger.error(f"❌ Error in trading cycle: {e}", exc_info=True)
            if DASHBOARD_AVAILABLE:
                add_error(str(e))

    def _check_claude_approval(self, signal: Dict, market_state: Dict) -> bool:
        """
        Check if Claude AI approves the trade based on learned patterns
        
        Args:
            signal: Trading signal dict
            market_state: Current market state
            
        Returns:
            True if approved, False if blocked
        """
        if not self.claude_system:
            return True  # If Claude not available, approve by default
        
        try:
            # Build trade dict for Claude to evaluate
            trade_to_check = {
                'trade_id': f"pending_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'direction': signal.get('direction'),
                'entry_price': signal.get('entry_price', market_state.get('current_price', 0)),
                'stop_loss': signal.get('stop_loss', 0),
                'take_profit_1': signal.get('take_profit_1', 0),
                'take_profit_2': signal.get('take_profit_2', 0),
                'strategy': signal.get('strategy'),
                'volatility': market_state.get('volatility', 0),
                'volume_ratio': market_state.get('volume_ratio', 1),
                'risk_amount': signal.get('risk_amount', 0),
            }
            
            # Get market context
            market_context = {
                'price': market_state.get('current_price', 0),
                'trend': market_state.get('trend', 'unknown'),
                'volatility': market_state.get('volatility', 'unknown'),
                'volume_ratio': market_state.get('volume_ratio', 1),
            }
            
            # Ask Claude to approve/reject
            decision = self.claude_system.approve_trade(trade_to_check, market_context)
            
            if not decision['approved']:
                logger.info(f"🤖 Claude blocked trade: {decision.get('reasoning', 'Unknown reason')}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Claude approval check failed: {e}")
            return True  # On error, default to approve (fail open)

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

            if DASHBOARD_AVAILABLE:
                add_signal({
                    'type': 'entry',
                    'direction': signal['direction'],
                    'strategy': signal['strategy'],
                    'reason': f"Executing {signal['direction'].upper()} trade"
                })

            # Place market order
            entry_order = self.order_manager.place_market_order(signal, position_size)

            if not entry_order:
                logger.error("❌ Failed to place entry order")
                if DASHBOARD_AVAILABLE:
                    add_error("Failed to place entry order")
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

            # Update dashboard
            if DASHBOARD_AVAILABLE:
                add_trade({
                    'symbol': config.TRADING_SYMBOL,
                    'side': signal['direction'],
                    'entry_price': signal['entry_price'],
                    'exit_price': 0,
                    'pnl': 0,
                    'strategy': signal['strategy']
                })

        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}", exc_info=True)
            if DASHBOARD_AVAILABLE:
                add_error(f"Trade execution error: {e}")

    def _update_positions(self):
        """
        Update all open positions with current prices
        Also analyze closed positions for Claude learning
        """
        open_positions = self.position_tracker.get_open_positions()

        if not open_positions:
            if DASHBOARD_AVAILABLE:
                update_positions([])
            return

        current_price = self.market_data.get_current_price(config.TRADING_SYMBOL)
        if not current_price:
            return

        dashboard_positions = []
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

            # Format for dashboard
            if DASHBOARD_AVAILABLE:
                dashboard_positions.append({
                    'symbol': config.TRADING_SYMBOL,
                    'side': position.get('direction', 'long'),
                    'size': position.get('size', 0),
                    'entry_price': position.get('entry_price', 0),
                    'current_price': current_price,
                    'pnl': position.get('pnl', 0),
                    'pnl_pct': position.get('pnl_pct', 0)
                })

        if DASHBOARD_AVAILABLE:
            update_positions(dashboard_positions)
        
        # Check for newly closed positions and send to Claude for learning
        self._check_closed_positions_for_learning()

    def _check_closed_positions_for_learning(self):
        """
        Check for recently closed positions and send losing ones to Claude
        """
        if not self.claude_system:
            return
            
        try:
            # Get recently closed positions
            closed_positions = self.position_tracker.get_recently_closed_positions()
            
            for position in closed_positions:
                trade_dict = {
                    'trade_id': position.get('position_id'),
                    'direction': position.get('direction'),
                    'entry_price': position.get('entry_price', 0),
                    'exit_price': position.get('exit_price', 0),
                    'stop_loss': position.get('stop_loss', 0),
                    'pnl': position.get('pnl', 0),
                    'loss_amount': abs(position.get('pnl', 0)) if position.get('pnl', 0) < 0 else 0,
                    'loss_pct': position.get('pnl_pct', 0),
                    'duration_minutes': position.get('duration_minutes', 0),
                    'strategy': position.get('strategy', 'breakout'),
                }
                
                # Process all completed trades (for success rate tracking)
                self.claude_system.process_completed_trade(trade_dict)
                
                # Only analyze losing trades for learning
                if position.get('pnl', 0) < 0:
                    logger.info(f"🤖 Sending losing trade to Claude for analysis: {trade_dict['trade_id']}")
                else:
                    logger.info(f"✅ Recording successful trade outcome: {trade_dict['trade_id']} - PnL: ${position.get('pnl', 0):.2f}")
                    
        except Exception as e:
            logger.error(f"Error in Claude learning check: {e}")

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
        
        if DASHBOARD_AVAILABLE:
            set_bot_status('stopped')

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
            
            # Claude AI stats
            if self.claude_system:
                claude_status = self.claude_system.get_system_status()
                approval_stats = claude_status.get('approval_stats', {})
                success_rate = approval_stats.get('success_rate', 0.0)
                success_rate_acceptable = approval_stats.get('success_rate_acceptable', True)
                logger.info(f"\n🤖 Claude AI Statistics:")
                logger.info(f"   Rules learned: {claude_status['learned_rules']}")
                logger.info(f"   Trades blocked: {self.claude_blocks}")
                logger.info(f"   Est. loss prevented: ${claude_status['estimated_prevented_loss']:.2f}")
                logger.info(f"   Success rate: {success_rate*100:.1f}% ({'✅' if success_rate_acceptable else '⚠️  BELOW 60%'})")
                logger.info(f"   Successful trades: {approval_stats.get('successful_trades', 0)} / {approval_stats.get('total_tracked_trades', 0)}")

        except Exception as e:
            logger.error(f"Error logging statistics: {e}")


def signal_handler(sig, frame):
    """Handle interrupt signals"""
    logger.info("\n⚠️  Interrupt signal received")
    if DASHBOARD_AVAILABLE:
        set_bot_status('stopped')
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

    # Start dashboard in background
    if DASHBOARD_AVAILABLE and getattr(config, 'DASHBOARD_ENABLED', True):
        dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
        dashboard_thread.start()
        time.sleep(1)  # Give dashboard time to start

    # Create and run system
    system = EliteQuantSystem()
    system.run()


if __name__ == "__main__":
    main()
