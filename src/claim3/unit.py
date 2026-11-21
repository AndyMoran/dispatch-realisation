"""Score one unit on Claim 3 (PREREGISTRATION §5), under one M13 branch.

Real units and synthetic batteries both pass through `score_claim3`. Claim 3 is a
separate module from Claims 1 and 2 (§10): it shares only inputs, η̂ and the
lower wall.

Readings and conventions fixed in PROJECT.md §11 (21 Nov 2026) before this code:

- Instructions accepted in the unit's complete weeks after its adoption week.
- Fitted: eligible instructions with r ≤ 1. r > 1 is counted, never fitted, and
  not counted towards identification (a conservative convention).
- Identified: at least min_instructions fitted offers with r ≥ min_r, and the
  slope check passed. An unavailable slope check means not identified.
- Placebo (offers only): the lower wall at the start of the acceptance's period
  at least |A|, no tolerance. Given Claim 2's failed band (ASSUMPTIONS P11), it
  is protocol-defined, not reliable proof of stored energy. No bid placebo: an
  upper wall needs a usable-energy figure (P4a).
- Flag, this branch: identified; both models' intervals exclude zero, or only the
  proportional one where the models are not separately identified; a non-empty
  placebo set whose f interval includes zero. §5.7's fourth condition, both
  branches, is `flagged_under_both`. Offers only; bids are reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from src.claim3.fits import (
    Grids,
    ModelFit,
    SlopeCheck,
    breakpoint,
    excludes_zero,
    fit_models,
    includes_zero,
    separately_identified,
    slope_check,
    transition_width,
)
from src.claim3.instructions import Measured, Side, instructions, measure, period_floor
from src.claims.scoring import unit_rng
from src.claims.screens import screen_meter
from src.claims.unit import (
    ETA_OUT_OF_BOUNDS,
    ETA_UNDEFINED,
    ClaimSettings,
    week_starts,
)
from src.model.params import load_params
from src.model.types import UnitInputs
from src.physics.declared import Branch
from src.physics.efficiency import EfficiencyUndefined, eta_hat, eta_in_bounds
from src.physics.walls import cumulative_change, lower_wall

NO_WEEKS = "no complete week after the adoption week"


@dataclass(frozen=True)
class Claim3Settings:
    """Claim 3's thresholds (config/claims.toml) with the shared run settings."""

    shared: ClaimSettings
    min_accepted_mwh: float
    grids: Grids
    draws: int
    slope_min: float
    slope_max: float
    iqr_fraction: float
    transition_upper: float
    transition_lower: float
    min_instructions: int
    min_r: float


def load_claim3_settings(shared: ClaimSettings) -> Claim3Settings:
    """Return Claim 3's thresholds, each pinned to its locked section."""
    p = load_params()
    return Claim3Settings(
        shared=shared,
        min_accepted_mwh=p.number("claim3.min_accepted_mwh"),
        grids=Grids(
            f_max=p.number("claim3.f_grid_max"),
            f_step=p.number("claim3.f_grid_step"),
            delta_step_mwh=p.number("claim3.delta_grid_step_mwh"),
        ),
        draws=p.integer("claim3.draws"),
        slope_min=p.number("claim3.slope_min"),
        slope_max=p.number("claim3.slope_max"),
        iqr_fraction=p.number("claim3.separability_iqr_fraction"),
        transition_upper=p.number("claim3.transition_upper"),
        transition_lower=p.number("claim3.transition_lower"),
        min_instructions=p.integer("claim3.min_instructions"),
        min_r=p.number("claim3.min_r"),
    )


@dataclass(frozen=True)
class SideResult:
    """One side's (offers' or bids') Claim 3 results."""

    side: Side
    fitted: int
    r_over_1: int
    toward_identification: int
    fit: ModelFit | None
    separable: bool | None
    slope: SlopeCheck | None
    breakpoint: tuple[float, float] | None
    transition_width: float | None
    placebo: ModelFit | None
    placebo_size: int
    identified: bool
    flagged: bool


@dataclass(frozen=True)
class Claim3Result:
    """A unit's Claim 3 results under one branch, or why it was not scored."""

    branch: Branch
    eta_hat: float | None
    unscored_reason: str | None
    measured: tuple[Measured, ...]
    offers: SideResult | None
    bids: SideResult | None

    def excluded_counts(self) -> dict[str, int]:
        """Return how many instructions each screen excluded."""
        counts: dict[str, int] = {}
        for m in self.measured:
            if m.excluded:
                counts[m.excluded] = counts.get(m.excluded, 0) + 1
        return counts


