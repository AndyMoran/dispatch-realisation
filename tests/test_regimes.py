"""Claim 3's sizing regimes and band pass marks (PREREGISTRATION §8).

The regime tests simulate batteries and check how instructions were sized, capped
and delivered. None scores Claim 3 on a simulated battery: no D, ρ, fit or flag is
computed before the band runner is committed. The pass-mark tests use made-up
outcomes.
"""

from datetime import timedelta
from functools import cache

import numpy as np
import pytest

from src.claim3 import instructions as ins
from src.synthetic import battery as bt
from src.synthetic import claim3_bands as c3b
from src.synthetic import regimes as rg
from src.synthetic.settings import load_synthetic_settings

SETTINGS = load_synthetic_settings()
FAULTS = bt.load_faults()
PHYSICS = bt.load_physics()
SHORT = 0
LENGTH = SETTINGS.lengths[SHORT]
POWER = SETTINGS.battery.power_mw


@cache
def dc() -> bt.DcEnergy:
    return bt.load_dc_energy(SETTINGS)


@cache
def run(
    scenario: bt.Scenario, regime: rg.Regime, declarer: str | None = None
) -> rg.RegimeRun:
    seed = (SETTINGS.master_seed, scenario.name, SHORT, 0)
    return rg.simulate_regime(
        scenario,
        LENGTH,
        SETTINGS,
        PHYSICS,
        dc(),
        seed,
        FAULTS,
        regime,
        declarer,  # type: ignore[arg-type]
    )


@cache
def draws(scenario: bt.Scenario) -> bt.Draws:
    days = (LENGTH.end - LENGTH.adoption_week_start).days
    starts = bt.efa_block_starts(LENGTH.adoption_week_start, days * 48)
    blocks = int((np.cumsum(starts) - 1).max()) + 2
    rng = bt.run_rng(SETTINGS.master_seed, scenario.name, SHORT, 0)
    return bt.draw(SETTINGS, days, blocks, rng)


def share(r: rg.RegimeRun, scenario: bt.Scenario, boa: bt.Boa) -> float:
    k = r.draw_index[boa.number - 1]
    assert draws(scenario).boa_start_min[k] == boa.accepted_min
    return float(draws(scenario).boa_share[k])


