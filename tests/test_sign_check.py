"""The M23 sign check and M25 run-code check, with canned data and planted bugs.

Nothing here touches Elexon or NESO.
"""

import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.ingest import pull, sign_check
from src.ingest.sign_check import (
    CheckStopped,
    check_labels,
    check_plan,
    neso_rows,
    period_start,
    periods_in,
    pn_negative_throughout,
    ps_units,
    pumping_periods,
    run_check,
    sf_values,
    stops,
)
from src.model.types import LevelSegment, MeterPeriod

D = date(2026, 10, 14)
SF_OR_LATER = ("SF", "R1", "R2", "R3", "RF", "DF")
NOW = datetime(2026, 11, 23, 18, 0, tzinfo=UTC)


def seg(
    start: datetime, minutes: int, level_from: float, level_to: float
) -> LevelSegment:
    return LevelSegment(start, start + timedelta(minutes=minutes), level_from, level_to)


# ------------------------------------------------------------------ periods


def test_period_start_counts_from_local_midnight() -> None:
    assert period_start(D, 1) == datetime(2026, 10, 13, 23, 0, tzinfo=UTC)  # BST
    assert period_start(date(2026, 11, 2), 1) == datetime(2026, 11, 2, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        period_start(D, 51)


def test_clock_change_days_have_46_and_50_periods() -> None:
    assert periods_in(date(2026, 10, 25)) == 50
    assert periods_in(date(2026, 3, 29)) == 46
    assert periods_in(D) == 48
    assert period_start(date(2026, 10, 25), 50) == datetime(
        2026, 10, 25, 23, 30, tzinfo=UTC
    )


# ------------------------------------------------------------------ PN


def test_pn_negative_throughout() -> None:
    t = period_start(D, 20)
    assert pn_negative_throughout([seg(t, 30, -100, -90)], t)
    assert pn_negative_throughout([seg(t - timedelta(hours=1), 120, -5, -5)], t)
    assert pn_negative_throughout(
        [seg(t, 10, -1, -1), seg(t + timedelta(minutes=10), 20, -1, -2)], t
    )


@pytest.mark.parametrize(
    "segments",
    [
        [],  # no PN
        [seg(period_start(D, 20), 30, -100, 0)],  # reaches zero
        [seg(period_start(D, 20), 30, 10, -10)],  # starts positive
        [seg(period_start(D, 20) + timedelta(minutes=5), 25, -1, -1)],  # starts late
        [seg(period_start(D, 20), 20, -1, -1)],  # ends early
        [  # a gap inside the period
            seg(period_start(D, 20), 10, -1, -1),
            seg(period_start(D, 20) + timedelta(minutes=15), 15, -1, -1),
        ],
    ],
)
def test_pn_not_negative_throughout(segments: list[LevelSegment]) -> None:
    assert not pn_negative_throughout(segments, period_start(D, 20))


# ------------------------------------------------------------------ NESO


def test_labels_must_be_exactly_a_and_f() -> None:
    check_labels(["A", "F", "A"])
    for bad in (["A"], ["F"], ["A", "F", "X"], ["actual", "forecast"], []):
        with pytest.raises(CheckStopped):
            check_labels(bad)


def neso_row(
    day: str, period: int, pumping: object, label: str = "A"
) -> dict[str, object]:
    return {
        "SETTLEMENT_DATE": f"{day}T00:00:00",
        "SETTLEMENT_PERIOD": period,
        "PUMP_STORAGE_PUMPING": pumping,
        "FORECAST_ACTUAL_INDICATOR": label,
    }


def test_pumping_periods_uses_actual_rows_above_zero() -> None:
    rows = [
        neso_row("2026-10-14", 20, 300),
        neso_row("2026-10-14", 21, 0),  # not pumping
        neso_row("2026-10-14", 22, 500, "F"),  # a forecast: never used
        neso_row("2026-10-14", 23, "n/a", "F"),  # not read, so not checked
    ]
    assert pumping_periods(rows) == {period_start(D, 20)}


@pytest.mark.parametrize(
    "row",
    [
        neso_row("2026-10-14", 20, None),
        neso_row("2026-10-14", 20, True),
        neso_row("2026-10-14", 49, 300),  # a 48-period day
    ],
)
def test_pumping_periods_stops_on_a_bad_row(row: dict[str, object]) -> None:
    with pytest.raises(CheckStopped):
        pumping_periods([row])


def test_neso_rows_checks_the_total() -> None:
    rows = [neso_row("2026-10-14", 20, 1)]
    body = json.dumps({"result": {"records": rows, "total": 1}}).encode()
    assert neso_rows(body) == rows
    short = json.dumps({"result": {"records": rows, "total": 2}}).encode()
    with pytest.raises(CheckStopped):
        neso_rows(short)


# ------------------------------------------------------------------ the rule


def check(
    values: dict[tuple[str, datetime], float], codes: Counter[str] | None = None
) -> sign_check.SignResult:
    t20 = period_start(D, 20)
    t21 = period_start(D, 21)
    pn = {"PS1": [seg(t20, 120, -200, -200)], "PS2": [seg(t20, 60, -50, -50)]}
    return run_check(values, pn, {t20, t21}, codes or Counter({"SF": 1}), SF_OR_LATER)


def test_all_negative_is_grounded() -> None:
    t = period_start(D, 20)
    r = check({("PS1", t): -90.0, ("PS2", t): -20.0})
    assert (r.selected, r.negative, r.verdict) == (2, 2, "negative: sign as read")
    assert stops(r) is None


def test_all_positive_reverses_the_sign_without_stopping() -> None:
    t = period_start(D, 20)
    r = check({("PS1", t): 90.0})
    assert r.verdict == "positive: sign reversed"
    assert stops(r) is None


@pytest.mark.parametrize("second", [5.0, 0.0])
def test_mixed_or_zero_stops(second: float) -> None:
    t20, t21 = period_start(D, 20), period_start(D, 21)
    r = check({("PS1", t20): -90.0, ("PS1", t21): second})
    assert r.verdict == "mixed"
    assert stops(r) == "sign check mixed (M23)"


def test_periods_outside_the_rule_are_not_selected() -> None:
    t20, t22 = period_start(D, 20), period_start(D, 22)
    # PS1 at 22: PN negative throughout, but no NESO pumping. PS3: no PN at all.
    r = check({("PS1", t22): 90.0, ("PS3", t20): 90.0})
    assert (r.units, r.sf_periods, r.selected) == (2, 2, 0)
    assert stops(r) == "sign check no period selected (M23)"


def test_run_codes_ii_is_known_anything_else_stops() -> None:
    t = period_start(D, 20)
    ok = check({("PS1", t): -1.0}, Counter({"SF": 3, "II": 2, "RF": 1}))
    assert ok.run_codes == {"II": 2, "RF": 1, "SF": 3} and stops(ok) is None
    bad = check({("PS1", t): -1.0}, Counter({"SF": 3, "R4": 1}))
    assert bad.unknown_run_codes == ["R4"]
    assert stops(bad) == "unknown run codes: ['R4'] (M25)"


def test_sf_values_keeps_sf_in_window_and_stops_on_a_conflict() -> None:
    t = period_start(D, 20)
    meter = {
        "PS1": [
            MeterPeriod(t, -5.0, "II"),
            MeterPeriod(t, -4.0, "SF"),
            MeterPeriod(t, -4.0, "SF"),  # the same value twice is one value
            MeterPeriod(t + timedelta(days=40), -3.0, "SF"),  # outside the window
        ]
    }
    assert sf_values(meter, {t}) == {("PS1", t): -4.0}
    meter["PS1"].append(MeterPeriod(t, -6.0, "SF"))
    with pytest.raises(CheckStopped):
        sf_values(meter, {t})


def test_ps_units() -> None:
    fuel = {"B": "PS", "A": "PS", "C": "CCGT", "D": "BATTERY"}
    assert ps_units(fuel, ["X"]) == ["A", "B"]
    with pytest.raises(CheckStopped):
        ps_units({"C": "CCGT"}, [])
    with pytest.raises(CheckStopped):
        ps_units(fuel, ["A"])


def test_plan_covers_october_b1610_pn_and_one_neso_request() -> None:
    requests = check_plan(["PS2", "PS1"])
    kinds = Counter(r.dataset for r in requests)
    assert kinds == {"B1610": 31, "PN": 31, "NESO_demand": 1}
    neso = requests[-1]
    assert neso.url.startswith("https://api.neso.energy/api/3/action/datastore_search?")
    assert "8a4a771c-3929-4e56-93ad-cdf13219dea5" in neso.public_url
    assert "fields=" not in neso.url  # NESO answers a field list with HTTP 409
    assert all(r.units == ("PS1", "PS2") for r in requests[:-1])


# ------------------------------------------------------------------ end to end


def fake_network(sf: list[float]) -> Callable[[str], bytes]:
    """B1610 SF values for periods 20, 21, ... of 14 Oct; PN negative all day."""
    day0 = period_start(D, 1)

    def get(url: str) -> bytes:
        if "api.neso.energy" in url:
            records = [neso_row("2026-10-14", 20 + i, 400) for i in range(len(sf))]
            records.append(neso_row("2026-12-01", 1, 0, "F"))
            return json.dumps(
                {"result": {"records": records, "total": len(records)}}
            ).encode()
        if "settlementDateFrom=2026-10-14" in url:
            rows = [
                {
                    "bmUnit": "PS1",
                    "halfHourEndTime": (period_start(D, 20 + i) + timedelta(minutes=30))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "quantity": v,
                    "settlementRunType": run,
                }
                for i, v in enumerate(sf)
                for run in ("II", "SF")
            ]
            return json.dumps({"data": rows}).encode()
        if "/PN/" in url and "from=2026-10-14" in url:
            row = {
                "bmUnit": "PS1",
                "timeFrom": day0.isoformat().replace("+00:00", "Z"),
                "timeTo": (day0 + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "levelFrom": -250,
                "levelTo": -250,
            }
            return json.dumps({"data": [row]}).encode()
        return json.dumps({"data": []}).encode()

    return get


def run_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sf: list[float]
) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(
        sign_check,
        "load_reference_fuel",
        lambda: ({"PS1": "PS", "BAT1": "BATTERY"}, Path("bmunits__dl1.json")),
    )
    monkeypatch.setattr(pull, "load_fleet", lambda: ["BAT1"])
    code = sign_check.main(fake_network(sf), lambda: NOW, tmp_path, pause_s=0)
    report = json.loads(
        (tmp_path / "outputs" / "pull" / "b1610_check.json").read_text()
    )
    return code, report


def test_end_to_end_negative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, report = run_main(tmp_path, monkeypatch, [-120.0, -118.0])
    assert code == 0 and report["stops"] is None
    result = report["result"]
    assert isinstance(result, dict)
    assert (result["selected"], result["verdict"]) == (2, "negative: sign as read")
    assert result["run_codes"] == {"II": 2, "SF": 2}
    assert report["indicator_labels"] == ["A", "F"]
    assert report["ps_units"] == 1
    text = json.dumps(report)
    assert "PS1" not in text and "-120" not in text  # no unit ID, no value
    manifest = (tmp_path / "data" / "manifests" / "pull_manifest.csv").read_bytes()
    assert b"\r\n" not in manifest and manifest.count(b"\n") == 64  # header + 63


def test_end_to_end_mixed_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, report = run_main(tmp_path, monkeypatch, [-120.0, 0.0])
    assert code == 1 and report["stops"] == "sign check mixed (M23)"


def test_rerun_reads_the_manifest_without_pulling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_main(tmp_path, monkeypatch, [-1.0])

    def offline(url: str) -> bytes:
        raise AssertionError("pulled again")

    code = sign_check.main(offline, lambda: NOW, tmp_path, pause_s=0)
    assert code == 0
