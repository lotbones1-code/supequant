"""
Breakout Strategy
Trades breakouts from consolidation with volatility compression
Requires: ATR compression + volume confirmation + clean breakout
"""

from typing import Dict, Optional, Tuple, List
import numpy as np
import logging
from config import (
    BREAKOUT_VOLUME_MULTIPLIER,
    BREAKOUT_ATR_COMPRESSION,
    BREAKOUT_CONSOLIDATION_BARS,
    ATR_STOP_MULTIPLIER,
    TP1_RR_RATIO,
    TP2_RR_RATIO
)

logger = logging.getLogger(__name__)


class BreakoutStrategy:
    """
    Breakout Trading Strategy
    Enters on clean breakouts from consolidation zones
    """

    def __init__(self):
        self.name = "Breakout"
        self.signals_generated = 0

    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for breakout opportunities

        Args:
            market_state: Complete market state

        Returns:
            Signal dict if setup found, None otherwise
        """
        try:
            # Use 15m timeframe as primary
            timeframes = market_state.get('timeframes', {})
            if '15m' not in timeframes:
                return None

            tf_data = timeframes['15m']
            candles = tf_data.get('candles', [])

            if len(candles) < 50:
                return None

            # Check for breakout conditions
            # 1. Volatility compression
            compression_check = self._check_compression(tf_data)
            if not compression_check:
                return None

            # 2. Consolidation pattern
            consolidation = self._detect_consolidation(candles)
            if not consolidation:
                return None

            # 3. Breakout detection
            breakout_signal = self._detect_breakout(candles, consolidation, tf_data)
            if not breakout_signal:
                return None

            # 4. Volume confirmation
            volume_confirmed = self._confirm_volume(tf_data)
            if not volume_confirmed:
                return None

            # Generate full signal
            signal = self._generate_signal(
                market_state,
                breakout_signal,
                consolidation,
                tf_data
            )

            if signal:
                self.signals_generated += 1
                logger.info(f"🎯 {self.name}: Signal generated - {signal['direction'].upper()}")

            return signal

        except Exception as e:
            logger.error(f"{self.name}: Error analyzing market: {e}")
            return None

    def _check_compression(self, tf_data: Dict) -> bool:
        """Check for volatility compression"""
        atr_data = tf_data.get('atr', {})
        if not atr_data:
            return False

        is_compressed = atr_data.get('is_compressed', False)

        # Also check ATR percentile
        atr_percentile = atr_data.get('atr_percentile', 50)

        # Want ATR in lower range (compressed)
        return is_compressed or atr_percentile < 40

    def _detect_consolidation(self, candles: List[Dict]) -> Optional[Dict]:
        """
        Detect consolidation zone

        Returns:
            Dict with consolidation details or None
        """
        if len(candles) < BREAKOUT_CONSOLIDATION_BARS:
            return None

        # Look at recent candles
        recent_candles = candles[-BREAKOUT_CONSOLIDATION_BARS:]

        highs = [c['high'] for c in recent_candles]
        lows = [c['low'] for c in recent_candles]
        closes = [c['close'] for c in recent_candles]

        # Calculate consolidation range
        resistance = max(highs)
        support = min(lows)
        range_size = resistance - support
        mid_price = (resistance + support) / 2

        if mid_price == 0:
            return None

        # Consolidation should be tight (< 3% range)
        range_pct = range_size / mid_price

        if range_pct > 0.03:  # More than 3% range = not consolidation
            return None

        # Check if price is staying within range (not trending)
        breaks = 0
        for candle in recent_candles[:-1]:  # Exclude last candle
            if candle['high'] > resistance or candle['low'] < support:
                breaks += 1

        # Allow max 2 breaks
        if breaks > 2:
            return None

        return {
            'resistance': resistance,
            'support': support,
            'mid': mid_price,
            'range_pct': range_pct,
            'bars': len(recent_candles)
        }

    def _detect_breakout(self, candles: List[Dict], consolidation: Dict,
                        tf_data: Dict) -> Optional[Dict]:
        """
        Detect breakout from consolidation

        Returns:
            Dict with breakout details or None
        """
        current_candle = candles[-1]
        resistance = consolidation['resistance']
        support = consolidation['support']

        current_high = current_candle['high']
        current_low = current_candle['low']
        current_close = current_candle['close']

        # Bullish breakout
        if current_close > resistance:
            # Confirm close is above resistance (not just wick)
            if current_close > resistance * 1.001:  # 0.1% above
                return {
                    'direction': 'long',
                    'breakout_level': resistance,
                    'entry_price': current_close,
                    'breakout_strength': (current_close - resistance) / resistance
                }

        # Bearish breakout
        elif current_close < support:
            # Confirm close is below support (not just wick)
            if current_close < support * 0.999:  # 0.1% below
                return {
                    'direction': 'short',
                    'breakout_level': support,
                    'entry_price': current_close,
                    'breakout_strength': (support - current_close) / support
                }

        return None

    def _confirm_volume(self, tf_data: Dict) -> bool:
        """Confirm breakout with volume"""
        volume_data = tf_data.get('volume', {})
        if not volume_data:
            return True  # Allow if no volume data

        volume_ratio = volume_data.get('volume_ratio', 1.0)

        # Volume should be above average
        return volume_ratio >= BREAKOUT_VOLUME_MULTIPLIER

    def _generate_signal(self, market_state: Dict, breakout: Dict,
                        consolidation: Dict, tf_data: Dict) -> Dict:
        """
        Generate complete trading signal with entry, stops, targets

        Returns:
            Complete signal dict
        """
        direction = breakout['direction']
        entry_price = breakout['entry_price']

        # Calculate ATR for stops
        atr_data = tf_data.get('atr', {})
        atr = atr_data.get('atr', 0)

        if atr == 0:
            # Fallback: use consolidation range
            atr = consolidation['resistance'] - consolidation['support']

        # Stop loss: Below support for long, above resistance for short
        if direction == 'long':
            stop_loss = consolidation['support'] - (atr * ATR_STOP_MULTIPLIER)
        else:
            stop_loss = consolidation['resistance'] + (atr * ATR_STOP_MULTIPLIER)

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
            'consolidation': consolidation,
            'breakout_strength': breakout['breakout_strength'],
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
