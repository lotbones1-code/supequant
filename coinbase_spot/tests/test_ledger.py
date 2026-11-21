"""Hand-calculated accounting and order-state regressions, never exchange I/O."""

from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
import sqlite3
import tempfile
import unittest

from coinbase_spot.ledger import Ledger, LedgerError
from coinbase_spot.models import D, Fill, Order, Product


def product() -> Product:
    return Product("SOL-USD", "SOL", "USD", D("0.001"), D("0.01"), D("0.001"),
                   D("0.001"), D("1000000"), D("0.01"), D("100000000"))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite"
        self.product = product()
        self.ledger = Ledger.create(self.path, product=self.product, initial_cash=D("1000"), run_id="test")
        self.addCleanup(lambda: self.ledger.close())

    def order(self, order_id, side, quantity, price, fee="0", timestamp=1):
        return Order(order_id, "SOL-USD", side, D(quantity), D(price), D(fee), timestamp)

    def fill(self, fill_id, order, quantity=None, price=None, fee="0", timestamp=None):
        return Fill(fill_id, order.order_id, order.product_id, order.side,
                    D(quantity) if quantity is not None else order.quantity,
                    D(price) if price is not None else order.limit_price,
                    D(fee), order.timestamp if timestamp is None else timestamp)

    def buy(self, quantity="10", price="100", fee_bps="0", fee_quote="0"):
        order = self.order("entry", "BUY", quantity, price, fee_bps)
        self.ledger.submit(order)
        self.ledger.apply_fill(self.fill("entry-fill", order, fee=fee_quote))
        return order

    def test_partial_then_stop_does_not_double_credit_prior_profit(self):
        # Original audit reproduction: +49.89 then -50.09 = -0.20.
        self.buy()
        first = self.order("tp1", "SELL", "5", "109.978", timestamp=2)
        self.ledger.submit(first)
        self.ledger.apply_fill(self.fill("tp1-fill", first))
        interim = self.ledger.snapshot()
        self.assertEqual(interim.quantity, D("5"))
        self.assertEqual(interim.realized_pnl, D("49.890"))
        second = self.order("stop-remaining", "SELL", "5", "89.982", timestamp=3)
        self.ledger.submit(second)
        self.ledger.apply_fill(self.fill("stop-fill", second))
        final = self.ledger.mark(3, D("89.982"))
        self.assertEqual(final.cash, D("999.800"))
        self.assertEqual(final.realized_pnl, D("-0.200"))
        self.assertEqual(final.quantity, 0)
        self.assertEqual(final.cost_basis, 0)
        self.assertEqual(final.equity - final.initial_cash, final.realized_pnl)

    def test_both_leg_fees_and_partial_cost_basis(self):
        self.buy(quantity="5", fee_bps="10", fee_quote="0.5")
        self.assertEqual(self.ledger.snapshot().cash, D("499.5"))
        first = self.order("partial", "SELL", "2", "110", "10", 2)
        self.ledger.submit(first)
        self.ledger.apply_fill(self.fill("partial-fill", first, fee="0.22"))
        snapshot = self.ledger.mark(2, D("110"))
        self.assertEqual(snapshot.cost_basis, D("300.3"))
        self.assertEqual(snapshot.realized_pnl, D("19.58"))
        self.assertEqual(snapshot.fees_paid, D("0.72"))
        self.assertEqual(snapshot.equity - D("1000"),
                         snapshot.realized_pnl + snapshot.quantity * snapshot.last_price - snapshot.cost_basis)
        last = self.order("last", "SELL", "3", "90", "10", 3)
        self.ledger.submit(last)
        self.ledger.apply_fill(self.fill("last-fill", last, fee="0.27"))
        self.assertEqual(self.ledger.snapshot().cash, D("989.01"))
        self.assertEqual(self.ledger.snapshot().realized_pnl, D("-10.99"))

    def test_flat_price_round_trip_loses_exact_fees(self):
        self.buy(quantity="5", fee_bps="10", fee_quote="0.5")
        exit_order = self.order("exit", "SELL", "5", "100", "10", 2)
        self.ledger.submit(exit_order)
        self.ledger.apply_fill(self.fill("exit-fill", exit_order, fee="0.5"))
        self.assertEqual(self.ledger.snapshot().cash, D("999"))
        self.assertEqual(self.ledger.snapshot().realized_pnl, D("-1"))

    def test_duplicate_fill_is_exactly_once_after_reload(self):
        order = self.buy(quantity="5")
        before = self.ledger.snapshot()
        self.ledger.close()
        self.ledger = Ledger.open(self.path, product=self.product, run_id="test")
        self.assertFalse(self.ledger.apply_fill(self.fill("entry-fill", order)))
        self.assertEqual(self.ledger.snapshot(), before)
        with self.assertRaises(LedgerError):
            self.ledger.apply_fill(self.fill("entry-fill", order, price="99"))
        self.assertEqual(self.ledger.snapshot(), before)

    def test_duplicate_intent_does_not_reserve_twice_and_conflict_rejects(self):
        order = self.order("entry", "BUY", "5", "100", "10")
        self.assertTrue(self.ledger.submit(order))
        self.assertFalse(self.ledger.submit(order))
        self.assertEqual(self.ledger.snapshot().reserved_cash, D("500.5"))
        with self.assertRaises(LedgerError):
            self.ledger.submit(replace(order, quantity=D("6")))

    def test_pending_order_counts_as_position_and_cash_is_not_reused(self):
        self.ledger.submit(self.order("pending", "BUY", "5", "100"))
        with Ledger.open(self.path, product=self.product, run_id="test") as other:
            self.assertEqual(other.snapshot().reserved_cash, D("500"))
            with self.assertRaises(LedgerError):
                other.submit(self.order("other", "BUY", "1", "100"))
        self.assertEqual(self.ledger.snapshot().open_order_count, 1)

    def test_cancel_request_retains_reservation_and_late_partial_is_booked(self):
        order = self.order("pending", "BUY", "5", "100")
        self.ledger.submit(order)
        self.ledger.apply_fill(self.fill("first", order, quantity="2"))
        self.ledger.request_cancel(order.order_id)
        self.assertEqual(self.ledger.snapshot().reserved_cash, D("300"))
        self.ledger.apply_fill(self.fill("during-cancel", order, quantity="1", timestamp=2))
        with self.assertRaises(LedgerError):
            self.ledger.confirm_cancel(order.order_id, filled_quantity=D("2"))
        self.assertEqual(self.ledger.snapshot().reserved_cash, D("200"))
        self.ledger.confirm_cancel(order.order_id, filled_quantity=D("3"))
        self.assertEqual(self.ledger.snapshot().reserved_cash, 0)
        self.assertEqual(self.ledger.snapshot().quantity, D("3"))
        self.assertEqual(self.ledger.snapshot().cash, D("700"))

    def test_uncertain_order_keeps_cash_reserved_across_restart(self):
        order = self.order("pending", "BUY", "5", "100")
        self.ledger.submit(order)
        self.ledger.mark_uncertain(order.order_id, "simulated response timeout")
        self.ledger.close()
        self.ledger = Ledger.open(self.path, product=self.product, run_id="test")
        self.assertTrue(self.ledger.snapshot().has_uncertain_order)
        self.assertEqual(self.ledger.snapshot().reserved_cash, D("500"))
        with self.assertRaises(LedgerError):
            self.ledger.submit(self.order("replacement", "BUY", "5", "100"))

    def test_no_overspending_including_fee(self):
        with self.assertRaises(LedgerError):
            self.ledger.submit(self.order("entry", "BUY", "10", "100", "10"))
        self.assertEqual(self.ledger.events(), [])

    def test_no_short_or_second_full_close(self):
        with self.assertRaises(LedgerError):
            self.ledger.submit(self.order("short", "SELL", "1", "100"))
        self.buy()
        exit_order = self.order("exit", "SELL", "10", "100", timestamp=2)
        self.ledger.submit(exit_order)
        with self.assertRaises(LedgerError):
            self.ledger.submit(self.order("other-exit", "SELL", "1", "100", timestamp=2))
        self.ledger.apply_fill(self.fill("exit-fill", exit_order))
        with self.assertRaises(LedgerError):
            self.ledger.submit(self.order("phantom-close", "SELL", "10", "100", timestamp=3))
        self.assertEqual(self.ledger.snapshot().cash, D("1000"))

    def test_invalid_fill_rolls_back_every_field_and_journal(self):
        order = self.order("entry", "BUY", "5", "100", "10")
        self.ledger.submit(order)
        before, events = self.ledger.snapshot(), self.ledger.events()
        invalid = [self.fill("bad-size", order, quantity="6"),
                   self.fill("bad-price", order, price="101"),
                   self.fill("bad-fee", order, fee="10"),
                   replace(self.fill("wrong-side", order), side="SELL"),
                   replace(self.fill("wrong-product", order), product_id="BTC-USD")]
        for fill in invalid:
            with self.subTest(fill=fill.fill_id), self.assertRaises(LedgerError):
                self.ledger.apply_fill(fill)
            self.assertEqual(self.ledger.snapshot(), before)
            self.assertEqual(self.ledger.events(), events)

    def test_halt_blocks_entry_but_exit_remains_possible(self):
        self.buy(quantity="5")
        self.ledger.halt("manual offline test halt")
        exit_order = self.order("exit", "SELL", "5", "100", timestamp=2)
        self.ledger.submit(exit_order)
        self.ledger.apply_fill(self.fill("exit-fill", exit_order))
        with self.assertRaises(LedgerError):
            self.ledger.submit(self.order("after-halt", "BUY", "1", "100", timestamp=3))

    def test_identity_rejects_other_run_mode_product_and_live(self):
        for changes in ({"run_id": "different"}, {"mode": "paper"}, {"mode": "live"},
                        {"product": replace(self.product, base_currency="BTC", product_id="BTC-USD")}):
            kwargs = {"product": self.product, "run_id": "test", **changes}
            with self.subTest(changes=changes), self.assertRaises((LedgerError, ValueError)):
                Ledger.open(self.path, **kwargs)
        with self.assertRaises(FileExistsError):
            Ledger.create(self.path, product=self.product, initial_cash=D("1"), run_id="replacement")

    def test_run_state_is_separate(self):
        with Ledger.create(Path(self.temp.name) / "other.sqlite", product=self.product,
                           initial_cash=D("500"), run_id="other") as other:
            self.buy(quantity="5")
            self.ledger.halt("test halt")
            self.assertEqual(other.snapshot().cash, D("500"))
            self.assertEqual(other.snapshot().quantity, 0)
            self.assertIsNone(other.snapshot().halt_reason)
            self.assertEqual(other.events(), [])

    def test_corrupt_journal_fails_instead_of_resetting(self):
        self.buy(quantity="5")
        self.ledger.close()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE events SET payload = '{}' WHERE seq=1")
        with self.assertRaises(LedgerError):
            Ledger.open(self.path, product=self.product, run_id="test")
        # No recovery overwrite occurred; keep a new connection only for cleanup.
        self.ledger = Ledger(sqlite3.connect(self.path), product=self.product, metadata={})

    def test_money_arithmetic_does_not_inherit_low_decimal_precision(self):
        with localcontext() as context:
            context.prec = 4
            self.buy(quantity="5.123", price="100.123")
            self.assertEqual(self.ledger.snapshot().cash, D("487.069871"))


if __name__ == "__main__":
    unittest.main()
