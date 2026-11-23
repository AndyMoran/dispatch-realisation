"""Claim 4 decomposition: is each crossing on the declaration side or the wall side?

Reported only (PROJECT.md §11); it cannot change any verdict.

The simulation knows the honest battery's true stored energy S_t, so its true
deliverable energy at the meter, √η × S_t, can stand between the declaration and
the wall. At each counted period start t, Claim 4's excess splits exactly as

    excess_t = (D^decl_t − √η·S_t) − (line_t − √η·S_t)
             = declaration gap      − wall margin

where line_t = N − (max K − K_t) + 0.02 × N. With K exact, the wall margin is at
least 0.02 × N, so an honest crossing needs the declaration above the truth, the
line below the truth, or both. Each violating period falls in exactly one class:

- declaration: D^decl above √η·S_t, and the line not below it;
- wall: the line below √η·S_t, and D^decl not above it;
- both: D^decl above and the line below.

Design: the 100 honest four-week runs of the committed check, same seeds, under
A/A, against the gate ceiling N = √η × S_max, in two arms as in the first
diagnostic: K from η̂ and K from the true η = 0.88. The identity above is checked
for every counted period against `src/claims/claim4.py`'s own excess.

Fixed before the run: a class accounts for the residual crossings if it holds at
least 80% of the true-η arm's violating periods with an excess of at least 5 MWh.
Otherwise the source is mixed. Reported for each class and arm: violating periods
(all, and with excess ≥ 5 MWh), runs with any, the largest declaration gap and
the most negative wall margin, and the share of declaration-side periods with an
instruction in progress at t.

Usage:
    uv run python -m src.synthetic.claim4_decomposition \
        --output outputs/known_answer/claim4_decomposition.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from src.claims.claim4 import Claim4Settings, excesses, load_claim4_settings
from src.claims.declared_series import AddBack, declared_series
from src.claims.screens import WeekMeter, screen_meter, week_boundaries
from src.claims.unit import load_claim_settings, week_starts
from src.model.params import load_params
from src.physics.efficiency import eta_hat
from src.physics.walls import cumulative_change, upper_wall
from src.synthetic import battery as bt
from src.synthetic import claim4_check as check
from src.synthetic.bands import length_indices
from src.synthetic.settings import load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claim4_decomposition.json"
LENGTH = "short"
BATTERY = bt.HONEST
LARGE_MWH = 5.0
ACCOUNTS_SHARE = 0.8
CLASSES = ("declaration", "wall", "both")
ARMS = ("estimated", "true")
IDENTITY_TOL_MWH = 1e-9
# The committed check ran before deviation 5, so this decomposition of it keeps
# that add-back rule.
ADDBACK: AddBack = "all"


def classify(declaration_gap: float, wall_margin: float) -> str:
    """Return the class of a violating period (module docstring)."""
    if declaration_gap - wall_margin <= 0.0:
        raise ValueError("not a violation: declaration gap ≤ wall margin")
    above = declaration_gap > 0.0
    below = wall_margin < 0.0
    if above and below:
        return "both"
    return "declaration" if above else "wall"


@dataclass
class Tally:
    """Counts for one arm, by class."""

    periods: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CLASSES, 0))
    large: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CLASSES, 0))
    runs: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CLASSES, 0))
    declaration_with_instruction: int = 0
    largest_declaration_gap_mwh: float | None = None
    lowest_wall_margin_mwh: float | None = None

    def add(self, other: Tally) -> None:
        """Add another tally's counts into this one."""
        for name in CLASSES:
            self.periods[name] += other.periods[name]
            self.large[name] += other.large[name]
            self.runs[name] += other.runs[name]
        self.declaration_with_instruction += other.declaration_with_instruction
        self.largest_declaration_gap_mwh = _max(
            self.largest_declaration_gap_mwh, other.largest_declaration_gap_mwh
        )
        self.lowest_wall_margin_mwh = _min(
            self.lowest_wall_margin_mwh, other.lowest_wall_margin_mwh
        )


def _max(a: float | None, b: float | None) -> float | None:
    return b if a is None else a if b is None else max(a, b)


def _min(a: float | None, b: float | None) -> float | None:
    return b if a is None else a if b is None else min(a, b)


def tally_week(
    declared: Sequence[float | None],
    truth: Sequence[float],
    line: Sequence[float],
    instruction: Sequence[bool],
) -> Tally:
    """Classify each violating period start of one week (one value per start)."""
    if not len(declared) == len(truth) == len(line) == len(instruction):
        raise ValueError("one value per period start")
    t = Tally()
    for d, s, w, active in zip(declared, truth, line, instruction, strict=True):
        if d is None:
            continue
        gap, margin = d - s, w - s
        if gap - margin <= 0.0:
            continue
        name = classify(gap, margin)
        t.periods[name] += 1
        if gap - margin >= LARGE_MWH:
            t.large[name] += 1
        if name == "declaration" and active:
            t.declaration_with_instruction += 1
        if name != "wall":
            t.largest_declaration_gap_mwh = _max(t.largest_declaration_gap_mwh, gap)
        if name != "declaration":
            t.lowest_wall_margin_mwh = _min(t.lowest_wall_margin_mwh, margin)
    return t


