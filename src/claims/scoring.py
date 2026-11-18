"""Unit scores, intervals and flag categories (PREREGISTRATION §4; §12, deviation 1).

A unit's score is the median of its scored weeks' ratios. Its 95% interval comes
from nested resampling: each draw takes the unit's scored weeks with replacement,
resamples each drawn week's UTC days with replacement, recomputes each weekly
ratio from the resampled days, and takes the median. The interval runs from the
2.5th to the 97.5th percentile of the draws (numpy's default, linear method).

A draw in which a resampled week has no denominator drops that week; a draw left
with no weeks is counted as degenerate and excluded. Each unit's generator is
seeded from one master seed (config/scoring.toml), so results do not depend on
order or on other units; draws are correlated across units, so per-unit bounds
are never combined into a fleet interval.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median
from typing import Literal

import numpy as np

from src.claims.results import WeekResult

Claim1Category = Literal["coherent", "not shown coherent", "indeterminate"]
Claim2Category = Literal["provable under-declaration", "none detected"]


@dataclass(frozen=True)
class Interval:
    """A unit score's resampled interval, with the draws that produced it."""

    lower: float
    upper: float
    draws: int
    degenerate_draws: int


def scored_weeks(weeks: Sequence[WeekResult]) -> tuple[WeekResult, ...]:
    """Return the weeks with a defined score, in week order."""
    keep = [w for w in weeks if w.score is not None]
    return tuple(sorted(keep, key=lambda w: w.week_start))


def unit_score(weeks: Sequence[WeekResult]) -> float | None:
    """Return the median weekly score; None if no week is scored (§4)."""
    scores = [w.score for w in scored_weeks(weeks)]
    return median(s for s in scores if s is not None) if scores else None


def unit_rng(master_seed: int) -> np.random.Generator:
    """Return a fresh generator for one unit, seeded from the master seed."""
    if master_seed < 0:
        raise ValueError(f"master seed below zero: {master_seed}")
    return np.random.default_rng(master_seed)


def nested_interval(
    weeks: Sequence[WeekResult], draws: int, coverage: float, rng: np.random.Generator
) -> Interval | None:
    """Return the nested-resampling interval of the unit score; None if unscored."""
    if draws < 1 or not 0 < coverage < 1:
        raise ValueError(f"bad draws or coverage: {draws}, {coverage}")
    kept = scored_weeks(weeks)
    if not kept:
        return None
    num = [np.array([p.numerator for p in w.parts]) for w in kept]
    den = [np.array([p.denominator for p in w.parts]) for w in kept]
    medians: list[float] = []
    for _ in range(draws):
        ratios: list[float] = []
        for i in rng.integers(0, len(kept), size=len(kept)):
            days = rng.integers(0, len(num[i]), size=len(num[i]))
            total = float(den[i][days].sum())
            if total > 0:
                ratios.append(float(num[i][days].sum()) / total)
        if ratios:
            medians.append(float(np.median(ratios)))
    if not medians:
        return None
    tail = 100 * (1 - coverage) / 2
    lower, upper = np.percentile(medians, [tail, 100 - tail])
    return Interval(float(lower), float(upper), draws, draws - len(medians))


def claim1_category(
    interval: Interval, coherent_upper: float, not_coherent_lower: float
) -> Claim1Category:
    """Return Claim 1's flag from the interval (§4 table)."""
    if interval.upper <= coherent_upper:
        return "coherent"
    if interval.lower >= not_coherent_lower:
        return "not shown coherent"
    return "indeterminate"


def claim2_category(interval: Interval, provable_lower: float) -> Claim2Category:
    """Return Claim 2's flag from the interval over contract-free weeks (§4 table)."""
    if interval.lower >= provable_lower:
        return "provable under-declaration"
    return "none detected"
