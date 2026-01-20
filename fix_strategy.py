#!/usr/bin/env python3
"""
Fix Strategy - Use Claude to analyze and improve
Efficiently uses Claude agent to fix strategy based on backtest results
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.claude_agent import ClaudeAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_strategy():
    """Use Claude to analyze and fix strategy"""
    logger.info("="*80)
    logger.info("🤖 USING CLAUDE TO FIX STRATEGY")
    logger.info("="*80)
    
    # Load latest results
    results_file = Path("backtesting/reports/results_quick_test.json")
    if not results_file.exists():
        logger.error("No results file found")
        return
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Load trades CSV
    trades_file = Path("backtesting/reports/trades_quick_test.csv")
    trades_data = ""
    if trades_file.exists():
        with open(trades_file, 'r') as f:
            trades_data = f.read()
    
    # Load strategy code
    strategy_file = Path("strategy/breakout_strategy_v3.py")
    with open(strategy_file, 'r') as f:
        strategy_code = f.read()
    
    # Key metrics
    metrics = results.get('metrics', {})
    trade_stats = metrics.get('trade_stats', {})
    performance = results.get('results', {}).get('performance', {})
    
    win_rate = trade_stats.get('win_rate_pct', 0)
    profit_factor = trade_stats.get('profit_factor', 0)
    avg_win = performance.get('avg_win', 0)
    avg_loss = performance.get('avg_loss', 0)
    total_return = results.get('results', {}).get('summary', {}).get('total_return_pct', 0)
    
    context = f"""
CRITICAL PROBLEM: Strategy is LOSING MONEY

BACKTEST RESULTS:
- Total Return: {total_return:.2f}% (LOSING!)
- Win Rate: {win_rate:.1f}% (Target: 50%+)
- Profit Factor: {profit_factor:.2f} (Target: >1.5, currently TERRIBLE)
- Avg Win: ${avg_win:.2f}
- Avg Loss: ${avg_loss:.2f}
- Total Trades: {trade_stats.get('total_trades', 0)}

TRADE DETAILS:
{trades_data}

ANALYSIS:
- ALL 4 trades hit stop loss
- Previous backtest had 1 winner (+$577), but this one has NONE
- Wider stops made losses BIGGER (not better)
- Need BETTER ENTRIES, not wider stops

STRATEGY CODE:
```python
{strategy_code[:4000]}
```

GOAL: Increase win rate to 50%+ while maintaining profit factor >2.0
APPROACH: Better entry quality, not more signals
"""
    
    system_prompt = """You are an expert trading strategy optimizer. Your goal is to increase win rate while maintaining profitability.

CRITICAL PRINCIPLES:
1. Quality over quantity - Better entries, not more signals
2. Stricter filters = Better trades (even if fewer)
3. Focus on what makes winners win (analyze the +$577 trade)
4. Avoid what makes losers lose (all hit stop - why?)

Provide SPECIFIC code changes with line numbers."""
    
    prompt = f"""The strategy is LOSING MONEY. All 4 trades hit stop loss.

{context}

Analyze and provide:
1. Why ALL trades hit stop (root cause)
2. What made the previous +$577 winner different
3. SPECIFIC code changes to fix (with line numbers)
4. Expected improvement (win rate target: 50%+)

Format as actionable code changes:
{{
    "analysis": "Why all trades fail",
    "root_cause": "Main issue",
    "fixes": [
        {{
            "file": "strategy/breakout_strategy_v3.py",
            "line": 80,
            "old": "if volume_ratio < 2.5:",
            "new": "if volume_ratio < 3.0:",
            "reasoning": "Require stronger volume for better entries"
        }}
    ],
    "expected_win_rate": 50,
    "expected_profit_factor": 2.5
}}"""
    
    try:
        agent = ClaudeAgent()
        logger.info("\n🤖 Asking Claude for fixes...")
        
        response = agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt,
            max_tokens=4096
        )
        
        content = response['content']
        logger.info("\n" + "="*80)
        logger.info("🤖 CLAUDE FIX RECOMMENDATIONS")
        logger.info("="*80)
        logger.info(content)
        logger.info("="*80)
        
        # Extract JSON if present
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                fixes = json.loads(json_match.group())
                logger.info("\n📋 ACTIONABLE FIXES:")
                if 'fixes' in fixes:
                    for i, fix in enumerate(fixes['fixes'][:10], 1):
                        logger.info(f"\n  {i}. {fix.get('file', 'unknown')}:{fix.get('line', '?')}")
                        logger.info(f"     OLD: {fix.get('old', 'N/A')}")
                        logger.info(f"     NEW: {fix.get('new', 'N/A')}")
                        logger.info(f"     Why: {fix.get('reasoning', 'N/A')}")
            except:
                pass
        
        usage = agent.get_token_usage()
        logger.info(f"\n💰 Tokens: {usage['total_tokens']}")
        
    except Exception as e:
        logger.error(f"❌ Failed: {e}", exc_info=True)


if __name__ == '__main__':
    fix_strategy()
