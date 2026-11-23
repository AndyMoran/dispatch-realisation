"""Claims 1 and 2 on hand-worked weeks, and their screens (PREREGISTRATION §4).

The working week starts Monday 2 Nov 2026, 00:00 UTC; UK time equals UTC then, so
EFA boundaries fall at 03:00, 07:00, 11:00, 15:00, 19:00 and 23:00 UTC. Period h
starts h × 30 minutes after the week starts. η̂ = 0.8 throughout.

The battery imports 10 MWh in period 2 (01:00–01:30) and exports 8 MWh in period 4
(02:00–02:30). Neither period touches an EFA boundary. Honest declared energy:
50 MWh, rising to 58 after the import, back to 50 after the export.
"""

import itertools
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.claims.claim1 import NO_USABLE_PERIODS, Claim1Screens, claim1_week, residuals
from src.claims.claim2 import NO_DECLARATION, claim2_week, violations
from src.claims.declared_series import AddBack, declared_series, protection_end
from src.claims.results import DayPart, WeekResult, load_scoring_settings
from src.claims.screens import (
    IDLE,
    MISSING_METER,
    UK,
    WeekMeter,
    efa_excluded,
    is_idle,
    require_week_start,
    screen_meter,
    week_boundaries,
)
from src.model.types import LevelSegment, MeterPeriod, Submission, build_unit_inputs

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)
SP = timedelta(minutes=30)
SF = frozenset({"SF", "R1", "R2", "R3", "RF", "DF"})
EFA = (23.0, 3.0, 7.0, 11.0, 15.0, 19.0)
ETA = 0.8


def meter(flows: dict[int, float] | None = None, run: str = "SF") -> list[MeterPeriod]:
    """A full week of net values: zero except `flows` (export positive)."""
    flows = flows or {}
    return [MeterPeriod(WEEK0 + h * SP, flows.get(h, 0.0), run) for h in range(336)]


def series(levels: dict[int, float], base: float = 50.0) -> list[float | None]:
    """Declared energy at the 337 boundaries: `base`, overridden from each index on."""
    out: list[float | None] = []
    level = base
    for b in range(337):
        level = levels.get(b, level)
        out.append(level)
    return out


HONEST = series({3: 58.0, 5: 50.0})
FLOWS = {2: -10.0, 4: 8.0}


def screens(contract: frozenset[datetime] = frozenset()) -> Claim1Screens:
    return Claim1Screens(None, 1.0, 1.0, EFA, contract)


def screened(flows: dict[int, float] = FLOWS) -> WeekMeter:
    return screen_meter(meter(flows), WEEK0, SF)


# ---------------------------------------------------------------------- screens


def test_week_shape_and_start() -> None:
    bounds = week_boundaries(WEEK0)
    assert len(bounds) == 337 and bounds[-1] == WEEK0 + timedelta(days=7)
    for bad in (WEEK0 + timedelta(days=1), WEEK0 + SP):
        with pytest.raises(ValueError):
            require_week_start(bad)


def test_missing_or_pre_sf_meter_leaves_the_week_unscored() -> None:
    assert screen_meter(meter()[1:], WEEK0, SF).unscored_reason == MISSING_METER
    assert screen_meter(meter(run="II"), WEEK0, SF).unscored_reason == MISSING_METER
    assert len(screen_meter(meter(), WEEK0, SF).periods) == 336


@pytest.mark.parametrize(("day", "periods"), [(24, 48), (25, 50), (26, 48)])
def test_efa_screen_takes_12_periods_every_uk_day(day: int, periods: int) -> None:
    """25 Oct 2026 has 50 periods (clocks go back); 12 are still excluded."""
    start = datetime(2026, 10, day, tzinfo=UK).astimezone(UTC)
    end = datetime(2026, 10, day + 1, tzinfo=UK).astimezone(UTC)
    starts = [start + k * SP for k in range(int((end - start) / SP))]
    assert len(starts) == periods
    assert sum(efa_excluded(s, EFA) for s in starts) == 12


def test_efa_window_is_one_period_each_side() -> None:
    """Boundary 03:00 GMT: exclude the 02:30 and 03:00 starts; keep 02:00 and 03:30."""
    at = WEEK0 + timedelta(hours=3)
    assert efa_excluded(at - SP, EFA) and efa_excluded(at, EFA)
    assert not efa_excluded(at - 2 * SP, EFA) and not efa_excluded(at + SP, EFA)


def test_idle_threshold() -> None:
    """Throughput 18 MWh: idle for a 20 MW unit (20 MWh threshold), not for 10 MW."""
    periods = meter(FLOWS)
    assert is_idle(periods, 20.0, 1.0, 1.0) and not is_idle(periods, 10.0, 1.0, 1.0)
    assert is_idle(meter(), None, 1.0, 1.0)


# ---------------------------------------------------------------------- claim 1


