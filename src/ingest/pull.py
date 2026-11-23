"""Scoring-window pulls: one module, one subcommand per source (PROJECT.md §11).

Design fixed in the decision log on 23 Nov 2026 before any of this ran:

- Every chunk is one settlement date, periods 1 to 50, so chunks neither overlap
  nor leave a gap, whichever way an endpoint treats the ends of a time range.
- Each response is saved as downloaded to `data/raw/pull/<dataset>/` and gets one
  manifest row (`data/manifests/pull_manifest.csv`): dataset, URL and parameters
  without the unit list, the number of units and a SHA-256 of their sorted IDs,
  UTC download time, SHA-256 of the response, row count and file (DATA_SOURCES.md,
  vintage policy). The fleet's unit IDs stay off the committed manifest, as the
  Gate A1 adoption table does.
- Nothing prints a data value. Probes print field names, JSON types, counts and
  the settlement dates and periods returned. No fleet unit is scored before the
  pinned scoring run.

This file holds the shared pieces and the probe. The pulls proper follow once
the probe's output has fixed the field mapping.

    uv run python -m src.ingest.pull probe
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]
ELEXON = "https://data.elexon.co.uk/bmrs/api/v1"
NESO = "https://api.neso.energy/api/3/action"
RAW = ROOT / "data" / "raw" / "pull"
MANIFEST = ROOT / "data" / "manifests" / "pull_manifest.csv"
FLEET_CSV = ROOT / "outputs" / "gate_a1" / "adoption_dates.csv"
PROBE_OUT = ROOT / "outputs" / "pull" / "probe.json"
FLEET_SIZE = 163  # PREREGISTRATION §2: the Gate A1 run of 30 Oct 2026
PROBE_DATES = (date(2026, 10, 14), date(2026, 10, 15))
PROBE_UNITS = 3
RETRY_WAIT_S = 5.0
NESO_DEMAND = "historic-demand-data"
MANIFEST_FIELDS = (
    "schema_version",
    "dataset",
    "url",
    "params",
    "units",
    "units_sha256",
    "utc_downloaded",
    "sha256",
    "rows",
    "raw_file",
)

Getter = Callable[[str], bytes]


class PullError(RuntimeError):
    """Stops a pull, rather than guessing (PIPELINE_RULES §1–2)."""


# ------------------------------------------------------------------ requests


@dataclass(frozen=True)
class Request:
    """One request: a dataset, a settlement date and the query it sends."""

    dataset: str
    settlement_date: date
    path: str
    params: tuple[tuple[str, str], ...]
    units: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        """Return the full URL sent: parameters, then one `bmUnit` per unit."""
        query = [*self.params, *(("bmUnit", u) for u in self.units)]
        return f"{ELEXON}{self.path}?{urllib.parse.urlencode(query)}"

    @property
    def public_url(self) -> str:
        """Return the URL without the unit list, for the committed manifest."""
        return f"{ELEXON}{self.path}?{urllib.parse.urlencode(self.params)}"

    @property
    def units_sha256(self) -> str:
        """Return a SHA-256 of the sorted unit IDs, joined by newlines."""
        return hashlib.sha256("\n".join(self.units).encode()).hexdigest()


STREAM = {
    "MDO": "/datasets/MDO/stream",
    "MDB": "/datasets/MDB/stream",
    "PN": "/datasets/PN/stream",
    "BOALF": "/datasets/BOALF/stream",
}


def stream_request(dataset: str, day: date, units: Sequence[str]) -> Request:
    """Return one settlement date, periods 1–50, for `units` (MDO, MDB, PN, BOALF)."""
    if dataset not in STREAM:
        raise PullError(f"not a stream dataset: {dataset}")
    d = day.isoformat()
    params = [
        ("from", d),
        ("to", d),
        ("settlementPeriodFrom", "1"),
        ("settlementPeriodTo", "50"),
    ]
    return Request(dataset, day, STREAM[dataset], tuple(params), tuple(sorted(units)))


def b1610_request(day: date, units: Sequence[str]) -> Request:
    """Return one settlement date of B1610, every settlement run type (M6)."""
    d = day.isoformat()
    params = (("settlementDateFrom", d), ("settlementDateTo", d))
    return Request("B1610", day, "/datasets/B1610/stream", params, tuple(sorted(units)))


def boav_request(day: date, bid_offer: str) -> Request:
    """Return one settlement date of settlement acceptance volumes, all units (R15)."""
    if bid_offer not in ("bid", "offer"):
        raise PullError(f"bidOffer must be bid or offer: {bid_offer}")
    path = f"/balancing/settlement/acceptance/volumes/all/{bid_offer}/{day.isoformat()}"
    return Request(f"BOAV_{bid_offer}", day, path, ())


def settlement_dates(first: date, last: date) -> list[date]:
    """Return every settlement date from `first` to `last`, both included."""
    if last < first:
        raise PullError("window ends before it starts")
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


# ------------------------------------------------------------------ fetch and save


def http_get(url: str, timeout: float = 120.0) -> bytes:
    """Return the body of a GET request; raise on any non-200 status."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.status
        body: bytes = resp.read()
    if status != 200:
        raise PullError(f"HTTP {status}: {url}")
    return body


