"""The pinned scoring run (PREREGISTRATION §10; PROJECT.md §11, 23 Nov 2026).

    uv run python -m src.scoring.run [--workers N]

Runs once, from a clean working tree, after fleet B1610 has arrived. It assembles
every BM unit's inputs (`src/ingest/assemble.py`), scores each unit with the code
the known-answer suite tested, and writes:

- `outputs/scoring/fleet_results.json`: the preregistered fleet results.
- `outputs/scoring/sensitivity.json`: the same fleet results under the §9
  variants of deviation 7, kept apart; no variant selects a headline.
- `outputs/scoring/run_record.json`: code commit, input and output hashes, counts.
- `data/interim/scoring/unit_results.json` (gitignored): each unit's
  preregistered results, the only input to the private packs.

Public files hold no unit ID and no lead party; the run checks this before
writing. Readings: the `score` row of PROJECT.md §11, and `src/scoring/fleet.py`.

- Claims 1–2 under both branches; contract-free weeks: none (§4 coverage run), so
  no hard flag is computed. Claim 1 carries no flag (deviation 2); its interval
  goes only to the unit's own pack.
- Reliability (§4) for Claims 1 and 2, per branch: odd and even UTC days, units
  with both halves, Spearman–Brown, unit bootstrap with the master seed.
- Claim 5 (§7): each unit's acceptances from its first non-default record to the
  end of the window, pooled by Kaplan–Meier; reported once.
- M13 slope diagnostic (§9), reported only: per unit, Branch A, ΔD^decl on
  (η̂·E⁻ − E⁺) through the origin, over periods in the weeks Claim 1 scored (read
  from its result) that pass its period screens and that no accepted instruction
  overlaps. Gates: η̂ within its bounds; at least 4 weeks scored by Claim 1
  (Claim 1's own minimum, counted whether or not each week yields a usable
  period); at least 48 usable periods. `weeks` reports how many weeks did yield
  one. A non-finite point or slope stops the whole run before any file is
  written. Fleet:
  percentiles of the slope, of 1/√η̂ and of the weeks and periods used, and the
  share of units whose slope lies nearer 1/√η̂ than 1. It never selects a branch.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from src.claims import claim5 as c5
from src.claims.declared_series import declared_series
from src.claims.reliability import (
    HalfScores,
    half_scores,
    reliability_interval,
    reliability_verdict,
    spearman,
    spearman_brown,
)
from src.claims.results import load_scoring_settings
from src.claims.scoring import Interval
from src.claims.screens import efa_excluded, screen_meter, week_boundaries
from src.claims.unit import (
    TOO_FEW_WEEKS,
    ClaimSettings,
    UnitResult,
    load_claim_settings,
    score_unit,
)
from src.ingest import assemble as asm
from src.ingest import pull
from src.model.params import load_params
from src.model.types import SETTLEMENT_PERIOD, LevelSegment, UnitInputs
from src.physics.declared import Branch
from src.scoring import fleet as fl

SCHEMA_VERSION = "1.0"
BRANCHES: tuple[Branch, ...] = ("A", "B")
PREREGISTERED = "preregistered"
FLEET_OUT = Path("outputs/scoring/fleet_results.json")
SENSITIVITY_OUT = Path("outputs/scoring/sensitivity.json")
RECORD_OUT = Path("outputs/scoring/run_record.json")
PRIVATE_OUT = Path("data/interim/scoring/unit_results.json")
KNOWN_ANSWER = Path("outputs/known_answer/claims12_known.json")
HASHED_INPUTS = (
    Path("data/manifests/pull_manifest.csv"),
    Path("data/manifests/gate_a1_manifest.csv"),
    Path("data/manifests/reference_manifest.csv"),
    asm.ADOPTION_CSV,
    asm.REFERENCE_FILE,
    Path("config/claims.toml"),
    Path("config/scoring.toml"),
    KNOWN_ANSWER,
)
# A reading of the `score` row (PROJECT.md §11, 23 Nov 2026), not preregistered
# text: one day's periods. Periods within a day are autocorrelated, so the
# weeks they come from are reported beside them.
SLOPE_MIN_PERIODS = 48
NO_SLOPE_ETA = "η̂ outside bounds or undefined"
NO_SLOPE_WEEKS = "fewer than 4 Claim 1 scored weeks"
NO_SLOPE_PERIODS = "fewer than 48 usable periods"
NO_SLOPE_VARIATION = "η̂·E⁻ − E⁺ is zero in every usable period"
SHARE_DEFINITION = (
    "numerator: units whose slope satisfies |slope − 1/√η̂| < |slope − 1|, "
    "strictly, so ties count as not nearer B; denominator: this block's 'units', "
    "the units with a computed slope, which passed three gates: η̂ within its "
    "bounds, at least 4 weeks scored by Claim 1 (Claim 1's own minimum, §2, reused "
    "as a data-sufficiency gate), and at least 48 usable periods; units failing a "
    "gate are counted by reason in 'not_computed'. Where η̂ is near 1 the two "
    "predictions nearly coincide (see 'one_over_sqrt_eta') and the comparison "
    "says little; no unit is excluded for that"
)
CLAIM1_LABEL = (
    "descriptive: how closely declarations tracked the meter; no Claim 1 flag is "
    "reported, because its known-answer gate failed at every tested length "
    "(deviation 2)"
)
CLAIM2_LABEL = (
    "share of settlement periods in violation, possibly reflecting reserve or "
    "response protection; not proof of under-declaration (ASSUMPTIONS P11). Weeks "
    "are not certified contract-free; version 1 cannot separate contract-exposed "
    "weeks from those of unknown status (deviation 6)"
)
NOT_APPLICABLE = {
    "flag thresholds": "no flag is published in version 1",
    "Claim 3 identification minimum": "Claim 3 was dropped under §8",
    "protection add-back": "no auction result gives protection volumes",
}


class RunError(RuntimeError):
    """Stops the pinned run before it writes anything."""


# ------------------------------------------------------------------ variants


@dataclass(frozen=True)
class Variant:
    """One setting of §9 (deviation 7): which claims it recomputes, and how."""

    name: str
    horizon_hours: float | None
    eta_bounds: tuple[float, float] | None
    efa: bool
    claims: tuple[str, ...]


def load_variants() -> tuple[Variant, ...]:
    """Return the preregistered setting and deviation 7's three variants."""
    p = load_params()
    low, high = p.numbers("sensitivity.eta_bounds_alt")
    hours = p.number("sensitivity.horizon_alt_hours")
    return (
        Variant(PREREGISTERED, None, None, True, ("claim1", "claim2")),
        Variant(f"H = {hours:g} hours", hours, None, True, ("claim1", "claim2")),
        Variant(
            f"η̂ bounds [{low}, {high}]", None, (low, high), True, ("claim1", "claim2")
        ),
        Variant(
            "Claim 1 without the EFA boundary exclusion", None, None, False, ("claim1",)
        ),
    )


