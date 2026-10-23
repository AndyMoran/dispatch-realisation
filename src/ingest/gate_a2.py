"""Gate A2: what battery skips are worth, per MW-year (PROJECT.md §5A, rule v1).

    python -m src.ingest.gate_a2 schema   # field names and stage values only; safe before lock
    python -m src.ingest.gate_a2 run      # refuses to run until PREREGISTRATION.md is locked

`schema` asks NESO's server for field names and distinct stage values, so no
skip volume ever reaches this machine before the lock. `run` downloads the
twelve monthly files, values skipped battery volume against MID, divides by
MW-years of exposure, and applies the decision rule. It names no units in its
report; a per-unit audit table goes to data/interim/ (gitignored).

A2 is a stakes gate. Its figure is not the Workstream B estimate (ASSUMPTIONS.md E6).
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "gate_a2.toml"
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


class GateA2Error(RuntimeError):
    """Stops the run rather than guessing (PIPELINE_RULES §1–2)."""


def load_config(path: Path = CONFIG) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


# ------------------------------------------------------------------ guards

def assert_locked(prereg: Path | None = None) -> None:
    """A2 reads outcome data, so it runs only after the pre-registration locks."""
    text = (prereg or ROOT / "PREREGISTRATION.md").read_text()
    status = next((l for l in text.splitlines() if l.startswith("**Status:")), "")
    if not status.startswith("**Status: LOCKED"):
        raise GateA2Error("PREREGISTRATION.md is not locked. Gate A2 reads outcome data "
                          "and may run only after the lock (PROJECT.md §5A).")


def choose_stage(stages_by_month: dict[str, set[int]], stage: int, fallback: int) -> int:
    """Stage 6 for all months, or the fallback for all months if any month lacks it."""
    return stage if all(stage in s for s in stages_by_month.values()) else fallback


# ------------------------------------------------------------------ prices

def half_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0 if ts.minute < 30 else 30, second=0, microsecond=0)


def parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def mid_by_half_hour(records: list[dict], f_time: str, f_price: str, f_volume: str
                     ) -> dict[datetime, float]:
    """Volume-weighted MID across providers with volume > 0; half hours with none are absent."""
    num: dict[datetime, float] = defaultdict(float)
    vol: dict[datetime, float] = defaultdict(float)
    for r in records:
        v = float(r.get(f_volume) or 0)
        if v > 0:
            t = half_hour(parse_utc(str(r[f_time])))
            num[t] += float(r[f_price]) * v
            vol[t] += v
    return {t: num[t] / vol[t] for t in sorted(vol)}


def daily_extremes(mid: dict[datetime, float], tz: str) -> dict[date, tuple[float, float]]:
    """(lowest, highest) MID for each local day."""
    zone = ZoneInfo(tz)
    out: dict[date, list[float]] = defaultdict(list)
    for t, p in mid.items():
        out[t.astimezone(zone).date()].append(p)
    return {d: (min(v), max(v)) for d, v in out.items()}


def margins(bid_offer: str, price: float, mid: float, day_lo: float, day_hi: float
            ) -> tuple[float, float]:
    """(headline, conservative) £/MWh. Positive when the BM pays better than wholesale."""
    if bid_offer.lower().startswith("offer"):
        return price - mid, price - day_hi
    if bid_offer.lower().startswith("bid"):
        return mid - price, day_lo - price
    raise GateA2Error(f"Unknown bid_offer value: {bid_offer!r}")


# ------------------------------------------------------------- computation

@dataclass
class Tally:
    value_headline: float = 0.0
    value_conservative: float = 0.0
    rows_used: int = 0
    rows_no_mid: int = 0
    mwh_no_mid: float = 0.0
    by_unit: dict = field(default_factory=lambda: defaultdict(float))


def value_skips(rows, stage: int, fleet: set[str], mid: dict[datetime, float],
                extremes: dict[date, tuple[float, float]], tz: str) -> Tally:
    """Value skipped volume of fleet units at one stage. Rows without MID are counted, not dropped silently."""
    zone = ZoneInfo(tz)
    t = Tally()
    for r in rows:
        if int(r["stage"]) != stage or r["bm_unit"] not in fleet:
            continue
        mwh = abs(float(r["skipped_volume_MWh"] or 0))
        if mwh == 0:
            continue
        ts = parse_utc(r["date"])
        hh = half_hour(ts)
        if hh not in mid:
            t.rows_no_mid += 1
            t.mwh_no_mid += mwh
            continue
        lo, hi = extremes[ts.astimezone(zone).date()]
        head, cons = margins(r["bid_offer"], float(r["average_price_per_MWh"]), mid[hh], lo, hi)
        t.value_headline += mwh * head
        t.value_conservative += mwh * cons
        t.by_unit[r["bm_unit"]] += mwh * head
        t.rows_used += 1
    return t


def exposure(months_present: dict[str, set[str]], gc: dict[str, float], window: list[str]
             ) -> tuple[float, float]:
    """(MW-years over the window, September-fleet sensitivity in MW-years).

    A unit is present from the first to the last window month in which it appears.
    """
    idx = {m: i for i, m in enumerate(window)}
    mw_years = 0.0
    for unit, months in months_present.items():
        if unit not in gc or not months:
            continue
        ix = sorted(idx[m] for m in months if m in idx)
        mw_years += gc[unit] * (ix[-1] - ix[0] + 1) / 12
    last = window[-1]
    sensitivity = sum(gc[u] for u, m in months_present.items() if u in gc and last in m)
    return mw_years, sensitivity


def _note_presence(rows, month: str, gc_fleet: set[str], fleet: set[str],
                   present: dict[str, set[str]], outside: set[str]):
    """Pass rows through, recording which fleet units appear and which NESO batteries are outside."""
    for r in rows:
        if r["bm_unit"] in gc_fleet:
            present[r["bm_unit"]].add(month)
        elif str(r.get("fuel", "")).lower() == "battery" and r["bm_unit"] not in fleet:
            outside.add(r["bm_unit"])
        yield r


def decide(low: float, point: float, cfg: dict) -> str:
    th = cfg["thresholds"]
    is_low, is_high = low < th["low"], point > th["high"]
    if is_low and is_high:
        return th["both_triggered"]
    if is_low:
        return "reputation"
    if is_high:
        return "product_grade"
    return "middle"


# ---------------------------------------------------------------- I/O: NESO

def _get_json(url: str, params: dict | None = None) -> dict:
    """GET JSON; on an HTTP error, raise with the server's own message (PIPELINE_RULES §2)."""
    import requests
    r = requests.get(url, params=params, timeout=120)
    if not r.ok:
        raise GateA2Error(f"HTTP {r.status_code} from {r.url}: {r.text[:400]}")
    return r.json()


