"""The pinned scoring run, on synthetic units, with planted bugs.

The fleet here is honest synthetic batteries from the known-answer suite, given
made-up unit IDs and lead parties; nothing touches real data.
"""

import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.claims import claim5 as c5
from src.claims.results import DayPart, WeekResult
from src.claims.unit import load_claim_settings
from src.ingest import assemble as asm
from src.ingest import pull
from src.scoring import fleet as fl
from src.scoring import run as sr
from src.synthetic import battery as bt
from src.synthetic.bands import BAND_SETS
from src.synthetic.settings import load_synthetic_settings

KNOWN = json.loads((pull.ROOT / sr.KNOWN_ANSWER).read_text())
UNITS = 7  # one secondary


# ------------------------------------------------------------------ fleet.py


def week(day: int, num: float, den: float) -> WeekResult:
    start = datetime(2026, 10, day, tzinfo=UTC)
    return WeekResult(start, (DayPart(start.date(), num, den),), 1.0, None)


def test_distribution_suppresses_below_five() -> None:
    assert fl.distribution([0.1, 0.2, 0.3, 0.4]) == {
        "units": 4,
        "suppressed": fl.SUPPRESSED,
    }
    d = fl.distribution([0.1, 0.2, 0.3, 0.4, 0.5])
    assert d["units"] == 5 and d["p50"] == pytest.approx(0.3)
    assert d["p10"] == pytest.approx(0.14)


def test_complementary_suppression() -> None:
    Cells = dict[str, dict[str, object]]
    small: dict[str, object] = {"units": 3, "suppressed": fl.SUPPRESSED}
    cells: Cells = {
        "a": small,
        "b": {"units": 9, "p50": 1.0},
        "c": {"units": 6, "p50": 2.0},
    }
    out = fl.complementary(cells)
    assert fl.is_suppressed(out["a"]) and fl.is_suppressed(out["c"])
    assert not fl.is_suppressed(out["b"]) and out["c"]["units"] == 6
    two: Cells = {"a": small, "b": small, "c": {"units": 9, "p50": 1.0}}
    assert not fl.is_suppressed(fl.complementary(two)["c"])
    none: Cells = {"b": {"units": 9, "p50": 1.0}, "c": {"units": 6, "p50": 2.0}}
    assert fl.complementary(none) == none


def test_wilson_and_groups() -> None:
    low, high = fl.wilson(17, 100)
    assert low == pytest.approx(0.1089, abs=1e-4) and high == pytest.approx(
        0.2555, abs=1e-4
    )
    assert fl.wilson(0, 100)[0] == 0.0 and fl.wilson(0, 100)[1] == pytest.approx(
        0.037, abs=1e-3
    )
    assert [fl.length_group(n) for n in (3, 4, 7, 8, 15, 16, 20, 21)] == [
        None,
        (4, 7),
        (4, 7),
        (8, 11),
        (12, 15),
        (16, 20),
        (16, 20),
        None,
    ]
    with pytest.raises(ValueError):
        fl.wilson(5, 0)


def test_honest_reference_reads_the_matched_pair() -> None:
    a4 = fl.honest_reference(KNOWN, "A", 4)
    assert a4 is not None and (a4["flagged"], a4["runs"]) == (17, 100)
    assert a4["label"] == fl.REFERENCE_LABEL
    b8 = fl.honest_reference(KNOWN, "B", 8)
    assert b8 is not None and b8["flagged"] == 7
    assert fl.honest_reference(KNOWN, "A", 9) is None  # not a tested length


def test_pooled_median_and_slope() -> None:
    weeks = [
        week(5, 1, 10),
        week(12, 3, 10),
        WeekResult(datetime(2026, 10, 19, tzinfo=UTC), (), 0.0, "x"),
    ]
    assert fl.pooled(weeks) == (4.0, 20.0)
    assert fl.unit_median(weeks) == pytest.approx(0.2)
    assert fl.scored_count(weeks) == 2
    assert fl.slope_through_origin([1, 2, 3], [2, 4, 6]) == pytest.approx(2)
    assert fl.slope_through_origin([0, 0], [1, 2]) is None


