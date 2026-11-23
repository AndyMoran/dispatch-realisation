"""Claim 4 synthetic check (docs/rules/claim4_synthetic_check.md; PROJECT.md §11).

An offline, truth-calibrated benchmark of Claim 4's method, fixed by deviation 3
(PREREGISTRATION §12, tag v1.0.3-lock) and the readings of 23 Nov 2026. Each
battery runs `known_answer.runs` times at 4 and 20 scored weeks, with the Claims
1–2 suite's seeds, so each simulation is one those runs used. Each run is
declared under Branch A and under Branch B, and each declaration is scored under
both, against five ceilings:

- gate: N = √η × S_max, where S_max is the highest true stored energy at any
  settlement-period boundary of the scored weeks and η is the true efficiency.
  The only gating ceiling.
- stored_peak: N = S_max, the same ceiling in stored energy (sensitivity).
- nominal: N = U = 100 MWh, §8's common setting (sensitivity).
- minute_scored: √η × the highest stored energy at any minute of the scored weeks
  (sensitivity).
- minute_run: √η × the highest stored energy at any minute of the whole run,
  adoption week included (sensitivity).

The gate: for each gating battery, declarer and length, at most 5 of 100 runs may
fail, judged on the matched pairs (A/A, B/B) with the gate ceiling. A run fails
if any counted period of any scored week is in violation, or if the run is
unscored. 4 and 20 weeks are separate gates. Per-week and per-period rates are
reported for every cell and gate nothing.

Usage:
    uv run python -m src.synthetic.claim4_check \
        --output outputs/known_answer/claim4_check.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import timedelta
from functools import partial
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from src.claims.claim4 import Claim4Result, load_claim4_settings, score_unit_claim4
from src.claims.declared_series import ADDBACK_RULES, AddBack
from src.claims.unit import load_claim_settings, week_starts
from src.model.params import load_params
from src.physics.declared import Branch
from src.synthetic import battery as bt
from src.synthetic.bands import BRANCHES, length_indices, required_runs
from src.synthetic.settings import SYNTHETIC_TOML, load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claim4_check.json"
RULE = "docs/rules/claim4_synthetic_check.md"
SCHEMA_VERSION = "1.0"
LENGTHS = ("short", "long")

GATING = (
    bt.HONEST,
    bt.HONEST_FR,
    bt.HONEST_RAMP,
    bt.HONEST_DERATE,
    bt.UNDER_CONSTANT,
)
REPORTED = (bt.OVER_CONSTANT, bt.OVER_PROPORTIONAL)
BATTERIES = GATING + REPORTED

GATE = "gate"
CEILINGS = ("gate", "stored_peak", "nominal", "minute_scored", "minute_run")
MATCHED: tuple[tuple[Branch, Branch], ...] = (("A", "A"), ("B", "B"))


def ceilings(
    stored_mwh: NDArray[np.float64],
    scored_from_min: int,
    eta: float,
    energy_mwh: float,
) -> dict[str, float]:
    """Return each ceiling from a run's true stored energy (module docstring).

    `stored_mwh` holds S at every minute boundary from the start of the run;
    `scored_from_min` is the first scored minute, a period boundary.
    """
    if scored_from_min % bt.MINUTES_PER_PERIOD:
        raise ValueError(f"scored weeks must start on a boundary: {scored_from_min}")
    if not 0 <= scored_from_min < stored_mwh.size - 1:
        raise ValueError(f"no scored minutes: {scored_from_min}")
    if (stored_mwh.size - 1) % bt.MINUTES_PER_PERIOD:
        raise ValueError("the run must end on a period boundary")
    root = math.sqrt(eta)
    boundary_max = float(stored_mwh[scored_from_min :: bt.MINUTES_PER_PERIOD].max())
    out = {
        "gate": root * boundary_max,
        "stored_peak": boundary_max,
        "nominal": energy_mwh,
        "minute_scored": root * float(stored_mwh[scored_from_min:].max()),
        "minute_run": root * float(stored_mwh.max()),
    }
    if not out["gate"] <= out["minute_scored"] <= out["minute_run"]:
        raise AssertionError("ceilings out of order")
    return out


@dataclass(frozen=True)
class Cell:
    """One run's Claim 4 outcome for one declarer, scoring branch and ceiling."""

    unscored_reason: str | None
    any_violation: bool | None
    scored_weeks: int
    weeks_with_violation: int
    counted_periods: int
    violating_periods: int
    largest_excess_mwh: float | None
    inconsistent_weeks: int

    @property
    def fails(self) -> bool:
        """Return whether the run counts against the battery (unscored or flagged)."""
        return self.unscored_reason is not None or bool(self.any_violation)


