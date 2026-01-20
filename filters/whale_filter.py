"""
Whale Movement Filter (Phase 3.1 Elite)

Uses on-chain data to detect whale positioning and exchange flows.
Integrates with OnchainTracker to provide trading signals.

Signals:
- Net exchange INFLOW = Whales depositing to sell = BEARISH
- Net exchange OUTFLOW = Whales withdrawing to hold = BULLISH

Score adjustments based on flow magnitude and confidence.
"""

from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class WhaleFilter:
    """
    Whale movement filter (Phase 3.1 Elite).
    
    Uses on-chain data to detect whale positioning:
    - Net exchange inflow = whales preparing to sell = BEARISH
    - Net exchange outflow = whales accumulating = BULLISH
    
    Features:
    - Score adjustments (not binary pass/fail)
    - Confidence levels (low/medium/high)
    - Graceful degradation without API key
    - Dashboard-ready status reporting
    """
    
    def __init__(self):
        self.name = "WhaleFlow"
        self.last_score_adjustment = 0
        self.tracker = None
        self.enabled = False
        
        # Initialize tracker
        self._init_tracker()
    
    def _init_tracker(self):
        """Initialize the on-chain tracker."""
        try:
            from data_feed.onchain_tracker import OnchainTracker
            self.tracker = OnchainTracker()
            self.enabled = self.tracker.api_available
            
            if self.enabled:
                logger.info(f"✅ {self.name}: Initialized with OnchainTracker")
            else:
                logger.warning(f"⚠️  {self.name}: Running in DEGRADED mode (no API key)")
                
        except Exception as e:
            logger.warning(f"⚠️  {self.name}: Could not initialize tracker: {e}")
            self.tracker = None
            self.enabled = False
    
    def check(self, market_state: Dict = None, signal_direction: str = '') -> Tuple[bool, str]:
        """
        Check whale positioning relative to signal direction.
        
        Args:
            market_state: Market state (not used, kept for interface consistency)
            signal_direction: 'long' or 'short'
            
        Returns:
            (passed: bool, reason: str)
        """
        import config
        
        # Check if filter is enabled
        if not getattr(config, 'WHALE_TRACKING_ENABLED', True):
            return True, "Whale tracking disabled"
        
        # Check if tracker is available
        if not self.tracker:
            return True, "Whale tracker not available"
        
        # Get flow analysis (uses 4-hour window by default)
        lookback_hours = getattr(config, 'WHALE_LOOKBACK_HOURS', 4)
        analysis = self.tracker.analyze_flow(hours=lookback_hours)
        
        direction = signal_direction.lower() if signal_direction else ''
        bias = analysis['bias']
        confidence = analysis['confidence']
        net_flow = analysis['net_flow_sol']
        
        # Get score adjustment for this direction
        if direction == 'long':
            score_adj = analysis['score_adjustment_long']
        elif direction == 'short':
            score_adj = analysis['score_adjustment_short']
        else:
            score_adj = 0
        
        self.last_score_adjustment = score_adj
        
        # Format flow for display
        if abs(net_flow) >= 1000000:
            flow_str = f"{net_flow/1000000:+.1f}M SOL"
        elif abs(net_flow) >= 1000:
            flow_str = f"{net_flow/1000:+.1f}k SOL"
        else:
            flow_str = f"{net_flow:+,.0f} SOL"
        
        # No data or degraded mode
        if not self.tracker.api_available:
            reason = "Whale tracking: No API (degraded mode)"
            logger.info(f"ℹ️  {self.name}: {reason}")
            return True, reason
        
        # Neutral flow
        if bias == 'neutral':
            reason = f"Whale flow neutral ({flow_str})"
            logger.info(f"ℹ️  {self.name}: {reason}")
            return True, reason
        
        # Non-neutral flow - build detailed reason
        exchanges = analysis.get('exchanges_involved', [])
        exchange_str = f" via {', '.join(exchanges[:2])}" if exchanges else ""
        
        reason = f"Whales {bias.upper()} ({flow_str}{exchange_str}) | Conf: {confidence} | Score: {score_adj:+d}"
        
        # Log based on alignment with signal
        signal_aligns_with_whales = (
            (direction == 'long' and bias == 'bullish') or
            (direction == 'short' and bias == 'bearish')
        )
        
        if signal_aligns_with_whales:
            logger.info(f"🐋 {self.name}: {reason} - ALIGNED with whale flow!")
        elif score_adj <= -15:
            logger.warning(f"⚠️  {self.name}: {reason} - Trading AGAINST whales")
        elif score_adj < 0:
            logger.info(f"📊 {self.name}: {reason}")
        else:
            logger.info(f"✅ {self.name}: {reason}")
        
        # Never hard reject - use score adjustments for flexibility
        return True, reason
    
    def get_whale_status(self) -> Dict:
        """
        Get current whale status for dashboard display.
        
        Returns:
            Dict with comprehensive whale status
        """
        if not self.tracker:
            return {
                'enabled': False,
                'degraded_mode': True,
                'bias': 'neutral',
                'emoji': '❓',
                'message': 'Whale tracker not initialized',
                'score_long': 0,
                'score_short': 0
            }
        
        return self.tracker.get_status()
    
    def get_recommendation(self) -> str:
        """
        Get simple recommendation based on whale flow.
        
        Returns:
            'FAVOR_LONGS' | 'FAVOR_SHORTS' | 'NEUTRAL'
        """
        if not self.tracker or not self.tracker.last_analysis:
            return 'NEUTRAL'
        
        bias = self.tracker.last_analysis.get('bias', 'neutral')
        
        if bias == 'bullish':
            return 'FAVOR_LONGS'
        elif bias == 'bearish':
            return 'FAVOR_SHORTS'
        return 'NEUTRAL'
    
    def refresh_data(self) -> bool:
        """
        Force refresh whale data (bypass cache).
        
        Returns:
            True if successful, False otherwise
        """
        if not self.tracker:
            return False
        
        try:
            # Clear cache to force fresh fetch
            self.tracker.last_fetch_time = None
            self.tracker.fetch_recent_transfers()
            return True
        except Exception as e:
            logger.error(f"{self.name}: Error refreshing data: {e}")
            return False
