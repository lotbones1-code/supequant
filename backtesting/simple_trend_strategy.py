"""
Simple Trend Following Strategy for Backtesting

A straightforward momentum strategy that:
1. Identifies trend using EMA alignment
2. Enters on pullbacks within the trend
3. Uses wider stops to ride the trend

This is BACKTEST ONLY - does not affect live trading.
"""

import logging
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)


class SimpleTrendStrategy:
    """
    Simple trend following strategy that works in trending markets.
    
    Entry conditions:
    - Clear trend on 15m (EMA 20 > 50 for uptrend)
    - Pullback to EMA 20 (price near EMA 20)
    - RSI not overbought/oversold (40-60 range for entries)
    
    Exit:
    - Wider ATR stop (2x ATR)
    - Trail stop after 1:1 R
    """
    
    def __init__(self, 
                 min_trend_strength: float = 0.3,
                 pullback_threshold: float = 0.02,  # Within 2% of EMA
                 atr_stop_mult: float = 2.0):
        self.min_trend_strength = min_trend_strength
        self.pullback_threshold = pullback_threshold
        self.atr_stop_mult = atr_stop_mult
        self.stats = {'signals': 0, 'long': 0, 'short': 0}
        
    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for trend following opportunities.
        
        Args:
            market_state: Current market data
            
        Returns:
            Signal dict or None
        """
        try:
            tf_data = market_state.get('timeframes', {}).get('15m', {})
            if not tf_data:
                return None
                
            trend = tf_data.get('trend', {})
            momentum = tf_data.get('momentum', {})
            volatility = tf_data.get('volatility', {})
            candles = tf_data.get('candles', [])
            
            if len(candles) < 50:
                return None
                
            current_price = tf_data.get('current_price', 0)
            if current_price <= 0:
                return None
            
            # Get indicators
            trend_direction = trend.get('trend_direction', 'neutral')
            trend_strength = trend.get('trend_strength', 0)
            ema_alignment = trend.get('ema_alignment', 0)
            
            ema_20 = trend.get('ema_20', current_price)
            ema_50 = trend.get('ema_50', current_price)
            
            rsi = momentum.get('rsi', 50)
            atr = volatility.get('atr', 0)
            
            if atr <= 0:
                return None
            
            # Check for clear trend
            is_uptrend = (
                trend_direction == 'bullish' and
                trend_strength >= self.min_trend_strength and
                ema_alignment > 0.1 and
                ema_20 > ema_50
            )
            
            is_downtrend = (
                trend_direction == 'bearish' and
                trend_strength >= self.min_trend_strength and
                ema_alignment < -0.1 and
                ema_20 < ema_50
            )
            
            if not is_uptrend and not is_downtrend:
                return None
            
            # Check for pullback to EMA
            price_to_ema = abs(current_price - ema_20) / current_price
            is_pullback = price_to_ema < self.pullback_threshold
            
            if not is_pullback:
                return None
            
            # RSI filter - don't enter at extremes
            if rsi < 30 or rsi > 70:
                return None
            
            # Generate signal
            direction = 'long' if is_uptrend else 'short'
            
            # Calculate stops and targets
            stop_distance = atr * self.atr_stop_mult
            
            if direction == 'long':
                stop_price = current_price - stop_distance
                target_price = current_price + (stop_distance * 2)  # 2:1 R:R
            else:
                stop_price = current_price + stop_distance
                target_price = current_price - (stop_distance * 2)
            
            self.stats['signals'] += 1
            self.stats[direction] += 1
            
            signal = {
                'strategy': 'simple_trend',
                'direction': direction,
                'entry_price': current_price,
                'stop_loss': stop_price,
                'target': target_price,
                'atr': atr,
                'trend_strength': trend_strength,
                'rsi': rsi,
                'metadata': {
                    'ema_alignment': ema_alignment,
                    'price_to_ema': price_to_ema,
                    'trend_direction': trend_direction
                }
            }
            
            logger.info(f"🎯 SimpleTrend: {direction.upper()} | "
                       f"Trend: {trend_strength:.2f} | RSI: {rsi:.1f}")
            
            return signal
            
        except Exception as e:
            logger.error(f"SimpleTrend error: {e}")
            return None


def create_simple_trend_strategy(min_strength: float = 0.3) -> SimpleTrendStrategy:
    """Factory function"""
    return SimpleTrendStrategy(min_trend_strength=min_strength)
