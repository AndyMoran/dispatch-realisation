"""Known-answer bands for Claim 3 (PREREGISTRATION §8).

Each battery in §8's table runs `known_answer.runs` times at 4 and at 20 scored
weeks (the 18 November lengths), under each instruction-sizing regime
(`regimes`). Each run's declarations are scored under Branch A and Branch B, and
§5.7's fourth condition makes the flag the conjunction: the same declarations must
flag under both. The A-declarer and the B-declarer are judged separately, and every
band must pass for both. Estimates (f̂, Δ̂) are read from the matched scoring: the
A-declarer scored under A, the B-declarer under B.

Pass rules (fixed before any band was computed; PROJECT.md §11):

- not flagged: in-band runs are scored under both branches and not flagged. The
  four plain honest batteries need all but `known_answer.honest_flag_max` of runs
  in band (§8: "at most 5% of the time"); other "Not flagged" cells need
  `bands.min_share` (config/synthetic.toml), the 18 November share.
- flagged, with an estimate: in-band runs are flagged and their matched estimate
  lies in §8's band; `known_answer.overdeclarer_flag_min` of runs (§8: 80%).
- flagged, or not identified: in-band runs are flagged, or not identified under
  at least one branch; `bands.min_share`.
- "r > 1 not raised" (fast redeclarer): no r > 1 instruction when scored under
  Branch A, for either declarer. Under (i), sizing and scoring read the same
  record, so A-scored r = A/MDO = u ≤ 1 for both declarers: any r > 1 there
  would mean an instruction sized beyond the published MDO, which the cell
  guards against. B-scored offers have r = u/√η̂ for both declarers, above 1
  whenever u > √η̂, for every battery: that comes from M13, not from
  redeclaring, so it is reported, not judged.
- report: counts only.

A run left unscored under either branch is a miss, as on 18 November. A band that
gates fails Claim 3's build if missed at either length; §8: "If the suite cannot
meet these bands, Claim 3 is dropped from version 1, and the report says so."

Usage:
    uv run python -m src.synthetic.claim3_bands --output \
        outputs/known_answer/claim3.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from src.claim3.unit import Claim3Result, load_claim3_settings, score_claim3
from src.claims.unit import load_claim_settings
from src.model.params import load_params
from src.physics.declared import Branch
from src.synthetic import battery as bt
from src.synthetic import regimes as rg
from src.synthetic.settings import SYNTHETIC_TOML, load_synthetic_settings

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "known_answer" / "claim3.json"
LENGTHS = ("short", "long")
SCHEMA_VERSION = "1.0"
BRANCHES: tuple[Branch, Branch] = ("A", "B")

RuleKind = Literal[
    "not flagged", "flagged with estimate", "flagged or not identified", "report"
]
Share = Literal["honest", "min_share", "overdeclarer"]


@dataclass(frozen=True)
class Rule:
    """One §8 cell: what a run must show to land in band."""

    kind: RuleKind
    share: Share | None = None
    estimate: Literal["f", "delta"] | None = None
    no_r_over_1: bool = False


@dataclass(frozen=True)
class Band:
    """A battery's two Claim 3 cells in §8's table."""

    scenario: bt.Scenario
    regime_i: Rule
    regimes_ii_iii: Rule


HONEST = Rule("not flagged", "honest")
NOT_FLAGGED = Rule("not flagged", "min_share")
REPORT = Rule("report")

# §8's table, in its order. The two one-sided-reading batteries carry no Claim 3 row.
BANDS = (
    Band(bt.HONEST, HONEST, HONEST),
    Band(bt.HONEST_FR, HONEST, HONEST),
    Band(bt.HONEST_RAMP, HONEST, HONEST),
    Band(
        bt.OVER_CONSTANT, Rule("flagged with estimate", "overdeclarer", "delta"), REPORT
    ),
    Band(
        bt.OVER_PROPORTIONAL, Rule("flagged with estimate", "overdeclarer", "f"), REPORT
    ),
    Band(bt.STATIC_PROFILE, Rule("flagged or not identified", "min_share"), REPORT),
    Band(bt.REDECLARE_FAST, Rule("not flagged", "min_share", no_r_over_1=True), REPORT),
    Band(bt.REDECLARE_SLOW, REPORT, REPORT),
    Band(bt.PN_IGNORED, REPORT, REPORT),
    Band(bt.UNDER_CONSTANT, NOT_FLAGGED, NOT_FLAGGED),
    Band(bt.HONEST_DERATE, HONEST, HONEST),
)


@dataclass(frozen=True)
class Scored:
    """One declarer's Claim 3 result under one scoring branch (offers)."""

    unscored: str | None
    fitted: int
    r_over_1: int
    toward_identification: int
    identified: bool
    flagged: bool
    f_hat: float | None
    delta_hat: float | None
    placebo_size: int
    excluded: dict[str, int]


