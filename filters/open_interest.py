"""
Open Interest Analysis Filter (Phase 3.4 Elite - Boost Heavy)

Uses Open Interest data to detect market positioning and divergences.
Configured with BOOST-HEAVY settings to help signals pass threshold.

Key Concepts:
- OI = Total open positions (long + short)
- Rising OI = New positions entering
- Falling OI = Positions closing
- Divergence = Price and OI moving opposite directions

Divergence Types:
- Price↑ + OI↑ = Bullish confirmation (new longs entering)
- Price↑ + OI↓ = Bearish divergence (shorts covering, weak rally)
- Price↓ + OI↓ = Bullish divergence (longs capitulating, reversal)
- Price↓ + OI↑ = Bearish confirmation (new shorts entering)

Boost-Heavy: Tilted toward helping signals pass, not blocking.
"""

from typing import Dict, Tuple, Optional, List
from datetime import datetime, timezone, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


class OpenInterestFilter:
    """
    Elite Open Interest analysis filter (Boost-Heavy version).
    
    Features:
    - OI divergence detection (price vs OI movement)
    - OI percentile tracking (crowded vs uncrowded)
    - Combines with funding rate for double confirmation
    - Builds internal OI history for percentile calculation
    
    Boost-Heavy: More likely to help signals pass than block them.
    """
    
    def __init__(self):
        self.name = "OpenInterest"
        self.last_score_adjustment = 0
        
        # Internal OI history for percentile calculation
        # We track OI values over time since API only gives current snapshot
        self.oi_history: deque = deque(maxlen=200)  # ~3 hours on 1-min cycles
        self.last_oi_update: Optional[datetime] = None
        self.min_history_for_percentile = 20  # Need at least 20 samples
        
        # Last analysis for dashboard
        self.last_analysis: Optional[Dict] = None
        
        logger.info(f"✅ {self.name}: Initialized (Boost-Heavy settings)")
    
    def _update_oi_history(self, current_oi: float) -> None:
        """
        Track OI values over time to build our own history.
        
        Args:
            current_oi: Current open interest value
        """
        now = datetime.now(timezone.utc)
        
        # Only update every 60 seconds to avoid duplicate entries
        if self.last_oi_update:
            time_since_last = (now - self.last_oi_update).total_seconds()
            if time_since_last < 60:
                return
        
        if current_oi > 0:
            self.oi_history.append({
                'timestamp': now,
                'oi': current_oi
            })
            self.last_oi_update = now
    
    def _calculate_oi_percentile(self, current_oi: float) -> Optional[float]:
        """
        Calculate where current OI ranks vs recent history.
        
        Args:
            current_oi: Current open interest
            
        Returns:
            Percentile (0-100) or None if not enough history
        """
        if len(self.oi_history) < self.min_history_for_percentile:
            return None
        
        oi_values = [h['oi'] for h in self.oi_history]
        below_count = sum(1 for v in oi_values if v < current_oi)
        percentile = (below_count / len(oi_values)) * 100
        
        return percentile
    
    def _get_oi_change(self, lookback_periods: int = 12) -> Optional[float]:
        """
        Calculate OI percentage change over lookback periods.
        
        Args:
            lookback_periods: Number of periods to look back
            
        Returns:
            Percentage change or None if not enough history
        """
        if len(self.oi_history) < lookback_periods + 1:
            return None
        
        current_oi = self.oi_history[-1]['oi']
        past_oi = self.oi_history[-lookback_periods - 1]['oi']
        
        if past_oi <= 0:
            return None
        
        change_pct = ((current_oi - past_oi) / past_oi) * 100
        return change_pct
    
    def _get_price_change(self, market_state: Dict, lookback_periods: int = 12) -> Optional[float]:
        """
        Calculate price percentage change from candles.
        
        Args:
            market_state: Market state dict with candles
            lookback_periods: Number of candles to look back
            
        Returns:
            Percentage change or None if not enough data
        """
        try:
            timeframes = market_state.get('timeframes', {})
            
            # Try 5m candles first, then 15m
            candles = None
            for tf in ['5m', '15m', '1H']:
                tf_data = timeframes.get(tf, {})
                candles = tf_data.get('candles', [])
                if candles and len(candles) >= lookback_periods + 1:
                    break
            
            if not candles or len(candles) < lookback_periods + 1:
                return None
            
            current_price = candles[-1].get('close', 0)
            past_price = candles[-lookback_periods - 1].get('close', 0)
            
            if past_price <= 0:
                return None
            
            change_pct = ((current_price - past_price) / past_price) * 100
            return change_pct
            
        except Exception as e:
            logger.debug(f"{self.name}: Error getting price change: {e}")
            return None
    
    def _detect_divergence(self, price_change: float, oi_change: float) -> str:
        """
        Detect divergence type between price and OI.
        
        Args:
            price_change: Price % change
            oi_change: OI % change
            
        Returns:
            Divergence type string
        """
        import config
        threshold = getattr(config, 'OI_DIVERGENCE_THRESHOLD_PCT', 2.0)
        
        price_up = price_change > threshold
        price_down = price_change < -threshold
        oi_up = oi_change > threshold
        oi_down = oi_change < -threshold
        
        if price_up and oi_up:
            return 'bullish_confirm'  # New longs entering, strong trend
        elif price_up and oi_down:
            return 'bearish_div'  # Shorts covering, weak rally
        elif price_down and oi_down:
            return 'bullish_div'  # Longs capitulating, potential reversal
        elif price_down and oi_up:
            return 'bearish_confirm'  # New shorts entering, strong downtrend
        
        return 'neutral'
    
    def check(self, market_state: Dict = None, signal_direction: str = '') -> Tuple[bool, str]:
        """
        Check OI conditions and return score adjustment.
        
        BOOST-HEAVY: Tilted toward helping signals pass.
        
        Args:
            market_state: Market state dict
            signal_direction: 'long' or 'short'
            
        Returns:
            (passed: bool, reason: str)
            Always returns True (never hard rejects).
        """
        import config
        
        # Check if filter is enabled
        if not getattr(config, 'OPEN_INTEREST_FILTER_ENABLED', True):
            self.last_score_adjustment = 0
            return True, "OI filter disabled"
        
        # Extract OI data
        oi_data = None
        current_oi = 0
        
        if market_state:
            oi_data = market_state.get('open_interest')
            if oi_data:
                current_oi = oi_data.get('open_interest', 0) or oi_data.get('open_interest_ccy', 0)
        
        if current_oi <= 0:
            self.last_score_adjustment = 0
            return True, "No OI data available"
        
        # Update internal history
        self._update_oi_history(current_oi)
        
        direction = signal_direction.lower() if signal_direction else ''
        
        # Get config values (BOOST-HEAVY settings)
        DIVERGENCE_BOOST = getattr(config, 'OI_DIVERGENCE_BOOST', 12)
        DIVERGENCE_PENALTY = getattr(config, 'OI_DIVERGENCE_PENALTY', 10)
        CONFIRMATION_BOOST = getattr(config, 'OI_CONFIRMATION_BOOST', 8)
        EXTREME_PENALTY = getattr(config, 'OI_EXTREME_PENALTY', 7)
        UNCROWDED_BOOST = getattr(config, 'OI_UNCROWDED_BOOST', 7)
        HIGH_PERCENTILE = getattr(config, 'OI_HIGH_PERCENTILE', 90)
        LOW_PERCENTILE = getattr(config, 'OI_LOW_PERCENTILE', 10)
        LOOKBACK = getattr(config, 'OI_LOOKBACK_PERIODS', 12)
        
        score_adj = 0
        reasons = []
        
        # Get changes
        price_change = self._get_price_change(market_state, LOOKBACK)
        oi_change = self._get_oi_change(LOOKBACK)
        oi_percentile = self._calculate_oi_percentile(current_oi)
        
        # 1. DIVERGENCE DETECTION
        if price_change is not None and oi_change is not None:
            divergence = self._detect_divergence(price_change, oi_change)
            
            if divergence == 'bullish_confirm':
                # Price up + OI up = strong bullish trend
                if direction == 'long':
                    score_adj += CONFIRMATION_BOOST
                    reasons.append(f"Bullish confirm (P:{price_change:+.1f}%, OI:{oi_change:+.1f}%)")
                elif direction == 'short':
                    score_adj -= CONFIRMATION_BOOST // 2  # Smaller penalty
                    reasons.append(f"Against bullish trend")
            
            elif divergence == 'bearish_div':
                # Price up + OI down = weak rally (shorts covering)
                if direction == 'long':
                    score_adj -= DIVERGENCE_PENALTY
                    reasons.append(f"Bearish div (weak rally, shorts covering)")
                elif direction == 'short':
                    score_adj += DIVERGENCE_BOOST
                    reasons.append(f"Bearish div supports short")
            
            elif divergence == 'bullish_div':
                # Price down + OI down = capitulation (reversal setup)
                if direction == 'long':
                    score_adj += DIVERGENCE_BOOST
                    reasons.append(f"Bullish div (capitulation, reversal)")
                elif direction == 'short':
                    score_adj -= DIVERGENCE_PENALTY
                    reasons.append(f"Bullish div warns against short")
            
            elif divergence == 'bearish_confirm':
                # Price down + OI up = strong bearish trend
                if direction == 'short':
                    score_adj += CONFIRMATION_BOOST
                    reasons.append(f"Bearish confirm (P:{price_change:+.1f}%, OI:{oi_change:+.1f}%)")
                elif direction == 'long':
                    score_adj -= CONFIRMATION_BOOST // 2  # Smaller penalty
                    reasons.append(f"Against bearish trend")
        
        # 2. OI PERCENTILE (crowding)
        if oi_percentile is not None:
            if oi_percentile >= HIGH_PERCENTILE:
                # Very crowded market - slightly reduce confidence
                score_adj -= EXTREME_PENALTY
                reasons.append(f"Crowded market (OI {oi_percentile:.0f}th pctl)")
                
                # Extra warning if funding is also extreme (double crowding)
                funding_rate = market_state.get('funding_rate') if market_state else None
                if funding_rate:
                    fr = funding_rate.get('funding_rate', 0) if isinstance(funding_rate, dict) else 0
                    if abs(fr) > 0.0008:  # > 0.08% = extreme
                        score_adj -= 5
                        reasons.append("+ extreme funding (squeeze risk)")
                        
            elif oi_percentile <= LOW_PERCENTILE:
                # Uncrowded market - room to run
                score_adj += UNCROWDED_BOOST
                reasons.append(f"Uncrowded (OI {oi_percentile:.0f}th pctl)")
        
        # Store results
        self.last_score_adjustment = score_adj
        self.last_analysis = {
            'current_oi': current_oi,
            'oi_change_pct': oi_change,
            'price_change_pct': price_change,
            'oi_percentile': oi_percentile,
            'divergence': self._detect_divergence(price_change or 0, oi_change or 0) if price_change and oi_change else 'unknown',
            'score_adjustment': score_adj,
            'history_size': len(self.oi_history)
        }
        
        # Build reason string
        if not reasons:
            if len(self.oi_history) < self.min_history_for_percentile:
                reason = f"OI warming up ({len(self.oi_history)}/{self.min_history_for_percentile} samples)"
            else:
                reason = f"OI neutral | OI: {current_oi/1e6:.1f}M"
        else:
            reason = " | ".join(reasons) + f" | Score: {score_adj:+d}"
        
        # Log
        if score_adj > 0:
            logger.info(f"✅ {self.name}: {reason}")
        elif score_adj < 0:
            logger.warning(f"⚠️  {self.name}: {reason}")
        else:
            logger.debug(f"ℹ️  {self.name}: {reason}")
        
        # Never hard reject
        return True, reason
    
    def get_oi_status(self) -> Dict:
        """
        Get OI status for dashboard display.
        
        Returns:
            Dict with OI analysis info
        """
        analysis = self.last_analysis or {}
        
        oi = analysis.get('current_oi', 0)
        percentile = analysis.get('oi_percentile')
        divergence = analysis.get('divergence', 'unknown')
        
        # Format OI nicely
        if oi >= 1e9:
            oi_str = f"{oi/1e9:.2f}B"
        elif oi >= 1e6:
            oi_str = f"{oi/1e6:.1f}M"
        elif oi >= 1e3:
            oi_str = f"{oi/1e3:.0f}K"
        else:
            oi_str = f"{oi:.0f}"
        
        # Divergence emoji
        div_emoji = {
            'bullish_confirm': '📈',
            'bearish_confirm': '📉',
            'bullish_div': '🔄📈',
            'bearish_div': '🔄📉',
            'neutral': '➡️',
            'unknown': '❓'
        }
        
        # Crowding status
        if percentile is not None:
            if percentile >= 90:
                crowd_status = 'CROWDED'
            elif percentile <= 10:
                crowd_status = 'UNCROWDED'
            else:
                crowd_status = 'NORMAL'
        else:
            crowd_status = 'WARMING UP'
        
        return {
            'enabled': True,
            'current_oi': oi,
            'oi_display': oi_str,
            'oi_percentile': percentile,
            'divergence': divergence,
            'emoji': div_emoji.get(divergence, '❓'),
            'crowd_status': crowd_status,
            'history_size': len(self.oi_history),
            'score_adjustment': analysis.get('score_adjustment', 0),
            'message': f"{div_emoji.get(divergence, '')} OI: {oi_str} | {crowd_status} | {divergence.replace('_', ' ').title()}"
        }
