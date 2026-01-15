"""
Strategy Manager
Coordinates multiple strategies and selects best signals
"""

from typing import Dict, List, Optional
import logging
from .breakout_strategy import BreakoutStrategy
from .pullback_strategy import PullbackStrategy

logger = logging.getLogger(__name__)


class StrategyManager:
    """
    Manages all trading strategies
    Runs each strategy and selects best signal
    """

    def __init__(self):
        self.strategies = {
            'breakout': BreakoutStrategy(),
            'pullback': PullbackStrategy()
        }

        self.signals_history = []
        logger.info("✅ StrategyManager initialized with 2 strategies")

    def analyze_market(self, market_state: Dict) -> Optional[Dict]:
        """
        Run all strategies and return best signal

        Args:
            market_state: Complete market state

        Returns:
            Best signal or None
        """
        signals = []

        # Run each strategy
        for strategy_name, strategy in self.strategies.items():
            try:
                signal = strategy.analyze(market_state)
                if signal:
                    # Ensure signal has 'strategy' key (fallback if strategy doesn't add it)
                    if 'strategy' not in signal:
                        signal['strategy'] = strategy_name
                    logger.info(f"📊 {strategy_name.upper()}: Signal detected")
                    signals.append(signal)
            except Exception as e:
                logger.error(f"❌ {strategy_name.upper()}: Error during analysis: {e}")

        if not signals:
            return None

        # If multiple signals, select best one
        # For now, prefer breakout over pullback
        # In future, could use AI scoring here
        best_signal = self._select_best_signal(signals)

        if best_signal:
            self.signals_history.append(best_signal)

        return best_signal

    def _select_best_signal(self, signals: List[Dict]) -> Optional[Dict]:
        """
        Select best signal from multiple candidates

        Priority:
        1. Breakout signals (more reliable)
        2. Pullback signals at strong levels

        Returns:
            Best signal
        """
        if not signals:
            return None

        if len(signals) == 1:
            return signals[0]

        # Prefer breakout (check for 'breakout' or 'BreakoutV2')
        for signal in signals:
            strategy_name = signal.get('strategy', '').lower()
            if 'breakout' in strategy_name:
                logger.info("🎯 Selected BREAKOUT signal")
                return signal

        # Otherwise return first signal
        logger.info(f"🎯 Selected {signals[0]['strategy'].upper()} signal")
        return signals[0]

    def get_statistics(self) -> Dict:
        """Get statistics for all strategies"""
        return {
            'strategies': {
                name: strategy.get_statistics()
                for name, strategy in self.strategies.items()
            },
            'total_signals': len(self.signals_history)
        }

    def get_recent_signals(self, limit: int = 10) -> List[Dict]:
        """Get recent signals"""
        return self.signals_history[-limit:] if self.signals_history else []
