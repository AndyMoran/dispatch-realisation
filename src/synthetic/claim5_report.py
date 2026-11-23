"""Claim 5 synthetic report: how far does L recover a known lag? (PROJECT.md §11)

Reported only; §8 sets no Claim 5 band, so it gates nothing (readings of 23 Nov
2026, point 10). Three batteries redeclare a known number of minutes after each
acceptance: the honest battery (1 minute), `redeclares_after_5_minutes` and
`honest_redeclares_after_25_minutes`. Each also publishes a routine record at
every period start. Each runs 100 times at 4 weeks with the Claims 1–2 suite's
seeds; Claim 5 is computed from its Branch A declarations over the scored weeks,
through the same entry point real units use (`unit_latency`).

Reported for each battery: the known lag; the Kaplan–Meier median, 75th and 90th
percentiles and ≤ 1-minute share; counts; and, of the observed intervals, the
share that ended on a routine record rather than the response, which only the
simulation can tell apart.

Usage:
    uv run python -m src.synthetic.claim5_report \
        --output outputs/known_answer/claim5_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.claims.claim5 import (
    Interval,
    load_claim5_settings,
    summarise,
    unit_latency,
)
from src.claims.unit import load_claim_settings, week_starts
from src.model.params import load_params
from src.synthetic import battery as bt
from src.synthetic.bands import length_indices
from src.synthetic.settings import load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claim5_report.json"
LENGTH = "short"
BATTERIES = (bt.HONEST, bt.REDECLARE_FAST, bt.REDECLARE_SLOW)


def ended_on_routine(interval: Interval, start: datetime, lag_min: int) -> bool | None:
    """Return whether an observed interval ended on a routine record.

    A routine record is published at a period start; the response is published
    `lag_min` after the acceptance. A record that is both counts as the response.
    None for a censored interval.
    """
    if interval.published is None:
        return None
    if interval.published - interval.accepted == timedelta(minutes=lag_min):
        return False
    offset = (interval.published - start) // timedelta(minutes=1)
    return offset % bt.MINUTES_PER_PERIOD == 0


@dataclass(frozen=True)
class RunResult:
    """One run's intervals and how many ended on a routine record."""

    intervals: tuple[Interval, ...]
    routine: int
    default_records: int


def run_once(battery_index: int, run_index: int) -> RunResult:
    """Simulate one run, as the Claims 1–2 suite did, and compute Claim 5."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    scenario = BATTERIES[battery_index]
    (li,) = length_indices([LENGTH])
    length = settings.lengths[li]
    rng = bt.run_rng(settings.master_seed, scenario.name, li, run_index)
    sim = bt.simulate(
        scenario,
        length,
        settings,
        bt.load_physics(),
        bt.load_dc_energy(settings),
        rng,
        faults,
    )
    lag = bt.lag_minutes(scenario, settings, faults)
    unit = bt.unit_inputs(sim, "A", lag, faults)
    weeks = week_starts(length.adoption_week_start, length.end)
    result = unit_latency(
        unit,
        weeks[0],
        length.end,
        load_claim5_settings(),
        load_claim_settings().default_abs_mwh,
    )
    routine = sum(
        1 for iv in result.intervals if ended_on_routine(iv, sim.start, lag) is True
    )
    return RunResult(result.intervals, routine, result.default_records)


def summarise_battery(
    name: str, lag_min: int, runs: Sequence[RunResult], benchmark_min: float
) -> dict[str, object]:
    """Return one battery's pooled statistics against its known lag."""
    intervals = [iv for r in runs for iv in r.intervals]
    observed = sum(1 for iv in intervals if iv.observed)
    routine = sum(r.routine for r in runs)
    return {
        "battery": name,
        "known_lag_min": lag_min,
        "runs": len(runs),
        **summarise(intervals, benchmark_min),
        "ended_on_routine": routine,
        "routine_share_of_observed": routine / observed if observed else None,
        "default_records": sum(r.default_records for r in runs),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report once and write its summary."""
    parser = argparse.ArgumentParser(description="Claim 5 synthetic report")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    runs = load_params().integer("known_answer.runs")
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    jobs = [(b, r) for b in range(len(BATTERIES)) for r in range(runs)]
    with ProcessPoolExecutor(max_workers=args.workers or os.cpu_count()) as pool:
        results = list(pool.map(run_once, *zip(*jobs, strict=True)))
    benchmark = load_claim5_settings().benchmark_min
    out = []
    for b, scenario in enumerate(BATTERIES):
        mine = [res for (bi, _), res in zip(jobs, results, strict=True) if bi == b]
        lag = bt.lag_minutes(scenario, settings, faults)
        out.append(summarise_battery(scenario.name, lag, mine, benchmark))
    summary = {
        "length": LENGTH,
        "branch": "A",
        "reported_only": True,
        "batteries": out,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
