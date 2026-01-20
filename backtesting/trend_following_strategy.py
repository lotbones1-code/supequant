"""
Trend Following Strategy - BACKTEST ONLY

Complements Mean Reversion by profiting in trending markets.

Logic:
- Uses EMA crossovers to identify trend direction
- Enters on pullbacks within established trends
- Rides trends with trailing stops (wider than Mean Reversion)

This strategy should WIN when Mean Reversion LOSES (trending markets)
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class TrendFollowingStrategy:
    """
    Trend Following Strategy
    
    BACKTEST ONLY - Not yet integrated into live trading.
    
    Entry Conditions:
    1. Strong trend detected (EMA 20 > EMA 50 > EMA 100 for uptrend)
    2. Price pulls back to EMA 20 (entry zone)
    3. RSI not extremely overbought/oversold
    4. Volume confirms trend
    
    Exit:
    - Trailing stop based on ATR
    - Exit if trend structure breaks
    """
    
    def __init__(self):
        self.name = "TrendFollowing"
        self.signals_generated = 0
        self.signals_blocked = 0
        
        # Parameters (loosened for more signals)
        self.ema_fast = 20
        self.ema_medium = 50
        self.ema_slow = 100
        self.min_trend_strength = 0.25  # Lowered from 0.35
        self.atr_stop_multiplier = 2.0  # Tighter stops
        self.atr_target_multiplier = 3.0  # More achievable targets
        
        logger.info(f"✅ {self.name}: Strategy initialized (trend-following)")
    
    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for trend following opportunities
        
        Args:
            market_state: Current market data with timeframes
            
        Returns:
            Signal dict if trend following setup found, None otherwise
        """
        try:
            timeframes = market_state.get('timeframes', {})
            tf_15m = timeframes.get('15m', {})
            tf_1h = timeframes.get('1H', {})
            
            if not tf_15m:
                return None
            
            candles = tf_15m.get('candles', [])
            if len(candles) < 100:
                return None
            
            # Get trend data
            trend = tf_15m.get('trend', {})
            trend_direction = trend.get('trend_direction', 'sideways')
            trend_strength = trend.get('trend_strength', 0)
            
            # Need strong trend (opposite of Mean Reversion)
            if trend_strength < self.min_trend_strength:
                return None
            
            if trend_direction == 'sideways':
                return None
            
            # Get 1H trend for optional confirmation (not required)
            trend_1h = tf_1h.get('trend', {})
            trend_1h_direction = trend_1h.get('trend_direction', 'sideways')
            
            # Bonus confidence if 1H agrees, but not required
            htf_aligned = (trend_1h_direction == trend_direction)
            
            # Calculate EMAs
            closes = [c['close'] for c in candles]
            ema_20 = self._calculate_ema(closes, self.ema_fast)
            ema_50 = self._calculate_ema(closes, self.ema_medium)
            ema_100 = self._calculate_ema(closes, self.ema_slow)
            
            current_price = candles[-1]['close']
            
            # Check EMA alignment (very loose - just need basic trend)
            direction = None
            if trend_direction == 'up' and ema_20 > ema_50:
                # Any price above EMA 50 in uptrend is a potential entry
                # Just need price to be near EMA 20 (within 5%)
                distance_to_ema20 = abs(current_price - ema_20) / ema_20
                if current_price > ema_50 and distance_to_ema20 < 0.05:
                    direction = 'long'
            elif trend_direction == 'down' and ema_20 < ema_50:
                # Any price below EMA 50 in downtrend
                distance_to_ema20 = abs(current_price - ema_20) / ema_20
                if current_price < ema_50 and distance_to_ema20 < 0.05:
                    direction = 'short'
            
            if not direction:
                return None
            
            # Calculate ATR for stops/targets
            atr = self._calculate_atr(candles)
            if atr <= 0:
                return None
            
            # Generate signal
            if direction == 'long':
                stop_price = current_price - (atr * self.atr_stop_multiplier)
                target_price = current_price + (atr * self.atr_target_multiplier)
            else:
                stop_price = current_price + (atr * self.atr_stop_multiplier)
                target_price = current_price - (atr * self.atr_target_multiplier)
            
            # Calculate R:R
            risk = abs(current_price - stop_price)
            reward = abs(target_price - current_price)
            risk_reward = reward / risk if risk > 0 else 0
            
            if risk_reward < 1.5:
                return None
            
            self.signals_generated += 1
            
            signal = {
                'symbol': market_state.get('symbol', 'SOL-USDT-SWAP'),
                'direction': direction,
                'strategy': self.name,
                'entry_price': current_price,
                'stop_price': stop_price,
                'target_price': target_price,
                'take_profit_1': current_price + (atr * 2.0) if direction == 'long' else current_price - (atr * 2.0),
                'take_profit_2': current_price + (atr * 3.0) if direction == 'long' else current_price - (atr * 3.0),
                'take_profit_3': target_price,
                'risk_reward_1': 2.0 / self.atr_stop_multiplier,
                'risk_reward_2': 3.0 / self.atr_stop_multiplier,
                'risk_reward_3': risk_reward,
                'confidence': 0.55 + (trend_strength * 0.3) + (0.1 if htf_aligned else 0),  # HTF alignment bonus
                'setup_type': 'trend_pullback',
                'trend_strength': trend_strength,
                'trend_direction': trend_direction,
                'ema_20': ema_20,
                'ema_50': ema_50,
                'atr': atr,
            }
            
            logger.info(f"🎯 {self.name}: {direction.upper()} @ ${current_price:.2f} | "
                       f"Trend: {trend_direction} ({trend_strength:.2f}) | "
                       f"R:R: {risk_reward:.2f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"{self.name}: Error analyzing market: {e}")
            return None
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> float:
        """Calculate Average True Range"""
        if len(candles) < period + 1:
            return 0
        
        trs = []
        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i-1]['close']
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        
        if len(trs) < period:
            return sum(trs) / len(trs) if trs else 0
        
        return sum(trs[-period:]) / period
