"""Claim 1: mass-balance coherence (PREREGISTRATION §4).

For each settlement period h, r_h = ΔD^decl_h − (η̂·E⁻_h − E⁺_h), with ΔD^decl_h
from the start of h to the start of h + 1. The weekly score is Σ|r_h| / Σ(E⁺_h + E⁻_h)
and the signed ratio Σr_h / Σ(E⁺_h + E⁻_h), both over the same screened periods
(PROJECT.md §11, 18 Nov 2026). A period enters only if it passes the EFA and contract
screens and a declaration is in force at both its ends.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from src.claims.results import DayPart, WeekResult
from src.claims.screens import (
    IDLE,
    PERIODS_PER_WEEK,
    WeekMeter,
    efa_excluded,
    is_idle,
)

NO_USABLE_PERIODS = "no usable periods"


@dataclass(frozen=True)
class Claim1Week:
    """A unit-week's Claim 1 result: the error ratio, and the signed ratio."""

    error: WeekResult
    signed: WeekResult


@dataclass(frozen=True)
class Claim1Screens:
    """Thresholds and exclusions Claim 1 applies to a week (§4)."""

    registered_mw: float | None
    idle_hours: float
    idle_floor_mwh: float
    efa_boundary_hours: tuple[float, ...]
    contract_change_starts: Collection[datetime]


def residuals(
    week: WeekMeter, declared: Sequence[float | None], eta: float
) -> tuple[float | None, ...]:
    """Return r_h for each period; None where a declaration is missing at either end."""
    if len(declared) != len(week.periods) + 1:
        raise ValueError("need one declaration per boundary: periods + 1")
    out: list[float | None] = []
    for h, period in enumerate(week.periods):
        start, end = declared[h], declared[h + 1]
        if start is None or end is None:
            out.append(None)
            continue
        out.append((end - start) - (eta * period.import_mwh - period.export_mwh))
    return tuple(out)


def claim1_week(
    week: WeekMeter,
    declared: Sequence[float | None],
    eta: float,
    screens: Claim1Screens,
) -> Claim1Week:
    """Return Claim 1's error and signed ratios for one unit-week, day by day."""
    reason = week.unscored_reason
    if reason is None and is_idle(
        week.periods, screens.registered_mw, screens.idle_hours, screens.idle_floor_mwh
    ):
        reason = IDLE
    if reason is not None:
        unscored = WeekResult(week.week_start, (), 0.0, reason)
        return Claim1Week(unscored, unscored)
    r = residuals(week, declared, eta)
    days = sorted({p.period_start.date() for p in week.periods})
    error = dict.fromkeys(days, 0.0)
    signed = dict.fromkeys(days, 0.0)
    flow = dict.fromkeys(days, 0.0)
    used = 0
    for period, r_h in zip(week.periods, r, strict=True):
        if r_h is None or period.period_start in screens.contract_change_starts:
            continue
        if efa_excluded(period.period_start, screens.efa_boundary_hours):
            continue
        day = period.period_start.date()
        error[day] += abs(r_h)
        signed[day] += r_h
        flow[day] += period.export_mwh + period.import_mwh
        used += 1
    if used == 0 or sum(flow.values()) <= 0:
        unscored = WeekResult(
            week.week_start, (), used / PERIODS_PER_WEEK, NO_USABLE_PERIODS
        )
        return Claim1Week(unscored, unscored)
    share = used / PERIODS_PER_WEEK
    return Claim1Week(
        WeekResult(week.week_start, _parts(days, error, flow), share, None),
        WeekResult(week.week_start, _parts(days, signed, flow), share, None),
    )


def _parts(
    days: list[date], numerator: dict[date, float], denominator: dict[date, float]
) -> tuple[DayPart, ...]:
    return tuple(DayPart(d, numerator[d], denominator[d]) for d in days)