# ------------------------------------------------------------------ a synthetic fleet


def synthetic_assembly() -> tuple[asm.Assembly, datetime]:
    settings = load_synthetic_settings()
    faults = bt.load_faults()
    band = next(b for b in BAND_SETS["deviation-2"] if b.scenario.name == "honest")
    length = settings.lengths[0]  # 4 scored weeks
    units: dict[str, asm.FleetUnit] = {}
    inputs = {}
    for i in range(UNITS):
        rng = bt.run_rng(settings.master_seed, band.scenario.name, 0, i)
        sim = bt.simulate(
            band.scenario,
            length,
            settings,
            bt.load_physics(),
            bt.load_dc_energy(settings),
            rng,
            faults,
        )
        uid = f"UNIT-{i:02d}"
        inputs[uid] = replace(
            bt.unit_inputs(
                sim, "A", bt.lag_minutes(band.scenario, settings, faults), faults
            ),
            unit_key=uid,
        )
        units[uid] = asm.FleetUnit(
            unit=uid,
            adoption_week_start=length.adoption_week_start,
            adopted_at=length.adoption_week_start + timedelta(hours=9),
            registered_mw=inputs[uid].registered_mw,
            lead_party=f"Lead Party {i % 3}",
            secondary=i == 0,
        )
    a = asm.Assembly(units, inputs, {}, {}, UNITS, {})
    return a, length.end


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any]:
    root = tmp_path_factory.mktemp("repo")
    (root / sr.KNOWN_ANSWER).parent.mkdir(parents=True)
    shutil.copy(pull.ROOT / sr.KNOWN_ANSWER, root / sr.KNOWN_ANSWER)
    assembly, end = synthetic_assembly()
    record = sr.run(root, workers=1, end=end, assembly=assembly, check_git=False)
    return root, record


def load(root: Path, rel: Path) -> Any:
    return json.loads((root / rel).read_text())


def test_public_outputs_name_no_unit(ran: tuple[Path, Any]) -> None:
    root, _ = ran
    for rel in (sr.FLEET_OUT, sr.SENSITIVITY_OUT, sr.RECORD_OUT):
        text = (root / rel).read_text()
        assert "UNIT-" not in text and "Lead Party" not in text
    private = (root / sr.PRIVATE_OUT).read_text()
    assert "UNIT-03" in private and "Lead Party 1" in private


def test_preregistered_fleet_results(ran: tuple[Path, Any]) -> None:
    root, record = ran
    f = load(root, sr.FLEET_OUT)
    assert f["units"] == {"bm_units": UNITS, "secondary_units": 1}
    c1 = f["claim1"]["error_ratio"]["A"]
    assert c1["all units"]["units"] == UNITS and "p50" in c1["all units"]
    # one secondary unit: suppressed, and the other cell with it (complementary)
    assert fl.is_suppressed(c1["secondary units (may be aggregated)"])
    assert fl.is_suppressed(c1["other units"]) and c1["other units"]["units"] == 6
    groups = f["claim2"]["by_length"]["A"]
    assert [g["scored_weeks"] for g in groups] == ["4–7", "8–11", "12–15", "16–20"]
    first = groups[0]
    assert first["units"] == UNITS and 0 <= first["violation_share_pooled"] <= 1
    assert (
        first["reference"]["flagged"] == 17 and first["reference"]["scored_weeks"] == 4
    )
    assert groups[1]["units"] == 0 and fl.is_suppressed(groups[1])
    groups_b = f["claim2"]["by_length"]["B"]
    assert groups_b[0]["reference"]["flagged"] == 20  # Branch B's matched pair
    assert groups[1]["reference"]["scored_weeks"] == 8  # reference shown regardless
    rel = f["reliability"]["A"]["claim1"]
    assert rel["units"] == UNITS and rel["verdict"] in (
        "reliable",
        "straddles 0.5",
        "unreliable",
    )
    c5 = f["claim5"]
    assert c5["boas"] > 0 and c5["units"] == UNITS
    slope = f["m13_slope"]
    assert slope["units"] == UNITS and "share_nearer_branch_b" in slope
    assert slope["share_nearer_branch_b_definition"] == sr.SHARE_DEFINITION
    assert slope["weeks"]["p50"] == 4
    assert record["units_scored"] == UNITS and record["code_commit"] == "not checked"
    assert set(record["outputs_sha256"]) == {
        str(sr.FLEET_OUT),
        str(sr.SENSITIVITY_OUT),
        str(sr.PRIVATE_OUT),
    }


