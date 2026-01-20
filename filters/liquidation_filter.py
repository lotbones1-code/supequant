"""
Liquidation Intelligence Filter (Phase 3.3 Elite)

Uses liquidation zone calculations and real-time liquidation data
to provide intelligent score adjustments for trading decisions.

Elite Features:
1. Proximity Risk - penalty for being near dangerous liquidation zones
2. Magnet Effect - boost for trading toward large liquidation clusters
3. Cascade Detection - adjust for active liquidation cascades
4. Exhaustion Signals - contrarian opportunity after cascade exhaustion

Signals:
- Near YOUR-SIDE liquidation zone = PENALTY (stop hunt risk)
- Near OPPOSITE-SIDE liquidation zone = BOOST (magnet/squeeze potential)
- Trading INTO cascade = PENALTY (dangerous)
- Riding cascade = BOOST (momentum play)
- Exhaustion after cascade = small contrarian boost
"""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class LiquidationFilter:
    """
    Elite liquidation intelligence filter.
    
    Provides score adjustments based on:
    - Liquidation zone proximity
    - Liquidation cascade detection
    - Magnet effect (large liquidation clusters)
    - Exhaustion signals
    
    NEVER hard rejects - uses score adjustments for flexibility.
    """
    
    def __init__(self):
        self.name = "LiquidationFilter"
        self.last_score_adjustment = 0
        self.tracker = None
        self.enabled = True
        
        # Initialize tracker
        self._init_tracker()
    
    def _init_tracker(self):
        """Initialize the liquidation tracker."""
        try:
            from data_feed.liquidation_tracker import LiquidationTracker
            self.tracker = LiquidationTracker()
            logger.info(f"✅ {self.name}: Initialized with LiquidationTracker")
        except Exception as e:
            logger.warning(f"⚠️  {self.name}: Could not initialize tracker: {e}")
            self.tracker = None
            self.enabled = False
    
    def check(self, market_state: Dict = None, signal_direction: str = '') -> Tuple[bool, str]:
        """
        Check liquidation conditions and return score adjustment.
        
        Args:
            market_state: Market state dict (should contain 'current_price', 'funding_rate')
            signal_direction: 'long' or 'short'
            
        Returns:
            (passed: bool, reason: str)
            Always returns True (never hard rejects), uses score adjustments.
        """
        import config
        
        # Check if filter is enabled
        if not getattr(config, 'LIQUIDATION_FILTER_ENABLED', True):
            self.last_score_adjustment = 0
            return True, "Liquidation filter disabled"
        
        # Check if tracker is available
        if not self.tracker:
            self.last_score_adjustment = 0
            return True, "Liquidation tracker not available"
        
        # Extract market data
        current_price = 0
        funding_rate = None
        
        if market_state:
            current_price = market_state.get('current_price', 0)
            funding_rate = market_state.get('funding_rate')
            
            # Try to get price from candles if not directly available
            if current_price == 0:
                timeframes = market_state.get('timeframes', {})
                for tf in ['5m', '15m', '1H']:
                    tf_data = timeframes.get(tf, {})
                    candles = tf_data.get('candles', [])
                    if candles:
                        current_price = candles[-1].get('close', 0)
                        if current_price > 0:
                            break
        
        if current_price <= 0:
            self.last_score_adjustment = 0
            return True, "No price data for liquidation analysis"
        
        direction = signal_direction.lower() if signal_direction else ''
        
        # Get comprehensive analysis
        analysis = self.tracker.get_comprehensive_analysis(current_price, funding_rate)
        zones = analysis['zones']
        flow = analysis['flow']
        
        # Get config values
        PROXIMITY_PCT = getattr(config, 'LIQ_ZONE_PROXIMITY_PCT', 2.0)
        MAGNET_RANGE_PCT = getattr(config, 'LIQ_MAGNET_RANGE_PCT', 3.0)
        PROXIMITY_PENALTY = getattr(config, 'LIQ_PROXIMITY_PENALTY', 15)
        MAGNET_BOOST = getattr(config, 'LIQ_MAGNET_BOOST', 10)
        CASCADE_PENALTY = getattr(config, 'LIQ_CASCADE_PENALTY', 20)
        CASCADE_BOOST = getattr(config, 'LIQ_CASCADE_BOOST', 15)
        EXHAUSTION_BOOST = getattr(config, 'LIQ_EXHAUSTION_BOOST', 5)
        
        # Calculate score adjustment
        score_adj = 0
        reasons = []
        
        # 1. PROXIMITY RISK
        # Going LONG near LONG liquidation zone (below price) = dangerous
        # Going SHORT near SHORT liquidation zone (above price) = dangerous
        long_zone_dist = zones.get('long_zone_distance_pct', 999)
        short_zone_dist = zones.get('short_zone_distance_pct', 999)
        
        if direction == 'long' and long_zone_dist <= PROXIMITY_PCT:
            score_adj -= PROXIMITY_PENALTY
            nearest = zones.get('nearest_long_liq', {})
            reasons.append(f"Near LONG liq zone (${nearest.get('price', '?')}, {long_zone_dist:.1f}% away)")
            logger.warning(f"⚠️  {self.name}: LONG signal near long liquidation zone - stop hunt risk")
        
        elif direction == 'short' and short_zone_dist <= PROXIMITY_PCT:
            score_adj -= PROXIMITY_PENALTY
            nearest = zones.get('nearest_short_liq', {})
            reasons.append(f"Near SHORT liq zone (${nearest.get('price', '?')}, {short_zone_dist:.1f}% away)")
            logger.warning(f"⚠️  {self.name}: SHORT signal near short liquidation zone - squeeze risk")
        
        # 2. MAGNET EFFECT
        # Going LONG with large SHORT liquidation zone above = squeeze magnet
        # Going SHORT with large LONG liquidation zone below = dump magnet
        large_short_zone = zones.get('nearest_large_short')
        large_long_zone = zones.get('nearest_large_long')
        
        if direction == 'long' and large_short_zone:
            dist = large_short_zone.get('distance_pct', 999)
            if dist <= MAGNET_RANGE_PCT:
                score_adj += MAGNET_BOOST
                reasons.append(f"SHORT squeeze magnet at ${large_short_zone.get('price', '?')}")
                logger.info(f"🧲 {self.name}: Large short liquidation zone above - squeeze potential")
        
        elif direction == 'short' and large_long_zone:
            dist = large_long_zone.get('distance_pct', 999)
            if dist <= MAGNET_RANGE_PCT:
                score_adj += MAGNET_BOOST
                reasons.append(f"LONG dump magnet at ${large_long_zone.get('price', '?')}")
                logger.info(f"🧲 {self.name}: Large long liquidation zone below - dump potential")
        
        # 3. CASCADE DETECTION
        cascade_active = flow.get('cascade_active', False)
        cascade_side = flow.get('cascade_side')
        
        if cascade_active and cascade_side:
            # Cascade side = which positions are getting liquidated
            # longs cascade = price dropping = bearish
            # shorts cascade = price rising = bullish
            
            if cascade_side == 'longs':
                # Longs getting liquidated = bearish momentum
                if direction == 'long':
                    score_adj -= CASCADE_PENALTY
                    reasons.append("CASCADE: Longs getting liquidated - dangerous to go long")
                    logger.warning(f"🌊 {self.name}: Trading LONG into long liquidation cascade!")
                elif direction == 'short':
                    score_adj += CASCADE_BOOST
                    reasons.append("CASCADE: Riding short momentum")
                    logger.info(f"🌊 {self.name}: Riding the long liquidation cascade short")
            
            elif cascade_side == 'shorts':
                # Shorts getting liquidated = bullish momentum
                if direction == 'short':
                    score_adj -= CASCADE_PENALTY
                    reasons.append("CASCADE: Shorts getting liquidated - dangerous to go short")
                    logger.warning(f"🌊 {self.name}: Trading SHORT into short liquidation cascade!")
                elif direction == 'long':
                    score_adj += CASCADE_BOOST
                    reasons.append("CASCADE: Riding long momentum")
                    logger.info(f"🌊 {self.name}: Riding the short squeeze long")
        
        # 4. EXHAUSTION SIGNAL
        exhaustion = flow.get('exhaustion_signal', False)
        
        if exhaustion and cascade_side:
            # Exhaustion after cascade = potential reversal
            if cascade_side == 'longs' and direction == 'long':
                score_adj += EXHAUSTION_BOOST
                reasons.append("Exhaustion: Long liquidations drying up")
                logger.info(f"💨 {self.name}: Long cascade exhaustion - contrarian opportunity")
            elif cascade_side == 'shorts' and direction == 'short':
                score_adj += EXHAUSTION_BOOST
                reasons.append("Exhaustion: Short liquidations drying up")
                logger.info(f"💨 {self.name}: Short cascade exhaustion - contrarian opportunity")
        
        # Store final adjustment
        self.last_score_adjustment = score_adj
        
        # Build reason string
        if not reasons:
            reason = f"Liquidation zones OK | Long zone: {long_zone_dist:.1f}% | Short zone: {short_zone_dist:.1f}%"
        else:
            reason = " | ".join(reasons) + f" | Score: {score_adj:+d}"
        
        # Log summary
        if score_adj > 0:
            logger.info(f"✅ {self.name}: {reason}")
        elif score_adj < 0:
            logger.warning(f"⚠️  {self.name}: {reason}")
        else:
            logger.debug(f"ℹ️  {self.name}: {reason}")
        
        # Never hard reject - use score adjustments
        return True, reason
    
    def get_liquidation_status(self) -> Dict:
        """
        Get current liquidation status for dashboard display.
        
        Returns:
            Dict with comprehensive liquidation status
        """
        if not self.tracker:
            return {
                'enabled': False,
                'message': 'Liquidation tracker not initialized',
                'bias': 'neutral',
                'emoji': '❓'
            }
        
        return self.tracker.get_status()
    
    def get_zone_summary(self, current_price: float = None) -> Dict:
        """
        Get a summary of liquidation zones.
        
        Args:
            current_price: Optional current price (uses cached if not provided)
            
        Returns:
            Dict with zone summary
        """
        if not self.tracker:
            return {}
        
        if current_price:
            zones = self.tracker.calculate_liquidation_zones(current_price)
        else:
            zones = self.tracker.last_zone_analysis or {}
        
        return {
            'nearest_long_zone': zones.get('nearest_long_liq'),
            'nearest_short_zone': zones.get('nearest_short_liq'),
            'nearest_large_long': zones.get('nearest_large_long'),
            'nearest_large_short': zones.get('nearest_large_short'),
            'long_zone_distance_pct': zones.get('long_zone_distance_pct', 999),
            'short_zone_distance_pct': zones.get('short_zone_distance_pct', 999)
        }
    
    def refresh_data(self) -> bool:
        """
        Force refresh liquidation data.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.tracker:
            return False
        
        try:
            self.tracker.last_api_fetch = None  # Clear cache
            self.tracker.fetch_recent_liquidations()
            return True
        except Exception as e:
            logger.error(f"{self.name}: Error refreshing data: {e}")
            return False