@dataclass(frozen=True)
class Declarer:
    """One declarer's results under both branches, and its run's counts."""

    a: Scored
    b: Scored
    counts: dict[str, int]
    curtailed_minutes: int
    limited_minutes: int

    @property
    def flagged(self) -> bool:
        """§5.7's fourth condition: flagged under both branches."""
        return self.a.flagged and self.b.flagged

    def matched(self, declarer: Branch) -> Scored:
        """Return the scoring under the declarer's own branch."""
        return self.a if declarer == "A" else self.b


def scored(result: Claim3Result) -> Scored:
    """Return the offer-side summary of a Claim 3 result."""
    o = result.offers
    fit = o.fit if o is not None else None
    return Scored(
        unscored=result.unscored_reason,
        fitted=o.fitted if o else 0,
        r_over_1=o.r_over_1 if o else 0,
        toward_identification=o.toward_identification if o else 0,
        identified=bool(o and o.identified),
        flagged=bool(o and o.flagged),
        f_hat=fit.f_hat if fit else None,
        delta_hat=fit.delta_hat if fit else None,
        placebo_size=o.placebo_size if o else 0,
        excluded=result.excluded_counts(),
    )


def run_once(
    band_index: int, length_index: int, run_index: int
) -> dict[str, dict[str, Declarer]]:
    """Simulate one run of a battery under every regime; score each declarer."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    physics = bt.load_physics()
    dc = bt.load_dc_energy(settings)
    band = BANDS[band_index]
    length = settings.lengths[length_index]
    claim3 = load_claim3_settings(load_claim_settings())
    seed = (settings.master_seed, band.scenario.name, length_index, run_index)
    lag = bt.lag_minutes(band.scenario, settings, faults)
    out: dict[str, dict[str, Declarer]] = {}
    for regime in rg.REGIMES:
        out[regime] = {}
        shared = None
        if regime != "mdo":
            shared = rg.simulate_regime(
                band.scenario, length, settings, physics, dc, seed, faults, regime
            )
        for declarer in BRANCHES:
            run = shared or rg.simulate_regime(
                band.scenario,
                length,
                settings,
                physics,
                dc,
                seed,
                faults,
                regime,
                declarer,
            )
            unit = bt.unit_inputs(run.sim, declarer, lag, faults, run.peak)
            results = [
                scored(
                    score_claim3(
                        unit, length.adoption_week_start, length.end, claim3, branch
                    )
                )
                for branch in BRANCHES
            ]
            out[regime][declarer] = Declarer(
                results[0],
                results[1],
                asdict(run.counts),
                run.sim.curtailed_minutes,
                run.sim.limited_minutes,
            )
    return out


def in_band(rule: Rule, d: Declarer, declarer: Branch) -> bool:
    """Return whether one run of one declarer lands in a cell's band."""
    if d.a.unscored or d.b.unscored:
        return False
    if rule.kind == "not flagged":
        clean = not rule.no_r_over_1 or d.a.r_over_1 == 0
        return not d.flagged and clean
    if rule.kind == "flagged or not identified":
        return d.flagged or not (d.a.identified and d.b.identified)
    if rule.kind == "flagged with estimate":
        if not d.flagged:
            return False
        p = load_params()
        m = d.matched(declarer)
        value = m.f_hat if rule.estimate == "f" else m.delta_hat
        key = (
            "known_answer.f_band"
            if rule.estimate == "f"
            else "known_answer.delta_band_mwh"
        )
        low, high = p.numbers(key)
        return value is not None and low <= value <= high
    raise ValueError(f"no band for a {rule.kind!r} cell")


def required(rule: Rule, runs: int) -> int | None:
    """Return the in-band runs a cell needs, or None for a report cell."""
    if rule.kind == "report":
        return None
    p = load_params()
    if rule.share == "honest":
        return runs - math.floor(p.number("known_answer.honest_flag_max") * runs + 1e-9)
    if rule.share == "overdeclarer":
        return math.ceil(p.number("known_answer.overdeclarer_flag_min") * runs - 1e-9)
    return math.ceil(load_synthetic_settings().band_min_share * runs - 1e-9)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = len(s) // 2
    return s[k] if len(s) % 2 else 0.5 * (s[k - 1] + s[k])


