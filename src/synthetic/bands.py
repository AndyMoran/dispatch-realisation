"""Known-answer bands for Claims 1 and 2 (PREREGISTRATION §8).

Each battery runs `known_answer.runs` times at each run length. Each run is
declared under Branch A and under Branch B, and each declaration is scored under
both branches. The matched pairs (A/A, B/B) are the bands; the cross pairs are
reported as diagnostics of what an unresolved M13 costs (PROJECT.md §11).

A matched cell passes when at least `bands.min_share` of its runs land in an
allowed outcome. An outcome is a flag category, or "not scored: <reason>".

Band kinds:
- build: a miss fails the build (§8); under deviation 2 (§12), a length where
  every Claim 1 build band passes is one at which Claim 1 flags are reportable.
- withdrawal: a miss withdraws Claim 1's one-sided reading (§4, §8); the build
  does not fail.
- recorded: a band whose pass or miss is recorded but gates nothing; deviation 2
  makes Claim 2's bands so.
- report: no band; counts are reported.

Two band sets: "first-run", exactly as run on 18 November 2026 and reproduced
by CI, and "deviation-2", every §8 row for Claims 1–2 at every tested length.

Contract status: a battery that holds no response contract has every week
contract-free. A battery that holds one has its contracts known, so none of its
weeks is contract-free, and Claim 2's hard flag is not scored for it, as for any
unit with contract time (§4).

Usage:
    uv run python -m src.synthetic.bands              # first-run lengths (CI)
    uv run python -m src.synthetic.bands --bands deviation-2 --lengths all \
        --report-only --output outputs/known_answer/claims12_by_length.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from src.claims.scoring import unit_score
from src.claims.unit import (
    TOO_FEW_CONTRACT_FREE,
    load_claim_settings,
    score_unit,
    week_starts,
)
from src.model.params import load_params
from src.physics.declared import Branch
from src.synthetic import battery as bt
from src.synthetic.settings import SYNTHETIC_TOML, load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claims12.json"
# The lengths of the first run (18 Nov 2026), kept as the default so CI reproduces
# its committed results. Deviation 2 (PREREGISTRATION §12) adds the others.
FIRST_RUN_LENGTHS = ("short", "long")
SCHEMA_VERSION = "1.0"
BRANCHES: tuple[Branch, Branch] = ("A", "B")
NOT_SCORED = "not scored: "

Kind = Literal["build", "withdrawal", "recorded", "report"]


@dataclass(frozen=True)
class Band:
    """One battery's Claims 1–2 rows of the §8 tables."""

    scenario: bt.Scenario
    claim1: frozenset[str]
    claim1_kind: Kind
    claim2: frozenset[str]
    claim2_kind: Kind


NO_HARD_FLAG = NOT_SCORED + TOO_FEW_CONTRACT_FREE

HONEST_BANDS = (
    Band(
        bt.HONEST,
        frozenset({"coherent"}),
        "build",
        frozenset({"none detected"}),
        "build",
    ),
    # §8 "Honest, with frequency-response noise": holds DC throughout, so its
    # weeks carry contract time and the hard flag cannot be raised (§4).
    Band(
        bt.HONEST_FR,
        frozenset({"coherent"}),
        "build",
        frozenset({NO_HARD_FLAG}),
        "build",
    ),
    # §8 one-sided-reading battery: "Coherent" in at least 95% of runs.
    Band(
        bt.HONEST_DC_EFA, frozenset({"coherent"}), "withdrawal", frozenset(), "report"
    ),
)


C1 = frozenset({"coherent"})
C1_OR_INDETERMINATE = frozenset({"coherent", "indeterminate"})
NOT_COHERENT = frozenset({"not shown coherent"})
NONE_DETECTED = frozenset({"none detected"})
PROVABLE = frozenset({"provable under-declaration"})

# Every §8 row for Claims 1–2 (deviation 2, PREREGISTRATION §12). Claim 2's bands
# are recorded, not gating. Batteries holding contracts cannot carry the hard flag
# (§4), so their Claim 2 band is "not scored on the hard flag".
DEVIATION_2_BANDS = (
    Band(bt.HONEST, C1, "build", NONE_DETECTED, "recorded"),
    Band(bt.HONEST_FR, C1, "build", frozenset({NO_HARD_FLAG}), "recorded"),
    Band(bt.HONEST_RAMP, C1, "build", NONE_DETECTED, "recorded"),
    Band(bt.OVER_CONSTANT, C1, "build", NONE_DETECTED, "recorded"),
    Band(bt.OVER_PROPORTIONAL, NOT_COHERENT, "build", NONE_DETECTED, "recorded"),
    Band(bt.STATIC_PROFILE, NOT_COHERENT, "build", NONE_DETECTED, "recorded"),
    Band(bt.REDECLARE_FAST, C1_OR_INDETERMINATE, "build", NONE_DETECTED, "recorded"),
    Band(bt.REDECLARE_SLOW, C1_OR_INDETERMINATE, "build", NONE_DETECTED, "recorded"),
    Band(bt.PN_IGNORED, NOT_COHERENT, "build", NONE_DETECTED, "recorded"),
    Band(bt.UNDER_CONSTANT, C1, "build", PROVABLE, "recorded"),
    Band(bt.HONEST_DERATE, C1, "build", NONE_DETECTED, "recorded"),
    # The two one-sided-reading batteries (§4, §8): 95% bands, withdrawal on a miss.
    Band(bt.HONEST_DC_EFA, C1, "withdrawal", frozenset(), "report"),
    Band(
        bt.OVER_PROPORTIONAL_RESERVE, NOT_COHERENT, "withdrawal", frozenset(), "report"
    ),
)

