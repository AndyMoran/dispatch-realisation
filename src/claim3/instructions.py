"""Claim 3, per instruction: A, D, the baseline, r and ρ (PREREGISTRATION §5.1–§5.3).

Readings and conventions fixed in PROJECT.md §11 (21 Nov 2026) before this code:

- A: the integral of the governing BOALF level (M24) minus PN over the
  instruction's delivery.
- D: Σ (B1610 net − PN energy) over the instruction's settlement periods, minus
  the frequency-response baseline.
- Baseline: for each spanned period, the median (metered − PN) over BOA-free
  periods of the same ISO week at the same UK local clock time, the two
  occurrences of the repeated autumn hour kept apart; scaled by the instruction's
  minutes in that period ÷ 30; summed. No observations: the instruction is
  excluded, and counted.
- r: |A| ÷ the declaration as published before acceptance (M9, restricted to
  submissions published strictly before the acceptance time, read at the
  acceptance minute). Offers: MDO, Branch B √η̂ × MDO. Bids: |MDB|, Branch B
  |MDB| ÷ √η̂ (§3).
- Screens: no other acceptance in any spanned period; |A| ≥ 1 MWh; the meter
  present (SF or later) in every spanned period.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Literal
from zoneinfo import ZoneInfo

from src.model.types import LevelSegment, MeterPeriod, Submission, UnitInputs
from src.physics.declared import Branch, declared_at, record_level
from src.physics.protection import piece_levels

UK = ZoneInfo("Europe/London")
PERIOD = timedelta(minutes=30)
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)

Side = Literal["offer", "bid"]

OTHER_BOA = "another acceptance in its periods"
BELOW_FLOOR = "accepted energy below the floor"
NO_METER = "meter missing or before SF in a spanned period"
NO_BASELINE = "no BOA-free observation for the baseline"
NO_DECLARATION = "no declaration published before acceptance"


@dataclass(frozen=True)
class Instruction:
    """One acceptance: its delivery, its accepted energy and its periods."""

    number: int
    accepted: datetime
    start: datetime
    end: datetime
    a_mwh: float
    periods: tuple[datetime, ...]

    @property
    def side(self) -> Side:
        """Return "offer" for energy above PN, "bid" for energy below it."""
        return "offer" if self.a_mwh > 0 else "bid"


@dataclass(frozen=True)
class Measured:
    """One instruction's Claim 3 quantities, or why it was excluded."""

    instruction: Instruction
    excluded: str | None
    d_mwh: float | None = None
    declared_mwh: float | None = None
    r: float | None = None
    rho: float | None = None

    @property
    def side(self) -> Side:
        """Return the instruction's side."""
        return self.instruction.side


def period_floor(t: datetime) -> datetime:
    """Return the start of the settlement period containing t (UTC)."""
    return t - timedelta(
        minutes=t.minute % 30, seconds=t.second, microseconds=t.microsecond
    )


class SegmentIndex:
    """Segments sorted by start (stably), to find those touching an interval.

    Only segments with time_from ≤ b and time_to ≥ a can cover a point of [a, b]
    or cut it, and filtering keeps their order, so every result below is the same
    with the index as with the full list; the index only saves time.
    """

    def __init__(self, segments: Sequence[LevelSegment]) -> None:
        self.original = tuple(segments)
        self.order = sorted(
            range(len(self.original)), key=lambda k: self.original[k].time_from
        )
        self.starts = [self.original[k].time_from for k in self.order]
        self.longest = max(
            (s.time_to - s.time_from for s in self.original), default=timedelta(0)
        )

    def touching(self, a: datetime, b: datetime) -> list[LevelSegment]:
        """Return every segment with time_from ≤ b and time_to ≥ a, in list order."""
        lo = bisect.bisect_left(self.starts, a - self.longest)
        hi = bisect.bisect_right(self.starts, b)
        found = sorted(k for k in self.order[lo:hi] if self.original[k].time_to >= a)
        return [self.original[k] for k in found]


Segments = Sequence[LevelSegment] | SegmentIndex


def _near(segments: Segments, a: datetime, b: datetime) -> Sequence[LevelSegment]:
    return segments.touching(a, b) if isinstance(segments, SegmentIndex) else segments


def segment_integral_mwh(segments: Segments, a: datetime, b: datetime) -> float:
    """Return the signed energy of piecewise-linear levels over [a, b], MWh.

    The governing segment covers each piece (M24); uncovered time counts as zero.
    """
    segments = _near(segments, a, b)
    cuts = sorted({a, b, *(x for s in segments for x in (s.time_from, s.time_to))})
    total = 0.0
    for lo, hi in zip(cuts, cuts[1:], strict=False):
        if lo < a or hi > b or hi <= lo:
            continue
        levels = piece_levels(segments, lo, hi)
        if levels is not None:
            total += 0.5 * (levels[0] + levels[1]) * ((hi - lo) / HOUR)
    return total


