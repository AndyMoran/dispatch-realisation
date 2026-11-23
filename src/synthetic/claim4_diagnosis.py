"""Claim 4 diagnostic: does η̂ in K explain the check's miss? (PROJECT.md §11)

Reported only; it cannot change the check's verdict, which stands as committed.

The claim under test: the honest battery crosses the upper wall because K, built
with η̂, accumulates efficiency error across each week. The diagnostic changes
only the efficiency used to build K. For each of the 100 honest four-week runs
of the committed check (same seeds, so the same simulation), under A/A:

- D^decl is computed once. A Branch A declaration does not use η̂; the script
  checks this by computing it under two efficiencies and requiring them equal.
- The meter, the boundaries and the gate ceiling N = √η × S_max are unchanged.
- Each week is judged twice: K from η̂ (the check's arm, which must reproduce the
  committed check's failing-run count, or the script stops) and K from the true
  η = 0.88.

Fixed before the run: the cause is supported if at most 5 of 100 runs have any
violation with the true η, the gate's own limit. Otherwise it is incomplete, and
meter noise, netting (ASSUMPTIONS P7), initial state, timing and boundary logic
are examined next. Run failures and per-week violations are reported separately.

Usage:
    uv run python -m src.synthetic.claim4_diagnosis \
        --output outputs/known_answer/claim4_diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.claims.claim4 import Claim4Settings, claim4_week, load_claim4_settings
from src.claims.declared_series import declared_series
from src.claims.screens import screen_meter, week_boundaries
from src.claims.unit import ClaimSettings, load_claim_settings, week_starts
from src.model.params import load_params
from src.model.types import UnitInputs
from src.physics.efficiency import eta_hat, eta_in_bounds
from src.physics.walls import cumulative_change, swing_mwh
from src.synthetic import battery as bt
from src.synthetic import claim4_check as check
from src.synthetic.bands import length_indices
from src.synthetic.settings import load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claim4_diagnosis.json"
CHECK = ROOT / "outputs" / "known_answer" / "claim4_check.json"
LENGTH = "short"
BATTERY = bt.HONEST
SUPPORTED_MAX_FAILING = 5
# Per scored week: violations, 1 if any, largest excess, swing, inconsistent.
Week = tuple[int, int, float | None, float, bool]


@dataclass(frozen=True)
class Arm:
    """One run's Claim 4 outcome with K built from one efficiency."""

    eta: float
    failed: bool
    weeks_with_violation: int
    violating_periods: int
    largest_excess_mwh: float | None
    largest_swing_mwh: float
    inconsistent_weeks: int


@dataclass(frozen=True)
class Diagnosis:
    """One run: its η̂, gate N, both arms and how far K drifts between them."""

    run: int
    eta_hat: float
    nameplate_mwh: float
    scored_weeks: int
    estimated: Arm
    true: Arm
    largest_k_gap_mwh: float


def diagnose_unit(
    unit: UnitInputs,
    adoption_week_start: datetime,
    end: datetime,
    settings: ClaimSettings,
    claim4: Claim4Settings,
    nameplate_mwh: float,
    true_eta: float,
    run: int = 0,
) -> Diagnosis:
    """Judge a unit's Branch A declarations against K from η̂ and from true η."""
    weeks = week_starts(adoption_week_start, end)
    if not weeks:
        raise ValueError("no scored weeks")
    window = [m for m in unit.meter if weeks[0] <= m.period_start < end]
    estimated = eta_hat(window)
    scored_ok = eta_in_bounds(estimated, settings.eta_min, settings.eta_max)
    arms: tuple[tuple[float, list[Week]], tuple[float, list[Week]]] = (
        (estimated, []),
        (true_eta, []),
    )
    gap = 0.0
    scored = 0
    for week_start in weeks:
        meter = screen_meter(unit.meter, week_start, settings.sf_or_later_runs)
        args = (
            settings.extra_periods,
            None,
            settings.default_abs_mwh,
            end,
        )
        times = week_boundaries(week_start)
        declared = declared_series(unit, times, estimated, "A", *args)
        if declared != declared_series(unit, times, true_eta, "A", *args):
            raise AssertionError("Branch A declarations depend on the efficiency")
        if meter.unscored_reason is None:
            k_est = cumulative_change(meter.periods, estimated)
            k_true = cumulative_change(meter.periods, true_eta)
            gap = max(gap, max(abs(a - b) for a, b in zip(k_est, k_true, strict=True)))
        for eta, out in arms:
            w = claim4_week(meter, declared, eta, nameplate_mwh, claim4)
            if w.unscored_reason is not None:
                continue
            swing = swing_mwh(cumulative_change(meter.periods, eta))
            out.append(
                (
                    w.violations,
                    int(w.violations > 0),
                    w.largest_excess_mwh,
                    swing,
                    bool(w.physics_inconsistent),
                )
            )
        scored = len(arms[0][1])
    return Diagnosis(
        run=run,
        eta_hat=estimated,
        nameplate_mwh=nameplate_mwh,
        scored_weeks=scored,
        estimated=_arm(estimated, arms[0][1], scored_ok),
        true=_arm(true_eta, arms[1][1], scored_ok),
        largest_k_gap_mwh=gap,
    )


