"""Gate A1: adoption dates and design-hierarchy triggers, from declaration data only.

Reads MDO/MDB from the Elexon Insights API. Never touches acceptances, skips,
prices or metered output (PROJECT.md §5A; outcome data stays locked).

    python -m src.ingest.gate_a1 probe   # endpoint shape; no unit IDs printed
    python -m src.ingest.gate_a1 smoke   # two-day pull, plumbing checks only, no statistics
    python -m src.ingest.gate_a1 run     # refuses to run until config is complete

Outputs (schema_version in every file, PIPELINE_RULES §6):
    data/raw/mdo_mdb/<dataset>/<chunk>.json       as downloaded
    data/manifests/gate_a1_manifest.csv           one row per request
    outputs/gate_a1/adoption_dates.csv            one row per unit, incl. excluded
    outputs/gate_a1/coverage.json                 requested / arrived / failed
    outputs/gate_a1/gate_a1_report.json           trigger statistics + selected design
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median, pstdev

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "gate_a1.toml"

REQUIRED_FOR_RUN = {
    "data": ["data_cutoff", "exclude_fuel_types"],
    "design1": ["min_units_per_cohort"],
    "design2": ["min_units", "min_weeks_per_unit", "min_within_unit_cv"],
    "design3": ["grace_end_announced", "min_weeks_before_cutoff", "min_reserve_units"],
    "api": ["mdo_path", "mdb_path", "from_param", "to_param",
            "field_unit", "field_time", "field_value", "field_published", "field_serial"],
}


class GateA1Error(RuntimeError):
    """Stops the run. Raised instead of guessing (PIPELINE_RULES §1–2)."""


# --------------------------------------------------------------------- config

def load_config(path: Path = CONFIG) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def assert_config_complete(cfg: dict) -> None:
    missing = [f"{sec}.{key}" for sec, keys in REQUIRED_FOR_RUN.items()
               for key in keys if cfg.get(sec, {}).get(key, "") == ""]
    d3 = cfg.get("design3", {})
    if d3.get("grace_end_announced") is True and d3.get("grace_end_date", "") == "":
        missing.append("design3.grace_end_date")
    if missing:
        raise GateA1Error(
            "Thresholds must be fixed before Gate A1 is evaluated (PROJECT.md §5A). "
            "Empty in config/gate_a1.toml: " + ", ".join(missing))


# --------------------------------------------------------------- statistics

@dataclass(frozen=True)
class Record:
    unit: str
    ts: datetime
    mwh: float
    dataset: str          # "MDO" or "MDB"
    published: str = ""   # publishTime: when this declaration was submitted
    serial: int = 0       # serialNumber: orders submissions published at the same time


def latest_declarations(records: list[Record]) -> tuple[list[Record], dict]:
    """Remove exact duplicates, then keep the latest submission per unit-minute.

    Chunk windows are inclusive at both ends, so neighbouring chunks overlap.
    MDO/MDB are redeclared after every BOA, so one minute can carry several
    submissions; earlier ones are superseded. Both counts are reported (§2).
    """
    unique = sorted(set(records), key=lambda r: (r.dataset, r.unit, r.ts, r.published, r.serial))
    latest: dict[tuple[str, str, datetime], Record] = {}
    for r in unique:
        latest[(r.dataset, r.unit, r.ts)] = r          # later submissions overwrite earlier
    kept = sorted(latest.values(), key=lambda r: (r.dataset, r.unit, r.ts))
    counts = {"records_received": len(records),
              "exact_duplicates_removed": len(records) - len(unique),
              "superseded_submissions": len(unique) - len(kept),
              "latest_declarations": len(kept)}
    return kept, counts


def adoption_dates(records: list[Record], default_abs: float) -> dict[str, dict]:
    """First non-default MDO or MDB submission per unit (PIPELINE_RULES §9).

    Units seen only with default values are kept, labelled, never dropped (§3).
    """
    units: dict[str, dict] = {}
    for r in sorted(records, key=lambda r: (r.unit, r.ts, r.dataset)):
        u = units.setdefault(r.unit, {"unit": r.unit, "first_real": None,
                                      "last_real": None, "n_real": 0, "n_default": 0})
        if abs(r.mwh) >= default_abs:
            u["n_default"] += 1
            continue
        u["n_real"] += 1
        u["first_real"] = u["first_real"] or r.ts
        u["last_real"] = r.ts
    for u in units.values():
        u["status"] = "adopted" if u["first_real"] else "excluded(default_values_only)"
    return units


def exclude_non_battery(units: dict[str, dict], fuel_by_unit: dict[str, str],
                        excluded_fuels: list[str]) -> dict[str, dict]:
    """Keep pumped storage and hydro out of the battery fleet (ASSUMPTIONS.md M10).

    Excluded units stay in the table with a reason (PIPELINE_RULES §3). A unit missing
    from the reference snapshot is kept: absence is not evidence it isn't a battery.
    """
    for unit, u in units.items():
        fuel = fuel_by_unit.get(unit)
        u["fuel_type"] = fuel or ""
        if u["status"] == "adopted" and fuel in excluded_fuels:
            u["status"] = f"excluded(fuel_type_{fuel})"
    return units


def load_reference_fuel(path: Path | None = None) -> tuple[dict[str, str], Path]:
    """Fuel type by Elexon BM unit ID, from the latest pinned reference snapshot."""
    snaps = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))
    if path is None:
        if not snaps:
            raise GateA1Error("No reference snapshot. Run `python -m src.ingest.reference` first.")
        path = snaps[-1]
    payload = json.loads(path.read_bytes())
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    return {str(r["elexonBmUnit"]): str(r.get("fuelType")) for r in rows if r.get("elexonBmUnit")}, path


def cohort_key(ts: datetime) -> str:
    y, w, _ = ts.isocalendar()
    return f"{y}-W{w:02d}"


def week_start(key: str) -> date:
    y, w = key.split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def within_unit_cv(records: list[Record], default_abs: float) -> dict[str, float]:
    """CV over days of the daily median of MDO + |MDB|. Declaration-only proxy."""
    by_unit_day: dict[tuple[str, date], dict[str, list[float]]] = {}
    for r in records:
        if abs(r.mwh) >= default_abs:
            continue
        d = by_unit_day.setdefault((r.unit, r.ts.date()), {"MDO": [], "MDB": []})
        d[r.dataset].append(abs(r.mwh))
    daily: dict[str, list[float]] = {}
    for (unit, _), v in sorted(by_unit_day.items()):
        if v["MDO"] and v["MDB"]:
            daily.setdefault(unit, []).append(median(v["MDO"]) + median(v["MDB"]))
    return {u: pstdev(x) / mean(x) for u, x in daily.items() if len(x) >= 2 and mean(x) > 0}


def passes(value: float, threshold: float, borderline: float) -> bool:
    """Borderline (within `borderline` of threshold) counts as a failure (§5A)."""
    return value >= threshold * (1 + borderline)


def evaluate(units: dict[str, dict], cv: dict[str, float], cfg: dict) -> dict:
    bl = cfg["rules"]["borderline_fraction"]
    cutoff = date.fromisoformat(cfg["data"]["data_cutoff"])
    adopted = {k: v for k, v in units.items() if v["status"] == "adopted"}

    # Design 1
    cohorts: dict[str, list[str]] = {}
    for u in adopted.values():
        cohorts.setdefault(cohort_key(u["first_real"]), []).append(u["unit"])
    sizes = {k: len(v) for k, v in sorted(cohorts.items())}
    n_min = cfg["design1"]["min_units_per_cohort"]
    # The last cohort has no not-yet-treated comparison group, so it is dropped
    # from estimation and does not count towards the cohort minimum (§5A).
    last = max(sizes) if sizes else None
    estimable = [k for k, n in sizes.items() if k != last and passes(n, n_min, bl)]
    earliest_post = ((cutoff - week_start(estimable[0])).days / 7) if estimable else 0.0
    d1 = {
        "cohort_sizes": sizes,
        "last_cohort_dropped": last,
        "estimable_cohorts_meeting_N": len(estimable),
        "earliest_cohort_post_weeks": round(earliest_post, 1),
    }
    d1["triggered"] = (passes(len(estimable), cfg["design1"]["min_cohorts"], bl)
                       and passes(earliest_post, cfg["design1"]["min_post_weeks_earliest"], bl))

    # Design 2
    weeks = {u: (v["last_real"] - v["first_real"]).days / 7 for u, v in adopted.items()}
    long_units = [u for u, w in weeks.items()
                  if passes(w, cfg["design2"]["min_weeks_per_unit"], bl)]
    cv_long = [cv[u] for u in long_units if u in cv]
    med_cv = median(cv_long) if cv_long else 0.0
    d2 = {"units_with_M_weeks": len(long_units), "median_within_unit_cv": round(med_cv, 4)}
    d2["triggered"] = (passes(len(long_units), cfg["design2"]["min_units"], bl)
                       and passes(med_cv, cfg["design2"]["min_within_unit_cv"], bl))

    # Design 3: announcement and timing only. Reserve-unit count needs contract
    # data not yet sourced, so it is reported as unevaluated, not guessed (§10).
    d3c = cfg["design3"]
    d3 = {"grace_end_announced": d3c["grace_end_announced"]}
    if d3c["grace_end_announced"] is True:
        gap = (cutoff - date.fromisoformat(d3c["grace_end_date"])).days / 7
        d3["weeks_before_cutoff"] = round(gap, 1)
        d3["reserve_units"] = "not evaluated: reserve contract data not sourced"
        d3["triggered"] = None
    else:
        d3["triggered"] = False

    selected = ("design1" if d1["triggered"] else "design2" if d2["triggered"]
                else "design3_pending" if d3["triggered"] is None else "design_note_only")
    return {"design1": d1, "design2": d2, "design3": d3, "selected": selected,
            "units_adopted": len(adopted), "units_seen": len(units)}


# --------------------------------------------------------------------- I/O

def _get(url: str, params: dict | None = None) -> bytes:
    import requests  # imported here so the statistics are testable offline
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.content


def probe(cfg: dict) -> None:
    spec = json.loads(_get(cfg["api"]["spec_url"]))
    hits = {p: v for p, v in spec.get("paths", {}).items()
            if any(t in p.upper() for t in ("MDO", "MDB", "MAXIMUMDELIVERY"))}
    if not hits:
        raise GateA1Error("No MDO/MDB path in the API spec. Check spec_url and the "
                          "Elexon developer portal by hand.")
    for path, ops in sorted(hits.items()):
        for method, op in ops.items():
            names = [p.get("name") for p in op.get("parameters", [])]
            print(f"{method.upper()} {path}  params={names}")
    print("Fill api.* in config/gate_a1.toml from the above, then test one hour with "
          "a request of your own. Do not fill thresholds from what the data shows.")


def parse_rows(body: bytes, dataset: str, api: dict) -> list[Record]:
    """Parse one API response. A missing field raises, so the chunk is recorded as failed."""
    payload = json.loads(body)
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    return [Record(unit=str(row[api["field_unit"]]),
                   ts=datetime.fromisoformat(str(row[api["field_time"]]).replace("Z", "+00:00")),
                   mwh=float(row[api["field_value"]]),
                   dataset=dataset,
                   published=str(row.get(api["field_published"], "")),
                   serial=int(row.get(api["field_serial"]) or 0))
            for row in rows]


def fetch(api: dict, start: datetime, end: datetime,
          raw_dir: Path, man_path: Path) -> tuple[list[Record], dict]:
    """Pull MDO and MDB in chunks; save raw bytes and a manifest row per request."""
    step = timedelta(hours=float(api["chunk_hours"]))
    for p in (raw_dir, man_path.parent):
        p.mkdir(parents=True, exist_ok=True)
    records: list[Record] = []
    coverage = {"schema_version": SCHEMA_VERSION, "requested": 0, "arrived": 0, "failed": []}
    new_manifest = not man_path.exists()
    with open(man_path, "a", newline="") as mf:
        man = csv.writer(mf)
        if new_manifest:
            man.writerow(["schema_version", "dataset", "url", "params", "utc_downloaded",
                          "sha256", "rows", "raw_file"])
        for dataset, path in (("MDO", api["mdo_path"]), ("MDB", api["mdb_path"])):
            t = start
            while t < end:
                params = {api["from_param"]: f"{t:%Y-%m-%dT%H:%MZ}",
                          api["to_param"]: f"{t + step:%Y-%m-%dT%H:%MZ}"}
                coverage["requested"] += 1
                try:
                    body = _get(api["base_url"] + path, params)
                    downloaded = datetime.now(timezone.utc)
                    # One file per download: earlier vintages are never overwritten (§7).
                    raw_file = raw_dir / dataset / f"{t:%Y%m%dT%H%M}__dl{downloaded:%Y%m%dT%H%M%S%f}.json"
                    chunk = parse_rows(body, dataset, api)
                    raw_file.parent.mkdir(parents=True, exist_ok=True)
                    raw_file.write_bytes(body)
                    man.writerow([SCHEMA_VERSION, dataset, api["base_url"] + path,
                                  json.dumps(params, sort_keys=True),
                                  downloaded.isoformat(),
                                  hashlib.sha256(body).hexdigest(), len(chunk),
                                  str(raw_file.relative_to(ROOT))])
                    records += chunk
                    coverage["arrived"] += 1
                except Exception as e:  # recorded, never dropped silently (§2)
                    coverage["failed"].append({"dataset": dataset, "from": t.isoformat(),
                                               "reason": f"{type(e).__name__}: {e}"})
                t += step
    return records, coverage


def assert_api_complete(cfg: dict) -> None:
    missing = [f"api.{k}" for k in REQUIRED_FOR_RUN["api"] if cfg["api"].get(k, "") == ""]
    if missing:
        raise GateA1Error("Empty in config/gate_a1.toml: " + ", ".join(missing))


def smoke(cfg: dict, days: int = 2) -> dict:
    """Exercise the pull end to end on a short window. Computes no adoption statistics.

    Checks: every request succeeds; every row parses; manifest rows match arrivals;
    timestamps fall inside the window; raw files on disk re-parse to the same records.
    Output goes to data/interim/smoke/ (gitignored) and never mixes with Gate A1's.
    """
    assert_api_complete(cfg)
    api = cfg["api"]
    start = datetime.fromisoformat(cfg["data"]["window_start"]).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=days)
    base = ROOT / "data" / "interim" / "smoke"
    man_path = base / "manifest.csv"
    if base.exists():
        shutil.rmtree(base)          # scratch only: each smoke run starts clean
    records, coverage = fetch(api, start, end, base / "raw", man_path)

    with open(man_path) as f:
        manifest_rows = sum(1 for _ in f) - 1
    out_of_window = sum(not (start <= r.ts <= end) for r in records)
    reparsed: list[Record] = []
    for raw in sorted((base / "raw").rglob("*.json")):
        reparsed += parse_rows(raw.read_bytes(), raw.parent.name, api)
    _, counts = latest_declarations(records)

    checks = {
        "all_requests_succeeded": not coverage["failed"],
        "manifest_rows_match_arrivals": manifest_rows == coverage["arrived"],
        "timestamps_inside_window": out_of_window == 0,
        "raw_files_reparse_identically": sorted(set(reparsed), key=str) == sorted(set(records), key=str),
    }
    summary = {"window": [start.isoformat(), end.isoformat()], "requested": coverage["requested"],
               "arrived": coverage["arrived"], "failed": coverage["failed"],
               "out_of_window_records": out_of_window, **counts,
               "checks": checks, "passed": all(checks.values())}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise GateA1Error("Smoke test failed: " +
                          ", ".join(k for k, ok in checks.items() if not ok))
    return summary


def run(cfg: dict) -> None:
    assert_config_complete(cfg)
    api, dcfg = cfg["api"], cfg["data"]
    start = datetime.fromisoformat(dcfg["window_start"]).replace(tzinfo=timezone.utc)
    end = (datetime.fromisoformat(dcfg["data_cutoff"]) + timedelta(days=1)).replace(tzinfo=timezone.utc)
    out_dir = ROOT / "outputs" / "gate_a1"
    out_dir.mkdir(parents=True, exist_ok=True)
    records, coverage = fetch(api, start, end, ROOT / "data" / "raw" / "mdo_mdb",
                              ROOT / "data" / "manifests" / "gate_a1_manifest.csv")

    (out_dir / "coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True))
    if coverage["failed"]:
        raise GateA1Error(f"{len(coverage['failed'])} requests failed; see coverage.json. "
                          "Gate A1 is not evaluated on incomplete data.")

    default_abs = dcfg["default_abs_mwh"]
    unique = sorted(set(records), key=lambda r: (r.dataset, r.unit, r.ts, r.published, r.serial))
    latest, counts = latest_declarations(records)
    coverage.update(counts)
    (out_dir / "coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True))
    # Adoption: first non-default submission of any vintage. Variation: latest only.
    fuel_by_unit, ref_path = load_reference_fuel()
    units = exclude_non_battery(adoption_dates(unique, default_abs), fuel_by_unit,
                                dcfg["exclude_fuel_types"])
    cv = within_unit_cv(latest, default_abs)
    with open(out_dir / "adoption_dates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["schema_version", "bm_unit", "status", "fuel_type", "first_real_utc",
                    "last_real_utc", "n_real", "n_default", "cohort", "within_unit_cv"])
        for u in sorted(units):
            v = units[u]
            w.writerow([SCHEMA_VERSION, u, v["status"], v["fuel_type"],
                        v["first_real"].isoformat() if v["first_real"] else "",
                        v["last_real"].isoformat() if v["last_real"] else "",
                        v["n_real"], v["n_default"],
                        cohort_key(v["first_real"]) if v["first_real"] else "",
                        f"{cv[u]:.6f}" if u in cv else ""])

    report = {"schema_version": SCHEMA_VERSION,
              "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
              "reference_snapshot": str(ref_path.relative_to(ROOT)),
              "reference_sha256": hashlib.sha256(ref_path.read_bytes()).hexdigest(),
              **evaluate(units, cv, cfg)}
    (out_dir / "gate_a1_report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    cfg = load_config()
    if cmd == "probe":
        probe(cfg)
    elif cmd == "smoke":
        smoke(cfg)
    elif cmd == "run":
        run(cfg)
    else:
        sys.exit("usage: python -m src.ingest.gate_a1 [probe|smoke|run]")
