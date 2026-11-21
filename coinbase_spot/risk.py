"""Deterministic risk checks for offline spot replay and paper ledgers.

These limits bound a planned stop loss, not the eventual loss of an exchange
order. Gaps and unavailable liquidity can exceed the plan. No function here
opens a connection, reads credentials, or creates an order.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from .models import D, Product, decimal_scope, floor_step

if TYPE_CHECKING:
    from .ledger import Ledger, Snapshot


@dataclass(frozen=True)
class RiskPolicy:
    """Conservative, immutable ceilings for the first offline milestone.

    A caller can tighten each bound but cannot increase it. Promotion to a
    different risk policy is a separate design decision, not an optimizer input.
    """

    risk_fraction: Decimal = Decimal("0.0025")
    max_notional_fraction: Decimal = Decimal("0.10")
    daily_loss_fraction: Decimal = Decimal("0.01")
    max_drawdown_fraction: Decimal = Decimal("0.03")

    def __post_init__(self) -> None:
        for name, maximum in (
            ("risk_fraction", Decimal("0.0025")),
            ("max_notional_fraction", Decimal("0.10")),
            ("daily_loss_fraction", Decimal("0.01")),
            ("max_drawdown_fraction", Decimal("0.03")),
        ):
            value = D(getattr(self, name))
            if not Decimal(0) < value <= maximum:
                raise ValueError(f"{name} must be positive and at most {maximum}")
            object.__setattr__(self, name, value)


def _require_policy(policy: RiskPolicy) -> None:
    if not isinstance(policy, RiskPolicy):
        raise ValueError("a validated offline RiskPolicy is required")


def _loss_reason(snapshot: "Snapshot", policy: RiskPolicy) -> str | None:
    """Compare inclusive loss boundaries using cash plus marked inventory."""

    equity = D(snapshot.equity)
    if equity <= 0:
        return "NONPOSITIVE_EQUITY"
    daily_baseline = D(snapshot.day_start_equity)
    high_water = D(snapshot.high_water)
    if daily_baseline <= 0 or high_water <= 0:
        raise ValueError("risk requires positive equity baselines from a ledger mark")
    with decimal_scope():
        if equity <= daily_baseline * (Decimal(1) - policy.daily_loss_fraction):
            return "DAILY_LOSS_LIMIT"
        if equity <= high_water * (Decimal(1) - policy.max_drawdown_fraction):
            return "MAX_DRAWDOWN_LIMIT"
    return None


def mark_and_check(
    ledger: "Ledger",
    timestamp: int,
    price: Decimal,
    policy: RiskPolicy = RiskPolicy(),
) -> "Snapshot":
    """Persist a mark and latch the first breached loss limit.

    The ledger owns UTC rollover on every timestamped event: the next day's
    baseline includes prior cash changes and fees, valued at the previous
    observed price, so an overnight gap remains a loss. A later recovery or
    midnight rollover never clears a prior halt. Risk exits remain possible.
    """

    _require_policy(policy)
    snapshot = ledger.mark(timestamp, price)
    if snapshot.halt_reason is not None:
        return snapshot
    reason = _loss_reason(snapshot, policy)
    if reason is not None:
        ledger.halt(reason)
        return ledger.snapshot()
    return snapshot


def size_entry(
    snapshot: "Snapshot",
    product: Product,
    *,
    entry_price: Decimal,
    stop_price: Decimal,
    fee_bps: Decimal,
    exit_slippage_bps: Decimal,
    policy: RiskPolicy = RiskPolicy(),
) -> Decimal:
    """Return a base-increment-rounded, cash-funded long entry quantity.

    The entry price is already the adverse, tick-quantized entry price. The
    stop is below that price; modeled exit slippage worsens it further. Both
    entry and exit fees count against the risk budget. Fees are explicit
    hypothetical assumptions, not a claim about the user's Coinbase fee tier.

    Invalid or blocked state raises ValueError. A valid plan whose entry or
    modeled protective exit cannot meet the product's minimums returns zero;
    size is never increased to force a trade. A later gap can still make an
    actual exit unfillable; this sizing check cannot guarantee an exit fill.
    The snapshot must have been marked before sizing. This function does not
    reserve cash; the ledger independently validates and reserves an intent.
    """

    _require_policy(policy)
    if not isinstance(product, Product):
        raise ValueError("a validated spot Product is required")
    if snapshot.halt_reason is not None:
        raise ValueError("entries are halted")
    if snapshot.has_uncertain_order:
        raise ValueError("an uncertain order prevents entry sizing")
    if snapshot.open_order_count != 0:
        raise ValueError("an open order prevents entry sizing")
    if D(snapshot.quantity) != 0 or D(snapshot.reserved_quantity) != 0:
        raise ValueError("entry sizing requires a flat, unreserved spot position")
    if not snapshot.day or snapshot.last_timestamp is None or D(snapshot.last_price) <= 0:
        raise ValueError("entry sizing requires an observed ledger mark")
    if _loss_reason(snapshot, policy) is not None:
        raise ValueError("marked equity has breached a loss limit")

    entry = D(entry_price)
    stop = D(stop_price)
    fees = D(fee_bps)
    slippage = D(exit_slippage_bps)
    if not Decimal(0) < stop < entry:
        raise ValueError("a long entry requires 0 < stop_price < entry_price")
    if not Decimal(0) <= fees < Decimal(10000):
        raise ValueError("fee_bps must be nonnegative and less than 10000")
    if not Decimal(0) <= slippage < Decimal(10000):
        raise ValueError("exit_slippage_bps must be nonnegative and less than 10000")
    if floor_step(entry, product.price_increment) != entry:
        raise ValueError("entry_price does not match the product price increment")
    if floor_step(stop, product.price_increment) != stop:
        raise ValueError("stop_price does not match the product price increment")

    equity = D(snapshot.equity)
    cash = D(snapshot.cash)
    reserved_cash = D(snapshot.reserved_cash)
    if cash < 0 or reserved_cash < 0 or reserved_cash > cash:
        raise ValueError("cash and reservations are inconsistent")

    with decimal_scope():
        available_cash = cash - reserved_cash
        fee_fraction = fees / Decimal(10000)
        adverse_exit = floor_step(
            stop * (Decimal(1) - slippage / Decimal(10000)),
            product.price_increment,
        )
        entry_cost_per_unit = entry * (Decimal(1) + fee_fraction)
        exit_proceeds_per_unit = adverse_exit * (Decimal(1) - fee_fraction)
        loss_per_unit = entry_cost_per_unit - exit_proceeds_per_unit
        if adverse_exit <= 0 or loss_per_unit <= 0:
            raise ValueError("the modeled stop loss must be finite and positive")

        risk_budget = equity * policy.risk_fraction
        notional_cap = equity * policy.max_notional_fraction
        quantity = floor_step(
            min(
                risk_budget / loss_per_unit,
                notional_cap / entry,
                available_cash / entry_cost_per_unit,
                product.base_max_size,
                product.quote_max_size / entry,
            ),
            product.base_increment,
        )

        # Division and rounding must never turn a ceiling into permission to
        # exceed it. Fail smaller if fixed-precision division lands at an edge.
        if (
            quantity * loss_per_unit > risk_budget
            or quantity * entry_cost_per_unit > available_cash
            or quantity * entry > notional_cap
            or quantity * entry > product.quote_max_size
            or quantity > product.base_max_size
        ):
            quantity = max(Decimal(0), quantity - product.base_increment)

        if quantity <= 0 or quantity < product.base_min_size:
            return Decimal(0)
        if quantity * entry < product.quote_min_size:
            return Decimal(0)
        if quantity * adverse_exit < product.quote_min_size:
            return Decimal(0)
        product.validate_order(quantity, entry)
        return quantity
