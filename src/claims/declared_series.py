"""Declared deliverable energy at each period boundary of a week (§3).

Claims 1 and 2 both read D^decl_t at the 337 boundaries of a unit-week. It is
computed once here, under one branch and one protection horizon.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from src.model.types import UnitInputs
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
    series: list[float | None] = []
    for t, mdo_mwh in zip(times, mdo, strict=True):
        if mdo_mwh is None:
            series.append(None)
            continue
        end = protection_end(t, extra_periods, horizon_hours)
        p_exp, _ = pn_protected_mwh(unit.pn, t, end)
        b_exp = boa_export_mwh(unit.boas, unit.pn, t, end)
        series.append(declared_deliverable_mwh(mdo_mwh, p_exp, b_exp, eta, branch))
    return tuple(series)
