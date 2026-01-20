#!/usr/bin/env python3
"""
Filter Tuning Tool
Finds optimal filter thresholds that would have allowed profitable trades
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from datetime import datetime, timedelta
from typing import Dict, List
import yaml

from backtesting.historical_data_loader import HistoricalDataLoader
from backtesting.backtest_engine import BacktestEngine
import config

logging.basicConfig(level=logging.WARNING)  # Reduce noise
logger = logging.getLogger(__name__)


class FilterTuner:
    """
    Tune filter thresholds to find balance between quality and frequency
    """
    
    def __init__(self):
        self.data_loader = HistoricalDataLoader()
        
    def run(self, days: int = 30):
        """
        Analyze historical data and suggest filter thresholds
        """
        logger.info("\n" + "="*80)
        logger.info("🔧 FILTER TUNING TOOL")
        logger.info("="*80)
        
        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        logger.info(f"\n📅 Analyzing: {start_date} to {end_date} ({days} days)")
        logger.info(f"📊 Loading data...\n")
        
        # Load data
        sol_data = self.data_loader.load_data(
            symbol=config.TRADING_SYMBOL,
            start_date=start_date,
            end_date=end_date,
            timeframes=['15m'],
            force_refresh=False
        )
        
        btc_data = self.data_loader.load_data(
            symbol=config.REFERENCE_SYMBOL,
            start_date=start_date,
            end_date=end_date,
            timeframes=['15m'],
            force_refresh=False
        )
        
        if not sol_data or not btc_data:
            logger.error("❌ Failed to load data")
            return
        
        # Run backtest with current filters
        logger.info("🎯 Running backtest with current filters...\n")
        engine = BacktestEngine(initial_capital=10000.0)
        results = engine.run(sol_data, btc_data, start_date, end_date)
        
        if not results:
            logger.error("❌ Backtest failed")
            return
        
        # Analyze results
        self._analyze_and_suggest(results)
        
    def _analyze_and_suggest(self, results: Dict):
        """
        Analyze backtest results and suggest filter adjustments
        """
        logger.info("\n" + "="*80)
        logger.info("📊 FILTER TUNING ANALYSIS")
        logger.info("="*80)
        
        signals = results.get('signals', {})
        trades = results.get('trades', {})
        filter_rejections = results.get('filter_rejections', {})
        
        total_signals = signals.get('total_signals', 0)
        total_trades = trades.get('total_trades', 0)
        signals_rejected = signals.get('signals_rejected', 0)
        
        logger.info(f"\n📈 CURRENT PERFORMANCE:")
        logger.info(f"   Signals Generated: {total_signals}")
        logger.info(f"   Signals Rejected: {signals_rejected}")
        logger.info(f"   Trades Executed: {total_trades}")
        
        if total_signals > 0:
            rejection_rate = (signals_rejected / total_signals) * 100
            logger.info(f"   Rejection Rate: {rejection_rate:.1f}%")
        
        logger.info(f"\n🚫 FILTER REJECTIONS:")
        for filter_name, count in sorted(filter_rejections.items(), 
                                         key=lambda x: x[1], reverse=True):
            if total_signals > 0:
                pct = (count / total_signals) * 100
                logger.info(f"   {filter_name}: {count} ({pct:.1f}%)")
        
        # Generate suggestions
        logger.info(f"\n💡 FILTER TUNING SUGGESTIONS:")
        
        if total_signals == 0:
            logger.warning(f"   ⚠️  No signals generated - strategy is the issue, not filters")
            logger.info(f"   → Focus on fixing strategy first (see debug_strategy.py)")
        elif total_trades == 0:
            logger.warning(f"   ⚠️  {total_signals} signals generated but 0 trades executed")
            logger.info(f"   → Filters are blocking all signals")
            
            # Find top blocker
            if filter_rejections:
                top_blocker = max(filter_rejections.items(), key=lambda x: x[1])[0]
                logger.info(f"\n   Main Blocker: {top_blocker}")
                self._suggest_filter_relaxation(top_blocker)
        else:
            win_rate = trades.get('win_rate', 0)
            logger.info(f"   ✅ {total_trades} trades executed with {win_rate:.1f}% win rate")
            if win_rate < 50:
                logger.info(f"   → Consider tightening filters to improve quality")
            else:
                logger.info(f"   → Performance looks good! Filters are working")
        
        # Generate relaxed config
        self._generate_relaxed_config(filter_rejections, total_signals)
        
        logger.info("\n" + "="*80 + "\n")
    
    def _suggest_filter_relaxation(self, filter_name: str):
        """Suggest how to relax a specific filter"""
        suggestions = {
            'multi_timeframe': [
                "Reduce HTF_TREND_MIN_STRENGTH from 0.3 to 0.2",
                "Reduce MTF_TREND_MIN_STRENGTH from 0.25 to 0.15",
                "Reduce TIMEFRAME_ALIGNMENT_THRESHOLD from 0.4 to 0.3"
            ],
            'market_regime': [
                "Increase ATR_MAX_PERCENTILE from 95 to 98",
                "Reduce ATR_MIN_PERCENTILE from 10 to 5",
                "Increase FUNDING_RATE_MAX from 0.001 to 0.002"
            ],
            'pattern_failure': [
                "Increase BULL_TRAP_THRESHOLD from 0.03 to 0.05",
                "Reduce LOW_LIQUIDITY_VOLUME_RATIO from 0.15 to 0.10"
            ],
            'btc_sol_correlation': [
                "Reduce BTC_SOL_MIN_CORRELATION from 0.4 to 0.3",
                "Increase BTC_SOL_DIVERGENCE_MAX from 0.25 to 0.35"
            ],
            'ai_rejection': [
                "Reduce AI_CONFIDENCE_THRESHOLD from 40 to 30"
            ],
            'macro_driver': [
                "Reduce MACRO_DRIVER_MIN_SCORE from 25 to 20"
            ]
        }
        
        if filter_name in suggestions:
            logger.info(f"\n   Suggested changes for {filter_name}:")
            for suggestion in suggestions[filter_name]:
                logger.info(f"      • {suggestion}")
    
    def _generate_relaxed_config(self, filter_rejections: Dict, total_signals: int):
        """Generate a relaxed config file"""
        logger.info(f"\n📝 Generating config_relaxed.yaml...")
        
        relaxed_config = {
            'filters': {
                'market_regime': {
                    'ATR_MIN_PERCENTILE': 5,  # Was 10
                    'ATR_MAX_PERCENTILE': 98,  # Was 95
                    'FUNDING_RATE_MAX': 0.002,  # Was 0.001
                },
                'multi_timeframe': {
                    'HTF_TREND_MIN_STRENGTH': 0.2,  # Was 0.3
                    'MTF_TREND_MIN_STRENGTH': 0.15,  # Was 0.25
                    'LTF_TREND_MIN_STRENGTH': 0.1,  # Was 0.2
                    'TIMEFRAME_ALIGNMENT_THRESHOLD': 0.3,  # Was 0.4
                },
                'pattern_failure': {
                    'BULL_TRAP_THRESHOLD': 0.05,  # Was 0.03
                    'BEAR_TRAP_THRESHOLD': 0.05,  # Was 0.03
                    'LOW_LIQUIDITY_VOLUME_RATIO': 0.10,  # Was 0.15
                },
                'btc_sol_correlation': {
                    'BTC_SOL_MIN_CORRELATION': 0.3,  # Was 0.4
                    'BTC_SOL_DIVERGENCE_MAX': 0.35,  # Was 0.25
                },
                'ai_rejection': {
                    'AI_CONFIDENCE_THRESHOLD': 30,  # Was 40
                },
                'macro_driver': {
                    'MACRO_DRIVER_MIN_SCORE': 20,  # Was 25
                }
            }
        }
        
        try:
            with open('config_relaxed.yaml', 'w') as f:
                yaml.dump(relaxed_config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"   ✅ Created config_relaxed.yaml")
            logger.info(f"   → Use these values to relax filters and allow more trades")
        except Exception as e:
            logger.error(f"   ❌ Failed to create config: {e}")


def main():
    """Run filter tuner"""
    tuner = FilterTuner()
    tuner.run(days=30)


if __name__ == '__main__':
    main()
