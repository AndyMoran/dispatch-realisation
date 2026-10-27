"""Gate A1 logic on synthetic declarations. No network, no real data."""
from datetime import datetime, timedelta, timezone

import pytest

from src.ingest.gate_a1 import (GateA1Error, Record, adoption_dates, assert_config_complete,
                                evaluate, latest_declarations, passes, within_unit_cv)

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
        "data": {"data_cutoff": "2026-10-31", "default_abs_mwh": 9999,
                 "exclude_fuel_types": ["PS", "NPSHYD"]},
        "design1": {"min_cohorts": 3, "min_units_per_cohort": 4, "min_post_weeks_earliest": 8},
        "design2": {"min_units": 10, "min_weeks_per_unit": 6, "min_within_unit_cv": 0.02},
        "design3": {"grace_end_announced": False, "grace_end_date": "",
                    "min_weeks_before_cutoff": 4, "min_reserve_units": 5},
        "rules": {"borderline_fraction": 0.10},
        "sensitivity": {"min_daily_mdo_range_mwh": 0.5, "onset_window_days": 7,
                        "onset_min_dynamic_days": 4},
        "api": {k: "x" for k in ["mdo_path", "mdb_path", "from_param", "to_param",
                                 "field_unit", "field_time", "field_value",
                                 "field_published", "field_serial"]},
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


def test_overlap_duplicates_removed_and_latest_kept():
    t = T0
    first = Record("U1", t, 50.0, "MDO", "2026-06-29T10:00:00Z", 1)
    later = Record("U1", t, 30.0, "MDO", "2026-06-29T12:05:00Z", 2)   # redeclared after a BOA
    kept, counts = latest_declarations([first, first, later])          # first appears in two chunks
    assert kept == [later]
    assert counts == {"records_received": 3, "exact_duplicates_removed": 1,
                      "superseded_submissions": 1, "latest_declarations": 1}


# ------------------------------------------------------------ fetch / smoke

import json as _json

import src.ingest.gate_a1 as g

API = {"base_url": "https://example.invalid", "mdo_path": "/MDO", "mdb_path": "/MDB",
       "from_param": "from", "to_param": "to", "chunk_hours": 24,
       "field_unit": "bmUnit", "field_time": "timeFrom", "field_value": "levelFrom",
       "field_published": "publishTime", "field_serial": "serialNumber"}


def fake_api(drop_field=None):
    """Two records per chunk; the chunk's end minute is repeated by the next chunk."""
    def _get(url, params):
        rows = []
        for ts in (params["from"], params["to"]):
            row = {"bmUnit": "U1", "timeFrom": ts, "levelFrom": 40.0 if "MDO" in url else -40.0,
                   "publishTime": "2026-06-24T18:00:00Z", "serialNumber": "7"}
            row.pop(drop_field, None)
            rows.append(row)
        return _json.dumps({"data": rows}).encode()
    return _get


def smoke_cfg():
    return {"data": {"window_start": "2026-06-25"}, "api": dict(API)}


def test_smoke_passes_and_counts_boundary_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "_get", fake_api())
    out = g.smoke(smoke_cfg(), days=2)
    assert out["passed"] and out["requested"] == 4 and out["arrived"] == 4
    assert out["exact_duplicates_removed"] == 2          # one shared boundary minute per dataset


def test_smoke_fails_visibly_on_missing_field(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "_get", fake_api(drop_field="levelFrom"))
    with pytest.raises(GateA1Error, match="all_requests_succeeded"):
        g.smoke(smoke_cfg(), days=1)


def test_rerun_keeps_earlier_raw_vintage(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "_get", fake_api())
    start = datetime(2026, 6, 25, tzinfo=timezone.utc)
    for _ in range(2):
        g.fetch(API, start, start + timedelta(days=1), tmp_path / "raw", tmp_path / "m.csv")
    assert len(list((tmp_path / "raw" / "MDO").glob("*.json"))) == 2


# ---------------------------------------------------------------- reference

from src.ingest.reference import inventory