def deviation_mwh(boas: Segments, pn: Segments, a: datetime, b: datetime) -> float:
    """Return ∫ (governing BOALF level − PN) over [a, b] where an acceptance governs."""
    boas, pn = _near(boas, a, b), _near(pn, a, b)
    cuts = sorted({a, b, *(x for s in [*boas, *pn] for x in (s.time_from, s.time_to))})
    total = 0.0
    for lo, hi in zip(cuts, cuts[1:], strict=False):
        if lo < a or hi > b or hi <= lo:
            continue
        instructed = piece_levels(boas, lo, hi)
        if instructed is None:
            continue
        pn0, pn1 = piece_levels(pn, lo, hi) or (0.0, 0.0)
        hours = (hi - lo) / HOUR
        total += 0.5 * ((instructed[0] - pn0) + (instructed[1] - pn1)) * hours
    return total


def instructions(unit: UnitInputs) -> tuple[Instruction, ...]:
    """Return every acceptance in the unit's BOALF, with A and its periods (§5.1)."""
    by_number: dict[int, list[LevelSegment]] = defaultdict(list)
    for s in unit.boas:
        if s.acceptance_number is not None and s.acceptance_time is not None:
            by_number[s.acceptance_number].append(s)
    boas, pn = SegmentIndex(unit.boas), SegmentIndex(unit.pn)
    out = []
    for number, segs in sorted(by_number.items()):
        start = min(s.time_from for s in segs)
        end = max(s.time_to for s in segs)
        accepted = min(s.acceptance_time for s in segs if s.acceptance_time)
        first, periods = period_floor(start), []
        while first < end:
            periods.append(first)
            first += PERIOD
        out.append(
            Instruction(
                number,
                accepted,
                start,
                end,
                deviation_mwh(boas, pn, start, end),
                tuple(periods),
            )
        )
    return tuple(out)


def clock_key(period_start: datetime) -> tuple[int, int, int]:
    """Return UK local (hour, minute, fold): the repeated autumn hour is two keys."""
    local = period_start.astimezone(UK)
    return local.hour, local.minute, local.fold


def iso_week(period_start: datetime) -> datetime:
    """Return the Monday 00:00 UTC that starts the period's ISO week."""
    day = period_start - timedelta(
        days=period_start.weekday(),
        hours=period_start.hour,
        minutes=period_start.minute,
        seconds=period_start.second,
        microseconds=period_start.microsecond,
    )
    return day


@dataclass(frozen=True)
class Baselines:
    """BOA-free (metered − PN) by ISO week and UK clock time, for §5.3."""

    values: dict[tuple[datetime, tuple[int, int, int]], list[float]]

    def median_mwh(self, period_start: datetime) -> float | None:
        """Return the median for the period's week and clock time; None if none."""
        found = self.values.get((iso_week(period_start), clock_key(period_start)))
        return median(found) if found else None


def baselines(
    meter: Sequence[MeterPeriod],
    pn: Sequence[LevelSegment],
    boas: Sequence[LevelSegment],
    sf_or_later: Collection[str],
) -> Baselines:
    """Return the BOA-free observations the baseline medians draw on."""
    busy = {p for s in boas for p in _periods_overlapping(s.time_from, s.time_to)}
    pn_index = SegmentIndex(pn)
    values: dict[tuple[datetime, tuple[int, int, int]], list[float]] = defaultdict(list)
    for m in meter:
        if m.period_start in busy or m.run_type not in sf_or_later:
            continue
        pn_mwh = segment_integral_mwh(pn_index, m.period_start, m.period_start + PERIOD)
        key = (iso_week(m.period_start), clock_key(m.period_start))
        values[key].append(m.net_mwh - pn_mwh)
    return Baselines(dict(values))


def _periods_overlapping(a: datetime, b: datetime) -> list[datetime]:
    out, p = [], period_floor(a)
    while p < b:
        out.append(p)
        p += PERIOD
    return out


@dataclass(frozen=True)
class _Published:
    """Submissions sorted by publish time, for "published before acceptance".

    `by_start` holds, per dataset, (time_from, position in `records`, record)
    sorted by start, with the longest record's span. It is used only when every
    record of the dataset has a time_to, so that where a record ends depends on
    no other record (M9; `record_ends`).
    """

    records: tuple[Submission, ...]
    publish: list[datetime]
    by_start: dict[str, tuple[list[datetime], list[tuple[int, Submission]], timedelta]]


