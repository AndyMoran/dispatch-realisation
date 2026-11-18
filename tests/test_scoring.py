"""Unit scores, nested-resampling intervals, flags and reliability (§4; §12, dev. 1)."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from src.claims.reliability import (
    HalfScores,
    half_scores,
    half_weeks,
    ranks,
    reliability_interval,
    reliability_verdict,
    spearman,
    spearman_brown,
)
from src.claims.results import DayPart, WeekResult
from src.claims.scoring import (
    Interval,
    claim1_category,
    claim2_category,
    nested_interval,
    scored_weeks,
    unit_rng,
    unit_score,
)

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)


def week(k: int, ratios: list[float], den: float = 10.0) -> WeekResult:
    """Week k with one day part per ratio: numerator ratio × den over den."""
    start = WEEK0 + timedelta(weeks=k)
    parts = tuple(
        DayPart((start + timedelta(days=d)).date(), r * den, den)
        for d, r in enumerate(ratios)
    )
    return WeekResult(start, parts, 1.0, None)


def flat(k: int, ratio: float) -> WeekResult:
    return week(k, [ratio] * 7)


UNSCORED = WeekResult(WEEK0 + timedelta(weeks=9), (), 0.0, "idle")


# ------------------------------------------------------------------ unit score


def test_unit_score_is_the_median_of_scored_weeks() -> None:
    weeks = [flat(0, 0.1), flat(1, 0.3), flat(2, 0.2), UNSCORED]
    assert unit_score(weeks) == pytest.approx(0.2)
    assert unit_score([UNSCORED]) is None
    assert [w.week_start for w in scored_weeks(weeks[::-1])] == [
        w.week_start for w in weeks[:3]
    ]


# ------------------------------------------------------------- nested interval


def test_constant_ratios_give_a_point_interval() -> None:
    """Every day of every week has ratio 0.1, so every draw's median is 0.1."""
    weeks = [flat(k, 0.1) for k in range(4)]
    interval = nested_interval(weeks, 1000, 0.95, unit_rng(1))
    assert interval is not None
    assert (interval.lower, interval.upper) == pytest.approx((0.1, 0.1))
    assert interval.degenerate_draws == 0


def test_interval_is_deterministic_and_ignores_input_order() -> None:
    weeks = [week(k, [0.05 * ((k + d) % 5) for d in range(7)]) for k in range(6)]
    first = nested_interval(weeks, 1000, 0.95, unit_rng(20261118))
    again = nested_interval(weeks[::-1] + [UNSCORED], 1000, 0.95, unit_rng(20261118))
    assert first == again
    score = unit_score(weeks)
    assert first is not None and score is not None
    assert first.lower <= score <= first.upper


def test_week_resampling_widens_a_spread_of_weeks() -> None:
    """Weeks at 0.1 and 0.3 with constant days: day resampling alone could not move
    any week, but resampling weeks makes the median vary between them."""
    weeks = [flat(0, 0.1), flat(1, 0.1), flat(2, 0.3), flat(3, 0.3)]
    interval = nested_interval(weeks, 1000, 0.95, unit_rng(5))
    assert interval is not None
    assert interval.lower == pytest.approx(0.1) and interval.upper == pytest.approx(0.3)


def test_empty_draws_are_counted_not_hidden() -> None:
    """One week, one day with throughput out of seven: about (6/7)^7 ≈ 34% of
    draws resample no day with a denominator, and are counted as degenerate."""
    parts = tuple(
        DayPart(date(2026, 11, 2 + d), 1.0 if d == 0 else 0.0, 10.0 if d == 0 else 0.0)
        for d in range(7)
    )
    sparse = WeekResult(WEEK0, parts, 1.0, None)
    interval = nested_interval([sparse], 1000, 0.95, unit_rng(3))
    assert interval is not None and 250 < interval.degenerate_draws < 430
    assert (interval.lower, interval.upper) == pytest.approx((0.1, 0.1))


def test_interval_refusals() -> None:
    assert nested_interval([UNSCORED], 10, 0.95, unit_rng(1)) is None
    for draws, coverage in ((0, 0.95), (10, 1.0)):
        with pytest.raises(ValueError):
            nested_interval([flat(0, 0.1)], draws, coverage, unit_rng(1))
    with pytest.raises(ValueError):
        unit_rng(-1)


# ---------------------------------------------------------------------- flags


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (0.01, 0.05, "coherent"),
        (0.15, 0.40, "not shown coherent"),
        (0.04, 0.16, "indeterminate"),
        (0.10, 0.14, "indeterminate"),
    ],
)
def test_claim1_categories(lower: float, upper: float, expected: str) -> None:
    assert claim1_category(Interval(lower, upper, 1000, 0), 0.05, 0.15) == expected


def test_claim2_categories() -> None:
    assert claim2_category(Interval(0.05, 0.2, 1000, 0), 0.05) == (
        "provable under-declaration"
    )
    assert claim2_category(Interval(0.049, 0.2, 1000, 0), 0.05) == "none detected"


# ----------------------------------------------------------------- reliability


def test_half_weeks_split_by_date_parity() -> None:
    """2 Nov is even: days 2, 4, 6, 8 even (4); 3, 5, 7 odd (3)."""
    weeks = [flat(0, 0.1), UNSCORED]
    assert [p.day.day for p in half_weeks(weeks, "odd")[0].parts] == [3, 5, 7]
    halves = half_scores(weeks)
    assert (halves.odd_days, halves.even_days) == (3, 4)
    assert halves.odd == pytest.approx(0.1) and halves.even == pytest.approx(0.1)


def test_ranks_and_spearman() -> None:
    assert ranks([10.0, 30.0, 20.0, 20.0]).tolist() == [1.0, 4.0, 2.5, 2.5]
    assert spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    with pytest.raises(ValueError):
        spearman([1], [1])


def test_spearman_brown() -> None:
    """2 × 0.6 / 1.6 = 0.75."""
    assert spearman_brown(0.6) == pytest.approx(0.75)
    assert spearman_brown(1.0) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        spearman_brown(-1.0)


def test_reliability_interval_and_verdicts() -> None:
    """Halves agree in rank for every unit, so every usable draw gives 1."""
    halves = [HalfScores(0.1 * k, 0.1 * k + 0.01, 14, 14) for k in range(1, 8)]
    interval = reliability_interval(halves, 500, 0.95, np.random.default_rng(2))
    assert interval is not None
    assert (interval.lower, interval.upper) == pytest.approx((1.0, 1.0))
    # With two units, half the draws pick one unit twice: no spread, no correlation.
    pair = reliability_interval(halves[:2], 500, 0.95, np.random.default_rng(2))
    assert pair is not None and 180 < pair.degenerate_draws < 320
    assert reliability_interval(halves[:1], 500, 0.95, np.random.default_rng(2)) is None
    assert reliability_verdict(Interval(0.2, 0.45, 1000, 0), 0.5) == "unreliable"
    assert reliability_verdict(Interval(0.4, 0.7, 1000, 0), 0.5) == "straddles 0.5"
    assert reliability_verdict(Interval(0.5, 0.9, 1000, 0), 0.5) == "reliable"
