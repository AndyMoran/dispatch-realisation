"""Reduce NESO 1-second system frequency to Dynamic Containment energy per period.

The frequency-response battery of the known-answer suite (PREREGISTRATION §8)
cycles within each settlement period as Dynamic Containment would ask. The raw
files are too large to commit, so this module turns them into one small file the
suite reads in CI: for each settlement period, the energy DC would export and
import per contracted MW, kept separate because netting hides exactly that two-way
flow (ASSUMPTIONS P7).

Every reading rule is fixed in config/synthetic.toml [frequency] before any file is
read (PROJECT.md §11, 18 Nov 2026):

- Timestamps are GMT. Each UTC day has 86,400 one-second slots.
- A missing slot is a second with no row, or with a value that is blank, not a
  number, or outside the valid range.
- A run of missing slots no longer than hold_max_gap_s, after a valid second, holds
  that second's value. A longer run, or one at the very start, gives no response.
- Exact duplicate rows are dropped and counted. Duplicates that differ stop the
  reduction.
- A header other than the expected one, a row without two fields, or a timestamp
  that is not a whole second in GMT also stops it.

Delivered response is idealised: exactly what the curve asks for, second by second
(ASSUMPTIONS P8).

Usage:
    uv run python -m src.synthetic.frequency fetch    # download, hash, manifest
    uv run python -m src.synthetic.frequency reduce   # derived file and summary
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import requests
from numpy.typing import NDArray

from src.synthetic.settings import (
    SYNTHETIC_TOML,
    FrequencySettings,
    ResponseCurve,
    load_synthetic_settings,
)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "frequency"
MANIFEST = ROOT / "data" / "manifests" / "frequency_manifest.csv"
MANIFEST_COLUMNS = (
    "schema_version",
    "url",
    "utc_downloaded",
    "sha256",
    "rows",
    "raw_file",
)
MANIFEST_SCHEMA = "1.0"
SUMMARY_SCHEMA = "1.0"
PERIOD_S = 1800
SECONDS_PER_HOUR = 3600.0
# CODING.md §5: four attempts, waits of 2, 4 and 8 s, 60 s timeout each.
RETRY_WAITS_S = (2.0, 4.0, 8.0)
TIMEOUT_S = 60.0
CHUNK_BYTES = 1 << 20
DERIVED_COLUMNS = (
    "period_start_utc",
    "export_mwh_per_mw",
    "import_mwh_per_mw",
    "held_s",
    "zeroed_s",
)

log = logging.getLogger(__name__)


class FrequencyFormatError(ValueError):
    """A frequency file breaks a reading rule: header, row shape or timestamp."""


class ConflictingDuplicate(ValueError):
    """Two rows give the same second different values."""


class ManifestMismatch(ValueError):
    """A raw file is missing from the manifest or its hash differs."""


class FetchFailed(RuntimeError):
    """A download still failed after every permitted attempt."""


@dataclass(frozen=True)
class Readings:
    """One file's rows: seconds since the epoch (UTC), the value text, the value."""

    seconds: NDArray[np.int64]
    text: NDArray[np.str_]
    hz: NDArray[np.float64]


@dataclass(frozen=True)
class Grid:
    """Frequency on every second of the span, after the gap rules.

    `hz` holds NaN where a slot gives no response. `valid_per_day` counts slots with a
    valid reading before the gap rules. Counts are over the span only.
    """

    hz: NDArray[np.float64]
    held: NDArray[np.bool_]
    zeroed: NDArray[np.bool_]
    valid_per_day: tuple[int, ...]
    rows_outside_span: int
    duplicates_dropped: int
    invalid_values: int


# ------------------------------------------------------------------ curve