def cell(result: Claim4Result) -> Cell:
    """Return a run's counts from one Claim 4 result."""
    weeks = result.scored_weeks
    excess = [w.largest_excess_mwh for w in weeks if w.largest_excess_mwh is not None]
    return Cell(
        unscored_reason=result.unscored_reason,
        any_violation=result.any_violation,
        scored_weeks=len(weeks),
        weeks_with_violation=sum(1 for w in weeks if w.violations > 0),
        counted_periods=sum(w.counted for w in weeks),
        violating_periods=sum(w.violations for w in weeks),
        largest_excess_mwh=max(excess) if excess else None,
        inconsistent_weeks=sum(1 for w in weeks if w.physics_inconsistent),
    )


@dataclass(frozen=True)
class RunRecord:
    """One run: its ceilings and a cell per (declarer, scorer, ceiling)."""

    ceilings: dict[str, float]
    cells: dict[tuple[Branch, Branch, str], Cell]


def run_once(
    battery_index: int,
    length_index: int,
    run_index: int,
    addback: AddBack | None = None,
) -> RunRecord:
    """Simulate one run, as the Claims 1–2 suite did, and score it on Claim 4.

    `addback` overrides the configured add-back rule; the committed check ran
    under "all", before deviation 5.
    """
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    physics = bt.load_physics()
    scenario = BATTERIES[battery_index]
    length = settings.lengths[length_index]
    rng = bt.run_rng(settings.master_seed, scenario.name, length_index, run_index)
    sim = bt.simulate(
        scenario,
        length,
        settings,
        physics,
        bt.load_dc_energy(settings),
        rng,
        faults,
    )
    weeks = week_starts(length.adoption_week_start, length.end)
    scored_from = (weeks[0] - sim.start) // timedelta(minutes=1)
    caps = ceilings(sim.stored_mwh, scored_from, physics.eta, physics.energy_mwh)
    claims = load_claim_settings()
    if addback is not None:
        claims = replace(claims, boa_addback=addback)
    c4 = load_claim4_settings()
    lag = bt.lag_minutes(scenario, settings, faults)
    cells: dict[tuple[Branch, Branch, str], Cell] = {}
    for declared in BRANCHES:
        unit = bt.unit_inputs(sim, declared, lag, faults)
        for scored in BRANCHES:
            results = score_unit_claim4(
                unit,
                length.adoption_week_start,
                length.end,
                claims,
                c4,
                scored,
                [caps[c] for c in CEILINGS],
            )
            for name, result in zip(CEILINGS, results, strict=True):
                cells[(declared, scored, name)] = cell(result)
    return RunRecord(caps, cells)


def summarise_cells(cells: Sequence[Cell]) -> dict[str, object]:
    """Return the counts and rates over one cell's runs."""
    weeks = sum(c.scored_weeks for c in cells)
    periods = sum(c.counted_periods for c in cells)
    hit_weeks = sum(c.weeks_with_violation for c in cells)
    hit_periods = sum(c.violating_periods for c in cells)
    excess = [c.largest_excess_mwh for c in cells if c.largest_excess_mwh is not None]
    reasons: dict[str, int] = {}
    for c in cells:
        if c.unscored_reason is not None:
            reasons[c.unscored_reason] = reasons.get(c.unscored_reason, 0) + 1
    return {
        "runs": len(cells),
        "runs_failing": sum(1 for c in cells if c.fails),
        "runs_with_violation": sum(1 for c in cells if c.any_violation),
        "runs_unscored": sum(reasons.values()),
        "unscored_reasons": dict(sorted(reasons.items())),
        "scored_weeks": weeks,
        "weeks_with_violation": hit_weeks,
        "week_violation_rate": hit_weeks / weeks if weeks else None,
        "counted_periods": periods,
        "violating_periods": hit_periods,
        "period_violation_rate": hit_periods / periods if periods else None,
        "largest_excess_mwh": max(excess) if excess else None,
        "inconsistent_weeks": sum(c.inconsistent_weeks for c in cells),
    }


