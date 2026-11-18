"""score_unit on hand-built units: one entry point for real and synthetic units.

The meter repeats a four-period cycle: import 2 MWh, import 2 MWh, export 1.8 MWh,
export 1.8 MWh. So η̂ = 3.6/4 = 0.9, and per period η̂·E⁻ − E⁺ is +1.8, +1.8,
−1.8, −1.8: K at the period starts runs 0, 1.8, 3.6, 1.8, 0, …, so the lower wall
L = K − min K = K, and τ = 0.02 × 3.6 = 0.072 MWh.
"""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from src.claims.unit import (
    ETA_OUT_OF_BOUNDS,
    ETA_UNDEFINED,
    TOO_FEW_CONTRACT_FREE,
    TOO_FEW_WEEKS,
    UnitResult,
    load_claim_settings,
    score_unit,
    week_starts,
)
from src.model.types import MeterPeriod, Submission, UnitInputs, build_unit_inputs
from src.physics.declared import Branch

ADOPTION = datetime(2026, 6, 1, tzinfo=UTC)
SP = timedelta(minutes=30)
SETTINGS = load_claim_settings()
CYCLE = (-2.0, -2.0, 1.8, 1.8)  # net MWh, export positive
K = (0.0, 1.8, 3.6, 1.8)  # K at each period start of the cycle


def unit(
    declared: Callable[[float], float], weeks: int = 4, cycle: tuple[float, ...] = CYCLE
) -> UnitInputs:
    """A unit with the cycled meter and one record per period, from D(K) to D(K')."""
    periods = (weeks + 1) * 7 * 48
    start = ADOPTION
    meter = [MeterPeriod(start + h * SP, cycle[h % 4], "SF") for h in range(periods)]
    records = []
    for h in range(periods):
        t0, t1 = start + h * SP, start + (h + 1) * SP
        k0, k1 = K[h % 4], K[(h + 1) % 4]
        records.append(Submission("MDO", t0, t1, declared(k0), declared(k1), t0, 0))
    return build_unit_inputs("hand", 1.0, records, meter, [], [])


def end(weeks: int = 4) -> datetime:
    return ADOPTION + timedelta(days=7 * (weeks + 1))


def score(
    u: UnitInputs, weeks: int = 4, branch: Branch = "A", free: bool = True
) -> UnitResult:
    starts = week_starts(ADOPTION, end(weeks))
    contract_free = set(starts) if free else set()
    return score_unit(u, ADOPTION, end(weeks), SETTINGS, branch, contract_free)


def test_week_starts_are_the_complete_weeks_after_adoption() -> None:
    assert week_starts(ADOPTION, end(4)) == tuple(
        ADOPTION + timedelta(days=7 * k) for k in range(1, 5)
    )
    assert week_starts(ADOPTION, end(4) - timedelta(minutes=30))[
        -1
    ] == ADOPTION + timedelta(days=21)
    with pytest.raises(ValueError):
        week_starts(ADOPTION + timedelta(days=1), end(4))


def test_coherent_declarations_are_coherent() -> None:
    """D = 50 + K: every r_h is zero, so the interval is [0, 0]; D never falls
    below the wall, so no violations."""
    r = score(unit(lambda k: 50.0 + k))
    assert r.eta_hat == pytest.approx(0.9)
    assert r.claim1_category == "coherent"
    assert r.claim1_interval is not None and r.claim1_interval.upper == pytest.approx(
        0.0
    )
    assert r.claim2_category == "none detected"


def test_branch_b_reads_stored_energy() -> None:
    """Declared as stored energy, MDO = (50 + K)/√η̂, coherent under B, not A."""
    root = math.sqrt(0.9)
    u = unit(lambda k: (50.0 + k) / root)
    assert score(u, branch="B").claim1_category == "coherent"
    assert score(u, branch="A").claim1_category != "coherent"


def test_static_declarations_are_not_coherent() -> None:
    """D constant: r_h = −(η̂E⁻ − E⁺), so a week's ratio is 4 × 1.8 / 7.6 = 0.947.
    (The run's last period has no declaration at its end, so the last week differs
    slightly; week 1 does not.)"""
    r = score(unit(lambda k: 50.0))
    assert r.claim1_category == "not shown coherent"
    assert r.claim1_weeks[0].error.score == pytest.approx(7.2 / 7.6)
    assert r.claim1_interval is not None and r.claim1_interval.lower > 0.9


def test_under_declaration_is_provable_on_contract_free_weeks() -> None:
    """D = K/2 sits below L − τ = K − 0.072 wherever K > 0.144: three periods in
    four, a share of 0.75."""
    r = score(unit(lambda k: k / 2))
    assert r.claim2_category == "provable under-declaration"
    assert r.claim2_interval is not None
    assert r.claim2_interval.lower == pytest.approx(0.75)
    unknown = score(unit(lambda k: k / 2), free=False)
    assert unknown.claim2_category is None
    assert unknown.claim2_reason == TOO_FEW_CONTRACT_FREE


def test_efficiency_out_of_bounds_is_not_scored() -> None:
    r = score(unit(lambda k: 50.0, cycle=(-2.0, -2.0, 2.0, 2.0)))
    assert r.eta_hat == pytest.approx(1.0)
    assert r.unscored_reason == ETA_OUT_OF_BOUNDS
    assert r.claim1_category is None and r.claim2_category is None


def test_no_import_is_not_scored() -> None:
    r = score(unit(lambda k: 50.0, cycle=(1.0, 1.0, 1.0, 1.0)))
    assert r.unscored_reason == ETA_UNDEFINED and r.eta_hat is None


def test_too_few_weeks_for_claim_1() -> None:
    r = score(unit(lambda k: 50.0 + k, weeks=3), weeks=3)
    assert r.claim1_category is None and r.claim1_reason == TOO_FEW_WEEKS
    assert r.claim2_category == "none detected"  # two contract-free weeks suffice


def test_no_complete_week_is_not_scored() -> None:
    r = score_unit(
        unit(lambda k: 50.0),
        ADOPTION,
        ADOPTION + timedelta(days=10),
        SETTINGS,
        "A",
        set(),
    )
    assert r.unscored_reason == TOO_FEW_WEEKS


def test_same_unit_same_result() -> None:
    a = score(unit(lambda k: 50.0 + 0.9 * k))
    b = score(unit(lambda k: 50.0 + 0.9 * k))
    assert a.claim1_interval == b.claim1_interval
