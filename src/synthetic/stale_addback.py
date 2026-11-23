"""Stale add-back diagnostic: does D^decl count an instruction twice? (PROJECT.md §11)

A post-hoc check, reported only; it changes no verdict and no committed result.

D^decl adds back the export energy of every instruction accepted at or before t
(§3, `boa_export_mwh`). A declaration published before that acceptance already
counts the same energy as deliverable, so while it stays in force the energy is
counted twice. The corrected rule tested here adds back only instructions
accepted strictly before the publish time of the MDO record in force at t. Both
times are published (MDO publishTime; BOALF acceptance time), so the rule could
be applied to real units. Nothing else changes: the meter, PN protection, the
horizon, the declarations, N and the true trajectory are as committed.

Stage A (Claim 4 frame): the 100 honest four-week runs, A/A, K from the true
η = 0.88, the gate ceiling, with the decomposition's classes
(`src/synthetic/claim4_decomposition.py`). Fixed before the run: the timing
mechanism is confirmed if the corrected rule removes at least 80% of the
original rule's declaration-side crossings of 5 MWh or more.

Stage B (Claims 1–2): the 13 batteries of deviation 2 at 4 and 20 weeks, with
their suite seeds, all four declarer–scoring pairs, scored by the committed code
(`score_unit`) under each rule. The original rule must reproduce the committed
cells (`outputs/known_answer/claims12_by_length.json`) for those lengths, or the
script stops. Fixed before the run: the effect is material if any matched-pair
band changes between pass and miss, or if any battery's matched-pair Claim 1 or
Claim 2 outcome changes in more than 1 of 100 runs at either length.

Usage:
    uv run python -m src.synthetic.stale_addback --stage A
    uv run python -m src.synthetic.stale_addback --stage B
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import sys
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from src.claims import unit as unit_module
from src.claims.declared_series import _Index, declared_series, protection_end
from src.claims.screens import screen_meter, week_boundaries
from src.claims.unit import load_claim_settings, week_starts
from src.model.params import load_params
from src.model.types import Dataset, Submission, UnitInputs, require_utc
from src.physics.declared import (
    Branch,
    declared_at,
    declared_deliverable_mwh,
    record_ends,
    record_level,
)
from src.physics.protection import boa_export_mwh, pn_protected_mwh
from src.physics.walls import cumulative_change
from src.synthetic import bands
from src.synthetic import battery as bt
from src.synthetic import claim4_check as check
from src.synthetic.bands import DEVIATION_2_BANDS, RunOutcome
from src.synthetic.claim4_decomposition import (
    LARGE_MWH,
    line_at_starts,
    tally_week,
    truth_at_starts,
)
from src.synthetic.settings import load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUT_A = ROOT / "outputs" / "known_answer" / "stale_addback_claim4.json"
OUT_B = ROOT / "outputs" / "known_answer" / "stale_addback_claims12.json"
COMMITTED_B = ROOT / "outputs" / "known_answer" / "claims12_by_length.json"
LENGTHS = ("short", "long")
CONFIRMED_SHARE = 0.8
MATERIAL_RUNS = 1  # more than this many changed runs, of 100, is material

# ------------------------------------------------------------------ the rule


def in_force_publish_times(
    submissions: Sequence[Submission],
    dataset: Dataset,
    times: Sequence[datetime],
    default_abs_mwh: float,
    data_end: datetime,
) -> tuple[datetime | None, ...]:
    """Return the publish time of the `dataset` record in force at each time.

    Mirrors `declared_at` (M9): records are painted in priority order and a
    default record means no declaration. None wherever `declared_at` gives None.
    """
    require_utc(data_end, "data_end")
    ordered = sorted(times)
    if list(times) != ordered:
        raise ValueError("times must be sorted")
    records = [s for s in submissions if s.dataset == dataset]
    ends = record_ends(records, data_end)
    out: list[datetime | None] = [None] * len(ordered)
    for record in sorted(
        records, key=lambda r: (r.publish_time, r.serial, r.time_from)
    ):
        lo = bisect.bisect_left(ordered, record.time_from)
        hi = bisect.bisect_left(ordered, ends[record])
        for i in range(lo, hi):
            level = record_level(record, ordered[i], ends[record])
            out[i] = None if abs(level) >= default_abs_mwh else record.publish_time
    return tuple(out)


def declared_series_corrected(
    unit: UnitInputs,
    times: Sequence[datetime],
    eta: float,
    branch: Branch,
    extra_periods: int,
    horizon_hours: float | None,
    default_abs_mwh: float,
    data_end: datetime,
) -> tuple[float | None, ...]:
    """Return D^decl adding back only instructions accepted before the record.

    As `declared_series`, except that B^exp counts an instruction only if it was
    accepted strictly before the publish time of the MDO record in force at t.
    """
    mdo = declared_at(unit.submissions, "MDO", times, default_abs_mwh, data_end)
    published = in_force_publish_times(
        unit.submissions, "MDO", times, default_abs_mwh, data_end
    )
    pn, boas = _Index(unit.pn), _Index(unit.boas)
    series: list[float | None] = []
    for t, mdo_mwh, pub in zip(times, mdo, published, strict=True):
        if mdo_mwh is None or pub is None:
            series.append(None)
            continue
        end = protection_end(t, extra_periods, horizon_hours)
        pn_near = pn.overlapping(t, end)
        p_exp, _ = pn_protected_mwh(pn_near, t, end)
        known = [
            s
            for s in boas.overlapping(t, end)
            if s.acceptance_time is not None and s.acceptance_time < pub
        ]
        b_exp = boa_export_mwh(known, pn_near, t, end)
        series.append(declared_deliverable_mwh(mdo_mwh, p_exp, b_exp, eta, branch))
    return tuple(series)


# ------------------------------------------------------------------ stage A


@dataclass(frozen=True)
class StageA:
    """One run's counts in the Claim 4 frame (true η, gate N, A/A)."""

    stale_periods: int
    counted_periods: int
    violations: dict[str, int]
    large_declaration: dict[str, int]
    large_declaration_at_stale: int