def response_share(
    hz: NDArray[np.float64], curve: ResponseCurve
) -> NDArray[np.float64]:
    """Return the DC response requested, as a share of contracted MW, per sample.

    Service Terms v6, Schedule 2: none within the deadband; linear to knee_share at
    the knee; linear to 1 at full delivery; 1 beyond. Positive is export, requested
    when frequency is below nominal. NaN (a zeroed slot) requests nothing.
    """
    deviation = curve.nominal_hz - hz
    size = np.abs(np.nan_to_num(deviation, nan=0.0))
    lower = (
        curve.knee_share
        * (size - curve.deadband_hz)
        / (curve.knee_hz - curve.deadband_hz)
    )
    upper = curve.knee_share + (1.0 - curve.knee_share) * (size - curve.knee_hz) / (
        curve.full_hz - curve.knee_hz
    )
    share = np.where(
        size <= curve.deadband_hz,
        0.0,
        np.where(
            size <= curve.knee_hz, lower, np.where(size <= curve.full_hz, upper, 1.0)
        ),
    )
    signed: NDArray[np.float64] = np.sign(np.nan_to_num(deviation, nan=0.0)) * share
    return signed


# ------------------------------------------------------------------ reading


def parse_timestamps(texts: Sequence[str]) -> NDArray[np.int64]:
    """Return whole seconds since the epoch for GMT timestamps; stop on any other.

    Accepted: "YYYY-MM-DD HH:MM:SS" or with "T", an optional all-zero fraction, and
    an optional "Z" or "+00:00". Anything else breaks the GMT whole-second rule.
    """
    cleaned = []
    for text in texts:
        t = text.strip().replace("T", " ")
        for suffix in ("Z", "+00:00"):
            t = t.removesuffix(suffix)
        stamp, dot, fraction = t.partition(".")
        if dot and (not fraction.isdigit() or fraction.strip("0")):
            raise FrequencyFormatError(f"not a whole second in GMT: {text!r}")
        if len(stamp) != 19 or stamp[10] != " ":
            raise FrequencyFormatError(f"timestamp not YYYY-MM-DD HH:MM:SS: {text!r}")
        cleaned.append(stamp.replace(" ", "T"))
    try:
        stamps = np.array(cleaned, dtype="datetime64[s]")
    except ValueError as err:
        raise FrequencyFormatError(f"unreadable timestamp: {err}") from err
    return stamps.astype(np.int64)


def parse_value(text: str) -> float:
    """Return a frequency in Hz, or NaN for a blank or non-numeric value."""
    try:
        return float(text)
    except ValueError:
        return float("nan")


def read_rows(lines: Iterable[str], header: tuple[str, str], name: str) -> Readings:
    """Return a frequency file's rows; stop on a wrong header or a malformed row."""
    reader = csv.reader(lines)
    first = next(reader, None)
    if first is None or tuple(c.strip() for c in first) != header:
        raise FrequencyFormatError(f"{name}: header {first!r}, expected {list(header)}")
    stamps: list[str] = []
    texts: list[str] = []
    for line_no, row in enumerate(reader, start=2):
        if len(row) != 2:
            raise FrequencyFormatError(f"{name} line {line_no}: {len(row)} fields")
        stamps.append(row[0])
        texts.append(row[1].strip())
    return Readings(
        seconds=parse_timestamps(stamps),
        text=np.array(texts, dtype=np.str_),
        hz=np.array([parse_value(t) for t in texts], dtype=np.float64),
    )


# ------------------------------------------------------------------ grid


