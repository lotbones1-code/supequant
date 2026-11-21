"""Independent safety regressions; temporary offline SQLite fixtures only."""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from coinbase_spot.ledger import Ledger, LedgerError
from coinbase_spot.models import D, Fill, Order, Product


class IndependentLedgerReview(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "review.sqlite"
        self.product = Product(
            "BTC-USD", "BTC", "USD", D(".01"), D(".01"), D(".01"),
            D(".01"), D("100"), D(".01"), D("10000000"),
        )

    def create(self):
        return Ledger.create(
            self.path, product=self.product, initial_cash=D("1000"),
            run_id="independent-review",
        )

    def reopen(self):
        return Ledger.open(
            self.path, product=self.product, run_id="independent-review",
        )

    def fill_one(self, ledger, side, timestamp, *, fee="1", price="100"):
        name = side.lower()
        ledger.submit(Order(
            name, "BTC-USD", side, D("1"), D(price), D("100"), timestamp,
        ))
        ledger.apply_fill(Fill(
            "fill-" + name, name, "BTC-USD", side, D("1"), D(price),
            D(fee), timestamp,
        ))

    def test_removing_halt_tail_is_detected_on_reopen(self):
        with self.create() as ledger:
            ledger.mark(0, D("100"))
            ledger.halt("independent-review-halt")
        with sqlite3.connect(self.path) as database:
            database.execute("DELETE FROM events WHERE seq=(SELECT MAX(seq) FROM events)")
        with self.assertRaises(LedgerError):
            with self.reopen():
                pass

    def test_emptying_journal_cannot_restore_initial_state(self):
        with self.create() as ledger:
            ledger.mark(0, D("100"))
            self.fill_one(ledger, "BUY", 1)
        with sqlite3.connect(self.path) as database:
            database.execute("DELETE FROM events")
        with self.assertRaises(LedgerError):
            with self.reopen():
                pass

    def test_new_day_baseline_includes_prior_day_execution_costs(self):
        with self.create() as ledger:
            ledger.mark(0, D("100"))
            self.fill_one(ledger, "BUY", 1)
            self.fill_one(ledger, "SELL", 2)
            self.assertEqual(ledger.snapshot().equity, D("998"))
            next_day = ledger.mark(86400, D("100"))
            self.assertEqual(next_day.day_start_equity, D("998"))
            self.assertEqual(next_day.equity, D("998"))

    def test_execution_crossing_day_does_not_erase_new_day_costs(self):
        with self.create() as ledger:
            ledger.mark(0, D("100"))
            self.fill_one(ledger, "BUY", 86399)
            self.fill_one(ledger, "SELL", 86401)
            after = ledger.mark(86402, D("100"))
            self.assertEqual(after.day_start_equity, D("999"))
            self.assertEqual(after.equity, D("998"))

    def test_prior_fee_rollover_still_counts_overnight_price_gap(self):
        with self.create() as ledger:
            ledger.mark(0, D("100"))
            self.fill_one(ledger, "BUY", 86399)
        with self.reopen() as ledger:
            after = ledger.mark(86400, D("80"))
            self.assertEqual(after.day_start_equity, D("999"))
            self.assertEqual(after.equity, D("979"))
            self.assertEqual(after.day_start_equity - after.equity, D("20"))


if __name__ == "__main__":
    unittest.main()
