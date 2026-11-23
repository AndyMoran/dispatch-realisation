"""Declarations in force, and declared deliverable energy (PREREGISTRATION §3).

The declaration in force at time t is the latest record covering t, latest by
publish time, then serial number, then start time (ASSUMPTIONS M9). A record runs
from time_from to time_to; without time_to it holds until the next record of its
own submission, else the unit's next record of any submission, else `data_end`.
These rules match src/ingest/power_bound.py, which produced the lock outputs.

One difference: a default record (|level| ≥ the default, ±9999 MWh; R13) means
"no declaration" for the time it covers, instead of being dropped. A unit that
reverts to defaults then has no declaration in force, rather than an older value
showing through (§2: reverting to defaults is a data-quality finding).

Declared deliverable energy, with PN and accepted-BOA protection added back:

    Branch A:  D^decl_t = MDO_t + P^exp_t + B^exp_t
    Branch B:  D^decl_t = √η̂ · MDO_t + P^exp_t + B^exp_t

Branch A reads MDO as export energy at the meter; Branch B as stored energy
(ASSUMPTIONS M13). Every result is computed under both.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from src.model.types import Dataset, Submission, require_utc

Branch = Literal["A", "B"]


def record_level(record: Submission, t: datetime, end: datetime) -> float:
    """Return a record's level at t, moving in a straight line over [time_from, end]."""
    if not record.time_from <= t < end:
        raise ValueError(f"{t.isoformat()} outside the record")
    if record.level_to_mwh is None:
        return record.level_from_mwh
    share = (t - record.time_from) / (end - record.time_from)
    return record.level_from_mwh + share * (record.level_to_mwh - record.level_from_mwh)


def record_ends(
    records: Sequence[Submission], data_end: datetime
) -> dict[Submission, datetime]:
    """Return where each record stops holding (M9; power_bound.py rule)."""
    starts = sorted({r.time_from for r in records})
    next_any = dict(zip(starts, starts[1:], strict=False))
    by_submission: dict[tuple[datetime, int], list[datetime]] = defaultdict(list)
    for r in records:
        by_submission[(r.publish_time, r.serial)].append(r.time_from)
    next_own: dict[tuple[tuple[datetime, int], datetime], datetime] = {}
    for key, own in by_submission.items():
        ordered = sorted(set(own))
        next_own.update(
            {(key, a): b for a, b in zip(ordered, ordered[1:], strict=False)}
        )
    ends: dict[Submission, datetime] = {}
    for r in records:
        hold = next_own.get(((r.publish_time, r.serial), r.time_from))
        hold = hold or next_any.get(r.time_from, data_end)
        ends[r] = min(r.time_to or hold, data_end)
    return ends


def declared_at(
    submissions: Sequence[Submission],
    dataset: Dataset,
    times: Sequence[datetime],
    default_abs_mwh: float,
    data_end: datetime,
) -> tuple[float | None, ...]:
    """Return the `dataset` level in force at each time; None where none is.

    None covers both "no record covers t" and "a default record covers t".
    """
    require_utc(data_end, "data_end")
    if default_abs_mwh <= 0:
        raise ValueError(f"default threshold not positive: {default_abs_mwh}")
    ordered_times = sorted(times)
    if list(times) != ordered_times:
        raise ValueError("times must be sorted")
    records = [s for s in submissions if s.dataset == dataset]
    ends = record_ends(records, data_end)
    values: list[float | None] = [None] * len(ordered_times)
    # Paint records in priority order, so the latest record wins each time (M9).
    for record in sorted(
        records, key=lambda r: (r.publish_time, r.serial, r.time_from)
    ):
        end = ends[record]
        lo = bisect.bisect_left(ordered_times, record.time_from)
        hi = bisect.bisect_left(ordered_times, end)
        for i in range(lo, hi):
            level = record_level(record, ordered_times[i], end)
            values[i] = None if abs(level) >= default_abs_mwh else level
    return tuple(values)


def in_force_publish_times(
    submissions: Sequence[Submission],
    dataset: Dataset,
    times: Sequence[datetime],
    default_abs_mwh: float,
    data_end: datetime,
) -> tuple[datetime | None, ...]:
    """Return the publish time of the `dataset` record in force at each time.

    Chosen exactly as `declared_at` chooses the level (M9), so it is None wherever
    `declared_at` gives None (§12, deviation 5).
    """
    require_utc(data_end, "data_end")
    if default_abs_mwh <= 0:
        raise ValueError(f"default threshold not positive: {default_abs_mwh}")
    ordered_times = sorted(times)
    if list(times) != ordered_times:
        raise ValueError("times must be sorted")
    records = [s for s in submissions if s.dataset == dataset]
    ends = record_ends(records, data_end)
    out: list[datetime | None] = [None] * len(ordered_times)
    for record in sorted(
        records, key=lambda r: (r.publish_time, r.serial, r.time_from)
    ):
        end = ends[record]
        lo = bisect.bisect_left(ordered_times, record.time_from)
        hi = bisect.bisect_left(ordered_times, end)
        for i in range(lo, hi):
            level = record_level(record, ordered_times[i], end)
            out[i] = None if abs(level) >= default_abs_mwh else record.publish_time
    return tuple(out)


def declared_deliverable_mwh(
    mdo_mwh: float, p_exp_mwh: float, b_exp_mwh: float, eta: float, branch: Branch
) -> float:
    """Return D^decl_t under Branch A or B (§3; M13)."""
    for name, value in (("MDO", mdo_mwh), ("P^exp", p_exp_mwh), ("B^exp", b_exp_mwh)):
        if value < 0 or not math.isfinite(value):
            raise ValueError(f"{name} must be finite and at least zero: {value}")
    if not 0 < eta <= 1:
        raise ValueError(f"η̂ outside (0, 1]: {eta}")
    deliverable = mdo_mwh if branch == "A" else math.sqrt(eta) * mdo_mwh
    return deliverable + p_exp_mwh + b_exp_mwh