def test_sensitivity_is_apart_and_complete(ran: tuple[Path, Any]) -> None:
    root, _ = ran
    s = load(root, sr.SENSITIVITY_OUT)
    names = [
        k for k in s if k not in ("schema_version", "label", "claim5", "not_applicable")
    ]
    assert names == sorted(
        [
            "H = 6 hours",
            "η̂ bounds [0.65, 0.99]",
            "Claim 1 without the EFA boundary exclusion",
        ]
    )
    assert "preregistered" not in s
    no_efa = s["Claim 1 without the EFA boundary exclusion"]
    assert "claim2_by_length" not in no_efa and "claim1_error_ratio" in no_efa
    assert "claim2_by_length" in s["H = 6 hours"]
    assert set(s["not_applicable"]) == set(sr.NOT_APPLICABLE)


def test_private_table_holds_each_unit(ran: tuple[Path, Any]) -> None:
    root, _ = ran
    p = load(root, sr.PRIVATE_OUT)
    units = p["units"]
    assert isinstance(units, list) and len(units) == UNITS
    u = units[1]
    a = u["branches"]["A"]
    assert a["claim1"]["scored_weeks"] == 4 and len(a["claim1"]["interval_95"]) == 2
    assert 0 <= a["claim2"]["violation_share_pooled"] <= 1
    assert u["claim5"]["boas"] > 0 and u["m13_slope"]["slope"] is not None


def test_the_run_runs_once(ran: tuple[Path, Any]) -> None:
    root, _ = ran
    with pytest.raises(sr.RunError, match="already run"):
        sr.run(root, check_git=False)


def test_a_modified_tree_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sr, "git_state", lambda root: ("abc", True))
    with pytest.raises(sr.RunError, match="commit before"):
        sr.run(tmp_path)


def test_assert_no_ids_catches_a_leak() -> None:
    record = sr.UnitRecord(
        "UNIT-X",
        "Lead Q",
        False,
        None,
        datetime(2026, 10, 5, tzinfo=UTC),
        {},
        c5.UnitLatency((), 0),
        sr.Slope(None, 0, 0, None, "x"),
    )
    sr.assert_no_ids('{"a": 1}', [record])
    with pytest.raises(sr.RunError):
        sr.assert_no_ids('{"who": "Lead Q"}', [record])
    with pytest.raises(sr.RunError):
        sr.assert_no_ids('["UNIT-X"]', [record])


def test_variants_read_the_config() -> None:
    names = [v.name for v in sr.load_variants()]
    assert names == [
        "preregistered",
        "H = 6 hours",
        "η̂ bounds [0.65, 0.99]",
        "Claim 1 without the EFA boundary exclusion",
    ]
    base = load_claim_settings()
    wide = sr.variant_settings(base, sr.load_variants()[2])
    assert (wide.eta_min, wide.eta_max) == (0.65, 0.99)
    assert sr.variant_settings(base, sr.load_variants()[3]).efa_boundary_hours == ()
    assert sr.variant_settings(base, sr.load_variants()[1]) == base  # H passed apart


