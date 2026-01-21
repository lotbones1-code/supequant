"""
Elite Prediction System V2 - Enhanced for Higher Win Rate

BACKTEST ONLY - Does NOT affect live trading

Improvements over V1:
1. Higher confidence thresholds (more selective)
2. Multi-horizon consensus (30d + 90d must agree)
3. Prediction accuracy weighting (trust recent accuracy)
4. Dynamic stop loss (tighter stops on aligned trades)
5. Early exit signals (exit when prediction reverses)
6. Block conflicting trades (strict mode)

This should increase win rate while maintaining profitability.
"""

import logging
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class PredictionDirection(Enum):
    """Prediction direction categories"""
    STRONG_BULLISH = "strong_bullish"  # >7% predicted gain
    BULLISH = "bullish"                 # 3-7% predicted gain
    NEUTRAL = "neutral"                 # -3% to +3%
    BEARISH = "bearish"                 # -3% to -7% predicted loss
    STRONG_BEARISH = "strong_bearish"  # <-7% predicted loss


@dataclass
class EliteGuidance:
    """Enhanced guidance from elite prediction system"""
    should_trade: bool
    direction: PredictionDirection
    confidence: float  # 0-1
    position_multiplier: float  # 0.25-2.5
    stop_adjustment: float  # 0.8-1.2 (multiplier for stop distance)
    reason: str
    consensus_score: float  # 0-1 (how much horizons agree)
    accuracy_weight: float  # 0-1 (recent prediction accuracy)
    predicted_30d_change: float
    predicted_90d_change: float


@dataclass 
class PredictionAccuracyTracker:
    """Track recent prediction accuracy to weight future decisions"""
    recent_errors: deque = field(default_factory=lambda: deque(maxlen=20))
    total_predictions: int = 0
    accurate_predictions: int = 0  # Within 10% of actual
    
    def add_result(self, predicted_change: float, actual_change: float):
        """Record a prediction result"""
        error = abs(predicted_change - actual_change)
        self.recent_errors.append(error)
        self.total_predictions += 1
        if error < 0.10:  # Within 10%
            self.accurate_predictions += 1
    
    def get_accuracy_weight(self) -> float:
        """Get weight based on recent accuracy (0.5-1.5)"""
        if len(self.recent_errors) < 5:
            return 1.0  # Not enough data
        
        avg_error = np.mean(list(self.recent_errors))
        # Lower error = higher weight
        # avg_error 0.05 (5%) -> weight 1.5
        # avg_error 0.20 (20%) -> weight 0.5
        weight = max(0.5, min(1.5, 1.5 - avg_error * 5))
        return weight
    
    def get_hit_rate(self) -> float:
        """Get overall accuracy rate"""
        if self.total_predictions == 0:
            return 0.5
        return self.accurate_predictions / self.total_predictions


class EliteMultiHorizonConsensus:
    """
    Check if multiple prediction horizons agree.
    
    Logic:
    - Both 30d and 90d should predict same direction
    - Higher consensus = more confidence
    - Disagreement = skip trade or reduce size
    """
    
    def __init__(self, 
                 require_agreement: bool = True,
                 min_consensus_score: float = 0.6):
        """
        Args:
            require_agreement: If True, block trades when horizons disagree
            min_consensus_score: Minimum consensus to allow trade (0-1)
        """
        self.require_agreement = require_agreement
        self.min_consensus_score = min_consensus_score
        
        # Stats
        self.checks_total = 0
        self.consensus_reached = 0
        self.consensus_failed = 0
    
    def check_consensus(self, 
                       pred_30d_change: float, 
                       pred_90d_change: float,
                       confidence_30d: float,
                       confidence_90d: float) -> Tuple[bool, float, str]:
        """
        Check if 30d and 90d predictions agree.
        
        Returns:
            (passes, consensus_score, reason)
        """
        self.checks_total += 1
        
        # Check if same direction
        same_direction = (pred_30d_change > 0) == (pred_90d_change > 0)
        
        # Calculate consensus score
        if same_direction:
            # Both agree - score based on magnitude similarity
            mag_30d = abs(pred_30d_change)
            mag_90d = abs(pred_90d_change)
            
            # Normalize magnitudes
            mag_ratio = min(mag_30d, mag_90d) / max(mag_30d, mag_90d) if max(mag_30d, mag_90d) > 0 else 1.0
            
            # Combine with confidence
            avg_confidence = (confidence_30d + confidence_90d) / 2
            consensus_score = mag_ratio * avg_confidence
            
            self.consensus_reached += 1
            return True, consensus_score, f"Horizons agree (score: {consensus_score:.2f})"
        else:
            # Disagree - low score
            self.consensus_failed += 1
            
            # Score based on which one is stronger
            strength_30d = abs(pred_30d_change) * confidence_30d
            strength_90d = abs(pred_90d_change) * confidence_90d
            
            # Very low consensus when disagreeing
            consensus_score = 0.3 * max(strength_30d, strength_90d)
            
            if self.require_agreement:
                return False, consensus_score, f"Horizons DISAGREE (30d: {pred_30d_change*100:+.1f}%, 90d: {pred_90d_change*100:+.1f}%)"
            else:
                return True, consensus_score, f"Weak consensus - horizons disagree"
    
    def get_stats(self) -> Dict:
        return {
            'total_checks': self.checks_total,
            'consensus_reached': self.consensus_reached,
            'consensus_failed': self.consensus_failed,
            'consensus_rate': self.consensus_reached / self.checks_total if self.checks_total > 0 else 0
        }


