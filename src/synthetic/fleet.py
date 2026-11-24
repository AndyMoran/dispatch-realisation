"""A small fleet of honest synthetic batteries, shaped like an assembled fleet.

Used by the tests of the pinned scoring run and the packs, so both run on the
same made-up units. Unit IDs (`UNIT-00` …) and lead parties (`Lead Party 0` …)
are invented; unit 0 is secondary.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from src.ingest import assemble as asm
from src.model.types import UnitInputs
from src.synthetic import battery as bt
from src.synthetic.bands import BAND_SETS
from src.synthetic.settings import load_synthetic_settings


def synthetic_assembly(
    units: int = 7, parties: int = 3
) -> tuple[asm.Assembly, datetime]:
    """Return an assembly of honest batteries over 4 scored weeks, and its end."""
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    band = next(b for b in BAND_SETS["deviation-2"] if b.scenario.name == "honest")
    length = settings.lengths[0]  # 4 scored weeks
    fleet: dict[str, asm.FleetUnit] = {}
    inputs: dict[str, UnitInputs] = {}
    for i in range(units):
        rng = bt.run_rng(settings.master_seed, band.scenario.name, 0, i)
        sim = bt.simulate(
            band.scenario,
            length,
            settings,
            bt.load_physics(),
            bt.load_dc_energy(settings),
            rng,
            faults,
        )
        uid = f"UNIT-{i:02d}"
        lag = bt.lag_minutes(band.scenario, settings, faults)
        inputs[uid] = replace(bt.unit_inputs(sim, "A", lag, faults), unit_key=uid)
        fleet[uid] = asm.FleetUnit(
            unit=uid,
            adoption_week_start=length.adoption_week_start,
            adopted_at=length.adoption_week_start + timedelta(hours=9),
            registered_mw=inputs[uid].registered_mw,
            lead_party=f"Lead Party {i % parties}",
            secondary=i == 0,
        )
    return asm.Assembly(fleet, inputs, {}, {}, units, {}), length.end
