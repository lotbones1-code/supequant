"""
Parameter Optimizer
Auto-tests parameter variations, finds best performers, deploys winners
Run weekly to continuously improve strategy
"""

import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import itertools

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class ParameterOptimizer:
    """
    Auto-tests strategy parameter variations
    Tracks results and deploys best performers
    """

    def __init__(self, symbol: str = "SOLUSDT", start_date: str = "2025-12-15", end_date: str = "2026-01-14"):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.results_file = Path("backtesting/optimization_results.json")
        self.current_best = self._load_best_params()
        self.test_results = []

    def _load_best_params(self) -> Dict:
        """Load current best parameters from file"""
        if self.results_file.exists():
            with open(self.results_file) as f:
                data = json.load(f)
                return data.get('current_best', self._default_params())
        return self._default_params()

    def _default_params(self) -> Dict:
        """V3 current best parameters"""
        return {
            'volume_ratio_min': 2.5,
            'volume_ratio_strong': 3.5,
            'stop_mult_weak': 2.0,
            'stop_mult_medium': 1.5,
            'stop_mult_strong': 1.2,
            'tp1_pct': 0.0,  # Breakeven
            'tp2_ratio': 1.5,  # 1.5x risk
            'tp3_ratio': 3.0,  # 3.0x risk
            'tp_split_1': 0.5,
            'tp_split_2': 0.3,
            'tp_split_3': 0.2,
            'pullback_threshold': 0.995,
        }

    def generate_variations(self) -> List[Dict]:
        """
        Generate parameter variations to test
        Tests realistic ranges around current best
        """
        variations = []
        current = self.current_best

        # Volume ratio variations
        volume_mins = [2.3, 2.5, 2.7]  # Test tighter/looser
        volume_strongs = [3.3, 3.5, 3.7]

        # Stop loss multiplier variations
        stop_weak = [1.8, 2.0, 2.2]
        stop_medium = [1.3, 1.5, 1.7]
        stop_strong = [1.0, 1.2, 1.4]

        # TP ratio variations
        tp2_ratios = [1.3, 1.5, 1.7]
        tp3_ratios = [2.5, 3.0, 3.5]

        # TP split variations
        tp_splits = [
            (0.4, 0.4, 0.2),  # More balanced
            (0.5, 0.3, 0.2),  # Current
            (0.5, 0.25, 0.25),  # More runners
            (0.6, 0.25, 0.15),  # Lock profits early
        ]

        # Create combinations (sample to avoid too many tests)
        for vol_min, vol_strong, stop_w, stop_m, stop_s, tp2, tp3, split in itertools.product(
            volume_mins, volume_strongs, stop_weak, stop_medium, stop_strong, tp2_ratios, tp3_ratios, tp_splits
        ):
            # Skip if volume thresholds don't make sense
            if vol_min >= vol_strong:
                continue

            variation = {
                'volume_ratio_min': vol_min,
                'volume_ratio_strong': vol_strong,
                'stop_mult_weak': stop_w,
                'stop_mult_medium': stop_m,
                'stop_mult_strong': stop_s,
                'tp2_ratio': tp2,
                'tp3_ratio': tp3,
                'tp_split_1': split[0],
                'tp_split_2': split[1],
                'tp_split_3': split[2],
            }
            variations.append(variation)

        # Limit to top candidates by randomness (test ~50 variations)
        import random
        if len(variations) > 50:
            variations = random.sample(variations, 50)

        logger.info(f"🧪 Generated {len(variations)} parameter variations to test")
        return variations

    def test_variation(self, params: Dict) -> Dict:
        """
        Run backtest with specific parameters
        Extracts key metrics
        """
        try:
            # Inject parameters into strategy
            self._inject_params(params)

            # Run backtest
            logger.info(f"🏃 Testing: volume={params['volume_ratio_min']:.1f}, "
                       f"stop={params['stop_mult_medium']:.1f}x, tp2={params['tp2_ratio']:.1f}x")

            result = subprocess.run(
                ["python", "backtest.py", "--symbol", self.symbol,
                 "--start-date", self.start_date, "--end-date", self.end_date],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                logger.error(f"❌ Backtest failed: {result.stderr}")
                return {'error': 'backtest_failed'}

            # Parse results
            metrics = self._parse_results(result.stdout)
            metrics['params'] = params
            metrics['timestamp'] = datetime.now().isoformat()

            return metrics

        except Exception as e:
            logger.error(f"❌ Test variation error: {e}")
            return {'error': str(e)}

    def _inject_params(self, params: Dict):
        """
        Inject parameters into strategy file
        V3 will read these values
        """
        # Create config file for strategy to read
        config = {
            'volume_ratio_min': params['volume_ratio_min'],
            'volume_ratio_strong': params['volume_ratio_strong'],
            'stop_mult_weak': params['stop_mult_weak'],
            'stop_mult_medium': params['stop_mult_medium'],
            'stop_mult_strong': params['stop_mult_strong'],
            'tp2_ratio': params['tp2_ratio'],
            'tp3_ratio': params['tp3_ratio'],
            'tp_split': {
                1: params['tp_split_1'],
                2: params['tp_split_2'],
                3: params['tp_split_3'],
            }
        }
        with open('strategy/v3_params_test.json', 'w') as f:
            json.dump(config, f, indent=2)

    def _parse_results(self, output: str) -> Dict:
        """
        Extract key metrics from backtest output
        """
        metrics = {
            'total_return': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'max_drawdown': 0,
            'expectancy': 0,
            'trades': 0,
        }

        # Parse backtest output
        for line in output.split('\n'):
            if 'Total Return:' in line or 'Total PnL:' in line:
                try:
                    metrics['total_return'] = float(line.split('%')[0].split()[-1])
                except:
                    pass
            elif 'Win Rate:' in line:
                try:
                    metrics['win_rate'] = float(line.split('%')[0].split()[-1])
                except:
                    pass
            elif 'Profit Factor:' in line:
                try:
                    metrics['profit_factor'] = float(line.split(':')[-1].strip())
                except:
                    pass
            elif 'Max Drawdown:' in line:
                try:
                    metrics['max_drawdown'] = float(line.split('%')[0].split()[-1])
                except:
                    pass
            elif 'Expectancy:' in line:
                try:
                    metrics['expectancy'] = float(line.split('$')[-1].split('/')[0].strip())
                except:
                    pass
            elif 'Trades Executed:' in line:
                try:
                    metrics['trades'] = int(line.split(':')[-1].strip())
                except:
                    pass

        return metrics

    def score_results(self, results: List[Dict]) -> List[Tuple[Dict, float]]:
        """
        Score results by multiple factors
        Higher score = better parameters
        """
        scored = []

        for result in results:
            if 'error' in result:
                score = -999
            else:
                # Weighted scoring
                return_score = result.get('total_return', 0) * 100  # 100x weight on returns
                win_rate_score = (result.get('win_rate', 0) - 30) * 5  # Prefer 50%+ win rate
                pf_score = (result.get('profit_factor', 0) - 0.87) * 50  # Prefer 1.3+
                drawdown_penalty = abs(result.get('max_drawdown', 0)) * 10  # Penalize large drawdowns

                score = return_score + win_rate_score + pf_score - drawdown_penalty

            scored.append((result, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def run_optimization(self, max_tests: int = 20):
        """
        Run full optimization cycle
        Tests variations and identifies best
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 PARAMETER OPTIMIZATION RUN")
        logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}\n")

        # Generate variations
        variations = self.generate_variations()
        variations = variations[:max_tests]  # Limit to max_tests

        logger.info(f"📊 Testing {len(variations)} parameter variations...\n")

        # Test each variation
        all_results = []
        for i, params in enumerate(variations, 1):
            logger.info(f"[{i}/{len(variations)}] Testing...")
            result = self.test_variation(params)
            all_results.append(result)

        # Score and rank
        scored = self.score_results(all_results)

        # Show top 5
        logger.info(f"\n{'='*60}")
        logger.info(f"🏆 TOP 5 RESULTS")
        logger.info(f"{'='*60}\n")

        for rank, (result, score) in enumerate(scored[:5], 1):
            if 'error' not in result:
                params = result['params']
                logger.info(f"#{rank} | Score: {score:.1f}")
                logger.info(f"  Return: {result.get('total_return', 0):.2f}% | "
                           f"Win Rate: {result.get('win_rate', 0):.1f}% | "
                           f"PF: {result.get('profit_factor', 0):.2f}")
                logger.info(f"  Params: vol={params['volume_ratio_min']:.1f}, "
                           f"stop={params['stop_mult_medium']:.1f}x, "
                           f"tp2={params['tp2_ratio']:.1f}x\n")

        # Check if new best beats current
        best_result, best_score = scored[0]
        current_return = self.current_best.get('last_return', -999)
        new_return = best_result.get('total_return', -999)

        logger.info(f"{'='*60}")
        logger.info(f"📈 DECISION")
        logger.info(f"{'='*60}")
        logger.info(f"Current best return: {current_return:.2f}%")
        logger.info(f"New best return: {new_return:.2f}%")
        logger.info(f"Improvement: {new_return - current_return:.2f}%\n")

        if new_return > current_return:
            logger.info(f"✅ NEW BEST FOUND! Deploying...\n")
            self._deploy_best_params(best_result)
            return True
        else:
            logger.info(f"❌ Current parameters still best. No change.\n")
            return False

    def _deploy_best_params(self, result: Dict):
        """
        Save best parameters for deployment
        Strategy will use these on next run
        """
        best_data = {
            'current_best': result['params'],
            'last_return': result.get('total_return', 0),
            'last_win_rate': result.get('win_rate', 0),
            'last_pf': result.get('profit_factor', 0),
            'deployed_date': datetime.now().isoformat(),
            'test_results': result,
        }

        with open(self.results_file, 'w') as f:
            json.dump(best_data, f, indent=2)

        logger.info(f"💾 Best parameters saved to {self.results_file}")
        logger.info(f"📄 Strategy will use new parameters on next run")


if __name__ == "__main__":
    # Run optimization
    optimizer = ParameterOptimizer(
        symbol="SOLUSDT",
        start_date="2025-12-15",
        end_date="2026-01-14"
    )

    # Test 20 variations (adjust for more comprehensive testing)
    improved = optimizer.run_optimization(max_tests=20)

    if improved:
        logger.info(f"\n🎉 Strategy improved! Deploy to live trading.")
    else:
        logger.info(f"\n📊 No improvement found. Keep current parameters.")
