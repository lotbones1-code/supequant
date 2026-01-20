#!/usr/bin/env python3
"""
Quick Debug Script - Efficiently uses Claude Agent
Runs backtest, checks results, and uses Claude only if needed
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from run_backtest import run_backtest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def quick_debug(days: int = 30, use_claude: bool = True):
    """
    Efficient debug workflow:
    1. Run quick backtest
    2. Check results
    3. Use Claude only if zero signals
    4. Show summary
    """
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    logger.info("="*80)
    logger.info("🚀 QUICK DEBUG - Efficient Claude Agent Usage")
    logger.info("="*80)
    logger.info(f"Period: {start_date} to {end_date} ({days} days)")
    logger.info("="*80 + "\n")
    
    # Step 1: Run backtest
    logger.info("📊 Step 1: Running backtest...")
    result = run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=10000.0,
        run_name=f"quick_debug_{start_date}_to_{end_date}",
        force_refresh=False
    )
    
    if not result:
        logger.error("❌ Backtest failed!")
        return
    
    # Step 2: Check results
    signals = result.get('results', {}).get('signals', {})
    trades = result.get('results', {}).get('trades', {})
    
    signals_generated = signals.get('total_signals', 0)
    trades_executed = trades.get('total_trades', 0)
    win_rate = trades.get('win_rate', 0)
    
    logger.info("\n" + "="*80)
    logger.info("📊 BACKTEST RESULTS")
    logger.info("="*80)
    logger.info(f"Signals Generated: {signals_generated}")
    logger.info(f"Trades Executed: {trades_executed}")
    logger.info(f"Win Rate: {win_rate:.2f}%")
    logger.info("="*80 + "\n")
    
    # Step 3: Use Claude only if needed
    if signals_generated == 0 and use_claude:
        logger.info("🤖 Step 2: Zero signals detected - Using Claude Agent...")
        logger.info("   Claude will analyze strategy and data loading issues\n")
        
        try:
            from agents.debug_agent import DebugAgent
            
            debugger = DebugAgent(max_iterations=3, auto_fix=False)  # Analysis only
            debug_result = debugger.debug_backtest(
                start_date=start_date,
                end_date=end_date,
                strategy='breakout',  # Will auto-detect V3
                initial_capital=10000.0
            )
            
            logger.info("\n" + "="*80)
            logger.info("🤖 CLAUDE ANALYSIS RESULTS")
            logger.info("="*80)
            
            if debug_result.get('fixes_applied'):
                logger.info("🔍 Issues Found:")
                for fix in debug_result['fixes_applied']:
                    fix_data = fix.get('fix', {})
                    reasoning = fix_data.get('reasoning', 'No reasoning')
                    blocking = fix_data.get('blocking_conditions', [])
                    
                    logger.info(f"\n  Iteration {fix['iteration']}:")
                    if blocking:
                        logger.info(f"    Blocking Conditions: {', '.join(blocking)}")
                    logger.info(f"    Analysis: {reasoning[:200]}...")
                    
                    changes = fix_data.get('recommended_changes', [])
                    if changes:
                        logger.info(f"    Recommended Changes: {len(changes)}")
                        for i, change in enumerate(changes[:3], 1):  # Show first 3
                            logger.info(f"      {i}. {change.get('file', 'unknown')}:{change.get('line', '?')}")
                            logger.info(f"         {change.get('reasoning', 'No reasoning')[:80]}")
            
            # Token usage
            usage = debugger.agent.get_token_usage()
            logger.info(f"\n💰 Token Usage: {usage['total_tokens']} tokens ({usage['total_requests']} requests)")
            logger.info("="*80 + "\n")
            
            logger.info("💡 To apply fixes automatically, run:")
            logger.info(f"   python -m agents.debug_agent --start {start_date} --end {end_date} --apply-fixes")
            
        except ImportError:
            logger.error("❌ Claude agent not available. Install: pip install anthropic")
            logger.error("   Set ANTHROPIC_API_KEY environment variable")
        except Exception as e:
            logger.error(f"❌ Claude debug failed: {e}", exc_info=True)
    elif signals_generated == 0:
        logger.warning("⚠️  Zero signals but Claude agent disabled")
        logger.info("   Run with --use-claude or set use_claude=True")
    else:
        logger.info("✅ Signals generated! No need for Claude debug.")
        if trades_executed == 0:
            logger.warning("⚠️  Signals generated but no trades executed")
            logger.info("   Check filter rejections in backtest report")
    
    logger.info("\n" + "="*80)
    logger.info("✅ QUICK DEBUG COMPLETE")
    logger.info("="*80 + "\n")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Quick debug with efficient Claude usage')
    parser.add_argument('--days', type=int, default=30, help='Days to backtest (default: 30)')
    parser.add_argument('--no-claude', action='store_true', help='Disable Claude agent')
    
    args = parser.parse_args()
    
    quick_debug(days=args.days, use_claude=not args.no_claude)
