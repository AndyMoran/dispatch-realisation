"""Gate A1 logic on synthetic declarations. No network, no real data."""
from datetime import datetime, timedelta, timezone

import pytest

from src.ingest.gate_a1 import (GateA1Error, Record, adoption_dates, assert_config_complete,
                                evaluate, passes, within_unit_cv)

T0 = datetime(2026, 6, 29, tzinfo=timezone.utc)  # a Monday


def unit_records(unit, adopt_day, days=60, base=100.0, wobble=0.0, default_days=0):
    out = []
    for d in range(-default_days, days):
        ts = T0 + timedelta(days=adopt_day + d, hours=12)
        real = d >= 0
        mdo = (base / 2 + (wobble if d % 2 else -wobble)) if real else 9999.0
        mdb = -(base / 2) if real else -9999.0
        out += [Record(unit, ts, mdo, "MDO"), Record(unit, ts, mdb, "MDB")]
    return out


def cfg(**over):
    c = {
        "data": {"data_cutoff": "2026-10-31", "default_abs_mwh": 9999},
        "design1": {"min_cohorts": 3, "min_units_per_cohort": 4, "min_post_weeks_earliest": 8},
        "design2": {"min_units": 10, "min_weeks_per_unit": 6, "min_within_unit_cv": 0.02},
        "design3": {"grace_end_announced": False, "grace_end_date": "",
                    "min_weeks_before_cutoff": 4, "min_reserve_units": 5},
        "rules": {"borderline_fraction": 0.10},
        "api": {k: "x" for k in ["mdo_path", "mdb_path", "from_param", "to_param",
                                 "field_unit", "field_time", "field_value"]},
    }
    for k, v in over.items():
        c[k].update(v)
    return c


def test_default_values_are_not_adoption():
    recs = unit_records("U1", adopt_day=14, default_days=14)
    u = adoption_dates(recs, 9999)["U1"]
    assert u["first_real"].date() == (T0 + timedelta(days=14)).date()
    assert u["n_default"] == 28


def test_default_only_unit_is_kept_and_labelled():
    recs = unit_records("U9", adopt_day=0, days=0, default_days=10)
    u = adoption_dates(recs, 9999)["U9"]
    assert u["status"] == "excluded(default_values_only)"


def test_borderline_counts_as_failure():
    assert not passes(4.3, 4, 0.10)   # within 10% above threshold
    assert passes(4.5, 4, 0.10)


def test_last_cohort_is_dropped_and_not_counted():
    recs = []
    for c, start in enumerate([0, 21, 42]):          # three cohorts, three weeks apart
        for i in range(5):
            recs += unit_records(f"C{c}U{i}", adopt_day=start, wobble=3)
    rep = evaluate(adoption_dates(recs, 9999), within_unit_cv(recs, 9999), cfg())
    assert rep["design1"]["last_cohort_dropped"] == "2026-W33"
    assert rep["design1"]["estimable_cohorts_meeting_N"] == 2
    assert rep["design1"]["triggered"] is False


def test_five_spread_cohorts_select_design1():
    recs = []
    for c, start in enumerate([0, 14, 28, 42, 56]):  # four estimable after dropping the last
        for i in range(5):
            recs += unit_records(f"C{c}U{i}", adopt_day=start, wobble=3)
    rep = evaluate(adoption_dates(recs, 9999), within_unit_cv(recs, 9999), cfg())
    assert rep["design1"]["estimable_cohorts_meeting_N"] == 4
    assert rep["selected"] == "design1"


def test_three_estimable_cohorts_is_borderline():
    # Exactly at the threshold of 3 is within 10%, so it counts as a failure.
    recs = []
    for c, start in enumerate([0, 14, 28, 42]):
        for i in range(5):
            recs += unit_records(f"C{c}U{i}", adopt_day=start, wobble=3)
    rep = evaluate(adoption_dates(recs, 9999), within_unit_cv(recs, 9999), cfg())
    assert rep["design1"]["estimable_cohorts_meeting_N"] == 3
    assert rep["design1"]["triggered"] is False


def test_compressed_adoption_falls_to_design2():
    recs = []
    for i in range(12):
        recs += unit_records(f"U{i}", adopt_day=0, days=70, wobble=5)
    rep = evaluate(adoption_dates(recs, 9999), within_unit_cv(recs, 9999), cfg())
    assert rep["design1"]["triggered"] is False
    assert rep["design2"]["triggered"] is True
    assert rep["selected"] == "design2"


def test_flat_declarations_give_design_note():
    recs = []
    for i in range(12):
        recs += unit_records(f"U{i}", adopt_day=0, days=70, wobble=0)
    rep = evaluate(adoption_dates(recs, 9999), within_unit_cv(recs, 9999), cfg())
    assert rep["selected"] == "design_note_only"


def test_run_refuses_with_blank_thresholds():
    c = cfg(design1={"min_units_per_cohort": ""})
    with pytest.raises(GateA1Error, match="min_units_per_cohort"):
        assert_config_complete(c)
