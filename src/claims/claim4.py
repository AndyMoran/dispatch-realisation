"""Claim 4: upper-wall violations (PREREGISTRATION §6; PROJECT.md §11, 23 Nov 2026).

Where a nameplate N bounds usable energy, the tank held at most N − (max K − K_t)
at each period boundary of a week (`src/physics/walls.py`). At the start of each
settlement period a violation occurs when

    D^decl_t > N − (max K − K_t) + 0.02 × N,

strictly, so equality or any excess within the tolerance is not one. The weekly
score is the share of counted periods in violation, with the largest excess in
MWh. A week whose swing max K − min K exceeds 1.02 × N is physics-inconsistent:
counted and reported, still scored, and not a violation in itself.

Screens and η̂ follow Claim 2, whose K Claim 4 shares (readings of 23 Nov 2026):
a week missing any B1610 period is unscored; idle weeks are scored; the EFA screen
does not apply; a period with no declaration in force is not counted. η̂ comes
from the unit's complete weeks after its adoption week, with the same bounds and
reasons as Claims 1–2 (`src/claims/unit.py`, step 1).

Claim 4 needs no contract exclusion (§6). D^decl is computed once per week and
judged against each nameplate given, so a caller can score several ceilings at
the cost of one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.claims.declared_series import declared_series
from src.claims.screens import WeekMeter, screen_meter, week_boundaries
from src.claims.unit import (
    ETA_OUT_OF_BOUNDS,
    ETA_UNDEFINED,
    TOO_FEW_WEEKS,
    ClaimSettings,
    week_starts,
)
from src.model.params import load_params
from src.model.types import UnitInputs
from src.physics.declared import Branch
from src.physics.efficiency import EfficiencyUndefined, eta_hat, eta_in_bounds
from src.physics.walls import cumulative_change, swing_mwh, upper_wall

NO_DECLARATION = "no declaration in force"
NO_SCORED_WEEK = "no scored week"


@dataclass(frozen=True)
class Claim4Settings:
    """Claim 4's two thresholds, from config/claims.toml (§6)."""

    tolerance_fraction: float
    inconsistent_factor: float

    def __post_init__(self) -> None:
        if not 0 <= self.tolerance_fraction < 1:
            raise ValueError(f"tolerance outside [0, 1): {self.tolerance_fraction}")
        if self.inconsistent_factor < 1:
            raise ValueError(f"inconsistent factor below 1: {self.inconsistent_factor}")


def load_claim4_settings() -> Claim4Settings:
    """Return §6's tolerance (0.02) and inconsistency factor (1.02)."""
    p = load_params()
    return Claim4Settings(
        tolerance_fraction=p.number("claim4.nameplate_tolerance"),
        inconsistent_factor=p.number("claim4.inconsistent_factor"),
    )


@dataclass(frozen=True)
class Claim4Week:
    """One unit-week against one nameplate, or the reason it is unscored."""

    week_start: datetime
    counted: int
    violations: int
    largest_excess_mwh: float | None
    physics_inconsistent: bool | None
    unscored_reason: str | None

    def __post_init__(self) -> None:
        if not 0 <= self.violations <= self.counted:
            raise ValueError("violations outside [0, counted]")
        scored = self.unscored_reason is None
        if scored and (self.counted == 0 or self.physics_inconsistent is None):
            raise ValueError("a scored week needs counted periods and a swing check")
        if not scored and (self.counted or self.physics_inconsistent is not None):
            raise ValueError("an unscored week carries no counts")
        if (self.violations > 0) != (self.largest_excess_mwh is not None):
            raise ValueError("largest excess is set exactly when there are violations")

    @property
    def share(self) -> float | None:
        """Return the share of counted periods in violation; None if unscored."""
        if self.unscored_reason is not None:
            return None
        return self.violations / self.counted


@dataclass(frozen=True)
class Claim4Result:
    """One unit's Claim 4 weeks under one branch and one nameplate."""

    branch: Branch
    nameplate_mwh: float
    eta_hat: float | None
    unscored_reason: str | None
    weeks: tuple[Claim4Week, ...]

    @property
    def scored_weeks(self) -> tuple[Claim4Week, ...]:
        """Return the weeks that were scored."""
        return tuple(w for w in self.weeks if w.unscored_reason is None)

    @property
    def any_violation(self) -> bool | None:
        """Return whether any scored week has a violation; None if unscored."""
        if self.unscored_reason is not None:
            return None
        return any(w.violations > 0 for w in self.scored_weeks)


