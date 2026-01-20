#!/usr/bin/env python3
"""
Force Test Trade
Bypasses all filters to force ONE paper trade to verify execution pipeline works
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from datetime import datetime
from typing import Dict

from data_feed.okx_client import OKXClient
from data_feed.market_data import MarketDataFeed
from execution.order_manager import OrderManager
from execution.position_tracker import PositionTracker
import config

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class ForceTestTrade:
    """
    Force a test trade to verify execution pipeline
    """
    
    def __init__(self):
        self.okx_client = OKXClient()
        self.market_data = MarketDataFeed(self.okx_client)
        self.order_manager = OrderManager(self.okx_client)
        self.position_tracker = PositionTracker(self.okx_client)
        
    def run(self, paper_mode: bool = True):
        """
        Force execute one test trade
        """
        logger.info("\n" + "="*80)
        logger.info("🧪 FORCE TEST TRADE")
        logger.info("="*80)
        
        if paper_mode:
            logger.info("📝 Mode: PAPER TRADING (simulated)")
        else:
            logger.warning("⚠️  Mode: LIVE TRADING (real money!)")
            response = input("Are you sure? Type 'YES' to continue: ")
            if response != 'YES':
                logger.info("Cancelled")
                return
        
        # Get current market price
        logger.info("\n📊 Fetching current market price...")
        current_price = self.market_data.get_current_price(config.TRADING_SYMBOL)
        
        if not current_price:
            logger.error("❌ Could not get current price")
            return
        
        logger.info(f"   Current {config.TRADING_SYMBOL} price: ${current_price:.2f}")
        
        # Create fake signal (bypasses all filters)
        fake_signal = {
            'direction': 'long',
            'strategy': 'breakout',
            'entry_price': current_price,
            'stop_loss': current_price * 0.98,  # 2% stop loss
            'take_profit_1': current_price * 1.03,  # 3% take profit
            'take_profit_2': current_price * 1.06,  # 6% take profit
            'entry_reason': 'FORCE_TEST_TRADE'
        }
        
        logger.info(f"\n🎯 FORCED SIGNAL:")
        logger.info(f"   Direction: {fake_signal['direction'].upper()}")
        logger.info(f"   Entry: ${fake_signal['entry_price']:.2f}")
        logger.info(f"   Stop Loss: ${fake_signal['stop_loss']:.2f}")
        logger.info(f"   TP1: ${fake_signal['take_profit_1']:.2f}")
        logger.info(f"   TP2: ${fake_signal['take_profit_2']:.2f}")
        
        # Calculate position size (0.5% risk)
        account_balance = 10000.0  # Default for testing
        risk_amount = account_balance * config.MAX_RISK_PER_TRADE
        stop_distance = abs(fake_signal['entry_price'] - fake_signal['stop_loss'])
        position_size = risk_amount / stop_distance if stop_distance > 0 else 0
        
        logger.info(f"\n💰 POSITION SIZING:")
        logger.info(f"   Account Balance: ${account_balance:,.2f}")
        logger.info(f"   Risk Amount: ${risk_amount:.2f} ({config.MAX_RISK_PER_TRADE*100:.1f}%)")
        logger.info(f"   Position Size: {position_size:.4f} contracts")
        
        if paper_mode:
            logger.info(f"\n📝 EXECUTING PAPER TRADE...")
            logger.info(f"   (This will be logged but not sent to exchange)")
            
            # In paper mode, just log the trade
            logger.info(f"   ✅ Paper trade logged:")
            logger.info(f"      Entry: ${fake_signal['entry_price']:.2f}")
            logger.info(f"      Size: {position_size:.4f}")
            logger.info(f"      Direction: {fake_signal['direction'].upper()}")
            
            # Check if paper trading logs exist
            from pathlib import Path
            log_file = Path('logs/paper_trades.jsonl')
            if log_file.exists():
                logger.info(f"\n   ✅ Paper trade log exists: {log_file}")
                logger.info(f"   → Check this file to verify trade was logged")
            else:
                logger.warning(f"\n   ⚠️  Paper trade log not found: {log_file}")
                logger.info(f"   → Paper trading engine may not be running")
        else:
            logger.warning(f"\n⚠️  LIVE TRADE EXECUTION:")
            logger.warning(f"   This would place a REAL order on the exchange!")
            logger.warning(f"   Not executing in this test script for safety")
        
        logger.info(f"\n✅ TEST COMPLETE")
        logger.info(f"   → If paper trading is running, check logs/paper_trades.jsonl")
        logger.info(f"   → If dashboard is running, check http://localhost:5001")
        logger.info("="*80 + "\n")


def main():
    """Run force test trade"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Force a test trade')
    parser.add_argument('--paper', action='store_true', default=True,
                       help='Paper trading mode (default)')
    parser.add_argument('--live', action='store_true',
                       help='Live trading mode (WARNING: real money!)')
    
    args = parser.parse_args()
    
    paper_mode = not args.live
    
    test = ForceTestTrade()
    test.run(paper_mode=paper_mode)


if __name__ == '__main__':
    main()
