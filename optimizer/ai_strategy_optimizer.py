"""
AI Strategy Optimizer
Uses Claude AI to iteratively improve trading strategy performance
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

try:
    import anthropic
except ImportError:
    print("❌ anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

logger = logging.getLogger(__name__)


class StrategyOptimizer:
    """
    AI-powered strategy optimization system
    Uses Claude to iteratively improve strategy until target metrics are met
    """

    def __init__(self, api_key: str, repo_path: str):
        """
        Initialize optimizer
        
        Args:
            api_key: Anthropic API key
            repo_path: Path to repository root
        """
        self.api_key = api_key
        self.repo_path = Path(repo_path)
        self.client = anthropic.Anthropic(api_key=api_key)
        
        # Optimization state
        self.optimization_history = []
        self.current_best_results = None
        self.current_best_strategy = None
        self.iteration_count = 0
        
        # History file
        self.history_file = self.repo_path / "optimizer" / "optimization_history.json"
        self.history_file.parent.mkdir(exist_ok=True)
        
        logger.info(f"✅ StrategyOptimizer initialized (repo: {self.repo_path})")

    def analyze_backtest_results(self, results_json_path: Optional[str] = None) -> Dict:
        """
        Analyze backtest results and identify main problems
        
        Args:
            results_json_path: Optional path to backtest JSON results (if None, finds latest)
            
        Returns:
            Dict with problem_diagnosis and suggested_fix
        """
        # If no path provided, find latest results file
        if results_json_path is None:
            reports_dir = self.repo_path / "backtesting" / "reports"
            json_files = sorted(
                reports_dir.glob("results_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if not json_files:
                logger.error("❌ No results JSON found")
                return {'problem_diagnosis': {'main_problem': 'No results found'}, 'suggested_fix': 'Run backtest first'}
            results_json_path = str(json_files[0])
        
        # Handle Path objects
        if isinstance(results_json_path, Path):
            results_json_path = str(results_json_path)
        
        with open(results_json_path, 'r') as f:
            data = json.load(f)
        
        results = data.get('results', {})
        metrics = data.get('metrics', {})
        
        # Extract key metrics
        win_rate = results.get('trades', {}).get('win_rate', 0) * 100
        total_pnl = results.get('summary', {}).get('total_pnl', 0)
        sharpe_ratio = metrics.get('risk', {}).get('sharpe_ratio', 0)
        num_trades = results.get('trades', {}).get('total_trades', 0)
        avg_win = results.get('performance', {}).get('avg_win', 0)
        avg_loss = abs(results.get('performance', {}).get('avg_loss', 0))
        
        # Diagnose main problem
        problems = []
        fixes = []
        
        if win_rate < 45:
            problems.append(f"Win rate too low ({win_rate:.1f}%)")
            fixes.append("Entry logic too loose, filtering bad signals")
        
        if total_pnl < 0:
            problems.append(f"Negative PnL (${total_pnl:.2f})")
            fixes.append("Exits aren't working, let winners run or tighten stops")
        
        if num_trades < 5:
            problems.append(f"Too few trades ({num_trades})")
            fixes.append("Strategy is too strict, need more entries")
        
        if num_trades > 50:
            problems.append(f"Too many trades ({num_trades})")
            fixes.append("Strategy overtrades, need better filters")
        
        if avg_loss > avg_win * 2 and avg_loss > 0:
            problems.append(f"Losses too large (avg_loss: ${avg_loss:.2f} vs avg_win: ${avg_win:.2f})")
            fixes.append("Risk management broken, stop losses too wide")
        
        if not problems:
            problems.append("Strategy performing well")
            fixes.append("Minor tweaks to improve edge")
        
        problem_diagnosis = {
            'main_problem': problems[0] if problems else "No major issues",
            'all_problems': problems,
            'metrics': {
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'sharpe_ratio': sharpe_ratio,
                'num_trades': num_trades,
                'avg_win': avg_win,
                'avg_loss': avg_loss
            }
        }
        
        suggested_fix = fixes[0] if fixes else "No changes needed"
        
        return {
            'problem_diagnosis': problem_diagnosis,
            'suggested_fix': suggested_fix,
            'metrics': problem_diagnosis['metrics']
        }

    def propose_strategy_changes(self, problem_diagnosis: Dict, current_code: Optional[str] = None) -> Dict:
        """
        Use Claude to propose specific strategy changes
        
        Args:
            problem_diagnosis: Problem analysis from analyze_backtest_results
            current_code: Optional current strategy code
            
        Returns:
            Dict with change_description and code_patch
        """
        problem = problem_diagnosis['problem_diagnosis']['main_problem']
        metrics = problem_diagnosis['metrics']
        
        prompt = f"""You are a quantitative trading strategy optimizer. Analyze this trading strategy problem and propose ONE specific, actionable code change.

CURRENT PROBLEM:
{problem}

CURRENT METRICS:
- Win Rate: {metrics['win_rate']:.1f}%
- Total PnL: ${metrics['total_pnl']:.2f}
- Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
- Number of Trades: {metrics['num_trades']}
- Avg Win: ${metrics['avg_win']:.2f}
- Avg Loss: ${metrics['avg_loss']:.2f}