def stage_a_run(run_index: int) -> StageA:
    """Rebuild one honest four-week run of the committed check; compare rules."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    physics = bt.load_physics()
    claims = load_claim_settings()
    tol = load_params().number("claim4.nameplate_tolerance")
    (li,) = bands.length_indices(["short"])
    length = settings.lengths[li]
    rng = bt.run_rng(settings.master_seed, bt.HONEST.name, li, run_index)
    sim = bt.simulate(
        bt.HONEST, length, settings, physics, bt.load_dc_energy(settings), rng, faults
    )
    weeks = week_starts(length.adoption_week_start, length.end)
    scored_from = (weeks[0] - sim.start) // timedelta(minutes=1)
    n = check.ceilings(sim.stored_mwh, scored_from, physics.eta, physics.energy_mwh)[
        check.GATE
    ]
    unit = bt.unit_inputs(sim, "A", bt.lag_minutes(bt.HONEST, settings, faults), faults)

    def both(times: Sequence[datetime]) -> dict[str, tuple[float | None, ...]]:
        x = (claims.extra_periods, claims.default_abs_mwh, length.end)
        original = declared_series(
            unit, times, physics.eta, "A", x[0], None, x[1], x[2]
        )
        corrected = declared_series_corrected(
            unit, times, physics.eta, "A", x[0], None, x[1], x[2]
        )
        return {"original": original[:-1], "corrected": corrected[:-1]}

    stale = counted = 0
    violations = {"original": 0, "corrected": 0}
    large = {"original": 0, "corrected": 0}
    large_at_stale = 0
    for week_start in weeks:
        meter = screen_meter(unit.meter, week_start, claims.sf_or_later_runs)
        if meter.unscored_reason is not None:
            continue
        times = week_boundaries(week_start)
        rules = both(times)
        first = (week_start - sim.start) // timedelta(minutes=1)
        truth, active = truth_at_starts(sim.stored_mwh, sim.boa_id, first, physics.eta)
        line = line_at_starts(cumulative_change(meter.periods, physics.eta), n, tol)
        differs = [
            a is not None and b is not None and bool(a != b)
            for a, b in zip(rules["original"], rules["corrected"], strict=True)
        ]
        stale += sum(differs)
        counted += sum(d is not None for d in rules["original"])
        for name, declared in rules.items():
            t = tally_week(declared, truth, line, active)
            violations[name] += sum(t.periods.values())
            large[name] += t.large["declaration"]
        for h, d in enumerate(rules["original"]):
            if d is None or not differs[h]:
                continue
            gap, margin = d - truth[h], line[h] - truth[h]
            if gap > 0 and margin >= 0 and gap - margin >= LARGE_MWH:
                large_at_stale += 1
    return StageA(stale, counted, violations, large, large_at_stale)


def summarise_a(runs: Sequence[StageA]) -> dict[str, object]:
    """Return Stage A's totals and the reading fixed before the run.

    Every count is a Python int, so the summary can be written as JSON.
    """
    runs = [
        StageA(
            int(r.stale_periods),
            int(r.counted_periods),
            {k: int(v) for k, v in r.violations.items()},
            {k: int(v) for k, v in r.large_declaration.items()},
            int(r.large_declaration_at_stale),
        )
        for r in runs
    ]
    original = sum(r.large_declaration["original"] for r in runs)
    corrected = sum(r.large_declaration["corrected"] for r in runs)
    removed = (original - corrected) / original if original else None
    return {
        "frame": "honest, short, A/A, K from true η, gate ceiling",
        "runs": len(runs),
        "counted_periods": sum(r.counted_periods for r in runs),
        "stale_periods": sum(r.stale_periods for r in runs),
        "violations": {
            rule: sum(r.violations[rule] for r in runs)
            for rule in ("original", "corrected")
        },
        "runs_with_violation": {
            rule: sum(1 for r in runs if r.violations[rule])
            for rule in ("original", "corrected")
        },
        "large_declaration_crossings": {"original": original, "corrected": corrected},
        "large_declaration_crossings_at_stale_periods": sum(
            r.large_declaration_at_stale for r in runs
        ),
        "share_removed": removed,
        "confirmed_share": CONFIRMED_SHARE,
        "timing_confirmed": removed is not None and removed >= CONFIRMED_SHARE,
    }


# ------------------------------------------------------------------ stage B


@contextmanager
def rule(corrected: bool) -> Iterator[None]:
    """Score with the corrected add-back rule inside the block, if asked."""
    if not corrected:
        yield
        return
    with mock.patch.object(unit_module, "declared_series", declared_series_corrected):
        yield


@dataclass(frozen=True)
class StageB:
    """One run of one battery under both rules, and how many boundaries differ."""

    original: RunOutcome
    corrected: RunOutcome
    stale_boundaries: int


def stage_b_run(band_index: int, length_index: int, run_index: int) -> StageB:
    """Score one Claims 1–2 run under both rules, as `bands.run_once` does."""
    with rule(False):
        original = bands.run_once("deviation-2", band_index, length_index, run_index)
    with rule(True):
        corrected = bands.run_once("deviation-2", band_index, length_index, run_index)
    return StageB(
        original, corrected, stale_boundaries(band_index, length_index, run_index)
    )


def stale_boundaries(band_index: int, length_index: int, run_index: int) -> int:
    """Count A-declared boundaries whose D^decl differs between the rules."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    band = DEVIATION_2_BANDS[band_index]
    length = settings.lengths[length_index]
    rng = bt.run_rng(settings.master_seed, band.scenario.name, length_index, run_index)
    sim = bt.simulate(
        band.scenario,
        length,
        settings,
        bt.load_physics(),
        bt.load_dc_energy(settings),
        rng,
        faults,
    )
    claims = load_claim_settings()
    unit = bt.unit_inputs(
        sim, "A", bt.lag_minutes(band.scenario, settings, faults), faults
    )
    count = 0
    eta = bt.load_physics().eta
    for week_start in week_starts(length.adoption_week_start, length.end):
        times = week_boundaries(week_start)
        a = declared_series(
            unit,
            times,
            eta,
            "A",
            claims.extra_periods,
            None,
            claims.default_abs_mwh,
            length.end,
        )
        b = declared_series_corrected(
            unit,
            times,
            eta,
            "A",
            claims.extra_periods,
            None,
            claims.default_abs_mwh,
            length.end,
        )
        count += sum(1 for x, y in zip(a, b, strict=True) if x != y)
    return count


