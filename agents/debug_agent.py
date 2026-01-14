"""
Debug Agent
Automated debugger that uses Claude to identify and fix issues
"""

import sys
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

from .claude_agent import ClaudeAgent
from .strategy_advisor import StrategyAdvisor

logger = logging.getLogger(__name__)


class DebugAgent:
    """
    Automated debugger that:
    - Runs backtest
    - Parses output for 0 signals
    - Reads strategy files
    - Identifies blocking conditions
    - Proposes fixes
    - Can iterate until signals generate
    """
    
    def __init__(self, claude_agent: Optional[ClaudeAgent] = None,
                 strategy_advisor: Optional[StrategyAdvisor] = None,
                 max_iterations: int = 5,
                 auto_fix: bool = False):
        """
        Initialize debug agent
        
        Args:
            claude_agent: Optional ClaudeAgent instance
            strategy_advisor: Optional StrategyAdvisor instance
            max_iterations: Maximum iterations to try fixing
            auto_fix: If True, automatically apply fixes (default: False - analysis only)
        """
        self.agent = claude_agent or ClaudeAgent()
        self.advisor = strategy_advisor or StrategyAdvisor(self.agent)
        self.max_iterations = max_iterations
        self.auto_fix = auto_fix  # DISABLE auto-fixing by default
        self.project_root = Path(__file__).parent.parent
        self.debug_history = []
        
    def debug_backtest(self, start_date: str, end_date: str,
                      strategy: str = "breakout", 
                      initial_capital: float = 10000.0) -> Dict:
        """
        Run backtest and debug if no signals generated
        
        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'
            strategy: Strategy to debug
            initial_capital: Initial capital for backtest
            
        Returns:
            Dict with debug results and fixes applied
        """
        logger.info(f"🔍 Starting automated debug for {strategy} strategy")
        logger.info(f"   Period: {start_date} to {end_date}")
        
        iteration = 0
        fixes_applied = []
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"Iteration {iteration}/{self.max_iterations}")
            logger.info(f"{'='*60}")
            
            # Run backtest
            logger.info("📊 Running backtest...")
            backtest_result = self._run_backtest(start_date, end_date, initial_capital)
            
            # Check if signals generated
            signals_generated = backtest_result.get('signals', {}).get('total_signals', 0)
            trades_executed = backtest_result.get('trades', {}).get('total_trades', 0)
            
            logger.info(f"   Signals Generated: {signals_generated}")
            logger.info(f"   Trades Executed: {trades_executed}")
            
            if signals_generated > 0:
                logger.info(f"✅ SUCCESS: {signals_generated} signals generated!")
                return {
                    'success': True,
                    'iterations': iteration,
                    'signals_generated': signals_generated,
                    'trades_executed': trades_executed,
                    'fixes_applied': fixes_applied,
                    'final_results': backtest_result
                }
            
            # No signals - debug
            logger.info("❌ No signals generated. Analyzing...")
            debug_result = self._debug_no_signals(strategy, backtest_result)
            
            # Store analysis
            analysis = {
                'iteration': iteration,
                'fix': debug_result.get('fix', {}),
                'reasoning': debug_result.get('reasoning', ''),
                'fix_available': debug_result.get('fix_available', False)
            }
            fixes_applied.append(analysis)
            
            # Print analysis results
            logger.info("\n" + "="*60)
            logger.info("🔍 ANALYSIS RESULTS")
            logger.info("="*60)
            logger.info(f"Signals generated: {signals_generated}")
            logger.info(f"Trades executed: {trades_executed}")
            logger.info(f"\nRecommended fixes:")
            
            if debug_result.get('fix_available'):
                fix_data = debug_result.get('fix', {})
                recommended = fix_data.get('recommended_changes', [])
                for i, change in enumerate(recommended[:5], 1):  # Show first 5
                    logger.info(f"  {i}. {change.get('file', 'unknown')} line {change.get('line', '?')}")
                    logger.info(f"     {change.get('reasoning', 'No reasoning provided')}")
                
                if self.auto_fix:
                    logger.info("\n🔧 Auto-fix enabled. Applying fixes...")
                    fix_result = self._apply_fix(debug_result['fix'])
                    analysis['applied'] = fix_result['success']
                    analysis['fix_errors'] = fix_result.get('errors', [])
                    
                    if not fix_result['success']:
                        logger.warning(f"⚠️  Fix application failed: {fix_result.get('errors', [])}")
                        break
                else:
                    logger.info("\n💡 Auto-fix is DISABLED (analysis only)")
                    logger.info("   To apply fixes, run with --apply-fixes flag or set auto_fix=True")
                    # Don't break - return analysis instead
                    return {
                        'success': False,
                        'iterations': iteration,
                        'signals_generated': signals_generated,
                        'fixes_applied': fixes_applied,
                        'analysis_only': True,
                        'final_results': backtest_result
                    }
            else:
                logger.warning("⚠️  No fix available from Claude analysis")
                break
        
        # Max iterations reached or no fix available
        logger.error(f"❌ Failed to generate signals after {iteration} iterations")
        return {
            'success': False,
            'iterations': iteration,
            'fixes_applied': fixes_applied,
            'final_results': backtest_result if 'backtest_result' in locals() else None
        }
    
    def _run_backtest(self, start_date: str, end_date: str,
                     initial_capital: float) -> Dict:
        """Run backtest and parse results"""
        try:
            # Import backtest components
            sys.path.insert(0, str(self.project_root))
            from backtesting.historical_data_loader import HistoricalDataLoader
            from backtesting.backtest_engine import BacktestEngine
            
            # Load data - need ALL timeframes for filters (4H, 15m, 5m, 1H)
            import config
            timeframes_to_load = [config.HTF_TIMEFRAME, config.MTF_TIMEFRAME, config.LTF_TIMEFRAME, '1H']
            
            loader = HistoricalDataLoader()
            sol_data = loader.load_data(
                symbol="SOL-USDT-SWAP",
                start_date=start_date,
                end_date=end_date,
                timeframes=timeframes_to_load,
                force_refresh=False
            )
            
            btc_data = loader.load_data(
                symbol="BTC-USDT-SWAP",
                start_date=start_date,
                end_date=end_date,
                timeframes=timeframes_to_load,
                force_refresh=False
            )
            
            if not sol_data or not btc_data:
                return {'error': 'Failed to load data'}
            
            # Run backtest
            engine = BacktestEngine(initial_capital=initial_capital)
            results = engine.run(sol_data, btc_data, start_date, end_date)
            
            return results if results else {'error': 'Backtest returned no results'}
            
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            return {'error': str(e)}
    
    def _debug_no_signals(self, strategy: str, backtest_results: Dict) -> Dict:
        """Use Claude to debug why no signals generated"""
        # Read strategy file
        strategy_file = self.project_root / "strategy" / f"{strategy}_strategy.py"
        if not strategy_file.exists():
            return {'fix_available': False, 'error': 'Strategy file not found'}
        
        with open(strategy_file, 'r') as f:
            strategy_code = f.read()
        
        # Build context
        context = f"""
Backtest Results:
- Signals Generated: {backtest_results.get('signals', {}).get('total_signals', 0)}
- Trades Executed: {backtest_results.get('trades', {}).get('total_trades', 0)}
- Filter Rejections: {backtest_results.get('filter_rejections', {})}

Strategy Code:
```python
{strategy_code[:3000]}  # First 3000 chars
```
"""
        
        system_prompt = """You are an expert debugger for trading strategies.

Analyze why signals aren't generating and provide specific code fixes.
Focus on threshold values that are too strict."""
        
        prompt = f"""The {strategy} strategy is generating ZERO signals in backtest.

{context}

Analyze the code and provide:
1. Which conditions are blocking signals
2. Current threshold values
3. Recommended threshold adjustments
4. Specific code changes (with line numbers if possible)
5. Expected impact

Format your response as JSON:
{{
    "blocking_conditions": ["condition1", "condition2"],
    "current_thresholds": {{"threshold1": "value1"}},
    "recommended_changes": [
        {{
            "file": "strategy/breakout_strategy.py",
            "line": 143,
            "old_code": "if range_pct > 0.03:",
            "new_code": "if range_pct > 0.05:",
            "reasoning": "5% allows more consolidation patterns"
        }}
    ],
    "reasoning": "Overall explanation"
}}"""
        
        response = self.agent._call_claude(
            [{'role': 'user', 'content': prompt}],
            system=system_prompt,
            max_tokens=4096
        )
        
        # Try to parse JSON from response
        content = response['content']
        try:
            # Extract JSON from response (might be wrapped in markdown)
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                fix_data = json.loads(json_match.group())
            else:
                # Fallback: return as text
                fix_data = {
                    'reasoning': content,
                    'recommended_changes': []
                }
        except json.JSONDecodeError:
            fix_data = {
                'reasoning': content,
                'recommended_changes': []
            }
        
        return {
            'fix_available': len(fix_data.get('recommended_changes', [])) > 0,
            'fix': fix_data,
            'reasoning': fix_data.get('reasoning', content)
        }
    
    def _apply_fix(self, fix_data: Dict) -> Dict:
        """Apply fix to strategy file"""
        changes = fix_data.get('recommended_changes', [])
        
        if not changes:
            return {'success': False, 'error': 'No changes provided'}
        
        applied = []
        errors = []
        
        for change in changes:
            file_path = self.project_root / change.get('file', '')
            if not file_path.exists():
                errors.append(f"File not found: {change.get('file')}")
                continue
            
            old_code = change.get('old_code', '')
            new_code = change.get('new_code', '')
            
            if not old_code or not new_code:
                errors.append(f"Missing old_code or new_code for {change.get('file')}")
                continue
            
            try:
                # Read file
                with open(file_path, 'r') as f:
                    file_content = f.read()
                
                # Apply change
                if old_code in file_content:
                    file_content = file_content.replace(old_code, new_code)
                    
                    # Write back
                    with open(file_path, 'w') as f:
                        f.write(file_content)
                    
                    applied.append({
                        'file': str(file_path),
                        'line': change.get('line', 'unknown'),
                        'change': f"{old_code} → {new_code}"
                    })
                    logger.info(f"   ✅ Applied: {file_path.name} line {change.get('line', '?')}")
                else:
                    errors.append(f"Code not found in {change.get('file')}: {old_code[:50]}")
                    
            except Exception as e:
                errors.append(f"Error applying fix to {change.get('file')}: {e}")
        
        return {
            'success': len(applied) > 0,
            'applied': applied,
            'errors': errors
        }
    
    def get_debug_history(self) -> List[Dict]:
        """Get debug history"""
        return self.debug_history


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Automated debugger for trading strategies')
    parser.add_argument('--start', type=str, required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--strategy', type=str, default='breakout', choices=['breakout', 'pullback'],
                       help='Strategy to debug')
    parser.add_argument('--capital', type=float, default=10000.0, help='Initial capital')
    parser.add_argument('--max-iterations', type=int, default=5, help='Max debug iterations')
    parser.add_argument('--apply-fixes', action='store_true', help='Actually apply fixes (default: analysis only)')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run debug (analysis-only by default, unless --apply-fixes is used)
    debugger = DebugAgent(max_iterations=args.max_iterations, auto_fix=args.apply_fixes)
    result = debugger.debug_backtest(
        args.start,
        args.end,
        args.strategy,
        args.capital
    )
    
    # Print summary
    print("\n" + "="*60)
    print("DEBUG SUMMARY")
    print("="*60)
    print(f"Success: {result['success']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Signals Generated: {result.get('signals_generated', 0)}")
    print(f"Fixes Applied: {len(result.get('fixes_applied', []))}")
    
    if result.get('fixes_applied'):
        print("\nFixes Applied:")
        for fix in result['fixes_applied']:
            print(f"  Iteration {fix['iteration']}: {fix.get('fix', {}).get('reasoning', 'N/A')[:100]}")
    
    # Token usage
    usage = debugger.agent.get_token_usage()
    print(f"\nToken Usage: {usage['total_tokens']} tokens ({usage['total_requests']} requests)")


if __name__ == '__main__':
    main()
