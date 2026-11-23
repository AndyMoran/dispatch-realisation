"""M23 sign check and M25 run-code check, before any fleet B1610 is pulled.

ASSUMPTIONS M23 fixes the check: every fuel-type `PS` unit in the pinned
reference snapshot (outside the fleet, M10); October 2026 settlement periods with
an SF run in which (a) the unit's own PN is negative throughout and (b) NESO's
historic demand data shows pumped-storage pumping above zero. B1610 negative in
every selected period: the sign is as the code reads it. Positive in every one:
the sign is reversed. Mixed, or no period selected: stop before any unit is
scored. A selected period whose SF value is exactly zero is neither, so it makes
the result mixed.

M25: the run codes in this pull are listed; any code other than the six "SF or
later" codes of `config/scoring.toml` and II stops the run.

Readings of 23 Nov 2026 (decision log): NESO's `FORECAST_ACTUAL_INDICATOR` must
take exactly the labels A and F across the 2026 resource, A read as actual; only
A rows are used, and any other label set stops the check. Output is counts and
run-code labels only; no value and no unit ID.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.claims.results import load_scoring_settings
from src.ingest import pull
from src.ingest.gate_a1 import load_reference_fuel
from src.ingest.parse import parse_meter, parse_segments
from src.ingest.pull import Getter, PullError, Request
from src.model.types import LevelSegment, MeterPeriod

LONDON = ZoneInfo("Europe/London")
PERIOD = timedelta(minutes=30)
II = "II"
ACTUAL, FORECAST = "A", "F"
SF = "SF"
PUMPED_STORAGE = "PS"
CHECK_DAYS = (date(2026, 10, 1), date(2026, 10, 31))  # settlement dates, inclusive
NESO_RESOURCE = "8a4a771c-3929-4e56-93ad-cdf13219dea5"  # historic demand 2026
NESO_LIMIT = 32000  # above a year of half-hours; the response's total is checked
OUT = pull.ROOT / "outputs" / "pull" / "b1610_check.json"


class CheckStopped(RuntimeError):
    """The check cannot reach a verdict; nothing downstream may run."""


def period_start(day: date, period: int) -> datetime:
    """Return the UTC start of a settlement period: local midnight plus periods.

    Counting from local midnight in UTC handles both clock-change days (46 and 50
    periods).
    """
    if not 1 <= period <= 50:
        raise ValueError(f"settlement period outside 1–50: {period}")
    midnight = datetime.combine(day, time(0), tzinfo=LONDON).astimezone(UTC)
    return midnight + (period - 1) * PERIOD


def periods_in(day: date) -> int:
    """Return how many settlement periods a day has: 46, 48 or 50."""
    nxt = datetime.combine(day + timedelta(days=1), time(0), tzinfo=LONDON)
    return round((nxt.astimezone(UTC) - period_start(day, 1)) / PERIOD)


def pn_negative_throughout(segments: Sequence[LevelSegment], start: datetime) -> bool:
    """Return whether PN covers the whole period and is below zero throughout."""
    end = start + PERIOD
    inside = sorted(
        (s for s in segments if s.time_from < end and s.time_to > start),
        key=lambda s: s.time_from,
    )
    if not inside or inside[0].time_from > start:
        return False
    reached = start
    for s in inside:
        if s.time_from > reached:
            return False  # a gap in PN
        if not (s.level_from_mw < 0 and s.level_to_mw < 0):
            return False
        reached = max(reached, s.time_to)
    return reached >= end


def check_labels(labels: Iterable[str]) -> None:
    """Stop unless the indicator's labels are exactly actual and forecast."""
    found = set(labels)
    if found != {ACTUAL, FORECAST}:
        raise CheckStopped(f"indicator labels are {sorted(found)}, not A and F")


def pumping_periods(rows: Iterable[Mapping[str, object]]) -> set[datetime]:
    """Return the UTC starts of actual periods with pumping above zero."""
    out: set[datetime] = set()
    for r in rows:
        if r.get("FORECAST_ACTUAL_INDICATOR") != ACTUAL:
            continue
        pumping = r.get("PUMP_STORAGE_PUMPING")
        if isinstance(pumping, bool) or not isinstance(pumping, int | float):
            raise CheckStopped("PUMP_STORAGE_PUMPING missing or not a number")
        if pumping > 0:
            day = date.fromisoformat(str(r["SETTLEMENT_DATE"])[:10])
            period = int(str(r["SETTLEMENT_PERIOD"]))
            if not 1 <= period <= periods_in(day):
                raise CheckStopped("a NESO settlement period outside its day")
            out.add(period_start(day, period))
    return out


