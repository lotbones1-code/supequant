"""
Training Data Schema
Defines standardized structure for ML model training data

This schema ensures consistent data format for:
- Feature collection
- Label assignment
- Model training
- Research ingestion
"""

from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class SignalOutcome(Enum):
    """Possible outcomes for a trade signal"""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    UNKNOWN = "unknown"


class TradeSignalRecord:
    """
    Schema for a single trade signal record

    This represents one potential trade opportunity and its outcome
    """

    def __init__(self):
        # Identification
        self.signal_id: str = ""
        self.timestamp: datetime = None
        self.symbol: str = ""

        # Signal details
        self.direction: str = ""  # 'long' or 'short'
        self.strategy: str = ""  # 'breakout', 'pullback', etc.
        self.entry_price: float = 0.0
        self.stop_price: float = 0.0
        self.target_price: float = 0.0

        # Market features (snapshot at signal time)
        self.features: Dict = {
            # Price action
            'price_change_1h': 0.0,
            'price_change_4h': 0.0,
            'price_change_24h': 0.0,

            # Volatility
            'atr_15m': 0.0,
            'atr_1h': 0.0,
            'volatility_regime': '',  # 'low', 'normal', 'high', 'extreme'

            # Trend
            'trend_15m': '',  # 'up', 'down', 'sideways'
            'trend_1h': '',
            'trend_4h': '',
            'trend_strength_4h': 0.0,

            # Volume
            'volume_ratio_15m': 0.0,
            'volume_spike': False,

            # Market data
            'funding_rate': 0.0,
            'open_interest_change': 0.0,

            # Technical indicators
            'rsi_15m': 0.0,
            'rsi_1h': 0.0,
            'distance_from_ema': 0.0,

            # BTC correlation
            'btc_trend_4h': '',
            'btc_correlation': 0.0,
            'btc_divergence': False,

            # Pattern features
            'consolidation_detected': False,
            'breakout_detected': False,
            'pullback_detected': False,
            'trap_risk': 0.0,

            # Multi-timeframe alignment
            'timeframe_alignment_score': 0.0,

            # Recent history
            'recent_fakeouts': 0,
            'recent_stop_hunts': 0
        }

        # Filter results
        self.filter_results: Dict = {
            'market_regime': {'passed': False, 'reason': ''},
            'multi_timeframe': {'passed': False, 'reason': ''},
            'ai_rejection': {'passed': False, 'reason': ''},
            'pattern_failure': {'passed': False, 'reason': ''},
            'btc_sol_correlation': {'passed': False, 'reason': ''},
            'macro_driver': {'passed': False, 'reason': ''},
            'checklist': {'passed': False, 'score': 0.0}
        }

        # Research filter outputs
        self.research_outputs: Dict = {
            'playbook_setup': '',
            'playbook_confidence': 0.0,
            'checklist_score': 0.0,
            'environment_bias': '',
            'tier_assessment': {}
        }

        # Outcome (filled in later)
        self.trade_executed: bool = False
        self.outcome: SignalOutcome = SignalOutcome.UNKNOWN
        self.outcome_details: Dict = {
            'pnl_pct': 0.0,
            'exit_price': 0.0,
            'exit_reason': '',  # 'target_hit', 'stop_hit', 'manual', 'timeout'
            'bars_held': 0,
            'max_favorable_excursion': 0.0,  # MFE
            'max_adverse_excursion': 0.0  # MAE
        }

        # Metadata
        self.model_version: str = "v1"
        self.data_quality: str = "good"  # 'good', 'partial', 'poor'

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'signal_id': self.signal_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'symbol': self.symbol,
            'direction': self.direction,
            'strategy': self.strategy,
            'entry_price': self.entry_price,
            'stop_price': self.stop_price,
            'target_price': self.target_price,
            'features': self.features,
            'filter_results': self.filter_results,
            'research_outputs': self.research_outputs,
            'trade_executed': self.trade_executed,
            'outcome': self.outcome.value,
            'outcome_details': self.outcome_details,
            'model_version': self.model_version,
            'data_quality': self.data_quality
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'TradeSignalRecord':
        """Load from dictionary"""
        record = cls()
        record.signal_id = data.get('signal_id', '')
        timestamp_str = data.get('timestamp')
        if timestamp_str:
            record.timestamp = datetime.fromisoformat(timestamp_str)
        record.symbol = data.get('symbol', '')
        record.direction = data.get('direction', '')
        record.strategy = data.get('strategy', '')
        record.entry_price = data.get('entry_price', 0.0)
        record.stop_price = data.get('stop_price', 0.0)
        record.target_price = data.get('target_price', 0.0)
        record.features = data.get('features', {})
        record.filter_results = data.get('filter_results', {})
        record.research_outputs = data.get('research_outputs', {})
        record.trade_executed = data.get('trade_executed', False)
        outcome_str = data.get('outcome', 'unknown')
        record.outcome = SignalOutcome(outcome_str)
        record.outcome_details = data.get('outcome_details', {})
        record.model_version = data.get('model_version', 'v1')
        record.data_quality = data.get('data_quality', 'good')
        return record


