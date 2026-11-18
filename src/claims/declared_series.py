"""Declared deliverable energy at each period boundary of a week (§3).

Claims 1 and 2 both read D^decl_t at the 337 boundaries of a unit-week. It is
computed once here, under one branch and one protection horizon.

For speed, each boundary passes the protection functions only the PN and BOA
segments that overlap its horizon [t, end]. A segment outside it has no end inside
the horizon and covers no part of it, so the result is identical to passing every
segment (tests/test_claims12.py checks this bit for bit).
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from datetime import datetime, timedelta

from src.model.types import LevelSegment, UnitInputs
from src.physics.declared import Branch, declared_at, declared_deliverable_mwh
from src.physics.protection import boa_export_mwh, horizon_end, pn_protected_mwh


def protection_end(
    t: datetime, extra_periods: int, horizon_hours: float | None
) -> datetime:
    """Return the end of H: current period plus `extra_periods`, or t + hours (§9)."""
    if horizon_hours is None:
        return horizon_end(t, extra_periods)
    if horizon_hours <= 0:
        raise ValueError(f"horizon_hours not positive: {horizon_hours}")
    return t + timedelta(hours=horizon_hours)


def declared_series(
    unit: UnitInputs,
    times: Sequence[datetime],
    eta: float,
    branch: Branch,
    extra_periods: int,
    horizon_hours: float | None,
    default_abs_mwh: float,
    data_end: datetime,
) -> tuple[float | None, ...]:
    """Return D^decl at each time; None where no MDO is in force (§3; M9)."""
    mdo = declared_at(unit.submissions, "MDO", times, default_abs_mwh, data_end)
    pn, boas = _Index(unit.pn), _Index(unit.boas)
    series: list[float | None] = []
    for t, mdo_mwh in zip(times, mdo, strict=True):
        if mdo_mwh is None:
            series.append(None)
            continue
        end = protection_end(t, extra_periods, horizon_hours)
        pn_near = pn.overlapping(t, end)
        p_exp, _ = pn_protected_mwh(pn_near, t, end)
        b_exp = boa_export_mwh(boas.overlapping(t, end), pn_near, t, end)
        series.append(declared_deliverable_mwh(mdo_mwh, p_exp, b_exp, eta, branch))
    return tuple(series)


class _Index:
    """Segments sorted by start, for finding those that overlap an interval."""

    def __init__(self, segments: Sequence[LevelSegment]) -> None:
        self.segments = tuple(segments)
        self.starts = [s.time_from for s in self.segments]
        if self.starts != sorted(self.starts):
            raise ValueError("segments must be sorted by start")
        self.longest = max(
            (s.time_to - s.time_from for s in self.segments), default=timedelta(0)
        )

    def overlapping(self, a: datetime, b: datetime) -> list[LevelSegment]:
        """Return every segment with time_from ≤ b and time_to ≥ a, in order."""
        lo = bisect.bisect_left(self.starts, a - self.longest)
        hi = bisect.bisect_right(self.starts, b)
        return [s for s in self.segments[lo:hi] if s.time_to >= a]
