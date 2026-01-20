"""
Liquidation Intelligence Tracker (Phase 3.3 Elite)

Calculates liquidation zones and tracks real liquidation events.
Uses OKX API for recent liquidations + mathematical zone estimation.

Key Concepts:
- Liquidation Zone: Price level where leveraged positions get force-closed
- LONG liquidation = price drops to zone (below current price)
- SHORT liquidation = price rises to zone (above current price)
- Liquidation cascades = snowball effect, price accelerates toward zones
- Exhaustion = liquidations slow down, reversal possible

Signals:
- Large LONG liq zone below + price dropping = magnet effect (bearish)
- Large SHORT liq zone above + price rising = squeeze potential (bullish)
- Trading INTO a cascade = dangerous
- Riding a cascade = momentum play
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class LiquidationSide(Enum):
    """Which side got liquidated"""
    LONG = "long"    # Longs liquidated = price dropped
    SHORT = "short"  # Shorts liquidated = price rose


@dataclass
class LiquidationEvent:
    """Represents a single liquidation event from OKX"""
    timestamp: datetime
    side: LiquidationSide
    price: float
    size_usd: float
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'side': self.side.value,
            'price': self.price,
            'size_usd': self.size_usd
        }


@dataclass
class LiquidationZone:
    """Represents a calculated liquidation zone"""
    price: float
    leverage: int
    side: LiquidationSide  # LONG zone = longs get liquidated here (below price)
    estimated_size: str    # 'small', 'medium', 'large'
    distance_pct: float    # Distance from current price
    
    def to_dict(self) -> Dict:
        return {
            'price': round(self.price, 2),
            'leverage': self.leverage,
            'side': self.side.value,
            'estimated_size': self.estimated_size,
            'distance_pct': round(self.distance_pct, 2)
        }


class LiquidationTracker:
    """
    Elite liquidation intelligence tracker.
    
    Features:
    - Calculates liquidation zones based on leverage math
    - Fetches recent liquidation events from OKX API
    - Detects cascade conditions (snowball liquidations)
    - Detects exhaustion signals (liquidations drying up)
    - Uses funding rate to estimate positioning bias
    
    Liquidation Math:
    - LONG at price P with leverage L: liquidated at P × (1 - 1/L)
      Example: 10x long at $200 → liquidated at $180 (-10%)
    - SHORT at price P with leverage L: liquidated at P × (1 + 1/L)
      Example: 10x short at $200 → liquidated at $220 (+10%)
    """
    
    # Common leverage levels (retail to degen)
    DEFAULT_LEVERAGE_LEVELS = [3, 5, 10, 20, 50, 100]
    
    def __init__(self):
        self.name = "LiquidationTracker"
        
        # API settings
        self.base_url = "https://www.okx.com/api/v5"
        
        # Cache for API calls
        self.last_api_fetch: Optional[datetime] = None
        self.cached_liquidations: List[LiquidationEvent] = []
        self.cache_duration_seconds = 60  # Cache for 1 minute
        
        # Zone cache
        self.last_zone_calc_price: Optional[float] = None
        self.cached_zones: Optional[Dict] = None
        self.zone_recalc_threshold_pct = 1.0  # Recalculate if price moves 1%
        
        # Liquidation history for cascade detection
        self.liquidation_history: List[LiquidationEvent] = []
        self.max_history = 500
        
        # Last analysis results
        self.last_zone_analysis: Optional[Dict] = None
        self.last_flow_analysis: Optional[Dict] = None
        
        # API status
        self.api_available = True
        self.last_api_error: Optional[str] = None
        
        logger.info(f"✅ {self.name}: Initialized with zone calculation + OKX API")
    
    def calculate_liquidation_price(self, entry_price: float, leverage: int, 
                                     is_long: bool) -> float:
        """
        Calculate liquidation price for a position.
        
        Args:
            entry_price: Position entry price
            leverage: Leverage multiplier
            is_long: True for long, False for short
            
        Returns:
            Liquidation price
        """
        if leverage <= 0:
            return 0
        
        if is_long:
            # Long liquidation: entry × (1 - 1/leverage)
            # 10x long at $200: 200 × (1 - 0.1) = $180
            return entry_price * (1 - 1/leverage)
        else:
            # Short liquidation: entry × (1 + 1/leverage)
            # 10x short at $200: 200 × (1 + 0.1) = $220
            return entry_price * (1 + 1/leverage)
    
    def _estimate_zone_size(self, leverage: int, funding_rate: float, 
                            is_long_zone: bool) -> str:
        """
        Estimate the size of a liquidation zone based on leverage and funding.
        
        Higher funding rate = more longs = larger LONG liquidation zones
        Lower funding rate = more shorts = larger SHORT liquidation zones
        
        Args:
            leverage: The leverage level
            funding_rate: Current funding rate (positive = longs pay)
            is_long_zone: True if this is a zone where longs get liquidated
            
        Returns:
            'small', 'medium', or 'large'
        """
        # Base size by leverage popularity
        # 10x and 20x are most common
        leverage_popularity = {
            3: 0.3,   # Low leverage = fewer positions
            5: 0.5,
            10: 1.0,  # Most popular
            20: 0.8,
            50: 0.4,
            100: 0.2  # Degen only
        }
        
        base_size = leverage_popularity.get(leverage, 0.5)
        
        # Adjust by funding rate (indicates positioning bias)
        # High positive funding = lots of longs = larger long liquidation zones
        if funding_rate is not None:
            if is_long_zone and funding_rate > 0.0005:  # > 0.05%
                # More longs than shorts, long zones are bigger
                base_size *= 1.5
            elif not is_long_zone and funding_rate < -0.0005:  # < -0.05%
                # More shorts than longs, short zones are bigger
                base_size *= 1.5
            elif is_long_zone and funding_rate < -0.0005:
                # Few longs, long zones are smaller
                base_size *= 0.6
            elif not is_long_zone and funding_rate > 0.0005:
                # Few shorts, short zones are smaller
                base_size *= 0.6
        
        # Classify
        if base_size >= 0.8:
            return 'large'
        elif base_size >= 0.5:
            return 'medium'
        return 'small'
    
    def calculate_liquidation_zones(self, current_price: float, 
                                     funding_rate: float = None,
                                     leverage_levels: List[int] = None) -> Dict:
        """
        Calculate liquidation zones for common leverage levels.
        
        Args:
            current_price: Current market price
            funding_rate: Current funding rate (for position bias estimation)
            leverage_levels: List of leverage levels to calculate
            
        Returns:
            Dict with long_zones, short_zones, and nearest zone info
        """
        import config
        
        if leverage_levels is None:
            leverage_levels = getattr(config, 'LIQ_LEVERAGE_LEVELS', 
                                     self.DEFAULT_LEVERAGE_LEVELS)
        
        # Check cache validity
        if (self.cached_zones and self.last_zone_calc_price and 
            abs(current_price - self.last_zone_calc_price) / self.last_zone_calc_price 
            < (getattr(config, 'LIQ_ZONE_RECALC_PCT', 1.0) / 100)):
            return self.cached_zones
        
        long_zones = []  # Zones where LONGS get liquidated (below price)
        short_zones = []  # Zones where SHORTS get liquidated (above price)
        
        for leverage in leverage_levels:
            # Calculate long liquidation zone (below current price)
            long_liq_price = self.calculate_liquidation_price(
                current_price, leverage, is_long=True
            )
            long_distance = ((current_price - long_liq_price) / current_price) * 100
            
            long_zones.append(LiquidationZone(
                price=long_liq_price,
                leverage=leverage,
                side=LiquidationSide.LONG,
                estimated_size=self._estimate_zone_size(leverage, funding_rate, True),
                distance_pct=long_distance
            ))
            
            # Calculate short liquidation zone (above current price)
            short_liq_price = self.calculate_liquidation_price(
                current_price, leverage, is_long=False
            )
            short_distance = ((short_liq_price - current_price) / current_price) * 100
            
            short_zones.append(LiquidationZone(
                price=short_liq_price,
                leverage=leverage,
                side=LiquidationSide.SHORT,
                estimated_size=self._estimate_zone_size(leverage, funding_rate, False),
                distance_pct=short_distance
            ))
        
        # Sort by distance (nearest first)
        long_zones.sort(key=lambda z: z.distance_pct)
        short_zones.sort(key=lambda z: z.distance_pct)
        
        result = {
            'current_price': current_price,
            'funding_rate': funding_rate,
            'long_zones': [z.to_dict() for z in long_zones],
            'short_zones': [z.to_dict() for z in short_zones],
            'nearest_long_liq': long_zones[0].to_dict() if long_zones else None,
            'nearest_short_liq': short_zones[0].to_dict() if short_zones else None,
            'long_zone_distance_pct': long_zones[0].distance_pct if long_zones else 999,
            'short_zone_distance_pct': short_zones[0].distance_pct if short_zones else 999,
        }
        
        # Find largest zones (most important)
        large_long_zones = [z for z in long_zones if z.estimated_size == 'large']
        large_short_zones = [z for z in short_zones if z.estimated_size == 'large']
        
        result['nearest_large_long'] = large_long_zones[0].to_dict() if large_long_zones else None
        result['nearest_large_short'] = large_short_zones[0].to_dict() if large_short_zones else None
        
        # Cache results
        self.cached_zones = result
        self.last_zone_calc_price = current_price
        self.last_zone_analysis = result
        
        return result
    
    def fetch_recent_liquidations(self) -> List[LiquidationEvent]:
        """
        Fetch recent liquidation events from OKX API.
        
        Uses: GET /api/v5/public/liquidation-orders
        
        Returns:
            List of LiquidationEvent objects
        """
        import config
        
        now = datetime.now(timezone.utc)
        cache_seconds = getattr(config, 'LIQ_CACHE_SECONDS', 60)
        
        # Check cache
        if (self.last_api_fetch and self.cached_liquidations and
            (now - self.last_api_fetch).total_seconds() < cache_seconds):
            return self.cached_liquidations
        
        events = []
        
        try:
            import requests
            
            url = f"{self.base_url}/public/liquidation-orders"
            params = {
                'instType': 'SWAP',
                'instId': 'SOL-USDT-SWAP',
                'limit': '100'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.last_api_error = None
                
                if data.get('code') == '0' and data.get('data'):
                    for item in data['data']:
                        try:
                            # Parse OKX liquidation order format
                            # Fields: ts, side, sz, px, instId, etc.
                            details = item.get('details', [])
                            
                            for detail in details:
                                timestamp_ms = int(detail.get('ts', 0))
                                side_str = detail.get('side', '').lower()
                                price = float(detail.get('bkPx', 0))  # Bankruptcy price
                                size = float(detail.get('sz', 0))
                                
                                # Estimate USD value (size is in contracts)
                                # For SOL-USDT-SWAP, 1 contract = 1 SOL
                                size_usd = size * price
                                
                                if timestamp_ms and price > 0:
                                    event = LiquidationEvent(
                                        timestamp=datetime.fromtimestamp(
                                            timestamp_ms / 1000, tz=timezone.utc
                                        ),
                                        side=LiquidationSide.LONG if side_str == 'buy' 
                                             else LiquidationSide.SHORT,
                                        # Note: OKX shows the liquidation order side
                                        # 'buy' = a long got liquidated (force sold)
                                        price=price,
                                        size_usd=size_usd
                                    )
                                    events.append(event)
                        except Exception as e:
                            logger.debug(f"{self.name}: Error parsing liquidation: {e}")
                            continue
                
                logger.debug(f"📊 {self.name}: Fetched {len(events)} liquidation events")
                
            elif response.status_code == 429:
                self.last_api_error = "Rate limited"
                logger.warning(f"⚠️  {self.name}: OKX rate limited")
                
            else:
                self.last_api_error = f"HTTP {response.status_code}"
                logger.warning(f"⚠️  {self.name}: OKX returned {response.status_code}")
                
        except Exception as e:
            self.last_api_error = str(e)
            logger.warning(f"⚠️  {self.name}: Error fetching liquidations: {e}")
        
        # Update cache
        if events:
            self.last_api_fetch = now
            self.cached_liquidations = events
            
            # Add to history (dedupe by timestamp+side+price)
            existing = {(e.timestamp, e.side, e.price) for e in self.liquidation_history}
            for event in events:
                key = (event.timestamp, event.side, event.price)
                if key not in existing:
                    self.liquidation_history.append(event)
            
            # Trim history
            if len(self.liquidation_history) > self.max_history:
                self.liquidation_history = self.liquidation_history[-self.max_history:]
        
        return self.cached_liquidations
    
    def analyze_liquidation_flow(self, hours: float = 1) -> Dict:
        """
        Analyze recent liquidation flow for cascade/exhaustion detection.
        
        Args:
            hours: Lookback period in hours
            
        Returns:
            Dict with flow analysis including cascade and exhaustion signals
        """
        # Fetch latest liquidations
        self.fetch_recent_liquidations()
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = [e for e in self.liquidation_history if e.timestamp > cutoff]
        
        # Aggregate by side
        longs_liquidated = [e for e in recent if e.side == LiquidationSide.LONG]
        shorts_liquidated = [e for e in recent if e.side == LiquidationSide.SHORT]
        
        longs_usd = sum(e.size_usd for e in longs_liquidated)
        shorts_usd = sum(e.size_usd for e in shorts_liquidated)
        total_usd = longs_usd + shorts_usd
        
        # Determine dominant side
        if longs_usd > shorts_usd * 1.5:
            dominant_side = 'longs'
            bias = 'bearish'  # Longs getting rekt = bearish
        elif shorts_usd > longs_usd * 1.5:
            dominant_side = 'shorts'
            bias = 'bullish'  # Shorts getting rekt = bullish
        else:
            dominant_side = 'balanced'
            bias = 'neutral'
        
        # Cascade detection: lots of one-sided liquidations in short time
        # Check last 15 minutes for intensity
        cascade_cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        recent_15m = [e for e in recent if e.timestamp > cascade_cutoff]
        recent_longs_15m = sum(1 for e in recent_15m if e.side == LiquidationSide.LONG)
        recent_shorts_15m = sum(1 for e in recent_15m if e.side == LiquidationSide.SHORT)
        
        cascade_active = False
        cascade_side = None
        if recent_longs_15m >= 5 and recent_longs_15m > recent_shorts_15m * 2:
            cascade_active = True
            cascade_side = 'longs'
        elif recent_shorts_15m >= 5 and recent_shorts_15m > recent_longs_15m * 2:
            cascade_active = True
            cascade_side = 'shorts'
        
        # Exhaustion detection: liquidations were heavy but now slowing
        # Compare last 15m to previous 45m
        older_cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
        older = [e for e in recent if e.timestamp <= cascade_cutoff and e.timestamp > older_cutoff]
        
        exhaustion_signal = False
        if len(older) >= 10 and len(recent_15m) <= len(older) * 0.2:
            # Liquidations dropped to 20% or less of previous rate
            exhaustion_signal = True
        
        result = {
            'period_hours': hours,
            'longs_liquidated_count': len(longs_liquidated),
            'shorts_liquidated_count': len(shorts_liquidated),
            'longs_liquidated_usd': longs_usd,
            'shorts_liquidated_usd': shorts_usd,
            'total_liquidated_usd': total_usd,
            'dominant_side': dominant_side,
            'bias': bias,
            'cascade_active': cascade_active,
            'cascade_side': cascade_side,
            'exhaustion_signal': exhaustion_signal,
            'recent_15m_count': len(recent_15m),
            'api_available': self.api_available,
            'last_error': self.last_api_error
        }
        
        self.last_flow_analysis = result
        
        if cascade_active:
            logger.warning(f"🌊 {self.name}: CASCADE ACTIVE - {cascade_side} getting liquidated")
        if exhaustion_signal:
            logger.info(f"💨 {self.name}: Exhaustion signal - liquidations slowing")
        
        return result
    
    def get_comprehensive_analysis(self, current_price: float, 
                                    funding_rate: float = None) -> Dict:
        """
        Get comprehensive liquidation analysis for trading decisions.
        
        Combines zone calculations with flow analysis.
        
        Args:
            current_price: Current market price
            funding_rate: Current funding rate
            
        Returns:
            Dict with zones, flow, and combined signals
        """
        # Calculate zones
        zones = self.calculate_liquidation_zones(current_price, funding_rate)
        
        # Analyze flow
        flow = self.analyze_liquidation_flow(hours=1)
        
        # Combine signals
        return {
            'zones': zones,
            'flow': flow,
            'current_price': current_price,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_status(self) -> Dict:
        """
        Get status for dashboard display.
        
        Returns:
            Dict with human-readable status
        """
        zones = self.last_zone_analysis or {}
        flow = self.last_flow_analysis or {}
        
        # Build status message
        cascade_msg = ""
        if flow.get('cascade_active'):
            cascade_msg = f"🌊 CASCADE: {flow.get('cascade_side', '?').upper()}"
        elif flow.get('exhaustion_signal'):
            cascade_msg = "💨 Exhaustion detected"
        
        bias = flow.get('bias', 'neutral')
        bias_emoji = {'bullish': '📈', 'bearish': '📉', 'neutral': '➡️'}
        
        # Format USD values
        total_liq = flow.get('total_liquidated_usd', 0)
        if total_liq >= 1000000:
            total_str = f"${total_liq/1000000:.1f}M"
        elif total_liq >= 1000:
            total_str = f"${total_liq/1000:.0f}k"
        else:
            total_str = f"${total_liq:.0f}"
        
        return {
            'enabled': True,
            'api_available': self.api_available,
            'bias': bias,
            'emoji': bias_emoji.get(bias, '❓'),
            'cascade_active': flow.get('cascade_active', False),
            'exhaustion_signal': flow.get('exhaustion_signal', False),
            'total_liquidated_1h': total_str,
            'dominant_side': flow.get('dominant_side', 'unknown'),
            'nearest_long_zone': zones.get('long_zone_distance_pct', 999),
            'nearest_short_zone': zones.get('short_zone_distance_pct', 999),
            'cascade_message': cascade_msg,
            'last_error': self.last_api_error,
            'message': f"{bias_emoji.get(bias, '')} Liq bias: {bias.upper()} | {total_str} liquidated (1h) {cascade_msg}"
        }


# Module-level convenience function
def get_liquidation_bias() -> str:
    """Quick check for current liquidation bias."""
    tracker = LiquidationTracker()
    flow = tracker.analyze_liquidation_flow(hours=1)
    return flow['bias']
