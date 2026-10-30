"""Lock-time counts on synthetic tables. No network, no real data."""
import json

from src.ingest.lock_counts import counts, full_weeks_after


def test_adoption_week_never_counts():
    assert full_weeks_after("2026-W45") == 1      # only W46 (9–15 Nov)
    assert full_weeks_after("2026-W46") == 0
    assert full_weeks_after("2026-W42") == 4      # W43–W46
    assert full_weeks_after("2026-W38") == 8      # W39–W46


def row(unit, cohort, status="adopted", n_default=0):
    return {"bm_unit": unit, "status": status, "cohort": cohort, "n_default": str(n_default)}


def ref(unit, gsp, gc=50.0, fuel="OTHER"):
    return {"elexonBmUnit": unit, "gspGroupId": gsp, "generationCapacity": gc, "fuelType": fuel}


def test_counts_samples_gsp_and_gaps():
    rows = [row(f"T_A{i}", "2026-W36") for i in range(6)] \
         + [row(f"T_B{i}", "2026-W42") for i in range(6)] \
         + [row("T_LATE", "2026-W44"), row("T_NEW", "2026-W43"), row("T_NOGC", "2026-W36"),
            row("T_PS", "2026-W36", status="excluded(fuel_type_PS)", n_default=3)]
    refs = [ref(f"T_A{i}", "_A") for i in range(6)] + [ref(f"T_B{i}", f"_B{i}") for i in range(6)] \
         + [ref("T_LATE", "_A"), ref("T_NOGC", "_A", gc=0), ref("T_PS", "_A", fuel="PS")]
    out = counts(rows, refs)
    assert out["adopted_units"] == 15 and out["missing_from_reference"] == 1
    assert out["in_reference_without_gc"] == 1
    assert out["default_valued_records_total"] == 3 and out["units_with_any_default_record"] == 1
    four, eight = out["samples"]["min_4_weeks"], out["samples"]["min_8_weeks"]
    assert four["units"] == 12 and eight["units"] == 6
    assert four["gsp_groups_with_2plus_units"] == 1 and four["gsp_units_contributing"] == 6
    assert four["gsp_week_fe_estimable"] is False
    assert "T_" not in json.dumps(out)              # no unit IDs in the output