def line_at_starts(
    k_mwh: Sequence[float], nameplate_mwh: float, tolerance_fraction: float
) -> list[float]:
    """Return N − (max K − K_t) + tolerance × N at each period start."""
    wall = upper_wall(k_mwh, nameplate_mwh)
    return [w + tolerance_fraction * nameplate_mwh for w in wall[:-1]]


def run_once(run_index: int) -> dict[str, Tally]:
    """Rebuild one honest four-week run of the committed check and decompose it."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    physics = bt.load_physics()
    claims = load_claim_settings()
    c4 = load_claim4_settings()
    (length_index,) = length_indices([LENGTH])
    length = settings.lengths[length_index]
    rng = bt.run_rng(settings.master_seed, BATTERY.name, length_index, run_index)
    sim = bt.simulate(
        BATTERY, length, settings, physics, bt.load_dc_energy(settings), rng, faults
    )
    weeks = week_starts(length.adoption_week_start, length.end)
    scored_from = (weeks[0] - sim.start) // timedelta(minutes=1)
    n = check.ceilings(sim.stored_mwh, scored_from, physics.eta, physics.energy_mwh)[
        check.GATE
    ]
    unit = bt.unit_inputs(sim, "A", bt.lag_minutes(BATTERY, settings, faults), faults)
    window = [m for m in unit.meter if weeks[0] <= m.period_start < length.end]
    etas = {"estimated": eta_hat(window), "true": physics.eta}
    out = {arm: Tally() for arm in ARMS}
    for week_start in weeks:
        meter = screen_meter(unit.meter, week_start, claims.sf_or_later_runs)
        if meter.unscored_reason is not None:
            continue
        declared = declared_series(
            unit,
            week_boundaries(week_start),
            etas["estimated"],
            "A",
            claims.extra_periods,
            None,
            claims.default_abs_mwh,
            length.end,
            ADDBACK,
        )[:-1]
        first = (week_start - sim.start) // timedelta(minutes=1)
        truth, active = truth_at_starts(sim.stored_mwh, sim.boa_id, first, physics.eta)
        for arm in ARMS:
            k = cumulative_change(meter.periods, etas[arm])
            line = line_at_starts(k, n, c4.tolerance_fraction)
            check_identity(declared, truth, line, meter, etas[arm], n, c4)
            out[arm].add(tally_week(declared, truth, line, active))
    for tally in out.values():
        tally.runs = {name: int(tally.periods[name] > 0) for name in CLASSES}
    return out


def truth_at_starts(
    stored_mwh: NDArray[np.float64],
    boa_id: NDArray[np.int64],
    first_min: int,
    eta: float,
    periods: int = 336,
) -> tuple[list[float], list[bool]]:
    """Return √η·S and whether an instruction is in progress, at each period start."""
    idx = [first_min + bt.MINUTES_PER_PERIOD * h for h in range(periods)]
    root = math.sqrt(eta)
    return [root * float(stored_mwh[i]) for i in idx], [
        bool(boa_id[i] >= 0) for i in idx
    ]


def check_identity(
    declared: Sequence[float | None],
    truth: Sequence[float],
    line: Sequence[float],
    meter: WeekMeter,
    eta: float,
    nameplate_mwh: float,
    c4: Claim4Settings,
) -> None:
    """Raise unless declaration gap − wall margin equals Claim 4's own excess."""
    own = excesses(meter, [*declared, None], eta, nameplate_mwh, c4.tolerance_fraction)
    for d, s, w, e in zip(declared, truth, line, own, strict=True):
        if d is None or e is None:
            continue
        if abs(((d - s) - (w - s)) - e) > IDENTITY_TOL_MWH:
            raise AssertionError("decomposition does not sum to Claim 4's excess")


def summarise(runs: Sequence[dict[str, Tally]]) -> dict[str, object]:
    """Return both arms' totals and the fixed reading for the true-η arm."""
    totals = {arm: Tally() for arm in ARMS}
    for r in runs:
        for arm in ARMS:
            totals[arm].add(r[arm])
    true = totals["true"]
    large = sum(true.large.values())
    leader = max(CLASSES, key=lambda c: true.large[c])
    share = true.large[leader] / large if large else None
    accounts = leader if share is not None and share >= ACCOUNTS_SHARE else "mixed"
    return {
        "battery": BATTERY.name,
        "length": LENGTH,
        "pair": "AA",
        "ceiling": check.GATE,
        "runs": len(runs),
        "large_mwh": LARGE_MWH,
        "accounts_share": ACCOUNTS_SHARE,
        "arms": {arm: asdict(totals[arm]) for arm in ARMS},
        "true_large_violations": large,
        "true_leading_class": leader if large else None,
        "true_leading_share": share,
        "reading": accounts if large else "no large violations",
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the decomposition once and write its summary."""
    parser = argparse.ArgumentParser(description="Claim 4 decomposition")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    runs = load_params().integer("known_answer.runs")
    with ProcessPoolExecutor(max_workers=args.workers or os.cpu_count()) as pool:
        results = list(pool.map(run_once, range(runs)))
    summary = summarise(results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
