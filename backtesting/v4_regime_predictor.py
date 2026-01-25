"""
V4 Regime Predictor

Predicts regime CHANGES before they occur (predictive, not reactive).

Leading indicators for regime transitions:
1. ADX turning points (ADX starting to decline = trend exhaustion)
2. Bollinger Band squeeze (compression precedes expansion)
3. Volume pattern (declining volume in trend = exhaustion)
4. RSI divergence (price new high but RSI lower high)

Each regime has OPTIMIZED parameters for:
- Enable/disable strategies
- Position size multiplier
- Quality threshold
- RSI thresholds
"""

import logging
import numpy as np
from typing import Dict, Tuple, List, Optional
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications."""
    STRONG_TREND_UP = "strong_trend_up"
    TREND_UP = "trend_up"
    RANGING = "ranging"
    TREND_DOWN = "trend_down"
    STRONG_TREND_DOWN = "strong_trend_down"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


class V4RegimePredictor:
    """
    Predicts regime changes BEFORE they occur.
    Uses leading indicators to anticipate transitions.
    """

    # Regime-specific trading parameters (OPTIMIZED)
    REGIME_PARAMS = {
        MarketRegime.STRONG_TREND_UP: {
            'enable_mr': False,          # No mean reversion in strong trends
            'enable_momentum': True,
            'enable_breakout': True,
            'mr_rsi_oversold': 20,        # Very strict - only extreme
            'mr_rsi_overbought': 85,
            'quality_threshold': 55,      # Higher bar
            'position_mult': 0.6,         # Smaller positions (trends can reverse)
            'prefer_direction': 'long',
        },
        MarketRegime.TREND_UP: {
            'enable_mr': True,
            'enable_momentum': True,
            'enable_breakout': True,
            'mr_rsi_oversold': 25,
            'mr_rsi_overbought': 80,
            'quality_threshold': 50,
            'position_mult': 0.8,
            'prefer_direction': 'long',
        },
        MarketRegime.RANGING: {
            'enable_mr': True,            # Mean reversion works best here
            'enable_momentum': True,
            'enable_breakout': True,
            'mr_rsi_oversold': 30,
            'mr_rsi_overbought': 70,
            'quality_threshold': 45,      # Lower bar - more opportunities
            'position_mult': 1.0,         # Full size
            'prefer_direction': None,     # No preference
        },
        MarketRegime.TREND_DOWN: {
            'enable_mr': True,
            'enable_momentum': True,
            'enable_breakout': True,
            'mr_rsi_oversold': 20,
            'mr_rsi_overbought': 75,
            'quality_threshold': 50,
            'position_mult': 0.8,
            'prefer_direction': 'short',
        },
        MarketRegime.STRONG_TREND_DOWN: {
            'enable_mr': False,
            'enable_momentum': True,
            'enable_breakout': True,
            'mr_rsi_oversold': 15,
            'mr_rsi_overbought': 80,
            'quality_threshold': 55,
            'position_mult': 0.6,
            'prefer_direction': 'short',
        },
        MarketRegime.HIGH_VOLATILITY: {
            'enable_mr': True,            # MR can work with wider bands
            'enable_momentum': False,     # Too dangerous
            'enable_breakout': False,     # False breakouts common
            'mr_rsi_oversold': 20,
            'mr_rsi_overbought': 80,
            'quality_threshold': 60,      # Much higher bar
            'position_mult': 0.4,         # Small positions
            'prefer_direction': None,
        },
        MarketRegime.UNKNOWN: {
            'enable_mr': True,
            'enable_momentum': True,
            'enable_breakout': True,
            'mr_rsi_oversold': 30,
            'mr_rsi_overbought': 70,
            'quality_threshold': 50,
            'position_mult': 0.7,
            'prefer_direction': None,
        },
    }

    def __init__(self):
        self.name = "V4RegimePredictor"

        self.current_regime = MarketRegime.UNKNOWN
        self.predicted_regime = MarketRegime.UNKNOWN
        self.regime_confidence = 0.5

        # Prediction horizon
        self.prediction_horizon = 12  # Predict 12 bars (3 hours) ahead

        # Leading indicator history
        self.adx_history = deque(maxlen=30)
        self.bb_width_history = deque(maxlen=30)
        self.volume_history = deque(maxlen=30)
        self.price_history = deque(maxlen=50)

        # Regime change tracking
        self.regime_changes = 0
        self.predictions_made = 0
        self.correct_predictions = 0

    def analyze(self, candles: List[Dict], market_state: Dict = None) -> Tuple[MarketRegime, float, Dict]:
        """
        Analyze current market and predict future regime.

        Args:
            candles: List of recent candles (need at least 30)
            market_state: Optional market state dict

        Returns:
            (predicted_regime, confidence, indicators)
        """
        self.predictions_made += 1

        if len(candles) < 30:
            return self.current_regime, 0.5, {}

        # Extract price data
        closes = [c['close'] for c in candles[-50:]]
        highs = [c['high'] for c in candles[-50:]]
        lows = [c['low'] for c in candles[-50:]]
        volumes = [c.get('volume', 0) for c in candles[-50:]]

        # Calculate indicators
        adx = self._calculate_adx(candles[-30:])
        bb_width = self._calculate_bb_width(closes[-20:])
        volume_trend = self._calculate_volume_trend(volumes[-10:])

        # Update history
        self.adx_history.append(adx)
        self.bb_width_history.append(bb_width)
        self.volume_history.append(np.mean(volumes[-5:]))

        # Determine current regime
        current = self._classify_current_regime(adx, bb_width, closes, market_state)

        # Predict future regime based on leading indicators
        predicted, confidence, indicators = self._predict_future_regime(
            current, adx, bb_width, volume_trend, closes
        )

        # Update state
        if self.current_regime != current:
            self.regime_changes += 1
        self.current_regime = current
        self.predicted_regime = predicted
        self.regime_confidence = confidence

        indicators.update({
            'adx': adx,
            'bb_width': bb_width,
            'volume_trend': volume_trend,
            'current_regime': current.value,
            'predicted_regime': predicted.value
        })

        return predicted, confidence, indicators

    def _classify_current_regime(self, adx: float, bb_width: float,
                                  closes: List[float], market_state: Dict = None) -> MarketRegime:
        """Classify current market regime based on indicators."""

        # Calculate trend direction from closes
        if len(closes) >= 20:
            sma_fast = np.mean(closes[-5:])
            sma_slow = np.mean(closes[-20:])
            trend_direction = 'up' if sma_fast > sma_slow else 'down'
        else:
            trend_direction = 'neutral'

        # Try to get from market state if available
        if market_state:
            trend_strength = market_state.get('trend', {}).get('trend_strength', 0.5)
        else:
            # Estimate trend strength from ADX
            trend_strength = min(1.0, adx / 50)

        # Check for high volatility first
        if len(self.bb_width_history) > 5:
            avg_bb = np.mean(list(self.bb_width_history))
            if bb_width > avg_bb * 1.5:  # 50% above average
                return MarketRegime.HIGH_VOLATILITY

        # Classify by ADX and trend direction
        if adx > 40:
            # Strong trend
            if trend_direction == 'up':
                return MarketRegime.STRONG_TREND_UP
            else:
                return MarketRegime.STRONG_TREND_DOWN
        elif adx > 25:
            # Moderate trend
            if trend_direction == 'up':
                return MarketRegime.TREND_UP
            else:
                return MarketRegime.TREND_DOWN
        else:
            # Ranging
            return MarketRegime.RANGING

    def _predict_future_regime(self, current: MarketRegime, adx: float,
                                bb_width: float, volume_trend: float,
                                closes: List[float]) -> Tuple[MarketRegime, float, Dict]:
        """
        Predict what regime will be in 12 bars based on leading indicators.
        """
        predicted = current
        confidence = 0.5
        signals = {}

        # Leading indicator 1: ADX turning points
        adx_declining = False
        adx_rising = False
        if len(self.adx_history) >= 5:
            recent_adx = list(self.adx_history)[-5:]
            adx_declining = recent_adx[-1] < recent_adx[0] * 0.9  # 10% decline
            adx_rising = recent_adx[-1] > recent_adx[0] * 1.1    # 10% rise
            signals['adx_declining'] = adx_declining
            signals['adx_rising'] = adx_rising

        # Leading indicator 2: Bollinger Band squeeze
        bb_squeeze = False
        bb_expanding = False
        if len(self.bb_width_history) >= 5:
            avg_width = np.mean(list(self.bb_width_history))
            bb_squeeze = bb_width < avg_width * 0.7
            bb_expanding = bb_width > avg_width * 1.3
            signals['bb_squeeze'] = bb_squeeze
            signals['bb_expanding'] = bb_expanding

        # Leading indicator 3: Volume trend
        signals['volume_trend'] = volume_trend

        # --- PREDICTION LOGIC ---

        # Trend exhaustion: ADX declining + volume declining in trend
        if current in [MarketRegime.STRONG_TREND_UP, MarketRegime.TREND_UP,
                       MarketRegime.STRONG_TREND_DOWN, MarketRegime.TREND_DOWN]:
            if adx_declining and volume_trend < 0:
                predicted = MarketRegime.RANGING
                confidence = 0.7
                logger.debug(f"V4 REGIME: Trend exhaustion predicted (ADX declining, volume down)")

        # Breakout incoming: BB squeeze in ranging market
        if current == MarketRegime.RANGING and bb_squeeze:
            # Predict direction based on recent bias
            if len(closes) >= 10:
                recent_change = (closes[-1] - closes[-10]) / closes[-10]
                if recent_change > 0.01:  # 1% up
                    predicted = MarketRegime.TREND_UP
                    confidence = 0.65
                elif recent_change < -0.01:  # 1% down
                    predicted = MarketRegime.TREND_DOWN
                    confidence = 0.65
                logger.debug(f"V4 REGIME: Breakout predicted from squeeze")

        # Trend acceleration: ADX rising + volume increasing
        if current == MarketRegime.TREND_UP and adx_rising and volume_trend > 0:
            predicted = MarketRegime.STRONG_TREND_UP
            confidence = 0.6
        elif current == MarketRegime.TREND_DOWN and adx_rising and volume_trend > 0:
            predicted = MarketRegime.STRONG_TREND_DOWN
            confidence = 0.6

        # High volatility detection
        if bb_expanding:
            predicted = MarketRegime.HIGH_VOLATILITY
            confidence = 0.7

        return predicted, confidence, signals

    def _calculate_adx(self, candles: List[Dict]) -> float:
        """Calculate ADX (Average Directional Index)."""
        if len(candles) < 14:
            return 25  # Default neutral

        try:
            highs = [c['high'] for c in candles]
            lows = [c['low'] for c in candles]
            closes = [c['close'] for c in candles]

            # Calculate True Range and Directional Movement
            tr_list = []
            plus_dm_list = []
            minus_dm_list = []

            for i in range(1, len(candles)):
                high_diff = highs[i] - highs[i-1]
                low_diff = lows[i-1] - lows[i]

                plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0
                minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0

                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1])
                )

                tr_list.append(tr)
                plus_dm_list.append(plus_dm)
                minus_dm_list.append(minus_dm)

            # Smooth with 14-period EMA
            period = 14
            if len(tr_list) < period:
                return 25

            atr = np.mean(tr_list[-period:])
            plus_di = 100 * np.mean(plus_dm_list[-period:]) / atr if atr > 0 else 0
            minus_di = 100 * np.mean(minus_dm_list[-period:]) / atr if atr > 0 else 0

            # Calculate ADX
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx = 100 * abs(plus_di - minus_di) / di_sum
            else:
                dx = 0

            return dx

        except Exception:
            return 25

    def _calculate_bb_width(self, closes: List[float]) -> float:
        """Calculate Bollinger Band width."""
        if len(closes) < 20:
            return 0.02

        try:
            sma = np.mean(closes[-20:])
            std = np.std(closes[-20:])
            bb_width = (2 * std * 2) / sma  # 2 std devs, relative to price
            return bb_width
        except Exception:
            return 0.02

    def _calculate_volume_trend(self, volumes: List[float]) -> float:
        """Calculate volume trend (-1 to 1)."""
        if len(volumes) < 5:
            return 0

        try:
            first_half = np.mean(volumes[:len(volumes)//2])
            second_half = np.mean(volumes[len(volumes)//2:])

            if first_half > 0:
                trend = (second_half - first_half) / first_half
                return max(-1, min(1, trend))
            return 0
        except Exception:
            return 0

    def get_params(self, use_predicted: bool = True) -> Dict:
        """Get trading parameters for current/predicted regime."""
        regime = self.predicted_regime if use_predicted else self.current_regime
        return self.REGIME_PARAMS.get(regime, self.REGIME_PARAMS[MarketRegime.UNKNOWN])

    def get_position_multiplier(self) -> float:
        """Get position multiplier for predicted regime."""
        params = self.get_params()
        return params.get('position_mult', 1.0)

    def get_stats(self) -> Dict:
        """Get predictor statistics."""
        return {
            'current_regime': self.current_regime.value,
            'predicted_regime': self.predicted_regime.value,
            'regime_confidence': f"{self.regime_confidence:.1%}",
            'regime_changes': self.regime_changes,
            'predictions_made': self.predictions_made,
            'current_params': self.get_params(use_predicted=False),
            'predicted_params': self.get_params(use_predicted=True),
        }

    def reset_stats(self):
        """Reset statistics for new backtest run."""
        self.regime_changes = 0
        self.predictions_made = 0
        self.correct_predictions = 0
        self.adx_history.clear()
        self.bb_width_history.clear()
        self.volume_history.clear()
        self.current_regime = MarketRegime.UNKNOWN
        self.predicted_regime = MarketRegime.UNKNOWN
