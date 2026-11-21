"""Transactional offline ledger. This module cannot submit exchange orders.

Every mutation is an append in a single SQLite transaction. State is rebuilt
from the journal while holding the transaction's lock, so stale in-memory
balances cannot spend the same reservation twice. Hash chaining detects
accidental journal damage; it is not an authentication or security boundary.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from .models import D, Fill, Order, Product, decimal_scope, floor_step, validate_id, validate_timestamp


class LedgerError(ValueError):
    """Invalid event, wrong state namespace, or damaged journal."""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      default=lambda obj: str(obj) if isinstance(obj, Decimal) else _not_serializable(obj))


def _not_serializable(obj: Any) -> None:
    raise TypeError(f"unsupported journal value: {type(obj).__name__}")


def _digest(previous: str, kind: str, payload: str) -> str:
    return hashlib.sha256((previous + "\n" + kind + "\n" + payload).encode()).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    cash: Decimal
    quantity: Decimal
    cost_basis: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    reserved_cash: Decimal
    reserved_quantity: Decimal
    equity: Decimal
    day_start_equity: Decimal
    high_water: Decimal
    last_price: Decimal
    day: str | None
    last_timestamp: int | None
    halt_reason: str | None
    has_uncertain_order: bool
    open_order_count: int
    initial_cash: Decimal

    @property
    def available_cash(self) -> Decimal:
        with decimal_scope():
            return self.cash - self.reserved_cash

    @property
    def available_quantity(self) -> Decimal:
        with decimal_scope():
            return self.quantity - self.reserved_quantity


ACTIVE_STATUSES = frozenset({"OPEN", "PARTIAL", "CANCEL_PENDING", "UNCERTAIN"})


@dataclass
class _State:
    initial_cash: Decimal
    cash: Decimal
    quantity: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")
    day: str | None = None
    day_start_equity: Decimal = Decimal("0")
    high_water: Decimal = Decimal("0")
    last_timestamp: int | None = None
    halt_reason: str | None = None
    orders: dict[str, dict] = field(default_factory=dict)
    fills: dict[str, dict] = field(default_factory=dict)

    def snapshot(self) -> Snapshot:
        reserved_cash = D("0")
        reserved_quantity = D("0")
        active = [record for record in self.orders.values() if record["status"] in ACTIVE_STATUSES]
        for record in active:
            intent = record["intent"]
            remaining = intent.quantity - record["filled"]
            if intent.side == "BUY":
                reserved_cash += remaining * intent.limit_price * (1 + intent.fee_bps / 10000)
            else:
                reserved_quantity += remaining
        return Snapshot(
            cash=self.cash, quantity=self.quantity, cost_basis=self.cost_basis,
            realized_pnl=self.realized_pnl, fees_paid=self.fees_paid,
            reserved_cash=reserved_cash, reserved_quantity=reserved_quantity,
            equity=self.cash + self.quantity * self.last_price,
            day_start_equity=self.day_start_equity, high_water=self.high_water,
            last_price=self.last_price, day=self.day, last_timestamp=self.last_timestamp,
            halt_reason=self.halt_reason,
            has_uncertain_order=any(record["status"] == "UNCERTAIN" for record in active),
            open_order_count=len(active), initial_cash=self.initial_cash,
        )


class Ledger:
    """A single-product offline state store, permanently bound to one run.

    `paper` is a reserved offline namespace, not a market-data connection or an
    execution adapter. Live/account namespaces are intentionally unsupported.
    """

    def __init__(self, connection: sqlite3.Connection, *, product: Product, metadata: dict):
        self._connection = connection
        self.product = product
        self._metadata = metadata

    @staticmethod
    def _identity(product: Product, initial_cash: Decimal, run_id: str, mode: str) -> dict:
        validate_id(run_id)
        if mode not in {"replay", "paper"}:
            raise LedgerError("only separate replay/paper state is supported; no live mode exists")
        initial_cash = D(initial_cash)
        if initial_cash <= 0:
            raise LedgerError("initial cash must be positive")
        return {"schema_version": 1, "product": product.to_dict(), "initial_cash": str(initial_cash),
                "run_id": run_id, "mode": mode}

    @classmethod
    def create(cls, path: Path, *, product: Product, initial_cash: Decimal,
               run_id: str, mode: str = "replay") -> "Ledger":
        metadata = cls._identity(product, initial_cash, run_id, mode)
        path = Path(path)
        # Never truncate, recycle, or silently reset a prior run's state.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        connection = sqlite3.connect(path, timeout=5, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE run_metadata (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)")
            connection.execute("CREATE TABLE journal_head (id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER NOT NULL, digest TEXT NOT NULL)")
            connection.execute("INSERT INTO run_metadata VALUES (1, ?)", (_json(metadata),))
            connection.execute("INSERT INTO journal_head VALUES (1, 0, ?)",
                               (hashlib.sha256(_json(metadata).encode()).hexdigest(),))
            connection.commit()
            return cls(connection, product=product, metadata=metadata)
        except BaseException:
            connection.rollback()
            connection.close()
            raise

    @classmethod
    def open(cls, path: Path, *, product: Product, run_id: str, mode: str = "replay") -> "Ledger":
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise LedgerError("ledger must be an existing regular state file")
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise LedgerError("ledger integrity check failed")
            rows = connection.execute("SELECT id, payload FROM run_metadata").fetchall()
            if len(rows) != 1 or rows[0][0] != 1:
                raise LedgerError("missing or ambiguous run metadata")
            metadata = json.loads(rows[0][1])
            expected = cls._identity(product, D(metadata["initial_cash"]), run_id, mode)
            if metadata != expected:
                raise LedgerError("state namespace/product/schema mismatch")
            result = cls(connection, product=product, metadata=metadata)
            result.snapshot()  # Validate the full journal before returning usable state.
            return result
        except BaseException:
            connection.close()
            raise

    @property
    def metadata(self) -> dict:
        return json.loads(_json(self._metadata))

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _read_state(self) -> tuple[_State, int, str]:
        initial = D(self._metadata["initial_cash"])
        state = _State(initial_cash=initial, cash=initial, day_start_equity=initial,
                       high_water=initial)
        sequence = 0
        digest = hashlib.sha256(_json(self._metadata).encode()).hexdigest()
        for seq, kind, payload, actual_digest in self._connection.execute(
            "SELECT seq, kind, payload, digest FROM events ORDER BY seq"
        ):
            if seq != sequence + 1 or actual_digest != _digest(digest, kind, payload):
                raise LedgerError("journal sequence/hash mismatch; state will not be reset")
            try:
                data = json.loads(payload)
                if not self._apply(state, kind, data):
                    raise LedgerError("journal contains a duplicate/no-op event")
            except (KeyError, TypeError, ValueError) as exc:
                raise LedgerError(f"invalid journal event {seq}") from exc
            sequence, digest = seq, actual_digest
        head = self._connection.execute("SELECT id, seq, digest FROM journal_head").fetchall()
        if head != [(1, sequence, digest)]:
            raise LedgerError("journal head mismatch; truncated history will not be reset")
        return state, sequence, digest

    def snapshot(self) -> Snapshot:
        with decimal_scope():
            self._connection.execute("BEGIN")
            try:
                state, _, _ = self._read_state()
                result = state.snapshot()
                self._connection.commit()
                return result
            except BaseException:
                self._connection.rollback()
                raise

    def events(self) -> list[dict]:
        with decimal_scope():
            self._connection.execute("BEGIN")
            try:
                self._read_state()
                result = [{"seq": seq, "type": kind, "payload": json.loads(payload), "sha256": digest}
                          for seq, kind, payload, digest in self._connection.execute(
                              "SELECT seq, kind, payload, digest FROM events ORDER BY seq")]
                self._connection.commit()
                return result
            except BaseException:
                self._connection.rollback()
                raise

    def _mutate(self, kind: str, data: dict) -> bool:
        with decimal_scope():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                state, sequence, digest = self._read_state()
                changed = self._apply(state, kind, data)
                if changed:
                    payload = _json(data)
                    new_digest = _digest(digest, kind, payload)
                    self._connection.execute("INSERT INTO events VALUES (?, ?, ?, ?)",
                                             (sequence + 1, kind, payload, new_digest))
                    self._connection.execute("UPDATE journal_head SET seq=?, digest=? WHERE id=1",
                                             (sequence + 1, new_digest))
                self._connection.commit()
                return changed
            except BaseException:
                self._connection.rollback()
                raise

    def submit(self, order: Order) -> bool:
        return self._mutate("SUBMIT", asdict(order))

    def apply_fill(self, fill: Fill) -> bool:
        return self._mutate("FILL", asdict(fill))

    def request_cancel(self, order_id: str) -> bool:
        return self._mutate("CANCEL_REQUESTED", {"order_id": order_id})

    def confirm_cancel(self, order_id: str, *, filled_quantity: Decimal) -> bool:
        return self._mutate("CANCEL_CONFIRMED", {"order_id": order_id, "filled_quantity": D(filled_quantity)})

    def mark_uncertain(self, order_id: str, reason: str) -> bool:
        return self._mutate("UNCERTAIN", {"order_id": order_id, "reason": reason})

    def mark(self, timestamp: int, price: Decimal) -> Snapshot:
        self._mutate("MARK", {"timestamp": timestamp, "price": D(price)})
        return self.snapshot()

    def halt(self, reason: str) -> bool:
        return self._mutate("HALT", {"reason": reason})

    @staticmethod
    def _clock(state: _State, timestamp: int) -> None:
        validate_timestamp(timestamp)
        if state.last_timestamp is not None and timestamp < state.last_timestamp:
            raise LedgerError("events cannot move backwards in time")
        day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        if day != state.day:
            # Roll before the new day's first timed event, including fills.
            # Include all prior-day realized changes at the previous mark,
            # while leaving the new day's price gap and fees in its PnL.
            state.day_start_equity = state.cash + state.quantity * state.last_price
            state.day = day
        state.last_timestamp = timestamp

    @staticmethod
    def _reason(value: str) -> None:
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise LedgerError("a nonempty reason of at most 500 characters is required")

    def _apply(self, state: _State, kind: str, data: dict) -> bool:
        if kind == "SUBMIT":
            intent = Order(**data)
            prior = state.orders.get(intent.order_id)
            if prior is not None:
                if prior["intent"] != intent:
                    raise LedgerError("order ID reused for a different intent")
                return False
            if intent.product_id != self.product.product_id:
                raise LedgerError("wrong product")
            self.product.validate_order(intent.quantity, intent.limit_price)
            self._clock(state, intent.timestamp)
            snapshot = state.snapshot()
            if intent.side == "BUY":
                if snapshot.halt_reason or snapshot.has_uncertain_order:
                    raise LedgerError("entries blocked by halt or uncertain state")
                if snapshot.quantity != 0 or snapshot.open_order_count:
                    raise LedgerError("only one owned or pending spot position is supported")
                cost = intent.quantity * intent.limit_price * (1 + intent.fee_bps / 10000)
                if cost > snapshot.available_cash:
                    raise LedgerError("insufficient unreserved cash including fees")
            elif intent.quantity > snapshot.available_quantity:
                raise LedgerError("cannot sell inventory not owned and available")
            state.orders[intent.order_id] = {"intent": intent, "status": "OPEN", "filled": D("0")}
        elif kind == "FILL":
            fill = Fill(**data)
            payload = json.loads(_json(asdict(fill)))
            prior = state.fills.get(fill.fill_id)
            if prior is not None:
                if prior != payload:
                    raise LedgerError("fill ID reused with conflicting economic contents")
                return False
            if fill.order_id not in state.orders:
                raise LedgerError("fill for unknown order; reconciliation required")
            record = state.orders[fill.order_id]
            intent = record["intent"]
            if record["status"] not in ACTIVE_STATUSES:
                raise LedgerError("late fill after terminal state requires separate reconciliation")
            if fill.product_id != intent.product_id or fill.side != intent.side:
                raise LedgerError("fill identity does not match its order")
            if fill.timestamp < intent.timestamp:
                raise LedgerError("fill predates intent")
            self._clock(state, fill.timestamp)
            if fill.quantity > intent.quantity - record["filled"]:
                raise LedgerError("fill exceeds remaining order quantity")
            if floor_step(fill.quantity, self.product.base_increment) != fill.quantity:
                raise LedgerError("fill quantity is off the base increment")
            if floor_step(fill.price, self.product.price_increment) != fill.price:
                raise LedgerError("fill price is off the price increment")
            notional = fill.quantity * fill.price
            if fill.fee_quote > notional * intent.fee_bps / 10000:
                raise LedgerError("fill fee exceeds the explicit reserved fee assumption")
            if fill.side == "BUY":
                if fill.price > intent.limit_price:
                    raise LedgerError("fill exceeds reserved entry price")
                state.cash -= notional + fill.fee_quote
                state.quantity += fill.quantity
                state.cost_basis += notional + fill.fee_quote
                if state.last_price == 0:
                    state.last_price = fill.price
            else:
                if fill.quantity > state.quantity:
                    raise LedgerError("fill would create a short position")
                removed_basis = (state.cost_basis if fill.quantity == state.quantity else
                                 state.cost_basis * fill.quantity / state.quantity)
                proceeds = notional - fill.fee_quote
                state.cash += proceeds
                state.quantity -= fill.quantity
                state.cost_basis -= removed_basis
                state.realized_pnl += proceeds - removed_basis
            state.fees_paid += fill.fee_quote
            record["filled"] += fill.quantity
            if record["filled"] == intent.quantity:
                record["status"] = "FILLED"
            elif record["status"] == "OPEN":
                record["status"] = "PARTIAL"
            state.fills[fill.fill_id] = payload
        elif kind in {"CANCEL_REQUESTED", "CANCEL_CONFIRMED", "UNCERTAIN"}:
            validate_id(data["order_id"])
            if data["order_id"] not in state.orders:
                raise LedgerError("unknown order")
            record = state.orders[data["order_id"]]
            if kind == "CANCEL_CONFIRMED":
                if D(data["filled_quantity"]) != record["filled"]:
                    raise LedgerError("cancel cumulative fill mismatch; reservation remains held")
                if record["status"] in {"FILLED", "CANCELED"}:
                    return False
                record["status"] = "CANCELED"
            elif kind == "CANCEL_REQUESTED":
                if record["status"] in {"FILLED", "CANCELED", "CANCEL_PENDING"}:
                    return False
                if record["status"] == "UNCERTAIN":
                    raise LedgerError("uncertainty needs explicit reconciliation, not a cancel request")
                record["status"] = "CANCEL_PENDING"
            else:
                self._reason(data["reason"])
                if record["status"] in {"FILLED", "CANCELED"}:
                    raise LedgerError("cannot mark a terminal order uncertain")
                if record["status"] == "UNCERTAIN":
                    return False
                record["status"] = "UNCERTAIN"
        elif kind == "MARK":
            self._clock(state, data["timestamp"])
            price = D(data["price"])
            if price <= 0:
                raise LedgerError("mark price must be positive")
            state.last_price = price
            equity = state.cash + state.quantity * price
            state.high_water = max(state.high_water, equity)
        elif kind == "HALT":
            self._reason(data["reason"])
            if state.halt_reason is not None:
                return False
            state.halt_reason = data["reason"]
        else:
            raise LedgerError("unknown event kind")
        snapshot = state.snapshot()
        if min(snapshot.cash, snapshot.quantity, snapshot.cost_basis, snapshot.available_cash, snapshot.available_quantity) < 0:
            raise LedgerError("event violates cash/inventory/reservation conservation")
        if snapshot.quantity == 0 and snapshot.cost_basis != 0:
            raise LedgerError("flat inventory must have zero cost basis")
        return True
