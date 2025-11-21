"""
Model Trainer
Trains AI rejection model on collected data
"""

import pickle
import numpy as np
from typing import Dict, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import logging
from .data_collector import DataCollector
from config import AI_MODEL_PATH, MIN_SAMPLES_FOR_TRAINING

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Trains and evaluates AI rejection model
    """

    def __init__(self):
        self.data_collector = DataCollector()
        self.model = None
        logger.info("✅ ModelTrainer initialized")

    def train_model(self) -> Tuple[bool, Optional[Dict]]:
        """
        Train AI model on collected data

        Returns:
            (success: bool, metrics: Dict)
        """
        try:
            # Load labeled data
            data = self.data_collector.get_labeled_data()

            if len(data) < MIN_SAMPLES_FOR_TRAINING:
                logger.warning(f"Not enough samples for training ({len(data)}/{MIN_SAMPLES_FOR_TRAINING})")
                return False, None

            logger.info(f"Training model on {len(data)} samples")

            # Prepare data
            X, y = self._prepare_training_data(data)

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            # Train model
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42
            )

            self.model.fit(X_train, y_train)

            # Evaluate
            y_pred = self.model.predict(X_test)

            metrics = {
                'accuracy': accuracy_score(y_test, y_pred),
                'precision': precision_score(y_test, y_pred),
                'recall': recall_score(y_test, y_pred),
                'f1': f1_score(y_test, y_pred),
                'samples_train': len(X_train),
                'samples_test': len(X_test)
            }

            logger.info(f"✅ Model trained successfully")
            logger.info(f"   Accuracy: {metrics['accuracy']:.3f}")
            logger.info(f"   Precision: {metrics['precision']:.3f}")
            logger.info(f"   Recall: {metrics['recall']:.3f}")
            logger.info(f"   F1: {metrics['f1']:.3f}")

            # Save model
            self._save_model()

            return True, metrics

        except Exception as e:
            logger.error(f"❌ Error training model: {e}")
            return False, None

    def _prepare_training_data(self, data: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare data for training

        Returns:
            (X: features, y: labels)
        """
        X = []
        y = []

        feature_keys = [
            'trend_strength', 'trend_direction', 'rsi',
            'atr_percentile', 'is_compressed',
            'volume_ratio', 'volume_trend', 'volume_delta_positive',
            'funding_rate', 'signal_direction',
            'strategy_breakout', 'strategy_pullback',
            'timeframe_alignment_ratio'
        ]

        for sample in data:
            features = sample.get('features', {})
            outcome = sample.get('outcome')

            if not features or not outcome:
                continue

            # Extract features in order
            feature_vector = []
            for key in feature_keys:
                feature_vector.append(features.get(key, 0))

            X.append(feature_vector)

            # Label: 1 = win, 0 = loss
            y.append(1 if outcome == 'win' else 0)

        return np.array(X), np.array(y)

    def _save_model(self):
        """Save trained model to disk"""
        try:
            with open(AI_MODEL_PATH, 'wb') as f:
                pickle.dump(self.model, f)

            logger.info(f"✅ Model saved: {AI_MODEL_PATH}")

        except Exception as e:
            logger.error(f"❌ Failed to save model: {e}")

    def load_model(self) -> bool:
        """Load trained model from disk"""
        try:
            with open(AI_MODEL_PATH, 'rb') as f:
                self.model = pickle.load(f)

            logger.info(f"✅ Model loaded: {AI_MODEL_PATH}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            return False

    def get_training_statistics(self) -> Dict:
        """Get training data statistics"""
        return self.data_collector.get_statistics()