def test_honest_week_scores_zero() -> None:
    """r_2 = 8 − 0.8 × 10 = 0; r_4 = −8 − (0 − 8) = 0. Score 0."""
    result = claim1_week(screened(), HONEST, ETA, screens())
    assert result.error.score == pytest.approx(0.0)
    assert result.signed.score == pytest.approx(0.0)


def test_over_declaring_week_by_hand() -> None:
    """Declared rises 10 (not 8) after the import and falls 10 after the export.

    r_2 = 10 − 8 = 2; r_4 = −10 − (−8) = −2. Error 4 / throughput 18 = 0.2222;
    signed (2 − 2) / 18 = 0. Usable: 336 − 7 × 12 EFA periods = 252 (0.75).
    """
    declared = series({3: 60.0, 5: 50.0})
    result = claim1_week(screened(), declared, ETA, screens())
    assert result.error.score == pytest.approx(4 / 18)
    assert result.signed.score == pytest.approx(0.0)
    assert result.error.usable_share == pytest.approx(0.75)
    monday = result.error.parts[0]
    assert monday.day == date(2026, 11, 2)
    assert (monday.numerator, monday.denominator) == pytest.approx((4.0, 18.0))
    assert len(result.error.parts) == 7


def test_errors_in_screened_periods_do_not_count() -> None:
    """A jump at 03:00 (EFA) or in a contract-change period leaves the score at 4/18."""
    declared = series({3: 60.0, 5: 50.0, 6: 70.0, 7: 50.0})
    result = claim1_week(screened(), declared, ETA, screens())
    assert result.error.score == pytest.approx(4 / 18)
    jump = series({3: 60.0, 5: 50.0, 9: 70.0, 10: 50.0})
    change = frozenset({WEEK0 + 8 * SP, WEEK0 + 9 * SP})
    assert claim1_week(screened(), jump, ETA, screens(change)).error.score == (
        pytest.approx(4 / 18)
    )


def test_missing_declaration_drops_both_adjacent_periods() -> None:
    declared = series({3: 60.0, 5: 50.0})
    declared[3] = None
    r = residuals(screened(), declared, ETA)
    assert r[2] is None and r[3] is None and r[4] == pytest.approx(-2.0)


def test_claim1_unscored_weeks() -> None:
    missing = screen_meter(meter()[1:], WEEK0, SF)
    assert claim1_week(missing, HONEST, ETA, screens()).error.unscored_reason == (
        MISSING_METER
    )
    idle = screen_meter(meter(), WEEK0, SF)
    assert claim1_week(idle, HONEST, ETA, screens()).error.unscored_reason == IDLE
    nothing: list[float | None] = [None] * 337
    result = claim1_week(screened(), nothing, ETA, screens())
    assert result.error.unscored_reason == NO_USABLE_PERIODS
    with pytest.raises(ValueError):
        residuals(screened(), HONEST[:-1], ETA)


# ---------------------------------------------------------------------- claim 2


def test_lower_wall_violations_by_hand() -> None:
    """K: 0 to boundary 2, 8 at boundaries 3–4, 0 from 5. min K = 0, so L = 8 at
    period starts 3 and 4, else 0. τ = 0.02 × 8 = 0.16, so the line is 7.84.

    Declaring 0 throughout: 2 violations in 336 scored periods (Monday: 2 of 48).
    Declaring 7.9 at starts 3–4 is inside the tolerance; 7.8 is not.
    """
    zero = series({}, base=0.0)
    result = claim2_week(screened(), zero, ETA, 0.02)
    assert result.score == pytest.approx(2 / 336)
    monday = result.parts[0]
    assert (monday.numerator, monday.denominator) == (2.0, 48.0)
    inside = series({3: 7.9, 5: 0.0}, base=0.0)
    assert claim2_week(screened(), inside, ETA, 0.02).score == pytest.approx(0.0)
    outside = series({3: 7.8, 5: 0.0}, base=0.0)
    assert claim2_week(screened(), outside, ETA, 0.02).score == pytest.approx(2 / 336)


def test_claim2_scores_idle_weeks_and_skips_missing_declarations() -> None:
    idle = screen_meter(meter(), WEEK0, SF)
    assert claim2_week(idle, series({}, 0.0), ETA, 0.02).score == pytest.approx(0.0)
    declared = series({}, base=0.0)
    declared[3] = None
    flags = violations(screened(), declared, ETA, 0.02)
    assert flags[3] is None and flags[4] is True
    nothing: list[float | None] = [None] * 337
    assert claim2_week(screened(), nothing, ETA, 0.02).unscored_reason == (
        NO_DECLARATION
    )
    missing = screen_meter(meter()[1:], WEEK0, SF)
    assert claim2_week(missing, HONEST, ETA, 0.02).unscored_reason == MISSING_METER
    with pytest.raises(ValueError):
        violations(screened(), HONEST, ETA, 1.5)


# ------------------------------------------------------------ declared series


