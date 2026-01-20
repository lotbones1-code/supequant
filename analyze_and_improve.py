#!/usr/bin/env python3
"""
Analyze Backtest Results and Improve Strategy
Uses Claude agent efficiently to analyze results and suggest improvements
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from agents.claude_agent import ClaudeAgent
from agents.strategy_advisor import StrategyAdvisor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def analyze_backtest_results(results_file: str):
    """
    Analyze backtest results using Claude agent
    """
    logger.info("="*80)
    logger.info("🤖 ANALYZING BACKTEST RESULTS WITH CLAUDE")
    logger.info("="*80)
    
    # Load results
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    metrics = results.get('metrics', {})
    trade_stats = metrics.get('trade_stats', {})
    performance = results.get('results', {}).get('performance', {})
    
    # Key metrics
    win_rate = trade_stats.get('win_rate_pct', 0)
    profit_factor = trade_stats.get('profit_factor', 0)
    avg_win = performance.get('avg_win', 0)
    avg_loss = performance.get('avg_loss', 0)
    total_trades = trade_stats.get('total_trades', 0)
    
    logger.info(f"\n📊 Current Performance:")
    logger.info(f"   Win Rate: {win_rate:.1f}%")
    logger.info(f"   Profit Factor: {profit_factor:.2f}")
    logger.info(f"   Avg Win: ${avg_win:.2f}")
    logger.info(f"   Avg Loss: ${avg_loss:.2f}")
    logger.info(f"   Total Trades: {total_trades}")
    
    # Load strategy code
    strategy_file = Path("strategy/breakout_strategy_v3.py")
    if not strategy_file.exists():
        logger.error(f"Strategy file not found: {strategy_file}")
        return
    
    with open(strategy_file, 'r') as f:
        strategy_code = f.read()
    
    # Load trade details
    trades_file = results_file.replace('results_', 'trades_').replace('.json', '.csv')
    trades_info = ""
    if Path(trades_file).exists():
        with open(trades_file, 'r') as f:
            trades_info = f.read()[:2000]  # First 2000 chars
    
    # Build analysis prompt
    context = f"""
Backtest Results Analysis:

PERFORMANCE METRICS:
- Win Rate: {win_rate:.1f}% (Target: 50%+)
- Profit Factor: {profit_factor:.2f} (Excellent! Target: >1.5)
- Average Win: ${avg_win:.2f}
- Average Loss: ${avg_loss:.2f}
- Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}:1 (Excellent!)
- Total Trades: {total_trades}
- Total Return: {results.get('results', {}).get('summary', {}).get('total_return_pct', 0):.2f}%

TRADE ANALYSIS:
- Exit Reasons: {results.get('metrics', {}).get('time_analysis', {}).get('exit_reasons', {})}
- Avg Trade Duration: {results.get('metrics', {}).get('time_analysis', {}).get('avg_trade_duration_bars', 0):.1f} bars
- Avg Win Duration: {results.get('metrics', {}).get('time_analysis', {}).get('avg_win_duration_bars', 0):.1f} bars
- Avg Loss Duration: {results.get('metrics', {}).get('time_analysis', {}).get('avg_loss_duration_bars', 0):.1f} bars

TRADE DETAILS:
{trades_info[:1500] if trades_info else 'No trade details available'}

STRATEGY CODE:
```python
{strategy_code[:3000]}
```
"""
    
    system_prompt = """You are an expert trading strategy analyst. Analyze backtest results and provide specific, actionable improvements.

Focus on:
1. Why win rate is low (25%) despite excellent profit factor (3.39)
2. Why 3 out of 4 trades hit stop loss
3. How to improve entry quality
4. Whether stop placement is optimal
5. Specific code changes to improve win rate while maintaining profit factor

Provide concrete, implementable suggestions."""
    
    prompt = f"""Analyze these backtest results and provide improvement recommendations.

{context}

KEY QUESTION: Win rate is only 25% (1 win, 3 losses) but profit factor is excellent (3.39) because wins are 10x larger than losses.

This suggests:
- Strategy logic is working (big wins prove it)
- But too many trades hit stop loss
- Need to improve entry quality OR stop placement

Provide:
1. Root cause analysis (why 75% hit stop?)
2. Specific improvements to increase win rate to 40%+
3. Code changes with line numbers
4. Expected impact

Format as JSON:
{{
    "analysis": "Overall analysis",
    "root_causes": ["cause1", "cause2"],
    "improvements": [
        {{
            "file": "strategy/breakout_strategy_v3.py",
            "line": 80,
            "change": "Lower volume threshold from 2.5 to 2.0",
            "reasoning": "Current threshold too strict, filtering good setups",
            "expected_impact": "Increase signals by 30%, win rate to 35%"
        }}
    ],
    "priority": "high/medium/low"
}}"""
    
    try:
        agent = ClaudeAgent()
        
        logger.info("\n🤖 Asking Claude for analysis...")
        response = agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt,
            max_tokens=4096
        )
        
        content = response['content']
        logger.info("\n" + "="*80)
        logger.info("🤖 CLAUDE ANALYSIS")
        logger.info("="*80)
        logger.info(content)
        logger.info("="*80)
        
        # Try to extract JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                analysis = json.loads(json_match.group())
                logger.info("\n📋 STRUCTURED RECOMMENDATIONS:")
                if 'improvements' in analysis:
                    for i, imp in enumerate(analysis['improvements'][:5], 1):
                        logger.info(f"\n  {i}. {imp.get('file', 'unknown')}:{imp.get('line', '?')}")
                        logger.info(f"     Change: {imp.get('change', 'N/A')}")
                        logger.info(f"     Reasoning: {imp.get('reasoning', 'N/A')}")
                        logger.info(f"     Expected: {imp.get('expected_impact', 'N/A')}")
            except:
                pass
        
        # Token usage
        usage = agent.get_token_usage()
        logger.info(f"\n💰 Token Usage: {usage['total_tokens']} tokens")
        
    except Exception as e:
        logger.error(f"❌ Claude analysis failed: {e}", exc_info=True)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze backtest results with Claude')
    parser.add_argument('--results', type=str, 
                       default='backtesting/reports/results_quick_test.json',
                       help='Path to results JSON file')
    
    args = parser.parse_args()
    
    analyze_backtest_results(args.results)
