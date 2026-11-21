"""One transparent long/flat reference strategy for plumbing validation.

There is no tuning, forecast, external model, or claim of a profitable edge.
Signals use completed candles and the prior channel, excluding the signal bar.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .market_data import completed_prefix
from .models import Candle, D, decimal_scope


STOP_ATR_MULTIPLE = D("2")


@dataclass(frozen=True)
class Decision:
    action: str
    atr: Decimal | None
    decision_time: int
    reason: str
    signal_id: str


def _positive_integer(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def decide(candles: Sequence[Candle], *, decision_time: int, in_position: bool,
           lookback: int = 20, atr_period: int = 14) -> Decision:
    """Decide from the observable prefix, independently of any later candles.

    ENTER means a next-open candidate, never an execution at this bar's close.
    EXIT means a next-open sale of owned inventory; it never opens a short.
    ATR is the simple mean of the last ``atr_period`` completed true ranges.
    """
    _positive_integer(lookback, "lookback")
    _positive_integer(atr_period, "atr_period")
    if type(in_position) is not bool:
        raise ValueError("in_position must be boolean")
    prefix = completed_prefix(candles, decision_time)
    identity = prefix[-1].product_id if prefix else "empty"

    def decision(action: str, reason: str, atr: Decimal | None = None) -> Decision:
        signal_id = f"decision.{identity}.{decision_time}.{action.lower()}"
        return Decision(action, atr, decision_time, reason, signal_id)

    if len(prefix) < max(lookback + 1, atr_period + 1):
        return decision("HOLD", "warmup")
    prior = prefix[-lookback - 1:-1]
    current = prefix[-1]
    with decimal_scope():
        ranges = []
        for index in range(len(prefix) - atr_period, len(prefix)):
            candle, previous = prefix[index], prefix[index - 1]
            ranges.append(max(candle.high - candle.low,
                              abs(candle.high - previous.close),
                              abs(candle.low - previous.close)))
        atr = sum(ranges, D("0")) / D(atr_period)
        if in_position and current.close < min(c.low for c in prior):
            return decision("EXIT", "close_below_prior_low_channel", atr)
        if not in_position and current.close > max(c.high for c in prior):
            if atr <= 0:
                return decision("HOLD", "zero_atr", atr)
            return decision("ENTER", "close_above_prior_high_channel", atr)
        return decision("HOLD", "no_channel_break", atr)
