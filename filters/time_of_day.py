"""
Time-of-Day Filter (Phase 2.3 Elite)

Institutional-grade time filter that:
- Blocks trading during low-liquidity periods (weekends, dead zone)
- Applies score adjustments based on trading session
- Considers day-of-week patterns (Monday slow, Friday squaring)
- Strategy-aware timing (breakouts vs pullbacks)
- Integrates with historical hourly performance data

Trading Sessions (UTC):
- ASIAN: 00:00-08:00 (lower volume, range-bound)
- LONDON: 08:00-16:00 (trend initiation, high volume)
- NEW_YORK: 13:00-21:00 (highest volume)
- OVERLAP: 13:00-16:00 (London + NY = best liquidity)
- DEAD_ZONE: 21:00-00:00 (avoid - low liquidity)
- WEEKEND: Saturday/Sunday (avoid completely)
"""

from typing import Dict, Tuple, Optional
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TradingSession(Enum):
    """Trading session classifications"""
    ASIAN = "asian"           # 00:00-08:00 UTC
    LONDON = "london"         # 08:00-13:00 UTC (before overlap)
    NEW_YORK = "new_york"     # 16:00-21:00 UTC (after overlap)
    OVERLAP = "overlap"       # 13:00-16:00 UTC (London + NY = BEST)
    DEAD_ZONE = "dead_zone"   # 21:00-00:00 UTC
    WEEKEND = "weekend"       # Saturday/Sunday


