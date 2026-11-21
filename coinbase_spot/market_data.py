"""Strict parsing of local Coinbase-shaped snapshots. This module never fetches data.

A manifest is a provenance declaration and byte-integrity check, not proof that a
file came from Coinbase. Synthetic data must remain explicitly labelled synthetic.
Coverage is [start, end): end is the close time of the final complete candle.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Sequence

from .models import Candle, D, Product, validate_timestamp


@dataclass(frozen=True)
class Capture:
    product: Product
    candles: tuple[Candle, ...]
    manifest: dict
    manifest_sha256: str


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def _read_json(data: bytes) -> object:
    try:
        return json.loads(data.decode("utf-8"), parse_float=Decimal,
                          parse_constant=_reject_constant, object_pairs_hook=_unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid UTF-8 JSON snapshot") from exc


def _epoch(value: object) -> int:
    # Coinbase returns candle starts as decimal strings, never local datetimes.
    if isinstance(value, str):
        if not re.fullmatch(r"0|[1-9][0-9]{0,11}", value):
            raise ValueError("candle start must be whole UTC epoch seconds")
        value = int(value)
    return validate_timestamp(value)


def validate_candles(candles: Sequence[Candle], *, product_id: str | None = None,
                     interval: int | None = None, normalize: bool = False) -> tuple[Candle, ...]:
    """Require one product, one interval, unique starts and contiguous coverage.

    Normalization is allowed only at the external-file boundary. Replay inputs
    must already be chronological; missing candles are never manufactured.
    """
    result = tuple(candles)
    if not result or any(not isinstance(c, Candle) for c in result):
        raise ValueError("a nonempty sequence of validated candles is required")
    if normalize:
        result = tuple(sorted(result, key=lambda c: c.start))
    expected_product = product_id if product_id is not None else result[0].product_id
    expected_interval = interval if interval is not None else result[0].interval
    if type(expected_interval) is not int or expected_interval <= 0:
        raise ValueError("invalid interval")
    for index, candle in enumerate(result):
        if candle.product_id != expected_product or candle.interval != expected_interval:
            raise ValueError("wrong product or mixed candle interval")
        if index and candle.start != result[index - 1].end:
            raise ValueError("duplicate, out-of-order, overlapping or missing candle")
    return result


def parse_coinbase_candles(payload: dict, *, product_id: str, interval: int) -> tuple[Candle, ...]:
    """Parse a saved public candles response, normalizing newest-first responses.

    The public endpoint does not put product identity in every candle. The
    manifest binds that identity; any additional envelope/row identity must agree.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("candles"), list):
        raise ValueError("expected a Coinbase-shaped object with a candles array")
    if "product_id" in payload and payload["product_id"] != product_id:
        raise ValueError("candle envelope product does not match manifest")
    if "interval_seconds" in payload and payload["interval_seconds"] != interval:
        raise ValueError("candle envelope interval does not match manifest")
    candles = []
    for row in payload["candles"]:
        if not isinstance(row, dict):
            raise ValueError("candle records must be objects")
        if "product_id" in row and row["product_id"] != product_id:
            raise ValueError("candle product does not match manifest")
        try:
            candles.append(Candle(product_id=product_id, start=_epoch(row["start"]),
                                  interval=interval,
                                  **{key: D(row[key]) for key in ("open", "high", "low", "close", "volume")}))
        except (KeyError, TypeError) as exc:
            raise ValueError("incomplete candle record") from exc
    return validate_candles(candles, product_id=product_id, interval=interval, normalize=True)


def completed_prefix(candles: Sequence[Candle], decision_time: int) -> tuple[Candle, ...]:
    """Return only consecutive complete bars; never inspect bars beyond the cutoff.

    Input must be chronological, as returned by the capture loader. Incomplete
    bars are excluded even when their start time precedes the decision time.
    """
    validate_timestamp(decision_time)
    result = []
    for candle in candles:
        if not isinstance(candle, Candle):
            raise ValueError("unvalidated candle")
        if candle.end > decision_time:
            break
        if result and (candle.start != result[-1].end or
                       candle.product_id != result[-1].product_id or
                       candle.interval != result[-1].interval):
            raise ValueError("completed prefix is not one contiguous product series")
        result.append(candle)
    return tuple(result)


def _manifest_file(directory: Path, spec: object) -> bytes:
    if not isinstance(spec, dict):
        raise ValueError("manifest file descriptor must be an object")
    name, digest = spec.get("path"), spec.get("sha256")
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("manifest files require relative local paths")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("manifest requires a lowercase SHA256 digest")
    path = (directory / name).resolve()
    if not path.is_relative_to(directory):
        raise ValueError("manifest file escapes its directory")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"SHA256 mismatch for {name}")
    return data


def load_capture(manifest_path: str | Path) -> Capture:
    """Read and validate a local v1 manifest and both exact-byte input hashes."""
    path = Path(manifest_path).resolve()
    manifest_bytes = path.read_bytes()
    manifest = _read_json(manifest_bytes)
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported capture manifest schema")
    product_id = manifest.get("product_id")
    interval = manifest.get("interval_seconds")
    if not isinstance(product_id, str) or type(interval) is not int or interval <= 0:
        raise ValueError("manifest must identify product and whole-second interval")
    coverage = manifest.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("missing explicit coverage")
    start, end = _epoch(coverage.get("start")), _epoch(coverage.get("end"))
    if start >= end or start % interval or end % interval:
        raise ValueError("invalid complete-candle coverage")
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("kind") not in ("synthetic", "recorded"):
        raise ValueError("provenance must explicitly be synthetic or recorded")
    for key in ("source", "description", "captured_at"):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            raise ValueError(f"missing provenance {key}")
    try:
        captured = datetime.fromisoformat(provenance["captured_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("captured_at must be a UTC ISO timestamp") from exc
    if captured.tzinfo is None or captured.utcoffset() != timedelta(0):
        raise ValueError("captured_at must explicitly use UTC")
    if provenance["kind"] == "recorded" and captured.timestamp() < end:
        raise ValueError("recorded capture predates the end of a purported complete candle")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"product", "candles"}:
        raise ValueError("manifest must bind exactly product and candles snapshots")
    product = Product.from_coinbase(_read_json(_manifest_file(path.parent, files["product"])))
    if product.product_id != product_id:
        raise ValueError("product snapshot does not match manifest")
    candles = parse_coinbase_candles(_read_json(_manifest_file(path.parent, files["candles"])),
                                    product_id=product_id, interval=interval)
    if candles[0].start != start or candles[-1].end != end or len(candles) != (end - start) // interval:
        raise ValueError("actual candle coverage does not match manifest")
    return Capture(product=product, candles=candles, manifest=manifest,
                   manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())


def series_digest(candles: Sequence[Candle]) -> str:
    """Hash normalized replay inputs; the capture manifest separately hashes bytes."""
    rows = [{"product_id": c.product_id, "start": c.start, "interval": c.interval,
             **{key: str(getattr(c, key)) for key in ("open", "high", "low", "close", "volume")}}
            for c in candles]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
