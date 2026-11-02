"""Contract-coverage rules on synthetic inputs. No network, no real data."""
from datetime import date, timedelta

from src.ingest.contract_coverage import (associated, auto_rule_kept, clean_weeks, draw_sample,
                                          iso_weeks)

W = [date(2026, 9, 7) + timedelta(days=7 * i) for i in range(4)]   # four Mondays


def test_spot_check_unverifiable_counts_as_wrong():
    rows = [{"outcome": "confirmed"}] * 26 + [{"outcome": "wrong"}] * 2 + [{"outcome": "unverifiable"}] * 2
    assert auto_rule_kept(rows) == (False, 4)
    assert auto_rule_kept(rows[:-1]) == (True, 3)


def test_sample_is_seeded_and_order_free():
    rows = [{"source": "eac", "auction_unit": f"U{i}"} for i in range(173)]
    a = draw_sample(rows)
    b = draw_sample(list(reversed(rows)))
    assert len(a) == 30 and a == b


def test_association_rules_a_b_c_without_chaining():
    lead = {"X": "LP1", "Y": "LP1", "Z": "LP2"}
    matched = {("eac", "a1"): "X", ("eac", "a2"): "Z"}
    party_of = {("eac", "a1"): "P1", ("eac", "a2"): "P2", ("eac", "u9"): "P9"}
    links = {"P3": {"LP1"}}
    extra = {"LP1": {"P4"}}
    got = associated("Y", lead, matched, party_of, links, extra, {"LP1", "LP2"})
    assert got == {"P1", "P3", "P4"}          # (b) via X, (c) both sides; P2 not chained in
    assert associated("Y", lead, matched, party_of, links, extra, {"LP2"}) is None   # unchecked


def test_clean_weeks_blocks_conservatively():
    unmatched = {"P1": {W[1]}, "P5": {W[2]}, "PU": {W[3]}}
    got = clean_weeks(W, own={W[0]}, unmatched_weeks_by_party=unmatched, assoc={"P1"},
                      orphan_weeks=set(), undetermined={"PU"})
    assert got == [W[2]]                      # P5 not associated, so W[2] stays clean
    assert clean_weeks(W, set(), unmatched, None, set(), set()) == [W[0]]
    assert clean_weeks(W, set(), {}, set(), {W[0]}, set()) == W[1:]


def test_iso_weeks_complete_only():
    assert iso_weeks(W[0], W[3]) == W[:3]
    assert iso_weeks(W[0], W[0] + timedelta(days=6)) == []
