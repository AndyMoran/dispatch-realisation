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
    "halfHourEndTime": "2026-10-14T13:00:00",  # as B1610 writes it: no offset
    "quantity": -12.25,
    "settlementRunType": "SF",
    "publishTime": "2026-11-05T09:00:00Z",
}


def test_meter_period_comes_from_settlement_date_and_period() -> None:
    out = parse_meter(
        [B1610_ROW, {**B1610_ROW, "settlementRunType": "R1", "quantity": -12.0}]
    )
    sf, r1 = out.by_unit["U1"]
    # Period 27 starts at 13:00 local, 12:00 UTC in British Summer Time.
    assert (sf.period_start, sf.net_mwh, sf.run_type) == (at(12, 0), -12.25, "SF")
    assert r1.run_type == "R1"
    # halfHourEndTime is never read, so a nonsense value changes nothing.
    odd = parse_meter([{**B1610_ROW, "halfHourEndTime": "x"}])
    assert odd.by_unit["U1"][0].period_start == at(12, 0)
    empty = parse_meter([{**B1610_ROW, "settlementRunType": ""}])
    assert "settlementRunType" in next(iter(empty.excluded))


def test_meter_periods_on_the_autumn_clock_change() -> None:
    rows = [
        {**B1610_ROW, "settlementDate": "2026-10-25", "settlementPeriod": k}
        for k in (3, 5, 50)
    ]
    starts = [p.period_start for p in parse_meter(rows).by_unit["U1"]]
    # 01:00 local happens twice: BST (00:00 UTC), then GMT (01:00 UTC).
    assert starts == [
        datetime(2026, 10, 25, 0, 0, tzinfo=UTC),
        datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
        datetime(2026, 10, 25, 23, 30, tzinfo=UTC),
    ]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"settlementPeriod": 49}, "outside its day"),  # 14 Oct has 48
        ({"settlementPeriod": 0}, "outside its day"),
        ({"settlementPeriod": None}, "settlementPeriod"),
        ({"settlementDate": "2026-10-14T00:00:00"}, "settlementDate"),
        ({"settlementDate": "14/10/2026"}, "settlementDate"),
        ({"settlementDate": "20261014"}, "settlementDate"),  # ISO basic form
        ({"settlementDate": None}, "settlementDate"),
    ],
)
def test_meter_rows_with_a_bad_period_are_excluded(
    change: dict[str, object], reason: str
) -> None:
    out = parse_meter([{**B1610_ROW, **change}])
    assert out.records == 0 and reason in next(iter(out.excluded))


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