def distinct_stages(api: str, resource_id: str, candidates=range(0, 10)) -> tuple[set[int], str]:
    """Stage values present in a resource, without fetching any volumes.

    Tries CKAN's SQL route, then its distinct search, then a row count per stage
    (`limit=0` returns only a total). Returns the stages and the route that worked.
    """
    errors = []
    try:
        sql = f'SELECT DISTINCT stage FROM "{resource_id}"'
        recs = _get_json(f"{api}/datastore_search_sql", {"sql": sql})["result"]["records"]
        return {int(x["stage"]) for x in recs}, "sql"
    except GateA2Error as e:
        errors.append(f"sql: {e}")
    try:
        recs = _get_json(f"{api}/datastore_search",
                         {"resource_id": resource_id, "fields": "stage",
                          "distinct": "true", "limit": 100})["result"]["records"]
        return {int(x["stage"]) for x in recs}, "distinct"
    except GateA2Error as e:
        errors.append(f"distinct: {e}")
    try:
        found = set()
        for k in candidates:
            res = _get_json(f"{api}/datastore_search",
                            {"resource_id": resource_id, "limit": 0,
                             "filters": json.dumps({"stage": k})})["result"]
            if res.get("total", 0) > 0:
                found.add(k)
        return found, "count_per_stage"
    except GateA2Error as e:
        errors.append(f"count: {e}")
    raise GateA2Error("Could not read stage values: " + " | ".join(errors))


def month_label(m: str) -> str:
    y, mm = m.split("-")
    return f"{MONTH_NAMES[int(mm) - 1]} {y}"


def match_resources(resources: list[dict], fragment: str, window: list[str]) -> dict[str, dict]:
    """One resource per month whose name contains the fragment and the month label."""
    out = {}
    for m in window:
        hits = [r for r in resources
                if fragment.lower() in r.get("name", "").lower()
                and month_label(m).lower() in r.get("name", "").lower()]
        if len(hits) != 1:
            raise GateA2Error(f"{len(hits)} resources match {fragment!r} for {month_label(m)}; "
                              "expected exactly one.")
        out[m] = hits[0]
    return out