def test_reference_inventory_reports_shape_not_units():
    rows = [{"elexonBmUnit": "T_UNITX1", "fuelType": "PS", "generationCapacity": 50, "demandCapacity": -50},
            {"elexonBmUnit": "T_UNITX2", "fuelType": "WIND", "generationCapacity": 0},
            {"elexonBmUnit": "T_UNITX3", "fuelType": "PS"}]
    inv = inventory(rows)
    assert inv["records"] == 3
    assert inv["capacity_fields_populated"] == {"demandCapacity": 1, "generationCapacity": 1}
    assert inv["fuel_types"] == {"PS": 2, "WIND": 1}
    assert "T_UNITX" not in _json.dumps(inv)          # no unit IDs in the printed inventory


def test_pumped_storage_excluded_but_kept_and_unknown_units_kept():
    recs = unit_records("PS1", adopt_day=0) + unit_records("BAT1", adopt_day=0) \
        + unit_records("NEW1", adopt_day=0)
    units = g.exclude_non_battery(adoption_dates(recs, 9999),
                                  {"PS1": "PS", "BAT1": "OTHER"}, ["PS", "NPSHYD"])
    assert units["PS1"]["status"] == "excluded(fuel_type_PS)"
    assert units["BAT1"]["status"] == "adopted"
    assert units["NEW1"]["status"] == "adopted" and units["NEW1"]["fuel_type"] == ""



# ------------------------------------------------------------ dynamic onset

def mdo_day(unit, day, values):
    return [Record(unit, T0 + timedelta(days=day, hours=h), v, "MDO") for h, v in enumerate(values)]


def test_static_then_dynamic_onset_and_summary():
    recs = []
    for d in range(10):                                  # 10 days copying a static maximum
        recs += mdo_day("U1", d, [100.0, 100.0, 100.0])
    for d in range(10, 20):                              # then tracking state of charge
        recs += mdo_day("U1", d, [80.0, 60.0, 70.0])
    onset = g.dynamic_onset(recs, 9999, 0.5, 7, 4)
    assert onset["U1"] == (T0 + timedelta(days=10)).date()
    units = adoption_dates(recs, 9999)
    summ = g.onset_summary(units, onset)
    assert summ["static_start_days_ge_7"] == 1 and summ["static_start_days_median"] == 10


def test_rounding_drift_and_isolated_days_are_not_dynamic():
    recs = []
    for d in range(14):
        recs += mdo_day("U2", d, [50.0, 50.002, 50.001])     # rounding drift only
    recs += mdo_day("U2", 3, [50.0, 40.0])                    # one isolated redeclaration day
    recs += mdo_day("U2", 9, [50.0, 40.0])
    onset = g.dynamic_onset(recs, 9999, 0.5, 7, 4)
    assert "U2" not in onset
    summ = g.onset_summary(adoption_dates(recs, 9999), onset)
    assert summ["never_dynamic_by_cutoff"] == 1


def test_defaults_and_mdb_ignored_for_onset():
    recs = []
    for d in range(7):
        recs += mdo_day("U3", d, [9999.0, 9999.0])
        recs += [Record("U3", T0 + timedelta(days=d, hours=h), v, "MDB") for h, v in enumerate([-10.0, -90.0])]
    assert g.dynamic_onset(recs, 9999, 0.5, 7, 4) == {}


def test_onset_cohorts_use_iso_weeks():
    recs = []
    for d in range(7):
        recs += mdo_day("U4", d, [80.0, 60.0])
    onset = g.dynamic_onset(recs, 9999, 0.5, 7, 4)
    summ = g.onset_summary(adoption_dates(recs, 9999), onset)
    assert summ["dynamic_onset_cohort_sizes"] == {"2026-W27": 1}   # T0 is Mon 29 Jun 2026



def test_run_refuses_before_cutoff_has_ended():
    from datetime import date
    with pytest.raises(GateA1Error, match="not complete"):
        g.assert_cutoff_complete(date(2026, 10, 29), date(2026, 10, 27))
    with pytest.raises(GateA1Error, match="not complete"):
        g.assert_cutoff_complete(date(2026, 10, 29), date(2026, 10, 29))
    g.assert_cutoff_complete(date(2026, 10, 29), date(2026, 10, 30))
