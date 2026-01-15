"""
Signal Scorer
Simple scoring function to evaluate signal quality (0-100)
"""

from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


def score_signal(market_data: Dict, signal: Dict) -> Tuple[int, Dict]:
    """
    Score a trading signal based on market conditions
    
    Args:
        market_data: Dict with 'volume', 'avg_volume_20', 'trend', 'rsi_14'
        signal: Dict with 'direction' ('long' or 'short')
    
    Returns:
        (score: int, breakdown: Dict) - Score from 0-100 and breakdown of points
    """
    score = 0
    breakdown = {}
    
    # Volume (more lenient)
    volume = market_data.get('volume', 0)
    avg_volume_20 = market_data.get('avg_volume_20', 0)
    if avg_volume_20 > 0:
        vol_ratio = volume / avg_volume_20
        if vol_ratio > 1.5:
            score += 30
            breakdown['volume'] = 30
        elif vol_ratio > 1.2:
            score += 15  # Partial credit
            breakdown['volume'] = 15
        else:
            breakdown['volume'] = 0
    else:
        breakdown['volume'] = 0
    
    # Trend (more lenient)
    trend = market_data.get('trend', '')
    signal_direction = signal.get('direction', '').lower()
    if trend == signal_direction:
        score += 40
        breakdown['trend'] = 40
    else:
        score += 10  # Give some credit for breakout
        breakdown['trend'] = 10
    
    # RSI (more lenient - give credit if NOT overbought)
    rsi = market_data.get('rsi_14', 50)
    if 25 < rsi < 75:  # Wider range
        score += 30
        breakdown['rsi'] = 30
    elif 20 < rsi < 80:
        score += 15  # Partial credit
        breakdown['rsi'] = 15
    else:
        breakdown['rsi'] = 0
    
    logger.info(f"Signal score: {score} (breakdown: {breakdown})")
    
    return score, breakdown
