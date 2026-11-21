"""The honest synthetic battery of the known-answer suite (PREREGISTRATION §8).

A battery is simulated minute by minute from the start of its adoption week to the
end of its last scored week, then reported through the same types as BMRS data
(`UnitInputs`): MDO and MDB records, one net meter value per settlement period, PN
and accepted instructions. The claims cannot tell it from a real unit.

Fixed before any band was computed (PROJECT.md §11, 18 Nov 2026):

- **Stored energy** S moves with the flow at the meter: exporting y MWh draws
  y/√η from storage, importing x MWh adds x·√η. Deliverable energy at the meter is
  √η·S, so §3's reconstruction holds exactly when nothing is netted.
- **PN** has a level for every settlement period, constant within it. Each charge
  or discharge window aims stored energy at its target (config/synthetic.toml), and
  is decided three hours before it starts, from the stored energy then forecast
  without frequency response. Three hours exceeds the longest protection horizon
  (current period plus three, at most two hours), so every PN a declaration
  protects was decided before the declaration.
- **Instructions** arrive as a Poisson stream. One that would overlap an active
  instruction is not accepted, and neither is one below 1 MW. Each is a constant
  deviation from PN, sized as a uniform share in [0.2, 1] of the energy the unit
  could deliver (offers) or absorb (bids) at acceptance, spread over its duration,
  and capped so PN, instruction and contracted response stay within power_mw.
  Sizing protects every PN already decided, not only PN within H, and the
  largest response contract over that span, so a window or contract known before
  the instruction cannot then overfill or empty the battery.
- **Dynamic Containment**: contracted MW is per settlement period. Where neither PN
  nor an instruction is active, the period's response flows both ways, as the
  frequency data says, and is metered net (ASSUMPTIONS P7). Where either is active,
  the response nets with it and flows one way; this ignores the rare seconds in
  which a large response would reverse the flow.
- **Declarations** (both branches from one simulation): a routine record at every
  period start for 30 minutes, and a record `lag` minutes after each acceptance to
  the end of its period. A record published at p knows acceptances at or before
  p − lag. It is a straight line from MDO at p, from the actual state, to MDO at
  its end, forecast from PN and known instructions without frequency response. It
  starts at its publish time, so it changes nothing before it was published.
- **MDO at the meter (Branch A)** = max(0, √η·S − P^exp − B^exp − R), where R is
  contracted MW × delivery_duration_h. **MDB** = −max(0, (U − S)/√η − P^imp −
  B^imp − R). Branch B declares stored energy: MDO/√η and MDB·√η.
- **Walls**: a minute whose response would take stored energy below empty or
  above full is cut off at the wall, and the meter records what was delivered.
  Curtailed minutes are counted; they arise only from response the battery did
  not forecast, since it makes no Vrec recovery trades (ASSUMPTIONS P9).
- **Meter**: the period's net energy plus Gaussian noise (config/synthetic.toml).

Randomness is drawn up front in a fixed order, so whether an instruction is
accepted never shifts any other draw.
"""

from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
from numpy.typing import NDArray

from src.model.params import load_params
from src.model.types import (
    Dataset,
    LevelSegment,
    MeterPeriod,
    Submission,
    UnitInputs,
    build_unit_inputs,
)
from src.physics.declared import Branch
from src.synthetic.settings import RunLength, SyntheticSettings

ROOT = Path(__file__).resolve().parents[2]
UK = ZoneInfo("Europe/London")
MINUTES_PER_PERIOD = 30
MINUTES_PER_DAY = 1440
EFA_BOUNDARY_HOURS_UK = frozenset({23, 3, 7, 11, 15, 19})
PN_DECISION_LEAD_MIN = 180
HORIZON_EXTRA_PERIODS = 3
BOA_SHARE_RANGE = (0.2, 1.0)
MIN_BOA_MW = 1.0
RUN_TYPE = "SF"

DcMode = Literal["none", "constant", "efa"]
Lag = Literal["honest", "fast", "slow"]
Declare = Literal["honest", "offset", "proportional", "static", "ignore_pn", "under"]
PhysicsMode = Literal["normal", "ramp", "derate"]


class SimulationError(RuntimeError):
    """The simulated battery broke a physical limit its settings should prevent."""


@dataclass(frozen=True)
class Scenario:
    """A synthetic battery: its name (which seeds it), contracts and planted fault.

    dc: "none" holds no response; "constant" holds the largest contract level all
    the time (frequency-response noise); "efa" draws a level per EFA block.
    reserve: holds reserve-style protection that steps at random half-hours.
    lag: when it redeclares after an instruction ("honest", or §8's "fast" and
    "slow" redeclarers).
    declare: how its MDO departs from the honest one (§8 rows): "offset" adds
    planted_delta_mwh; "proportional" declares available / (1 − planted_f);
    "static" declares the full tank throughout; "ignore_pn" leaves PN protection
    in MDO; "under" subtracts under_declaration_mwh, floored at zero.
    physics: "ramp" limits PN and instruction power to ramp_limited_mw_per_min;
    "derate" limits export power linearly to derate_to_fraction below
    derate_below_soc of U.
    """

    name: str
    dc: DcMode
    reserve: bool = False
    lag: Lag = "honest"
    declare: Declare = "honest"
    physics: PhysicsMode = "normal"

    @property
    def holds_contracts(self) -> bool:
        """Return whether any week of this battery carries contract time (§4)."""
        return self.dc != "none" or self.reserve


