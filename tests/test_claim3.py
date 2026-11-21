"""Claim 3 (PREREGISTRATION §5) on hand-built units and hand-worked fits.

The main unit has one scored week with 21 offers, A = 4.0, 4.3, …, 10.0 MWh, each
a single settlement period at a clock time no other day uses, so every baseline
median is zero. It declares MDO = 10 MWh throughout but can deliver at most
`cap` MWh: with cap = 8 it is a proportional over-declarer with f = 0.2 exactly
(ρ = min(1, 0.8/r), r = A/10), and Δ = 2 MWh. Ninety minutes before each offer it
imports the energy it will deliver, so the lower wall at the start of the period
holding the acceptance (a minute before delivery) is what it delivers, and the
placebo set is exactly the offers with A ≤ cap. The imports sit at even period
offsets and the offers at odd ones, so no import shares an offer's clock time.
"""

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.claim3 import fits
from src.claim3 import instructions as ins
from src.claim3.unit import (
    flagged_under_both,
    load_claim3_settings,
    score_claim3,
)
from src.claims.scoring import Interval
from src.claims.unit import load_claim_settings
from src.model.types import (
    LevelSegment,
    MeterPeriod,
    Submission,
    UnitInputs,
    build_unit_inputs,
)
from src.physics.declared import Branch

ADOPTION = datetime(2026, 6, 1, tzinfo=UTC)
WEEK = ADOPTION + timedelta(days=7)
END = ADOPTION + timedelta(days=14)
SP = timedelta(minutes=30)
ETA = 0.88
SETTINGS = load_claim3_settings(load_claim_settings())
A_VALUES = [round(4.0 + 0.3 * k, 6) for k in range(21)]


def slot(k: int) -> datetime:
    """Offer k: day k % 7 of the scored week, at a clock time no other day uses."""
    day, j = k % 7, k // 7
    return WEEK + timedelta(days=day) + (3 + 2 * day + 16 * j) * SP


def make_unit(
    cap: float = 8.0,
    declared: float = 10.0,
    extra_boas: list[LevelSegment] | None = None,
    extra_records: list[Submission] | None = None,
    a_values: list[float] = A_VALUES,
    same_clock: bool = False,
    drop_period: datetime | None = None,
    charge_lead: int = 3,
) -> UnitInputs:
    net = {ADOPTION + h * SP: 0.0 for h in range(14 * 48)}
    boas = []
    for k, a in enumerate(a_values):
        t = (WEEK + timedelta(days=k % 7) + 4 * SP) if same_clock else slot(k)
        delivered = min(a, cap)
        net[t] = delivered
        net[t - charge_lead * SP] = -delivered / ETA
        boas.append(
            LevelSegment(
                t,
                t + SP,
                2 * a,
                2 * a,
                acceptance_number=k + 1,
                acceptance_time=t - timedelta(minutes=1),
            )
        )
        if same_clock and k >= 6:
            break
    meter = [
        MeterPeriod(p, q, "SF") for p, q in sorted(net.items()) if p != drop_period
    ]
    published = ADOPTION - timedelta(days=1)
    records = [
        Submission("MDO", ADOPTION, END, declared, declared, published, 0),
        Submission("MDB", ADOPTION, END, -declared, -declared, published, 0),
        *(extra_records or []),
    ]
    return build_unit_inputs(
        "hand",
        50.0,
        records,
        meter,
        [],
        sorted(boas + (extra_boas or []), key=lambda s: s.time_from),
    )


# ------------------------------------------------------------------ per instruction


def test_deviation_counts_only_energy_above_pn() -> None:
    """BOALF 10 MW over a 5 MW PN for an hour: A = 5 MWh."""
    t = WEEK
    boa = [
        LevelSegment(t, t + 2 * SP, 10.0, 10.0, acceptance_number=1, acceptance_time=t)
    ]
    pn = [LevelSegment(t - SP, t + 3 * SP, 5.0, 5.0)]
    assert ins.deviation_mwh(boa, pn, t, t + 2 * SP) == pytest.approx(5.0)
    assert ins.segment_integral_mwh(pn, t, t + SP) == pytest.approx(2.5)


