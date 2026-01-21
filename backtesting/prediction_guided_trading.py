"""
Elite Prediction-Guided Trading System - Backtest Only

Uses price predictions to enhance trading decisions:
1. Direction Filter - Only trade when prediction aligns with signal
2. Confidence Sizing - Scale positions based on prediction confidence
3. Market Timing - Skip trading during uncertain periods
4. Trend Bias - Favor trades aligned with predicted direction

This is COMPLETELY ISOLATED from live trading.
All features use BACKTEST_ prefix in config.
"""

import logging
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PredictionSignal(Enum):
    """Prediction direction signal"""
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


@dataclass
class PredictionGuidance:
    """Guidance from prediction system for trading"""
    direction: PredictionSignal
    confidence: float  # 0-1
    position_multiplier: float  # 0.5-2.0
    should_trade: bool
    reason: str
    predicted_change_pct: float
    prediction_horizon_days: int


class ElitePredictionFilter:
    """
    Elite filter that uses predictions to validate trade signals.
    
    Logic:
    - If prediction is bullish and signal is LONG → Allow with boost
    - If prediction is bearish and signal is SHORT → Allow with boost
    - If prediction conflicts with signal → Block or reduce size
    - If prediction is neutral/uncertain → Normal trading
    """
    
    def __init__(self, 
                 min_alignment_confidence: float = 0.4,
                 block_on_conflict: bool = False,
                 conflict_size_reduction: float = 0.5):
        """
        Args:
            min_alignment_confidence: Minimum confidence to consider prediction
            block_on_conflict: If True, block trades that conflict with prediction
            conflict_size_reduction: Reduce position size by this factor on conflict
        """
        self.min_alignment_confidence = min_alignment_confidence
        self.block_on_conflict = block_on_conflict
        self.conflict_size_reduction = conflict_size_reduction
        
        # Stats
        self.trades_aligned = 0
        self.trades_conflicted = 0
        self.trades_neutral = 0
        self.trades_blocked = 0
    
    def check_alignment(self, signal_direction: str, prediction: 'PricePrediction') -> Tuple[bool, float, str]:
        """
        Check if signal aligns with prediction.
        
        Args:
            signal_direction: 'long' or 'short'
            prediction: The price prediction
            
        Returns:
            (should_trade, position_multiplier, reason)
        """
        if prediction is None:
            self.trades_neutral += 1
            return True, 1.0, "No prediction available"
        
        # Calculate predicted direction
        predicted_change = (prediction.predicted_price - prediction.current_price) / prediction.current_price
        confidence = prediction.confidence
        
        # Determine prediction signal
        if predicted_change > 0.05 and confidence > 0.5:
            pred_direction = PredictionSignal.STRONG_BULLISH
        elif predicted_change > 0.02:
            pred_direction = PredictionSignal.BULLISH
        elif predicted_change < -0.05 and confidence > 0.5:
            pred_direction = PredictionSignal.STRONG_BEARISH
        elif predicted_change < -0.02:
            pred_direction = PredictionSignal.BEARISH
        else:
            pred_direction = PredictionSignal.NEUTRAL
        
        # Check alignment
        signal_is_long = signal_direction.lower() == 'long'
        pred_is_bullish = pred_direction in [PredictionSignal.BULLISH, PredictionSignal.STRONG_BULLISH]
        pred_is_bearish = pred_direction in [PredictionSignal.BEARISH, PredictionSignal.STRONG_BEARISH]
        
        # ALIGNED: Signal matches prediction
        if (signal_is_long and pred_is_bullish) or (not signal_is_long and pred_is_bearish):
            self.trades_aligned += 1
            # Boost position on strong alignment
            if pred_direction in [PredictionSignal.STRONG_BULLISH, PredictionSignal.STRONG_BEARISH]:
                multiplier = min(1.5, 1.0 + confidence * 0.5)
                return True, multiplier, f"Strong alignment (+{multiplier:.1f}x)"
            else:
                multiplier = min(1.25, 1.0 + confidence * 0.25)
                return True, multiplier, f"Aligned (+{multiplier:.1f}x)"
        
        # CONFLICTED: Signal opposes prediction
        if (signal_is_long and pred_is_bearish) or (not signal_is_long and pred_is_bullish):
            self.trades_conflicted += 1
            
            if self.block_on_conflict and confidence > self.min_alignment_confidence:
                self.trades_blocked += 1
                return False, 0.0, f"Blocked - prediction conflicts ({predicted_change*100:+.1f}%)"
            else:
                # Reduce size on conflict
                multiplier = self.conflict_size_reduction
                return True, multiplier, f"Conflict - reduced size ({multiplier:.1f}x)"
        
        # NEUTRAL: Prediction is uncertain
        self.trades_neutral += 1
        return True, 1.0, "Neutral prediction"
    
    def get_stats(self) -> Dict:
        """Get filter statistics"""
        total = self.trades_aligned + self.trades_conflicted + self.trades_neutral
        return {
            'total_checked': total,
            'aligned': self.trades_aligned,
            'conflicted': self.trades_conflicted,
            'neutral': self.trades_neutral,
            'blocked': self.trades_blocked,
            'alignment_rate': self.trades_aligned / total if total > 0 else 0
        }