def variant_settings(base: ClaimSettings, v: Variant) -> ClaimSettings:
    """Return the claim settings a variant scores under."""
    s = base
    if v.eta_bounds is not None:
        s = replace(s, eta_min=v.eta_bounds[0], eta_max=v.eta_bounds[1])
    if not v.efa:
        s = replace(s, efa_boundary_hours=())
    return s


# ------------------------------------------------------------------ one unit


@dataclass(frozen=True)
class BranchResult:
    """A unit's Claims 1–2 under one branch and one setting: what the fleet needs."""

    eta: float | None
    unscored_reason: str | None
    claim1_weeks: int
    claim1_score: float | None
    claim1_signed: float | None
    claim1_interval: Interval | None
    claim1_reason: str | None
    claim2_weeks: int
    claim2_periods_in_violation: float
    claim2_periods_scored: float
    claim2_median: float | None
    claim2_reason: str | None
    claim1_halves: HalfScores | None
    claim2_halves: HalfScores | None


def branch_result(r: UnitResult, min_weeks: int, preregistered: bool) -> BranchResult:
    """Return what the fleet figures and packs read from a unit's result."""
    error = [w.error for w in r.claim1_weeks]
    signed = [w.signed for w in r.claim1_weeks]
    w1 = fl.scored_count(error)
    w2 = fl.scored_count(r.claim2_weeks)
    enough1 = w1 >= min_weeks and r.unscored_reason is None
    enough2 = w2 >= min_weeks and r.unscored_reason is None
    num, den = fl.pooled(r.claim2_weeks)
    reason = r.unscored_reason or TOO_FEW_WEEKS
    return BranchResult(
        eta=r.eta_hat,
        unscored_reason=r.unscored_reason,
        claim1_weeks=w1,
        claim1_score=fl.unit_median(error) if enough1 else None,
        claim1_signed=fl.unit_median(signed) if enough1 else None,
        claim1_interval=r.claim1_interval if preregistered and enough1 else None,
        claim1_reason=None if enough1 else reason,
        claim2_weeks=w2,
        claim2_periods_in_violation=num if enough2 else 0.0,
        claim2_periods_scored=den if enough2 else 0.0,
        claim2_median=fl.unit_median(r.claim2_weeks) if enough2 else None,
        claim2_reason=None if enough2 else reason,
        claim1_halves=half_scores(error) if preregistered and enough1 else None,
        claim2_halves=half_scores(r.claim2_weeks)
        if preregistered and enough2
        else None,
    )


