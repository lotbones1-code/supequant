"""
SupeQuant Elite Trading System - Main Entry Point
SOL-USDT Perpetual Trading with Heavy Filtering
"""

import asyncio
import signal
import sys
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional
import os

# Local imports
import config
from data_feed.okx_client import OKXClient
from strategy.strategy_engine import StrategyEngine
from filters.filter_manager import FilterManager
from risk.risk_manager import RiskManager
from execution.order_manager import OrderManager
from utils.logger import setup_logging

# Dashboard imports
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
    add_error
)

# Setup logging
logger = setup_logging("main")

# Global shutdown flag
shutdown_flag = False
dashboard_app = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_flag
    logger.info("\n\u26a0\ufe0f  Interrupt signal received")
    shutdown_flag = True
    set_bot_status('stopped')


def run_dashboard():
    """Run dashboard in separate thread"""
    global dashboard_app
    try:
        dashboard_app = create_app()
        logger.info(f"\U0001f4ca Dashboard starting on http://localhost:{config.DASHBOARD_PORT}")
        # Run without reloader in thread
        dashboard_app.run(
            host=config.DASHBOARD_HOST,
            port=config.DASHBOARD_PORT,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


class TradingBot:
    """Main trading bot orchestrator"""
    
    def __init__(self):
        self.okx_client: Optional[OKXClient] = None
        self.strategy_engine: Optional[StrategyEngine] = None
        self.filter_manager: Optional[FilterManager] = None
        self.risk_manager: Optional[RiskManager] = None
        self.order_manager: Optional[OrderManager] = None
        
        self.last_trade_time = None
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.start_balance = 0.0
        self.last_day_check = datetime.now().date()
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("\U0001f680 Initializing SupeQuant Trading System...")
        
        # Initialize OKX client
        self.okx_client = OKXClient(
            api_key=config.OKX_API_KEY,
            secret_key=config.OKX_SECRET_KEY,
            passphrase=config.OKX_PASSPHRASE,
            simulated=config.OKX_SIMULATED
        )
        
        # Test connection
        if not await self.okx_client.test_connection():
            raise Exception("Failed to connect to OKX API")
        
        logger.info(f"\u2705 Connected to OKX ({'DEMO' if config.OKX_SIMULATED else 'LIVE'} mode)")
        
        # Initialize components
        self.strategy_engine = StrategyEngine(self.okx_client)
        self.filter_manager = FilterManager(self.okx_client)
        self.risk_manager = RiskManager(self.okx_client)
        self.order_manager = OrderManager(self.okx_client)
        
        # Get initial balance
        balance_info = await self.okx_client.get_account_balance()
        if balance_info:
            self.start_balance = float(balance_info.get('totalEq', 0))
            update_balance(
                float(balance_info.get('totalEq', 0)),
                float(balance_info.get('totalEq', 0))
            )
            logger.info(f"\U0001f4b0 Account Balance: ${self.start_balance:.2f}")
        
        logger.info("\u2705 All components initialized")
        set_bot_status('running')
        
    async def run_trading_loop(self):
        """Main trading loop"""
        logger.info("\n\U0001f3af Starting trading loop...")
        logger.info(f"   Symbol: {config.TRADING_SYMBOL}")
        logger.info(f"   Mode: {'DEMO' if config.OKX_SIMULATED else 'LIVE'}")
        logger.info(f"   Max Daily Trades: {config.MAX_DAILY_TRADES}")
        logger.info(f"   Dashboard: http://localhost:{config.DASHBOARD_PORT}\n")
        
        while not shutdown_flag:
            try:
                await self.trading_cycle()
                
                # Wait before next cycle
                for _ in range(60):  # 60 second cycles
                    if shutdown_flag:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in trading cycle: {e}")
                add_error(str(e))
                await asyncio.sleep(30)
                
    async def trading_cycle(self):
        """Single trading cycle"""
        # Check if new day - reset daily counters
        today = datetime.now().date()
        if today != self.last_day_check:
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.last_day_check = today
            logger.info("\U0001f305 New trading day started")
        
        # Get current market data
        sol_data = await self.okx_client.get_candles(
            config.TRADING_SYMBOL,
            config.LTF_TIMEFRAME,
            limit=config.LTF_LOOKBACK
        )
        
        if not sol_data:
            logger.warning("\u26a0\ufe0f  Failed to fetch market data")
            return
        
        # Update dashboard with current price
        current_price = float(sol_data[-1][4])  # Close price
        btc_data = await self.okx_client.get_candles(
            config.REFERENCE_SYMBOL,
            config.LTF_TIMEFRAME,
            limit=10
        )
        btc_price = float(btc_data[-1][4]) if btc_data else 0
        update_prices(current_price, btc_price)
        
        # Update balance
        balance_info = await self.okx_client.get_account_balance()
        if balance_info:
            equity = float(balance_info.get('totalEq', 0))
            update_balance(equity, equity)
        
        # Check open positions
        positions = await self.okx_client.get_positions()
        if positions:
            formatted_positions = []
            for pos in positions:
                if float(pos.get('pos', 0)) != 0:
                    formatted_positions.append({
                        'symbol': pos.get('instId', ''),
                        'side': 'long' if float(pos.get('pos', 0)) > 0 else 'short',
                        'size': abs(float(pos.get('pos', 0))),
                        'entry_price': float(pos.get('avgPx', 0)),
                        'current_price': current_price,
                        'pnl': float(pos.get('upl', 0)),
                        'pnl_pct': float(pos.get('uplRatio', 0)) * 100
                    })
            update_positions(formatted_positions)
        else:
            update_positions([])
        
        # Check if we can trade
        if self.daily_trades >= config.MAX_DAILY_TRADES:
            logger.info(f"\U0001f6ab Daily trade limit reached ({self.daily_trades}/{config.MAX_DAILY_TRADES})")
            return
        
        if self.last_trade_time:
            minutes_since_last = (datetime.now() - self.last_trade_time).seconds / 60
            if minutes_since_last < config.TRADE_INTERVAL_MINUTES:
                logger.debug(f"Waiting {config.TRADE_INTERVAL_MINUTES - minutes_since_last:.0f}m before next trade")
                return
        
        # Run strategy analysis
        signal = await self.strategy_engine.analyze(sol_data)
        
        if not signal:
            logger.info("\U0001f4c9 No signal detected")
            add_signal({'type': 'scan', 'reason': 'No signal detected'})
            return
        
        logger.info(f"\U0001f4ca Signal detected: {signal['direction'].upper()} from {signal['strategy']}")
        add_signal({
            'type': 'detected',
            'direction': signal['direction'],
            'strategy': signal['strategy'],
            'reason': f"Raw signal from {signal['strategy']}"
        })
        
        # Apply filters
        filter_result = await self.filter_manager.evaluate_signal(signal, sol_data)
        update_filter_stats(filter_result.get('stats', {}))
        
        if not filter_result['approved']:
            logger.info(f"\u274c Signal rejected: {filter_result['reason']}")
            add_signal({
                'type': 'rejected',
                'direction': signal['direction'],
                'reason': filter_result['reason']
            })
            return
        
        logger.info(f"\u2705 Signal approved (score: {filter_result.get('score', 0):.0f})")
        add_signal({
            'type': 'approved',
            'direction': signal['direction'],
            'reason': f"Filter score: {filter_result.get('score', 0):.0f}"
        })
        
        # Calculate position size
        position_size = await self.risk_manager.calculate_position_size(
            current_price,
            signal.get('stop_loss', current_price * 0.98)
        )
        
        if position_size <= 0:
            logger.warning("\u26a0\ufe0f  Position size too small")
            return
        
        # Execute trade
        logger.info(f"\U0001f4b5 Executing {signal['direction'].upper()} trade...")
        add_signal({
            'type': 'entry',
            'direction': signal['direction'],
            'strategy': signal['strategy'],
            'reason': f"Size: {position_size}, Entry: ${current_price:.2f}"
        })
        
        order_result = await self.order_manager.execute_entry(
            symbol=config.TRADING_SYMBOL,
            side=signal['direction'],
            size=position_size,
            entry_price=current_price,
            stop_loss=signal.get('stop_loss'),
            take_profit=signal.get('take_profit')
        )
        
        if order_result['success']:
            logger.info(f"\u2705 Trade executed: {order_result.get('order_id', 'N/A')}")
            self.daily_trades += 1
            self.last_trade_time = datetime.now()
            
            add_trade({
                'symbol': config.TRADING_SYMBOL,
                'side': signal['direction'],
                'entry_price': current_price,
                'size': position_size,
                'strategy': signal['strategy'],
                'pnl': 0,  # Will be updated on close
                'exit_price': 0
            })
        else:
            logger.error(f"\u274c Trade failed: {order_result.get('error', 'Unknown')}")
            add_error(f"Trade failed: {order_result.get('error', 'Unknown')}")


async def main():
    """Main entry point"""
    global shutdown_flag
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Print banner
    print("\n" + "="*50)
    print("   SupeQuant Elite Trading System v2.0")
    print("   SOL-USDT Perpetual | Heavy Filtering")
    print("="*50 + "\n")
    
    # Start dashboard in background thread
    if config.DASHBOARD_ENABLED:
        dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
        dashboard_thread.start()
        await asyncio.sleep(1)  # Give dashboard time to start
    
    # Initialize and run bot
    bot = TradingBot()
    
    try:
        await bot.initialize()
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        add_error(f"Fatal: {e}")
    finally:
        set_bot_status('stopped')
        logger.info("\n\U0001f44b Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
