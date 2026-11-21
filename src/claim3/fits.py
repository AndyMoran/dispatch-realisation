"""Claim 3's two models, their intervals and specification checks (§5.4–§5.5).

Readings and conventions fixed in PROJECT.md §11 (21 Nov 2026) before this code:

- Proportional: ρ = min(1, (1 − f)/r); additive: ρ = min(1, (MDO − Δ)/|A|), MDO
  being the declaration as published before acceptance (Branch B converted).
- Least squares over §5.4's grids; 95% percentile intervals from resampling
  instructions with replacement; ties on the grid go to the smaller value.
- Slope check: log ρ on log r beyond the proportional kink 1 − f̂, ρ ≤ 0 excluded
  and counted. Fewer than three points: unavailable. Outside [slope_min,
  slope_max]: "model rejected".
- Separability: IQR of the declarations below a fraction of their median: the
  models are not separately identified.
- Breakpoint (diagnostic): ρ = 1 up to b, then a straight line; b on a 0.01 grid.
- Transition width (diagnostic): from a decreasing isotonic fit of ρ on r; the
  gap between the first r where it falls to 0.95 and to 0.75; unavailable if it
  does not cross both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from src.claims.scoring import Interval

SlopeStatus = Literal["passed", "model rejected", "unavailable"]
BREAKPOINT_STEP = 0.01
MIN_SLOPE_POINTS = 3


@dataclass(frozen=True)
class Grids:
    """§5.4's grids, from config/claims.toml."""

    f_max: float
    f_step: float
    delta_step_mwh: float

    def f(self) -> NDArray[np.float64]:
        """Return f from 0 to f_max in steps of f_step."""
        count = round(self.f_max / self.f_step) + 1
        return np.round(np.arange(count) * self.f_step, 10)

    def delta(self, top_mwh: float) -> NDArray[np.float64]:
        """Return Δ from 0 to `top_mwh` in steps of delta_step_mwh."""
        count = int(np.floor(top_mwh / self.delta_step_mwh + 1e-9)) + 1
        return np.round(np.arange(max(count, 1)) * self.delta_step_mwh, 10)