HONEST = Scenario("honest", "none")
HONEST_FR = Scenario("honest_frequency_response", "constant")
HONEST_DC_EFA = Scenario("honest_dc_efa", "efa")
HONEST_RAMP = Scenario("honest_ramp_limited", "none", physics="ramp")
HONEST_DERATE = Scenario("honest_derating", "none", physics="derate")
OVER_CONSTANT = Scenario("constant_over_declaration", "none", declare="offset")
OVER_PROPORTIONAL = Scenario(
    "proportional_over_declaration", "none", declare="proportional"
)
STATIC_PROFILE = Scenario("static_profile_from_maximum", "none", declare="static")
REDECLARE_FAST = Scenario("redeclares_after_5_minutes", "none", lag="fast")
REDECLARE_SLOW = Scenario("honest_redeclares_after_25_minutes", "none", lag="slow")
PN_IGNORED = Scenario("pn_protection_ignored", "none", declare="ignore_pn")
UNDER_CONSTANT = Scenario("constant_under_declaration", "none", declare="under")
OVER_PROPORTIONAL_RESERVE = Scenario(
    "proportional_over_declaration_with_reserve",
    "none",
    reserve=True,
    declare="proportional",
)


@dataclass(frozen=True)
class Faults:
    """§8's planted-fault figures, from config/claims.toml."""

    delta_mwh: float
    f: float
    under_mwh: float
    fast_lag_min: int
    slow_lag_min: int
    derate_to_fraction: float
    derate_below_soc: float


def load_faults() -> Faults:
    """Return §8's planted-fault figures as config/claims.toml pins them."""
    p = load_params()
    return Faults(
        delta_mwh=p.number("known_answer.planted_delta_mwh"),
        f=p.number("known_answer.planted_f"),
        under_mwh=p.number("known_answer.under_declaration_mwh"),
        fast_lag_min=p.integer("known_answer.redeclare_fast_min"),
        slow_lag_min=p.integer("known_answer.redeclare_slow_min"),
        derate_to_fraction=p.number("known_answer.derate_to_fraction"),
        derate_below_soc=p.number("known_answer.derate_below_soc"),
    )


def lag_minutes(scenario: Scenario, settings: SyntheticSettings, faults: Faults) -> int:
    """Return the minutes from acceptance to redeclaration for a battery."""
    if scenario.lag == "fast":
        return faults.fast_lag_min
    if scenario.lag == "slow":
        return faults.slow_lag_min
    return settings.honest_lag_min


@dataclass(frozen=True)
class Physics:
    """§8's common settings, from config/claims.toml."""

    energy_mwh: float
    eta: float

    @property
    def root_eta(self) -> float:
        """Return √η, the one-way efficiency."""
        return math.sqrt(self.eta)


@dataclass(frozen=True)
class DcEnergy:
    """DC energy per contracted MW for each settlement period from 1 Jun 2026."""

    start: datetime
    export_mwh_per_mw: NDArray[np.float64]
    import_mwh_per_mw: NDArray[np.float64]

    def window(self, start: datetime, periods: int) -> tuple[NDArray[np.float64], ...]:
        """Return (export, import) per MW for `periods` periods from `start`."""
        offset = (start - self.start) // timedelta(minutes=MINUTES_PER_PERIOD)
        if offset < 0 or offset + periods > self.export_mwh_per_mw.size:
            raise SimulationError(f"run from {start} lies outside the frequency data")
        stop = offset + periods
        return (
            self.export_mwh_per_mw[offset:stop].copy(),
            self.import_mwh_per_mw[offset:stop].copy(),
        )


@dataclass(frozen=True)
class Boa:
    """One accepted instruction: a constant deviation from PN, minutes from start."""

    number: int
    accepted_min: int
    end_min: int
    deviation_mw: float


