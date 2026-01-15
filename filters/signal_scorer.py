"""
Signal Scorer
Scoring system for trading signals (0-100 points)
Replaces binary filters with nuanced scoring

⚠️ TUNED FOR 60%+ WIN RATE - DO NOT WEAKEN THRESHOLDS
"""

from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class SignalScorer:
    """
    Scores trading signals based on multiple quality factors
    Returns score (0-100) and breakdown of points
    
    Scoring breakdown:
    - Volume: 0-25 pts (2.5x+ for full points)
    - Trend: 0-25 pts (strong alignment required)
    - RSI: 0-25 pts (sweet spot required)
    - Volatility: 0-25 pts (ideal ATR range)
    - Bonus: +15 pts for multi-factor confirmation
    - Penalty: -10 pts for counter-trend
    
    Target: 55+ score for trade entry
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
        confirmations = 0  # Track number of strong confirmations
        
        signal_direction = signal.get('direction', '').lower()
        
        # =====================================
        # VOLUME SCORING (0-25 pts)
        # =====================================
        volume = market_data.get('volume', 0)
        avg_volume_20 = market_data.get('avg_volume_20', 0)
        if avg_volume_20 > 0:
            vol_ratio = volume / avg_volume_20
            if vol_ratio > 3.0:  # VERY strong volume
                score += 25
                breakdown['volume'] = 25
                confirmations += 1
            elif vol_ratio > 2.5:
                score += 20
                breakdown['volume'] = 20
                confirmations += 1
            elif vol_ratio > 2.0:
                score += 15
                breakdown['volume'] = 15
            elif vol_ratio > 1.5:
                score += 8
                breakdown['volume'] = 8
            elif vol_ratio > 1.2:
                score += 4
                breakdown['volume'] = 4
            else:
                breakdown['volume'] = 0
        else:
            breakdown['volume'] = 0
        
        # =====================================
        # TREND ALIGNMENT (0-25 pts)
        # =====================================
        trend = market_data.get('trend', '').lower()
        trend_strength = market_data.get('trend_strength', 0)
        
        # Check if signal aligns with trend
        trend_aligned = False
        trend_opposed = False
        
        if trend == 'up' and signal_direction == 'long':
            trend_aligned = True
        elif trend == 'down' and signal_direction == 'short':
            trend_aligned = True
        elif trend == 'up' and signal_direction == 'short':
            trend_opposed = True
        elif trend == 'down' and signal_direction == 'long':
            trend_opposed = True
        
        if trend_aligned:
            if trend_strength > 0.6:  # STRONG trend alignment
                score += 25
                breakdown['trend'] = 25
                confirmations += 1
            elif trend_strength > 0.4:
                score += 20
                breakdown['trend'] = 20
                confirmations += 1
            elif trend_strength > 0.2:
                score += 12
                breakdown['trend'] = 12
            else:
                score += 8
                breakdown['trend'] = 8
        elif trend_opposed:
            # ⚠️ PENALTY for counter-trend trading
            score -= 10
            breakdown['trend'] = -10
            breakdown['counter_trend_penalty'] = True
        elif trend == 'neutral' or trend == 'sideways' or trend == '':
            score += 5  # Small credit for neutral
            breakdown['trend'] = 5
        else:
            breakdown['trend'] = 0
        
        # =====================================
        # RSI CONFIRMATION (0-25 pts)
        # =====================================
        rsi = market_data.get('rsi_14', 50)
        
        # CRITICAL: Extreme RSI = danger zone
        if rsi > 75 or rsi < 25:
            breakdown['rsi'] = 0
            breakdown['rsi_extreme'] = True
        elif rsi > 70 or rsi < 30:
            breakdown['rsi'] = 3  # Very small credit
        elif signal_direction == 'long':
            if 45 < rsi < 60:  # IDEAL for longs
                score += 25
                breakdown['rsi'] = 25
                confirmations += 1
            elif 40 < rsi < 65:
                score += 18
                breakdown['rsi'] = 18
            elif 35 < rsi < 70:
                score += 10
                breakdown['rsi'] = 10
            else:
                breakdown['rsi'] = 0
        elif signal_direction == 'short':
            if 40 < rsi < 55:  # IDEAL for shorts
                score += 25
                breakdown['rsi'] = 25
                confirmations += 1
            elif 35 < rsi < 60:
                score += 18
                breakdown['rsi'] = 18
            elif 30 < rsi < 65:
                score += 10
                breakdown['rsi'] = 10
            else:
                breakdown['rsi'] = 0
        else:
            breakdown['rsi'] = 0
        
        # =====================================
        # VOLATILITY (0-25 pts)
        # =====================================
        atr = market_data.get('atr', 0)
        current_price = market_data.get('current_price', 0)
        if current_price > 0 and atr > 0:
            atr_pct = (atr / current_price) * 100
            if 0.8 < atr_pct < 1.8:  # IDEAL volatility
                score += 25
                breakdown['volatility'] = 25
                confirmations += 1
            elif 0.5 < atr_pct < 2.2:
                score += 18
                breakdown['volatility'] = 18
            elif 0.3 < atr_pct < 3.0:
                score += 10
                breakdown['volatility'] = 10
            elif 0.2 < atr_pct < 4.0:
                score += 5
                breakdown['volatility'] = 5
            else:
                breakdown['volatility'] = 0
        else:
            breakdown['volatility'] = 0
        
        # =====================================
        # MULTI-FACTOR BONUS (+15 pts)
        # =====================================
        # If 3+ factors are strong confirmations, add bonus
        breakdown['confirmations'] = confirmations
        if confirmations >= 3:
            score += 15
            breakdown['multi_factor_bonus'] = 15
        elif confirmations >= 2:
            score += 8
            breakdown['multi_factor_bonus'] = 8
        else:
            breakdown['multi_factor_bonus'] = 0
        
        # =====================================
        # FINAL SCORE
        # =====================================
        # Clamp to 0-100 range
        score = max(0, min(100, score))
        breakdown['final_score'] = score
        
        # Log score breakdown
        logger.info(f"📊 Signal Score: {score}/100 "
                   f"(vol:{breakdown.get('volume', 0)}, "
                   f"trend:{breakdown.get('trend', 0)}, "
                   f"rsi:{breakdown.get('rsi', 0)}, "
                   f"volatility:{breakdown.get('volatility', 0)}, "
                   f"bonus:{breakdown.get('multi_factor_bonus', 0)}) "
                   f"[{confirmations} confirmations]")
        
        return score, breakdown
