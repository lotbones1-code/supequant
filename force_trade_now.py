#!/usr/bin/env python3
"""
Force Trade Now
Safely executes a trade through the normal pipeline with safety checks
Bypasses filters but respects risk management
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from datetime import datetime
from typing import Dict

from utils.logger import setup_logging
from data_feed import OKXClient, MarketDataFeed
from risk import RiskManager
from execution import OrderManager, PositionTracker
from data_feed.indicators import TechnicalIndicators
import config

setup_logging()
logger = logging.getLogger(__name__)


class ForceTradeNow:
    """
    Force a trade through normal execution pipeline
    Bypasses filters but respects risk management
    """
    
    def __init__(self):
        self.okx_client = OKXClient()
        self.market_data = MarketDataFeed(self.okx_client)
        self.risk_manager = RiskManager(self.okx_client)
        self.order_manager = OrderManager(self.okx_client)
        self.position_tracker = PositionTracker(self.okx_client)
        self.indicators = TechnicalIndicators()
        
    def run(self):
        """
        Force execute one trade with safety checks
        """
        logger.info("\n" + "="*80)
        logger.info("⚡ FORCE TRADE NOW")
        logger.info("="*80)
        
        # SAFETY CHECK 1: Mode verification and warning
        is_live = not config.OKX_SIMULATED
        mode_str = "LIVE" if is_live else "SIMULATED"
        
        if is_live:
            logger.warning("\n" + "🔴" * 40)
            logger.warning("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
            logger.warning("🔴" * 40)
            logger.warning(f"   Mode: {mode_str}")
            logger.warning("   This will execute a REAL trade with REAL money!")
            logger.warning("   All risk management rules still apply.")
            logger.warning("🔴" * 40 + "\n")
        else:
            logger.info(f"✅ Safety Check 1: SIMULATED MODE (safe)")
            logger.info(f"   Current mode: {mode_str}")
        
        # SAFETY CHECK 2: Check risk manager and trading balance
        logger.info("\n📊 Checking risk manager...")
        
        # Get USDT trading balance (not total equity)
        trading_balance = self.risk_manager.get_trading_balance()
        if not trading_balance or trading_balance <= 0:
            logger.error("❌ Could not get trading balance")
            return
        
        # Also get total equity for reference
        account_balance = trading_balance  # Use trading balance for position sizing
        
        logger.info(f"✅ Safety Check 2: USDT Trading Balance: ${trading_balance:.2f}")
        logger.info(f"   (This is your available USDT for SOL trading)")
        
        # Check if can trade - get number of open positions first
        open_positions = self.position_tracker.get_open_positions()
        num_open_positions = len(open_positions) if open_positions else 0
        can_trade, reason = self.risk_manager.check_can_trade(num_open_positions)
        if not can_trade:
            logger.error(f"❌ Risk manager blocked trade: {reason}")
            return
        
        logger.info(f"✅ Safety Check 3: Risk manager allows trading (open positions: {num_open_positions})")
        
        # Get current market data
        logger.info("\n📊 Fetching market data...")
        current_price = self.market_data.get_current_price(config.TRADING_SYMBOL)
        if not current_price:
            logger.error("❌ Could not get current price")
            return
        
        logger.info(f"   Current {config.TRADING_SYMBOL} price: ${current_price:.2f}")
        
        # Get ATR for proper stop loss calculation
        logger.info("   Fetching ATR data...")
        # Use same timeframes as main system
        timeframes_list = [
            config.MICRO_TIMEFRAME,
            config.LTF_TIMEFRAME,
            config.MTF_TIMEFRAME,
            config.HTF_TIMEFRAME
        ]
        market_state = self.market_data.get_market_state(config.TRADING_SYMBOL, timeframes_list)
        if not market_state:
            logger.error("❌ Could not get market state")
            return
        
        # Get ATR from 15m timeframe (standard)
        timeframes = market_state.get('timeframes', {})
        mtf_data = timeframes.get('15m', {})
        atr_data = mtf_data.get('atr', {})
        current_atr = atr_data.get('current', None)
        
        if not current_atr:
            logger.warning("⚠️  Could not get ATR, using 2% default stop loss")
            stop_loss = current_price * 0.98
        else:
            # Use ATR-based stop loss (1.5x ATR as per config)
            stop_distance = current_atr * config.ATR_STOP_MULTIPLIER
            stop_loss = current_price - stop_distance  # For long position
            logger.info(f"   ATR: ${current_atr:.2f}")
            logger.info(f"   Stop distance: ${stop_distance:.2f} ({config.ATR_STOP_MULTIPLIER}x ATR)")
        
        # Calculate take profits based on risk/reward ratios
        risk_amount = abs(current_price - stop_loss)
        tp1 = current_price + (risk_amount * config.TP1_RR_RATIO)
        tp2 = current_price + (risk_amount * config.TP2_RR_RATIO)
        
        # Create signal (bypasses filters)
        signal = {
            'direction': 'long',
            'strategy': 'forced_trade',
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'risk_amount': risk_amount,
            'entry_reason': 'FORCED_TRADE_NOW'
        }
        
        # Check for aggressive TP if growth mode enabled
        if config.GROWTH_MODE_ENABLED and config.GROWTH_AGGRESSIVE_TP:
            aggressive_tp = self.risk_manager.get_aggressive_tp_targets(signal)
            if aggressive_tp:
                signal['take_profit_3'] = aggressive_tp.get('tp3')
                signal['tp_split'] = config.GROWTH_TP_SPLIT
        
        logger.info(f"\n🎯 FORCED SIGNAL:")
        logger.info(f"   Direction: {signal['direction'].upper()}")
        logger.info(f"   Entry: ${signal['entry_price']:.2f}")
        logger.info(f"   Stop Loss: ${signal['stop_loss']:.2f} ({((stop_loss/current_price - 1) * 100):.2f}%)")
        logger.info(f"   TP1: ${signal['take_profit_1']:.2f} ({config.TP1_RR_RATIO}:1 RR)")
        logger.info(f"   TP2: ${signal['take_profit_2']:.2f} ({config.TP2_RR_RATIO}:1 RR)")
        if signal.get('take_profit_3'):
            logger.info(f"   TP3: ${signal['take_profit_3']:.2f} ({config.GROWTH_TP3_RR}:1 RR)")
        
        # Calculate position size using risk manager
        logger.info(f"\n💰 Calculating position size...")
        position_size, size_details = self.risk_manager.calculate_position_size(
            signal, account_balance
        )
        
        logger.info(f"   Position Size: {position_size:.4f} contracts")
        logger.info(f"   Notional Value: ${size_details['notional_value']:.2f}")
        logger.info(f"   Risk Amount: ${size_details['risk_per_trade_usd']:.2f} ({size_details['risk_per_trade_pct']:.2f}%)")
        
        # Final confirmation
        trading_type = "SPOT" if config.TRADING_MODE == "spot" else "PERPETUAL"
        logger.info(f"\n{'='*80}")
        logger.info(f"⚠️  READY TO EXECUTE:")
        logger.info(f"{'='*80}")
        logger.info(f"   Account Mode: {mode_str}")
        logger.info(f"   Trading Type: {trading_type} (with spot fallback if needed)")
        logger.info(f"   Symbol: {config.TRADING_SYMBOL}")
        logger.info(f"   Direction: {signal['direction'].upper()}")
        logger.info(f"   Size: {position_size:.4f} contracts")
        logger.info(f"   Entry: ${signal['entry_price']:.2f}")
        logger.info(f"   Stop Loss: ${signal['stop_loss']:.2f}")
        logger.info(f"   TP1: ${signal['take_profit_1']:.2f}")
        logger.info(f"   TP2: ${signal['take_profit_2']:.2f}")
        logger.info(f"   Notional Value: ${size_details['notional_value']:.2f}")
        logger.info(f"   Risk Amount: ${size_details['risk_per_trade_usd']:.2f} ({size_details['risk_per_trade_pct']:.2f}%)")
        logger.info(f"{'='*80}")
        
        # Require explicit confirmation for live trades
        if is_live:
            logger.warning("\n🔴 LIVE TRADE CONFIRMATION REQUIRED 🔴")
            logger.warning("   This will execute a REAL trade with REAL money!")
            logger.warning("   Type 'EXECUTE' to proceed, or anything else to cancel:")
            confirmation = input("   > ").strip().upper()
            
            if confirmation != 'EXECUTE':
                logger.info("\n❌ Trade cancelled by user")
                return
            
            logger.info("\n✅ Confirmation received - Executing LIVE trade...")
        else:
            logger.info("\n📝 SIMULATED MODE - Proceeding with paper trade...")
        
        # Execute trade using normal pipeline
        logger.info(f"\n🚀 Executing trade through normal pipeline...")
        
        try:
            # Clear session order tracking for fresh trade
            self.order_manager.clear_session_orders()
            
            # Place market order
            entry_order = self.order_manager.place_market_order(signal, position_size)
            
            if not entry_order:
                logger.error("❌ Failed to place entry order")
                return
            
            logger.info(f"✅ Entry order placed: {entry_order.get('order_id', 'N/A')}")
            
            # Create position
            position = self.position_tracker.create_position(signal, entry_order)
            logger.info(f"✅ Position created: {position['position_id']}")
            
            # Place stop loss
            stop_order = self.order_manager.place_stop_loss(position, signal['stop_loss'])
            if stop_order:
                position['orders']['stop_loss'] = stop_order.get('order_id')
                logger.info(f"✅ Stop loss order placed: {stop_order.get('order_id', 'N/A')}")
            
            # Place take profits
            # IMPORTANT: Use actual entry size, not requested size
            # (spot fallback may have adjusted the size)
            actual_size = entry_order.get('size', position_size)
            if actual_size != position_size:
                logger.info(f"   📝 Using actual entry size ({actual_size:.4f}) for TP calculations")
            
            tp_split = signal.get('tp_split', {1: 0.5, 2: 0.5})
            
            # TP1
            tp1_size = actual_size * tp_split.get(1, 0.5)
            tp1_order = self.order_manager.place_take_profit(position, signal['take_profit_1'], tp1_size)
            if tp1_order:
                position['orders']['take_profit_1'] = tp1_order.get('order_id')
                logger.info(f"✅ TP1 order placed: {tp1_order.get('order_id', 'N/A')}")
            
            # TP2
            tp2_size = actual_size * tp_split.get(2, 0.5)
            tp2_order = self.order_manager.place_take_profit(position, signal['take_profit_2'], tp2_size)
            if tp2_order:
                position['orders']['take_profit_2'] = tp2_order.get('order_id')
                logger.info(f"✅ TP2 order placed: {tp2_order.get('order_id', 'N/A')}")
            
            # TP3 (if enabled)
            if signal.get('take_profit_3'):
                tp3_size = actual_size * tp_split.get(3, 0.0)
                if tp3_size > 0:
                    tp3_order = self.order_manager.place_take_profit(position, signal['take_profit_3'], tp3_size)
                    if tp3_order:
                        position['orders']['take_profit_3'] = tp3_order.get('order_id')
                        logger.info(f"✅ TP3 order placed: {tp3_order.get('order_id', 'N/A')}")
            
            logger.info("\n" + "="*80)
            logger.info("✅ TRADE EXECUTED SUCCESSFULLY")
            logger.info(f"Position ID: {position['position_id']}")
            logger.info(f"Entry: ${signal['entry_price']:.2f}")
            logger.info(f"Stop Loss: ${signal['stop_loss']:.2f}")
            logger.info(f"Take Profit 1: ${signal['take_profit_1']:.2f}")
            logger.info(f"Take Profit 2: ${signal['take_profit_2']:.2f}")
            if signal.get('take_profit_3'):
                logger.info(f"Take Profit 3: ${signal['take_profit_3']:.2f}")
            logger.info("="*80 + "\n")
            
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}", exc_info=True)
            return


def main():
    """Run force trade"""
    try:
        force_trade = ForceTradeNow()
        force_trade.run()
    except KeyboardInterrupt:
        logger.info("\n⚠️  Cancelled by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)


if __name__ == '__main__':
    main()
