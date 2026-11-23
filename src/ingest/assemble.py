"""Each fleet unit's inputs for the pinned scoring run, and a counts-only check.

Design fixed in the decision log on 23 Nov 2026 (`v1.0.6-lock`), before this code:

- MDO and MDB: Gate A1's official run of 30 Oct 2026 (UTC days 25 Jun – 29 Oct,
  one file per dataset and day, from `data/manifests/gate_a1_manifest.csv`) and
  the `mdo-mdb` pull (30 Oct – 16 Nov). The two meet at 30 Oct 00:00 UTC, which
  both include, so records that appear in both are removed as exact duplicates.
- PN, BOALF and B1610: the `pn`, `boalf` and `b1610` pulls.
- Registered MW (GC if positive, else |DC|, else none; M16), lead party and
  secondary status (BMRS type V) from the pinned reference snapshot of 23 Oct.
- Adoption week from Gate A1's adoption table. That table holds one entry that is
  no BM unit: the null-bmUnit bucket, Gate A1's grouping of records with no
  `bmUnit` (PREREGISTRATION §12, deviation 9). It is dropped here, so the fleet
  is 162 BM units; the pulls already made keep the 163-entry batches they ran
  with, and `check` reports what each batch returned.

Only the chunks each pull plans for the fleet are read, so the probes' chunks
never are. Every file is checked against its manifest SHA-256 before it is read.
Rows for units outside the fleet are counted and skipped.

    uv run python -m src.ingest.assemble check

`check` runs before fleet B1610 exists. It assembles MDO, MDB, PN and BOALF and
writes `outputs/scoring/assemble_check.json`: counts of files, rows, records,
duplicates and exclusions, and the PN gaps and overlaps that ASSUMPTIONS M24
requires before the scoring run. It scores nothing and writes no unit ID and no
value.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.ingest import pull
from src.ingest.parse import (
    Parsed,
    parse_meter,
    parse_segments,
    parse_submissions,
)
from src.ingest.pull import PullError
from src.model.types import (
    LevelSegment,
    MeterPeriod,
    Submission,
    UnitInputs,
    build_unit_inputs,
)

SCHEMA_VERSION = "1.0"
GATE_A1_MANIFEST = Path("data/manifests/gate_a1_manifest.csv")
GATE_A1_RUN_DAY = date(2026, 10, 30)  # PREREGISTRATION §2: the official run
GATE_A1_DAYS = (date(2026, 6, 25), date(2026, 10, 29))  # UTC days, inclusive
REFERENCE_FILE = Path("data/raw/reference/bmunits__dl20261023T130744.json")
REFERENCE_SHA256 = "9245d0ccefb5f8de647cc07ea6db9758a4f6eb6bef4bc6c8acffc23c25ed798b"
ADOPTION_CSV = Path("outputs/gate_a1/adoption_dates.csv")
SCORING_END = datetime(2026, 11, 16, tzinfo=UTC)  # Monday after Sunday 15 Nov
CHECK_OUT = Path("outputs/scoring/assemble_check.json")
SECONDARY_TYPE = "V"
WEEK = timedelta(days=7)
GAP_BUCKETS = (
    ("under 30 min", timedelta(minutes=30)),
    ("30 min to 6 h", timedelta(hours=6)),
    ("6 h to 24 h", timedelta(hours=24)),
)
LONGEST_BUCKET = "24 h or more"


class AssemblyError(RuntimeError):
    """Stops assembly rather than guessing (PIPELINE_RULES §1–2)."""


# ------------------------------------------------------------------ the fleet


@dataclass(frozen=True)
class FleetUnit:
    """A fleet unit's fixed facts: no data from the scoring window."""

    unit: str
    adoption_week_start: datetime
    registered_mw: float | None
    lead_party: str
    secondary: bool

    @property
    def first_scored_week(self) -> datetime:
        """Return the Monday after the adoption week (§3: it never counts)."""
        return self.adoption_week_start + WEEK


