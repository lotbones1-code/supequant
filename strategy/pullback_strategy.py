"""
Pullback Strategy
Trades pullbacks in established trends
Enters on retracement to key Fibonacci levels with trend resumption
"""

from typing import Dict, Optional, Tuple, List
import numpy as np
import logging
from config import (
    PULLBACK_FIBONACCI_LEVELS,
    PULLBACK_MAX_RETRACEMENT,
    PULLBACK_TREND_STRENGTH_MIN,
    ATR_STOP_MULTIPLIER,
    TP1_RR_RATIO,
    TP2_RR_RATIO
)

logger = logging.getLogger(__name__)


class PullbackStrategy:
    """
    Pullback Trading Strategy
    Enters on pullbacks within strong trends
    """

    def __init__(self):
        self.name = "Pullback"
        self.signals_generated = 0

    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for pullback opportunities

        Args:
            market_state: Complete market state

        Returns:
            Signal dict if setup found, None otherwise
        """
        try:
            # Use 15m as primary, but need 1h for trend
            timeframes = market_state.get('timeframes', {})

            if '15m' not in timeframes or '1h' not in timeframes:
                return None

            htf_data = timeframes['1h']
            mtf_data = timeframes['15m']

            # Check for pullback conditions
            # 1. Strong trend on HTF
            trend_check = self._check_trend_strength(htf_data)
            if not trend_check:
                return None

            trend_direction = trend_check['direction']

            # 2. Identify swing high/low
            swing = self._identify_swing(mtf_data, trend_direction)
            if not swing:
                return None

            # 3. Detect pullback to Fib level
            pullback = self._detect_pullback(mtf_data, swing, trend_direction)
            if not pullback:
                return None

            # 4. Look for resumption signal
            resumption = self._check_resumption(mtf_data, trend_direction)
            if not resumption:
                return None

            # Generate full signal
            signal = self._generate_signal(
                market_state,
                trend_direction,
                swing,
                pullback,
                mtf_data
            )

            if signal:
                self.signals_generated += 1
                logger.info(f"🎯 {self.name}: Signal generated - {signal['direction'].upper()}")

            return signal

        except Exception as e:
            logger.error(f"{self.name}: Error analyzing market: {e}")
            return None

    def _check_trend_strength(self, htf_data: Dict) -> Optional[Dict]:
        """
        Check for strong trend on higher timeframe

        Returns:
            Dict with trend info or None
        """
        trend_data = htf_data.get('trend', {})
        if not trend_data:
            return None

        trend_strength = trend_data.get('trend_strength', 0)
        trend_direction = trend_data.get('trend_direction', 'sideways')

        # Need strong trend
        if trend_strength < PULLBACK_TREND_STRENGTH_MIN:
            return None

        # Can't trade sideways
        if trend_direction == 'sideways':
            return None

        return {
            'direction': 'long' if trend_direction == 'up' else 'short',
            'strength': trend_strength
        }

    def _identify_swing(self, mtf_data: Dict, trend_direction: str) -> Optional[Dict]:
        """
        Identify the swing high (for uptrend) or swing low (for downtrend)
        This is the point from which we measure pullback
        """
        candles = mtf_data.get('candles', [])
        if len(candles) < 20:
            return None

        recent_candles = candles[-20:]

        if trend_direction == 'long':
            # Find swing high
            highs = [c['high'] for c in recent_candles]
            swing_high = max(highs)
            swing_index = highs.index(swing_high)

            # Make sure swing high is not the most recent candle
            if swing_index >= len(recent_candles) - 2:
                return None

            return {
                'type': 'swing_high',
                'price': swing_high,
                'index': swing_index
            }

        else:  # short
            # Find swing low
            lows = [c['low'] for c in recent_candles]
            swing_low = min(lows)
            swing_index = lows.index(swing_low)

            # Make sure swing low is not the most recent candle
            if swing_index >= len(recent_candles) - 2:
                return None

            return {
                'type': 'swing_low',
                'price': swing_low,
                'index': swing_index
            }

    def _detect_pullback(self, mtf_data: Dict, swing: Dict,
                        trend_direction: str) -> Optional[Dict]:
        """
        Detect pullback to Fibonacci levels

        Returns:
            Dict with pullback info or None
        """
        candles = mtf_data.get('candles', [])
        if len(candles) < 5:
            return None

        current_price = candles[-1]['close']
        swing_price = swing['price']

        # Get the start of the move (before swing)
        candles_before_swing = candles[-20:swing['index']] if swing['index'] > 0 else []
        if not candles_before_swing:
            return None

        if trend_direction == 'long':
            # For uptrend: measure from low before swing high
            move_start = min([c['low'] for c in candles_before_swing])
            move_size = swing_price - move_start

            if move_size <= 0:
                return None

            # Calculate retracement
            retracement = (swing_price - current_price) / move_size

            # Check if at Fib level
            fib_level = self._nearest_fib_level(retracement)

            if fib_level and retracement <= PULLBACK_MAX_RETRACEMENT:
                return {
                    'move_start': move_start,
                    'move_end': swing_price,
                    'retracement': retracement,
                    'fib_level': fib_level,
                    'current_price': current_price
                }

        else:  # short
            # For downtrend: measure from high before swing low
            move_start = max([c['high'] for c in candles_before_swing])
            move_size = move_start - swing_price

            if move_size <= 0:
                return None

            # Calculate retracement
            retracement = (current_price - swing_price) / move_size

            # Check if at Fib level
            fib_level = self._nearest_fib_level(retracement)

            if fib_level and retracement <= PULLBACK_MAX_RETRACEMENT:
                return {
                    'move_start': move_start,
                    'move_end': swing_price,
                    'retracement': retracement,
                    'fib_level': fib_level,
                    'current_price': current_price
                }

        return None

    def _nearest_fib_level(self, retracement: float) -> Optional[float]:
        """
        Check if retracement is near a Fibonacci level

        Returns:
            Fib level if near one, None otherwise
        """
        tolerance = 0.05  # 5% tolerance

        for fib in PULLBACK_FIBONACCI_LEVELS:
            if abs(retracement - fib) <= tolerance:
                return fib

        return None

    def _check_resumption(self, mtf_data: Dict, trend_direction: str) -> bool:
        """
        Check for trend resumption signals

        Look for:
        - Bullish candle for long
        - Bearish candle for short
        - Volume increase
        """
        candles = mtf_data.get('candles', [])
        if len(candles) < 2:
            return False

        current_candle = candles[-1]
        prev_candle = candles[-2]

        open_price = current_candle['open']
        close_price = current_candle['close']

        if trend_direction == 'long':
            # Need bullish candle
            if close_price <= open_price:
                return False

            # Ideally breaking above previous high
            if close_price > prev_candle['high']:
                return True

            # Or strong bullish body
            body_size = close_price - open_price
            candle_range = current_candle['high'] - current_candle['low']
            if candle_range > 0 and (body_size / candle_range) > 0.6:
                return True

        else:  # short
            # Need bearish candle
            if close_price >= open_price:
                return False

            # Ideally breaking below previous low
            if close_price < prev_candle['low']:
                return True

            # Or strong bearish body
            body_size = open_price - close_price
            candle_range = current_candle['high'] - current_candle['low']
            if candle_range > 0 and (body_size / candle_range) > 0.6:
                return True

        return False

    def _generate_signal(self, market_state: Dict, direction: str,
                        swing: Dict, pullback: Dict, mtf_data: Dict) -> Dict:
        """
        Generate complete trading signal

        Returns:
            Complete signal dict
        """
        entry_price = pullback['current_price']

        # Calculate ATR for stops
        atr_data = mtf_data.get('atr', {})
        atr = atr_data.get('atr', 0)

        if atr == 0:
            # Fallback
            move_size = abs(pullback['move_end'] - pullback['move_start'])
            atr = move_size * 0.1

        # Stop loss: Beyond the pullback low/high
        if direction == 'long':
            # Stop below recent swing low
            recent_low = min([c['low'] for c in mtf_data.get('candles', [])[-10:]])
            stop_loss = recent_low - (atr * ATR_STOP_MULTIPLIER)
        else:
            # Stop above recent swing high
            recent_high = max([c['high'] for c in mtf_data.get('candles', [])[-10:]])
            stop_loss = recent_high + (atr * ATR_STOP_MULTIPLIER)

        # Calculate risk
        risk = abs(entry_price - stop_loss)

        # Take profits
        if direction == 'long':
            tp1 = entry_price + (risk * TP1_RR_RATIO)
            tp2 = entry_price + (risk * TP2_RR_RATIO)
        else:
            tp1 = entry_price - (risk * TP1_RR_RATIO)
            tp2 = entry_price - (risk * TP2_RR_RATIO)

        signal = {
            'strategy': self.name,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'risk_amount': risk,
            'risk_reward_1': TP1_RR_RATIO,
            'risk_reward_2': TP2_RR_RATIO,
            'fib_level': pullback['fib_level'],
            'retracement': pullback['retracement'],
            'swing': swing,
            'atr': atr,
            'timestamp': market_state.get('timestamp'),
            'current_price': market_state.get('current_price')
        }

        return signal

    def get_statistics(self) -> Dict:
        """Get strategy statistics"""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated
        }
