"""Claim 2 contract screen, stage 1: find NESO's response and reserve auction results.

    python -m src.ingest.contract_sources discover

Stage 1 of three (PREREGISTRATION.md §4):
  1. discover (this script): which datasets hold auction results by unit for the
     products in scope, with their fields, row counts and date coverage. Metadata
     only: no auction units, no BM units, no volumes are printed.
  2. alias table: auction units listed, mapped to BM units or marked unmappable,
     committed with evidence before any coverage count exists.
  3. coverage: the counting rule committed, then run once (contract_coverage.py).

Products in scope: Dynamic Containment, Moderation and Regulation; Quick, Slow and
Balancing Reserve; STOR. Mandatory frequency response is searched for too, so the
open question in I13 can be settled from what NESO publishes.

Output: outputs/lock/contract_sources_discovery.json (metadata only; safe to commit).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.neso.energy/api/3/action"
SCHEMA_VERSION = "1.0"

SEARCHES = {
    "response_reserve_by_unit": "auction results by unit",
    "eac": "enduring auction capability results",
    "dynamic_containment": "dynamic containment",
    "dynamic_moderation": "dynamic moderation",
    "dynamic_regulation": "dynamic regulation",
    "quick_reserve": "quick reserve",
    "slow_reserve": "slow reserve",
    "balancing_reserve": "balancing reserve",
    "stor": "short term operating reserve",
    "mandatory_frequency_response": "mandatory frequency response",
}
DATE_HINT = re.compile(r"date|start|end|efa|delivery|period|time", re.I)


def date_fields(fields: list[dict]) -> list[str]:
    """Fields worth a min/max: typed as dates, or named like one."""
    return [f["id"] for f in fields
            if f["id"] != "_id" and (str(f.get("type", "")).startswith("timestamp")
                                     or str(f.get("type", "")) == "date"
                                     or DATE_HINT.search(f["id"]))]


def _get(action: str, **params) -> dict:
    import requests
    r = requests.get(f"{API}/{action}", params=params, timeout=120)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"{action} failed: {body.get('error')}")
    return body["result"]


def describe_resource(res: dict) -> dict:
    out = {"id": res["id"], "name": res.get("name"), "format": res.get("format"),
           "datastore_active": bool(res.get("datastore_active")),
           "last_modified": res.get("last_modified") or res.get("created")}
    if not out["datastore_active"]:
        return out
    meta = _get("datastore_search", resource_id=res["id"], limit=0)
    fields = [f for f in meta["fields"] if f["id"] != "_id"]
    out["fields"] = [{"id": f["id"], "type": f.get("type")} for f in fields]
    out["rows"] = meta.get("total")
    coverage = {}
    for f in date_fields(fields):
        sql = f'SELECT MIN("{f}") AS lo, MAX("{f}") AS hi FROM "{res["id"]}"'
        try:
            rec = _get("datastore_search_sql", sql=sql)["records"][0]
            coverage[f] = [rec.get("lo"), rec.get("hi")]
        except Exception as e:                     # a failed query is recorded, not hidden
            coverage[f] = f"query failed: {type(e).__name__}"
    out["date_coverage"] = coverage
    return out


def discover() -> dict:
    packages: dict[str, dict] = {}
    for key, q in SEARCHES.items():
        for p in _get("package_search", q=q, rows=20)["results"]:
            entry = packages.setdefault(p["name"], {"title": p.get("title"),
                                                    "matched_searches": [],
                                                    "metadata_modified": p.get("metadata_modified"),
                                                    "resources": p.get("resources", [])})
            entry["matched_searches"].append(key)
    for entry in packages.values():
        entry["resources"] = [describe_resource(r) for r in entry["resources"]]
    out = {"schema_version": SCHEMA_VERSION,
           "run_utc": datetime.now(timezone.utc).isoformat(),
           "api": API, "searches": SEARCHES,
           "packages": dict(sorted(packages.items()))}
    dest = ROOT / "outputs" / "lock" / "contract_sources_discovery.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, sort_keys=True))
    for name, p in out["packages"].items():
        print(f"\n{name}  [{', '.join(p['matched_searches'])}]\n  {p['title']}")
        for r in p["resources"]:
            cov = {k: v for k, v in (r.get("date_coverage") or {}).items()}
            print(f"  - {r['name']} ({r['format']}, rows={r.get('rows')}, id={r['id']})")
            if r.get("fields"):
                print(f"    fields: {[f['id'] for f in r['fields']]}")
            if cov:
                print(f"    dates: {cov}")
    print(f"\nWritten: {dest.relative_to(ROOT)}")
    return out


# ------------------------------------------------------------------ stage 2

# Results-by-unit resources for the window, chosen from the stage 1 discovery
# (outputs/lock/contract_sources_discovery.json, 2 Nov 2026). STOR is absent: NESO
# ceased STOR procurement with delivery on 31 Mar 2026, before the window.
RESOURCES = {
    "eac": {"id": "a63ab354-7e68-44c2-ad96-c6f920c30e85",
            "name": "NESO Response-Reserve Results By Unit",
            "unit": "auctionUnit", "party": "registeredAuctionParticipant",
            "tech": "technologyType", "place": "postCode",
            "product": "auctionProduct", "service": "serviceType",
            "start": "deliveryStart", "end": "deliveryEnd", "qty": "executedQuantity"},
    "sffr": {"id": "76bc5d39-c39f-490b-984e-58eb8ff296ef",
             "name": "Static Firm Frequency Response Auction Results",
             "unit": "Unit", "party": "Provider", "tech": "Technology Type",
             "place": "Location", "product": "Service", "service": "Status",
             "start": "Delivery Start", "end": "Delivery End", "qty": "Accepted Volume"},
}
WINDOW_START = "2026-06-22"          # Monday of 2026-W26, the earliest adoption week
UNIDENTIFIED_TECH = {"", "none", "null", "unknown", "other", "multi fuel type"}
AUTO_MIN_SCORE, AUTO_MIN_MARGIN = 0.5, 0.2


def in_scope(techs: set[str]) -> bool:
    """Battery, or technology the results do not identify (PREREGISTRATION §4)."""
    return any("batter" in t.lower() or "storage" in t.lower()
               or t.strip().lower() in UNIDENTIFIED_TECH for t in techs)


def auto_match(c: list[tuple[float, str]]) -> bool:
    """Proposed rule, for adjudication only: a clear, unique best candidate."""
    s1 = c[0][0] if c else 0.0
    s2 = c[1][0] if len(c) > 1 else 0.0
    return s1 >= AUTO_MIN_SCORE and s1 - s2 >= AUTO_MIN_MARGIN


STOP = {"battery", "bess", "storage", "energy", "ltd", "limited", "power", "solar",
        "the", "and", "of", "plc", "uk", "site", "unit", "park", "project"}


def _check_resource(key: str) -> dict:
    spec = RESOURCES[key]
    name = (_get("resource_show", id=spec["id"]).get("name") or "").strip()
    if name != spec["name"]:
        raise RuntimeError(f"{key}: resource {spec['id']} is now named {name!r}, "
                           f"expected {spec['name']!r}. Re-run discover and update RESOURCES.")
    return spec


def _sql(sql: str) -> list[dict]:
    return _get("datastore_search_sql", sql=sql)["records"]


def categories() -> dict:
    """Category values with row counts in the window: products, services, technologies.

    No auction units or volumes. Decides which products count and how
    technology is labelled, before the counting rule is written.
    """
    out = {}
    for key in RESOURCES:
        spec = _check_resource(key)
        q = lambda col: _sql(  # noqa: E731
            f'SELECT "{col}" AS v, COUNT(*) AS n, MIN("{spec["start"]}") AS lo, '
            f'MAX("{spec["start"]}") AS hi FROM "{spec["id"]}" '
            f'WHERE "{spec["start"]}" >= \'{WINDOW_START}\' GROUP BY 1 ORDER BY 2 DESC')
        out[key] = {col: q(spec[col]) for col in ("service", "product", "tech")}
    _write("contract_categories.json", out)
    for key, cols in out.items():
        for col, rows in cols.items():
            print(f"\n{key} / {RESOURCES[key][col]}")
            for r in rows:
                print(f"  {r['n']:>9}  {r['v']}   [{r['lo']} .. {r['hi']}]")
    return out


def tokens(s: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (s or "").lower())
    return {w for w in words if w not in STOP and len(w) > 1}


def similarity(a: str | None, b: str | None) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def candidates(auction: dict, bm_units: list[dict], name_fields: list[str],
               party_field: str | None, k: int = 3) -> list[tuple[float, str]]:
    """Top-k fleet BM units by name similarity, plus a bonus when the parties overlap."""
    scored = []
    for b in bm_units:
        s = max((similarity(auction["unit"], b.get(f)) for f in name_fields), default=0.0)
        if party_field and similarity(auction["party"], b.get(party_field)) > 0:
            s += 0.25
        if s > 0:
            scored.append((round(s, 3), str(b["elexonBmUnit"])))
    return sorted(scored, reverse=True)[:k]


def units() -> dict:
    """List auction units with awards in the window and draft fleet BM unit candidates.

    Writes the full list to data/interim/contract/ (gitignored: it names units).
    Prints counts only. The draft is for adjudication: each row is decided as a
    fleet BM unit, "not_fleet" (with evidence) or "unmappable", and the result is
    committed as config/contract_alias.csv before any coverage count is computed.
    """
    import csv
    snaps = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))
    adoption = ROOT / "outputs" / "gate_a1" / "adoption_dates.csv"
    if not snaps or not adoption.exists():
        raise SystemExit("Need a reference snapshot and outputs/gate_a1/adoption_dates.csv.")
    payload = json.loads(snaps[-1].read_bytes())
    ref = payload.get("data", payload) if isinstance(payload, dict) else payload
    with open(adoption) as f:
        fleet = {r["bm_unit"] for r in csv.DictReader(f) if r["status"] == "adopted"}
    # The snapshot can hold several records per unit; keep one per elexonBmUnit.
    bm_units = list({str(r["elexonBmUnit"]): r for r in ref
                     if str(r.get("elexonBmUnit")) in fleet}.values())
    from src.ingest.lock_counts import full_weeks_after
    with open(adoption) as f:
        eligible = {r["bm_unit"] for r in csv.DictReader(f)
                    if r["status"] == "adopted" and full_weeks_after(r["cohort"]) >= 4}
    fields = sorted({k for r in ref for k in r})
    name_fields = [f for f in fields if re.search(r"name|bmunit", f, re.I)
                   and not re.search(r"party|gsp|type", f, re.I)]
    party_field = next((f for f in fields if f.lower() == "leadpartyname"), None)

    rows = []
    for key in RESOURCES:
        spec = _check_resource(key)
        recs = _sql(
            f'SELECT "{spec["party"]}" AS party, "{spec["unit"]}" AS unit, '
            f'"{spec["tech"]}" AS tech, "{spec["place"]}" AS place, '
            f'"{spec["product"]}" AS product, COUNT(*) AS n, '
            f'MIN("{spec["start"]}") AS first, MAX("{spec["end"]}") AS last '
            f'FROM "{spec["id"]}" WHERE "{spec["start"]}" >= \'{WINDOW_START}\' '
            f'GROUP BY 1, 2, 3, 4, 5')
        merged: dict[tuple, dict] = {}
        for r in recs:
            m = merged.setdefault((r["party"], r["unit"]), {
                "source": key, "party": r["party"], "unit": r["unit"], "tech": set(),
                "place": set(), "products": set(), "rows": 0, "first": r["first"],
                "last": r["last"]})
            m["tech"].add(str(r["tech"])); m["place"].add(str(r["place"]))
            m["products"].add(str(r["product"])); m["rows"] += int(r["n"])
            m["first"] = min(m["first"], r["first"]); m["last"] = max(m["last"], r["last"])
        rows += merged.values()

    dest = ROOT / "data" / "interim" / "contract" / "alias_draft.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "registered_participant", "auction_unit", "technology",
                    "location", "products", "award_rows", "first_delivery", "last_delivery",
                    "candidate_1", "score_1", "candidate_2", "score_2", "candidate_3", "score_3",
                    "in_scope", "candidate_1_eligible", "auto_rule",
                    "decision", "bm_unit", "evidence"])
        for r in sorted(rows, key=lambda r: (r["source"], str(r["party"]), str(r["unit"]))):
            c = candidates(r, bm_units, name_fields, party_field)
            r["scope"], r["auto"] = in_scope(r["tech"]), auto_match(c)
            r["elig"] = bool(c) and c[0][1] in eligible
            c += [("", "")] * (3 - len(c))
            w.writerow([r["source"], r["party"], r["unit"], ";".join(sorted(r["tech"])),
                        ";".join(sorted(r["place"])), ";".join(sorted(r["products"])),
                        r["rows"], r["first"], r["last"],
                        c[0][1], c[0][0], c[1][1], c[1][0], c[2][1], c[2][0],
                        r["scope"], r["elig"], r["auto"], "", "", ""])
    scope = [r for r in rows if r["scope"]]
    tech = Counter(";".join(sorted(r["tech"])) for r in rows)
    summary = {"window_start": WINDOW_START, "reference_name_fields": name_fields,
               "reference_party_field": party_field, "fleet_bm_units": len(bm_units),
               "eligible_bm_units": len(eligible),
               "auction_units": dict(Counter(r["source"] for r in rows)),
               "auction_units_by_technology": dict(tech.most_common()),
               "registered_participants": len({r["party"] for r in rows}),
               "in_scope": len(scope),
               "in_scope_participants": len({r["party"] for r in scope}),
               "in_scope_auto_rule": sum(r["auto"] for r in scope),
               "in_scope_top_candidate_eligible": sum(r["elig"] for r in scope),
               "in_scope_auto_rule_and_eligible": sum(r["auto"] and r["elig"] for r in scope),
               "auto_rule": {"min_score": AUTO_MIN_SCORE, "min_margin": AUTO_MIN_MARGIN}}
    _write("contract_units_summary.json", summary)
    print(json.dumps(summary, indent=2))
    print(f"\nDraft for adjudication (gitignored): {dest.relative_to(ROOT)}")
    return summary


def _write(name: str, obj) -> None:
    dest = ROOT / "outputs" / "lock" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    cmd = (sys.argv[1:] or [""])[0]
    commands = {"discover": discover, "categories": categories, "units": units}
    if cmd not in commands:
        sys.exit("usage: python -m src.ingest.contract_sources [discover|categories|units]")
    commands[cmd]()
