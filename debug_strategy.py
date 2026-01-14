#!/usr/bin/env python3
"""
Debug Strategy - Find why strategy generates zero signals
Shows what conditions are failing and how close we are to triggering
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
from data_feed.indicators import TechnicalIndicators
import config

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class StrategyDebugger:
    """
    Debug why strategy isn't generating signals
    Shows what conditions are failing and how close we are
    """
    
    def __init__(self):
        self.data_loader = HistoricalDataLoader()
        self.breakout_strategy = BreakoutStrategy()
        self.pullback_strategy = PullbackStrategy()
        self.indicators = TechnicalIndicators()
        
        self.stats = {
            'candles_analyzed': 0,
            'almost_triggered': [],
            'condition_failures': defaultdict(int),
            'closest_calls': []
        }
        
    def run(self, days: int = 7):
        """
        Debug strategy on last N days
        """
        logger.info("\n" + "="*80)
        logger.info("🔍 STRATEGY DEBUGGER")
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
        
        if not sol_data:
            logger.error("❌ Failed to load data")
            return
        
        candles_15m = sol_data.get('15m', [])
        logger.info(f"✅ Loaded {len(candles_15m)} candles\n")
        
        # Debug breakout strategy
        logger.info("🔍 Debugging Breakout Strategy...\n")
        self._debug_breakout_strategy(sol_data, candles_15m)
        
        # Print report
        self._print_report()
        
    def _debug_breakout_strategy(self, sol_data: Dict, candles: List[Dict]):
        """
        Debug breakout strategy in detail
        """
        for idx in range(50, len(candles)):  # Start at 50 for history
            candle = candles[idx]
            current_time = datetime.fromtimestamp(candle['timestamp'] / 1000)
            
            # Build market state
            market_state = self._build_market_state(sol_data, idx, '15m')
            if not market_state:
                continue
            
            self.stats['candles_analyzed'] += 1
            
            # Check each condition manually
            timeframes = market_state.get('timeframes', {})
            if '15m' not in timeframes:
                self.stats['condition_failures']['no_15m_data'] += 1
                continue
            
            tf_data = timeframes['15m']
            candles_list = tf_data.get('candles', [])
            
            if len(candles_list) < 50:
                self.stats['condition_failures']['insufficient_candles'] += 1
                continue
            
            # Check 1: Volatility compression
            compression_result = self._check_compression_debug(tf_data)
            if not compression_result['passed']:
                self.stats['condition_failures']['volatility_compression'] += 1
                self._track_closest_call('compression', compression_result, current_time, candle['close'])
                continue
            
            # Check 2: Consolidation
            consolidation_result = self._check_consolidation_debug(candles_list)
            if not consolidation_result['passed']:
                self.stats['condition_failures']['consolidation'] += 1
                self._track_closest_call('consolidation', consolidation_result, current_time, candle['close'])
                continue
            
            # Check 3: Breakout detection
            breakout_result = self._check_breakout_debug(candles_list, consolidation_result['data'])
            if not breakout_result['passed']:
                self.stats['condition_failures']['breakout_detection'] += 1
                self._track_closest_call('breakout', breakout_result, current_time, candle['close'])
                continue
            
            # Check 4: Volume
            volume_result = self._check_volume_debug(tf_data)
            if not volume_result['passed']:
                self.stats['condition_failures']['volume'] += 1
                self._track_closest_call('volume', volume_result, current_time, candle['close'])
                continue
            
            # If we get here, all conditions passed - signal should be generated
            logger.info(f"✅ ALL CONDITIONS PASSED at {current_time.strftime('%Y-%m-%d %H:%M')} - Signal should be generated!")
            self.stats['almost_triggered'].append({
                'time': current_time,
                'price': candle['close'],
                'compression': compression_result,
                'consolidation': consolidation_result,
                'breakout': breakout_result,
                'volume': volume_result
            })
    
    def _check_compression_debug(self, tf_data: Dict) -> Dict:
        """Check volatility compression with details"""
        atr_data = tf_data.get('atr', {})
        if not atr_data:
            return {'passed': False, 'reason': 'No ATR data', 'atr_percentile': None}
        
        is_compressed = atr_data.get('is_compressed', False)
        atr_percentile = atr_data.get('atr_percentile', 50)
        
        # Updated threshold: ATR < 1.5x average (relaxed from percentile < 40)
        current_atr = atr_data.get('atr', 0)
        atr_series = atr_data.get('atr_series', [])
        
        if current_atr == 0 or not atr_series or len(atr_series) < 20:
            # Fallback to percentile check
            passed = atr_percentile < 60  # Relaxed from 40
            return {
                'passed': passed,
                'reason': f"ATR percentile {atr_percentile:.1f} {'< 60' if passed else '>= 60'} (fallback)",
                'atr_percentile': atr_percentile,
                'threshold': 60
            }
        
        # Calculate average ATR
        avg_atr = sum(atr_series[-20:]) / min(20, len(atr_series))
        passed = current_atr < (avg_atr * 1.5)
        
        return {
            'passed': passed,
            'reason': f"ATR {current_atr:.4f} {'< 1.5x avg' if passed else '>= 1.5x avg'} ({avg_atr:.4f})",
            'atr_percentile': atr_percentile,
            'current_atr': current_atr,
            'avg_atr': avg_atr,
            'threshold': 1.5
        }
    
    def _check_consolidation_debug(self, candles: List[Dict]) -> Dict:
        """Check consolidation with details"""
        if len(candles) < 20:
            return {'passed': False, 'reason': 'Insufficient candles'}
        
        # Look at last 20 candles
        recent = candles[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        resistance = max(highs)
        support = min(lows)
        range_size = resistance - support
        mid_price = (resistance + support) / 2
        range_pct = range_size / mid_price if mid_price > 0 else 0
        
        # Current threshold: range_pct <= 0.03 (3%)
        passed = range_pct <= 0.03
        
        # Count breaks
        breaks = 0
        for c in recent:
            if c['high'] > resistance * 1.001 or c['low'] < support * 0.999:
                breaks += 1
        
        # Max 2 breaks allowed
        if breaks > 2:
            passed = False
        
        return {
            'passed': passed,
            'reason': f"Range {range_pct:.2%} {'<= 5%' if range_pct <= 0.05 else '> 5%'}, breaks={breaks}",
            'range_pct': range_pct,
            'breaks': breaks,
            'support': support,
            'resistance': resistance,
            'threshold': 0.05,  # Updated from 0.03
            'data': {'support': support, 'resistance': resistance, 'range_pct': range_pct}
        }
    
    def _check_breakout_debug(self, candles: List[Dict], consolidation: Dict) -> Dict:
        """Check breakout with details"""
        if not candles:
            return {'passed': False, 'reason': 'No candles'}
        
        current_candle = candles[-1]
        current_close = current_candle['close']
        resistance = consolidation['resistance']
        support = consolidation['support']
        
        # Updated logic: close > resistance * 1.0005 (long) OR close < support * 0.9995 (short)
        # Relaxed from 0.1% to 0.05%
        long_breakout = current_close > resistance * 1.0005
        short_breakout = current_close < support * 0.9995
        
        passed = long_breakout or short_breakout
        direction = 'long' if long_breakout else 'short' if short_breakout else None
        
        # Calculate how close we are
        if direction == 'long':
            distance_to_breakout = ((current_close - resistance) / resistance) * 100
        elif direction == 'short':
            distance_to_breakout = ((support - current_close) / support) * 100
        else:
            # Not broken out - calculate distance (using new 0.05% threshold)
            if current_close > (resistance + support) / 2:
                distance_to_breakout = ((resistance * 1.0005 - current_close) / current_close) * 100
            else:
                distance_to_breakout = ((current_close - support * 0.9995) / current_close) * 100
        
        return {
            'passed': passed,
            'reason': f"{'LONG' if long_breakout else 'SHORT' if short_breakout else 'NO'} breakout",
            'current_price': current_close,
            'resistance': resistance,
            'support': support,
            'distance_to_breakout_pct': distance_to_breakout,
            'direction': direction
        }
    
    def _check_volume_debug(self, tf_data: Dict) -> Dict:
        """Check volume with details"""
        volume_data = tf_data.get('volume', {})
        if not volume_data:
            return {'passed': True, 'reason': 'No volume data (allowed)'}
        
        volume_ratio = volume_data.get('volume_ratio', 1.0)
        threshold = 0.8  # Relaxed: 80% of average (was BREAKOUT_VOLUME_MULTIPLIER = 1.2)
        
        passed = volume_ratio >= threshold
        
        return {
            'passed': passed,
            'reason': f"Volume ratio {volume_ratio:.2f} {'>=' if passed else '<'} {threshold}",
            'volume_ratio': volume_ratio,
            'threshold': threshold
        }
    
    def _build_market_state(self, data: Dict, current_idx: int, primary_tf: str) -> Dict:
        """Build market state (same as backtest engine)"""
        if current_idx >= len(data[primary_tf]):
            return None
        
        market_state = {
            'timeframes': {},
            'timestamp': data[primary_tf][current_idx]['timestamp']
        }
        
        for tf_name, candles in data.items():
            current_ts = data[primary_tf][current_idx]['timestamp']
            tf_candles = [c for c in candles if c['timestamp'] <= current_ts]
            
            if not tf_candles:
                continue
            
            lookback = 200
            recent_candles = tf_candles[-lookback:] if len(tf_candles) > lookback else tf_candles
            
            indicators = self._calculate_indicators(recent_candles)
            
            market_state['timeframes'][tf_name] = {
                'candles': recent_candles,
                'current_price': recent_candles[-1]['close'],
                **indicators
            }
        
        return market_state
    
    def _calculate_indicators(self, candles: List[Dict]) -> Dict:
        """Calculate indicators"""
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
            # Calculate ATR percentile
            sorted_atr = sorted(atr_series)
            current_atr = atr_series[-1]
            percentile = (sorted_atr.index(current_atr) / len(sorted_atr)) * 100 if current_atr in sorted_atr else 50
            
            indicators['atr'] = {
                'atr': atr_series[-1],
                'atr_previous': atr_series[-2] if len(atr_series) > 1 else atr_series[-1],
                'atr_percentile': percentile,
                'is_compressed': percentile < 60,  # Relaxed from 40
                'atr_series': atr_series  # Include full series for compression check
            }
        
        # Volume
        avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
        indicators['volume'] = {
            'current_volume': volumes[-1],
            'average_volume': avg_volume,
            'volume_ratio': volumes[-1] / avg_volume if avg_volume > 0 else 1.0
        }
        
        return indicators
    
    def _track_closest_call(self, condition: str, result: Dict, time: datetime, price: float):
        """Track closest calls (almost triggered)"""
        if condition == 'breakout' and 'distance_to_breakout_pct' in result:
            distance = abs(result['distance_to_breakout_pct'])
            if distance < 1.0:  # Within 1% of triggering
                self.stats['closest_calls'].append({
                    'time': time,
                    'price': price,
                    'condition': condition,
                    'distance': distance,
                    'details': result
                })
    
    def _print_report(self):
        """Print debug report"""
        logger.info("\n" + "="*80)
        logger.info("📊 STRATEGY DEBUG REPORT")
        logger.info("="*80)
        
        logger.info(f"\n📈 ANALYSIS:")
        logger.info(f"   Candles Analyzed: {self.stats['candles_analyzed']}")
        logger.info(f"   Almost Triggered: {len(self.stats['almost_triggered'])}")
        logger.info(f"   Closest Calls: {len(self.stats['closest_calls'])}")
        
        logger.info(f"\n🚫 CONDITION FAILURES:")
        for condition, count in sorted(self.stats['condition_failures'].items(), 
                                       key=lambda x: x[1], reverse=True):
            pct = (count / self.stats['candles_analyzed']) * 100 if self.stats['candles_analyzed'] > 0 else 0
            logger.info(f"   {condition}: {count} times ({pct:.1f}%)")
        
        if self.stats['closest_calls']:
            logger.info(f"\n🎯 CLOSEST CALLS (almost triggered):")
            for call in sorted(self.stats['closest_calls'], key=lambda x: x['distance'])[:10]:
                logger.info(f"   {call['time'].strftime('%Y-%m-%d %H:%M')}: {call['condition']} - {call['distance']:.2f}% away")
                if 'details' in call:
                    logger.info(f"      {call['details'].get('reason', '')}")
        
        logger.info(f"\n💡 RECOMMENDATIONS:")
        
        # Find main blocker
        if self.stats['condition_failures']:
            main_blocker = max(self.stats['condition_failures'].items(), key=lambda x: x[1])
            blocker_pct = (main_blocker[1] / self.stats['candles_analyzed']) * 100 if self.stats['candles_analyzed'] > 0 else 0
            
            logger.info(f"   Main Blocker: {main_blocker[0]} ({blocker_pct:.1f}% of candles)")
            
            if main_blocker[0] == 'consolidation':
                logger.info(f"   → Consolidation range threshold is too strict (currently 3%)")
                logger.info(f"   → Suggestion: Increase to 5% or 7%")
            elif main_blocker[0] == 'volatility_compression':
                logger.info(f"   → ATR percentile threshold is too strict (currently < 40)")
                logger.info(f"   → Suggestion: Increase to < 60 or < 80")
            elif main_blocker[0] == 'breakout_detection':
                logger.info(f"   → Breakout detection is too strict (requires 0.1% above/below)")
                logger.info(f"   → Suggestion: Reduce to 0.05% or check if price is near breakout")
            elif main_blocker[0] == 'volume':
                logger.info(f"   → Volume requirement is too strict (currently {config.BREAKOUT_VOLUME_MULTIPLIER}x)")
                logger.info(f"   → Suggestion: Reduce to 1.2x or 1.0x")
        
        logger.info("\n" + "="*80 + "\n")


def main():
    """Run debugger"""
    debugger = StrategyDebugger()
    debugger.run(days=7)


if __name__ == '__main__':
    main()
