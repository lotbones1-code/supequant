"""
Filter Manager
Orchestrates all filters and provides unified interface
ALL filters must pass before a trade is allowed
"""

from typing import Dict, Tuple, List
import logging
from .market_regime import MarketRegimeFilter
from .multi_timeframe import MultiTimeframeFilter
from .ai_rejection import AIRejectionFilter
from .pattern_failure import PatternFailureFilter

logger = logging.getLogger(__name__)


class FilterManager:
    """
    Manages all trading filters
    Ensures EVERY filter passes before allowing trade
    """

    def __init__(self):
        self.filters = {
            'market_regime': MarketRegimeFilter(),
            'multi_timeframe': MultiTimeframeFilter(),
            'ai_rejection': AIRejectionFilter(),
            'pattern_failure': PatternFailureFilter()
        }

        self.filter_stats = {
            'total_checks': 0,
            'passed': 0,
            'failed': 0,
            'failed_by_filter': {}
        }

        logger.info("✅ FilterManager initialized with 4 filters")

    def check_all(self, market_state: Dict, signal_direction: str,
                 strategy_name: str) -> Tuple[bool, Dict]:
        """
        Run ALL filters on a trade signal
        If ANY filter fails, trade is rejected

        Args:
            market_state: Complete market state from MarketDataFeed
            signal_direction: 'long' or 'short'
            strategy_name: 'breakout' or 'pullback'

        Returns:
            (all_passed: bool, results: Dict)
        """
        self.filter_stats['total_checks'] += 1

        results = {
            'overall_pass': True,
            'filter_results': {},
            'failed_filters': [],
            'passed_filters': []
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 FILTER CHECK: {signal_direction.upper()} {strategy_name}")
        logger.info(f"{'='*60}")

        # Run each filter in sequence
        # Order matters: cheaper checks first

        # Filter 1: Market Regime (fast check)
        regime_passed, regime_reason = self.filters['market_regime'].check(market_state)
        results['filter_results']['market_regime'] = {
            'passed': regime_passed,
            'reason': regime_reason
        }

        if not regime_passed:
            results['overall_pass'] = False
            results['failed_filters'].append('market_regime')
            self._log_failure('market_regime', regime_reason)
        else:
            results['passed_filters'].append('market_regime')

        # Filter 2: Pattern Failure (fast check)
        pattern_passed, pattern_reason = self.filters['pattern_failure'].check(
            market_state, signal_direction
        )
        results['filter_results']['pattern_failure'] = {
            'passed': pattern_passed,
            'reason': pattern_reason
        }

        if not pattern_passed:
            results['overall_pass'] = False
            results['failed_filters'].append('pattern_failure')
            self._log_failure('pattern_failure', pattern_reason)
        else:
            results['passed_filters'].append('pattern_failure')

        # Filter 3: Multi-Timeframe (moderate check)
        mtf_passed, mtf_reason = self.filters['multi_timeframe'].check(
            market_state, signal_direction
        )
        results['filter_results']['multi_timeframe'] = {
            'passed': mtf_passed,
            'reason': mtf_reason
        }

        if not mtf_passed:
            results['overall_pass'] = False
            results['failed_filters'].append('multi_timeframe')
            self._log_failure('multi_timeframe', mtf_reason)
        else:
            results['passed_filters'].append('multi_timeframe')

        # Filter 4: AI Rejection (most expensive check, run last)
        ai_passed, ai_reason = self.filters['ai_rejection'].check(
            market_state, signal_direction, strategy_name
        )
        results['filter_results']['ai_rejection'] = {
            'passed': ai_passed,
            'reason': ai_reason
        }

        if not ai_passed:
            results['overall_pass'] = False
            results['failed_filters'].append('ai_rejection')
            self._log_failure('ai_rejection', ai_reason)
        else:
            results['passed_filters'].append('ai_rejection')

        # Update stats
        if results['overall_pass']:
            self.filter_stats['passed'] += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ ALL FILTERS PASSED - TRADE ALLOWED")
            logger.info(f"{'='*60}\n")
        else:
            self.filter_stats['failed'] += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"❌ TRADE REJECTED")
            logger.info(f"Failed filters: {', '.join(results['failed_filters'])}")
            logger.info(f"{'='*60}\n")

        return results['overall_pass'], results

    def _log_failure(self, filter_name: str, reason: str):
        """Log filter failure"""
        if filter_name not in self.filter_stats['failed_by_filter']:
            self.filter_stats['failed_by_filter'][filter_name] = 0
        self.filter_stats['failed_by_filter'][filter_name] += 1

        logger.warning(f"❌ {filter_name}: {reason}")

    def get_filter_statistics(self) -> Dict:
        """
        Get statistics on filter performance

        Returns:
            Dict with filter stats
        """
        stats = self.filter_stats.copy()

        # Calculate pass rate
        if stats['total_checks'] > 0:
            stats['pass_rate'] = stats['passed'] / stats['total_checks']
            stats['reject_rate'] = stats['failed'] / stats['total_checks']
        else:
            stats['pass_rate'] = 0
            stats['reject_rate'] = 0

        return stats

    def get_individual_filter_stats(self) -> Dict:
        """
        Get stats for each individual filter

        Returns:
            Dict mapping filter name to stats
        """
        return {
            'market_regime': self._get_filter_specific_stats('market_regime'),
            'multi_timeframe': self._get_filter_specific_stats('multi_timeframe'),
            'ai_rejection': self._get_filter_specific_stats('ai_rejection'),
            'pattern_failure': self._get_filter_specific_stats('pattern_failure')
        }

    def _get_filter_specific_stats(self, filter_name: str) -> Dict:
        """Get stats for a specific filter"""
        fail_count = self.filter_stats['failed_by_filter'].get(filter_name, 0)
        total = self.filter_stats['total_checks']

        return {
            'total_checks': total,
            'failed': fail_count,
            'fail_rate': fail_count / total if total > 0 else 0
        }

    def reset_statistics(self):
        """Reset all filter statistics"""
        self.filter_stats = {
            'total_checks': 0,
            'passed': 0,
            'failed': 0,
            'failed_by_filter': {}
        }
        logger.info("Filter statistics reset")

    def get_market_quality_score(self, market_state: Dict, signal_direction: str) -> float:
        """
        Calculate overall market quality score (0-1)
        Even if not taking trade, useful to know market quality

        Returns:
            Quality score where 1.0 = perfect conditions
        """
        scores = []

        # Market regime score
        regime_filter = self.filters['market_regime']
        regime_score = regime_filter.get_regime_score(market_state)
        scores.append(regime_score)

        # Timeframe alignment score (0 or 1 based on pass/fail)
        mtf_filter = self.filters['multi_timeframe']
        mtf_passed, _ = mtf_filter.check(market_state, signal_direction)
        scores.append(1.0 if mtf_passed else 0.0)

        # Pattern failure score (0 or 1 based on pass/fail)
        pattern_filter = self.filters['pattern_failure']
        pattern_passed, _ = pattern_filter.check(market_state, signal_direction)
        scores.append(1.0 if pattern_passed else 0.0)

        # Average all scores
        overall_score = sum(scores) / len(scores)

        return overall_score

    def log_filter_summary(self):
        """Log a summary of filter performance"""
        stats = self.get_filter_statistics()

        logger.info("\n" + "="*60)
        logger.info("FILTER PERFORMANCE SUMMARY")
        logger.info("="*60)
        logger.info(f"Total checks: {stats['total_checks']}")
        logger.info(f"Passed: {stats['passed']} ({stats['pass_rate']*100:.1f}%)")
        logger.info(f"Rejected: {stats['failed']} ({stats['reject_rate']*100:.1f}%)")
        logger.info("\nRejections by filter:")

        for filter_name, count in stats['failed_by_filter'].items():
            rate = count / stats['total_checks'] * 100 if stats['total_checks'] > 0 else 0
            logger.info(f"  {filter_name}: {count} ({rate:.1f}%)")

        logger.info("="*60 + "\n")
