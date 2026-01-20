"""
Smart Multi-Timeframe Intelligence for Backtesting

This module checks higher timeframes to confirm signals before entry.
Key principle: Trade in the direction of the higher timeframe trend.

Features:
1. 1H trend alignment check
2. 4H trend alignment check
3. Multi-timeframe momentum confirmation
4. Trend strength scoring across timeframes

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
    alignment_score: float  # 0-1, how aligned are the timeframes
    reason: str


class SmartMTFChecker:
    """
    Multi-Timeframe Intelligence for smarter trade filtering.
    
    Rules:
    - For LONG trades: Higher timeframes should be bullish or neutral (not bearish)
    - For SHORT trades: Higher timeframes should be bearish or neutral (not bullish)
    - Bonus confidence when all timeframes align
    - Reduce confidence when timeframes conflict
    """
    
    def __init__(self, 
                 require_1h_alignment: bool = True,
                 require_4h_alignment: bool = False,
                 min_alignment_score: float = 0.3):
        """
        Initialize MTF checker.
        
        Args:
            require_1h_alignment: Require 1H trend to align with trade direction
            require_4h_alignment: Require 4H trend to align (stricter)
            min_alignment_score: Minimum alignment score to allow trade (0-1)
        """
        self.require_1h_alignment = require_1h_alignment
        self.require_4h_alignment = require_4h_alignment
        self.min_alignment_score = min_alignment_score
        
        # Stats tracking
        self.stats = {
            'signals_checked': 0,
            'signals_allowed': 0,
            'signals_blocked': 0,
            'blocked_by_1h': 0,
            'blocked_by_4h': 0,
            'perfect_alignment': 0
        }
        
        logger.info(f"📊 SmartMTFChecker initialized (1H: {require_1h_alignment}, 4H: {require_4h_alignment})")
    
    def analyze(self, market_state: Dict, direction: str) -> MTFAnalysis:
        """
        Analyze multi-timeframe alignment for a potential trade.
        
        Args:
            market_state: Market state dict with timeframes data
            direction: 'long' or 'short'
            
        Returns:
            MTFAnalysis with decision and details
        """
        self.stats['signals_checked'] += 1
        direction = direction.lower()
        
        # Extract trend data from each timeframe
        trend_15m = self._get_trend(market_state, '15m')
        trend_1h = self._get_trend(market_state, '1H')
        trend_4h = self._get_trend(market_state, '4H')
        
        # Calculate alignment score
        alignment_score = self._calculate_alignment(direction, trend_15m, trend_1h, trend_4h)
        
        # Check if trade is allowed
        allowed = True
        reason = "MTF alignment OK"
        
        # Check 1H alignment
        if self.require_1h_alignment:
            if direction == 'long' and trend_1h == 'bearish':
                allowed = False
                reason = "1H trend is bearish - don't go long against higher TF"
                self.stats['blocked_by_1h'] += 1
            elif direction == 'short' and trend_1h == 'bullish':
                allowed = False
                reason = "1H trend is bullish - don't go short against higher TF"
                self.stats['blocked_by_1h'] += 1
        
        # Check 4H alignment (stricter)
        if self.require_4h_alignment and allowed:
            if direction == 'long' and trend_4h == 'bearish':
                allowed = False
                reason = "4H trend is bearish - major trend against trade"
                self.stats['blocked_by_4h'] += 1
            elif direction == 'short' and trend_4h == 'bullish':
                allowed = False
                reason = "4H trend is bullish - major trend against trade"
                self.stats['blocked_by_4h'] += 1
        
        # Check minimum alignment score
        if allowed and alignment_score < self.min_alignment_score:
            allowed = False
            reason = f"Alignment score too low: {alignment_score:.2f} < {self.min_alignment_score}"
        
        # Track stats
        if allowed:
            self.stats['signals_allowed'] += 1
            if alignment_score >= 0.9:
                self.stats['perfect_alignment'] += 1
        else:
            self.stats['signals_blocked'] += 1
        
        # Calculate confidence based on alignment
        confidence = self._calculate_confidence(alignment_score, trend_15m, trend_1h, trend_4h, direction)
        
        return MTFAnalysis(
            allowed=allowed,
            confidence=confidence,
            trend_1h=trend_1h,
            trend_4h=trend_4h,
            trend_15m=trend_15m,
            alignment_score=alignment_score,
            reason=reason
        )
    
    def _get_trend(self, market_state: Dict, timeframe: str) -> str:
        """Extract trend direction from market state for a timeframe."""
        try:
            tf_data = market_state.get('timeframes', {}).get(timeframe, {})
            trend = tf_data.get('trend', {})
            
            direction = trend.get('trend_direction', 'neutral')
            strength = trend.get('trend_strength', 0)
            
            # Need minimum strength to be considered trending
            if strength < 0.2:
                return 'neutral'
            
            if direction in ['up', 'bullish', 'long']:
                return 'bullish'
            elif direction in ['down', 'bearish', 'short']:
                return 'bearish'
            else:
                return 'neutral'
                
        except Exception as e:
            logger.debug(f"Could not get {timeframe} trend: {e}")
            return 'neutral'
    
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
                             direction: str) -> float:
        """Calculate confidence multiplier based on MTF analysis."""
        
        # Base confidence from alignment
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
    min_alignment: float = 0.3
) -> SmartMTFChecker:
    """Create a configured MTF checker for backtesting."""
    return SmartMTFChecker(
        require_1h_alignment=require_1h,
        require_4h_alignment=require_4h,
        min_alignment_score=min_alignment
    )