def excesses(
    week: WeekMeter,
    declared: Sequence[float | None],
    eta: float,
    nameplate_mwh: float,
    tolerance_fraction: float,
) -> tuple[float | None, ...]:
    """Return D^decl − (wall + tolerance) at each period start; None if undeclared.

    A period is in violation exactly where its value is above zero.
    """
    if len(declared) != len(week.periods) + 1:
        raise ValueError("need one declaration per boundary: periods + 1")
    if not 0 <= tolerance_fraction < 1:
        raise ValueError(f"tolerance outside [0, 1): {tolerance_fraction}")
    k = cumulative_change(week.periods, eta)
    wall = upper_wall(k, nameplate_mwh)
    line = [w + tolerance_fraction * nameplate_mwh for w in wall]
    return tuple(
        None if d is None else d - line[h]
        for h, d in enumerate(declared[: len(week.periods)])
    )


def claim4_week(
    week: WeekMeter,
    declared: Sequence[float | None],
    eta: float,
    nameplate_mwh: float,
    settings: Claim4Settings,
) -> Claim4Week:
    """Return Claim 4's counts for one unit-week against one nameplate."""
    if week.unscored_reason is not None:
        return Claim4Week(week.week_start, 0, 0, None, None, week.unscored_reason)
    values = [
        e
        for e in excesses(
            week, declared, eta, nameplate_mwh, settings.tolerance_fraction
        )
        if e is not None
    ]
    if not values:
        return Claim4Week(week.week_start, 0, 0, None, None, NO_DECLARATION)
    over = [e for e in values if e > 0.0]
    swing = swing_mwh(cumulative_change(week.periods, eta))
    return Claim4Week(
        week_start=week.week_start,
        counted=len(values),
        violations=len(over),
        largest_excess_mwh=max(over) if over else None,
        physics_inconsistent=swing > settings.inconsistent_factor * nameplate_mwh,
        unscored_reason=None,
    )


def score_unit_claim4(
    unit: UnitInputs,
    adoption_week_start: datetime,
    end: datetime,
    settings: ClaimSettings,
    claim4: Claim4Settings,
    branch: Branch,
    nameplates_mwh: Sequence[float],
    horizon_hours: float | None = None,
) -> tuple[Claim4Result, ...]:
    """Return the unit's Claim 4 weeks under `branch`, one result per nameplate."""
    if not nameplates_mwh or min(nameplates_mwh) <= 0:
        raise ValueError(f"nameplates must be positive: {nameplates_mwh}")
    weeks = week_starts(adoption_week_start, end)
    if not weeks:
        return _unscored(branch, nameplates_mwh, None, TOO_FEW_WEEKS)
    window = [m for m in unit.meter if weeks[0] <= m.period_start < end]
    try:
        eta = eta_hat(window)
    except EfficiencyUndefined:
        return _unscored(branch, nameplates_mwh, None, ETA_UNDEFINED)
    if not eta_in_bounds(eta, settings.eta_min, settings.eta_max):
        return _unscored(branch, nameplates_mwh, eta, ETA_OUT_OF_BOUNDS)
    by_nameplate: list[list[Claim4Week]] = [[] for _ in nameplates_mwh]
    for week_start in weeks:
        meter = screen_meter(unit.meter, week_start, settings.sf_or_later_runs)
        declared = declared_series(
            unit,
            week_boundaries(week_start),
            eta,
            branch,
            settings.extra_periods,
            horizon_hours,
            settings.default_abs_mwh,
            end,
            settings.boa_addback,
        )
        for out, n in zip(by_nameplate, nameplates_mwh, strict=True):
            out.append(claim4_week(meter, declared, eta, n, claim4))
    results = []
    for out, n in zip(by_nameplate, nameplates_mwh, strict=True):
        scored = any(w.unscored_reason is None for w in out)
        reason = None if scored else NO_SCORED_WEEK
        results.append(Claim4Result(branch, n, eta, reason, tuple(out)))
    return tuple(results)


def _unscored(
    branch: Branch, nameplates_mwh: Sequence[float], eta: float | None, reason: str
) -> tuple[Claim4Result, ...]:
    return tuple(Claim4Result(branch, n, eta, reason, ()) for n in nameplates_mwh)
