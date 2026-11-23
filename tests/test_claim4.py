"""Claim 4 (PREREGISTRATION §6) and its synthetic check, on hand-worked units.

No band battery is simulated here: the check's runner is exercised with a stub,
so no Claim 4 result for any synthetic battery exists before the check runs
(docs/rules/claim4_synthetic_check.md, order of work).
"""

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.claims.claim4 import (
    NO_DECLARATION,
    NO_SCORED_WEEK,
    Claim4Settings,
    Claim4Week,
    claim4_week,
    excesses,
    load_claim4_settings,
    score_unit_claim4,
)
from src.claims.screens import MISSING_METER, WeekMeter, screen_meter
from src.claims.unit import (
    ETA_OUT_OF_BOUNDS,
    ETA_UNDEFINED,
    TOO_FEW_WEEKS,
    load_claim_settings,
    score_unit,
)
from src.model.types import MeterPeriod, Submission, UnitInputs, build_unit_inputs
from src.physics.declared import Branch
from src.synthetic import claim4_check as check
from src.synthetic.bands import BRANCHES
from src.synthetic.claim4_check import Cell, Runner, RunRecord, ceilings, run_suite

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)
END = WEEK0 + timedelta(days=7)
ADOPTION = WEEK0 - timedelta(days=7)
SP = timedelta(minutes=30)
SF = frozenset({"SF", "R1", "R2", "R3", "RF", "DF"})
ETA = 0.8
C4 = Claim4Settings(0.02, 1.02)
# Import 10 MWh in period 2 and export 8 in period 4: with η̂ 0.8, K is 0 at
# boundaries 0–2, 8 at boundaries 3–4 and 0 from boundary 5. max K = 8.
FLOWS = {2: -10.0, 4: 8.0}


def meter(flows: dict[int, float]) -> list[MeterPeriod]:
    """A full week of net values: zero except `flows` (export positive)."""
    return [MeterPeriod(WEEK0 + h * SP, flows.get(h, 0.0), "SF") for h in range(336)]


def week(flows: dict[int, float] = FLOWS) -> WeekMeter:
    return screen_meter(meter(flows), WEEK0, SF)


def flat(level: float, overrides: dict[int, float] | None = None) -> list[float | None]:
    """Declared energy at the 337 boundaries: `level`, except at `overrides`."""
    out: list[float | None] = [level] * 337
    for b, value in (overrides or {}).items():
        out[b] = value
    return out


# ------------------------------------------------------------------ one week


def test_settings_come_from_section_6() -> None:
    assert load_claim4_settings() == Claim4Settings(0.02, 1.02)
    with pytest.raises(ValueError):
        Claim4Settings(1.0, 1.02)
    with pytest.raises(ValueError):
        Claim4Settings(0.02, 0.99)


def test_upper_wall_violations_by_hand() -> None:
    """N = 100: the wall is 100 − (8 − K_t), so 92 at every period start but 3 and
    4, where it is 100. The tolerance is 0.02 × 100 = 2, so the line is 94 (102 at
    starts 3–4). Declaring 95 throughout exceeds it at 334 starts, by 1 MWh.
    """
    result = claim4_week(week(), flat(95.0), ETA, 100.0, C4)
    assert (result.counted, result.violations) == (336, 334)
    assert result.largest_excess_mwh == pytest.approx(1.0)
    assert result.share == pytest.approx(334 / 336)
    assert result.physics_inconsistent is False
    values = excesses(week(), flat(95.0), ETA, 100.0, 0.02)
    assert values[2] == pytest.approx(1.0)
    assert values[3] == pytest.approx(-7.0)
    assert values[4] == pytest.approx(-7.0)
    assert values[5] == pytest.approx(1.0)


def test_inequality_is_strict() -> None:
    """Equality with wall + tolerance is not a violation; any excess above it is."""
    at_line = claim4_week(week(), flat(94.0), ETA, 100.0, C4)
    assert (at_line.violations, at_line.largest_excess_mwh) == (0, None)
    assert at_line.share == 0.0
    above = claim4_week(week(), flat(94.0 + 1e-9), ETA, 100.0, C4)
    assert above.violations == 334


def test_tolerance_scales_with_the_nameplate_not_the_swing() -> None:
    """N = 50: line 50 − 8 + 1 = 43. Declaring 43.5 violates; with a tolerance of
    0.02 × swing (0.16) the line would be 42.16 and 42.5 would violate too.
    """
    assert claim4_week(week(), flat(43.5), ETA, 50.0, C4).violations == 334
    assert claim4_week(week(), flat(42.5), ETA, 50.0, C4).violations == 0