def test_overlaps_any() -> None:
    from src.model.types import LevelSegment

    t = datetime(2026, 10, 5, 10, tzinfo=UTC)
    segs = [
        LevelSegment(t, t + timedelta(minutes=10), 5, 5, 1, t),
        LevelSegment(t + timedelta(hours=2), t + timedelta(hours=5), 5, 5, 2, t),
    ]
    starts = [s.time_from for s in segs]
    longest = timedelta(hours=3)
    half = timedelta(minutes=30)
    assert sr.overlaps_any(starts, segs, longest, t, t + half)
    assert not sr.overlaps_any(
        starts, segs, longest, t + timedelta(minutes=10), t + half
    )
    assert sr.overlaps_any(
        starts, segs, longest, t + timedelta(hours=4), t + timedelta(hours=4) + half
    )
    assert not sr.overlaps_any(
        starts, segs, longest, t + timedelta(hours=5), t + timedelta(hours=6)
    )
    assert not sr.overlaps_any(starts, segs, longest, t - half, t)


def test_fewer_than_four_weeks_enter_no_fleet_figure() -> None:
    from src.claims.unit import TOO_FEW_WEEKS, score_unit

    assembly, end = synthetic_assembly()
    uid = "UNIT-01"
    fu = assembly.units[uid]
    settings = load_claim_settings()
    short = score_unit(
        assembly.inputs[uid],
        fu.adoption_week_start,
        end - timedelta(days=7),
        settings,
        "A",
        frozenset(),
    )
    r = sr.branch_result(short, settings.min_scored_weeks, True)
    assert (r.claim1_weeks, r.claim2_weeks) == (3, 3)
    assert r.claim1_score is None and r.claim1_reason == TOO_FEW_WEEKS
    assert r.claim2_median is None and r.claim2_reason == TOO_FEW_WEEKS
    assert r.claim1_interval is None and r.claim1_halves is None
    full = score_unit(
        assembly.inputs[uid], fu.adoption_week_start, end, settings, "A", frozenset()
    )
    r4 = sr.branch_result(full, settings.min_scored_weeks, False)
    assert (
        r4.claim1_score is not None and r4.claim1_interval is None
    )  # variant: no interval


def test_parallel_and_serial_runs_agree() -> None:
    assembly, end = synthetic_assembly()
    settings = load_claim_settings()
    variants = sr.load_variants()[:1]
    tasks = [
        sr.Task(
            assembly.units[u],
            assembly.inputs[u],
            end,
            settings,
            variants,
            c5.load_claim5_settings(),
        )
        for u in ("UNIT-02", "UNIT-01")
    ]
    serial = sr.score_all(tasks, workers=1)
    parallel = sr.score_all(tasks, workers=2)
    assert [r.unit for r in serial] == ["UNIT-01", "UNIT-02"]
    assert serial == parallel


def test_slope_reasons_and_guards() -> None:
    inv = 1 / 0.9**0.5
    few = sr.slope_from_points([1.0] * 47, [1.0] * 47, 4, inv)
    assert few.slope is None and few.reason == sr.NO_SLOPE_PERIODS
    flat = sr.slope_from_points([0.0] * 60, [1.0] * 60, 4, inv)
    assert flat.slope is None and flat.reason == sr.NO_SLOPE_VARIATION
    ok = sr.slope_from_points([1.0, 2.0] * 30, [2.0, 4.0] * 30, 4, inv)
    assert ok.slope == pytest.approx(2.0) and ok.reason is None and ok.weeks == 4
    with pytest.raises(ValueError, match="non-finite"):
        fl.slope_through_origin([1.0, float("nan")], [1.0, 2.0])
    with pytest.raises(ValueError):
        sr.dumps({"x": float("inf")})


