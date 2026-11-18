"""Score one unit on Claims 1 and 2, from inputs to flags (PREREGISTRATION §3–§4).

Real units and synthetic batteries both pass through `score_unit`, so the
known-answer suite tests the code that scores the fleet.

1. η̂ from every metered period of the unit's complete weeks after its adoption
   week, before any screen (§3). Outside [eta_min, eta_max], or undefined, the
   unit is not scored on Claims 1–2, with that reason.
2. For each complete ISO week after the adoption week: the missing-meter screen,
   D^decl at its 337 boundaries, Claim 1's weekly ratios and Claim 2's share.
3. Claim 1: with at least min_scored_weeks scored weeks, the nested-resampling
   interval of the median error ratio and its category (§4; §12, deviation 1).
4. Claim 2's hard flag: the same over contract-free scored weeks only, with at
   least min_contract_free_weeks of them (§4).

Each interval starts from a fresh generator seeded with the master seed
(config/scoring.toml), so a unit's result does not depend on any other unit.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.claims.claim1 import Claim1Screens, Claim1Week, claim1_week
from src.claims.claim2 import claim2_week
from src.claims.declared_series import declared_series
from src.claims.results import WeekResult, load_scoring_settings
from src.claims.scoring import (
    Claim1Category,
    Claim2Category,
    Interval,
    claim1_category,
    claim2_category,
    nested_interval,
    scored_weeks,
    unit_rng,
)
from src.claims.screens import require_week_start, screen_meter, week_boundaries
from src.model.params import load_params
from src.model.types import UnitInputs
from src.physics.declared import Branch
from src.physics.efficiency import EfficiencyUndefined, eta_hat, eta_in_bounds

WEEK = timedelta(days=7)
ETA_UNDEFINED = "η̂ undefined: no metered import"
ETA_OUT_OF_BOUNDS = "η̂ outside bounds"
TOO_FEW_WEEKS = "fewer scored weeks than required"
TOO_FEW_CONTRACT_FREE = "fewer contract-free scored weeks than required"


@dataclass(frozen=True)
class ClaimSettings:
    """Every threshold and run setting Claims 1–2 read, from their sources."""

    eta_min: float
    eta_max: float
    extra_periods: int
    idle_hours: float
    idle_floor_mwh: float
    efa_boundary_hours: tuple[float, ...]
    coherent_upper: float
    not_coherent_lower: float
    tau_fraction: float
    provable_lower: float
    min_scored_weeks: int
    min_contract_free_weeks: int
    coverage: float
    draws: int
    master_seed: int
    default_abs_mwh: float
    sf_or_later_runs: frozenset[str]


def load_claim_settings() -> ClaimSettings:
    """Return thresholds from config/claims.toml and run settings from scoring.toml."""
    p = load_params()
    run = load_scoring_settings()
    return ClaimSettings(
        eta_min=p.number("efficiency.eta_min"),
        eta_max=p.number("efficiency.eta_max"),
        extra_periods=p.integer("protection.horizon_extra_periods"),
        idle_hours=p.number("screens.idle_hours"),
        idle_floor_mwh=p.number("screens.idle_floor_mwh"),
        efa_boundary_hours=p.numbers("screens.efa_boundary_hours"),
        coherent_upper=p.number("claim1.coherent_upper"),
        not_coherent_lower=p.number("claim1.not_coherent_lower"),
        tau_fraction=p.number("claim2.tau_fraction"),
        provable_lower=p.number("claim2.provable_lower"),
        min_scored_weeks=p.integer("eligibility.min_scored_weeks"),
        min_contract_free_weeks=p.integer("claim2.min_contract_free_weeks"),
        coverage=p.number("scoring.interval"),
        draws=p.integer("scoring.draws"),
        master_seed=run.master_seed,
        default_abs_mwh=run.default_abs_mwh,
        sf_or_later_runs=run.sf_or_later_runs,
    )


@dataclass(frozen=True)
class UnitResult:
    """One unit's Claims 1–2 results under one branch, or why it was not scored."""

    branch: Branch
    eta_hat: float | None
    unscored_reason: str | None
    claim1_weeks: tuple[Claim1Week, ...]
    claim2_weeks: tuple[WeekResult, ...]
    claim1_interval: Interval | None
    claim1_category: Claim1Category | None
    claim1_reason: str | None
    claim2_interval: Interval | None
    claim2_category: Claim2Category | None
    claim2_reason: str | None