@dataclass(frozen=True)
class Slope:
    """A unit's M13 slope diagnostic (§9), Branch A, preregistered settings."""

    slope: float | None
    periods: int
    weeks: int
    inv_sqrt_eta: float | None
    reason: str | None


@dataclass(frozen=True)
class UnitRecord:
    """Everything the run keeps for one unit."""

    unit: str
    lead_party: str
    secondary: bool
    registered_mw: float | None
    adoption_week_start: datetime
    results: dict[tuple[str, str], BranchResult]
    latency: c5.UnitLatency
    slope: Slope


def overlaps_any(
    starts: Sequence[datetime],
    segs: Sequence[LevelSegment],
    longest: timedelta,
    a: datetime,
    b: datetime,
) -> bool:
    """Return whether any segment overlaps [a, b): segments sorted by start."""
    lo = bisect.bisect_left(starts, a - longest)
    hi = bisect.bisect_left(starts, b)
    return any(s.time_to > a for s in segs[lo:hi])


def slope_from_points(
    x: Sequence[float], y: Sequence[float], weeks: int, inv: float
) -> Slope:
    """Return the slope, or why there is none, from the usable periods' points."""
    if len(x) < SLOPE_MIN_PERIODS:
        return Slope(None, len(x), weeks, inv, NO_SLOPE_PERIODS)
    s = fl.slope_through_origin(x, y)
    reason = None if s is not None else NO_SLOPE_VARIATION
    return Slope(s, len(x), weeks, inv, reason)


def m13_slope(
    unit: UnitInputs,
    scored_weeks: frozenset[datetime],
    end: datetime,
    settings: ClaimSettings,
    eta: float | None,
) -> Slope:
    """Return the unit's slope of ΔD^decl on (η̂·E⁻ − E⁺) (module docstring).

    `scored_weeks` are the weeks Claim 1 scored for this unit, Branch A,
    preregistered settings, taken from its result rather than recomputed.
    """
    if eta is None or not settings.eta_min <= eta <= settings.eta_max:
        return Slope(None, 0, 0, None, NO_SLOPE_ETA)
    inv = 1 / math.sqrt(eta)
    if len(scored_weeks) < settings.min_scored_weeks:
        return Slope(None, 0, len(scored_weeks), inv, NO_SLOPE_WEEKS)
    boas = sorted(unit.boas, key=lambda s: s.time_from)
    starts = [s.time_from for s in boas]
    longest = max((s.time_to - s.time_from for s in boas), default=timedelta(0))
    x: list[float] = []
    y: list[float] = []
    used_weeks = 0
    for ws in sorted(scored_weeks):
        meter = screen_meter(unit.meter, ws, settings.sf_or_later_runs)
        declared = declared_series(
            unit,
            week_boundaries(ws),
            eta,
            "A",
            settings.extra_periods,
            None,
            settings.default_abs_mwh,
            end,
            settings.boa_addback,
        )
        before = len(x)
        for h, p in enumerate(meter.periods):
            d0, d1 = declared[h], declared[h + 1]
            if d0 is None or d1 is None:
                continue
            if efa_excluded(p.period_start, settings.efa_boundary_hours):
                continue
            stop = p.period_start + SETTLEMENT_PERIOD
            if overlaps_any(starts, boas, longest, p.period_start, stop):
                continue
            x.append(eta * p.import_mwh - p.export_mwh)
            y.append(d1 - d0)
        used_weeks += len(x) > before
    return slope_from_points(x, y, used_weeks, inv)


