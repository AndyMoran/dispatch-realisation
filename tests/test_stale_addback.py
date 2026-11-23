"""The stale add-back diagnostic (src/synthetic/stale_addback.py), by hand.

No band battery is simulated here; each stage runs once, after this commit.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.claims import unit as unit_module
from src.claims.declared_series import declared_series
from src.model.types import LevelSegment, Submission, build_unit_inputs
from src.synthetic import stale_addback as sa
from src.synthetic.bands import RunOutcome
from src.synthetic.stale_addback import (
    StageA,
    StageB,
    changed_runs,
    declared_series_corrected,
    in_force_publish_times,
    same_cells,
    summarise_a,
)

WEEK0 = datetime(2026, 11, 2, tzinfo=UTC)
END = WEEK0 + timedelta(days=7)
MIN = timedelta(minutes=1)


def boa(accepted_min: int, start_min: int = 10, end_min: int = 70) -> LevelSegment:
    """20 MW export from start to end, accepted at `accepted_min` (PN is zero)."""
    return LevelSegment(
        WEEK0 + start_min * MIN,
        WEEK0 + end_min * MIN,
        20.0,
        20.0,
        1,
        WEEK0 + accepted_min * MIN,
    )


ROUTINE = Submission("MDO", WEEK0, END, 40.0, None, WEEK0, 1)
REDECLARED = Submission("MDO", WEEK0 + 11 * MIN, END, 20.0, None, WEEK0 + 11 * MIN, 1)


def d(records: list[Submission], boas: list[LevelSegment], at_min: int) -> tuple:
    u = build_unit_inputs("u", None, records, [], [], boas)
    t = [WEEK0 + at_min * MIN]
    args = (0.8, "A", 3, None, 9999.0, END)
    return (
        declared_series(u, t, *args)[0],  # type: ignore[arg-type]
        declared_series_corrected(u, t, *args)[0],  # type: ignore[arg-type]
    )


def test_publish_time_of_the_record_in_force() -> None:
    times = [WEEK0 + m * MIN for m in (0, 10, 11, 20)]
    got = in_force_publish_times([ROUTINE, REDECLARED], "MDO", times, 9999.0, END)
    assert got == (WEEK0, WEEK0, WEEK0 + 11 * MIN, WEEK0 + 11 * MIN)
    default = Submission("MDO", WEEK0, END, 9999.0, None, WEEK0 + MIN, 1)
    assert in_force_publish_times([default], "MDO", times[:1], 9999.0, END) == (None,)
    with pytest.raises(ValueError):
        in_force_publish_times([ROUTINE], "MDO", times[::-1], 9999.0, END)


def test_stale_declaration_counts_the_instruction_twice() -> None:
    """MDO 40 published at 0; 20 MW from minute 10 to 70, accepted at 10.

    At minute 30 the horizon reaches past minute 70, so B^exp = 20 × 40/60 =
    13.33 MWh. The original rule adds it to the stale 40; the corrected rule does
    not, because the instruction came after the record was published.
    """
    original, corrected = d([ROUTINE], [boa(10)], 30)
    assert original == pytest.approx(40.0 + 40.0 / 3.0)
    assert corrected == pytest.approx(40.0)


def test_after_redeclaration_both_rules_agree() -> None:
    """A record published at minute 11 knows the instruction: both add it back."""
    original, corrected = d([ROUTINE, REDECLARED], [boa(10)], 30)
    assert original == corrected == pytest.approx(20.0 + 40.0 / 3.0)


def test_earlier_acceptance_is_added_back_and_same_minute_is_not() -> None:
    before = d([ROUTINE], [boa(-5)], 30)
    assert before[0] == before[1]
    same_minute = d([REDECLARED], [boa(11)], 30)
    assert same_minute[1] == pytest.approx(20.0)
    assert same_minute[0] == pytest.approx(20.0 + 40.0 / 3.0)


def test_rule_switches_only_inside_the_block() -> None:
    assert unit_module.declared_series is declared_series
    with sa.rule(True):
        assert unit_module.declared_series is declared_series_corrected
    assert unit_module.declared_series is declared_series
    with sa.rule(False):
        assert unit_module.declared_series is declared_series


def a_run(original: int, corrected: int) -> StageA:
    return StageA(
        5,
        1344,
        {"original": 9, "corrected": 1},
        {"original": original, "corrected": corrected},
        original,
    )


@pytest.mark.parametrize(
    ("original", "corrected", "confirmed"),
    [(10, 2, True), (10, 3, False), (0, 0, False)],
)
def test_stage_a_reading(original: int, corrected: int, confirmed: bool) -> None:
    s = summarise_a([a_run(original, corrected)])
    assert s["timing_confirmed"] is confirmed
    assert s["stale_periods"] == 5


def outcome(c1: str) -> RunOutcome:
    pairs = [("A", "A"), ("A", "B"), ("B", "A"), ("B", "B")]
    return RunOutcome(
        {p: c1 for p in pairs},  # type: ignore[misc]
        {p: "none detected" for p in pairs},  # type: ignore[misc]
        {p: 0.0 for p in pairs},  # type: ignore[misc]
        0,
    )


def test_changed_runs_counts_each_pair() -> None:
    runs = [
        StageB(outcome("coherent"), outcome("coherent"), 0),
        StageB(outcome("coherent"), outcome("indeterminate"), 3),
    ]
    assert changed_runs(runs, "claim1", ("A", "A")) == 1
    assert changed_runs(runs, "claim2", ("B", "B")) == 0


def test_same_cells_compares_only_the_named_lengths() -> None:
    a = {"cells": [{"length": "short", "x": 1}, {"length": "w5", "x": 2}]}
    b = {"cells": [{"length": "w5", "x": 3}, {"length": "short", "x": 1}]}
    assert same_cells(a, b, ["short"]) is True
    assert same_cells(a, b, ["short", "w5"]) is False


@pytest.mark.parametrize(("changed", "material"), [(0, False), (1, False), (2, True)])
def test_stage_b_materiality(changed: int, material: bool) -> None:
    """Honest battery, 100 runs, all coherent; `changed` runs become indeterminate
    under the corrected rule. 95 are needed, so no band flips; more than 1 changed
    run of 100 is material.
    """
    (short,) = sa.bands.length_indices(["short"])
    runs = [
        StageB(
            outcome("coherent"),
            outcome("indeterminate" if i < changed else "coherent"),
            0,
        )
        for i in range(100)
    ]
    records = {(0, short): runs}
    committed = sa.bands.summarise(
        sa.DEVIATION_2_BANDS, {(0, short): [r.original for r in runs]}, 100, True
    )
    s = sa.summarise_b(records, 100, committed)
    assert s["reproduces_committed"] is True
    assert s["band_flips"] == []
    assert s["most_runs_changed"] == changed
    assert s["material"] is material


def test_stage_b_band_flip_is_material_and_a_mismatch_is_not_judged() -> None:
    (short,) = sa.bands.length_indices(["short"])
    # Two runs, both needed in band: one change flips the band, though one
    # changed run alone would not be material.
    runs = [
        StageB(outcome("coherent"), outcome("indeterminate"), 0),
        StageB(outcome("coherent"), outcome("coherent"), 0),
    ]
    committed = sa.bands.summarise(
        sa.DEVIATION_2_BANDS, {(0, short): [r.original for r in runs]}, 2, True
    )
    s = sa.summarise_b({(0, short): runs}, 2, committed)
    assert s["band_flips"] and s["material"] is True
    other = {"cells": []}
    assert sa.summarise_b({(0, short): runs}, 2, other)["material"] is False
