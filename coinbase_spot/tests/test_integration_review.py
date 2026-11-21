"""Independent offline review of CLI failure and completion boundaries."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from coinbase_spot.__main__ import _save_new, main
from coinbase_spot.ledger import Ledger
from coinbase_spot.models import D, Product


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class IndependentReplayReview(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def capture(self, rows, *, minimum="0.01"):
        directory = self.root / "source"
        directory.mkdir()
        product_data = json.loads((FIXTURES / "synthetic_product.json").read_text())
        product_data["quote_min_size"] = minimum
        raw_product = (json.dumps(product_data, sort_keys=True) + "\n").encode()
        candles = [{"start": str(index * 60), "open": row[0], "high": row[1],
                    "low": row[2], "close": row[3], "volume": "100"}
                   for index, row in enumerate(rows)]
        raw_candles = (json.dumps({"candles": candles}, sort_keys=True) + "\n").encode()
        (directory / "product.json").write_bytes(raw_product)
        (directory / "candles.json").write_bytes(raw_candles)
        manifest = {
            "schema_version": 1, "product_id": "SOL-USD", "interval_seconds": 60,
            "coverage": {"start": "0", "end": str(len(rows) * 60)},
            "provenance": {"kind": "synthetic", "source": "independent offline regression",
                           "description": "Invented prices; no exchange capture or profitability evidence.",
                           "captured_at": "1970-01-02T00:00:00Z"},
            "files": {
                "product": {"path": "product.json", "sha256": hashlib.sha256(raw_product).hexdigest()},
                "candles": {"path": "candles.json", "sha256": hashlib.sha256(raw_candles).hexdigest()},
            },
        }
        path = directory / "capture.json"
        path.write_text(json.dumps(manifest))
        return path, Product.from_coinbase(product_data)

    def run_cli(self, manifest, *, fee="0", slippage="0"):
        output = self.root / "output"
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            result = main([
                "replay", "--manifest", str(manifest), "--run-id", "review-run",
                "--output-root", str(output), "--initial-cash", "1000",
                "--fee-bps", fee, "--slippage-bps", slippage,
                "--lookback", "3", "--atr-period", "2",
            ])
        return result, output / "review-run"

    def test_failed_completion_flush_does_not_publish_final_filename(self):
        for name in ("result.json", "failure.json"):
            destination = self.root / name
            with self.subTest(name=name):
                with patch("coinbase_spot.__main__.os.fsync", side_effect=OSError("simulated flush failure")):
                    with self.assertRaises(OSError):
                        _save_new(destination, b'{"status": "complete"}\n')
                self.assertFalse(destination.exists(), "failed writes must not leave a final artifact")

    def test_final_name_is_removed_if_directory_flush_fails(self):
        destination = self.root / "result.json"
        with patch("coinbase_spot.__main__.os.fsync", side_effect=[None, OSError("directory flush failure")]):
            with self.assertRaises(OSError):
                _save_new(destination, b'{"status": "complete"}\n')
        self.assertFalse(destination.exists())

    def test_partial_write_never_publishes_or_leaves_a_staging_file(self):
        actual_fdopen = os.fdopen
        for failure in ("short_return", "write_error"):
            @contextmanager
            def interrupted_writer(fd, mode):
                with actual_fdopen(fd, mode) as stream:
                    def partial_write(data):
                        written = stream.write(data[:5])
                        if failure == "write_error":
                            raise OSError("simulated write error after partial bytes")
                        return written
                    yield SimpleNamespace(write=partial_write, flush=stream.flush, fileno=stream.fileno)

            with self.subTest(failure=failure):
                with patch("coinbase_spot.__main__.os.fdopen", new=interrupted_writer):
                    with self.assertRaises(OSError):
                        _save_new(self.root / "result.json", b'{"status": "complete"}\n')
                self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_output_is_never_clobbered_or_removed(self):
        destination = self.root / "result.json"
        original = b'{"original": "retained exactly"}\n'
        destination.write_bytes(original)
        inode = destination.stat().st_ino
        with self.assertRaises(FileExistsError):
            _save_new(destination, b'{"replacement": "must fail"}\n')
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(destination.stat().st_ino, inode)

    def test_unfillable_gap_produces_failure_without_completed_result(self):
        rows = [("100", "101", "99", "100")] * 3 + [
            ("100", "104", "99", "103"),
            ("110", "112", "109", "111"),
            ("1", "2", "0.5", "1"),
        ]
        manifest, product = self.capture(rows, minimum="20")
        code, output = self.run_cli(manifest)
        self.assertEqual(code, 2)
        self.assertFalse((output / "result.json").exists())
        failure = json.loads((output / "failure.json").read_text())
        self.assertEqual(failure["status"], "INCOMPLETE")
        self.assertIn("inventory is retained", failure["message"])
        with Ledger.open(output / "ledger.sqlite", product=product, run_id="review-run") as ledger:
            self.assertGreater(ledger.snapshot().quantity, D(0))
            self.assertIsNotNone(ledger.snapshot().halt_reason)
            self.assertEqual(ledger.snapshot().open_order_count, 0)

    def test_no_signal_window_keeps_cash_and_truthfully_charges_buy_hold(self):
        manifest, _ = self.capture([("100", "101", "99", "100")] * 6)
        code, output = self.run_cli(manifest, fee="10", slippage="10")
        self.assertEqual(code, 0)
        self.assertFalse((output / "failure.json").exists())
        report = json.loads((output / "result.json").read_text())
        summary = report["summary"]
        for name in ("net_pnl", "realized_pnl", "return_pct", "fees_paid", "max_observed_drawdown_pct"):
            self.assertEqual(D(summary[name]), D(0), name)
        self.assertEqual(D(summary["final_cash"]), D("1000"))
        self.assertEqual(summary["entry_count"], 0)
        self.assertEqual(report["market_data"]["end"], 360)
        self.assertEqual(report["provenance"]["capture"]["declaration"]["kind"], "synthetic")
        self.assertLess(D(report["benchmarks"]["buy_and_hold"]["net_pnl"]), D(0))
        self.assertEqual(report["benchmarks"]["cash"]["return_pct"], "0")


if __name__ == "__main__":
    unittest.main()
