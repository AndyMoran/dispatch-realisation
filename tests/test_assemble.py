"""Assembly of fleet inputs and the counts-only check, on a made-up repository.

Every file is written to a temporary folder; nothing touches Elexon or the real
raw data. The pulls are made by the real pull code with a fake network.
"""

import csv
import hashlib
import json
import urllib.parse
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.ingest import assemble as asm
from src.ingest import pull
from src.ingest.assemble import (
    AssemblyError,
    gap_bucket,
    pn_gaps,
    pn_overlaps,
    registered_mw,
    week_start_of,
)
from src.model.types import LevelSegment

NOW = datetime(2026, 11, 23, 21, 0, tzinfo=UTC)
FLEET = ("U1", "U2")
ENTRIES = ("None", "U1", "U2")  # as Gate A1 listed them: the null bucket included


def z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def at(day: int, hour: int = 0, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def sub(unit: str, t: datetime, level: float, published: datetime) -> dict[str, object]:
    return {
        "bmUnit": unit,
        "timeFrom": z(t),
        "timeTo": z(t + timedelta(minutes=30)),
        "levelFrom": level,
        "levelTo": level,
        "publishTime": z(published),
        "serialNumber": "7",
    }


BOUNDARY = sub("U1", at(30, 0, 10), 40.0, at(29, 23, 10))  # in both sources


# ------------------------------------------------------------------ the fixture


def write_json(path: Path, rows: list[dict[str, object]]) -> str:
    body = json.dumps({"data": rows}).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def fake_elexon(url: str) -> bytes:
    """The pulls' responses: a few records, empty elsewhere."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    rows: list[dict[str, object]] = []
    if "/MDO/" in url and q["from"].startswith("2026-10-30"):
        rows = [
            BOUNDARY,
            sub("U1", at(2, 9), 35.0, at(2, 8)),
            sub("U9", at(2, 9), 1, at(2, 8)),
            {**sub("U1", at(2, 9), 1, at(2, 8)), "bmUnit": None},  # no bmUnit
        ]
    if "/PN/" in url and q["from"] in ("2026-11-02", "2026-11-03"):
        day = int(q["from"][-2:])
        rows = [
            {
                "bmUnit": "U1",
                "timeFrom": z(at(day, 0)),
                "timeTo": z(at(day, 20)),  # 4 h uncovered each day
                "levelFrom": -10,
                "levelTo": -10,
            }
        ]
    if "/BOALF/" in url and q["from"] in ("2026-11-04", "2026-11-05"):
        rows = [  # one instruction across midnight, in both days' chunks
            {
                "bmUnit": "U1",
                "timeFrom": z(at(4, 23)),
                "timeTo": z(at(5, 1)),
                "levelFrom": 20,
                "levelTo": 20,
                "acceptanceNumber": 5,
                "acceptanceTime": z(at(4, 22)),
            }
        ]
    if "/B1610/" in url and q["settlementDateFrom"] == "2026-11-04":
        rows = [
            {
                "bmUnit": "U1",
                "settlementDate": "2026-11-04",
                "settlementPeriod": 10,
                "quantity": 3.5,
                "settlementRunType": "SF",
            }
        ]
    return json.dumps({"data": rows}).encode()


def build_repo(
    root: Path, monkeypatch: pytest.MonkeyPatch, meter: bool = False
) -> None:
    """Write a two-unit fleet, a reference snapshot, Gate A1's runs and the pulls."""
    adoption = root / asm.ADOPTION_CSV
    adoption.parent.mkdir(parents=True)
    with adoption.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["schema_version", "bm_unit", "status", "cohort", "first_real_utc"])
        w.writerow(
            ["1.0", "U1", "adopted", "2026-W44", "2026-10-27T09:00:00+00:00"]
        )  # first scored week 2 Nov
        w.writerow(
            ["1.0", "U2", "adopted", "2026-W46", "2026-11-10T12:30:00+00:00"]
        )  # no complete week by 16 Nov
        w.writerow(["1.0", "X1", "excluded", "2026-W30", ""])
        w.writerow(
            ["1.0", "None", "adopted", "2026-W44", "2026-10-28T00:00:00+00:00"]
        )  # the null-bmUnit bucket
    reference: list[dict[str, object]] = [
        {
            "elexonBmUnit": "U1",
            "generationCapacity": "50",
            "demandCapacity": "-50",
            "leadPartyName": "Lead A",
            "bmUnitType": "T",
        },
        {
            "elexonBmUnit": "U2",
            "generationCapacity": 0,
            "demandCapacity": -20,
            "leadPartyName": "Lead B",
            "bmUnitType": "V",
        },
        {"elexonBmUnit": "U9", "generationCapacity": 9},
    ]
    sha = write_json(root / asm.REFERENCE_FILE, reference)
    monkeypatch.setattr(asm, "REFERENCE_SHA256", sha)

    manifest = root / asm.GATE_A1_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "schema_version",
                "dataset",
                "url",
                "params",
                "utc_downloaded",
                "sha256",
                "rows",
                "raw_file",
            ]
        )
        for ds in ("MDO", "MDB"):
            for d in pull.settlement_dates(*asm.GATE_A1_DAYS):
                for run, extra in (("20261027T1200", "early"), ("20261030T1200", "")):
                    rows: list[dict[str, object]] = []
                    if ds == "MDO" and d == date(2026, 10, 29) and not extra:
                        rows = [BOUNDARY, sub("U1", at(29, 6, 10), 30.0, at(29, 5, 10))]
                    if extra and ds == "MDO" and d == date(2026, 10, 1):
                        rows = [
                            sub("U1", at(1, 6, 10), 999.0, at(1, 5, 10))
                        ]  # never read
                    rel = f"data/raw/mdo_mdb/{ds}/{d:%Y%m%d}__dl{run}.json"
                    h = write_json(root / rel, rows)
                    params = json.dumps(
                        {
                            "from": f"{d}T00:00Z",
                            "to": f"{d + timedelta(days=1)}T00:00Z",
                        },
                        sort_keys=True,
                    )
                    when = (
                        "2026-10-27T12:00:00+00:00"
                        if extra
                        else "2026-10-30T12:00:00+00:00"
                    )
                    w.writerow(["1.0", ds, "u", params, when, h, len(rows), rel])

    raw = root / "data" / "raw" / "pull"
    pull_manifest = root / "data" / "manifests" / "pull_manifest.csv"
    names = ["mdo-mdb", "pn", "boalf", *(["b1610"] if meter else [])]
    for name in names:
        report = pull.run_requests(
            name,
            pull.plan(name, FLEET if name == "b1610" else ENTRIES),  # as pulled
            fake_elexon,
            lambda: NOW,
            raw,
            pull_manifest,
            0,
        )
        assert report["complete"]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    build_repo(tmp_path, monkeypatch, meter=True)
    return tmp_path


