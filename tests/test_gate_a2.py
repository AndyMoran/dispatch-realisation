"""Gate A2 logic on synthetic rows. No network, no real data."""
from datetime import date, datetime, timezone

import pytest

import src.ingest.gate_a2 as a2

UTC = timezone.utc
CFG = {"thresholds": {"low": 5000, "high": 10000, "both_triggered": "middle"}}


def test_run_refuses_before_lock(tmp_path):
    p = tmp_path / "PREREGISTRATION.md"
    p.write_text("# Pre-registration\n\n**Status: DRAFT — not locked.**\n")
    with pytest.raises(a2.GateA2Error, match="not locked"):
        a2.assert_locked(p)
    p.write_text("# Pre-registration\n\n**Status: LOCKED — 2 Nov 2026, commit abc1234.**\n")
    a2.assert_locked(p)


def test_stage_fallback_applies_to_all_months():
    assert a2.choose_stage({"2025-10": {5, 6}, "2025-11": {5, 6}}, 6, 5) == 6
    assert a2.choose_stage({"2025-10": {5}, "2025-11": {5, 6}}, 6, 5) == 5


def test_mid_is_volume_weighted_and_skips_zero_volume():
    recs = [{"startTime": "2026-01-01T00:00:00Z", "price": 100, "volume": 3},
            {"startTime": "2026-01-01T00:00:00Z", "price": 200, "volume": 1},
            {"startTime": "2026-01-01T00:30:00Z", "price": 999, "volume": 0}]
    mid = a2.mid_by_half_hour(recs, "startTime", "price", "volume")
    assert mid == {datetime(2026, 1, 1, 0, 0, tzinfo=UTC): 125.0}


def test_margin_signs():
    # Offer paid 150 vs MID 100: +50 headline; vs day's best 140: +10 conservative.
    assert a2.margins("Offer", 150, 100, day_lo=60, day_hi=140) == (50, 10)
    # Bid at 40 vs MID 100: +60 headline; vs day's lowest 60: +20 conservative.
    assert a2.margins("Bid", 40, 100, day_lo=60, day_hi=140) == (60, 20)


def test_daily_extremes_use_local_day():
    # 23:30 UTC on 30 Jun is 00:30 BST on 1 Jul.
    mid = {datetime(2026, 6, 30, 23, 30, tzinfo=UTC): 50.0,
           datetime(2026, 7, 1, 12, 0, tzinfo=UTC): 80.0}
    ext = a2.daily_extremes(mid, "Europe/London")
    assert ext == {date(2026, 7, 1): (50.0, 80.0)}


def row(unit, stage, mwh, price=150, bo="Offer", t="2026-01-01T00:05:00Z"):
    return {"date": t, "bm_unit": unit, "fuel": "Battery", "bid_offer": bo, "stage": str(stage),
            "average_price_per_MWh": str(price), "pair_id": "1", "skipped_volume_MWh": str(mwh)}


def test_value_skips_filters_stage_and_fleet_and_counts_missing_mid():
    mid = {datetime(2026, 1, 1, 0, 0, tzinfo=UTC): 100.0}
    ext = {date(2026, 1, 1): (60.0, 140.0)}
    rows = [row("U1", 6, 2), row("U1", 5, 9), row("X9", 6, 9),
            row("U1", 6, 1, t="2026-01-01T03:00:00Z")]          # no MID for that half hour
    t = a2.value_skips(rows, 6, {"U1"}, mid, ext, "Europe/London")
    assert t.value_headline == 2 * 50 and t.value_conservative == 2 * 10
    assert t.rows_used == 1 and t.rows_no_mid == 1 and t.mwh_no_mid == 1


def test_exposure_is_mw_years_first_to_last_month():
    window = [f"2025-{m:02d}" for m in (10, 11, 12)] + [f"2026-{m:02d}" for m in range(1, 10)]
    present = {"A": {"2025-10", "2026-09"},          # whole window: 12 months
               "B": {"2026-04", "2026-06"},          # Apr–Jun: 3 months
               "C": {"2026-01"}}                      # no GC: excluded
    mw, sens = a2.exposure(present, {"A": 50.0, "B": 100.0}, window)
    assert mw == pytest.approx(50 * 1 + 100 * 3 / 12)
    assert sens == 50.0                               # only A present in September


def test_decision_rule_including_both_triggers():
    assert a2.decide(4000, 8000, CFG) == "reputation"
    assert a2.decide(6000, 12000, CFG) == "product_grade"
    assert a2.decide(6000, 8000, CFG) == "middle"
    assert a2.decide(4000, 12000, CFG) == "middle"    # inconclusive: defer to Gate B
    assert a2.decide(5000, 10000, CFG) == "middle"    # thresholds themselves are not crossed


def test_resource_matching_requires_exactly_one_per_month():
    res = [{"name": "Skip Rate - In Merit All Balancing Mechanism - October 2025", "id": "a"},
           {"name": "Skip Rate - In Merit Post System Action - October 2025", "id": "b"}]
    got = a2.match_resources(res, "In Merit All Balancing Mechanism", ["2025-10"])
    assert got["2025-10"]["id"] == "a"
    with pytest.raises(a2.GateA2Error, match="0 resources"):
        a2.match_resources(res, "In Merit All Balancing Mechanism", ["2025-11"])


def test_presence_pass_through_streams_and_records():
    present, outside = {}, set()
    from collections import defaultdict
    present = defaultdict(set)
    rows = iter([row("U1", 6, 1), row("NB", 6, 1), row("U2", 6, 1)])
    passed = list(a2._note_presence(rows, "2026-01", {"U1"}, {"U1", "U2"}, present, outside))
    assert len(passed) == 3                      # every row still reaches the valuation
    assert present == {"U1": {"2026-01"}}        # U2 is fleet but has no GC: not exposure
    assert outside == {"NB"}                     # NESO battery outside the M10 fleet