BAND_SETS: dict[str, tuple[Band, ...]] = {
    "first-run": HONEST_BANDS,
    "deviation-2": DEVIATION_2_BANDS,
}


@dataclass(frozen=True)
class RunOutcome:
    """One run's outcomes, by (declared branch, scored branch)."""

    claim1: dict[tuple[Branch, Branch], str]
    claim2: dict[tuple[Branch, Branch], str]
    violation_share: dict[tuple[Branch, Branch], float | None]
    curtailed_minutes: int
    limited_minutes: int = 0


def outcome_label(category: str | None, reason: str | None) -> str:
    """Return a flag category, or "not scored: <reason>"."""
    if category is not None:
        return category
    return NOT_SCORED + (reason or "unknown")


def run_once(
    band_set: str, band_index: int, length_index: int, run_index: int
) -> RunOutcome:
    """Simulate one run of a battery and score it under all four branch pairs."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    band = BAND_SETS[band_set][band_index]
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
    weeks = week_starts(length.adoption_week_start, length.end)
    free: frozenset[datetime] = (
        frozenset() if band.scenario.holds_contracts else frozenset(weeks)
    )
    lag = bt.lag_minutes(band.scenario, settings, faults)
    c1: dict[tuple[Branch, Branch], str] = {}
    c2: dict[tuple[Branch, Branch], str] = {}
    share: dict[tuple[Branch, Branch], float | None] = {}
    for declared in BRANCHES:
        unit = bt.unit_inputs(sim, declared, lag, faults)
        for scored in BRANCHES:
            r = score_unit(
                unit, length.adoption_week_start, length.end, claims, scored, free
            )
            c1[(declared, scored)] = outcome_label(r.claim1_category, r.claim1_reason)
            c2[(declared, scored)] = outcome_label(r.claim2_category, r.claim2_reason)
            share[(declared, scored)] = unit_score(r.claim2_weeks)
    return RunOutcome(c1, c2, share, sim.curtailed_minutes, sim.limited_minutes)


def required_runs(runs: int, min_share: float) -> int:
    """Return the fewest in-band runs that pass: ⌈min_share × runs⌉."""
    return math.ceil(min_share * runs - 1e-9)


def summarise(
    bands: Sequence[Band],
    outcomes: dict[tuple[int, int], list[RunOutcome]],
    runs: int,
    by_length: bool = False,
) -> dict[str, object]:
    """Return the suite's cells, pass marks and overall verdicts."""
    settings = load_synthetic_settings()
    need = required_runs(runs, settings.band_min_share)
    cells: list[dict[str, object]] = []
    build_ok, one_sided_ok = True, True
    for (b, li), results in sorted(outcomes.items()):
        band = bands[b]
        for claim, allowed, kind in (
            ("claim1", band.claim1, band.claim1_kind),
            ("claim2", band.claim2, band.claim2_kind),
        ):
            for declared in BRANCHES:
                for scored in BRANCHES:
                    labels = [
                        (r.claim1 if claim == "claim1" else r.claim2)[
                            (declared, scored)
                        ]
                        for r in results
                    ]
                    counts = Counter(labels)
                    matched = declared == scored
                    hits = sum(counts[a] for a in allowed)
                    passed = None
                    if matched and kind != "report":
                        passed = hits >= need
                        if kind == "build":
                            build_ok = build_ok and passed
                        elif kind == "withdrawal":
                            one_sided_ok = one_sided_ok and passed
                    cells.append(
                        {
                            "battery": band.scenario.name,
                            "length": settings.lengths[li].name,
                            "declared": declared,
                            "scored": scored,
                            "claim": claim,
                            "kind": kind if matched else "cross-pair diagnostic",
                            "allowed": sorted(allowed),
                            "counts": dict(sorted(counts.items())),
                            "in_band": hits if allowed else None,
                            "required": need if matched and kind != "report" else None,
                            "passed": passed,
                        }
                    )
        curtailed = [r.curtailed_minutes for r in results]
        cells.append(
            {
                "battery": band.scenario.name,
                "length": settings.lengths[li].name,
                "runs_with_curtailment": sum(1 for c in curtailed if c),
                "max_curtailed_minutes": max(curtailed),
            }
        )
    summary: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "runs": runs,
        "min_share": settings.band_min_share,
        "required_in_band": need,
        "settings_sha256": hashlib.sha256(SYNTHETIC_TOML.read_bytes()).hexdigest(),
        "cells": cells,
        "build_bands_passed": build_ok,
        "one_sided_reading_stands": one_sided_ok,
    }
    if by_length:
        summary["lengths"] = length_verdicts(cells, outcomes, bands)
    return summary