def test_largest_excess_and_a_single_violation() -> None:
    declared = flat(93.0, {10: 96.0})
    result = claim4_week(week(), declared, ETA, 100.0, C4)
    assert (result.violations, result.largest_excess_mwh) == (1, pytest.approx(2.0))


def test_wall_follows_k_through_the_week() -> None:
    """Declaring 101 at starts 3–4 and 93 elsewhere: inside the wall at 3–4 (line
    102), so no violation. Declaring 101 at start 5 is over (line 94).
    """
    inside = flat(93.0, {3: 101.0, 4: 101.0})
    assert claim4_week(week(), inside, ETA, 100.0, C4).violations == 0
    outside = flat(93.0, {5: 101.0})
    assert claim4_week(week(), outside, ETA, 100.0, C4).violations == 1


def test_undeclared_periods_are_not_counted() -> None:
    declared = flat(95.0)
    declared[3] = None
    declared[7] = None
    result = claim4_week(week(), declared, ETA, 100.0, C4)
    assert (result.counted, result.violations) == (334, 333)
    nothing: list[float | None] = [None] * 337
    empty = claim4_week(week(), nothing, ETA, 100.0, C4)
    assert empty.unscored_reason == NO_DECLARATION
    assert empty.share is None


def test_final_boundary_is_not_a_period_start() -> None:
    """The 337th boundary closes the week; it is not judged."""
    declared = flat(93.0, {336: 500.0})
    assert claim4_week(week(), declared, ETA, 100.0, C4).violations == 0


def test_missing_meter_leaves_the_week_unscored() -> None:
    gap = screen_meter(meter(FLOWS)[1:], WEEK0, SF)
    result = claim4_week(gap, flat(95.0), ETA, 100.0, C4)
    assert result.unscored_reason == MISSING_METER
    assert result.physics_inconsistent is None


def test_physics_inconsistent_week_is_flagged_and_still_scored() -> None:
    """Swing 8: inconsistent when 8 > 1.02 × N, so at N = 7 but not at N = 8."""
    low = claim4_week(week(), flat(0.0), ETA, 7.0, C4)
    assert low.physics_inconsistent is True
    assert low.unscored_reason is None and low.counted == 336
    assert claim4_week(week(), flat(0.0), ETA, 8.0, C4).physics_inconsistent is False
    # 8 > 7.9 but not > 1.02 × 7.9 = 8.058: the factor matters.
    assert claim4_week(week(), flat(0.0), ETA, 7.9, C4).physics_inconsistent is False


def test_idle_week_is_scored() -> None:
    idle = week({})
    result = claim4_week(idle, flat(98.0), ETA, 100.0, C4)
    assert (result.counted, result.violations) == (336, 0)
    assert claim4_week(idle, flat(102.5), ETA, 100.0, C4).violations == 336


def test_shapes_and_week_rules() -> None:
    with pytest.raises(ValueError):
        excesses(week(), [0.0] * 336, ETA, 100.0, 0.02)
    with pytest.raises(ValueError):
        excesses(week(), flat(0.0), ETA, 100.0, 1.0)
    with pytest.raises(ValueError):
        Claim4Week(WEEK0, 10, 11, 1.0, False, None)
    with pytest.raises(ValueError):
        Claim4Week(WEEK0, 10, 1, None, False, None)
    with pytest.raises(ValueError):
        Claim4Week(WEEK0, 10, 0, None, None, None)
    with pytest.raises(ValueError):
        Claim4Week(WEEK0, 3, 0, None, None, "reason")


# ------------------------------------------------------------------ one unit


def unit(flows: dict[int, float] = FLOWS, mdo: float | None = 40.0) -> UnitInputs:
    """One scored week (WEEK0) after an adoption week; MDO constant, no PN or BOA.

    The adoption week imports 10 MWh and exports nothing. It is outside the scoring
    window, so η̂ ignores it; counted, it would halve η̂ to 0.4.
    """
    subs = [] if mdo is None else [Submission("MDO", WEEK0, END, mdo, None, WEEK0, 1)]
    adoption = [
        MeterPeriod(ADOPTION + h * SP, -10.0 if h == 0 else 0.0, "SF")
        for h in range(336)
    ]
    return build_unit_inputs("u", None, subs, adoption + meter(flows), [], [])


