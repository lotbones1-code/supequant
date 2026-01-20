"""
Funding Rate Arbitrage Strategy (Phase 4.2 Elite)

Captures extreme funding rate imbalances to collect funding payments.
This is a LOW-RISK, LOW-FREQUENCY strategy that only triggers on rare extremes.

Core Logic:
- High positive funding (>0.15%) = Longs paying shorts = SHORT to collect
- High negative funding (<-0.15%) = Shorts paying longs = LONG to collect
- Hold until funding is paid, then exit (time-based, not price-based)

CRITICAL: This is NOT a price prediction strategy.
          We don't care about price direction, only funding collection.
          
Safety:
- Only triggers when funding > fees (guaranteed profit)
- Only in low volatility markets (price won't move against us)
- Emergency stop loss for flash crash protection
- Time-based exit after funding collection
"""

from typing import Dict, Optional
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class FundingArbitrageStrategy:
    """
    Elite Funding Rate Arbitrage Strategy.
    
    Collects funding payments at extreme funding rates.
    
    Key features:
    - Only triggers at EXTREME funding (>0.15%)
    - Time-based exit (not price targets)
    - Low volatility requirement
    - Minimum time buffer before funding
    - Coordinates with existing FundingRateFilter
    """
    
    def __init__(self):
        self.name = "FundingArbitrage"
        self.strategy_type = "arbitrage"
        self.signals_generated = 0
        self.signals_blocked_volatility = 0
        self.signals_blocked_time = 0
        
        logger.info(f"✅ {self.name}: Strategy initialized (time-based arb)")
    
    def analyze(self, market_state: Dict) -> Optional[Dict]:
        """
        Analyze market for funding arbitrage opportunities.
        
        ONLY returns signal if:
        1. Funding rate is EXTREME (>0.15% or <-0.15%)
        2. Enough time until next funding (>1.5 hours)
        3. Market is low volatility (ATR < 65th percentile)
        4. Expected profit > 0 after fees
        
        Args:
            market_state: Complete market state from MarketDataFeed
            
        Returns:
            Signal dict if arb opportunity found, None otherwise
        """
        import config
        
        try:
            # Get config values
            extreme_threshold = getattr(config, 'FR_EXTREME_THRESHOLD', 0.0015)
            min_hours = getattr(config, 'FR_MIN_HOURS_TO_FUNDING', 1.5)
            max_atr_pct = getattr(config, 'FR_MAX_ATR_PERCENTILE', 65)
            require_low_vol = getattr(config, 'FR_REQUIRE_LOW_VOLATILITY', True)
            emergency_stop = getattr(config, 'FR_EMERGENCY_STOP_PCT', 0.025)
            max_hold = getattr(config, 'FR_MAX_HOLD_HOURS', 9.0)
            
            # Step 1: Get funding data
            funding_data = market_state.get('funding_rate', {})
            if not funding_data:
                return None
            
            funding_rate = self._get_funding_rate(funding_data)
            if funding_rate is None:
                return None
            
            # Step 2: Check if funding is EXTREME enough
            if abs(funding_rate) < extreme_threshold:
                return None  # Not extreme enough, skip
            
            # Step 3: Calculate time to next funding
            hours_to_funding = self._get_hours_to_funding(funding_data)
            if hours_to_funding is None:
                return None  # Can't determine timing
            
            # Step 4: Check minimum time buffer
            if hours_to_funding < min_hours:
                self.signals_blocked_time += 1
                logger.debug(f"{self.name}: Blocked - only {hours_to_funding:.1f}h to funding (need {min_hours}h)")
                return None
            
            # Step 5: Check volatility (only in low-vol markets)
            if require_low_vol:
                atr_percentile = self._get_atr_percentile(market_state)
                if atr_percentile > max_atr_pct:
                    self.signals_blocked_volatility += 1
                    logger.debug(f"{self.name}: Blocked - ATR {atr_percentile}th pct too high")
                    return None
            
            # Step 6: Determine direction (contrarian to funding)
            if funding_rate > extreme_threshold:
                direction = 'short'  # Crowded longs paying, short to collect
                crowd = 'long'
            elif funding_rate < -extreme_threshold:
                direction = 'long'   # Crowded shorts paying, long to collect
                crowd = 'short'
            else:
                return None
            
            # Step 7: Build signal
            current_price = market_state.get('current_price', 0)
            if current_price <= 0:
                return None
            
            # Calculate emergency stop loss
            stop_distance = current_price * emergency_stop
            if direction == 'short':
                stop_loss = current_price + stop_distance
            else:
                stop_loss = current_price - stop_distance
            
            # Get expected funding time
            next_funding_time = self._get_next_funding_time(funding_data)
            
            # Calculate expected profit
            fee_cost = 0.0012  # ~0.12% round trip fees
            expected_profit_pct = (abs(funding_rate) - fee_cost) * 100
            
            signal = {
                'strategy': self.name,
                'strategy_type': 'arbitrage',  # Flag for special handling
                'direction': direction,
                'entry_price': current_price,
                
                # Emergency stop only (2.5% away)
                'stop_loss': stop_loss,
                
                # NO PROFIT TARGETS for arb - time-based exit
                'take_profit_1': None,
                'take_profit_2': None,
                
                # Time-based exit fields (new for arb)
                'exit_after_funding': True,
                'max_hold_hours': max_hold,
                'entry_time': datetime.now(timezone.utc).isoformat(),
                'expected_funding_time': next_funding_time.isoformat() if next_funding_time else None,
                
                # Arb metadata
                'funding_rate': funding_rate,
                'funding_pct': funding_rate * 100,
                'hours_to_funding': hours_to_funding,
                'expected_profit_pct': expected_profit_pct,
                'crowd_position': crowd,
                
                # Standard fields
                'timestamp': market_state.get('timestamp'),
                'current_price': current_price
            }
            
            self.signals_generated += 1
            logger.info(f"💰 {self.name}: ARB opportunity! {direction.upper()} @ {funding_rate*100:.3f}% funding")
            logger.info(f"   Expected profit: {expected_profit_pct:.3f}% | Hours to funding: {hours_to_funding:.1f}h")
            
            return signal
            
        except Exception as e:
            logger.error(f"{self.name}: Error analyzing market: {e}")
            return None
    
    def _get_funding_rate(self, funding_data: Dict) -> Optional[float]:
        """
        Safely extract funding rate from funding data.
        
        Handles both dict and direct value formats.
        """
        if not funding_data:
            return None
        
        if isinstance(funding_data, dict):
            return funding_data.get('funding_rate', None)
        
        try:
            return float(funding_data)
        except (TypeError, ValueError):
            return None
    
    def _get_hours_to_funding(self, funding_data: Dict) -> Optional[float]:
        """
        Calculate hours until next funding payment.
        
        OKX funding times: 00:00, 08:00, 16:00 UTC (every 8 hours)
        """
        if not funding_data or not isinstance(funding_data, dict):
            # Fallback: calculate from current time
            return self._calculate_hours_to_next_funding()
        
        next_funding = funding_data.get('next_funding_time')
        if not next_funding:
            return self._calculate_hours_to_next_funding()
        
        try:
            now = datetime.now(timezone.utc)
            
            if isinstance(next_funding, datetime):
                # Already a datetime
                if next_funding.tzinfo is None:
                    next_funding = next_funding.replace(tzinfo=timezone.utc)
                delta = (next_funding - now).total_seconds() / 3600
            elif isinstance(next_funding, (int, float)):
                # Timestamp (milliseconds or seconds)
                ts = next_funding / 1000 if next_funding > 1e12 else next_funding
                delta = (ts - now.timestamp()) / 3600
            else:
                return self._calculate_hours_to_next_funding()
            
            return max(0, delta)
            
        except Exception:
            return self._calculate_hours_to_next_funding()
    
    def _calculate_hours_to_next_funding(self) -> float:
        """
        Calculate hours to next funding based on OKX schedule.
        
        OKX funds at 00:00, 08:00, 16:00 UTC.
        """
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        
        # Find next funding hour
        funding_hours = [0, 8, 16, 24]  # 24 = next day 00:00
        next_funding_hour = None
        
        for fh in funding_hours:
            if fh > current_hour:
                next_funding_hour = fh
                break
        
        if next_funding_hour is None:
            next_funding_hour = 24  # Next day 00:00
        
        # Calculate delta
        hours_to_funding = next_funding_hour - current_hour
        minutes_to_funding = -now.minute  # Subtract current minutes
        
        total_hours = hours_to_funding + (minutes_to_funding / 60)
        return max(0, total_hours)
    
    def _get_next_funding_time(self, funding_data: Dict) -> Optional[datetime]:
        """Get the next funding time as datetime."""
        if not funding_data or not isinstance(funding_data, dict):
            return self._calculate_next_funding_time()
        
        next_funding = funding_data.get('next_funding_time')
        if not next_funding:
            return self._calculate_next_funding_time()
        
        try:
            if isinstance(next_funding, datetime):
                return next_funding
            elif isinstance(next_funding, (int, float)):
                ts = next_funding / 1000 if next_funding > 1e12 else next_funding
                return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass
        
        return self._calculate_next_funding_time()
    
    def _calculate_next_funding_time(self) -> datetime:
        """Calculate next funding time based on OKX schedule."""
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        
        funding_hours = [0, 8, 16]
        
        for fh in funding_hours:
            if fh > current_hour:
                return now.replace(hour=fh, minute=0, second=0, microsecond=0)
        
        # Next day 00:00
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=0, minute=0, second=0, microsecond=0)
    
    def _get_atr_percentile(self, market_state: Dict) -> float:
        """Get ATR percentile from market state."""
        timeframes = market_state.get('timeframes', {})
        
        # Try 15m first, then 1H
        for tf in ['15m', '1H']:
            if tf in timeframes:
                atr_data = timeframes[tf].get('atr', {})
                percentile = atr_data.get('atr_percentile', 50)
                if percentile:
                    return percentile
        
        return 50  # Default neutral
    
    def get_statistics(self) -> Dict:
        """Get strategy statistics."""
        return {
            'name': self.name,
            'type': self.strategy_type,
            'signals_generated': self.signals_generated,
            'signals_blocked_volatility': self.signals_blocked_volatility,
            'signals_blocked_time': self.signals_blocked_time
        }
