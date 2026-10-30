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


if __name__ == "__main__":
    if (sys.argv[1:] or [""])[0] != "discover":
        sys.exit("usage: python -m src.ingest.contract_sources discover")
    discover()