class EliteDirectionFilter:
    """
    Enhanced direction filter with stricter thresholds.
    
    V2 Improvements:
    - Higher thresholds (3% for bullish, 7% for strong)
    - Can block conflicting trades entirely
    - Uses accuracy weighting
    """
    
    def __init__(self,
                 bullish_threshold: float = 0.03,      # 3% for bullish (was 2%)
                 strong_threshold: float = 0.07,       # 7% for strong (was 5%)
                 min_confidence: float = 0.50,         # 50% (was 40%)
                 block_on_conflict: bool = True,       # Block conflicts (was False)
                 conflict_reduction: float = 0.3):     # 70% reduction (was 50%)
        
        self.bullish_threshold = bullish_threshold
        self.strong_threshold = strong_threshold
        self.min_confidence = min_confidence
        self.block_on_conflict = block_on_conflict
        self.conflict_reduction = conflict_reduction
        
        # Stats
        self.trades_aligned = 0
        self.trades_strong_aligned = 0
        self.trades_conflicted = 0
        self.trades_blocked = 0
        self.trades_neutral = 0
    
    def get_direction(self, predicted_change: float, confidence: float) -> PredictionDirection:
        """Classify prediction direction"""
        if predicted_change > self.strong_threshold and confidence > 0.5:
            return PredictionDirection.STRONG_BULLISH
        elif predicted_change > self.bullish_threshold:
            return PredictionDirection.BULLISH
        elif predicted_change < -self.strong_threshold and confidence > 0.5:
            return PredictionDirection.STRONG_BEARISH
        elif predicted_change < -self.bullish_threshold:
            return PredictionDirection.BEARISH
        else:
            return PredictionDirection.NEUTRAL
    
    def check_alignment(self, 
                       signal_direction: str, 
                       predicted_change: float,
                       confidence: float,
                       accuracy_weight: float = 1.0) -> Tuple[bool, float, PredictionDirection, str]:
        """
        Check if signal aligns with prediction.
        
        Returns:
            (should_trade, multiplier, direction, reason)
        """
        direction = self.get_direction(predicted_change, confidence)
        
        signal_is_long = signal_direction.lower() == 'long'
        pred_is_bullish = direction in [PredictionDirection.BULLISH, PredictionDirection.STRONG_BULLISH]
        pred_is_bearish = direction in [PredictionDirection.BEARISH, PredictionDirection.STRONG_BEARISH]
        is_neutral = direction == PredictionDirection.NEUTRAL
        
        # Apply accuracy weight to confidence
        effective_confidence = confidence * accuracy_weight
        
        # NEUTRAL: Prediction uncertain
        if is_neutral:
            self.trades_neutral += 1
            return True, 0.9, direction, "Neutral prediction - slight reduction"
        
        # ALIGNED: Signal matches prediction
        if (signal_is_long and pred_is_bullish) or (not signal_is_long and pred_is_bearish):
            if direction in [PredictionDirection.STRONG_BULLISH, PredictionDirection.STRONG_BEARISH]:
                self.trades_strong_aligned += 1
                # Big boost for strong alignment
                multiplier = min(2.0, 1.3 + effective_confidence * 0.7)
                return True, multiplier, direction, f"STRONG alignment ({direction.value}) +{multiplier:.1f}x"
            else:
                self.trades_aligned += 1
                multiplier = min(1.5, 1.0 + effective_confidence * 0.5)
                return True, multiplier, direction, f"Aligned ({direction.value}) +{multiplier:.1f}x"
        
        # CONFLICTED: Signal opposes prediction
        self.trades_conflicted += 1
        
        if self.block_on_conflict and effective_confidence > self.min_confidence:
            self.trades_blocked += 1
            return False, 0.0, direction, f"BLOCKED - conflicts with {direction.value} (conf: {effective_confidence:.2f})"
        else:
            # Severe reduction on conflict
            multiplier = self.conflict_reduction
            return True, multiplier, direction, f"Conflict with {direction.value} - reduced to {multiplier:.1f}x"
    
    def get_stats(self) -> Dict:
        total = self.trades_aligned + self.trades_strong_aligned + self.trades_conflicted + self.trades_neutral
        return {
            'total': total,
            'aligned': self.trades_aligned,
            'strong_aligned': self.trades_strong_aligned,
            'conflicted': self.trades_conflicted,
            'blocked': self.trades_blocked,
            'neutral': self.trades_neutral,
            'alignment_rate': (self.trades_aligned + self.trades_strong_aligned) / total if total > 0 else 0
        }


