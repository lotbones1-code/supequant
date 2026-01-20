"""
Smart Multi-Timeframe Intelligence for Backtesting

This module checks higher timeframes to confirm signals before entry.

Strategy-Aware Logic:
- TREND FOLLOWING (Momentum, Breakout, Pullback): Trade WITH the trend
- MEAN REVERSION: Only block when trend is EXTREMELY strong (catching falling knife)

Features:
1. Strategy-aware filtering
2. Trend strength detection (not just direction)
3. Multi-timeframe momentum confirmation
4. Falling knife protection for Mean Reversion

BACKTESTING ONLY - Does not affect live trading.
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MTFAnalysis:
    """Results of multi-timeframe analysis"""
    allowed: bool
    confidence: float
    trend_1h: str  # 'bullish', 'bearish', 'neutral'
    trend_4h: str
    trend_15m: str
    trend_strength_1h: float  # 0-1 how strong is the trend
    alignment_score: float  # 0-1, how aligned are the timeframes
    reason: str


# Strategies that FADE trends (trade against the move)
MEAN_REVERSION_STRATEGIES = ['meanreversion', 'mean_reversion', 'mr']

# Strategies that FOLLOW trends (trade with the move)
TREND_FOLLOWING_STRATEGIES = ['momentum', 'breakout', 'pullback', 'trend']


class SmartMTFChecker:
    """
    Multi-Timeframe Intelligence for smarter trade filtering.
    
    Strategy-Aware Rules:
    
    FOR TREND FOLLOWING (Momentum, Breakout, Pullback):
    - LONG trades: Higher timeframes should be bullish or neutral
    - SHORT trades: Higher timeframes should be bearish or neutral
    
    FOR MEAN REVERSION:
    - Only block when trend is EXTREMELY strong (strength > 0.7)
    - Catches the "falling knife" scenario
    - Otherwise allow trades against the trend (that's the whole point of MR!)
    """
    
    def __init__(self, 
                 require_1h_alignment: bool = True,
                 require_4h_alignment: bool = False,
                 min_alignment_score: float = 0.3,
                 mr_extreme_threshold: float = 0.7):
        """
        Initialize MTF checker.
        
        Args:
            require_1h_alignment: Require 1H trend to align with trade direction (for trend following)
            require_4h_alignment: Require 4H trend to align (stricter, for trend following)
            min_alignment_score: Minimum alignment score to allow trade (for trend following)
            mr_extreme_threshold: For Mean Reversion - only block if trend strength exceeds this
        """
        self.require_1h_alignment = require_1h_alignment
        self.require_4h_alignment = require_4h_alignment
        self.min_alignment_score = min_alignment_score
        self.mr_extreme_threshold = mr_extreme_threshold
        
        # Stats tracking
        self.stats = {
            'signals_checked': 0,
            'signals_allowed': 0,
            'signals_blocked': 0,
            'blocked_by_1h': 0,
            'blocked_by_4h': 0,
            'blocked_extreme_trend': 0,  # MR blocked by extreme trend
            'perfect_alignment': 0
        }
        
        logger.info(f"📊 SmartMTFChecker initialized (1H: {require_1h_alignment}, 4H: {require_4h_alignment}, MR threshold: {mr_extreme_threshold})")
    
    def analyze(self, market_state: Dict, direction: str, strategy: str = None) -> MTFAnalysis:
        """
        Analyze multi-timeframe alignment for a potential trade.
        
        Args:
            market_state: Market state dict with timeframes data
            direction: 'long' or 'short'
            strategy: Strategy name (determines filtering logic)
            
        Returns:
            MTFAnalysis with decision and details
        """
        self.stats['signals_checked'] += 1
        direction = direction.lower()
        strategy_lower = (strategy or '').lower().replace(' ', '').replace('_', '')
        
        # Determine if this is a mean reversion strategy
        is_mean_reversion = any(mr in strategy_lower for mr in MEAN_REVERSION_STRATEGIES)
        
        # Extract trend data from each timeframe
        trend_15m, strength_15m = self._get_trend_with_strength(market_state, '15m')
        trend_1h, strength_1h = self._get_trend_with_strength(market_state, '1H')
        trend_4h, strength_4h = self._get_trend_with_strength(market_state, '4H')
        
        # Calculate alignment score
        alignment_score = self._calculate_alignment(direction, trend_15m, trend_1h, trend_4h)
        
        # Check if trade is allowed - DIFFERENT LOGIC FOR MEAN REVERSION
        allowed = True
        reason = "MTF check OK"
        
        if is_mean_reversion:
            # MEAN REVERSION LOGIC
            # Only block if we're going against an EXTREMELY strong trend
            # Mean reversion FADES moves, so opposing trend is expected!
            allowed, reason = self._check_mean_reversion(
                direction, trend_1h, strength_1h, trend_4h, strength_4h
            )
        else:
            # TREND FOLLOWING LOGIC (Momentum, Breakout, etc.)
            # Trade WITH the higher timeframe trend
            allowed, reason = self._check_trend_following(
                direction, trend_1h, trend_4h, alignment_score
            )
        
        # Track stats
        if allowed:
            self.stats['signals_allowed'] += 1
            if alignment_score >= 0.9:
                self.stats['perfect_alignment'] += 1
        else:
            self.stats['signals_blocked'] += 1
        
        # Calculate confidence based on alignment and strategy
        confidence = self._calculate_confidence(
            alignment_score, trend_15m, trend_1h, trend_4h, direction, is_mean_reversion
        )
        
        return MTFAnalysis(
            allowed=allowed,
            confidence=confidence,
            trend_1h=trend_1h,
            trend_4h=trend_4h,
            trend_15m=trend_15m,
            trend_strength_1h=strength_1h,
            alignment_score=alignment_score,
            reason=reason
        )
    
    def _check_mean_reversion(self, direction: str, trend_1h: str, strength_1h: float,
                               trend_4h: str, strength_4h: float) -> Tuple[bool, str]:
        """
        Mean Reversion MTF check - only block EXTREME trends (falling knife protection).
        
        MR is SUPPOSED to trade against the trend. Only block when:
        1. 1H trend is strong (>0.7) AND against our direction
        2. 4H trend is very strong (>0.8) AND against our direction
        """
        # Check if going against an EXTREMELY strong 1H trend
        is_against_1h = (
            (direction == 'long' and trend_1h == 'bearish') or
            (direction == 'short' and trend_1h == 'bullish')
        )
        
        if is_against_1h and strength_1h >= self.mr_extreme_threshold:
            self.stats['blocked_extreme_trend'] += 1
            return False, f"EXTREME 1H trend against MR trade (strength: {strength_1h:.2f}) - falling knife risk"
        
        # Check 4H for very extreme trends (higher threshold)
        is_against_4h = (
            (direction == 'long' and trend_4h == 'bearish') or
            (direction == 'short' and trend_4h == 'bullish')
        )
        
        if is_against_4h and strength_4h >= 0.8:
            self.stats['blocked_extreme_trend'] += 1
            return False, f"EXTREME 4H trend against MR trade (strength: {strength_4h:.2f}) - major falling knife"
        
        return True, "MR trade OK - trend not extreme"
    
    def _check_trend_following(self, direction: str, trend_1h: str, trend_4h: str,
                                alignment_score: float) -> Tuple[bool, str]:
        """
        Trend Following MTF check - trade WITH the higher timeframe trend.
        """
        # Check 1H alignment
        if self.require_1h_alignment:
            if direction == 'long' and trend_1h == 'bearish':
                self.stats['blocked_by_1h'] += 1
                return False, "1H trend is bearish - don't go long against higher TF"
            elif direction == 'short' and trend_1h == 'bullish':
                self.stats['blocked_by_1h'] += 1
                return False, "1H trend is bullish - don't go short against higher TF"
        
        # Check 4H alignment (stricter)
        if self.require_4h_alignment:
            if direction == 'long' and trend_4h == 'bearish':
                self.stats['blocked_by_4h'] += 1
                return False, "4H trend is bearish - major trend against trade"
            elif direction == 'short' and trend_4h == 'bullish':
                self.stats['blocked_by_4h'] += 1
                return False, "4H trend is bullish - major trend against trade"
        
        # Check minimum alignment score
        if alignment_score < self.min_alignment_score:
            return False, f"Alignment score too low: {alignment_score:.2f} < {self.min_alignment_score}"
        
        return True, "Trend following MTF OK"
    
    def _get_trend_with_strength(self, market_state: Dict, timeframe: str) -> Tuple[str, float]:
        """
        Extract trend direction AND strength from market state for a timeframe.
        
        Returns:
            Tuple of (trend_direction, trend_strength)
        """
        try:
            tf_data = market_state.get('timeframes', {}).get(timeframe, {})
            trend = tf_data.get('trend', {})
            
            direction = trend.get('trend_direction', 'neutral')
            strength = trend.get('trend_strength', 0)
            
            # Need minimum strength to be considered trending
            if strength < 0.2:
                return 'neutral', strength
            
            if direction in ['up', 'bullish', 'long']:
                return 'bullish', strength
            elif direction in ['down', 'bearish', 'short']:
                return 'bearish', strength
            else:
                return 'neutral', strength
                
        except Exception as e:
            logger.debug(f"Could not get {timeframe} trend: {e}")
            return 'neutral', 0.0
    
    def _get_trend(self, market_state: Dict, timeframe: str) -> str:
        """Extract trend direction from market state for a timeframe (legacy)."""
        trend, _ = self._get_trend_with_strength(market_state, timeframe)
        return trend
    
    def _calculate_alignment(self, direction: str, trend_15m: str, trend_1h: str, trend_4h: str) -> float:
        """
        Calculate how well the timeframes align with the trade direction.
        
        Returns:
            float: 0-1 alignment score
        """
        score = 0.0
        
        # Define what trends support each direction
        if direction == 'long':
            supporting = ['bullish', 'neutral']
            opposing = 'bearish'
        else:
            supporting = ['bearish', 'neutral']
            opposing = 'bullish'
        
        # Weight: 4H = 40%, 1H = 35%, 15m = 25%
        if trend_4h in supporting:
            score += 0.40
            if trend_4h != 'neutral':  # Extra for aligned (not just neutral)
                score += 0.10
        
        if trend_1h in supporting:
            score += 0.35
            if trend_1h != 'neutral':
                score += 0.08
        
        if trend_15m in supporting:
            score += 0.25
            if trend_15m != 'neutral':
                score += 0.05
        
        # Penalty for opposing trends
        if trend_4h == opposing:
            score -= 0.20
        if trend_1h == opposing:
            score -= 0.15
        
        return max(0.0, min(1.0, score))
    
    def _calculate_confidence(self, alignment_score: float, 
                             trend_15m: str, trend_1h: str, trend_4h: str,
                             direction: str, is_mean_reversion: bool = False) -> float:
        """Calculate confidence multiplier based on MTF analysis."""
        
        if is_mean_reversion:
            # For Mean Reversion: Higher confidence when trends are NOT aligned
            # (because MR fades moves - counter-trend is expected)
            
            # Base confidence - start high for MR
            confidence = 0.7
            
            # BONUS when going against weak/neutral trends (ideal for MR)
            if trend_1h == 'neutral':
                confidence += 0.15  # Ranging market - perfect for MR
            if trend_4h == 'neutral':
                confidence += 0.10
            
            # Slight penalty for very strong opposing trends (even if allowed)
            # This adjusts position size without blocking
            trends = [trend_15m, trend_1h, trend_4h]
            opposing = 'bearish' if direction == 'long' else 'bullish'
            strong_opposing = sum(1 for t in trends if t == opposing)
            
            if strong_opposing >= 2:
                confidence *= 0.85  # Reduce size slightly
            
            return min(1.0, confidence)
        else:
            # For Trend Following: Use alignment score
            confidence = alignment_score
            
            # Perfect alignment bonus
            if direction == 'long':
                if trend_15m == 'bullish' and trend_1h == 'bullish' and trend_4h == 'bullish':
                    confidence = min(1.0, confidence + 0.15)
            else:
                if trend_15m == 'bearish' and trend_1h == 'bearish' and trend_4h == 'bearish':
                    confidence = min(1.0, confidence + 0.15)
            
            # Conflicting timeframes penalty
            trends = [trend_15m, trend_1h, trend_4h]
            if 'bullish' in trends and 'bearish' in trends:
                confidence *= 0.8  # 20% penalty for conflict
            
            return confidence
    
    def get_stats(self) -> Dict:
        """Get MTF checker statistics."""
        total = self.stats['signals_checked']
        return {
            **self.stats,
            'block_rate': self.stats['signals_blocked'] / total if total > 0 else 0,
            'perfect_rate': self.stats['perfect_alignment'] / self.stats['signals_allowed'] if self.stats['signals_allowed'] > 0 else 0
        }


# Convenience function for backtest integration
def create_mtf_checker(
    require_1h: bool = True,
    require_4h: bool = False,
    min_alignment: float = 0.3,
    mr_extreme_threshold: float = 0.7
) -> SmartMTFChecker:
    """Create a configured MTF checker for backtesting."""
    return SmartMTFChecker(
        require_1h_alignment=require_1h,
        require_4h_alignment=require_4h,
        min_alignment_score=min_alignment,
        mr_extreme_threshold=mr_extreme_threshold
    )
