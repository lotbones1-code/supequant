"""
Regime-Adaptive Trading System (Backtest Only)

Detects market regime and automatically adjusts strategy settings:
- TRENDING: Disable Mean Reversion, enable Trend Following, wider stops
- RANGING: Enable Mean Reversion, tighter RSI, normal position size
- CHOPPY: Reduce position size, require higher quality, or skip trades

This system learns over time by tracking what works in each regime.
"""

import logging
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    CHOPPY = "choppy"
    UNKNOWN = "unknown"


@dataclass
class RegimeConfig:
    """Configuration settings for each regime"""
    # Strategy enables
    enable_mean_reversion: bool = True
    enable_trend_following: bool = False
    enable_breakout: bool = True
    enable_pullback: bool = True
    
    # Position sizing
    position_size_mult: float = 1.0
    
    # Quality thresholds
    min_score_threshold: int = 45
    
    # Mean Reversion settings
    mr_rsi_oversold: int = 30
    mr_rsi_overbought: int = 70
    
    # Stop/TP adjustments
    stop_multiplier: float = 1.0  # Multiply ATR stop by this
    
    # Description
    description: str = ""


# Pre-defined regime configurations
REGIME_CONFIGS = {
    MarketRegime.TRENDING_UP: RegimeConfig(
        enable_mean_reversion=False,  # MR loses in trends
        enable_trend_following=True,   # TF wins in trends
        enable_breakout=True,
        enable_pullback=True,
        position_size_mult=0.7,        # Smaller size (trend can reverse)
        min_score_threshold=50,        # Higher quality required
        mr_rsi_oversold=25,            # If MR enabled, very strict
        mr_rsi_overbought=75,
        stop_multiplier=1.5,           # Wider stops for trends
        description="TRENDING UP: MR disabled, TF enabled, wider stops"
    ),
    MarketRegime.TRENDING_DOWN: RegimeConfig(
        enable_mean_reversion=False,
        enable_trend_following=True,
        enable_breakout=True,
        enable_pullback=True,
        position_size_mult=0.7,
        min_score_threshold=50,
        mr_rsi_oversold=25,
        mr_rsi_overbought=75,
        stop_multiplier=1.5,
        description="TRENDING DOWN: MR disabled, TF enabled, wider stops"
    ),
    MarketRegime.RANGING: RegimeConfig(
        enable_mean_reversion=True,    # MR excels in ranges
        enable_trend_following=False,  # TF loses in ranges
        enable_breakout=False,         # Breakouts fail in ranges
        enable_pullback=True,
        position_size_mult=1.0,        # Full size
        min_score_threshold=45,        # Normal threshold
        mr_rsi_oversold=30,
        mr_rsi_overbought=70,
        stop_multiplier=1.0,           # Normal stops
        description="RANGING: MR enabled, TF disabled, normal settings"
    ),
    MarketRegime.CHOPPY: RegimeConfig(
        enable_mean_reversion=False,   # Nothing works well in chop
        enable_trend_following=False,
        enable_breakout=False,
        enable_pullback=False,
        position_size_mult=0.3,        # Very small if forced to trade
        min_score_threshold=60,        # Very high quality only
        mr_rsi_oversold=25,
        mr_rsi_overbought=75,
        stop_multiplier=0.7,           # Tighter stops (cut losses fast)
        description="CHOPPY: Most strategies disabled, minimal risk"
    ),
    MarketRegime.UNKNOWN: RegimeConfig(
        enable_mean_reversion=True,
        enable_trend_following=False,
        enable_breakout=True,
        enable_pullback=True,
        position_size_mult=0.5,        # Half size when uncertain
        min_score_threshold=50,
        mr_rsi_oversold=30,
        mr_rsi_overbought=70,
        stop_multiplier=1.0,
        description="UNKNOWN: Conservative settings, reduced size"
    )
}


@dataclass
class RegimeStats:
    """Track performance per regime for adaptive learning"""
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades


