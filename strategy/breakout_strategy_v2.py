"""
Breakout Strategy V2
Profitable breakout strategy with strict entry criteria

Key features:
1. Volume confirmation: Only enter if volume > 2x 20-period average
2. ATR-based stop loss: 1.5x ATR below entry for longs, above for shorts
3. RSI confirmation: Long only if RSI > 50, Short only if RSI < 50
4. Risk/Reward: TP1 at 2:1, TP2 at 3:1
5. Trend filter: 20 EMA > 50 EMA for longs, opposite for shorts
"""

from typing import Dict, Optional, List
import logging
from data_feed.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class BreakoutStrategyV2:
    """
    Improved Breakout Trading Strategy
    Enters on confirmed breakouts with strict entry criteria
    """

    def __init__(self):
        self.name = "BreakoutV2"
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
            
            # Check volume confirmation (must be > 2x average)
            if volume_ratio < 2.0:
                return None
            
            # STRICTER: Volume must be highest of last 10 candles
            if len(candles) >= 10:
                recent_volumes = [c.get('volume', 0) for c in candles[-10:]]
                if current_volume < max(recent_volumes):
                    return None  # Not the highest volume
            
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
            
            # RSI confirmation
            if direction == 'long' and rsi <= 50:
                return None
            if direction == 'short' and rsi >= 50:
                return None
            
            # Trend filter: 20 EMA > 50 EMA for longs, opposite for shorts
            if direction == 'long' and ema_20_value <= ema_50_value:
                return None
            if direction == 'short' and ema_20_value >= ema_50_value:
                return None
            
            # Generate signal with proper risk/reward
            signal = self._generate_signal(
                direction, current_price, atr
            )
            
            if signal:
                self.signals_generated += 1
                logger.info(f"🎯 {self.name}: {direction.upper()} @ ${signal['entry_price']:.2f} "
                          f"(SL: ${signal['stop_loss']:.2f}, TP1: ${signal['take_profit_1']:.2f}, "
                          f"TP2: ${signal['take_profit_2']:.2f})")
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
        
        # Bullish breakout: close above resistance (not just wick)
        if current_close > resistance * 1.002:  # Close must be 0.2% above resistance
            # Don't enter if already moved >0.5% past breakout level (chasing)
            if current_close > resistance * 1.005:
                return None  # Already moved too far
            
            # Verify candle closed beyond level (not just wick touched)
            if current_close > current_low * 1.001:  # Close should be above low
                return {
                    'direction': 'long',
                    'breakout_level': resistance
                }
        
        # Bearish breakout: close below support (not just wick)
        if current_close < support * 0.998:  # Close must be 0.2% below support
            # Don't enter if already moved >0.5% past breakout level (chasing)
            if current_close < support * 0.995:
                return None  # Already moved too far
            
            # Verify candle closed beyond level (not just wick touched)
            if current_close < current_high * 0.999:  # Close should be below high
                return {
                    'direction': 'short',
                    'breakout_level': support
                }
        
        return None

    def _generate_signal(self, direction: str, entry_price: float, atr: float) -> Optional[Dict]:
        """
        Generate signal with proper risk/reward
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            atr: ATR value
            
        Returns:
            Complete signal dict
        """
        # Stop loss: 1.5x ATR from entry
        if direction == 'long':
            stop_loss = entry_price - (atr * 1.5)
        else:
            stop_loss = entry_price + (atr * 1.5)
        
        # Calculate risk
        risk = abs(entry_price - stop_loss)
        
        # Take profits: TP1 at 2:1, TP2 at 3:1
        if direction == 'long':
            take_profit_1 = entry_price + (risk * 2.0)
            take_profit_2 = entry_price + (risk * 3.0)
        else:
            take_profit_1 = entry_price - (risk * 2.0)
            take_profit_2 = entry_price - (risk * 3.0)
        
        signal = {
            'strategy': self.name,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit_1': take_profit_1,
            'take_profit_2': take_profit_2
        }
        
        return signal

    def get_statistics(self) -> Dict:
        """Get strategy statistics"""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated
        }
