"""The Claim 4 decomposition (src/synthetic/claim4_decomposition.py), by hand.

No band battery is simulated here; the decomposition runs once, after this commit.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.claims.claim4 import Claim4Settings
from src.claims.screens import screen_meter
from src.model.types import MeterPeriod
from src.physics.walls import cumulative_change
from src.synthetic.claim4_decomposition import (
    Tally,
    check_identity,
    classify,
    line_at_starts,
    summarise,
    tally_week,
    truth_at_starts,
)

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)
SP = timedelta(minutes=30)
C4 = Claim4Settings(0.02, 1.02)


def test_classes_are_exclusive_and_cover_every_violation() -> None:
    assert classify(1.0, 0.5) == "declaration"
    assert classify(-2.0, -3.0) == "wall"
    assert classify(0.0, -1.0) == "wall"
    assert classify(2.0, -1.0) == "both"
    with pytest.raises(ValueError):
        classify(1.0, 1.0)


def test_tally_week_by_hand() -> None:
    """Per start (declared, truth, line): excess = declared − line.

    0: (10, 9, 9.5) excess 0.5, declaration; 1: (10, 12, 9) excess 1, wall;
    2: (10, 10, 9) excess 1, wall; 3: undeclared; 4: (10, 5, 11) no violation;
    5: (10, 8, 7) excess 3, both; 6: (20, 10, 12) excess 8, declaration, large;
    7: (20, 10, 16) declaration gap 10 but excess 4, so not large.
    """
    declared: list[float | None] = [10.0, 10.0, 10.0, None, 10.0, 10.0, 20.0, 20.0]
    truth = [9.0, 12.0, 10.0, 5.0, 5.0, 8.0, 10.0, 10.0]
    line = [9.5, 9.0, 9.0, 0.0, 11.0, 7.0, 12.0, 16.0]
    active = [True, False, False, False, False, False, False, False]
    t = tally_week(declared, truth, line, active)
    assert t.periods == {"declaration": 3, "wall": 2, "both": 1}
    assert t.large == {"declaration": 1, "wall": 0, "both": 0}
    assert t.declaration_with_instruction == 1
    assert t.largest_declaration_gap_mwh == pytest.approx(10.0)
    assert t.lowest_wall_margin_mwh == pytest.approx(-3.0)
    with pytest.raises(ValueError):
        tally_week(declared, truth[:-1], line, active)


def test_tallies_add() -> None:
    a = tally_week([10.0], [9.0], [9.5], [False])
    b = tally_week([10.0], [12.0], [9.0], [False])
    a.add(b)
    assert a.periods == {"declaration": 1, "wall": 1, "both": 0}
    assert a.largest_declaration_gap_mwh == pytest.approx(1.0)
    assert a.lowest_wall_margin_mwh == pytest.approx(-3.0)


def test_line_at_starts() -> None:
    """K 0, 8, 8, 0 at four boundaries; N 100: wall 92, 100, 100, 92; three starts."""
    assert line_at_starts([0.0, 8.0, 8.0, 0.0], 100.0, 0.02) == pytest.approx(
        [94.0, 102.0, 102.0]
    )


def test_truth_at_starts() -> None:
    stored = np.arange(100, dtype=float)
    boa = np.full(100, -1, dtype=np.int64)
    boa[40] = 3
    truth, active = truth_at_starts(stored, boa, 10, 0.81, periods=3)
    assert truth == pytest.approx([9.0, 36.0, 63.0])
    assert active == [False, True, False]


def test_identity_holds_and_a_wrong_line_is_caught() -> None:
    meter = screen_meter(
        [
            MeterPeriod(WEEK0 + h * SP, {2: -10.0, 4: 8.0}.get(h, 0.0), "SF")
            for h in range(336)
        ],
        WEEK0,
        frozenset({"SF"}),
    )
    k = cumulative_change(meter.periods, 0.8)
    line = line_at_starts(k, 100.0, 0.02)
    declared: list[float | None] = [95.0] * 336
    declared[7] = None
    truth = [90.0] * 336
    check_identity(declared, truth, line, meter, 0.8, 100.0, C4)
    with pytest.raises(AssertionError):
        check_identity(declared, truth, [x + 1.0 for x in line], meter, 0.8, 100.0, C4)


def run(large: dict[str, int]) -> dict[str, Tally]:
    true = Tally()
    true.large.update(large)
    true.periods.update(large)
    return {"estimated": Tally(), "true": true}


@pytest.mark.parametrize(
    ("large", "reading", "share"),
    [
        ({"declaration": 8, "wall": 2}, "declaration", 0.8),
        ({"declaration": 7, "wall": 3}, "mixed", 0.7),
        ({"wall": 9, "both": 1}, "wall", 0.9),
        ({}, "no large violations", None),
    ],
)
def test_reading_is_fixed_before_the_run(
    large: dict[str, int], reading: str, share: float | None
) -> None:
    s = summarise([run(large)])
    assert s["reading"] == reading
    assert s["true_leading_share"] == (None if share is None else pytest.approx(share))