class TimeOfDayFilter:
    """
    Elite time-based filter (Phase 2.3).
    
    Analyzes current time to determine:
    - Trading session quality
    - Day-of-week patterns
    - Strategy-specific timing
    - Score adjustments
    
    This filter helps avoid:
    - Weekend low liquidity
    - Dead zone fakeouts
    - Monday slow starts
    - Friday position squaring
    """
    
    def __init__(self):
        self.name = "TimeOfDay"
        self.last_session = None
        self.last_score_adjustment = 0
        
        # Try to load historical hourly performance
        self.hourly_performance = {}
        self._load_historical_performance()
    
    def _load_historical_performance(self):
        """Load hourly win rates from TradeQualityInspector if available."""
        try:
            from utils.trade_quality import TradeQualityInspector
            inspector = TradeQualityInspector()
            hourly_data = inspector.analyze_trade_by_hour()
            if hourly_data and 'by_hour' in hourly_data:
                self.hourly_performance = hourly_data['by_hour']
                if self.hourly_performance:
                    logger.info(f"📊 {self.name}: Loaded historical performance for {len(self.hourly_performance)} hours")
        except Exception as e:
            logger.debug(f"{self.name}: Could not load historical performance: {e}")
    
    def get_current_session(self, dt: datetime = None) -> TradingSession:
        """
        Determine current trading session based on UTC time.
        
        Session boundaries (UTC):
        - 00:00-08:00: Asian
        - 08:00-13:00: London (pre-overlap)
        - 13:00-16:00: Overlap (BEST)
        - 16:00-21:00: New York (post-overlap)
        - 21:00-00:00: Dead Zone
        
        Args:
            dt: Datetime to check (defaults to now UTC)
            
        Returns:
            TradingSession enum
        """
        if dt is None:
            dt = datetime.now(timezone.utc)
        
        # Check weekend first (Saturday = 5, Sunday = 6)
        if dt.weekday() >= 5:
            return TradingSession.WEEKEND
        
        hour = dt.hour
        
        # Session boundaries (UTC)
        if 13 <= hour < 16:
            return TradingSession.OVERLAP  # Best liquidity - London + NY
        elif 8 <= hour < 13:
            return TradingSession.LONDON   # London session
        elif 16 <= hour < 21:
            return TradingSession.NEW_YORK # NY session
        elif 0 <= hour < 8:
            return TradingSession.ASIAN    # Asian session
        else:  # 21 <= hour < 24
            return TradingSession.DEAD_ZONE
    
    def get_session_score(self, session: TradingSession, 
                          strategy: str = '') -> int:
        """
        Get score adjustment for trading session.
        
        Args:
            session: Current trading session
            strategy: 'breakout' or 'pullback'
            
        Returns:
            Score adjustment (-100 to +15)
        """
        strategy = strategy.lower() if strategy else ''
        
        # Base session scores
        session_scores = {
            TradingSession.OVERLAP: 15,      # Best liquidity
            TradingSession.LONDON: 10,       # Good for trends
            TradingSession.NEW_YORK: 10,     # High volume
            TradingSession.ASIAN: 0,         # OK for ranging
            TradingSession.DEAD_ZONE: -15,   # Avoid
            TradingSession.WEEKEND: -20,     # Lower liquidity but tradeable
        }
        
        base_score = session_scores.get(session, 0)
        
        # Strategy-specific adjustments
        if strategy == 'breakout':
            if session == TradingSession.OVERLAP:
                base_score += 5  # Breakouts work great in overlap
            elif session == TradingSession.LONDON:
                base_score += 3  # London open breakouts
            elif session == TradingSession.ASIAN:
                base_score -= 10  # Breakouts often fail in Asian (range-bound)
        elif strategy == 'pullback':
            if session == TradingSession.ASIAN:
                base_score += 5  # Mean reversion works in Asian ranges
            elif session == TradingSession.OVERLAP:
                base_score += 3  # Pullbacks in strong trends
        
        return base_score
    
    def get_day_score(self, dt: datetime = None) -> int:
        """
        Get score adjustment for day of week.
        
        Patterns:
        - Monday: Slow start, gaps from weekend
        - Tuesday-Thursday: Prime trading days
        - Friday: Position squaring, especially afternoon
        
        Args:
            dt: Datetime to check
            
        Returns:
            Score adjustment
        """
        if dt is None:
            dt = datetime.now(timezone.utc)
        
        weekday = dt.weekday()
        hour = dt.hour
        
        # Monday (0): Slow start
        if weekday == 0:
            if hour < 8:
                return -10  # Monday Asian is very slow
            elif hour < 13:
                return -5   # Monday morning still slow
            return 0  # Monday afternoon OK
        
        # Tuesday-Thursday (1, 2, 3): Prime days
        if weekday in [1, 2, 3]:
            return 5
        
        # Friday (4): Position squaring
        if weekday == 4:
            if hour >= 20:
                return -15  # Friday late evening = avoid
            elif hour >= 18:
                return -10  # Friday evening = caution
            elif hour >= 15:
                return -5   # Friday afternoon = some squaring
            return 0  # Friday morning OK
        
        # Weekend (5, 6) - lower liquidity but crypto trades 24/7
        return -15
    
    def get_historical_hour_score(self, hour: int) -> int:
        """
        Get score based on YOUR historical performance at this hour.
        
        Uses data from TradeQualityInspector to reward/penalize
        hours where you historically win or lose more.
        
        Args:
            hour: UTC hour (0-23)
            
        Returns:
            Score adjustment based on historical win rate
        """
        if not self.hourly_performance:
            return 0  # No data yet
        
        hour_data = self.hourly_performance.get(hour, {})
        win_rate = hour_data.get('win_rate', 50)
        trade_count = hour_data.get('count', 0)
        
        # Need at least 5 trades at this hour for confidence
        if trade_count < 5:
            return 0
        
        # Score based on historical win rate
        if win_rate >= 70:
            return 10  # Your best hours
        elif win_rate >= 60:
            return 5
        elif win_rate >= 50:
            return 0
        elif win_rate >= 40:
            return -5
        else:
            return -10  # Your worst hours
    
    def check(self, market_state: Dict = None, signal_direction: str = '',
              strategy: str = '') -> Tuple[bool, str]:
        """
        Check if current time is suitable for trading.
        
        Args:
            market_state: Not used, but kept for interface consistency
            signal_direction: 'long' or 'short' (not used currently)
            strategy: 'breakout' or 'pullback' for strategy-specific timing
            
        Returns:
            (passed: bool, reason: str)
        """
        import config
        
        # Check if filter is enabled
        if not getattr(config, 'TIME_OF_DAY_FILTER_ENABLED', True):
            return True, "Time filter disabled"
        
        now = datetime.now(timezone.utc)
        session = self.get_current_session(now)
        self.last_session = session
        
        # Calculate component scores
        session_score = self.get_session_score(session, strategy)
        day_score = self.get_day_score(now)
        historical_score = self.get_historical_hour_score(now.hour)
        
        total_score = session_score + day_score + historical_score
        self.last_score_adjustment = total_score
        
        # Format time info for logging
        day_name = now.strftime('%A')
        time_str = now.strftime('%H:%M UTC')
        
        # === DECISION LOGIC ===
        
        # WEEKEND: Hard reject
        if session == TradingSession.WEEKEND:
            if getattr(config, 'AVOID_WEEKENDS', True):
                reason = f"🚫 Weekend ({day_name} {time_str}) - Low liquidity, avoid"
                logger.warning(f"❌ {self.name}: {reason}")
                return False, reason
        
        # DEAD ZONE: Reject if configured
        if session == TradingSession.DEAD_ZONE:
            if getattr(config, 'AVOID_DEAD_ZONE', True):
                reason = f"🌙 Dead zone ({time_str}) - Very low liquidity"
                logger.warning(f"❌ {self.name}: {reason}")
                return False, reason
        
        # LOW LIQUIDITY HOURS: Check configurable window
        if getattr(config, 'AVOID_LOW_LIQUIDITY_HOURS', False):
            start = getattr(config, 'LOW_LIQUIDITY_START_UTC', 0)
            end = getattr(config, 'LOW_LIQUIDITY_END_UTC', 4)
            
            # Handle the hour check
            if start <= now.hour < end:
                reason = f"😴 Low liquidity hours ({time_str})"
                logger.warning(f"⚠️ {self.name}: {reason} - Heavy score penalty")
                # Apply extra penalty but don't reject
                self.last_score_adjustment = min(total_score - 10, -15)
        
        # Build reason string
        session_name = session.value.upper().replace('_', ' ')
        
        # Create detailed breakdown
        score_parts = []
        if session_score != 0:
            score_parts.append(f"session={session_score:+d}")
        if day_score != 0:
            score_parts.append(f"day={day_score:+d}")
        if historical_score != 0:
            score_parts.append(f"history={historical_score:+d}")
        
        score_breakdown = ", ".join(score_parts) if score_parts else "neutral"
        
        reason = f"{session_name} | {day_name} {time_str} | score={total_score:+d} ({score_breakdown})"
        
        # Log based on score
        if total_score >= 15:
            logger.info(f"🔥 {self.name}: {reason} - PRIME trading time!")
        elif total_score >= 5:
            logger.info(f"✅ {self.name}: {reason} - Good time")
        elif total_score >= 0:
            logger.info(f"ℹ️  {self.name}: {reason}")
        elif total_score >= -10:
            logger.warning(f"⚠️  {self.name}: {reason} - Suboptimal time")
        else:
            logger.warning(f"⚠️  {self.name}: {reason} - Poor time, consider waiting")
        
        return True, reason
    
    def get_time_status(self) -> Dict:
        """
        Get current time status for dashboard display.
        
        Returns:
            Dict with session info, scores, and recommendations
        """
        now = datetime.now(timezone.utc)
        session = self.get_current_session(now)
        
        session_emoji = {
            TradingSession.OVERLAP: '🔥',
            TradingSession.LONDON: '🇬🇧',
            TradingSession.NEW_YORK: '🇺🇸',
            TradingSession.ASIAN: '🌏',
            TradingSession.DEAD_ZONE: '🌙',
            TradingSession.WEEKEND: '🚫',
        }
        
        session_quality = {
            TradingSession.OVERLAP: 'EXCELLENT',
            TradingSession.LONDON: 'GOOD',
            TradingSession.NEW_YORK: 'GOOD',
            TradingSession.ASIAN: 'FAIR',
            TradingSession.DEAD_ZONE: 'POOR',
            TradingSession.WEEKEND: 'AVOID',
        }
        
        emoji = session_emoji.get(session, '❓')
        quality = session_quality.get(session, 'UNKNOWN')
        
        # Calculate current scores
        session_score = self.get_session_score(session)
        day_score = self.get_day_score(now)
        historical_score = self.get_historical_hour_score(now.hour)
        total_score = session_score + day_score + historical_score
        
        return {
            'session': session.value,
            'session_display': session.value.upper().replace('_', ' '),
            'emoji': emoji,
            'quality': quality,
            'time_utc': now.strftime('%H:%M UTC'),
            'day': now.strftime('%A'),
            'hour': now.hour,
            'score_adjustment': total_score,
            'score_breakdown': {
                'session': session_score,
                'day': day_score,
                'historical': historical_score
            },
            'is_prime_time': session == TradingSession.OVERLAP,
            'is_good_time': session in [TradingSession.OVERLAP, TradingSession.LONDON, TradingSession.NEW_YORK],
            'should_avoid': session in [TradingSession.DEAD_ZONE, TradingSession.WEEKEND],
            'message': f"{emoji} {session.value.upper().replace('_', ' ')} - {quality}"
        }
    
    def get_next_good_session(self) -> Dict:
        """
        Get info about when the next good trading session starts.
        
        Useful for dashboard to show "Next good time in X hours".
        
        Returns:
            Dict with next session info
        """
        now = datetime.now(timezone.utc)
        current_session = self.get_current_session(now)
        
        # If already in good session, return current
        if current_session in [TradingSession.OVERLAP, TradingSession.LONDON, TradingSession.NEW_YORK]:
            return {
                'status': 'now',
                'message': 'Good trading time NOW',
                'session': current_session.value
            }
        
        hour = now.hour
        
        # Calculate hours until next good session
        if current_session == TradingSession.ASIAN:
            # Next good: London at 08:00
            hours_until = (8 - hour) if hour < 8 else (24 - hour + 8)
            next_session = 'LONDON'
        elif current_session == TradingSession.DEAD_ZONE:
            # Next good: London at 08:00 (tomorrow)
            hours_until = (24 - hour) + 8
            next_session = 'LONDON'
        elif current_session == TradingSession.WEEKEND:
            # Next good: Monday London at 08:00
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            hours_until = days_until_monday * 24 + (8 - hour)
            next_session = 'LONDON (Monday)'
        else:
            hours_until = 0
            next_session = current_session.value
        
        return {
            'status': 'waiting',
            'hours_until': hours_until,
            'message': f"Next good session: {next_session} in {hours_until}h",
            'session': next_session
        }


# Module-level convenience function
def is_good_trading_time() -> bool:
    """Quick check if current time is good for trading."""
    filter_instance = TimeOfDayFilter()
    session = filter_instance.get_current_session()
    return session in [TradingSession.OVERLAP, TradingSession.LONDON, TradingSession.NEW_YORK]
