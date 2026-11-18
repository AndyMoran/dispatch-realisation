"""Tank walls: what the meter alone proves about stored energy (PREREGISTRATION §3).

Within a week, exporting y MWh lowers deliverable energy by y, and importing x MWh
raises it by η̂·x. K_t is the cumulative change since the week began, measured at
each settlement-period boundary. The tank held D_0 + K_t for some unknown D_0 ≥ 0,
and never less than zero, so at every boundary it held at least

    L_t = K_t − min K                      (lower wall; Claim 2)

Where a nameplate N bounds usable energy, it held at most

    N − (max K − K_t)                      (upper wall; Claim 4, §6)

Neither wall uses a declaration, and the lower wall needs no capacity figure.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.model.types import SETTLEMENT_PERIOD, MeterPeriod


class MissingSettlementPeriod(ValueError):
    """The meter has a gap, so the walls cannot be built across it."""


def require_contiguous(meter: Sequence[MeterPeriod]) -> None:
    """Raise unless the periods follow one another with no gap or repeat."""
    for earlier, later in zip(meter, meter[1:], strict=False):
        if later.period_start - earlier.period_start != SETTLEMENT_PERIOD:
            raise MissingSettlementPeriod(
                f"gap or repeat between {earlier.period_start.isoformat()} "
                f"and {later.period_start.isoformat()}"
            )


def cumulative_change(meter: Sequence[MeterPeriod], eta: float) -> tuple[float, ...]:
    """Return K at every boundary of the week: K_0 = 0, then one value per period.

    The result has one more value than `meter`: the boundary after period h is
    K_{h+1} = K_h + η̂·E⁻_h − E⁺_h.
    """
    if not meter:
        raise MissingSettlementPeriod("no settlement periods")
    if not 0 < eta <= 1:
        raise ValueError(f"η̂ outside (0, 1]: {eta}")
    require_contiguous(meter)
    k_mwh = [0.0]
    for period in meter:
        k_mwh.append(k_mwh[-1] + eta * period.import_mwh - period.export_mwh)
    return tuple(k_mwh)


def lower_wall(k_mwh: Sequence[float]) -> tuple[float, ...]:
    """Return L_t = K_t − min K: the least energy the tank provably held."""
    if not k_mwh:
        raise ValueError("no boundaries")
    floor = min(k_mwh)
    walls = tuple(k - floor for k in k_mwh)
    if min(walls) != 0.0:
        raise AssertionError("the lower wall must touch zero somewhere")
    return walls


def upper_wall(k_mwh: Sequence[float], nameplate_mwh: float) -> tuple[float, ...]:
    """Return N − (max K − K_t): the most energy the tank could have held (§6)."""
    if not k_mwh:
        raise ValueError("no boundaries")
    if nameplate_mwh <= 0:
        raise ValueError(f"nameplate not positive: {nameplate_mwh}")
    ceiling = max(k_mwh)
    return tuple(nameplate_mwh - (ceiling - k) for k in k_mwh)


def swing_mwh(k_mwh: Sequence[float]) -> float:
    """Return max K − min K: the week's swing, used by Claim 2's tolerance and §6."""
    if not k_mwh:
        raise ValueError("no boundaries")
    return max(k_mwh) - min(k_mwh)