def _arm(eta: float, weeks: list[Week], scored_ok: bool) -> Arm:
    """Summarise one arm; a run with η̂ out of bounds or no scored week fails."""
    excess = [e for _, _, e, _, _ in weeks if e is not None]
    return Arm(
        eta=eta,
        failed=not scored_ok or not weeks or any(v > 0 for v, _, _, _, _ in weeks),
        weeks_with_violation=sum(hit for _, hit, _, _, _ in weeks),
        violating_periods=sum(v for v, _, _, _, _ in weeks),
        largest_excess_mwh=max(excess) if excess else None,
        largest_swing_mwh=max((s for _, _, _, s, _ in weeks), default=0.0),
        inconsistent_weeks=sum(1 for *_, bad in weeks if bad),
    )


def run_once(run_index: int) -> Diagnosis:
    """Rebuild one honest four-week run of the committed check and diagnose it."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    physics = bt.load_physics()
    (length_index,) = length_indices([LENGTH])
    length = settings.lengths[length_index]
    rng = bt.run_rng(settings.master_seed, BATTERY.name, length_index, run_index)
    sim = bt.simulate(
        BATTERY,
        length,
        settings,
        physics,
        bt.load_dc_energy(settings),
        rng,
        faults,
    )
    weeks = week_starts(length.adoption_week_start, length.end)
    scored_from = (weeks[0] - sim.start) // timedelta(minutes=1)
    caps = check.ceilings(sim.stored_mwh, scored_from, physics.eta, physics.energy_mwh)
    lag = bt.lag_minutes(BATTERY, settings, faults)
    unit = bt.unit_inputs(sim, "A", lag, faults)
    return diagnose_unit(
        unit,
        length.adoption_week_start,
        length.end,
        load_claim_settings(),
        load_claim4_settings(),
        caps[check.GATE],
        physics.eta,
        run_index,
    )


def summarise(
    runs: Sequence[Diagnosis], committed_failing: int | None
) -> dict[str, object]:
    """Return both arms' counts, the reproduction check and the fixed reading."""

    def arm(name: str) -> dict[str, object]:
        arms = [getattr(r, name) for r in runs]
        weeks = sum(r.scored_weeks for r in runs)
        excess = [
            a.largest_excess_mwh for a in arms if a.largest_excess_mwh is not None
        ]
        return {
            "eta": "η̂ per run" if name == "estimated" else arms[0].eta,
            "runs_failing": sum(a.failed for a in arms),
            "weeks_with_violation": sum(a.weeks_with_violation for a in arms),
            "week_violation_rate": (
                sum(a.weeks_with_violation for a in arms) / weeks if weeks else None
            ),
            "violating_periods": sum(a.violating_periods for a in arms),
            "largest_excess_mwh": max(excess) if excess else None,
            "inconsistent_weeks": sum(a.inconsistent_weeks for a in arms),
        }

    estimated = arm("estimated")
    true = arm("true")
    reproduced = committed_failing is None or (
        estimated["runs_failing"] == committed_failing
    )
    failing = true["runs_failing"]
    assert isinstance(failing, int)
    etas = [r.eta_hat for r in runs]
    return {
        "battery": BATTERY.name,
        "length": LENGTH,
        "pair": "AA",
        "ceiling": check.GATE,
        "runs": len(runs),
        "committed_check_runs_failing": committed_failing,
        "reproduces_committed_check": reproduced,
        "estimated": estimated,
        "true": true,
        "eta_hat": {
            "min": min(etas),
            "median": statistics.median(etas),
            "max": max(etas),
        },
        "largest_k_gap_mwh": max(r.largest_k_gap_mwh for r in runs),
        "supported_max_failing": SUPPORTED_MAX_FAILING,
        "cause_supported": reproduced and failing <= SUPPORTED_MAX_FAILING,
        "per_run": [asdict(r) for r in runs],
    }


def committed_failing(path: Path = CHECK) -> int | None:
    """Return the committed check's failing runs for this cell, if recorded."""
    if not path.exists():
        return None
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    value = cells[f"{BATTERY.name}/{LENGTH}/AA/{check.GATE}"]["runs_failing"]
    return int(value)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the diagnostic once; return 1 if it does not reproduce the check."""
    parser = argparse.ArgumentParser(description="Claim 4 diagnostic")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    runs = load_params().integer("known_answer.runs")
    with ProcessPoolExecutor(max_workers=args.workers or os.cpu_count()) as pool:
        results = list(pool.map(run_once, range(runs)))
    summary = summarise(results, committed_failing())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)
    return 0 if summary["reproduces_committed_check"] else 1


if __name__ == "__main__":
    sys.exit(main())