def length_verdicts(
    cells: Sequence[dict[str, object]],
    outcomes: dict[tuple[int, int], list[RunOutcome]],
    bands: Sequence[Band],
) -> list[dict[str, object]]:
    """Return, per length, deviation 2's verdicts (PREREGISTRATION §12).

    claim1_reportable: every matched Claim 1 build band passed at that length.
    one_sided_reading_stands: both one-sided batteries also passed there.
    claim2_bands_passed: whether every recorded Claim 2 band passed (gates nothing).
    """
    settings = load_synthetic_settings()
    out = []
    for li in sorted({li for _, li in outcomes}):
        name = settings.lengths[li].name

        def passed(claim: str, kind: str, length: str = name) -> bool:
            judged = [
                c["passed"]
                for c in cells
                if c.get("length") == length
                and c.get("claim") == claim
                and c.get("kind") == kind
            ]
            return bool(judged) and all(judged)

        limited = [
            r.limited_minutes for (_, i), rs in outcomes.items() if i == li for r in rs
        ]
        out.append(
            {
                "length": name,
                "scored_weeks": settings.lengths[li].scored_weeks,
                "claim1_reportable": passed("claim1", "build"),
                "one_sided_reading_stands": passed("claim1", "build")
                and passed("claim1", "withdrawal"),
                "claim2_bands_passed": passed("claim2", "recorded"),
                "batteries": len(bands),
                "max_limited_minutes": max(limited) if limited else 0,
            }
        )
    return out


def length_indices(names: Sequence[str]) -> list[int]:
    """Return the configured index of each named run length (its seed index)."""
    configured = [length.name for length in load_synthetic_settings().lengths]
    unknown = [n for n in names if n not in configured]
    if unknown:
        raise ValueError(f"unknown run lengths {unknown}; configured: {configured}")
    return [configured.index(n) for n in names]


def run_suite(
    band_set: str,
    runs: int,
    lengths: Sequence[str] = FIRST_RUN_LENGTHS,
    workers: int | None = None,
) -> dict[str, object]:
    """Run every band's battery `runs` times at each named length; summarise."""
    bands = BAND_SETS[band_set]
    jobs = [
        (b, li, r)
        for b in range(len(bands))
        for li in length_indices(lengths)
        for r in range(runs)
    ]
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        results = list(
            pool.map(run_once, [band_set] * len(jobs), *zip(*jobs, strict=True))
        )
    outcomes: dict[tuple[int, int], list[RunOutcome]] = {}
    for (b, li, _), result in zip(jobs, results, strict=True):
        outcomes.setdefault((b, li), []).append(result)
    return summarise(bands, outcomes, runs, by_length=band_set != "first-run")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Claims 1–2 bands, write the summary, return 1 if a build band fails."""
    parser = argparse.ArgumentParser(description="Claims 1–2 known-answer bands")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--lengths",
        default=",".join(FIRST_RUN_LENGTHS),
        help="run lengths by name, comma-separated, or 'all'",
    )
    parser.add_argument("--bands", choices=sorted(BAND_SETS), default="first-run")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="exit 0 even if a build band fails (reproducing a recorded run)",
    )
    args = parser.parse_args(argv)
    names = (
        [length.name for length in load_synthetic_settings().lengths]
        if args.lengths == "all"
        else args.lengths.split(",")
    )
    runs = load_params().integer("known_answer.runs")
    summary = run_suite(args.bands, runs, names)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)
    return 0 if args.report_only or summary["build_bands_passed"] else 1


def same_results(a: dict[str, object], b: dict[str, object]) -> bool:
    """Return whether two summaries agree in everything but the settings hash.

    The settings file gains entries over time (deviation 2 added run lengths); a
    rerun reproduces a recorded run if every cell and verdict is identical.
    """
    keep = {k for k in a.keys() | b.keys() if k != "settings_sha256"}
    return all(a.get(k) == b.get(k) for k in keep)


if __name__ == "__main__":
    sys.exit(main())