def test_clock_keys_split_the_repeated_autumn_hour() -> None:
    """00:30 and 01:30 UTC on 25 Oct 2026 are both 01:30 UK time, once in BST and
    once in GMT: two different keys."""
    a = ins.clock_key(datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    b = ins.clock_key(datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert a[:2] == b[:2] == (1, 30) and a != b


def test_iso_week_and_period_floor() -> None:
    t = datetime(2026, 6, 10, 13, 47, 12, tzinfo=UTC)
    assert ins.iso_week(t) == datetime(2026, 6, 8, tzinfo=UTC)
    assert ins.period_floor(t) == datetime(2026, 6, 10, 13, 30, tzinfo=UTC)


def measured(unit: UnitInputs, branch: Branch = "A") -> tuple[ins.Measured, ...]:
    return ins.measure(
        unit, ins.instructions(unit), ETA, branch, 1.0, 9999.0, END, frozenset({"SF"})
    )


def test_quantities_hand_worked() -> None:
    """Offer A = 10: r = 1, D = 8 (the cap), ρ = 0.8. Offer A = 4: r = 0.4, ρ = 1."""
    rows = {round(m.instruction.a_mwh, 6): m for m in measured(make_unit())}
    top, low = rows[10.0], rows[4.0]
    assert top.excluded is None and top.r == pytest.approx(1.0)
    assert top.d_mwh == pytest.approx(8.0) and top.rho == pytest.approx(0.8)
    assert low.r == pytest.approx(0.4) and low.rho == pytest.approx(1.0)


def test_branch_b_reads_mdo_as_stored_energy() -> None:
    """Under B the deliverable declaration is √η̂ × MDO, so r = A / (√0.88 × 10)."""
    rows = {round(m.instruction.a_mwh, 6): m for m in measured(make_unit(), "B")}
    assert rows[10.0].r == pytest.approx(10.0 / (math.sqrt(ETA) * 10.0))


def test_only_records_published_before_acceptance_count() -> None:
    """A record published at the acceptance minute itself is not yet visible."""
    t = slot(20)
    late = Submission(
        "MDO", t - timedelta(minutes=1), END, 5.0, 5.0, t - timedelta(minutes=1), 0
    )
    rows = {
        round(m.instruction.a_mwh, 6): m
        for m in measured(make_unit(extra_records=[late]))
    }
    assert rows[10.0].r == pytest.approx(1.0)  # still against 10, not 5


def test_screens() -> None:
    t = slot(0)
    overlap = LevelSegment(
        t + timedelta(minutes=10),
        t + timedelta(minutes=20),
        1.0,
        1.0,
        acceptance_number=99,
        acceptance_time=t,
    )
    reasons = [m.excluded for m in measured(make_unit(extra_boas=[overlap]))]
    assert reasons.count(ins.OTHER_BOA) == 2  # both acceptances share the period
    small = [m.excluded for m in measured(make_unit(a_values=[0.5]))]
    assert small == [ins.BELOW_FLOOR]
    same = [m.excluded for m in measured(make_unit(same_clock=True))]
    assert set(same) == {ins.NO_BASELINE}  # every day busy at that clock time
    missing = [m.excluded for m in measured(make_unit(drop_period=slot(3)))]
    assert missing.count(ins.NO_METER) == 1


def test_no_declaration_published_before_acceptance() -> None:
    unit = make_unit()
    unit = build_unit_inputs(
        "hand",
        50.0,
        [Submission("MDO", ADOPTION, END, 10.0, 10.0, END - SP, 0)],
        list(unit.meter),
        list(unit.pn),
        list(unit.boas),
    )
    assert {m.excluded for m in measured(unit)} == {ins.NO_DECLARATION}


def test_bids_mirror_with_mdb() -> None:
    """A bid of −6 MWh against |MDB| = 10: r = 0.6; under B, r = 6 / (10/√η̂)."""
    t = slot(0)
    bid = LevelSegment(
        t,
        t + SP,
        -12.0,
        -12.0,
        acceptance_number=1,
        acceptance_time=t - timedelta(minutes=1),
    )
    base = make_unit(a_values=[])
    meter = [
        MeterPeriod(m.period_start, -6.0 if m.period_start == t else m.net_mwh, "SF")
        for m in base.meter
    ]
    unit = build_unit_inputs("hand", 50.0, list(base.submissions), meter, [], [bid])
    (a,) = measured(unit, "A")
    (b,) = measured(unit, "B")
    assert a.side == "bid" and a.r == pytest.approx(0.6) and a.rho == pytest.approx(1.0)
    assert b.r == pytest.approx(6.0 / (10.0 / math.sqrt(ETA)))


# ------------------------------------------------------------------ fits


GRIDS = fits.Grids(0.9, 0.01, 0.1)


def test_grids() -> None:
    assert GRIDS.f()[[0, 20, -1]].tolist() == [0.0, 0.2, 0.9] and GRIDS.f().size == 91
    assert GRIDS.delta(1.0).tolist() == pytest.approx([0.1 * k for k in range(11)])


def test_proportional_and_additive_recover_exact_values() -> None:
    r = np.array([0.4, 0.6, 0.8, 0.9, 1.0])
    rho = np.minimum(1.0, 0.8 / r)
    assert fits.best_on_grid(
        fits.proportional_curves(r, GRIDS.f()), rho, GRIDS.f()
    ) == pytest.approx(0.2)
    declared = np.full(5, 10.0)
    accepted = r * 10
    grid = GRIDS.delta(10.0)
    curves = fits.additive_curves(declared, accepted, grid)
    assert fits.best_on_grid(curves, rho, grid) == pytest.approx(2.0)


def test_slope_check_outcomes() -> None:
    r = np.array([0.85, 0.9, 1.0, 0.5])
    exact = fits.slope_check(r, np.minimum(1, 0.8 / r), 0.2, -1.5, -0.5)
    assert exact.status == "passed" and exact.slope == pytest.approx(-1.0)
    steep = fits.slope_check(r, np.minimum(1, (0.8 / r) ** 3), 0.2, -1.5, -0.5)
    assert steep.status == "model rejected" and steep.slope == pytest.approx(-3.0)
    few = fits.slope_check(
        np.array([0.9, 1.0, 0.5]), np.array([0.9, 0.8, 1.0]), 0.2, -1.5, -0.5
    )
    assert few.status == "unavailable"  # two points beyond the kink, not "rejected"
    zero = fits.slope_check(r, np.array([0.9, -0.1, 0.8, 1.0]), 0.2, -1.5, -0.5)
    assert zero.status == "unavailable" and zero.nonpositive_rho == 1


def test_separability() -> None:
    assert not fits.separately_identified(np.full(10, 10.0), 0.25)
    assert fits.separately_identified(np.array([5.0, 10.0, 15.0, 20.0]), 0.25)


def test_breakpoint_hand_worked() -> None:
    """ρ = 1 to r = 0.5, then falling with slope −1: b = 0.5, slope = −1."""
    r = np.array([0.2, 0.4, 0.5, 0.7, 0.9])
    rho = np.where(r <= 0.5, 1.0, 1.0 - (r - 0.5))
    b, slope = fits.breakpoint(r, rho)
    assert b == pytest.approx(0.5) and slope == pytest.approx(-1.0)


def test_decreasing_fit_pools_violators() -> None:
    """1, 0.8, 0.9, 0.5: the rise 0.8 → 0.9 is pooled to 0.85, 0.85."""
    out = fits.decreasing_fit(np.array([1.0, 0.8, 0.9, 0.5]))
    assert out.tolist() == pytest.approx([1.0, 0.85, 0.85, 0.5])


def test_transition_width() -> None:
    r = np.array([0.5, 0.7, 0.8, 0.9, 1.0])
    rho = np.array([1.0, 1.0, 0.94, 0.8, 0.7])
    assert fits.transition_width(r, rho, 0.95, 0.75) == pytest.approx(1.0 - 0.8)
    assert fits.transition_width(r, np.ones(5), 0.95, 0.75) is None


def test_interval_tests() -> None:
    assert fits.excludes_zero(Interval(0.01, 0.3, 10, 0))
    assert not fits.excludes_zero(Interval(0.0, 0.3, 10, 0))
    assert fits.includes_zero(Interval(0.0, 0.1, 10, 0))
    assert not fits.includes_zero(Interval(0.02, 0.1, 10, 0))


def test_fit_models_on_exact_data() -> None:
    r = np.array([0.5, 0.7, 0.85, 0.9, 1.0])
    rho = np.minimum(1.0, 0.8 / r)
    out = fits.fit_models(
        r, rho, np.full(5, 10.0), r * 10, GRIDS, 200, 0.95, np.random.default_rng(1)
    )
    assert out is not None and out.f_hat == pytest.approx(0.2)
    assert out.delta_hat == pytest.approx(2.0)
    assert (
        fits.fit_models(
            r[:0], rho[:0], r[:0], r[:0], GRIDS, 10, 0.95, np.random.default_rng(1)
        )
        is None
    )


# ------------------------------------------------------------------ unit


def test_over_declarer_is_flagged() -> None:
    res = score_claim3(make_unit(), ADOPTION, END, SETTINGS, "A")
    offers = res.offers
    assert res.eta_hat == pytest.approx(ETA) and offers is not None and offers.fit
    assert offers.fit.f_hat == pytest.approx(0.2)
    assert offers.fit.delta_hat == pytest.approx(2.0)
    assert offers.separable is False  # MDO constant: the proportional fit decides
    assert offers.slope is not None and offers.slope.status == "passed"
    assert offers.toward_identification == 17  # A ≥ 5 MWh
    assert offers.identified
    assert offers.placebo_size == 14  # A ≤ 8 MWh: the wall proves A
    assert offers.placebo is not None and fits.includes_zero(offers.placebo.f_interval)
    assert offers.flagged


def test_flag_needs_both_branches() -> None:
    a = score_claim3(make_unit(), ADOPTION, END, SETTINGS, "A")
    b = score_claim3(make_unit(), ADOPTION, END, SETTINGS, "B")
    assert b.offers is not None and b.offers.flagged
    assert flagged_under_both(a, b)
    with pytest.raises(ValueError):
        flagged_under_both(b, a)


def test_honest_unit_is_not_flagged() -> None:
    """cap 12: every offer delivered in full, ρ = 1, f̂ = 0; nothing lies beyond the
    kink, so the slope check is unavailable and the unit not identified."""
    res = score_claim3(make_unit(cap=12.0), ADOPTION, END, SETTINGS, "A")
    offers = res.offers
    assert offers is not None and offers.fit is not None
    assert offers.fit.f_hat == pytest.approx(0.0)
    assert offers.slope is not None and offers.slope.status == "unavailable"
    assert not offers.identified and not offers.flagged


def test_r_over_one_is_counted_not_fitted() -> None:
    """Declared 7: offers with A > 7 have r > 1; they are counted, not fitted."""
    res = score_claim3(make_unit(declared=7.0), ADOPTION, END, SETTINGS, "A")
    offers = res.offers
    assert offers is not None
    over = sum(1 for a in A_VALUES if a > 7.0)
    assert offers.r_over_1 == over and offers.fitted == 21 - over


def test_empty_placebo_set_cannot_flag() -> None:
    """cap 3: no offer is proven by the wall, so condition 3 fails."""
    res = score_claim3(make_unit(cap=3.0), ADOPTION, END, SETTINGS, "A")
    assert res.offers is not None and res.offers.placebo_size == 0
    assert not res.offers.flagged


def test_bids_are_never_flagged() -> None:
    res = score_claim3(make_unit(), ADOPTION, END, SETTINGS, "A")
    assert res.bids is not None and not res.bids.flagged and res.bids.fitted == 0


def test_unscored_units() -> None:
    assert score_claim3(
        make_unit(), ADOPTION, ADOPTION + timedelta(days=3), SETTINGS, "A"
    ).unscored_reason
    no_import = make_unit(a_values=[])
    assert score_claim3(no_import, ADOPTION, END, SETTINGS, "A").unscored_reason


def test_excluded_counts_and_eta_bounds() -> None:
    t = slot(0)
    overlap = LevelSegment(
        t + timedelta(minutes=10),
        t + timedelta(minutes=20),
        1.0,
        1.0,
        acceptance_number=99,
        acceptance_time=t,
    )
    res = score_claim3(make_unit(extra_boas=[overlap]), ADOPTION, END, SETTINGS, "A")
    assert res.excluded_counts() == {ins.OTHER_BOA: 2}
    tight = replace(SETTINGS, shared=replace(SETTINGS.shared, eta_min=0.95))
    out = score_claim3(make_unit(), ADOPTION, END, tight, "A")
    assert out.eta_hat == pytest.approx(ETA) and out.unscored_reason


def test_week_without_meter_has_no_walls() -> None:
    """A gap leaves the week with no wall: every offer that week leaves the
    placebo set, so condition 3 fails."""
    res = score_claim3(make_unit(drop_period=slot(3)), ADOPTION, END, SETTINGS, "A")
    assert res.offers is not None and res.offers.placebo_size == 0


def test_slope_unavailable_when_r_does_not_vary() -> None:
    r = np.full(4, 0.9)
    check = fits.slope_check(r, np.full(4, 0.8), 0.2, -1.5, -0.5)
    assert check.status == "unavailable" and check.points == 4


def test_wall_is_read_at_the_acceptance_period() -> None:
    """Charging inside the period that holds the acceptance does not count: the
    wall is read at that period's start, before the charge, so no offer is in
    the placebo set. Read at the start of delivery instead, all 14 would be."""
    res = score_claim3(make_unit(charge_lead=1), ADOPTION, END, SETTINGS, "A")
    assert res.offers is not None and res.offers.placebo_size == 0
