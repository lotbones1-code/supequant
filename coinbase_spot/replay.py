"""Deterministic offline, cash-funded spot replay with explicit bar assumptions.

Decision at a completed bar end -> entry/exit at the following bar open. Intrabar
times are unavailable: a stop observation, or the held-position adverse-low mark,
is timestamped at that bar's end before its close mark. A stop is realized before
any later low is marked, and an open exit precedes every intrabar observation.
The conservative low-before-close path is not a reconstructed tick path.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Sequence

from .ledger import Ledger
from .market_data import series_digest, validate_candles
from .models import Candle, D, Fill, Order, Product, ceil_step, decimal_scope, floor_step
from .risk import RiskPolicy, mark_and_check, size_entry
from .strategy import Decision, STOP_ATR_MULTIPLE, decide


@dataclass(frozen=True)
class StopTrigger:
    reference_price: Decimal
    timestamp: int
    reason: str


def protective_exit(candle: Candle, *, stop_price: Decimal,
                    remaining_quantity: Decimal) -> StopTrigger | None:
    """Protect any remaining inventory, independent of an earlier partial exit.

    A gap fills from the observed open, never from a better obsolete stop price.
    The caller applies adverse slippage, tick rounding, fees and owned quantity.
    """
    stop, quantity = D(stop_price), D(remaining_quantity)
    if stop <= 0 or quantity < 0:
        raise ValueError("invalid protective stop or remaining inventory")
    if quantity == 0:
        return None
    if candle.open <= stop:
        return StopTrigger(candle.open, candle.start, "gap_stop")
    if candle.low <= stop:
        return StopTrigger(stop, candle.end, "intrabar_stop")
    return None


def _benchmark(candles: tuple[Candle, ...], product: Product, initial_cash: Decimal,
               fee_bps: Decimal, slippage_bps: Decimal) -> dict:
    """All-cash buy/hold comparator with the same costs and product quantization."""
    fees, slip = fee_bps / D(10000), slippage_bps / D(10000)
    entry = ceil_step(candles[0].open * (D(1) + slip), product.price_increment)
    exit_price = floor_step(candles[-1].close * (D(1) - slip), product.price_increment)
    quantity = floor_step(min(initial_cash / (entry * (D(1) + fees)),
                              product.base_max_size, product.quote_max_size / entry),
                          product.base_increment)
    if quantity * entry * (D(1) + fees) > initial_cash:
        quantity = max(D(0), quantity - product.base_increment)
    result = {"name": "buy_and_hold", "allocation": "all initial cash subject to product limits",
              "entry_timestamp": candles[0].start, "exit_timestamp": candles[-1].end,
              "entry_price": str(entry), "exit_price": str(exit_price)}
    try:
        product.validate_order(quantity, entry)
        product.validate_order(quantity, exit_price)
    except ValueError as exc:
        result.update({"available": False, "reason": str(exc)})
        return result
    entry_fee = quantity * entry * fees
    exit_fee = quantity * exit_price * fees
    final_equity = initial_cash - quantity * entry - entry_fee + quantity * exit_price - exit_fee
    result.update({"available": True, "quantity": str(quantity), "fees_paid": str(entry_fee + exit_fee),
                   "initial_notional_fraction": str(quantity * entry / initial_cash),
                   "final_equity": str(final_equity), "net_pnl": str(final_equity - initial_cash),
                   "return_pct": str((final_equity / initial_cash - D(1)) * D(100))})
    return result


def run_replay(*, candles: Sequence[Candle], product: Product, ledger: Ledger,
               fee_bps: Decimal, slippage_bps: Decimal, policy: RiskPolicy = RiskPolicy(),
               lookback: int = 20, atr_period: int = 14) -> dict:
    """Replay a full validated window into a fresh, separately namespaced ledger.

    No restarts are silently resumed: strategy state is intentionally not persisted
    in this first replay milestone. An existing event stream is rejected. The
    ledger itself does support persisted fills and reconciliation for later paper
    work. Fees here are hypothetical explicit inputs, not actual exchange tiers.
    """
    if not isinstance(product, Product) or not isinstance(policy, RiskPolicy):
        raise ValueError("validated product and policy are required")
    series = validate_candles(candles, product_id=product.product_id)
    fees, slippage = D(fee_bps), D(slippage_bps)
    if not D(0) <= fees < D(10000) or not D(0) <= slippage < D(10000):
        raise ValueError("fee and slippage bps must be nonnegative and below 10000")
    # Validate parameters before the first ledger mutation.
    decide((), decision_time=series[0].start, in_position=False,
           lookback=lookback, atr_period=atr_period)
    metadata = ledger.metadata
    if metadata["mode"] != "replay" or metadata["product"] != product.to_dict():
        raise ValueError("replay requires a matching dedicated replay ledger")
    if ledger.events():
        raise ValueError("full replay requires a pristine ledger with no events")
    initial = ledger.snapshot()
    if initial.quantity != 0 or initial.open_order_count or initial.halt_reason or initial.cash <= 0:
        raise ValueError("replay ledger is not pristine and cash-funded")
    with decimal_scope():
        return _run(series, product, ledger, fees, slippage, policy,
                    lookback, atr_period, initial.cash)


def _run(series: tuple[Candle, ...], product: Product, ledger: Ledger,
         fee_bps: Decimal, slippage_bps: Decimal, policy: RiskPolicy,
         lookback: int, atr_period: int, initial_cash: Decimal) -> dict:
    fee_rate, slip = fee_bps / D(10000), slippage_bps / D(10000)
    fills, decisions, equity_curve, skipped_entries = [], [], [], []
    pending: Decision | None = None
    stop: Decimal | None = None
    order_sequence = 0
    bars_with_inventory = 0

    def mark(timestamp: int, price: Decimal, phase: str) -> object:
        snapshot = mark_and_check(ledger, timestamp, price, policy)
        equity_curve.append({"timestamp": timestamp, "phase": phase, "price": str(price),
                             "cash": str(snapshot.cash), "quantity": str(snapshot.quantity),
                             "equity": str(snapshot.equity), "high_water": str(snapshot.high_water),
                             "day_start_equity": str(snapshot.day_start_equity),
                             "halt_reason": snapshot.halt_reason})
        return snapshot

    def fill(side: str, quantity: Decimal, price: Decimal, timestamp: int,
             reason: str, signal_id: str | None) -> None:
        nonlocal order_sequence
        product.validate_order(quantity, price)
        order_sequence += 1
        order_id = f"replay.{product.product_id}.{timestamp}.{order_sequence:06d}.{side.lower()}"
        order = Order(order_id, product.product_id, side, quantity, price, fee_bps, timestamp)
        if not ledger.submit(order):
            raise ValueError("unexpected duplicate replay intent")
        fee = quantity * price * fee_rate
        execution = Fill(order_id + ".fill.1", order_id, product.product_id, side,
                         quantity, price, fee, timestamp)
        if not ledger.apply_fill(execution):
            raise ValueError("unexpected duplicate replay fill")
        fills.append({"fill_id": execution.fill_id, "order_id": order_id,
                      "product_id": product.product_id, "side": side,
                      "quantity": str(quantity), "price": str(price), "fee_quote": str(fee),
                      "timestamp": timestamp, "reason": reason, "signal_id": signal_id})

    def sell(reference_price: Decimal, timestamp: int, reason: str,
             signal_id: str | None = None) -> None:
        nonlocal stop
        snapshot = ledger.snapshot()
        if snapshot.quantity <= 0:
            return
        if snapshot.available_quantity != snapshot.quantity:
            raise ValueError("replay cannot assume an exit through reserved or uncertain inventory")
        price = floor_step(reference_price * (D(1) - slip), product.price_increment)
        # An exchange minimum cannot be wished away on exit. Fail the replay
        # visibly if the requested simulation cannot represent a legal sale.
        try:
            product.validate_order(snapshot.quantity, price)
        except ValueError as exc:
            if snapshot.halt_reason is None:
                ledger.halt("EXIT_UNEXECUTABLE_PRODUCT_LIMITS")
            raise ValueError(f"replay incomplete: {reason} exit violates product bounds; "
                             "simulated inventory is retained in the ledger") from exc
        fill("SELL", snapshot.quantity, price, timestamp, reason, signal_id)
        stop = None
        mark(timestamp, reference_price, reason + "_after_fill")

    for index, candle in enumerate(series):
        snapshot = mark(candle.start, candle.open, "open")
        had_inventory = snapshot.quantity > 0
        exited_at_open = False
        signal = pending
        pending = None

        # A gap through an existing stop takes precedence over a scheduled exit.
        if snapshot.quantity > 0 and stop is not None and candle.open <= stop:
            sell(candle.open, candle.start, "gap_stop")
            exited_at_open = True
        elif snapshot.quantity > 0 and signal is not None and signal.action == "EXIT":
            sell(candle.open, candle.start, "channel_exit", signal.signal_id)
            exited_at_open = True

        if signal is not None and signal.action == "ENTER" and not exited_at_open:
            snapshot = ledger.snapshot()
            entry = ceil_step(candle.open * (D(1) + slip), product.price_increment)
            distance = (signal.atr or D(0)) * STOP_ATR_MULTIPLE
            candidate_stop = floor_step(max(D(0), entry - distance), product.price_increment)
            if snapshot.halt_reason or snapshot.has_uncertain_order or snapshot.quantity or snapshot.open_order_count:
                skipped_entries.append({"signal_id": signal.signal_id, "timestamp": candle.start,
                                        "reason": snapshot.halt_reason or "state_blocks_entry"})
            elif not D(0) < candidate_stop < entry:
                skipped_entries.append({"signal_id": signal.signal_id, "timestamp": candle.start,
                                        "reason": "invalid_atr_stop"})
            else:
                quantity = size_entry(snapshot, product, entry_price=entry, stop_price=candidate_stop,
                                      fee_bps=fee_bps, exit_slippage_bps=slippage_bps, policy=policy)
                if quantity > 0:
                    fill("BUY", quantity, entry, candle.start, "channel_entry", signal.signal_id)
                    stop = candidate_stop
                    had_inventory = True
                    mark(candle.start, candle.open, "entry_after_fill")
                else:
                    skipped_entries.append({"signal_id": signal.signal_id, "timestamp": candle.start,
                                            "reason": "below_product_minimum"})

        # This phase sees the low only after all open-time decisions and fills.
        snapshot = ledger.snapshot()
        if snapshot.quantity > 0:
            if stop is None:
                raise ValueError("owned replay inventory has no protective stop")
            trigger = protective_exit(candle, stop_price=stop, remaining_quantity=snapshot.quantity)
            if trigger:
                mark(trigger.timestamp, trigger.reference_price, trigger.reason + "_before_fill")
                sell(trigger.reference_price, trigger.timestamp, trigger.reason)
            else:
                mark(candle.end, candle.low, "held_adverse_low")

        snapshot = mark(candle.end, candle.close, "close")
        bars_with_inventory += int(had_inventory)
        observable = series[max(0, index - max(lookback, atr_period)):index + 1]
        decision = decide(observable, decision_time=candle.end,
                          in_position=snapshot.quantity > 0, lookback=lookback, atr_period=atr_period)
        decisions.append({"signal_id": decision.signal_id, "timestamp": decision.decision_time,
                          "action": decision.action, "atr": None if decision.atr is None else str(decision.atr),
                          "reason": decision.reason})
        if index < len(series) - 1:
            pending = decision if decision.action in ("ENTER", "EXIT") else None
        elif snapshot.quantity > 0:
            sell(candle.close, candle.end, "end_of_data")

    final = ledger.snapshot()
    if final.quantity or final.open_order_count:
        raise ValueError("replay did not terminate flat with every intent settled")
    max_drawdown = max((D(1) - D(point["equity"]) / D(point["high_water"]) for point in equity_curve), default=D(0))
    max_gross_fraction = max((D(point["quantity"]) * D(point["price"]) / D(point["equity"])
                              for point in equity_curve if D(point["equity"]) > 0), default=D(0))
    return {
        "schema_version": 1, "mode": "offline_replay", "purpose": "pipeline validation; no profitability claim",
        "market_data": {"product_id": product.product_id, "interval_seconds": series[0].interval,
                        "start": series[0].start, "end": series[-1].end, "candle_count": len(series),
                        "normalized_candles_sha256": series_digest(series)},
        "strategy": {"name": "long_flat_prior_channel", "lookback": lookback,
                     "atr_period": atr_period, "stop_atr_multiple": str(STOP_ATR_MULTIPLE)},
        "assumptions": {"fee_bps_per_side": str(fee_bps), "adverse_slippage_bps_per_side": str(slippage_bps),
                        "fees_are_hypothetical": True, "tick_rounding": "buy up; sell down",
                        "entry_timing": "completed close decision; following open fill",
                        "intrabar_timing": "open exits first; stop observation or held low at bar end; close last",
                        "intrabar_path": "conservative low-before-close observation, not reconstructed ticks",
                        "liquidity_model": "full immediate fills; no order-book, latency or queue simulation",
                        "terminal_inventory": "liquidate with costs at final close, labelled end_of_data",
                        "policy": {name: str(value) for name, value in asdict(policy).items()}},
        "summary": {"initial_cash": str(initial_cash), "final_cash": str(final.cash),
                    "final_quantity": str(final.quantity), "final_equity": str(final.equity),
                    "net_pnl": str(final.equity - initial_cash), "realized_pnl": str(final.realized_pnl),
                    "return_pct": str((final.equity / initial_cash - D(1)) * D(100)),
                    "fees_paid": str(final.fees_paid), "max_observed_drawdown_pct": str(max_drawdown * D(100)),
                    "entry_count": sum(item["side"] == "BUY" for item in fills),
                    "exit_count": sum(item["side"] == "SELL" for item in fills),
                    "bars_with_inventory": bars_with_inventory, "halt_reason": final.halt_reason,
                    "max_observed_gross_fraction": str(max_gross_fraction)},
        "benchmarks": {"cash": {"final_equity": str(initial_cash), "return_pct": "0"},
                       "buy_and_hold": _benchmark(series, product, initial_cash, fee_bps, slippage_bps),
                       "comparison_note": "Buy/hold allocates up to all initial cash; strategy entry notional is capped by policy. Returns are not matched for exposure."},
        "decisions": decisions, "skipped_entries": skipped_entries, "fills": fills,
        "equity_curve": equity_curve,
    }
