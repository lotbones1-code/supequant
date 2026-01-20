#!/usr/bin/env python3
"""
Production Force Trade Script
Uses the ProductionOrderManager for clean trade execution

Features:
- Auto cleanup before trade (cancels orders, sells SOL)
- Proper position sizing for spot trading
- Smart TP placement with virtual fallback
- Background monitoring for SL and virtual TPs
"""

import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Imports
import config
from data_feed.okx_client import OKXClient
from data_feed.market_data import MarketDataFeed
from risk.risk_manager import RiskManager
from execution.production_manager import ProductionOrderManager


class ProductionForceTrade:
    """Production-grade force trade execution"""
    
    def __init__(self):
        logger.info("="*60)
        logger.info("🚀 PRODUCTION FORCE TRADE")
        logger.info("="*60)
        
        # Initialize components
        self.client = OKXClient()
        self.market_data = MarketDataFeed(self.client)
        self.risk_manager = RiskManager(self.client)
        self.production_manager = ProductionOrderManager(self.client)
        
        # Check mode
        self.is_live = not config.OKX_SIMULATED
        mode_str = "🔴 LIVE" if self.is_live else "🟢 SIMULATED"
        logger.info(f"Mode: {mode_str}")
    
    def run(self):
        """Execute a production trade"""
        
        # Safety warning for live trading
        if self.is_live:
            logger.warning("\n" + "🔴"*20)
            logger.warning("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
            logger.warning("🔴"*20 + "\n")
        
        # Step 1: Prepare account (cleanup)
        logger.info("\n📋 STEP 1: Preparing account...")
        symbol = config.SPOT_SYMBOL  # Use spot for OKX US
        
        ready = self.production_manager.prepare_for_trade(symbol)
        if not ready:
            logger.error("❌ Account not ready for trading")
            return
        
        # Step 2: Get market data
        logger.info("\n📊 STEP 2: Getting market data...")
        current_price = self.market_data.get_current_price(symbol)
        if not current_price:
            logger.error("❌ Could not get current price")
            return
        logger.info(f"   Current {symbol} price: ${current_price:.2f}")
        
        # Step 3: Create signal
        logger.info("\n🎯 STEP 3: Creating trade signal...")
        
        # Use 2% stop loss
        stop_loss_pct = 0.02
        stop_loss = current_price * (1 - stop_loss_pct)
        risk_per_share = current_price - stop_loss
        
        # Calculate TPs based on risk/reward
        tp1 = current_price + (risk_per_share * config.TP1_RR_RATIO)  # 1.5:1
        tp2 = current_price + (risk_per_share * config.TP2_RR_RATIO)  # 2.5:1
        
        signal = {
            'direction': 'long',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'strategy': 'force_trade_production',
            'confidence': 0.7
        }
        
        logger.info(f"   Direction: LONG")
        logger.info(f"   Entry: ${current_price:.2f}")
        logger.info(f"   Stop Loss: ${stop_loss:.2f} (-{stop_loss_pct*100:.1f}%)")
        logger.info(f"   TP1: ${tp1:.2f} ({config.TP1_RR_RATIO}:1 RR)")
        logger.info(f"   TP2: ${tp2:.2f} ({config.TP2_RR_RATIO}:1 RR)")
        
        # Step 4: Calculate position size
        logger.info("\n💰 STEP 4: Calculating position size...")
        usdt_balance = self.client.get_trading_balance('USDT')
        if not usdt_balance or usdt_balance < 10:
            logger.error(f"❌ Insufficient USDT: ${usdt_balance or 0:.2f}")
            return
        
        # For spot: use 95% of balance
        max_size = (usdt_balance * 0.95) / current_price
        logger.info(f"   USDT Balance: ${usdt_balance:.2f}")
        logger.info(f"   Max Position: {max_size:.4f} SOL")
        
        # Step 5: Confirmation
        logger.info("\n" + "="*60)
        logger.info("⚠️  READY TO EXECUTE")
        logger.info("="*60)
        logger.info(f"   Mode: {'LIVE' if self.is_live else 'SIMULATED'}")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Direction: LONG")
        logger.info(f"   Max Size: {max_size:.4f} SOL (~${usdt_balance:.2f})")
        logger.info(f"   Entry: ${current_price:.2f}")
        logger.info(f"   Stop Loss: ${stop_loss:.2f}")
        logger.info(f"   TP1: ${tp1:.2f} (50%)")
        logger.info(f"   TP2: ${tp2:.2f} (50%)")
        logger.info("="*60)
        
        if self.is_live:
            logger.warning("\n🔴 LIVE TRADE CONFIRMATION REQUIRED 🔴")
            logger.warning("   Type 'EXECUTE' to proceed:")
            confirmation = input("   > ").strip().upper()
            
            if confirmation != 'EXECUTE':
                logger.info("❌ Trade cancelled")
                return
        
        # Step 6: Execute trade
        logger.info("\n🚀 STEP 5: Executing trade...")
        position = self.production_manager.execute_trade(signal, max_size)
        
        if not position:
            logger.error("❌ Trade execution failed")
            return
        
        logger.info("\n" + "="*60)
        logger.info("✅ TRADE COMPLETE")
        logger.info("="*60)
        logger.info(f"   Position ID: {position.position_id}")
        logger.info(f"   Entry: ${position.entry_price:.2f}")
        logger.info(f"   Size: {position.actual_entry_size:.4f} SOL")
        logger.info(f"   Stop Loss: ${position.stop_loss:.2f} (Virtual)")
        logger.info(f"   TP1: ${position.tp1_price:.2f} ({'Virtual' if position.tp1_is_virtual else 'Limit'})")
        logger.info(f"   TP2: ${position.tp2_price:.2f} ({'Virtual' if position.tp2_is_virtual else 'Limit'})")
        logger.info("="*60)
        
        # If we have virtual orders, keep running to monitor
        if position.tp1_is_virtual or position.tp2_is_virtual or position.sl_is_virtual:
            logger.info("\n🔍 Monitoring virtual orders...")
            logger.info("   Press Ctrl+C to stop monitoring (position will remain open)")
            
            try:
                while position.state.value in ['active', 'tp1_filled']:
                    import time
                    time.sleep(5)
                    
                    # Get current price and show status
                    price = self.market_data.get_current_price(symbol)
                    if price:
                        pnl = (price - position.entry_price) * position.actual_entry_size
                        pnl_pct = ((price / position.entry_price) - 1) * 100
                        logger.info(f"   📊 Price: ${price:.2f} | PnL: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                        
            except KeyboardInterrupt:
                logger.info("\n⏹️  Monitoring stopped")
                logger.info("   Position remains open - manage manually on OKX")
        
        logger.info("\n✅ Done!")


def main():
    """Main entry point"""
    try:
        trader = ProductionForceTrade()
        trader.run()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
