import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from coinbase_spot.market_data import completed_prefix, load_capture, parse_coinbase_candles


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((FIXTURES / "synthetic_candles.json").read_text())

    def parse(self, payload):
        return parse_coinbase_candles(payload, product_id="SOL-USD", interval=60)

    def test_manifest_hashes_identity_and_reverse_sorted_response(self):
        capture = load_capture(FIXTURES / "synthetic_manifest.json")
        self.assertEqual(capture.product.product_id, "SOL-USD")
        self.assertEqual(capture.manifest["provenance"]["kind"], "synthetic")
        self.assertEqual(len(capture.candles), 50)
        self.assertEqual(len(capture.manifest_sha256), 64)
        self.assertEqual(capture.candles[0].start, capture.manifest["coverage"]["start"])
        self.assertEqual(capture.candles[-1].end, capture.manifest["coverage"]["end"])

    def test_duplicate_and_gap_are_rejected_not_repaired(self):
        for mutation in (lambda rows: rows.append(copy.deepcopy(rows[0])), lambda rows: rows.pop(5)):
            with self.subTest(mutation=mutation):
                payload = copy.deepcopy(self.payload)
                mutation(payload["candles"])
                with self.assertRaises(ValueError):
                    self.parse(payload)

    def test_wrong_product_nonpositive_and_nonfinite_prices(self):
        for key, value in (("product_id", "BTC-USD"), ("open", "0"), ("high", "NaN"),
                           ("low", "-1"), ("volume", "-1"), ("start", "2026-01-01T00:00:00")):
            with self.subTest(key=key, value=value):
                payload = copy.deepcopy(self.payload)
                payload["candles"][0][key] = value
                with self.assertRaises(ValueError):
                    self.parse(payload)

    def test_invalid_ohlc_or_off_grid_timestamp_rejected(self):
        for key, value in (("high", "1"), ("start", "1767225601")):
            payload = copy.deepcopy(self.payload)
            payload["candles"][0][key] = value
            with self.assertRaises(ValueError):
                self.parse(payload)

    def test_incomplete_candle_excluded_until_end(self):
        bars = self.parse(self.payload)
        self.assertEqual(len(completed_prefix(bars, bars[3].start + 30)), 3)
        self.assertEqual(len(completed_prefix(bars, bars[3].end)), 4)
        self.assertEqual(completed_prefix(bars, bars[0].start), ())

    def altered_manifest(self, change, *, alter_bytes=False):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for source in FIXTURES.glob("*.json"):
                shutil.copyfile(source, target / source.name)
            manifest_path = target / "synthetic_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            change(manifest)
            manifest_path.write_text(json.dumps(manifest))
            if alter_bytes:
                with (target / "synthetic_product.json").open("ab") as stream:
                    stream.write(b" ")
            with self.assertRaises(ValueError):
                load_capture(manifest_path)

    def test_exact_input_byte_hash_is_enforced(self):
        self.altered_manifest(lambda manifest: None, alter_bytes=True)

    def test_coverage_product_and_utc_provenance_enforced(self):
        self.altered_manifest(lambda m: m["coverage"].update(end=m["coverage"]["end"] + 60))
        self.altered_manifest(lambda m: m.update(product_id="BTC-USD"))
        self.altered_manifest(lambda m: m["provenance"].update(captured_at="2026-01-02T00:00:00"))
        self.altered_manifest(lambda m: m["provenance"].update(kind="recorded", captured_at="2025-12-01T00:00:00Z"))

    def test_paths_cannot_escape_capture_directory(self):
        self.altered_manifest(lambda m: m["files"]["product"].update(path="../outside.json"))

    def test_duplicate_manifest_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_capture(path)


if __name__ == "__main__":
    unittest.main()
