"""Declared deliverable energy at each period boundary of a week (§3; §12, deviation 5).

Accepted-BOA export energy (B^exp) is added back only for instructions accepted
strictly before the publish time of the MDO record in force at t ("known",
deviation 5). A record published before an acceptance cannot have netted that
instruction, so adding it back would count the same energy twice while the record
stays in force. "all" is the rule before deviation 5, which adds back every
instruction accepted at or before t; it is kept only to reproduce results run
under it (the first Claims 1–2 run, deviation 2's run and the Claim 4 check).

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
from typing import Literal

from src.model.types import LevelSegment, UnitInputs
from src.physics.declared import (
    Branch,
    declared_at,
    declared_deliverable_mwh,
    in_force_publish_times,
)
from src.physics.protection import boa_export_mwh, horizon_end, pn_protected_mwh

AddBack = Literal["known", "all"]
ADDBACK_RULES: tuple[AddBack, ...] = ("known", "all")


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
    addback: AddBack = "known",
) -> tuple[float | None, ...]:
    """Return D^decl at each time; None where no MDO is in force (§3; M9).

    `addback` chooses which accepted instructions B^exp counts (module docstring).
    """
    if addback not in ADDBACK_RULES:
        raise ValueError(f"unknown add-back rule: {addback}")
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
        near = boas.overlapping(t, end)
        if addback == "known":
            near = [
                s
                for s in near
                if s.acceptance_time is not None and s.acceptance_time < pub
            ]
        b_exp = boa_export_mwh(near, pn_near, t, end)
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
