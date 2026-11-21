from dataclasses import replace
from decimal import localcontext
from pathlib import Path
import tempfile
import unittest

from coinbase_spot.ledger import Ledger
from coinbase_spot.market_data import load_capture
from coinbase_spot.models import Candle, D
from coinbase_spot.replay import protective_exit, run_replay
from coinbase_spot.risk import RiskPolicy


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASE = [("100", "101", "99", "100")] * 3 + [("100", "104", "99", "103")]


def bars(rows):
    return tuple(Candle("SOL-USD", i * 60, 60, *map(D, row), D("100"))
                 for i, row in enumerate(rows))


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.product = load_capture(FIXTURES / "synthetic_manifest.json").product

    def replay(self, candles, *, fee="0", slippage="0", policy=RiskPolicy()):
        with tempfile.TemporaryDirectory() as directory:
            with Ledger.create(Path(directory) / "replay.sqlite", product=self.product,
                               initial_cash=D("1000"), run_id="test", mode="replay") as ledger:
                return run_replay(candles=candles, product=self.product, ledger=ledger,
                                  fee_bps=D(fee), slippage_bps=D(slippage), policy=policy,
                                  lookback=3, atr_period=2)

    def test_entry_delayed_to_next_open_and_final_liquidation(self):
        result = self.replay(bars(BASE + [("110", "112", "109", "111")]))
        buy, sale = result["fills"]
        self.assertEqual((buy["side"], buy["timestamp"], D(buy["price"])), ("BUY", 240, D("110")))
        self.assertEqual(buy["signal_id"], result["decisions"][3]["signal_id"])
        self.assertEqual(sale["reason"], "end_of_data")
        self.assertEqual(sale["timestamp"], 300)
        self.assertEqual(D(result["summary"]["final_quantity"]), 0)

    def test_stop_recomputed_from_actual_fill_and_checked_in_entry_bar(self):
        result = self.replay(bars(BASE + [("110", "112", "101", "111")]))
        buy, sale = result["fills"]
        # Frozen signal ATR is 3.5, actual fill is 110, so stop is 103, not 96.
        self.assertEqual(D(sale["price"]), D("103"))
        self.assertEqual(sale["reason"], "intrabar_stop")
        self.assertGreater(sale["timestamp"], buy["timestamp"])
        self.assertEqual(result["summary"]["entry_count"], 1)

    def test_gap_stop_uses_open_not_obsolete_stop(self):
        result = self.replay(bars(BASE + [("110", "112", "109", "111"),
                                          ("90", "92", "89", "91")]))
        sale = result["fills"][1]
        self.assertEqual((sale["reason"], sale["timestamp"], D(sale["price"])), ("gap_stop", 300, D("90")))
        self.assertFalse(any(point["phase"] == "held_adverse_low" and point["timestamp"] == 360
                             for point in result["equity_curve"]))

    def test_scheduled_open_exit_precedes_later_intrabar_stop(self):
        result = self.replay(bars(BASE + [("110", "112", "109", "111"),
                                         ("111", "113", "110", "112"),
                                         ("112", "114", "111", "113"),
                                         ("113", "114", "108", "108.5"),
                                         ("110", "112", "80", "100")]))
        sale = result["fills"][1]
        self.assertEqual((sale["reason"], sale["timestamp"], D(sale["price"])),
                         ("channel_exit", 480, D("110")))
        self.assertFalse(any(point["phase"] == "held_adverse_low" and point["timestamp"] == 540
                             for point in result["equity_curve"]))

    def test_gap_below_exit_minimum_fails_without_fabricating_flat_inventory(self):
        product = replace(self.product, quote_min_size=D("20"))
        candles = bars(BASE + [("110", "112", "109", "111"), ("1", "2", "0.5", "1")])
        with tempfile.TemporaryDirectory() as directory:
            with Ledger.create(Path(directory) / "replay.sqlite", product=product,
                               initial_cash=D("1000"), run_id="test", mode="replay") as ledger:
                with self.assertRaisesRegex(ValueError, "replay incomplete.*inventory is retained"):
                    run_replay(candles=candles, product=product, ledger=ledger,
                               fee_bps=D("0"), slippage_bps=D("0"), lookback=3, atr_period=2)
                self.assertGreater(ledger.snapshot().quantity, 0)
                self.assertIsNotNone(ledger.snapshot().halt_reason)
                self.assertEqual(ledger.snapshot().open_order_count, 0)

    def test_adverse_costs_and_ledger_cash_conservation(self):
        result = self.replay(bars(BASE + [("110", "112", "109", "111")]), fee="20", slippage="10")
        expected_cash, total_fees = D("1000"), D("0")
        for execution in result["fills"]:
            notional = D(execution["quantity"]) * D(execution["price"])
            charge = D(execution["fee_quote"])
            total_fees += charge
            expected_cash += (notional if execution["side"] == "SELL" else -notional) - charge
        self.assertEqual(D(result["summary"]["final_cash"]), expected_cash)
        self.assertEqual(D(result["summary"]["fees_paid"]), total_fees)
        self.assertGreater(total_fees, 0)
        self.assertGreater(D(result["fills"][0]["price"]), D("110"))
        self.assertLess(D(result["fills"][1]["price"]), D("111"))
        self.assertEqual(D(result["summary"]["realized_pnl"]), expected_cash - D("1000"))

    def test_future_high_low_cannot_change_entry_sizing(self):
        original = bars(BASE + [("110", "112", "109", "111")])
        changed = original[:-1] + (replace(original[-1], high=D("9999"), low=D("1")),)
        first, second = self.replay(original), self.replay(changed)
        self.assertEqual(first["fills"][0], second["fills"][0])

    def test_decision_prefix_invariant_when_future_data_changes(self):
        original = bars(BASE + [("110", "112", "109", "111"), ("111", "115", "110", "114")])
        changed = original[:-1] + (replace(original[-1], high=D("9999"), low=D("1"), close=D("2")),)
        first, second = self.replay(original), self.replay(changed)
        self.assertEqual(first["decisions"][:-1], second["decisions"][:-1])
        self.assertEqual(first["fills"][0], second["fills"][0])

    def test_full_window_cash_baseline_and_cost_aware_buy_hold(self):
        result = self.replay(bars(BASE + [("110", "112", "109", "111")]), fee="20", slippage="10")
        self.assertEqual(result["equity_curve"][0]["timestamp"], 0)
        self.assertEqual(result["equity_curve"][-1]["timestamp"], 300)
        self.assertEqual(result["benchmarks"]["cash"]["return_pct"], "0")
        benchmark = result["benchmarks"]["buy_and_hold"]
        self.assertTrue(benchmark["available"])
        self.assertGreater(D(benchmark["fees_paid"]), 0)
        self.assertGreater(D(benchmark["initial_notional_fraction"]), D("0.9"))
        self.assertIn("not matched for exposure", result["benchmarks"]["comparison_note"])

    def test_adverse_mark_triggers_durable_halt_even_if_close_recovers(self):
        policy = RiskPolicy(daily_loss_fraction=D("0.001"))
        result = self.replay(bars(BASE + [("110", "112", "104", "111")]), policy=policy)
        self.assertEqual(result["summary"]["halt_reason"], "DAILY_LOSS_LIMIT")
        self.assertGreater(D(result["summary"]["final_equity"]), D("1000"))
        self.assertGreater(D(result["summary"]["max_observed_drawdown_pct"]), D("0.1"))

    def test_protection_applies_to_remaining_inventory_after_partial_sale(self):
        candle = bars([("90", "95", "80", "92")])[0]
        trigger = protective_exit(candle, stop_price=D("100"), remaining_quantity=D("0.1"))
        self.assertEqual((trigger.reason, trigger.reference_price), ("gap_stop", D("90")))
        self.assertIsNone(protective_exit(candle, stop_price=D("100"), remaining_quantity=D("0")))

    def test_replay_requires_fresh_matching_replay_namespace(self):
        candles = bars(BASE)
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("paper", "replay"):
                with Ledger.create(Path(directory) / (mode + ".sqlite"), product=self.product,
                                   initial_cash=D("1000"), run_id="test", mode=mode) as ledger:
                    if mode == "replay":
                        ledger.mark(0, D("100"))
                    with self.assertRaises(ValueError):
                        run_replay(candles=candles, product=self.product, ledger=ledger,
                                   fee_bps=D("0"), slippage_bps=D("0"), lookback=3, atr_period=2)

    def test_money_results_independent_of_ambient_decimal_precision(self):
        candles = bars(BASE + [("110", "112", "109", "111")])
        normal = self.replay(candles, fee="20", slippage="10")
        with localcontext() as context:
            context.prec = 7
            changed = self.replay(candles, fee="20", slippage="10")
        self.assertEqual(normal, changed)


if __name__ == "__main__":
    unittest.main()
