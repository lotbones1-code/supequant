"""
Diagnostic Tool - Why Are We Not Getting Trades?
Shows exactly which filters are rejecting signals
"""

import time
import logging
from datetime import datetime
from typing import Dict, List

# Import modules
from utils.logger import setup_logging
from data_feed import OKXClient, MarketDataFeed
from filters import FilterManager
from strategy import StrategyManager
from risk import RiskManager
from execution import PositionTracker

import config

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

class DiagnosticTool:
    """
    Analyzes market data and shows why trades aren't happening
    """

    def __init__(self):
        logger.info("🔍 Initializing Diagnostic Tool")
        
        self.okx_client = OKXClient()
        self.market_data = MarketDataFeed(self.okx_client)
        self.filter_manager = FilterManager()
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager(self.okx_client)
        self.position_tracker = PositionTracker(self.okx_client)
        
        self.timeframes = [
            config.MICRO_TIMEFRAME,
            config.LTF_TIMEFRAME,
            config.MTF_TIMEFRAME,
            config.HTF_TIMEFRAME
        ]
        
        self.stats = {
            'signals_generated': 0,
            'signals_rejected': 0,
            'filter_failures': {},
            'cycle_count': 0
        }
        
        logger.info("✅ Diagnostic Tool Ready")

    def run(self, cycles: int = 10):
        """
        Run diagnostic for N cycles
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"🔍 DIAGNOSTIC MODE - Running {cycles} cycles")
        logger.info(f"{'='*70}\n")
        
        for cycle in range(cycles):
            self.stats['cycle_count'] += 1
            logger.info(f"\n{'─'*70}")
            logger.info(f"CYCLE #{cycle + 1} - {datetime.now()}")
            logger.info(f"{'─'*70}")
            
            self._analyze_cycle()
            
            time.sleep(30)  # Wait 30 seconds between cycles
        
        self._print_final_report()

    def _analyze_cycle(self):
        """
        Single diagnostic cycle
        """
        try:
            # Get market data
            logger.info("📊 Fetching market data...")
            sol_market_state = self.market_data.get_market_state(
                config.TRADING_SYMBOL,
                self.timeframes
            )
            
            if not sol_market_state:
                logger.error("❌ Could not fetch SOL market data")
                return
            
            # Get BTC data for correlation
            btc_market_state = None
            if hasattr(config, 'REFERENCE_SYMBOL'):
                btc_market_state = self.market_data.get_market_state(
                    config.REFERENCE_SYMBOL,
                    self.timeframes
                )
            
            # Show current market conditions
            self._show_market_conditions(sol_market_state, btc_market_state)
            
            # Check for signals
            signal = self.strategy_manager.analyze_market(sol_market_state)
            
            if not signal:
                logger.warning("❌ NO SIGNAL GENERATED")
                return
            
            logger.info(f"\n🎯 SIGNAL DETECTED: {signal['strategy'].upper()} - {signal['direction'].upper()}")
            self.stats['signals_generated'] += 1
            
            # Show signal details
            logger.info(f"   Entry: ${signal['entry_price']:.2f}")
            logger.info(f"   Stop Loss: ${signal['stop_loss']:.2f}")
            logger.info(f"   TP1: ${signal['take_profit_1']:.2f}")
            logger.info(f"   TP2: ${signal['take_profit_2']:.2f}")
            
            # Run filters with detailed feedback
            logger.info(f"\n🔍 Running filter checks...")
            filters_passed, filter_results = self.filter_manager.check_all(
                sol_market_state,
                signal['direction'],
                signal['strategy'],
                btc_market_state
            )
            
            if filters_passed:
                logger.info(f"\n✅ ALL FILTERS PASSED - TRADE WOULD EXECUTE")
            else:
                logger.warning(f"\n❌ SIGNAL REJECTED BY FILTERS")
                self.stats['signals_rejected'] += 1
                
                failed_filters = filter_results.get('failed_filters', [])
                logger.warning(f"   Failed filters: {', '.join(failed_filters)}")
                
                # Track which filters are blocking
                for failed_filter in failed_filters:
                    if failed_filter not in self.stats['filter_failures']:
                        self.stats['filter_failures'][failed_filter] = 0
                    self.stats['filter_failures'][failed_filter] += 1
                
                # Show details for each failed filter
                if 'details' in filter_results:
                    for filter_name, details in filter_results['details'].items():
                        if not details.get('passed', True):
                            logger.warning(f"\n   ⚠️  {filter_name}:")
                            if 'reason' in details:
                                logger.warning(f"      Reason: {details['reason']}")
                            if 'value' in details:
                                logger.warning(f"      Value: {details['value']}")
                            if 'threshold' in details:
                                logger.warning(f"      Threshold: {details['threshold']}")
        
        except Exception as e:
            logger.error(f"❌ Error in diagnostic cycle: {e}", exc_info=True)

    def _show_market_conditions(self, sol_data: Dict, btc_data: Dict = None):
        """
        Display current market conditions
        """
        logger.info("\n📈 SOL Market Conditions:")
        
        if 'current_candle' in sol_data:
            candle = sol_data['current_candle']
            logger.info(f"   Current Price: ${candle.get('close', 'N/A'):.2f}")
            logger.info(f"   24h High: ${candle.get('high_24h', 'N/A'):.2f}")
            logger.info(f"   24h Low: ${candle.get('low_24h', 'N/A'):.2f}")
        
        if 'indicators' in sol_data:
            ind = sol_data['indicators']
            logger.info(f"   ATR (5m): {ind.get('atr_5m', 'N/A'):.4f}")
            logger.info(f"   RSI (5m): {ind.get('rsi_5m', 'N/A'):.2f}")
            logger.info(f"   Volume: {ind.get('volume_24h', 'N/A'):.0f}")
        
        if btc_data:
            logger.info("\n📉 BTC Market Conditions:")
            if 'current_candle' in btc_data:
                candle = btc_data['current_candle']
                logger.info(f"   Current Price: ${candle.get('close', 'N/A'):.2f}")
            if 'indicators' in btc_data:
                ind = btc_data['indicators']
                logger.info(f"   ATR (5m): {ind.get('atr_5m', 'N/A'):.4f}")
                logger.info(f"   RSI (5m): {ind.get('rsi_5m', 'N/A'):.2f}")

    def _print_final_report(self):
        """
        Print diagnostic summary
        """
        logger.info(f"\n\n{'='*70}")
        logger.info(f"📊 DIAGNOSTIC REPORT")
        logger.info(f"{'='*70}")
        
        logger.info(f"\n📈 Signal Generation:")
        logger.info(f"   Total cycles: {self.stats['cycle_count']}")
        logger.info(f"   Signals generated: {self.stats['signals_generated']}")
        logger.info(f"   Signals rejected: {self.stats['signals_rejected']}")
        
        if self.stats['signals_generated'] > 0:
            reject_pct = (self.stats['signals_rejected'] / self.stats['signals_generated']) * 100
            logger.info(f"   Rejection rate: {reject_pct:.1f}%")
        
        logger.info(f"\n🔍 Filter Failures:")
        if self.stats['filter_failures']:
            for filter_name, count in sorted(self.stats['filter_failures'].items(), key=lambda x: x[1], reverse=True):
                logger.info(f"   {filter_name}: {count} times")
        else:
            logger.info(f"   None (no signals were rejected by filters)")
        
        logger.info(f"\n💡 Recommendations:")
        
        if self.stats['signals_generated'] == 0:
            logger.info(f"   • Strategy is not generating any signals")
            logger.info(f"   • Check: Market conditions don't match strategy logic")
            logger.info(f"   • Try: Lower timeframe settings or adjust thresholds")
        elif self.stats['signals_rejected'] == 0:
            logger.info(f"   ✅ All signals are passing filters!")
            logger.info(f"   • Trades should be executing (check execution engine)")
        else:
            # Find the top filter that's blocking trades
            top_blocker = max(self.stats['filter_failures'].items(), key=lambda x: x[1])[0]
            logger.info(f"   • Main blocker: {top_blocker} ({self.stats['filter_failures'][top_blocker]} rejections)")
            logger.info(f"   • Consider: Relaxing {top_blocker} threshold slightly")
            logger.info(f"   • Or: Check if market conditions match filter requirements")
        
        logger.info(f"\n{'='*70}\n")

def main():
    """
    Run diagnostic
    """
    tool = DiagnosticTool()
    
    # Run for 10 cycles (5 minutes total)
    tool.run(cycles=10)

if __name__ == "__main__":
    main()