class EliteDynamicStops:
    """
    Adjust stop loss based on prediction alignment.
    
    Logic:
    - Strong aligned trades: Tighter stops (lock in profits faster)
    - Conflicting trades: Wider stops (give more room to be wrong)
    - Based on prediction confidence
    """
    
    def __init__(self,
                 aligned_stop_mult: float = 0.85,      # 15% tighter stops on aligned
                 strong_aligned_stop_mult: float = 0.75,  # 25% tighter on strong aligned
                 conflict_stop_mult: float = 1.1,      # 10% wider on conflict
                 neutral_stop_mult: float = 1.0):
        
        self.aligned_stop_mult = aligned_stop_mult
        self.strong_aligned_stop_mult = strong_aligned_stop_mult
        self.conflict_stop_mult = conflict_stop_mult
        self.neutral_stop_mult = neutral_stop_mult
        
        # Stats
        self.stops_tightened = 0
        self.stops_widened = 0
        self.stops_unchanged = 0
    
    def get_stop_adjustment(self, 
                           direction: PredictionDirection,
                           is_aligned: bool,
                           confidence: float) -> Tuple[float, str]:
        """
        Get stop loss adjustment multiplier.
        
        Returns:
            (stop_multiplier, reason)
        """
        if direction == PredictionDirection.NEUTRAL:
            self.stops_unchanged += 1
            return self.neutral_stop_mult, "Neutral - standard stop"
        
        if is_aligned:
            if direction in [PredictionDirection.STRONG_BULLISH, PredictionDirection.STRONG_BEARISH]:
                self.stops_tightened += 1
                mult = self.strong_aligned_stop_mult
                return mult, f"Strong aligned - tight stop ({mult:.0%})"
            else:
                self.stops_tightened += 1
                mult = self.aligned_stop_mult
                return mult, f"Aligned - tighter stop ({mult:.0%})"
        else:
            # Conflict
            self.stops_widened += 1
            mult = self.conflict_stop_mult
            return mult, f"Conflict - wider stop ({mult:.0%})"
    
    def get_stats(self) -> Dict:
        return {
            'tightened': self.stops_tightened,
            'widened': self.stops_widened,
            'unchanged': self.stops_unchanged
        }


