"""
Dual Regime Trading System (Backtest Only)

A complete system that:
1. Detects market regime using multiple indicators
2. Routes to the appropriate strategy
3. Tracks performance per regime

BACKTEST ONLY - Does not affect live trading.
"""

import logging
import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Regime(Enum):
    STRONG_UPTREND = "strong_uptrend"
    UPTREND = "uptrend"
    RANGING = "ranging"
    DOWNTREND = "downtrend"
    STRONG_DOWNTREND = "strong_downtrend"
    CHOPPY = "choppy"


@dataclass
class RegimeAnalysis:
    """Complete regime analysis result"""
    regime: Regime
    confidence: float
    adx: float
    trend_direction: str
    ema_alignment_15m: float
    ema_alignment_4h: float
    higher_highs: int
    lower_lows: int
    volatility_percentile: float
    recommendation: str  # 'trend_following', 'mean_reversion', 'skip'


class ProperRegimeDetector:
    """
    Multi-indicator regime detection.
    
    Uses:
    - ADX for trend strength
    - EMA alignment on multiple timeframes
    - Price structure (HH/HL vs LH/LL)
    - Volatility context
    """
    
    def __init__(self):
        self.regime_history: List[Regime] = []
        self.stats = {
            'strong_uptrend': 0,
            'uptrend': 0,
            'ranging': 0,
            'downtrend': 0,
            'strong_downtrend': 0,
            'choppy': 0
        }
        
    def calculate_adx(self, candles: List[Dict], period: int = 14) -> float:
        """Calculate ADX from candles"""
        if len(candles) < period + 10:
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
        
        # Smoothed averages (Wilder's smoothing)
        def smooth(data, period):
            result = np.zeros(len(data))
            result[period-1] = np.sum(data[:period])
            for i in range(period, len(data)):
                result[i] = result[i-1] - result[i-1]/period + data[i]
            return result / period
        
        atr = smooth(tr, period)
        plus_di = 100 * smooth(plus_dm, period) / (atr + 1e-10)
        minus_di = 100 * smooth(minus_dm, period) / (atr + 1e-10)
        
        # DX and ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = smooth(dx, period)
        
        return float(adx[-1]) if len(adx) > 0 and not np.isnan(adx[-1]) else 0
    
    def count_structure(self, candles: List[Dict], lookback: int = 20) -> Tuple[int, int]:
        """
        Count higher highs and lower lows.
        
        Returns:
            (higher_highs_count, lower_lows_count)
        """
        if len(candles) < lookback + 5:
            return 0, 0
            
        recent = candles[-lookback:]
        
        # Find swing points (local highs/lows over 5 bars)
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(recent) - 2):
            # Swing high
            if (recent[i]['high'] > recent[i-1]['high'] and 
                recent[i]['high'] > recent[i-2]['high'] and
                recent[i]['high'] > recent[i+1]['high'] and 
                recent[i]['high'] > recent[i+2]['high']):
                swing_highs.append(recent[i]['high'])
            
            # Swing low
            if (recent[i]['low'] < recent[i-1]['low'] and 
                recent[i]['low'] < recent[i-2]['low'] and
                recent[i]['low'] < recent[i+1]['low'] and 
                recent[i]['low'] < recent[i+2]['low']):
                swing_lows.append(recent[i]['low'])
        
        # Count higher highs
        hh_count = 0
        for i in range(1, len(swing_highs)):
            if swing_highs[i] > swing_highs[i-1]:
                hh_count += 1
        
        # Count lower lows
        ll_count = 0
        for i in range(1, len(swing_lows)):
            if swing_lows[i] < swing_lows[i-1]:
                ll_count += 1
        
        return hh_count, ll_count
    
    def analyze(self, market_state: Dict) -> RegimeAnalysis:
        """
        Comprehensive regime analysis.
        
        Args:
            market_state: Market data with multiple timeframes
            
        Returns:
            RegimeAnalysis with all details
        """
        # Get 15m data
        tf_15m = market_state.get('timeframes', {}).get('15m', {})
        candles_15m = tf_15m.get('candles', [])
        trend_15m = tf_15m.get('trend', {})
        volatility_15m = tf_15m.get('volatility', {})
        # Handle both 'atr' dict and 'volatility' dict formats
        if not volatility_15m:
            volatility_15m = tf_15m.get('atr', {})
        
        # Get 4H data
        tf_4h = market_state.get('timeframes', {}).get('4H', {})
        trend_4h = tf_4h.get('trend', {})
        
        # Calculate ADX
        adx = self.calculate_adx(candles_15m) if len(candles_15m) > 20 else 0
        
        # Calculate EMA alignment from EMA values (handle missing ema_alignment field)
        ema_20_15m = trend_15m.get('ema_20', 0)
        ema_50_15m = trend_15m.get('ema_50', 0)
        ema_align_15m = trend_15m.get('ema_alignment', 0)
        if ema_align_15m == 0 and ema_50_15m > 0:
            ema_align_15m = (ema_20_15m - ema_50_15m) / ema_50_15m
        
        ema_20_4h = trend_4h.get('ema_20', 0)
        ema_50_4h = trend_4h.get('ema_50', 0)
        ema_align_4h = trend_4h.get('ema_alignment', 0)
        if ema_align_4h == 0 and ema_50_4h > 0:
            ema_align_4h = (ema_20_4h - ema_50_4h) / ema_50_4h
        
        # Get trend direction (handle 'up'/'down' format from backtest)
        trend_dir_15m = trend_15m.get('trend_direction', 'neutral')
        if trend_dir_15m == 'up':
            trend_dir_15m = 'bullish'
        elif trend_dir_15m == 'down':
            trend_dir_15m = 'bearish'
            
        trend_dir_4h = trend_4h.get('trend_direction', 'neutral')
        if trend_dir_4h == 'up':
            trend_dir_4h = 'bullish'
        elif trend_dir_4h == 'down':
            trend_dir_4h = 'bearish'
        
        # Count structure
        hh_count, ll_count = self.count_structure(candles_15m)
        
        # Get volatility (handle both formats)
        vol_percentile = volatility_15m.get('atr_percentile', 50)
        if vol_percentile == 50:  # Default, try alternate location
            atr_data = tf_15m.get('atr', {})
            vol_percentile = atr_data.get('atr_percentile', 50)
        
        # Determine regime using multiple factors
        regime, confidence, recommendation = self._classify_regime(
            adx=adx,
            ema_align_15m=ema_align_15m,
            ema_align_4h=ema_align_4h,
            trend_dir_15m=trend_dir_15m,
            trend_dir_4h=trend_dir_4h,
            hh_count=hh_count,
            ll_count=ll_count,
            vol_percentile=vol_percentile
        )
        
        # Track stats
        self.stats[regime.value] = self.stats.get(regime.value, 0) + 1
        self.regime_history.append(regime)
        if len(self.regime_history) > 100:
            self.regime_history = self.regime_history[-100:]
        
        return RegimeAnalysis(
            regime=regime,
            confidence=confidence,
            adx=adx,
            trend_direction=trend_dir_4h if trend_dir_4h != 'neutral' else trend_dir_15m,
            ema_alignment_15m=ema_align_15m,
            ema_alignment_4h=ema_align_4h,
            higher_highs=hh_count,
            lower_lows=ll_count,
            volatility_percentile=vol_percentile,
            recommendation=recommendation
        )
    
    def _classify_regime(self, adx: float, ema_align_15m: float, ema_align_4h: float,
                        trend_dir_15m: str, trend_dir_4h: str,
                        hh_count: int, ll_count: int, vol_percentile: float) -> Tuple[Regime, float, str]:
        """
        Classify regime using all available data.
        
        Returns:
            (regime, confidence, recommendation)
        """
        # Score bullish and bearish factors
        bullish_score = 0
        bearish_score = 0
        
        # ADX contribution (strong indicator of trend strength)
        if adx > 35:
            # Strong trend - direction determined by other factors
            if ema_align_15m > 0 or ema_align_4h > 0 or trend_dir_15m == 'bullish':
                bullish_score += 3
            elif ema_align_15m < 0 or ema_align_4h < 0 or trend_dir_15m == 'bearish':
                bearish_score += 3
        elif adx > 25:
            # Moderate trend
            if ema_align_15m > 0 or ema_align_4h > 0 or trend_dir_15m == 'bullish':
                bullish_score += 2
            elif ema_align_15m < 0 or ema_align_4h < 0 or trend_dir_15m == 'bearish':
                bearish_score += 2
        
        # EMA alignment contribution (use MUCH lower thresholds - data shows small values)
        if ema_align_4h > 0.02:  # Was 0.3
            bullish_score += 2
        elif ema_align_4h < -0.02:
            bearish_score += 2
        
        if ema_align_15m > 0.01:  # Was 0.2
            bullish_score += 1
        elif ema_align_15m < -0.01:
            bearish_score += 1
        
        # Trend direction contribution
        if trend_dir_4h == 'bullish':
            bullish_score += 2
        elif trend_dir_4h == 'bearish':
            bearish_score += 2
            
        if trend_dir_15m == 'bullish':
            bullish_score += 1
        elif trend_dir_15m == 'bearish':
            bearish_score += 1
        
        # Price structure contribution
        if hh_count >= 2 and ll_count == 0:
            bullish_score += 2
        elif ll_count >= 2 and hh_count == 0:
            bearish_score += 2
        elif hh_count >= 1:
            bullish_score += 1
        elif ll_count >= 1:
            bearish_score += 1
        
        # Classify based on scores (lowered thresholds for easier trend detection)
        total_score = bullish_score + bearish_score
        
        # Strong trend: high ADX + clear direction
        if bullish_score >= 5 and adx > 30:
            regime = Regime.STRONG_UPTREND
            confidence = min(0.9, 0.5 + bullish_score * 0.05)
            recommendation = 'trend_following'
        elif bearish_score >= 5 and adx > 30:
            regime = Regime.STRONG_DOWNTREND
            confidence = min(0.9, 0.5 + bearish_score * 0.05)
            recommendation = 'trend_following'
        # Moderate trend: decent ADX + direction
        elif bullish_score >= 3 and bullish_score > bearish_score and adx > 25:
            regime = Regime.UPTREND
            confidence = 0.6 + bullish_score * 0.03
            recommendation = 'trend_following'
        elif bearish_score >= 3 and bearish_score > bullish_score and adx > 25:
            regime = Regime.DOWNTREND
            confidence = 0.6 + bearish_score * 0.03
            recommendation = 'trend_following'
        # Low ADX = ranging
        elif adx < 20:
            regime = Regime.RANGING
            confidence = 0.7
            recommendation = 'mean_reversion'
        # High volatility + no direction = choppy
        elif vol_percentile > 70 and abs(bullish_score - bearish_score) <= 1:
            regime = Regime.CHOPPY
            confidence = 0.5
            recommendation = 'skip'
        # Default to ranging
        else:
            regime = Regime.RANGING
            confidence = 0.55
            recommendation = 'mean_reversion'
        
        return regime, confidence, recommendation