def week_starts(adoption_week_start: datetime, end: datetime) -> tuple[datetime, ...]:
    """Return each complete ISO week after the adoption week, up to `end`."""
    require_week_start(adoption_week_start)
    out: list[datetime] = []
    start = adoption_week_start + WEEK
    for _ in range(max((end - start) // WEEK, 0)):
        out.append(start)
        start += WEEK
    return tuple(out)


def score_unit(
    unit: UnitInputs,
    adoption_week_start: datetime,
    end: datetime,
    settings: ClaimSettings,
    branch: Branch,
    contract_free_weeks: Collection[datetime],
    horizon_hours: float | None = None,
    contract_change_starts: Collection[datetime] = frozenset(),
) -> UnitResult:
    """Return the unit's Claims 1–2 weeks, intervals and flags (module docstring)."""
    weeks = week_starts(adoption_week_start, end)
    if not weeks:
        return _unscored(branch, None, TOO_FEW_WEEKS)
    window = [m for m in unit.meter if weeks[0] <= m.period_start < end]
    try:
        eta = eta_hat(window)
    except EfficiencyUndefined:
        return _unscored(branch, None, ETA_UNDEFINED)
    if not eta_in_bounds(eta, settings.eta_min, settings.eta_max):
        return _unscored(branch, eta, ETA_OUT_OF_BOUNDS)
    screens = Claim1Screens(
        registered_mw=unit.registered_mw,
        idle_hours=settings.idle_hours,
        idle_floor_mwh=settings.idle_floor_mwh,
        efa_boundary_hours=settings.efa_boundary_hours,
        contract_change_starts=contract_change_starts,
    )
    c1: list[Claim1Week] = []
    c2: list[WeekResult] = []
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
        )
        c1.append(claim1_week(meter, declared, eta, screens))
        c2.append(claim2_week(meter, declared, eta, settings.tau_fraction))
    i1, cat1, why1 = _claim1(c1, settings)
    free = [w for w in c2 if w.week_start in contract_free_weeks]
    i2, cat2, why2 = _claim2(free, settings)
    return UnitResult(
        branch, eta, None, tuple(c1), tuple(c2), i1, cat1, why1, i2, cat2, why2
    )


def _claim1(
    weeks: Sequence[Claim1Week], settings: ClaimSettings
) -> tuple[Interval | None, Claim1Category | None, str | None]:
    error = [w.error for w in weeks]
    if len(scored_weeks(error)) < settings.min_scored_weeks:
        return None, None, TOO_FEW_WEEKS
    interval = nested_interval(
        error, settings.draws, settings.coverage, unit_rng(settings.master_seed)
    )
    if interval is None:
        return None, None, TOO_FEW_WEEKS
    category = claim1_category(
        interval, settings.coherent_upper, settings.not_coherent_lower
    )
    return interval, category, None


def _claim2(
    weeks: Sequence[WeekResult], settings: ClaimSettings
) -> tuple[Interval | None, Claim2Category | None, str | None]:
    if len(scored_weeks(weeks)) < settings.min_contract_free_weeks:
        return None, None, TOO_FEW_CONTRACT_FREE
    interval = nested_interval(
        weeks, settings.draws, settings.coverage, unit_rng(settings.master_seed)
    )
    if interval is None:
        return None, None, TOO_FEW_CONTRACT_FREE
    return interval, claim2_category(interval, settings.provable_lower), None


def _unscored(branch: Branch, eta: float | None, reason: str) -> UnitResult:
    return UnitResult(
        branch, eta, reason, (), (), None, None, reason, None, None, reason
    )