def test_unit_scored_against_several_nameplates() -> None:
    """η̂ = 8/10 = 0.8. D^decl = 40 under Branch A. N = 30: line 22.6, or 30.6 at
    starts 3–4, so all 336 starts violate, the largest by 17.4. N = 100: none.
    """
    settings = load_claim_settings()
    tight, loose = score_unit_claim4(
        unit(), ADOPTION, END, settings, C4, "A", [30.0, 100.0]
    )
    assert tight.eta_hat == pytest.approx(0.8)
    assert tight.unscored_reason is None and tight.any_violation is True
    (w,) = tight.scored_weeks
    assert (w.counted, w.violations) == (336, 336)
    assert w.largest_excess_mwh == pytest.approx(17.4)
    assert loose.any_violation is False
    assert (tight.nameplate_mwh, loose.nameplate_mwh) == (30.0, 100.0)


def test_cell_counts_from_a_result() -> None:
    settings = load_claim_settings()
    tight, loose = score_unit_claim4(
        unit(), ADOPTION, END, settings, C4, "A", [30.0, 100.0]
    )
    assert check.cell(tight) == Cell(None, True, 1, 1, 336, 336, pytest.approx(17.4), 0)
    assert check.cell(loose).fails is False
    (none,) = score_unit_claim4(unit({}), ADOPTION, END, settings, C4, "A", [30.0])
    assert check.cell(none).fails is True


def test_branch_b_scales_the_declaration() -> None:
    """Branch B: D^decl = √0.8 × 40 = 35.777; at N = 30 the largest excess is 13.18."""
    settings = load_claim_settings()
    (result,) = score_unit_claim4(unit(), ADOPTION, END, settings, C4, "B", [30.0])
    (w,) = result.scored_weeks
    assert w.largest_excess_mwh == pytest.approx(math.sqrt(0.8) * 40.0 - 22.6)


def test_eta_hat_matches_claims_1_and_2() -> None:
    settings = load_claim_settings()
    (result,) = score_unit_claim4(unit(), ADOPTION, END, settings, C4, "A", [100.0])
    other = score_unit(unit(), ADOPTION, END, settings, "A", frozenset())
    assert result.eta_hat == other.eta_hat


@pytest.mark.parametrize(
    ("flows", "end", "reason"),
    [
        (FLOWS, WEEK0, TOO_FEW_WEEKS),
        ({}, END, ETA_UNDEFINED),
        ({2: -10.0, 4: 5.0}, END, ETA_OUT_OF_BOUNDS),
    ],
)
def test_unscored_units(flows: dict[int, float], end: datetime, reason: str) -> None:
    settings = load_claim_settings()
    results = score_unit_claim4(
        unit(flows), ADOPTION, end, settings, C4, "A", [30.0, 100.0]
    )
    assert [r.unscored_reason for r in results] == [reason, reason]
    assert all(r.any_violation is None and r.weeks == () for r in results)


def test_unit_with_no_declaration_has_no_scored_week() -> None:
    settings = load_claim_settings()
    (result,) = score_unit_claim4(
        unit(mdo=None), ADOPTION, END, settings, C4, "A", [100.0]
    )
    assert result.unscored_reason == NO_SCORED_WEEK
    assert result.weeks[0].unscored_reason == NO_DECLARATION
    assert result.any_violation is None


def test_nameplates_must_be_positive() -> None:
    settings = load_claim_settings()
    for bad in ([], [0.0], [100.0, -1.0]):
        with pytest.raises(ValueError):
            score_unit_claim4(unit(), ADOPTION, END, settings, C4, "A", bad)


# ------------------------------------------------------------------ ceilings


def test_ceilings_by_hand() -> None:
    """90 minutes, scored from minute 30: boundaries 30, 60, 90 hold 0, 40, 0, so
    S_max = 40 and the gate is √0.81 × 40 = 36. Minute 45 holds 50 (scored, off a
    boundary) and minute 10 holds 70 (the adoption part).
    """
    stored = np.zeros(91)
    stored[45], stored[60], stored[10] = 50.0, 40.0, 70.0
    caps = ceilings(stored, 30, 0.81, 100.0)
    assert caps == pytest.approx(
        {
            "gate": 36.0,
            "stored_peak": 40.0,
            "nominal": 100.0,
            "minute_scored": 45.0,
            "minute_run": 63.0,
        }
    )
    with pytest.raises(ValueError):
        ceilings(stored, 15, 0.81, 100.0)
    with pytest.raises(ValueError):
        ceilings(np.zeros(92), 30, 0.81, 100.0)
    with pytest.raises(ValueError):
        ceilings(stored, 90, 0.81, 100.0)


