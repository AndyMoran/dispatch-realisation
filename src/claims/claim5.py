"""Claim 5: redeclaration latency (PREREGISTRATION §7; PROJECT.md §11, 23 Nov 2026).

For each accepted BOA, L is the minutes from its acceptance time to the unit's
first MDO or MDB record with publishTime at or after it. Records holding the
±9999 default (R13) are not redeclarations and do not end an interval; they are
counted. An interval is censored at the earliest of the unit's next acceptance,
30 minutes after this one and the end of the data. A record published at or
after the next acceptance belongs to that acceptance; a record at exactly 30
minutes is observed.

L measures the time to the first record after an acceptance, which need not
respond to it: a unit that also publishes routine records shows an L no longer
than the time to its next one. Public data cannot separate the two.

Censoring is handled by the Kaplan–Meier estimator, pooled over acceptances.
Unless Elexon confirms M14, L is an upper bound and the ≤ 1-minute share a lower
bound (§7).
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.model.params import load_params
from src.model.types import LevelSegment, Submission, UnitInputs, require_utc

NEXT_ACCEPTANCE = "next acceptance"
CENSOR_LIMIT = "censoring limit"
END_OF_DATA = "end of data"
REASONS = (NEXT_ACCEPTANCE, CENSOR_LIMIT, END_OF_DATA)
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class Claim5Settings:
    """§7's censoring limit and benchmark, in minutes, from config/claims.toml."""

    censor_min: float
    benchmark_min: float

    def __post_init__(self) -> None:
        if self.censor_min <= 0 or self.benchmark_min < 0:
            raise ValueError("censoring limit must be positive, benchmark not negative")


def load_claim5_settings() -> Claim5Settings:
    """Return §7's 30-minute censoring limit and 1-minute benchmark."""
    p = load_params()
    return Claim5Settings(
        p.number("claim5.censor_min"), p.number("claim5.benchmark_min")
    )


@dataclass(frozen=True)
class Interval:
    """One acceptance's latency: observed, or censored with its reason."""

    accepted: datetime
    minutes: float
    observed: bool
    reason: str | None
    published: datetime | None

    def __post_init__(self) -> None:
        if self.minutes < 0:
            raise ValueError("negative latency")
        if self.observed != (self.reason is None):
            raise ValueError("an observed interval has no censoring reason")
        if self.observed != (self.published is not None):
            raise ValueError("an observed interval ends at a published record")
        if self.reason is not None and self.reason not in REASONS:
            raise ValueError(f"unknown censoring reason: {self.reason}")


def acceptances(boas: Sequence[LevelSegment]) -> list[datetime]:
    """Return each accepted instruction's acceptance time once, earliest first.

    BOALF gives an instruction as several segments sharing an acceptance number.
    """
    seen: dict[int, datetime] = {}
    for s in boas:
        if s.acceptance_number is None or s.acceptance_time is None:
            raise ValueError("a BOA segment needs an acceptance number and time")
        first = seen.setdefault(s.acceptance_number, s.acceptance_time)
        if first != s.acceptance_time:
            raise ValueError(f"acceptance {s.acceptance_number} has two times")
    return sorted(seen.values())


def is_default(record: Submission, default_abs_mwh: float) -> bool:
    """Return whether a record holds the ±9999 default anywhere (R13)."""
    levels = [record.level_from_mwh]
    if record.level_to_mwh is not None:
        levels.append(record.level_to_mwh)
    return any(abs(v) >= default_abs_mwh for v in levels)


def publish_times(
    submissions: Sequence[Submission], default_abs_mwh: float
) -> tuple[list[datetime], int]:
    """Return the sorted publish times of MDO and MDB records that are not
    defaults, and how many default records were left out."""
    times: set[datetime] = set()
    defaults = 0
    for s in submissions:
        if s.dataset not in ("MDO", "MDB"):
            continue
        if is_default(s, default_abs_mwh):
            defaults += 1
        else:
            times.add(s.publish_time)
    return sorted(times), defaults


