"""
Strategy Manager
Coordinates multiple strategies and selects best signals
"""

from typing import Dict, List, Optional
import logging
from .breakout_strategy import BreakoutStrategy
from .breakout_strategy_v2 import BreakoutStrategyV2
from .breakout_strategy_v3 import BreakoutStrategyV3
from .pullback_strategy import PullbackStrategy
from .mean_reversion import MeanReversionStrategy
from .funding_arbitrage import FundingArbitrageStrategy
from .momentum_strategy import MomentumStrategy
from .structure_strategy import StructureStrategy
import config

logger = logging.getLogger(__name__)


class StrategyManager:
    """
    Manages all trading strategies
    Runs each strategy and selects best signal
    """

    def __init__(self):
        self.strategies = {
            'breakout_v2': BreakoutStrategyV2(),
            'breakout_v3': BreakoutStrategyV3(),
            'pullback': PullbackStrategy()
        }
        
        # Add Mean Reversion strategy if enabled (Phase 4.1)
        if getattr(config, 'MEAN_REVERSION_ENABLED', False):
            self.strategies['mean_reversion'] = MeanReversionStrategy()
            logger.info("   Mean Reversion strategy: ENABLED (ranging markets only)")
        
        # Add Funding Arbitrage strategy if enabled (Phase 4.2)
        if getattr(config, 'FUNDING_ARBITRAGE_ENABLED', False):
            self.strategies['funding_arbitrage'] = FundingArbitrageStrategy()
            logger.info("   Funding Arbitrage strategy: ENABLED (extreme funding only)")
        
        # Add Momentum strategy if enabled (Elite - catches trending moves)
        if getattr(config, 'MOMENTUM_STRATEGY_ENABLED', True):
            self.strategies['momentum'] = MomentumStrategy()
            logger.info("   Momentum strategy: ENABLED (trend-following)")
        
        # Add Structure strategy if enabled (Elite - S/R + Market Structure + Volume)
        if getattr(config, 'STRUCTURE_STRATEGY_ENABLED', True):
            self.strategies['structure'] = StructureStrategy()
            logger.info("   Structure strategy: ENABLED (S/R + structure analysis)")

        self.signals_history = []
        logger.info(f"✅ StrategyManager initialized with {len(self.strategies)} strategies")

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
        1. Breakout V3 signals (highest quality momentum)
        2. Breakout V2 signals (momentum)
        3. Mean Reversion signals in RANGING markets (fade extremes)
        4. Pullback signals (trend continuation)
        5. Funding Arbitrage signals (lowest priority - only if nothing else)

        Returns:
            Best signal
        """
        if not signals:
            return None

        if len(signals) == 1:
            return signals[0]

        # Categorize signals
        mr_signal = None
        arb_signal = None
        breakout_signals = []
        other_signals = []
        
        for signal in signals:
            strategy_name = signal.get('strategy', '').lower()
            strategy_type = signal.get('strategy_type', '').lower()
            
            if 'meanreversion' in strategy_name or 'mean_reversion' in strategy_name:
                mr_signal = signal
            elif 'fundingarbitrage' in strategy_name or 'funding_arbitrage' in strategy_name or strategy_type == 'arbitrage':
                arb_signal = signal  # Save for last (lowest priority)
            elif 'breakout' in strategy_name:
                breakout_signals.append(signal)
            else:
                other_signals.append(signal)
        
        # Priority 1: Breakout V3 (highest quality)
        for signal in breakout_signals:
            strategy_name = signal.get('strategy', '').lower()
            if 'v3' in strategy_name or 'breakoutv3' in strategy_name:
                logger.info("🎯 Selected BREAKOUT V3 signal (highest priority)")
                return signal
        
        # Priority 2: Breakout V2
        for signal in breakout_signals:
            strategy_name = signal.get('strategy', '').lower()
            if 'v2' in strategy_name or 'breakoutv2' in strategy_name:
                logger.info("🎯 Selected BREAKOUT V2 signal")
                return signal
        
        # Priority 3: Mean Reversion in ranging markets
        if mr_signal and mr_signal.get('regime') == 'ranging':
            logger.info("🎯 Selected MEAN REVERSION signal (ranging market)")
            return mr_signal
        
        # Priority 4: Any other breakout
        if breakout_signals:
            logger.info("🎯 Selected BREAKOUT signal")
            return breakout_signals[0]
        
        # Priority 5: Pullback and other signals
        if other_signals:
            logger.info(f"🎯 Selected {other_signals[0]['strategy'].upper()} signal")
            return other_signals[0]
        
        # Priority 6: Mean Reversion (even if not confirmed ranging)
        if mr_signal:
            logger.info("🎯 Selected MEAN REVERSION signal")
            return mr_signal
        
        # Priority 7 (LOWEST): Funding Arbitrage
        # Only take arb if NOTHING else is available
        # Arb is low-risk but also low-reward
        if arb_signal:
            logger.info("💰 Selected FUNDING ARBITRAGE signal (no other opportunities)")
            return arb_signal
        
        return None

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
