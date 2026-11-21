"""End-to-end, no-clobber CLI checks in disposable output directories."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from coinbase_spot.__main__ import main
from coinbase_spot.market_data import load_capture
from coinbase_spot.models import D


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_manifest.json"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "outputs"

    def arguments(self, run_id="demo"):
        return ["replay", "--manifest", str(FIXTURE), "--run-id", run_id,
                "--output-root", str(self.output), "--initial-cash", "1000",
                "--fee-bps", "60", "--slippage-bps", "10"]

    def call(self, arguments):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(arguments)

    def test_end_to_end_report_has_provenance_and_portable_verified_inputs(self):
        self.assertEqual(self.call(self.arguments()), 0)
        output = self.output / "demo"
        report = json.loads((output / "result.json").read_text())
        self.assertEqual(report["mode"], "offline_replay")
        self.assertEqual(report["provenance"]["capture"]["declaration"]["kind"], "synthetic")
        self.assertEqual(D(report["summary"]["final_quantity"]), 0)
        self.assertGreater(report["summary"]["entry_count"], 0)
        self.assertEqual(report["summary"]["entry_count"], report["summary"]["exit_count"])
        self.assertFalse((output / "failure.json").exists())
        self.assertTrue((output / "ledger.sqlite").is_file())
        self.assertTrue((output / "events.jsonl").is_file())
        copied = load_capture(output / "inputs" / "capture.json")
        source = load_capture(FIXTURE)
        self.assertEqual(copied.candles, source.candles)
        self.assertEqual(copied.product, source.product)
        self.assertEqual((output / "inputs" / "original_manifest.json").read_bytes(), FIXTURE.read_bytes())
        self.assertIn("SYNTHETIC INPUT", (output / "report.md").read_text())

    def test_existing_run_is_refused_without_changing_any_artifact(self):
        self.assertEqual(self.call(self.arguments()), 0)
        output = self.output / "demo"
        before = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in output.rglob("*") if p.is_file()}
        self.assertEqual(self.call(self.arguments()), 2)
        after = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in output.rglob("*") if p.is_file()}
        self.assertEqual(after, before)

    def test_failed_replay_never_produces_completion_artifact(self):
        with patch("coinbase_spot.__main__.run_replay", side_effect=ValueError("simulated incomplete replay")):
            self.assertEqual(self.call(self.arguments()), 2)
        output = self.output / "demo"
        self.assertFalse((output / "result.json").exists())
        self.assertFalse((output / "report.md").exists())
        failure = json.loads((output / "failure.json").read_text())
        self.assertEqual(failure["status"], "INCOMPLETE")
        self.assertTrue((output / "ledger.sqlite").is_file())
        self.assertEqual(self.call(self.arguments()), 2)

    def test_live_command_and_missing_cost_assumptions_are_rejected(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as live:
                main(["live"])
            self.assertEqual(live.exception.code, 2)
            arguments = self.arguments()
            arguments = arguments[:arguments.index("--fee-bps")]
            with self.assertRaises(SystemExit) as missing:
                main(arguments)
            self.assertEqual(missing.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_run_id_cannot_escape_output_root(self):
        self.assertEqual(self.call(self.arguments("../escape")), 2)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