@dataclass(frozen=True)
class SignResult:
    """The check's counts and verdict: no value, no unit ID."""

    units: int
    sf_periods: int
    selected: int
    negative: int
    positive: int
    zero: int
    verdict: str
    run_codes: dict[str, int]
    unknown_run_codes: list[str]


def run_check(
    sf_values: Mapping[tuple[str, datetime], float],
    pn: Mapping[str, Sequence[LevelSegment]],
    pumping: set[datetime],
    run_codes: Counter[str],
    sf_or_later: Iterable[str],
) -> SignResult:
    """Select periods by M23's rule and return the counts and the verdict.

    `sf_values` holds each PS unit's SF value by (unit, period start). Raises
    `CheckStopped` for an unknown run code (M25), a mixed result or no selection.
    """
    known = set(sf_or_later) | {II}
    unknown = sorted(set(run_codes) - known)
    selected = [
        v
        for (unit, start), v in sorted(sf_values.items())
        if start in pumping and pn_negative_throughout(pn.get(unit, ()), start)
    ]
    neg = sum(1 for v in selected if v < 0)
    pos = sum(1 for v in selected if v > 0)
    zero = len(selected) - neg - pos
    if not selected:
        verdict = "no period selected"
    elif neg == len(selected):
        verdict = "negative: sign as read"
    elif pos == len(selected):
        verdict = "positive: sign reversed"
    else:
        verdict = "mixed"
    return SignResult(
        units=len({u for u, _ in sf_values}),
        sf_periods=len(sf_values),
        selected=len(selected),
        negative=neg,
        positive=pos,
        zero=zero,
        verdict=verdict,
        run_codes=dict(sorted(run_codes.items())),
        unknown_run_codes=unknown,
    )


def stops(result: SignResult) -> str | None:
    """Return why the check stops the pipeline, or None if it reached a verdict."""
    if result.unknown_run_codes:
        return f"unknown run codes: {result.unknown_run_codes} (M25)"
    if result.verdict in ("mixed", "no period selected"):
        return f"sign check {result.verdict} (M23)"
    return None


# ------------------------------------------------------------------ the pull


def ps_units(fuel: Mapping[str, str], fleet: Iterable[str]) -> list[str]:
    """Return the reference snapshot's pumped-storage units, sorted.

    Stops if there are none, or if any is in the fleet (M10 puts them outside it).
    """
    units = sorted(u for u, f in fuel.items() if f == PUMPED_STORAGE)
    if not units:
        raise CheckStopped("no fuel-type PS unit in the reference snapshot")
    if set(units) & set(fleet):
        raise CheckStopped("a PS unit is in the fleet, against M10")
    return units


def neso_request() -> Request:
    """Return the one NESO request: every field of the whole 2026 resource.

    No `fields` filter: NESO's server counts rows by `_id`, so a field list without
    `_id` fails with HTTP 409 (23 Nov 2026). Only the four mapped fields are read.
    """
    params = (
        ("resource_id", NESO_RESOURCE),
        ("limit", str(NESO_LIMIT)),
        ("sort", "_id"),
    )
    return Request(
        "NESO_demand", date(2026, 1, 1), "/datastore_search", params, (), pull.NESO
    )


def check_plan(units: Sequence[str]) -> list[Request]:
    """Return every request of the check, in a fixed order: B1610, PN, NESO."""
    days = pull.settlement_dates(*CHECK_DAYS)
    meter = [pull.b1610_request(d, b) for d in days for b in pull.batches(units)]
    pn = [pull.stream_request("PN", d, b) for d in days for b in pull.batches(units)]
    return [*meter, *pn, neso_request()]


def planned_files(
    requests: Sequence[Request], manifest: Path = pull.MANIFEST, root: Path = pull.ROOT
) -> dict[Request, Path]:
    """Return each request's raw file, from the manifest; stop if one is missing.

    A chunk held twice is read from its latest download (the manifest's last row).
    """
    want = {pull.chunk_key(r): r for r in requests}
    found: dict[Request, Path] = {}
    with manifest.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["dataset"], row["url"], row["units_sha256"])
            if key in want:
                found[want[key]] = root / row["raw_file"]
    missing = len(requests) - len(found)
    if missing:
        raise CheckStopped(f"{missing} planned chunks are not in the manifest")
    return found


