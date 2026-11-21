"""Claim 3's three instruction-sizing regimes (PREREGISTRATION §8).

§8: "Claim 3 runs under three instruction-sizing regimes: (i) sized to MDO; (ii)
sized to MEL × duration; (iii) sized to PN deviation only." Readings fixed before
any code (PROJECT.md §11, 21 Nov 2026), with the choices this module adds:

- **Same draws.** Each regime runs from the run's own generator, so every regime
  sees the same instruction times, durations, sides and shares u in [0.2, 1].
  The Claims 1–2 batteries (`battery.simulate`) keep their own sizing untouched.
- **(i) "mdo":** u × the MDO (offers) or |MDB| (bids) NESO could see: the record
  the scoring code selects, published strictly before the acceptance minute (M9).
  NESO reads the number as MWh at the meter, whatever the declarer meant, so the
  A-declarer and B-declarer are simulated separately. An acceptance with no record
  covering it is not issued, and counted.
- **(ii) "mel":** offers go to BOALF level +(MEL − c), bids to −(MIL − c), where
  MEL = MIL = power_mw and c is the largest contracted response MW over the span,
  so |BOALF| + response = power_mw in both directions. The deviation is that
  level minus PN in each period; A = ∫(level − PN). u is not used.
- **(iii) "pn":** turn-down of PN-scheduled flow: an offer only while PN imports in
  every period spanned, a bid only while it exports; u × the smallest |PN| over
  the span. Otherwise not issued, and counted.
- **Power cap**, (i) and (iii): |PN + instruction| + contracted response ≤
  power_mw over the span; a capped instruction is counted.
- **Delivery** (§5: delivered = min(accepted, E_available)): E_available is the
  energy the underlying battery really has at acceptance, net of §3's protection
  over H: its honest MDO at the meter (|MDB| for bids), from its true stored
  energy, PN, known instructions and contracts. A planted fault changes only the
  declaration, never the battery's physical state or this limit. The battery
  follows the instruction until that budget is spent, then stops; BOALF still
  shows the whole instruction. Walls, ramp limits and derating act on top, as
  in `battery`.
- **Static profile** under (i): sizing depends on the declaration, so its peak
  comes from the same battery's honest run under (i) with the same draws, and
  is independent of the faulted declaration.
- **PN after an instruction.** Sizing from MDO protects PN only within H, so an
  instruction can leave a window decided earlier unreachable. After each
  instruction, the PN of every decided window that no published record can see
  (starting at or after the end of H measured from the end of the current period)
  is re-decided from the state then, as a real unit would renominate before gate
  closure. PN inside any record's horizon never changes, so every record reported
  is the record NESO saw. Remaining wall contacts are counted, as in `battery`.

Instructions that overlap an active one, or fall below 1 MW, are refused as in
`battery`. Stored energy is tracked minute by minute, with walls, as events are
applied, so each record is computed from the state at its publish time.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from src.model.types import Dataset, Submission
from src.physics.declared import Branch, declared_at
from src.synthetic import battery as bt
from src.synthetic.settings import RunLength, SyntheticSettings

Regime = Literal["mdo", "mel", "pn"]
REGIMES: tuple[Regime, Regime, Regime] = ("mdo", "mel", "pn")
REGIME_NAMES = {"mdo": "(i) sized to MDO", "mel": "(ii) MEL", "pn": "(iii) PN"}
# Far above any synthetic level: no synthetic record is ever a ±9999 default.
NO_DEFAULT_MWH = 1.0e9


@dataclass(frozen=True)
class Counts:
    """How a run's instruction draws were treated."""

    issued: int = 0
    overlapping: int = 0
    below_1_mw: int = 0
    no_record: int = 0
    wrong_sign: int = 0
    capped: int = 0
    stopped_short: int = 0
    replanned: int = 0


@dataclass(frozen=True)
class RegimeRun:
    """One run of one battery under one regime (and, under (i), one declarer)."""

    sim: bt.Simulation
    regime: Regime
    declarer: Branch | None
    counts: Counts
    peak: tuple[float, float] | None
    draw_index: tuple[int, ...]


