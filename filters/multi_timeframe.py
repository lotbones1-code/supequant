"""
Multi-Timeframe Trend Filter
Ensures trend alignment across multiple timeframes
Entry only allowed when HTF, MTF, and LTF all agree
"""

from typing import Dict, Optional, Tuple, List
import logging
from config import (
    HTF_TIMEFRAME,
    MTF_TIMEFRAME,
    LTF_TIMEFRAME,
    HTF_TREND_MIN_STRENGTH,
    MTF_TREND_MIN_STRENGTH,
    LTF_TREND_MIN_STRENGTH,
    TIMEFRAME_ALIGNMENT_THRESHOLD
)

logger = logging.getLogger(__name__)


class MultiTimeframeFilter:
    """
    Filter #2: Multi-Timeframe Trend Alignment
    Requires trend agreement across HTF, MTF, and LTF
    """

    def __init__(self):
        self.name = "MultiTimeframe"

    def check(self, market_state: Dict, signal_direction: str) -> Tuple[bool, str]:
        """
        Check if all timeframes align with signal direction

        Args:
            market_state: Complete market state
            signal_direction: 'long' or 'short'

        Returns:
            (passed: bool, reason: str)
        """
        try:
            timeframes = market_state.get('timeframes', {})

            # Get trend data for each timeframe
            htf_trend = self._get_trend_data(timeframes, HTF_TIMEFRAME)
            mtf_trend = self._get_trend_data(timeframes, MTF_TIMEFRAME)
            ltf_trend = self._get_trend_data(timeframes, LTF_TIMEFRAME)

            # If HTF data is missing (e.g., 4H timeframe not available), allow the trade
            # This is common when requesting recent data where larger timeframes may not have completed candles
            if not htf_trend:
                logger.warning(f"⚠️  {self.name}: HTF ({HTF_TIMEFRAME}) data not available, allowing trade")
                return True, "HTF data not available, skipping check"
            
            # MTF and LTF are still required
            if not all([mtf_trend, ltf_trend]):
                return False, "Missing trend data for MTF or LTF timeframes"

            # Check 1: HTF must show strong trend in signal direction
            htf_check = self._check_timeframe_trend(
                htf_trend,
                signal_direction,
                HTF_TREND_MIN_STRENGTH,
                "HTF"
            )
            if not htf_check[0]:
                return htf_check

            # Check 2: MTF must confirm the trend
            mtf_check = self._check_timeframe_trend(
                mtf_trend,
                signal_direction,
                MTF_TREND_MIN_STRENGTH,
                "MTF"
            )
            if not mtf_check[0]:
                return mtf_check

            # Check 3: LTF must align (can be weaker)
            ltf_check = self._check_timeframe_trend(
                ltf_trend,
                signal_direction,
                LTF_TREND_MIN_STRENGTH,
                "LTF"
            )
            if not ltf_check[0]:
                return ltf_check

            # Check 4: Calculate overall alignment score
            alignment_score = self._calculate_alignment_score(
                htf_trend, mtf_trend, ltf_trend, signal_direction
            )

            if alignment_score < TIMEFRAME_ALIGNMENT_THRESHOLD:
                return False, f"Timeframe alignment too weak ({alignment_score:.2f} < {TIMEFRAME_ALIGNMENT_THRESHOLD})"

            # All checks passed
            logger.info(f"✅ {self.name}: All timeframes aligned {signal_direction} (score: {alignment_score:.2f})")
            return True, f"Timeframes aligned {signal_direction}"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            return False, f"Filter error: {e}"

    def _get_trend_data(self, timeframes: Dict, tf: str) -> Optional[Dict]:
        """Extract trend data for a specific timeframe"""
        if tf not in timeframes:
            logger.warning(f"{self.name}: Timeframe {tf} not available")
            return None

        tf_data = timeframes[tf]
        return tf_data.get('trend')

    def _check_timeframe_trend(self, trend_data: Dict, signal_direction: str,
                              min_strength: float, tf_name: str) -> Tuple[bool, str]:
        """
        Check if a single timeframe's trend aligns with signal

        Args:
            trend_data: Trend metrics for the timeframe
            signal_direction: 'long' or 'short'
            min_strength: Minimum trend strength required
            tf_name: Name for logging (HTF/MTF/LTF)
        """
        if not trend_data:
            return False, f"{tf_name} trend data unavailable"

        trend_direction = trend_data.get('trend_direction', 'sideways')
        trend_strength = trend_data.get('trend_strength', 0)

        # Check if trend strength is sufficient
        if trend_strength < min_strength:
            return False, f"{tf_name} trend too weak ({trend_strength:.2f} < {min_strength})"

        # Check if trend direction matches signal
        if signal_direction == 'long':
            if trend_direction != 'up':
                return False, f"{tf_name} trend is {trend_direction}, need up for long"
        elif signal_direction == 'short':
            if trend_direction != 'down':
                return False, f"{tf_name} trend is {trend_direction}, need down for short"

        return True, f"{tf_name} trend aligned ({trend_direction}, strength {trend_strength:.2f})"

    def _calculate_alignment_score(self, htf_trend: Dict, mtf_trend: Dict,
                                   ltf_trend: Dict, signal_direction: str) -> float:
        """
        Calculate overall timeframe alignment score (0-1)

        Considers:
        - Trend direction match
        - Trend strength
        - EMA alignment
        """
        score = 0.0
        max_score = 0.0

        # HTF contribution (weight: 3)
        htf_contribution = self._get_trend_contribution(htf_trend, signal_direction) * 3
        score += htf_contribution
        max_score += 3

        # MTF contribution (weight: 2)
        mtf_contribution = self._get_trend_contribution(mtf_trend, signal_direction) * 2
        score += mtf_contribution
        max_score += 2

        # LTF contribution (weight: 1)
        ltf_contribution = self._get_trend_contribution(ltf_trend, signal_direction) * 1
        score += ltf_contribution
        max_score += 1

        return score / max_score if max_score > 0 else 0

    def _get_trend_contribution(self, trend_data: Dict, signal_direction: str) -> float:
        """
        Calculate how much a single timeframe contributes to alignment (0-1)
        """
        if not trend_data:
            return 0.0

        contribution = 0.0

        # Base contribution from trend strength
        trend_strength = trend_data.get('trend_strength', 0)
        contribution += trend_strength * 0.5

        # Bonus for correct direction
        trend_direction = trend_data.get('trend_direction', 'sideways')
        if (signal_direction == 'long' and trend_direction == 'up') or \
           (signal_direction == 'short' and trend_direction == 'down'):
            contribution += 0.3

        # Bonus for EMA alignment
        ema_short = trend_data.get('ema_short', 0)
        ema_long = trend_data.get('ema_long', 0)

        if ema_short and ema_long:
            if (signal_direction == 'long' and ema_short > ema_long) or \
               (signal_direction == 'short' and ema_short < ema_long):
                contribution += 0.2

        return min(contribution, 1.0)

    def get_divergence_signals(self, market_state: Dict) -> List[str]:
        """
        Check for timeframe divergences (warning signals)

        Returns list of warnings like:
        - "HTF bearish but MTF bullish"
        - "Weakening momentum on LTF"
        """
        warnings = []
        timeframes = market_state.get('timeframes', {})

        htf_trend = self._get_trend_data(timeframes, HTF_TIMEFRAME)
        mtf_trend = self._get_trend_data(timeframes, MTF_TIMEFRAME)
        ltf_trend = self._get_trend_data(timeframes, LTF_TIMEFRAME)

        if not all([htf_trend, mtf_trend, ltf_trend]):
            return warnings

        # Check for direction mismatches
        htf_dir = htf_trend.get('trend_direction', 'sideways')
        mtf_dir = mtf_trend.get('trend_direction', 'sideways')
        ltf_dir = ltf_trend.get('trend_direction', 'sideways')

        if htf_dir != mtf_dir and htf_dir != 'sideways' and mtf_dir != 'sideways':
            warnings.append(f"HTF {htf_dir} but MTF {mtf_dir}")

        if mtf_dir != ltf_dir and mtf_dir != 'sideways' and ltf_dir != 'sideways':
            warnings.append(f"MTF {mtf_dir} but LTF {ltf_dir}")

        # Check for weakening trends
        if htf_trend.get('trend_strength', 1) < HTF_TREND_MIN_STRENGTH * 0.8:
            warnings.append("HTF trend weakening")

        if mtf_trend.get('trend_strength', 1) < MTF_TREND_MIN_STRENGTH * 0.8:
            warnings.append("MTF trend weakening")

        return warnings

    def get_best_entry_timeframe(self, market_state: Dict, signal_direction: str) -> Optional[str]:
        """
        Determine which timeframe is best for entry timing
        Usually the LTF, but checks for optimal alignment
        """
        # Check if overall alignment is good
        passed, reason = self.check(market_state, signal_direction)

        if not passed:
            return None

        # Prefer LTF for precise entry
        return LTF_TIMEFRAME