def resources_and_stages(cfg: dict) -> tuple[dict, dict, dict[str, set[int]]]:
    neso, window = cfg["neso"], cfg["window"]["months"]
    pkg = _get_json(f"{neso['api']}/package_show", {"id": neso["package_id"]})["result"]
    all_bm = match_resources(pkg["resources"], neso["all_bm_name"], window)
    psa = match_resources(pkg["resources"], neso["psa_name"], window)
    stages: dict[str, set[int]] = {}
    routes: set[str] = set()
    for m in window:
        s: set[int] = set()
        first = True
        for res in (all_bm[m], psa[m]):
            meta = _get_json(f"{neso['api']}/datastore_search",
                             {"resource_id": res["id"], "limit": 0})["result"]
            names = {f["id"] for f in meta["fields"]}
            missing = [f for f in neso["fields"] if f not in names]
            if missing:
                raise GateA2Error(f"{res['name']}: missing fields {missing}")
            vals, route = distinct_stages(neso["api"], res["id"])
            routes.add(route)
            s = vals if first else s & vals          # a stage counts only if both files have it
            first = False
        stages[m] = s
    print(f"stage query route(s): {sorted(routes)}", file=sys.stderr)
    return all_bm, psa, stages


def schema(cfg: dict) -> dict:
    """Field names, resource names and distinct stage values. No volumes, no prices."""
    all_bm, psa, stages = resources_and_stages(cfg)
    w = cfg["window"]
    el = cfg["elexon"]
    spec = _get_json(el["spec_url"])
    mid_ops = spec["paths"].get(el["mid_path"], {})
    mid_params = {m: [p["name"] for p in op.get("parameters", [])] for m, op in mid_ops.items()}
    out = {
        "resources_all_bm": {m: r["name"] for m, r in all_bm.items()},
        "resources_psa": {m: r["name"] for m, r in psa.items()},
        "stages_in_both_files": {m: sorted(s) for m, s in stages.items()},
        "stage_rule": f"stage {w['stage']} if every month has it, else stage {w['fallback_stage']} for all",
        "stage_selected": choose_stage(stages, w["stage"], w["fallback_stage"]),
        "mid_endpoint_params": mid_params,
    }
    print(json.dumps(out, indent=2))
    return out


# ----------------------------------------------------------------- I/O: run

def download(url: str, dest: Path, manifest: Path, label: str) -> Path:
    import requests
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    stamp = datetime.now(timezone.utc)
    path = dest / f"{label}__dl{stamp:%Y%m%dT%H%M%S}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    new = not manifest.exists()
    with open(manifest, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["schema_version", "label", "url", "utc_downloaded", "sha256", "raw_file"])
        w.writerow([SCHEMA_VERSION, label, url, stamp.isoformat(),
                    hashlib.sha256(r.content).hexdigest(), str(path.relative_to(ROOT))])
    return path


def load_fleet(cfg: dict) -> tuple[set[str], dict[str, float], dict]:
    """M10 fleet in National Grid IDs, with GC; counts of unmapped and no-GC units."""
    snaps = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))
    if not snaps:
        raise GateA2Error("No reference snapshot. Run `python -m src.ingest.reference`.")
    ref = json.loads(snaps[-1].read_bytes())
    ref = ref.get("data", ref) if isinstance(ref, dict) else ref
    ng_of = {str(r["elexonBmUnit"]): str(r.get("nationalGridBmUnit") or "") for r in ref}
    gc_of = {str(r["elexonBmUnit"]): float(r.get("generationCapacity") or 0) for r in ref}
    adoption = ROOT / cfg["fleet"]["gate_a1_adoption"]
    if not adoption.exists():
        raise GateA2Error("Gate A1 adoption table not found; run Gate A1 first.")
    with open(adoption) as f:
        elexon_ids = [r["bm_unit"] for r in csv.DictReader(f) if r["status"] == "adopted"]
    fleet, gc, counts = set(), {}, {"fleet_units": len(elexon_ids), "unmapped": 0, "no_gc": 0}
    for e in elexon_ids:
        ng = ng_of.get(e, "")
        if not ng:
            counts["unmapped"] += 1
            continue
        fleet.add(ng)
        if gc_of.get(e, 0) > 0:
            gc[ng] = gc_of[e]
        else:
            counts["no_gc"] += 1
    counts["reference_snapshot"] = str(snaps[-1].relative_to(ROOT))
    counts["reference_sha256"] = hashlib.sha256(snaps[-1].read_bytes()).hexdigest()
    return fleet, gc, counts


def fetch_mid(cfg: dict) -> list[dict]:
    el = cfg["elexon"]
    if not el["mid_from_param"] or not el["mid_to_param"]:
        raise GateA2Error("Fill elexon.mid_from_param / mid_to_param from `gate_a2 schema`.")
    months = cfg["window"]["months"]
    start = date.fromisoformat(months[0] + "-01")
    y, m = map(int, months[-1].split("-"))
    end = date(y + (m == 12), m % 12 + 1, 1)
    out, d = [], start
    while d < end:
        e = min(d + timedelta(days=el["mid_chunk_days"]), end)
        payload = _get_json(el["base_url"] + el["mid_path"],
                            {el["mid_from_param"]: d.isoformat(), el["mid_to_param"]: e.isoformat()})
        out += payload.get("data", payload) if isinstance(payload, dict) else payload
        d = e
    return dedupe_mid(out, el["field_provider"], el["field_time"])


