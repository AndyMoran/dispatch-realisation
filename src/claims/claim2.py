"""Claim 2: lower-wall violations (PREREGISTRATION §4).

At the start of each settlement period, a violation occurs when
D^decl_t < L_t − τ_w, with τ_w = 0.02 × (max K − min K) for the week. The weekly
score is the share of periods in violation, over periods with a declaration in
force. Claim 2 inherits only Claim 1's missing-meter screen: idle weeks are scored,
and the EFA screen does not apply. Contract status classifies whole weeks, outside
this module; only contract-free weeks enter the hard flag.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.claims.results import DayPart, WeekResult
from src.claims.screens import PERIODS_PER_WEEK, WeekMeter
from src.physics.walls import cumulative_change, lower_wall, swing_mwh

NO_DECLARATION = "no declaration in force"


def violations(
    week: WeekMeter, declared: Sequence[float | None], eta: float, tau_fraction: float
) -> tuple[bool | None, ...]:
    """Return, per period start, whether D^decl < L − τ; None if nothing is declared."""
    if len(declared) != len(week.periods) + 1:
        raise ValueError("need one declaration per boundary: periods + 1")
    if not 0 <= tau_fraction < 1:
        raise ValueError(f"tau_fraction outside [0, 1): {tau_fraction}")
    k = cumulative_change(week.periods, eta)
    wall = lower_wall(k)
    tau = tau_fraction * swing_mwh(k)
    return tuple(
        None if d is None else d < wall[h] - tau
        for h, d in enumerate(declared[: len(week.periods)])
    )


def claim2_week(
    week: WeekMeter, declared: Sequence[float | None], eta: float, tau_fraction: float
) -> WeekResult:
    """Return Claim 2's violation share for one unit-week, day by day."""
    if week.unscored_reason is not None:
        return WeekResult(week.week_start, (), 0.0, week.unscored_reason)
    flags = violations(week, declared, eta, tau_fraction)
    days = sorted({p.period_start.date() for p in week.periods})
    hits = dict.fromkeys(days, 0.0)
    scored = dict.fromkeys(days, 0.0)
    for period, flag in zip(week.periods, flags, strict=True):
        if flag is None:
            continue
        day = period.period_start.date()
        hits[day] += 1.0 if flag else 0.0
        scored[day] += 1.0
    used = int(sum(scored.values()))
    if used == 0:
        return WeekResult(week.week_start, (), 0.0, NO_DECLARATION)
    parts = tuple(DayPart(d, hits[d], scored[d]) for d in days)
    return WeekResult(week.week_start, parts, used / PERIODS_PER_WEEK, None)