def week_start_of(cohort: str) -> datetime:
    """Return the Monday 00:00 UTC of an ISO week written as `2026-W27`."""
    year, _, week = cohort.partition("-W")
    try:
        day = date.fromisocalendar(int(year), int(week), 1)
    except ValueError as exc:
        raise AssemblyError(f"not an ISO week: {cohort!r}") from exc
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def registered_mw(row: Mapping[str, object]) -> float | None:
    """Return GC if positive, else |DC| if positive, else None (ASSUMPTIONS M16)."""
    gc = _capacity(row.get("generationCapacity"))
    if gc > 0:
        return gc
    dc = abs(_capacity(row.get("demandCapacity")))
    return dc if dc > 0 else None


def _capacity(value: object) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise AssemblyError("capacity is not a number")
    try:
        return float(value)
    except ValueError as exc:
        raise AssemblyError("capacity is not a number") from exc


def read_verified(path: Path, sha256: str) -> bytes:
    """Return a file's bytes, stopping if it is missing or its hash differs."""
    if not path.exists():
        raise AssemblyError(f"missing file: {path.name}")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != sha256:
        raise AssemblyError(f"SHA-256 differs from the manifest: {path.name}")
    return body


def reference_rows(root: Path) -> list[dict[str, object]]:
    """Return the pinned reference snapshot's rows (PREREGISTRATION §2)."""
    return pull.rows_of(read_verified(root / REFERENCE_FILE, REFERENCE_SHA256))


def fleet_units(
    adoption_csv: Path,
    reference: Sequence[Mapping[str, object]],
    units: Sequence[str],
) -> dict[str, FleetUnit]:
    """Return the fleet's BM units with their fixed facts, by unit ID.

    Stops if a unit lacks an adoption week, or has no reference row, or has two
    reference rows. Reference rows with no `elexonBmUnit` are never matched.
    """
    with adoption_csv.open(newline="", encoding="utf-8") as f:
        cohort = {r["bm_unit"]: r.get("cohort", "") for r in csv.DictReader(f)}
    by_unit: dict[str, list[Mapping[str, object]]] = {}
    for row in reference:
        key = row.get("elexonBmUnit")
        if isinstance(key, str) and key:
            by_unit.setdefault(key, []).append(row)
    out: dict[str, FleetUnit] = {}
    for u in units:
        if u == pull.NULL_BUCKET:
            raise AssemblyError("the null-bmUnit bucket is not a BM unit")
        rows = by_unit.get(u, [])
        if len(rows) != 1:
            raise AssemblyError(f"{len(rows)} reference rows for a fleet unit, not 1")
        if not cohort.get(u):
            raise AssemblyError("a fleet unit has no adoption week")
        ref = rows[0]
        out[u] = FleetUnit(
            unit=u,
            adoption_week_start=week_start_of(cohort[u]),
            registered_mw=registered_mw(ref),
            lead_party=str(ref.get("leadPartyName") or ""),
            secondary=str(ref.get("bmUnitType")) == SECONDARY_TYPE,
        )
    return out


# ------------------------------------------------------------------ the files


@dataclass(frozen=True)
class Chunk:
    """One raw file to read, with its dataset and manifest hash."""

    dataset: str
    path: Path
    sha256: str
    units: tuple[str, ...] = ()  # the batch a pulled chunk asked for


def gate_a1_chunks(root: Path) -> list[Chunk]:
    """Return Gate A1's official-run files: one per dataset and UTC day.

    The manifest also holds an earlier run of 27 Oct; only rows downloaded on
    the official run's day are read. Stops unless each dataset and day appears
    exactly once.
    """
    days = pull.settlement_dates(*GATE_A1_DAYS)
    want = {(ds, d.isoformat()) for ds in ("MDO", "MDB") for d in days}
    found: dict[tuple[str, str], Chunk] = {}
    held_twice = 0  # a second row for one dataset and day
    with (root / GATE_A1_MANIFEST).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["utc_downloaded"][:10] != GATE_A1_RUN_DAY.isoformat():
                continue
            frm = str(json.loads(row["params"]).get("from", ""))
            key = (row["dataset"], frm[:10])
            if key not in want or not frm.endswith("T00:00Z"):
                raise AssemblyError("a Gate A1 row outside the planned days")
            if key in found:
                held_twice += 1
            found[key] = Chunk(row["dataset"], root / row["raw_file"], row["sha256"])
    if held_twice or len(found) != len(want):
        raise AssemblyError(
            f"Gate A1 run: {len(found)} of {len(want)} files, {held_twice} twice"
        )
    return [found[k] for k in sorted(found)]