def build_grid(readings: Sequence[Readings], fs: FrequencySettings) -> Grid:
    """Place every row on the span's one-second grid and apply the gap rules."""
    start_s = int(fs.start.timestamp())
    n = fs.days * fs.slots_per_day
    seconds = np.concatenate([r.seconds for r in readings]) - start_s
    text = np.concatenate([r.text for r in readings])
    hz = np.concatenate([r.hz for r in readings])
    inside = (seconds >= 0) & (seconds < n)
    outside = int(np.count_nonzero(~inside))
    seconds, text, hz = seconds[inside], text[inside], hz[inside]
    order = np.argsort(seconds, kind="stable")
    seconds, text, hz = seconds[order], text[order], hz[order]
    repeat = np.flatnonzero(seconds[1:] == seconds[:-1]) + 1
    differ = repeat[text[repeat] != text[repeat - 1]]
    if differ.size:
        when = datetime.fromtimestamp(start_s + int(seconds[differ[0]]), tz=UTC)
        raise ConflictingDuplicate(f"{when:%Y-%m-%d %H:%M:%S} GMT has differing rows")
    keep = np.ones(seconds.size, dtype=bool)
    keep[repeat] = False
    seconds, hz = seconds[keep], hz[keep]
    low, high = fs.valid_hz
    valid_row = np.isfinite(hz) & (hz >= low) & (hz <= high)
    grid = np.full(n, np.nan)
    grid[seconds[valid_row]] = hz[valid_row]
    held = hold_mask(~np.isnan(grid), fs.hold_max_gap_s)
    filled = grid.copy()
    last_valid = np.maximum.accumulate(np.where(~np.isnan(grid), np.arange(n), 0))
    filled[held] = grid[last_valid[held]]
    per_day = (~np.isnan(grid)).reshape(fs.days, fs.slots_per_day).sum(axis=1)
    return Grid(
        hz=filled,
        held=held,
        zeroed=np.isnan(filled),
        valid_per_day=tuple(int(x) for x in per_day),
        rows_outside_span=outside,
        duplicates_dropped=int(repeat.size),
        invalid_values=int(np.count_nonzero(~valid_row)),
    )


def hold_mask(valid: NDArray[np.bool_], max_gap_s: int) -> NDArray[np.bool_]:
    """Return the missing slots that hold the last valid value.

    A run of missing slots qualifies if it is at most max_gap_s long and follows a
    valid slot; a run at the very start has nothing to hold.
    """
    missing = ~valid
    if not missing.any():
        return np.zeros(valid.size, dtype=bool)
    before = np.concatenate(([False], missing[:-1]))
    after = np.concatenate((missing[1:], [False]))
    starts = np.flatnonzero(missing & ~before)
    ends = np.flatnonzero(missing & ~after) + 1
    lengths = ends - starts
    qualifies = (lengths <= max_gap_s) & (starts > 0)
    held = np.zeros(valid.size, dtype=bool)
    held[missing] = np.repeat(qualifies, lengths)
    return held


# ------------------------------------------------------------------ periods


@dataclass(frozen=True)
class PeriodEnergy:
    """DC energy per contracted MW for each settlement period, by direction."""

    period_start: tuple[datetime, ...]
    export_mwh_per_mw: NDArray[np.float64]
    import_mwh_per_mw: NDArray[np.float64]
    held_s: NDArray[np.int64]
    zeroed_s: NDArray[np.int64]


def period_energy(grid: Grid, curve: ResponseCurve, start: datetime) -> PeriodEnergy:
    """Return each period's export and import energy per MW of DC, kept separate.

    One second at share s delivers s × 1 MW × 1/3600 h = s/3600 MWh per MW.
    """
    if grid.hz.size % PERIOD_S:
        raise ValueError("the grid does not hold whole settlement periods")
    share = response_share(grid.hz, curve).reshape(-1, PERIOD_S)
    periods = share.shape[0]
    return PeriodEnergy(
        period_start=tuple(
            start + timedelta(seconds=PERIOD_S * i) for i in range(periods)
        ),
        export_mwh_per_mw=np.clip(share, 0.0, None).sum(axis=1) / SECONDS_PER_HOUR,
        import_mwh_per_mw=np.clip(-share, 0.0, None).sum(axis=1) / SECONDS_PER_HOUR,
        held_s=grid.held.reshape(-1, PERIOD_S).sum(axis=1).astype(np.int64),
        zeroed_s=grid.zeroed.reshape(-1, PERIOD_S).sum(axis=1).astype(np.int64),
    )