class EliteConfidenceSizer:
    """
    Elite position sizing based on prediction confidence.
    
    Logic:
    - High confidence prediction → Larger position
    - Low confidence prediction → Smaller position
    - Very low confidence → Minimum position or skip
    """
    
    def __init__(self,
                 base_size: float = 1.0,
                 min_confidence: float = 0.3,
                 max_multiplier: float = 2.0,
                 min_multiplier: float = 0.5):
        """
        Args:
            base_size: Base position size multiplier
            min_confidence: Below this, use minimum size
            max_multiplier: Maximum position multiplier
            min_multiplier: Minimum position multiplier
        """
        self.base_size = base_size
        self.min_confidence = min_confidence
        self.max_multiplier = max_multiplier
        self.min_multiplier = min_multiplier
        
        # Stats
        self.sizes_calculated = 0
        self.avg_multiplier = 0.0
    
    def calculate_size(self, prediction: 'PricePrediction', signal_confidence: float = 0.5) -> Tuple[float, str]:
        """
        Calculate position size based on prediction confidence.
        
        Args:
            prediction: The price prediction
            signal_confidence: Confidence from the trading signal (0-1)
            
        Returns:
            (size_multiplier, reason)
        """
        if prediction is None:
            return self.base_size, "No prediction - using base size"
        
        pred_confidence = prediction.confidence
        
        # Combine prediction and signal confidence
        combined_confidence = (pred_confidence * 0.6 + signal_confidence * 0.4)
        
        # Calculate multiplier
        if combined_confidence < self.min_confidence:
            multiplier = self.min_multiplier
            reason = f"Low confidence ({combined_confidence:.2f}) - min size"
        elif combined_confidence > 0.7:
            # Scale up for high confidence
            multiplier = self.base_size + (combined_confidence - 0.5) * (self.max_multiplier - self.base_size) / 0.5
            multiplier = min(multiplier, self.max_multiplier)
            reason = f"High confidence ({combined_confidence:.2f}) - {multiplier:.2f}x"
        else:
            # Normal confidence
            multiplier = self.base_size + (combined_confidence - 0.3) * 0.5
            reason = f"Normal confidence ({combined_confidence:.2f}) - {multiplier:.2f}x"
        
        # Update stats
        self.sizes_calculated += 1
        self.avg_multiplier = (self.avg_multiplier * (self.sizes_calculated - 1) + multiplier) / self.sizes_calculated
        
        return multiplier, reason
    
    def get_stats(self) -> Dict:
        """Get sizing statistics"""
        return {
            'sizes_calculated': self.sizes_calculated,
            'avg_multiplier': self.avg_multiplier
        }


