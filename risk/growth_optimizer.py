"""
Growth Optimizer
Aggressive growth system for turning small accounts into large ones
- Compound growth: Increase position size as account grows
- Confidence-based sizing: Bigger positions on high-confidence setups
- Leverage optimization: Use leverage safely for faster growth
- Dynamic TP targets: Aggressive targets with trailing stops
"""

from typing import Dict, Optional, Tuple
import logging
from datetime import datetime
import math

logger = logging.getLogger(__name__)


class GrowthOptimizer:
    """
    Optimizes for aggressive growth while maintaining safety
    
    Features:
    - Compound growth: Position sizes scale with account
    - Confidence multipliers: Bigger positions on better setups
    - Leverage management: Safe leverage usage
    - Dynamic targets: Aggressive TP with trailing stops
    """
    
    def __init__(self, 
                 base_risk_pct: float = 0.01,
                 max_risk_pct: float = 0.05,
                 leverage: int = 3,
                 compound_enabled: bool = True,
                 confidence_multiplier_enabled: bool = True):
        """
        Initialize growth optimizer
        
        Args:
            base_risk_pct: Base risk per trade (1% default)
            max_risk_pct: Maximum risk per trade (5% default)
            leverage: Leverage multiplier (3x default, safe)
            compound_enabled: Enable compound growth
            confidence_multiplier_enabled: Enable confidence-based sizing
        """
        self.base_risk_pct = base_risk_pct
        self.max_risk_pct = max_risk_pct
        self.leverage = leverage
        self.compound_enabled = compound_enabled
        self.confidence_multiplier_enabled = confidence_multiplier_enabled
        
        # Growth tracking
        self.starting_balance = None
        self.current_balance = None
        self.growth_multiplier = 1.0
        
        # Performance tracking
        self.win_streak = 0
        self.loss_streak = 0
        self.recent_win_rate = 0.5
        
        logger.info(f"✅ GrowthOptimizer initialized")
        logger.info(f"   Base risk: {base_risk_pct*100}%")
        logger.info(f"   Max risk: {max_risk_pct*100}%")
        logger.info(f"   Leverage: {leverage}x")
        logger.info(f"   Compound: {'ENABLED' if compound_enabled else 'DISABLED'}")
    
    def calculate_optimal_position_size(self, 
                                      signal: Dict,
                                      account_balance: float,
                                      base_position_size: float,
                                      confidence_score: Optional[float] = None) -> Tuple[float, Dict]:
        """
        Calculate optimal position size with growth optimizations
        
        Args:
            signal: Trading signal
            account_balance: Current account balance
            base_position_size: Base position size from risk manager
            confidence_score: Confidence score (0-1) for this setup
            
        Returns:
            (optimized_size, details_dict)
        """
        # Initialize starting balance
        if self.starting_balance is None:
            self.starting_balance = account_balance
            logger.info(f"💰 Starting balance: ${account_balance:.2f}")
        
        self.current_balance = account_balance
        
        # Calculate growth multiplier
        if self.compound_enabled and self.starting_balance > 0:
            # Scale risk as account grows (up to max_risk_pct)
            growth_factor = account_balance / self.starting_balance
            # Logarithmic scaling to prevent too aggressive growth
            growth_multiplier = 1.0 + (math.log10(max(1.0, growth_factor)) * 0.5)
            growth_multiplier = min(growth_multiplier, self.max_risk_pct / self.base_risk_pct)
            self.growth_multiplier = growth_multiplier
        else:
            growth_multiplier = 1.0
        
        # Confidence multiplier
        confidence_multiplier = 1.0
        if self.confidence_multiplier_enabled and confidence_score is not None:
            # Scale from 0.5x to 2.0x based on confidence
            # High confidence (0.8+) = 2.0x
            # Low confidence (0.5-) = 0.5x
            if confidence_score >= 0.8:
                confidence_multiplier = 2.0
            elif confidence_score >= 0.7:
                confidence_multiplier = 1.5
            elif confidence_score >= 0.6:
                confidence_multiplier = 1.2
            elif confidence_score < 0.5:
                confidence_multiplier = 0.5
            else:
                confidence_multiplier = 1.0
        
        # Win streak multiplier (increase size after wins)
        streak_multiplier = 1.0
        if self.win_streak >= 3:
            streak_multiplier = 1.2  # 20% boost after 3 wins
        elif self.win_streak >= 5:
            streak_multiplier = 1.5  # 50% boost after 5 wins
        
        # Loss streak reduction (reduce size after losses)
        if self.loss_streak >= 2:
            streak_multiplier *= 0.7  # Reduce 30% after 2 losses
        elif self.loss_streak >= 3:
            streak_multiplier *= 0.5  # Reduce 50% after 3 losses
        
        # Calculate final position size
        optimized_size = base_position_size * growth_multiplier * confidence_multiplier * streak_multiplier
        
        # Apply leverage
        leveraged_size = optimized_size * self.leverage
        
        # Safety cap: Never risk more than max_risk_pct
        max_size = (account_balance * self.max_risk_pct) / abs(signal.get('entry_price', 1) - signal.get('stop_loss', 0))
        leveraged_size = min(leveraged_size, max_size)
        
        details = {
            'base_size': base_position_size,
            'growth_multiplier': growth_multiplier,
            'confidence_multiplier': confidence_multiplier,
            'streak_multiplier': streak_multiplier,
            'optimized_size': optimized_size,
            'leverage': self.leverage,
            'final_size': leveraged_size,
            'account_balance': account_balance,
            'starting_balance': self.starting_balance,
            'growth_factor': account_balance / self.starting_balance if self.starting_balance > 0 else 1.0,
            'confidence_score': confidence_score
        }
        
        logger.info(f"🚀 Growth-optimized position:")
        logger.info(f"   Base: {base_position_size:.4f}")
        logger.info(f"   Growth multiplier: {growth_multiplier:.2f}x")
        logger.info(f"   Confidence multiplier: {confidence_multiplier:.2f}x")
        logger.info(f"   Streak multiplier: {streak_multiplier:.2f}x")
        logger.info(f"   Final (with {self.leverage}x leverage): {leveraged_size:.4f}")
        
        return leveraged_size, details
    
    def calculate_aggressive_tp_targets(self, 
                                       entry_price: float,
                                       stop_loss: float,
                                       direction: str) -> Dict:
        """
        Calculate aggressive take profit targets
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            direction: 'long' or 'short'
            
        Returns:
            Dict with TP1, TP2, TP3 prices and risk/reward ratios
        """
        risk = abs(entry_price - stop_loss)
        
        if direction == 'long':
            # Aggressive targets: 3R, 5R, 8R
            tp1 = entry_price + (risk * 3.0)  # 3:1 RR
            tp2 = entry_price + (risk * 5.0)  # 5:1 RR
            tp3 = entry_price + (risk * 8.0)  # 8:1 RR
        else:  # short
            tp1 = entry_price - (risk * 3.0)
            tp2 = entry_price - (risk * 5.0)
            tp3 = entry_price - (risk * 8.0)
        
        return {
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'take_profit_3': tp3,
            'rr_ratio_1': 3.0,
            'rr_ratio_2': 5.0,
            'rr_ratio_3': 8.0,
            'position_split': {1: 0.4, 2: 0.35, 3: 0.25}  # 40/35/25 split
        }
    
    def update_performance(self, pnl: float):
        """
        Update performance tracking
        
        Args:
            pnl: Profit/loss from last trade
        """
        if pnl > 0:
            self.win_streak += 1
            self.loss_streak = 0
        else:
            self.loss_streak += 1
            self.win_streak = 0
        
        # Update recent win rate (simple moving average)
        # This would ideally track last N trades
        # For now, just track streaks
    
    def get_growth_stats(self) -> Dict:
        """Get growth statistics"""
        if not self.starting_balance or not self.current_balance:
            return {
                'starting_balance': 0,
                'current_balance': 0,
                'total_growth': 0,
                'total_growth_pct': 0,
                'growth_multiplier': 1.0
            }
        
        total_growth = self.current_balance - self.starting_balance
        total_growth_pct = (total_growth / self.starting_balance) * 100
        
        return {
            'starting_balance': self.starting_balance,
            'current_balance': self.current_balance,
            'total_growth': total_growth,
            'total_growth_pct': total_growth_pct,
            'growth_multiplier': self.growth_multiplier,
            'win_streak': self.win_streak,
            'loss_streak': self.loss_streak,
            'leverage': self.leverage
        }
    
    def reset(self):
        """Reset optimizer (e.g., for new account)"""
        self.starting_balance = None
        self.current_balance = None
        self.growth_multiplier = 1.0
        self.win_streak = 0
        self.loss_streak = 0
        logger.info("🔄 GrowthOptimizer reset")
