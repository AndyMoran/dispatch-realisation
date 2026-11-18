"""Input types shared by real BMRS data and the synthetic batteries.

Every claim reads one unit's data through `UnitInputs`, whatever its origin. The types
carry what BMRS publishes and nothing about where a record came from: a manifest,
seed or "synthetic" marker lives in run metadata, which the claims never see
(PROJECT.md §11, module layout, 18 Nov 2026).

Times are timezone-aware UTC. Energies are MWh and power levels MW. Records are
frozen, and collections are tuples sorted by time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

SETTLEMENT_PERIOD = timedelta(minutes=30)

Dataset = Literal["MDO", "MDB"]


class InvalidRecord(ValueError):
    """A record breaks a rule of its type: a sign, a time or an ordering."""


def require_utc(when: datetime, name: str) -> None:
    """Raise unless `when` is timezone-aware and at UTC offset zero."""
    offset = when.utcoffset()
    if offset is None:
        raise InvalidRecord(f"{name}: naive datetime {when.isoformat()}")
    if offset != timedelta(0):
        raise InvalidRecord(f"{name}: not UTC: {when.isoformat()}")


def require_finite(value: float, name: str) -> None:
    """Raise unless `value` is a finite number."""
    if not math.isfinite(value):
        raise InvalidRecord(f"{name}: not finite: {value}")


@dataclass(frozen=True)
class Submission:
    """One MDO or MDB record as BMRS publishes it (PREREGISTRATION §3; M9).

    BMRS fields: timeFrom, timeTo, levelFrom, levelTo, publishTime, serialNumber.
    The value moves in a straight line from `level_from_mwh` to `level_to_mwh`
    over the record; without `level_to_mwh` it is constant. `time_to` is absent
    when the API gives none. A submission is all records sharing `publish_time`
    and `serial`. MDO is declared export energy, at least zero; MDB is declared
    import energy, at most zero.
    """

    dataset: Dataset
    time_from: datetime
    time_to: datetime | None
    level_from_mwh: float
    level_to_mwh: float | None
    publish_time: datetime
    serial: int

    def __post_init__(self) -> None:
        require_utc(self.time_from, "time_from")
        require_utc(self.publish_time, "publish_time")
        if self.time_to is not None:
            require_utc(self.time_to, "time_to")
            if self.time_to <= self.time_from:
                raise InvalidRecord(f"{self.dataset}: time_to not after time_from")
        levels = [self.level_from_mwh]
        if self.level_to_mwh is not None:
            levels.append(self.level_to_mwh)
        for level in levels:
            require_finite(level, "level_mwh")
            if self.dataset == "MDO" and level < 0:
                raise InvalidRecord(f"MDO below zero: {level}")
            if self.dataset == "MDB" and level > 0:
                raise InvalidRecord(f"MDB above zero: {level}")


@dataclass(frozen=True)
class MeterPeriod:
    """One B1610 value: the unit's net metered energy in one settlement period.

    B1610 publishes one signed quantity per unit and period (ASSUMPTIONS M23).
    Export is taken as positive, pending M23's sign check. Two-way flow within the
    period is netted and cannot be recovered (ASSUMPTIONS P7).
    """

    period_start: datetime
    net_mwh: float
    run_type: str

    def __post_init__(self) -> None:
        require_utc(self.period_start, "period_start")
        on_boundary = self.period_start.minute in (0, 30)
        if not on_boundary or self.period_start.second or self.period_start.microsecond:
            raise InvalidRecord(f"period_start off a boundary: {self.period_start}")
        require_finite(self.net_mwh, "net_mwh")
        if not self.run_type.strip():
            raise InvalidRecord("run_type is empty")

    @property
    def export_mwh(self) -> float:
        """E⁺ for this period: the net value if positive, else zero (§3)."""
        return max(self.net_mwh, 0.0)

    @property
    def import_mwh(self) -> float:
        """E⁻ for this period: minus the net value if negative, else zero (§3)."""
        return max(-self.net_mwh, 0.0)


@dataclass(frozen=True)
class LevelSegment:
    """A straight-line power level from one time to another, as PN and BOALF give it.

    `acceptance_number` and `acceptance_time` are set for an accepted instruction
    (BOALF) and absent for a physical notification (PN).
    """

    time_from: datetime
    time_to: datetime
    level_from_mw: float
    level_to_mw: float
    acceptance_number: int | None = None
    acceptance_time: datetime | None = None

    def __post_init__(self) -> None:
        require_utc(self.time_from, "time_from")
        require_utc(self.time_to, "time_to")
        if self.time_to <= self.time_from:
            raise InvalidRecord("segment time_to not after time_from")
        require_finite(self.level_from_mw, "level_from_mw")
        require_finite(self.level_to_mw, "level_to_mw")
        if (self.acceptance_number is None) != (self.acceptance_time is None):
            raise InvalidRecord("acceptance number and time must come together")
        if self.acceptance_time is not None:
            require_utc(self.acceptance_time, "acceptance_time")

    def energy_mwh(self) -> float:
        """Energy under the segment: mean level times duration in hours."""
        hours = (self.time_to - self.time_from) / timedelta(hours=1)
        return 0.5 * (self.level_from_mw + self.level_to_mw) * hours


@dataclass(frozen=True)
class UnitInputs:
    """Everything the claims read for one unit, from BMRS or a synthetic battery.

    `unit_key` is an opaque label for joining and reporting; no claim may depend on
    it. `registered_mw` is GC, else |DC|, else absent (ASSUMPTIONS M16).
    """

    unit_key: str
    registered_mw: float | None
    submissions: tuple[Submission, ...]
    meter: tuple[MeterPeriod, ...]
    pn: tuple[LevelSegment, ...]
    boas: tuple[LevelSegment, ...]

    def __post_init__(self) -> None:
        if not self.unit_key.strip():
            raise InvalidRecord("unit_key is empty")
        if self.registered_mw is not None:
            require_finite(self.registered_mw, "registered_mw")
            if self.registered_mw <= 0:
                raise InvalidRecord(f"registered_mw not positive: {self.registered_mw}")
        _require_sorted([s.publish_time for s in self.submissions], "submissions")
        starts = [m.period_start for m in self.meter]
        _require_sorted(starts, "meter")
        if len(set(starts)) != len(starts):
            raise InvalidRecord("meter: two values for one settlement period")
        if any(seg.acceptance_number is not None for seg in self.pn):
            raise InvalidRecord("pn: a segment carries an acceptance")
        if any(seg.acceptance_number is None for seg in self.boas):
            raise InvalidRecord("boas: a segment has no acceptance")
        _require_sorted([s.time_from for s in self.pn], "pn")
        _require_sorted([s.time_from for s in self.boas], "boas")


def build_unit_inputs(
    unit_key: str,
    registered_mw: float | None,
    submissions: list[Submission],
    meter: list[MeterPeriod],
    pn: list[LevelSegment],
    boas: list[LevelSegment],
) -> UnitInputs:
    """Return `UnitInputs` with every collection sorted by an explicit time key.

    Ties are broken by value so that the order never depends on input order
    (CODING.md §4).
    """
    return UnitInputs(
        unit_key=unit_key,
        registered_mw=registered_mw,
        submissions=tuple(
            sorted(
                submissions,
                key=lambda s: (s.publish_time, s.serial, s.dataset, s.time_from),
            )
        ),
        meter=tuple(sorted(meter, key=lambda m: m.period_start)),
        pn=tuple(sorted(pn, key=_segment_key)),
        boas=tuple(sorted(boas, key=_segment_key)),
    )


def _segment_key(seg: LevelSegment) -> tuple[datetime, int, float, float]:
    return (
        seg.time_from,
        seg.acceptance_number or 0,
        seg.level_from_mw,
        seg.level_to_mw,
    )


def _require_sorted(times: list[datetime], name: str) -> None:
    if any(later < earlier for earlier, later in zip(times, times[1:], strict=False)):
        raise InvalidRecord(f"{name}: not sorted by time")
