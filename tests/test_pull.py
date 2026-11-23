"""The scoring-window pull module's shared pieces and probe, with a fake network.

Nothing here touches Elexon or NESO: every response is canned.
"""

import csv
import hashlib
import json
import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.ingest import pull
from src.ingest.pull import (
    PullError,
    Request,
    b1610_request,
    boav_request,
    dates_and_periods,
    get_with_retry,
    json_type,
    load_fleet,
    overlap,
    probe,
    rows_of,
    save,
    schema,
    settlement_dates,
    stream_request,
)

D = date(2026, 10, 14)
NOW = datetime(2026, 11, 23, 18, 0, tzinfo=UTC)


def test_stream_request_is_one_settlement_date() -> None:
    r = stream_request("PN", D, ["U2", "U1"])
    q = urllib.parse.parse_qsl(urllib.parse.urlsplit(r.url).query)
    assert q == [
        ("from", "2026-10-14"),
        ("to", "2026-10-14"),
        ("settlementPeriodFrom", "1"),
        ("settlementPeriodTo", "50"),
        ("bmUnit", "U1"),
        ("bmUnit", "U2"),
    ]
    assert r.url.startswith("https://data.elexon.co.uk/bmrs/api/v1/datasets/PN/stream?")
    with pytest.raises(PullError):
        stream_request("B1610", D, [])


def test_public_url_and_manifest_keep_unit_ids_out() -> None:
    r = stream_request("BOALF", D, ["U2", "U1"])
    assert "U1" in r.url and "U1" not in r.public_url
    assert r.units == ("U1", "U2")
    assert r.units_sha256 == hashlib.sha256(b"U1\nU2").hexdigest()


def test_b1610_asks_for_every_run_type() -> None:
    r = b1610_request(D, ["U1"])
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.url).query))
    assert q["settlementDateFrom"] == q["settlementDateTo"] == "2026-10-14"
    assert "settlementRunType" not in q


def test_boav_path() -> None:
    assert boav_request(D, "offer").url.endswith(
        "/balancing/settlement/acceptance/volumes/all/offer/2026-10-14?"
    )
    with pytest.raises(PullError):
        boav_request(D, "both")


def test_settlement_dates_cover_both_ends() -> None:
    days = settlement_dates(date(2026, 10, 24), date(2026, 10, 26))
    assert days == [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)]
    with pytest.raises(PullError):
        settlement_dates(D, date(2026, 10, 1))


def test_retry_then_raise() -> None:
    calls: list[str] = []

    def flaky(url: str) -> bytes:
        calls.append(url)
        if len(calls) < 2:
            raise OSError("reset")
        return b"[]"

    assert get_with_retry(flaky, "u", tries=3, wait_s=0) == b"[]"
    assert len(calls) == 2

    def broken(url: str) -> bytes:
        raise OSError("down")

    with pytest.raises(PullError):
        get_with_retry(broken, "u", tries=2, wait_s=0)


def test_rows_from_list_or_wrapper() -> None:
    assert rows_of(b'[{"a": 1}]') == [{"a": 1}]
    assert rows_of(b'{"data": [{"a": 1}]}') == [{"a": 1}]
    with pytest.raises(PullError):
        rows_of(b'{"x": 1}')
    with pytest.raises(PullError):
        rows_of(b"[1, 2]")


def test_save_writes_raw_and_manifest(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw" / "pull"
    manifest = tmp_path / "data" / "manifests" / "pull_manifest.csv"
    body = b'[{"settlementDate": "2026-10-14"}, {"settlementDate": "2026-10-14"}]'
    row = save(stream_request("PN", D, ["U1"]), body, NOW, raw, manifest)
    save(stream_request("PN", D, ["U1"]), body, NOW, raw, manifest)
    with manifest.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2 and rows[0] == row
    assert row["rows"] == "2" and row["units"] == "1"
    assert row["sha256"] == hashlib.sha256(body).hexdigest()
    assert "U1" not in json.dumps(rows)
    assert (tmp_path / row["raw_file"]).read_bytes() == body


def test_fleet_loader(tmp_path: Path) -> None:
    path = tmp_path / "adoption.csv"
    rows = [("U2", "adopted"), ("U1", "adopted"), ("U3", "excluded(fuel_type_PS)")]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["schema_version", "bm_unit", "status", "fuel_type"])
        w.writerows(("1.0", u, s, "") for u, s in rows)
    assert load_fleet(path, expected=2) == ["U1", "U2"]
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("unit,status\nU1,adopted\n")
    with pytest.raises(PullError, match="bm_unit"):
        load_fleet(wrong, expected=1)
    with pytest.raises(PullError):
        load_fleet(path, expected=163)
    with pytest.raises(PullError):
        load_fleet(tmp_path / "missing.csv")


