"""
Signal Scorer
Scoring system for trading signals (0-100 points)
Replaces binary filters with nuanced scoring
"""

from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class SignalScorer:
    """
    Scores trading signals based on multiple quality factors
    Returns score (0-100) and breakdown of points
    """

    def score_signal(self, market_data: Dict, signal: Dict) -> Tuple[int, Dict]:
        """
        Score a trading signal based on market conditions
        
        Args:
            market_data: Dict with market data (volume, trend, rsi, atr, etc.)
            signal: Dict with signal info (direction, etc.)
        
        Returns:
            (score: int, breakdown: Dict) - Score from 0-100 and breakdown of points
        """
        score = 0
        breakdown = {}
        
        # Volume (0-25 pts) - STRICTER: require 2.5x for full points
        volume = market_data.get('volume', 0)
        avg_volume_20 = market_data.get('avg_volume_20', 0)
        if avg_volume_20 > 0:
            vol_ratio = volume / avg_volume_20
            if vol_ratio > 2.5:  # RAISED from 2.0
                score += 25
                breakdown['volume'] = 25
            elif vol_ratio > 2.0:
                score += 15
                breakdown['volume'] = 15
            elif vol_ratio > 1.5:
                score += 8
                breakdown['volume'] = 8
            else:
                breakdown['volume'] = 0
        else:
            breakdown['volume'] = 0
        
        # Trend alignment (0-25 pts) - STRICTER: only give 25 for STRONG alignment
        trend = market_data.get('trend', '').lower()
        trend_strength = market_data.get('trend_strength', 0)  # Get trend strength if available
        signal_direction = signal.get('direction', '').lower()
        
        # Map trend directions: 'up' -> 'long', 'down' -> 'short'
        # Only give full 25 points if STRONG trend alignment (strength > 0.5)
        if trend == 'up' and signal_direction == 'long':
            if trend_strength > 0.5:  # STRONG trend
                score += 25
                breakdown['trend'] = 25
            else:
                score += 15  # Weak trend alignment
                breakdown['trend'] = 15
        elif trend == 'down' and signal_direction == 'short':
            if trend_strength > 0.5:  # STRONG trend
                score += 25
                breakdown['trend'] = 25
            else:
                score += 15  # Weak trend alignment
                breakdown['trend'] = 15
        elif trend == 'neutral' or trend == 'sideways' or trend == '':
            score += 8  # REDUCED from 12
            breakdown['trend'] = 8
        else:
            # Trend opposes signal - no credit
            breakdown['trend'] = 0
        
        # RSI confirmation (0-25 pts) - STRICTER: 0 points if overbought/oversold
        rsi = market_data.get('rsi_14', 50)
        
        # CRITICAL: If RSI is extreme (overbought/oversold), give 0 points (reversal risk)
        if rsi > 70 or rsi < 30:
            breakdown['rsi'] = 0
        elif signal_direction == 'long':
            if 40 < rsi < 65:
                score += 25
                breakdown['rsi'] = 25
            elif 35 < rsi < 70:
                score += 15
                breakdown['rsi'] = 15
            elif 30 < rsi < 75:
                score += 8
                breakdown['rsi'] = 8
            else:
                breakdown['rsi'] = 0
        elif signal_direction == 'short':
            if 35 < rsi < 60:
                score += 25
                breakdown['rsi'] = 25
            elif 30 < rsi < 65:
                score += 15
                breakdown['rsi'] = 15
            elif 25 < rsi < 70:
                score += 8
                breakdown['rsi'] = 8
            else:
                breakdown['rsi'] = 0
        else:
            breakdown['rsi'] = 0
        
        # Volatility (0-25 pts) - ATR as percentage of price
        atr = market_data.get('atr', 0)
        current_price = market_data.get('current_price', 0)
        if current_price > 0 and atr > 0:
            atr_pct = (atr / current_price) * 100
            if 0.5 < atr_pct < 2.0:
                score += 25
                breakdown['volatility'] = 25
            elif 0.3 < atr_pct < 3.0:
                score += 15
                breakdown['volatility'] = 15
            elif 0.2 < atr_pct < 4.0:
                score += 8
                breakdown['volatility'] = 8
            else:
                breakdown['volatility'] = 0
        else:
            breakdown['volatility'] = 0
        
        # Log score breakdown
        logger.info(f"📊 Signal Score: {score}/100 (volume: {breakdown.get('volume', 0)}, "
                   f"trend: {breakdown.get('trend', 0)}, rsi: {breakdown.get('rsi', 0)}, "
                   f"volatility: {breakdown.get('volatility', 0)})")
        
        return score, breakdown