class RegimeClassifier:
    """
    Classifies market regime based on multiple indicators.
    
    Uses:
    - Trend strength (EMA alignment, ADX)
    - Volatility (ATR percentile)
    - Price action (higher highs/lows vs range-bound)
    """
    
    def __init__(self, 
                 trend_threshold: float = 0.4,
                 strong_trend_threshold: float = 0.6,
                 volatility_high: float = 70,
                 volatility_low: float = 30,
                 lookback_periods: int = 20):
        """
        Args:
            trend_threshold: Min trend_strength for trending classification
            strong_trend_threshold: trend_strength for strong trend
            volatility_high: ATR percentile above this = high volatility
            volatility_low: ATR percentile below this = low volatility
            lookback_periods: Candles to analyze for regime
        """
        self.trend_threshold = trend_threshold
        self.strong_trend_threshold = strong_trend_threshold
        self.volatility_high = volatility_high
        self.volatility_low = volatility_low
        self.lookback_periods = lookback_periods
        
        # Regime history for smoothing
        self.regime_history: List[MarketRegime] = []
        self.max_history = 5  # Smooth over last 5 classifications
        
    def classify(self, market_state: Dict) -> Tuple[MarketRegime, float, Dict]:
        """
        Classify current market regime.
        
        Args:
            market_state: Market data with indicators
            
        Returns:
            (regime, confidence, details)
        """
        try:
            # Extract data from 15m timeframe
            tf_data = market_state.get('timeframes', {}).get('15m', {})
            trend_data = tf_data.get('trend', {})
            volatility_data = tf_data.get('volatility', {})
            candles = tf_data.get('candles', [])
            
            # Get key metrics
            trend_strength = trend_data.get('trend_strength', 0)
            trend_direction = trend_data.get('trend_direction', 'neutral')
            ema_alignment = trend_data.get('ema_alignment', 0)
            
            atr_percentile = volatility_data.get('atr_percentile', 50)
            
            # Calculate additional metrics from candles
            range_ratio = self._calculate_range_ratio(candles)
            directional_moves = self._count_directional_moves(candles)
            
            details = {
                'trend_strength': trend_strength,
                'trend_direction': trend_direction,
                'ema_alignment': ema_alignment,
                'atr_percentile': atr_percentile,
                'range_ratio': range_ratio,
                'directional_moves': directional_moves
            }
            
            # Classification logic
            regime = MarketRegime.UNKNOWN
            confidence = 0.5
            
            # Check for trending market
            if trend_strength >= self.strong_trend_threshold:
                # Strong trend
                if trend_direction == 'bullish' or ema_alignment > 0.3:
                    regime = MarketRegime.TRENDING_UP
                    confidence = min(0.9, 0.6 + trend_strength * 0.4)
                elif trend_direction == 'bearish' or ema_alignment < -0.3:
                    regime = MarketRegime.TRENDING_DOWN
                    confidence = min(0.9, 0.6 + trend_strength * 0.4)
                    
            elif trend_strength >= self.trend_threshold:
                # Moderate trend
                if trend_direction == 'bullish':
                    regime = MarketRegime.TRENDING_UP
                    confidence = 0.5 + trend_strength * 0.3
                elif trend_direction == 'bearish':
                    regime = MarketRegime.TRENDING_DOWN
                    confidence = 0.5 + trend_strength * 0.3
                else:
                    # Trend strength but no direction = choppy
                    regime = MarketRegime.CHOPPY
                    confidence = 0.6
                    
            elif trend_strength < 0.25:
                # Low trend strength
                if atr_percentile < self.volatility_low:
                    # Low volatility + low trend = ranging
                    regime = MarketRegime.RANGING
                    confidence = 0.7 + (self.volatility_low - atr_percentile) / 100
                elif atr_percentile > self.volatility_high:
                    # High volatility + low trend = choppy
                    regime = MarketRegime.CHOPPY
                    confidence = 0.6 + (atr_percentile - self.volatility_high) / 100
                else:
                    # Normal volatility + low trend = ranging
                    regime = MarketRegime.RANGING
                    confidence = 0.6
            else:
                # Middle ground - use range ratio
                if range_ratio > 0.7:
                    regime = MarketRegime.RANGING
                    confidence = 0.55
                elif directional_moves > 0.6:
                    if trend_direction == 'bullish':
                        regime = MarketRegime.TRENDING_UP
                    else:
                        regime = MarketRegime.TRENDING_DOWN
                    confidence = 0.55
                else:
                    regime = MarketRegime.CHOPPY
                    confidence = 0.5
            
            # Smooth regime changes (avoid whipsawing)
            regime = self._smooth_regime(regime)
            
            details['raw_regime'] = regime.value
            details['confidence'] = confidence
            
            return regime, confidence, details
            
        except Exception as e:
            logger.warning(f"Regime classification error: {e}")
            return MarketRegime.UNKNOWN, 0.3, {'error': str(e)}
    
    def _calculate_range_ratio(self, candles: List[Dict]) -> float:
        """
        Calculate how range-bound the price is.
        High ratio = price staying within a range
        Low ratio = price breaking out of ranges
        """
        if len(candles) < self.lookback_periods:
            return 0.5
            
        recent = candles[-self.lookback_periods:]
        
        # Find overall range
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        overall_high = max(highs)
        overall_low = min(lows)
        overall_range = overall_high - overall_low
        
        if overall_range == 0:
            return 1.0
        
        # Count how many candles stayed within middle 60% of range
        middle_high = overall_low + overall_range * 0.8
        middle_low = overall_low + overall_range * 0.2
        
        in_range = sum(1 for c in recent if c['high'] < middle_high and c['low'] > middle_low)
        
        return in_range / len(recent)
    
    def _count_directional_moves(self, candles: List[Dict]) -> float:
        """
        Count consecutive directional moves.
        High value = strong directional bias
        Low value = back-and-forth movement
        """
        if len(candles) < self.lookback_periods:
            return 0.5
            
        recent = candles[-self.lookback_periods:]
        
        # Count up vs down candles
        up_candles = sum(1 for c in recent if c['close'] > c['open'])
        
        # Bias towards one direction
        ratio = up_candles / len(recent)
        
        # Convert to 0-1 scale where 0.5 = no bias, 1.0 = strong bias
        return abs(ratio - 0.5) * 2
    
    def _smooth_regime(self, new_regime: MarketRegime) -> MarketRegime:
        """
        Smooth regime changes to avoid whipsawing.
        Only change regime if it's consistent over multiple readings.
        """
        self.regime_history.append(new_regime)
        
        if len(self.regime_history) > self.max_history:
            self.regime_history = self.regime_history[-self.max_history:]
        
        if len(self.regime_history) < 3:
            return new_regime
        
        # Count most common regime in history
        regime_counts = {}
        for r in self.regime_history:
            regime_counts[r] = regime_counts.get(r, 0) + 1
        
        most_common = max(regime_counts, key=regime_counts.get)
        
        # Only switch if new regime appears 2+ times recently
        if regime_counts.get(new_regime, 0) >= 2:
            return new_regime
        
        return most_common


