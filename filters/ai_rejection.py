"""
AI Rejection Filter
Uses machine learning model to score trade setups
Rejects trades with low confidence scores
Model will be trained on past predictions and outcomes
"""

import os
import pickle
from typing import Dict, Tuple, Optional, List
import numpy as np
import logging
from config import (
    AI_CONFIDENCE_THRESHOLD,
    AI_MODEL_PATH,
    AI_FEATURE_WINDOW
)

logger = logging.getLogger(__name__)


class AIRejectionFilter:
    """
    Filter #3: AI-based Trade Rejection
    Uses trained model to score setups and reject low-confidence trades
    """

    def __init__(self):
        self.name = "AIRejection"
        self.model = None
        self.model_loaded = False
        self._load_model()

    def _load_model(self):
        """Load trained model if it exists"""
        if os.path.exists(AI_MODEL_PATH):
            try:
                with open(AI_MODEL_PATH, 'rb') as f:
                    self.model = pickle.load(f)
                self.model_loaded = True
                logger.info(f"✅ {self.name}: Model loaded from {AI_MODEL_PATH}")
            except Exception as e:
                logger.warning(f"⚠️  {self.name}: Failed to load model: {e}")
                self.model_loaded = False
        else:
            logger.info(f"ℹ️  {self.name}: No trained model found (will use rule-based scoring)")
            self.model_loaded = False

    def check(self, market_state: Dict, signal_direction: str,
             strategy_name: str) -> Tuple[bool, str]:
        """
        Check if trade setup passes AI confidence threshold

        Args:
            market_state: Complete market state
            signal_direction: 'long' or 'short'
            strategy_name: 'breakout' or 'pullback'

        Returns:
            (passed: bool, reason: str)
        """
        try:
            # Extract features from market state
            features = self._extract_features(market_state, signal_direction, strategy_name)

            if features is None:
                logger.warning(f"{self.name}: Failed to extract features")
                # Default to allowing trade if feature extraction fails
                return True, "Feature extraction failed (allowed by default)"

            # Get confidence score
            if self.model_loaded and self.model is not None:
                confidence = self._predict_with_model(features)
            else:
                confidence = self._rule_based_score(features, market_state, signal_direction)

            # Check against threshold
            if confidence < AI_CONFIDENCE_THRESHOLD:
                return False, f"AI confidence too low ({confidence:.1f} < {AI_CONFIDENCE_THRESHOLD})"

            logger.info(f"✅ {self.name}: Trade confidence acceptable ({confidence:.1f})")
            return True, f"AI confidence OK ({confidence:.1f})"

        except Exception as e:
            logger.error(f"❌ {self.name}: Error during filter check: {e}")
            # On error, default to allowing trade (fail open)
            return True, f"Filter error (allowed): {e}"

    def _extract_features(self, market_state: Dict, signal_direction: str,
                         strategy_name: str) -> Optional[Dict]:
        """
        Extract features for AI model

        Features include:
        - Price action patterns
        - Volume characteristics
        - Volatility metrics
        - Trend strength
        - Multi-timeframe alignment
        - Market regime indicators
        """
        try:
            features = {}
            timeframes = market_state.get('timeframes', {})

            # Get data from primary timeframe (15m)
            primary_tf = '15m'
            if primary_tf not in timeframes:
                # Fall back to first available
                primary_tf = list(timeframes.keys())[0] if timeframes else None

            if not primary_tf:
                return None

            tf_data = timeframes[primary_tf]

            # === TREND FEATURES ===
            trend = tf_data.get('trend', {})
            features['trend_strength'] = trend.get('trend_strength', 0)
            features['trend_direction'] = 1 if trend.get('trend_direction') == 'up' else -1 if trend.get('trend_direction') == 'down' else 0
            features['rsi'] = trend.get('rsi', 50)

            # === VOLATILITY FEATURES ===
            atr = tf_data.get('atr', {})
            features['atr_percentile'] = atr.get('atr_percentile', 50)
            features['is_compressed'] = 1 if atr.get('is_compressed', False) else 0
            features['atr_value'] = atr.get('atr', 0)

            # === VOLUME FEATURES ===
            volume = tf_data.get('volume', {})
            features['volume_ratio'] = volume.get('volume_ratio', 1.0)
            features['volume_trend'] = 1 if volume.get('volume_trend') == 'increasing' else -1 if volume.get('volume_trend') == 'decreasing' else 0
            features['volume_delta_positive'] = 1 if volume.get('volume_delta_positive', False) else 0

            # === MARKET REGIME FEATURES ===
            funding = market_state.get('funding_rate', {})
            features['funding_rate'] = funding.get('funding_rate', 0) if funding else 0

            oi = market_state.get('open_interest', {})
            features['open_interest'] = oi.get('open_interest', 0) if oi else 0

            # === SIGNAL FEATURES ===
            features['signal_direction'] = 1 if signal_direction == 'long' else -1
            features['strategy_breakout'] = 1 if strategy_name == 'breakout' else 0
            features['strategy_pullback'] = 1 if strategy_name == 'pullback' else 0

            # === TIMEFRAME ALIGNMENT ===
            # Check how many timeframes agree
            aligned_count = 0
            total_count = 0
            for tf in timeframes.values():
                tf_trend = tf.get('trend', {})
                tf_dir = tf_trend.get('trend_direction', 'sideways')
                if tf_dir != 'sideways':
                    total_count += 1
                    if (signal_direction == 'long' and tf_dir == 'up') or \
                       (signal_direction == 'short' and tf_dir == 'down'):
                        aligned_count += 1

            features['timeframe_alignment_ratio'] = aligned_count / total_count if total_count > 0 else 0

            return features

        except Exception as e:
            logger.error(f"{self.name}: Feature extraction error: {e}")
            return None

    def _predict_with_model(self, features: Dict) -> float:
        """
        Use trained ML model to predict confidence score

        Returns:
            Confidence score (0-100)
        """
        try:
            # Convert features to format expected by model
            feature_array = self._features_to_array(features)

            # Get prediction
            prediction = self.model.predict_proba([feature_array])[0]

            # Convert to 0-100 scale
            confidence = prediction[1] * 100  # Probability of success class

            return confidence

        except Exception as e:
            logger.error(f"{self.name}: Model prediction error: {e}")
            # Fall back to rule-based
            return self._rule_based_score(features, None, None)

    def _features_to_array(self, features: Dict) -> np.ndarray:
        """Convert feature dict to numpy array for model"""
        # Define feature order (must match training)
        feature_order = [
            'trend_strength',
            'trend_direction',
            'rsi',
            'atr_percentile',
            'is_compressed',
            'volume_ratio',
            'volume_trend',
            'volume_delta_positive',
            'funding_rate',
            'signal_direction',
            'strategy_breakout',
            'strategy_pullback',
            'timeframe_alignment_ratio'
        ]

        feature_array = []
        for feat in feature_order:
            feature_array.append(features.get(feat, 0))

        return np.array(feature_array)

    def _rule_based_score(self, features: Dict, market_state: Optional[Dict],
                         signal_direction: Optional[str]) -> float:
        """
        Rule-based scoring when no trained model available
        Returns confidence score (0-100)
        """
        score = 50.0  # Start at neutral

        # Trend strength (+20 max)
        trend_strength = features.get('trend_strength', 0)
        score += trend_strength * 20

        # Trend direction alignment (+15)
        if features.get('trend_direction', 0) == features.get('signal_direction', 0):
            score += 15

        # Timeframe alignment (+20 max)
        alignment = features.get('timeframe_alignment_ratio', 0)
        score += alignment * 20

        # Volume confirmation (+10)
        if features.get('volume_ratio', 1.0) > 1.2 and features.get('volume_delta_positive', 0) == 1:
            score += 10

        # Volatility compression bonus (+10)
        if features.get('is_compressed', 0) == 1:
            score += 10

        # RSI not extreme (+5)
        rsi = features.get('rsi', 50)
        if 30 < rsi < 70:
            score += 5

        # Penalties
        # Extreme funding (-15)
        funding = abs(features.get('funding_rate', 0))
        if funding > 0.0005:
            score -= 15

        # Wrong volume delta (-10)
        if features.get('volume_delta_positive', 0) != (1 if features.get('signal_direction', 0) == 1 else 0):
            score -= 10

        # Clip to 0-100
        score = max(0, min(100, score))

        return score

    def save_prediction_for_training(self, features: Dict, confidence: float,
                                    trade_id: str, timestamp: str):
        """
        Save prediction for later training
        This will be used to build training dataset
        """
        # Import here to avoid circular dependency
        from model_learning.data_collector import save_prediction

        try:
            save_prediction({
                'trade_id': trade_id,
                'timestamp': timestamp,
                'features': features,
                'confidence': confidence,
                'outcome': None  # Will be filled in later
            })
        except Exception as e:
            logger.error(f"{self.name}: Failed to save prediction: {e}")

    def get_feature_importance(self) -> Optional[Dict]:
        """
        Get feature importance from trained model

        Returns:
            Dict mapping feature names to importance scores
        """
        if not self.model_loaded or self.model is None:
            return None

        try:
            # For tree-based models
            if hasattr(self.model, 'feature_importances_'):
                feature_names = [
                    'trend_strength', 'trend_direction', 'rsi',
                    'atr_percentile', 'is_compressed',
                    'volume_ratio', 'volume_trend', 'volume_delta_positive',
                    'funding_rate', 'signal_direction',
                    'strategy_breakout', 'strategy_pullback',
                    'timeframe_alignment_ratio'
                ]

                importances = self.model.feature_importances_
                return dict(zip(feature_names, importances))

        except Exception as e:
            logger.error(f"{self.name}: Failed to get feature importance: {e}")

        return None