def derived_csv(energy: PeriodEnergy) -> str:
    """Return the derived file's text, with fixed columns and number format."""
    lines = [",".join(DERIVED_COLUMNS)]
    for i, when in enumerate(energy.period_start):
        lines.append(
            f"{when:%Y-%m-%dT%H:%M:%SZ},{energy.export_mwh_per_mw[i]:.9f},"
            f"{energy.import_mwh_per_mw[i]:.9f},{energy.held_s[i]},{energy.zeroed_s[i]}"
        )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ files


def sha256_file(path: Path) -> str:
    """Return a file's SHA-256 in hex."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path: Path, text: str) -> None:
    """Write text through a temporary file in the same folder, then rename it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def manifest_rows(manifest: Path) -> list[dict[str, str]]:
    """Return the manifest's rows, or none if it does not exist yet."""
    if not manifest.exists():
        return []
    with manifest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MANIFEST_COLUMNS:
            raise ManifestMismatch(f"{manifest.name}: unexpected columns")
        return list(reader)


def pinned_file(
    url: str, rows: Sequence[dict[str, str]], root: Path
) -> tuple[Path, str]:
    """Return the latest raw file recorded for a URL, after checking its hash."""
    matches = [r for r in rows if r["url"] == url]
    if not matches:
        raise ManifestMismatch(f"no manifest row for {url}")
    row = max(matches, key=lambda r: r["utc_downloaded"])
    path = root / row["raw_file"]
    if not path.exists():
        raise ManifestMismatch(f"{row['raw_file']} is in the manifest but missing")
    actual = sha256_file(path)
    if actual != row["sha256"]:
        raise ManifestMismatch(f"{row['raw_file']}: SHA-256 {actual} ≠ manifest")
    return path, actual


def download(url: str, dest: Path) -> int:
    """Download url to dest atomically; return its row count, header excluded.

    CODING.md §5: at most four attempts; retries only on timeouts, connection
    errors, HTTP 429 and 5xx.
    """
    for attempt, wait_s in enumerate((*RETRY_WAITS_S, None), start=1):
        try:
            response = requests.get(url, stream=True, timeout=TIMEOUT_S)
        except (requests.Timeout, requests.ConnectionError) as err:
            reason = type(err).__name__
        else:
            if response.status_code == 200:
                return _save(response, dest)
            if response.status_code != 429 and response.status_code < 500:
                raise FetchFailed(f"{url}: HTTP {response.status_code}")
            reason = f"HTTP {response.status_code}"
        log.warning("attempt %d for %s failed: %s", attempt, url, reason)
        if wait_s is None:
            raise FetchFailed(f"{url}: {reason} after {attempt} attempts")
        time.sleep(wait_s)
    raise FetchFailed(url)  # unreachable: the loop returns or raises


