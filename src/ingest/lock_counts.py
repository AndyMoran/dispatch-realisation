"""Lock-time counts for PREREGISTRATION.md, from declaration and reference data only.

    python -m src.ingest.lock_counts

Reads the official Gate A1 adoption table and the latest pinned reference
snapshot. Reads no acceptances, prices or metered output. Prints and saves
fleet counts only, with no unit IDs:

- H3 sample sizes under the 4- and 8-week rules, by adoption week (§4)
- GSP group × week feasibility under each rule (§6)
- units missing from the reference snapshot or lacking GC (M8)
- default-valued declaration records (R13)

Counts are upper bounds: a week can still fail a metric's screens (§3) once
metered data are read.

Output: outputs/lock/lock_counts.json (no unit IDs; safe to commit).
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]

# Mirrors PREREGISTRATION.md; change there first.
WINDOW_END = date(2026, 11, 15)        # §2: outcome window ends Sunday 15 Nov 2026
SAMPLE_RULES = (4, 8)                  # §4: primary ≥ 4 scored weeks; robustness ≥ 8
GSP_MIN_UNITS_PER_GROUP = 2            # §6
GSP_MIN_CONTRIBUTING = 10              # §6
EXCLUDED_FUELS = ("PS", "NPSHYD")      # M10


def week_start(key: str) -> date:
    y, w = key.split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def full_weeks_after(adoption_week: str, window_end: date = WINDOW_END) -> int:
    """Complete ISO weeks after the adoption week, up to the week ending on window_end.

    The adoption week itself never counts: it holds declarations for only part
    of the week (PREREGISTRATION.md §3, scored weeks).
    """
    first = week_start(adoption_week) + timedelta(days=7)
    last = window_end - timedelta(days=window_end.weekday())   # Monday of the last week
    return 0 if first > last else (last - first).days // 7 + 1


def counts(adoption_rows: list[dict], reference_rows: list[dict]) -> dict:
    ref = {str(r["elexonBmUnit"]): r for r in reference_rows if r.get("elexonBmUnit")}
    adopted = [r for r in adoption_rows if r["status"] == "adopted"]
    missing = [r for r in adopted if r["bm_unit"] not in ref]
    no_gc = [r for r in adopted if r["bm_unit"] in ref
             and not float(ref[r["bm_unit"]].get("generationCapacity") or 0) > 0]
    fuel_now_excluded = [r for r in adopted if r["bm_unit"] in ref
                         and str(ref[r["bm_unit"]].get("fuelType")) in EXCLUDED_FUELS]
    usable = [r for r in adopted if r["bm_unit"] in ref
              and float(ref[r["bm_unit"]].get("generationCapacity") or 0) > 0]

    rules = {}
    for k in SAMPLE_RULES:
        sample = [r for r in usable if full_weeks_after(r["cohort"]) >= k]
        by_gsp = Counter(str(ref[r["bm_unit"]].get("gspGroupId") or "") for r in sample)
        groups_ok = {g: n for g, n in by_gsp.items() if g and n >= GSP_MIN_UNITS_PER_GROUP}
        contributing = sum(groups_ok.values())
        rules[f"min_{k}_weeks"] = {
            "units": len(sample),
            "by_adoption_week": dict(sorted(Counter(r["cohort"] for r in sample).items())),
            "gsp_groups_with_2plus_units": len(groups_ok),
            "gsp_units_contributing": contributing,
            "gsp_week_fe_estimable": contributing >= GSP_MIN_CONTRIBUTING,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "window_end": WINDOW_END.isoformat(),
        "adopted_units": len(adopted),
        "missing_from_reference": len(missing),
        "missing_from_reference_by_adoption_week":
            dict(sorted(Counter(r["cohort"] for r in missing).items())),
        "in_reference_without_gc": len(no_gc),
        "adopted_but_excluded_fuel_in_this_snapshot": len(fuel_now_excluded),
        "default_valued_records_total": sum(int(r.get("n_default") or 0) for r in adoption_rows),
        "units_with_any_default_record": sum(int(r.get("n_default") or 0) > 0 for r in adoption_rows),
        "samples": rules,
        "note": "Upper bounds: weeks may still fail metric screens once metered data are read.",
    }


def main() -> dict:
    adoption = ROOT / "outputs" / "gate_a1" / "adoption_dates.csv"
    snaps = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))
    if not adoption.exists() or not snaps:
        raise SystemExit("Need outputs/gate_a1/adoption_dates.csv and a reference snapshot.")
    with open(adoption) as f:
        rows = list(csv.DictReader(f))
    payload = json.loads(snaps[-1].read_bytes())
    ref = payload.get("data", payload) if isinstance(payload, dict) else payload
    out = {**counts(rows, ref),
           "adoption_table_sha256": hashlib.sha256(adoption.read_bytes()).hexdigest(),
           "reference_snapshot": str(snaps[-1].relative_to(ROOT)),
           "reference_sha256": hashlib.sha256(snaps[-1].read_bytes()).hexdigest()}
    dest = ROOT / "outputs" / "lock" / "lock_counts.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True))
    return out


if __name__ == "__main__":
    main()
