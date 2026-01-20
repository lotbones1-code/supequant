"""
Model Learning Module
Collects data and trains AI rejection model

Components:
- DataCollector: Collects trade signals and outcomes
- ModelTrainer: Trains rejection model
- schema: Defines training data structure
- ingest_research: Parses historical data for training
"""

from .data_collector import DataCollector
from .model_trainer import ModelTrainer
from .schema import TradeSignalRecord, SignalOutcome, extract_features_from_market_state
from .ingest_research import ResearchDataIngestor

__all__ = [
    'DataCollector',
    'ModelTrainer',
    'TradeSignalRecord',
    'SignalOutcome',
    'extract_features_from_market_state',
    'ResearchDataIngestor'
]