@dataclass(frozen=True)
class Simulation:
    """One run of one battery: its inputs and its true state, minute by minute.

    Per period: PN, whether a window set it, contracted response and its energy
    per MW. Per minute: the instructed deviation, its acceptance minute (−1 where
    none) and the instruction's index (−1 where none). `stored_mwh` holds S at
    every minute boundary, `minutes + 1` values.
    """

    scenario: Scenario
    start: datetime
    minutes: int
    physics: Physics
    power_mw: float
    delivery_duration_h: float
    pn_mw: NDArray[np.float64]
    pn_active: NDArray[np.bool_]
    dc_mw: NDArray[np.float64]
    dc_export_mwh_per_mw: NDArray[np.float64]
    dc_import_mwh_per_mw: NDArray[np.float64]
    boas: tuple[Boa, ...]
    boa_id: NDArray[np.int64]
    boa_dev_mw: NDArray[np.float64]
    boa_accepted_min: NDArray[np.int64]
    stored_mwh: NDArray[np.float64]
    meter_net_mwh: NDArray[np.float64]
    boas_not_accepted: int
    curtailed_minutes: int
    reserve_mwh: NDArray[np.float64]
    limited_minutes: int

    @property
    def periods(self) -> int:
        """Return the number of settlement periods simulated."""
        return self.minutes // MINUTES_PER_PERIOD


# ------------------------------------------------------------------ inputs


def load_physics() -> Physics:
    """Return U and η as §8 prints them (config/claims.toml)."""
    params = load_params()
    return Physics(
        energy_mwh=params.number("known_answer.capacity_mwh"),
        eta=params.number("known_answer.eta"),
    )