def changed_runs(
    runs: Sequence[StageB], claim: str, pair: tuple[Branch, Branch]
) -> int:
    """Return how many runs' outcomes differ between the rules."""
    return sum(
        1
        for r in runs
        if getattr(r.original, claim)[pair] != getattr(r.corrected, claim)[pair]
    )


def summarise_b(
    records: dict[tuple[int, int], list[StageB]],
    runs: int,
    committed: dict[str, object],
) -> dict[str, object]:
    """Return both rules' band cells, the reproduction check and the reading."""
    original = bands.summarise(
        DEVIATION_2_BANDS,
        {k: [r.original for r in v] for k, v in records.items()},
        runs,
        by_length=True,
    )
    corrected = bands.summarise(
        DEVIATION_2_BANDS,
        {k: [r.corrected for r in v] for k, v in records.items()},
        runs,
        by_length=True,
    )
    reproduces = same_cells(original, committed, LENGTHS)
    flips = [
        {"original": a, "corrected": b}
        for a, b in zip(_cells(original), _cells(corrected), strict=True)
        if a.get("passed") != b.get("passed")
    ]
    settings = load_synthetic_settings()
    changes = []
    matched: tuple[tuple[Branch, Branch], ...] = (("A", "A"), ("B", "B"))
    counts: list[int] = []
    for (b, li), recs in sorted(records.items()):
        for claim in ("claim1", "claim2"):
            for pair in matched:
                n = changed_runs(recs, claim, pair)
                counts.append(n)
                changes.append(
                    {
                        "battery": DEVIATION_2_BANDS[b].scenario.name,
                        "length": settings.lengths[li].name,
                        "claim": claim,
                        "pair": "".join(pair),
                        "runs_changed": n,
                    }
                )
    stale = {
        f"{DEVIATION_2_BANDS[b].scenario.name}/{settings.lengths[li].name}": sum(
            r.stale_boundaries for r in recs
        )
        for (b, li), recs in sorted(records.items())
    }
    most = max(counts, default=0)
    material = bool(flips) or most > MATERIAL_RUNS
    return {
        "lengths": list(LENGTHS),
        "runs": runs,
        "reproduces_committed": reproduces,
        "band_flips": flips,
        "runs_changed": changes,
        "most_runs_changed": most,
        "material_runs": MATERIAL_RUNS,
        "material": reproduces and material,
        "stale_boundaries_declared_A": stale,
        "original_lengths": original.get("lengths"),
        "corrected_lengths": corrected.get("lengths"),
        "corrected_cells": _cells(corrected),
    }