def proportional_curves(
    r: NDArray[np.float64], f_grid: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Return ρ = min(1, (1 − f)/r) for every f (rows) and instruction (columns)."""
    out: NDArray[np.float64] = np.minimum(1.0, (1.0 - f_grid)[:, None] / r[None, :])
    return out


def additive_curves(
    declared: NDArray[np.float64],
    accepted: NDArray[np.float64],
    delta_grid: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Return ρ = min(1, (MDO − Δ)/|A|) for every Δ (rows) and instruction."""
    out: NDArray[np.float64] = np.minimum(
        1.0, (declared[None, :] - delta_grid[:, None]) / accepted[None, :]
    )
    return out


def best_on_grid(
    curves: NDArray[np.float64], rho: NDArray[np.float64], grid: NDArray[np.float64]
) -> float:
    """Return the grid value with the least squared error (ties: the smallest)."""
    sse = ((curves - rho[None, :]) ** 2).sum(axis=1)
    return float(grid[int(np.argmin(sse))])


@dataclass(frozen=True)
class ModelFit:
    """Both models' estimates and intervals on one set of instructions."""

    n: int
    f_hat: float
    f_interval: Interval
    delta_hat: float
    delta_interval: Interval


def fit_models(
    r: NDArray[np.float64],
    rho: NDArray[np.float64],
    declared: NDArray[np.float64],
    accepted: NDArray[np.float64],
    grids: Grids,
    draws: int,
    coverage: float,
    rng: np.random.Generator,
) -> ModelFit | None:
    """Return both fits and their resampled intervals; None for no instructions."""
    n = r.size
    if n == 0:
        return None
    f_grid = grids.f()
    d_grid = grids.delta(float(np.median(declared)))
    prop = proportional_curves(r, f_grid)
    add = additive_curves(declared, accepted, d_grid)
    f_hat = best_on_grid(prop, rho, f_grid)
    d_hat = best_on_grid(add, rho, d_grid)
    f_draws = np.empty(draws)
    d_draws = np.empty(draws)
    for k in range(draws):
        idx = rng.integers(0, n, size=n)
        f_draws[k] = best_on_grid(prop[:, idx], rho[idx], f_grid)
        d_draws[k] = best_on_grid(add[:, idx], rho[idx], d_grid)
    tail = 100 * (1 - coverage) / 2
    f_lo, f_hi = np.percentile(f_draws, [tail, 100 - tail])
    d_lo, d_hi = np.percentile(d_draws, [tail, 100 - tail])
    return ModelFit(
        n,
        f_hat,
        Interval(float(f_lo), float(f_hi), draws, 0),
        d_hat,
        Interval(float(d_lo), float(d_hi), draws, 0),
    )


def excludes_zero(interval: Interval) -> bool:
    """Return whether an interval for f or Δ lies wholly above zero."""
    return interval.lower > 0.0


def includes_zero(interval: Interval) -> bool:
    """Return whether an interval for f reaches down to zero."""
    return interval.lower <= 0.0


@dataclass(frozen=True)
class SlopeCheck:
    """§5.5's slope check: log ρ on log r beyond the proportional kink."""

    status: SlopeStatus
    slope: float | None
    points: int
    nonpositive_rho: int


def slope_check(
    r: NDArray[np.float64],
    rho: NDArray[np.float64],
    f_hat: float,
    slope_min: float,
    slope_max: float,
) -> SlopeCheck:
    """Return the slope check: passed, "model rejected", or unavailable."""
    beyond = r > 1.0 - f_hat
    positive = rho > 0
    nonpositive = int(np.count_nonzero(beyond & ~positive))
    use = beyond & positive
    points = int(np.count_nonzero(use))
    if points < MIN_SLOPE_POINTS:
        return SlopeCheck("unavailable", None, points, nonpositive)
    x, y = np.log(r[use]), np.log(rho[use])
    if np.ptp(x) <= 0.0:
        return SlopeCheck("unavailable", None, points, nonpositive)
    slope = float(np.polyfit(x, y, 1)[0])
    status: SlopeStatus = (
        "passed" if slope_min <= slope <= slope_max else "model rejected"
    )
    return SlopeCheck(status, slope, points, nonpositive)


def separately_identified(declared: NDArray[np.float64], iqr_fraction: float) -> bool:
    """Return whether MDO varies enough to tell the two models apart (§5.5)."""
    q1, mid, q3 = np.percentile(declared, [25, 50, 75])
    return bool(q3 - q1 >= iqr_fraction * mid)


def breakpoint(r: NDArray[np.float64], rho: NDArray[np.float64]) -> tuple[float, float]:
    """Return (b, slope) of ρ = 1 for r ≤ b, then 1 + slope × (r − b): least squares."""
    best = (np.inf, 0.0, 0.0)
    top = float(r.max())
    for b in np.round(np.arange(0.0, top + BREAKPOINT_STEP, BREAKPOINT_STEP), 10):
        after = r > b
        x = r[after] - b
        slope = float((rho[after] - 1.0) @ x / (x @ x)) if after.any() else 0.0
        fitted = np.where(after, 1.0 + slope * (r - b), 1.0)
        sse = float(((rho - fitted) ** 2).sum())
        if sse < best[0]:
            best = (sse, float(b), slope)
    return best[1], best[2]


def decreasing_fit(y: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return the least-squares non-increasing fit to y (pool adjacent violators)."""
    blocks: list[list[float]] = []  # [mean, count]
    for value in y:
        blocks.append([float(value), 1.0])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            m2, c2 = blocks.pop()
            m1, c1 = blocks.pop()
            blocks.append([(m1 * c1 + m2 * c2) / (c1 + c2), c1 + c2])
    out = np.concatenate([np.full(int(c), m) for m, c in blocks])
    result: NDArray[np.float64] = out
    return result


def transition_width(
    r: NDArray[np.float64], rho: NDArray[np.float64], upper: float, lower: float
) -> float | None:
    """Return the spread of r over which the fitted ρ falls from upper to lower."""
    order = np.argsort(r, kind="stable")
    fitted = decreasing_fit(rho[order])
    rs = r[order]
    hit_upper = np.flatnonzero(fitted <= upper)
    hit_lower = np.flatnonzero(fitted <= lower)
    if hit_upper.size == 0 or hit_lower.size == 0:
        return None
    return float(rs[hit_lower[0]] - rs[hit_upper[0]])
