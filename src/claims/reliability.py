"""Reliability of a claim across units (PREREGISTRATION §4).

Each unit's score is computed separately on odd and even calendar days: date parity
of the UTC day (PROJECT.md §11, 18 Nov 2026). The Spearman correlation of the two
halves across units, stepped up by the Spearman–Brown formula, is the claim's
reliability. Its 95% interval comes from resampling units. Halves can differ by a
day or more at 31-day month ends or after screening; their sizes are reported, and
the standard formula, as locked, assumes equal halves.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from src.claims.results import WeekResult
from src.claims.scoring import Interval, unit_score

Parity = Literal["odd", "even"]
Verdict = Literal["reliable", "straddles 0.5", "unreliable"]


@dataclass(frozen=True)
class HalfScores:
    """One unit's scores on odd and even days, and the days in each half."""

    odd: float | None
    even: float | None
    odd_days: int
    even_days: int


def half_weeks(weeks: Sequence[WeekResult], parity: Parity) -> tuple[WeekResult, ...]:
    """Return the weeks keeping only days of the given date parity."""
    want = 1 if parity == "odd" else 0
    out: list[WeekResult] = []
    for w in weeks:
        parts = tuple(p for p in w.parts if p.day.day % 2 == want)
        if w.unscored_reason is None and parts:
            out.append(WeekResult(w.week_start, parts, w.usable_share, None))
    return tuple(out)


def half_scores(weeks: Sequence[WeekResult]) -> HalfScores:
    """Return the unit's odd-day and even-day scores (§4)."""
    odd, even = half_weeks(weeks, "odd"), half_weeks(weeks, "even")
    return HalfScores(
        unit_score(odd),
        unit_score(even),
        sum(len(w.parts) for w in odd),
        sum(len(w.parts) for w in even),
    )


def ranks(values: Sequence[float]) -> np.ndarray:
    """Return ranks from 1, with ties given their average rank."""
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="stable")
    out = np.empty(len(arr))
    i = 0
    while i < len(arr):
        j = i
        while j + 1 < len(arr) and arr[order[j + 1]] == arr[order[i]]:
            j += 1
        out[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Return Spearman's rank correlation; None if either side has no spread."""
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("need two equal-length samples of at least 2")
    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def spearman_brown(rho: float) -> float:
    """Return full-length reliability from a split-half correlation: 2ρ / (1 + ρ)."""
    if not -1 < rho <= 1:
        raise ValueError(f"correlation outside (−1, 1]: {rho}")
    return 2 * rho / (1 + rho)


def reliability_interval(
    halves: Sequence[HalfScores], draws: int, coverage: float, rng: np.random.Generator
) -> Interval | None:
    """Return the 95% interval of the stepped-up reliability, resampling units."""
    pairs = [
        (h.odd, h.even) for h in halves if h.odd is not None and h.even is not None
    ]
    if len(pairs) < 2:
        return None
    odd = np.array([p[0] for p in pairs])
    even = np.array([p[1] for p in pairs])
    values: list[float] = []
    for _ in range(draws):
        pick = rng.integers(0, len(pairs), size=len(pairs))
        rho = spearman(odd[pick].tolist(), even[pick].tolist())
        if rho is not None and rho > -1:
            values.append(spearman_brown(rho))
    if not values:
        return None
    tail = 100 * (1 - coverage) / 2
    lower, upper = np.percentile(values, [tail, 100 - tail])
    return Interval(float(lower), float(upper), draws, draws - len(values))


def reliability_verdict(interval: Interval, floor: float) -> Verdict:
    """Return §4's reading of the interval against the 0.5 floor."""
    if interval.upper < floor:
        return "unreliable"
    if interval.lower < floor:
        return "straddles 0.5"
    return "reliable"
