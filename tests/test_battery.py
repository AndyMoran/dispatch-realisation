"""The honest synthetic battery: physics, records and determinism.

These tests check the battery against §3's physics and the declaration rule fixed
on 18 Nov 2026. They compute no claim score: bands come in a later patch, after
the batteries are fixed.
"""

import dataclasses
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.claims.declared_series import declared_series
from src.claims.screens import week_boundaries
from src.physics.declared import Branch
from src.synthetic import battery as bt
from src.synthetic.settings import RunLength, load_synthetic_settings

SETTINGS = load_synthetic_settings()
PHYSICS = bt.load_physics()
DC = bt.load_dc_energy(SETTINGS)
# One adoption week and one scored week, inside the frequency span.
TWO_WEEKS = RunLength("test", datetime(2026, 6, 1, tzinfo=UTC), 1)
LAG = SETTINGS.honest_lag_min


def run(
    scenario: bt.Scenario = bt.HONEST, seed: int = 0, **changes: Any
) -> bt.Simulation:
    settings = dataclasses.replace(SETTINGS, **changes) if changes else SETTINGS
    rng = bt.run_rng(SETTINGS.master_seed, scenario.name, 0, seed)
    return bt.simulate(scenario, TWO_WEEKS, settings, PHYSICS, DC, rng)


# ------------------------------------------------------------------ inputs


def test_physics_from_section_8() -> None:
    assert PHYSICS.energy_mwh == pytest.approx(100.0)
    assert PHYSICS.eta == pytest.approx(0.88)
    assert PHYSICS.root_eta == pytest.approx(math.sqrt(0.88))


