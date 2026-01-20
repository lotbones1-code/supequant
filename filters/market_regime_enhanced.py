"""
Market Regime Enhanced Filter - Phase 2.1

Detects market regime and adjusts trading confidence accordingly.
Classifies market into 4 regimes:
- TRENDING: Strong directional movement, good for trend-following
- RANGING: Sideways movement, good for mean-reversion
- HIGH_VOLATILITY: Large price swings, reduced confidence
- LOW_VOLATILITY: Compressed price action, wait for breakout

Uses existing market_state data (trend_strength, ATR, etc.)
"""

from typing import Dict, Tuple, Optional
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications"""
    BULLISH_TREND = "bullish_trend"
    BEARISH_TREND = "bearish_trend"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


class MarketRegimeEnhancedFilter:
    """
    Enhanced market regime detection filter.
    
    Classifies market conditions and adjusts confidence based on
    whether the signal aligns with the detected regime.
    
    This is a QUALITY FILTER - it contributes to the overall score
    rather than being a binary pass/fail.
    """
    
    def __init__(self):
        self.name = "MarketRegimeEnhanced"
        
        # Thresholds (can be overridden from config)
        self.trending_min_strength = 0.6      # trend_strength > this = trending
        self.ranging_max_strength = 0.35      # trend_strength < this = ranging
        self.high_vol_percentile = 80         # ATR percentile > this = high vol
        self.low_vol_percentile = 25          # ATR percentile < this = low vol
        
        # Try to load from config
        try:
            from config import (
                REGIME_TRENDING_MIN_STRENGTH,
                REGIME_RANGING_MAX_STRENGTH,
                REGIME_HIGH_VOL_PERCENTILE,
                REGIME_LOW_VOL_PERCENTILE
            )
            self.trending_min_strength = REGIME_TRENDING_MIN_STRENGTH
            self.ranging_max_strength = REGIME_RANGING_MAX_STRENGTH
            self.high_vol_percentile = REGIME_HIGH_VOL_PERCENTILE
            self.low_vol_percentile = REGIME_LOW_VOL_PERCENTILE
        except ImportError:
            pass  # Use defaults
        
        # Track last detected regime for logging
        self.last_regime = None
        self.last_score_adjustment = 0
    
    def detect_regime(self, market_state: Dict) -> Tuple[MarketRegime, Dict]:
        """
        Detect the current market regime.
        
        Args:
            market_state: Complete market state from MarketDataFeed
            
        Returns:
            (regime: MarketRegime, details: Dict)
        """
        details = {
            'trend_strength': 0,
            'trend_direction': 'neutral',
            'atr_percentile': 50,
            'ema_position': 'neutral'
        }
        
        # Get timeframe data (prefer 15m, fallback to others)
        timeframes = market_state.get('timeframes', {})
        tf_data = None
        for tf in ['15m', '5m', '1H']:
            if tf in timeframes:
                tf_data = timeframes[tf]
                break
        
        if not tf_data:
            return MarketRegime.UNKNOWN, details
        
        # Extract trend data
        trend_data = tf_data.get('trend', {})
        trend_strength = trend_data.get('trend_strength', 0)
        trend_direction = trend_data.get('trend_direction', 'neutral')
        ema_short = trend_data.get('ema_short', 0)
        ema_long = trend_data.get('ema_long', 0)
        
        details['trend_strength'] = trend_strength
        details['trend_direction'] = trend_direction
        
        # Determine EMA position (price relative to EMAs)
        if ema_short > 0 and ema_long > 0:
            if ema_short > ema_long * 1.002:  # Short EMA above long = bullish
                details['ema_position'] = 'bullish'
            elif ema_short < ema_long * 0.998:  # Short EMA below long = bearish
                details['ema_position'] = 'bearish'
            else:
                details['ema_position'] = 'neutral'
        
        # Extract ATR data for volatility
        atr_data = tf_data.get('atr', {})
        atr_percentile = atr_data.get('atr_percentile', 50)
        details['atr_percentile'] = atr_percentile
        
        # Check for HIGH VOLATILITY first (overrides other classifications)
        if atr_percentile > self.high_vol_percentile:
            return MarketRegime.HIGH_VOLATILITY, details
        
        # Check for LOW VOLATILITY (squeeze conditions)
        if atr_percentile < self.low_vol_percentile:
            return MarketRegime.LOW_VOLATILITY, details
        
        # Check for TRENDING market
        if trend_strength >= self.trending_min_strength:
            if trend_direction == 'up' or details['ema_position'] == 'bullish':
                return MarketRegime.BULLISH_TREND, details
            elif trend_direction == 'down' or details['ema_position'] == 'bearish':
                return MarketRegime.BEARISH_TREND, details
        
        # Check for RANGING market
        if trend_strength <= self.ranging_max_strength:
            return MarketRegime.RANGING, details
        
        # Default: somewhere in between - treat as mild ranging
        return MarketRegime.RANGING, details
    
    def get_score_adjustment(self, regime: MarketRegime, signal_direction: str, 
                            strategy_name: str = '') -> int:
        """
        Get confidence score adjustment based on regime and signal alignment.
        
        Args:
            regime: Detected market regime
            signal_direction: 'long' or 'short'
            strategy_name: 'breakout' or 'pullback' (optional)
            
        Returns:
            Score adjustment (-20 to +20)
        """
        direction = signal_direction.lower()
        strategy = strategy_name.lower() if strategy_name else ''
        
        # BULLISH TREND
        if regime == MarketRegime.BULLISH_TREND:
            if direction == 'long':
                return 15  # Aligned with trend
            else:
                return -15  # Counter-trend (risky)
        
        # BEARISH TREND
        elif regime == MarketRegime.BEARISH_TREND:
            if direction == 'short':
                return 15  # Aligned with trend
            else:
                return -15  # Counter-trend (risky)
        
        # RANGING
        elif regime == MarketRegime.RANGING:
            if strategy == 'pullback':
                return 10  # Mean reversion works in ranges
            elif strategy == 'breakout':
                return -5  # Breakouts often fail in ranges
            else:
                return 0  # Neutral
        
        # HIGH VOLATILITY
        elif regime == MarketRegime.HIGH_VOLATILITY:
            return -15  # Reduce confidence - choppy conditions
        
        # LOW VOLATILITY
        elif regime == MarketRegime.LOW_VOLATILITY:
            if strategy == 'breakout':
                return 5  # Breakouts can work after squeezes
            else:
                return -5  # Generally wait for expansion
        
        # UNKNOWN
        return 0
    
    def check(self, market_state: Dict, signal_direction: str = '', 
              strategy_name: str = '') -> Tuple[bool, str]:
        """
        Check if market regime is suitable for trading.
        
        This filter rarely rejects trades outright - it primarily
        adjusts confidence scores. Only extreme conditions trigger rejection.
        
        Args:
            market_state: Complete market state from MarketDataFeed
            signal_direction: 'long' or 'short'
            strategy_name: 'breakout' or 'pullback'
            
        Returns:
            (passed: bool, reason: str)
        """
        try:
            # Detect current regime
            regime, details = self.detect_regime(market_state)
            self.last_regime = regime
            
            # Calculate score adjustment
            score_adj = self.get_score_adjustment(regime, signal_direction, strategy_name)
            self.last_score_adjustment = score_adj
            
            # Format regime name for logging
            regime_name = regime.value.upper().replace('_', ' ')
            
            # Build reason string
            reason_parts = [
                f"Regime: {regime_name}",
                f"trend_strength={details['trend_strength']:.2f}",
                f"ATR_pct={details['atr_percentile']:.0f}"
            ]
            
            if score_adj != 0:
                reason_parts.append(f"score_adj={score_adj:+d}")
            
            reason = " | ".join(reason_parts)
            
            # Log the detection
            if score_adj > 0:
                logger.info(f"✅ {self.name}: {reason}")
            elif score_adj < 0:
                logger.warning(f"⚠️  {self.name}: {reason}")
            else:
                logger.info(f"ℹ️  {self.name}: {reason}")
            
            # Rejection logic - only reject in extreme cases
            # High volatility counter-trend trades are dangerous
            if regime == MarketRegime.HIGH_VOLATILITY:
                if regime == MarketRegime.HIGH_VOLATILITY and abs(score_adj) >= 15:
                    # Don't reject, just warn - let score handle it
                    pass
            
            # For now, always pass but let the score adjustment affect the trade
            return True, reason
            
        except Exception as e:
            logger.error(f"❌ {self.name}: Error during check: {e}")
            return True, f"Regime check error: {e}"
    
    def get_regime_info(self) -> Dict:
        """Get information about the last detected regime."""
        return {
            'regime': self.last_regime.value if self.last_regime else 'unknown',
            'score_adjustment': self.last_score_adjustment
        }
    
    def get_regime_score(self, market_state: Dict) -> float:
        """
        Get a normalized regime quality score (0-1).
        Higher = better trading conditions.
        
        Args:
            market_state: Complete market state
            
        Returns:
            Score from 0 to 1
        """
        regime, details = self.detect_regime(market_state)
        
        # Base scores for each regime
        regime_scores = {
            MarketRegime.BULLISH_TREND: 0.8,
            MarketRegime.BEARISH_TREND: 0.8,
            MarketRegime.RANGING: 0.5,
            MarketRegime.HIGH_VOLATILITY: 0.3,
            MarketRegime.LOW_VOLATILITY: 0.4,
            MarketRegime.UNKNOWN: 0.5
        }
        
        return regime_scores.get(regime, 0.5)


# Module-level convenience function
def detect_market_regime(market_state: Dict) -> Tuple[str, Dict]:
    """
    Convenience function to detect market regime.
    
    Returns:
        (regime_name: str, details: Dict)
    """
    filter_instance = MarketRegimeEnhancedFilter()
    regime, details = filter_instance.detect_regime(market_state)
    return regime.value, details
