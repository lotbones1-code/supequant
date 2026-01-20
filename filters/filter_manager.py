"""
Filter Manager
Orchestrates all filters and provides unified interface
Uses scoring system for quality filters, binary for critical filters
Enhanced with ConfidenceEngineV2 for elite position sizing
"""

from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone
import logging
from .market_regime import MarketRegimeFilter
from .market_regime_enhanced import MarketRegimeEnhancedFilter
from .multi_timeframe import MultiTimeframeFilter
from .ai_rejection import AIRejectionFilter
from .pattern_failure import PatternFailureFilter
from .btc_sol_correlation import BTCSOLCorrelationFilter
from .macro_driver import MacroDriverFilter
from .time_of_day import TimeOfDayFilter
from .funding_rate import FundingRateFilter
from .whale_filter import WhaleFilter
from .liquidation_filter import LiquidationFilter
from .open_interest import OpenInterestFilter
from .signal_scorer import SignalScorer
from research_filters import SOLPlaybookEngine, TradingChecklistFilter, DriverTierWeighting
import config

logger = logging.getLogger(__name__)


class FilterManager:
    """
    Manages all trading filters
    Ensures EVERY filter passes before allowing trade
    """

    def __init__(self):
        # Critical filters (binary - must pass)
        self.critical_filters = {
            'pattern_failure': PatternFailureFilter(),  # Must not be a trap
        }
        
        # Quality filters (scoring system)
        self.quality_filters = {
            'market_regime': MarketRegimeFilter(),
            'market_regime_enhanced': MarketRegimeEnhancedFilter(),  # Phase 2.1
            'multi_timeframe': MultiTimeframeFilter(),
            'ai_rejection': AIRejectionFilter(),
            'btc_sol_correlation': BTCSOLCorrelationFilter(),
            'macro_driver': MacroDriverFilter(),
            'time_of_day': TimeOfDayFilter(),  # Phase 2.3
            'funding_rate': FundingRateFilter(),  # Phase 2.4
            'whale_flow': WhaleFilter(),  # Phase 3.1
            'liquidation': LiquidationFilter(),  # Phase 3.3
            'open_interest': OpenInterestFilter(),  # Phase 3.4
            'checklist': TradingChecklistFilter(config)
        }
        
        # Signal scorer for quality metrics
        self.signal_scorer = SignalScorer()
        
        # Pattern matcher for adaptive learning (similarity to winners)
        try:
            from strategy.pattern_matcher import PatternMatcher
            self.pattern_matcher = PatternMatcher()
            logger.info(f"   Pattern matcher: Enabled ({self.pattern_matcher.get_statistics()['winning_patterns']} winning patterns)")
        except Exception as e:
            logger.warning(f"   Pattern matcher: Disabled ({e})")
            self.pattern_matcher = None

        # Research filters (advisory/enrichment)
        self.research_filters = {
            'sol_playbook': SOLPlaybookEngine(),
            'driver_weighting': DriverTierWeighting()
        }

        # ConfidenceEngineV2 for elite position sizing
        self.confidence_engine = None
        if getattr(config, 'CONFIDENCE_ENGINE_V2_ENABLED', False):
            try:
                from utils.confidence_v2 import ConfidenceEngineV2
                self.confidence_engine = ConfidenceEngineV2()
                logger.info(f"   ConfidenceEngineV2: ENABLED (dynamic position sizing)")
            except Exception as e:
                logger.warning(f"   ConfidenceEngineV2: Failed to load ({e})")
                self.confidence_engine = None
        else:
            logger.info(f"   ConfidenceEngineV2: Disabled")

        self.filter_stats = {
            'total_checks': 0,
            'passed': 0,
            'failed': 0,
            'failed_by_filter': {},
            'score_distribution': [],  # Track score distribution
            'confidence_distribution': []  # Track confidence distribution
        }

        logger.info(f"✅ FilterManager initialized with scoring system")
        logger.info(f"   Critical filters: {len(self.critical_filters)} (binary)")
        logger.info(f"   Quality filters: {len(self.quality_filters)} (scoring)")

    def check_all(self, market_state: Dict, signal_direction: str,
                 strategy_name: str, btc_market_state: Optional[Dict] = None) -> Tuple[bool, Dict]:
        """
        Run filters on a trade signal using scoring system
        
        Critical filters must pass (binary).
        Quality filters contribute to score (0-100).
        Trade allowed if score >= 50.

        Args:
            market_state: Complete market state from MarketDataFeed (for SOL)
            signal_direction: 'long' or 'short'
            strategy_name: 'breakout' or 'pullback'
            btc_market_state: Optional Bitcoin market state for correlation check

        Returns:
            (passed: bool, results: Dict with score, breakdown, position_size_multiplier)
        """
        self.filter_stats['total_checks'] += 1

        results = {
            'overall_pass': False,
            'filter_results': {},
            'failed_filters': [],
            'passed_filters': [],
            'score': 0,
            'score_breakdown': {},
            'position_size_multiplier': 1.0
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 FILTER CHECK: {signal_direction.upper()} {strategy_name}")
        logger.info(f"{'='*60}")

        # Step 1: Check critical filters (binary - must pass)
        for filter_name, filter_obj in self.critical_filters.items():
            if filter_name == 'pattern_failure':
                passed, reason = filter_obj.check(market_state, signal_direction)
            else:
                passed, reason = filter_obj.check(market_state)
            
            results['filter_results'][filter_name] = {
                'passed': passed,
                'reason': reason
            }
            
            if not passed:
                results['overall_pass'] = False
                results['failed_filters'].append(filter_name)
                self._log_failure(filter_name, reason)
                logger.info(f"❌ CRITICAL FILTER FAILED: {filter_name} - {reason}")
                logger.info(f"{'='*60}\n")
                self.filter_stats['failed'] += 1
                return False, results
            else:
                results['passed_filters'].append(filter_name)

        # Step 2: Score quality filters
        # Extract market data for scoring
        timeframes = market_state.get('timeframes', {})
        tf_15m = timeframes.get('15m', {})
        
        volume_data = tf_15m.get('volume', {})
        trend_data = tf_15m.get('trend', {})
        atr_data = tf_15m.get('atr', {})
        
        # Calculate RSI if not available
        candles = tf_15m.get('candles', [])
        rsi = None
        if candles and len(candles) >= 14:
            from data_feed.indicators import TechnicalIndicators
            indicators = TechnicalIndicators()
            closes = [c['close'] for c in candles]
            rsi = indicators.calculate_rsi(closes, period=14)
        
        # Get current price from candles if not in market_state
        current_price = market_state.get('current_price', 0)
        if current_price == 0 and candles:
            current_price = candles[-1].get('close', 0)
        
        # Prepare market data for scoring
        market_data_for_scoring = {
            'volume': volume_data.get('current_volume', 0),
            'avg_volume_20': volume_data.get('average_volume', 0),
            'trend': trend_data.get('trend_direction', 'neutral'),
            'trend_strength': trend_data.get('trend_strength', 0),  # Add trend strength
            'rsi_14': rsi if rsi is not None else 50,
            'atr': atr_data.get('atr', 0),
            'current_price': current_price
        }
        
        signal_for_scoring = {
            'direction': signal_direction
        }
        
        # Score the signal
        score, score_breakdown = self.signal_scorer.score_signal(
            market_data_for_scoring, signal_for_scoring
        )
        
        # Boost score based on similarity to winning patterns (adaptive learning)
        if self.pattern_matcher:
            try:
                market_context = {
                    'volatility': market_state.get('volatility', 0),
                    'volume_ratio': market_state.get('volume_ratio', 1),
                    'trend': market_state.get('trend', 'unknown')
                }
                pattern_score = self.pattern_matcher.score_signal(signal_for_scoring, market_context)
                # Blend pattern score with base score (30% pattern, 70% base)
                score = (score * 0.7) + (pattern_score * 0.3)
                score_breakdown['pattern_similarity'] = pattern_score
                logger.debug(f"   Pattern similarity boost: {pattern_score:.1f} (final score: {score:.1f})")
            except Exception as e:
                logger.debug(f"   Pattern matching failed: {e}")
        
        results['score'] = score
        results['score_breakdown'] = score_breakdown
        self.filter_stats['score_distribution'].append(score)
        
        # Step 3: Check if score meets threshold (adaptive - starts at 45, raises to 55 after learning)
        score_threshold = getattr(config, 'SCORE_THRESHOLD', 45)
        
        # Adaptive threshold: raise after enough trades if enabled
        if getattr(config, 'SCORE_THRESHOLD_ADAPTIVE_ENABLED', True):
            # Check if we have enough winning patterns learned
            if self.pattern_matcher:
                stats = self.pattern_matcher.get_statistics()
                total_patterns = stats.get('total_patterns', 0)
                winning_patterns = stats.get('winning_patterns', 0)
                
                # Raise threshold if we have 20+ winning patterns
                if winning_patterns >= getattr(config, 'SCORE_THRESHOLD_MIN_TRADES_FOR_ADAPTATION', 20):
                    score_threshold = getattr(config, 'SCORE_THRESHOLD_ADAPTED_VALUE', 55)
                    logger.debug(f"📈 Adaptive threshold raised: {score_threshold} (after {winning_patterns} winning patterns)")
            else:
                # Fallback: try to get stats from position tracker if available
                try:
                    from execution.position_tracker import PositionTracker
                    import sqlite3
                    # Try to read from database directly
                    conn = sqlite3.connect('trading.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM positions WHERE pnl > 0")
                    winning_trades = cursor.fetchone()[0]
                    conn.close()
                    
                    if winning_trades >= getattr(config, 'SCORE_THRESHOLD_MIN_TRADES_FOR_ADAPTATION', 20):
                        score_threshold = getattr(config, 'SCORE_THRESHOLD_ADAPTED_VALUE', 55)
                        logger.debug(f"📈 Adaptive threshold raised: {score_threshold} (after {winning_trades} winning trades)")
                except:
                    pass  # Fallback to default if can't get stats
        
        if score < score_threshold:
            results['overall_pass'] = False
            results['failed_filters'].append('quality_score')
            logger.info(f"❌ QUALITY SCORE TOO LOW: {score}/100 (minimum: {score_threshold})")
            logger.info(f"{'='*60}\n")
            self.filter_stats['failed'] += 1
            return False, results
        
        # Step 4: Enhanced confidence scoring with ConfidenceEngineV2
        confidence_band = 'MEDIUM'
        position_multiplier = 1.0
        adjusted_confidence = score
        confidence_details = {}
        
        if self.confidence_engine:
            try:
                # Build signal context for ConfidenceEngineV2
                signal_context = {
                    'symbol': 'SOL',
                    'direction': signal_direction,
                    'base_confidence': score,
                    'filters_passed': results['passed_filters'],
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'volatility': atr_data.get('atr', 0) / current_price if current_price > 0 else 0.02,
                    'trend_strength': trend_data.get('trend_strength', 0.5)
                }
                
                # Get enhanced confidence from V2 engine
                conf_result = self.confidence_engine.compute_confidence(signal_context)
                
                adjusted_confidence = conf_result['adjusted_confidence']
                confidence_band = conf_result['confidence_band']
                position_multiplier = conf_result['position_size_multiplier']
                confidence_details = conf_result
                
                # Track confidence distribution
                self.filter_stats['confidence_distribution'].append(adjusted_confidence)
                
                # Log the enhancement
                adjustment = conf_result['adjustment']
                if adjustment != 0:
                    logger.info(f"📊 ConfidenceEngineV2: {score:.0f} → {adjusted_confidence:.0f} ({adjustment:+.1f})")
                    logger.info(f"   Band: {confidence_band} | Multiplier: {position_multiplier}x")
                    components = conf_result.get('components', {})
                    if components:
                        logger.debug(f"   Components: filter={components.get('filter_score', 0):.2f}, "
                                    f"tod={components.get('time_of_day_score', 0):.2f}, "
                                    f"confluence={components.get('confluence_score', 0):.2f}, "
                                    f"market={components.get('market_score', 0):.2f}")
                
            except Exception as e:
                logger.warning(f"⚠️  ConfidenceEngineV2 failed, using base scoring: {e}")
                # Fall back to simple scoring
                if score >= 80:
                    position_multiplier = getattr(config, 'CONF_V2_ELITE_MULTIPLIER', 1.5)
                    confidence_band = 'ELITE'
                elif score >= 60:
                    position_multiplier = getattr(config, 'CONF_V2_HIGH_MULTIPLIER', 1.3)
                    confidence_band = 'HIGH'
                elif score >= 40:
                    position_multiplier = getattr(config, 'CONF_V2_MEDIUM_MULTIPLIER', 1.0)
                    confidence_band = 'MEDIUM'
                else:
                    position_multiplier = getattr(config, 'CONF_V2_LOW_MULTIPLIER', 0.5)
                    confidence_band = 'LOW'
        else:
            # No confidence engine - use simple thresholds from config
            if score >= 80:
                position_multiplier = getattr(config, 'CONF_V2_ELITE_MULTIPLIER', 1.5)
                confidence_band = 'ELITE'
            elif score >= 60:
                position_multiplier = getattr(config, 'CONF_V2_HIGH_MULTIPLIER', 1.3)
                confidence_band = 'HIGH'
            elif score >= 40:
                position_multiplier = getattr(config, 'CONF_V2_MEDIUM_MULTIPLIER', 1.0)
                confidence_band = 'MEDIUM'
            else:
                position_multiplier = getattr(config, 'CONF_V2_LOW_MULTIPLIER', 0.5)
                confidence_band = 'LOW'
        
        results['position_size_multiplier'] = position_multiplier
        results['confidence_band'] = confidence_band
        results['adjusted_confidence'] = adjusted_confidence
        results['confidence_details'] = confidence_details
        results['overall_pass'] = True
        
        # Log success
        logger.info(f"✅ SIGNAL PASSED - Score: {score:.0f}/100 → Confidence: {adjusted_confidence:.0f} ({confidence_band})")
        logger.info(f"   Position size multiplier: {position_multiplier}x")
        logger.info(f"{'='*60}\n")
        
        self.filter_stats['passed'] += 1
        return True, results

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

        # Filter 5: BTC-SOL Correlation (if enabled and BTC data available)
        if config.BTC_SOL_CORRELATION_ENABLED and btc_market_state:
            correlation_passed, correlation_reason = self.filters['btc_sol_correlation'].check(
                market_state, btc_market_state, signal_direction
            )
            results['filter_results']['btc_sol_correlation'] = {
                'passed': correlation_passed,
                'reason': correlation_reason
            }

            if not correlation_passed:
                results['overall_pass'] = False
                results['failed_filters'].append('btc_sol_correlation')
                self._log_failure('btc_sol_correlation', correlation_reason)
            else:
                results['passed_filters'].append('btc_sol_correlation')

        # Filter 6: Macro Driver (if enabled)
        macro_state = None
        if config.MACRO_DRIVER_ENABLED:
            macro_passed, macro_reason, macro_state = self.filters['macro_driver'].check(
                market_state, btc_market_state, signal_direction
            )
            results['filter_results']['macro_driver'] = {
                'passed': macro_passed,
                'reason': macro_reason,
                'macro_assessment': macro_state
            }

            if not macro_passed:
                results['overall_pass'] = False
                results['failed_filters'].append('macro_driver')
                self._log_failure('macro_driver', macro_reason)
            else:
                results['passed_filters'].append('macro_driver')

        # Filter 7: Trading Checklist (if enabled)
        checklist_details = None
        if config.CHECKLIST_ENABLED:
            checklist_passed, checklist_reason, checklist_details = self.filters['checklist'].check(
                market_state, macro_state, None  # TODO: Pass AI signals when available
            )
            results['filter_results']['checklist'] = {
                'passed': checklist_passed,
                'reason': checklist_reason,
                'details': checklist_details
            }

            if not checklist_passed:
                results['overall_pass'] = False
                results['failed_filters'].append('checklist')
                self._log_failure('checklist', checklist_reason)
            else:
                results['passed_filters'].append('checklist')

            # Store checklist multiplier for position sizing
            if checklist_details:
                results['position_size_multiplier'] = checklist_details.get('total_score', 80) / 100

        # Research Filter: SOL Playbook (advisory only, doesn't block)
        playbook_analysis = self.research_filters['sol_playbook'].analyze(
            market_state, btc_market_state
        )
        results['playbook_analysis'] = playbook_analysis
        logger.info(f"📖 Playbook: {playbook_analysis.get('setup', 'none')} setup (confidence: {playbook_analysis.get('confidence', 0):.2f})")

        # Research Filter: Driver Tier Weighting (advisory only, doesn't block)
        if macro_state and 'tier_outputs' in macro_state:
            tiers = macro_state['tier_outputs']
            tier_assessment = self.research_filters['driver_weighting'].aggregate_assessment(
                tiers.get('tier1', {}),
                tiers.get('tier2', {}),
                tiers.get('tier3', {}),
                tiers.get('tier4', {}),
                signal_direction
            )
            results['tier_assessment'] = tier_assessment
            logger.info(f"⚖️  Tier Assessment: {tier_assessment.get('environment_bias', 'neutral')} (score: {tier_assessment.get('weighted_score', 50):.1f})")

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
