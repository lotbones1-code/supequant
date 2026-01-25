"""
V4 Kelly Position Sizer

Implements the Kelly Criterion for optimal position sizing:
    Kelly % = W - [(1-W) / R]

Where:
    W = Win rate (probability of winning)
    R = Win/Loss ratio (average win / average loss)

Uses Half-Kelly for safety (reduces optimal by 50%).

Historical data from backtests:
- Baseline win rate: 51.28%
- Baseline win/loss ratio: 2.61 ($771.86 / $295.36)
- LONG win rate: 55%
- SHORT win rate: 8%
"""

import logging
from typing import Dict, Tuple, Optional
from collections import deque

logger = logging.getLogger(__name__)


class V4KellyPositionSizer:
    """
    Optimal position sizing using Kelly Criterion.
    Uses Half-Kelly for safety.
    """

    # Historical baselines from backtest analysis
    BASELINE_WIN_RATE = 0.5128       # 51.28% overall
    BASELINE_WIN_LOSS_RATIO = 2.61   # $771.86 / $295.36

    LONG_WIN_RATE = 0.55             # 55% for longs (from analysis)
    SHORT_WIN_RATE = 0.08            # 8% for shorts (from analysis)

    def __init__(self):
        self.name = "V4KellySizer"

        # Safety multiplier (Half-Kelly)
        self.KELLY_FRACTION = 0.5

        # Position limits
        self.MIN_POSITION_MULT = 0.25    # Never below 25% size
        self.MAX_POSITION_MULT = 3.0     # Never above 3x size

        # Rolling statistics (adapt to recent performance)
        self.rolling_win_rate = self.BASELINE_WIN_RATE
        self.rolling_win_loss_ratio = self.BASELINE_WIN_LOSS_RATIO
        self.recent_trades = deque(maxlen=50)  # Last 50 trades

        # Separate tracking for longs vs shorts
        self.long_trades = deque(maxlen=30)
        self.short_trades = deque(maxlen=30)

        # Statistics
        self.calculations = 0
        self.edge_warnings = 0

    def update_from_trade(self, pnl: float, is_win: bool, direction: str = 'long'):
        """
        Update rolling statistics after each trade.

        Args:
            pnl: Profit/loss amount
            is_win: Whether trade was profitable
            direction: 'long' or 'short'
        """
        trade_record = {'pnl': pnl, 'win': is_win, 'direction': direction}
        self.recent_trades.append(trade_record)

        if direction == 'long':
            self.long_trades.append(trade_record)
        else:
            self.short_trades.append(trade_record)

        # Update rolling stats if we have enough data
        if len(self.recent_trades) >= 10:
            self._update_rolling_stats()

    def _update_rolling_stats(self):
        """Recalculate rolling win rate and win/loss ratio."""
        if not self.recent_trades:
            return

        wins = [t for t in self.recent_trades if t['win']]
        losses = [t for t in self.recent_trades if not t['win']]

        # Update win rate
        self.rolling_win_rate = len(wins) / len(self.recent_trades)

        # Update win/loss ratio
        if wins and losses:
            avg_win = sum(abs(t['pnl']) for t in wins) / len(wins)
            avg_loss = sum(abs(t['pnl']) for t in losses) / len(losses)
            if avg_loss > 0:
                self.rolling_win_loss_ratio = avg_win / avg_loss

    def calculate_kelly_multiplier(self, direction: str,
                                   v4_win_probability: Optional[float] = None) -> Tuple[float, Dict]:
        """
        Calculate position size multiplier based on Kelly Criterion.

        Args:
            direction: 'long' or 'short'
            v4_win_probability: Optional P(win) from V4 predictor

        Returns:
            (multiplier: float, details: Dict)
        """
        self.calculations += 1

        # Determine win rate to use
        if v4_win_probability is not None:
            # Use V4 ML prediction if available
            W = v4_win_probability
            source = 'v4_predictor'
        else:
            # Use direction-specific historical rate
            if direction == 'long':
                W = self._get_long_win_rate()
                source = 'long_historical'
            else:
                W = self._get_short_win_rate()
                source = 'short_historical'

        # Use rolling win/loss ratio
        R = self.rolling_win_loss_ratio

        # Kelly formula: W - (1-W)/R
        if R > 0:
            full_kelly = W - (1 - W) / R
        else:
            full_kelly = 0

        # Half-Kelly for safety
        half_kelly = full_kelly * self.KELLY_FRACTION

        # Handle negative edge
        if full_kelly <= 0:
            self.edge_warnings += 1
            logger.warning(f"V4 KELLY: Negative edge detected! W={W:.1%}, R={R:.2f}, "
                          f"Kelly={full_kelly:.1%}")
            multiplier = self.MIN_POSITION_MULT
        else:
            # Clamp to bounds
            multiplier = max(self.MIN_POSITION_MULT,
                           min(self.MAX_POSITION_MULT, half_kelly * 5))  # Scale for leverage

        details = {
            'win_rate': W,
            'win_rate_source': source,
            'win_loss_ratio': R,
            'full_kelly_pct': f"{full_kelly:.1%}",
            'half_kelly_pct': f"{half_kelly:.1%}",
            'final_multiplier': multiplier,
            'direction': direction,
            'clamped': multiplier == self.MIN_POSITION_MULT or multiplier == self.MAX_POSITION_MULT
        }

        logger.debug(f"V4 KELLY: {direction} W={W:.1%} R={R:.2f} -> mult={multiplier:.2f}x")

        return multiplier, details

    def _get_long_win_rate(self) -> float:
        """Get win rate for long trades."""
        if len(self.long_trades) >= 10:
            wins = sum(1 for t in self.long_trades if t['win'])
            return wins / len(self.long_trades)
        return self.LONG_WIN_RATE

    def _get_short_win_rate(self) -> float:
        """Get win rate for short trades."""
        if len(self.short_trades) >= 10:
            wins = sum(1 for t in self.short_trades if t['win'])
            return wins / len(self.short_trades)
        return self.SHORT_WIN_RATE

    def get_optimal_kelly(self, win_rate: float, win_loss_ratio: float) -> float:
        """
        Calculate pure Kelly percentage (before safety adjustment).
        Useful for analysis.

        Args:
            win_rate: Probability of winning (0-1)
            win_loss_ratio: Average win / average loss

        Returns:
            Optimal Kelly fraction (0-1, can be negative for negative edge)
        """
        if win_loss_ratio <= 0:
            return 0
        return win_rate - (1 - win_rate) / win_loss_ratio

    def get_stats(self) -> Dict:
        """Get Kelly sizer statistics."""
        return {
            'calculations': self.calculations,
            'edge_warnings': self.edge_warnings,
            'rolling_win_rate': f"{self.rolling_win_rate:.1%}",
            'rolling_win_loss_ratio': f"{self.rolling_win_loss_ratio:.2f}",
            'recent_trades': len(self.recent_trades),
            'long_trades': len(self.long_trades),
            'short_trades': len(self.short_trades),
            'settings': {
                'kelly_fraction': self.KELLY_FRACTION,
                'min_mult': self.MIN_POSITION_MULT,
                'max_mult': self.MAX_POSITION_MULT,
            }
        }

    def reset_stats(self):
        """Reset statistics for new backtest run."""
        self.calculations = 0
        self.edge_warnings = 0
        self.recent_trades.clear()
        self.long_trades.clear()
        self.short_trades.clear()
        self.rolling_win_rate = self.BASELINE_WIN_RATE
        self.rolling_win_loss_ratio = self.BASELINE_WIN_LOSS_RATIO