@dataclass(frozen=True)
class Task:
    """One unit's inputs and the run's settings, for a worker process."""

    fleet_unit: asm.FleetUnit
    inputs: UnitInputs
    end: datetime
    settings: ClaimSettings
    variants: tuple[Variant, ...]
    claim5: c5.Claim5Settings


def score_one(task: Task) -> UnitRecord:
    """Score one unit under every branch and setting; its latency and slope."""
    fu, unit = task.fleet_unit, task.inputs
    results: dict[tuple[str, str], BranchResult] = {}
    scored: frozenset[datetime] = frozenset()
    for v in task.variants:
        s = variant_settings(task.settings, v)
        for b in BRANCHES:
            r = score_unit(
                unit,
                fu.adoption_week_start,
                task.end,
                s,
                b,
                frozenset(),
                v.horizon_hours,
            )
            results[(v.name, b)] = branch_result(
                r, s.min_scored_weeks, v.name == PREREGISTERED
            )
            if v.name == PREREGISTERED and b == "A":
                scored = frozenset(
                    w.error.week_start
                    for w in r.claim1_weeks
                    if w.error.score is not None
                )
    latency = c5.unit_latency(
        unit, fu.adopted_at, task.end, task.claim5, task.settings.default_abs_mwh
    )
    eta = results[(PREREGISTERED, "A")].eta
    slope = m13_slope(unit, scored, task.end, task.settings, eta)
    return UnitRecord(
        fu.unit,
        fu.lead_party,
        fu.secondary,
        fu.registered_mw,
        fu.adoption_week_start,
        results,
        latency,
        slope,
    )


def score_all(tasks: Sequence[Task], workers: int | None = None) -> list[UnitRecord]:
    """Score every unit, in parallel if asked; results in unit order."""
    ordered = sorted(tasks, key=lambda t: t.fleet_unit.unit)
    if workers == 1:
        return [score_one(t) for t in ordered]
    with ProcessPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        return list(pool.map(score_one, ordered))


# ------------------------------------------------------------------ the fleet


def claim1_cells(
    records: Sequence[UnitRecord], variant: str, branch: str, signed: bool = False
) -> dict[str, object]:
    """Return Claim 1's distribution for the fleet, with secondary units apart (§3)."""

    def values(keep: Callable[[UnitRecord], bool]) -> list[float]:
        out: list[float] = []
        for r in records:
            res = r.results[(variant, branch)]
            v = res.claim1_signed if signed else res.claim1_score
            if v is not None and keep(r):
                out.append(v)
        return out

    split = fl.complementary(
        {
            "secondary units (may be aggregated)": fl.distribution(
                values(lambda r: r.secondary)
            ),
            "other units": fl.distribution(values(lambda r: not r.secondary)),
        }
    )
    return {"all units": fl.distribution(values(lambda r: True)), **split}


def claim2_groups(
    records: Sequence[UnitRecord],
    variant: str,
    branch: str,
    known: Mapping[str, object],
) -> list[dict[str, object]]:
    """Return Claim 2's pooled share by length group, each beside its reference."""
    out: list[dict[str, object]] = []
    for low, high in fl.LENGTH_GROUPS:
        members = [
            r.results[(variant, branch)]
            for r in records
            if r.results[(variant, branch)].claim2_median is not None
            and fl.length_group(r.results[(variant, branch)].claim2_weeks)
            == (low, high)
        ]
        cell: dict[str, object] = {
            "scored_weeks": f"{low}–{high}",
            "units": len(members),
        }
        if len(members) < fl.MIN_CELL:
            cell["suppressed"] = fl.SUPPRESSED
        else:
            hits = sum(m.claim2_periods_in_violation for m in members)
            scored = sum(m.claim2_periods_scored for m in members)
            medians = [m.claim2_median for m in members if m.claim2_median is not None]
            cell["violation_share_pooled"] = hits / scored if scored else None
            cell["unit_scores"] = fl.percentiles(medians, fl.QUARTILES)
        cell["reference"] = fl.honest_reference(known, branch, low)
        out.append(cell)
    return out