def test_dc_energy_matches_its_summary(tmp_path: Path) -> None:
    """The committed derived file is used only if its hash matches its summary."""
    fs = SETTINGS.frequency
    root = Path(__file__).resolve().parents[1]
    copy = tmp_path / fs.derived_file
    copy.parent.mkdir(parents=True)
    copy.write_text((root / fs.derived_file).read_text(encoding="utf-8") + "\n")
    (tmp_path / fs.summary_file).write_text(
        (root / fs.summary_file).read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(bt.SimulationError, match="does not match"):
        bt.load_dc_energy(SETTINGS, root=tmp_path)


def test_dc_window_outside_span_refused() -> None:
    with pytest.raises(bt.SimulationError, match="outside"):
        DC.window(datetime(2026, 5, 31, tzinfo=UTC), 48)


def test_run_rng_deterministic_and_distinct() -> None:
    def first(*key: int | str) -> float:
        name, length, index = key
        return float(bt.run_rng(1, str(name), int(length), int(index)).random())

    assert first("honest", 0, 0) == first("honest", 0, 0)
    values = {first("honest", 0, 0), first("honest", 1, 0), first("honest", 0, 1)}
    values.add(first("honest_frequency_response", 0, 0))
    assert len(values) == 4


def test_efa_blocks_across_the_clock_change() -> None:
    """24 Oct is BST: boundaries at 22, 02, 06, 10, 14, 18 UTC. From 01:00 UTC on
    25 Oct clocks are GMT: 03, 07, 11, 15, 19, 23 UTC."""
    start = datetime(2026, 10, 24, tzinfo=UTC)
    starts = bt.efa_block_starts(start, 96)
    hours = [
        (start + timedelta(minutes=30 * int(p))).hour for p in np.flatnonzero(starts)
    ]
    assert hours == [2, 6, 10, 14, 18, 22, 3, 7, 11, 15, 19, 23]


# ------------------------------------------------------------------ physics


def test_windows_reach_their_targets_exactly() -> None:
    """No instructions, no response: the first charge window (00:00–03:00) ends at
    85 MWh, the first discharge window (05:00–08:00) at 15 MWh."""
    sim = run(boa_mean_per_day=0.0)
    assert sim.stored_mwh[180] == pytest.approx(85.0, abs=1e-9)
    assert sim.stored_mwh[480] == pytest.approx(15.0, abs=1e-9)
    assert sim.curtailed_minutes == 0


def test_energy_balance_without_response() -> None:
    """Without response each minute flows one way, so stored energy follows the
    meter minute by minute: S_end − S_0 = Σ import·√η − Σ export/√η. Summed by
    period instead, it would not: an instruction can reverse the flow within a
    period, and netting hides that (ASSUMPTIONS P7)."""
    sim = run(meter_noise_sd_mwh=0.0)
    r = PHYSICS.root_eta
    q = bt.meter_mwh(bt._working(sim), 0, sim.minutes, with_dc=False)
    assert q.reshape(sim.periods, -1).sum(axis=1) == pytest.approx(sim.meter_net_mwh)
    expected = float(np.clip(-q, 0, None).sum() * r - np.clip(q, 0, None).sum() / r)
    assert sim.stored_mwh[-1] - sim.stored_mwh[0] == pytest.approx(expected, abs=1e-6)


def test_idle_response_flows_both_ways() -> None:
    """In a period with no PN and no instruction, the meter shows the net response
    c·(e − i), but storage pays both losses: −c·e/√η + c·i·√η (ASSUMPTIONS P7)."""
    sim = run(bt.HONEST_FR, meter_noise_sd_mwh=0.0, boa_mean_per_day=0.0)
    p = next(p for p in range(sim.periods) if not sim.pn_active[p] and p > 12)
    c, e, i = sim.dc_mw[p], sim.dc_export_mwh_per_mw[p], sim.dc_import_mwh_per_mw[p]
    r = PHYSICS.root_eta
    assert sim.meter_net_mwh[p] == pytest.approx(c * (e - i), abs=1e-9)
    change = sim.stored_mwh[(p + 1) * 30] - sim.stored_mwh[p * 30]
    assert change == pytest.approx(-c * e / r + c * i * r, abs=1e-9)
    assert e > 0 and i > 0  # the period really did flow both ways


def test_meter_noise_has_the_set_size() -> None:
    quiet = run(meter_noise_sd_mwh=0.0)
    noisy = run()
    noise = noisy.meter_net_mwh - quiet.meter_net_mwh
    assert np.std(noise) == pytest.approx(SETTINGS.meter_noise_sd_mwh, rel=0.15)


def test_power_limit_never_exceeded() -> None:
    """PN, instruction and contracted response stay within power_mw every minute."""
    for scenario in (bt.HONEST, bt.HONEST_FR, bt.HONEST_DC_EFA):
        sim = run(scenario)
        period = np.arange(sim.minutes) // 30
        used = np.abs(sim.pn_mw[period] + sim.boa_dev_mw) + sim.dc_mw[period]
        assert used.max() <= SETTINGS.battery.power_mw + 1e-9


def test_instructions_never_overlap_and_meet_the_floor() -> None:
    sim = run(bt.HONEST_DC_EFA)
    for a, b in zip(sim.boas, sim.boas[1:], strict=False):
        assert a.end_min <= b.accepted_min
    assert all(abs(b.deviation_mw) >= bt.MIN_BOA_MW for b in sim.boas)
    assert sim.boas and sim.boas_not_accepted >= 0


def test_curtail_hand_worked() -> None:
    """From 1 MWh: −0.6 → 0.4; −0.6 would reach −0.2, cut to 0; +0.5 → 0.5."""
    stored, actual, cut = bt.curtail(1.0, np.array([-0.6, -0.6, 0.5]), 100.0)
    assert stored == pytest.approx([1.0, 0.4, 0.0, 0.5])
    assert actual == pytest.approx([-0.6, -0.4, 0.5])
    assert cut.tolist() == [False, True, False]
    stored, _, cut = bt.curtail(99.0, np.array([2.0]), 100.0)
    assert stored[-1] == pytest.approx(100.0) and cut.tolist() == [True]


def test_same_seed_same_run() -> None:
    a, b = run(bt.HONEST_DC_EFA, seed=3), run(bt.HONEST_DC_EFA, seed=3)
    assert np.array_equal(a.stored_mwh, b.stored_mwh)
    assert np.array_equal(a.meter_net_mwh, b.meter_net_mwh)
    assert a.boas == b.boas
    assert not np.array_equal(a.stored_mwh, run(bt.HONEST_DC_EFA, seed=4).stored_mwh)


# ------------------------------------------------------------------ records


def test_record_times_follow_the_rule() -> None:
    """A routine record at every period start for 30 minutes; one `lag` minutes
    after each acceptance to the end of its period, unless that is a period start."""
    sim = run()
    times = dict(bt.record_times(sim, LAG))
    for p in range(sim.periods):
        assert times[30 * p] == 30 * (p + 1)
    for boa in sim.boas:
        publish = boa.accepted_min + LAG
        if publish % 30 and publish < sim.minutes:
            assert times[publish] == (publish // 30 + 1) * 30
    assert len(times) == sim.periods + sum(
        1 for b in sim.boas if (b.accepted_min + LAG) % 30
    )


def test_submissions_start_at_publication() -> None:
    """Every record starts at its publish time, so it changes no earlier minute."""
    u = bt.unit_inputs(run(), "A", LAG)
    assert all(s.time_from == s.publish_time for s in u.submissions)
    assert {s.dataset for s in u.submissions} == {"MDO", "MDB"}


def test_pn_has_a_level_for_every_period() -> None:
    sim = run()
    segs = bt.pn_segments(sim)
    assert len(segs) == sim.periods
    for a, b in zip(segs, segs[1:], strict=False):
        assert a.time_to == b.time_from
        assert (a.time_to - a.time_from) == timedelta(minutes=30)


def test_instruction_segments_are_absolute_levels() -> None:
    """BOALF gives absolute levels: PN plus the deviation, split at period starts."""
    sim = run()
    segs = bt.boa_segments(sim)
    boa = next(b for b in sim.boas if b.accepted_min // 30 != (b.end_min - 1) // 30)
    pieces = [s for s in segs if s.acceptance_number == boa.number]
    assert len(pieces) == (boa.end_min - 1) // 30 - boa.accepted_min // 30 + 1
    for s in pieces:
        p = int((s.time_from - sim.start) / timedelta(minutes=30))
        assert s.level_from_mw == pytest.approx(sim.pn_mw[p] + boa.deviation_mw)
        assert s.acceptance_time == sim.start + timedelta(minutes=boa.accepted_min)


def truth_mwh(sim: bt.Simulation, minute: int) -> float:
    """√η·S − contracted MW × 0.25 h, computed here, not by the battery (§3)."""
    period = min(minute, sim.minutes - 1) // 30
    held = float(sim.dc_mw[period]) * SETTINGS.response.delivery_duration_h
    return float(sim.stored_mwh[minute]) * PHYSICS.root_eta - held


def stale(sim: bt.Simulation, minute: int) -> bool:
    """An acceptance in (minute − lag, minute] is not yet in the record in force."""
    return any(minute - LAG < b.accepted_min <= minute for b in sim.boas)


@pytest.mark.parametrize("scenario", [bt.HONEST, bt.HONEST_FR, bt.HONEST_DC_EFA])
@pytest.mark.parametrize("branch", ["A", "B"])
def test_honest_declared_energy_is_the_truth(
    scenario: bt.Scenario, branch: Branch
) -> None:
    """At every period start of the scored week, D^decl computed by the scoring
    physics (§3, under the battery's own branch) equals √η·S − R, except where an
    acceptance is younger than the lag, and where MDO was floored at zero."""
    sim = run(scenario)
    unit = bt.unit_inputs(sim, branch, LAG)
    week = TWO_WEEKS.first_scored_week
    times = week_boundaries(week)[:-1]
    declared = declared_series(
        unit,
        times,
        PHYSICS.eta,
        branch,
        3,
        None,
        9999.0,
        TWO_WEEKS.end,
    )
    work = bt._working(sim)
    checked = 0
    for t, d in zip(times, declared, strict=True):
        minute = int((t - sim.start) / timedelta(minutes=1))
        if stale(sim, minute):
            continue
        truth = truth_mwh(sim, minute)
        assert d is not None
        prot = bt.protection(work, minute, minute - LAG, sim.minutes)
        if truth - prot.pn_export - prot.boa_export < 0:  # MDO floored at zero
            assert d >= truth
            continue
        assert d == pytest.approx(truth, abs=1e-6), t
        checked += 1
    assert checked > 300


def test_branch_b_declares_stored_energy() -> None:
    """Branch B's MDO is Branch A's divided by √η; its MDB is A's times √η."""
    sim = run()
    a = bt.submissions(sim, "A", LAG)
    b = bt.submissions(sim, "B", LAG)
    r = PHYSICS.root_eta
    for x, y in zip(a, b, strict=True):
        factor = 1 / r if x.dataset == "MDO" else r
        assert y.level_from_mwh == pytest.approx(x.level_from_mwh * factor)


def test_unit_inputs_carry_power_and_sf_meter() -> None:
    u = bt.unit_inputs(run(), "A", LAG)
    assert u.registered_mw == pytest.approx(SETTINGS.battery.power_mw)
    assert {m.run_type for m in u.meter} == {"SF"}
    assert len(u.meter) == 14 * 48


def test_lag_leaves_the_declaration_stale() -> None:
    """At a period start where an acceptance is younger than the lag, the record in
    force does not net the instruction yet, so D^decl exceeds the truth by the
    instruction's export energy within H, which the scoring adds back (§3, M21)."""
    found = 0
    for seed in range(20):
        sim = run(seed=seed)
        unit = bt.unit_inputs(sim, "A", LAG)
        work = bt._working(sim)
        for boa in sim.boas:
            if boa.accepted_min % 30 or boa.deviation_mw <= 0:
                continue
            t = sim.start + timedelta(minutes=boa.accepted_min)
            if t < TWO_WEEKS.first_scored_week:
                continue
            (d,) = declared_series(
                unit, [t], PHYSICS.eta, "A", 3, None, 9999.0, TWO_WEEKS.end
            )
            prot = bt.protection(work, boa.accepted_min, boa.accepted_min, sim.minutes)
            truth = truth_mwh(sim, boa.accepted_min)
            assert d is not None and d == pytest.approx(truth + prot.boa_export)
            found += 1
    assert found >= 1


# ------------------------------------------------------------------ planted faults

FAULTS = bt.load_faults()


def test_faults_from_section_8() -> None:
    assert (FAULTS.delta_mwh, FAULTS.f, FAULTS.under_mwh) == (10.0, 0.2, 20.0)
    assert (FAULTS.fast_lag_min, FAULTS.slow_lag_min) == (5, 25)
    assert (FAULTS.derate_to_fraction, FAULTS.derate_below_soc) == (0.5, 0.2)


@pytest.mark.parametrize(
    ("declare", "mdo", "expected"),
    [
        ("honest", 40.0, 40.0),
        ("offset", 40.0, 50.0),  # + 10 MWh
        ("proportional", 40.0, 50.0),  # 40 / (1 − 0.2): declares 1.25 × available
        ("under", 40.0, 20.0),  # − 20 MWh
        ("under", 15.0, 0.0),  # floored: MDO cannot be negative
    ],
)
def test_planted_declarations_hand_worked(
    declare: Any, mdo: float, expected: float
) -> None:
    got, _ = bt.planted(mdo, -30.0, declare, FAULTS, PHYSICS)
    assert got == pytest.approx(expected)


def test_static_profile_holds_the_given_peak() -> None:
    assert bt.planted(40.0, -30.0, "static", FAULTS, PHYSICS, (80.0, -90.0)) == (
        80.0,
        -90.0,
    )
    with pytest.raises(bt.SimulationError, match="own peak"):
        bt.planted(40.0, -30.0, "static", FAULTS, PHYSICS)


def test_static_battery_copies_its_own_maximum() -> None:
    """§8 "Static profile copied from maximum": every record holds the battery's
    own highest honest MDO (and deepest honest MDB), not the nameplate tank."""
    sim = run()
    honest = bt.submissions(sim, "A", LAG)
    static = bt.submissions(
        dataclasses.replace(sim, scenario=bt.STATIC_PROFILE), "A", LAG, FAULTS
    )

    def ends(dataset: str, records: list[Any]) -> list[float]:
        out: list[float] = []
        for x in records:
            if x.dataset == dataset:
                assert x.level_to_mwh is not None
                out += [x.level_from_mwh, x.level_to_mwh]
        return out

    top, deep = max(ends("MDO", honest)), min(ends("MDB", honest))
    assert set(ends("MDO", static)) == {top}
    assert set(ends("MDB", static)) == {deep}
    assert top < 100.0 * PHYSICS.root_eta  # below the full tank


def test_planted_fault_needs_section_8_figures() -> None:
    with pytest.raises(bt.SimulationError, match="needs"):
        bt.planted(40.0, -30.0, "offset", None, PHYSICS)


def test_offset_battery_declares_10_mwh_above_the_honest_one() -> None:
    """Same run, same records: only the MDO level moves, by exactly Δ."""
    sim = run()
    faulty = dataclasses.replace(sim, scenario=bt.OVER_CONSTANT)
    honest = bt.submissions(sim, "A", LAG)
    over = bt.submissions(faulty, "A", LAG, FAULTS)
    for h, o in zip(honest, over, strict=True):
        shift = 10.0 if h.dataset == "MDO" else 0.0
        assert o.level_from_mwh == pytest.approx(h.level_from_mwh + shift)
        assert o.time_from == h.time_from and o.publish_time == h.publish_time


def test_pn_ignored_leaves_pn_energy_in_mdo() -> None:
    """MDO rises by the PN export energy within H that an honest unit nets off."""
    sim = run()
    faulty = dataclasses.replace(sim, scenario=bt.PN_IGNORED)
    work = bt._working(sim)
    honest = bt.submissions(sim, "A", LAG)
    ignored = bt.submissions(faulty, "A", LAG, FAULTS)
    seen = 0
    for h, g in zip(honest, ignored, strict=True):
        if h.dataset != "MDO":
            continue
        minute = int((h.publish_time - sim.start) / timedelta(minutes=1))
        prot = bt.protection(work, minute, minute - LAG, sim.minutes)
        if h.level_from_mwh > 0:  # not floored
            assert g.level_from_mwh == pytest.approx(h.level_from_mwh + prot.pn_export)
            seen += prot.pn_export > 0
    assert seen > 50


def test_lags_and_record_times() -> None:
    assert bt.lag_minutes(bt.HONEST, SETTINGS, FAULTS) == 1
    assert bt.lag_minutes(bt.REDECLARE_FAST, SETTINGS, FAULTS) == 5
    assert bt.lag_minutes(bt.REDECLARE_SLOW, SETTINGS, FAULTS) == 25
    sim = run()
    times = dict(bt.record_times(sim, 25))
    for boa in sim.boas:
        publish = boa.accepted_min + 25
        if publish % 30 and publish < sim.minutes:
            assert publish in times


def test_contract_holders() -> None:
    assert not bt.HONEST.holds_contracts and not bt.OVER_PROPORTIONAL.holds_contracts
    assert bt.HONEST_FR.holds_contracts and bt.HONEST_DC_EFA.holds_contracts
    assert bt.OVER_PROPORTIONAL_RESERVE.holds_contracts


# ------------------------------------------------------------------ reserve


def test_reserve_levels_hand_worked() -> None:
    """Steps 5, 10, 20, −40, 3 within [0, 30]: 5, 15, 30 (capped), 0 (floored), 3."""
    out = bt.reserve_levels(np.array([5.0, 10.0, 20.0, -40.0, 3.0]), (0.0, 30.0))
    assert out.tolist() == [5.0, 15.0, 30.0, 0.0, 3.0]


def test_reserve_changes_about_one_period_in_ten() -> None:
    sim = run(bt.OVER_PROPORTIONAL_RESERVE)
    steps = np.diff(sim.reserve_mwh)
    share = np.count_nonzero(steps) / steps.size
    assert 0.06 < share < 0.12  # 0.10 drawn, fewer seen when clipped at a bound
    assert sim.reserve_mwh.min() >= 0.0 and sim.reserve_mwh.max() <= 30.0


def test_honest_reserve_holder_declares_net_of_reserve() -> None:
    """An honest battery holding reserve: D^decl = √η·S − reserve at period starts."""
    holder = bt.Scenario("test_reserve_holder", "none", reserve=True)
    sim = run(holder)
    unit = bt.unit_inputs(sim, "A", LAG)
    times = week_boundaries(TWO_WEEKS.first_scored_week)[:-1]
    declared = declared_series(
        unit, times, PHYSICS.eta, "A", 3, None, 9999.0, TWO_WEEKS.end
    )
    work = bt._working(sim)
    checked = 0
    for t, d in zip(times, declared, strict=True):
        minute = int((t - sim.start) / timedelta(minutes=1))
        if stale(sim, minute):
            continue
        p = minute // 30
        truth = float(sim.stored_mwh[minute]) * PHYSICS.root_eta - sim.reserve_mwh[p]
        prot = bt.protection(work, minute, minute - LAG, sim.minutes)
        if truth - prot.pn_export - prot.boa_export < 0:
            continue
        assert d == pytest.approx(truth, abs=1e-6)
        checked += 1
    assert checked > 250


def test_honest_batteries_draw_no_reserve() -> None:
    assert not run().reserve_mwh.any()


# ------------------------------------------------------------------ delivery limits


def test_ramp_hand_worked() -> None:
    """Requested 0, 20, 20, 20, 0 MW at 5 MW/min: delivered 0, 5, 10, 15, 10."""
    stored, metered, cut, limited = bt.deliver(
        50.0, np.array([0.0, 20.0, 20.0, 20.0, 0.0]), PHYSICS, 50.0, ramp_mw_per_min=5.0
    )
    assert (metered * 60).tolist() == pytest.approx([0.0, 5.0, 10.0, 15.0, 10.0])
    assert limited.tolist() == [False, True, True, True, True]
    assert not cut.any()
    assert stored[-1] == pytest.approx(50.0 - 40.0 / 60 / PHYSICS.root_eta)


def test_derating_hand_worked() -> None:
    """At 10 MWh (10% of U, half of 20%), export is capped at 50 × (0.5 + 0.5 × 0.5)
    = 37.5 MW; import is not limited."""
    _, metered, _, limited = bt.deliver(
        10.0, np.array([50.0]), PHYSICS, 50.0, derate=(0.5, 0.2)
    )
    assert metered[0] * 60 == pytest.approx(37.5)
    assert limited.tolist() == [True]
    _, metered, _, limited = bt.deliver(
        10.0, np.array([-50.0]), PHYSICS, 50.0, derate=(0.5, 0.2)
    )
    assert metered[0] * 60 == pytest.approx(-50.0) and not limited.any()


def test_delivery_stops_at_the_walls() -> None:
    stored, metered, cut, _ = bt.deliver(0.1, np.array([60.0]), PHYSICS, 50.0)
    assert stored[-1] == pytest.approx(0.0) and cut.tolist() == [True]
    assert metered[0] == pytest.approx(0.1 * PHYSICS.root_eta)


def test_limited_batteries_simulate_within_limits() -> None:
    for scenario in (bt.HONEST_RAMP, bt.HONEST_DERATE):
        sim = (
            run(scenario)
            if scenario.physics != "derate"
            else bt.simulate(
                scenario,
                TWO_WEEKS,
                SETTINGS,
                PHYSICS,
                DC,
                bt.run_rng(SETTINGS.master_seed, scenario.name, 0, 0),
                FAULTS,
            )
        )
        assert 0.0 <= sim.stored_mwh.min() and sim.stored_mwh.max() <= 100.0
        assert sim.limited_minutes > 0


def test_derating_needs_its_figures() -> None:
    with pytest.raises(bt.SimulationError, match="derating"):
        run(bt.HONEST_DERATE)


def test_limits_need_a_battery_without_response() -> None:
    bad = bt.Scenario("test_ramp_with_dc", "constant", physics="ramp")
    with pytest.raises(bt.SimulationError, match="hold no response"):
        run(bad)


@pytest.mark.parametrize("scenario", [bt.HONEST_RAMP, bt.HONEST_DERATE])
def test_limited_batteries_plan_with_their_own_limits(scenario: bt.Scenario) -> None:
    """Without instructions, each window still ends at its target under the
    battery's own limits: 85 MWh after the first charge (00:00–03:00) and 15 MWh
    after the first discharge (05:00–08:00), to within the ramp's tail."""
    quiet = dataclasses.replace(SETTINGS, boa_mean_per_day=0.0)
    sim = bt.simulate(
        scenario,
        TWO_WEEKS,
        quiet,
        PHYSICS,
        DC,
        bt.run_rng(SETTINGS.master_seed, scenario.name, 0, 0),
        FAULTS,
    )
    assert sim.stored_mwh[180] == pytest.approx(85.0, abs=0.5)
    assert sim.stored_mwh[480] == pytest.approx(15.0, abs=0.5)
    assert sim.curtailed_minutes == 0


def test_derating_battery_never_reaches_a_wall() -> None:
    """Planning under its own derating, it falls short only for want of power."""
    sim = bt.simulate(
        bt.HONEST_DERATE,
        TWO_WEEKS,
        SETTINGS,
        PHYSICS,
        DC,
        bt.run_rng(SETTINGS.master_seed, bt.HONEST_DERATE.name, 0, 0),
        FAULTS,
    )
    assert sim.curtailed_minutes == 0 and sim.limited_minutes > 0


def test_ramp_starts_from_the_power_already_delivered() -> None:
    """Already at 18 MW, a 20 MW request is within 5 MW/min: delivered in full.
    From rest it would be held to 5 MW."""
    _, metered, _, limited = bt.deliver(
        50.0, np.array([20.0]), PHYSICS, 50.0, ramp_mw_per_min=5.0, previous_mw=18.0
    )
    assert metered[0] * 60 == pytest.approx(20.0) and not limited.any()
    _, metered, _, _ = bt.deliver(
        50.0, np.array([20.0]), PHYSICS, 50.0, ramp_mw_per_min=5.0
    )
    assert metered[0] * 60 == pytest.approx(5.0)