def test_slope_reads_only_claim1_scored_weeks() -> None:
    from src.claims.unit import score_unit

    assembly, end = synthetic_assembly()
    uid = "UNIT-02"
    unit = assembly.inputs[uid]
    settings = load_claim_settings()
    r = score_unit(
        unit, assembly.units[uid].adoption_week_start, end, settings, "A", frozenset()
    )
    scored = frozenset(
        w.error.week_start for w in r.claim1_weeks if w.error.score is not None
    )
    full = sr.m13_slope(unit, scored, end, settings, r.eta_hat)
    assert full.slope is not None and full.weeks == 4
    dropped = sorted(scored)[1:]
    part = sr.m13_slope(unit, frozenset(dropped), end, settings, r.eta_hat)
    assert part.reason == sr.NO_SLOPE_WEEKS and part.periods == 0
    wider = replace(settings, min_scored_weeks=3)
    three = sr.m13_slope(unit, frozenset(dropped), end, wider, r.eta_hat)
    assert three.weeks == 3 and 0 < three.periods < full.periods
    assert sr.m13_slope(unit, scored, end, settings, None).reason == sr.NO_SLOPE_ETA


def test_honest_reference_checks_the_outcome_names() -> None:
    a12 = fl.honest_reference(KNOWN, "A", 12)  # the file omits a zero count
    assert a12 is not None and (a12["flagged"], a12["runs"]) == (0, 100)
    renamed = json.loads(json.dumps(KNOWN))
    for c in renamed["cells"]:
        if fl.PROVABLE in c.get("counts", {}):
            c["counts"]["provable"] = c["counts"].pop(fl.PROVABLE)
    with pytest.raises(ValueError, match="unknown Claim 2 outcomes"):
        fl.honest_reference(renamed, "A", 4)


def test_a_non_finite_value_stops_the_run_before_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / sr.KNOWN_ANSWER).parent.mkdir(parents=True)
    shutil.copy(pull.ROOT / sr.KNOWN_ANSWER, tmp_path / sr.KNOWN_ANSWER)
    assembly, end = synthetic_assembly()
    monkeypatch.setattr(sr, "slope_fleet", lambda records: {"slope": float("nan")})
    with pytest.raises(ValueError):
        sr.run(tmp_path, workers=1, end=end, assembly=assembly, check_git=False)
    for rel in (sr.FLEET_OUT, sr.SENSITIVITY_OUT, sr.RECORD_OUT, sr.PRIVATE_OUT):
        assert not (tmp_path / rel).exists()
    with pytest.raises(ValueError, match="non-finite slope"):
        fl.slope_through_origin([1e-160], [1e300])  # Σx² is tiny but positive


def test_the_private_table_carries_a_slope_gate_reason() -> None:
    from src.claims.unit import score_unit

    assembly, end = synthetic_assembly()
    uid = "UNIT-04"
    fu, unit = assembly.units[uid], assembly.inputs[uid]
    settings = load_claim_settings()
    short_end = end - timedelta(days=7)  # 3 scored weeks
    results: dict[tuple[str, str], sr.BranchResult] = {}
    for b in sr.BRANCHES:
        r = score_unit(
            unit, fu.adoption_week_start, short_end, settings, b, frozenset()
        )
        results[(sr.PREREGISTERED, b)] = sr.branch_result(
            r, settings.min_scored_weeks, True
        )
        if b == "A":
            scored = frozenset(
                w.error.week_start for w in r.claim1_weeks if w.error.score is not None
            )
            slope = sr.m13_slope(unit, scored, short_end, settings, r.eta_hat)
    record = sr.UnitRecord(
        uid,
        fu.lead_party,
        fu.secondary,
        fu.registered_mw,
        fu.adoption_week_start,
        results,
        c5.UnitLatency((), 0),
        slope,
    )
    table = json.loads(sr.dumps(sr.private_table([record], c5.load_claim5_settings())))
    unit_row = table["units"][0]
    assert unit_row["m13_slope"]["reason"] == sr.NO_SLOPE_WEEKS
    assert unit_row["m13_slope"]["weeks"] == 3
    assert unit_row["branches"]["A"]["claim1"]["reason"] is not None