def test_declared_series_adds_pn_protection() -> None:
    """MDO 40 all week; PN 10 MW all week; no BOAs.

    H = current period + 3 from a period start = 2 h: D = 40 + 10 × 2 = 60.
    H = 6 h: D = 40 + 60 = 100. Branch B, η̂ 0.81: 0.9 × 40 + 20 = 56.
    """
    end = WEEK0 + timedelta(days=7)
    mdo = Submission("MDO", WEEK0, end, 40.0, None, WEEK0, 1)
    pn = LevelSegment(WEEK0, end + timedelta(hours=6), 10.0, 10.0)
    unit = build_unit_inputs("u", None, [mdo], [], [pn], [])
    times = [WEEK0, WEEK0 + SP]
    assert declared_series(unit, times, 0.81, "A", 3, None, 9999.0, end) == (
        pytest.approx((60.0, 60.0))
    )
    assert declared_series(unit, times, 0.81, "A", 3, 6.0, 9999.0, end) == (
        pytest.approx((100.0, 100.0))
    )
    assert declared_series(unit, times, 0.81, "B", 3, None, 9999.0, end) == (
        pytest.approx((56.0, 56.0))
    )
    assert declared_series(unit, [end], 0.81, "A", 3, None, 9999.0, end) == (None,)
    with pytest.raises(ValueError):
        protection_end(WEEK0, 3, 0.0)


# ---------------------------------------------------------- results, settings


def test_week_result_rules() -> None:
    with pytest.raises(ValueError):
        WeekResult(WEEK0, (), 0.5, None)
    with pytest.raises(ValueError):
        WeekResult(WEEK0, (DayPart(date(2026, 11, 2), 1.0, 1.0),), 0.5, "idle")
    with pytest.raises(ValueError):
        WeekResult(WEEK0, (), 1.5, "idle")
    with pytest.raises(ValueError):
        DayPart(date(2026, 11, 2), 1.0, -1.0)


def test_scoring_settings_load_and_refuse_bad_values(tmp_path: Path) -> None:
    settings = load_scoring_settings()
    assert settings.master_seed == 20261118 and "SF" in settings.sf_or_later_runs
    assert "II" not in settings.sf_or_later_runs
    good = 'schema_version = "1.0"\nmaster_seed = 1\nreliability_draws = 10\n'
    good += 'default_abs_mwh = 9999.0\nsf_or_later_runs = ["SF"]\n'
    for broken in (
        good.replace("master_seed = 1", "master_seed = -1"),
        good.replace("reliability_draws = 10", "reliability_draws = 0"),
        good.replace("9999.0", "0"),
        good.replace('["SF"]', "[]"),
        good.replace('"1.0"', '"0.1"'),
    ):
        path = tmp_path / "s.toml"
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(ValueError):
            load_scoring_settings(path)


def test_declared_series_windowing_changes_nothing() -> None:
    """Passing only nearby segments gives the same D^decl, bit for bit, as passing
    every segment, on a synthetic unit with instructions spanning period ends."""
    from src.claims.screens import week_boundaries
    from src.physics.declared import (
        declared_at,
        declared_deliverable_mwh,
        in_force_publish_times,
    )
    from src.physics.protection import boa_export_mwh, pn_protected_mwh
    from src.synthetic import battery as bt
    from src.synthetic.settings import RunLength, load_synthetic_settings

    settings = load_synthetic_settings()
    length = RunLength("test", datetime(2026, 6, 1, tzinfo=UTC), 1)
    sim = bt.simulate(
        bt.HONEST_DC_EFA,
        length,
        settings,
        bt.load_physics(),
        bt.load_dc_energy(settings),
        bt.run_rng(1, "windowing", 0, 0),
    )
    unit = bt.unit_inputs(sim, "A", 1)
    edges = week_boundaries(length.first_scored_week)
    # Period starts, and seven minutes in, where segments begin before t.
    times = sorted([*edges, *(t + timedelta(minutes=7) for t in edges[:-1])])
    published = in_force_publish_times(
        unit.submissions, "MDO", times, 9999.0, length.end
    )
    rules: tuple[AddBack, ...] = ("all", "known")
    for hours, rule in itertools.product((None, 6.0), rules):
        fast = declared_series(
            unit, times, 0.88, "A", 3, hours, 9999.0, length.end, rule
        )
        mdo = declared_at(unit.submissions, "MDO", times, 9999.0, length.end)
        checked = 0
        for t, m, f, pub in zip(times, mdo, fast, published, strict=True):
            if m is None:  # the run's end: no record in force
                assert f is None
                continue
            assert pub is not None
            end = protection_end(t, 3, hours)
            p_exp, _ = pn_protected_mwh(unit.pn, t, end)
            boas = [
                s
                for s in unit.boas
                if rule == "all"
                or (s.acceptance_time is not None and s.acceptance_time < pub)
            ]
            b_exp = boa_export_mwh(boas, unit.pn, t, end)
            assert f == declared_deliverable_mwh(m, p_exp, b_exp, 0.88, "A")
            checked += 1
        assert checked == 2 * 336
