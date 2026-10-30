"""Claim 3 power bound, before the lock, from declaration and reference data only.

    python -m src.ingest.power_bound

Decides how much effort goes into Claim 3 in version 1: build it now, or keep
its specification and defer the build. It does not decide validity. Claim 3
stays secondary in either branch, and its promotion rule is unchanged.

The rule, fixed before this script was first run (PROJECT.md §11, 30 Oct 2026):

    A unit is *potentially identifiable* if at least 10% of its declaration-
    minutes after its adoption week satisfy 1 MWh <= MDO <= 2 x MW x 60 min,
    so that a one-hour full-power instruction could reach r >= 0.5.
    Claim 3 is built in version 1 if at least 30 of the 98 scored units are
    potentially identifiable. Otherwise its specification is kept, unbuilt.

The bound is a necessary-condition screen, not a sufficiency test. It bounds
the r that instructions could reach, not the r they did reach; the realised
distribution is a scoring-run output. The 1 MWh floor mirrors Claim 3's
A >= 1 MWh screen: an instruction sized to MDO needs MDO >= A.

Reported but not deciding: T = 30 and 90 minutes; r ~ 1 (MDO <= MW x T);
5% and 20% minute shares; MDB (bids); the split by BM unit type.

MW follows the M16 chain: GC if positive, else |DC|. MELS is not pulled here, so
units with neither have no MW. They are reported as "mw_unavailable" and count
as not potentially identifiable in the decision. Bounds from |DC| are marked
indicative.

Declarations: the Gate A1 raw files, verified against their manifest hashes.
Latest submission per unit-minute wins (M9); |MWh| >= 9999 defaults are dropped.
A record holds from timeFrom to timeTo where the API gives timeTo, else until
the unit's next record. Minutes run from the Monday after the adoption week to
the end of the Gate A1 data cut-off day.

Output: outputs/lock/power_bound.json. Fleet counts only, no unit IDs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.ingest.lock_counts import full_weeks_after, mw_source, week_start

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "gate_a1.toml"

# The decision rule. Mirrors PROJECT.md §11 (30 Oct 2026); change there first, and
# only before the first run.
DECISION_T_MIN = 60
DECISION_K = 2              # r >= 1/K reachable: MDO <= K x MW x T
DECISION_MINUTE_SHARE = 0.10
DECISION_MIN_UNITS = 30     # of the 98 scored units
MIN_WEEKS = 4               # scored sample: >= 4 scored weeks (PREREGISTRATION §2)
MDO_FLOOR_MWH = 1.0         # mirrors Claim 3's A >= 1 MWh screen

# Reported, not deciding.
T_GRID = (30, 60, 90)
K_GRID = (1, 2)
SHARE_GRID = (0.05, 0.10, 0.20)


class PowerBoundError(RuntimeError):
    """Stops the run instead of guessing (PIPELINE_RULES §1–2)."""


@dataclass(frozen=True)
class Seg:
    unit: str
    start: datetime          # timeFrom
    end: datetime | None     # timeTo, if the API gives one
    level_from: float
    level_to: float | None
    published: str
    serial: int


def _ts(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def parse(body: bytes, api: dict) -> list[Seg]:
    payload = json.loads(body)
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    out = []
    for row in rows:
        out.append(Seg(unit=str(row[api["field_unit"]]),
                       start=_ts(row[api["field_time"]]),
                       end=_ts(row["timeTo"]) if row.get("timeTo") else None,
                       level_from=float(row[api["field_value"]]),
                       level_to=float(row["levelTo"]) if row.get("levelTo") is not None else None,
                       published=str(row.get(api["field_published"], "")),
                       serial=int(row.get(api["field_serial"]) or 0)))
    return out


def minute_values(segs: list[Seg], data_end: datetime) -> dict[datetime, float]:
    """One unit, one dataset: the declaration in force at each minute.

    Later submissions (publishTime, then serialNumber) overwrite earlier ones (M9).
    A record without timeTo holds until the next record of its own submission;
    failing that, the unit's next record of any submission; failing that, data_end.
    A later submission covering only some minutes does not cut short an earlier one.
    """
    starts = sorted({s.start for s in segs})
    nxt_any = {a: b for a, b in zip(starts, starts[1:])}
    by_sub: dict[tuple[str, int], list[datetime]] = defaultdict(list)
    for s in set(segs):
        by_sub[(s.published, s.serial)].append(s.start)
    nxt_sub = {}
    for key, st in by_sub.items():
        st = sorted(set(st))
        nxt_sub.update({(key, a): b for a, b in zip(st, st[1:])})
    minutes: dict[datetime, float] = {}
    for s in sorted(set(segs), key=lambda s: (s.published, s.serial, s.start)):
        hold = nxt_sub.get(((s.published, s.serial), s.start)) or nxt_any.get(s.start, data_end)
        end = min(s.end or hold, data_end)
        if end <= s.start:
            continue
        span = (end - s.start).total_seconds()
        t = s.start.replace(second=0, microsecond=0)
        while t < end:
            if s.level_to is None or span == 0:
                v = s.level_from
            else:
                v = s.level_from + (s.level_to - s.level_from) * (t - s.start).total_seconds() / span
            minutes[t] = v
            t += timedelta(minutes=1)
    return minutes


def unit_shares(minutes: dict[datetime, float], first_scored: datetime, data_end: datetime,
                mw: float, default_abs: float) -> dict | None:
    """Share of in-scope, non-default minutes with floor <= |level| <= K x MW x T."""
    vals = [abs(v) for t, v in minutes.items()
            if first_scored <= t < data_end and abs(v) < default_abs]
    if not vals:
        return None
    n = len(vals)
    return {"minutes": n,
            **{f"k{k}_t{t}": sum(MDO_FLOOR_MWH <= v <= k * mw * t / 60 for v in vals) / n
               for k in K_GRID for t in T_GRID}}


def tally(per_unit: list[dict]) -> dict:
    """Units passing each share threshold, by group. Units without MW never pass."""
    groups = {"all": per_unit,
              "non_secondary": [u for u in per_unit if u["unit_type"] != "V"],
              "secondary_V": [u for u in per_unit if u["unit_type"] == "V"]}
    out = {}
    for g, units in groups.items():
        grid = {}
        for k in K_GRID:
            for t in T_GRID:
                for share in SHARE_GRID:
                    grid[f"k{k}_t{t}_share{int(share * 100)}"] = sum(
                        1 for u in units if u["shares"] and u["shares"][f"k{k}_t{t}"] >= share)
        out[g] = {"units": len(units),
                  "mw_unavailable": sum(1 for u in units if u["mw_source"] == "mel_fallback"),
                  "no_in_scope_minutes": sum(
                      1 for u in units if u["mw_source"] != "mel_fallback" and not u["shares"]),
                  "mw_indicative_dc": sum(1 for u in units if u["mw_source"] == "dc"),
                  "units_passing": grid}
    return out


def decide(groups: dict) -> dict:
    key = f"k{DECISION_K}_t{DECISION_T_MIN}_share{int(DECISION_MINUTE_SHARE * 100)}"
    n = groups["all"]["units_passing"][key]
    n_non_v = groups["non_secondary"]["units_passing"][key]
    return {"decision_cell": key,
            "potentially_identifiable": n,
            "of_scored_units": groups["all"]["units"],
            "threshold_units": DECISION_MIN_UNITS,
            "build_claim_3_in_v1": n >= DECISION_MIN_UNITS,
            "potentially_identifiable_non_secondary": n_non_v,
            "passes_only_because_of_secondary_units":
                n >= DECISION_MIN_UNITS and n_non_v < DECISION_MIN_UNITS,
            "reading": "Necessary-condition screen on effort, not validity. Identified set "
                       "will be no larger than the potential set; the promotion rule governs."}


def run_bound(segs_by_dataset: dict[str, list[Seg]], adoption_rows: list[dict],
              reference_rows: list[dict], data_end: datetime, default_abs: float) -> dict:
    ref = {str(r["elexonBmUnit"]): r for r in reference_rows if r.get("elexonBmUnit")}
    sample = [r for r in adoption_rows
              if r["status"] == "adopted" and full_weeks_after(r["cohort"]) >= MIN_WEEKS]
    by_unit: dict[str, dict[str, list[Seg]]] = defaultdict(lambda: defaultdict(list))
    for ds, segs in segs_by_dataset.items():
        for s in segs:
            by_unit[s.unit][ds].append(s)
    result = {}
    for ds in segs_by_dataset:
        per_unit = []
        for r in sample:
            u, rr = r["bm_unit"], ref.get(r["bm_unit"])
            src = mw_source(rr)
            mw = (float(rr["generationCapacity"]) if src == "gc"
                  else abs(float(rr["demandCapacity"])) if src == "dc" else None)
            first_scored = datetime.combine(week_start(r["cohort"]) + timedelta(days=7),
                                            datetime.min.time(), timezone.utc)
            shares = None
            if mw:
                shares = unit_shares(minute_values(by_unit[u][ds], data_end),
                                     first_scored, data_end, mw, default_abs)
            per_unit.append({"unit_type": str((rr or {}).get("bmUnitType")),
                             "mw_source": src, "shares": shares})
        groups = tally(per_unit)
        result[ds] = {"groups": groups,
                      "minutes_in_scope": sum(u["shares"]["minutes"] for u in per_unit if u["shares"]),
                      "unit_type_counts": dict(sorted(Counter(u["unit_type"] for u in per_unit).items()))}
        if ds == "MDO":
            result[ds]["decision"] = decide(groups)
    return result


def _load_segments(api: dict) -> tuple[dict[str, list[Seg]], dict]:
    manifest = ROOT / "data" / "manifests" / "gate_a1_manifest.csv"
    with open(manifest) as f:
        rows = list(csv.DictReader(f))
    segs: dict[str, list[Seg]] = {"MDO": [], "MDB": []}
    bad, read, with_time_to = [], 0, 0
    for row in rows:
        path = ROOT / row["raw_file"]
        if not path.exists():
            bad.append(("missing", row["raw_file"]))
            continue
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != row["sha256"]:
            bad.append(("hash_mismatch", row["raw_file"]))
            continue
        parsed = parse(body, api)
        with_time_to += sum(s.end is not None for s in parsed)
        segs[row["dataset"]] += parsed
        read += 1
    if bad:
        raise PowerBoundError(f"{len(bad)} raw files missing or changed, e.g. {bad[:3]}")
    info = {"raw_files_read": read,
            "records_read": sum(len(v) for v in segs.values()),
            "records_with_timeTo": with_time_to,
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    return segs, info


def main() -> dict:
    cfg = tomllib.loads(CONFIG.read_text())
    adoption = ROOT / "outputs" / "gate_a1" / "adoption_dates.csv"
    snaps = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))
    if not adoption.exists() or not snaps:
        raise SystemExit("Need outputs/gate_a1/adoption_dates.csv and a reference snapshot.")
    with open(adoption) as f:
        adoption_rows = list(csv.DictReader(f))
    payload = json.loads(snaps[-1].read_bytes())
    ref = payload.get("data", payload) if isinstance(payload, dict) else payload
    cutoff = date.fromisoformat(cfg["data"]["data_cutoff"])
    data_end = datetime.combine(cutoff + timedelta(days=1), datetime.min.time(), timezone.utc)
    segs, info = _load_segments(cfg["api"])
    out = {"schema_version": SCHEMA_VERSION,
           "rule": {"T_min": DECISION_T_MIN, "K": DECISION_K,
                    "minute_share": DECISION_MINUTE_SHARE, "min_units": DECISION_MIN_UNITS,
                    "mdo_floor_mwh": MDO_FLOOR_MWH, "min_scored_weeks": MIN_WEEKS},
           "data_end_exclusive": data_end.isoformat(),
           **info,
           "adoption_table_sha256": hashlib.sha256(adoption.read_bytes()).hexdigest(),
           "reference_snapshot": str(snaps[-1].relative_to(ROOT)),
           "reference_sha256": hashlib.sha256(snaps[-1].read_bytes()).hexdigest(),
           "results": run_bound(segs, adoption_rows, ref, data_end, cfg["data"]["default_abs_mwh"])}
    dest = ROOT / "outputs" / "lock" / "power_bound.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True))
    return out


if __name__ == "__main__":
    main()
