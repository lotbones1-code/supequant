#!/usr/bin/env python3
"""
Strategy Diagnostic Tool
Tests strategies directly to see why they're not generating signals

Usage:
    python diagnose_strategies.py --start 2024-09-01 --end 2024-11-30
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from backtesting.historical_data_loader import HistoricalDataLoader
from strategy.breakout_strategy import BreakoutStrategy
from strategy.pullback_strategy import PullbackStrategy
from data_feed.indicators import TechnicalIndicators
import config

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def build_market_state(sol_data, idx):
    """Build market state at specific candle"""
    indicators_calc = TechnicalIndicators()
    market_state = {'timeframes': {}}

    primary_tf = '15m'
    candles_15m = sol_data.get(primary_tf, [])

    if not candles_15m or idx >= len(candles_15m):
        return None

    current_ts = candles_15m[idx]['timestamp']

    for tf_name, all_candles in sol_data.items():
        # Get candles up to current time
        tf_candles = [c for c in all_candles if c['timestamp'] <= current_ts]

        if not tf_candles:
            continue

        # Take last 100 candles
        recent = tf_candles[-100:] if len(tf_candles) > 100 else tf_candles

        if len(recent) < 20:
            continue

        # Calculate indicators
        closes = [c['close'] for c in recent]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        volumes = [c['volume'] for c in recent]

        # ATR
        atr_series = indicators_calc.calculate_atr_series(highs, lows, closes, period=14)

        # EMA
        ema_fast = indicators_calc.calculate_ema(closes, period=20)
        ema_slow = indicators_calc.calculate_ema(closes, period=50)

        indicators = {}

        if atr_series:
            indicators['atr'] = {
                'atr': atr_series[-1],
                'atr_previous': atr_series[-2] if len(atr_series) > 1 else atr_series[-1]
            }

        if ema_fast and ema_slow:
            trend_dir = 'up' if ema_fast[-1] > ema_slow[-1] else 'down'
            trend_strength = abs(ema_fast[-1] - ema_slow[-1]) / ema_slow[-1]

            indicators['trend'] = {
                'trend_direction': trend_dir,
                'trend_strength': min(trend_strength * 10, 1.0),
                'ema_20': ema_fast[-1],
                'ema_50': ema_slow[-1]
            }

        # Volume
        avg_vol = sum(volumes[-20:]) / min(20, len(volumes))
        indicators['volume'] = {
            'current_volume': volumes[-1],
            'average_volume': avg_vol,
            'volume_ratio': volumes[-1] / avg_vol if avg_vol > 0 else 1.0
        }

        market_state['timeframes'][tf_name] = {
            'candles': recent,
            'current_price': recent[-1]['close'],
            **indicators
        }

    return market_state


def diagnose_strategies(start_date, end_date):
    """Run diagnostic on strategies"""

    print(f"\n{'='*80}")
    print(f"STRATEGY DIAGNOSTIC TOOL")
    print(f"{'='*80}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Testing: Breakout & Pullback strategies")
    print(f"{'='*80}\n")

    # Load data
    print("📥 Loading historical data...")
    loader = HistoricalDataLoader()
    sol_data = loader.load_data(config.TRADING_SYMBOL, start_date, end_date)

    if not sol_data or not sol_data.get('15m'):
        print("❌ Failed to load data")
        return

    candles_15m = sol_data['15m']
    print(f"✅ Loaded {len(candles_15m)} candles (15m timeframe)\n")

    # Initialize strategies
    breakout = BreakoutStrategy()
    pullback = PullbackStrategy()

    # Sample every 100 candles to check conditions
    sample_indices = range(200, len(candles_15m), 100)  # Start at 200 to have enough history

    print(f"🔍 Checking {len(list(sample_indices))} sample points...\n")

    breakout_count = 0
    pullback_count = 0
    samples_checked = 0

    for idx in sample_indices:
        samples_checked += 1
        market_state = build_market_state(sol_data, idx)

        if not market_state:
            continue

        candle_time = datetime.fromtimestamp(candles_15m[idx]['timestamp'] / 1000)

        # Test breakout
        breakout_signal = breakout.analyze(market_state)
        if breakout_signal:
            breakout_count += 1
            print(f"✅ BREAKOUT found at {candle_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Direction: {breakout_signal.get('direction', 'unknown')}")
            print(f"   Entry: ${breakout_signal.get('entry_price', 0):.2f}")

        # Test pullback
        pullback_signal = pullback.analyze(market_state)
        if pullback_signal:
            pullback_count += 1
            print(f"✅ PULLBACK found at {candle_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Direction: {pullback_signal.get('direction', 'unknown')}")
            print(f"   Entry: ${pullback_signal.get('entry_price', 0):.2f}")

    # Summary
    print(f"\n{'='*80}")
    print(f"DIAGNOSTIC RESULTS")
    print(f"{'='*80}")
    print(f"Samples Checked: {samples_checked}")
    print(f"Breakout Signals: {breakout_count}")
    print(f"Pullback Signals: {pullback_count}")
    print(f"Total Signals: {breakout_count + pullback_count}")

    if breakout_count == 0 and pullback_count == 0:
        print(f"\n⚠️  NO SIGNALS FOUND!")
        print(f"\nPossible reasons:")
        print(f"1. Market conditions don't meet strategy criteria")
        print(f"2. Strategies are too strict (need tuning)")
        print(f"3. Missing required timeframe data")
        print(f"4. Strategy logic has issues")

        print(f"\n💡 Recommendations:")
        print(f"- Check if all timeframes (1m, 5m, 15m, 1H, 4H) have data")
        print(f"- Review strategy criteria in strategy/ folder")
        print(f"- Try different date ranges (bull market, bear market)")
        print(f"- Consider loosening strategy requirements")
    else:
        print(f"\n✅ Strategies ARE finding signals!")
        print(f"\nIf backtest shows 0 trades, the issue is likely:")
        print(f"- Filters rejecting all signals")
        print(f"- Daily trade limits")
        print(f"- Trade interval spacing")

    print(f"{'='*80}\n")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Diagnose why strategies aren\'t finding signals')
    parser.add_argument('--start', type=str, default='2024-09-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2024-11-30', help='End date (YYYY-MM-DD)')

    args = parser.parse_args()

    diagnose_strategies(args.start, args.end)