class ProperTrendStrategy:
    """
    Proper trend following strategy with multiple entry types.
    
    Entry Types:
    1. EMA Pullback - Price touches EMA 20 in a trend
    2. Breakout Continuation - New high/low after consolidation
    3. Momentum Entry - Strong momentum bar in trend direction
    """
    
    def __init__(self, min_adx: float = 20):
        self.min_adx = min_adx
        self.stats = {
            'signals': 0,
            'ema_pullback': 0,
            'breakout': 0,
            'momentum': 0
        }
        
    def analyze(self, market_state: Dict, regime_analysis: RegimeAnalysis) -> Optional[Dict]:
        """
        Generate trend following signal if conditions are met.
        
        Args:
            market_state: Market data
            regime_analysis: Current regime analysis
            
        Returns:
            Signal dict or None
        """
        # Only trade in trending regimes
        if regime_analysis.recommendation != 'trend_following':
            return None
        
        # Determine direction
        if regime_analysis.regime in [Regime.STRONG_UPTREND, Regime.UPTREND]:
            direction = 'long'
        elif regime_analysis.regime in [Regime.STRONG_DOWNTREND, Regime.DOWNTREND]:
            direction = 'short'
        else:
            return None
        
        # Get market data
        tf_15m = market_state.get('timeframes', {}).get('15m', {})
        candles = tf_15m.get('candles', [])
        trend = tf_15m.get('trend', {})
        
        # Handle volatility/atr in different formats
        volatility = tf_15m.get('volatility', {})
        if not volatility:
            volatility = tf_15m.get('atr', {})
        
        momentum = tf_15m.get('momentum', {})
        
        if len(candles) < 30:
            return None
        
        current_price = tf_15m.get('current_price', candles[-1]['close'])
        ema_20 = trend.get('ema_20', current_price)
        ema_50 = trend.get('ema_50', current_price)
        
        # Get ATR - handle both dict formats
        atr = volatility.get('atr', 0)
        if atr == 0 and isinstance(volatility, dict):
            atr = volatility.get('atr', 0)
        if atr == 0:
            # Calculate from candles
            if len(candles) > 14:
                trs = []
                for i in range(1, min(15, len(candles))):
                    h, l, c_prev = candles[-i]['high'], candles[-i]['low'], candles[-i-1]['close']
                    tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
                    trs.append(tr)
                atr = np.mean(trs) if trs else 0
        
        rsi = momentum.get('rsi', 50)
        
        if atr <= 0:
            return None
        
        # Try each entry type
        signal = None
        entry_type = None
        
        # Entry Type 1: EMA Pullback
        signal = self._check_ema_pullback(direction, current_price, ema_20, ema_50, atr, rsi, candles)
        if signal:
            entry_type = 'ema_pullback'
        
        # Entry Type 2: Breakout Continuation
        if not signal:
            signal = self._check_breakout(direction, current_price, atr, candles)
            if signal:
                entry_type = 'breakout'
        
        # Entry Type 3: Momentum Entry
        if not signal:
            signal = self._check_momentum(direction, current_price, atr, candles, regime_analysis)
            if signal:
                entry_type = 'momentum'
        
        if signal:
            signal['strategy'] = 'trend_following'
            signal['entry_type'] = entry_type
            signal['regime'] = regime_analysis.regime.value
            signal['regime_confidence'] = regime_analysis.confidence
            
            self.stats['signals'] += 1
            self.stats[entry_type] += 1
            
            logger.info(f"🎯 TrendFollow [{entry_type}]: {direction.upper()} | "
                       f"Regime: {regime_analysis.regime.value} | "
                       f"ADX: {regime_analysis.adx:.1f}")
        
        return signal
    
    def _check_ema_pullback(self, direction: str, price: float, ema_20: float, 
                           ema_50: float, atr: float, rsi: float, candles: List[Dict]) -> Optional[Dict]:
        """
        Entry on pullback to EMA 20 in a trend.
        LOOSENED CONDITIONS for more signals.
        """
        # Skip EMA alignment check - regime already confirmed trend
        
        # Check price near EMA 20 (within 1.5 ATR - loosened from 0.5)
        distance_to_ema = abs(price - ema_20)
        if distance_to_ema > atr * 1.5:
            return None
        
        # RSI check - loosened
        if direction == 'long' and rsi > 75:  # Was 70
            return None
        if direction == 'short' and rsi < 25:  # Was 30
            return None
        
        # Skip wick check - too restrictive
        
        if direction == 'long':
            stop = price - atr * 1.5
            target = price + atr * 2.5
        else:
            stop = price + atr * 1.5
            target = price - atr * 2.5
        
        return {
            'direction': direction,
            'entry_price': price,
            'stop_loss': stop,
            'target': target,
            'atr': atr,
            'rsi': rsi
        }
    
    def _check_breakout(self, direction: str, price: float, atr: float, 
                       candles: List[Dict]) -> Optional[Dict]:
        """
        Entry on breakout continuation.
        LOOSENED: Just check if price made new high/low recently.
        """
        if len(candles) < 10:
            return None
        
        # Check for continuation (recent high/low break)
        recent = candles[-10:]
        recent_high = max(c['high'] for c in recent[:-3])  # Exclude last 3
        recent_low = min(c['low'] for c in recent[:-3])
        
        if direction == 'long':
            # Price broke above recent high and still above it
            if price < recent_high * 0.995:  # Within 0.5% of high
                return None
            stop = price - atr * 2
            target = price + atr * 3
        else:
            # Price broke below recent low and still below it
            if price > recent_low * 1.005:
                return None
            stop = price + atr * 2
            target = price - atr * 3
        
        return {
            'direction': direction,
            'entry_price': price,
            'stop_loss': stop,
            'target': target,
            'atr': atr
        }
    
    def _check_momentum(self, direction: str, price: float, atr: float,
                       candles: List[Dict], regime: RegimeAnalysis) -> Optional[Dict]:
        """
        Entry on momentum in trend direction.
        LOOSENED: Works in any trending regime, lower bar for momentum.
        """
        # Allow in any trending regime (not just strong)
        if regime.regime in [Regime.RANGING, Regime.CHOPPY]:
            return None
        
        if len(candles) < 5:
            return None
        
        last_candle = candles[-1]
        body_size = abs(last_candle['close'] - last_candle['open'])
        
        # Average body size of last 10 candles
        avg_body = np.mean([abs(c['close'] - c['open']) for c in candles[-10:]])
        
        # Need above-average momentum candle (1.2x average - was 2x)
        if body_size < avg_body * 1.2:
            return None
        
        # Check direction matches
        is_bullish_candle = last_candle['close'] > last_candle['open']
        
        if direction == 'long' and not is_bullish_candle:
            return None
        if direction == 'short' and is_bullish_candle:
            return None
        
        # Entry at current price
        if direction == 'long':
            stop = last_candle['low'] - atr * 0.5
            target = price + atr * 3
        else:
            stop = last_candle['high'] + atr * 0.5
            target = price - atr * 3
        
        return {
            'direction': direction,
            'entry_price': price,
            'stop_loss': stop,
            'target': target,
            'atr': atr
        }


