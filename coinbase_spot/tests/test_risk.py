"""Money and state regressions for the isolated offline risk boundary."""

from dataclasses import FrozenInstanceError
from decimal import Decimal, ROUND_UP, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from coinbase_spot.ledger import Ledger
from coinbase_spot.models import D, Fill, Order, Product, decimal_scope
from coinbase_spot.risk import RiskPolicy, mark_and_check, size_entry


def product(**changes) -> Product:
    values = {
        "product_id": "SOL-USD",
        "base_currency": "SOL",
        "quote_currency": "USD",
        "base_increment": D("0.001"),
        "quote_increment": D("0.01"),
        "price_increment": D("0.01"),
        "base_min_size": D("0.001"),
        "base_max_size": D("1000000"),
        "quote_min_size": D("0.01"),
        "quote_max_size": D("1000000000"),
    }
    values.update(changes)
    return Product(**values)


def marked_snapshot(**changes):
    """Only the fields read by sizing; integration tests use real ledgers."""

    values = {
        "cash": D("1000"),
        "quantity": D("0"),
        "reserved_cash": D("0"),
        "reserved_quantity": D("0"),
        "equity": D("1000"),
        "day_start_equity": D("1000"),
        "high_water": D("1000"),
        "last_price": D("100"),
        "day": "1970-01-01",
        "last_timestamp": 100,
        "halt_reason": None,
        "has_uncertain_order": False,
        "open_order_count": 0,
    }
    values.update(changes)
    return SimpleNamespace(**values)


