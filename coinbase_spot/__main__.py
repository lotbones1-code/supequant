"""Explicit offline replay CLI. No live command, credentials, or network code."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile

from . import __version__
from .ledger import Ledger
from .market_data import Capture, load_capture
from .models import D, validate_id
from .replay import run_replay
from .risk import RiskPolicy


UPSTREAM_BASE_COMMIT = "122e0066537ad0697fe7df08a40b6cc9a66675d1"


def _bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n").encode()


def _save_new(path: Path, data: bytes) -> None:
    """Publish complete bytes atomically without overwriting an existing file."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    staged = Path(temporary)
    published = False
    try:
        with os.fdopen(fd, "wb") as stream:
            if stream.write(data) != len(data):
                raise OSError("incomplete artifact write")
            stream.flush()
            os.fsync(stream.fileno())
        # Same-filesystem hard-link publication is atomic and refuses clobbering.
        os.link(staged, path)
        published = True
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        # Only remove the inode created by this call, never a pre-existing file.
        if published:
            try:
                if path.samefile(staged):
                    path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        staged.unlink(missing_ok=True)


def _source_identity() -> dict:
    package = Path(__file__).parent
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(package.glob("*.py"))}
    return {"version": __version__, "upstream_base_commit": UPSTREAM_BASE_COMMIT,
            "python_files_sha256": hashes,
            "implementation_sha256": hashlib.sha256(_bytes(hashes)).hexdigest()}


def _copy_inputs(capture: Capture, source: Path, output: Path) -> dict:
    """Retain the exact verified data bytes and a portable manifest for this run."""
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != capture.manifest_sha256:
        raise ValueError("capture manifest changed after validation")
    payloads = {}
    for name, descriptor in capture.manifest["files"].items():
        path = (source.parent / descriptor["path"]).resolve()
        if not path.is_relative_to(source.parent):
            raise ValueError("input path escaped the capture directory")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
            raise ValueError("input bytes changed after validation")
        payloads[name] = data
    target = output / "inputs"
    target.mkdir()
    _save_new(target / "original_manifest.json", original)
    portable = json.loads(_bytes(capture.manifest))
    for name, data in payloads.items():
        _save_new(target / f"{name}.json", data)
        portable["files"][name]["path"] = f"{name}.json"
    encoded = _bytes(portable)
    _save_new(target / "capture.json", encoded)
    return {"original_manifest_sha256": capture.manifest_sha256,
            "portable_manifest_sha256": hashlib.sha256(encoded).hexdigest(),
            "input_files_sha256": {name: spec["sha256"] for name, spec in capture.manifest["files"].items()},
            "declaration": capture.manifest["provenance"]}


