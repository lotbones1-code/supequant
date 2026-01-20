"""
Funding Rate Filter (Phase 2.4 Elite)

Contrarian funding rate filter that uses market positioning to find edge:
- High positive funding = Crowded longs = SHORT opportunity
- High negative funding = Crowded shorts = LONG opportunity

This is CONTRARIAN logic - trade against the crowd at extremes.

Features:
- Multi-level thresholds (moderate vs extreme)
- Score adjustments (not binary pass/fail)
- Funding history tracking for trend detection
- Squeeze risk assessment (sustained extreme = squeeze incoming)
- Time-to-funding awareness (squeeze more likely near payment)
- Dashboard-ready status reporting
"""

from typing import Dict, Tuple, Optional, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class FundingRateFilter:
    """
    Contrarian funding rate filter (Phase 2.4 Elite).
    
    Uses funding rate as a sentiment/positioning indicator:
    - High positive funding = Longs paying shorts = Crowded longs = SHORT opportunity
    - High negative funding = Shorts paying longs = Crowded shorts = LONG opportunity
    
    This is institutional-grade CONTRARIAN logic - trade against extremes.
    """
    
    def __init__(self):
        self.name = "FundingRate"
        self.last_funding_rate = None
        self.last_score_adjustment = 0
        self.last_analysis = None
        
        # Historical funding for trend detection
        self.funding_history: List[float] = []
        self.max_history = 10  # Track last 10 funding readings
    
    def _get_funding_rate(self, market_state: Dict) -> Optional[float]:
        """
        Safely extract funding rate from market state.
        
        The funding rate is nested in market_state:
        market_state['funding_rate'] = {
            'funding_rate': 0.00085,  # <-- The actual value
            'funding_time': datetime,
            'next_funding_time': datetime
        }
        
        Returns:
            Funding rate as float, or None if unavailable
        """
        funding_data = market_state.get('funding_rate')
        if not funding_data:
            return None
        
        # Handle both dict and direct value
        if isinstance(funding_data, dict):
            return funding_data.get('funding_rate', 0)
        return float(funding_data) if funding_data else None
    
    def _get_time_to_funding(self, market_state: Dict) -> Optional[float]:
        """
        Get hours until next funding payment.
        
        Funding is paid every 8 hours on most exchanges.
        Squeeze probability increases as funding time approaches.
        
        Returns:
            Hours until next funding, or None if unavailable
        """
        funding_data = market_state.get('funding_rate')
        if not funding_data or not isinstance(funding_data, dict):
            return None
        
        next_funding = funding_data.get('next_funding_time')
        if not next_funding:
            return None
        
        try:
            now = datetime.now(timezone.utc)
            if isinstance(next_funding, datetime):
                delta = (next_funding - now).total_seconds() / 3600
            else:
                # Assume timestamp in milliseconds
                next_ts = next_funding / 1000 if next_funding > 1e12 else next_funding
                delta = (next_ts - now.timestamp()) / 3600
            
            return max(0, delta)
        except Exception:
            return None
    
    def analyze_funding(self, market_state: Dict) -> Dict:
        """
        Comprehensive funding rate analysis.
        
        Determines:
        - Current funding level (extreme/moderate/neutral)
        - Crowd positioning (long/short/balanced)
        - Contrarian bias (bullish/bearish/neutral)
        - Squeeze risk (based on sustained extreme readings)
        - Score adjustments for each direction
        
        Returns:
            Dict with full analysis
        """
        import config
        
        result = {
            'funding_rate': 0,
            'funding_pct': 0,
            'level': 'neutral',
            'crowd_position': 'balanced',
            'contrarian_bias': 'neutral',
            'hours_to_funding': None,
            'squeeze_risk': 'low',
            'score_adjustment_long': 0,
            'score_adjustment_short': 0
        }
        
        funding_rate = self._get_funding_rate(market_state)
        if funding_rate is None:
            return result
        
        result['funding_rate'] = funding_rate
        result['funding_pct'] = funding_rate * 100
        self.last_funding_rate = funding_rate
        
        # Update history for trend detection
        self.funding_history.append(funding_rate)
        if len(self.funding_history) > self.max_history:
            self.funding_history.pop(0)
        
        # Get thresholds from config
        EXTREME_THRESHOLD = getattr(config, 'FUNDING_RATE_EXTREME_THRESHOLD', 0.001)  # 0.1%
        MODERATE_THRESHOLD = getattr(config, 'FUNDING_RATE_MODERATE_THRESHOLD', 0.0005)  # 0.05%
        
        # Get score adjustments from config
        EXTREME_PENALTY = getattr(config, 'FUNDING_RATE_EXTREME_PENALTY', 20)
        EXTREME_BOOST = getattr(config, 'FUNDING_RATE_EXTREME_BOOST', 15)
        MODERATE_PENALTY = getattr(config, 'FUNDING_RATE_MODERATE_PENALTY', 10)
        MODERATE_BOOST = getattr(config, 'FUNDING_RATE_MODERATE_BOOST', 7)
        
        # === Determine level and score adjustments ===
        
        # EXTREME POSITIVE: Crowded longs, favor shorts
        if funding_rate > EXTREME_THRESHOLD:
            result['level'] = 'extreme_positive'
            result['crowd_position'] = 'long'
            result['contrarian_bias'] = 'bearish'
            result['score_adjustment_long'] = -EXTREME_PENALTY  # Don't join crowded longs
            result['score_adjustment_short'] = EXTREME_BOOST    # Contrarian SHORT opportunity
        
        # MODERATE POSITIVE: Somewhat crowded longs
        elif funding_rate > MODERATE_THRESHOLD:
            result['level'] = 'moderate_positive'
            result['crowd_position'] = 'long'
            result['contrarian_bias'] = 'bearish'
            result['score_adjustment_long'] = -MODERATE_PENALTY
            result['score_adjustment_short'] = MODERATE_BOOST
        
        # EXTREME NEGATIVE: Crowded shorts, favor longs
        elif funding_rate < -EXTREME_THRESHOLD:
            result['level'] = 'extreme_negative'
            result['crowd_position'] = 'short'
            result['contrarian_bias'] = 'bullish'
            result['score_adjustment_long'] = EXTREME_BOOST     # Contrarian LONG opportunity
            result['score_adjustment_short'] = -EXTREME_PENALTY # Don't join crowded shorts
        
        # MODERATE NEGATIVE: Somewhat crowded shorts
        elif funding_rate < -MODERATE_THRESHOLD:
            result['level'] = 'moderate_negative'
            result['crowd_position'] = 'short'
            result['contrarian_bias'] = 'bullish'
            result['score_adjustment_long'] = MODERATE_BOOST
            result['score_adjustment_short'] = -MODERATE_PENALTY
        
        # NEUTRAL: Balanced positioning
        else:
            result['level'] = 'neutral'
            result['crowd_position'] = 'balanced'
            result['contrarian_bias'] = 'neutral'
        
        # === Time to next funding ===
        hours_to_funding = self._get_time_to_funding(market_state)
        result['hours_to_funding'] = hours_to_funding
        
        # === Squeeze risk assessment ===
        # Sustained extreme funding = squeeze incoming
        if len(self.funding_history) >= 3:
            recent = self.funding_history[-3:]
            squeeze_threshold = EXTREME_THRESHOLD * 0.8  # 80% of extreme
            
            # All recent readings extreme positive = long squeeze risk
            if all(f > squeeze_threshold for f in recent):
                if hours_to_funding is not None and hours_to_funding < 2:
                    result['squeeze_risk'] = 'high'  # Squeeze likely imminent
                else:
                    result['squeeze_risk'] = 'medium'
            
            # All recent readings extreme negative = short squeeze risk
            elif all(f < -squeeze_threshold for f in recent):
                if hours_to_funding is not None and hours_to_funding < 2:
                    result['squeeze_risk'] = 'high'
                else:
                    result['squeeze_risk'] = 'medium'
        
        # If squeeze risk is high, boost contrarian signal even more
        if result['squeeze_risk'] == 'high':
            if result['contrarian_bias'] == 'bearish':
                result['score_adjustment_short'] += 5  # Extra boost for shorts
            elif result['contrarian_bias'] == 'bullish':
                result['score_adjustment_long'] += 5  # Extra boost for longs
        
        return result
    
    def check(self, market_state: Dict = None, signal_direction: str = '') -> Tuple[bool, str]:
        """
        Check if funding rate conditions favor the signal direction.
        
        Contrarian logic:
        - High positive funding → Favor shorts, penalize longs
        - High negative funding → Favor longs, penalize shorts
        
        This filter uses score adjustments, not hard rejections.
        It's more nuanced than binary pass/fail.
        
        Args:
            market_state: Market state containing funding_rate
            signal_direction: 'long' or 'short'
            
        Returns:
            (passed: bool, reason: str)
        """
        import config
        
        # Check if filter is enabled
        if not getattr(config, 'FUNDING_RATE_FILTER_ENABLED', True):
            return True, "Funding rate filter disabled"
        
        if not market_state:
            return True, "No market state provided"
        
        # Analyze funding
        analysis = self.analyze_funding(market_state)
        self.last_analysis = analysis
        
        funding_rate = analysis['funding_rate']
        level = analysis['level']
        direction = signal_direction.lower() if signal_direction else ''
        
        # Get score adjustment for this direction
        if direction == 'long':
            score_adj = analysis['score_adjustment_long']
        elif direction == 'short':
            score_adj = analysis['score_adjustment_short']
        else:
            score_adj = 0
        
        self.last_score_adjustment = score_adj
        
        # Format funding for display (as percentage)
        funding_pct = funding_rate * 100
        funding_str = f"{funding_pct:+.4f}%"
        
        # Build reason string
        squeeze_info = ""
        if analysis['squeeze_risk'] != 'low':
            squeeze_info = f" | Squeeze: {analysis['squeeze_risk'].upper()}"
        
        time_info = ""
        if analysis['hours_to_funding'] is not None:
            time_info = f" | Next funding: {analysis['hours_to_funding']:.1f}h"
        
        # Neutral funding - simple response
        if level == 'neutral':
            reason = f"Funding neutral ({funding_str})"
            logger.info(f"ℹ️  {self.name}: {reason}")
            return True, reason
        
        # Non-neutral funding - detailed response
        crowd = analysis['crowd_position']
        bias = analysis['contrarian_bias']
        
        reason = f"Funding {funding_str} | Crowd: {crowd} | Bias: {bias} | Score: {score_adj:+d}{squeeze_info}{time_info}"
        
        # Log based on whether signal aligns with contrarian bias
        if (direction == 'long' and bias == 'bullish') or (direction == 'short' and bias == 'bearish'):
            logger.info(f"🎯 {self.name}: {reason} - CONTRARIAN OPPORTUNITY!")
        elif score_adj <= -15:
            logger.warning(f"⚠️  {self.name}: {reason} - Trading WITH the crowd")
        elif score_adj < 0:
            logger.info(f"📊 {self.name}: {reason}")
        else:
            logger.info(f"✅ {self.name}: {reason}")
        
        # Never hard reject - use score adjustments for flexibility
        return True, reason
    
    def get_funding_status(self) -> Dict:
        """
        Get current funding status for dashboard display.
        
        Returns:
            Dict with status, funding info, and recommendations
        """
        if not self.last_analysis:
            return {
                'status': 'UNKNOWN',
                'emoji': '❓',
                'funding_rate': 0,
                'funding_pct': '0.0000%',
                'crowd': 'unknown',
                'bias': 'neutral',
                'hours_to_funding': None,
                'squeeze_risk': 'low',
                'score_long': 0,
                'score_short': 0,
                'message': 'No funding data yet'
            }
        
        a = self.last_analysis
        funding_pct = a['funding_rate'] * 100
        
        # Emoji based on level
        level_emoji = {
            'extreme_positive': '🔴',    # Crowded longs, bearish
            'moderate_positive': '🟠',   # Somewhat crowded longs
            'neutral': '⚪',             # Balanced
            'moderate_negative': '🟡',   # Somewhat crowded shorts
            'extreme_negative': '🟢'     # Crowded shorts, bullish
        }
        
        emoji = level_emoji.get(a['level'], '❓')
        
        # Status display
        status_map = {
            'extreme_positive': 'CROWDED LONGS',
            'moderate_positive': 'LONGS HEAVY',
            'neutral': 'BALANCED',
            'moderate_negative': 'SHORTS HEAVY',
            'extreme_negative': 'CROWDED SHORTS'
        }
        
        status = status_map.get(a['level'], 'UNKNOWN')
        
        # Build message
        bias_arrow = '↓' if a['contrarian_bias'] == 'bearish' else ('↑' if a['contrarian_bias'] == 'bullish' else '→')
        
        return {
            'status': status,
            'emoji': emoji,
            'funding_rate': a['funding_rate'],
            'funding_pct': f"{funding_pct:+.4f}%",
            'level': a['level'],
            'crowd': a['crowd_position'],
            'bias': a['contrarian_bias'],
            'bias_arrow': bias_arrow,
            'hours_to_funding': a['hours_to_funding'],
            'squeeze_risk': a['squeeze_risk'],
            'score_long': a['score_adjustment_long'],
            'score_short': a['score_adjustment_short'],
            'history_count': len(self.funding_history),
            'message': f"{emoji} {status} ({funding_pct:+.3f}%) {bias_arrow}"
        }
    
    def get_contrarian_recommendation(self) -> str:
        """
        Get a simple contrarian recommendation based on current funding.
        
        Returns:
            'FAVOR_SHORTS' | 'FAVOR_LONGS' | 'NEUTRAL'
        """
        if not self.last_analysis:
            return 'NEUTRAL'
        
        bias = self.last_analysis['contrarian_bias']
        if bias == 'bearish':
            return 'FAVOR_SHORTS'
        elif bias == 'bullish':
            return 'FAVOR_LONGS'
        return 'NEUTRAL'


# Module-level convenience function
def get_funding_bias(market_state: Dict) -> str:
    """
    Quick check for contrarian funding bias.
    
    Returns:
        'bullish' | 'bearish' | 'neutral'
    """
    filter_instance = FundingRateFilter()
    analysis = filter_instance.analyze_funding(market_state)
    return analysis['contrarian_bias']