def summarise(
    outcomes: dict[tuple[int, int], list[dict[str, dict[str, Declarer]]]], runs: int
) -> dict[str, object]:
    """Return every cell, its pass mark, and the per-length and overall verdicts."""
    settings = load_synthetic_settings()
    cells: list[dict[str, object]] = []
    for (b, li), results in sorted(outcomes.items()):
        band = BANDS[b]
        for regime in rg.REGIMES:
            rule = band.regime_i if regime == "mdo" else band.regimes_ii_iii
            need = required(rule, runs)
            for declarer in BRANCHES:
                ds = [r[regime][declarer] for r in results]
                matched = [d.matched(declarer) for d in ds]
                hits = (
                    sum(in_band(rule, d, declarer) for d in ds)
                    if need is not None
                    else None
                )
                totals: dict[str, int] = {}
                for d in ds:
                    for k, v in d.counts.items():
                        totals[k] = totals.get(k, 0) + v
                cells.append(
                    {
                        "battery": band.scenario.name,
                        "length": settings.lengths[li].name,
                        "regime": rg.REGIME_NAMES[regime],
                        "declarer": declarer,
                        "rule": rule.kind,
                        "required": need,
                        "in_band": hits,
                        "passed": None
                        if need is None
                        else hits is not None and hits >= need,
                        "flagged": sum(d.flagged for d in ds),
                        "flagged_under_a": sum(d.a.flagged for d in ds),
                        "flagged_under_b": sum(d.b.flagged for d in ds),
                        "identified_under_both": sum(
                            d.a.identified and d.b.identified for d in ds
                        ),
                        "unscored": sum(bool(d.a.unscored or d.b.unscored) for d in ds),
                        "matched_f_hat_median": _median(
                            [m.f_hat for m in matched if m.f_hat is not None]
                        ),
                        "matched_delta_hat_median": _median(
                            [m.delta_hat for m in matched if m.delta_hat is not None]
                        ),
                        "r_over_1_runs_under_a": sum(d.a.r_over_1 > 0 for d in ds),
                        "r_over_1_runs_under_b": sum(d.b.r_over_1 > 0 for d in ds),
                        "r_over_1_instructions_under_a": sum(d.a.r_over_1 for d in ds),
                        "r_over_1_instructions_under_b": sum(d.b.r_over_1 for d in ds),
                        "matched_fitted_median": _median(
                            [float(m.fitted) for m in matched]
                        ),
                        "matched_placebo_empty_runs": sum(
                            m.placebo_size == 0 for m in matched
                        ),
                        "instruction_counts": dict(sorted(totals.items())),
                        "runs_with_curtailment": sum(
                            d.curtailed_minutes > 0 for d in ds
                        ),
                        "max_curtailed_minutes": max(d.curtailed_minutes for d in ds),
                        "max_limited_minutes": max(d.limited_minutes for d in ds),
                    }
                )
    verdicts = []
    for li in sorted({li for _, li in outcomes}):
        name = settings.lengths[li].name
        judged = [
            c["passed"]
            for c in cells
            if c["length"] == name and c["passed"] is not None
        ]
        verdicts.append(
            {
                "length": name,
                "scored_weeks": settings.lengths[li].scored_weeks,
                "bands_met": bool(judged) and all(judged),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "runs": runs,
        "settings_sha256": hashlib.sha256(SYNTHETIC_TOML.read_bytes()).hexdigest(),
        "cells": cells,
        "lengths": verdicts,
        "claim3_bands_met": all(bool(v["bands_met"]) for v in verdicts),
    }


def run_suite(
    runs: int, lengths: Sequence[str] = LENGTHS, workers: int | None = None
) -> dict[str, object]:
    """Run every battery `runs` times at each length; summarise."""
    names = [length.name for length in load_synthetic_settings().lengths]
    indices = [names.index(n) for n in lengths]
    jobs = [
        (b, li, r) for b in range(len(BANDS)) for li in indices for r in range(runs)
    ]
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        results = list(pool.map(run_once, *zip(*jobs, strict=True)))
    outcomes: dict[tuple[int, int], list[dict[str, dict[str, Declarer]]]] = {}
    for (b, li, _), result in zip(jobs, results, strict=True):
        outcomes.setdefault((b, li), []).append(result)
    return summarise(outcomes, runs)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Claim 3 bands, write the summary, return 1 if a band is missed."""
    parser = argparse.ArgumentParser(description="Claim 3 known-answer bands")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="exit 0 even if a band is missed (reproducing a recorded run)",
    )
    args = parser.parse_args(argv)
    summary = run_suite(load_params().integer("known_answer.runs"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)
    return 0 if args.report_only or summary["claim3_bands_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