def neso_rows(body: bytes) -> list[dict[str, object]]:
    """Return NESO's rows, stopping unless the response holds every row it counts."""
    rows = pull.rows_of(body)
    total = json.loads(body).get("result", {}).get("total")
    if total != len(rows):
        raise CheckStopped(f"NESO returned {len(rows)} rows of {total}")
    return rows


def sf_values(
    meter: Mapping[str, Sequence[MeterPeriod]], starts: set[datetime]
) -> dict[tuple[str, datetime], float]:
    """Return each unit's SF value by period start, for the check's periods.

    Stops if one unit and period has two different SF values.
    """
    out: dict[tuple[str, datetime], float] = {}
    for unit, periods in meter.items():
        for p in periods:
            if p.run_type != SF or p.period_start not in starts:
                continue
            key = (unit, p.period_start)
            if key in out and out[key] != p.net_mwh:
                raise CheckStopped("two different SF values for one unit and period")
            out[key] = p.net_mwh
    return out


def check_starts() -> set[datetime]:
    """Return the UTC start of every settlement period in the check's dates."""
    out: set[datetime] = set()
    for day in pull.settlement_dates(*CHECK_DAYS):
        out.update(period_start(day, k) for k in range(1, periods_in(day) + 1))
    return out


def evaluate(
    files: Mapping[Request, Path], sf_or_later: Iterable[str]
) -> dict[str, object]:
    """Read the check's raw files and return its report: counts and labels only."""
    meter_rows: list[dict[str, object]] = []
    pn_rows: list[dict[str, object]] = []
    neso: list[dict[str, object]] = []
    for request, path in files.items():
        body = path.read_bytes()
        if request.dataset == "B1610":
            meter_rows += pull.rows_of(body)
        elif request.dataset == "PN":
            pn_rows += pull.rows_of(body)
        else:
            neso = neso_rows(body)
    meter = parse_meter(meter_rows)
    pn = parse_segments("PN", pn_rows)
    codes: Counter[str] = Counter(
        p.run_type for ps in meter.by_unit.values() for p in ps
    )
    labels = {str(r.get("FORECAST_ACTUAL_INDICATOR")) for r in neso}
    check_labels(labels)
    october = check_starts()
    pumping = pumping_periods(neso) & october
    result = run_check(
        sf_values(meter.by_unit, october), pn.by_unit, pumping, codes, sf_or_later
    )
    return {
        "schema_version": pull.SCHEMA_VERSION,
        "indicator_labels": sorted(labels),
        "neso_rows": len(neso),
        "neso_pumping_periods_in_window": len(pumping),
        "b1610_rows": len(meter_rows),
        "b1610_excluded": dict(meter.excluded),
        "pn_rows": len(pn_rows),
        "pn_excluded": dict(pn.excluded),
        "result": asdict(result),
        "stops": stops(result),
    }


def main(
    get: Getter = pull.http_get,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    root: Path = pull.ROOT,
    pause_s: float | None = None,
) -> int:
    """Pull what the check needs, run it and write the report; non-zero on a stop."""
    raw_root = root / pull.RAW.relative_to(pull.ROOT)
    manifest = root / pull.MANIFEST.relative_to(pull.ROOT)
    out = root / OUT.relative_to(pull.ROOT)
    fuel, snapshot = load_reference_fuel()
    units = ps_units(fuel, pull.load_fleet())
    requests = check_plan(units)
    coverage = pull.run_requests(
        "b1610-check", requests, get, now, raw_root, manifest, pause_s
    )
    report: dict[str, object] = {
        "coverage": coverage,
        "reference_snapshot": snapshot.name,
        "ps_units": len(units),
    }
    try:
        if not coverage["complete"]:
            raise PullError("the check's pull is incomplete")
        report |= evaluate(
            planned_files(requests, manifest, root),
            load_scoring_settings().sf_or_later_runs,
        )
    except (CheckStopped, PullError) as exc:
        report["stops"] = str(exc)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("stops") is None else 1