def get_with_retry(get: Getter, url: str, tries: int = 3, wait_s: float = 5.0) -> bytes:
    """Return `get(url)`, retrying a failure up to `tries` times in all."""
    pause = RETRY_WAIT_S if wait_s is None else wait_s
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return get(url)
        except Exception as exc:  # every failure is retried, then raised
            last = exc
            if attempt + 1 < tries:
                time.sleep(pause * (attempt + 1))
    raise PullError(f"failed after {tries} tries: {url}: {last}")


def rows_of(body: bytes) -> list[dict[str, object]]:
    """Return the rows of a JSON response: a list, or a `data` list in a wrapper."""
    parsed = json.loads(body)
    rows = parsed.get("data") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise PullError("response is not a list of rows")
    return rows


def save(
    request: Request,
    body: bytes,
    downloaded: datetime,
    raw_root: Path = RAW,
    manifest: Path = MANIFEST,
) -> dict[str, str]:
    """Save a response as downloaded and append its manifest row; return the row."""
    stamp = downloaded.strftime("%Y%m%dT%H%M%S%f")
    digest = hashlib.sha256(body).hexdigest()
    folder = raw_root / request.dataset
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{request.settlement_date.isoformat()}__{digest[:12]}__dl{stamp}.json"
    path = folder / name
    path.write_bytes(body)
    row = {
        "schema_version": SCHEMA_VERSION,
        "dataset": request.dataset,
        "url": request.public_url,
        "params": json.dumps(list(request.params)),
        "units": str(len(request.units)),
        "units_sha256": request.units_sha256 if request.units else "",
        "utc_downloaded": downloaded.isoformat(),
        "sha256": digest,
        "rows": str(len(rows_of(body))),
        "raw_file": str(path.relative_to(raw_root.parents[2])),
    }
    new = not manifest.exists()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


# ------------------------------------------------------------------ the fleet


def load_fleet(path: Path = FLEET_CSV, expected: int = FLEET_SIZE) -> list[str]:
    """Return the fleet's unit IDs, sorted, from Gate A1's adoption table.

    The fleet is every unit with status "adopted" (PREREGISTRATION §2). The table
    holds unit IDs, so it stays on the machine that ran Gate A1.
    """
    if not path.exists():
        raise PullError(f"no fleet table at {path}; it comes from Gate A1's run")
    with path.open(newline="", encoding="utf-8") as f:
        units = sorted(r["unit"] for r in csv.DictReader(f) if r["status"] == "adopted")
    if len(units) != expected:
        raise PullError(f"fleet has {len(units)} units, not the locked {expected}")
    return units


# ------------------------------------------------------------------ the probe


def json_type(value: object) -> str:
    """Return a value's JSON type name, never the value itself."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def schema(rows: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    """Return each field's JSON types across rows, sorted: names and types only."""
    out: dict[str, set[str]] = {}
    for r in rows:
        for k, v in r.items():
            out.setdefault(k, set()).add(json_type(v))
    return {k: sorted(v) for k, v in sorted(out.items())}