def load_dc_energy(settings: SyntheticSettings, root: Path = ROOT) -> DcEnergy:
    """Return the committed DC energy file, after checking it against its summary."""
    fs = settings.frequency
    path = root / fs.derived_file
    summary = (root / fs.summary_file).read_text(encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if f'"derived_sha256": "{digest}"' not in summary:
        raise SimulationError(f"{fs.derived_file} does not match its summary")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    first = datetime.fromisoformat(rows[0]["period_start_utc"].replace("Z", "+00:00"))
    if first != fs.start or len(rows) != fs.days * 48:
        raise SimulationError(f"{fs.derived_file} does not cover the frequency span")
    return DcEnergy(
        start=first,
        export_mwh_per_mw=np.array([float(r["export_mwh_per_mw"]) for r in rows]),
        import_mwh_per_mw=np.array([float(r["import_mwh_per_mw"]) for r in rows]),
    )


def run_rng(
    master_seed: int, battery: str, length_index: int, run_index: int
) -> np.random.Generator:
    """Return the generator for one run (config/synthetic.toml [runs])."""
    name_key = int.from_bytes(hashlib.sha256(battery.encode()).digest()[:8], "big")
    seq = np.random.SeedSequence(
        master_seed, spawn_key=(name_key, length_index, run_index)
    )
    return np.random.default_rng(seq)


def efa_block_starts(start: datetime, periods: int) -> NDArray[np.bool_]:
    """Return, per period, whether an EFA block starts there (UK time)."""
    out = np.zeros(periods, dtype=bool)
    for p in range(periods):
        local = (start + timedelta(minutes=MINUTES_PER_PERIOD * p)).astimezone(UK)
        out[p] = local.minute == 0 and local.hour in EFA_BOUNDARY_HOURS_UK
    return out


# ------------------------------------------------------------------ draws


@dataclass(frozen=True)
class Draws:
    """Every random number a run uses, drawn up front in a fixed order."""

    initial_share: float
    dc_levels_mw: NDArray[np.float64]
    boa_start_min: NDArray[np.int64]
    boa_duration_min: NDArray[np.int64]
    boa_is_offer: NDArray[np.bool_]
    boa_share: NDArray[np.float64]
    meter_noise_mwh: NDArray[np.float64]
    reserve_step_mwh: NDArray[np.float64]


def draw(
    settings: SyntheticSettings, days: int, blocks: int, rng: np.random.Generator
) -> Draws:
    """Return a run's draws: start state, contracts, instructions, meter noise."""
    low, high = settings.battery.initial_soc_share
    initial = float(rng.uniform(low, high))
    levels = np.array(settings.response.contract_levels_mw)
    dc_levels = levels[rng.integers(0, levels.size, size=blocks)]
    counts = rng.poisson(settings.boa_mean_per_day, size=days)
    total = int(counts.sum())
    day_of = np.repeat(np.arange(days), counts)
    minute = rng.integers(0, MINUTES_PER_DAY, size=total)
    shortest, longest = settings.boa_duration_min
    duration = rng.integers(shortest, longest + 1, size=total)
    offer = rng.random(size=total) < settings.boa_offer_share
    share = rng.uniform(*BOA_SHARE_RANGE, size=total)
    noise = rng.normal(0.0, settings.meter_noise_sd_mwh, size=days * 48)
    # Drawn last, so adding it left every earlier draw, and the first run, intact.
    changes = rng.random(size=days * 48) < settings.reserve_change_probability
    size = rng.uniform(*settings.reserve_step_mwh, size=days * 48)
    sign = np.where(rng.random(size=days * 48) < 0.5, -1.0, 1.0)
    order = np.argsort(day_of * MINUTES_PER_DAY + minute, kind="stable")
    return Draws(
        initial_share=initial,
        dc_levels_mw=dc_levels,
        boa_start_min=(day_of * MINUTES_PER_DAY + minute)[order],
        boa_duration_min=duration[order],
        boa_is_offer=offer[order],
        boa_share=share[order],
        meter_noise_mwh=noise,
        reserve_step_mwh=np.where(changes, sign * size, 0.0),
    )


# ------------------------------------------------------------------ flows


@dataclass
class _Arrays:
    """Working arrays while a run is built, frozen into Simulation after."""

    pn_mw: NDArray[np.float64]
    pn_active: NDArray[np.bool_]
    boa_id: NDArray[np.int64]
    boa_dev: NDArray[np.float64]
    boa_acc: NDArray[np.int64]
    boas: list[Boa]
    dc_mw: NDArray[np.float64]
    dc_exp: NDArray[np.float64]
    dc_imp: NDArray[np.float64]
    reserve: NDArray[np.float64]


def _deviation(
    a: _Arrays, start: int, stop: int, known_up_to: int | None
) -> NDArray[np.float64]:
    """Return instructed deviation per minute; only known ones if a cut-off is given."""
    dev = a.boa_dev[start:stop]
    if known_up_to is None:
        return dev
    out: NDArray[np.float64] = np.where(a.boa_acc[start:stop] <= known_up_to, dev, 0.0)
    return out


def meter_mwh(
    a: _Arrays, start: int, stop: int, with_dc: bool, known_up_to: int | None = None
) -> NDArray[np.float64]:
    """Return net metered energy in each minute of [start, stop); export positive."""
    period = np.arange(start, stop) // MINUTES_PER_PERIOD
    energy: NDArray[np.float64] = (
        a.pn_mw[period] + _deviation(a, start, stop, known_up_to)
    ) / 60.0
    if with_dc:
        per_minute = (a.dc_exp[period] - a.dc_imp[period]) / MINUTES_PER_PERIOD
        energy = energy + a.dc_mw[period] * per_minute
    return energy


def stored_change(
    a: _Arrays,
    start: int,
    stop: int,
    root_eta: float,
    with_dc: bool,
    known_up_to: int | None = None,
) -> NDArray[np.float64]:
    """Return the change in stored energy in each minute of [start, stop).

    With response and no PN or instruction active, the response flows both ways
    within the period and each direction pays its own loss (ASSUMPTIONS P7).
    """
    net = meter_mwh(a, start, stop, with_dc, known_up_to)
    change = np.where(net > 0, -net / root_eta, -net * root_eta)
    if with_dc:
        period = np.arange(start, stop) // MINUTES_PER_PERIOD
        idle = ~a.pn_active[period] & (a.boa_id[start:stop] < 0)
        c = a.dc_mw[period] / MINUTES_PER_PERIOD
        gross = -c * a.dc_exp[period] / root_eta + c * a.dc_imp[period] * root_eta
        change = np.where(idle, gross, change)
    out: NDArray[np.float64] = change
    return out


def horizon_stop(minute: int) -> int:
    """Return the minute H ends: the period containing `minute`, plus three (M15)."""
    return (
        minute // MINUTES_PER_PERIOD + 1 + HORIZON_EXTRA_PERIODS
    ) * MINUTES_PER_PERIOD


@dataclass(frozen=True)
class Protection:
    """Energy protected from a minute to the end of H, at the meter."""

    pn_export: float
    pn_import: float
    boa_export: float
    boa_import: float


def protection(
    a: _Arrays, minute: int, known_up_to: int, minutes: int, stop: int | None = None
) -> Protection:
    """Return PN and known-instruction energy from `minute` to the end of H (§3).

    Only instructions accepted at or before `known_up_to` count. PN within H was
    always decided before (PN_DECISION_LEAD_MIN exceeds H). `stop` overrides the
    end of H, for sizing instructions against every PN already decided.
    """
    stop = min(horizon_stop(minute) if stop is None else stop, minutes)
    if stop <= minute:
        return Protection(0.0, 0.0, 0.0, 0.0)
    pn = a.pn_mw[np.arange(minute, stop) // MINUTES_PER_PERIOD] / 60.0
    dev = _deviation(a, minute, stop, known_up_to) / 60.0
    return Protection(
        pn_export=float(np.clip(pn, 0.0, None).sum()),
        pn_import=float(np.clip(-pn, 0.0, None).sum()),
        boa_export=float(np.clip(dev, 0.0, None).sum()),
        boa_import=float(np.clip(-dev, 0.0, None).sum()),
    )


def mdo_mdb_a(
    stored_mwh: float,
    prot: Protection,
    reserved_mwh: float,
    physics: Physics,
) -> tuple[float, float]:
    """Return honest (MDO, MDB) at the meter, Branch A, from stored energy."""
    r = physics.root_eta
    mdo = stored_mwh * r - prot.pn_export - prot.boa_export - reserved_mwh
    headroom = (physics.energy_mwh - stored_mwh) / r
    mdb = headroom - prot.pn_import - prot.boa_import - reserved_mwh
    return max(mdo, 0.0), -max(mdb, 0.0)


# ------------------------------------------------------------------ run


def simulate(
    scenario: Scenario,
    length: RunLength,
    settings: SyntheticSettings,
    physics: Physics,
    dc: DcEnergy,
    rng: np.random.Generator,
    faults: Faults | None = None,
) -> Simulation:
    """Return one run of a battery (module docstring).

    `faults` is needed only for the derating battery, whose limits §8 fixes.
    """
    if scenario.physics == "derate" and faults is None:
        raise SimulationError("the derating battery needs §8's derating figures")
    start = length.adoption_week_start
    days = (length.end - start).days
    minutes = days * MINUTES_PER_DAY
    periods = minutes // MINUTES_PER_PERIOD
    block_start = efa_block_starts(start, periods)
    block_index = np.cumsum(block_start) - 1
    blocks = int(block_index.max()) + 2
    d = draw(settings, days, blocks, rng)
    dc_exp, dc_imp = dc.window(start, periods)
    levels = np.asarray(settings.response.contract_levels_mw)
    if scenario.dc == "none":
        dc_mw = np.zeros(periods)
    elif scenario.dc == "constant":
        dc_mw = np.full(periods, float(levels.max()))
    else:
        dc_mw = d.dc_levels_mw[block_index + 1].astype(float)
    reserve = (
        reserve_levels(d.reserve_step_mwh, settings.reserve_range_mwh)
        if scenario.reserve
        else np.zeros(periods)
    )
    a = _Arrays(
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
    s0 = d.initial_share * physics.energy_mwh
    not_accepted = _run_events(a, d, settings, physics, s0, minutes)
    limited = np.zeros(minutes, dtype=bool)
    if scenario.physics == "normal":
        change = stored_change(a, 0, minutes, physics.root_eta, with_dc=True)
        metered = meter_mwh(a, 0, minutes, with_dc=True)
        stored, change, curtailed = curtail(s0, change, physics.energy_mwh)
        if curtailed.any():
            r = physics.root_eta
            actual = np.where(change < 0, -change * r, -change / r)
            metered = np.where(curtailed, actual, metered)
    else:
        if scenario.dc != "none":
            raise SimulationError("ramp and derating batteries hold no response")
        requested = meter_mwh(a, 0, minutes, with_dc=False) * 60.0
        stored, metered, curtailed, limited = deliver(
            s0,
            requested,
            physics,
            settings.battery.power_mw,
            ramp_mw_per_min=(
                settings.ramp_limited_mw_per_min if scenario.physics == "ramp" else None
            ),
            derate=(
                (faults.derate_to_fraction, faults.derate_below_soc)
                if scenario.physics == "derate" and faults is not None
                else None
            ),
        )
    meter = metered.reshape(periods, -1).sum(axis=1)
    return Simulation(
        scenario=scenario,
        start=start,
        minutes=minutes,
        physics=physics,
        power_mw=settings.battery.power_mw,
        delivery_duration_h=settings.response.delivery_duration_h,
        pn_mw=a.pn_mw,
        pn_active=a.pn_active,
        dc_mw=a.dc_mw,
        dc_export_mwh_per_mw=dc_exp,
        dc_import_mwh_per_mw=dc_imp,
        boas=tuple(a.boas),
        boa_id=a.boa_id,
        boa_dev_mw=a.boa_dev,
        boa_accepted_min=a.boa_acc,
        stored_mwh=stored,
        meter_net_mwh=meter + d.meter_noise_mwh,
        boas_not_accepted=not_accepted,
        curtailed_minutes=int(np.count_nonzero(curtailed)),
        reserve_mwh=reserve,
        limited_minutes=int(np.count_nonzero(limited)),
    )


def reserve_levels(
    steps_mwh: NDArray[np.float64], range_mwh: tuple[float, float]
) -> NDArray[np.float64]:
    """Return reserve protection per period: a walk of the steps, kept in range.

    It starts at the bottom of the range and changes only at period starts.
    """
    low, high = range_mwh
    out = np.empty(steps_mwh.size)
    level = low
    for p, step in enumerate(steps_mwh):
        level = min(max(level + float(step), low), high)
        out[p] = level
    return out


def deliver(
    s0: float,
    requested_mw: NDArray[np.float64],
    physics: Physics,
    power_mw: float,
    ramp_mw_per_min: float | None = None,
    derate: tuple[float, float] | None = None,
) -> tuple[
    NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_], NDArray[np.bool_]
]:
    """Return stored energy, metered energy, curtailed and limited minutes.

    Minute by minute, for a battery holding no response: the requested power (PN
    plus instruction) is limited by the ramp rate from the previous minute's
    delivered power, and, when derating, export is limited to power_mw ×
    (to_fraction + (1 − to_fraction) × S / (below × U)) while S is below below × U.
    A minute that would cross empty or full is cut off at the wall, as in curtail.
    """
    r, full = physics.root_eta, physics.energy_mwh
    n = requested_mw.size
    levels = np.empty(n + 1)
    metered = np.empty(n)
    curtailed = np.zeros(n, dtype=bool)
    limited = np.zeros(n, dtype=bool)
    levels[0] = level = s0
    previous = 0.0
    for m in range(n):
        power = float(requested_mw[m])
        if ramp_mw_per_min is not None:
            low, high = previous - ramp_mw_per_min, previous + ramp_mw_per_min
            if power < low or power > high:
                power = min(max(power, low), high)
                limited[m] = True
        if derate is not None and power > 0:
            to_fraction, below = derate
            share = min(level / (below * full), 1.0)
            cap = power_mw * (to_fraction + (1.0 - to_fraction) * share)
            if power > cap:
                power = cap
                limited[m] = True
        energy = power / 60.0
        wanted = level + (-energy / r if energy > 0 else -energy * r)
        if wanted < 0.0 or wanted > full:
            curtailed[m] = True
            wanted = min(max(wanted, 0.0), full)
            change = wanted - level
            energy = -change * r if change < 0 else -change / r
            power = energy * 60.0
        levels[m + 1] = level = wanted
        metered[m] = energy
        previous = power
    return levels, metered, curtailed, limited


def curtail(
    s0: float, change: NDArray[np.float64], energy_mwh: float
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    """Return stored energy, actual changes and curtailed minutes, within [0, U].

    A battery cannot go below empty or above full: in a minute that would cross a
    wall, the flow stops at the wall. Only frequency response can reach a wall, as
    instructions and PN are sized against stored energy.
    """
    stored = s0 + np.concatenate(([0.0], np.cumsum(change)))
    if stored.min() >= 0.0 and stored.max() <= energy_mwh:
        return stored, change, np.zeros(change.size, dtype=bool)
    actual = change.copy()
    curtailed = np.zeros(change.size, dtype=bool)
    levels = np.empty(change.size + 1)
    levels[0] = level = s0
    for m in range(change.size):
        wanted = level + change[m]
        if wanted < 0.0 or wanted > energy_mwh:
            curtailed[m] = True
            wanted = min(max(wanted, 0.0), energy_mwh)
            actual[m] = wanted - level
        levels[m + 1] = level = wanted
    return levels, actual, curtailed


def _windows(settings: SyntheticSettings, days: int) -> list[tuple[int, int, str]]:
    """Return (decision minute, window start minute, kind), in decision order."""
    b = settings.battery
    out = []
    for day in range(days):
        for hours, kind in [(h, "charge") for h in b.charge_start_hours_utc] + [
            (h, "discharge") for h in b.discharge_start_hours_utc
        ]:
            w = day * MINUTES_PER_DAY + round(hours * 60)
            out.append((max(w - PN_DECISION_LEAD_MIN, 0), w, kind))
    return sorted(out)


def _run_events(
    a: _Arrays,
    d: Draws,
    settings: SyntheticSettings,
    physics: Physics,
    s0: float,
    minutes: int,
) -> int:
    """Apply PN decisions and instructions in time order; return those refused."""
    events: list[tuple[int, int, int]] = []  # (minute, 0 = PN / 1 = BOA, index)
    windows = _windows(settings, minutes // MINUTES_PER_DAY)
    events += [(dec, 0, i) for i, (dec, _, _) in enumerate(windows)]
    events += [(int(m), 1, i) for i, m in enumerate(d.boa_start_min)]
    events.sort()
    known_s, known_m, refused = s0, 0, 0
    for minute, kind, i in events:
        known_s += float(
            stored_change(a, known_m, minute, physics.root_eta, True).sum()
        )
        known_m = minute
        if kind == 0:
            _decide_pn(a, windows[i], known_s, settings, physics, minutes)
        elif not _accept_boa(a, d, i, minute, known_s, settings, physics, minutes):
            refused += 1
    return refused


def _decide_pn(
    a: _Arrays,
    window: tuple[int, int, str],
    stored_now: float,
    settings: SyntheticSettings,
    physics: Physics,
    minutes: int,
) -> None:
    """Set a window's PN so stored energy reaches its target, as forecast now."""
    decided, w, kind = window
    b = settings.battery
    length = round(b.window_h * 60)
    if w >= minutes:
        return
    forecast = stored_now + float(
        stored_change(a, decided, w, physics.root_eta, False).sum()
    )
    hours = b.window_h
    cap = b.power_mw - max(settings.response.contract_levels_mw)
    r = physics.root_eta
    if kind == "charge":
        need_or_spare = b.soc_high_share * physics.energy_mwh - forecast
        level = -min(max(need_or_spare, 0.0) / r / hours, cap)
    else:
        need_or_spare = forecast - b.soc_low_share * physics.energy_mwh
        level = min(max(need_or_spare, 0.0) * r / hours, cap)
    first, last = (
        w // MINUTES_PER_PERIOD,
        min(w + length, minutes) // MINUTES_PER_PERIOD,
    )
    a.pn_mw[first:last] = level
    a.pn_active[first:last] = need_or_spare > 0


def _accept_boa(
    a: _Arrays,
    d: Draws,
    i: int,
    minute: int,
    stored_now: float,
    settings: SyntheticSettings,
    physics: Physics,
    minutes: int,
) -> bool:
    """Accept instruction i if it fits; return whether it was accepted."""
    stop = minute + int(d.boa_duration_min[i])
    if stop > minutes or (a.boa_id[minute:stop] >= 0).any():
        return False
    decided = np.flatnonzero(a.pn_active)
    last_pn = (int(decided.max()) + 1) * MINUTES_PER_PERIOD if decided.size else 0
    sizing_stop = min(max(horizon_stop(minute), last_pn, stop), minutes)
    prot = protection(a, minute, minute, minutes, sizing_stop)
    held = a.dc_mw[minute // MINUTES_PER_PERIOD : -(-sizing_stop // MINUTES_PER_PERIOD)]
    reserved = float(held.max()) * settings.response.delivery_duration_h + float(
        a.reserve[minute // MINUTES_PER_PERIOD]
    )
    mdo, mdb = mdo_mdb_a(stored_now, prot, reserved, physics)
    span = np.arange(minute, stop) // MINUTES_PER_PERIOD
    hours = (stop - minute) / 60.0
    power = settings.battery.power_mw
    if d.boa_is_offer[i]:
        headroom = float((power - a.pn_mw[span] - a.dc_mw[span]).min())
        level = min(headroom, d.boa_share[i] * mdo / hours)
    else:
        headroom = float((power + a.pn_mw[span] - a.dc_mw[span]).min())
        level = -min(headroom, d.boa_share[i] * -mdb / hours)
    if abs(level) < MIN_BOA_MW:
        return False
    a.boas.append(Boa(len(a.boas) + 1, minute, stop, level))
    a.boa_id[minute:stop] = len(a.boas) - 1
    a.boa_dev[minute:stop] = level
    a.boa_acc[minute:stop] = minute
    return True


# ------------------------------------------------------------------ reporting


def _working(sim: Simulation) -> _Arrays:
    return _Arrays(
        pn_mw=sim.pn_mw,
        pn_active=sim.pn_active,
        boa_id=sim.boa_id,
        boa_dev=sim.boa_dev_mw,
        boa_acc=sim.boa_accepted_min,
        boas=list(sim.boas),
        dc_mw=sim.dc_mw,
        dc_exp=sim.dc_export_mwh_per_mw,
        dc_imp=sim.dc_import_mwh_per_mw,
        reserve=sim.reserve_mwh,
    )


def reserved_mwh(sim: Simulation, minute: int) -> float:
    """Return energy held for contracts at a minute: response MW × duration, plus
    reserve-style protection."""
    p = min(minute, sim.minutes - 1) // MINUTES_PER_PERIOD
    return float(sim.dc_mw[p]) * sim.delivery_duration_h + float(sim.reserve_mwh[p])


def declared_levels(
    sim: Simulation,
    a: _Arrays,
    publish_min: int,
    end_min: int,
    lag_min: int,
    ignore_pn: bool = False,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return ((MDO from, to), (MDB from, to)) at the meter for one record (A).

    The start is the actual state at publication; the end is forecast from PN and
    the instructions known then (accepted at or before publish − lag), without
    frequency response or instructions not yet known.
    """
    known = publish_min - lag_min
    r = sim.physics.root_eta
    s_from = float(sim.stored_mwh[publish_min])
    s_to = s_from + float(
        stored_change(a, publish_min, end_min, r, False, known_up_to=known).sum()
    )
    levels = []
    for minute, stored in ((publish_min, s_from), (end_min, s_to)):
        prot = protection(a, minute, known, sim.minutes)
        if ignore_pn:  # §8 "PN protection ignored": PN energy left in MDO and MDB
            prot = Protection(0.0, 0.0, prot.boa_export, prot.boa_import)
        levels.append(mdo_mdb_a(stored, prot, reserved_mwh(sim, minute), sim.physics))
    (mdo0, mdb0), (mdo1, mdb1) = levels
    return (mdo0, mdo1), (mdb0, mdb1)


def record_times(sim: Simulation, lag_min: int) -> list[tuple[int, int]]:
    """Return (publish, end) minutes of every record, routine and post-instruction."""
    routine = {
        p * MINUTES_PER_PERIOD: (p + 1) * MINUTES_PER_PERIOD for p in range(sim.periods)
    }
    for boa in sim.boas:
        p = boa.accepted_min + lag_min
        if p < sim.minutes and p % MINUTES_PER_PERIOD:
            routine.setdefault(p, (p // MINUTES_PER_PERIOD + 1) * MINUTES_PER_PERIOD)
    return sorted(routine.items())


def planted(
    mdo: float, mdb: float, declare: Declare, faults: Faults | None, physics: Physics
) -> tuple[float, float]:
    """Return (MDO, MDB) at the meter after the battery's planted fault (§8)."""
    if declare in ("honest", "ignore_pn"):
        return mdo, mdb
    if faults is None:
        raise SimulationError(f"declaration fault {declare!r} needs §8's figures")
    if declare == "offset":
        return mdo + faults.delta_mwh, mdb
    if declare == "proportional":
        return mdo / (1.0 - faults.f), mdb
    if declare == "under":
        return max(mdo - faults.under_mwh, 0.0), mdb
    full = physics.energy_mwh  # "static": the full tank, as if copied from maximum
    return full * physics.root_eta, -full / physics.root_eta


def submissions(
    sim: Simulation, branch: Branch, lag_min: int, faults: Faults | None = None
) -> list[Submission]:
    """Return the battery's MDO and MDB records, declared under `branch`.

    The planted fault acts on the meter-side (Branch A) declaration; Branch B
    then converts it, as an honest Branch B declarer would convert its own.
    """
    r = sim.physics.root_eta
    a = _working(sim)
    declare = sim.scenario.declare
    datasets: tuple[Dataset, Dataset] = ("MDO", "MDB")
    out = []
    for publish, end in record_times(sim, lag_min):
        (mdo0, mdo1), (mdb0, mdb1) = declared_levels(
            sim, a, publish, end, lag_min, ignore_pn=declare == "ignore_pn"
        )
        mdo0, mdb0 = planted(mdo0, mdb0, declare, faults, sim.physics)
        mdo1, mdb1 = planted(mdo1, mdb1, declare, faults, sim.physics)
        if branch == "B":
            mdo0, mdo1, mdb0, mdb1 = mdo0 / r, mdo1 / r, mdb0 * r, mdb1 * r
        t0 = sim.start + timedelta(minutes=publish)
        t1 = sim.start + timedelta(minutes=end)
        for dataset, lo, hi in zip(datasets, (mdo0, mdb0), (mdo1, mdb1), strict=True):
            out.append(
                Submission(
                    dataset=dataset,
                    time_from=t0,
                    time_to=t1,
                    level_from_mwh=lo,
                    level_to_mwh=hi,
                    publish_time=t0,
                    serial=0,
                )
            )
    return out


def pn_segments(sim: Simulation) -> list[LevelSegment]:
    """Return PN as one constant segment per settlement period (BSC Section Q)."""
    step = timedelta(minutes=MINUTES_PER_PERIOD)
    return [
        LevelSegment(sim.start + p * step, sim.start + (p + 1) * step, lvl, lvl)
        for p, lvl in enumerate(float(x) for x in sim.pn_mw)
    ]


def boa_segments(sim: Simulation) -> list[LevelSegment]:
    """Return accepted instructions as absolute levels, one piece per period."""
    out = []
    for boa in sim.boas:
        cuts = sorted(
            {boa.accepted_min, boa.end_min}
            | {
                m
                for m in range(boa.accepted_min + 1, boa.end_min)
                if m % MINUTES_PER_PERIOD == 0
            }
        )
        accepted = sim.start + timedelta(minutes=boa.accepted_min)
        for lo, hi in zip(cuts, cuts[1:], strict=False):
            level = float(sim.pn_mw[lo // MINUTES_PER_PERIOD]) + boa.deviation_mw
            out.append(
                LevelSegment(
                    sim.start + timedelta(minutes=lo),
                    sim.start + timedelta(minutes=hi),
                    level,
                    level,
                    acceptance_number=boa.number,
                    acceptance_time=accepted,
                )
            )
    return out


def meter_periods(sim: Simulation) -> list[MeterPeriod]:
    """Return one net meter value per settlement period, run type SF."""
    step = timedelta(minutes=MINUTES_PER_PERIOD)
    return [
        MeterPeriod(sim.start + p * step, float(q), RUN_TYPE)
        for p, q in enumerate(sim.meter_net_mwh)
    ]


def unit_inputs(
    sim: Simulation, branch: Branch, lag_min: int, faults: Faults | None = None
) -> UnitInputs:
    """Return the run as the claims see a unit (`UnitInputs`)."""
    return build_unit_inputs(
        unit_key=f"synthetic:{sim.scenario.name}:{branch}",
        registered_mw=sim.power_mw,
        submissions=submissions(sim, branch, lag_min, faults),
        meter=meter_periods(sim),
        pn=pn_segments(sim),
        boas=boa_segments(sim),
    )
