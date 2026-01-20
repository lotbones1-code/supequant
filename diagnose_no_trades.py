#!/usr/bin/env python3
"""
Diagnostic Tool - Why Are We Not Getting Trades?
Shows exactly which filters are rejecting signals and why
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

from backtesting.historical_data_loader import HistoricalDataLoader
from strategy.breakout_strategy import BreakoutStrategy
from strategy.pullback_strategy import PullbackStrategy
from filters.filter_manager import FilterManager
from data_feed.indicators import TechnicalIndicators
import config

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class TradeDiagnostic:
    """
    Comprehensive diagnostic to find why no trades are executing
    """
    
    def __init__(self):
        self.data_loader = HistoricalDataLoader()
        self.breakout_strategy = BreakoutStrategy()
        self.pullback_strategy = PullbackStrategy()
        self.filter_manager = FilterManager()
        self.indicators = TechnicalIndicators()
        
        # Statistics
        self.stats = {
            'raw_signals': 0,
            'long_signals': 0,
            'short_signals': 0,
            'breakout_signals': 0,
            'pullback_signals': 0,
            'filter_rejections': defaultdict(int),
            'filter_details': defaultdict(list),
            'signals_passed_all_filters': 0,
            'kill_switch_status': {}
        }
        
    def run(self, days: int = 30):
        """
        Run diagnostic on last N days of data
        """
        logger.info("\n" + "="*80)
        logger.info("🔍 TRADE DIAGNOSTIC REPORT")
        logger.info("="*80)
        
        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        logger.info(f"\n📅 Date Range: {start_date} to {end_date} ({days} days)")
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
        
        # Count candles
        candles_15m = sol_data.get('15m', [])
        total_candles = len(candles_15m)
        logger.info(f"✅ Loaded {total_candles} candles (15m timeframe)\n")
        
        # Process each candle
        logger.info("🔍 Analyzing signals and filters...\n")
        self._analyze_signals(sol_data, btc_data, candles_15m)
        
        # Check kill switches
        self._check_kill_switches()
        
        # Print report
        self._print_report(total_candles, days)
        
    def _analyze_signals(self, sol_data: Dict, btc_data: Dict, candles: List[Dict]):
        """
        Analyze signals and filter rejections
        """
        from backtesting.backtest_engine import BacktestEngine
        
        # Build market state for each candle (simulate backtest)
        for idx in range(50, len(candles)):  # Start at 50 to have enough history
            candle = candles[idx]
            current_time = datetime.fromtimestamp(candle['timestamp'] / 1000)
            
            # Build market state (same as backtest engine)
            sol_market_state = self._build_market_state(sol_data, idx, '15m')
            btc_market_state = self._build_market_state(btc_data, idx, '15m')
            
            if not sol_market_state or not btc_market_state:
                continue
            
            # Check for signals
            breakout_signal = self.breakout_strategy.analyze(sol_market_state)
            pullback_signal = self.pullback_strategy.analyze(sol_market_state)
            
            # Test breakout signal
            if breakout_signal:
                self.stats['raw_signals'] += 1
                self.stats['breakout_signals'] += 1
                if breakout_signal['direction'] == 'long':
                    self.stats['long_signals'] += 1
                else:
                    self.stats['short_signals'] += 1
                
                # Test filters
                self._test_filters(sol_market_state, btc_market_state, 
                                 breakout_signal, 'breakout')
            
            # Test pullback signal
            if pullback_signal:
                self.stats['raw_signals'] += 1
                self.stats['pullback_signals'] += 1
                if pullback_signal['direction'] == 'long':
                    self.stats['long_signals'] += 1
                else:
                    self.stats['short_signals'] += 1
                
                # Test filters
                self._test_filters(sol_market_state, btc_market_state,
                                 pullback_signal, 'pullback')
            
            # Progress update
            if idx % 1000 == 0:
                logger.info(f"   Processed {idx}/{len(candles)} candles... ({self.stats['raw_signals']} signals found)")
    
    def _build_market_state(self, data: Dict, current_idx: int, primary_tf: str) -> Dict:
        """
        Build market state at a specific point (same as backtest engine)
        """
        if current_idx >= len(data[primary_tf]):
            return None
        
        market_state = {
            'timeframes': {},
            'timestamp': data[primary_tf][current_idx]['timestamp']
        }
        
        # For each timeframe, get candles up to current point
        for tf_name, candles in data.items():
            current_ts = data[primary_tf][current_idx]['timestamp']
            tf_candles = [c for c in candles if c['timestamp'] <= current_ts]
            
            if not tf_candles:
                continue
            
            # Take last N candles
            lookback_map = {
                '1m': 300,
                '5m': 300,
                '15m': 200,
                '1H': 100,
                '4H': 100
            }
            lookback = lookback_map.get(tf_name, 100)
            recent_candles = tf_candles[-lookback:] if len(tf_candles) > lookback else tf_candles
            
            # Calculate indicators
            indicators = self._calculate_indicators(recent_candles)
            
            market_state['timeframes'][tf_name] = {
                'candles': recent_candles,
                'current_price': recent_candles[-1]['close'],
                **indicators
            }
        
        return market_state
    
    def _calculate_indicators(self, candles: List[Dict]) -> Dict:
        """Calculate technical indicators"""
        if len(candles) < 20:
            return {}
        
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        volumes = [c['volume'] for c in candles]
        
        indicators = {}
        
        # ATR
        atr_series = self.indicators.calculate_atr_series(highs, lows, closes, period=14)
        if atr_series:
            indicators['atr'] = {
                'atr': atr_series[-1],
                'atr_previous': atr_series[-2] if len(atr_series) > 1 else atr_series[-1]
            }
        
        # Trend
        ema_fast = self.indicators.calculate_ema(closes, period=20)
        ema_slow = self.indicators.calculate_ema(closes, period=50)
        
        if ema_fast and ema_slow:
            trend_direction = 'up' if ema_fast[-1] > ema_slow[-1] else 'down'
            trend_strength = abs(ema_fast[-1] - ema_slow[-1]) / ema_slow[-1]
            
            indicators['trend'] = {
                'trend_direction': trend_direction,
                'trend_strength': min(trend_strength * 10, 1.0),
                'ema_20': ema_fast[-1],
                'ema_50': ema_slow[-1]
            }
        
        # Volume
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
        indicators['volume'] = {
            'current_volume': volumes[-1],
            'average_volume': avg_volume,
            'volume_ratio': volumes[-1] / avg_volume if avg_volume > 0 else 1.0
        }
        
        return indicators
    
    def _test_filters(self, sol_market_state: Dict, btc_market_state: Dict,
                     signal: Dict, strategy: str):
        """
        Test each filter individually and track rejections
        """
        # Run all filters
        filters_passed, filter_results = self.filter_manager.check_all(
            sol_market_state,
            signal['direction'],
            strategy,
            btc_market_state
        )
        
        if filters_passed:
            self.stats['signals_passed_all_filters'] += 1
        else:
            # Track which filters failed
            failed_filters = filter_results.get('failed_filters', [])
            for filter_name in failed_filters:
                self.stats['filter_rejections'][filter_name] += 1
                
                # Store rejection reason
                filter_detail = filter_results.get('filter_results', {}).get(filter_name, {})
                reason = filter_detail.get('reason', 'Unknown')
                self.stats['filter_details'][filter_name].append(reason)
    
    def _check_kill_switches(self):
        """Check kill switch status"""
        from pathlib import Path
        
        kill_switch_file = Path('KILL_SWITCH.txt')
        self.stats['kill_switch_status']['file_exists'] = kill_switch_file.exists()
        
        # Check daily loss (would need to track this, but for now just note it)
        self.stats['kill_switch_status']['daily_loss'] = 'Unknown (would need trade history)'
        self.stats['kill_switch_status']['drawdown'] = 'Unknown (would need trade history)'
    
    def _print_report(self, total_candles: int, days: int):
        """
        Print comprehensive diagnostic report
        """
        logger.info("\n" + "="*80)
        logger.info("📊 DIAGNOSTIC REPORT")
        logger.info("="*80)
        
        logger.info(f"\n📈 DATA LOADED:")
        logger.info(f"   Period: {days} days")
        logger.info(f"   Total Candles: {total_candles:,}")
        logger.info(f"   Expected signals per day: ~{total_candles / days / 96:.1f} (assuming 96 candles/day for 15m)")
        
        logger.info(f"\n🎯 SIGNAL GENERATION:")
        logger.info(f"   Raw Signals Generated: {self.stats['raw_signals']}")
        logger.info(f"   Long Signals: {self.stats['long_signals']}")
        logger.info(f"   Short Signals: {self.stats['short_signals']}")
        logger.info(f"   Breakout Signals: {self.stats['breakout_signals']}")
        logger.info(f"   Pullback Signals: {self.stats['pullback_signals']}")
        
        if self.stats['raw_signals'] == 0:
            logger.warning(f"\n   ⚠️  PROBLEM: Strategy generating ZERO signals!")
            logger.warning(f"   → This is the bottleneck - no signals = no trades")
        else:
            signal_rate = (self.stats['raw_signals'] / total_candles) * 100
            logger.info(f"   Signal Rate: {signal_rate:.3f}% of candles")
        
        logger.info(f"\n🚫 FILTER REJECTION RATES:")
        if self.stats['raw_signals'] > 0:
            for filter_name, rejections in sorted(self.stats['filter_rejections'].items(), 
                                                 key=lambda x: x[1], reverse=True):
                rejection_rate = (rejections / self.stats['raw_signals']) * 100
                logger.info(f"   {filter_name}: rejected {rejections}/{self.stats['raw_signals']} ({rejection_rate:.1f}%)")
                
                # Show top rejection reasons
                reasons = self.stats['filter_details'][filter_name]
                if reasons:
                    from collections import Counter
                    top_reasons = Counter(reasons).most_common(3)
                    for reason, count in top_reasons:
                        logger.info(f"      → {reason} ({count}x)")
        else:
            logger.info(f"   No signals to filter (strategy not generating signals)")
        
        logger.info(f"\n✅ SIGNALS PASSED ALL FILTERS:")
        logger.info(f"   {self.stats['signals_passed_all_filters']} signals passed all filters")
        if self.stats['raw_signals'] > 0:
            pass_rate = (self.stats['signals_passed_all_filters'] / self.stats['raw_signals']) * 100
            logger.info(f"   Pass Rate: {pass_rate:.1f}%")
        
        logger.info(f"\n🛑 KILL-SWITCH STATUS:")
        logger.info(f"   File Kill-Switch: {'ON' if self.stats['kill_switch_status']['file_exists'] else 'OFF'}")
        logger.info(f"   Daily Loss: {self.stats['kill_switch_status']['daily_loss']}")
        logger.info(f"   Drawdown: {self.stats['kill_switch_status']['drawdown']}")
        
        # Identify bottleneck
        logger.info(f"\n🔍 BOTTLENECK ANALYSIS:")
        if self.stats['raw_signals'] == 0:
            logger.error(f"   ❌ BOTTLENECK: Strategy generating 0 signals")
            logger.error(f"   → Strategy conditions are too strict")
            logger.error(f"   → Check: Breakout consolidation range, volume requirements, volatility compression")
        elif self.stats['signals_passed_all_filters'] == 0:
            top_blocker = max(self.stats['filter_rejections'].items(), key=lambda x: x[1])[0] if self.stats['filter_rejections'] else None
            if top_blocker:
                rejection_rate = (self.stats['filter_rejections'][top_blocker] / self.stats['raw_signals']) * 100
                logger.error(f"   ❌ BOTTLENECK: Filter '{top_blocker}' rejecting {rejection_rate:.1f}% of signals")
                logger.error(f"   → This filter is blocking all trades")
        else:
            logger.info(f"   ✅ No obvious bottleneck - {self.stats['signals_passed_all_filters']} signals passed all checks")
        
        # Recommendations
        logger.info(f"\n💡 RECOMMENDATIONS:")
        if self.stats['raw_signals'] == 0:
            logger.info(f"   1. Relax strategy conditions:")
            logger.info(f"      - Increase consolidation range threshold (currently 3%)")
            logger.info(f"      - Lower volume requirement")
            logger.info(f"      - Relax volatility compression check")
            logger.info(f"   2. Check if market conditions match strategy expectations")
            logger.info(f"   3. Try different timeframes (5m, 1H)")
        elif self.stats['signals_passed_all_filters'] == 0:
            top_blocker = max(self.stats['filter_rejections'].items(), key=lambda x: x[1])[0] if self.stats['filter_rejections'] else None
            if top_blocker:
                logger.info(f"   1. Relax '{top_blocker}' filter threshold")
                logger.info(f"   2. Check filter configuration in config.py")
                logger.info(f"   3. Review rejection reasons above")
        else:
            logger.info(f"   ✅ System is generating and passing signals!")
            logger.info(f"   → If still no trades, check execution engine")
        
        logger.info("\n" + "="*80 + "\n")


def main():
    """Run diagnostic"""
    diagnostic = TradeDiagnostic()
    diagnostic.run(days=30)


if __name__ == '__main__':
    main()
