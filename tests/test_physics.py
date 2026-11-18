"""Physics of PREREGISTRATION §3, each checked against a hand-worked example."""

from datetime import UTC, datetime, timedelta

import pytest

from src.model.types import LevelSegment, MeterPeriod, Submission
from src.physics.declared import declared_at, declared_deliverable_mwh, record_level
from src.physics.efficiency import EfficiencyUndefined, eta_hat, eta_in_bounds
from src.physics.protection import (
    boa_export_mwh,
    horizon_end,
    level_at,
    pn_protected_mwh,
    positive_part_mwh,
)
from src.physics.walls import (
    MissingSettlementPeriod,
    cumulative_change,
    lower_wall,
    swing_mwh,
    upper_wall,
)

T0 = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
MIN = timedelta(minutes=1)
SP = timedelta(minutes=30)
DEFAULT = 9999.0


def periods(*net_mwh: float) -> list[MeterPeriod]:
    return [MeterPeriod(T0 + k * SP, q, "SF") for k, q in enumerate(net_mwh)]


def seg(
    start: int, end: int, a: float, b: float, acc: int | None = None
) -> LevelSegment:
    """A level segment from minute `start` to minute `end`, a MW to b MW."""
    when = None if acc is None else T0 - MIN * (10 - acc)
    return LevelSegment(T0 + start * MIN, T0 + end * MIN, a, b, acc, when)


def rec(
    start: int,
    end: int | None,
    level: float,
    published: int,
    serial: int = 1,
    level_to: float | None = None,
    dataset: str = "MDO",
) -> Submission:
    return Submission(
        dataset,  # type: ignore[arg-type]  # tests pass the literal directly
        T0 + start * MIN,
        None if end is None else T0 + end * MIN,
        level,
        level_to,
        T0 + published * MIN,
        serial,
    )


# ------------------------------------------------------------------ efficiency


def test_eta_hat_is_export_over_import() -> None:
    """Export 4.4 + 4.4 = 8.8 MWh, import 10 MWh: η̂ = 8.8 / 10 = 0.88."""
    assert eta_hat(periods(-10.0, 4.4, 4.4)) == pytest.approx(0.88)


def test_eta_hat_needs_import_and_bounds_are_inclusive() -> None:
    with pytest.raises(EfficiencyUndefined):
        eta_hat(periods(5.0, 0.0))
    with pytest.raises(EfficiencyUndefined):
        eta_hat([])
    assert eta_in_bounds(0.70, 0.70, 0.98) and eta_in_bounds(0.98, 0.70, 0.98)
    assert not eta_in_bounds(0.69, 0.70, 0.98)
    with pytest.raises(ValueError):
        eta_in_bounds(0.8, 0.98, 0.70)


# ----------------------------------------------------------------------- walls


def test_walls_by_hand() -> None:
    """η̂ = 0.8; net values +10, −20, +5 MWh (export positive).

    K: 0; 0 − 10 = −10; −10 + 0.8 × 20 = 6; 6 − 5 = 1.
    Lower wall, K − min K with min −10: 10, 0, 16, 11.
    Upper wall with N = 30, N − (max K − K) with max 6: 24, 14, 30, 25.
    Swing: 6 − (−10) = 16.
    """
    k = cumulative_change(periods(10.0, -20.0, 5.0), 0.8)
    assert k == pytest.approx((0.0, -10.0, 6.0, 1.0))
    assert lower_wall(k) == pytest.approx((10.0, 0.0, 16.0, 11.0))
    assert upper_wall(k, 30.0) == pytest.approx((24.0, 14.0, 30.0, 25.0))
    assert swing_mwh(k) == pytest.approx(16.0)


def test_walls_reject_gaps_empty_and_bad_inputs() -> None:
    gap = [MeterPeriod(T0, 1.0, "SF"), MeterPeriod(T0 + 2 * SP, 1.0, "SF")]
    with pytest.raises(MissingSettlementPeriod):
        cumulative_change(gap, 0.9)
    with pytest.raises(MissingSettlementPeriod):
        cumulative_change([], 0.9)
    with pytest.raises(ValueError):
        cumulative_change(periods(1.0), 1.2)
    for wall in (lower_wall, swing_mwh):
        with pytest.raises(ValueError):
            wall(())
    with pytest.raises(ValueError):
        upper_wall((), 10.0)
    with pytest.raises(ValueError):
        upper_wall((0.0,), 0.0)


