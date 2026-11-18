"""Week results shared by Claims 1 and 2, and the run settings they read.

A week's score is a ratio of two sums over its settlement periods. Each week keeps
those sums day by day, so that scoring can resample days (PREREGISTRATION §4;
§12, deviation 1).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

SCORING_TOML = Path(__file__).resolve().parents[2] / "config" / "scoring.toml"


@dataclass(frozen=True)
class DayPart:
    """One UTC day's share of a weekly ratio: the two sums over its periods."""

    day: date
    numerator: float
    denominator: float

    def __post_init__(self) -> None:
        if self.denominator < 0:
            raise ValueError(f"{self.day}: denominator below zero")


@dataclass(frozen=True)
class WeekResult:
    """One unit-week for one claim: day parts, coverage, or the reason it is unscored.

    `parts` is empty when the week is unscored. `usable_share` is the share of the
    week's settlement periods that entered the sums.
    """

    week_start: datetime
    parts: tuple[DayPart, ...]
    usable_share: float
    unscored_reason: str | None

    def __post_init__(self) -> None:
        if not 0.0 <= self.usable_share <= 1.0:
            raise ValueError(f"usable_share outside [0, 1]: {self.usable_share}")
        if self.unscored_reason is None and not self.parts:
            raise ValueError("a scored week needs day parts")
        if self.unscored_reason is not None and self.parts:
            raise ValueError("an unscored week has no day parts")

    @property
    def score(self) -> float | None:
        """Return the week's ratio; None if unscored or nothing entered the sums."""
        denominator = sum(p.denominator for p in self.parts)
        if self.unscored_reason is not None or denominator <= 0:
            return None
        return sum(p.numerator for p in self.parts) / denominator


@dataclass(frozen=True)
class ScoringSettings:
    """Settings the pre-registration leaves to the run (config/scoring.toml)."""

    master_seed: int
    reliability_draws: int
    default_abs_mwh: float
    sf_or_later_runs: frozenset[str]


def load_scoring_settings(path: Path = SCORING_TOML) -> ScoringSettings:
    """Return the run settings, refusing a missing or malformed value."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "1.0":
        raise ValueError(f"{path.name}: schema_version must be 1.0")
    seed, draws = raw.get("master_seed"), raw.get("reliability_draws")
    default, runs = raw.get("default_abs_mwh"), raw.get("sf_or_later_runs")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError(f"{path.name}: master_seed must be a whole number ≥ 0")
    if not isinstance(draws, int) or isinstance(draws, bool) or draws < 1:
        raise ValueError(f"{path.name}: reliability_draws must be a whole number ≥ 1")
    if not isinstance(default, int | float) or default <= 0:
        raise ValueError(f"{path.name}: default_abs_mwh must be positive")
    if (
        not isinstance(runs, list)
        or not runs
        or not all(isinstance(r, str) for r in runs)
    ):
        raise ValueError(f"{path.name}: sf_or_later_runs must list run codes")
    return ScoringSettings(seed, draws, float(default), frozenset(runs))