# ------------------------------------------------------------------ pieces


def test_week_start_of() -> None:
    assert week_start_of("2026-W44") == at(26, 0, 10)
    for bad in ("2026-44", "x", "2026-W60"):
        with pytest.raises(AssemblyError):
            week_start_of(bad)


def test_registered_mw_follows_m16() -> None:
    assert registered_mw({"generationCapacity": "50", "demandCapacity": "-60"}) == 50
    assert registered_mw({"generationCapacity": 0, "demandCapacity": -20}) == 20
    assert registered_mw({"generationCapacity": None, "demandCapacity": ""}) is None
    assert registered_mw({}) is None
    with pytest.raises(AssemblyError):
        registered_mw({"generationCapacity": "fifty"})
    with pytest.raises(AssemblyError):
        registered_mw({"generationCapacity": True})


def seg(start: datetime, hours: float) -> LevelSegment:
    return LevelSegment(start, start + timedelta(hours=hours), -1, -1)


def test_pn_gaps_and_overlaps() -> None:
    start, end = at(2), at(3)
    assert pn_gaps([seg(at(1), 48)], start, end) == []
    assert pn_gaps([], start, end) == [timedelta(days=1)]
    gaps = pn_gaps([seg(at(2, 2), 3), seg(at(2, 4), 2), seg(at(2, 10), 20)], start, end)
    assert gaps == [timedelta(hours=2), timedelta(hours=4)]
    tail = pn_gaps([seg(at(2, 0), 20)], start, end)
    assert tail == [timedelta(hours=4)]
    assert pn_overlaps([seg(at(2, 2), 3), seg(at(2, 4), 2), seg(at(2, 10), 2)]) == 1
    assert pn_overlaps([seg(at(2, 0), 5), seg(at(2, 1), 1), seg(at(2, 3), 1)]) == 2
    assert gap_bucket(timedelta(minutes=29)) == "under 30 min"
    assert gap_bucket(timedelta(minutes=30)) == "30 min to 6 h"
    assert gap_bucket(timedelta(hours=6)) == "6 h to 24 h"
    assert gap_bucket(timedelta(hours=24)) == "24 h or more"