# ------------------------------------------------------------------ protection


def test_horizon_is_current_period_plus_three() -> None:
    """At 00:10 the current period ends 00:30; three more end at 02:00."""
    assert horizon_end(T0 + 10 * MIN, 3) == T0 + 4 * SP
    assert horizon_end(T0 + 30 * MIN, 3) == T0 + 5 * SP
    assert horizon_end(T0, 0) == T0 + SP
    with pytest.raises(ValueError):
        horizon_end(T0, -1)


@pytest.mark.parametrize(
    ("a", "b", "hours", "expected"),
    [
        (10.0, 10.0, 2.0, 20.0),  # constant 10 MW for 2 h
        (-10.0, -5.0, 1.0, 0.0),  # wholly below zero
        (-10.0, 10.0, 1.0, 2.5),  # crosses at 30 min: ½ × 10 MW × 0.5 h
        (10.0, -30.0, 1.0, 1.25),  # crosses at 15 min: ½ × 10 MW × 0.25 h
    ],
)
def test_positive_part(a: float, b: float, hours: float, expected: float) -> None:
    assert positive_part_mwh(a, b, hours) == pytest.approx(expected)


def test_pn_protected_energy() -> None:
    """PN ramps −10 → +10 MW over the first hour, then holds 10 MW for an hour.

    From 00:00 to 02:00: export ½ × 10 × 0.5 + 10 × 1 = 12.5 MWh;
    import ½ × 10 × 0.5 = 2.5 MWh.
    """
    pn = [seg(0, 60, -10.0, 10.0), seg(60, 120, 10.0, 10.0)]
    export_mwh, import_mwh = pn_protected_mwh(pn, T0, T0 + 4 * SP)
    assert export_mwh == pytest.approx(12.5)
    assert import_mwh == pytest.approx(2.5)


def test_pn_step_change_is_read_from_the_right_side() -> None:
    """PN steps from 0 to 20 MW at 00:30. Over 00:30–01:00: 20 × 0.5 = 10 MWh."""
    pn = [seg(0, 30, 0.0, 0.0), seg(30, 60, 20.0, 20.0)]
    assert pn_protected_mwh(pn, T0 + 30 * MIN, T0 + 60 * MIN) == pytest.approx(
        (10.0, 0.0)
    )


def test_boa_export_above_pn() -> None:
    """PN 5 MW throughout. BOA 1 instructs 25 MW, 00:30–01:00: 20 MW above PN
    for 0.5 h = 10 MWh. Acceptance 2 lowers 00:45–01:00 to 15 MW: the second
    quarter-hour is 10 MW above PN, so 20 × 0.25 + 10 × 0.25 = 7.5 MWh.
    """
    pn = [seg(0, 120, 5.0, 5.0)]
    first = [seg(30, 60, 25.0, 25.0, acc=1)]
    assert boa_export_mwh(first, pn, T0, T0 + 4 * SP) == pytest.approx(10.0)
    both = [*first, seg(45, 60, 15.0, 15.0, acc=2)]
    assert boa_export_mwh(both, pn, T0, T0 + 4 * SP) == pytest.approx(7.5)


def test_boa_accepted_after_t_does_not_count() -> None:
    """Acceptance 9 is made at 23:59 the day before; at 23:50 it is unknown."""
    boa = [seg(30, 60, 25.0, 25.0, acc=9)]
    assert boa_export_mwh(boa, [], T0 - 10 * MIN, T0 + 4 * SP) == 0.0
    assert boa_export_mwh(boa, [], T0, T0 + 4 * SP) == pytest.approx(12.5)


def test_bid_below_pn_adds_no_export() -> None:
    """A bid at −10 MW against PN 0 is import, not export: B^exp = 0."""
    boa = [seg(0, 30, -10.0, -10.0, acc=1)]
    assert boa_export_mwh(boa, [], T0, T0 + SP) == 0.0


