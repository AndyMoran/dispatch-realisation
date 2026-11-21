"""Pass marks for the Claims 1–2 bands, on made-up outcomes; no battery is run."""

from typing import Any

from src.synthetic import bands as bd


def outcome(c1: str, c2: str, cross_c1: str | None = None) -> bd.RunOutcome:
    pairs = [("A", "A"), ("A", "B"), ("B", "A"), ("B", "B")]
    claim1 = {p: (c1 if p[0] == p[1] else (cross_c1 or c1)) for p in pairs}
    return bd.RunOutcome(
        claim1=claim1,  # type: ignore[arg-type]
        claim2=dict.fromkeys(pairs, c2),  # type: ignore[arg-type]
        violation_share=dict.fromkeys(pairs, 0.0),  # type: ignore[arg-type]
        curtailed_minutes=0,
    )


def cells(summary: dict[str, Any], battery: str, claim: str) -> list[dict[str, Any]]:
    return [
        c
        for c in summary["cells"]
        if c.get("battery") == battery and c.get("claim") == claim
    ]


def test_required_runs_is_95_of_100() -> None:
    assert bd.required_runs(100, 0.95) == 95
    assert bd.required_runs(20, 0.95) == 19


def test_outcome_labels() -> None:
    assert bd.outcome_label("coherent", None) == "coherent"
    assert bd.outcome_label(None, "η̂ outside bounds") == "not scored: η̂ outside bounds"


def test_95_in_band_passes_94_fails() -> None:
    bands = bd.HONEST_BANDS[:1]
    good = [outcome("coherent", "none detected")] * 95 + [
        outcome("indeterminate", "none detected")
    ] * 5
    s = bd.summarise(bands, {(0, 0): good}, 100)
    assert s["build_bands_passed"] is True
    bad = [outcome("coherent", "none detected")] * 94 + [
        outcome("not scored: η̂ outside bounds", "none detected")
    ] * 6
    s = bd.summarise(bands, {(0, 0): bad}, 100)
    assert s["build_bands_passed"] is False
    (matched,) = [
        c for c in cells(s, "honest", "claim1") if c["declared"] == c["scored"] == "A"
    ]
    assert matched["in_band"] == 94 and matched["required"] == 95


def test_cross_pairs_are_reported_not_judged() -> None:
    """A-declared, B-scored runs may all miss without failing the build."""
    runs = [outcome("coherent", "none detected", cross_c1="indeterminate")] * 100
    s = bd.summarise(bd.HONEST_BANDS[:1], {(0, 0): runs}, 100)
    assert s["build_bands_passed"] is True
    cross = [c for c in cells(s, "honest", "claim1") if c["declared"] != c["scored"]]
    assert all(
        c["passed"] is None and c["kind"] == "cross-pair diagnostic" for c in cross
    )


def test_one_sided_miss_withdraws_reading_but_keeps_build() -> None:
    runs = [outcome("indeterminate", "provable under-declaration")] * 100
    s = bd.summarise(bd.HONEST_BANDS, {(2, 0): runs}, 100)
    assert s["build_bands_passed"] is True
    assert s["one_sided_reading_stands"] is False
    (report,) = [
        c
        for c in cells(s, "honest_dc_efa", "claim2")
        if c["declared"] == c["scored"] == "A"
    ]
    assert report["passed"] is None and report["in_band"] is None


def test_contracted_battery_band_is_no_hard_flag() -> None:
    """The frequency-response battery holds DC, so its band is 'not scored' on the
    hard flag; a flag raised on it would miss the band."""
    assert bd.HONEST_BANDS[1].claim2 == frozenset({bd.NO_HARD_FLAG})
    runs = [outcome("coherent", bd.NO_HARD_FLAG)] * 100
    assert bd.summarise(bd.HONEST_BANDS, {(1, 1): runs}, 100)["build_bands_passed"]


def test_length_indices_follow_the_settings() -> None:
    """short and long keep seed indices 0 and 1; added lengths follow in order."""
    assert bd.length_indices(["short", "long"]) == [0, 1]
    assert bd.length_indices(["w5", "w16"]) == [2, 8]
    assert bd.FIRST_RUN_LENGTHS == ("short", "long")


def test_unknown_length_refused() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown run lengths"):
        bd.length_indices(["w9"])


def test_same_results_ignores_only_the_settings_hash() -> None:
    a = {"settings_sha256": "x", "cells": [1], "build_bands_passed": False}
    assert bd.same_results(a, {**a, "settings_sha256": "y"})
    assert not bd.same_results(a, {**a, "cells": [2]})
    assert not bd.same_results(a, {**a, "build_bands_passed": True})


def test_deviation_2_set_covers_every_section_8_row() -> None:
    """Eleven Claims 1–2 rows of §8's main table, plus the two one-sided batteries;
    Claim 2's bands are recorded, not gating."""
    bands = bd.DEVIATION_2_BANDS
    assert len(bands) == 13
    assert len({b.scenario.name for b in bands}) == 13
    assert sum(b.claim1_kind == "build" for b in bands) == 11
    assert sum(b.claim1_kind == "withdrawal" for b in bands) == 2
    assert {b.claim2_kind for b in bands} == {"recorded", "report"}
    under = next(b for b in bands if b.scenario.declare == "under")
    assert under.claim2 == bd.PROVABLE


def test_recorded_claim2_miss_gates_nothing() -> None:
    runs = [outcome("coherent", "provable under-declaration")] * 100
    s = bd.summarise(bd.DEVIATION_2_BANDS, {(0, 0): runs}, 100, by_length=True)
    assert s["build_bands_passed"] is True
    lengths: Any = s["lengths"]
    (verdict,) = lengths
    assert verdict["claim1_reportable"] is True
    assert verdict["claim2_bands_passed"] is False


def test_length_verdicts_need_every_build_band() -> None:
    good = [outcome("coherent", "none detected")] * 100
    bad = [outcome("indeterminate", "none detected")] * 100
    s = bd.summarise(
        bd.DEVIATION_2_BANDS,
        {(0, 0): good, (2, 0): bad, (0, 1): good},
        100,
        by_length=True,
    )
    lengths: Any = s["lengths"]
    short, long = lengths
    assert short["claim1_reportable"] is False and long["claim1_reportable"] is True


def test_one_sided_reading_needs_both_batteries_at_that_length() -> None:
    ok = [outcome("coherent", "none detected")] * 100
    miss = [outcome("indeterminate", "none detected")] * 100
    s = bd.summarise(
        bd.DEVIATION_2_BANDS, {(0, 0): ok, (11, 0): miss}, 100, by_length=True
    )
    lengths: Any = s["lengths"]
    (verdict,) = lengths
    assert verdict["claim1_reportable"] is True
    assert verdict["one_sided_reading_stands"] is False