def dedupe_mid(records: list[dict], f_provider: str, f_time: str) -> list[dict]:
    """One record per provider per half hour. Chunk windows include both ends, so
    each boundary half hour arrives twice; the later copy is kept."""
    seen: dict[tuple[str, str], dict] = {}
    for r in records:
        seen[(str(r[f_provider]), str(r[f_time]))] = r
    return [seen[k] for k in sorted(seen)]


def run(cfg: dict) -> dict:
    assert_locked()
    w, el = cfg["window"], cfg["elexon"]
    all_bm, psa, stages = resources_and_stages(cfg)
    stage = choose_stage(stages, w["stage"], w["fallback_stage"])
    fleet, gc, fleet_counts = load_fleet(cfg)
    gc_fleet = {u for u in fleet if u in gc}               # units without GC leave both sides
    mid = mid_by_half_hour(fetch_mid(cfg), el["field_time"], el["field_price"], el["field_volume"])
    ext = daily_extremes(mid, cfg["margin"]["local_tz"])

    raw, man = ROOT / "data" / "raw" / "neso", ROOT / "data" / "manifests" / "gate_a2_manifest.csv"
    tallies = {"all_bm": Tally(), "psa": Tally()}
    present: dict[str, set[str]] = defaultdict(set)
    neso_battery_outside_fleet: set[str] = set()
    for m in w["months"]:
        for key, res in (("all_bm", all_bm[m]), ("psa", psa[m])):
            path = download(res["url"], raw, man, f"{key}_{m}")
            with open(path, newline="") as f:
                # One streaming pass: monthly files can run to millions of rows.
                rows = csv.DictReader(f)
                if key == "all_bm":
                    rows = _note_presence(rows, m, gc_fleet, fleet, present,
                                          neso_battery_outside_fleet)
                t = value_skips(rows, stage, gc_fleet, mid, ext, cfg["margin"]["local_tz"])
            agg = tallies[key]
            agg.value_headline += t.value_headline
            agg.value_conservative += t.value_conservative
            agg.rows_used += t.rows_used
            agg.rows_no_mid += t.rows_no_mid
            agg.mwh_no_mid += t.mwh_no_mid
            for u, v in t.by_unit.items():
                agg.by_unit[u] += v

    mw_years, sens_mw = exposure(present, gc, w["months"])
    if mw_years <= 0:
        raise GateA2Error("Zero MW-years of exposure: fleet mapping or files are wrong.")
    point = tallies["all_bm"].value_headline / mw_years
    low = tallies["psa"].value_conservative / mw_years
    decision = decide(low, point, cfg)

    audit = ROOT / "data" / "interim" / "gate_a2_by_unit.csv"   # gitignored: names units
    audit.parent.mkdir(parents=True, exist_ok=True)
    with open(audit, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["schema_version", "bm_unit_ng", "gc_mw", "months_present", "all_bm_value_headline_gbp"])
        for u in sorted(gc_fleet):
            wr.writerow([SCHEMA_VERSION, u, gc[u], len(present.get(u, ())),
                         round(tallies["all_bm"].by_unit.get(u, 0.0), 2)])

    report = {
        "schema_version": SCHEMA_VERSION,
        "rule": "PROJECT.md §5A Gate A2 v1",
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "stage_used": stage,
        "stages_in_both_files": {m: sorted(s) for m, s in stages.items()},
        "window": [w["months"][0], w["months"][-1]],
        "fleet": {**fleet_counts, "scored_with_gc": len(gc_fleet),
                  "neso_battery_units_outside_fleet": len(neso_battery_outside_fleet)},
        "mw_years": round(mw_years, 2),
        "point_gbp_per_mw_year": round(point),
        "low_gbp_per_mw_year": round(low),
        "sensitivity_point_september_fleet": round(tallies["all_bm"].value_headline / sens_mw)
                                             if sens_mw else None,
        "rows_without_mid": {k: t.rows_no_mid for k, t in tallies.items()},
        "mwh_without_mid": {k: round(t.mwh_no_mid, 1) for k, t in tallies.items()},
        "decision": decision,
        "note": "Stakes gate only; not the Workstream B estimate (ASSUMPTIONS.md E6).",
    }
    out = ROOT / "outputs" / "gate_a2" / "gate_a2_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "schema":
        schema(load_config())
    elif cmd == "run":
        run(load_config())
    else:
        sys.exit("usage: python -m src.ingest.gate_a2 [schema|run]")