def _cells(summary: dict[str, object]) -> list[dict[str, object]]:
    cells = summary["cells"]
    assert isinstance(cells, list)
    return [c for c in cells if "claim" in c]


def same_cells(
    ours: dict[str, object], committed: dict[str, object], lengths: Sequence[str]
) -> bool:
    """Return whether our band cells equal the committed ones for `lengths`."""

    def pick(summary: dict[str, object]) -> list[str]:
        cells = summary["cells"]
        assert isinstance(cells, list)
        return sorted(
            json.dumps(c, sort_keys=True) for c in cells if c.get("length") in lengths
        )

    return pick(ours) == pick(committed)


# ------------------------------------------------------------------ command line


def main(argv: Sequence[str] | None = None) -> int:
    """Run one stage once and write its summary."""
    parser = argparse.ArgumentParser(description="Stale add-back diagnostic")
    parser.add_argument("--stage", choices=("A", "B"), required=True)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    runs = load_params().integer("known_answer.runs")
    workers = args.workers or os.cpu_count()
    if args.stage == "A":
        with ProcessPoolExecutor(max_workers=workers) as pool:
            summary = summarise_a(list(pool.map(stage_a_run, range(runs))))
        out = OUT_A
    else:
        indices = bands.length_indices(LENGTHS)
        jobs = [
            (b, li, r)
            for b in range(len(DEVIATION_2_BANDS))
            for li in indices
            for r in range(runs)
        ]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(stage_b_run, *zip(*jobs, strict=True)))
        records: dict[tuple[int, int], list[StageB]] = {}
        for (b, li, _), res in zip(jobs, results, strict=True):
            records.setdefault((b, li), []).append(res)
        committed = json.loads(COMMITTED_B.read_text(encoding="utf-8"))
        summary = summarise_b(records, runs, committed)
        out = OUT_B
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, out)
    return 0 if args.stage == "A" or summary["reproduces_committed"] else 1


if __name__ == "__main__":
    sys.exit(main())