def _published(submissions: Sequence[Submission]) -> _Published:
    ordered = tuple(sorted(submissions, key=lambda s: (s.publish_time, s.serial)))
    by_start = {}
    for dataset in ("MDO", "MDB"):
        rows = [
            (r.time_from, k, r) for k, r in enumerate(ordered) if r.dataset == dataset
        ]
        if any(r.time_to is None for _, _, r in rows):
            continue
        rows.sort(key=lambda row: (row[0], row[1]))
        longest = max(
            (r.time_to - r.time_from for _, _, r in rows if r.time_to),
            default=timedelta(0),
        )
        by_start[dataset] = (
            [t for t, _, _ in rows],
            [(k, r) for _, k, r in rows],
            longest,
        )
    return _Published(ordered, [s.publish_time for s in ordered], by_start)


def declared_before(
    published: _Published,
    side: Side,
    accepted: datetime,
    default_abs_mwh: float,
    data_end: datetime,
) -> float | None:
    """Return MDO (offers) or |MDB| (bids) as published before acceptance (M22)."""
    cut = bisect.bisect_left(published.publish, accepted)
    minute = accepted.replace(second=0, microsecond=0)
    dataset: Literal["MDO", "MDB"] = "MDO" if side == "offer" else "MDB"
    if dataset in published.by_start:
        value = _latest_covering(
            published, dataset, cut, minute, default_abs_mwh, data_end
        )
    else:
        known = published.records[:cut]
        (value,) = declared_at(known, dataset, [minute], default_abs_mwh, data_end)
    return None if value is None else abs(value)


def _latest_covering(
    published: _Published,
    dataset: str,
    cut: int,
    minute: datetime,
    default_abs_mwh: float,
    data_end: datetime,
) -> float | None:
    """`declared_at` for one minute, when every record has a time_to: the record
    painted last among those published before `cut` that cover `minute` wins."""
    starts, rows, longest = published.by_start[dataset]
    lo = bisect.bisect_left(starts, minute - longest)
    hi = bisect.bisect_right(starts, minute)
    best: tuple[tuple[datetime, int, datetime, int], Submission, datetime] | None = None
    for k, record in rows[lo:hi]:
        if k >= cut:
            continue
        assert record.time_to is not None
        end = min(record.time_to, data_end)
        if not record.time_from <= minute < end:
            continue
        key = (record.publish_time, record.serial, record.time_from, k)
        if best is None or key > best[0]:
            best = (key, record, end)
    if best is None:
        return None
    level = record_level(best[1], minute, best[2])
    return None if abs(level) >= default_abs_mwh else level


def measure(
    unit: UnitInputs,
    items: Sequence[Instruction],
    eta: float,
    branch: Branch,
    min_accepted_mwh: float,
    default_abs_mwh: float,
    data_end: datetime,
    sf_or_later: Collection[str],
) -> tuple[Measured, ...]:
    """Return each instruction's D, declared energy, r and ρ, or its exclusion."""
    meter = {m.period_start: m for m in unit.meter}
    base = baselines(unit.meter, unit.pn, unit.boas, sf_or_later)
    published = _published(unit.submissions)
    root = math.sqrt(eta)
    boas, pn = SegmentIndex(unit.boas), SegmentIndex(unit.pn)
    out = []
    for ins in items:
        others = [
            s
            for s in boas.touching(ins.periods[0], ins.periods[-1] + PERIOD)
            if s.acceptance_number != ins.number
            and s.time_from < ins.periods[-1] + PERIOD
            and s.time_to > ins.periods[0]
        ]
        if others:
            out.append(Measured(ins, OTHER_BOA))
            continue
        if abs(ins.a_mwh) < min_accepted_mwh:
            out.append(Measured(ins, BELOW_FLOOR))
            continue
        rows = [meter.get(p) for p in ins.periods]
        if any(r is None or r.run_type not in sf_or_later for r in rows):
            out.append(Measured(ins, NO_METER))
            continue
        delivered = 0.0
        missing_baseline = False
        for p, row in zip(ins.periods, rows, strict=True):
            assert row is not None
            pn_mwh = segment_integral_mwh(pn, p, p + PERIOD)
            share = _overlap(ins.start, ins.end, p, p + PERIOD) / PERIOD
            typical = base.median_mwh(p)
            if typical is None:
                missing_baseline = True
                break
            delivered += row.net_mwh - pn_mwh - typical * share
        if missing_baseline:
            out.append(Measured(ins, NO_BASELINE))
            continue
        declared = declared_before(
            published, ins.side, ins.accepted, default_abs_mwh, data_end
        )
        if declared is None:
            out.append(Measured(ins, NO_DECLARATION))
            continue
        if ins.side == "offer":
            effective = declared if branch == "A" else root * declared
        else:
            effective = declared if branch == "A" else declared / root
        r = abs(ins.a_mwh) / effective if effective > 0 else math.inf
        out.append(Measured(ins, None, delivered, effective, r, delivered / ins.a_mwh))
    return tuple(out)


def _overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> timedelta:
    return max(min(a1, b1) - max(a0, b0), timedelta(0))
