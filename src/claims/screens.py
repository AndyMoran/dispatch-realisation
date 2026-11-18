"""Screens for Claims 1 and 2 (PREREGISTRATION §3–§4; PROJECT.md §11, 18 Nov 2026).

- Missing meter: a unit-week is unscored if any of its 336 settlement periods lacks
  a B1610 value from the SF run or later.
- Idle (Claim 1 only): throughput below registered MW × 1 hour, or below 1 MWh for
  a unit with no registered MW.
- EFA boundaries (Claim 1 only): for each boundary B at 23:00, 03:00, 07:00, 11:00,
  15:00 and 19:00 UK time, the periods [B − 30 min, B) and [B, B + 30 min) are
  excluded: 12 periods a day, the clock-change days included.

Weeks are ISO weeks in UTC, starting Monday 00:00 UTC, so every week has 336
settlement periods whatever UK clocks do.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.model.types import SETTLEMENT_PERIOD, MeterPeriod, require_utc

UK = ZoneInfo("Europe/London")
WEEK = timedelta(days=7)
PERIODS_PER_WEEK = 336
MISSING_METER = "missing B1610 (SF or later)"
IDLE = "idle"


@dataclass(frozen=True)
class WeekMeter:
    """A unit-week's meter after the missing-meter screen.

    `periods` holds all 336 periods in order, or is empty with a reason.
    """

    week_start: datetime
    periods: tuple[MeterPeriod, ...]
    unscored_reason: str | None


def week_boundaries(week_start: datetime) -> tuple[datetime, ...]:
    """Return the 337 period boundaries of the week, from its start to its end."""
    require_week_start(week_start)
    return tuple(
        week_start + k * SETTLEMENT_PERIOD for k in range(PERIODS_PER_WEEK + 1)
    )


def require_week_start(week_start: datetime) -> None:
    """Raise unless `week_start` is a Monday at 00:00 UTC."""
    require_utc(week_start, "week_start")
    midnight = week_start.time() == datetime.min.time()
    if week_start.weekday() != 0 or not midnight:
        raise ValueError(f"not Monday 00:00 UTC: {week_start.isoformat()}")


def screen_meter(
    meter: Sequence[MeterPeriod], week_start: datetime, sf_or_later: Collection[str]
) -> WeekMeter:
    """Return the week's 336 periods, or no periods if any is missing or pre-SF."""
    starts = week_boundaries(week_start)[:-1]
    by_start = {m.period_start: m for m in meter if week_start <= m.period_start}
    periods = [by_start.get(s) for s in starts]
    complete = [p for p in periods if p is not None and p.run_type in sf_or_later]
    if len(complete) != PERIODS_PER_WEEK:
        return WeekMeter(week_start, (), MISSING_METER)
    return WeekMeter(week_start, tuple(complete), None)


def is_idle(
    periods: Sequence[MeterPeriod],
    registered_mw: float | None,
    idle_hours: float,
    floor_mwh: float,
) -> bool:
    """Return whether the week's throughput falls below its idle threshold (§4)."""
    throughput = sum(p.export_mwh + p.import_mwh for p in periods)
    threshold = floor_mwh if registered_mw is None else registered_mw * idle_hours
    return throughput < threshold


def efa_excluded(period_start: datetime, boundary_hours: Collection[float]) -> bool:
    """Return whether the period starts or ends at an EFA boundary in UK time."""
    require_utc(period_start, "period_start")
    hours = {int(h) for h in boundary_hours}
    for instant in (period_start, period_start + SETTLEMENT_PERIOD):
        local = instant.astimezone(UK)
        if local.minute == 0 and local.hour in hours:
            return True
    return False
