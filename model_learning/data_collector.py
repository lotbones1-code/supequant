"""
Data Collector
Collects predictions and outcomes for model training
"""

import json
import os
from typing import Dict, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataCollector:
    """
    Collects training data for AI model
    Stores predictions and their outcomes
    """

    def __init__(self, data_dir: str = "model_learning/training_data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self.predictions_file = os.path.join(data_dir, "predictions.jsonl")
        self.labeled_file = os.path.join(data_dir, "labeled_data.jsonl")

        logger.info(f"✅ DataCollector initialized: {data_dir}")

    def save_prediction(self, prediction: Dict):
        """
        Save a prediction for later labeling

        Args:
            prediction: Dict with features, confidence, trade_id
        """
        try:
            prediction['saved_at'] = datetime.now().isoformat()

            with open(self.predictions_file, 'a') as f:
                f.write(json.dumps(prediction) + '\n')

            logger.debug(f"Prediction saved: {prediction.get('trade_id')}")

        except Exception as e:
            logger.error(f"Failed to save prediction: {e}")

    def label_prediction(self, trade_id: str, outcome: str, pnl: float):
        """
        Label a prediction with its outcome

        Args:
            trade_id: Trade ID
            outcome: 'win' or 'loss'
            pnl: Profit/loss amount
        """
        try:
            # Load prediction
            prediction = self._find_prediction(trade_id)

            if not prediction:
                logger.warning(f"Prediction not found: {trade_id}")
                return

            # Add label
            prediction['outcome'] = outcome
            prediction['pnl'] = pnl
            prediction['labeled_at'] = datetime.now().isoformat()

            # Save to labeled data
            with open(self.labeled_file, 'a') as f:
                f.write(json.dumps(prediction) + '\n')

            logger.info(f"✅ Prediction labeled: {trade_id} -> {outcome}")

        except Exception as e:
            logger.error(f"Failed to label prediction: {e}")

    def _find_prediction(self, trade_id: str) -> Dict:
        """Find prediction by trade ID"""
        try:
            if not os.path.exists(self.predictions_file):
                return None

            with open(self.predictions_file, 'r') as f:
                for line in f:
                    pred = json.loads(line)
                    if pred.get('trade_id') == trade_id:
                        return pred

        except Exception as e:
            logger.error(f"Error finding prediction: {e}")

        return None

    def get_labeled_data(self) -> List[Dict]:
        """
        Get all labeled data for training

        Returns:
            List of labeled predictions
        """
        data = []

        try:
            if not os.path.exists(self.labeled_file):
                return data

            with open(self.labeled_file, 'r') as f:
                for line in f:
                    data.append(json.loads(line))

            logger.info(f"Loaded {len(data)} labeled samples")

        except Exception as e:
            logger.error(f"Error loading labeled data: {e}")

        return data

    def get_statistics(self) -> Dict:
        """Get data collection statistics"""
        predictions_count = 0
        labeled_count = 0

        if os.path.exists(self.predictions_file):
            with open(self.predictions_file, 'r') as f:
                predictions_count = sum(1 for _ in f)

        if os.path.exists(self.labeled_file):
            with open(self.labeled_file, 'r') as f:
                labeled_count = sum(1 for _ in f)

        return {
            'total_predictions': predictions_count,
            'labeled_samples': labeled_count,
            'unlabeled_samples': predictions_count - labeled_count
        }


# Standalone function for use in filters
def save_prediction(prediction: Dict):
    """Standalone function to save prediction"""
    collector = DataCollector()
    collector.save_prediction(prediction)
