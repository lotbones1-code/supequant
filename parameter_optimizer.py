#!/usr/bin/env python3
"""
Parameter Optimizer
Auto-tuning framework that tests parameter variations and deploys best performing set

Usage:
    python parameter_optimizer.py --start 2024-01-01 --end 2024-03-31
    python parameter_optimizer.py --quick  # Quick 30-day test
    python parameter_optimizer.py --auto-deploy  # Auto-deploy if better
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import copy

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backtesting.historical_data_loader import HistoricalDataLoader
from backtesting.backtest_engine import BacktestEngine
from backtesting.performance_metrics import PerformanceMetrics
from strategy.breakout_strategy_v3 import BreakoutStrategyV3
import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/parameter_optimizer.log')
    ]
)

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """
    Auto-tuning framework for strategy parameters
    Tests variations and selects best performing set
    """

    def __init__(self, results_dir: str = "optimizer_results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
        self.experiments_file = self.results_dir / "experiments.json"
        self.best_params_file = self.results_dir / "best_params.json"
        
        # Load previous experiments
        self.experiments = self._load_experiments()
        self.best_params = self._load_best_params()

    def _load_experiments(self) -> List[Dict]:
        """Load previous experiment results"""
        if self.experiments_file.exists():
            try:
                with open(self.experiments_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load experiments: {e}")
        return []

    def _load_best_params(self) -> Optional[Dict]:
        """Load best parameters"""
        if self.best_params_file.exists():
            try:
                with open(self.best_params_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load best params: {e}")
        return None

    def _save_experiment(self, experiment: Dict):
        """Save experiment result"""
        self.experiments.append(experiment)
        with open(self.experiments_file, 'w') as f:
            json.dump(self.experiments, f, indent=2)

    def _save_best_params(self, params: Dict, performance: Dict):
        """Save best parameters"""
        best = {
            'params': params,
            'performance': performance,
            'date': datetime.now().isoformat()
        }
        with open(self.best_params_file, 'w') as f:
            json.dump(best, f, indent=2)
        self.best_params = best

    def generate_parameter_variations(self) -> List[Dict]:
        """
        Generate parameter variations to test
        
        Returns:
            List of parameter config dicts
        """
        variations = []
        
        # Base parameters (current V3 defaults)
        base = {
            'volume_ratio_threshold': 2.5,
            'stop_multipliers': {3.5: 1.2, 2.5: 1.5, 0: 2.0},
            'tp2_multiplier': 1.5,
            'tp3_multiplier': 3.0,
            'position_split': {1: 0.5, 2: 0.3, 3: 0.2}
        }
        variations.append(('base', base))
        
        # Variation 1: Tighter volume threshold (2.3)
        v1 = base.copy()
        v1['volume_ratio_threshold'] = 2.3
        variations.append(('volume_2.3', v1))
        
        # Variation 2: Looser volume threshold (2.8)
        v2 = base.copy()
        v2['volume_ratio_threshold'] = 2.8
        variations.append(('volume_2.8', v2))
        
        # Variation 3: Tighter stops (1.1/1.4/1.8)
        v3 = base.copy()
        v3['stop_multipliers'] = {3.5: 1.1, 2.5: 1.4, 0: 1.8}
        variations.append(('tighter_stops', v3))
        
        # Variation 4: Wider stops (1.3/1.6/2.2)
        v4 = base.copy()
        v4['stop_multipliers'] = {3.5: 1.3, 2.5: 1.6, 0: 2.2}
        variations.append(('wider_stops', v4))
        
        # Variation 5: Different TP levels (1.2x / 2.5x)
        v5 = base.copy()
        v5['tp2_multiplier'] = 1.2
        v5['tp3_multiplier'] = 2.5
        variations.append(('tp_1.2_2.5', v5))
        
        # Variation 6: Different position split (40/40/20)
        v6 = base.copy()
        v6['position_split'] = {1: 0.4, 2: 0.4, 3: 0.2}
        variations.append(('split_40_40_20', v6))
        
        # Variation 7: Different position split (60/30/10)
        v7 = base.copy()
        v7['position_split'] = {1: 0.6, 2: 0.3, 3: 0.1}
        variations.append(('split_60_30_10', v7))
        
        # Variation 8: Combined - tighter volume + tighter stops
        v8 = base.copy()
        v8['volume_ratio_threshold'] = 2.3
        v8['stop_multipliers'] = {3.5: 1.1, 2.5: 1.4, 0: 1.8}
        variations.append(('tight_volume_stops', v8))
        
        # Variation 9: Combined - looser volume + wider stops
        v9 = base.copy()
        v9['volume_ratio_threshold'] = 2.8
        v9['stop_multipliers'] = {3.5: 1.3, 2.5: 1.6, 0: 2.2}
        variations.append(('loose_volume_stops', v9))
        
        # Variation 10: Optimized TP + split
        v10 = base.copy()
        v10['tp2_multiplier'] = 1.2
        v10['tp3_multiplier'] = 2.5
        v10['position_split'] = {1: 0.4, 2: 0.4, 3: 0.2}
        variations.append(('optimized_tp_split', v10))
        
        return variations

    def run_backtest_with_params(self, params: Dict, start_date: str, end_date: str,
                                 initial_capital: float = 10000.0) -> Optional[Dict]:
        """
        Run backtest with specific parameters
        
        Args:
            params: Parameter config dict
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital
            
        Returns:
            Results dict or None if failed
        """
        try:
            # Load data
            data_loader = HistoricalDataLoader()
            timeframes_to_load = [config.HTF_TIMEFRAME, config.MTF_TIMEFRAME, config.LTF_TIMEFRAME, '1H']
            
            sol_data = data_loader.load_data(
                symbol=config.TRADING_SYMBOL,
                start_date=start_date,
                end_date=end_date,
                timeframes=timeframes_to_load,
                force_refresh=False
            )
            
            btc_data = data_loader.load_data(
                symbol=config.REFERENCE_SYMBOL,
                start_date=start_date,
                end_date=end_date,
                timeframes=timeframes_to_load,
                force_refresh=False
            )
            
            if not sol_data or not btc_data:
                return None
            
            # Create engine with parameterized strategy
            parameterized_strategy = BreakoutStrategyV3(config=params)
            engine = BacktestEngine(initial_capital=initial_capital, breakout_strategy=parameterized_strategy)
            
            # Run backtest
            results = engine.run(
                sol_data=sol_data,
                btc_data=btc_data,
                start_date=start_date,
                end_date=end_date
            )
            
            if not results:
                return None
            
            # Calculate metrics
            metrics = PerformanceMetrics.calculate_all(results, results['all_trades'])
            
            return {
                'results': results,
                'metrics': metrics
            }
            
        except Exception as e:
            logger.error(f"Backtest failed with params {params}: {e}")
            return None

    def optimize(self, start_date: str, end_date: str, initial_capital: float = 10000.0,
                 improvement_threshold: float = 0.05, auto_deploy: bool = False) -> Dict:
        """
        Run optimization loop
        
        Args:
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital
            improvement_threshold: Minimum improvement % to consider better (default 5%)
            auto_deploy: If True, automatically deploy best params if better
            
        Returns:
            Optimization results dict
        """
        logger.info("\n" + "="*80)
        logger.info("🚀 PARAMETER OPTIMIZATION STARTING")
        logger.info("="*80)
        logger.info(f"Period: {start_date} to {end_date}")
        logger.info(f"Capital: ${initial_capital:,.2f}")
        logger.info(f"Improvement Threshold: {improvement_threshold*100:.1f}%")
        logger.info("="*80 + "\n")
        
        # Get baseline (current best or default)
        baseline_params = self.best_params['params'] if self.best_params else {
            'volume_ratio_threshold': 2.5,
            'stop_multipliers': {3.5: 1.2, 2.5: 1.5, 0: 2.0},
            'tp2_multiplier': 1.5,
            'tp3_multiplier': 3.0,
            'position_split': {1: 0.5, 2: 0.3, 3: 0.2}
        }
        
        logger.info("📊 Running baseline backtest...")
        baseline_result = self.run_backtest_with_params(
            baseline_params, start_date, end_date, initial_capital
        )
        
        if not baseline_result:
            logger.error("❌ Baseline backtest failed")
            return {'success': False, 'error': 'Baseline failed'}
        
        baseline_return = baseline_result['metrics']['returns'].get('total_return_pct', 0)
        baseline_sharpe = baseline_result['metrics']['risk'].get('sharpe_ratio', 0)
        
        logger.info(f"✅ Baseline: {baseline_return:+.2f}% return, Sharpe: {baseline_sharpe:.2f}\n")
        
        # Test variations
        variations = self.generate_parameter_variations()
        best_result = baseline_result
        best_params = baseline_params
        best_name = 'baseline'
        best_return = baseline_return
        
        logger.info(f"🧪 Testing {len(variations)} parameter variations...\n")
        
        for name, params in variations:
            logger.info(f"Testing: {name}")
            logger.info(f"  Params: {json.dumps(params, indent=2)}")
            
            result = self.run_backtest_with_params(params, start_date, end_date, initial_capital)
            
            if not result:
                logger.warning(f"  ❌ Failed\n")
                continue
            
            return_pct = result['metrics']['returns'].get('total_return_pct', 0)
            sharpe = result['metrics']['risk'].get('sharpe_ratio', 0)
            win_rate = result['metrics']['trade_stats'].get('win_rate', 0)
            
            logger.info(f"  Return: {return_pct:+.2f}% | Sharpe: {sharpe:.2f} | Win Rate: {win_rate:.1f}%")
            
            # Save experiment
            experiment = {
                'name': name,
                'params': params,
                'performance': {
                    'return_pct': return_pct,
                    'sharpe_ratio': sharpe,
                    'win_rate': win_rate,
                    'total_trades': result['results']['trades']['total_trades'],
                    'profit_factor': result['metrics']['trade_stats'].get('profit_factor', 0)
                },
                'date': datetime.now().isoformat()
            }
            self._save_experiment(experiment)
            
            # Check if better
            improvement = return_pct - baseline_return
            if return_pct > best_return:
                logger.info(f"  ✅ NEW BEST! Improvement: {improvement:+.2f}%")
                best_result = result
                best_params = params
                best_name = name
                best_return = return_pct
            else:
                logger.info(f"  ⚠️  Worse by {abs(improvement):.2f}%")
            
            logger.info("")
        
        # Summary
        logger.info("="*80)
        logger.info("📊 OPTIMIZATION SUMMARY")
        logger.info("="*80)
        logger.info(f"Baseline Return: {baseline_return:+.2f}%")
        logger.info(f"Best Return: {best_return:+.2f}%")
        logger.info(f"Improvement: {best_return - baseline_return:+.2f}%")
        logger.info(f"Best Config: {best_name}")
        logger.info("="*80 + "\n")
        
        # Auto-deploy if better
        if auto_deploy and best_return > baseline_return * (1 + improvement_threshold):
            logger.info(f"🚀 AUTO-DEPLOYING: {best_name} ({best_return:+.2f}% vs {baseline_return:+.2f}%)")
            self._save_best_params(best_params, {
                'return_pct': best_return,
                'sharpe_ratio': best_result['metrics']['risk'].get('sharpe_ratio', 0),
                'win_rate': best_result['metrics']['trade_stats'].get('win_rate', 0)
            })
            logger.info("✅ Best parameters saved to optimizer_results/best_params.json")
        elif best_return > baseline_return:
            logger.info(f"💡 Found better params ({best_name}) but not auto-deploying")
            logger.info("   Use --auto-deploy to automatically save best params")
        else:
            logger.info("ℹ️  No improvement found, keeping baseline")
        
        return {
            'success': True,
            'baseline': {
                'return': baseline_return,
                'params': baseline_params
            },
            'best': {
                'name': best_name,
                'return': best_return,
                'params': best_params,
                'improvement': best_return - baseline_return
            },
            'experiments': len(variations)
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Optimize strategy parameters',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=10000.0, help='Initial capital')
    parser.add_argument('--quick', action='store_true', help='Quick 30-day test')
    parser.add_argument('--auto-deploy', action='store_true', help='Auto-deploy if better')
    parser.add_argument('--threshold', type=float, default=0.05, help='Improvement threshold (default: 0.05 = 5%%)')
    
    args = parser.parse_args()
    
    # Handle quick mode
    if args.quick:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    else:
        if not args.start or not args.end:
            parser.error("--start and --end are required (or use --quick)")
        start_date = args.start
        end_date = args.end
    
    # Run optimizer
    optimizer = ParameterOptimizer()
    result = optimizer.optimize(
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.capital,
        improvement_threshold=args.threshold,
        auto_deploy=args.auto_deploy
    )
    
    if result['success']:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