class RiskSizingTests(unittest.TestCase):
    def size(self, *, snapshot=None, instrument=None, **changes):
        values = {
            "entry_price": D("100"),
            "stop_price": D("95"),
            "fee_bps": D("60"),
            "exit_slippage_bps": D("50"),
        }
        values.update(changes)
        return size_entry(
            marked_snapshot() if snapshot is None else snapshot,
            product() if instrument is None else instrument,
            **values,
        )

    def test_stop_budget_includes_both_fees_and_adverse_exit(self):
        quantity = self.size()
        # Hand-calculated per-unit costs: pay 100.60; the slipped 94.525
        # sell is rounded down to 94.52, yielding 93.95288 after its fee.
        self.assertEqual(quantity, D("0.376"))
        self.assertLessEqual(quantity * D("6.64712"), D("2.50"))
        self.assertGreater((quantity + D("0.001")) * D("6.64712"), D("2.50"))
        zero_cost_quantity = self.size(fee_bps=D(0), exit_slippage_bps=D(0))
        self.assertEqual(zero_cost_quantity, D("0.5"))
        self.assertLess(quantity, zero_cost_quantity)

    def test_tight_stop_cannot_bypass_ten_percent_notional_cap(self):
        quantity = self.size(stop_price=D("99.99"), fee_bps=D(0), exit_slippage_bps=D(0))
        self.assertEqual(quantity, D("1"))
        self.assertEqual(quantity * D("100"), D("100"))

    def test_cash_cap_includes_entry_fee_even_if_equity_is_stale(self):
        # A deliberately inconsistent upstream snapshot makes cash the binding
        # ceiling: an overstated equity estimate must not authorize overspending.
        quantity = self.size(snapshot=marked_snapshot(cash=D("5")))
        self.assertEqual(quantity, D("0.049"))
        self.assertLessEqual(quantity * D("100.6"), D("5"))
        self.assertGreater((quantity + D("0.001")) * D("100.6"), D("5"))
        reserved = self.size(snapshot=marked_snapshot(cash=D("5"), reserved_cash=D("1")))
        self.assertLessEqual(reserved * D("100.6"), D("4"))

    def test_rounds_down_non_power_of_ten_increment(self):
        quantity = self.size(instrument=product(base_increment=D("0.03")))
        self.assertEqual(quantity, D("0.36"))

    def test_adverse_exit_tick_rounding_cannot_exceed_stop_budget(self):
        quantity = self.size(instrument=product(price_increment=D("0.1")))
        # A coarser tick changes the slipped exit to 94.5: ignoring the
        # actual sell-price rounding would permit 0.376 and exceed 2.50 loss.
        self.assertEqual(quantity, D("0.374"))
        self.assertLessEqual(quantity * D("6.667"), D("2.5"))
        self.assertGreater(D("0.376") * D("6.667"), D("2.5"))

    def test_product_maxima_cap_quantity(self):
        self.assertEqual(self.size(instrument=product(base_max_size=D("0.2"))), D("0.2"))
        self.assertEqual(self.size(instrument=product(quote_max_size=D("25"))), D("0.25"))

    def test_minimums_never_round_up_into_a_trade(self):
        self.assertEqual(self.size(instrument=product(base_min_size=D("0.4"))), D(0))
        self.assertEqual(self.size(instrument=product(quote_min_size=D("40"))), D(0))
        self.assertEqual(self.size(snapshot=marked_snapshot(cash=D(0))), D(0))

    def test_planned_stop_exit_must_also_meet_product_minimum(self):
        # The ordinary 0.376 size has 37.60 entry notional but only
        # 35.53952 at its adverse stop. An expected exit below 37 is invalid.
        self.assertEqual(self.size(instrument=product(quote_min_size=D("37"))), D(0))
        self.assertEqual(self.size(instrument=product(quote_min_size=D("35"))), D("0.376"))

    def test_fresh_ledger_positive_cash_does_not_substitute_for_a_mark(self):
        with TemporaryDirectory() as directory:
            with Ledger.create(Path(directory) / "fresh.sqlite3", product=product(),
                               initial_cash=D("1000"), run_id="unmarked-risk") as ledger:
                fresh = ledger.snapshot()
                self.assertEqual(fresh.equity, D("1000"))
                self.assertGreater(fresh.day_start_equity, D(0))
                self.assertGreater(fresh.high_water, D(0))
                with self.assertRaisesRegex(ValueError, "observed ledger mark"):
                    self.size(snapshot=fresh)
                marked = mark_and_check(ledger, 100, D("100"))
                self.assertGreater(self.size(snapshot=marked), D(0))
        for missing in ({"day": None}, {"last_timestamp": None}, {"last_price": D(0)}):
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "observed ledger mark"):
                self.size(snapshot=marked_snapshot(**missing))

    def test_entry_rejects_halt_uncertainty_pending_and_owned_inventory(self):
        for changes in (
            {"halt_reason": "MANUAL_HALT"},
            {"has_uncertain_order": True},
            {"open_order_count": 1},
            {"quantity": D("0.001")},
            {"reserved_quantity": D("0.001")},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.size(snapshot=marked_snapshot(**changes))

    def test_unlatched_loss_breach_cannot_be_sized(self):
        with self.assertRaises(ValueError):
            self.size(snapshot=marked_snapshot(equity=D("990"), cash=D("990")))
        with self.assertRaises(ValueError):
            self.size(snapshot=marked_snapshot(day_start_equity=D(0), high_water=D(0)))

    def test_rejects_invalid_price_cost_and_reservation_inputs(self):
        for changes in (
            {"entry_price": D(0)},
            {"stop_price": D(0)},
            {"stop_price": D("100")},
            {"stop_price": D("101")},
            {"entry_price": D("100.005")},
            {"stop_price": D("95.005")},
            {"fee_bps": D("-1")},
            {"fee_bps": D("10000")},
            {"exit_slippage_bps": D("-1")},
            {"exit_slippage_bps": D("10000")},
            {"fee_bps": Decimal("NaN")},
            {"exit_slippage_bps": Decimal("Infinity")},
            {"entry_price": 100.0},
            {"fee_bps": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.size(**changes)
        with self.assertRaises(ValueError):
            self.size(snapshot=marked_snapshot(reserved_cash=D("1001")))

    def test_policy_cannot_be_loosened_or_mutated(self):
        for field, value in (
            ("risk_fraction", "0.0026"),
            ("max_notional_fraction", "0.1001"),
            ("daily_loss_fraction", "0.0101"),
            ("max_drawdown_fraction", "0.0301"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                RiskPolicy(**{field: D(value)})
        for value in (D(0), D("-1"), Decimal("NaN"), 0.001, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RiskPolicy(risk_fraction=value)
        policy = RiskPolicy(risk_fraction=D("0.001"))
        self.assertLess(self.size(policy=policy), self.size())
        with self.assertRaises(FrozenInstanceError):
            policy.risk_fraction = D("0.01")

    def test_ambient_decimal_context_cannot_change_size(self):
        normal = self.size()
        with localcontext() as context:
            context.prec = 6
            context.rounding = ROUND_UP
            self.assertEqual(self.size(), normal)


class RiskLedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "risk.sqlite3"
        self.product = product()
        self.ledger = Ledger.create(
            self.path, product=self.product, initial_cash=D("1000"), run_id="risk-test"
        )
        mark_and_check(self.ledger, 100, D("100"))

    def tearDown(self):
        self.ledger.close()
        self.directory.cleanup()

    def execute(self, side, *, quantity="1", price="100", fee_bps="0", timestamp=101):
        quantity, price, fee_bps = D(quantity), D(price), D(fee_bps)
        order_id = f"{side.lower()}-{timestamp}"
        self.ledger.submit(Order(
            order_id=order_id, product_id="SOL-USD", side=side,
            quantity=quantity, limit_price=price, fee_bps=fee_bps,
            timestamp=timestamp,
        ))
        with decimal_scope():
            fee_quote = quantity * price * fee_bps / D("10000")
        self.ledger.apply_fill(Fill(
            fill_id=f"fill-{order_id}", order_id=order_id, product_id="SOL-USD",
            side=side, quantity=quantity, price=price, fee_quote=fee_quote,
            timestamp=timestamp,
        ))

    def test_daily_limit_uses_realized_and_unrealized_loss_including_fees(self):
        self.execute("BUY", fee_bps="60")
        before_exit = mark_and_check(self.ledger, 102, D("91"))
        self.assertEqual(before_exit.equity, D("990.4"))
        self.assertIsNone(before_exit.halt_reason)
        self.execute("SELL", price="91", fee_bps="60", timestamp=103)
        after_exit = mark_and_check(self.ledger, 103, D("91"))
        self.assertEqual(after_exit.equity, D("989.854"))
        self.assertEqual(after_exit.halt_reason, "DAILY_LOSS_LIMIT")

    def test_exact_daily_boundary_halts_including_open_loss(self):
        self.execute("BUY")
        snapshot = mark_and_check(self.ledger, 102, D("90"))
        self.assertEqual(snapshot.equity, D("990"))
        self.assertEqual(snapshot.halt_reason, "DAILY_LOSS_LIMIT")

    def test_midnight_baseline_does_not_erase_overnight_gap(self):
        self.execute("BUY")
        last_day = mark_and_check(self.ledger, 86340, D("98"))
        self.assertEqual(last_day.equity, D("998"))
        self.assertIsNone(last_day.halt_reason)
        next_day = mark_and_check(self.ledger, 86400, D("80"))
        self.assertEqual(next_day.day_start_equity, D("998"))
        self.assertEqual(next_day.equity, D("980"))
        self.assertEqual(next_day.halt_reason, "DAILY_LOSS_LIMIT")

    def test_high_water_survives_midnight_and_drawdown_can_bind_first(self):
        self.execute("BUY", quantity="5")
        peak = mark_and_check(self.ledger, 200, D("140"))
        self.assertEqual(peak.high_water, D("1200"))
        previous_close = mark_and_check(self.ledger, 86340, D("134"))
        self.assertIsNone(previous_close.halt_reason)
        rollover = mark_and_check(self.ledger, 86400, D("134"))
        self.assertEqual(rollover.day_start_equity, D("1170"))
        self.assertEqual(rollover.high_water, D("1200"))
        at_limit = mark_and_check(self.ledger, 86401, D("132.8"))
        self.assertEqual(at_limit.equity, D("1164"))
        self.assertEqual(at_limit.halt_reason, "MAX_DRAWDOWN_LIMIT")

    def test_halt_survives_restart_recovery_and_midnight_but_allows_exit(self):
        self.execute("BUY")
        mark_and_check(self.ledger, 102, D("90"))
        self.ledger.close()
        self.ledger = Ledger.open(self.path, product=self.product, run_id="risk-test")
        self.assertEqual(self.ledger.snapshot().halt_reason, "DAILY_LOSS_LIMIT")
        recovered = mark_and_check(self.ledger, 86400, D("110"))
        self.assertEqual(recovered.halt_reason, "DAILY_LOSS_LIMIT")
        self.execute("SELL", price="110", timestamp=86401)
        snapshot = mark_and_check(self.ledger, 86401, D("110"))
        self.assertEqual(snapshot.quantity, D(0))
        self.assertEqual(snapshot.halt_reason, "DAILY_LOSS_LIMIT")
        with self.assertRaises(ValueError):
            size_entry(snapshot, self.product, entry_price=D("110"), stop_price=D("100"),
                       fee_bps=D(0), exit_slippage_bps=D(0))
        with self.assertRaises(ValueError):
            self.ledger.submit(Order("blocked", "SOL-USD", "BUY", D("0.1"), D("110"), D(0), 86402))

    def test_cancel_requested_and_unknown_orders_keep_entries_blocked(self):
        self.ledger.submit(Order("pending", "SOL-USD", "BUY", D("1"), D("100"), D("60"), 101))
        before = self.ledger.snapshot()
        self.ledger.request_cancel("pending")
        after = self.ledger.snapshot()
        self.assertEqual(after.reserved_cash, before.reserved_cash)
        with self.assertRaises(ValueError):
            size_entry(after, self.product, entry_price=D("100"), stop_price=D("95"),
                       fee_bps=D("60"), exit_slippage_bps=D("50"))
        self.ledger.mark_uncertain("pending", "simulated ambiguous acknowledgement")
        self.assertTrue(self.ledger.snapshot().has_uncertain_order)
        self.ledger.close()
        self.ledger = Ledger.open(self.path, product=self.product, run_id="risk-test")
        reopened = self.ledger.snapshot()
        self.assertTrue(reopened.has_uncertain_order)
        self.assertEqual(reopened.reserved_cash, before.reserved_cash)
        with self.assertRaises(ValueError):
            size_entry(reopened, self.product, entry_price=D("100"), stop_price=D("95"),
                       fee_bps=D("60"), exit_slippage_bps=D("50"))


if __name__ == "__main__":
    unittest.main()