class EliteMarketTimer:
    """
    Elite market timing based on prediction uncertainty.
    
    Logic:
    - Skip trading when predictions are highly uncertain
    - Skip trading when models disagree significantly
    - Allow trading when predictions are confident
    """
    
    def __init__(self,
                 min_confidence_to_trade: float = 0.35,
                 uncertainty_lookback: int = 5):
        """
        Args:
            min_confidence_to_trade: Minimum confidence to allow trading
            uncertainty_lookback: Number of recent predictions to check
        """
        self.min_confidence_to_trade = min_confidence_to_trade
        self.uncertainty_lookback = uncertainty_lookback
        
        # Track recent predictions
        self.recent_predictions: List[Dict] = []
        
        # Stats
        self.trades_allowed = 0
        self.trades_skipped = 0
    
    def should_trade(self, prediction: 'PricePrediction') -> Tuple[bool, str]:
        """
        Determine if market conditions are favorable for trading.
        
        Args:
            prediction: Current price prediction
            
        Returns:
            (should_trade, reason)
        """
        if prediction is None:
            self.trades_allowed += 1
            return True, "No prediction - allowing trade"
        
        # Store prediction
        self.recent_predictions.append({
            'confidence': prediction.confidence,
            'predicted_change': (prediction.predicted_price - prediction.current_price) / prediction.current_price,
            'model': prediction.model_used
        })
        
        # Keep only recent predictions
        if len(self.recent_predictions) > self.uncertainty_lookback:
            self.recent_predictions = self.recent_predictions[-self.uncertainty_lookback:]
        
        # Check confidence
        if prediction.confidence < self.min_confidence_to_trade:
            self.trades_skipped += 1
            return False, f"Low confidence ({prediction.confidence:.2f} < {self.min_confidence_to_trade})"
        
        # Check if predictions are flip-flopping (sign changes)
        if len(self.recent_predictions) >= 3:
            changes = [p['predicted_change'] for p in self.recent_predictions[-3:]]
            sign_changes = sum(1 for i in range(1, len(changes)) if changes[i] * changes[i-1] < 0)
            
            if sign_changes >= 2:
                self.trades_skipped += 1
                return False, "Predictions flip-flopping - market uncertain"
        
        self.trades_allowed += 1
        return True, f"Market timing OK (conf: {prediction.confidence:.2f})"
    
    def get_stats(self) -> Dict:
        """Get timing statistics"""
        total = self.trades_allowed + self.trades_skipped
        return {
            'trades_allowed': self.trades_allowed,
            'trades_skipped': self.trades_skipped,
            'skip_rate': self.trades_skipped / total if total > 0 else 0
        }


class EliteTrendBias:
    """
    Elite trend bias from predictions.
    
    Logic:
    - If 30-day prediction is strongly bullish, favor longs
    - If 30-day prediction is strongly bearish, favor shorts
    - Apply a bias multiplier to aligned trades
    """
    
    def __init__(self,
                 strong_trend_threshold: float = 0.05,
                 bias_multiplier: float = 1.3,
                 anti_bias_multiplier: float = 0.7):
        """
        Args:
            strong_trend_threshold: % change to consider strong trend
            bias_multiplier: Boost for aligned trades
            anti_bias_multiplier: Reduction for counter-trend trades
        """
        self.strong_trend_threshold = strong_trend_threshold
        self.bias_multiplier = bias_multiplier
        self.anti_bias_multiplier = anti_bias_multiplier
        
        # Current bias
        self.current_bias = "neutral"
        self.bias_strength = 0.0
        
        # Stats
        self.bias_boosts = 0
        self.bias_reductions = 0
    
    def update_bias(self, prediction: 'PricePrediction'):
        """Update trend bias from prediction"""
        if prediction is None or prediction.time_horizon_days < 25:
            return
        
        predicted_change = (prediction.predicted_price - prediction.current_price) / prediction.current_price
        
        if predicted_change > self.strong_trend_threshold:
            self.current_bias = "bullish"
            self.bias_strength = min(1.0, predicted_change / 0.1)
        elif predicted_change < -self.strong_trend_threshold:
            self.current_bias = "bearish"
            self.bias_strength = min(1.0, abs(predicted_change) / 0.1)
        else:
            self.current_bias = "neutral"
            self.bias_strength = 0.0
    
    def apply_bias(self, signal_direction: str) -> Tuple[float, str]:
        """
        Apply trend bias to a trade.
        
        Args:
            signal_direction: 'long' or 'short'
            
        Returns:
            (multiplier, reason)
        """
        if self.current_bias == "neutral":
            return 1.0, "No trend bias"
        
        signal_is_long = signal_direction.lower() == 'long'
        bias_is_bullish = self.current_bias == "bullish"
        
        # Aligned with bias
        if (signal_is_long and bias_is_bullish) or (not signal_is_long and not bias_is_bullish):
            self.bias_boosts += 1
            multiplier = 1.0 + (self.bias_multiplier - 1.0) * self.bias_strength
            return multiplier, f"Trend bias boost ({self.current_bias}, {multiplier:.2f}x)"
        
        # Against bias
        self.bias_reductions += 1
        multiplier = 1.0 - (1.0 - self.anti_bias_multiplier) * self.bias_strength
        return multiplier, f"Against trend bias ({self.current_bias}, {multiplier:.2f}x)"
    
    def get_stats(self) -> Dict:
        """Get bias statistics"""
        return {
            'current_bias': self.current_bias,
            'bias_strength': self.bias_strength,
            'boosts': self.bias_boosts,
            'reductions': self.bias_reductions
        }