class DualRegimeSystem:
    """
    Complete dual regime trading system.
    
    Routes to appropriate strategy based on detected regime:
    - Trending → Trend Following
    - Ranging → Mean Reversion (existing)
    - Choppy → Skip
    """
    
    def __init__(self):
        self.detector = ProperRegimeDetector()
        self.trend_strategy = ProperTrendStrategy()
        
        # Performance tracking per regime
        self.regime_performance = {
            regime.value: {'trades': 0, 'wins': 0, 'pnl': 0.0}
            for regime in Regime
        }
        
        # Current state
        self.current_analysis: Optional[RegimeAnalysis] = None
        
    def analyze(self, market_state: Dict) -> Tuple[RegimeAnalysis, Optional[Dict]]:
        """
        Analyze market and generate appropriate signal.
        
        Returns:
            (regime_analysis, signal_or_none)
        """
        # Get regime analysis
        analysis = self.detector.analyze(market_state)
        self.current_analysis = analysis
        
        # Generate signal based on recommendation
        signal = None
        
        if analysis.recommendation == 'trend_following':
            signal = self.trend_strategy.analyze(market_state, analysis)
        
        # Mean reversion handled externally (existing system)
        # We just return the analysis so backtest engine knows what to do
        
        return analysis, signal
    
    def record_trade_result(self, regime: str, pnl: float, is_win: bool):
        """Record trade result for performance tracking"""
        if regime in self.regime_performance:
            self.regime_performance[regime]['trades'] += 1
            self.regime_performance[regime]['pnl'] += pnl
            if is_win:
                self.regime_performance[regime]['wins'] += 1
    
    def get_report(self) -> str:
        """Generate performance report"""
        lines = ["\n" + "=" * 60]
        lines.append("DUAL REGIME SYSTEM REPORT")
        lines.append("=" * 60)
        
        lines.append("\nREGIME DETECTION STATS:")
        for regime, count in self.detector.stats.items():
            if count > 0:
                lines.append(f"  {regime}: {count} candles")
        
        lines.append("\nPERFORMANCE BY REGIME:")
        for regime, perf in self.regime_performance.items():
            if perf['trades'] > 0:
                win_rate = perf['wins'] / perf['trades'] * 100
                lines.append(f"  {regime}:")
                lines.append(f"    Trades: {perf['trades']}")
                lines.append(f"    Win Rate: {win_rate:.1f}%")
                lines.append(f"    PnL: ${perf['pnl']:.2f}")
        
        lines.append("\nTREND STRATEGY STATS:")
        for entry_type, count in self.trend_strategy.stats.items():
            lines.append(f"  {entry_type}: {count}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


def create_dual_regime_system() -> DualRegimeSystem:
    """Factory function"""
    return DualRegimeSystem()
