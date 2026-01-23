#!/usr/bin/env python3
"""
Threshold Sweep Script
Tests different SCORE_THRESHOLD values and reports results
"""

import subprocess
import json
import sys
from pathlib import Path

def run_backtest_with_threshold(threshold: int) -> dict:
    """Run backtest with a specific threshold and return results"""

    # Modify config.py temporarily
    config_path = Path(__file__).parent / 'config.py'
    config_content = config_path.read_text()

    # Replace the threshold
    old_line = None
    new_line = f"SCORE_THRESHOLD = {threshold}  # Optimized from backtesting (was 50) - more trades, better returns"

    for line in config_content.split('\n'):
        if line.startswith('SCORE_THRESHOLD =') and '# Optimized' in line:
            old_line = line
            break

    if old_line:
        modified_config = config_content.replace(old_line, new_line)
        config_path.write_text(modified_config)

    # Run backtest
    result = subprocess.run(
        ['python', 'run_backtest.py', '--start', '2025-10-01', '--end', '2025-12-31', '--capital', '10000'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )

    # Parse results from JSON
    results_path = Path(__file__).parent / 'backtesting/reports/results_2025-10-01_to_2025-12-31.json'
    if results_path.exists():
        with open(results_path) as f:
            return json.load(f)

    return None

def main():
    thresholds = [35, 40, 45, 50, 55, 60, 65]
    results = []

    print("=" * 80)
    print("SCORE_THRESHOLD SWEEP")
    print("=" * 80)

    for thresh in thresholds:
        print(f"\n🔄 Testing threshold: {thresh}")
        result = run_backtest_with_threshold(thresh)

        if result:
            metrics = result.get('metrics', {})
            results.append({
                'threshold': thresh,
                'return_pct': metrics.get('total_return_pct', 0),
                'win_rate': metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'sharpe': metrics.get('sharpe_ratio', 0),
                'max_dd': metrics.get('max_drawdown_pct', 0),
                'trades': metrics.get('total_trades', 0)
            })
            print(f"   Return: {metrics.get('total_return_pct', 0):.2f}%")
            print(f"   Win Rate: {metrics.get('win_rate', 0):.2f}%")
            print(f"   Profit Factor: {metrics.get('profit_factor', 0):.2f}")
            print(f"   Sharpe: {metrics.get('sharpe_ratio', 0):.2f}")
            print(f"   Max DD: {metrics.get('max_drawdown_pct', 0):.2f}%")
            print(f"   Trades: {metrics.get('total_trades', 0)}")

    # Print summary table
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Threshold':<12} {'Return%':<10} {'WinRate%':<10} {'PF':<8} {'Sharpe':<8} {'MaxDD%':<10} {'Trades':<8}")
    print("-" * 80)

    for r in results:
        print(f"{r['threshold']:<12} {r['return_pct']:<10.2f} {r['win_rate']:<10.2f} {r['profit_factor']:<8.2f} {r['sharpe']:<8.2f} {r['max_dd']:<10.2f} {r['trades']:<8}")

    # Find best threshold by return
    best = max(results, key=lambda x: x['return_pct'])
    print(f"\n✅ Best threshold by return: {best['threshold']} ({best['return_pct']:.2f}% return)")

    # Save results
    with open('threshold_sweep_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\n📄 Results saved to threshold_sweep_results.json")

if __name__ == '__main__':
    main()