class EliteEarlyExit:
    """
    Signal early exit when prediction reverses during a trade.
    
    Logic:
    - If holding LONG and prediction turns bearish -> exit early
    - If holding SHORT and prediction turns bullish -> exit early
    - Only if confidence is high enough
    """
    
    def __init__(self,
                 min_confidence_for_exit: float = 0.55,
                 min_prediction_change: float = 0.03):  # 3% reversal needed
        
        self.min_confidence_for_exit = min_confidence_for_exit
        self.min_prediction_change = min_prediction_change
        
        # Track active trades and their entry predictions
        self.active_trades: Dict[str, Dict] = {}
        
        # Stats
        self.early_exits_triggered = 0
        self.early_exits_checked = 0
    
    def register_trade(self, trade_id: str, direction: str, entry_prediction: float):
        """Register a new trade for monitoring"""
        self.active_trades[trade_id] = {
            'direction': direction,
            'entry_prediction': entry_prediction
        }
    
    def check_early_exit(self, 
                        trade_id: str,
                        current_prediction: float,
                        confidence: float) -> Tuple[bool, str]:
        """
        Check if trade should exit early based on prediction change.
        
        Returns:
            (should_exit, reason)
        """
        if trade_id not in self.active_trades:
            return False, "Trade not registered"
        
        self.early_exits_checked += 1
        
        trade = self.active_trades[trade_id]
        direction = trade['direction']
        entry_pred = trade['entry_prediction']
        
        # Check confidence threshold
        if confidence < self.min_confidence_for_exit:
            return False, f"Confidence too low ({confidence:.2f})"
        
        # Check for prediction reversal
        is_long = direction.lower() == 'long'
        
        if is_long:
            # Exit long if prediction turns significantly bearish
            if current_prediction < -self.min_prediction_change:
                self.early_exits_triggered += 1
                del self.active_trades[trade_id]
                return True, f"EXIT EARLY: Prediction reversed to {current_prediction*100:+.1f}%"
        else:
            # Exit short if prediction turns significantly bullish
            if current_prediction > self.min_prediction_change:
                self.early_exits_triggered += 1
                del self.active_trades[trade_id]
                return True, f"EXIT EARLY: Prediction reversed to {current_prediction*100:+.1f}%"
        
        return False, "No reversal detected"
    
    def close_trade(self, trade_id: str):
        """Remove trade from tracking"""
        if trade_id in self.active_trades:
            del self.active_trades[trade_id]
    
    def get_stats(self) -> Dict:
        return {
            'active_trades': len(self.active_trades),
            'early_exits_triggered': self.early_exits_triggered,
            'checks_performed': self.early_exits_checked
        }


class EliteMarketTiming:
    """
    Enhanced market timing with stricter confidence requirements.
    """
    
    def __init__(self,
                 min_confidence: float = 0.50,         # 50% (was 35%)
                 min_consensus: float = 0.60,          # 60% consensus required
                 max_flip_flops: int = 1):             # Max 1 direction change in recent predictions
        
        self.min_confidence = min_confidence
        self.min_consensus = min_consensus
        self.max_flip_flops = max_flip_flops
        
        # Track recent predictions
        self.recent_predictions: List[float] = []
        
        # Stats
        self.allowed = 0
        self.blocked_low_conf = 0
        self.blocked_flip_flop = 0
        self.blocked_low_consensus = 0
    
    def should_trade(self, 
                    confidence: float,
                    consensus_score: float,
                    predicted_change: float) -> Tuple[bool, str]:
        """
        Check if conditions are favorable for trading.
        """
        # Track prediction direction
        self.recent_predictions.append(predicted_change)
        if len(self.recent_predictions) > 5:
            self.recent_predictions = self.recent_predictions[-5:]
        
        # Check confidence
        if confidence < self.min_confidence:
            self.blocked_low_conf += 1
            return False, f"Low confidence ({confidence:.2f} < {self.min_confidence})"
        
        # Check consensus
        if consensus_score < self.min_consensus:
            self.blocked_low_consensus += 1
            return False, f"Low consensus ({consensus_score:.2f} < {self.min_consensus})"
        
        # Check flip-flopping
        if len(self.recent_predictions) >= 3:
            changes = self.recent_predictions[-3:]
            flip_flops = sum(1 for i in range(1, len(changes)) if changes[i] * changes[i-1] < 0)
            
            if flip_flops > self.max_flip_flops:
                self.blocked_flip_flop += 1
                return False, f"Market flip-flopping ({flip_flops} reversals)"
        
        self.allowed += 1
        return True, f"Market timing OK (conf: {confidence:.2f}, cons: {consensus_score:.2f})"
    
    def get_stats(self) -> Dict:
        total = self.allowed + self.blocked_low_conf + self.blocked_flip_flop + self.blocked_low_consensus
        return {
            'allowed': self.allowed,
            'blocked_low_conf': self.blocked_low_conf,
            'blocked_flip_flop': self.blocked_flip_flop,
            'blocked_low_consensus': self.blocked_low_consensus,
            'pass_rate': self.allowed / total if total > 0 else 0
        }