# ------------------------------------------------------------------ assembly


def test_assembly_reads_only_the_pinned_chunks(repo: Path) -> None:
    a = asm.assemble(repo, with_meter=True, entries=3, bm_units=2)
    u1, u2 = a.inputs["U1"], a.inputs["U2"]
    levels = sorted(s.level_from_mwh for s in u1.submissions)
    assert levels == [30.0, 35.0, 40.0]  # 27 Oct run never read; boundary once
    assert a.counts["MDO"].duplicate_records == 1
    assert a.counts["MDO"].rows_outside_fleet == 2  # U9, and a row with no bmUnit
    assert sorted(a.units) == ["U1", "U2"] and a.adoption_entries == 3
    assert a.counts["MDO"].files == 127 + 18
    assert len(u1.pn) == 2 and len(u1.boas) == 1
    assert a.counts["BOALF"].duplicate_records == 1
    assert [m.net_mwh for m in u1.meter] == [3.5]
    assert u2.submissions == () and u2.meter == ()
    assert a.units["U1"].registered_mw == 50 and not a.units["U1"].secondary
    assert a.units["U2"].registered_mw == 20 and a.units["U2"].secondary
    assert a.units["U2"].lead_party == "Lead B"
    assert a.units["U1"].adopted_at == datetime(2026, 10, 27, 9, tzinfo=UTC)
    with pytest.raises(AssemblyError, match="first non-default"):
        asm.adoption_instant("")
    with pytest.raises(AssemblyError, match="not in UTC"):
        asm.adoption_instant("2026-10-27T09:00:00+01:00")
    assert a.chunks_held_twice == {"b1610": 0, "boalf": 0, "mdo-mdb": 0, "pn": 0}


def test_probe_chunks_are_never_read(repo: Path) -> None:
    probe = pull.stream_request("PN", date(2026, 11, 2), ["U1"])  # a 1-unit chunk
    body = json.dumps(
        {
            "data": [
                {
                    "bmUnit": "U1",
                    "timeFrom": z(at(2)),
                    "timeTo": z(at(3)),
                    "levelFrom": 1,
                    "levelTo": 1,
                }
            ]
        }
    )
    pull.save(
        probe,
        body.encode(),
        NOW,
        repo / "data/raw/pull",
        repo / "data/manifests/pull_manifest.csv",
    )
    a = asm.assemble(repo, with_meter=True, entries=3, bm_units=2)
    assert len(a.inputs["U1"].pn) == 2


def test_check_report_counts_only(repo: Path) -> None:
    code = asm.main(["check"], root=repo, entries=3, bm_units=2)
    assert code == 0
    report = json.loads((repo / asm.CHECK_OUT).read_text())
    text = json.dumps(report)
    for secret in ("U1", "U2", "Lead A", "Lead B", "40.0", "35.0"):
        assert secret not in text
    pn = report["pn_m24"]
    # U1: window 2–16 Nov; PN covers 2 Nov 00–20 and 3 Nov 00–20.
    assert pn["units_with_a_window"] == 1 and pn["units_without_a_window"] == 1
    assert pn["gaps"] == 2 and pn["units_with_a_gap"] == 1
    assert pn["gaps_by_length"] == {
        "under 30 min": 0,
        "30 min to 6 h": 1,
        "6 h to 24 h": 0,
        "24 h or more": 1,
    }
    assert pn["gap_hours"] == 4 + (12 * 24 + 4)  # 2 Nov 20–24; 3 Nov 20 to 16 Nov
    assert report["units"] == 2 and report["secondary_units"] == 1
    assert report["fleet"] == {
        "adoption_entries_as_pulled": 3,
        "null_bmunit_buckets_dropped": 1,
        "bm_units": 2,
    }
    cover = report["pull_coverage_by_batch"]
    assert cover["PN"] == [
        {"batch": 1, "bm_units": 2, "bm_units_with_rows": 1, "holds_null_bucket": True}
    ]
    assert cover["MDO"][0]["bm_units_with_rows"] == 1
    assert cover["MDB"][0]["bm_units_with_rows"] == 0
    assert report["units_with_no_records"] == {"MDO/MDB": 1, "PN": 1, "BOALF": 1}
    assert "B1610" not in report["datasets"]
    assert asm.main(["score"], root=repo, entries=3, bm_units=2) == 2