def peak_of(sim: bt.Simulation, lag_min: int) -> tuple[float, float]:
    """Return the highest honest MDO and deepest honest MDB of a run (meter, A)."""
    a = bt._working(sim)
    levels = [
        bt.declared_levels(sim, a, publish, end, lag_min)
        for publish, end in bt.record_times(sim, lag_min)
    ]
    return max(max(mdo) for mdo, _ in levels), min(min(mdb) for _, mdb in levels)


def simulate_regime(
    scenario: bt.Scenario,
    length: RunLength,
    settings: SyntheticSettings,
    physics: bt.Physics,
    dc: bt.DcEnergy,
    rng_seed: tuple[int, str, int, int],
    faults: bt.Faults,
    regime: Regime,
    declarer: Branch | None = None,
) -> RegimeRun:
    """Return one run under `regime`; under (i), as declared under `declarer`.

    `rng_seed` is (master seed, battery name, length index, run index): each pass
    draws afresh from it, so passes and regimes share every draw.
    """
    if (regime == "mdo") != (declarer is not None):
        raise ValueError("regime (i) needs a declarer; (ii) and (iii) take none")
    lag = bt.lag_minutes(scenario, settings, faults)
    peak: tuple[float, float] | None = None
    if regime == "mdo" and scenario.declare == "static":
        honest = replace(scenario, declare="honest")
        first = _simulate(
            honest, length, settings, physics, dc, rng_seed, faults, regime, declarer
        )
        peak = peak_of(first[0], lag)
    sim, counts, issued = _simulate(
        scenario,
        length,
        settings,
        physics,
        dc,
        rng_seed,
        faults,
        regime,
        declarer,
        peak,
    )
    return RegimeRun(sim, regime, declarer, counts, peak, issued)


def _simulate(
    scenario: bt.Scenario,
    length: RunLength,
    settings: SyntheticSettings,
    physics: bt.Physics,
    dc: bt.DcEnergy,
    rng_seed: tuple[int, str, int, int],
    faults: bt.Faults,
    regime: Regime,
    declarer: Branch | None,
    peak: tuple[float, float] | None = None,
    replan: bool = True,
) -> tuple[bt.Simulation, Counts, tuple[int, ...]]:
    limits = bt.limits_for(scenario, settings, faults)
    start = length.adoption_week_start
    days = (length.end - start).days
    minutes = days * bt.MINUTES_PER_DAY
    periods = minutes // bt.MINUTES_PER_PERIOD
    block_start = bt.efa_block_starts(start, periods)
    block_index = np.cumsum(block_start) - 1
    blocks = int(block_index.max()) + 2
    d = bt.draw(settings, days, blocks, bt.run_rng(*rng_seed))
    dc_exp, dc_imp = dc.window(start, periods)
    levels = np.asarray(settings.response.contract_levels_mw)
    if scenario.dc == "none":
        dc_mw = np.zeros(periods)
    elif scenario.dc == "constant":
        dc_mw = np.full(periods, float(levels.max()))
    else:
        dc_mw = d.dc_levels_mw[block_index + 1].astype(float)
    reserve = (
        bt.reserve_levels(d.reserve_step_mwh, settings.reserve_range_mwh)
        if scenario.reserve
        else np.zeros(periods)
    )
    a = bt._Arrays(
        pn_mw=np.zeros(periods),
        pn_active=np.zeros(periods, dtype=bool),
        boa_id=np.full(minutes, -1, dtype=np.int64),
        boa_dev=np.zeros(minutes),
        boa_acc=np.full(minutes, -1, dtype=np.int64),
        boas=[],
        dc_mw=dc_mw,
        dc_exp=dc_exp,
        dc_imp=dc_imp,
        reserve=reserve,
    )
    stored = np.full(minutes + 1, np.nan)
    stored[0] = d.initial_share * physics.energy_mwh
    view = bt.Simulation(
        scenario=scenario,
        start=start,
        minutes=minutes,
        physics=physics,
        power_mw=settings.battery.power_mw,
        delivery_duration_h=settings.response.delivery_duration_h,
        pn_mw=a.pn_mw,
        pn_active=a.pn_active,
        dc_mw=dc_mw,
        dc_export_mwh_per_mw=dc_exp,
        dc_import_mwh_per_mw=dc_imp,
        boas=(),
        boa_id=a.boa_id,
        boa_dev_mw=a.boa_dev,
        boa_accepted_min=a.boa_acc,
        stored_mwh=stored,
        meter_net_mwh=np.zeros(periods),
        boas_not_accepted=0,
        curtailed_minutes=0,
        reserve_mwh=reserve,
        limited_minutes=0,
    )
    ctx = _Context(
        a, d, view, stored, settings, physics, limits, faults, regime, declarer, peak
    )
    ctx.replan = replan
    counts = ctx.run()
    sim = _finish(view, a, stored, d, physics, limits, counts)
    return sim, counts, tuple(ctx.issued_draws)