class FeatureImportance:
    """
    Track which features are most important for predictions

    Used to understand what the model learns
    """

    def __init__(self):
        self.feature_scores: Dict[str, float] = {}
        self.last_updated: datetime = None

    def update(self, feature_name: str, importance: float):
        """Update importance score for a feature"""
        self.feature_scores[feature_name] = importance
        self.last_updated = datetime.now()

    def get_top_features(self, n: int = 10) -> List[tuple]:
        """Get top N most important features"""
        sorted_features = sorted(
            self.feature_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_features[:n]


class ModelPerformance:
    """
    Track model performance metrics over time
    """

    def __init__(self):
        self.metrics: Dict = {
            'accuracy': 0.0,
            'precision': 0.0,
            'recall': 0.0,
            'f1_score': 0.0,
            'auc_roc': 0.0,
            'true_positives': 0,
            'false_positives': 0,
            'true_negatives': 0,
            'false_negatives': 0
        }
        self.last_updated: datetime = None
        self.sample_count: int = 0

    def update(self, y_true: List, y_pred: List):
        """Update metrics with new predictions"""
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

        self.metrics['accuracy'] = accuracy_score(y_true, y_pred)
        self.metrics['precision'] = precision_score(y_true, y_pred, zero_division=0)
        self.metrics['recall'] = recall_score(y_true, y_pred, zero_division=0)
        self.metrics['f1_score'] = f1_score(y_true, y_pred, zero_division=0)

        # Update confusion matrix values
        from sklearn.metrics import confusion_matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        self.metrics['true_positives'] = int(tp)
        self.metrics['false_positives'] = int(fp)
        self.metrics['true_negatives'] = int(tn)
        self.metrics['false_negatives'] = int(fn)

        self.last_updated = datetime.now()
        self.sample_count = len(y_true)


def extract_features_from_market_state(market_state: Dict, btc_market_state: Optional[Dict] = None) -> Dict:
    """
    Extract standardized features from market state

    This function converts raw market_state into the feature schema
    """
    features = {}

    # Extract timeframe data
    timeframes = market_state.get('timeframes', {})

    # Price changes
    if '1H' in timeframes:
        candles_1h = timeframes['1H'].get('candles', [])
        if len(candles_1h) >= 2:
            features['price_change_1h'] = (candles_1h[-1]['close'] - candles_1h[-2]['close']) / candles_1h[-2]['close']

    if '4H' in timeframes:
        candles_4h = timeframes['4H'].get('candles', [])
        if len(candles_4h) >= 2:
            features['price_change_4h'] = (candles_4h[-1]['close'] - candles_4h[-2]['close']) / candles_4h[-2]['close']
        if len(candles_4h) >= 6:
            features['price_change_24h'] = (candles_4h[-1]['close'] - candles_4h[-6]['close']) / candles_4h[-6]['close']

    # Volatility
    if '15m' in timeframes:
        atr_data = timeframes['15m'].get('atr', {})
        features['atr_15m'] = atr_data.get('atr', 0.0)
        vol_data = timeframes['15m'].get('volatility', {})
        features['volatility_regime'] = vol_data.get('volatility_regime', 'normal')

    if '1H' in timeframes:
        atr_data = timeframes['1H'].get('atr', {})
        features['atr_1h'] = atr_data.get('atr', 0.0)

    # Trends
    for tf_name in ['15m', '1H', '4H']:
        if tf_name in timeframes:
            trend_data = timeframes[tf_name].get('trend', {})
            features[f'trend_{tf_name.lower()}'] = trend_data.get('trend_direction', 'sideways')
            if tf_name == '4H':
                features['trend_strength_4h'] = trend_data.get('trend_strength', 0.0)

    # Volume
    if '15m' in timeframes:
        vol_data = timeframes['15m'].get('volume', {})
        features['volume_ratio_15m'] = vol_data.get('volume_ratio', 1.0)
        features['volume_spike'] = vol_data.get('volume_ratio', 1.0) > 2.0

    # Market data
    funding = market_state.get('funding_rate', {})
    features['funding_rate'] = funding.get('funding_rate', 0.0)
    features['open_interest_change'] = market_state.get('open_interest_change', 0.0)

    # BTC correlation
    if btc_market_state:
        btc_timeframes = btc_market_state.get('timeframes', {})
        if '4H' in btc_timeframes:
            btc_trend = btc_timeframes['4H'].get('trend', {})
            features['btc_trend_4h'] = btc_trend.get('trend_direction', 'sideways')
        # TODO: Add correlation calculation

    return features
