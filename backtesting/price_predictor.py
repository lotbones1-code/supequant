"""
Elite Price Prediction System - Backtest Only

Predicts crypto prices for:
- 1 month
- 2-3 months  
- 1 year

Features:
- Multiple prediction models (ensemble)
- Learns from past accuracy
- Tracks prediction performance
- Completely isolated from trading logic
- Only used in backtesting initially

Models:
1. Trend Extrapolation (EMA-based)
2. Volatility-Adjusted Momentum
3. Historical Pattern Matching
4. Regression-Based Forecasting
5. Ensemble (weighted average)
"""

import logging
import numpy as np
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class PricePrediction:
    """A price prediction for a future date"""
    symbol: str
    current_price: float
    predicted_price: float
    prediction_date: str  # ISO format
    target_date: str  # ISO format
    confidence: float  # 0-1
    model_used: str
    time_horizon_days: int
    created_at: str


@dataclass
class PredictionAccuracy:
    """Tracks accuracy of past predictions"""
    prediction_id: str
    predicted_price: float
    actual_price: float
    error_percent: float
    error_absolute: float
    target_date: str
    model_used: str
    evaluated_at: str


class TrendExtrapolator:
    """Predicts price based on trend extrapolation using EMAs"""
    
    def __init__(self, short_ema: int = 20, long_ema: int = 50):
        self.short_ema = short_ema
        self.long_ema = long_ema
    
    def predict(self, prices: List[float], days_ahead: int) -> Tuple[float, float]:
        """Predict price using trend extrapolation. Returns (predicted_price, confidence)"""
        if len(prices) < self.long_ema:
            return prices[-1] if prices else 0.0, 0.1
        
        prices_array = np.array(prices)
        ema_short = self._calculate_ema(prices_array, self.short_ema)
        ema_long = self._calculate_ema(prices_array, self.long_ema)
        
        trend = (ema_short[-1] - ema_long[-1]) / ema_long[-1] if ema_long[-1] > 0 else 0
        momentum = (prices[-1] - prices[-min(20, len(prices))]) / prices[-min(20, len(prices))] if len(prices) > 20 else 0
        
        current_price = prices[-1]
        predicted_price = current_price * (1 + trend * days_ahead / 30) * (1 + momentum * days_ahead / 30)
        
        trend_strength = abs(trend)
        confidence = min(0.8, 0.3 + trend_strength * 2)
        
        return predicted_price, confidence
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA"""
        if len(prices) < period:
            return prices
        
        ema = np.zeros_like(prices)
        multiplier = 2.0 / (period + 1)
        ema[0] = prices[0]
        for i in range(1, len(prices)):
            ema[i] = (prices[i] * multiplier) + (ema[i-1] * (1 - multiplier))
        return ema


class VolatilityMomentumPredictor:
    """Predicts price using volatility-adjusted momentum"""
    
    def __init__(self, lookback: int = 30):
        self.lookback = lookback
    
    def predict(self, prices: List[float], days_ahead: int) -> Tuple[float, float]:
        """Predict using volatility-adjusted momentum"""
        if len(prices) < self.lookback:
            return prices[-1] if prices else 0.0, 0.1
        
        recent_prices = prices[-self.lookback:]
        prices_array = np.array(recent_prices)
        returns = np.diff(prices_array) / prices_array[:-1]
        volatility = np.std(returns) * np.sqrt(252)
        momentum = np.mean(returns) * 252
        
        current_price = prices[-1]
        adjusted_momentum = momentum * (1 - min(volatility, 1.0))
        daily_return = adjusted_momentum / 252
        predicted_price = current_price * ((1 + daily_return) ** days_ahead)
        confidence = max(0.2, 0.7 - volatility)
        
        return predicted_price, confidence


class PatternMatcher:
    """Matches current price pattern to historical patterns"""
    
    def __init__(self, pattern_length: int = 30):
        self.pattern_length = pattern_length
    
    def predict(self, prices: List[float], days_ahead: int) -> Tuple[float, float]:
        """Predict by matching patterns"""
        if len(prices) < self.pattern_length * 2:
            return prices[-1] if prices else 0.0, 0.1
        
        recent_pattern = prices[-self.pattern_length:]
        recent_normalized = self._normalize(recent_pattern)
        historical = prices[:-self.pattern_length]
        best_match = None
        best_similarity = 0
        
        for i in range(len(historical) - self.pattern_length):
            pattern = historical[i:i+self.pattern_length]
            pattern_normalized = self._normalize(pattern)
            similarity = np.corrcoef(recent_normalized, pattern_normalized)[0, 1] if len(recent_normalized) > 1 else 0
            
            if similarity > best_similarity:
                best_similarity = similarity
                if i + self.pattern_length + days_ahead < len(historical):
                    future_idx = i + self.pattern_length + days_ahead
                    best_match = historical[future_idx]
        
        if best_match and best_similarity > 0.5:
            pattern_end_price = historical[i + self.pattern_length - 1] if i + self.pattern_length - 1 < len(historical) else prices[-1]
            scale_factor = prices[-1] / pattern_end_price if pattern_end_price > 0 else 1.0
            predicted_price = best_match * scale_factor
            confidence = min(0.7, best_similarity)
        else:
            predicted_price = prices[-1]
            confidence = 0.2
        
        return predicted_price, confidence
    
    def _normalize(self, prices: List[float]) -> np.ndarray:
        """Normalize prices to 0-1 range"""
        prices_array = np.array(prices)
        min_price = prices_array.min()
        max_price = prices_array.max()
        if max_price == min_price:
            return np.ones_like(prices_array) * 0.5
        return (prices_array - min_price) / (max_price - min_price)


class RegressionPredictor:
    """Uses linear regression for price prediction"""
    
    def __init__(self, lookback: int = 60):
        self.lookback = lookback
    
    def predict(self, prices: List[float], days_ahead: int) -> Tuple[float, float]:
        """Predict using linear regression"""
        if len(prices) < self.lookback:
            return prices[-1] if prices else 0.0, 0.1
        
        recent_prices = prices[-self.lookback:]
        x = np.arange(len(recent_prices))
        y = np.array(recent_prices)
        
        coeffs = np.polyfit(x, y, deg=1)
        slope = coeffs[0]
        intercept = coeffs[1]
        
        future_x = len(recent_prices) + days_ahead - 1
        predicted_price = slope * future_x + intercept
        
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        confidence = max(0.2, min(0.7, r_squared))
        
        return max(0, predicted_price), confidence


class ElitePricePredictor:
    """Elite ensemble price predictor with learning"""
    
    def __init__(self, symbol: str, storage_path: str = None):
        self.symbol = symbol
        
        if storage_path is None:
            storage_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'predictions')
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.trend_model = TrendExtrapolator()
        self.volatility_model = VolatilityMomentumPredictor()
        self.pattern_model = PatternMatcher()
        self.regression_model = RegressionPredictor()
        
        self.model_weights = {
            'trend': 0.25,
            'volatility': 0.25,
            'pattern': 0.25,
            'regression': 0.25
        }
        
        self.predictions: Dict[str, PricePrediction] = {}
        self.accuracy_history: List[PredictionAccuracy] = []
        
        self._load_accuracy_history()
        self._update_weights_from_accuracy()
    
    def predict(self, current_price: float, prices_history: List[float], 
                target_date: datetime, prediction_time: datetime = None) -> PricePrediction:
        """Make a price prediction for a target date"""
        if prediction_time is None:
            prediction_time = datetime.now(timezone.utc)
        elif prediction_time.tzinfo is None:
            # Make timezone-aware if naive
            prediction_time = prediction_time.replace(tzinfo=timezone.utc)
        
        if target_date.tzinfo is None:
            target_date = target_date.replace(tzinfo=timezone.utc)
        
        days_ahead = (target_date - prediction_time).days
        
        if days_ahead <= 0:
            return PricePrediction(
                symbol=self.symbol,
                current_price=current_price,
                predicted_price=current_price,
                prediction_date=prediction_time.isoformat(),
                target_date=target_date.isoformat(),
                confidence=1.0,
                model_used='current',
                time_horizon_days=0,
                created_at=prediction_time.isoformat()
            )
        
        trend_price, trend_conf = self.trend_model.predict(prices_history, days_ahead)
        vol_price, vol_conf = self.volatility_model.predict(prices_history, days_ahead)
        pattern_price, pattern_conf = self.pattern_model.predict(prices_history, days_ahead)
        reg_price, reg_conf = self.regression_model.predict(prices_history, days_ahead)
        
        weights = self.model_weights
        weighted_price = (
            trend_price * weights['trend'] * trend_conf +
            vol_price * weights['volatility'] * vol_conf +
            pattern_price * weights['pattern'] * pattern_conf +
            reg_price * weights['regression'] * reg_conf
        ) / (
            weights['trend'] * trend_conf +
            weights['volatility'] * vol_conf +
            weights['pattern'] * pattern_conf +
            weights['regression'] * reg_conf + 1e-10
        )
        
        overall_confidence = (
            trend_conf * weights['trend'] +
            vol_conf * weights['volatility'] +
            pattern_conf * weights['pattern'] +
            reg_conf * weights['regression']
        )
        
        model_scores = {
            'trend': weights['trend'] * trend_conf,
            'volatility': weights['volatility'] * vol_conf,
            'pattern': weights['pattern'] * pattern_conf,
            'regression': weights['regression'] * reg_conf
        }
        dominant_model = max(model_scores, key=model_scores.get)
        
        prediction = PricePrediction(
            symbol=self.symbol,
            current_price=current_price,
            predicted_price=weighted_price,
            prediction_date=prediction_time.isoformat(),
            target_date=target_date.isoformat(),
            confidence=overall_confidence,
            model_used=f'ensemble({dominant_model})',
            time_horizon_days=days_ahead,
            created_at=prediction_time.isoformat()
        )
        
        prediction_id = f"{self.symbol}_{target_date.strftime('%Y%m%d')}_{prediction_time.strftime('%Y%m%d')}"
        self.predictions[prediction_id] = prediction
        self._save_prediction(prediction)
        
        return prediction
    
    def evaluate_prediction(self, prediction_id: str, actual_price: float):
        """Evaluate a prediction against actual price"""
        if prediction_id not in self.predictions:
            return
        
        prediction = self.predictions[prediction_id]
        error_absolute = abs(actual_price - prediction.predicted_price)
        error_percent = (error_absolute / prediction.predicted_price) * 100 if prediction.predicted_price > 0 else 100
        
        accuracy = PredictionAccuracy(
            prediction_id=prediction_id,
            predicted_price=prediction.predicted_price,
            actual_price=actual_price,
            error_percent=error_percent,
            error_absolute=error_absolute,
            target_date=prediction.target_date,
            model_used=prediction.model_used,
            evaluated_at=datetime.now(timezone.utc).isoformat()
        )
        
        self.accuracy_history.append(accuracy)
        self._save_accuracy(accuracy)
        self._update_weights_from_accuracy()
    
    def _update_weights_from_accuracy(self):
        """Update model weights based on historical accuracy"""
        if len(self.accuracy_history) < 10:
            return
        
        model_errors = {
            'trend': [],
            'volatility': [],
            'pattern': [],
            'regression': []
        }
        
        for acc in self.accuracy_history[-50:]:
            model = acc.model_used
            if 'trend' in model.lower():
                model_errors['trend'].append(acc.error_percent)
            elif 'volatility' in model.lower():
                model_errors['volatility'].append(acc.error_percent)
            elif 'pattern' in model.lower():
                model_errors['pattern'].append(acc.error_percent)
            elif 'regression' in model.lower():
                model_errors['regression'].append(acc.error_percent)
        
        model_scores = {}
        for model, errors in model_errors.items():
            if errors:
                avg_error = np.mean(errors)
                model_scores[model] = 1.0 / (1.0 + avg_error / 10.0)
            else:
                model_scores[model] = 0.25
        
        total_score = sum(model_scores.values())
        if total_score > 0:
            self.model_weights = {k: v / total_score for k, v in model_scores.items()}
    
    def get_accuracy_stats(self) -> Dict:
        """Get prediction accuracy statistics"""
        if not self.accuracy_history:
            return {
                'total_predictions': 0,
                'avg_error_percent': 0,
                'model_performance': {}
            }
        
        errors = [acc.error_percent for acc in self.accuracy_history]
        
        model_perf = {}
        for model in ['trend', 'volatility', 'pattern', 'regression']:
            model_errors = [acc.error_percent for acc in self.accuracy_history 
                          if model in acc.model_used.lower()]
            if model_errors:
                model_perf[model] = {
                    'avg_error': np.mean(model_errors),
                    'count': len(model_errors)
                }
        
        return {
            'total_predictions': len(self.accuracy_history),
            'avg_error_percent': np.mean(errors),
            'median_error_percent': np.median(errors),
            'best_error': np.min(errors),
            'worst_error': np.max(errors),
            'model_performance': model_perf,
            'current_weights': self.model_weights
        }
    
    def _save_prediction(self, prediction: PricePrediction):
        """Save prediction to disk"""
        file_path = self.storage_path / f"predictions_{self.symbol}.jsonl"
        with open(file_path, 'a') as f:
            f.write(json.dumps(asdict(prediction)) + '\n')
    
    def _save_accuracy(self, accuracy: PredictionAccuracy):
        """Save accuracy record to disk"""
        file_path = self.storage_path / f"accuracy_{self.symbol}.jsonl"
        with open(file_path, 'a') as f:
            f.write(json.dumps(asdict(accuracy)) + '\n')
    
    def _load_accuracy_history(self):
        """Load historical accuracy data"""
        file_path = self.storage_path / f"accuracy_{self.symbol}.jsonl"
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            self.accuracy_history.append(PredictionAccuracy(**data))
            except Exception as e:
                logger.error(f"Error loading accuracy history: {e}")


def create_price_predictor(symbol: str, storage_path: str = None) -> ElitePricePredictor:
    """Create a price predictor instance"""
    return ElitePricePredictor(symbol, storage_path)