def summarise(
    records: dict[tuple[int, int], list[RunRecord]],
    lengths: Sequence[str],
    runs: int,
    min_share: float,
) -> dict[str, object]:
    """Return every cell's counts, the gate's verdicts and the overall verdict."""
    need = required_runs(runs, min_share)
    allowed = runs - need
    cells: dict[str, object] = {}
    gates: dict[str, object] = {}
    peaks: dict[str, object] = {}
    for (b, li), recs in sorted(records.items()):
        if len(recs) != runs:
            raise ValueError(f"battery {b}, length {li}: {len(recs)} runs, not {runs}")
        name = BATTERIES[b].name
        length = lengths[li]
        peaks[f"{name}/{length}"] = {
            c: [r.ceilings[c] for r in recs] for c in ("gate", "minute_run")
        }
        for declared in BRANCHES:
            for scored in BRANCHES:
                for ceiling in CEILINGS:
                    key = f"{name}/{length}/{declared}{scored}/{ceiling}"
                    summary = summarise_cells(
                        [r.cells[(declared, scored, ceiling)] for r in recs]
                    )
                    cells[key] = summary
                    gating = (
                        b < len(GATING)
                        and (declared, scored) in MATCHED
                        and ceiling == GATE
                    )
                    if gating:
                        failing = summary["runs_failing"]
                        assert isinstance(failing, int)
                        gates[key] = {
                            "runs_failing": failing,
                            "allowed": allowed,
                            "passed": failing <= allowed,
                        }
    expected = len(GATING) * len(lengths) * len(MATCHED)
    if len(gates) != expected:
        raise ValueError(f"{len(gates)} gate cells, expected {expected}")
    passed = all(isinstance(g, dict) and g["passed"] is True for g in gates.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "rule": RULE,
        "settings_sha256": hashlib.sha256(SYNTHETIC_TOML.read_bytes()).hexdigest(),
        "runs": runs,
        "min_share": min_share,
        "lengths": list(lengths),
        "gating_batteries": [s.name for s in GATING],
        "reported_batteries": [s.name for s in REPORTED],
        "ceilings": list(CEILINGS),
        "gates": gates,
        "claim4_check_passed": passed,
        "cells": cells,
        "ceiling_values": peaks,
    }


Runner = Callable[[int, int, int], RunRecord]


def run_suite(
    runs: int,
    lengths: Sequence[str] = LENGTHS,
    workers: int | None = None,
    runner: Runner = run_once,
) -> dict[str, object]:
    """Run every battery `runs` times at each length; summarise.

    `workers=0` runs in this process, which tests use with a stub `runner`.
    """
    settings = load_synthetic_settings()
    indices = length_indices(lengths)
    jobs = [
        (b, li, r)
        for b in range(len(BATTERIES))
        for li in range(len(indices))
        for r in range(runs)
    ]
    if workers == 0:
        results = [runner(b, indices[li], r) for b, li, r in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
            results = list(
                pool.map(
                    runner,
                    [b for b, _, _ in jobs],
                    [indices[li] for _, li, _ in jobs],
                    [r for _, _, r in jobs],
                )
            )
    records: dict[tuple[int, int], list[RunRecord]] = {}
    for (b, li, _), result in zip(jobs, results, strict=True):
        records.setdefault((b, li), []).append(result)
    return summarise(records, lengths, runs, settings.band_min_share)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check once and write its summary. The verdict is in the output."""
    parser = argparse.ArgumentParser(description="Claim 4 synthetic check")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--addback",
        choices=ADDBACK_RULES,
        default=None,
        help="add-back rule; default config/scoring.toml. The committed check "
        "(23 Nov 2026) ran under 'all', before deviation 5",
    )
    args = parser.parse_args(argv)
    runs = load_params().integer("known_answer.runs")
    rule = args.addback or load_claim_settings().boa_addback
    summary = run_suite(runs, LENGTHS, args.workers, partial(run_once, addback=rule))
    summary["boa_addback"] = rule
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