def test_check_runs_without_any_b1610(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_repo(tmp_path, monkeypatch, meter=False)
    a = asm.assemble(tmp_path, with_meter=False, entries=3, bm_units=2)
    assert all(i.meter == () for i in a.inputs.values())
    with pytest.raises(AssemblyError, match="b1610"):
        asm.assemble(tmp_path, with_meter=True, entries=3, bm_units=2)


# ------------------------------------------------------------------ it stops


def tamper(path: Path) -> None:
    path.write_bytes(path.read_bytes().replace(b"]", b", {}]", 1))


def gate_file(root: Path, day: str, run: str = "20261030T1200") -> Path:
    return root / f"data/raw/mdo_mdb/MDO/{day}__dl{run}.json"


def rewrite_manifest(path: Path, keep: Callable[[dict[str, str]], bool]) -> None:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = [r for r in reader if keep(r)]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def test_a_changed_file_stops(repo: Path) -> None:
    tamper(gate_file(repo, "20261029"))
    with pytest.raises(AssemblyError, match="SHA-256"):
        asm.assemble(repo, entries=3, bm_units=2)


def test_a_missing_gate_a1_day_stops(repo: Path) -> None:
    rewrite_manifest(
        repo / asm.GATE_A1_MANIFEST,
        lambda r: (
            not (
                r["params"].startswith('{"from": "2026-07-01')
                and r["utc_downloaded"].startswith("2026-10-30")
            )
        ),
    )
    with pytest.raises(AssemblyError, match="252 of 254"):
        asm.assemble(repo, entries=3, bm_units=2)


def test_a_missing_pull_chunk_stops(repo: Path) -> None:
    rewrite_manifest(
        repo / "data/manifests/pull_manifest.csv",
        lambda r: not (r["dataset"] == "PN" and "2026-08-01" in r["url"]),
    )
    with pytest.raises(AssemblyError, match="pn: 1 planned chunks"):
        asm.assemble(repo, entries=3, bm_units=2)


def test_reference_problems_stop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asm, "REFERENCE_SHA256", "0" * 64)
    with pytest.raises(AssemblyError, match="SHA-256"):
        asm.assemble(repo, entries=3, bm_units=2)
    rows = [{"elexonBmUnit": "U1"}, {"elexonBmUnit": "U1"}, {"elexonBmUnit": "U2"}]
    with pytest.raises(AssemblyError, match="2 reference rows"):
        asm.fleet_units(repo / asm.ADOPTION_CSV, rows, FLEET)
    with pytest.raises(AssemblyError, match="0 reference rows"):
        asm.fleet_units(repo / asm.ADOPTION_CSV, rows[:1], FLEET)


def test_two_meter_values_for_one_period_stop(repo: Path) -> None:
    manifest = repo / "data/manifests/pull_manifest.csv"
    with manifest.open(newline="") as f:
        row = next(
            r
            for r in csv.DictReader(f)
            if r["dataset"] == "B1610" and "2026-11-05" in r["url"]
        )
    path = repo / row["raw_file"]
    rows = [
        {
            "bmUnit": "U1",
            "settlementDate": "2026-11-04",
            "settlementPeriod": 10,
            "quantity": 9.0,
            "settlementRunType": "R1",
        }
    ]
    sha = write_json(path, rows)
    with manifest.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows_out = [
            {**r, "sha256": sha} if r["raw_file"] == row["raw_file"] else r
            for r in reader
        ]
    with manifest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)
    with pytest.raises(AssemblyError, match="two values"):
        asm.assemble(repo, entries=3, bm_units=2)


def test_the_null_bucket_is_never_a_unit(repo: Path) -> None:
    rows: list[dict[str, object]] = [
        {"elexonBmUnit": None, "generationCapacity": 5},
        {"elexonBmUnit": "", "generationCapacity": 5},
        {"elexonBmUnit": "U1"},
        {"elexonBmUnit": "U2"},
    ]
    units = asm.fleet_units(repo / asm.ADOPTION_CSV, rows, FLEET)
    assert sorted(units) == ["U1", "U2"]
    with pytest.raises(AssemblyError, match="null-bmUnit bucket"):
        asm.fleet_units(repo / asm.ADOPTION_CSV, rows, ENTRIES)
    with pytest.raises(AssemblyError, match="2 BM units, not 3"):
        asm.assemble(repo, entries=3, bm_units=3)
