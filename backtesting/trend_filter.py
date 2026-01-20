"""
Trend Detection Filters for Backtesting
Tests multiple approaches to detect trending vs ranging markets.

All filters are BACKTEST ONLY - do not affect live trading.
"""

import logging
import numpy as np
from typing import Dict, Tuple, List

logger = logging.getLogger(__name__)


class ADXTrendFilter:
    """
    ADX (Average Directional Index) based trend detection.
    ADX > 25 = trending market (skip mean reversion)
    ADX < 20 = ranging market (mean reversion works)
    """
    
    def __init__(self, trend_threshold: float = 25, range_threshold: float = 20, period: int = 14):
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold
        self.period = period
        self.stats = {'trending_blocks': 0, 'ranging_allows': 0}
        
    def calculate_adx(self, candles: List[Dict]) -> float:
        """Calculate ADX from candles"""
        if len(candles) < self.period + 1:
            return 0
            
        highs = np.array([c['high'] for c in candles])
        lows = np.array([c['low'] for c in candles])
        closes = np.array([c['close'] for c in candles])
        
        # True Range
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        
        # +DM and -DM
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smoothed averages
        atr = self._smooth(tr, self.period)
        plus_di = 100 * self._smooth(plus_dm, self.period) / (atr + 1e-10)
        minus_di = 100 * self._smooth(minus_dm, self.period) / (atr + 1e-10)
        
        # DX and ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = self._smooth(dx, self.period)
        
        return adx[-1] if len(adx) > 0 else 0
    
    def _smooth(self, data: np.ndarray, period: int) -> np.ndarray:
        """Wilder's smoothing"""
        result = np.zeros_like(data)
        result[period-1] = np.mean(data[:period])
        for i in range(period, len(data)):
            result[i] = (result[i-1] * (period - 1) + data[i]) / period
        return result[period-1:]
    
    def should_allow_mr(self, market_state: Dict) -> Tuple[bool, float, str]:
        """
        Check if Mean Reversion should be allowed.
        
        Returns:
            (allow_mr, adx_value, reason)
        """
        candles = market_state.get('timeframes', {}).get('15m', {}).get('candles', [])
        
        if len(candles) < 30:
            return True, 0, "Insufficient data"
            
        adx = self.calculate_adx(candles[-50:])
        
        if adx > self.trend_threshold:
            self.stats['trending_blocks'] += 1
            return False, adx, f"ADX {adx:.1f} > {self.trend_threshold} (trending)"
        else:
            self.stats['ranging_allows'] += 1
            return True, adx, f"ADX {adx:.1f} (ranging/neutral)"


class HTFTrendFilter:
    """
    Higher Timeframe (4H) trend detection.
    Uses EMA alignment on 4H to detect trend.
    """
    
    def __init__(self, require_alignment: bool = True):
        self.require_alignment = require_alignment
        self.stats = {'trending_blocks': 0, 'ranging_allows': 0}
        
    def should_allow_mr(self, market_state: Dict) -> Tuple[bool, str, str]:
        """
        Check if Mean Reversion should be allowed based on 4H trend.
        
        Returns:
            (allow_mr, trend_direction, reason)
        """
        htf_data = market_state.get('timeframes', {}).get('4H', {})
        trend = htf_data.get('trend', {})
        
        trend_direction = trend.get('trend_direction', 'neutral')
        trend_strength = trend.get('trend_strength', 0)
        ema_alignment = trend.get('ema_alignment', 0)
        
        # Strong 4H trend = don't do MR
        if abs(ema_alignment) > 0.5 or trend_strength > 0.5:
            self.stats['trending_blocks'] += 1
            return False, trend_direction, f"4H trend: {trend_direction} (strength: {trend_strength:.2f})"
        else:
            self.stats['ranging_allows'] += 1
            return True, trend_direction, f"4H neutral/ranging"