def reliability(
    halves: Sequence[HalfScores], draws: int, coverage: float, floor: float, seed: int
) -> dict[str, object]:
    """Return §4's reliability for one claim and branch, from the units' halves."""
    pairs = [h for h in halves if h.odd is not None and h.even is not None]
    out: dict[str, object] = {
        "units": len(pairs),
        "odd_days": sum(h.odd_days for h in pairs),
        "even_days": sum(h.even_days for h in pairs),
    }
    if len(pairs) < fl.MIN_CELL:
        return {**out, "suppressed": fl.SUPPRESSED}
    rho = spearman(
        [h.odd for h in pairs if h.odd is not None],
        [h.even for h in pairs if h.even is not None],
    )
    out["spearman_half"] = rho
    out["reliability"] = spearman_brown(rho) if rho is not None and rho > -1 else None
    # Every cell's bootstrap starts from the master seed: common random numbers,
    # so the result is the same whatever order the cells are computed in.
    interval = reliability_interval(pairs, draws, coverage, np.random.default_rng(seed))
    out["interval_95"] = None if interval is None else [interval.lower, interval.upper]
    out["verdict"] = None if interval is None else reliability_verdict(interval, floor)
    out["floor"] = floor
    return out


def slope_fleet(records: Sequence[UnitRecord]) -> dict[str, object]:
    """Return the M13 slope diagnostic's fleet figures (module docstring)."""
    have = [r.slope for r in records if r.slope.slope is not None]
    reasons = Counter(r.slope.reason for r in records if r.slope.slope is None)
    out: dict[str, object] = {
        "label": "reported only; never selects a branch or changes a result (§9)",
        "units": len(have),
        "not_computed": dict(sorted((str(k), v) for k, v in reasons.items())),
    }
    if len(have) < fl.MIN_CELL:
        return {**out, "suppressed": fl.SUPPRESSED}
    slopes = [s.slope for s in have if s.slope is not None]
    inv = [s.inv_sqrt_eta for s in have if s.inv_sqrt_eta is not None]
    nearer_b = sum(
        1
        for s in have
        if s.slope is not None
        and s.inv_sqrt_eta is not None
        and abs(s.slope - s.inv_sqrt_eta) < abs(s.slope - 1)
    )
    out["slope"] = fl.percentiles(slopes)
    out["one_over_sqrt_eta"] = fl.percentiles(inv)
    out["share_nearer_branch_b"] = nearer_b / len(have)
    out["share_nearer_branch_b_definition"] = SHARE_DEFINITION
    out["periods"] = fl.percentiles([float(s.periods) for s in have], fl.QUARTILES)
    out["weeks"] = fl.percentiles([float(s.weeks) for s in have], fl.QUARTILES)
    return out


def claim5_fleet(
    records: Sequence[UnitRecord], settings: c5.Claim5Settings
) -> dict[str, object]:
    """Return Claim 5 pooled over every unit's acceptances, reported once."""
    intervals = [iv for r in records for iv in r.latency.intervals]
    units = sum(1 for r in records if r.latency.intervals)
    out = c5.summarise(intervals, settings.benchmark_min, units)
    out["default_records_not_counted"] = sum(r.latency.default_records for r in records)
    out["what_l_measures"] = (
        "time to the first record after an acceptance, which need not respond to "
        "it; a unit that publishes routine records shows an L no longer than the "
        "time to its next one, and public data cannot separate the two"
    )
    out["r_cross_check"] = "not made: r is Claim 3's ratio and Claim 3 is not reported"
    return out


