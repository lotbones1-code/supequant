"""
Breakout Strategy V3
Improved breakout strategy with 4 key enhancements

Key features:
1. Volume confirmation: Only enter if volume > 2.5x 20-period average
2. Pullback confirmation: Eliminates false breakouts
3. Dynamic stop loss: Adjusts based on volume strength
4. Progressive profit-taking: 3 TP levels to lock profits
5. ATR-based stop loss: Dynamic multiplier based on volume
6. RSI confirmation: Long only if RSI > 50, Short only if RSI < 50
7. Risk/Reward: TP1 at breakeven (50%), TP2 at 1.5:1 (30%), TP3 at 3:1 (20%)
8. Trend filter: 20 EMA > 50 EMA for longs, opposite for shorts
"""

from typing import Dict, Optional, List
import logging
from data_feed.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class BreakoutStrategyV3:
    """
    Breakout Strategy V3 with 4 improvements:
    1. Pullback confirmation (eliminates false breakouts)
    2. Dynamic stop loss (prevents stops on pullbacks)
    3. Progressive profit-taking (locks profits, reduces reversals)
    4. Stricter volume (2.5x minimum instead of 2.0x)
    """

    def __init__(self):
        self.name = "BreakoutV3"
        self.signals_generated = 0
        self.indicators = TechnicalIndicators()

    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for breakout opportunities with strict criteria
        
        Args:
            market_state: Complete market state
            
        Returns:
            Signal dict if setup found, None otherwise
        """
        try:
            timeframes = market_state.get('timeframes', {})
            if '15m' not in timeframes:
                return None
            
            tf_data = timeframes['15m']
            candles = tf_data.get('candles', [])
            
            if len(candles) < 50:  # Need enough history for indicators
                return None
            
            # Get indicators
            volume_data = tf_data.get('volume', {})
            atr_data = tf_data.get('atr', {})
            trend_data = tf_data.get('trend', {})
            
            # Calculate RSI
            closes = [c['close'] for c in candles]
            rsi = self.indicators.calculate_rsi(closes, period=14)
            if rsi is None:
                return None
            
            # Get ATR
            atr = atr_data.get('atr', 0)
            if atr == 0:
                return None
            
            # Get volume metrics
            current_volume = volume_data.get('current_volume', 0)
            avg_volume_20 = volume_data.get('average_volume', 0)
            volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 0
            
            # BALANCED: Require strong volume but not TOO strict
            # Analysis: 3.0x + highest = only 1 signal (too strict)
            # Solution: 2.5x + top 3 = better balance (quality + quantity)
            if volume_ratio < 2.5:  # Balanced threshold
                logger.debug(f"❌ {self.name}: Volume too weak ({volume_ratio:.2f}x < 2.5x)")
                return None
            
            # BALANCED: Volume must be in top 3 (not highest, but still strong)
            # This allows more opportunities while maintaining quality
            if len(candles) >= 10:
                recent_volumes = sorted([c.get('volume', 0) for c in candles[-10:]], reverse=True)
                if len(recent_volumes) >= 3 and current_volume < recent_volumes[2]:  # Must be top 3
                    logger.debug(f"❌ {self.name}: Volume not in top 3")
                    return None
            
            current_candle = candles[-1]
            current_price = current_candle['close']
            
            # Calculate EMAs for trend filter
            ema_20 = self.indicators.calculate_ema(closes, period=20)
            ema_50 = self.indicators.calculate_ema(closes, period=50)
            
            if not ema_20 or not ema_50 or len(ema_20) == 0 or len(ema_50) == 0:
                return None
            
            ema_20_value = ema_20[-1]  # Get last value from list
            ema_50_value = ema_50[-1]  # Get last value from list
            
            # Detect breakout direction
            breakout = self._detect_breakout(candles, current_price)
            
            if not breakout:
                return None
            
            direction = breakout['direction']
            breakout_level = breakout['breakout_level']
            
            # IMPROVEMENT 1: Pullback confirmation (eliminates false breakouts)
            if not self._detect_pullback_confirmation(candles, breakout_level, direction):
                logger.debug(f"❌ {self.name}: Pullback confirmation failed - level already tested")
                return None
            
            # CRITICAL: Stricter entry filters to improve quality
            # Analysis shows all trades hit stop - need BETTER entries, not more entries
            
            # BALANCED: RSI confirmation - require momentum but not extreme
            # Analysis: RSI 55+ too strict, RSI 50+ too lenient
            # Solution: RSI 52+ for longs, 48- for shorts (balanced)
            if direction == 'long':
                if rsi < 52:  # Require RSI > 52 for longs (balanced momentum)
                    logger.debug(f"❌ {self.name}: RSI too weak ({rsi:.1f} < 52)")
                    return None
            else:  # short
                if rsi > 48:  # Require RSI < 48 for shorts (balanced momentum)
                    logger.debug(f"❌ {self.name}: RSI too weak ({rsi:.1f} > 48)")
                    return None
            
            # BALANCED: Trend filter - require trend but allow close EMAs
            # Analysis: 0.3% EMA diff too strict (only 1 signal)
            # Solution: Require EMA alignment but allow 0.15% diff (balanced)
            ema_diff_pct = abs(ema_20_value - ema_50_value) / ema_50_value if ema_50_value > 0 else 0
            
            if direction == 'long':
                # Require EMA20 above EMA50 (or very close <0.15% diff)
                if ema_20_value < ema_50_value and ema_diff_pct >= 0.0015:
                    logger.debug(f"❌ {self.name}: Trend not aligned (EMA diff: {ema_diff_pct*100:.2f}%)")
                    return None
            else:  # short
                # Require EMA20 below EMA50 (or very close)
                if ema_20_value > ema_50_value and ema_diff_pct >= 0.0015:
                    logger.debug(f"❌ {self.name}: Trend not aligned (EMA diff: {ema_diff_pct*100:.2f}%)")
                    return None
            
            # ADDITIONAL: Require strong breakout candle (not just barely above)
            current_candle = candles[-1]
            candle_body = abs(current_candle['close'] - current_candle['open'])
            candle_range = current_candle['high'] - current_candle['low']
            
            if candle_range > 0:
                body_ratio = candle_body / candle_range
                # Require strong candle body (>50% of range) for clear breakout
                if body_ratio < 0.5:
                    logger.debug(f"❌ {self.name}: Breakout candle too weak (body ratio: {body_ratio:.2f} < 0.5)")
                    return None
            
            # CRITICAL IMPROVEMENT: Momentum confirmation
            # Price must continue moving in breakout direction (not reverse immediately)
            # Check if previous 2 candles also moved in breakout direction
            if len(candles) >= 3:
                prev_candle_1 = candles[-2]
                prev_candle_2 = candles[-3]
                
                if direction == 'long':
                    # For longs: Previous candles should show upward momentum
                    # At least 2 of last 3 candles should close higher than open
                    bullish_candles = 0
                    for c in [prev_candle_2, prev_candle_1, current_candle]:
                        if c['close'] > c['open']:
                            bullish_candles += 1
                    
                    if bullish_candles < 2:  # Need at least 2 bullish candles
                        logger.debug(f"❌ {self.name}: Insufficient bullish momentum ({bullish_candles}/3 candles)")
                        return None
                    
                    # Additional: Current candle should close above previous high
                    if current_candle['close'] <= prev_candle_1['high']:
                        logger.debug(f"❌ {self.name}: Not breaking previous high (weak breakout)")
                        return None
                        
                else:  # short
                    # For shorts: Previous candles should show downward momentum
                    bearish_candles = 0
                    for c in [prev_candle_2, prev_candle_1, current_candle]:
                        if c['close'] < c['open']:
                            bearish_candles += 1
                    
                    if bearish_candles < 2:  # Need at least 2 bearish candles
                        logger.debug(f"❌ {self.name}: Insufficient bearish momentum ({bearish_candles}/3 candles)")
                        return None
                    
                    # Additional: Current candle should close below previous low
                    if current_candle['close'] >= prev_candle_1['low']:
                        logger.debug(f"❌ {self.name}: Not breaking previous low (weak breakout)")
                        return None
            
            # CRITICAL IMPROVEMENT: Volatility filter
            # Avoid breakouts in high volatility (likely to reverse)
            # Check if ATR is expanding rapidly (sign of volatility spike)
            if len(candles) >= 20:
                recent_atrs = []
                for i in range(len(candles) - 20, len(candles)):
                    if i >= 14:  # Need at least 14 candles for ATR
                        period_candles = candles[i-13:i+1]
                        highs = [c['high'] for c in period_candles]
                        lows = [c['low'] for c in period_candles]
                        closes = [c['close'] for c in period_candles]
                        
                        if len(period_candles) == 14:
                            tr_values = []
                            for j in range(1, len(period_candles)):
                                tr1 = highs[j] - lows[j]
                                tr2 = abs(highs[j] - closes[j-1])
                                tr3 = abs(lows[j] - closes[j-1])
                                tr_values.append(max(tr1, tr2, tr3))
                            
                            if tr_values:
                                atr_value = sum(tr_values) / len(tr_values)
                                recent_atrs.append(atr_value)
                
                if len(recent_atrs) >= 2:
                    current_atr_approx = recent_atrs[-1] if recent_atrs else atr
                    prev_atr_approx = recent_atrs[-2] if len(recent_atrs) >= 2 else atr
                    
                    # If ATR increased by more than 50%, skip (volatility spike)
                    if prev_atr_approx > 0 and current_atr_approx > prev_atr_approx * 1.5:
                        logger.debug(f"❌ {self.name}: Volatility spike detected (ATR: {prev_atr_approx:.2f} → {current_atr_approx:.2f})")
                        return None
            
            # Generate signal with proper risk/reward and dynamic stops
            signal = self._generate_signal(
                direction, current_price, atr, volume_ratio
            )
            
            if signal:
                self.signals_generated += 1
                logger.info(f"🎯 {self.name}: {direction.upper()} @ ${signal['entry_price']:.2f} "
                          f"(SL: ${signal['stop_loss']:.2f}, TP1: ${signal['take_profit_1']:.2f}, "
                          f"TP2: ${signal['take_profit_2']:.2f}, TP3: ${signal['take_profit_3']:.2f})")
                return signal
            
            return None
            
        except Exception as e:
            logger.error(f"{self.name}: Error analyzing market: {e}")
            return None

    def _detect_breakout(self, candles: List[Dict], current_price: float) -> Optional[Dict]:
        """
        Detect breakout from consolidation with strict criteria
        
        Requirements:
        1. At least 5 candles of consolidation before breakout
        2. Breakout candle must CLOSE beyond level (not just wick)
        3. Don't enter if already moved >0.5% past breakout level
        
        Returns:
            Dict with direction or None
        """
        if len(candles) < 25:  # Need at least 25 candles (5 consolidation + 20 lookback)
            return None
        
        # Require at least 5 candles of consolidation before breakout
        consolidation_candles = candles[-25:-1]  # Last 24 candles (excluding current)
        if len(consolidation_candles) < 5:
            return None
        
        # Look for consolidation in last 20 candles (before current)
        recent = candles[-21:-1]  # Candles -21 to -2 (20 candles before current)
        if not recent or len(recent) < 5:
            return None
            
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        resistance = max(highs)
        support = min(lows)
        
        current_candle = candles[-1]
        current_close = current_candle['close']
        current_high = current_candle['high']
        current_low = current_candle['low']
        
        # CRITICAL: Stricter breakout detection for BETTER entry quality
        # Analysis: All trades hit stop - need QUALITY over quantity
        # Focus on CLEAR, STRONG breakouts only
        
        breakout_threshold = 1.003  # 0.3% above/below (requires CLEAR breakout, not marginal)
        chase_threshold = 1.005  # Don't chase if moved >0.5% past level (strict)
        
        # Calculate consolidation range - require MEANINGFUL consolidation
        consolidation_range = resistance - support
        range_pct = consolidation_range / support if support > 0 else 0
        
        # CRITICAL: Require meaningful consolidation (at least 1% range)
        # Small ranges = noise, not real breakouts
        if range_pct < 0.01:  # Less than 1% range = skip
            return None
        
        # Bullish breakout: close above resistance (not just wick)
        if current_close > resistance * breakout_threshold:
            # Don't enter if already moved too far past breakout level (chasing)
            if current_close > resistance * chase_threshold:
                return None  # Already moved too far - missed the entry
            
            # CRITICAL: Verify STRONG breakout candle
            # Close should be well above the low (strong bullish candle)
            if current_close <= current_low * 1.002:  # Close must be >0.2% above low
                return None  # Weak candle, likely false breakout
            
            # Additional: Check if breakout is confirmed (close > open for bullish)
            if current_close <= current_candle['open']:
                return None  # Bearish/doji candle on breakout = weak
            
            # CRITICAL: Require breakout to hold (not just touch and reverse)
            # Close should be at least 0.15% above breakout level (not marginal)
            if current_close <= resistance * 1.0015:
                return None  # Too close to breakout level, likely false breakout
            
            return {
                'direction': 'long',
                'breakout_level': resistance
            }
        
        # Bearish breakout: close below support (not just wick)
        if current_close < support * (2 - breakout_threshold):  # 0.997 for shorts
            # Don't enter if already moved too far past breakout level (chasing)
            if current_close < support * (2 - chase_threshold):  # 0.995 for shorts
                return None  # Already moved too far
            
            # CRITICAL: Verify STRONG breakout candle
            # Close should be well below the high (strong bearish candle)
            if current_close >= current_high * 0.998:  # Close must be <0.2% below high
                return None  # Weak candle, likely false breakout
            
            # Additional: Check if breakout is confirmed (close < open for bearish)
            if current_close >= current_candle['open']:
                return None  # Bullish/doji candle on breakout = weak
            
            # CRITICAL: Require breakout to hold (not just touch and reverse)
            # Close should be at least 0.15% below breakout level (not marginal)
            if current_close >= support * 0.9985:
                return None  # Too close to breakout level, likely false breakout
            
            return {
                'direction': 'short',
                'breakout_level': support
            }
        
        return None

    def _detect_pullback_confirmation(self, candles: List[Dict], breakout_level: float, direction: str) -> bool:
        """
        IMPROVEMENT 1: Pullback Confirmation
        
        Eliminates false breakouts by checking if resistance/support was already tested
        in previous candles. If level was tested recently, it's likely a false breakout.
        
        Args:
            candles: List of candle dicts
            breakout_level: Resistance (long) or support (short) level
            direction: 'long' or 'short'
            
        Returns:
            True if pullback confirmation passes (level NOT previously tested)
            False if level was tested (likely false breakout)
        """
        if len(candles) < 3:
            return True  # Not enough history, allow trade
        
        # Check previous 2 candles (candles[-3] and candles[-2])
        # candles[-1] is current candle (the breakout)
        
        # OPTIMIZED: Use tighter tolerance (0.998/1.002) to catch more false breakouts
        # but allow if level was barely touched (more realistic)
        tolerance = 0.998  # 0.2% tolerance for longs, 0.2% for shorts
        
        if direction == 'long':
            # For longs: Check if resistance was tested in previous 2 candles
            # If candles[-3] or candles[-2] high >= breakout_level * tolerance: SKIP
            if len(candles) >= 3:
                prev_2_high = candles[-3].get('high', 0)
                if prev_2_high >= breakout_level * tolerance:
                    logger.debug(f"❌ Pullback: Resistance tested in candle[-3] (high: {prev_2_high:.2f} >= {breakout_level * tolerance:.2f})")
                    return False
            
            if len(candles) >= 2:
                prev_1_high = candles[-2].get('high', 0)
                if prev_1_high >= breakout_level * tolerance:
                    logger.debug(f"❌ Pullback: Resistance tested in candle[-2] (high: {prev_1_high:.2f} >= {breakout_level * tolerance:.2f})")
                    return False
            
            logger.debug(f"✅ Pullback: Resistance NOT previously tested (level: {breakout_level:.2f})")
            return True
        
        else:  # short
            # For shorts: Check if support was tested in previous 2 candles
            # If candles[-3] or candles[-2] low <= breakout_level * (2 - tolerance): SKIP
            if len(candles) >= 3:
                prev_2_low = candles[-3].get('low', 0)
                if prev_2_low <= breakout_level * (2 - tolerance):  # 1.002 for shorts
                    logger.debug(f"❌ Pullback: Support tested in candle[-3] (low: {prev_2_low:.2f} <= {breakout_level * (2 - tolerance):.2f})")
                    return False
            
            if len(candles) >= 2:
                prev_1_low = candles[-2].get('low', 0)
                if prev_1_low <= breakout_level * (2 - tolerance):  # 1.002 for shorts
                    logger.debug(f"❌ Pullback: Support tested in candle[-2] (low: {prev_1_low:.2f} <= {breakout_level * (2 - tolerance):.2f})")
                    return False
            
            logger.debug(f"✅ Pullback: Support NOT previously tested (level: {breakout_level:.2f})")
            return True

    def _calculate_dynamic_stop_multiplier(self, volume_ratio: float) -> float:
        """
        IMPROVEMENT 2: Dynamic Stop Loss
        
        BALANCED: Slightly wider stops to prevent premature stop-outs
        Analysis: MFE 0.96% but stop hit at 0.56% - stop too tight!
        Solution: Give trades more room (1.3x/1.6x/2.2x) while maintaining quality entries
        
        Calculates stop multiplier based on volume strength.
        Strong volume = tighter stops (less likely to pullback)
        Weak volume = wider stops (more likely to pullback)
        
        Args:
            volume_ratio: Current volume / average volume
            
        Returns:
            Stop multiplier (1.3x, 1.6x, or 2.2x ATR) - Balanced to prevent premature stops
        """
        # BALANCED: Slightly wider stops to prevent premature stop-outs
        # MFE analysis shows trades need more room (0.96% MFE vs 0.56% stop)
        if volume_ratio > 3.5:
            multiplier = 1.3  # Was 1.2 - give strong breakouts more room
            logger.debug(f"📊 Dynamic Stop: Strong volume ({volume_ratio:.2f}x) → 1.3x ATR")
        elif volume_ratio >= 2.5:
            multiplier = 1.6  # Was 1.5 - balanced default
            logger.debug(f"📊 Dynamic Stop: Medium volume ({volume_ratio:.2f}x) → 1.6x ATR")
        else:
            multiplier = 2.2  # Was 2.0 - wider for weaker volume
            logger.debug(f"📊 Dynamic Stop: Weak volume ({volume_ratio:.2f}x) → 2.2x ATR")
        
        return multiplier

    def _generate_signal(self, direction: str, entry_price: float, atr: float, volume_ratio: float) -> Optional[Dict]:
        """
        Generate signal with proper risk/reward and IMPROVEMENTS 2 & 3
        
        IMPROVEMENT 2: Dynamic stop loss based on volume
        IMPROVEMENT 3: Progressive profit-taking (3 TP levels)
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            atr: ATR value
            volume_ratio: Volume ratio for dynamic stop calculation
            
        Returns:
            Complete signal dict
        """
        # IMPROVEMENT 2: Dynamic stop loss
        stop_multiplier = self._calculate_dynamic_stop_multiplier(volume_ratio)
        
        # Stop loss: Dynamic multiplier x ATR from entry
        if direction == 'long':
            stop_loss = entry_price - (atr * stop_multiplier)
        else:
            stop_loss = entry_price + (atr * stop_multiplier)
        
        # Calculate risk
        risk = abs(entry_price - stop_loss)
        
        # IMPROVEMENT 3: Progressive profit-taking (3 TP levels)
        if direction == 'long':
            # TP1: Breakeven (exit 50% of position)
            take_profit_1 = entry_price
            # TP2: 1.5:1 R:R (exit 30% of position)
            take_profit_2 = entry_price + (risk * 1.5)
            # TP3: 3.0:1 R:R (exit 20% of position)
            take_profit_3 = entry_price + (risk * 3.0)
        else:
            # TP1: Breakeven (exit 50% of position)
            take_profit_1 = entry_price
            # TP2: 1.5:1 R:R (exit 30% of position)
            take_profit_2 = entry_price - (risk * 1.5)
            # TP3: 3.0:1 R:R (exit 20% of position)
            take_profit_3 = entry_price - (risk * 3.0)
        
        signal = {
            'strategy': self.name,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit_1': take_profit_1,
            'take_profit_2': take_profit_2,
            'take_profit_3': take_profit_3,
            'position_split': {1: 0.5, 2: 0.3, 3: 0.2}  # 50% at TP1, 30% at TP2, 20% at TP3
        }
        
        logger.info(f"💰 {self.name}: TP1=${take_profit_1:.2f} (50%), TP2=${take_profit_2:.2f} (30%), TP3=${take_profit_3:.2f} (20%)")
        
        return signal

    def get_statistics(self) -> Dict:
        """Get strategy statistics"""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated
        }
