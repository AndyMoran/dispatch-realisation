"""Round-trip efficiency from the meter (PREREGISTRATION §3, "Efficiency").

η̂ = ΣE⁺ / ΣE⁻ over all the unit's complete weeks after its adoption week, before
any screen. B1610 gives one net value per period, so E⁺ and E⁻ are its positive
and negative parts (ASSUMPTIONS M23). Netting hides two-way flow within a period,
which biases η̂ low by an unknown amount (ASSUMPTIONS P7).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.model.types import MeterPeriod


class EfficiencyUndefined(ValueError):
    """η̂ cannot be computed: the unit imported nothing in the window."""


def eta_hat(meter: Sequence[MeterPeriod]) -> float:
    """Return η̂, metered export divided by metered import (§3)."""
    export_mwh = sum(m.export_mwh for m in meter)
    import_mwh = sum(m.import_mwh for m in meter)
    if import_mwh <= 0:
        raise EfficiencyUndefined("no metered import in the window")
    eta = export_mwh / import_mwh
    if eta < 0:
        raise AssertionError("η̂ below zero from non-negative sums")
    return eta


def eta_in_bounds(eta: float, eta_min: float, eta_max: float) -> bool:
    """Return whether η̂ lies in [eta_min, eta_max]; outside, Claims 1–4 skip the unit.

    §3 sets [0.70, 0.98]; §9 repeats every flag with [0.65, 0.99].
    """
    if not eta_min < eta_max:
        raise ValueError(f"bounds out of order: [{eta_min}, {eta_max}]")
    return eta_min <= eta <= eta_max