def pull_chunks(name: str, units: Sequence[str], root: Path) -> tuple[list[Chunk], int]:
    """Return a pull's planned files for the fleet, and chunks held twice."""
    requests = pull.plan(name, units)
    manifest = root / pull.MANIFEST.relative_to(pull.ROOT)
    try:
        found, twice = pull.planned_chunks(requests, manifest, root)
    except PullError as exc:
        raise AssemblyError(f"{name}: {exc}") from exc
    return [Chunk(r.dataset, *found[r], r.units) for r in requests], twice


# ------------------------------------------------------------------ reading


@dataclass
class DatasetCounts:
    """What one dataset's reading did: counts only (PIPELINE_RULES §2)."""

    files: int = 0
    rows: int = 0
    rows_outside_fleet: int = 0
    duplicate_rows: int = 0
    duplicate_records: int = 0
    records: int = 0
    excluded: Counter[str] = field(default_factory=Counter)
    rows_by_batch: dict[tuple[str, ...], set[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Return the counts as plain JSON values."""
        return {
            "files": self.files,
            "rows": self.rows,
            "rows_outside_fleet": self.rows_outside_fleet,
            "duplicate_rows_in_a_file": self.duplicate_rows,
            "duplicate_records_across_files": self.duplicate_records,
            "records": self.records,
            "excluded": dict(sorted(self.excluded.items())),
        }


def read_records[T](
    chunks: Iterable[Chunk],
    fleet: set[str],
    parse: Callable[[list[dict[str, object]]], Parsed[T]],
    counts: DatasetCounts,
    out: dict[str, set[T]],
) -> None:
    """Parse each file's fleet rows into `out`, one set per unit, counting as it goes.

    A record already held, from another file, is a duplicate (R12a) and is counted.
    """
    for chunk in chunks:
        rows = pull.rows_of(read_verified(chunk.path, chunk.sha256))
        counts.files += 1
        counts.rows += len(rows)
        keep = [r for r in rows if r.get("bmUnit") in fleet]
        counts.rows_outside_fleet += len(rows) - len(keep)
        if chunk.units:
            seen = counts.rows_by_batch.setdefault(chunk.units, set())
            seen.update(str(r["bmUnit"]) for r in keep)
        parsed = parse(keep)
        counts.duplicate_rows += parsed.duplicates
        counts.excluded.update(parsed.excluded)
        for unit, records in parsed.by_unit.items():
            held = out.setdefault(unit, set())
            before = len(held)
            held.update(records)
            counts.duplicate_records += len(records) - (len(held) - before)
    counts.records = sum(len(v) for v in out.values())


@dataclass
class Assembly:
    """Every fleet unit's inputs, its fixed facts, and the reading's counts."""

    units: dict[str, FleetUnit]
    inputs: dict[str, UnitInputs]
    counts: dict[str, DatasetCounts]
    chunks_held_twice: dict[str, int]
    adoption_entries: int
    batches: dict[str, list[tuple[str, ...]]]


def assemble(
    root: Path = pull.ROOT,
    with_meter: bool = True,
    entries: int = pull.FLEET_SIZE,
    bm_units: int = pull.BM_UNITS,
) -> Assembly:
    """Return each fleet unit's inputs from the pinned files (module docstring).

    Without the meter, `meter` is empty for every unit: `check` uses this before
    fleet B1610 exists. Stops if B1610 gives one unit two values for a period.
    """
    pulled_as = pull.load_fleet(root / ADOPTION_CSV, entries)
    ids = pull.bm_units(pulled_as)
    if len(ids) != bm_units:
        raise AssemblyError(f"{len(ids)} BM units, not {bm_units}")
    units = fleet_units(root / ADOPTION_CSV, reference_rows(root), ids)
    fleet = set(ids)
    counts = {k: DatasetCounts() for k in ("MDO", "MDB", "PN", "BOALF", "B1610")}
    twice: dict[str, int] = {}
    pulled: dict[str, list[Chunk]] = {}
    names = ["mdo-mdb", "pn", "boalf", *(["b1610"] if with_meter else [])]
    plans = {n: ids if n == "b1610" else pulled_as for n in names}  # as pulled
    for name in names:
        pulled[name], twice[name] = pull_chunks(name, plans[name], root)
    gate = gate_a1_chunks(root)

    mdo: dict[str, set[Submission]] = {}
    mdb: dict[str, set[Submission]] = {}
    declarations = [*gate, *pulled["mdo-mdb"]]
    read_records(
        [c for c in declarations if c.dataset == "MDO"],
        fleet,
        lambda r: parse_submissions("MDO", r),
        counts["MDO"],
        mdo,
    )
    read_records(
        [c for c in declarations if c.dataset == "MDB"],
        fleet,
        lambda r: parse_submissions("MDB", r),
        counts["MDB"],
        mdb,
    )
    pn: dict[str, set[LevelSegment]] = {}
    boas: dict[str, set[LevelSegment]] = {}
    read_records(
        pulled["pn"], fleet, lambda r: parse_segments("PN", r), counts["PN"], pn
    )
    read_records(
        pulled["boalf"],
        fleet,
        lambda r: parse_segments("BOALF", r),
        counts["BOALF"],
        boas,
    )
    meter: dict[str, set[MeterPeriod]] = {}
    if with_meter:
        read_records(pulled["b1610"], fleet, parse_meter, counts["B1610"], meter)
    for periods in meter.values():
        if len({p.period_start for p in periods}) != len(periods):
            raise AssemblyError("B1610 gives a fleet unit two values for one period")

    inputs = {
        u: build_unit_inputs(
            u,
            units[u].registered_mw,
            [*mdo.get(u, ()), *mdb.get(u, ())],
            list(meter.get(u, ())),
            list(pn.get(u, ())),
            list(boas.get(u, ())),
        )
        for u in ids
    }
    batches = {n: pull.batches(plans[n]) for n in names}
    return Assembly(units, inputs, counts, twice, len(pulled_as), batches)


# ------------------------------------------------------------------ the check


def pn_gaps(
    segments: Sequence[LevelSegment], start: datetime, end: datetime
) -> list[timedelta]:
    """Return the lengths of the stretches of [start, end) that no PN covers."""
    gaps: list[timedelta] = []
    reached = start
    for s in sorted(segments, key=lambda s: (s.time_from, s.time_to)):
        if reached >= end:
            break
        if s.time_to <= reached:
            continue
        if s.time_from > reached:
            gaps.append(min(s.time_from, end) - reached)
        reached = max(reached, s.time_to)
    if reached < end:
        gaps.append(end - reached)
    return gaps


def pn_overlaps(segments: Sequence[LevelSegment]) -> int:
    """Return how many PN segments start before an earlier one has ended (M24)."""
    count = 0
    latest_end: datetime | None = None
    for s in sorted(segments, key=lambda s: (s.time_from, s.time_to)):
        if latest_end is not None and s.time_from < latest_end:
            count += 1
        latest_end = s.time_to if latest_end is None else max(latest_end, s.time_to)
    return count


def gap_bucket(length: timedelta) -> str:
    """Return the fixed length band a PN gap falls in."""
    for name, upper in GAP_BUCKETS:
        if length < upper:
            return name
    return LONGEST_BUCKET


def pn_report(assembly: Assembly, end: datetime = SCORING_END) -> dict[str, object]:
    """Return PN gaps and overlaps over each unit's scoring window: counts only.

    A unit's window runs from its first scored week to `end`; units whose
    window is empty are counted and left out.
    """
    buckets: Counter[str] = Counter()
    gaps = units_with_gap = units_without_pn = no_window = overlaps = 0
    hours = 0.0
    for u, unit in sorted(assembly.units.items()):
        start = unit.first_scored_week
        if start >= end:
            no_window += 1
            continue
        segs = [
            s for s in assembly.inputs[u].pn if s.time_to > start and s.time_from < end
        ]
        if not segs:
            units_without_pn += 1
        found = pn_gaps(segs, start, end)
        gaps += len(found)
        units_with_gap += bool(found)
        hours += sum(g.total_seconds() for g in found) / 3600
        buckets.update(gap_bucket(g) for g in found)
        overlaps += pn_overlaps(segs)
    order = [name for name, _ in GAP_BUCKETS] + [LONGEST_BUCKET]
    return {
        "window": "each unit's first scored week to 2026-11-16T00:00Z",
        "units_with_a_window": len(assembly.units) - no_window,
        "units_without_a_window": no_window,
        "units_with_no_pn_in_window": units_without_pn,
        "units_with_a_gap": units_with_gap,
        "gaps": gaps,
        "gap_hours": round(hours, 2),
        "gaps_by_length": {name: buckets[name] for name in order},
        "overlapping_segments": overlaps,
    }


PULL_DATASETS = {"mdo-mdb": ("MDO", "MDB"), "pn": ("PN",), "boalf": ("BOALF",)}


def pull_coverage(assembly: Assembly) -> dict[str, list[dict[str, object]]]:
    """Return, per pulled dataset and batch, how many of the batch's BM units the
    pull returned rows for: counts and batch numbers only (deviation 9)."""
    out: dict[str, list[dict[str, object]]] = {}
    for name, datasets in PULL_DATASETS.items():
        for ds in datasets:
            seen_by_batch = assembly.counts[ds].rows_by_batch
            out[ds] = [
                {
                    "batch": i + 1,
                    "bm_units": len(pull.bm_units(batch)),
                    "bm_units_with_rows": len(seen_by_batch.get(batch, set())),
                    "holds_null_bucket": pull.NULL_BUCKET in batch,
                }
                for i, batch in enumerate(assembly.batches[name])
            ]
    return out


def check_report(assembly: Assembly) -> dict[str, object]:
    """Return the assemble check's report: counts only, no unit ID, no value."""
    empty = {
        ds: sum(1 for i in assembly.inputs.values() if not getattr(i, attr))
        for ds, attr in (("MDO/MDB", "submissions"), ("PN", "pn"), ("BOALF", "boas"))
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "fleet": {
            "adoption_entries_as_pulled": assembly.adoption_entries,
            "null_bmunit_buckets_dropped": assembly.adoption_entries
            - len(assembly.units),
            "bm_units": len(assembly.units),
        },
        "pull_coverage_by_batch": pull_coverage(assembly),
        "units": len(assembly.units),
        "secondary_units": sum(u.secondary for u in assembly.units.values()),
        "units_without_registered_mw": sum(
            u.registered_mw is None for u in assembly.units.values()
        ),
        "datasets": {
            ds: c.as_dict() for ds, c in assembly.counts.items() if ds != "B1610"
        },
        "pull_chunks_held_twice": dict(sorted(assembly.chunks_held_twice.items())),
        "units_with_no_records": empty,
        "pn_m24": pn_report(assembly),
        "b1610": "not read: the fleet B1610 pull is locked until SF covers 15 Nov",
    }


def main(
    argv: Sequence[str] | None = None,
    root: Path = pull.ROOT,
    entries: int = pull.FLEET_SIZE,
    bm_units: int = pull.BM_UNITS,
) -> int:
    """Run `check`: assemble without B1610 and write the counts-only report."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["check"]:
        print("usage: python -m src.ingest.assemble check", file=sys.stderr)
        return 2
    report = check_report(assemble(root, False, entries, bm_units))
    out = root / CHECK_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
