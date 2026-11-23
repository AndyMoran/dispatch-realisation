"""The Claim 4 diagnostic (src/synthetic/claim4_diagnosis.py), on hand-built units.

No band battery is simulated here; the diagnostic runs once, after this commit.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.claims.claim4 import Claim4Settings
from src.claims.unit import load_claim_settings
from src.model.types import MeterPeriod, Submission, UnitInputs, build_unit_inputs
from src.synthetic import claim4_diagnosis as diag
from src.synthetic.claim4_diagnosis import Arm, Diagnosis, diagnose_unit, summarise

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)
END = WEEK0 + timedelta(days=7)
ADOPTION = WEEK0 - timedelta(days=7)
SP = timedelta(minutes=30)
C4 = Claim4Settings(0.02, 1.02)
# η̂ = 8/10 = 0.8: K is 0 at boundaries 0–2, 8 at 3–4 and 0 from 5.
FLOWS = {2: -10.0, 4: 8.0}


def unit(flows: dict[int, float] = FLOWS, mdo: float = 93.5) -> UnitInputs:
    meter = [MeterPeriod(WEEK0 + h * SP, flows.get(h, 0.0), "SF") for h in range(336)]
    mdo_record = Submission("MDO", WEEK0, END, mdo, None, WEEK0, 1)
    return build_unit_inputs("u", None, [mdo_record], meter, [], [])


def run(u: UnitInputs, true_eta: float) -> Diagnosis:
    return diagnose_unit(u, ADOPTION, END, load_claim_settings(), C4, 100.0, true_eta)


def test_same_efficiency_gives_identical_arms() -> None:
    d = run(unit(), 0.8)
    assert d.eta_hat == pytest.approx(0.8)
    assert d.estimated == d.true
    assert d.largest_k_gap_mwh == 0.0
    assert d.scored_weeks == 1


def test_only_k_changes_between_arms_by_hand() -> None:
    """True η 0.9: K is 0, then 9 at boundaries 3–4, then 1. N = 100, D = 93.5.

    η̂ arm: line 94 (102 at starts 3–4): no violation.
    True arm: max K = 9, so the line is 93 at starts 0–2, 102 at 3–4, 94 from 5:
    3 violations, each 0.5. The two K differ by at most 1 MWh.
    """
    d = run(unit(), 0.9)
    assert d.estimated.failed is False and d.estimated.violating_periods == 0
    assert d.true.failed is True
    assert d.true.violating_periods == 3
    assert d.true.largest_excess_mwh == pytest.approx(0.5)
    assert d.true.largest_swing_mwh == pytest.approx(9.0)
    assert d.estimated.largest_swing_mwh == pytest.approx(8.0)
    assert d.largest_k_gap_mwh == pytest.approx(1.0)
    assert (d.estimated.eta, d.true.eta) == (pytest.approx(0.8), 0.9)


def test_eta_hat_out_of_bounds_fails_both_arms() -> None:
    d = run(unit({2: -10.0, 4: 5.0}), 0.88)
    assert d.estimated.failed and d.true.failed


def arm(failed: bool, weeks: int = 0) -> Arm:
    return Arm(0.88, failed, weeks, weeks, 1.0 if weeks else None, 50.0, 0)


def record(i: int, est: bool, true: bool) -> Diagnosis:
    return Diagnosis(i, 0.85, 93.0, 4, arm(est, int(est)), arm(true, int(true)), 2.0)


@pytest.mark.parametrize(
    ("true_failing", "committed", "supported", "reproduced"),
    [
        (5, 10, True, True),
        (6, 10, False, True),
        (0, 9, False, False),
        (0, None, True, True),
    ],
)
def test_reading_is_fixed_before_the_run(
    true_failing: int, committed: int | None, supported: bool, reproduced: bool
) -> None:
    runs = [record(i, i < 10, i < true_failing) for i in range(100)]
    s = summarise(runs, committed)
    assert s["reproduces_committed_check"] is reproduced
    assert s["cause_supported"] is supported
    estimated, true = s["estimated"], s["true"]
    assert isinstance(estimated, dict) and isinstance(true, dict)
    assert (estimated["runs_failing"], true["runs_failing"]) == (10, true_failing)
    assert true["week_violation_rate"] == pytest.approx(true_failing / 400)


def test_committed_failing_reads_the_check(tmp_path: Path) -> None:
    path = tmp_path / "check.json"
    assert diag.committed_failing(path) is None
    key = "honest/short/AA/gate"
    path.write_text(json.dumps({"cells": {key: {"runs_failing": 91}}}))
    assert diag.committed_failing(path) == 91