@dataclass
class _Context:
    a: bt._Arrays
    d: bt.Draws
    view: bt.Simulation
    stored: NDArray[np.float64]
    settings: SyntheticSettings
    physics: bt.Physics
    limits: bt.Limits | None
    faults: bt.Faults
    regime: Regime
    declarer: Branch | None
    peak: tuple[float, float] | None
    known: int = 0
    previous_mw: float = 0.0
    counts: dict[str, int] = field(default_factory=dict)
    replan: bool = True
    issued_draws: list[int] = field(default_factory=list)

    def run(self) -> Counts:
        """Apply PN decisions and instruction draws in time order."""
        minutes = self.view.minutes
        windows = bt._windows(self.settings, minutes // bt.MINUTES_PER_DAY)
        events = [(dec, 0, i) for i, (dec, _, _) in enumerate(windows)]
        events += [(int(m), 1, i) for i, m in enumerate(self.d.boa_start_min)]
        events.sort()
        for minute, kind, i in events:
            self.advance(minute)
            if kind == 0:
                self.decide(windows[i])
            elif self.offer_instruction(i, minute) and self.replan:
                self.replan_after(minute, windows)
        return Counts(**self.counts)

    def replan_after(self, minute: int, windows: list[tuple[int, int, str]]) -> None:
        """Re-decide the PN of every decided window no record published so far can
        see, from the state now. A record ends at the end of its period, and its
        end level protects PN to the end of H from there."""
        period_end = (minute // bt.MINUTES_PER_PERIOD + 1) * bt.MINUTES_PER_PERIOD
        beyond = bt.horizon_stop(period_end)
        for decided, start, kind in windows:
            if decided <= minute and start >= beyond:
                self.decide((minute, start, kind))
                self.count("replanned")

    def count(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def advance(self, minute: int) -> None:
        """Fill stored energy up to `minute`, with walls and the battery's limits."""
        lo, hi = self.known, minute
        if hi <= lo:
            return
        a, s, p = self.a, self.stored, self.physics
        if self.limits is None:
            change = bt.stored_change(a, lo, hi, p.root_eta, with_dc=True)
            s[lo : hi + 1] = bt.curtail(float(s[lo]), change, p.energy_mwh)[0]
        else:
            requested = bt.meter_mwh(a, lo, hi, with_dc=False) * 60.0
            levels, metered, _, _ = bt.deliver(
                float(s[lo]),
                requested,
                p,
                self.limits.power_mw,
                self.limits.ramp_mw_per_min,
                self.limits.derate,
                self.previous_mw,
            )
            s[lo : hi + 1] = levels
            self.previous_mw = float(metered[-1]) * 60.0
        self.known = hi

    def decide(self, window: tuple[int, int, str]) -> None:
        now = float(self.stored[self.known])
        minutes = self.view.minutes
        if self.limits is None:
            bt._decide_pn(self.a, window, now, self.settings, self.physics, minutes)
        else:
            bt._plan_pn(
                self.a,
                window,
                now,
                self.previous_mw,
                self.settings,
                self.physics,
                minutes,
                self.limits,
            )

    def published(self, minute: int, offer: bool) -> float | None:
        """Return the MDO (or |MDB|) NESO could see at `minute`: the latest record
        covering it published strictly before it (M9), in the declarer's units."""
        assert self.declarer is not None
        scenario = self.view.scenario
        lag = bt.lag_minutes(scenario, self.settings, self.faults)
        period_start = minute // bt.MINUTES_PER_PERIOD * bt.MINUTES_PER_PERIOD
        if period_start == minute:
            return None  # every record covering this minute starts at it
        end = period_start + bt.MINUTES_PER_PERIOD
        publish = max(
            [period_start]
            + [
                b.accepted_min + lag
                for b in self.a.boas
                if period_start < b.accepted_min + lag < minute
            ]
        )
        record = _record(
            self.view, self.a, publish, end, lag, self.faults, self.peak, self.declarer
        )
        dataset: Dataset = "MDO" if offer else "MDB"
        t = self.view.start + timedelta(minutes=minute)
        data_end = self.view.start + timedelta(minutes=end)
        (value,) = declared_at(record, dataset, [t], NO_DEFAULT_MWH, data_end)
        assert value is not None
        return abs(value)

    def offer_instruction(self, i: int, minute: int) -> bool:
        """Size, cap and accept instruction draw i; return whether it was issued."""
        a, d, settings = self.a, self.d, self.settings
        minutes = self.view.minutes
        stop = minute + int(d.boa_duration_min[i])
        if stop > minutes or (a.boa_id[minute:stop] >= 0).any():
            self.count("overlapping")
            return False
        offer = bool(d.boa_is_offer[i])
        span = np.arange(minute, stop) // bt.MINUTES_PER_PERIOD
        published = self.published(minute, offer) if self.regime == "mdo" else None
        if self.regime == "mdo" and published is None:
            self.count("no_record")
            return False
        sized = size(
            self.regime,
            offer,
            float(d.boa_share[i]),
            (stop - minute) / 60.0,
            a.pn_mw[span],
            a.dc_mw[span],
            settings.battery.power_mw,
            published,
        )
        if isinstance(sized, str):
            self.count(sized)
            return False
        dev, level_mw, capped = sized
        if capped:
            self.count("capped")
        budget = self.budget(minute, offer)
        delivered = _stop_at_budget(dev, budget)
        if not np.array_equal(delivered, dev):
            self.count("stopped_short")
        self.count("issued")
        number = len(a.boas) + 1
        a.boas.append(bt.Boa(number, minute, stop, float(dev[0]), level_mw))
        a.boa_id[minute:stop] = number - 1
        a.boa_dev[minute:stop] = delivered
        a.boa_acc[minute:stop] = minute
        self.issued_draws.append(i)
        return True

    def budget(self, minute: int, offer: bool) -> float:
        """Return E_available: the honest MDO (|MDB|) of the battery's true state at
        acceptance, before this instruction; the planted fault plays no part."""
        prot = bt.protection(self.a, minute, minute, self.view.minutes)
        reserved = bt.reserved_mwh(self.view, minute)
        mdo, mdb = bt.mdo_mdb_a(
            float(self.stored[minute]), prot, reserved, self.physics
        )
        return mdo if offer else -mdb


def size(
    regime: Regime,
    offer: bool,
    u: float,
    hours: float,
    pn_mw: NDArray[np.float64],
    dc_mw: NDArray[np.float64],
    power_mw: float,
    published_mwh: float | None = None,
) -> tuple[NDArray[np.float64], float | None, bool] | str:
    """Return (deviation per minute, absolute BOALF level or None, capped), or the
    reason the instruction is not issued. `pn_mw` and `dc_mw` hold each minute's
    period values over the instruction's span (module docstring)."""
    sign = 1.0 if offer else -1.0
    level_mw: float | None = None
    if regime == "mdo":
        if published_mwh is None:
            return "no_record"
        dev = np.full(pn_mw.size, sign * u * published_mwh / hours)
    elif regime == "pn":
        opposite = (pn_mw < 0).all() if offer else (pn_mw > 0).all()
        if not opposite:
            return "wrong_sign"
        dev = np.full(pn_mw.size, sign * u * float(np.abs(pn_mw).min()))
    else:
        level_mw = sign * (power_mw - float(dc_mw.max()))
        dev = level_mw - pn_mw
    capped = False
    if regime != "mel":
        headroom = float((power_mw - sign * pn_mw - dc_mw).min())
        if abs(float(dev[0])) > headroom:
            dev = np.full(pn_mw.size, sign * headroom)
            capped = True
    if (sign * dev).min() < bt.MIN_BOA_MW:
        return "below_1_mw"
    return dev, level_mw, capped


def _stop_at_budget(dev: NDArray[np.float64], budget: float) -> NDArray[np.float64]:
    """Return the deviation delivered per minute: in full until `budget` MWh is
    spent, then the remainder of that minute, then nothing."""
    energy = np.abs(dev) / 60.0
    spent = np.cumsum(energy)
    if spent[-1] <= budget:
        return dev
    out = dev.copy()
    k = int(np.searchsorted(spent, budget, side="right"))
    before = float(spent[k - 1]) if k else 0.0
    out[k] = dev[k] * max(budget - before, 0.0) / float(energy[k])
    out[k + 1 :] = 0.0
    return out


def _record(
    sim: bt.Simulation,
    a: bt._Arrays,
    publish: int,
    end: int,
    lag: int,
    faults: bt.Faults,
    peak: tuple[float, float] | None,
    branch: Branch,
) -> list[Submission]:
    """Return one record's MDO and MDB submissions, as `battery.submissions` does."""
    declare = sim.scenario.declare
    (mdo0, mdo1), (mdb0, mdb1) = bt.declared_levels(
        sim, a, publish, end, lag, ignore_pn=declare == "ignore_pn"
    )
    mdo0, mdb0 = bt.planted(mdo0, mdb0, declare, faults, sim.physics, peak)
    mdo1, mdb1 = bt.planted(mdo1, mdb1, declare, faults, sim.physics, peak)
    if branch == "B":
        r = sim.physics.root_eta
        mdo0, mdo1, mdb0, mdb1 = mdo0 / r, mdo1 / r, mdb0 * r, mdb1 * r
    t0 = sim.start + timedelta(minutes=publish)
    t1 = sim.start + timedelta(minutes=end)
    return [
        Submission("MDO", t0, t1, mdo0, mdo1, t0, 0),
        Submission("MDB", t0, t1, mdb0, mdb1, t0, 0),
    ]


def _finish(
    view: bt.Simulation,
    a: bt._Arrays,
    tracked: NDArray[np.float64],
    d: bt.Draws,
    physics: bt.Physics,
    limits: bt.Limits | None,
    counts: Counts,
) -> bt.Simulation:
    """Return the run as `battery.simulate` reports one, checked against tracking."""
    minutes, periods = view.minutes, view.minutes // bt.MINUTES_PER_PERIOD
    s0 = float(tracked[0])
    limited = np.zeros(minutes, dtype=bool)
    if limits is None:
        change = bt.stored_change(a, 0, minutes, physics.root_eta, with_dc=True)
        metered = bt.meter_mwh(a, 0, minutes, with_dc=True)
        stored, change, curtailed = bt.curtail(s0, change, physics.energy_mwh)
        if curtailed.any():
            r = physics.root_eta
            actual = np.where(change < 0, -change * r, -change / r)
            metered = np.where(curtailed, actual, metered)
    else:
        requested = bt.meter_mwh(a, 0, minutes, with_dc=False) * 60.0
        stored, metered, curtailed, limited = bt.deliver(
            s0,
            requested,
            physics,
            limits.power_mw,
            limits.ramp_mw_per_min,
            limits.derate,
        )
    known = ~np.isnan(tracked)
    if np.abs(stored[known] - tracked[known]).max() > 1e-6:
        raise bt.SimulationError("tracked stored energy departs from the full run")
    meter = metered.reshape(periods, -1).sum(axis=1)
    refused = counts.overlapping + counts.below_1_mw + counts.no_record
    return replace(
        view,
        boas=tuple(a.boas),
        stored_mwh=stored,
        meter_net_mwh=meter + d.meter_noise_mwh,
        boas_not_accepted=refused + counts.wrong_sign,
        curtailed_minutes=int(np.count_nonzero(curtailed)),
        limited_minutes=int(np.count_nonzero(limited)),
    )
