#!/usr/bin/env python3
"""
Run AI Strategy Optimization
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from optimizer.ai_strategy_optimizer import StrategyOptimizer

if __name__ == '__main__':
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ Set ANTHROPIC_API_KEY first")
        print("   export ANTHROPIC_API_KEY='sk-ant-your-key-here'")
        sys.exit(1)
    
    optimizer = StrategyOptimizer(
        api_key=api_key,
        repo_path=str(project_root)
    )
    
    print("🚀 Starting AI Strategy Optimization")
    print("Target: 55%+ win rate, 1.5+ Sharpe")
    print("=" * 60)
    
    results = optimizer.optimization_loop(
        target_win_rate=55,
        target_sharpe=1.5,
        max_iterations=20,
        start_date="2026-01-01",
        end_date="2026-01-14"
    )
    
    print("\n✅ OPTIMIZATION COMPLETE")
    print(f"Win Rate: {results.get('final_win_rate', 0):.1f}%")
    print(f"Sharpe: {results.get('final_sharpe', 0):.2f}")
    print(f"PnL: ${results.get('final_pnl', 0):.2f}")
    print(f"Iterations: {results.get('iterations', 0)}")
