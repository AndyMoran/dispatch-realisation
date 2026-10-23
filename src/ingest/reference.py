"""Snapshot of BMRS BM unit reference data: lead party, fuel type, capacities.

    python -m src.ingest.reference

Saves the response as downloaded, writes a manifest row, and prints a short
inventory: field names, record count, fuel types, and how many records carry
each capacity field. Prints no per-unit rows. Pinned snapshots, not "latest",
feed the registered-MW denominator and the optimiser map (DATA_SOURCES.md).

Outputs (gitignored raw; manifest committed):
    data/raw/reference/bmunits__dl<UTC>.json
    data/manifests/reference_manifest.csv
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]
URL = "https://data.elexon.co.uk/bmrs/api/v1/reference/bmunits/all"
CAPACITY_HINTS = ("capacity", "gc", "dc", "registered")


def _get(url: str) -> bytes:
    import requests
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def inventory(rows: list[dict]) -> dict:
    """Shape of the snapshot only: no per-unit output."""
    fields = sorted({k for r in rows for k in r})
    capacity_fields = [f for f in fields if any(h in f.lower() for h in CAPACITY_HINTS)]
    fuel_key = next((f for f in fields if f.lower() == "fueltype"), None)
    return {
        "records": len(rows),
        "fields": fields,
        "capacity_fields_populated": {
            f: sum(1 for r in rows if r.get(f) not in (None, "", 0)) for f in capacity_fields},
        "fuel_types": dict(sorted(Counter(str(r.get(fuel_key)) for r in rows).items()))
                      if fuel_key else "no fuelType field",
    }


def snapshot() -> dict:
    body = _get(URL)
    downloaded = datetime.now(timezone.utc)
    payload = json.loads(body)
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    raw = ROOT / "data" / "raw" / "reference" / f"bmunits__dl{downloaded:%Y%m%dT%H%M%S}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(body)
    man = ROOT / "data" / "manifests" / "reference_manifest.csv"
    man.parent.mkdir(parents=True, exist_ok=True)
    new = not man.exists()
    with open(man, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["schema_version", "url", "utc_downloaded", "sha256", "rows", "raw_file"])
        w.writerow([SCHEMA_VERSION, URL, downloaded.isoformat(),
                    hashlib.sha256(body).hexdigest(), len(rows), str(raw.relative_to(ROOT))])
    out = {"snapshot_utc": downloaded.isoformat(), **inventory(rows)}
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    snapshot()
