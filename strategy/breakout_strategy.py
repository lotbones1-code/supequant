"""
Breakout Strategy
Trades breakouts from consolidation with volatility compression
Requires: ATR compression + volume confirmation + clean breakout

⚠️ DO NOT replace analyze() with a test stub - this is production code
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
from data_feed.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class BreakoutStrategy:
    """
    Breakout Trading Strategy
    Enters on clean breakouts from consolidation zones
    
    Requirements for signal:
    1. Volatility compression (ATR in lower percentile)
    2. Clear consolidation zone (tight range)
    3. Clean breakout with volume
    """

    def __init__(self):
        self.name = "Breakout"
        self.signals_generated = 0
        self.indicators = TechnicalIndicators()

    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        PRODUCTION breakout detection
        
        ⚠️ DO NOT replace this with a test stub that generates signals
        on every price movement - that's why we had 30% win rate!
        """
        try:
            timeframes = market_state.get('timeframes', {})
            
            # Need 15m timeframe for breakout detection
            if '15m' not in timeframes:
                return None

            tf_data = timeframes['15m']
            candles = tf_data.get('candles', [])

            if len(candles) < BREAKOUT_CONSOLIDATION_BARS + 5:
                return None

            # Step 1: Check for volatility compression
            if not self._check_compression(tf_data):
                return None

            # Step 2: Detect consolidation zone
            consolidation = self._detect_consolidation(candles)
            if not consolidation:
                return None

            # Step 3: Detect breakout
            breakout = self._detect_breakout(candles, consolidation, tf_data)
            if not breakout:
                return None

            # Step 4: Confirm with volume
            if not self._confirm_volume(tf_data):
                logger.debug(f"{self.name}: Breakout without volume confirmation")
                return None

            # All conditions met - generate signal
            signal = self._generate_signal(market_state, breakout, consolidation, tf_data)
            
            self.signals_generated += 1
            logger.info(f"🎯 {self.name}: {breakout['direction'].upper()} breakout "
                       f"(strength: {breakout['breakout_strength']*100:.2f}%, "
                       f"range: {consolidation['range_pct']*100:.2f}%)")
            
            return signal

        except Exception as e:
            logger.error(f"{self.name} error: {e}")
            return None

    def _check_compression(self, tf_data: Dict) -> bool:
        """
        Check for volatility compression (required for breakout)
        
        Returns True if ATR is compressed (potential energy building)
        """
        atr_data = tf_data.get('atr', {})
        if not atr_data:
            # No ATR data - can't confirm compression
            # Allow trade but log warning
            logger.debug(f"{self.name}: No ATR data for compression check")
            return True

        is_compressed = atr_data.get('is_compressed', False)
        atr_percentile = atr_data.get('atr_percentile', 50)

        # Compression means ATR is in lower range (coiled spring)
        # Accept if explicitly compressed OR if ATR below 60th percentile
        return is_compressed or atr_percentile <= 60

    def _detect_consolidation(self, candles: List[Dict]) -> Optional[Dict]:
        """
        Detect consolidation zone (tight range, no trend)

        Returns:
            Dict with consolidation details or None
        """
        if len(candles) < BREAKOUT_CONSOLIDATION_BARS:
            return None

        # Look at recent candles for consolidation
        recent_candles = candles[-BREAKOUT_CONSOLIDATION_BARS:]

        highs = [c['high'] for c in recent_candles]
        lows = [c['low'] for c in recent_candles]
        closes = [c['close'] for c in recent_candles]

        # Calculate consolidation boundaries
        resistance = max(highs)
        support = min(lows)
        range_size = resistance - support
        mid_price = (resistance + support) / 2

        if mid_price == 0:
            return None

        # Consolidation should be tight (< 3% range for crypto)
        range_pct = range_size / mid_price

        if range_pct > 0.03:  # More than 3% = trending, not consolidating
            return None

        # Check that price stayed within range (sideways, not trending)
        # Count how many candles broke outside the range
        inner_resistance = resistance * 0.995  # 0.5% inside
        inner_support = support * 1.005
        
        contained_candles = 0
        for candle in recent_candles[:-1]:  # Exclude the potential breakout candle
            if candle['high'] <= inner_resistance and candle['low'] >= inner_support:
                contained_candles += 1
        
        # Need at least 60% of candles contained (proper consolidation)
        containment_ratio = contained_candles / (len(recent_candles) - 1)
        if containment_ratio < 0.6:
            return None

        return {
            'resistance': resistance,
            'support': support,
            'mid': mid_price,
            'range_pct': range_pct,
            'bars': len(recent_candles),
            'containment': containment_ratio
        }

    def _detect_breakout(self, candles: List[Dict], consolidation: Dict,
                        tf_data: Dict) -> Optional[Dict]:
        """
        Detect breakout from consolidation
        
        Requires: Close beyond boundary (not just wick)

        Returns:
            Dict with breakout details or None
        """
        current_candle = candles[-1]
        prev_candle = candles[-2]
        
        resistance = consolidation['resistance']
        support = consolidation['support']

        current_close = current_candle['close']
        current_open = current_candle['open']
        prev_close = prev_candle['close']

        # Bullish breakout: Close above resistance
        if current_close > resistance:
            # Must be a clean break (close above, not just wick)
            breakout_margin = (current_close - resistance) / resistance
            
            # Need at least 0.2% above resistance for confirmation
            if breakout_margin >= 0.002:
                # Check candle direction (should be bullish)
                if current_close > current_open:
                    return {
                        'direction': 'long',
                        'breakout_level': resistance,
                        'entry_price': current_close,
                        'breakout_strength': breakout_margin
                    }

        # Bearish breakout: Close below support
        elif current_close < support:
            breakout_margin = (support - current_close) / support
            
            # Need at least 0.2% below support for confirmation
            if breakout_margin >= 0.002:
                # Check candle direction (should be bearish)
                if current_close < current_open:
                    return {
                        'direction': 'short',
                        'breakout_level': support,
                        'entry_price': current_close,
                        'breakout_strength': breakout_margin
                    }

        return None

    def _confirm_volume(self, tf_data: Dict) -> bool:
        """
        Confirm breakout with volume
        
        Valid breakouts should have higher than average volume
        """
        volume_data = tf_data.get('volume', {})
        if not volume_data:
            # No volume data - allow but with caution
            logger.debug(f"{self.name}: No volume data for confirmation")
            return True

        volume_ratio = volume_data.get('volume_ratio', 1.0)

        # Volume should be at least BREAKOUT_VOLUME_MULTIPLIER (default 1.2x)
        return volume_ratio >= BREAKOUT_VOLUME_MULTIPLIER

    def _generate_signal(self, market_state: Dict, breakout: Dict,
                        consolidation: Dict, tf_data: Dict) -> Dict:
        """
        Generate complete trading signal with entry, stops, targets
        """
        direction = breakout['direction']
        entry_price = breakout['entry_price']

        # Calculate ATR for stops
        atr_data = tf_data.get('atr', {})
        atr = atr_data.get('atr', 0)

        if atr == 0:
            # Fallback: use consolidation range as ATR proxy
            atr = consolidation['resistance'] - consolidation['support']

        # Stop loss placement
        if direction == 'long':
            # Stop below support with ATR buffer
            stop_loss = consolidation['support'] - (atr * ATR_STOP_MULTIPLIER)
        else:
            # Stop above resistance with ATR buffer
            stop_loss = consolidation['resistance'] + (atr * ATR_STOP_MULTIPLIER)

        # Calculate risk for R:R targets
        risk = abs(entry_price - stop_loss)

        # Take profits at configured R:R ratios
        if direction == 'long':
            tp1 = entry_price + (risk * TP1_RR_RATIO)
            tp2 = entry_price + (risk * TP2_RR_RATIO)
        else:
            tp1 = entry_price - (risk * TP1_RR_RATIO)
            tp2 = entry_price - (risk * TP2_RR_RATIO)

        signal = {
            'strategy': self.name,
            'direction': direction.upper(),  # Standardize to uppercase
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'stop_price': stop_loss,  # Alias for backtest engine
            'take_profit': tp1,  # Primary target
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'target_price': tp1,  # Alias for backtest engine
            'risk_amount': risk,
            'risk_reward_1': TP1_RR_RATIO,
            'risk_reward_2': TP2_RR_RATIO,
            'consolidation': consolidation,
            'breakout_strength': breakout['breakout_strength'],
            'atr': atr,
            'timestamp': market_state.get('timestamp')
        }

        return signal

    def get_statistics(self) -> Dict:
        """Get strategy statistics"""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated
        }