class StrictRSIFilter:
    """
    Only allow MR trades at very extreme RSI levels.
    Standard RSI 30/70 -> Strict RSI 20/80
    """
    
    def __init__(self, oversold: int = 20, overbought: int = 80):
        self.oversold = oversold
        self.overbought = overbought
        self.stats = {'filtered': 0, 'passed': 0}
        
    def should_allow_signal(self, signal: Dict, market_state: Dict) -> Tuple[bool, str]:
        """
        Check if signal meets strict RSI requirements.
        
        Returns:
            (allow, reason)
        """
        direction = signal.get('direction', 'long')
        
        # Get RSI from market state
        tf_data = market_state.get('timeframes', {}).get('15m', {})
        momentum = tf_data.get('momentum', {})
        rsi = momentum.get('rsi', 50)
        
        if direction == 'long' and rsi > self.oversold:
            self.stats['filtered'] += 1
            return False, f"RSI {rsi:.1f} not extreme enough (need < {self.oversold})"
        elif direction == 'short' and rsi < self.overbought:
            self.stats['filtered'] += 1
            return False, f"RSI {rsi:.1f} not extreme enough (need > {self.overbought})"
        else:
            self.stats['passed'] += 1
            return True, f"RSI {rsi:.1f} is extreme"


class PriceStructureFilter:
    """
    Detect trend by counting higher highs/lows vs lower highs/lows.
    If price is making consistent HH/HL = uptrend (don't short)
    If price is making consistent LH/LL = downtrend (don't long)
    """
    
    def __init__(self, lookback: int = 20, min_count: int = 4):
        self.lookback = lookback
        self.min_count = min_count  # Need at least this many HH or LL to confirm trend
        self.stats = {'trending_blocks': 0, 'allows': 0}
        
    def analyze_structure(self, candles: List[Dict]) -> Tuple[str, int, int]:
        """
        Analyze price structure.
        
        Returns:
            (trend, higher_highs_count, lower_lows_count)
        """
        if len(candles) < self.lookback:
            return 'neutral', 0, 0
            
        recent = candles[-self.lookback:]
        
        # Find swing highs and lows (simplified)
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Count higher highs
        hh_count = 0
        for i in range(1, len(highs)):
            if highs[i] > highs[i-1]:
                hh_count += 1
                
        # Count lower lows
        ll_count = 0
        for i in range(1, len(lows)):
            if lows[i] < lows[i-1]:
                ll_count += 1
        
        # Determine trend
        hh_ratio = hh_count / (len(highs) - 1)
        ll_ratio = ll_count / (len(lows) - 1)
        
        if hh_ratio > 0.6:
            return 'uptrend', hh_count, ll_count
        elif ll_ratio > 0.6:
            return 'downtrend', hh_count, ll_count
        else:
            return 'neutral', hh_count, ll_count
    
    def should_allow_signal(self, signal: Dict, market_state: Dict) -> Tuple[bool, str]:
        """
        Check if signal aligns with price structure.
        
        Returns:
            (allow, reason)
        """
        candles = market_state.get('timeframes', {}).get('15m', {}).get('candles', [])
        direction = signal.get('direction', 'long')
        
        trend, hh, ll = self.analyze_structure(candles)
        
        # Don't go against strong trend
        if trend == 'uptrend' and direction == 'short':
            self.stats['trending_blocks'] += 1
            return False, f"Price structure: UPTREND ({hh} HH) - don't short"
        elif trend == 'downtrend' and direction == 'long':
            self.stats['trending_blocks'] += 1
            return False, f"Price structure: DOWNTREND ({ll} LL) - don't long"
        else:
            self.stats['allows'] += 1
            return True, f"Price structure: {trend}"


# Factory functions
def create_adx_filter(threshold: float = 25) -> ADXTrendFilter:
    return ADXTrendFilter(trend_threshold=threshold)

def create_htf_filter() -> HTFTrendFilter:
    return HTFTrendFilter()

def create_strict_rsi_filter(oversold: int = 20, overbought: int = 80) -> StrictRSIFilter:
    return StrictRSIFilter(oversold=oversold, overbought=overbought)

def create_price_structure_filter(lookback: int = 20) -> PriceStructureFilter:
    return PriceStructureFilter(lookback=lookback)
