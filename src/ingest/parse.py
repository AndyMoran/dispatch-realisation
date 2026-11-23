"""Raw pull responses to the model's types, by the field mapping of 23 Nov 2026.

PROJECT.md §11 fixes the mapping from the probes. Each parser returns the records
it built, grouped by `bmUnit`, and a count of the rows it could not use, by
reason (PIPELINE_RULES §2–3): a row the model rejects is excluded and counted,
never dropped silently.

Exact duplicate rows are removed first: MDO and MDB chunks are timestamp ranges
inclusive at both ends, so neighbouring days share their boundary rows (R12a).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.model.types import (
    Dataset,
    InvalidRecord,
    LevelSegment,
    MeterPeriod,
    Submission,
)

Row = Mapping[str, object]


@dataclass
class Parsed[T]:
    """Records by unit, and excluded rows counted by reason."""

    by_unit: dict[str, list[T]] = field(default_factory=dict)
    excluded: Counter[str] = field(default_factory=Counter)
    duplicates: int = 0

    def add(self, unit: str, record: T) -> None:
        """File one record under its unit."""
        self.by_unit.setdefault(unit, []).append(record)

    @property
    def records(self) -> int:
        """Return how many records were built."""
        return sum(len(v) for v in self.by_unit.values())


class FieldError(ValueError):
    """A row lacks a mapped field, or holds it in the wrong form."""


def unique_rows(rows: Iterable[Row]) -> tuple[list[Row], int]:
    """Return the rows with exact duplicates removed, and how many were removed."""
    seen: set[str] = set()
    out: list[Row] = []
    dupes = 0
    for r in rows:
        key = json.dumps(r, sort_keys=True)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        out.append(r)
    return out, dupes


def text(row: Row, name: str) -> str:
    """Return a field that must be a non-empty string."""
    v = row.get(name)
    if not isinstance(v, str) or not v:
        raise FieldError(f"{name} missing or not text")
    return v


def number(row: Row, name: str) -> float:
    """Return a field that must be a number (not a boolean)."""
    v = row.get(name)
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise FieldError(f"{name} missing or not a number")
    return float(v)


def whole(row: Row, name: str) -> int:
    """Return a field that must be a whole number, given as a number or as text.

    MDO and MDB give `serialNumber` as text (probe, 23 Nov 2026); any form other
    than digits stops the row.
    """
    v = row.get(name)
    if isinstance(v, bool):
        raise FieldError(f"{name} is a boolean")
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    raise FieldError(f"{name} missing or not a whole number")


def instant(row: Row, name: str) -> datetime:
    """Return a field that must be a timestamp with a UTC offset of zero."""
    raw = text(row, name)
    try:
        t = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise FieldError(f"{name} not a timestamp") from exc
    if t.tzinfo is None or t.utcoffset() != UTC.utcoffset(None):
        raise FieldError(f"{name} not in UTC")
    return t.astimezone(UTC)


def parse_submissions(dataset: Dataset, rows: Iterable[Row]) -> Parsed[Submission]:
    """MDO or MDB rows to `Submission`s, by unit."""
    out: Parsed[Submission] = Parsed()
    kept, out.duplicates = unique_rows(rows)
    for r in kept:
        try:
            unit = text(r, "bmUnit")
            level_to = None if r.get("levelTo") is None else number(r, "levelTo")
            time_to = None if r.get("timeTo") is None else instant(r, "timeTo")
            sub = Submission(
                dataset=dataset,
                time_from=instant(r, "timeFrom"),
                time_to=time_to,
                level_from_mwh=number(r, "levelFrom"),
                level_to_mwh=level_to,
                publish_time=instant(r, "publishTime"),
                serial=whole(r, "serialNumber"),
            )
        except (FieldError, InvalidRecord) as exc:
            out.excluded[f"{dataset}: {exc}"] += 1
            continue
        out.add(unit, sub)
    return out


def parse_segments(kind: str, rows: Iterable[Row]) -> Parsed[LevelSegment]:
    """PN or BOALF rows to `LevelSegment`s, by unit.

    A zero-length row carries no energy and no duration, so it is excluded and
    counted under its own reason, never filed.
    """
    if kind not in ("PN", "BOALF"):
        raise ValueError(f"not a segment dataset: {kind}")
    out: Parsed[LevelSegment] = Parsed()
    kept, out.duplicates = unique_rows(rows)
    for r in kept:
        try:
            unit = text(r, "bmUnit")
            start, end = instant(r, "timeFrom"), instant(r, "timeTo")
            if end == start:
                out.excluded[f"{kind}: zero length"] += 1
                continue
            number_, accepted = (
                (whole(r, "acceptanceNumber"), instant(r, "acceptanceTime"))
                if kind == "BOALF"
                else (None, None)
            )
            seg = LevelSegment(
                start,
                end,
                number(r, "levelFrom"),
                number(r, "levelTo"),
                number_,
                accepted,
            )
        except (FieldError, InvalidRecord) as exc:
            out.excluded[f"{kind}: {exc}"] += 1
            continue
        out.add(unit, seg)
    return out


def parse_meter(rows: Iterable[Row]) -> Parsed[MeterPeriod]:
    """B1610 rows to `MeterPeriod`s, by unit; every run type kept (M6).

    The period starts 30 minutes before `halfHourEndTime`. Choosing the latest SF
    or later run per period is the scoring run's job, not the parser's.
    """
    out: Parsed[MeterPeriod] = Parsed()
    kept, out.duplicates = unique_rows(rows)
    for r in kept:
        try:
            unit = text(r, "bmUnit")
            period = MeterPeriod(
                instant(r, "halfHourEndTime") - timedelta(minutes=30),
                number(r, "quantity"),
                text(r, "settlementRunType"),
            )
        except (FieldError, InvalidRecord) as exc:
            out.excluded[f"B1610: {exc}"] += 1
            continue
        out.add(unit, period)
    return out