def not_scored(
    records: Sequence[UnitRecord], variant: str = PREREGISTERED
) -> dict[str, object]:
    """Return counts of units not entering each claim, by reason and branch."""
    out: dict[str, object] = {}
    for b in BRANCHES:
        out[b] = {
            claim: dict(
                sorted(
                    Counter(
                        str(getattr(r.results[(variant, b)], f"{claim}_reason"))
                        for r in records
                        if getattr(r.results[(variant, b)], f"{claim}_reason")
                        is not None
                    ).items()
                )
            )
            for claim in ("claim1", "claim2")
        }
    return out


def fleet_results(
    records: Sequence[UnitRecord],
    settings: ClaimSettings,
    run: Mapping[str, object],
    known: Mapping[str, object],
    claim5: c5.Claim5Settings,
) -> dict[str, object]:
    """Return the preregistered fleet results (reading (a))."""
    draws = int(str(run["reliability_draws"]))
    floor = float(str(run["reliability_floor"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "settings": PREREGISTERED,
        "units": {
            "bm_units": len(records),
            "secondary_units": sum(r.secondary for r in records),
        },
        "not_scored": not_scored(records),
        "claim1": {
            "label": CLAIM1_LABEL,
            "error_ratio": {
                b: claim1_cells(records, PREREGISTERED, b) for b in BRANCHES
            },
            "signed_ratio": {
                b: claim1_cells(records, PREREGISTERED, b, signed=True)
                for b in BRANCHES
            },
        },
        "claim2": {
            "label": CLAIM2_LABEL,
            "by_length": {
                b: claim2_groups(records, PREREGISTERED, b, known) for b in BRANCHES
            },
        },
        "reliability": {
            b: {
                claim: reliability(
                    [
                        h
                        for r in records
                        if (
                            h := getattr(
                                r.results[(PREREGISTERED, b)], f"{claim}_halves"
                            )
                        )
                        is not None
                    ],
                    draws,
                    settings.coverage,
                    floor,
                    settings.master_seed,
                )
                for claim in ("claim1", "claim2")
            }
            for b in BRANCHES
        },
        "claim5": claim5_fleet(records, claim5),
        "m13_slope": slope_fleet(records),
    }


def sensitivity(
    records: Sequence[UnitRecord],
    variants: Sequence[Variant],
    known: Mapping[str, object],
) -> dict[str, object]:
    """Return the fleet results under each §9 variant (deviation 7), apart."""
    out: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "label": (
            "sensitivity only: the preregistered results are in fleet_results.json; "
            "no variant selects a headline (deviation 7)"
        ),
        "claim5": (
            "reported once in fleet_results.json: it reads no branch, horizon or "
            "efficiency"
        ),
        "not_applicable": NOT_APPLICABLE,
    }
    for v in variants:
        if v.name == PREREGISTERED:
            continue
        cell: dict[str, object] = {"not_scored": not_scored(records, v.name)}
        cell["claim1_error_ratio"] = {
            b: claim1_cells(records, v.name, b) for b in BRANCHES
        }
        cell["claim1_signed_ratio"] = {
            b: claim1_cells(records, v.name, b, signed=True) for b in BRANCHES
        }
        if "claim2" in v.claims:
            cell["claim2_by_length"] = {
                b: claim2_groups(records, v.name, b, known) for b in BRANCHES
            }
        out[v.name] = cell
    return out


def private_table(
    records: Sequence[UnitRecord], claim5: c5.Claim5Settings
) -> dict[str, object]:
    """Return each unit's preregistered results: names units, never committed."""
    units: list[dict[str, object]] = []
    for r in records:
        branches: dict[str, object] = {}
        for b in BRANCHES:
            res = r.results[(PREREGISTERED, b)]
            branches[b] = {
                "eta_hat": res.eta,
                "unscored_reason": res.unscored_reason,
                "claim1": {
                    "scored_weeks": res.claim1_weeks,
                    "score": res.claim1_score,
                    "signed": res.claim1_signed,
                    "interval_95": None
                    if res.claim1_interval is None
                    else [res.claim1_interval.lower, res.claim1_interval.upper],
                    "reason": res.claim1_reason,
                },
                "claim2": {
                    "scored_weeks": res.claim2_weeks,
                    "violation_share_pooled": (
                        res.claim2_periods_in_violation / res.claim2_periods_scored
                        if res.claim2_periods_scored
                        else None
                    ),
                    "median_weekly_share": res.claim2_median,
                    "reason": res.claim2_reason,
                },
            }
        units.append(
            {
                "unit": r.unit,
                "lead_party": r.lead_party,
                "secondary": r.secondary,
                "registered_mw": r.registered_mw,
                "adoption_week_start": r.adoption_week_start.isoformat(),
                "branches": branches,
                "claim5": c5.summarise(
                    r.latency.intervals,
                    claim5.benchmark_min,
                    1 if r.latency.intervals else 0,
                ),
                "m13_slope": asdict(r.slope),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "private": "names units: never committed; the private packs' only input",
        "units": units,
    }


# ------------------------------------------------------------------ the run


def assert_no_ids(text: str, records: Iterable[UnitRecord]) -> None:
    """Stop if a public file's text names a unit or a lead party."""
    for r in records:
        for name in (r.unit, r.lead_party):
            if name and json.dumps(name) in text:
                raise RunError("a public output names a unit or lead party")


def sha256(path: Path) -> str:
    """Return a file's SHA-256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state(root: Path) -> tuple[str, bool]:
    """Return the commit and whether any tracked file is modified."""
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return commit, bool(status)


def dumps(obj: object) -> str:
    """Return the JSON text every output uses."""
    text = json.dumps(
        obj, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    )
    return text + "\n"  # allow_nan=False: a non-finite value stops the run


def run(
    root: Path = pull.ROOT,
    workers: int | None = None,
    end: datetime = asm.SCORING_END,
    assembly: asm.Assembly | None = None,
    check_git: bool = True,
) -> dict[str, object]:
    """Run the pinned scoring run once and write its outputs (module docstring)."""
    record_path = root / RECORD_OUT
    if record_path.exists():
        raise RunError(
            "the pinned scoring run has already run (run_record.json exists)"
        )
    commit, dirty = git_state(root) if check_git else ("not checked", False)
    if dirty:
        raise RunError("tracked files are modified: commit before the pinned run")
    started = datetime.now(UTC)
    if assembly is None:
        assembly = asm.assemble(root, with_meter=True)
    settings = load_claim_settings()
    params = load_params()
    claim5 = c5.load_claim5_settings()
    variants = load_variants()
    known = json.loads((root / KNOWN_ANSWER).read_text(encoding="utf-8"))
    scoring = load_scoring_settings()
    tasks = [
        Task(fu, assembly.inputs[u], end, settings, variants, claim5)
        for u, fu in assembly.units.items()
    ]
    records = score_all(tasks, workers)
    run_settings = {
        "reliability_draws": scoring.reliability_draws,
        "reliability_floor": params.number("scoring.reliability_floor"),
    }
    public = {
        FLEET_OUT: dumps(fleet_results(records, settings, run_settings, known, claim5)),
        SENSITIVITY_OUT: dumps(sensitivity(records, variants, known)),
    }
    for text in public.values():
        assert_no_ids(text, records)
    private = dumps(private_table(records, claim5))
    # The run record is written last: it is the run-once guard, so a run that
    # fails before it can be repeated, overwriting these files.
    for rel, text in [*public.items(), (PRIVATE_OUT, private)]:
        out = root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    record = {
        "schema_version": SCHEMA_VERSION,
        "code_commit": commit,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "scoring_end": end.isoformat(),
        "variants": [v.name for v in variants],
        "units_scored": len(records),
        "inputs_sha256": {
            str(p): sha256(root / p) for p in HASHED_INPUTS if (root / p).exists()
        },
        "outputs_sha256": {
            str(rel): hashlib.sha256(text.encode()).hexdigest()
            for rel, text in [*public.items(), (PRIVATE_OUT, private)]
        },
        "assembly": {ds: c.as_dict() for ds, c in sorted(assembly.counts.items())},
    }
    text = dumps(record)
    assert_no_ids(text, records)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(text, encoding="utf-8")
    return record


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pinned scoring run; print the run record (no unit ID)."""
    parser = argparse.ArgumentParser(description="The pinned scoring run")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        record = run(workers=args.workers)
    except (RunError, asm.AssemblyError) as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 1
    print(dumps(record), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
