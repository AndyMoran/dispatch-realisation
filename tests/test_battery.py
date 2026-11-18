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