def score_claim3(
    unit: UnitInputs,
    adoption_week_start: datetime,
    end: datetime,
    settings: Claim3Settings,
    branch: Branch,
) -> Claim3Result:
    """Return the unit's Claim 3 results under `branch` (module docstring)."""
    shared = settings.shared
    weeks = week_starts(adoption_week_start, end)
    if not weeks:
        return Claim3Result(branch, None, NO_WEEKS, (), None, None)
    window = [m for m in unit.meter if weeks[0] <= m.period_start < end]
    try:
        eta = eta_hat(window)
    except EfficiencyUndefined:
        return Claim3Result(branch, None, ETA_UNDEFINED, (), None, None)
    if not eta_in_bounds(eta, shared.eta_min, shared.eta_max):
        return Claim3Result(branch, eta, ETA_OUT_OF_BOUNDS, (), None, None)
    items = [i for i in instructions(unit) if weeks[0] <= i.accepted and i.end <= end]
    measured = measure(
        unit,
        items,
        eta,
        branch,
        settings.min_accepted_mwh,
        shared.default_abs_mwh,
        end,
        shared.sf_or_later_runs,
    )
    walls = _walls(unit, weeks, eta, shared.sf_or_later_runs)
    offers = _side("offer", measured, walls, settings)
    bids = _side("bid", measured, walls, settings)
    return Claim3Result(branch, eta, None, measured, offers, bids)


def _walls(
    unit: UnitInputs,
    weeks: Sequence[datetime],
    eta: float,
    sf_or_later: frozenset[str],
) -> dict[datetime, float]:
    """Return the lower wall at every period start of every complete-meter week."""
    out: dict[datetime, float] = {}
    for w in weeks:
        meter = screen_meter(unit.meter, w, sf_or_later)
        if not meter.periods:
            continue
        wall = lower_wall(cumulative_change(meter.periods, eta))
        for k, period in enumerate(meter.periods):
            out[period.period_start] = wall[k]
    return out


def _side(
    side: Side,
    measured: Sequence[Measured],
    walls: dict[datetime, float],
    settings: Claim3Settings,
) -> SideResult:
    usable = [m for m in measured if m.excluded is None and m.side == side]
    fitted = [m for m in usable if m.r is not None and m.r <= 1.0]
    over = len(usable) - len(fitted)
    toward = sum(1 for m in fitted if m.r is not None and m.r >= settings.min_r)
    shared = settings.shared
    if not fitted:
        return SideResult(
            side, 0, over, 0, None, None, None, None, None, None, 0, False, False
        )
    r, rho, declared, accepted = _arrays(fitted)
    fit = fit_models(
        r,
        rho,
        declared,
        accepted,
        settings.grids,
        settings.draws,
        shared.coverage,
        unit_rng(shared.master_seed),
    )
    assert fit is not None
    separable = separately_identified(declared, settings.iqr_fraction)
    slope = slope_check(r, rho, fit.f_hat, settings.slope_min, settings.slope_max)
    identified = toward >= settings.min_instructions and slope.status == "passed"
    placebo_items: list[Measured] = []
    placebo: ModelFit | None = None
    if side == "offer":
        placebo_items = [
            m
            for m in fitted
            if walls.get(period_floor(m.instruction.accepted), -1.0)
            >= abs(m.instruction.a_mwh)
        ]
        if placebo_items:
            pr, prho, pdecl, pacc = _arrays(placebo_items)
            placebo = fit_models(
                pr,
                prho,
                pdecl,
                pacc,
                settings.grids,
                settings.draws,
                shared.coverage,
                unit_rng(shared.master_seed),
            )
    excludes = excludes_zero(fit.f_interval) and (
        excludes_zero(fit.delta_interval) or not separable
    )
    flagged = (
        side == "offer"
        and identified
        and excludes
        and placebo is not None
        and includes_zero(placebo.f_interval)
    )
    return SideResult(
        side=side,
        fitted=len(fitted),
        r_over_1=over,
        toward_identification=toward,
        fit=fit,
        separable=separable,
        slope=slope,
        breakpoint=breakpoint(r, rho),
        transition_width=transition_width(
            r, rho, settings.transition_upper, settings.transition_lower
        ),
        placebo=placebo,
        placebo_size=len(placebo_items),
        identified=identified,
        flagged=flagged,
    )


def _arrays(
    items: Sequence[Measured],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    r = np.array([m.r for m in items], dtype=float)
    rho = np.array([m.rho for m in items], dtype=float)
    declared = np.array([m.declared_mwh for m in items], dtype=float)
    accepted = np.array([abs(m.instruction.a_mwh) for m in items], dtype=float)
    return r, rho, declared, accepted


def flagged_under_both(a: Claim3Result, b: Claim3Result) -> bool:
    """Return §5.7's fourth condition: the same declarations flag under A and B."""
    if a.branch != "A" or b.branch != "B":
        raise ValueError("pass the Branch A result, then the Branch B result")
    return bool(a.offers and a.offers.flagged and b.offers and b.offers.flagged)
