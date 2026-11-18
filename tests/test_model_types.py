"""Shared input types: valid, empty and malformed input; netting; no provenance."""

import dataclasses
import random
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.model import types as t
from src.model.types import (
    InvalidRecord,
    LevelSegment,
    MeterPeriod,
    Submission,
    UnitInputs,
    build_unit_inputs,
)

T0 = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)


def sub(dataset: t.Dataset = "MDO", value: float = 50.0, minute: int = 0) -> Submission:
    return Submission(
        dataset=dataset,
        time_from=T0 + timedelta(minutes=minute),
        time_to=T0 + timedelta(minutes=minute + 1),
        level_from_mwh=value,
        level_to_mwh=None,
        publish_time=T0 + timedelta(minutes=minute),
        serial=minute,
    )


def seg(start_min: int, level: float, acceptance: int | None = None) -> LevelSegment:
    accepted = None if acceptance is None else T0 + timedelta(minutes=start_min - 2)
    return LevelSegment(
        time_from=T0 + timedelta(minutes=start_min),
        time_to=T0 + timedelta(minutes=start_min + 30),
        level_from_mw=level,
        level_to_mw=level,
        acceptance_number=acceptance,
        acceptance_time=accepted,
    )


# ------------------------------------------------------------------ valid input


def test_valid_unit_builds_and_sorts_every_collection() -> None:
    meter = [MeterPeriod(T0 + timedelta(minutes=m), 1.0, "SF") for m in (60, 0, 30)]
    unit = build_unit_inputs(
        "unit-a",
        50.0,
        [sub(minute=10), sub("MDB", -20.0, minute=5)],
        meter,
        [seg(30, 10.0), seg(0, 10.0)],
        [seg(30, 20.0, acceptance=2), seg(0, 20.0, acceptance=1)],
    )
    assert [m.period_start.minute for m in unit.meter] == [0, 30, 0]
    assert [s.dataset for s in unit.submissions] == ["MDB", "MDO"]
    assert [s.acceptance_number for s in unit.boas] == [1, 2]


def test_build_order_never_depends_on_input_order() -> None:
    meter = [
        MeterPeriod(T0 + timedelta(minutes=30 * k), float(k), "SF") for k in range(8)
    ]
    subs = [sub(value=float(k), minute=k) for k in range(8)]
    first = build_unit_inputs("u", None, subs, meter, [], [])
    rng = random.Random(7)
    rng.shuffle(meter)
    rng.shuffle(subs)
    assert build_unit_inputs("u", None, subs, meter, [], []) == first


def test_empty_collections_are_valid() -> None:
    unit = build_unit_inputs("unit-a", None, [], [], [], [])
    assert unit.meter == () and unit.submissions == ()


# ------------------------------------------------------------- netting (P7, M23)


@pytest.mark.parametrize(
    ("net", "export", "imported"),
    [(3.5, 3.5, 0.0), (-2.0, 0.0, 2.0), (0.0, 0.0, 0.0)],
)
def test_net_meter_value_splits_into_one_direction(
    net: float, export: float, imported: float
) -> None:
    """B1610 gives one net value; at most one of E⁺ and E⁻ is non-zero (§3)."""
    period = MeterPeriod(T0, net, "SF")
    assert period.export_mwh == pytest.approx(export)
    assert period.import_mwh == pytest.approx(imported)


def test_meter_type_has_no_separate_flows() -> None:
    """Synthetic batteries can only report what B1610 reports: one net value."""
    names = {f.name for f in dataclasses.fields(MeterPeriod)}
    assert names == {"period_start", "net_mwh", "run_type"}


def test_segment_energy_is_trapezium() -> None:
    """A ramp from 0 to 20 MW over 30 minutes delivers 5 MWh: (0 + 20) / 2 × 0.5 h."""
    ramp = LevelSegment(T0, T0 + timedelta(minutes=30), 0.0, 20.0)
    assert ramp.energy_mwh() == pytest.approx(5.0)


# ------------------------------------------------------------- no provenance


def test_no_type_carries_provenance() -> None:
    """Nothing a claim reads can say whether a unit is real or synthetic."""
    banned = {"source", "synthetic", "provenance", "seed", "manifest", "origin"}
    for cls in (Submission, MeterPeriod, LevelSegment, UnitInputs):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not names & banned, f"{cls.__name__} carries {names & banned}"


# ----------------------------------------------------------------- malformed


@pytest.mark.parametrize(
    "when",
    [datetime(2026, 10, 5), datetime(2026, 10, 5, tzinfo=timezone(timedelta(hours=1)))],
)
def test_times_must_be_utc(when: datetime) -> None:
    with pytest.raises(InvalidRecord):
        MeterPeriod(when, 1.0, "SF")
    with pytest.raises(InvalidRecord):
        Submission("MDO", when, None, 1.0, None, T0, 1)


@pytest.mark.parametrize(("dataset", "value"), [("MDO", -1.0), ("MDB", 1.0)])
def test_declaration_signs(dataset: t.Dataset, value: float) -> None:
    with pytest.raises(InvalidRecord, match="zero"):
        sub(dataset, value)


def test_malformed_records_are_rejected() -> None:
    with pytest.raises(InvalidRecord, match="not after"):
        Submission("MDO", T0, T0, 1.0, None, T0, 1)
    with pytest.raises(InvalidRecord, match="finite"):
        Submission("MDO", T0, None, float("nan"), None, T0, 1)
    with pytest.raises(InvalidRecord, match="below zero"):
        Submission("MDO", T0, None, 5.0, -1.0, T0, 1)
    with pytest.raises(InvalidRecord, match="boundary"):
        MeterPeriod(T0 + timedelta(minutes=15), 1.0, "SF")
    with pytest.raises(InvalidRecord, match="run_type"):
        MeterPeriod(T0, 1.0, " ")
    with pytest.raises(InvalidRecord, match="not after"):
        LevelSegment(T0, T0, 1.0, 1.0)
    with pytest.raises(InvalidRecord, match="together"):
        LevelSegment(T0, T0 + timedelta(minutes=1), 1.0, 1.0, acceptance_number=3)


def test_unit_rules() -> None:
    period = MeterPeriod(T0, 1.0, "SF")
    with pytest.raises(InvalidRecord, match="two values"):
        UnitInputs("u", None, (), (period, period), (), ())
    with pytest.raises(InvalidRecord, match="not sorted"):
        later = MeterPeriod(T0 + timedelta(minutes=30), 1.0, "SF")
        UnitInputs("u", None, (), (later, period), (), ())
    with pytest.raises(InvalidRecord, match="unit_key"):
        UnitInputs(" ", None, (), (), (), ())
    with pytest.raises(InvalidRecord, match="registered_mw"):
        UnitInputs("u", 0.0, (), (), (), ())
    with pytest.raises(InvalidRecord, match="carries an acceptance"):
        UnitInputs("u", None, (), (), (seg(0, 1.0, acceptance=1),), ())
    with pytest.raises(InvalidRecord, match="no acceptance"):
        UnitInputs("u", None, (), (), (), (seg(0, 1.0),))


def test_records_are_frozen() -> None:
    period = MeterPeriod(T0, 1.0, "SF")
    with pytest.raises(dataclasses.FrozenInstanceError):
        period.net_mwh = 2.0  # type: ignore[misc]  # testing immutability on purpose
