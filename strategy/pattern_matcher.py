"""
Pattern Matcher
Compares new signals to past winners/losers to score similarity
Higher similarity to winners = higher confidence score
"""

import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class PatternMatcher:
    """
    Matches new trading signals against historical winning/losing patterns
    Returns confidence score based on similarity to winners
    """
    
    def __init__(self, winning_patterns_file: str = "claude_winning_patterns.json",
                 losing_patterns_file: str = "claude_rejection_rules.json"):
        self.winning_patterns_file = winning_patterns_file
        self.losing_patterns_file = losing_patterns_file
        self.winning_patterns = self._load_patterns(winning_patterns_file)
        self.losing_patterns = self._load_patterns(losing_patterns_file)
    
    def _load_patterns(self, filepath: str) -> List[Dict]:
        """Load patterns from JSON file"""
        if not Path(filepath).exists():
            return []
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            logger.warning(f"Failed to load patterns from {filepath}: {e}")
            return []
    
    def score_signal(self, signal: Dict, market_context: Dict) -> float:
        """
        Score a signal based on similarity to winning patterns
        
        Args:
            signal: Trading signal dict with entry_price, direction, strategy, etc.
            market_context: Market state dict with volatility, volume_ratio, trend, etc.
            
        Returns:
            Confidence score 0-100 (higher = more similar to winners)
        """
        if not self.winning_patterns:
            # No patterns learned yet, return neutral score
            return 50.0
        
        # Extract features from signal and market context
        signal_features = self._extract_features(signal, market_context)
        
        # Calculate similarity to each winning pattern
        similarities = []
        for pattern in self.winning_patterns:
            pattern_features = self._extract_features_from_pattern(pattern)
            similarity = self._calculate_similarity(signal_features, pattern_features)
            # Weight by success (more successful patterns count more)
            weight = min(pattern.get('success_count', 1), 5)  # Cap weight at 5
            similarities.append(similarity * weight)
        
        if not similarities:
            return 50.0
        
        # Average similarity, weighted
        avg_similarity = sum(similarities) / sum(min(p.get('success_count', 1), 5) for p in self.winning_patterns)
        
        # Convert to 0-100 score
        # Similarity ranges from 0-1, map to 0-100
        # Boost score if very similar (multiply by 1.2, cap at 100)
        score = min(avg_similarity * 100 * 1.2, 100.0)
        
        # Penalize if similar to losing patterns
        if self.losing_patterns:
            losing_similarities = []
            for pattern in self.losing_patterns:
                pattern_features = self._extract_features_from_pattern(pattern)
                similarity = self._calculate_similarity(signal_features, pattern_features)
                losing_similarities.append(similarity)
            
            if losing_similarities:
                avg_losing_similarity = sum(losing_similarities) / len(losing_similarities)
                # Reduce score if similar to losers
                score = score * (1 - avg_losing_similarity * 0.5)  # Reduce by up to 50%
        
        return max(0.0, min(100.0, score))
    
    def _extract_features(self, signal: Dict, market_context: Dict) -> Dict:
        """Extract features from signal and market context"""
        return {
            'direction': signal.get('direction', '').lower(),
            'strategy': signal.get('strategy', '').lower(),
            'volatility': market_context.get('volatility', 0),
            'volume_ratio': market_context.get('volume_ratio', 1),
            'trend': market_context.get('trend', '').lower(),
            'entry_price': signal.get('entry_price', 0),
            'stop_loss': signal.get('stop_loss', 0),
            'risk_reward': self._calculate_risk_reward(signal)
        }
    
    def _extract_features_from_pattern(self, pattern: Dict) -> Dict:
        """Extract features from a saved pattern"""
        return {
            'direction': pattern.get('direction', '').lower(),
            'strategy': pattern.get('strategy', '').lower(),
            'volatility': pattern.get('volatility', 0),
            'volume_ratio': pattern.get('volume_ratio', 1),
            'trend': pattern.get('trend', '').lower(),
            'entry_price': pattern.get('entry_price', 0),
            'stop_loss': pattern.get('stop_loss', 0),
            'risk_reward': self._calculate_risk_reward_from_pattern(pattern)
        }
    
    def _calculate_risk_reward(self, signal: Dict) -> float:
        """Calculate risk/reward ratio from signal"""
        entry = signal.get('entry_price', 0)
        stop = signal.get('stop_loss', 0)
        tp1 = signal.get('take_profit_1', 0)
        
        if entry == 0 or stop == 0:
            return 0.0
        
        risk = abs(entry - stop)
        reward = abs(tp1 - entry) if tp1 > 0 else risk * 1.5  # Default 1.5:1
        
        return reward / risk if risk > 0 else 0.0
    
    def _calculate_risk_reward_from_pattern(self, pattern: Dict) -> float:
        """Calculate risk/reward from pattern"""
        entry = pattern.get('entry_price', 0)
        stop = pattern.get('stop_loss', 0)
        
        if entry == 0 or stop == 0:
            return 0.0
        
        risk = abs(entry - stop)
        # Estimate reward from PnL if available
        pnl_pct = pattern.get('pnl_pct', 0)
        if pnl_pct > 0:
            reward = entry * (pnl_pct / 100)
            return reward / risk if risk > 0 else 0.0
        
        return 1.5  # Default estimate
    
    def _calculate_similarity(self, features1: Dict, features2: Dict) -> float:
        """
        Calculate similarity between two feature sets (0-1)
        Uses weighted cosine similarity for numerical features, exact match for categorical
        """
        # Categorical features (must match exactly)
        categorical_weight = 0.3
        categorical_score = 0.0
        categorical_features = ['direction', 'strategy', 'trend']
        
        for feat in categorical_features:
            if features1.get(feat) == features2.get(feat):
                categorical_score += 1.0
        
        categorical_score = categorical_score / len(categorical_features) if categorical_features else 0.0
        
        # Numerical features (normalized distance)
        numerical_weight = 0.7
        numerical_features = ['volatility', 'volume_ratio', 'risk_reward']
        
        numerical_scores = []
        for feat in numerical_features:
            val1 = features1.get(feat, 0)
            val2 = features2.get(feat, 0)
            
            if val1 == 0 and val2 == 0:
                numerical_scores.append(1.0)  # Both zero = match
            elif val1 == 0 or val2 == 0:
                numerical_scores.append(0.0)  # One zero, one not = no match
            else:
                # Normalized distance (closer = higher score)
                max_val = max(abs(val1), abs(val2))
                distance = abs(val1 - val2) / max_val if max_val > 0 else 0
                similarity = 1.0 - min(distance, 1.0)  # Convert distance to similarity
                numerical_scores.append(similarity)
        
        numerical_score = sum(numerical_scores) / len(numerical_scores) if numerical_scores else 0.0
        
        # Weighted combination
        total_similarity = (categorical_score * categorical_weight) + (numerical_score * numerical_weight)
        
        return total_similarity
    
    def get_statistics(self) -> Dict:
        """Get pattern matching statistics"""
        return {
            'winning_patterns': len(self.winning_patterns),
            'losing_patterns': len(self.losing_patterns),
            'total_patterns': len(self.winning_patterns) + len(self.losing_patterns)
        }