class ElitePredictionGuidedTrading:
    """
    Master class combining all prediction-guided trading features.
    
    This is the main interface for the backtest engine.
    """
    
    def __init__(self,
                 enable_direction_filter: bool = True,
                 enable_confidence_sizing: bool = True,
                 enable_market_timing: bool = True,
                 enable_trend_bias: bool = True,
                 direction_filter_config: Dict = None,
                 confidence_sizer_config: Dict = None,
                 market_timer_config: Dict = None,
                 trend_bias_config: Dict = None):
        """
        Initialize all prediction-guided trading components.
        """
        self.enable_direction_filter = enable_direction_filter
        self.enable_confidence_sizing = enable_confidence_sizing
        self.enable_market_timing = enable_market_timing
        self.enable_trend_bias = enable_trend_bias
        
        # Initialize components
        self.direction_filter = ElitePredictionFilter(**(direction_filter_config or {}))
        self.confidence_sizer = EliteConfidenceSizer(**(confidence_sizer_config or {}))
        self.market_timer = EliteMarketTimer(**(market_timer_config or {}))
        self.trend_bias = EliteTrendBias(**(trend_bias_config or {}))
        
        # Current prediction cache
        self.current_30d_prediction = None
        self.current_90d_prediction = None
        
        # Stats
        self.total_signals_checked = 0
        self.signals_allowed = 0
        self.signals_blocked = 0
        
        logger.info("🔮 Elite Prediction-Guided Trading initialized")
        logger.info(f"   Direction Filter: {'ENABLED' if enable_direction_filter else 'DISABLED'}")
        logger.info(f"   Confidence Sizing: {'ENABLED' if enable_confidence_sizing else 'DISABLED'}")
        logger.info(f"   Market Timing: {'ENABLED' if enable_market_timing else 'DISABLED'}")
        logger.info(f"   Trend Bias: {'ENABLED' if enable_trend_bias else 'DISABLED'}")
    
    def update_predictions(self, predictions: List['PricePrediction']):
        """Update cached predictions"""
        for pred in predictions:
            if pred.time_horizon_days == 30:
                self.current_30d_prediction = pred
                # Update trend bias
                if self.enable_trend_bias:
                    self.trend_bias.update_bias(pred)
            elif pred.time_horizon_days == 90:
                self.current_90d_prediction = pred
    
    def evaluate_signal(self, signal_direction: str, signal_confidence: float = 0.5) -> PredictionGuidance:
        """
        Evaluate a trading signal using all prediction-guided features.
        
        Args:
            signal_direction: 'long' or 'short'
            signal_confidence: Confidence from the trading signal (0-1)
            
        Returns:
            PredictionGuidance with final decision and multipliers
        """
        self.total_signals_checked += 1
        
        prediction = self.current_30d_prediction
        final_multiplier = 1.0
        reasons = []
        should_trade = True
        
        # 1. Market Timing Check
        if self.enable_market_timing and prediction:
            timing_ok, timing_reason = self.market_timer.should_trade(prediction)
            reasons.append(f"Timing: {timing_reason}")
            if not timing_ok:
                should_trade = False
                self.signals_blocked += 1
                return PredictionGuidance(
                    direction=PredictionSignal.NEUTRAL,
                    confidence=0.0,
                    position_multiplier=0.0,
                    should_trade=False,
                    reason=" | ".join(reasons),
                    predicted_change_pct=0.0,
                    prediction_horizon_days=30
                )
        
        # 2. Direction Filter
        if self.enable_direction_filter and prediction:
            dir_ok, dir_mult, dir_reason = self.direction_filter.check_alignment(signal_direction, prediction)
            reasons.append(f"Direction: {dir_reason}")
            final_multiplier *= dir_mult
            if not dir_ok:
                should_trade = False
                self.signals_blocked += 1
                return PredictionGuidance(
                    direction=PredictionSignal.NEUTRAL,
                    confidence=0.0,
                    position_multiplier=0.0,
                    should_trade=False,
                    reason=" | ".join(reasons),
                    predicted_change_pct=0.0,
                    prediction_horizon_days=30
                )
        
        # 3. Confidence Sizing
        if self.enable_confidence_sizing and prediction:
            conf_mult, conf_reason = self.confidence_sizer.calculate_size(prediction, signal_confidence)
            reasons.append(f"Sizing: {conf_reason}")
            final_multiplier *= conf_mult
        
        # 4. Trend Bias
        if self.enable_trend_bias:
            bias_mult, bias_reason = self.trend_bias.apply_bias(signal_direction)
            reasons.append(f"Bias: {bias_reason}")
            final_multiplier *= bias_mult
        
        # Clamp final multiplier
        final_multiplier = max(0.25, min(2.5, final_multiplier))
        
        # Determine prediction signal
        pred_change = 0.0
        if prediction:
            pred_change = (prediction.predicted_price - prediction.current_price) / prediction.current_price * 100
        
        if pred_change > 5:
            direction = PredictionSignal.STRONG_BULLISH
        elif pred_change > 2:
            direction = PredictionSignal.BULLISH
        elif pred_change < -5:
            direction = PredictionSignal.STRONG_BEARISH
        elif pred_change < -2:
            direction = PredictionSignal.BEARISH
        else:
            direction = PredictionSignal.NEUTRAL
        
        self.signals_allowed += 1
        
        return PredictionGuidance(
            direction=direction,
            confidence=prediction.confidence if prediction else 0.5,
            position_multiplier=final_multiplier,
            should_trade=should_trade,
            reason=" | ".join(reasons),
            predicted_change_pct=pred_change,
            prediction_horizon_days=30
        )
    
    def get_report(self) -> str:
        """Get comprehensive report of prediction-guided trading"""
        lines = [
            "",
            "=" * 60,
            "🔮 PREDICTION-GUIDED TRADING REPORT",
            "=" * 60,
            f"Total Signals Checked: {self.total_signals_checked}",
            f"Signals Allowed: {self.signals_allowed}",
            f"Signals Blocked: {self.signals_blocked}",
            f"Block Rate: {self.signals_blocked / self.total_signals_checked * 100:.1f}%" if self.total_signals_checked > 0 else "Block Rate: N/A",
            ""
        ]
        
        if self.enable_direction_filter:
            stats = self.direction_filter.get_stats()
            lines.append("📊 Direction Filter:")
            lines.append(f"   Aligned: {stats['aligned']} | Conflicted: {stats['conflicted']} | Neutral: {stats['neutral']}")
            lines.append(f"   Blocked: {stats['blocked']} | Alignment Rate: {stats['alignment_rate']*100:.1f}%")
        
        if self.enable_confidence_sizing:
            stats = self.confidence_sizer.get_stats()
            lines.append("📊 Confidence Sizing:")
            lines.append(f"   Sizes Calculated: {stats['sizes_calculated']}")
            lines.append(f"   Avg Multiplier: {stats['avg_multiplier']:.2f}x")
        
        if self.enable_market_timing:
            stats = self.market_timer.get_stats()
            lines.append("📊 Market Timing:")
            lines.append(f"   Allowed: {stats['trades_allowed']} | Skipped: {stats['trades_skipped']}")
            lines.append(f"   Skip Rate: {stats['skip_rate']*100:.1f}%")
        
        if self.enable_trend_bias:
            stats = self.trend_bias.get_stats()
            lines.append("📊 Trend Bias:")
            lines.append(f"   Current: {stats['current_bias']} (strength: {stats['bias_strength']:.2f})")
            lines.append(f"   Boosts: {stats['boosts']} | Reductions: {stats['reductions']}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


def create_prediction_guided_trading(
    enable_direction_filter: bool = True,
    enable_confidence_sizing: bool = True,
    enable_market_timing: bool = True,
    enable_trend_bias: bool = True
) -> ElitePredictionGuidedTrading:
    """Factory function to create prediction-guided trading system"""
    return ElitePredictionGuidedTrading(
        enable_direction_filter=enable_direction_filter,
        enable_confidence_sizing=enable_confidence_sizing,
        enable_market_timing=enable_market_timing,
        enable_trend_bias=enable_trend_bias
    )
