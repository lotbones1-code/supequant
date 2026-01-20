"""
Adaptive Trading Systems for Future-Proofing

These systems learn and adapt to changing market conditions:
1. AdaptiveThreshold - Adjusts quality threshold based on recent performance
2. RollingRegimeDetector - Real-time regime detection with parameter adjustment
3. PerformanceBasedLearning - Learns which signals/filters predict wins

All systems are designed for backtesting first, then can be added to live system.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# 1. ADAPTIVE THRESHOLD SYSTEM
# =============================================================================

@dataclass
class TradeResult:
    """Record of a completed trade for learning"""
    timestamp: datetime
    direction: str
    strategy: str
    entry_score: float
    pnl: float
    is_win: bool
    regime: str = "unknown"
    filter_scores: Dict[str, float] = field(default_factory=dict)


class AdaptiveThreshold:
    """
    Dynamically adjusts the quality threshold based on recent performance.
    
    Logic:
    - If winning a lot → can afford to be more selective (raise threshold)
    - If losing → need better setups (raise threshold) OR market is bad (lower to catch any good ones)
    - Uses rolling window of recent trades to make decisions
    
    This is smarter than static thresholds because it adapts to:
    - Changing market conditions
    - Strategy performance drift
    - Filter effectiveness changes
    """
    
    def __init__(self, 
                 base_threshold: float = 45,
                 min_threshold: float = 35,
                 max_threshold: float = 65,
                 lookback_trades: int = 20,
                 target_win_rate: float = 0.50,
                 adjustment_speed: float = 0.1):
        """
        Args:
            base_threshold: Starting threshold
            min_threshold: Never go below this
            max_threshold: Never go above this
            lookback_trades: Number of recent trades to consider
            target_win_rate: Desired win rate to maintain
            adjustment_speed: How fast to adjust (0.1 = 10% adjustment per check)
        """
        self.base_threshold = base_threshold
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.lookback_trades = lookback_trades
        self.target_win_rate = target_win_rate
        self.adjustment_speed = adjustment_speed
        
        # Current state
        self.current_threshold = base_threshold
        self.trade_history: deque = deque(maxlen=lookback_trades * 2)  # Keep extra for analysis
        
        # Performance tracking
        self.threshold_history: List[Tuple[datetime, float]] = []
        self.adjustments_made = 0
        
        # Learning: track which thresholds work best
        self.threshold_performance: Dict[int, Dict] = {}  # threshold -> {wins, losses, pnl}
        
    def record_trade(self, trade: TradeResult):
        """Record a completed trade for learning"""
        self.trade_history.append(trade)
        
        # Track performance at current threshold level
        threshold_bucket = int(self.current_threshold // 5) * 5  # Round to nearest 5
        if threshold_bucket not in self.threshold_performance:
            self.threshold_performance[threshold_bucket] = {'wins': 0, 'losses': 0, 'pnl': 0.0}
        
        self.threshold_performance[threshold_bucket]['pnl'] += trade.pnl
        if trade.is_win:
            self.threshold_performance[threshold_bucket]['wins'] += 1
        else:
            self.threshold_performance[threshold_bucket]['losses'] += 1
    
    def get_threshold(self, current_time: Optional[datetime] = None) -> float:
        """
        Get the current adaptive threshold.
        
        Adjusts based on recent performance.
        """
        if len(self.trade_history) < 5:
            return self.current_threshold  # Not enough data yet
        
        # Get recent trades
        recent = list(self.trade_history)[-self.lookback_trades:]
        if len(recent) < 5:
            return self.current_threshold
        
        # Calculate recent performance
        wins = sum(1 for t in recent if t.is_win)
        total = len(recent)
        win_rate = wins / total
        recent_pnl = sum(t.pnl for t in recent)
        
        # Determine adjustment direction and magnitude
        old_threshold = self.current_threshold
        
        if win_rate < self.target_win_rate - 0.1:
            # Losing too much → RAISE threshold to be more selective
            adjustment = self.adjustment_speed * (self.target_win_rate - win_rate) * 50
            self.current_threshold = min(self.max_threshold, 
                                        self.current_threshold + adjustment)
            reason = f"low_win_rate ({win_rate:.1%})"
            
        elif win_rate > self.target_win_rate + 0.15 and recent_pnl > 0:
            # Winning a lot and profitable → can LOWER threshold slightly to catch more trades
            adjustment = self.adjustment_speed * (win_rate - self.target_win_rate) * 30
            self.current_threshold = max(self.min_threshold,
                                        self.current_threshold - adjustment)
            reason = f"high_win_rate ({win_rate:.1%})"
            
        elif recent_pnl < 0 and win_rate < 0.45:
            # Losing money with decent attempts → need HIGHER quality
            self.current_threshold = min(self.max_threshold,
                                        self.current_threshold + 3)
            reason = f"losing_money (${recent_pnl:.0f})"
        else:
            # Performance is acceptable, small drift toward base
            drift = (self.base_threshold - self.current_threshold) * 0.05
            self.current_threshold += drift
            reason = "drift_to_base"
        
        # Ensure bounds
        self.current_threshold = max(self.min_threshold, 
                                    min(self.max_threshold, self.current_threshold))
        
        # Log if changed significantly
        if abs(self.current_threshold - old_threshold) > 0.5:
            self.adjustments_made += 1
            if current_time:
                self.threshold_history.append((current_time, self.current_threshold))
            logger.info(f"🎚️ ADAPTIVE THRESHOLD: {old_threshold:.1f} → {self.current_threshold:.1f} ({reason})")
        
        return self.current_threshold
    
    def get_optimal_threshold(self) -> float:
        """
        Based on collected data, what threshold would have been optimal?
        """
        if not self.threshold_performance:
            return self.base_threshold
        
        # Find threshold with best risk-adjusted performance
        best_threshold = self.base_threshold
        best_score = float('-inf')
        
        for threshold, perf in self.threshold_performance.items():
            total = perf['wins'] + perf['losses']
            if total < 5:
                continue
            
            win_rate = perf['wins'] / total
            avg_pnl = perf['pnl'] / total
            
            # Score = win_rate * avg_pnl (risk-adjusted)
            score = win_rate * avg_pnl if avg_pnl > 0 else avg_pnl
            
            if score > best_score:
                best_score = score
                best_threshold = threshold
        
        return best_threshold
    
    def get_report(self) -> str:
        """Generate performance report"""
        lines = ["\n" + "=" * 60]
        lines.append("ADAPTIVE THRESHOLD REPORT")
        lines.append("=" * 60)
        
        lines.append(f"\nConfiguration:")
        lines.append(f"  Base: {self.base_threshold} | Min: {self.min_threshold} | Max: {self.max_threshold}")
        lines.append(f"  Target Win Rate: {self.target_win_rate:.0%}")
        
        lines.append(f"\nPerformance:")
        lines.append(f"  Total Trades Tracked: {len(self.trade_history)}")
        lines.append(f"  Threshold Adjustments: {self.adjustments_made}")
        lines.append(f"  Current Threshold: {self.current_threshold:.1f}")
        lines.append(f"  Optimal Threshold (hindsight): {self.get_optimal_threshold()}")
        
        if self.threshold_performance:
            lines.append(f"\nPerformance by Threshold Level:")
            for threshold in sorted(self.threshold_performance.keys()):
                perf = self.threshold_performance[threshold]
                total = perf['wins'] + perf['losses']
                if total > 0:
                    wr = perf['wins'] / total * 100
                    lines.append(f"  {threshold}: {total} trades, {wr:.0f}% WR, ${perf['pnl']:.0f} PnL")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# 2. ROLLING REGIME DETECTOR
# =============================================================================

class MarketRegime(Enum):
    STRONG_TREND_UP = "strong_trend_up"
    TREND_UP = "trend_up"
    RANGING = "ranging"
    TREND_DOWN = "trend_down"
    STRONG_TREND_DOWN = "strong_trend_down"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


@dataclass
class RegimeConfig:
    """Configuration for a specific regime"""
    enable_mean_reversion: bool = True
    enable_momentum: bool = True
    mr_rsi_oversold: int = 30
    mr_rsi_overbought: int = 70
    quality_threshold: float = 45
    position_size_mult: float = 1.0
    description: str = ""


class RollingRegimeDetector:
    """
    Real-time regime detection using rolling indicators.
    
    Unlike the Dual Regime System which classifies per-candle,
    this uses longer-term rolling windows to detect regime SHIFTS
    and adjusts trading parameters accordingly.
    
    Key insight: We don't need to predict the regime perfectly,
    we just need to detect when it CHANGES and adjust.
    """
    
    def __init__(self,
                 trend_window: int = 50,      # Candles to assess trend
                 volatility_window: int = 30,  # Candles to assess volatility
                 regime_persistence: int = 10, # Candles before confirming regime change
                 adx_trend_threshold: float = 30,
                 adx_strong_threshold: float = 45):
        
        self.trend_window = trend_window
        self.volatility_window = volatility_window
        self.regime_persistence = regime_persistence
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_strong_threshold = adx_strong_threshold
        
        # Current state
        self.current_regime = MarketRegime.RANGING
        self.regime_start_time: Optional[datetime] = None
        self.regime_candle_count = 0
        self.pending_regime: Optional[MarketRegime] = None
        self.pending_count = 0
        
        # History
        self.regime_history: List[Tuple[datetime, MarketRegime]] = []
        self.regime_durations: Dict[str, List[int]] = {r.value: [] for r in MarketRegime}
        
        # Regime-specific configs
        self.regime_configs = self._create_regime_configs()
        
        # Performance tracking by regime
        self.regime_performance: Dict[str, Dict] = {
            r.value: {'trades': 0, 'wins': 0, 'pnl': 0.0} for r in MarketRegime
        }
    
    def _create_regime_configs(self) -> Dict[MarketRegime, RegimeConfig]:
        """Create optimized configurations for each regime"""
        return {
            MarketRegime.STRONG_TREND_UP: RegimeConfig(
                enable_mean_reversion=False,  # MR fails in strong trends
                enable_momentum=True,
                quality_threshold=50,
                position_size_mult=0.5,  # Smaller size, trend can reverse
                description="Strong uptrend - MR disabled, momentum only"
            ),
            MarketRegime.TREND_UP: RegimeConfig(
                enable_mean_reversion=True,
                enable_momentum=True,
                mr_rsi_oversold=25,  # Stricter - only deep pullbacks
                mr_rsi_overbought=80,  # Looser - let winners run
                quality_threshold=50,
                position_size_mult=0.75,
                description="Uptrend - cautious MR, favor longs"
            ),
            MarketRegime.RANGING: RegimeConfig(
                enable_mean_reversion=True,
                enable_momentum=True,
                mr_rsi_oversold=30,
                mr_rsi_overbought=70,
                quality_threshold=45,
                position_size_mult=1.0,
                description="Ranging - normal MR parameters"
            ),
            MarketRegime.TREND_DOWN: RegimeConfig(
                enable_mean_reversion=True,
                enable_momentum=True,
                mr_rsi_oversold=20,  # Looser - catch bounces early
                mr_rsi_overbought=75,  # Stricter - only strong overbought
                quality_threshold=50,
                position_size_mult=0.75,
                description="Downtrend - cautious MR, favor shorts"
            ),
            MarketRegime.STRONG_TREND_DOWN: RegimeConfig(
                enable_mean_reversion=False,  # MR fails in strong trends
                enable_momentum=True,
                quality_threshold=50,
                position_size_mult=0.5,
                description="Strong downtrend - MR disabled, momentum only"
            ),
            MarketRegime.HIGH_VOLATILITY: RegimeConfig(
                enable_mean_reversion=True,
                enable_momentum=False,  # Too choppy for momentum
                mr_rsi_oversold=25,
                mr_rsi_overbought=75,
                quality_threshold=55,  # Higher bar
                position_size_mult=0.5,  # Smaller positions
                description="High volatility - reduced size, higher quality bar"
            ),
            MarketRegime.LOW_VOLATILITY: RegimeConfig(
                enable_mean_reversion=True,
                enable_momentum=True,
                quality_threshold=40,  # Can be less strict
                position_size_mult=1.2,  # Slightly larger ok
                description="Low volatility - slightly relaxed parameters"
            ),
        }
    
    def calculate_adx(self, candles: List[Dict], period: int = 14) -> float:
        """Calculate ADX from candles"""
        if len(candles) < period + 1:
            return 0
        
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        closes = [c['close'] for c in candles]
        
        # True Range
        tr_list = []
        plus_dm_list = []
        minus_dm_list = []
        
        for i in range(1, len(candles)):
            high, low, prev_close = highs[i], lows[i], closes[i-1]
            prev_high, prev_low = highs[i-1], lows[i-1]
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
            
            plus_dm = max(0, high - prev_high) if high - prev_high > prev_low - low else 0
            minus_dm = max(0, prev_low - low) if prev_low - low > high - prev_high else 0
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
        
        if len(tr_list) < period:
            return 0
        
        # Wilder's smoothing
        def wilder_smooth(data, period):
            smoothed = [sum(data[:period])]
            for val in data[period:]:
                smoothed.append(smoothed[-1] - smoothed[-1]/period + val)
            return smoothed
        
        atr = wilder_smooth(tr_list, period)
        plus_di_smooth = wilder_smooth(plus_dm_list, period)
        minus_di_smooth = wilder_smooth(minus_dm_list, period)
        
        # DI values
        dx_list = []
        for i in range(len(atr)):
            if atr[i] == 0:
                continue
            plus_di = 100 * plus_di_smooth[i] / atr[i]
            minus_di = 100 * minus_di_smooth[i] / atr[i]
            
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx = 100 * abs(plus_di - minus_di) / di_sum
                dx_list.append(dx)
        
        if len(dx_list) < period:
            return 0
        
        # ADX is smoothed DX
        adx = sum(dx_list[-period:]) / period
        return adx
    
    def analyze(self, candles: List[Dict], current_time: datetime) -> Tuple[MarketRegime, RegimeConfig]:
        """
        Analyze current market state and return regime + config.
        
        Uses persistence to avoid flip-flopping between regimes.
        """
        if len(candles) < self.trend_window:
            return self.current_regime, self.regime_configs[self.current_regime]
        
        # Calculate indicators
        recent = candles[-self.trend_window:]
        closes = [c['close'] for c in recent]
        
        # Trend direction and strength
        ema_20 = np.mean(closes[-20:])
        ema_50 = np.mean(closes[-50:]) if len(closes) >= 50 else np.mean(closes)
        trend_direction = 1 if ema_20 > ema_50 else -1
        trend_strength = abs(ema_20 - ema_50) / ema_50 if ema_50 > 0 else 0
        
        # ADX
        adx = self.calculate_adx(candles[-60:]) if len(candles) >= 60 else 0
        
        # Volatility
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        volatility = np.std(returns) * 100 if returns else 0  # As percentage
        
        # Determine detected regime
        detected_regime = self._classify_regime(adx, trend_direction, trend_strength, volatility)
        
        # Apply persistence - don't change regime too quickly
        if detected_regime != self.current_regime:
            if detected_regime == self.pending_regime:
                self.pending_count += 1
                if self.pending_count >= self.regime_persistence:
                    # Confirmed regime change
                    old_regime = self.current_regime
                    self.current_regime = detected_regime
                    self.pending_regime = None
                    self.pending_count = 0
                    
                    # Record duration of old regime
                    if self.regime_start_time:
                        self.regime_durations[old_regime.value].append(self.regime_candle_count)
                    
                    self.regime_start_time = current_time
                    self.regime_candle_count = 0
                    self.regime_history.append((current_time, self.current_regime))
                    
                    logger.info(f"🔄 REGIME CHANGE: {old_regime.value} → {self.current_regime.value}")
            else:
                # New pending regime
                self.pending_regime = detected_regime
                self.pending_count = 1
        else:
            # Same regime, reset pending
            self.pending_regime = None
            self.pending_count = 0
        
        self.regime_candle_count += 1
        
        return self.current_regime, self.regime_configs[self.current_regime]
    
    def _classify_regime(self, adx: float, trend_dir: int, trend_strength: float, 
                        volatility: float) -> MarketRegime:
        """Classify market regime based on indicators"""
        
        # Check volatility extremes first
        if volatility > 3.0:  # Very high volatility (>3% moves)
            return MarketRegime.HIGH_VOLATILITY
        if volatility < 0.5:  # Very low volatility (<0.5% moves)
            return MarketRegime.LOW_VOLATILITY
        
        # Check trend strength
        if adx > self.adx_strong_threshold:
            # Strong trend
            return MarketRegime.STRONG_TREND_UP if trend_dir > 0 else MarketRegime.STRONG_TREND_DOWN
        elif adx > self.adx_trend_threshold:
            # Moderate trend
            return MarketRegime.TREND_UP if trend_dir > 0 else MarketRegime.TREND_DOWN
        else:
            # Ranging
            return MarketRegime.RANGING
    
    def record_trade(self, regime: str, pnl: float, is_win: bool):
        """Record trade result for regime performance tracking"""
        if regime in self.regime_performance:
            self.regime_performance[regime]['trades'] += 1
            self.regime_performance[regime]['pnl'] += pnl
            if is_win:
                self.regime_performance[regime]['wins'] += 1
    
    def get_report(self) -> str:
        """Generate regime detection report"""
        lines = ["\n" + "=" * 60]
        lines.append("ROLLING REGIME DETECTOR REPORT")
        lines.append("=" * 60)
        
        lines.append(f"\nCurrent Regime: {self.current_regime.value}")
        lines.append(f"Regime Duration: {self.regime_candle_count} candles")
        
        lines.append(f"\nRegime Changes: {len(self.regime_history)}")
        
        lines.append(f"\nPerformance by Regime:")
        for regime, perf in self.regime_performance.items():
            if perf['trades'] > 0:
                wr = perf['wins'] / perf['trades'] * 100
                lines.append(f"  {regime}:")
                lines.append(f"    Trades: {perf['trades']} | WR: {wr:.0f}% | PnL: ${perf['pnl']:.0f}")
        
        lines.append(f"\nRegime Duration Statistics:")
        for regime, durations in self.regime_durations.items():
            if durations:
                avg = np.mean(durations)
                lines.append(f"  {regime}: avg {avg:.0f} candles ({len(durations)} occurrences)")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# 3. PERFORMANCE-BASED FILTER LEARNING
# =============================================================================

class FilterLearner:
    """
    Learns which filter scores correlate with winning trades.
    
    Instead of fixed weights, this system:
    1. Tracks filter scores for every trade
    2. Correlates scores with outcomes
    3. Adjusts weights to favor predictive filters
    
    This helps identify which signals matter and which don't.
    """
    
    def __init__(self, 
                 learning_rate: float = 0.1,
                 min_trades_to_learn: int = 20):
        
        self.learning_rate = learning_rate
        self.min_trades_to_learn = min_trades_to_learn
        
        # Filter weights (start equal)
        self.filter_weights = {
            'volume': 1.0,
            'trend': 1.0,
            'rsi': 1.0,
            'volatility': 1.0,
            'pattern': 1.0,
            'btc_correlation': 1.0,
        }
        
        # Historical data for learning
        self.trade_data: List[Dict] = []
        
        # Learned correlations
        self.filter_correlations: Dict[str, float] = {}
        
        # Track which filters predicted wins
        self.filter_win_rates: Dict[str, Dict] = {
            f: {'high_score_wins': 0, 'high_score_total': 0,
                'low_score_wins': 0, 'low_score_total': 0}
            for f in self.filter_weights.keys()
        }
    
    def record_trade(self, filter_scores: Dict[str, float], pnl: float, is_win: bool):
        """Record trade with its filter scores for learning"""
        self.trade_data.append({
            'scores': filter_scores,
            'pnl': pnl,
            'is_win': is_win
        })
        
        # Update filter win rates
        for filter_name, score in filter_scores.items():
            if filter_name not in self.filter_win_rates:
                self.filter_win_rates[filter_name] = {
                    'high_score_wins': 0, 'high_score_total': 0,
                    'low_score_wins': 0, 'low_score_total': 0
                }
            
            # High score = above 15 (out of typical 0-25 per component)
            if score > 15:
                self.filter_win_rates[filter_name]['high_score_total'] += 1
                if is_win:
                    self.filter_win_rates[filter_name]['high_score_wins'] += 1
            else:
                self.filter_win_rates[filter_name]['low_score_total'] += 1
                if is_win:
                    self.filter_win_rates[filter_name]['low_score_wins'] += 1
        
        # Update weights if we have enough data
        if len(self.trade_data) >= self.min_trades_to_learn:
            self._update_weights()
    
    def _update_weights(self):
        """Update filter weights based on correlation with wins"""
        for filter_name in self.filter_weights.keys():
            stats = self.filter_win_rates.get(filter_name, {})
            
            high_total = stats.get('high_score_total', 0)
            low_total = stats.get('low_score_total', 0)
            
            if high_total < 5 or low_total < 5:
                continue  # Not enough data
            
            high_wr = stats['high_score_wins'] / high_total
            low_wr = stats['low_score_wins'] / low_total
            
            # If high scores predict wins better than low scores, increase weight
            predictive_power = high_wr - low_wr
            
            # Adjust weight
            adjustment = predictive_power * self.learning_rate
            new_weight = max(0.2, min(2.0, self.filter_weights[filter_name] + adjustment))
            
            if abs(new_weight - self.filter_weights[filter_name]) > 0.05:
                logger.debug(f"📊 Filter weight update: {filter_name} {self.filter_weights[filter_name]:.2f} → {new_weight:.2f}")
            
            self.filter_weights[filter_name] = new_weight
            self.filter_correlations[filter_name] = predictive_power
    
    def get_weighted_score(self, filter_scores: Dict[str, float]) -> float:
        """Calculate weighted score using learned weights"""
        total_weight = 0
        weighted_sum = 0
        
        for filter_name, score in filter_scores.items():
            weight = self.filter_weights.get(filter_name, 1.0)
            weighted_sum += score * weight
            total_weight += weight * 25  # Normalize assuming max 25 per filter
        
        if total_weight == 0:
            return 50  # Default
        
        return (weighted_sum / total_weight) * 100
    
    def get_most_predictive_filters(self) -> List[Tuple[str, float]]:
        """Return filters ranked by predictive power"""
        return sorted(self.filter_correlations.items(), 
                     key=lambda x: abs(x[1]), reverse=True)
    
    def get_report(self) -> str:
        """Generate learning report"""
        lines = ["\n" + "=" * 60]
        lines.append("FILTER LEARNING REPORT")
        lines.append("=" * 60)
        
        lines.append(f"\nTrades Analyzed: {len(self.trade_data)}")
        
        lines.append(f"\nLearned Filter Weights:")
        for f, w in sorted(self.filter_weights.items(), key=lambda x: x[1], reverse=True):
            correlation = self.filter_correlations.get(f, 0)
            lines.append(f"  {f}: {w:.2f} (correlation: {correlation:+.2f})")
        
        lines.append(f"\nFilter Win Rate Analysis:")
        for f, stats in self.filter_win_rates.items():
            high_total = stats['high_score_total']
            low_total = stats['low_score_total']
            if high_total > 0 and low_total > 0:
                high_wr = stats['high_score_wins'] / high_total * 100
                low_wr = stats['low_score_wins'] / low_total * 100
                lines.append(f"  {f}:")
                lines.append(f"    High score WR: {high_wr:.0f}% ({high_total} trades)")
                lines.append(f"    Low score WR: {low_wr:.0f}% ({low_total} trades)")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_adaptive_threshold(base_threshold: float = 45) -> AdaptiveThreshold:
    """Create adaptive threshold system with sensible defaults"""
    return AdaptiveThreshold(
        base_threshold=base_threshold,
        min_threshold=35,
        max_threshold=65,
        lookback_trades=15,
        target_win_rate=0.48,
        adjustment_speed=0.15
    )


def create_rolling_regime_detector() -> RollingRegimeDetector:
    """Create rolling regime detector with sensible defaults"""
    return RollingRegimeDetector(
        trend_window=50,
        volatility_window=30,
        regime_persistence=8,  # ~2 hours of 15m candles before confirming change
        adx_trend_threshold=28,
        adx_strong_threshold=40
    )


def create_filter_learner() -> FilterLearner:
    """Create filter learning system"""
    return FilterLearner(
        learning_rate=0.1,
        min_trades_to_learn=15
    )
