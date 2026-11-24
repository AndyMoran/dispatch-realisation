"""Fleet figures from unit results: pure functions, no data access.

Readings fixed in PROJECT.md §11 (23 Nov 2026, `v1.0.6-lock`, and the `score` row):

- A unit enters a claim's fleet figures if it has at least `min_weeks` scored weeks
  for that claim (PREREGISTRATION §2, 4 weeks).
- A distribution reports the 10th, 25th, 50th, 75th and 90th percentiles of unit
  scores (numpy's linear method) and the number of units.
- Every public figure from unit scores covers at least 5 units (deviation 8). A
  cell below that is suppressed. Where a partition is published with its total,
  a single suppressed cell would follow by subtraction, so the smallest other
  cell is suppressed too (complementary suppression). In doubt, withhold.
- Claim 2's fleet share in a group is the share of settlement periods in
  violation, pooled over every scored week of the group's units; unit scores'
  quartiles describe the spread. Groups: 4–7, 8–11, 12–15 and 16–20 Claim 2
  scored weeks, each beside the honest battery's false-flag rate at the group's
  shortest length, labelled as a synthetic reference with its runs and a 95%
  Wilson interval.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median

import numpy as np

from src.claims.results import WeekResult

QUANTILES = ((10, "p10"), (25, "p25"), (50, "p50"), (75, "p75"), (90, "p90"))
QUARTILES = ((25, "p25"), (50, "p50"), (75, "p75"))
MIN_CELL = 5
LENGTH_GROUPS = ((4, 7), (8, 11), (12, 15), (16, 20))  # PROJECT.md §11, 23 Nov 2026
SUPPRESSED = "suppressed: fewer than 5 units, or to protect another cell"
REFERENCE_LABEL = "synthetic reference, not a matched comparator"
Z95 = 1.959963984540054
PROVABLE = "provable under-declaration"  # Claim 2's flag in claims12_known.json
CLAIM2_OUTCOMES = frozenset({PROVABLE, "none detected"})  # src/claims/scoring.py


def percentiles(
    values: Sequence[float], which: Sequence[tuple[int, str]] = QUANTILES
) -> dict[str, float]:
    """Return the named percentiles of the values (linear method)."""
    if not values:
        raise ValueError("no values")
    got = np.percentile(np.asarray(values, dtype=float), [q for q, _ in which])
    return {name: float(v) for (_, name), v in zip(which, got, strict=True)}


def distribution(values: Sequence[float]) -> dict[str, object]:
    """Return a cell: the unit count and percentiles, or the count and suppression."""
    if len(values) < MIN_CELL:
        return {"units": len(values), "suppressed": SUPPRESSED}
    return {"units": len(values), **percentiles(values)}


def is_suppressed(cell: Mapping[str, object]) -> bool:
    """Return whether a cell has been withheld."""
    return "suppressed" in cell


def suppress(cell: Mapping[str, object]) -> dict[str, object]:
    """Return the cell with every figure withheld; the unit count stays."""
    return {"units": cell.get("units"), "suppressed": SUPPRESSED}


def complementary(
    cells: Mapping[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Return cells of a partition published with its total, protected by subtraction.

    If exactly one cell is suppressed, the smallest other cell is suppressed too.
    """
    out = {k: dict(v) for k, v in cells.items()}
    hidden = [k for k, v in out.items() if is_suppressed(v)]
    if len(hidden) == 1:
        rest = [k for k in out if k not in hidden]
        if rest:
            smallest = min(rest, key=lambda k: (int(str(out[k]["units"])), k))
            out[smallest] = suppress(out[smallest])
    return out


def unit_median(weeks: Sequence[WeekResult]) -> float | None:
    """Return the median of the scored weeks' ratios (the unit score, §4)."""
    scores = [w.score for w in weeks if w.score is not None]
    return median(s for s in scores if s is not None) if scores else None


def scored_count(weeks: Sequence[WeekResult]) -> int:
    """Return how many weeks have a score."""
    return sum(1 for w in weeks if w.score is not None)


def pooled(weeks: Sequence[WeekResult]) -> tuple[float, float]:
    """Return the summed numerator and denominator over the scored weeks."""
    num = den = 0.0
    for w in weeks:
        if w.score is None:
            continue
        num += sum(p.numerator for p in w.parts)
        den += sum(p.denominator for p in w.parts)
    return num, den


def length_group(weeks: int) -> tuple[int, int] | None:
    """Return the fixed length group a scored-week count falls in, if any."""
    for low, high in LENGTH_GROUPS:
        if low <= weeks <= high:
            return low, high
    return None


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Return the Wilson score interval for k successes in n trials."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError(f"bad counts: {k} of {n}")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    low = 0.0 if k == 0 else max(0.0, centre - half)
    high = 1.0 if k == n else min(1.0, centre + half)
    return low, high


def honest_reference(
    known: Mapping[str, object], branch: str, weeks: int
) -> dict[str, object] | None:
    """Return the honest battery's Claim 2 false-flag rate at `weeks`, for `branch`.

    Read from the known-answer results (`claims12_known.json`): the matched pair,
    declared and scored under the same branch. None if that length was not tested.
    """
    lengths = known.get("lengths")
    cells = known.get("cells")
    if not isinstance(lengths, list) or not isinstance(cells, list):
        raise ValueError("known-answer results lack lengths or cells")
    key = next((x["length"] for x in lengths if x.get("scored_weeks") == weeks), None)
    if key is None:
        return None
    for c in cells:
        if (
            c.get("battery") == "honest"
            and c.get("claim") == "claim2"
            and c.get("length") == key
            and c.get("declared") == branch
            and c.get("scored") == branch
        ):
            counts = c["counts"]
            unknown = set(counts) - CLAIM2_OUTCOMES
            # Runs are the sum of the outcome counts, so each run must have
            # exactly one known outcome; a new outcome name needs a code change.
            if unknown:  # a renamed outcome would otherwise read as zero flags
                raise ValueError(f"unknown Claim 2 outcomes: {sorted(unknown)}")
            runs = int(sum(counts.values()))
            flagged = int(counts.get(PROVABLE, 0))  # the file omits zero counts
            low, high = wilson(flagged, runs)
            return {
                "label": REFERENCE_LABEL,
                "scored_weeks": weeks,
                "runs": runs,
                "flagged": flagged,
                "rate": flagged / runs,
                "wilson_95": [low, high],
            }
    raise ValueError(f"no honest Claim 2 cell at {weeks} weeks, branch {branch}")


def slope_through_origin(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Return the least-squares slope of y on x through the origin; None if Σx² = 0."""
    if len(x) != len(y):
        raise ValueError("x and y differ in length")
    sxx = sum(a * a for a in x)
    sxy = sum(a * b for a, b in zip(x, y, strict=True))
    if not (math.isfinite(sxx) and math.isfinite(sxy)):
        raise ValueError("non-finite values in the slope's points")
    if sxx <= 0:
        return None
    slope = sxy / sxx
    if not math.isfinite(slope):  # a tiny Σx² can overflow the division
        raise ValueError("non-finite slope")
    return slope
