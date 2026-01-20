"""
Mean Reversion Strategy (Phase 4.1 Elite)

Trades oversold/overbought bounces in RANGING markets only.
Uses RSI extremes + Bollinger Band touches with confirmation.

CRITICAL: This strategy ONLY triggers when market is RANGING.
         It will NOT trade in trending markets to avoid fading strong moves.

Entry Conditions:
- Market regime is RANGING (trend_strength < 0.45)
- RSI at extreme (≤30 for long, ≥70 for short)
- Price touching Bollinger Band
- Reversal candle confirmation (optional but recommended)

Targets:
- TP1: BB midline (conservative, high probability)
- TP2: Opposite BB band (aggressive, let winner run)

Risk:
- Stop beyond recent swing with ATR buffer
- Minimum R:R validation before taking trade
"""

from typing import Dict, Optional, Tuple, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MeanReversionStrategy:
    """
    Elite Mean Reversion Strategy.
    
    Only trades in RANGING markets where mean reversion has edge.
    Uses RSI + Bollinger Bands + reversal confirmation.
    """
    
    def __init__(self):
        self.name = "MeanReversion"
        self.signals_generated = 0
        self.signals_blocked_trending = 0
        
        # Import indicators
        try:
            from data_feed.indicators import TechnicalIndicators
            self.indicators = TechnicalIndicators()
        except ImportError:
            self.indicators = None
            logger.warning(f"⚠️ {self.name}: Could not import TechnicalIndicators")
        
        logger.info(f"✅ {self.name}: Strategy initialized (regime-aware)")
    
    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for mean reversion opportunities.
        
        ONLY returns signal if:
        1. Market is RANGING (not trending)
        2. RSI at extreme
        3. Price at Bollinger Band
        4. Reversal confirmation (if enabled)
        5. Risk:Reward is acceptable
        
        Args:
            market_state: Complete market state from MarketDataFeed
            
        Returns:
            Signal dict if setup found, None otherwise
        """
        import config
        
        try:
            # Get config values
            timeframe = getattr(config, 'MR_TIMEFRAME', '15m')
            max_trend_strength = getattr(config, 'MR_MAX_TREND_STRENGTH', 0.45)
            require_ranging = getattr(config, 'MR_REQUIRE_RANGING_REGIME', True)
            
            # Get timeframe data
            timeframes = market_state.get('timeframes', {})
            
            if timeframe not in timeframes:
                logger.debug(f"{self.name}: Timeframe {timeframe} not available")
                return None
            
            tf_data = timeframes[timeframe]
            candles = tf_data.get('candles', [])
            
            if len(candles) < 30:  # Need enough data for BB + RSI
                return None
            
            # STEP 1: Check market regime (CRITICAL) - Multi-timeframe check
            if require_ranging:
                regime_ok = self._check_regime(tf_data, max_trend_strength, market_state)
                if not regime_ok:
                    self.signals_blocked_trending += 1
                    return None
            
            # STEP 2: Check RSI extreme
            direction, rsi_value = self._check_rsi_extreme(candles)
            if direction is None:
                return None
            
            # STEP 3: Check Bollinger Band touch
            bb_touch = self._check_bb_touch(candles, direction)
            if not bb_touch:
                return None
            
            # STEP 4: Check reversal candle confirmation
            if getattr(config, 'MR_REQUIRE_REVERSAL_CANDLE', True):
                reversal_ok = self._check_reversal_candle(candles, direction)
                if not reversal_ok:
                    return None
            
            # STEP 5: Check volume confirmation (if enabled)
            if getattr(config, 'MR_REQUIRE_VOLUME_SPIKE', False):
                volume_ok = self._check_volume_confirmation(candles)
                if not volume_ok:
                    return None
            
            # STEP 6: Calculate entry, stop, targets
            signal = self._generate_signal(
                market_state, tf_data, candles, direction, 
                rsi_value, bb_touch
            )
            
            if signal:
                # STEP 7: Validate R:R
                min_rr = getattr(config, 'MR_RR_MINIMUM', 1.5)
                if signal.get('risk_reward_1', 0) < min_rr:
                    logger.debug(f"{self.name}: R:R too low ({signal['risk_reward_1']:.2f} < {min_rr})")
                    return None
                
                self.signals_generated += 1
                logger.info(f"🎯 {self.name}: Signal generated - {direction.upper()} | RSI: {rsi_value:.1f} | BB: {bb_touch['position']}")
            
            return signal
            
        except Exception as e:
            logger.error(f"{self.name}: Error analyzing market: {e}")
            return None
    
    def _check_regime(self, tf_data: Dict, max_trend_strength: float, market_state: Dict = None) -> bool:
        """
        Check if market is in RANGING regime using MULTI-TIMEFRAME analysis.
        
        Mean reversion FAILS in trending markets, so we block if:
        - Primary timeframe trend_strength > threshold
        - Higher timeframe (1H) shows strong trend (even if 15m looks ranging)
        
        Returns:
            True if market is RANGING (safe for mean reversion)
        """
        # Check primary timeframe
        trend_data = tf_data.get('trend', {})
        
        if not trend_data:
            # No trend data - block for safety (was allowing before)
            logger.debug(f"{self.name}: Blocked - no trend data available")
            return False
        
        trend_strength = trend_data.get('trend_strength', 0)
        trend_direction = trend_data.get('trend_direction', 'sideways')
        
        # Block if primary timeframe trend is too strong
        if trend_strength > max_trend_strength:
            logger.debug(f"{self.name}: Blocked - 15m trend too strong ({trend_strength:.2f} > {max_trend_strength})")
            return False
        
        # NEW: Check higher timeframe (1H) trend
        if market_state:
            timeframes = market_state.get('timeframes', {})
            htf_data = timeframes.get('1H', {})
            htf_trend = htf_data.get('trend', {})
            htf_strength = htf_trend.get('trend_strength', 0)
            
            # If 1H is trending strongly, block even if 15m looks ranging
            # Use slightly higher threshold for 1H (0.35 instead of 0.30)
            if htf_strength > max_trend_strength + 0.05:
                logger.debug(f"{self.name}: Blocked - 1H trend too strong ({htf_strength:.2f})")
                return False
        
        # Ideal: sideways/ranging market
        if trend_direction == 'sideways':
            return True
        
        # Allow only very weak trends
        if trend_strength < max_trend_strength * 0.6:  # Tightened from 0.7
            return True
        
        # Marginal case - block to be safe (was allowing before)
        logger.debug(f"{self.name}: Blocked - marginal trend regime ({trend_strength:.2f})")
        return False
    
    def _check_rsi_extreme(self, candles: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Check if RSI is at oversold/overbought extreme.
        
        Returns:
            (direction: 'long'/'short'/None, rsi_value: float)
        """
        import config
        
        if not self.indicators:
            return None, 50.0
        
        closes = [c['close'] for c in candles]
        period = getattr(config, 'MR_RSI_PERIOD', 14)
        
        rsi = self.indicators.calculate_rsi(closes, period)
        
        if rsi is None:
            return None, 50.0
        
        oversold = getattr(config, 'MR_RSI_OVERSOLD', 30)
        overbought = getattr(config, 'MR_RSI_OVERBOUGHT', 70)
        
        if rsi <= oversold:
            return 'long', rsi
        elif rsi >= overbought:
            return 'short', rsi
        
        return None, rsi
    
    def _check_bb_touch(self, candles: List[Dict], direction: str) -> Optional[Dict]:
        """
        Check if price is touching/beyond Bollinger Band.
        
        For LONG: price should be at or below lower band
        For SHORT: price should be at or above upper band
        
        Returns:
            Dict with BB info or None
        """
        import config
        
        if not self.indicators:
            return None
        
        closes = [c['close'] for c in candles]
        period = getattr(config, 'MR_BB_PERIOD', 20)
        std_dev = getattr(config, 'MR_BB_STD_DEV', 2.0)
        
        upper, middle, lower = self.indicators.calculate_bollinger_bands(
            closes, period, std_dev
        )
        
        if not upper or not middle or not lower:
            return None
        
        current_close = candles[-1]['close']
        current_low = candles[-1]['low']
        current_high = candles[-1]['high']
        
        upper_band = upper[-1]
        middle_band = middle[-1]
        lower_band = lower[-1]
        
        if direction == 'long':
            # Check if price touched/pierced lower band
            if current_low <= lower_band or current_close <= lower_band * 1.002:  # 0.2% tolerance
                return {
                    'position': 'lower',
                    'upper': upper_band,
                    'middle': middle_band,
                    'lower': lower_band,
                    'touch_price': min(current_low, current_close)
                }
        
        elif direction == 'short':
            # Check if price touched/pierced upper band
            if current_high >= upper_band or current_close >= upper_band * 0.998:  # 0.2% tolerance
                return {
                    'position': 'upper',
                    'upper': upper_band,
                    'middle': middle_band,
                    'lower': lower_band,
                    'touch_price': max(current_high, current_close)
                }
        
        return None
    
    def _check_reversal_candle(self, candles: List[Dict], direction: str) -> bool:
        """
        Check for reversal candle confirmation.
        
        For LONG: bullish candle (close > open) with decent body
        For SHORT: bearish candle (close < open) with decent body
        
        Returns:
            True if reversal candle detected
        """
        if len(candles) < 2:
            return False
        
        current = candles[-1]
        prev = candles[-2]
        
        open_price = current['open']
        close_price = current['close']
        high_price = current['high']
        low_price = current['low']
        
        candle_range = high_price - low_price
        if candle_range <= 0:
            return False
        
        body_size = abs(close_price - open_price)
        body_ratio = body_size / candle_range
        
        if direction == 'long':
            # Need bullish candle
            if close_price <= open_price:
                return False
            
            # Strong reversal: close above prev high or good body ratio
            if close_price > prev['high']:
                return True
            if body_ratio > 0.5:  # At least 50% body
                return True
                
        elif direction == 'short':
            # Need bearish candle
            if close_price >= open_price:
                return False
            
            # Strong reversal: close below prev low or good body ratio
            if close_price < prev['low']:
                return True
            if body_ratio > 0.5:  # At least 50% body
                return True
        
        return False
    
    def _check_volume_confirmation(self, candles: List[Dict]) -> bool:
        """
        Check if current volume is above average.
        
        Returns:
            True if volume spike detected
        """
        import config
        
        if len(candles) < 21:
            return True  # Allow if not enough history
        
        volumes = [c.get('volume', 0) for c in candles]
        current_volume = volumes[-1]
        avg_volume = sum(volumes[-21:-1]) / 20  # Average of last 20 (excluding current)
        
        if avg_volume <= 0:
            return True  # Allow if no volume data
        
        multiplier = getattr(config, 'MR_VOLUME_MULTIPLIER', 1.2)
        
        return current_volume >= avg_volume * multiplier
    
    def _generate_signal(self, market_state: Dict, tf_data: Dict, 
                         candles: List[Dict], direction: str,
                         rsi_value: float, bb_touch: Dict) -> Optional[Dict]:
        """
        Generate complete trading signal with entry, stop, and targets.
        
        Targets are based on Bollinger Bands:
        - TP1: BB midline (high probability)
        - TP2: Opposite BB band (let winner run)
        
        Returns:
            Complete signal dict matching existing schema
        """
        import config
        
        entry_price = candles[-1]['close']
        
        # Get ATR for stop calculation
        atr_data = tf_data.get('atr', {})
        atr = atr_data.get('atr', 0)
        
        # Fallback ATR calculation
        if atr == 0:
            bb_width = bb_touch['upper'] - bb_touch['lower']
            atr = bb_width * 0.15  # Approximate
        
        atr_multiplier = getattr(config, 'MR_ATR_STOP_MULTIPLIER', 1.5)
        
        # Calculate stop loss (beyond recent swing + ATR buffer)
        recent_candles = candles[-10:]
        
        if direction == 'long':
            # Stop below recent low
            recent_low = min([c['low'] for c in recent_candles])
            stop_loss = recent_low - (atr * atr_multiplier)
            
            # TP1: BB midline, TP2: Upper band
            tp1 = bb_touch['middle']
            tp2 = bb_touch['upper']
            
        else:  # short
            # Stop above recent high
            recent_high = max([c['high'] for c in recent_candles])
            stop_loss = recent_high + (atr * atr_multiplier)
            
            # TP1: BB midline, TP2: Lower band
            tp1 = bb_touch['middle']
            tp2 = bb_touch['lower']
        
        # Calculate risk and R:R
        risk = abs(entry_price - stop_loss)
        
        if risk <= 0:
            return None
        
        reward1 = abs(tp1 - entry_price)
        reward2 = abs(tp2 - entry_price)
        
        rr1 = reward1 / risk if risk > 0 else 0
        rr2 = reward2 / risk if risk > 0 else 0
        
        # Build signal dict (matching existing schema)
        signal = {
            'strategy': self.name,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'risk_amount': risk,
            'risk_reward_1': rr1,
            'risk_reward_2': rr2,
            
            # Mean reversion specific
            'rsi': rsi_value,
            'bb_position': bb_touch['position'],
            'bb_upper': bb_touch['upper'],
            'bb_middle': bb_touch['middle'],
            'bb_lower': bb_touch['lower'],
            'regime': 'ranging',
            
            # Standard fields
            'atr': atr,
            'timestamp': market_state.get('timestamp'),
            'current_price': market_state.get('current_price', entry_price)
        }
        
        return signal
    
    def get_statistics(self) -> Dict:
        """Get strategy statistics."""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated,
            'signals_blocked_trending': self.signals_blocked_trending
        }
