"""
Research Data Ingestion
Parses historical trade signals and outcomes for model training

This module:
- Reads past trade logs
- Extracts features and outcomes
- Validates data quality
- Converts to TradeSignalRecord format
- Prepares for model training
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from .schema import TradeSignalRecord, SignalOutcome

logger = logging.getLogger(__name__)


class ResearchDataIngestor:
    """
    Ingests historical trading data for model training

    Processes:
    - Trade logs (trades.log)
    - Filter decision logs (filters.log)
    - Training data files (training_data/*.json)
    """

    def __init__(self, data_dir: str = "model_learning/training_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.records: List[TradeSignalRecord] = []
        self.statistics = {
            'total_records': 0,
            'good_quality': 0,
            'partial_quality': 0,
            'poor_quality': 0,
            'wins': 0,
            'losses': 0,
            'breakevens': 0,
            'unknown': 0
        }

    def ingest_from_json_files(self) -> int:
        """
        Load training data from JSON files in training_data directory

        Returns:
            Number of records loaded
        """
        json_files = list(self.data_dir.glob("*.json"))
        logger.info(f"📥 Found {len(json_files)} JSON files in {self.data_dir}")

        loaded_count = 0
        for json_file in json_files:
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Handle both single record and list of records
                if isinstance(data, list):
                    for record_data in data:
                        record = TradeSignalRecord.from_dict(record_data)
                        self.records.append(record)
                        loaded_count += 1
                else:
                    record = TradeSignalRecord.from_dict(data)
                    self.records.append(record)
                    loaded_count += 1

            except Exception as e:
                logger.error(f"❌ Error loading {json_file}: {e}")
                continue

        logger.info(f"✅ Loaded {loaded_count} records from JSON files")
        self._update_statistics()
        return loaded_count

    def ingest_from_trade_log(self, log_file: str = "logs/trades.log") -> int:
        """
        Parse trade log file to extract signal records

        This is a placeholder - would need to parse actual log format
        """
        log_path = Path(log_file)
        if not log_path.exists():
            logger.warning(f"⚠️  Trade log not found: {log_file}")
            return 0

        # TODO: Implement log parsing
        # Would need to:
        # 1. Read log file line by line
        # 2. Extract trade signals and outcomes
        # 3. Match outcomes to signals
        # 4. Create TradeSignalRecord for each
        # 5. Handle missing data gracefully

        logger.info("📝 Trade log parsing not yet implemented")
        return 0

    def filter_by_quality(self, min_quality: str = 'partial') -> List[TradeSignalRecord]:
        """
        Filter records by data quality

        Args:
            min_quality: 'good', 'partial', or 'poor'

        Returns:
            Filtered list of records
        """
        quality_order = {'good': 2, 'partial': 1, 'poor': 0}
        min_level = quality_order.get(min_quality, 0)

        filtered = [
            r for r in self.records
            if quality_order.get(r.data_quality, 0) >= min_level
        ]

        logger.info(f"📊 Filtered to {len(filtered)} records with quality >= {min_quality}")
        return filtered

    def filter_by_outcome(self, outcome: SignalOutcome) -> List[TradeSignalRecord]:
        """
        Filter records by outcome type

        Useful for balancing training data
        """
        filtered = [r for r in self.records if r.outcome == outcome]
        logger.info(f"📊 Filtered to {len(filtered)} records with outcome = {outcome.value}")
        return filtered

    def get_training_data(self, min_quality: str = 'partial',
                         balance_classes: bool = True) -> tuple:
        """
        Prepare training data for ML model

        Returns:
            (X, y) where X is features and y is labels
        """
        # Filter by quality
        records = self.filter_by_quality(min_quality)

        # Remove unknown outcomes
        records = [r for r in records if r.outcome != SignalOutcome.UNKNOWN]

        if len(records) == 0:
            logger.warning("⚠️  No valid training data available")
            return [], []

        # Balance classes if requested
        if balance_classes:
            records = self._balance_classes(records)

        # Extract features and labels
        X = []
        y = []

        for record in records:
            # Convert features dict to list (must be in consistent order)
            feature_list = self._features_to_list(record.features)
            X.append(feature_list)

            # Convert outcome to binary label (1 = win, 0 = loss/breakeven)
            label = 1 if record.outcome == SignalOutcome.WIN else 0
            y.append(label)

        logger.info(f"📊 Prepared training data: {len(X)} samples")
        logger.info(f"   Class distribution: {sum(y)} wins, {len(y) - sum(y)} losses")

        return X, y

    def _balance_classes(self, records: List[TradeSignalRecord]) -> List[TradeSignalRecord]:
        """
        Balance wins and losses for training

        Uses undersampling of majority class
        """
        wins = [r for r in records if r.outcome == SignalOutcome.WIN]
        losses = [r for r in records if r.outcome in [SignalOutcome.LOSS, SignalOutcome.BREAKEVEN]]

        min_count = min(len(wins), len(losses))

        if min_count == 0:
            return records

        # Undersample majority class
        wins_balanced = wins[:min_count]
        losses_balanced = losses[:min_count]

        balanced = wins_balanced + losses_balanced
        logger.info(f"⚖️  Balanced classes: {len(wins_balanced)} wins, {len(losses_balanced)} losses")

        return balanced

    def _features_to_list(self, features: Dict) -> List[float]:
        """
        Convert features dict to ordered list for ML

        IMPORTANT: Order must be consistent!
        """
        # Define feature order (must match when using model)
        feature_keys = [
            'price_change_1h',
            'price_change_4h',
            'price_change_24h',
            'atr_15m',
            'atr_1h',
            'trend_strength_4h',
            'volume_ratio_15m',
            'funding_rate',
            'open_interest_change',
            'rsi_15m',
            'rsi_1h',
            'distance_from_ema',
            'btc_correlation',
            'timeframe_alignment_score',
            'trap_risk',
            'recent_fakeouts',
            'recent_stop_hunts'
        ]

        # Convert categorical features to numeric
        def trend_to_num(trend: str) -> float:
            return {'up': 1.0, 'down': -1.0, 'sideways': 0.0}.get(trend, 0.0)

        def vol_regime_to_num(regime: str) -> float:
            return {'low': 0.25, 'normal': 0.5, 'high': 0.75, 'extreme': 1.0}.get(regime, 0.5)

        # Add numeric conversions
        numeric_features = []
        for key in feature_keys:
            value = features.get(key, 0.0)
            if isinstance(value, (int, float)):
                numeric_features.append(float(value))
            else:
                numeric_features.append(0.0)

        # Add trend features
        numeric_features.append(trend_to_num(features.get('trend_15m', 'sideways')))
        numeric_features.append(trend_to_num(features.get('trend_1h', 'sideways')))
        numeric_features.append(trend_to_num(features.get('trend_4h', 'sideways')))
        numeric_features.append(trend_to_num(features.get('btc_trend_4h', 'sideways')))

        # Add volatility regime
        numeric_features.append(vol_regime_to_num(features.get('volatility_regime', 'normal')))

        # Add boolean features
        numeric_features.append(1.0 if features.get('volume_spike', False) else 0.0)
        numeric_features.append(1.0 if features.get('consolidation_detected', False) else 0.0)
        numeric_features.append(1.0 if features.get('breakout_detected', False) else 0.0)
        numeric_features.append(1.0 if features.get('pullback_detected', False) else 0.0)
        numeric_features.append(1.0 if features.get('btc_divergence', False) else 0.0)

        return numeric_features

    def _update_statistics(self):
        """Update statistics about loaded data"""
        self.statistics['total_records'] = len(self.records)

        for record in self.records:
            # Quality distribution
            if record.data_quality == 'good':
                self.statistics['good_quality'] += 1
            elif record.data_quality == 'partial':
                self.statistics['partial_quality'] += 1
            else:
                self.statistics['poor_quality'] += 1

            # Outcome distribution
            if record.outcome == SignalOutcome.WIN:
                self.statistics['wins'] += 1
            elif record.outcome == SignalOutcome.LOSS:
                self.statistics['losses'] += 1
            elif record.outcome == SignalOutcome.BREAKEVEN:
                self.statistics['breakevens'] += 1
            else:
                self.statistics['unknown'] += 1

    def print_statistics(self):
        """Print summary of loaded data"""
        stats = self.statistics

        logger.info("\n" + "="*60)
        logger.info("RESEARCH DATA INGESTION SUMMARY")
        logger.info("="*60)
        logger.info(f"Total records: {stats['total_records']}")
        logger.info(f"\nData Quality:")
        logger.info(f"  Good: {stats['good_quality']}")
        logger.info(f"  Partial: {stats['partial_quality']}")
        logger.info(f"  Poor: {stats['poor_quality']}")
        logger.info(f"\nOutcome Distribution:")
        logger.info(f"  Wins: {stats['wins']}")
        logger.info(f"  Losses: {stats['losses']}")
        logger.info(f"  Breakevens: {stats['breakevens']}")
        logger.info(f"  Unknown: {stats['unknown']}")

        if stats['wins'] + stats['losses'] > 0:
            win_rate = stats['wins'] / (stats['wins'] + stats['losses']) * 100
            logger.info(f"\nWin Rate: {win_rate:.1f}%")

        logger.info("="*60 + "\n")

    def export_to_csv(self, output_file: str = "model_learning/training_data/dataset.csv"):
        """
        Export records to CSV for analysis

        Useful for manual review and external tools
        """
        import csv

        if len(self.records) == 0:
            logger.warning("⚠️  No records to export")
            return

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='') as f:
            # Would need to flatten record structure for CSV
            # TODO: Implement CSV export
            logger.info(f"📄 CSV export not yet implemented")