def dates_and_periods(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Return the settlement dates and the period range the rows cover."""
    dates = sorted({str(r["settlementDate"]) for r in rows if "settlementDate" in r})
    periods: set[int] = set()
    for key in ("settlementPeriod", "settlementPeriodFrom", "settlementPeriodTo"):
        for r in rows:
            v = r.get(key)
            if isinstance(v, int) and not isinstance(v, bool):
                periods.add(v)
    return {
        "settlement_dates": dates,
        "period_min": min(periods) if periods else None,
        "period_max": max(periods) if periods else None,
    }


def overlap(
    a: Sequence[Mapping[str, object]], b: Sequence[Mapping[str, object]]
) -> int:
    """Return how many rows appear, identically, in both responses."""
    keys = {json.dumps(r, sort_keys=True) for r in a}
    return sum(1 for r in b if json.dumps(r, sort_keys=True) in keys)


def probe_endpoint(
    make: Callable[[date], Request],
    get: Getter,
    now: Callable[[], datetime],
    raw_root: Path = RAW,
    manifest: Path = MANIFEST,
) -> dict[str, object]:
    """Request two adjacent settlement dates; report schema, coverage and overlap."""
    report: dict[str, object] = {}
    rows_by_day: list[list[dict[str, object]]] = []
    for day in PROBE_DATES:
        request = make(day)
        try:
            body = get_with_retry(get, request.url)
        except PullError as exc:
            report[day.isoformat()] = {"error": str(exc).split(":", 1)[0]}
            rows_by_day.append([])
            continue
        save(request, body, now(), raw_root, manifest)
        rows = rows_of(body)
        rows_by_day.append(rows)
        report[day.isoformat()] = {
            "rows": len(rows),
            "fields": schema(rows),
            **dates_and_periods(rows),
        }
    report["rows_in_both_days"] = overlap(rows_by_day[0], rows_by_day[1])
    return report


def neso_demand_schema(get: Getter) -> dict[str, object]:
    """Return the field names and types of NESO's historic demand data, by year.

    Schema discovery only (decision log, 23 Nov 2026): no row is read.
    """
    meta = json.loads(get_with_retry(get, f"{NESO}/package_show?id={NESO_DEMAND}"))
    resources = meta.get("result", {}).get("resources", [])
    out: dict[str, object] = {}
    for r in resources:
        name = str(r.get("name", ""))
        if "2026" not in name:
            continue
        q = urllib.parse.urlencode({"resource_id": r["id"], "limit": 0})
        body = json.loads(get_with_retry(get, f"{NESO}/datastore_search?{q}"))
        fields = body.get("result", {}).get("fields", [])
        out[name] = {
            "resource_id": r["id"],
            "fields": {str(f["id"]): str(f.get("type", "")) for f in fields},
        }
    if not out:
        raise PullError("no 2026 resource in NESO's historic demand data")
    return out


def _stream_for(dataset: str, units: Sequence[str], day: date) -> Request:
    return stream_request(dataset, day, units)


def _b1610_for(units: Sequence[str], day: date) -> Request:
    return b1610_request(day, units)


def _boav_for(side: str, day: date) -> Request:
    return boav_request(day, side)


def probe(
    get: Getter = http_get,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    fleet: Sequence[str] | None = None,
    raw_root: Path = RAW,
    manifest: Path = MANIFEST,
) -> dict[str, object]:
    """Probe every source the pulls will use; return names, types and counts."""
    units = list(fleet) if fleet is not None else load_fleet()
    sample = sorted(units)[:PROBE_UNITS]
    out: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "probe_dates": [d.isoformat() for d in PROBE_DATES],
        "units_sampled": len(sample),
        "endpoints": {},
    }
    endpoints: dict[str, dict[str, object]] = {}
    for dataset in STREAM:
        endpoints[dataset] = probe_endpoint(
            partial(_stream_for, dataset, sample), get, now, raw_root, manifest
        )
    endpoints["B1610"] = probe_endpoint(
        partial(_b1610_for, sample), get, now, raw_root, manifest
    )
    for side in ("bid", "offer"):
        endpoints[f"BOAV_{side}"] = probe_endpoint(
            partial(_boav_for, side), get, now, raw_root, manifest
        )
    out["endpoints"] = endpoints
    out["neso_historic_demand"] = neso_demand_schema(get)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Run a subcommand. Only the probe exists until its output fixes the mapping."""
    parser = argparse.ArgumentParser(description="Scoring-window pulls")
    parser.add_argument("command", choices=("probe",))
    args = parser.parse_args(argv)
    if args.command == "probe":
        result = probe()
        PROBE_OUT.parent.mkdir(parents=True, exist_ok=True)
        PROBE_OUT.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