class ElitePredictionSystemV2:
    """
    Master class combining all elite prediction features.
    
    This is the main interface for the backtest engine.
    V2 with all improvements for higher win rate.
    """
    
    def __init__(self,
                 # Feature toggles
                 enable_direction_filter: bool = True,
                 enable_consensus: bool = True,
                 enable_accuracy_weighting: bool = True,
                 enable_dynamic_stops: bool = True,
                 enable_early_exit: bool = True,
                 enable_market_timing: bool = True,
                 # Strictness settings
                 block_on_conflict: bool = True,
                 require_consensus: bool = True,
                 min_confidence: float = 0.50,
                 min_consensus: float = 0.60):
        
        self.enable_direction_filter = enable_direction_filter
        self.enable_consensus = enable_consensus
        self.enable_accuracy_weighting = enable_accuracy_weighting
        self.enable_dynamic_stops = enable_dynamic_stops
        self.enable_early_exit = enable_early_exit
        self.enable_market_timing = enable_market_timing
        
        # Initialize components
        self.direction_filter = EliteDirectionFilter(
            block_on_conflict=block_on_conflict,
            min_confidence=min_confidence
        )
        self.consensus_checker = EliteMultiHorizonConsensus(
            require_agreement=require_consensus,
            min_consensus_score=min_consensus
        )
        self.accuracy_tracker = PredictionAccuracyTracker()
        self.dynamic_stops = EliteDynamicStops()
        self.early_exit = EliteEarlyExit()
        self.market_timer = EliteMarketTiming(
            min_confidence=min_confidence,
            min_consensus=min_consensus
        )
        
        # Prediction cache
        self.current_30d_prediction = None
        self.current_90d_prediction = None
        
        # Stats
        self.total_signals = 0
        self.signals_allowed = 0
        self.signals_blocked = 0
        
        logger.info("🔮 Elite Prediction System V2 initialized")
        logger.info(f"   Direction Filter: {'ON' if enable_direction_filter else 'OFF'}")
        logger.info(f"   Multi-Horizon Consensus: {'ON' if enable_consensus else 'OFF'}")
        logger.info(f"   Accuracy Weighting: {'ON' if enable_accuracy_weighting else 'OFF'}")
        logger.info(f"   Dynamic Stops: {'ON' if enable_dynamic_stops else 'OFF'}")
        logger.info(f"   Early Exit: {'ON' if enable_early_exit else 'OFF'}")
        logger.info(f"   Market Timing: {'ON' if enable_market_timing else 'OFF'}")
        logger.info(f"   Block on Conflict: {block_on_conflict}")
        logger.info(f"   Min Confidence: {min_confidence:.0%}")
        logger.info(f"   Min Consensus: {min_consensus:.0%}")
    
    def update_predictions(self, predictions: List):
        """Update cached predictions from backtest engine"""
        for pred in predictions:
            if hasattr(pred, 'time_horizon_days'):
                if pred.time_horizon_days == 30:
                    self.current_30d_prediction = pred
                elif pred.time_horizon_days == 90:
                    self.current_90d_prediction = pred
    
    def record_prediction_result(self, predicted_change: float, actual_change: float):
        """Record prediction result for accuracy tracking"""
        if self.enable_accuracy_weighting:
            self.accuracy_tracker.add_result(predicted_change, actual_change)
    
    def evaluate_signal(self, 
                       signal_direction: str,
                       signal_confidence: float = 0.5) -> EliteGuidance:
        """
        Evaluate a trading signal using all elite features.
        
        Returns comprehensive guidance for the trade.
        """
        self.total_signals += 1
        
        # Default values
        should_trade = True
        position_multiplier = 1.0
        stop_adjustment = 1.0
        consensus_score = 0.5
        accuracy_weight = 1.0
        reasons = []
        direction = PredictionDirection.NEUTRAL
        pred_30d_change = 0.0
        pred_90d_change = 0.0
        confidence = 0.5
        
        # Get predictions
        pred_30d = self.current_30d_prediction
        pred_90d = self.current_90d_prediction
        
        if pred_30d:
            pred_30d_change = (pred_30d.predicted_price - pred_30d.current_price) / pred_30d.current_price
            confidence = pred_30d.confidence
        
        if pred_90d:
            pred_90d_change = (pred_90d.predicted_price - pred_90d.current_price) / pred_90d.current_price
        
        # 1. Accuracy weighting
        if self.enable_accuracy_weighting:
            accuracy_weight = self.accuracy_tracker.get_accuracy_weight()
        
        # 2. Multi-horizon consensus
        if self.enable_consensus and pred_30d and pred_90d:
            passes, consensus_score, cons_reason = self.consensus_checker.check_consensus(
                pred_30d_change, pred_90d_change,
                pred_30d.confidence, pred_90d.confidence
            )
            reasons.append(f"Consensus: {cons_reason}")
            
            if not passes:
                should_trade = False
                self.signals_blocked += 1
                return EliteGuidance(
                    should_trade=False,
                    direction=PredictionDirection.NEUTRAL,
                    confidence=confidence,
                    position_multiplier=0.0,
                    stop_adjustment=1.0,
                    reason=" | ".join(reasons),
                    consensus_score=consensus_score,
                    accuracy_weight=accuracy_weight,
                    predicted_30d_change=pred_30d_change,
                    predicted_90d_change=pred_90d_change
                )
        
        # 3. Market timing
        if self.enable_market_timing and pred_30d:
            timing_ok, timing_reason = self.market_timer.should_trade(
                confidence, consensus_score, pred_30d_change
            )
            reasons.append(f"Timing: {timing_reason}")
            
            if not timing_ok:
                should_trade = False
                self.signals_blocked += 1
                return EliteGuidance(
                    should_trade=False,
                    direction=PredictionDirection.NEUTRAL,
                    confidence=confidence,
                    position_multiplier=0.0,
                    stop_adjustment=1.0,
                    reason=" | ".join(reasons),
                    consensus_score=consensus_score,
                    accuracy_weight=accuracy_weight,
                    predicted_30d_change=pred_30d_change,
                    predicted_90d_change=pred_90d_change
                )
        
        # 4. Direction filter
        if self.enable_direction_filter and pred_30d:
            dir_ok, dir_mult, direction, dir_reason = self.direction_filter.check_alignment(
                signal_direction, pred_30d_change, confidence, accuracy_weight
            )
            reasons.append(f"Direction: {dir_reason}")
            position_multiplier *= dir_mult
            
            if not dir_ok:
                should_trade = False
                self.signals_blocked += 1
                return EliteGuidance(
                    should_trade=False,
                    direction=direction,
                    confidence=confidence,
                    position_multiplier=0.0,
                    stop_adjustment=1.0,
                    reason=" | ".join(reasons),
                    consensus_score=consensus_score,
                    accuracy_weight=accuracy_weight,
                    predicted_30d_change=pred_30d_change,
                    predicted_90d_change=pred_90d_change
                )
        
        # 5. Dynamic stops
        if self.enable_dynamic_stops:
            is_aligned = position_multiplier >= 1.0
            stop_adjustment, stop_reason = self.dynamic_stops.get_stop_adjustment(
                direction, is_aligned, confidence
            )
            reasons.append(f"Stop: {stop_reason}")
        
        # Apply consensus boost/penalty
        if consensus_score > 0.8:
            position_multiplier *= 1.1
            reasons.append(f"High consensus boost (+10%)")
        elif consensus_score < 0.5:
            position_multiplier *= 0.8
            reasons.append(f"Low consensus penalty (-20%)")
        
        # Clamp final multiplier
        position_multiplier = max(0.25, min(2.5, position_multiplier))
        
        self.signals_allowed += 1
        
        return EliteGuidance(
            should_trade=True,
            direction=direction,
            confidence=confidence,
            position_multiplier=position_multiplier,
            stop_adjustment=stop_adjustment,
            reason=" | ".join(reasons),
            consensus_score=consensus_score,
            accuracy_weight=accuracy_weight,
            predicted_30d_change=pred_30d_change,
            predicted_90d_change=pred_90d_change
        )
    
    def check_early_exit(self, trade_id: str) -> Tuple[bool, str]:
        """Check if a trade should exit early"""
        if not self.enable_early_exit or not self.current_30d_prediction:
            return False, "Early exit disabled"
        
        pred_30d = self.current_30d_prediction
        pred_change = (pred_30d.predicted_price - pred_30d.current_price) / pred_30d.current_price
        
        return self.early_exit.check_early_exit(
            trade_id, pred_change, pred_30d.confidence
        )
    
    def register_trade_for_early_exit(self, trade_id: str, direction: str):
        """Register a trade for early exit monitoring"""
        if self.enable_early_exit and self.current_30d_prediction:
            pred = self.current_30d_prediction
            pred_change = (pred.predicted_price - pred.current_price) / pred.current_price
            self.early_exit.register_trade(trade_id, direction, pred_change)
    
    def close_trade(self, trade_id: str):
        """Close a trade (remove from early exit tracking)"""
        self.early_exit.close_trade(trade_id)
    
    def get_report(self) -> str:
        """Get comprehensive report"""
        lines = [
            "",
            "=" * 70,
            "🔮 ELITE PREDICTION SYSTEM V2 REPORT",
            "=" * 70,
            f"Total Signals Evaluated: {self.total_signals}",
            f"Signals Allowed: {self.signals_allowed}",
            f"Signals Blocked: {self.signals_blocked}",
            f"Block Rate: {self.signals_blocked / self.total_signals * 100:.1f}%" if self.total_signals > 0 else "Block Rate: N/A",
            ""
        ]
        
        if self.enable_direction_filter:
            stats = self.direction_filter.get_stats()
            lines.append("📊 Direction Filter:")
            lines.append(f"   Aligned: {stats['aligned']} | Strong: {stats['strong_aligned']} | Conflict: {stats['conflicted']}")
            lines.append(f"   Blocked: {stats['blocked']} | Neutral: {stats['neutral']}")
            lines.append(f"   Alignment Rate: {stats['alignment_rate']*100:.1f}%")
        
        if self.enable_consensus:
            stats = self.consensus_checker.get_stats()
            lines.append("📊 Multi-Horizon Consensus:")
            lines.append(f"   Reached: {stats['consensus_reached']} | Failed: {stats['consensus_failed']}")
            lines.append(f"   Consensus Rate: {stats['consensus_rate']*100:.1f}%")
        
        if self.enable_accuracy_weighting:
            lines.append("📊 Accuracy Weighting:")
            lines.append(f"   Current Weight: {self.accuracy_tracker.get_accuracy_weight():.2f}x")
            lines.append(f"   Hit Rate: {self.accuracy_tracker.get_hit_rate()*100:.1f}%")
        
        if self.enable_dynamic_stops:
            stats = self.dynamic_stops.get_stats()
            lines.append("📊 Dynamic Stops:")
            lines.append(f"   Tightened: {stats['tightened']} | Widened: {stats['widened']} | Unchanged: {stats['unchanged']}")
        
        if self.enable_early_exit:
            stats = self.early_exit.get_stats()
            lines.append("📊 Early Exit:")
            lines.append(f"   Triggered: {stats['early_exits_triggered']} | Checks: {stats['checks_performed']}")
        
        if self.enable_market_timing:
            stats = self.market_timer.get_stats()
            lines.append("📊 Market Timing:")
            lines.append(f"   Allowed: {stats['allowed']} | Blocked (conf): {stats['blocked_low_conf']}")
            lines.append(f"   Blocked (flip): {stats['blocked_flip_flop']} | Blocked (cons): {stats['blocked_low_consensus']}")
            lines.append(f"   Pass Rate: {stats['pass_rate']*100:.1f}%")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


def create_elite_prediction_system_v2(
    enable_all: bool = True,
    strict_mode: bool = True,
    min_confidence: float = 0.50,
    min_consensus: float = 0.60
) -> ElitePredictionSystemV2:
    """
    Factory function to create Elite Prediction System V2.
    
    Args:
        enable_all: Enable all features
        strict_mode: Use strict settings (block conflicts, require consensus)
        min_confidence: Minimum confidence threshold
        min_consensus: Minimum consensus threshold
    """
    return ElitePredictionSystemV2(
        enable_direction_filter=enable_all,
        enable_consensus=enable_all,
        enable_accuracy_weighting=enable_all,
        enable_dynamic_stops=enable_all,
        enable_early_exit=enable_all,
        enable_market_timing=enable_all,
        block_on_conflict=strict_mode,
        require_consensus=strict_mode,
        min_confidence=min_confidence,
        min_consensus=min_consensus
    )
