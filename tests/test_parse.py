"""Raw rows to model types, by the field mapping of 23 Nov 2026 (`src/ingest/parse.py`).

Every row here is hand-built in the shape the probes showed; none comes from a pull.
"""

from datetime import UTC, datetime

import pytest

from src.ingest.parse import (
    FieldError,
    instant,
    parse_meter,
    parse_segments,
    parse_submissions,
    unique_rows,
    whole,
)


def at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 10, 14, h, m, tzinfo=UTC)


MDO_ROW = {
    "dataset": "MDO",
    "bmUnit": "U1",
    "nationalGridBmUnit": "N1",
    "timeFrom": "2026-10-14T12:00:00Z",
    "timeTo": "2026-10-14T12:30:00Z",
    "levelFrom": 40,
    "levelTo": 38.5,
    "publishTime": "2026-10-14T11:59:00Z",
    "serialNumber": "17",
    "settlementDate": "2026-10-14",
    "settlementPeriod": 27,
}


def test_submission_by_hand() -> None:
    out = parse_submissions("MDO", [MDO_ROW])
    (sub,) = out.by_unit["U1"]
    assert (sub.time_from, sub.time_to) == (at(12), at(12, 30))
    assert (sub.level_from_mwh, sub.level_to_mwh) == (40.0, 38.5)
    assert (sub.publish_time, sub.serial) == (at(11, 59), 17)
    assert out.records == 1 and not out.excluded


def test_boundary_duplicates_are_removed_and_counted() -> None:
    out = parse_submissions(
        "MDO", [MDO_ROW, dict(MDO_ROW), {**MDO_ROW, "serialNumber": "18"}]
    )
    assert out.duplicates == 1 and out.records == 2


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"serialNumber": "17a"}, "serialNumber"),
        ({"levelFrom": -1}, "MDO below zero"),
        ({"timeTo": "2026-10-14T12:00:00Z"}, "time_to not after"),
        ({"publishTime": "2026-10-14T11:59:00+01:00"}, "not in UTC"),
        ({"timeFrom": None}, "timeFrom"),
        ({"bmUnit": ""}, "bmUnit"),
    ],
)
def test_bad_rows_are_excluded_with_a_reason(
    change: dict[str, object], reason: str
) -> None:
    out = parse_submissions(
        "MDO", [{**MDO_ROW, **change}, {**MDO_ROW, "serialNumber": "99"}]
    )
    assert out.records == 1
    ((label, n),) = out.excluded.items()
    assert n == 1 and reason in label and label.startswith("MDO: ")


def test_mdb_sign_and_open_ended_records() -> None:
    row = {
        **MDO_ROW,
        "dataset": "MDB",
        "levelFrom": -20,
        "levelTo": None,
        "timeTo": None,
    }
    (sub,) = parse_submissions("MDB", [row]).by_unit["U1"]
    assert sub.level_to_mwh is None and sub.time_to is None
    bad = parse_submissions("MDB", [{**row, "levelFrom": 5}])
    assert "MDB above zero" in next(iter(bad.excluded))


BOALF_ROW = {
    "bmUnit": "U1",
    "acceptanceNumber": 501,
    "acceptanceTime": "2026-10-14T12:03:00Z",
    "timeFrom": "2026-10-14T12:05:00Z",
    "timeTo": "2026-10-14T12:30:00Z",
    "levelFrom": 0,
    "levelTo": 25,
    "soFlag": True,
    "deemedBoFlag": False,
}


def test_boalf_segment_keeps_acceptance_and_ignores_flags() -> None:
    out = parse_segments(
        "BOALF", [BOALF_ROW, {**BOALF_ROW, "soFlag": False, "acceptanceNumber": 502}]
    )
    first, second = out.by_unit["U1"]
    assert (first.acceptance_number, first.acceptance_time) == (501, at(12, 3))
    assert (first.level_from_mw, first.level_to_mw) == (0.0, 25.0)
    assert second.acceptance_number == 502


def test_pn_segment_has_no_acceptance() -> None:
    row = {
        k: v
        for k, v in BOALF_ROW.items()
        if k not in ("acceptanceNumber", "acceptanceTime")
    }
    (seg,) = parse_segments("PN", [row]).by_unit["U1"]
    assert seg.acceptance_number is None and seg.acceptance_time is None


def test_zero_length_segments_are_counted_not_filed() -> None:
    zero = {**BOALF_ROW, "timeTo": BOALF_ROW["timeFrom"]}
    out = parse_segments("BOALF", [zero, BOALF_ROW])
    assert out.records == 1 and out.excluded == {"BOALF: zero length": 1}
    with pytest.raises(ValueError):
        parse_segments("MDO", [])


def test_boalf_without_acceptance_is_excluded() -> None:
    out = parse_segments("BOALF", [{**BOALF_ROW, "acceptanceTime": None}])
    assert out.records == 0 and "acceptanceTime" in next(iter(out.excluded))


B1610_ROW = {
    "bmUnit": "U1",
    "settlementDate": "2026-10-14",
    "settlementPeriod": 27,
    "halfHourEndTime": "2026-10-14T13:00:00Z",
    "quantity": -12.25,
    "settlementRunType": "SF",
    "publishTime": "2026-11-05T09:00:00Z",
}


def test_meter_period_starts_half_an_hour_before_its_end() -> None:
    out = parse_meter(
        [B1610_ROW, {**B1610_ROW, "settlementRunType": "R1", "quantity": -12.0}]
    )
    sf, r1 = out.by_unit["U1"]
    assert (sf.period_start, sf.net_mwh, sf.run_type) == (at(12, 30), -12.25, "SF")
    assert r1.run_type == "R1"
    bad = parse_meter([{**B1610_ROW, "halfHourEndTime": "2026-10-14T13:10:00Z"}])
    assert "off a boundary" in next(iter(bad.excluded))
    empty = parse_meter([{**B1610_ROW, "settlementRunType": ""}])
    assert "settlementRunType" in next(iter(empty.excluded))


def test_field_helpers() -> None:
    assert whole({"n": 3}, "n") == 3 and whole({"n": " 12 "}, "n") == 12
    for bad in (True, 1.5, "x", None):
        with pytest.raises(FieldError):
            whole({"n": bad}, "n")
    with pytest.raises(FieldError):
        instant({"t": "yesterday"}, "t")
    with pytest.raises(FieldError):
        instant({"t": "2026-10-14T12:00:00"}, "t")
    rows, dupes = unique_rows([{"a": 1, "b": 2}, {"b": 2, "a": 1}])
    assert len(rows) == 1 and dupes == 1
