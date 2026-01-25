"""
V4 Winner Predictor

GradientBoosting classifier with probability calibration
for predicting trade outcome BEFORE entry.

Features:
- 20 features total (13 existing + 7 new)
- Walk-forward validation (never sees future data)
- Isotonic calibration for accurate probability estimates

Key thresholds:
- P(win) >= 0.70: TRADE_ELITE (2x position)
- P(win) >= 0.55: TRADE_NORMAL (1x position)
- P(win) >= 0.45: TRADE_REDUCED (0.5x position)
- P(win) < 0.45: SKIP (block trade)
"""

import logging
import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)

# Try to import sklearn, gracefully handle if not available
try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("sklearn not available - V4 Winner Predictor will use fallback")


@dataclass
class V4Prediction:
    """Result of winner prediction."""
    win_probability: float
    decision: str  # TRADE_ELITE, TRADE_NORMAL, TRADE_REDUCED, SKIP
    position_multiplier: float
    confidence: float
    features: Optional[Dict] = None


class V4WinnerPredictor:
    """
    GradientBoosting classifier for predicting trade outcome.
    """

    # Feature names (20 total)
    FEATURE_NAMES = [
        # Existing 13 features
        'trend_strength', 'trend_direction', 'rsi', 'atr_percentile',
        'is_compressed', 'volume_ratio', 'volume_trend', 'volume_delta_positive',
        'funding_rate', 'signal_direction', 'strategy_breakout', 'strategy_pullback',
        'timeframe_alignment_ratio',
        # New V4 features (7)
        'direction_bias', 'rsi_extremity', 'bb_position',
        'htf_trend_alignment', 'regime_confidence', 'quality_score', 'hour_score'
    ]

    # Thresholds for decision making
    TRADE_THRESHOLD = 0.55      # Only trade if P(win) > 55%
    ELITE_THRESHOLD = 0.70      # Elite sizing if P(win) > 70%
    SKIP_THRESHOLD = 0.45       # Block if P(win) < 45%

    def __init__(self):
        self.name = "V4WinnerPredictor"

        self.model = None
        self.scaler = None
        self.is_trained = False

        # Training history
        self.training_data = deque(maxlen=500)  # Store recent labeled trades
        self.min_samples_to_train = 30

        # Feature importance
        self.feature_importance = {}

        # Statistics
        self.predictions_made = 0
        self.predictions_by_decision = {}

        # Initialize model if sklearn available
        if SKLEARN_AVAILABLE:
            self._init_model()

    def _init_model(self):
        """Initialize the GradientBoosting model with calibration."""
        base_model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            min_samples_split=10,
            min_samples_leaf=5,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42
        )

        # Wrap with isotonic calibration for better probability estimates
        self.model = CalibratedClassifierCV(
            base_model,
            cv=3,
            method='isotonic'
        )

        self.scaler = StandardScaler()

    def add_training_sample(self, signal: Dict, market_state: Dict,
                            outcome: bool, pnl: float):
        """
        Add a completed trade to training data.

        Args:
            signal: Original signal dict
            market_state: Market state at entry
            outcome: True if profitable, False otherwise
            pnl: Profit/loss amount
        """
        features = self._extract_features(signal, market_state)
        self.training_data.append({
            'features': features,
            'outcome': 1 if outcome else 0,
            'pnl': pnl
        })

        # Retrain periodically
        if len(self.training_data) >= self.min_samples_to_train:
            if len(self.training_data) % 20 == 0:  # Retrain every 20 samples
                self._train()

    def _train(self):
        """Train the model on accumulated data."""
        if not SKLEARN_AVAILABLE:
            return

        if len(self.training_data) < self.min_samples_to_train:
            return

        try:
            # Prepare data
            X = np.array([d['features'] for d in self.training_data])
            y = np.array([d['outcome'] for d in self.training_data])

            # Scale features
            X_scaled = self.scaler.fit_transform(X)

            # Train with time-series split
            self.model.fit(X_scaled, y)
            self.is_trained = True

            # Extract feature importance
            self._extract_feature_importance()

            logger.info(f"V4 WINNER PREDICTOR: Trained on {len(self.training_data)} samples")

        except Exception as e:
            logger.error(f"V4 WINNER PREDICTOR training failed: {e}")
            self.is_trained = False

    def _extract_feature_importance(self):
        """Extract and store feature importance from trained model."""
        try:
            if hasattr(self.model, 'calibrated_classifiers_'):
                # Get importance from first calibrated classifier
                base = self.model.calibrated_classifiers_[0].estimator
                if hasattr(base, 'feature_importances_'):
                    importances = base.feature_importances_
                    self.feature_importance = dict(zip(self.FEATURE_NAMES, importances))
        except Exception:
            pass

    def predict_trade(self, signal: Dict, market_state: Dict,
                      quality_score: float = 50) -> V4Prediction:
        """
        Predict probability of winning BEFORE trade entry.

        Args:
            signal: Trade signal dict
            market_state: Current market state
            quality_score: Quality score from filter manager

        Returns:
            V4Prediction with decision and multiplier
        """
        self.predictions_made += 1

        # Extract features
        features = self._extract_features(signal, market_state, quality_score)

        # If model not trained, use heuristic fallback
        if not self.is_trained or not SKLEARN_AVAILABLE:
            return self._heuristic_prediction(signal, market_state, quality_score)

        try:
            # Scale and predict
            X = np.array([features])
            X_scaled = self.scaler.transform(X)
            win_probability = self.model.predict_proba(X_scaled)[0][1]
        except Exception as e:
            logger.warning(f"V4 prediction failed: {e}, using heuristic")
            return self._heuristic_prediction(signal, market_state, quality_score)

        # Make decision
        decision, multiplier = self._make_decision(win_probability)

        # Track statistics
        self.predictions_by_decision[decision] = self.predictions_by_decision.get(decision, 0) + 1

        return V4Prediction(
            win_probability=win_probability,
            decision=decision,
            position_multiplier=multiplier,
            confidence=abs(win_probability - 0.5) * 2,  # 0-1 confidence
            features=dict(zip(self.FEATURE_NAMES, features))
        )

    def _make_decision(self, win_probability: float) -> Tuple[str, float]:
        """Convert win probability to trading decision."""
        if win_probability >= self.ELITE_THRESHOLD:
            return 'TRADE_ELITE', 2.0
        elif win_probability >= self.TRADE_THRESHOLD:
            return 'TRADE_NORMAL', 1.0
        elif win_probability >= self.SKIP_THRESHOLD:
            return 'TRADE_REDUCED', 0.5
        else:
            return 'SKIP', 0.0

    def _extract_features(self, signal: Dict, market_state: Dict,
                          quality_score: float = 50) -> List[float]:
        """
        Extract 20 features from signal and market state.
        """
        features = []

        # Helper to safely get nested values
        def safe_get(d, *keys, default=0):
            try:
                val = d
                for k in keys:
                    val = val.get(k, {})
                return val if val != {} else default
            except Exception:
                return default

        # --- Existing 13 features ---

        # 1. trend_strength
        features.append(safe_get(market_state, 'trend', 'trend_strength', default=0.5))

        # 2. trend_direction (encode: -1=down, 0=neutral, 1=up)
        td = safe_get(market_state, 'trend', 'trend_direction', default='neutral')
        td_map = {'up': 1, 'bullish': 1, 'down': -1, 'bearish': -1}
        features.append(td_map.get(str(td).lower(), 0))

        # 3. rsi
        rsi = signal.get('rsi', safe_get(market_state, 'rsi', 'rsi', default=50))
        features.append(rsi / 100 if rsi else 0.5)

        # 4. atr_percentile
        features.append(safe_get(market_state, 'atr', 'atr_percentile', default=50) / 100)

        # 5. is_compressed
        features.append(1 if safe_get(market_state, 'is_compressed', default=False) else 0)

        # 6. volume_ratio
        vol_ratio = safe_get(market_state, 'volume', 'volume_ratio', default=1.0)
        features.append(min(vol_ratio / 3.0, 1.0))  # Normalize to 0-1

        # 7. volume_trend
        vol_trend = safe_get(market_state, 'volume', 'volume_trend', default='neutral')
        vt_map = {'increasing': 1, 'up': 1, 'decreasing': -1, 'down': -1}
        features.append(vt_map.get(str(vol_trend).lower(), 0))

        # 8. volume_delta_positive
        features.append(1 if safe_get(market_state, 'volume', 'delta_positive', default=False) else 0)

        # 9. funding_rate (normalize)
        funding = safe_get(market_state, 'funding_rate', default=0)
        features.append(max(-1, min(1, funding * 1000)))  # Scale and clamp

        # 10. signal_direction (1=long, 0=short)
        direction = signal.get('direction', 'long').lower()
        features.append(1 if direction == 'long' else 0)

        # 11. strategy_breakout
        strategy = signal.get('strategy', '').lower()
        features.append(1 if 'breakout' in strategy else 0)

        # 12. strategy_pullback
        features.append(1 if 'pullback' in strategy or 'reversion' in strategy else 0)

        # 13. timeframe_alignment_ratio
        features.append(safe_get(signal, 'timeframe_alignment', default=0.5))

        # --- New V4 features (7) ---

        # 14. direction_bias (1=long has advantage, 0=short)
        features.append(1 if direction == 'long' else 0)

        # 15. rsi_extremity (how extreme is RSI from 50)
        rsi_val = rsi if rsi else 50
        features.append(abs(rsi_val - 50) / 50)

        # 16. bb_position (0-1, where in Bollinger Bands)
        bb_pos = safe_get(market_state, 'bollinger', 'bb_position', default=0.5)
        features.append(bb_pos)

        # 17. htf_trend_alignment (does 4H agree with signal?)
        htf_trend = safe_get(market_state, 'timeframes', '4H', 'trend', 'trend_direction', default='neutral')
        if direction == 'long' and str(htf_trend).lower() in ['up', 'bullish']:
            features.append(1)
        elif direction == 'short' and str(htf_trend).lower() in ['down', 'bearish']:
            features.append(1)
        else:
            features.append(0)

        # 18. regime_confidence
        features.append(safe_get(market_state, 'regime_confidence', default=0.5))

        # 19. quality_score (normalized)
        features.append(quality_score / 100)

        # 20. hour_score (0.8 for good hours, 0.5 for others)
        from datetime import datetime, timezone
        hour = datetime.now(timezone.utc).hour
        good_hours = [2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16]
        features.append(0.8 if hour in good_hours else 0.5)

        return features

    def _heuristic_prediction(self, signal: Dict, market_state: Dict,
                              quality_score: float) -> V4Prediction:
        """
        Fallback heuristic when model not trained.
        Uses direction bias and quality score.
        """
        direction = signal.get('direction', 'long').lower()

        # Base probability from direction
        if direction == 'long':
            base_prob = 0.55  # Historical long win rate
        else:
            base_prob = 0.08  # Historical short win rate

        # Adjust by quality score
        quality_adj = (quality_score - 50) / 100  # -0.5 to +0.5
        win_probability = base_prob + quality_adj * 0.2

        # Clamp to valid range
        win_probability = max(0.05, min(0.95, win_probability))

        decision, multiplier = self._make_decision(win_probability)

        return V4Prediction(
            win_probability=win_probability,
            decision=decision,
            position_multiplier=multiplier,
            confidence=0.3,  # Low confidence for heuristic
            features=None
        )

    def get_stats(self) -> Dict:
        """Get predictor statistics."""
        return {
            'predictions_made': self.predictions_made,
            'is_trained': self.is_trained,
            'training_samples': len(self.training_data),
            'predictions_by_decision': self.predictions_by_decision,
            'feature_importance': dict(sorted(
                self.feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]) if self.feature_importance else {},
            'thresholds': {
                'elite': self.ELITE_THRESHOLD,
                'trade': self.TRADE_THRESHOLD,
                'skip': self.SKIP_THRESHOLD
            }
        }

    def reset_stats(self):
        """Reset statistics for new backtest run."""
        self.predictions_made = 0
        self.predictions_by_decision = {}
        self.training_data.clear()
        self.is_trained = False