def instructed_mwh(boa: bt.Boa, sim: bt.Simulation) -> float:
    """A: the integral of (BOALF − PN) over the instruction, as scoring reads it."""
    minutes = np.arange(boa.accepted_min, boa.end_min)
    pn = sim.pn_mw[minutes // bt.MINUTES_PER_PERIOD]
    level = boa.level_mw if boa.level_mw is not None else pn + boa.deviation_mw
    return float(np.sum(level - pn) / 60.0)


def delivered_mwh(boa: bt.Boa, sim: bt.Simulation) -> float:
    return float(sim.boa_dev_mw[boa.accepted_min : boa.end_min].sum() / 60.0)


# ------------------------------------------------------------------ delivery rule


def test_stop_at_budget_hand_worked() -> None:
    """30 MW for 10 minutes is 5 MWh; a 3.25 MWh budget gives six full minutes
    (3 MWh), a half minute, then nothing."""
    dev = np.full(10, 30.0)
    out = rg._stop_at_budget(dev, 3.25)
    assert out.tolist() == [30.0] * 6 + [15.0] + [0.0] * 3
    assert rg._stop_at_budget(dev, 5.0) is dev
    assert rg._stop_at_budget(-dev, 0.0).tolist() == [0.0] * 10


# ------------------------------------------------------------------ sizing by hand

Sized = tuple[np.ndarray, float | None, bool]


def ok(result: Sized | str) -> Sized:
    assert not isinstance(result, str), result
    return result


PN_IMPORT = np.array([-20.0] * 30 + [-10.0] * 30)  # an hour: two periods
NO_DC = np.zeros(60)


def test_size_mdo_hand_worked() -> None:
    """u 0.5 of a 30 MWh MDO over an hour: 15 MW; capped by 50 − |PN| − DC."""
    dev, level, capped = ok(
        rg.size("mdo", True, 0.5, 1.0, np.zeros(60), NO_DC, 50.0, 30.0)
    )
    assert dev.tolist() == [15.0] * 60 and level is None and not capped
    exporting = np.full(60, 30.0)
    dev, _, capped = ok(
        rg.size("mdo", True, 1.0, 1.0, exporting, np.full(60, 10.0), 50.0, 30.0)
    )
    assert dev.tolist() == [10.0] * 60 and capped  # 50 − 30 − 10
    assert (
        rg.size("mdo", True, 0.5, 1.0, np.zeros(60), NO_DC, 50.0, None) == "no_record"
    )
    assert (
        rg.size("mdo", False, 0.5, 1.0, np.zeros(60), NO_DC, 50.0, 1.0) == "below_1_mw"
    )


def test_size_pn_hand_worked() -> None:
    """Turn-down: u 0.5 of the smallest import, 10 MW, so 5 MW throughout; an
    export period anywhere in the span stops it."""
    dev, level, capped = ok(rg.size("pn", True, 0.5, 1.0, PN_IMPORT, NO_DC, 50.0))
    assert dev.tolist() == [5.0] * 60 and level is None and not capped
    mixed = PN_IMPORT.copy()
    mixed[-1] = 0.0
    assert rg.size("pn", True, 0.5, 1.0, mixed, NO_DC, 50.0) == "wrong_sign"
    assert rg.size("pn", False, 0.5, 1.0, PN_IMPORT, NO_DC, 50.0) == "wrong_sign"
    dev, _, _ = ok(rg.size("pn", False, 0.5, 1.0, -PN_IMPORT, NO_DC, 50.0))
    assert dev.tolist() == [-5.0] * 60


def test_size_mel_hand_worked() -> None:
    """MEL 50 less the largest contract (20 MW): BOALF at 30 MW, deviation 30 − PN
    per period; MIL for bids."""
    dc = np.array([0.0] * 30 + [20.0] * 30)
    dev, level, capped = ok(rg.size("mel", True, 0.3, 1.0, PN_IMPORT, dc, 50.0))
    assert level == 30.0 and not capped
    assert dev.tolist() == [50.0] * 30 + [40.0] * 30
    dev, level, _ = ok(rg.size("mel", False, 0.3, 1.0, PN_IMPORT, NO_DC, 50.0))
    assert level == -50.0 and dev.tolist() == [-30.0] * 30 + [-40.0] * 30


# ------------------------------------------------------------------ regime (i)


@pytest.mark.parametrize("declarer", ["A", "B"])
@pytest.mark.parametrize(
    "scenario",
    [
        bt.HONEST,
        bt.OVER_PROPORTIONAL,
        bt.STATIC_PROFILE,
        bt.REDECLARE_FAST,
        bt.HONEST_RAMP,
        bt.HONEST_DERATE,
    ],
)
def test_mdo_sizing_reads_what_scoring_reads(
    scenario: bt.Scenario, declarer: str
) -> None:
    """A = u × the MDO (|MDB|) the scoring code selects, published before the
    acceptance minute, unless the power cap binds; then A is smaller and the cap
    holds. This also checks that every record used for sizing is the record later
    reported: re-planned PN never reaches a published record's horizon."""
    r = run(scenario, "mdo", declarer)
    sim = r.sim
    lag = bt.lag_minutes(scenario, SETTINGS, FAULTS)
    unit = bt.unit_inputs(sim, declarer, lag, FAULTS, r.peak)  # type: ignore[arg-type]
    published = ins._published(unit.submissions)
    capped = 0
    for boa in sim.boas:
        side: ins.Side = "offer" if boa.deviation_mw > 0 else "bid"
        accepted = sim.start + timedelta(minutes=boa.accepted_min)
        seen = ins.declared_before(published, side, accepted, 9999.0, LENGTH.end)
        assert seen is not None
        a = instructed_mwh(boa, sim)
        u = share(r, scenario, boa)
        if abs(abs(a) - u * seen) > 1e-9:
            capped += 1
            assert abs(a) < u * seen
    assert capped == r.counts.capped
    assert r.counts.issued == len(sim.boas)


def test_mdo_acceptance_on_a_period_start_is_not_issued() -> None:
    r = run(bt.HONEST, "mdo", "A")
    d = draws(bt.HONEST)
    on_start = set(d.boa_start_min[d.boa_start_min % 30 == 0].tolist())
    assert not on_start & {b.accepted_min for b in r.sim.boas}
    assert r.counts.no_record > 0


def test_declarers_are_simulated_separately_under_mdo() -> None:
    """NESO reads a B-declarer's stored-energy figure as MWh at the meter, so its
    instructions are larger by 1/√η where neither is capped."""
    a, b = run(bt.HONEST, "mdo", "A").sim, run(bt.HONEST, "mdo", "B").sim
    first_a, first_b = a.boas[0], b.boas[0]
    assert first_a.accepted_min == first_b.accepted_min
    assert first_b.deviation_mw / first_a.deviation_mw == pytest.approx(
        1 / PHYSICS.root_eta
    )


def test_static_profile_peak_comes_from_its_honest_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    inner = rg._simulate

    def spy(scenario, *args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(scenario.declare)
        return inner(scenario, *args, **kwargs)

    monkeypatch.setattr(rg, "_simulate", spy)
    seed = (SETTINGS.master_seed, bt.STATIC_PROFILE.name, SHORT, 0)
    rg.simulate_regime(
        bt.STATIC_PROFILE, LENGTH, SETTINGS, PHYSICS, dc(), seed, FAULTS, "mdo", "A"
    )
    assert seen == ["honest", "static"]
    monkeypatch.undo()
    r = run(bt.STATIC_PROFILE, "mdo", "A")
    assert r.peak is not None
    lag = bt.lag_minutes(bt.STATIC_PROFILE, SETTINGS, FAULTS)
    first_pass = rg._simulate(
        bt.Scenario(bt.STATIC_PROFILE.name, "none"),
        LENGTH,
        SETTINGS,
        PHYSICS,
        dc(),
        (SETTINGS.master_seed, bt.STATIC_PROFILE.name, SHORT, 0),
        FAULTS,
        "mdo",
        "A",
    )[0]
    assert r.peak == rg.peak_of(first_pass, lag)
    assert r.peak[0] > 0


# ------------------------------------------------------------------ (ii) and (iii)


def test_mel_level_is_mel_less_response() -> None:
    for scenario in (bt.HONEST, bt.HONEST_FR):
        sim = run(scenario, "mel").sim
        for boa in sim.boas:
            held = sim.dc_mw[boa.accepted_min // 30 : -(-boa.end_min // 30)].max()
            assert boa.level_mw is not None
            assert abs(boa.level_mw) == pytest.approx(POWER - held)


def test_pn_regime_turns_down_scheduled_flow_only() -> None:
    sim = run(bt.HONEST, "pn").sim
    r = run(bt.HONEST, "pn")
    assert r.counts.wrong_sign > 0 and sim.boas
    for boa in sim.boas:
        pn = sim.pn_mw[np.arange(boa.accepted_min, boa.end_min) // 30]
        assert (np.sign(pn) == -np.sign(boa.deviation_mw)).all()
        u = share(r, bt.HONEST, boa)
        assert abs(boa.deviation_mw) == pytest.approx(u * np.abs(pn).min())


@pytest.mark.parametrize("regime", ["mdo", "pn"])
def test_power_cap(regime: rg.Regime) -> None:
    """|PN + instruction| + contracted response ≤ power_mw throughout."""
    declarer = "A" if regime == "mdo" else None
    sim = run(bt.HONEST_FR, regime, declarer).sim
    for boa in sim.boas:
        p = np.arange(boa.accepted_min, boa.end_min) // 30
        total = np.abs(sim.pn_mw[p] + boa.deviation_mw) + sim.dc_mw[p]
        assert total.max() <= POWER + 1e-9


# ------------------------------------------------------------------ all regimes


@pytest.mark.parametrize("regime", ["mdo", "mel", "pn"])
def test_same_draws_and_no_overlap(regime: rg.Regime) -> None:
    declarer = "A" if regime == "mdo" else None
    r = run(bt.HONEST, regime, declarer)
    sim = r.sim
    d = draws(bt.HONEST)
    assert list(r.draw_index) == sorted(r.draw_index)
    for boa in sim.boas:
        k = r.draw_index[boa.number - 1]
        assert boa.accepted_min == d.boa_start_min[k]
        assert boa.end_min - boa.accepted_min == d.boa_duration_min[k]
        assert (boa.deviation_mw > 0) == bool(d.boa_is_offer[k])
    spans = sorted((b.accepted_min, b.end_min) for b in sim.boas)
    assert all(a1 <= b0 for (_, a1), (b0, _) in zip(spans, spans[1:], strict=False))


@pytest.mark.parametrize("regime", ["mdo", "mel"])
def test_delivery_stops_at_the_honest_budget(regime: rg.Regime) -> None:
    """The planted over-declarer delivers its honest MDO, never more, and every
    instruction within that budget in full."""
    declarer = "A" if regime == "mdo" else None
    r = run(bt.OVER_PROPORTIONAL, regime, declarer)
    stopped = 0
    for boa in r.sim.boas:
        a, got = instructed_mwh(boa, r.sim), delivered_mwh(boa, r.sim)
        assert abs(got) <= abs(a) + 1e-9
        stopped += abs(got) < abs(a) - 1e-9
    assert stopped == r.counts.stopped_short > 0


def test_proportional_fault_stops_short_only_above_u_of_0_8() -> None:
    """Declared = honest/(1 − f), honest = budget: an uncapped offer with share u
    falls short exactly when u > 1 − f."""
    r = run(bt.OVER_PROPORTIONAL, "mdo", "A")
    lag = bt.lag_minutes(bt.OVER_PROPORTIONAL, SETTINGS, FAULTS)
    unit = bt.unit_inputs(r.sim, "A", lag, FAULTS)
    published = ins._published(unit.submissions)
    checked = 0
    for boa in r.sim.boas:
        if boa.deviation_mw <= 0:
            continue
        accepted = r.sim.start + timedelta(minutes=boa.accepted_min)
        seen = ins.declared_before(published, "offer", accepted, 9999.0, LENGTH.end)
        u = share(r, bt.OVER_PROPORTIONAL, boa)
        assert seen is not None
        if abs(instructed_mwh(boa, r.sim) - u * seen) > 1e-9:
            continue  # capped
        short = delivered_mwh(boa, r.sim) < instructed_mwh(boa, r.sim) - 1e-9
        assert short == (u > 1 - FAULTS.f + 1e-9)
        checked += 1
    assert checked > 10


def test_replanning_is_counted_and_reduces_curtailment() -> None:
    """Re-deciding PN beyond H after an instruction keeps decided windows from
    running into the walls as often."""
    seed = (SETTINGS.master_seed, bt.HONEST.name, SHORT, 0)
    with_replan = run(bt.HONEST, "mdo", "A")
    assert with_replan.counts.replanned > 0
    without = rg._simulate(
        bt.HONEST,
        LENGTH,
        SETTINGS,
        PHYSICS,
        dc(),
        seed,
        FAULTS,
        "mdo",
        "A",
        replan=False,
    )
    assert without[1].replanned == 0
    assert with_replan.sim.curtailed_minutes < without[0].curtailed_minutes


def test_regime_needs_matching_declarer() -> None:
    with pytest.raises(ValueError):
        run(bt.HONEST, "mdo")
    with pytest.raises(ValueError):
        run(bt.HONEST, "mel", "A")


def test_claims12_batteries_unchanged() -> None:
    """Instructions with no absolute level report PN + deviation, as before."""
    boa = bt.Boa(1, 0, 30, 5.0)
    assert boa.level_mw is None


# ------------------------------------------------------------------ pass marks


def scored(
    flagged: bool = False,
    identified: bool = True,
    f_hat: float | None = 0.0,
    delta_hat: float | None = 0.0,
    r_over_1: int = 0,
    unscored: str | None = None,
) -> c3b.Scored:
    return c3b.Scored(
        unscored, 30, r_over_1, 20, identified, flagged, f_hat, delta_hat, 5, {}
    )


def declarer(a: c3b.Scored, b: c3b.Scored | None = None) -> c3b.Declarer:
    return c3b.Declarer(a, b or a, {"issued": 1}, 0, 0)


def test_required_runs() -> None:
    honest = c3b.Rule("not flagged", "honest")
    assert c3b.required(honest, 100) == 95
    assert (
        c3b.required(c3b.Rule("flagged with estimate", "overdeclarer", "f"), 100) == 80
    )
    assert c3b.required(c3b.Rule("not flagged", "min_share"), 100) == 95
    assert c3b.required(c3b.REPORT, 100) is None


def test_flag_needs_both_branches() -> None:
    rule = c3b.Rule("not flagged", "honest")
    one = declarer(scored(flagged=True), scored(flagged=False))
    assert not one.flagged and c3b.in_band(rule, one, "A")
    both = declarer(scored(flagged=True))
    assert both.flagged and not c3b.in_band(rule, both, "A")


def test_unscored_is_a_miss() -> None:
    rule = c3b.Rule("not flagged", "honest")
    assert not c3b.in_band(rule, declarer(scored(unscored="η̂ undefined")), "A")


def test_estimate_band_uses_matched_scoring() -> None:
    """The B-declarer's f̂ comes from its Branch B scoring."""
    rule = c3b.Rule("flagged with estimate", "overdeclarer", "f")
    d = declarer(scored(flagged=True, f_hat=0.14), scored(flagged=True, f_hat=0.2))
    assert c3b.in_band(rule, d, "B") and not c3b.in_band(rule, d, "A")
    delta = c3b.Rule("flagged with estimate", "overdeclarer", "delta")
    assert c3b.in_band(delta, declarer(scored(flagged=True, delta_hat=7.0)), "A")
    assert not c3b.in_band(delta, declarer(scored(flagged=True, delta_hat=13.1)), "A")
    assert not c3b.in_band(rule, declarer(scored(flagged=False, f_hat=0.2)), "A")


def test_flagged_or_not_identified() -> None:
    rule = c3b.Rule("flagged or not identified", "min_share")
    assert c3b.in_band(rule, declarer(scored(flagged=True)), "A")
    assert c3b.in_band(rule, declarer(scored(), scored(identified=False)), "A")
    assert not c3b.in_band(rule, declarer(scored()), "A")


def test_fast_redeclarer_needs_no_r_over_1() -> None:
    rule = c3b.Rule("not flagged", "min_share", no_r_over_1=True)
    assert c3b.in_band(rule, declarer(scored()), "A")
    assert not c3b.in_band(rule, declarer(scored(r_over_1=1)), "A")
    # only Branch A scoring counts, for either declarer: B-scored r = u/√η̂
    assert c3b.in_band(rule, declarer(scored(), scored(r_over_1=2)), "A")
    assert c3b.in_band(rule, declarer(scored(), scored(r_over_1=2)), "B")
    assert not c3b.in_band(rule, declarer(scored(r_over_1=1), scored()), "B")


def test_report_cells_have_no_band() -> None:
    with pytest.raises(ValueError):
        c3b.in_band(c3b.REPORT, declarer(scored()), "A")


def test_summary_verdicts() -> None:
    """One honest cell short by one run fails its length and the build."""
    regimes = list(rg.REGIMES)

    def outcome(flag: bool) -> dict[str, dict[str, c3b.Declarer]]:
        """Flagged under regime (i) only: the other cells always pass."""
        d = declarer(scored(flagged=flag))
        clean = declarer(scored())
        return {r: {"A": d if r == "mdo" else clean, "B": clean} for r in regimes}

    good = [outcome(False)] * 95 + [outcome(True)] * 5
    bad = [outcome(False)] * 94 + [outcome(True)] * 6
    s = c3b.summarise({(0, 0): good, (0, 1): bad}, 100)
    by_length = {v["length"]: v["bands_met"] for v in s["lengths"]}  # type: ignore[attr-defined]
    assert by_length == {"short": True, "long": False}
    assert s["claim3_bands_met"] is False
    cell = s["cells"][0]  # type: ignore[index]
    assert cell["required"] == 95 and cell["in_band"] == 95 and cell["passed"]


def test_bands_follow_section_8() -> None:
    names = [b.scenario.name for b in c3b.BANDS]
    assert len(names) == 11 and len(set(names)) == 11
    honest = {b.scenario.name for b in c3b.BANDS if b.regime_i.share == "honest"}
    assert honest == {
        bt.HONEST.name,
        bt.HONEST_FR.name,
        bt.HONEST_RAMP.name,
        bt.HONEST_DERATE.name,
    }
    assert all(
        b.regimes_ii_iii.kind == "report"
        for b in c3b.BANDS
        if b.regime_i.kind in ("flagged with estimate", "flagged or not identified")
    )


def test_run_once_plumbing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every regime and declarer is simulated and scored under both branches; the
    scoring is replaced by a stub, so no Claim 3 result is computed."""
    from src.claim3.unit import Claim3Result

    calls: list[tuple[str, str]] = []

    def stub(unit, start, end, settings, branch):  # type: ignore[no-untyped-def]
        calls.append((unit.unit_key, branch))
        return Claim3Result(branch, 0.88, None, (), None, None)

    monkeypatch.setattr(c3b, "score_claim3", stub)
    out = c3b.run_once(0, SHORT, 0)
    assert set(out) == set(rg.REGIMES)
    assert all(set(v) == {"A", "B"} for v in out.values())
    assert len(calls) == 12
    assert {b for _, b in calls} == {"A", "B"}
    d = out["mdo"]["A"]
    assert d.counts["issued"] == run(bt.HONEST, "mdo", "A").counts.issued
    assert not d.flagged and d.a.fitted == 0


def test_delivery_limit_is_the_true_state_not_the_declaration() -> None:
    """Each stopped instruction delivers exactly the honest MDO (|MDB|) of the
    battery's true state at acceptance, computed before the instruction, for
    batteries whose declarations are faulty in different ways."""
    for scenario in (bt.OVER_PROPORTIONAL, bt.STATIC_PROFILE, bt.PN_IGNORED):
        r = run(scenario, "mdo", "A")
        sim, a = r.sim, bt._working(r.sim)
        checked = 0
        for boa in sim.boas:
            got, wanted = delivered_mwh(boa, sim), instructed_mwh(boa, sim)
            if abs(got) >= abs(wanted) - 1e-9:
                continue
            m = boa.accepted_min
            prot = bt.protection(a, m, m - 1, sim.minutes)
            mdo, mdb = bt.mdo_mdb_a(
                float(sim.stored_mwh[m]), prot, bt.reserved_mwh(sim, m), PHYSICS
            )
            assert abs(got) == pytest.approx(mdo if boa.deviation_mw > 0 else -mdb)
            checked += 1
        assert checked > 0, scenario.name


@pytest.mark.parametrize("declarer", ["A", "B"])
def test_r_under_each_scoring_branch(declarer: str) -> None:
    """Under (i), A-scored r = A ÷ MDO = u ≤ 1 for both declarers. B-scored r is
    u/√η̂ for offers (A ÷ (√η̂ × MDO)) and u × √η̂ for bids (A ÷ (|MDB| ÷ √η̂)),
    so B-scored offers exceed 1 whenever u > √η̂. Computed with η̂ = η; no ρ."""
    r = run(bt.REDECLARE_FAST, "mdo", declarer)
    lag = bt.lag_minutes(bt.REDECLARE_FAST, SETTINGS, FAULTS)
    unit = bt.unit_inputs(r.sim, declarer, lag, FAULTS)  # type: ignore[arg-type]
    published = ins._published(unit.submissions)
    over_b = 0
    for boa in r.sim.boas:
        side: ins.Side = "offer" if boa.deviation_mw > 0 else "bid"
        accepted = r.sim.start + timedelta(minutes=boa.accepted_min)
        seen = ins.declared_before(published, side, accepted, 9999.0, LENGTH.end)
        assert seen is not None
        r_a = abs(instructed_mwh(boa, r.sim)) / seen
        root = PHYSICS.root_eta
        r_b = r_a / root if side == "offer" else r_a * root
        assert r_a <= 1 + 1e-12
        over_b += r_b > 1
    assert over_b > 0  # offers with u > √η, for either declarer
