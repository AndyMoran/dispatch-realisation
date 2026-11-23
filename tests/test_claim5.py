"""Claim 5 (PREREGISTRATION §7) and its synthetic report, on hand-worked cases.

No band battery is simulated here; the report runs once, after this commit.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.claims.claim5 import (
    CENSOR_LIMIT,
    END_OF_DATA,
    NEXT_ACCEPTANCE,
    Claim5Settings,
    Interval,
    acceptances,
    is_default,
    kaplan_meier,
    latency_intervals,
    load_claim5_settings,
    publish_times,
    quantile,
    summarise,
    survival_at,
    unit_latency,
)
from src.model.types import LevelSegment, Submission, build_unit_inputs
from src.synthetic.claim5_report import RunResult, ended_on_routine, summarise_battery

T0 = datetime(2026, 11, 2, tzinfo=UTC)
END = T0 + timedelta(days=1)
MIN = timedelta(minutes=1)
SEC = timedelta(seconds=1)


def at(minutes: float) -> datetime:
    return T0 + minutes * MIN


def record(dataset: str, published: datetime, level: float = 40.0) -> Submission:
    return Submission(
        dataset, published, published + 30 * MIN, level, None, published, 1
    )  # type: ignore[arg-type]


def boa(number: int, accepted: datetime) -> LevelSegment:
    return LevelSegment(accepted, accepted + 20 * MIN, 10.0, 10.0, number, accepted)


def test_settings_come_from_section_7() -> None:
    assert load_claim5_settings() == Claim5Settings(30.0, 1.0)
    with pytest.raises(ValueError):
        Claim5Settings(0.0, 1.0)


def test_each_acceptance_counted_once() -> None:
    """Two segments of acceptance 7 (a period split) count once."""
    segs = [boa(7, at(10)), boa(7, at(10)), boa(8, at(3))]
    assert acceptances(segs) == [at(3), at(10)]
    with pytest.raises(ValueError):
        acceptances([boa(7, at(10)), boa(7, at(11))])
    with pytest.raises(ValueError):
        acceptances([LevelSegment(at(0), at(30), 1.0, 1.0)])


def test_defaults_are_left_out_and_counted() -> None:
    recs = [
        record("MDO", at(5)),
        record("MDB", at(6), -20.0),
        record("MDO", at(7), 9999.0),
        record("MDB", at(8), -9999.0),
    ]
    times, defaults = publish_times(recs, 9999.0)
    assert times == [at(5), at(6)] and defaults == 2
    ramp = Submission("MDO", at(0), at(30), 40.0, 9999.0, at(9), 1)
    assert is_default(ramp, 9999.0)


@pytest.mark.parametrize(
    ("published", "minutes", "observed", "reason"),
    [
        ([at(13.5)], 3.5, True, None),  # observed
        ([at(10)], 0.0, True, None),  # published at the acceptance: L = 0
        ([at(9), at(12)], 2.0, True, None),  # an earlier record does not count
        ([at(40)], 30.0, True, None),  # exactly 30 minutes is observed
        ([at(40) + SEC], 30.0, False, CENSOR_LIMIT),  # just after: censored at 30
        ([], 30.0, False, CENSOR_LIMIT),
    ],
)
def test_one_acceptance_by_hand(
    published: list[datetime], minutes: float, observed: bool, reason: str | None
) -> None:
    (iv,) = latency_intervals([at(10)], published, 30.0, END)
    assert iv.minutes == pytest.approx(minutes)
    assert (iv.observed, iv.reason) == (observed, reason)


def test_next_acceptance_censors_and_owns_its_record() -> None:
    """Acceptances at 10 and 18. A record at 18 belongs to the second, so the first
    is censored at 8 minutes; the second has L = 0. A record at 17 ends the first.
    """
    first, second = latency_intervals([at(10), at(18)], [at(18)], 30.0, END)
    assert (first.minutes, first.observed, first.reason) == (
        8.0,
        False,
        NEXT_ACCEPTANCE,
    )
    assert (second.minutes, second.observed) == (0.0, True)
    first, second = latency_intervals([at(10), at(18)], [at(17)], 30.0, END)
    assert (first.minutes, first.observed) == (7.0, True)
    assert (second.reason, second.minutes) == (CENSOR_LIMIT, 30.0)


def test_end_of_data_censors() -> None:
    end = at(20)
    (iv,) = latency_intervals([at(10)], [at(25)], 30.0, end)
    assert (iv.minutes, iv.reason) == (10.0, END_OF_DATA)
    with pytest.raises(ValueError):
        latency_intervals([at(20)], [], 30.0, end)
    with pytest.raises(ValueError):
        latency_intervals([at(10), at(5)], [], 30.0, END)


def test_interval_rules() -> None:
    with pytest.raises(ValueError):
        Interval(at(0), -1.0, True, None, at(0))
    with pytest.raises(ValueError):
        Interval(at(0), 1.0, True, CENSOR_LIMIT, at(1))
    with pytest.raises(ValueError):
        Interval(at(0), 1.0, False, CENSOR_LIMIT, at(1))
    with pytest.raises(ValueError):
        Interval(at(0), 1.0, False, "other", None)


def obs(m: float) -> Interval:
    return Interval(at(0), m, True, None, at(m))


def cen(m: float) -> Interval:
    return Interval(at(0), m, False, CENSOR_LIMIT, None)


def test_kaplan_meier_by_hand() -> None:
    """Observed 1, 2, 3 and censored 2. At 1: 4 at risk, S = 3/4. At 2 the event
    counts before the censoring: 3 at risk, S = 3/4 × 2/3 = 1/2. At 3: 1 at risk,
    S = 0. Median 2, 75th percentile 3, share within 1 minute 1/4.
    """
    ivs = [obs(1), obs(2), obs(3), cen(2)]
    curve = kaplan_meier(ivs)
    assert curve == pytest.approx([(1.0, 0.75), (2.0, 0.5), (3.0, 0.0)])
    assert quantile(curve, 0.5) == 2.0
    assert quantile(curve, 0.75) == 3.0
    assert survival_at(curve, 0.5) == 1.0
    assert survival_at(curve, 1.0) == pytest.approx(0.75)
    s = summarise(ivs, 1.0, units=1)
    assert s["share_within_benchmark"] == pytest.approx(0.25)
    assert (s["boas"], s["observed"], s["median_min"]) == (4, 3, 2.0)
    with pytest.raises(ValueError):
        quantile(curve, 1.0)


def test_heavy_censoring_leaves_upper_quantiles_unreached() -> None:
    """Observed 1, then three censored at 30: S stays at 3/4, so the median and
    above are never reached."""
    s = summarise([obs(1), cen(30), cen(30), cen(30)], 1.0)
    assert s["median_min"] is None and s["p90_min"] is None
    assert s["share_within_benchmark"] == pytest.approx(0.25)
    assert summarise([], 1.0)["median_min"] is None


def test_unit_latency_window_and_defaults() -> None:
    """Acceptances at 5 (before the window) and 40; records at 41 and a default
    at 40.5. Only the acceptance at 40 is in the window; the default is skipped.
    """
    unit = build_unit_inputs(
        "u",
        None,
        [record("MDO", at(41)), record("MDO", at(40.5), 9999.0)],
        [],
        [],
        [boa(1, at(5)), boa(2, at(40))],
    )
    got = unit_latency(unit, at(30), END, load_claim5_settings(), 9999.0)
    (iv,) = got.intervals
    assert (iv.accepted, iv.minutes, iv.observed) == (at(40), 1.0, True)
    assert got.default_records == 1
    with pytest.raises(ValueError):
        unit_latency(unit, at(30), at(30), load_claim5_settings(), 9999.0)


# ------------------------------------------------------------------ synthetic report


def test_routine_or_response() -> None:
    """Lag 5. Accepted at 27: a record at 30 is routine (a period start); one at 32
    is the response. Accepted at 25: a record at 30 is the response and a period
    start at once, so it counts as the response."""
    assert ended_on_routine(Interval(at(27), 3.0, True, None, at(30)), T0, 5) is True
    assert ended_on_routine(Interval(at(27), 5.0, True, None, at(32)), T0, 5) is False
    assert ended_on_routine(Interval(at(25), 5.0, True, None, at(30)), T0, 5) is False
    assert ended_on_routine(cen(30), T0, 5) is None


def test_battery_summary() -> None:
    runs = [RunResult((obs(1), obs(3)), 1, 0), RunResult((cen(30),), 0, 2)]
    s = summarise_battery("x", 1, runs, 1.0)
    assert (s["known_lag_min"], s["boas"], s["observed"]) == (1, 3, 2)
    assert s["routine_share_of_observed"] == pytest.approx(0.5)
    assert s["default_records"] == 2
    empty = summarise_battery("y", 5, [RunResult((cen(30),), 0, 0)], 1.0)
    assert empty["routine_share_of_observed"] is None