class RegimeAdaptiveRouter:
    """
    Routes trading decisions based on detected regime.
    Tracks performance per regime for adaptive learning.
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.classifier = RegimeClassifier()
        
        # Performance tracking per regime
        self.regime_stats: Dict[MarketRegime, RegimeStats] = {
            regime: RegimeStats() for regime in MarketRegime
        }
        
        # Current state
        self.current_regime: MarketRegime = MarketRegime.UNKNOWN
        self.current_confidence: float = 0.5
        self.regime_details: Dict = {}
        
        # Trade tracking
        self.trades_in_regime: Dict[str, MarketRegime] = {}  # trade_id -> regime
        
        logger.info("Regime-Adaptive Router initialized")
        
    def analyze(self, market_state: Dict) -> Tuple[RegimeConfig, Dict]:
        """
        Analyze market and return appropriate config for current regime.
        
        Args:
            market_state: Current market data
            
        Returns:
            (regime_config, analysis_details)
        """
        if not self.enabled:
            return REGIME_CONFIGS[MarketRegime.UNKNOWN], {'enabled': False}
        
        # Classify regime
        regime, confidence, details = self.classifier.classify(market_state)
        
        self.current_regime = regime
        self.current_confidence = confidence
        self.regime_details = details
        
        # Get config for this regime
        config = REGIME_CONFIGS.get(regime, REGIME_CONFIGS[MarketRegime.UNKNOWN])
        
        # Add regime info to details
        details['regime'] = regime.value
        details['regime_description'] = config.description
        details['strategies_enabled'] = {
            'mean_reversion': config.enable_mean_reversion,
            'trend_following': config.enable_trend_following,
            'breakout': config.enable_breakout,
            'pullback': config.enable_pullback
        }
        details['position_size_mult'] = config.position_size_mult
        details['min_score'] = config.min_score_threshold
        
        # Log regime change
        logger.info(f"📊 REGIME: {regime.value.upper()} (conf: {confidence:.0%})")
        logger.debug(f"   {config.description}")
        
        return config, details
    
    def should_trade_strategy(self, strategy_name: str, regime_config: RegimeConfig) -> bool:
        """
        Check if a strategy should be active in current regime.
        
        Args:
            strategy_name: Name of strategy ('mean_reversion', 'trend_following', etc.)
            regime_config: Current regime configuration
            
        Returns:
            True if strategy should be active
        """
        strategy_map = {
            'mean_reversion': regime_config.enable_mean_reversion,
            'trend_following': regime_config.enable_trend_following,
            'breakout': regime_config.enable_breakout,
            'pullback': regime_config.enable_pullback,
            'momentum': regime_config.enable_trend_following,  # Same as TF
            'structure': True  # Always allow structure
        }
        
        return strategy_map.get(strategy_name.lower(), True)
    
    def record_trade_entry(self, trade_id: str):
        """Record which regime a trade was entered in"""
        self.trades_in_regime[trade_id] = self.current_regime
        
    def record_trade_result(self, trade_id: str, pnl: float):
        """
        Record trade result for regime performance tracking.
        
        Args:
            trade_id: Unique trade identifier
            pnl: Profit/loss of the trade
        """
        regime = self.trades_in_regime.get(trade_id, MarketRegime.UNKNOWN)
        
        stats = self.regime_stats[regime]
        stats.total_trades += 1
        stats.total_pnl += pnl
        
        if pnl > 0:
            stats.winning_trades += 1
            # Update running average win
            n = stats.winning_trades
            stats.avg_win = stats.avg_win * (n - 1) / n + pnl / n
        else:
            # Update running average loss
            n = stats.total_trades - stats.winning_trades
            if n > 0:
                stats.avg_loss = stats.avg_loss * (n - 1) / n + pnl / n
        
        # Clean up
        if trade_id in self.trades_in_regime:
            del self.trades_in_regime[trade_id]
            
        logger.debug(f"Regime {regime.value} stats: {stats.total_trades} trades, "
                    f"{stats.win_rate:.0%} win rate, ${stats.total_pnl:.2f} PnL")
    
    def get_regime_report(self) -> str:
        """Generate performance report by regime"""
        lines = ["\n" + "=" * 60]
        lines.append("REGIME PERFORMANCE REPORT")
        lines.append("=" * 60)
        
        for regime, stats in self.regime_stats.items():
            if stats.total_trades > 0:
                lines.append(f"\n{regime.value.upper()}:")
                lines.append(f"  Trades: {stats.total_trades}")
                lines.append(f"  Win Rate: {stats.win_rate:.1%}")
                lines.append(f"  Total PnL: ${stats.total_pnl:.2f}")
                lines.append(f"  Avg Win: ${stats.avg_win:.2f}")
                lines.append(f"  Avg Loss: ${stats.avg_loss:.2f}")
        
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


def create_regime_router(enabled: bool = True) -> RegimeAdaptiveRouter:
    """Factory function to create regime router"""
    return RegimeAdaptiveRouter(enabled=enabled)
