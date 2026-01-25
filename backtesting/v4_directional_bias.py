"""
V4 Directional Bias Filter

Exploits the massive LONG vs SHORT win rate discrepancy discovered in analysis:
- LONG trades: 55% win rate
- SHORT trades: 8% win rate (6.6x worse!)

This filter blocks most shorts and only allows them under strict conditions.
"""

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class V4DirectionalBiasFilter:
    """
    Exploits the massive LONG vs SHORT win rate discrepancy.

    Rules:
    1. LONG signals: Always allowed (55% historical WR)
    2. SHORT signals: Only allowed if ALL 5 conditions met
    """

    def __init__(self):
        self.name = "V4DirectionalBias"

        # SHORT ALLOWANCE CONDITIONS (all must be true)
        self.SHORT_MIN_QUALITY = 65       # Higher quality bar for shorts
        self.SHORT_MIN_RSI = 75           # Must be extreme overbought
        self.SHORT_POSITION_MULT = 0.7    # Even if allowed, reduce size 30%

        # Statistics
        self.longs_allowed = 0
        self.shorts_allowed = 0
        self.shorts_blocked = 0
        self.block_reasons = {}

    def check(self, signal: Dict, market_state: Dict,
              quality_score: float, regime: str = 'unknown',
              prediction_direction: str = 'neutral') -> Tuple[bool, float, str]:
        """
        Check if signal should be allowed based on direction.

        Args:
            signal: Trade signal dict with 'direction', 'rsi', etc.
            market_state: Market state with timeframe data
            quality_score: Quality score from filter manager
            regime: Current market regime
            prediction_direction: From prediction system

        Returns:
            (allowed: bool, position_multiplier: float, reason: str)
        """
        direction = signal.get('direction', '').lower()

        # LONG: Always allowed with full size
        if direction == 'long':
            self.longs_allowed += 1
            return True, 1.0, "LONG allowed (55% historical WR)"

        # SHORT: Must pass 5 strict checks
        if direction == 'short':
            return self._check_short_conditions(
                signal, market_state, quality_score, regime, prediction_direction
            )

        # Unknown direction
        return False, 0.0, f"Unknown direction: {direction}"

    def _check_short_conditions(self, signal: Dict, market_state: Dict,
                                 quality_score: float, regime: str,
                                 prediction_direction: str) -> Tuple[bool, float, str]:
        """
        Check all 5 conditions for SHORT signals.
        SHORT must pass ALL conditions to be allowed.
        """

        # Condition 1: 4H trend must be bearish
        htf_trend = self._get_htf_trend(market_state)
        if htf_trend not in ['down', 'bearish', 'strong_down']:
            self.shorts_blocked += 1
            reason = f"4H trend '{htf_trend}' not bearish"
            self._record_block(reason)
            return False, 0.0, f"SHORT blocked: {reason}"

        # Condition 2: RSI must be extreme overbought (>75)
        rsi = signal.get('rsi', 50)
        if rsi is None:
            rsi = self._get_rsi_from_market(market_state)
        if rsi < self.SHORT_MIN_RSI:
            self.shorts_blocked += 1
            reason = f"RSI {rsi:.1f} < {self.SHORT_MIN_RSI} (not extreme overbought)"
            self._record_block(reason)
            return False, 0.0, f"SHORT blocked: {reason}"

        # Condition 3: Quality score must be higher for shorts
        if quality_score < self.SHORT_MIN_QUALITY:
            self.shorts_blocked += 1
            reason = f"Quality {quality_score:.0f} < {self.SHORT_MIN_QUALITY}"
            self._record_block(reason)
            return False, 0.0, f"SHORT blocked: {reason}"

        # Condition 4: Prediction system must agree (bearish)
        if prediction_direction not in ['bearish', 'strong_bearish', 'down']:
            self.shorts_blocked += 1
            reason = f"Prediction '{prediction_direction}' not bearish"
            self._record_block(reason)
            return False, 0.0, f"SHORT blocked: {reason}"

        # Condition 5: Regime must be trending down
        if regime not in ['trend_down', 'strong_trend_down', 'bearish_trend']:
            self.shorts_blocked += 1
            reason = f"Regime '{regime}' not bearish trend"
            self._record_block(reason)
            return False, 0.0, f"SHORT blocked: {reason}"

        # All 5 conditions passed - allow SHORT with reduced size
        self.shorts_allowed += 1
        logger.info(f"V4 SHORT ALLOWED: All 5 conditions met (RSI={rsi:.1f}, "
                   f"quality={quality_score:.0f}, regime={regime})")
        return True, self.SHORT_POSITION_MULT, "SHORT allowed: All 5 conditions met (size reduced 30%)"

    def _get_htf_trend(self, market_state: Dict) -> str:
        """Extract 4H trend from market state."""
        try:
            # Try various paths to find 4H trend
            if 'timeframes' in market_state:
                htf = market_state['timeframes'].get('4H', {})
                trend = htf.get('trend', {})
                return trend.get('trend_direction', 'neutral')

            if '4H' in market_state:
                return market_state['4H'].get('trend', {}).get('trend_direction', 'neutral')

            # Check for trend_direction at top level
            return market_state.get('trend_direction', 'neutral')
        except Exception:
            return 'neutral'

    def _get_rsi_from_market(self, market_state: Dict) -> float:
        """Extract RSI from market state if not in signal."""
        try:
            if 'timeframes' in market_state:
                mtf = market_state['timeframes'].get('15m', {})
                return mtf.get('rsi', {}).get('rsi', 50)

            if '15m' in market_state:
                return market_state['15m'].get('rsi', 50)

            return market_state.get('rsi', 50)
        except Exception:
            return 50

    def _record_block(self, reason: str):
        """Record block reason for statistics."""
        key = reason.split(':')[0] if ':' in reason else reason[:30]
        self.block_reasons[key] = self.block_reasons.get(key, 0) + 1

    def get_stats(self) -> Dict:
        """Get filter statistics."""
        total_shorts = self.shorts_allowed + self.shorts_blocked
        short_allow_rate = self.shorts_allowed / max(1, total_shorts)

        return {
            'longs_allowed': self.longs_allowed,
            'shorts_allowed': self.shorts_allowed,
            'shorts_blocked': self.shorts_blocked,
            'short_allow_rate': f"{short_allow_rate:.1%}",
            'block_reasons': self.block_reasons,
            'long_short_ratio': f"{self.longs_allowed}:{self.shorts_allowed}"
        }

    def reset_stats(self):
        """Reset statistics for new backtest run."""
        self.longs_allowed = 0
        self.shorts_allowed = 0
        self.shorts_blocked = 0
        self.block_reasons = {}
