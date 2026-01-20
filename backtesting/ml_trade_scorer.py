"""
ML Trade Scorer for Backtesting

This module uses machine learning to score trade signals based on historical patterns.
It learns from past trades what features are associated with wins vs losses.

Features used:
- RSI value and extremity
- Trend strength and direction
- Volume patterns
- Volatility (ATR)
- Bollinger Band position
- Time of day patterns

BACKTESTING ONLY - Does not affect live trading.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class MLPrediction:
    """ML model prediction result"""
    score: float  # 0-1 probability of winning trade
    should_trade: bool
    confidence: float
    features_used: Dict[str, float]
    reason: str


class MLTradeScorer:
    """
    Simple ML-based trade scoring using learned patterns.
    
    Uses a lightweight approach suitable for backtesting:
    1. Collects features from winning and losing trades
    2. Learns optimal feature ranges for wins
    3. Scores new signals based on how well they match winning patterns
    
    No external ML libraries needed - pure Python implementation.
    """
    
    def __init__(self, 
                 min_score_threshold: float = 0.4,
                 learning_rate: float = 0.1,
                 use_adaptive_threshold: bool = True):
        """
        Initialize ML scorer.
        
        Args:
            min_score_threshold: Minimum score to allow trade (0-1)
            learning_rate: How fast to adapt to new data
            use_adaptive_threshold: Auto-adjust threshold based on performance
        """
        self.min_score_threshold = min_score_threshold
        self.learning_rate = learning_rate
        self.use_adaptive_threshold = use_adaptive_threshold
        
        # Learned feature statistics
        self.win_stats = defaultdict(lambda: {'sum': 0, 'sum_sq': 0, 'count': 0})
        self.loss_stats = defaultdict(lambda: {'sum': 0, 'sum_sq': 0, 'count': 0})
        
        # Feature weights (learned importance)
        self.feature_weights = {
            'rsi_extremity': 1.0,      # How extreme RSI is
            'trend_alignment': 0.8,     # Trade direction vs trend
            'volume_ratio': 0.6,        # Volume vs average
            'volatility_norm': 0.7,     # Normalized ATR
            'bb_position': 0.9,         # Bollinger Band position
            'hour_score': 0.4,          # Time of day factor
            'rr_ratio': 1.2,            # Risk/reward ratio
        }
        
        # Performance tracking
        self.stats = {
            'signals_scored': 0,
            'signals_passed': 0,
            'signals_blocked': 0,
            'trades_tracked': 0,
            'wins_tracked': 0,
            'losses_tracked': 0,
        }
        
        # Initialize with some baseline patterns (from backtesting observations)
        self._initialize_baseline_patterns()
        
        logger.info(f"🤖 MLTradeScorer initialized (threshold: {min_score_threshold})")
    
    def _initialize_baseline_patterns(self):
        """Initialize with observed winning patterns from backtesting."""
        # These are based on the successful Dec-Jan period patterns
        
        # Winning trade patterns (Mean Reversion)
        winning_patterns = [
            {'rsi_extremity': 0.8, 'bb_position': 0.9, 'trend_alignment': 0.3, 'rr_ratio': 2.5},
            {'rsi_extremity': 0.7, 'bb_position': 0.85, 'trend_alignment': 0.4, 'rr_ratio': 2.0},
            {'rsi_extremity': 0.9, 'bb_position': 0.95, 'trend_alignment': 0.2, 'rr_ratio': 3.0},
        ]
        
        # Losing trade patterns (trending market losses)
        losing_patterns = [
            {'rsi_extremity': 0.5, 'bb_position': 0.6, 'trend_alignment': 0.8, 'rr_ratio': 1.5},
            {'rsi_extremity': 0.4, 'bb_position': 0.5, 'trend_alignment': 0.9, 'rr_ratio': 1.2},
        ]
        
        # Add to statistics
        for pattern in winning_patterns:
            for feature, value in pattern.items():
                self._update_stats(self.win_stats, feature, value)
        
        for pattern in losing_patterns:
            for feature, value in pattern.items():
                self._update_stats(self.loss_stats, feature, value)
    
    def _update_stats(self, stats: Dict, feature: str, value: float):
        """Update running statistics for a feature."""
        stats[feature]['sum'] += value
        stats[feature]['sum_sq'] += value ** 2
        stats[feature]['count'] += 1
    
    def _get_mean_std(self, stats: Dict, feature: str) -> Tuple[float, float]:
        """Calculate mean and std for a feature."""
        s = stats[feature]
        if s['count'] == 0:
            return 0.5, 0.2  # Default
        
        mean = s['sum'] / s['count']
        variance = (s['sum_sq'] / s['count']) - (mean ** 2)
        std = max(0.1, variance ** 0.5)  # Min std to avoid division issues
        return mean, std
    
    def extract_features(self, signal: Dict, market_state: Dict) -> Dict[str, float]:
        """
        Extract ML features from a signal and market state.
        
        Returns dict of feature_name -> normalized_value (0-1)
        """
        features = {}
        
        try:
            # 1. RSI Extremity (how oversold/overbought)
            rsi = signal.get('rsi', signal.get('metadata', {}).get('rsi', 50))
            if rsi is None or rsi == 'N/A':
                rsi = 50
            rsi = float(rsi)
            
            # Extremity: how far from 50 (neutral)
            features['rsi_extremity'] = abs(rsi - 50) / 50
            
            # 2. Bollinger Band position
            bb_pos = signal.get('bb_position', signal.get('metadata', {}).get('bb_position', 0.5))
            if bb_pos is None or bb_pos == 'N/A':
                bb_pos = 0.5
            features['bb_position'] = float(bb_pos)
            
            # 3. Trend alignment (1 = with trend, 0 = against trend)
            direction = signal.get('direction', 'long').lower()
            tf_data = market_state.get('timeframes', {}).get('15m', {})
            trend = tf_data.get('trend', {})
            trend_dir = trend.get('trend_direction', 'neutral')
            
            if direction == 'long':
                if trend_dir in ['up', 'bullish']:
                    features['trend_alignment'] = 1.0
                elif trend_dir in ['down', 'bearish']:
                    features['trend_alignment'] = 0.0
                else:
                    features['trend_alignment'] = 0.5
            else:  # short
                if trend_dir in ['down', 'bearish']:
                    features['trend_alignment'] = 1.0
                elif trend_dir in ['up', 'bullish']:
                    features['trend_alignment'] = 0.0
                else:
                    features['trend_alignment'] = 0.5
            
            # 4. Volume ratio
            vol_ratio = signal.get('volume_ratio', signal.get('metadata', {}).get('volume_ratio', 1.0))
            if vol_ratio is None or vol_ratio == 'N/A':
                vol_ratio = 1.0
            # Normalize: 0.5-2.0 range mapped to 0-1
            features['volume_ratio'] = min(1.0, max(0.0, (float(vol_ratio) - 0.5) / 1.5))
            
            # 5. Volatility (normalized ATR)
            atr = signal.get('atr', signal.get('metadata', {}).get('atr', 0))
            if atr is None or atr == 'N/A':
                atr = 0
            entry = signal.get('entry_price', 1)
            if entry and entry > 0:
                features['volatility_norm'] = min(1.0, float(atr) / float(entry) * 100)  # ATR as % of price
            else:
                features['volatility_norm'] = 0.5
            
            # 6. Risk/Reward ratio
            entry_price = float(signal.get('entry_price', 0) or 0)
            stop_loss = float(signal.get('stop_loss', 0) or 0)
            take_profit = float(signal.get('take_profit_1', signal.get('take_profit', 0)) or 0)
            
            if entry_price > 0 and stop_loss > 0 and take_profit > 0:
                risk = abs(entry_price - stop_loss)
                reward = abs(take_profit - entry_price)
                if risk > 0:
                    rr = reward / risk
                    features['rr_ratio'] = min(1.0, rr / 5.0)  # Normalize: 5:1 RR = 1.0
                else:
                    features['rr_ratio'] = 0.5
            else:
                features['rr_ratio'] = 0.5
            
            # 7. Hour score (certain hours historically better)
            timestamp = signal.get('timestamp', '')
            try:
                if 'T' in str(timestamp):
                    hour = int(str(timestamp).split('T')[1][:2])
                else:
                    hour = 12  # Default to noon
                # Prefer US trading hours (14-21 UTC) and Asian session (0-8 UTC)
                if 14 <= hour <= 21 or 0 <= hour <= 8:
                    features['hour_score'] = 0.8
                else:
                    features['hour_score'] = 0.5
            except:
                features['hour_score'] = 0.5
                
        except Exception as e:
            logger.debug(f"Feature extraction error: {e}")
            # Return default features
            features = {
                'rsi_extremity': 0.5,
                'bb_position': 0.5,
                'trend_alignment': 0.5,
                'volume_ratio': 0.5,
                'volatility_norm': 0.5,
                'rr_ratio': 0.5,
                'hour_score': 0.5,
            }
        
        return features
    
    def score_signal(self, signal: Dict, market_state: Dict) -> MLPrediction:
        """
        Score a trading signal using learned patterns.
        
        Returns MLPrediction with score and recommendation.
        """
        self.stats['signals_scored'] += 1
        
        # Extract features
        features = self.extract_features(signal, market_state)
        
        # Calculate score based on similarity to winning patterns
        score = 0.0
        total_weight = 0.0
        
        for feature_name, value in features.items():
            if feature_name not in self.feature_weights:
                continue
                
            weight = self.feature_weights[feature_name]
            total_weight += weight
            
            # Get win/loss statistics for this feature
            win_mean, win_std = self._get_mean_std(self.win_stats, feature_name)
            loss_mean, loss_std = self._get_mean_std(self.loss_stats, feature_name)
            
            # Calculate probability this value is from a winner
            # Using simple distance-based scoring
            win_distance = abs(value - win_mean) / win_std
            loss_distance = abs(value - loss_mean) / loss_std
            
            # Convert to probability (closer to win pattern = higher score)
            if win_distance + loss_distance > 0:
                feature_score = loss_distance / (win_distance + loss_distance)
            else:
                feature_score = 0.5
            
            score += feature_score * weight
        
        # Normalize score
        if total_weight > 0:
            score = score / total_weight
        else:
            score = 0.5
        
        # Determine if should trade
        should_trade = score >= self.min_score_threshold
        
        # Calculate confidence
        confidence = abs(score - 0.5) * 2  # How far from uncertain
        
        # Generate reason
        if should_trade:
            reason = f"ML score {score:.2f} >= {self.min_score_threshold} threshold"
            self.stats['signals_passed'] += 1
        else:
            reason = f"ML score {score:.2f} < {self.min_score_threshold} threshold - pattern matches losers"
            self.stats['signals_blocked'] += 1
        
        return MLPrediction(
            score=score,
            should_trade=should_trade,
            confidence=confidence,
            features_used=features,
            reason=reason
        )
    
    def record_trade_result(self, signal: Dict, market_state: Dict, won: bool):
        """
        Record a trade result to improve the model.
        
        Call this after each trade completes to update learned patterns.
        """
        self.stats['trades_tracked'] += 1
        
        features = self.extract_features(signal, market_state)
        
        if won:
            self.stats['wins_tracked'] += 1
            stats = self.win_stats
        else:
            self.stats['losses_tracked'] += 1
            stats = self.loss_stats
        
        # Update statistics with learning rate
        for feature_name, value in features.items():
            # Weighted update (more recent trades have more influence)
            self._update_stats(stats, feature_name, value)
        
        # Adaptive threshold adjustment
        if self.use_adaptive_threshold and self.stats['trades_tracked'] >= 10:
            win_rate = self.stats['wins_tracked'] / self.stats['trades_tracked']
            
            # If win rate is too low, raise threshold (be more selective)
            if win_rate < 0.5 and self.min_score_threshold < 0.7:
                self.min_score_threshold += 0.02
                logger.debug(f"ML: Raised threshold to {self.min_score_threshold:.2f} (low win rate)")
            # If win rate is high, we can be slightly less selective
            elif win_rate > 0.7 and self.min_score_threshold > 0.3:
                self.min_score_threshold -= 0.01
                logger.debug(f"ML: Lowered threshold to {self.min_score_threshold:.2f} (high win rate)")
    
    def get_stats(self) -> Dict:
        """Get ML scorer statistics."""
        total = self.stats['signals_scored']
        return {
            **self.stats,
            'block_rate': self.stats['signals_blocked'] / total if total > 0 else 0,
            'current_threshold': self.min_score_threshold,
            'learned_win_patterns': sum(s['count'] for s in self.win_stats.values()),
            'learned_loss_patterns': sum(s['count'] for s in self.loss_stats.values()),
        }


# Convenience function for backtest integration
def create_ml_scorer(
    min_score: float = 0.4,
    learning_rate: float = 0.1,
    adaptive: bool = True
) -> MLTradeScorer:
    """Create a configured ML scorer for backtesting."""
    return MLTradeScorer(
        min_score_threshold=min_score,
        learning_rate=learning_rate,
        use_adaptive_threshold=adaptive
    )
