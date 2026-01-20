"""
Elite Market Structure Intelligence Module

Provides institutional-grade market analysis:
1. Support/Resistance Detection - Finds key price levels automatically
2. Market Structure Analysis - Higher highs, lower lows, structure breaks
3. Volume Profile - High volume nodes as dynamic S/R

This module enables the system to "see" the market like a professional trader,
not just look for specific patterns.

Usage:
    from data_feed.market_structure import MarketStructureAnalyzer
    
    analyzer = MarketStructureAnalyzer()
    analysis = analyzer.analyze(candles)
    
    # Returns:
    # - support_levels: List of support prices
    # - resistance_levels: List of resistance prices
    # - structure: 'bullish', 'bearish', or 'ranging'
    # - structure_break: True if recent structure break
    # - volume_nodes: High volume price zones
    # - trend_bias: -1 to +1 directional bias
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PriceLevel:
    """Represents a support/resistance level."""
    price: float
    strength: int  # Number of touches
    level_type: str  # 'support' or 'resistance'
    last_touch: datetime
    is_broken: bool = False


@dataclass 
class StructurePoint:
    """Represents a swing high or swing low."""
    price: float
    index: int
    point_type: str  # 'high' or 'low'
    timestamp: Optional[datetime] = None


@dataclass
class VolumeNode:
    """Represents a high-volume price zone."""
    price_low: float
    price_high: float
    volume: float
    is_high_volume: bool


class MarketStructureAnalyzer:
    """
    Elite Market Structure Analysis.
    
    Detects:
    - Support/Resistance levels (price touches)
    - Market structure (HH, HL, LH, LL patterns)
    - Structure breaks (trend reversals)
    - Volume profile (where liquidity sits)
    """
    
    def __init__(self, 
                 level_tolerance_pct: float = 0.5,
                 min_touches: int = 2,
                 swing_lookback: int = 5,
                 volume_bins: int = 20):
        """
        Initialize analyzer.
        
        Args:
            level_tolerance_pct: How close price must be to count as "touch" (%)
            min_touches: Minimum touches to confirm S/R level
            swing_lookback: Bars to look back for swing detection
            volume_bins: Number of price bins for volume profile
        """
        self.level_tolerance_pct = level_tolerance_pct
        self.min_touches = min_touches
        self.swing_lookback = swing_lookback
        self.volume_bins = volume_bins
        
        # Cache
        self._cached_levels: List[PriceLevel] = []
        self._cached_structure: List[StructurePoint] = []
        
        logger.info(f"✅ MarketStructureAnalyzer: Initialized (elite mode)")
    
    def analyze(self, candles: List[Dict]) -> Dict:
        """
        Perform complete market structure analysis.
        
        Args:
            candles: List of OHLCV candles
            
        Returns:
            Dict with complete analysis
        """
        if len(candles) < 30:
            return self._empty_analysis()
        
        # Extract price data
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        closes = [c['close'] for c in candles]
        volumes = [c.get('volume', 0) for c in candles]
        
        current_price = closes[-1]
        
        # 1. Detect Support/Resistance
        support_levels, resistance_levels = self._detect_sr_levels(highs, lows, closes, current_price)
        
        # 2. Analyze Market Structure
        swing_points = self._find_swing_points(highs, lows)
        structure, structure_break, break_direction = self._analyze_structure(swing_points, current_price)
        
        # 3. Build Volume Profile
        volume_nodes, high_volume_zones = self._build_volume_profile(closes, volumes)
        
        # 4. Calculate overall bias
        trend_bias = self._calculate_trend_bias(
            structure, swing_points, closes, support_levels, resistance_levels
        )
        
        # 5. Find nearest levels
        nearest_support = self._find_nearest_level(current_price, support_levels, 'below')
        nearest_resistance = self._find_nearest_level(current_price, resistance_levels, 'above')
        
        # 6. Detect if at key level
        at_support = self._is_at_level(current_price, support_levels)
        at_resistance = self._is_at_level(current_price, resistance_levels)
        
        analysis = {
            'current_price': current_price,
            
            # Support/Resistance
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'at_support': at_support,
            'at_resistance': at_resistance,
            
            # Market Structure
            'structure': structure,  # 'bullish', 'bearish', 'ranging'
            'structure_break': structure_break,
            'break_direction': break_direction,  # 'bullish', 'bearish', or None
            'swing_points': swing_points[-6:] if len(swing_points) >= 6 else swing_points,
            
            # Volume Profile
            'volume_nodes': volume_nodes,
            'high_volume_zones': high_volume_zones,
            
            # Overall
            'trend_bias': trend_bias,  # -1 to +1
            'analysis_quality': 'good' if len(candles) >= 50 else 'limited'
        }
        
        return analysis
    
    def _detect_sr_levels(self, highs: List[float], lows: List[float], 
                          closes: List[float], current_price: float) -> Tuple[List[float], List[float]]:
        """
        Detect support and resistance levels.
        
        Uses multiple methods:
        1. Swing highs/lows
        2. Price clustering
        3. Round numbers
        """
        support_levels = []
        resistance_levels = []
        
        tolerance = current_price * (self.level_tolerance_pct / 100)
        
        # Method 1: Swing highs and lows
        swing_highs = []
        swing_lows = []
        
        lookback = self.swing_lookback
        for i in range(lookback, len(highs) - lookback):
            # Swing high
            if highs[i] == max(highs[i-lookback:i+lookback+1]):
                swing_highs.append(highs[i])
            # Swing low
            if lows[i] == min(lows[i-lookback:i+lookback+1]):
                swing_lows.append(lows[i])
        
        # Cluster similar levels
        resistance_levels = self._cluster_levels(swing_highs, tolerance)
        support_levels = self._cluster_levels(swing_lows, tolerance)
        
        # Method 2: Add round number levels near price
        round_levels = self._get_round_numbers(current_price)
        for level in round_levels:
            if level > current_price and level not in resistance_levels:
                resistance_levels.append(level)
            elif level < current_price and level not in support_levels:
                support_levels.append(level)
        
        # Sort and filter to nearest levels
        support_levels = sorted([s for s in support_levels if s < current_price], reverse=True)[:5]
        resistance_levels = sorted([r for r in resistance_levels if r > current_price])[:5]
        
        return support_levels, resistance_levels
    
    def _cluster_levels(self, levels: List[float], tolerance: float) -> List[float]:
        """Cluster nearby levels into single level."""
        if not levels:
            return []
        
        levels = sorted(levels)
        clusters = []
        current_cluster = [levels[0]]
        
        for level in levels[1:]:
            if level - current_cluster[-1] <= tolerance:
                current_cluster.append(level)
            else:
                # Average of cluster
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [level]
        
        clusters.append(sum(current_cluster) / len(current_cluster))
        return clusters
    
    def _get_round_numbers(self, price: float) -> List[float]:
        """Get psychologically significant round numbers near price."""
        levels = []
        
        # Determine increment based on price magnitude
        if price > 100:
            increments = [10, 25, 50, 100]
        elif price > 10:
            increments = [1, 5, 10, 25]
        else:
            increments = [0.5, 1, 2.5, 5]
        
        for inc in increments:
            # Levels above and below
            base = int(price / inc) * inc
            levels.extend([base - inc, base, base + inc, base + 2*inc])
        
        return list(set(levels))
    
    def _find_swing_points(self, highs: List[float], lows: List[float]) -> List[StructurePoint]:
        """Find swing highs and lows for structure analysis."""
        swing_points = []
        lookback = self.swing_lookback
        
        for i in range(lookback, len(highs) - lookback):
            # Swing high
            if highs[i] == max(highs[i-lookback:i+lookback+1]):
                swing_points.append(StructurePoint(
                    price=highs[i],
                    index=i,
                    point_type='high'
                ))
            # Swing low
            if lows[i] == min(lows[i-lookback:i+lookback+1]):
                swing_points.append(StructurePoint(
                    price=lows[i],
                    index=i,
                    point_type='low'
                ))
        
        # Sort by index
        swing_points.sort(key=lambda x: x.index)
        return swing_points
    
    def _analyze_structure(self, swing_points: List[StructurePoint], 
                           current_price: float) -> Tuple[str, bool, Optional[str]]:
        """
        Analyze market structure from swing points.
        
        Returns:
            (structure, structure_break, break_direction)
            - structure: 'bullish', 'bearish', or 'ranging'
            - structure_break: True if recent structure break
            - break_direction: Direction of break if any
        """
        if len(swing_points) < 4:
            return 'ranging', False, None
        
        # Get recent swing highs and lows
        recent_highs = [p for p in swing_points[-8:] if p.point_type == 'high']
        recent_lows = [p for p in swing_points[-8:] if p.point_type == 'low']
        
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            return 'ranging', False, None
        
        # Check for higher highs, higher lows (bullish)
        # or lower highs, lower lows (bearish)
        
        hh = recent_highs[-1].price > recent_highs[-2].price  # Higher high
        hl = recent_lows[-1].price > recent_lows[-2].price   # Higher low
        lh = recent_highs[-1].price < recent_highs[-2].price  # Lower high
        ll = recent_lows[-1].price < recent_lows[-2].price   # Lower low
        
        # Determine structure
        if hh and hl:
            structure = 'bullish'
        elif lh and ll:
            structure = 'bearish'
        else:
            structure = 'ranging'
        
        # Check for structure break
        structure_break = False
        break_direction = None
        
        # Bullish break: Price breaks above recent lower high in downtrend
        # Bearish break: Price breaks below recent higher low in uptrend
        
        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            last_high = recent_highs[-1].price
            last_low = recent_lows[-1].price
            prev_high = recent_highs[-2].price
            prev_low = recent_lows[-2].price
            
            # Bearish structure break (price breaks below higher low)
            if structure == 'bullish' or (hl and not ll):
                if current_price < last_low:
                    structure_break = True
                    break_direction = 'bearish'
            
            # Bullish structure break (price breaks above lower high)
            if structure == 'bearish' or (lh and not hh):
                if current_price > last_high:
                    structure_break = True
                    break_direction = 'bullish'
        
        return structure, structure_break, break_direction
    
    def _build_volume_profile(self, closes: List[float], 
                              volumes: List[float]) -> Tuple[List[VolumeNode], List[Tuple[float, float]]]:
        """
        Build volume profile to find high-volume zones.
        """
        if not volumes or sum(volumes) == 0:
            return [], []
        
        price_min = min(closes)
        price_max = max(closes)
        price_range = price_max - price_min
        
        if price_range == 0:
            return [], []
        
        bin_size = price_range / self.volume_bins
        
        # Accumulate volume in each price bin
        volume_by_bin = [0.0] * self.volume_bins
        
        for close, vol in zip(closes, volumes):
            bin_idx = min(int((close - price_min) / bin_size), self.volume_bins - 1)
            volume_by_bin[bin_idx] += vol
        
        # Find high volume nodes (above average)
        avg_volume = sum(volume_by_bin) / self.volume_bins
        
        volume_nodes = []
        high_volume_zones = []
        
        for i, vol in enumerate(volume_by_bin):
            node = VolumeNode(
                price_low=price_min + i * bin_size,
                price_high=price_min + (i + 1) * bin_size,
                volume=vol,
                is_high_volume=vol > avg_volume * 1.5
            )
            volume_nodes.append(node)
            
            if node.is_high_volume:
                high_volume_zones.append((node.price_low, node.price_high))
        
        return volume_nodes, high_volume_zones
    
    def _calculate_trend_bias(self, structure: str, swing_points: List[StructurePoint],
                              closes: List[float], support_levels: List[float],
                              resistance_levels: List[float]) -> float:
        """
        Calculate overall trend bias from -1 (very bearish) to +1 (very bullish).
        """
        bias = 0.0
        
        # Structure bias
        if structure == 'bullish':
            bias += 0.4
        elif structure == 'bearish':
            bias -= 0.4
        
        # Price position bias
        if len(closes) >= 20:
            sma_20 = sum(closes[-20:]) / 20
            current = closes[-1]
            
            if current > sma_20:
                bias += 0.2
            else:
                bias -= 0.2
        
        # Momentum bias (recent closes)
        if len(closes) >= 5:
            recent_direction = closes[-1] - closes[-5]
            if recent_direction > 0:
                bias += 0.2
            else:
                bias -= 0.2
        
        # Distance to S/R bias
        current_price = closes[-1]
        if support_levels and resistance_levels:
            dist_to_support = current_price - support_levels[0] if support_levels else float('inf')
            dist_to_resistance = resistance_levels[0] - current_price if resistance_levels else float('inf')
            
            # Closer to support = slightly bullish (bounce potential)
            # Closer to resistance = slightly bearish (rejection potential)
            if dist_to_support < dist_to_resistance:
                bias += 0.1
            else:
                bias -= 0.1
        
        return max(-1.0, min(1.0, bias))
    
    def _find_nearest_level(self, price: float, levels: List[float], 
                            direction: str) -> Optional[float]:
        """Find nearest level above or below price."""
        if not levels:
            return None
        
        if direction == 'below':
            below = [l for l in levels if l < price]
            return max(below) if below else None
        else:
            above = [l for l in levels if l > price]
            return min(above) if above else None
    
    def _is_at_level(self, price: float, levels: List[float]) -> bool:
        """Check if price is at a key level."""
        tolerance = price * (self.level_tolerance_pct / 100)
        for level in levels:
            if abs(price - level) <= tolerance:
                return True
        return False
    
    def _empty_analysis(self) -> Dict:
        """Return empty analysis when not enough data."""
        return {
            'current_price': 0,
            'support_levels': [],
            'resistance_levels': [],
            'nearest_support': None,
            'nearest_resistance': None,
            'at_support': False,
            'at_resistance': False,
            'structure': 'unknown',
            'structure_break': False,
            'break_direction': None,
            'swing_points': [],
            'volume_nodes': [],
            'high_volume_zones': [],
            'trend_bias': 0.0,
            'analysis_quality': 'insufficient_data'
        }
    
    def get_trade_setup(self, analysis: Dict) -> Optional[Dict]:
        """
        Determine if there's a tradeable setup based on analysis.
        
        STRICT VERSION - Only high-confidence setups.
        Previous version generated too many losing trades (88 trades, 24% win rate).
        
        Returns setup dict if found, None otherwise.
        """
        if analysis['analysis_quality'] == 'insufficient_data':
            return None
        
        current_price = analysis['current_price']
        structure = analysis['structure']
        structure_break = analysis['structure_break']
        break_direction = analysis['break_direction']
        at_support = analysis['at_support']
        at_resistance = analysis['at_resistance']
        trend_bias = analysis['trend_bias']
        
        setup = None
        
        # STRICT: Only structure breaks pass (highest quality signal)
        # Structure break = confirmed trend reversal
        if structure_break and break_direction:
            # Additional confirmation: trend bias should align with break direction
            bias_confirms = (break_direction == 'bullish' and trend_bias > 0) or \
                           (break_direction == 'bearish' and trend_bias < 0)
            
            if bias_confirms:
                setup = {
                    'type': 'structure_break',
                    'direction': 'long' if break_direction == 'bullish' else 'short',
                    'reason': f'Structure break {break_direction} (bias confirms: {trend_bias:.2f})',
                    'confidence': 0.75  # High confidence for confirmed break
                }
            else:
                # Break without bias confirmation - still valid but lower confidence
                setup = {
                    'type': 'structure_break',
                    'direction': 'long' if break_direction == 'bullish' else 'short',
                    'reason': f'Structure break {break_direction} (no bias confirm)',
                    'confidence': 0.70
                }
        
        # REMOVED: Support bounce, resistance rejection, trend continuation
        # These were generating too many false signals
        # Only structure breaks are reliable enough
        
        return setup
    
    def get_status(self) -> Dict:
        """Get analyzer status for dashboard."""
        return {
            'enabled': True,
            'level_tolerance_pct': self.level_tolerance_pct,
            'min_touches': self.min_touches,
            'swing_lookback': self.swing_lookback
        }
