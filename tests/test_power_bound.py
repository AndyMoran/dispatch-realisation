"""Power bound on synthetic declarations. No network, no real data."""
import json
from datetime import datetime, timedelta, timezone

from src.ingest.power_bound import Seg, minute_values, parse, run_bound, unit_shares

UTC = timezone.utc
T0 = datetime(2026, 9, 7, tzinfo=UTC)          # Monday of 2026-W37


def seg(unit, start, level, end=None, published="2026-09-01T00:00:00Z", serial=0, level_to=None):
    return Seg(unit, start, end, level, level_to, published, serial)


def test_hold_until_next_and_latest_wins():
    a = seg("U", T0, 10.0)
    b = seg("U", T0 + timedelta(minutes=3), 50.0)
    late = seg("U", T0 + timedelta(minutes=1), 99.0, end=T0 + timedelta(minutes=2),
               published="2026-09-02T00:00:00Z")      # redeclaration of minute 1 only
    m = minute_values([a, b, late], data_end=T0 + timedelta(minutes=5))
    assert [m[T0 + timedelta(minutes=i)] for i in range(5)] == [10.0, 99.0, 10.0, 50.0, 50.0]


def test_known_share_floor_and_defaults():
    # 100 MW unit; decision bound at K=2, T=60 is 200 MWh.
    minutes = {T0 + timedelta(minutes=i): v for i, v in enumerate(
        [160.0] * 30 + [300.0] * 60 + [0.5] * 5 + [9999.0] * 5)}
    s = unit_shares(minutes, T0, T0 + timedelta(days=1), mw=100.0, default_abs=9999)
    assert s["minutes"] == 95                      # defaults dropped
    assert abs(s["k2_t60"] - 30 / 95) < 1e-12      # 0.5 MWh is below the 1 MWh floor
    assert s["k1_t90"] == 0.0                       # 160 > 100 x 1.5


def test_adoption_week_excluded():
    minutes = {T0 - timedelta(days=1): 10.0, T0: 500.0}
    s = unit_shares(minutes, T0, T0 + timedelta(days=1), mw=100.0, default_abs=9999)
    assert s["minutes"] == 1 and s["k2_t60"] == 0.0


def test_parse_uses_time_to_when_present():
    api = {"field_unit": "bmUnit", "field_time": "timeFrom", "field_value": "levelFrom",
           "field_published": "publishTime", "field_serial": "serialNumber"}
    body = json.dumps({"data": [{"bmUnit": "U", "timeFrom": "2026-09-07T00:00Z",
                                 "timeTo": "2026-09-07T00:02Z", "levelFrom": 4, "levelTo": 4,
                                 "publishTime": "x", "serialNumber": 1}]}).encode()
    (s,) = parse(body, api)
    assert s.end == T0 + timedelta(minutes=2)


def test_decision_counts_and_secondary_split():
    end = T0 + timedelta(days=1)
    adoption, ref, segs = [], [], []
    for i in range(40):
        u, utype = f"U{i}", ("V" if i < 15 else "E")
        adoption.append({"bm_unit": u, "status": "adopted", "cohort": "2026-W36"})
        ref.append({"elexonBmUnit": u, "generationCapacity": 100.0, "bmUnitType": utype})
        level = 150.0 if i < 32 else 500.0           # 32 in reach, 8 not
        segs.append(seg(u, T0, level))
    adoption.append({"bm_unit": "NOMW", "status": "adopted", "cohort": "2026-W36"})
    ref.append({"elexonBmUnit": "NOMW", "generationCapacity": 0, "demandCapacity": 0,
                "bmUnitType": "E"})
    segs.append(seg("NOMW", T0, 150.0))
    adoption.append({"bm_unit": "LATE", "status": "adopted", "cohort": "2026-W44"})  # < 4 weeks
    out = run_bound({"MDO": segs}, adoption, ref, end, 9999)["MDO"]
    d = out["decision"]
    assert d["of_scored_units"] == 41 and d["potentially_identifiable"] == 32
    assert d["build_claim_3_in_v1"] is True
    assert d["potentially_identifiable_non_secondary"] == 17
    assert d["passes_only_because_of_secondary_units"] is True
    assert out["groups"]["all"]["mw_unavailable"] == 1
