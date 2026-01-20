"""
Elite Momentum Strategy

Rides established trends by catching momentum in motion.
Unlike breakout (waits for consolidation break) or mean reversion (fades extremes),
this strategy enters when momentum is CONFIRMED and rides the wave.

Key Differences from Other Strategies:
- Breakout: Needs consolidation + volume spike
- Pullback: Needs retracement to fib level
- Mean Reversion: Needs ranging market + RSI extreme
- Momentum: Just needs TREND + MOMENTUM ALIGNMENT + VOLUME

Entry Conditions:
- Trend established (trend_strength > 0.35)
- RSI confirms direction (>50 for long, <50 for short)
- Price above/below EMAs (trend alignment)
- Volume above average (smart money participating)
- NOT overbought/oversold (avoid chasing tops/bottoms)

Targets:
- TP1: 1.5R (quick partial profit)
- TP2: 2.5R (let winner run with trend)

Risk:
- ATR-based stop below recent swing
- Smaller position if trend already extended
"""

from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MomentumStrategy:
    """
    Elite Momentum Strategy.
    
    Catches trending moves by riding established momentum.
    Different from breakout - doesn't need consolidation.
    Different from mean reversion - doesn't fade, follows trend.
    """
    
    def __init__(self):
        self.name = "Momentum"
        self.signals_generated = 0
        self.signals_blocked = 0
        
        # Import indicators
        try:
            from data_feed.indicators import TechnicalIndicators
            self.indicators = TechnicalIndicators()
        except ImportError:
            self.indicators = None
            logger.warning(f"⚠️ {self.name}: Could not import TechnicalIndicators")
        
        logger.info(f"✅ {self.name}: Strategy initialized (trend-following)")
    
    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for momentum opportunities.
        
        Returns signal if:
        1. Trend is established (but not exhausted)
        2. RSI confirms direction
        3. Price aligned with EMAs
        4. Volume confirms participation
        
        Args:
            market_state: Complete market state from MarketDataFeed
            
        Returns:
            Signal dict if setup found, None otherwise
        """
        import config
        
        try:
            # Get config values
            if not getattr(config, 'MOMENTUM_STRATEGY_ENABLED', True):
                return None
            
            timeframe = getattr(config, 'MR_TIMEFRAME', '15m')  # Use same as mean reversion
            min_trend_strength = getattr(config, 'MOMENTUM_TREND_STRENGTH_MIN', 0.35)
            rsi_bull_min = getattr(config, 'MOMENTUM_RSI_BULL_MIN', 50)
            rsi_bear_max = getattr(config, 'MOMENTUM_RSI_BEAR_MAX', 50)
            volume_confirm = getattr(config, 'MOMENTUM_VOLUME_CONFIRM', 1.1)
            atr_stop_mult = getattr(config, 'MOMENTUM_ATR_STOP_MULTIPLIER', 1.5)
            tp1_rr = getattr(config, 'MOMENTUM_TP1_RR', 1.5)
            tp2_rr = getattr(config, 'MOMENTUM_TP2_RR', 2.5)
            
            # Get timeframe data
            timeframes = market_state.get('timeframes', {})
            tf_data = timeframes.get(timeframe, {})
            
            if not tf_data:
                logger.debug(f"{self.name}: No {timeframe} data available")
                return None
            
            # Get candles
            candles = tf_data.get('candles', [])
            if len(candles) < 30:
                logger.debug(f"{self.name}: Not enough candles ({len(candles)} < 30)")
                return None
            
            # Extract data
            closes = [c['close'] for c in candles]
            highs = [c['high'] for c in candles]
            lows = [c['low'] for c in candles]
            volumes = [c.get('volume', 0) for c in candles]
            
            current_price = closes[-1]
            current_high = highs[-1]
            current_low = lows[-1]
            
            # Get trend data
            trend_data = tf_data.get('trend', {})
            trend_direction = trend_data.get('trend_direction', 'neutral')
            trend_strength = trend_data.get('trend_strength', 0)
            
            # Get ATR
            atr_data = tf_data.get('atr', {})
            atr = atr_data.get('atr', 0)
            
            if atr == 0:
                # Calculate ATR manually
                atr = self._calculate_atr(highs, lows, closes, 14)
            
            # ==========================================
            # STEP 1: Check Trend Strength
            # ==========================================
            if trend_strength < min_trend_strength:
                logger.debug(f"{self.name}: Trend too weak ({trend_strength:.2f} < {min_trend_strength})")
                return None
            
            # ==========================================
            # STEP 2: Calculate RSI
            # ==========================================
            rsi = self._calculate_rsi(closes, 14)
            if rsi is None:
                return None
            
            # ==========================================
            # STEP 3: Determine Direction
            # ==========================================
            direction = None
            
            # LONG conditions
            if (trend_direction == 'up' and 
                rsi > rsi_bull_min and 
                rsi < 75):  # Not overbought (avoid chasing tops)
                direction = 'long'
                
            # SHORT conditions  
            elif (trend_direction == 'down' and 
                  rsi < rsi_bear_max and 
                  rsi > 25):  # Not oversold (avoid chasing bottoms)
                direction = 'short'
            
            if not direction:
                logger.debug(f"{self.name}: No momentum alignment (trend={trend_direction}, RSI={rsi:.1f})")
                return None
            
            # ==========================================
            # STEP 4: EMA Alignment Check
            # ==========================================
            ema_20 = self._calculate_ema(closes, 20)
            ema_50 = self._calculate_ema(closes, 50)
            
            if ema_20 is None or ema_50 is None:
                return None
            
            # For longs: price > EMA20 > EMA50 (stacked bullish)
            # For shorts: price < EMA20 < EMA50 (stacked bearish)
            if direction == 'long':
                if not (current_price > ema_20 and ema_20 > ema_50):
                    logger.debug(f"{self.name}: EMAs not stacked bullish")
                    return None
            else:  # short
                if not (current_price < ema_20 and ema_20 < ema_50):
                    logger.debug(f"{self.name}: EMAs not stacked bearish")
                    return None
            
            # ==========================================
            # STEP 5: Volume Confirmation
            # ==========================================
            if len(volumes) >= 20:
                avg_volume = sum(volumes[-20:]) / 20
                current_volume = volumes[-1]
                
                if avg_volume > 0 and current_volume < avg_volume * volume_confirm:
                    logger.debug(f"{self.name}: Volume too low ({current_volume/avg_volume:.2f}x < {volume_confirm}x)")
                    return None
                
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            else:
                volume_ratio = 1.0
            
            # ==========================================
            # STEP 6: Calculate Entry, Stop, Targets
            # ==========================================
            entry_price = current_price
            
            if direction == 'long':
                # Stop below recent swing low
                recent_low = min(lows[-10:])
                stop_loss = recent_low - (atr * 0.5)  # Buffer below swing
                
                # Ensure minimum stop distance
                min_stop_distance = atr * atr_stop_mult
                if entry_price - stop_loss < min_stop_distance:
                    stop_loss = entry_price - min_stop_distance
                
                risk = entry_price - stop_loss
                take_profit_1 = entry_price + (risk * tp1_rr)
                take_profit_2 = entry_price + (risk * tp2_rr)
                
            else:  # short
                # Stop above recent swing high
                recent_high = max(highs[-10:])
                stop_loss = recent_high + (atr * 0.5)  # Buffer above swing
                
                # Ensure minimum stop distance
                min_stop_distance = atr * atr_stop_mult
                if stop_loss - entry_price < min_stop_distance:
                    stop_loss = entry_price + min_stop_distance
                
                risk = stop_loss - entry_price
                take_profit_1 = entry_price - (risk * tp1_rr)
                take_profit_2 = entry_price - (risk * tp2_rr)
            
            # ==========================================
            # STEP 7: Risk:Reward Validation
            # ==========================================
            if direction == 'long':
                rr_ratio = (take_profit_1 - entry_price) / (entry_price - stop_loss) if entry_price > stop_loss else 0
            else:
                rr_ratio = (entry_price - take_profit_1) / (stop_loss - entry_price) if stop_loss > entry_price else 0
            
            if rr_ratio < 1.2:
                logger.debug(f"{self.name}: R:R too low ({rr_ratio:.2f} < 1.2)")
                self.signals_blocked += 1
                return None
            
            # ==========================================
            # STEP 8: Build Signal
            # ==========================================
            self.signals_generated += 1
            
            signal = {
                'strategy': self.name,
                'direction': direction,
                'entry_price': round(entry_price, 4),
                'stop_loss': round(stop_loss, 4),
                'stop_price': round(stop_loss, 4),  # Alias
                'take_profit_1': round(take_profit_1, 4),
                'take_profit_2': round(take_profit_2, 4),
                'take_profit': round(take_profit_1, 4),  # Alias
                'target_price': round(take_profit_2, 4),  # Alias
                'risk_amount': round(abs(entry_price - stop_loss), 4),  # Must be at top level for risk_manager
                'timestamp': datetime.now().isoformat(),
                'metadata': {
                    'trend_strength': round(trend_strength, 3),
                    'trend_direction': trend_direction,
                    'rsi': round(rsi, 1),
                    'volume_ratio': round(volume_ratio, 2),
                    'atr': round(atr, 4),
                    'ema_20': round(ema_20, 4),
                    'ema_50': round(ema_50, 4),
                    'rr_ratio': round(rr_ratio, 2)
                }
            }
            
            logger.info(f"🚀 {self.name}: {direction.upper()} signal @ {entry_price:.2f}")
            logger.info(f"   Trend: {trend_direction} ({trend_strength:.2f}), RSI: {rsi:.1f}, Vol: {volume_ratio:.1f}x")
            logger.info(f"   SL: {stop_loss:.2f}, TP1: {take_profit_1:.2f}, TP2: {take_profit_2:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"❌ {self.name}: Error during analysis: {e}")
            return None
    
    def _calculate_rsi(self, prices: list, period: int = 14) -> Optional[float]:
        """Calculate RSI."""
        if len(prices) < period + 1:
            return None
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_ema(self, prices: list, period: int) -> Optional[float]:
        """Calculate EMA."""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_atr(self, highs: list, lows: list, closes: list, period: int = 14) -> float:
        """Calculate ATR."""
        if len(highs) < period + 1:
            return 0
        
        true_ranges = []
        for i in range(1, len(highs)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_ranges.append(max(high_low, high_close, low_close))
        
        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges) if true_ranges else 0
        
        return sum(true_ranges[-period:]) / period
    
    def get_statistics(self) -> Dict:
        """Get strategy statistics."""
        return {
            'name': self.name,
            'signals_generated': self.signals_generated,
            'signals_blocked': self.signals_blocked
        }