def test_schema_reports_names_and_types_never_values() -> None:
    rows = [
        {"quantity": 12.5, "bmUnit": "SECRET-1", "flag": True, "x": None},
        {"quantity": 3, "bmUnit": "SECRET-2", "flag": False, "x": [1]},
    ]
    s = schema(rows)
    assert s == {
        "bmUnit": ["string"],
        "flag": ["boolean"],
        "quantity": ["number"],
        "x": ["array", "null"],
    }
    text = json.dumps(s)
    assert "SECRET" not in text and "12.5" not in text
    assert json_type({}) == "object"


def test_dates_periods_and_overlap() -> None:
    a = [
        {"settlementDate": "2026-10-14", "settlementPeriod": 1},
        {"settlementDate": "2026-10-14", "settlementPeriod": 48},
    ]
    b = [{"settlementDate": "2026-10-15", "settlementPeriodFrom": 1}, a[1]]
    assert dates_and_periods(a) == {
        "settlement_dates": ["2026-10-14"],
        "period_min": 1,
        "period_max": 48,
    }
    assert dates_and_periods([]) == {
        "settlement_dates": [],
        "period_min": None,
        "period_max": None,
    }
    assert overlap(a, b) == 1


def fake_network(url: str) -> bytes:
    """Canned responses: Elexon rows by settlement date; NESO package and fields."""
    if "package_show" in url:
        return json.dumps(
            {
                "result": {
                    "resources": [
                        {"id": "r2025", "name": "Historic demand data 2025"},
                        {"id": "r2026", "name": "Historic demand data 2026"},
                    ]
                }
            }
        ).encode()
    if "datastore_search" in url:
        assert "r2026" in url and "limit=0" in url
        fields = [
            {"id": "SETTLEMENT_DATE", "type": "text"},
            {"id": "PUMP", "type": "int"},
        ]
        return json.dumps({"result": {"fields": fields, "records": []}}).encode()
    if "/acceptance/volumes/" in url:
        if "/offer/" in url:
            raise OSError("404")
        return b'{"data": [{"settlementDate": "2026-10-14", "settlementPeriod": 3}]}'
    day = "2026-10-15" if "2026-10-15" in url else "2026-10-14"
    return json.dumps(
        [
            {
                "settlementDate": day,
                "settlementPeriod": 1,
                "levelFrom": 7,
                "bmUnit": "U1",
            },
            {
                "settlementDate": day,
                "settlementPeriod": 50,
                "levelFrom": 9,
                "bmUnit": "U1",
            },
        ]
    ).encode()


def test_probe_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pull, "RETRY_WAIT_S", 0.0)
    raw = tmp_path / "data" / "raw" / "pull"
    manifest = tmp_path / "data" / "manifests" / "pull_manifest.csv"
    out = probe(fake_network, lambda: NOW, ["U3", "U1", "U2", "U4"], raw, manifest)
    endpoints = out["endpoints"]
    assert isinstance(endpoints, dict)
    assert set(endpoints) == {
        "MDO",
        "MDB",
        "PN",
        "BOALF",
        "B1610",
        "BOAV_bid",
        "BOAV_offer",
    }
    pn = endpoints["PN"]
    assert pn["2026-10-14"]["settlement_dates"] == ["2026-10-14"]
    assert pn["2026-10-14"]["period_max"] == 50
    assert pn["rows_in_both_days"] == 0
    assert endpoints["BOAV_offer"]["2026-10-14"] == {"error": "failed after 3 tries"}
    assert out["units_sampled"] == 3
    neso = out["neso_historic_demand"]
    assert neso == {
        "Historic demand data 2026": {
            "resource_id": "r2026",
            "fields": {"SETTLEMENT_DATE": "text", "PUMP": "int"},
        }
    }
    text = json.dumps(out)
    assert "U1" not in text and '"levelFrom": 7' not in text
    with manifest.open() as f:
        assert len(list(csv.DictReader(f))) == 12  # 6 endpoints answered, 2 days each


def test_neso_without_a_2026_resource_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_2026(url: str) -> bytes:
        return b'{"result": {"resources": [{"id": "r", "name": "Historic 2025"}]}}'

    with pytest.raises(PullError):
        pull.neso_demand_schema(no_2026)


def test_request_is_hashable_and_fixed() -> None:
    r = Request("X", D, "/p", (("a", "1"),))
    assert r.units == () and r.public_url == r.url