STRATEGY FILES TO MODIFY:
1. strategy/signal_scorer.py - Signal quality scoring (0-100 points)
2. strategy/breakout_strategy.py - Entry signal generation
3. backtesting/backtest_engine.py - Trade execution and exits
4. filters/filter_manager.py - Signal filtering

Propose ONE focused change that addresses the main problem. Examples:
- "Lower quality score threshold from 30 to 25 in backtest_engine.py line X"
- "Add volume spike detection (>2x average) in signal_scorer.py"
- "Implement trailing stop loss in backtest_engine.py _execute_trade method"
- "Add RSI divergence check in breakout_strategy.py"
- "Reduce position size multiplier when on losing streak"

Return your response as JSON:
{{
    "change_description": "Clear description of the change",
    "file_path": "path/to/file.py",
    "code_patch": "Specific code to add/modify (show context lines)",
    "reasoning": "Why this change will help"
}}"""

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            
            # Try to extract JSON from response
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            change_proposal = json.loads(response_text)
            
            logger.info(f"💡 Claude proposed: {change_proposal.get('change_description', 'Unknown')}")
            
            return change_proposal
            
        except Exception as e:
            logger.error(f"❌ Error getting Claude proposal: {e}")
            # Fallback to simple heuristic
            return {
                "change_description": f"Adjust quality score threshold (heuristic fallback)",
                "file_path": "backtesting/backtest_engine.py",
                "code_patch": "# Heuristic change - manual review needed",
                "reasoning": f"Error getting AI proposal: {e}"
            }

    def apply_change(self, code_patch: Dict) -> bool:
        """
        Safely apply Claude-suggested change to strategy files
        
        Args:
            code_patch: Dict with file_path and code_patch
            
        Returns:
            True if successful, False otherwise
        """
        file_path = code_patch.get('file_path', '')
        code_change = code_patch.get('code_patch', '')
        
        if not file_path or not code_change:
            logger.error("❌ Invalid code patch: missing file_path or code_patch")
            return False
        
        full_path = self.repo_path / file_path
        
        if not full_path.exists():
            logger.error(f"❌ File not found: {full_path}")
            return False
        
        try:
            # Read current file
            with open(full_path, 'r') as f:
                current_code = f.read()
            
            # For now, we'll log the change and require manual review
            # In production, you'd parse the code_patch and apply it automatically
            logger.warning(f"⚠️  Code change requires manual review:")
            logger.warning(f"   File: {file_path}")
            logger.warning(f"   Change: {code_change[:200]}...")
            
            # Git commit the current state
            try:
                subprocess.run(
                    ['git', 'add', str(full_path)],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True
                )
                subprocess.run(
                    ['git', 'commit', '-m', f"Optimization iteration {self.iteration_count}: {code_patch.get('change_description', 'Change')}"],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True
                )
                logger.info(f"✅ Git commit created for iteration {self.iteration_count}")
            except subprocess.CalledProcessError as e:
                logger.warning(f"⚠️  Git commit failed (non-fatal): {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error applying change: {e}")
            return False

    def run_backtest(self, start_date: str = "2026-01-01", end_date: str = "2026-01-14") -> Dict:
        """
        Execute backtest and capture results
        
        Args:
            start_date: Start date for backtest
            end_date: End date for backtest
            
        Returns:
            Dict with backtest results
        """
        logger.info(f"🔄 Running backtest: {start_date} to {end_date}")
        
        try:
            # Run backtest
            result = subprocess.run(
                [sys.executable, str(self.repo_path / "run_backtest.py"),
                 "--start", start_date, "--end", end_date],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"❌ Backtest failed: {result.stderr}")
                return {}
            
            # Find the latest results JSON
            reports_dir = self.repo_path / "backtesting" / "reports"
            json_files = sorted(
                reports_dir.glob("results_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            if not json_files:
                logger.error("❌ No results JSON found")
                return {}
            
            latest_json = json_files[0]
            logger.info(f"📊 Loading results from: {latest_json}")
            
            with open(latest_json, 'r') as f:
                results = json.load(f)
            
            return results
            
        except subprocess.TimeoutExpired:
            logger.error("❌ Backtest timed out")
            return {}
        except Exception as e:
            logger.error(f"❌ Error running backtest: {e}")
            return {}

    def compare_results(self, old_results: Dict, new_results: Dict) -> Dict:
        """
        Compare old vs new results
        
        Args:
            old_results: Previous backtest results
            new_results: New backtest results
            
        Returns:
            Dict with improvement metrics
        """
        if not old_results or not new_results:
            return {'improvement_pct': 0, 'better': False}
        
        old_metrics = old_results.get('results', {}).get('trades', {})
        new_metrics = new_results.get('results', {}).get('trades', {})
        
        old_win_rate = old_metrics.get('win_rate', 0) * 100
        new_win_rate = new_metrics.get('win_rate', 0) * 100
        
        old_pnl = old_results.get('results', {}).get('summary', {}).get('total_pnl', 0)
        new_pnl = new_results.get('results', {}).get('summary', {}).get('total_pnl', 0)
        
        old_sharpe = new_results.get('metrics', {}).get('risk', {}).get('sharpe_ratio', 0)
        new_sharpe = new_results.get('metrics', {}).get('risk', {}).get('sharpe_ratio', 0)
        
        # Calculate improvement
        win_rate_improvement = new_win_rate - old_win_rate
        pnl_improvement = new_pnl - old_pnl
        sharpe_improvement = new_sharpe - old_sharpe
        
        # Overall improvement score (weighted)
        improvement_score = (
            win_rate_improvement * 0.3 +
            (pnl_improvement / 100) * 0.5 +  # Normalize PnL
            sharpe_improvement * 0.2
        )
        
        better = improvement_score > 0
        
        return {
            'improvement_pct': improvement_score,
            'better': better,
            'win_rate_change': win_rate_improvement,
            'pnl_change': pnl_improvement,
            'sharpe_change': sharpe_improvement
        }

    def optimization_loop(self, target_win_rate: float = 55, target_sharpe: float = 1.5,
                         max_iterations: int = 20, start_date: str = "2026-01-01",
                         end_date: str = "2026-01-14") -> Dict:
        """
        Main optimization loop
        
        Args:
            target_win_rate: Target win rate percentage
            target_sharpe: Target Sharpe ratio
            max_iterations: Maximum iterations to run
            start_date: Backtest start date
            end_date: Backtest end date
            
        Returns:
            Final results dict
        """
        logger.info(f"🚀 Starting optimization loop")
        logger.info(f"   Target: {target_win_rate}% win rate, {target_sharpe} Sharpe")
        logger.info(f"   Max iterations: {max_iterations}")
        
        # Run initial backtest
        initial_results = self.run_backtest(start_date, end_date)
        if not initial_results:
            logger.error("❌ Initial backtest failed")
            return {}
        
        self.current_best_results = initial_results
        initial_metrics = self.analyze_backtest_results()  # Will find latest automatically
        
        logger.info(f"📊 Initial metrics:")
        logger.info(f"   Win Rate: {initial_metrics['metrics']['win_rate']:.1f}%")
        logger.info(f"   PnL: ${initial_metrics['metrics']['total_pnl']:.2f}")
        logger.info(f"   Sharpe: {initial_metrics['metrics']['sharpe_ratio']:.2f}")
        
        # Optimization loop
        for iteration in range(1, max_iterations + 1):
            self.iteration_count = iteration
            logger.info(f"\n{'='*60}")
            logger.info(f"🔄 ITERATION {iteration}/{max_iterations}")
            logger.info(f"{'='*60}")
            
            # Check if targets met
            current_win_rate = initial_metrics['metrics']['win_rate']
            current_sharpe = initial_metrics['metrics']['sharpe_ratio']
            
            if current_win_rate >= target_win_rate and current_sharpe >= target_sharpe:
                logger.info("✅ TARGETS MET!")
                break
            
            # Analyze current results
            analysis = self.analyze_backtest_results()  # Will find latest automatically
            
            # Propose change
            proposal = self.propose_strategy_changes(analysis)
            
            # Apply change
            if not self.apply_change(proposal):
                logger.warning("⚠️  Failed to apply change, skipping iteration")
                continue
            
            # Run backtest
            new_results = self.run_backtest(start_date, end_date)
            if not new_results:
                logger.warning("⚠️  Backtest failed, reverting")
                # Git revert
                try:
                    subprocess.run(['git', 'reset', '--hard', 'HEAD~1'], cwd=self.repo_path, check=True)
                except:
                    pass
                continue
            
            # Compare results
            comparison = self.compare_results(self.current_best_results, new_results)
            
            # Log iteration
            iteration_log = {
                'iteration': iteration,
                'timestamp': datetime.now().isoformat(),
                'proposal': proposal.get('change_description', 'Unknown'),
                'old_metrics': initial_metrics['metrics'],
                'new_metrics': analysis['metrics'],
                'improvement': comparison,
                'kept': comparison['better'] or comparison['improvement_pct'] > -5  # Keep if not too bad
            }
            
            self.optimization_history.append(iteration_log)
            
            # Save history
            with open(self.history_file, 'w') as f:
                json.dump(self.optimization_history, f, indent=2)
            
            # Decide: keep or revert
            if comparison['better'] or comparison['improvement_pct'] > -5:
                logger.info(f"✅ Improvement: {comparison['improvement_pct']:.2f}% - KEEPING CHANGE")
                self.current_best_results = new_results
                initial_metrics = analysis
            else:
                logger.warning(f"❌ Degradation: {comparison['improvement_pct']:.2f}% - REVERTING")
                try:
                    subprocess.run(['git', 'reset', '--hard', 'HEAD~1'], cwd=self.repo_path, check=True)
                except:
                    pass
        
        # Final results
        final_metrics = self.analyze_backtest_results()  # Will find latest automatically
        
        return {
            'final_win_rate': final_metrics['metrics']['win_rate'],
            'final_sharpe': final_metrics['metrics']['sharpe_ratio'],
            'final_pnl': final_metrics['metrics']['total_pnl'],
            'iterations': self.iteration_count,
            'history': self.optimization_history
        }