def latency_intervals(
    accepted: Sequence[datetime],
    published: Sequence[datetime],
    censor_min: float,
    data_end: datetime,
) -> list[Interval]:
    """Return one interval per acceptance, from sorted times (module docstring)."""
    require_utc(data_end, "data_end")
    if list(accepted) != sorted(accepted) or list(published) != sorted(published):
        raise ValueError("times must be sorted")
    limit = timedelta(minutes=censor_min)
    out = []
    for i, a in enumerate(accepted):
        if a >= data_end:
            raise ValueError("acceptance at or after the end of the data")
        bounds = [(a + limit, CENSOR_LIMIT), (data_end, END_OF_DATA)]
        if i + 1 < len(accepted):
            bounds.append((accepted[i + 1], NEXT_ACCEPTANCE))
        j = bisect.bisect_left(published, a)
        p = published[j] if j < len(published) else None
        if (
            p is not None
            and p <= a + limit
            and p < data_end
            and (i + 1 == len(accepted) or p < accepted[i + 1])
        ):
            out.append(Interval(a, (p - a) / MINUTE, True, None, p))
            continue
        order = {NEXT_ACCEPTANCE: 0, CENSOR_LIMIT: 1, END_OF_DATA: 2}
        end, reason = min(bounds, key=lambda b: (b[0], order[b[1]]))
        out.append(Interval(a, (end - a) / MINUTE, False, reason, None))
    return out


@dataclass(frozen=True)
class UnitLatency:
    """One unit's intervals in a window, and the default records left out."""

    intervals: tuple[Interval, ...]
    default_records: int


def unit_latency(
    unit: UnitInputs,
    window_start: datetime,
    window_end: datetime,
    settings: Claim5Settings,
    default_abs_mwh: float,
) -> UnitLatency:
    """Return Claim 5's intervals for acceptances in [window_start, window_end).

    Records published after the window still end intervals that start inside it;
    the data end at `window_end` for censoring, so none does.
    """
    require_utc(window_start, "window_start")
    if window_end <= window_start:
        raise ValueError("empty window")
    accepted = [a for a in acceptances(unit.boas) if window_start <= a < window_end]
    published, defaults = publish_times(unit.submissions, default_abs_mwh)
    return UnitLatency(
        tuple(latency_intervals(accepted, published, settings.censor_min, window_end)),
        defaults,
    )


# ------------------------------------------------------------------ Kaplan–Meier


def kaplan_meier(intervals: Sequence[Interval]) -> list[tuple[float, float]]:
    """Return the survival curve S(t) as (time, S) steps at each observed time.

    At a time with both events and censorings, events count first, as usual.
    """
    times = sorted({iv.minutes for iv in intervals if iv.observed})
    at_risk = len(intervals)
    by_time: dict[float, tuple[int, int]] = {}
    for iv in intervals:
        d, c = by_time.get(iv.minutes, (0, 0))
        by_time[iv.minutes] = (d + iv.observed, c + (not iv.observed))
    curve: list[tuple[float, float]] = []
    s = 1.0
    for t in sorted(by_time):
        d, c = by_time[t]
        if d:
            s *= 1.0 - d / at_risk
            curve.append((t, s))
        at_risk -= d + c
    assert [t for t, _ in curve] == times
    return curve


def survival_at(curve: Sequence[tuple[float, float]], minutes: float) -> float:
    """Return S(minutes): the estimated share with L greater than `minutes`."""
    s = 1.0
    for t, value in curve:
        if t > minutes:
            break
        s = value
    return s


def quantile(curve: Sequence[tuple[float, float]], q: float) -> float | None:
    """Return the smallest time with S ≤ 1 − q; None if the curve never gets there."""
    if not 0 < q < 1:
        raise ValueError(f"quantile outside (0, 1): {q}")
    for t, s in curve:
        if s <= 1.0 - q + 1e-12:
            return t
    return None


def summarise(
    intervals: Sequence[Interval], benchmark_min: float, units: int | None = None
) -> dict[str, object]:
    """Return §7's statistics for pooled intervals (readings of 23 Nov 2026)."""
    curve = kaplan_meier(intervals)
    censored = {r: sum(1 for iv in intervals if iv.reason == r) for r in REASONS}
    return {
        "boas": len(intervals),
        "units": units,
        "observed": sum(1 for iv in intervals if iv.observed),
        "censored": censored,
        "median_min": quantile(curve, 0.5) if intervals else None,
        "p75_min": quantile(curve, 0.75) if intervals else None,
        "p90_min": quantile(curve, 0.9) if intervals else None,
        "share_within_benchmark": (
            1.0 - survival_at(curve, benchmark_min) if intervals else None
        ),
        "benchmark_min": benchmark_min,
        "bound": "L an upper bound; the benchmark share a lower bound (M14)",
    }
