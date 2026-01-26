"""
V4 Early Exit Mechanism

Exploits the MAE/MFE patterns discovered in trade analysis:
- Winners MAE: 0.69% (small adverse movement)
- Losers MAE: 2.06% (large adverse movement - 3x worse!)
- Winners MFE: 2.10% (strong positive momentum early)
- Losers MFE: 0.49% (weak momentum - 4x worse!)

Key insight: Losers show their losing pattern EARLY. We can detect
and exit before the full stop loss is hit, saving capital.
"""

import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EarlyExitResult:
    """Result of early exit check."""
    should_exit: bool
    reason: str
    exit_price: float
    savings_estimate: float  # Estimated savings vs full stop


class V4EarlyExitManager:
    """
    Monitors open trades and triggers early exit based on MAE/MFE patterns.

    Exit Triggers:
    1. MAE > 1.2% in first 5 bars (loser pattern)
    2. MFE < 0.3% by bar 8 (no momentum = loser pattern)
    3. MAE > MFE after bar 5 (struggling trade)
    """

    def __init__(self):
        self.name = "V4EarlyExit"

        # CONSERVATIVE THRESHOLDS (only catch clear losers)
        # Winners MAE avg: 0.69%, Losers MAE avg: 2.06%
        # Threshold set at 1.8% (closer to loser average, don't cut winners)
        self.MAE_THRESHOLD_5BAR = 0.018  # 1.8% - matches config.V4_MAE_THRESHOLD_5BAR

        # Winners MFE avg: 2.10%, Losers MFE avg: 0.49%
        # Threshold set at 0.2% (very low - only exit if NO momentum at all)
        self.MFE_THRESHOLD_12BAR = 0.002  # 0.2% - matches config.V4_MFE_THRESHOLD_8BAR
        self.MFE_CHECK_BAR = 12  # Check at bar 12 (config name says 8BAR but actually bar 12)

        # If MAE > MFE by significant margin, trade is struggling
        self.MAE_MFE_RATIO_THRESHOLD = 1.5  # MAE must be 1.5x MFE (was 1.0x)
        self.MIN_MAE_FOR_RATIO_CHECK = 0.012  # 1.2% min MAE (was 0.5%)
        self.MIN_BARS_FOR_RATIO_CHECK = 10  # Wait longer (was bar 5)

        # Statistics
        self.early_exits_triggered = 0
        self.total_savings = 0.0
        self.exit_by_reason = {}

    def check_early_exit(self, trade, current_price: float,
                         bars_held: int) -> Tuple[bool, str, float]:
        """
        Check if trade should exit early based on MAE/MFE patterns.

        Args:
            trade: BacktestTrade object with entry_price, direction, etc.
            current_price: Current market price
            bars_held: Number of bars since entry

        Returns:
            (should_exit: bool, reason: str, exit_price: float)
        """
        # Get entry price (handle different attribute names)
        entry = getattr(trade, 'actual_entry_price', None) or getattr(trade, 'entry_price', 0)
        direction = getattr(trade, 'direction', 'long').lower()

        if entry <= 0:
            return False, "", 0.0

        # Calculate current MAE/MFE
        if direction == 'long':
            current_pnl_pct = (current_price - entry) / entry
            current_mfe = max(0, current_pnl_pct)
            current_mae = max(0, -current_pnl_pct)
        else:  # short
            current_pnl_pct = (entry - current_price) / entry
            current_mfe = max(0, current_pnl_pct)
            current_mae = max(0, -current_pnl_pct)

        # Update trade's running MAE/MFE
        max_mfe = getattr(trade, 'max_favorable_excursion', 0) or 0
        max_mae = getattr(trade, 'max_adverse_excursion', 0) or 0

        trade.max_favorable_excursion = max(max_mfe, current_mfe)
        trade.max_adverse_excursion = max(max_mae, current_mae)

        # CHECK 1: MAE way too high in first 5 bars (clear loser pattern)
        # Only trigger on MAE > 1.5% (losers avg 2.06%, winners avg 0.69%)
        if bars_held <= 5 and trade.max_adverse_excursion > self.MAE_THRESHOLD_5BAR:
            self.early_exits_triggered += 1
            reason = f"MAE {trade.max_adverse_excursion:.2%} > 1.5% in first {bars_held} bars"
            self._record_exit("mae_5bar")
            logger.warning(f"V4 EARLY EXIT: {reason}")
            return True, reason, current_price

        # CHECK 2: Zero momentum by bar 12 (trade going nowhere)
        # Only trigger if MFE < 0.2% (basically no positive movement at all)
        if bars_held == self.MFE_CHECK_BAR and trade.max_favorable_excursion < self.MFE_THRESHOLD_12BAR:
            self.early_exits_triggered += 1
            reason = f"MFE {trade.max_favorable_excursion:.2%} < 0.2% by bar {bars_held}"
            self._record_exit("mfe_12bar")
            logger.warning(f"V4 EARLY EXIT: {reason}")
            return True, reason, current_price

        # CHECK 3: MAE significantly > MFE after bar 10 (clearly struggling)
        # Only trigger if MAE > 1.2% AND MAE > 1.5x MFE (conservative)
        if bars_held > self.MIN_BARS_FOR_RATIO_CHECK:
            if trade.max_adverse_excursion > self.MIN_MAE_FOR_RATIO_CHECK:
                if trade.max_adverse_excursion > trade.max_favorable_excursion * self.MAE_MFE_RATIO_THRESHOLD:
                    self.early_exits_triggered += 1
                    reason = (f"MAE ({trade.max_adverse_excursion:.2%}) > "
                             f"1.5x MFE ({trade.max_favorable_excursion:.2%})")
                    self._record_exit("mae_mfe_ratio")
                    logger.warning(f"V4 EARLY EXIT: {reason}")
                    return True, reason, current_price

        return False, "", 0.0

    def calculate_savings(self, trade, early_exit_price: float,
                          stop_price: float) -> float:
        """
        Calculate how much we saved by exiting early vs hitting full stop.

        Args:
            trade: The trade being closed
            early_exit_price: Price we exited at
            stop_price: Original stop loss price

        Returns:
            Savings in price units (positive = we saved money)
        """
        entry = getattr(trade, 'actual_entry_price', None) or getattr(trade, 'entry_price', 0)
        direction = getattr(trade, 'direction', 'long').lower()
        position_size = getattr(trade, 'position_size', 1)

        if direction == 'long':
            full_stop_loss = entry - stop_price
            early_exit_loss = entry - early_exit_price
        else:
            full_stop_loss = stop_price - entry
            early_exit_loss = early_exit_price - entry

        savings = (full_stop_loss - early_exit_loss) * position_size
        self.total_savings += max(0, savings)

        return savings

    def _record_exit(self, reason_key: str):
        """Record exit reason for statistics."""
        self.exit_by_reason[reason_key] = self.exit_by_reason.get(reason_key, 0) + 1

    def get_stats(self) -> Dict:
        """Get early exit statistics."""
        return {
            'early_exits_triggered': self.early_exits_triggered,
            'total_savings': f"${self.total_savings:.2f}",
            'exit_breakdown': self.exit_by_reason,
            'thresholds': {
                'mae_5bar': f"{self.MAE_THRESHOLD_5BAR:.1%}",
                'mfe_12bar': f"{self.MFE_THRESHOLD_12BAR:.1%}",
                'mae_mfe_ratio': f"{self.MAE_MFE_RATIO_THRESHOLD}x",
            }
        }

    def reset_stats(self):
        """Reset statistics for new backtest run."""
        self.early_exits_triggered = 0
        self.total_savings = 0.0
        self.exit_by_reason = {}
