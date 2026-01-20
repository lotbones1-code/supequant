"""
Confidence Engine V2 - Phase 2 Module 1

Enhanced confidence scoring that uses historical performance data
from Phase 1.5 analytics to refine confidence scores and suggest
position sizing.

Features:
- Filter effectiveness scoring (from FilterScorer)
- Time-of-day performance scoring (from TradeQualityInspector)
- Confluence scoring (number of filters passed)
- Market condition scoring (volatility + trend)
- Position size multiplier recommendations

Usage:
    from utils.confidence_v2 import ConfidenceEngineV2
    
    engine = ConfidenceEngineV2()
    result = engine.compute_confidence({
        "symbol": "SOL",
        "direction": "long",
        "base_confidence": 75,
        "filters_passed": ["volume_filter", "momentum_filter"],
        "timestamp": "2026-01-18T14:30:00Z",
        "volatility": 0.02,
        "trend_strength": 0.65
    })
    print(engine.explain(result))

Note: This is READ-ONLY analytics. Does not affect trading until
explicitly wired into the strategy layer.
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class ConfidenceEngineV2:
    """
    Confidence scoring V2 - Uses historical performance data to refine
    confidence scores and suggest position sizing.
    
    Leverages Phase 1.5 modules:
    - FilterScorer: Filter effectiveness data
    - TradeQualityInspector: Hourly and duration patterns
    """
    
    # Configurable position size multipliers by confidence band
    SIZE_MULTIPLIERS = {
        'LOW': 0.5,      # Half size on low confidence
        'MEDIUM': 1.0,   # Normal size
        'HIGH': 1.3,     # Slightly larger
        'ELITE': 1.5     # Max confidence boost
    }
    
    # Confidence band thresholds
    BAND_THRESHOLDS = {
        'LOW': (0, 39),
        'MEDIUM': (40, 59),
        'HIGH': (60, 79),
        'ELITE': (80, 100)
    }
    
    # Component weights for adjustment calculation
    # Total max adjustment: +/- 32 points
    WEIGHTS = {
        'filter': 10,      # Max +/- 10 points from filter effectiveness
        'time_of_day': 8,  # Max +/- 8 points from hour performance
        'confluence': 8,   # Max +/- 8 points from filter count
        'market': 6        # Max +/- 6 points from market conditions
    }
    
    # Minimum trades required for reliable scoring
    MIN_TRADES_FOR_SCORING = 5
    
    def __init__(self, trade_journal_path: str = 'runs'):
        """
        Initialize the confidence engine.
        
        Args:
            trade_journal_path: Path to trade journal files
        """
        self.trade_journal_path = trade_journal_path
        
        # Lazy load Phase 1.5 modules
        self._filter_scorer = None
        self._quality_inspector = None
        self._data_loaded = False
        
        logger.info("📊 ConfidenceEngineV2 initialized")
    
    def _ensure_data_loaded(self):
        """Lazy load the Phase 1.5 analytics modules."""
        if self._data_loaded:
            return
        
        try:
            from utils.filter_scorer import FilterScorer
            self._filter_scorer = FilterScorer(self.trade_journal_path)
        except ImportError:
            logger.warning("FilterScorer not available")
            self._filter_scorer = None
        except Exception as e:
            logger.warning(f"Could not load FilterScorer: {e}")
            self._filter_scorer = None
        
        try:
            from utils.trade_quality import TradeQualityInspector
            self._quality_inspector = TradeQualityInspector(self.trade_journal_path)
        except ImportError:
            logger.warning("TradeQualityInspector not available")
            self._quality_inspector = None
        except Exception as e:
            logger.warning(f"Could not load TradeQualityInspector: {e}")
            self._quality_inspector = None
        
        self._data_loaded = True
    
    def _get_trade_count(self) -> int:
        """Get the number of trades available for analysis."""
        self._ensure_data_loaded()
        if self._quality_inspector:
            return len(self._quality_inspector.trades)
        return 0
    
    def _score_filters(self, filters_passed: List[str]) -> float:
        """
        Score based on filter effectiveness.
        
        Uses FilterScorer to look up each filter's historical precision
        and contribution to win rate.
        
        Args:
            filters_passed: List of filter names that passed
            
        Returns:
            Score in range [-1.0, +1.0]
        """
        if not filters_passed:
            return 0.0
        
        self._ensure_data_loaded()
        
        if not self._filter_scorer:
            return 0.0
        
        scores = []
        for filter_name in filters_passed:
            try:
                filter_data = self._filter_scorer.score_filter(filter_name)
                
                # Check if we have meaningful data
                if filter_data.get('status') in ['no_data', 'low_data']:
                    continue
                
                precision = filter_data.get('precision', 50)
                contribution = filter_data.get('contribution', 0)
                
                # Map precision + contribution to score
                # Precision > 70% with positive contribution = good
                # Precision < 50% = bad
                if precision >= 70 and contribution > 0:
                    score = 0.5 + min(contribution / 20, 0.5)  # 0.5 to 1.0
                elif precision >= 60:
                    score = 0.2  # Moderately good
                elif precision >= 50:
                    score = 0.0  # Neutral
                elif precision >= 40:
                    score = -0.3  # Slightly bad
                else:
                    score = -0.6  # Bad filter
                
                scores.append(score)
                
            except Exception as e:
                logger.debug(f"Could not score filter {filter_name}: {e}")
                continue
        
        if not scores:
            return 0.0
        
        # Return average score
        return sum(scores) / len(scores)
    
    def _score_time_of_day(self, timestamp: str) -> float:
        """
        Score based on time-of-day performance.
        
        Uses TradeQualityInspector to look up win rate for the hour.
        
        Args:
            timestamp: ISO format timestamp
            
        Returns:
            Score in range [-1.0, +1.0]
        """
        if not timestamp:
            return 0.0
        
        self._ensure_data_loaded()
        
        if not self._quality_inspector:
            return 0.0
        
        try:
            # Parse timestamp and extract hour
            if timestamp.endswith('Z'):
                timestamp = timestamp.replace('Z', '+00:00')
            dt = datetime.fromisoformat(timestamp)
            hour = dt.hour
            
            # Get hourly analysis
            hourly_data = self._quality_inspector.analyze_trade_by_hour()
            
            if not hourly_data.get('has_data'):
                return 0.0
            
            hourly_stats = hourly_data.get('hourly_stats', {})
            hour_stats = hourly_stats.get(hour)
            
            if not hour_stats or hour_stats.get('trades', 0) < 3:
                return 0.0  # Not enough data for this hour
            
            win_rate = hour_stats.get('win_rate', 50)
            
            # Map win rate to score
            # 70%+ → +1.0, 60% → +0.5, 50% → 0, 40% → -0.5, 30% → -1.0
            if win_rate >= 70:
                return 1.0
            elif win_rate >= 60:
                return 0.5 + (win_rate - 60) / 20  # 0.5 to 1.0
            elif win_rate >= 50:
                return (win_rate - 50) / 20  # 0 to 0.5
            elif win_rate >= 40:
                return (win_rate - 50) / 20  # -0.5 to 0
            elif win_rate >= 30:
                return -0.5 - (40 - win_rate) / 20  # -0.5 to -1.0
            else:
                return -1.0
                
        except Exception as e:
            logger.debug(f"Could not score time of day: {e}")
            return 0.0
    
    def _score_confluence(self, filters_passed: List[str]) -> float:
        """
        Score based on number of filters passed (confluence).
        
        More filters passing generally indicates stronger signal,
        but we use historical data when available.
        
        Args:
            filters_passed: List of filter names that passed
            
        Returns:
            Score in range [-1.0, +1.0]
        """
        num_filters = len(filters_passed) if filters_passed else 0
        
        # Simple heuristic based on filter count
        # Can be enhanced with historical confluence data later
        if num_filters == 0:
            return -0.5  # No filter validation is risky
        elif num_filters == 1:
            return -0.2  # Single filter is weak
        elif num_filters == 2:
            return 0.0   # Two filters is baseline
        elif num_filters == 3:
            return 0.2   # Good confluence
        elif num_filters == 4:
            return 0.4   # Strong confluence
        else:
            return 0.5   # Very strong confluence (5+)
    
    def _score_market_conditions(self, volatility: float, trend_strength: float) -> float:
        """
        Score based on current market conditions.
        
        Prefers trending markets with moderate volatility.
        Penalizes choppy/high-vol environments.
        
        Args:
            volatility: Realized volatility (typically 0.01-0.05)
            trend_strength: Trend strength 0-1
            
        Returns:
            Score in range [-1.0, +1.0]
        """
        # Default values if not provided
        if volatility is None:
            volatility = 0.02
        if trend_strength is None:
            trend_strength = 0.5
        
        # Ideal conditions: strong trend (>0.6), moderate vol (0.015-0.025)
        # Bad conditions: weak trend (<0.3), high vol (>0.04)
        
        # Score trend strength (0-1 → -0.5 to +0.5)
        if trend_strength >= 0.7:
            trend_score = 0.5
        elif trend_strength >= 0.5:
            trend_score = (trend_strength - 0.5) * 2.5  # 0 to 0.5
        elif trend_strength >= 0.3:
            trend_score = (trend_strength - 0.5) * 2.5  # -0.5 to 0
        else:
            trend_score = -0.5
        
        # Score volatility (prefer moderate)
        if 0.015 <= volatility <= 0.025:
            vol_score = 0.3  # Ideal range
        elif 0.01 <= volatility <= 0.03:
            vol_score = 0.1  # Acceptable
        elif volatility < 0.01:
            vol_score = -0.2  # Too quiet, might be false signals
        elif volatility <= 0.04:
            vol_score = -0.2  # Getting choppy
        else:
            vol_score = -0.5  # Too volatile
        
        # Combine (trend matters more than vol)
        combined = trend_score * 0.7 + vol_score * 0.3
        
        return max(-1.0, min(1.0, combined))
    
    def compute_confidence(self, signal_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute enhanced confidence score from signal context.
        
        Args:
            signal_context: Dict containing:
                - symbol: Trading symbol (e.g., "SOL")
                - direction: "long" or "short"
                - base_confidence: Original confidence score (0-100)
                - filters_passed: List of filter names that passed
                - timestamp: ISO format timestamp
                - volatility: Optional, realized volatility
                - trend_strength: Optional, trend strength 0-1
                
        Returns:
            Dict with adjusted confidence, band, and sizing recommendation
        """
        # Extract inputs with defaults
        symbol = signal_context.get('symbol', 'UNKNOWN')
        direction = signal_context.get('direction', 'long')
        base_confidence = signal_context.get('base_confidence', 50)
        filters_passed = signal_context.get('filters_passed', [])
        timestamp = signal_context.get('timestamp', '')
        volatility = signal_context.get('volatility')
        trend_strength = signal_context.get('trend_strength')
        
        # Calculate component scores
        filter_score = self._score_filters(filters_passed)
        tod_score = self._score_time_of_day(timestamp)
        conf_score = self._score_confluence(filters_passed)
        market_score = self._score_market_conditions(volatility, trend_strength)
        
        # Calculate total adjustment
        adjustment = (
            filter_score * self.WEIGHTS['filter'] +
            tod_score * self.WEIGHTS['time_of_day'] +
            conf_score * self.WEIGHTS['confluence'] +
            market_score * self.WEIGHTS['market']
        )
        
        # Apply adjustment and clamp
        adjusted_confidence = max(0, min(100, base_confidence + adjustment))
        
        # Determine confidence band
        band = 'MEDIUM'
        for band_name, (low, high) in self.BAND_THRESHOLDS.items():
            if low <= adjusted_confidence <= high:
                band = band_name
                break
        
        # Get position size multiplier
        multiplier = self.SIZE_MULTIPLIERS.get(band, 1.0)
        
        # Check data quality
        trade_count = self._get_trade_count()
        data_quality = 'good' if trade_count >= self.MIN_TRADES_FOR_SCORING else 'limited'
        
        return {
            'symbol': symbol,
            'direction': direction,
            'base_confidence': base_confidence,
            'adjusted_confidence': round(adjusted_confidence, 1),
            'adjustment': round(adjustment, 1),
            'confidence_band': band,
            'position_size_multiplier': multiplier,
            'components': {
                'filter_score': round(filter_score, 3),
                'time_of_day_score': round(tod_score, 3),
                'confluence_score': round(conf_score, 3),
                'market_score': round(market_score, 3)
            },
            'data_quality': data_quality,
            'trades_analyzed': trade_count
        }
    
    def explain(self, signal_context: Dict[str, Any]) -> str:
        """
        Generate human-readable explanation of confidence calculation.
        
        Args:
            signal_context: Same as compute_confidence
            
        Returns:
            Formatted explanation string
        """
        result = self.compute_confidence(signal_context)
        
        symbol = result['symbol']
        direction = result['direction'].upper()
        base = result['base_confidence']
        adjusted = result['adjusted_confidence']
        band = result['confidence_band']
        multiplier = result['position_size_multiplier']
        components = result['components']
        data_quality = result['data_quality']
        trades = result['trades_analyzed']
        
        # Build explanation
        lines = []
        lines.append(f"Confidence V2: {symbol} {direction}")
        lines.append("━" * 40)
        lines.append(f"Base: {base} → Adjusted: {adjusted} ({band})")
        lines.append("")
        lines.append("Components:")
        
        # Filter score
        f_score = components['filter_score']
        f_pts = round(f_score * self.WEIGHTS['filter'], 1)
        f_desc = "effective filters" if f_score > 0 else "weak filters" if f_score < 0 else "neutral"
        lines.append(f"  Filters:      {f_score:+.2f} → {f_pts:+.1f} pts ({f_desc})")
        
        # Time of day score
        t_score = components['time_of_day_score']
        t_pts = round(t_score * self.WEIGHTS['time_of_day'], 1)
        t_desc = "good hour" if t_score > 0 else "weak hour" if t_score < 0 else "neutral"
        lines.append(f"  Time of Day:  {t_score:+.2f} → {t_pts:+.1f} pts ({t_desc})")
        
        # Confluence score
        c_score = components['confluence_score']
        c_pts = round(c_score * self.WEIGHTS['confluence'], 1)
        num_filters = len(signal_context.get('filters_passed', []))
        lines.append(f"  Confluence:   {c_score:+.2f} → {c_pts:+.1f} pts ({num_filters} filters)")
        
        # Market score
        m_score = components['market_score']
        m_pts = round(m_score * self.WEIGHTS['market'], 1)
        m_desc = "favorable" if m_score > 0 else "unfavorable" if m_score < 0 else "neutral"
        lines.append(f"  Market:       {m_score:+.2f} → {m_pts:+.1f} pts ({m_desc})")
        
        # Total
        total_pts = f_pts + t_pts + c_pts + m_pts
        lines.append(f"                {'─' * 20}")
        lines.append(f"  Total:              {total_pts:+.1f} pts")
        lines.append("")
        lines.append(f"Position Sizing: {multiplier}x ({band} confidence)")
        
        # Data quality note
        if data_quality == 'limited':
            lines.append("")
            lines.append(f"⚠️  Limited data ({trades} trades) - scores may be neutral")
        
        return "\n".join(lines)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of engine configuration and data status.
        
        Returns:
            Dict with config and status info
        """
        self._ensure_data_loaded()
        
        return {
            'weights': self.WEIGHTS,
            'size_multipliers': self.SIZE_MULTIPLIERS,
            'band_thresholds': self.BAND_THRESHOLDS,
            'trades_available': self._get_trade_count(),
            'min_trades_for_scoring': self.MIN_TRADES_FOR_SCORING,
            'filter_scorer_available': self._filter_scorer is not None,
            'quality_inspector_available': self._quality_inspector is not None
        }


# CLI for testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    print("\n📊 Confidence Engine V2 Test\n")
    
    engine = ConfidenceEngineV2()
    
    # Test with sample signal
    sample_signal = {
        "symbol": "SOL",
        "direction": "long",
        "base_confidence": 75,
        "filters_passed": ["market_regime", "pattern_failure", "momentum_filter"],
        "timestamp": "2026-01-18T14:30:00Z",
        "volatility": 0.022,
        "trend_strength": 0.68
    }
    
    # Compute confidence
    result = engine.compute_confidence(sample_signal)
    
    print("Result:")
    print(f"  Base: {result['base_confidence']} → Adjusted: {result['adjusted_confidence']}")
    print(f"  Band: {result['confidence_band']}")
    print(f"  Multiplier: {result['position_size_multiplier']}x")
    print(f"  Data quality: {result['data_quality']} ({result['trades_analyzed']} trades)")
    print()
    
    # Print explanation
    print(engine.explain(sample_signal))
    
    print("\n✅ Confidence Engine V2 test complete!")