def test_protection_rejects_reversed_horizon_and_bad_times() -> None:
    with pytest.raises(ValueError):
        pn_protected_mwh([], T0, T0 - MIN)
    with pytest.raises(ValueError):
        boa_export_mwh([], [], T0, T0 - MIN)
    with pytest.raises(ValueError):
        level_at(seg(0, 30, 1.0, 1.0), T0 + 31 * MIN)
    with pytest.raises(ValueError):
        positive_part_mwh(1.0, 1.0, -1.0)


# ---------------------------------------------------------------- declarations


def test_latest_submission_wins_and_ramps_interpolate() -> None:
    """Submission 1 (published 00:00): 40 MWh, 00:00–02:00.
    Submission 2 (published 00:20): 30 → 10 MWh, 00:30–01:30.
    At 00:00: 40. At 00:30: 30. At 01:00: halfway, 20. At 01:30: back to 40.
    """
    subs = [rec(0, 120, 40.0, published=0), rec(30, 90, 30.0, 20, level_to=10.0)]
    times = [T0 + k * SP for k in range(4)]
    assert declared_at(subs, "MDO", times, DEFAULT, T0 + 4 * SP) == pytest.approx(
        (40.0, 30.0, 20.0, 40.0)
    )


def test_serial_breaks_publish_time_ties() -> None:
    subs = [rec(0, 60, 40.0, 0, serial=2), rec(0, 60, 25.0, 0, serial=1)]
    assert declared_at(subs, "MDO", [T0], DEFAULT, T0 + SP) == (40.0,)


def test_open_record_holds_until_its_submissions_next_record() -> None:
    """One submission with records at 00:00 (no end) and 01:00: the first holds
    until 01:00, so at 00:30 it reads 40; the second holds to data_end."""
    subs = [rec(0, None, 40.0, 0), rec(60, None, 20.0, 0)]
    times = [T0, T0 + SP, T0 + 2 * SP, T0 + 3 * SP]
    assert declared_at(subs, "MDO", times, DEFAULT, T0 + 3 * SP) == (
        40.0,
        40.0,
        20.0,
        None,
    )


def test_defaults_mean_no_declaration() -> None:
    """A later default record covers 00:30: nothing is in force there."""
    subs = [rec(0, 120, 40.0, 0), rec(30, 60, DEFAULT, 10)]
    times = [T0, T0 + SP, T0 + 2 * SP]
    assert declared_at(subs, "MDO", times, DEFAULT, T0 + 4 * SP) == (40.0, None, 40.0)


def test_datasets_are_kept_apart_and_empty_is_none() -> None:
    subs = [rec(0, 60, -15.0, 0, dataset="MDB")]
    assert declared_at(subs, "MDO", [T0], DEFAULT, T0 + SP) == (None,)
    assert declared_at(subs, "MDB", [T0], DEFAULT, T0 + SP) == (-15.0,)
    assert declared_at([], "MDO", [], DEFAULT, T0) == ()


def test_declared_at_rejects_unsorted_times_and_bad_default() -> None:
    with pytest.raises(ValueError):
        declared_at([], "MDO", [T0 + SP, T0], DEFAULT, T0)
    with pytest.raises(ValueError):
        declared_at([], "MDO", [T0], 0.0, T0)
    with pytest.raises(ValueError):
        record_level(rec(0, 30, 1.0, 0), T0 + 30 * MIN, T0 + 30 * MIN)


def test_declared_deliverable_branches() -> None:
    """MDO 50, P^exp 10, B^exp 5, η̂ 0.81 (√η̂ = 0.9).
    Branch A: 50 + 10 + 5 = 65. Branch B: 0.9 × 50 + 10 + 5 = 60.
    """
    assert declared_deliverable_mwh(50.0, 10.0, 5.0, 0.81, "A") == pytest.approx(65.0)
    assert declared_deliverable_mwh(50.0, 10.0, 5.0, 0.81, "B") == pytest.approx(60.0)
    with pytest.raises(ValueError):
        declared_deliverable_mwh(-1.0, 0.0, 0.0, 0.9, "A")
    with pytest.raises(ValueError):
        declared_deliverable_mwh(1.0, 0.0, 0.0, 0.0, "A")
