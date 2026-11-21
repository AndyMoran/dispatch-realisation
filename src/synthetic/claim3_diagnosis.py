"""Why Claim 3's over-declarers were not flagged: a diagnostic of the placebo set.

Run after the Claim 3 band run (PROJECT.md §11, 21 November 2026). It changes
nothing in the suite and decides nothing; it reruns runs 0–9 at 20 weeks for the
two over-declarers and the honest battery, regime (i), A-declarer scored under
Branch A only, with the suite's seeds, and reports for each run:

- the scoring code's own placebo set (§5.6): fitted offers whose lower wall at
  the start of the acceptance's period is at least A, using the run's η̂;
- the placebo fit, and whether the run is identified and flagged under Branch A;
- each placebo offer that fell short, by its cause in the simulated ground truth:
  - "wall above true stock": √η × stored energy at acceptance was below A, so the
    lower wall overstated what the battery held (η̂ error; ASSUMPTIONS P11);
  - "held A, stopped by protection": the battery held at least A, but its
    deliverable energy after protecting PN, known instructions and contracts was
    smaller, and it stopped there;
  - "other": neither; the suite has none, and the script reports any it finds.

Usage:
    uv run python -m src.synthetic.claim3_diagnosis \
        --output outputs/known_answer/claim3_diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from src.claim3.instructions import period_floor
from src.claim3.unit import _walls, load_claim3_settings, score_claim3
from src.claims.unit import load_claim_settings, week_starts
from src.synthetic import battery as bt
from src.synthetic import regimes as rg
from src.synthetic.settings import load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claim3_diagnosis.json"
BATTERIES = (bt.OVER_PROPORTIONAL, bt.OVER_CONSTANT, bt.HONEST)
LENGTH = "long"
RUNS = range(10)
CAUSES = ("wall above true stock", "held A, stopped by protection", "other")


def cause(sim: bt.Simulation, boa: bt.Boa, a_mwh: float) -> str:
    """Return why a placebo offer fell short, from the simulated ground truth."""
    m = boa.accepted_min
    if float(sim.stored_mwh[m]) * sim.physics.root_eta < a_mwh:
        return CAUSES[0]
    prot = bt.protection(bt._working(sim), m, m - 1, sim.minutes)
    held = prot.pn_export + prot.boa_export + bt.reserved_mwh(sim, m)
    return CAUSES[1] if held > 0 else CAUSES[2]


def diagnose_run(scenario: bt.Scenario, run_index: int) -> dict[str, object]:
    """Return one run's placebo set, its fit and the causes of its shortfalls."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    names = [length.name for length in settings.lengths]
    li = names.index(LENGTH)
    length = settings.lengths[li]
    seed = (settings.master_seed, scenario.name, li, run_index)
    run = rg.simulate_regime(
        scenario,
        length,
        settings,
        bt.load_physics(),
        bt.load_dc_energy(settings),
        seed,
        faults,
        "mdo",
        "A",
    )
    lag = bt.lag_minutes(scenario, settings, faults)
    unit = bt.unit_inputs(run.sim, "A", lag, faults, run.peak)
    shared = load_claim_settings()
    result = score_claim3(
        unit, length.adoption_week_start, length.end, load_claim3_settings(shared), "A"
    )
    offers = result.offers
    assert offers is not None and result.eta_hat is not None
    weeks = week_starts(length.adoption_week_start, length.end)
    walls = _walls(unit, weeks, result.eta_hat, shared.sf_or_later_runs)
    by_number = {b.number: b for b in run.sim.boas}
    placebo = [
        m
        for m in result.measured
        if m.excluded is None
        and m.side == "offer"
        and m.r is not None
        and m.r <= 1.0
        and walls.get(period_floor(m.instruction.accepted), -1.0)
        >= abs(m.instruction.a_mwh)
    ]
    if len(placebo) != offers.placebo_size:
        raise RuntimeError("placebo set differs from the scoring code's")
    causes = dict.fromkeys(CAUSES, 0)
    short = 0
    for m in placebo:
        boa = by_number[m.instruction.number]
        delivered = float(run.sim.boa_dev_mw[boa.accepted_min : boa.end_min].sum())
        if delivered / 60.0 < m.instruction.a_mwh - 1e-9:
            short += 1
            causes[cause(run.sim, boa, m.instruction.a_mwh)] += 1
    fit = offers.placebo
    return {
        "battery": scenario.name,
        "run": run_index,
        "eta_hat": result.eta_hat,
        "identified": offers.identified,
        "flagged": offers.flagged,
        "f_hat": offers.fit.f_hat if offers.fit else None,
        "placebo_size": len(placebo),
        "placebo_f_hat": fit.f_hat if fit else None,
        "placebo_f_interval": [fit.f_interval.lower, fit.f_interval.upper]
        if fit
        else None,
        "placebo_short": short,
        "placebo_short_by_cause": causes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Diagnose runs 0–9 of each battery and write the results."""
    parser = argparse.ArgumentParser(description="Claim 3 placebo diagnosis")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    runs = [diagnose_run(s, r) for s in BATTERIES for r in RUNS]
    totals: dict[str, dict[str, int]] = {}
    for row in runs:
        t = totals.setdefault(
            str(row["battery"]),
            {"placebo_offers": 0, "short": 0, **dict.fromkeys(CAUSES, 0)},
        )
        t["placebo_offers"] += int(row["placebo_size"])  # type: ignore[call-overload]
        t["short"] += int(row["placebo_short"])  # type: ignore[call-overload]
        for k, v in row["placebo_short_by_cause"].items():  # type: ignore[attr-defined]
            t[k] += v
    out = {
        "length": LENGTH,
        "regime": "(i)",
        "declarer": "A",
        "scored": "A",
        "runs": runs,
        "totals": totals,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
