"""Energy a unit protects for its PN and accepted instructions (PREREGISTRATION §3).

MDO is net of that energy (ASSUMPTIONS M12), so declared deliverable energy adds it
back over the protection horizon H:

- P^exp_t, P^imp_t: export and import energy in the PN from t to the end of H.
- B^exp_t: export energy of accepted BOAs above PN, still to be delivered from t
  to the end of H (ASSUMPTIONS M21).

H runs to the end of the settlement period containing t, plus three more (M15);
§9 repeats every flag with H = 6 hours from t.

PN and BOALF give levels in MW as straight-line segments. Energies are integrated
exactly, splitting a segment where it crosses zero. Where no PN segment covers a
time, the PN is taken as zero; where no accepted BOA covers it, no instruction
applies. Where acceptances overlap, the highest acceptance number accepted by t
gives the instructed level (PROVISIONAL: BOALF supersedes earlier acceptances).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from src.model.types import SETTLEMENT_PERIOD, LevelSegment, require_utc

HOUR = timedelta(hours=1)


def horizon_end(t: datetime, extra_periods: int) -> datetime:
    """Return the end of the settlement period containing t, plus `extra_periods`."""
    require_utc(t, "t")
    if extra_periods < 0:
        raise ValueError(f"extra_periods below zero: {extra_periods}")
    floor = t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)
    return floor + SETTLEMENT_PERIOD * (1 + extra_periods)


def positive_part_mwh(start_mw: float, end_mw: float, hours: float) -> float:
    """Return the energy above zero under a straight line from start_mw to end_mw."""
    if hours < 0:
        raise ValueError(f"negative duration: {hours}")
    if start_mw >= 0 and end_mw >= 0:
        return 0.5 * (start_mw + end_mw) * hours
    if start_mw <= 0 and end_mw <= 0:
        return 0.0
    high = max(start_mw, end_mw)
    # The line crosses zero; the area above it is a triangle of height `high`.
    return 0.5 * high * hours * high / (high - min(start_mw, end_mw))


def level_at(segment: LevelSegment, t: datetime) -> float:
    """Return a segment's level at t, by straight-line interpolation."""
    if not segment.time_from <= t <= segment.time_to:
        raise ValueError(f"{t.isoformat()} outside the segment")
    share = (t - segment.time_from) / (segment.time_to - segment.time_from)
    return segment.level_from_mw + share * (segment.level_to_mw - segment.level_from_mw)


def piece_levels(
    segments: Sequence[LevelSegment], a: datetime, b: datetime
) -> tuple[float, float] | None:
    """Return the levels at a and b of the segment covering the piece [a, b].

    The segment is the one covering the piece's midpoint, so a step change at a
    segment boundary is read from the side the piece lies on. Where segments
    overlap, the highest acceptance number wins. None means nothing covers it.
    """
    governing = _governing(segments, a + (b - a) / 2)
    if governing is None:
        return None
    return level_at(governing, a), level_at(governing, b)


def pn_protected_mwh(
    pn: Sequence[LevelSegment], t: datetime, end: datetime
) -> tuple[float, float]:
    """Return (P^exp, P^imp): PN export and import energy from t to end (§3)."""
    require_utc(end, "end")
    if end < t:
        raise ValueError("horizon ends before it starts")
    export_mwh = import_mwh = 0.0
    for a, b in _pieces([t, end, *_ends(pn)], t, end):
        hours = (b - a) / HOUR
        start_mw, end_mw = piece_levels(pn, a, b) or (0.0, 0.0)
        export_mwh += positive_part_mwh(start_mw, end_mw, hours)
        import_mwh += positive_part_mwh(-start_mw, -end_mw, hours)
    return export_mwh, import_mwh


def boa_export_mwh(
    boas: Sequence[LevelSegment],
    pn: Sequence[LevelSegment],
    t: datetime,
    end: datetime,
) -> float:
    """Return B^exp: accepted-BOA export energy above PN from t to end (§3; M21).

    Only acceptances made at or before t count: later ones were not yet known.
    """
    require_utc(end, "end")
    if end < t:
        raise ValueError("horizon ends before it starts")
    accepted = [
        s for s in boas if s.acceptance_time is not None and s.acceptance_time <= t
    ]
    total_mwh = 0.0
    for a, b in _pieces([t, end, *_ends(accepted), *_ends(pn)], t, end):
        instructed = piece_levels(accepted, a, b)
        if instructed is None:
            continue
        pn_start, pn_end = piece_levels(pn, a, b) or (0.0, 0.0)
        above_start, above_end = instructed[0] - pn_start, instructed[1] - pn_end
        total_mwh += positive_part_mwh(above_start, above_end, (b - a) / HOUR)
    return total_mwh


def _ends(segments: Sequence[LevelSegment]) -> list[datetime]:
    return [x for s in segments for x in (s.time_from, s.time_to)]


def _pieces(
    times: list[datetime], start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    cuts = sorted({x for x in times if start <= x <= end})
    return [(a, b) for a, b in zip(cuts, cuts[1:], strict=False) if b > a]


def _governing(segments: Sequence[LevelSegment], t: datetime) -> LevelSegment | None:
    covering = [s for s in segments if s.time_from <= t <= s.time_to]
    if not covering:
        return None
    return max(covering, key=lambda s: (s.acceptance_number or 0, s.time_from))