def _save(response: requests.Response, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            for chunk in response.iter_content(CHUNK_BYTES):
                handle.write(chunk)
        with open(tmp, encoding="utf-8", newline="") as handle:
            first = handle.readline()
            rows = sum(1 for _ in handle)
        if len(next(csv.reader([first]), [])) != 2 or rows == 0:
            raise FrequencyFormatError(f"{dest.name}: not a two-column file with rows")
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return rows


def fetch(fs: FrequencySettings, root: Path = ROOT, manifest: Path = MANIFEST) -> None:
    """Download each configured file not already pinned, recording a manifest row.

    A file already in the manifest is reused only if its hash still matches; a
    mismatch raises rather than downloading again (CODING.md §5).
    """
    rows = manifest_rows(manifest)
    todo = [
        (f, u)
        for f, u in zip(fs.files, fs.urls, strict=True)
        if not any(r["url"] == u for r in rows)
    ]
    for _, url in zip(fs.files, fs.urls, strict=True):
        if any(r["url"] == url for r in rows):
            _ = pinned_file(url, rows, root)
    log.info(
        "fetching %d of %d monthly files (about 2.6 million rows each)",
        len(todo),
        len(fs.files),
    )
    for name, url in todo:
        stamp = datetime.now(tz=UTC)
        dest = (
            root
            / "data"
            / "raw"
            / "frequency"
            / (f"{Path(name).stem}__dl{stamp:%Y%m%dT%H%M%S}.csv")
        )
        count = download(url, dest)
        row = {
            "schema_version": MANIFEST_SCHEMA,
            "url": url,
            "utc_downloaded": stamp.isoformat(),
            "sha256": sha256_file(dest),
            "rows": str(count),
            "raw_file": dest.relative_to(root).as_posix(),
        }
        _append_manifest(manifest, row)
        log.info(
            "%s: %d rows to %s at %s",
            url,
            count,
            row["raw_file"],
            row["utc_downloaded"],
        )


def _append_manifest(manifest: Path, row: dict[str, str]) -> None:
    rows = manifest_rows(manifest) + [row]
    lines = [",".join(MANIFEST_COLUMNS)]
    lines += [",".join(r[c] for c in MANIFEST_COLUMNS) for r in rows]
    write_atomic(manifest, "\n".join(lines) + "\n")


def reduce(
    fs: FrequencySettings,
    curve: ResponseCurve,
    root: Path = ROOT,
    manifest: Path = MANIFEST,
    settings_path: Path = SYNTHETIC_TOML,
) -> dict[str, object]:
    """Write the derived file, then the summary; return the summary.

    Raw files are read only after their hashes match the manifest. The summary is
    written last, so a derived file without one is incomplete.
    """
    rows = manifest_rows(manifest)
    sources = [pinned_file(url, rows, root) for url in fs.urls]
    readings = []
    for (path, _), name in zip(sources, fs.files, strict=True):
        with path.open(encoding="utf-8", newline="") as handle:
            readings.append(read_rows(handle, fs.header, name))
    grid = build_grid(readings, fs)
    energy = period_energy(grid, curve, fs.start)
    derived = root / fs.derived_file
    write_atomic(derived, derived_csv(energy))
    short_days = {
        (fs.first_day + timedelta(days=i)).isoformat(): fs.slots_per_day - valid
        for i, valid in enumerate(grid.valid_per_day)
        if valid < fs.slots_per_day
    }
    summary: dict[str, object] = {
        "schema_version": SUMMARY_SCHEMA,
        "sources": [
            {
                "file": name,
                "url": url,
                "sha256": digest,
                "raw_file": path.relative_to(root).as_posix(),
            }
            for name, url, (path, digest) in zip(
                fs.files, fs.urls, sources, strict=True
            )
        ],
        "script_sha256": sha256_file(Path(__file__)),
        "settings_sha256": sha256_file(settings_path),
        "curve_source": curve.source,
        "span_utc": [fs.first_day.isoformat(), fs.last_day.isoformat()],
        "periods": len(energy.period_start),
        "slots": int(grid.hz.size),
        "rows_outside_span": grid.rows_outside_span,
        "duplicates_dropped": grid.duplicates_dropped,
        "invalid_values": grid.invalid_values,
        "held_slots": int(np.count_nonzero(grid.held)),
        "zeroed_slots": int(np.count_nonzero(grid.zeroed)),
        "missing_slots_by_day": short_days,
        "derived_file": fs.derived_file,
        "derived_sha256": sha256_file(derived),
    }
    write_atomic(
        root / fs.summary_file, json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> None:
    """Run `fetch` or `reduce` with the settings in config/synthetic.toml."""
    parser = argparse.ArgumentParser(description="DC energy per period from frequency")
    parser.add_argument("step", choices=("fetch", "reduce"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    settings = load_synthetic_settings()
    if args.step == "fetch":
        fetch(settings.frequency)
    else:
        summary = reduce(settings.frequency, settings.response)
        log.info(
            "derived %s: %s periods, %s held and %s zeroed slots",
            summary["derived_file"],
            summary["periods"],
            summary["held_slots"],
            summary["zeroed_slots"],
        )


if __name__ == "__main__":
    main()