def _markdown(report: dict) -> str:
    summary = report["summary"]
    provenance = report["provenance"]
    kind = provenance["capture"]["declaration"]["kind"]
    return f"""# Offline Coinbase spot replay

**{kind.upper()} INPUT — pipeline validation only. No investment-performance claim.**

Run: `{provenance['run_id']}`. Mode: offline replay. Product: `{report['market_data']['product_id']}`.
Fees and slippage are explicit hypothetical assumptions, not an account's verified fee tier.

| Observation | Value |
|---|---:|
| Initial simulated cash | {summary['initial_cash']} |
| Final simulated equity | {summary['final_equity']} |
| Net simulated PnL | {summary['net_pnl']} |
| Fees charged | {summary['fees_paid']} |
| Return over the entire input window (%) | {summary['return_pct']} |
| Maximum observed drawdown (%) | {summary['max_observed_drawdown_pct']} |
| Entries / exits | {summary['entry_count']} / {summary['exit_count']} |
| Remaining inventory | {summary['final_quantity']} |
| Entry halt | {summary['halt_reason'] or 'none'} |

The complete result, decisions, fills, skipped entries, marked equity and cash/buy-and-hold
comparators are in `result.json`. Buy-and-hold uses up to all initial cash while this
reference strategy caps entry notional at 10%; returns are not matched for exposure.

`run.json` binds parameters, runtime and source-file hashes. `inputs/capture.json`
and the adjacent files retain a portable copy of the exact data. `events.jsonl` and
`ledger.sqlite` retain the complete transaction journal. A `result.json` is written
only after a successful, flat completion; `failure.json` means an incomplete run.

This model uses full simulated fills and a declared OHLC event order. It does not
model queue position, market depth, exchange latency or guaranteed stop fills.
Loss limits halt new entries; existing inventory still depends on its modeled exit.
There is no live execution adapter, account access, agent service or promotion path.
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Credential-free offline Coinbase spot replay only")
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay = subparsers.add_parser("replay", help="validate local snapshots and run one isolated simulation")
    replay.add_argument("--manifest", required=True, type=Path)
    replay.add_argument("--run-id", required=True)
    replay.add_argument("--output-root", required=True, type=Path)
    replay.add_argument("--initial-cash", required=True, help="hypothetical quote cash, a decimal string")
    replay.add_argument("--fee-bps", required=True, help="hypothetical fee per side; 100 bps = 1%")
    replay.add_argument("--slippage-bps", required=True, help="hypothetical adverse slippage per side")
    replay.add_argument("--lookback", default=20, type=int)
    replay.add_argument("--atr-period", default=14, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = None
    try:
        validate_id(args.run_id)
        initial, fees, slip = D(args.initial_cash), D(args.fee_bps), D(args.slippage_bps)
        if initial <= 0 or not 0 <= fees < 10000 or not 0 <= slip < 10000:
            raise ValueError("positive initial cash and fee/slippage bps within [0, 10000) are required")
        if args.lookback < 1 or args.atr_period < 1:
            raise ValueError("strategy windows must be positive integers")
        source = args.manifest.resolve()
        capture = load_capture(source)
        args.output_root.mkdir(parents=True, exist_ok=True)
        candidate = args.output_root / args.run_id
        candidate.mkdir(exist_ok=False)  # Includes no-clobber protection for failed runs.
        output = candidate
        capture_identity = _copy_inputs(capture, source, output)
        policy = RiskPolicy()
        provenance = {"run_id": args.run_id, "capture": capture_identity, "code": _source_identity()}
        definition = {
            "schema_version": 1, "mode": "offline_replay", "provenance": provenance,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                        "system": platform.system(), "sqlite": sqlite3.sqlite_version},
            "parameters": {"initial_cash": str(initial), "fee_bps_per_side": str(fees),
                           "slippage_bps_per_side": str(slip), "lookback": args.lookback,
                           "atr_period": args.atr_period, "policy": asdict(policy)},
        }
        _save_new(output / "run.json", _bytes(definition))
        with Ledger.create(output / "ledger.sqlite", product=capture.product,
                           initial_cash=initial, run_id=args.run_id) as ledger:
            report = run_replay(candles=capture.candles, product=capture.product, ledger=ledger,
                                fee_bps=fees, slippage_bps=slip, policy=policy,
                                lookback=args.lookback, atr_period=args.atr_period)
            report["provenance"] = provenance
            events = ledger.events()
        _save_new(output / "events.jsonl", b"".join(
            (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode() for event in events))
        _save_new(output / "report.md", _markdown(report).encode())
        # The completion artifact is intentionally last. No resumption or promotion.
        _save_new(output / "result.json", _bytes(report))
        print(f"Completed offline replay: {output / 'report.md'}")
        print(f"Input kind: {capture.manifest['provenance']['kind']}; no live execution exists.")
        return 0
    except Exception as exc:
        if output is not None:
            try:
                _save_new(output / "failure.json", _bytes({"status": "INCOMPLETE", "error_type": type(exc).__name__,
                                                          "message": str(exc)}))
            except OSError:
                pass
        print(f"Offline replay refused or incomplete: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