# ------------------------------------------------------------------ the gate

PASS = Cell(None, False, 4, 0, 1344, 0, None, 0)
FLAGGED = Cell(None, True, 4, 1, 1344, 3, 0.5, 0)
Failing = dict[tuple[int, int, int], dict[tuple[Branch, Branch, str], Cell]]
UNSCORED = Cell("η̂ outside bounds", None, 0, 0, 0, 0, None, 0)


def stub(failing: Failing) -> Runner:
    def runner(b: int, li: int, r: int) -> RunRecord:
        cells: dict[tuple[Branch, Branch, str], Cell] = {
            (d, s, c): PASS for d in BRANCHES for s in BRANCHES for c in check.CEILINGS
        }
        cells.update(failing.get((b, li, r), {}))
        caps = dict.fromkeys(check.CEILINGS, 50.0)
        return RunRecord(caps, cells)

    return runner


def test_gate_passes_when_nothing_fails() -> None:
    summary = run_suite(2, workers=0, runner=stub({}))
    assert summary["claim4_check_passed"] is True
    gates = summary["gates"]
    assert isinstance(gates, dict) and len(gates) == 5 * 2 * 2


def test_one_failing_matched_gate_run_fails_the_check() -> None:
    """2 runs at min_share 0.95 need both to pass, so one failure misses."""
    summary = run_suite(
        2, workers=0, runner=stub({(1, 1, 0): {("B", "B", "gate"): FLAGGED}})
    )
    assert summary["claim4_check_passed"] is False
    gates = summary["gates"]
    assert isinstance(gates, dict)
    assert gates["honest_frequency_response/long/BB/gate"] == {
        "runs_failing": 1,
        "allowed": 0,
        "passed": False,
    }


def test_an_unscored_run_counts_against_the_battery() -> None:
    summary = run_suite(
        2, workers=0, runner=stub({(4, 0, 1): {("A", "A", "gate"): UNSCORED}})
    )
    assert summary["claim4_check_passed"] is False
    cells = summary["cells"]
    assert isinstance(cells, dict)
    cell = cells["constant_under_declaration/short/AA/gate"]
    assert cell["runs_unscored"] == 1 and cell["runs_failing"] == 1
    assert cell["week_violation_rate"] == 0.0


@pytest.mark.parametrize(
    "failing",
    [
        {(0, 0, 0): {("A", "B", "gate"): FLAGGED}},  # a cross pair
        {(0, 0, 0): {("A", "A", "nominal"): FLAGGED}},  # a sensitivity ceiling
        {(5, 0, 0): {("A", "A", "gate"): FLAGGED}},  # a reported over-declarer
        {(6, 1, 1): {("B", "B", "gate"): UNSCORED}},
    ],
)
def test_only_matched_gate_cells_of_gating_batteries_gate(
    failing: Failing,
) -> None:
    assert run_suite(2, workers=0, runner=stub(failing))["claim4_check_passed"] is True


def test_rates_per_week_and_period_are_reported() -> None:
    summary = run_suite(
        2, workers=0, runner=stub({(5, 1, 0): {("A", "A", "gate"): FLAGGED}})
    )
    cells = summary["cells"]
    assert isinstance(cells, dict)
    cell = cells["constant_over_declaration/long/AA/gate"]
    assert cell["runs_with_violation"] == 1
    assert cell["week_violation_rate"] == pytest.approx(1 / 8)
    assert cell["period_violation_rate"] == pytest.approx(3 / 2688)
    assert cell["largest_excess_mwh"] == 0.5


def test_gating_and_reported_batteries_are_the_rules() -> None:
    names = [s.name for s in check.GATING]
    assert names == [
        "honest",
        "honest_frequency_response",
        "honest_ramp_limited",
        "honest_derating",
        "constant_under_declaration",
    ]
    assert [s.name for s in check.REPORTED] == [
        "constant_over_declaration",
        "proportional_over_declaration",
    ]
    assert check.LENGTHS == ("short", "long")
