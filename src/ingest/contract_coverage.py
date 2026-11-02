"""Claim 2 contract screen, stage 3: hand files, pre-coverage report, one coverage run.

    python -m src.ingest.contract_coverage prepare    # draw the spot check; write templates
    python -m src.ingest.contract_coverage precheck   # validate hand files; report residual risk
    python -m src.ingest.contract_coverage coverage   # the single coverage run

Rules: PREREGISTRATION.md §4 (committed before this script first runs).

- Scope: EAC and Static FFR awards for auction units whose technology is battery
  or not identified (contract_sources.in_scope).
- Matching: the auto-rule (contract_sources.auto_match), unless the spot check
  fails, plus hand decisions in config/contract/alias.csv, which override it.
- Spot check: 30 auto-matched rows, seed SEED; unverifiable counts as wrong;
  more than MAX_WRONG wrong drops the auto-rule.
- Association, no chaining: (a) participant of a unit matched to U; (b) participant
  of a unit matched to any fleet unit with U's lead party; (c) hand links.
  Undetermined or missing participants, and lead parties not checked, are
  associated with everything. Unmatched units with no participant affect every unit.
- Contract-free unit-week: no award, by a unit matched to U or by an unmatched
  in-scope unit of an associated participant, overlapping the ISO week (UTC).
- Decision: fleet result if >= MIN_UNITS eligible units have >= MIN_CLEAN_WEEKS
  contract-free weeks; otherwise the hard flag is a case series.

Hand files (committed; they name units but hold no scores):
    config/contract/auto_matches.csv, spot_check.csv, links.csv,
    lead_party_check.csv, alias.csv
Outputs:
    outputs/lock/contract_precheck.json, outputs/lock/contract_coverage.json (counts only)
    data/interim/contract/unit_week_status.csv (per unit; gitignored)
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.ingest.contract_sources import RESOURCES, WINDOW_START, _check_resource, _sql, in_scope
from src.ingest.lock_counts import full_weeks_after, week_start

SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config" / "contract"
DRAFT = ROOT / "data" / "interim" / "contract" / "alias_draft.csv"
PRECHECK = ROOT / "outputs" / "lock" / "contract_precheck.json"
COVERAGE = ROOT / "outputs" / "lock" / "contract_coverage.json"

# Mirrors PREREGISTRATION.md §4; change there first, and only before `prepare` runs.
SEED = 20261102
SAMPLE_SIZE = 30
MAX_WRONG = 3
MIN_UNITS = 30
MIN_CLEAN_WEEKS = 2
OUTCOMES = {"confirmed", "wrong", "unverifiable"}
LINK_STATUS = {"linked", "no_fleet", "undetermined"}
ALIAS_DECISIONS = {"bm_unit", "not_fleet", "unmappable"}
SQL_ROW_LIMIT = 32000   # CKAN's datastore_search_sql cap; reaching it means truncation

HAND_FILES = ("auto_matches.csv", "spot_check.csv", "links.csv",
              "lead_party_check.csv", "alias.csv")


class CoverageError(RuntimeError):
    """Stops the run instead of guessing (PIPELINE_RULES §1–2)."""


# ------------------------------------------------------------------ pure rules

def auto_rule_kept(spot: list[dict]) -> tuple[bool, int]:
    """Unverifiable counts as wrong; more than MAX_WRONG wrong drops the auto-rule."""
    bad = sum(1 for r in spot if r["outcome"] in ("wrong", "unverifiable"))
    return bad <= MAX_WRONG, bad


def draw_sample(auto_rows: list[dict], k: int = SAMPLE_SIZE, seed: int = SEED) -> list[dict]:
    rows = sorted(auto_rows, key=lambda r: (r["source"], r["auction_unit"]))
    return random.Random(seed).sample(rows, min(k, len(rows)))


def associated(unit: str, lead: dict[str, str], matched: dict[tuple, str],
               party_of: dict[tuple, str], links: dict[str, set[str]],
               extra: dict[str, set[str]], checked_leads: set[str]) -> set[str] | None:
    """Participants associated with a fleet unit; None means 'every participant'.

    (a) participants of auction units matched to the unit; (b) of units matched to
    any fleet unit with the same lead party; (c) hand links, from either side.
    A lead party not checked from its own side is associated with everything.
    """
    lp = lead.get(unit)
    if lp not in checked_leads:
        return None
    out = set()
    for key, bm in matched.items():
        if bm == unit or (lp and lead.get(bm) == lp):
            out.add(party_of[key])
    out |= {p for p, leads in links.items() if lp in leads}
    out |= extra.get(lp, set())
    return out


def clean_weeks(weeks: list[date], own: set[date], unmatched_weeks_by_party: dict[str, set[date]],
                assoc: set[str] | None, orphan_weeks: set[date],
                undetermined: set[str]) -> list[date]:
    """Weeks with no award by a matched unit, an associated party's unmatched unit,
    an undetermined party's unmatched unit, or an unmatched unit with no party."""
    blocked = set(own) | orphan_weeks
    for p, wk in unmatched_weeks_by_party.items():
        if assoc is None or p in assoc or p in undetermined:
            blocked |= wk
    return [w for w in weeks if w not in blocked]


def iso_weeks(first: date, end_exclusive: date) -> list[date]:
    out, w = [], first
    while w + timedelta(days=7) <= end_exclusive:
        out.append(w)
        w += timedelta(days=7)
    return out


# ------------------------------------------------------------------ file helpers

def _read(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    if path.exists():
        raise CoverageError(f"{path.relative_to(ROOT)} exists; hand work is never overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _draft() -> list[dict]:
    if not DRAFT.exists():
        raise CoverageError("Run `python -m src.ingest.contract_sources units` first.")
    rows = _read(DRAFT)
    for r in rows:
        r["scope"] = in_scope(set(r["technology"].split(";")))
        r["auto"] = r["auto_rule"] == "True"
    return rows


def _fleet() -> tuple[dict[str, str], dict[str, str], set[str], dict[str, str]]:
    """Lead party per fleet unit, adoption cohort per unit, eligible set, unit type."""
    snaps = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))
    payload = json.loads(snaps[-1].read_bytes())
    ref = payload.get("data", payload) if isinstance(payload, dict) else payload
    ref = {str(r["elexonBmUnit"]): r for r in ref if r.get("elexonBmUnit")}
    adoption = [r for r in _read(ROOT / "outputs" / "gate_a1" / "adoption_dates.csv")
                if r["status"] == "adopted"]
    lead = {r["bm_unit"]: str((ref.get(r["bm_unit"]) or {}).get("leadPartyName") or "")
            for r in adoption}
    cohort = {r["bm_unit"]: r["cohort"] for r in adoption}
    eligible = {u for u, c in cohort.items() if full_weeks_after(c) >= 4}
    utype = {u: str((ref.get(u) or {}).get("bmUnitType")) for u in cohort}
    return lead, cohort, eligible, utype


# ------------------------------------------------------------------ commands

def prepare() -> None:
    rows = _draft()
    lead, _, eligible, _ = _fleet()
    scope = [r for r in rows if r["scope"]]
    auto = [r for r in scope if r["auto"]]
    _write_csv(CFG / "auto_matches.csv",
               ["source", "registered_participant", "auction_unit", "bm_unit", "score_1", "score_2"],
               [[r["source"], r["registered_participant"], r["auction_unit"], r["candidate_1"],
                 r["score_1"], r["score_2"]] for r in sorted(auto, key=lambda r: (r["source"], r["auction_unit"]))])
    sample = draw_sample([{"source": r["source"], "auction_unit": r["auction_unit"], **r} for r in auto])
    _write_csv(CFG / "spot_check.csv",
               ["source", "registered_participant", "auction_unit", "technology", "location",
                "bm_unit", "bm_lead_party", "outcome", "evidence"],
               [[r["source"], r["registered_participant"], r["auction_unit"], r["technology"],
                 r["location"], r["candidate_1"], lead.get(r["candidate_1"], ""), "", ""]
                for r in sample])
    via = defaultdict(set)
    for r in auto:
        via[r["registered_participant"]].add(lead.get(r["candidate_1"], ""))
    parties = Counter(r["registered_participant"] for r in scope)
    _write_csv(CFG / "links.csv",
               ["registered_participant", "in_scope_units", "auto_matched_units",
                "lead_parties_via_auto_matches", "status", "lead_parties", "evidence"],
               [[p, n, sum(1 for r in auto if r["registered_participant"] == p),
                 ";".join(sorted(x for x in via[p] if x)), "", "", ""]
                for p, n in sorted(parties.items())])
    leads = Counter(lead[u] for u in eligible)
    by_lead = defaultdict(set)
    for r in auto:
        by_lead[lead.get(r["candidate_1"], "")].add(r["registered_participant"])
    _write_csv(CFG / "lead_party_check.csv",
               ["lead_party", "eligible_units", "participants_via_auto_matches",
                "extra_participants", "checked", "evidence"],
               [[lp, n, ";".join(sorted(by_lead[lp])), "", "", ""] for lp, n in sorted(leads.items())])
    _write_csv(CFG / "alias.csv", ["source", "auction_unit", "decision", "bm_unit", "evidence"], [])
    print(json.dumps({"in_scope": len(scope), "auto_matched": len(auto),
                      "spot_check_rows": len(sample), "participants": len(parties),
                      "eligible_lead_parties": len(leads)}, indent=2))
    print(f"\nFill in {CFG.relative_to(ROOT)}/: spot_check.csv (outcome, evidence), links.csv "
          "(status, lead_parties, evidence), lead_party_check.csv (extra_participants, "
          "checked=yes, evidence), alias.csv (optional). Commit them, then run precheck.")


def _hand() -> dict:
    files = {name: CFG / name for name in HAND_FILES}
    missing = [n for n, p in files.items() if not p.exists()]
    if missing:
        raise CoverageError(f"Missing hand files: {missing}. Run prepare first.")
    auto = _read(files["auto_matches.csv"])
    spot = _read(files["spot_check.csv"])
    expected = {(r["source"], r["auction_unit"]) for r in draw_sample(auto)}
    if {(r["source"], r["auction_unit"]) for r in spot} != expected:
        raise CoverageError("spot_check.csv rows differ from the seeded draw.")
    bad = [r["auction_unit"] for r in spot if r["outcome"] not in OUTCOMES]
    if bad:
        raise CoverageError(f"{len(bad)} spot-check rows lack a valid outcome {sorted(OUTCOMES)}.")
    links = _read(files["links.csv"])
    for r in links:
        if r["status"] and r["status"] not in LINK_STATUS:
            raise CoverageError(f"links.csv: bad status {r['status']!r}")
    alias = _read(files["alias.csv"])
    for r in alias:
        if r["decision"] not in ALIAS_DECISIONS:
            raise CoverageError(f"alias.csv: bad decision {r['decision']!r}")
    return {"files": files, "auto": auto, "spot": spot, "links": links, "alias": alias,
            "leads": _read(files["lead_party_check.csv"])}


def _resolve(h: dict, draft: list[dict]) -> dict:
    kept, n_bad = auto_rule_kept(h["spot"])
    scope = {(r["source"], r["auction_unit"]): r for r in draft if r["scope"]}
    party_of = {k: r["registered_participant"] for k, r in scope.items()}
    matched = {}
    if kept:
        matched = {(r["source"], r["auction_unit"]): r["bm_unit"] for r in h["auto"]}
    else:   # failure drops the auto-rule; only hand-confirmed spot rows survive
        matched = {(r["source"], r["auction_unit"]): r["bm_unit"]
                   for r in h["spot"] if r["outcome"] == "confirmed"}
    removed = set()
    for r in h["alias"]:
        key = (r["source"], r["auction_unit"])
        matched.pop(key, None)
        if r["decision"] == "bm_unit":
            matched[key] = r["bm_unit"]
        elif r["decision"] == "not_fleet":
            removed.add(key)
    matched = {k: v for k, v in matched.items() if k in scope}
    unmatched = [k for k in scope if k not in matched and k not in removed]
    seen = {r["registered_participant"] for r in h["links"]}
    undetermined = {r["registered_participant"] for r in h["links"]
                    if r["status"] in ("", "undetermined")}
    undetermined |= {party_of[k] for k in scope if party_of[k] and party_of[k] not in seen}
    links = {r["registered_participant"]: set(filter(None, r["lead_parties"].split(";")))
             for r in h["links"] if r["status"] == "linked"}
    checked = {r["lead_party"] for r in h["leads"] if r["checked"].strip().lower() == "yes"}
    extra = {r["lead_party"]: set(filter(None, r["extra_participants"].split(";")))
             for r in h["leads"]}
    return {"kept": kept, "n_bad": n_bad, "party_of": party_of, "matched": matched,
            "unmatched": unmatched, "removed": removed, "undetermined": undetermined,
            "links": links, "checked": checked, "extra": extra}


def precheck() -> dict:
    h, draft = _hand(), _draft()
    lead, _, eligible, _ = _fleet()
    x = _resolve(h, draft)
    eligible_leads = {lead[u] for u in eligible}
    out = {"schema_version": SCHEMA_VERSION, "run_utc": datetime.now(timezone.utc).isoformat(),
           "spot_check": {"rows": len(h["spot"]), "wrong_or_unverifiable": x["n_bad"],
                          "max_wrong": MAX_WRONG, "auto_rule_kept": x["kept"],
                          "outcomes": dict(Counter(r["outcome"] for r in h["spot"]))},
           "in_scope_auction_units": len(x["party_of"]),
           "matched": len(x["matched"]), "not_fleet": len(x["removed"]),
           "unmatched": len(x["unmatched"]),
           "unmatched_without_participant": sum(1 for k in x["unmatched"] if not x["party_of"][k]),
           "participants_undetermined": len(x["undetermined"]),
           "eligible_lead_parties": len(eligible_leads),
           "eligible_lead_parties_not_checked": len(eligible_leads - x["checked"]),
           "hand_file_sha256": {n: _sha(p) for n, p in h["files"].items()},
           "draft_sha256": _sha(DRAFT)}
    PRECHECK.parent.mkdir(parents=True, exist_ok=True)
    PRECHECK.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True))
    print("\nCommit this file, then run coverage once.")
    return out


def _awards(scope_keys: set[tuple]) -> dict[tuple, set[date]] | None:
    """ISO-week starts (UTC) of awards per in-scope auction unit; None if a set fails to load."""
    filters = {"eac": f'"{RESOURCES["eac"]["qty"]}"::numeric > 0',
               "sffr": f'"Status" = \'Accepted\' AND "{RESOURCES["sffr"]["qty"]}"::numeric > 0'}
    out: dict[tuple, set[date]] = defaultdict(set)
    for key, spec in RESOURCES.items():
        try:
            _check_resource(key)
            recs = _sql(
                f'SELECT "{spec["unit"]}" AS unit, '
                f'date_trunc(\'week\', "{spec["start"]}"::timestamp) AS w1, '
                f'date_trunc(\'week\', "{spec["end"]}"::timestamp - interval \'1 second\') AS w2 '
                f'FROM "{spec["id"]}" WHERE "{spec["start"]}" >= \'{WINDOW_START}\' '
                f'AND {filters[key]} GROUP BY 1, 2, 3')
        except Exception as e:
            print(f"{key}: results could not be loaded ({type(e).__name__}: {e})")
            return None
        if len(recs) >= SQL_ROW_LIMIT:
            raise CoverageError(f"{key}: {len(recs)} rows hit the SQL cap; results truncated.")
        for r in recs:
            k = (key, r["unit"])
            if k in scope_keys:
                for w in (r["w1"], r["w2"]):
                    out[k].add(date.fromisoformat(str(w)[:10]))
    return out


def coverage() -> dict:
    if COVERAGE.exists():
        raise CoverageError("contract_coverage.json exists. The coverage count runs once (§4).")
    if not PRECHECK.exists():
        raise CoverageError("Run and commit precheck first.")
    pre = json.loads(PRECHECK.read_text())
    h, draft = _hand(), _draft()
    now = {n: _sha(p) for n, p in h["files"].items()}
    if now != pre["hand_file_sha256"] or _sha(DRAFT) != pre["draft_sha256"]:
        raise CoverageError("Hand files or draft changed since precheck. Re-run precheck and commit.")
    lead, cohort, eligible, utype = _fleet()
    x = _resolve(h, draft)
    awards = _awards(set(x["party_of"]))
    today = datetime.now(timezone.utc).date()
    end = today - timedelta(days=today.weekday())          # Monday of this week, exclusive
    unmatched_by_party: dict[str, set[date]] = defaultdict(set)
    orphan: set[date] = set()
    if awards is not None:
        for k in x["unmatched"]:
            p = x["party_of"][k]
            (unmatched_by_party[p] if p else orphan).update(awards.get(k, set()))
    rows, clean_counts = [], {}
    for u in sorted(eligible):
        weeks = iso_weeks(week_start(cohort[u]) + timedelta(days=7), end)
        if awards is None:
            clean = []
        else:
            own = set().union(*(awards.get(k, set()) for k, bm in x["matched"].items() if bm == u))
            assoc = associated(u, lead, x["matched"], x["party_of"], x["links"],
                               x["extra"], x["checked"])
            clean = clean_weeks(weeks, own, unmatched_by_party, assoc, orphan, x["undetermined"])
        clean_counts[u] = len(clean)
        rows.append([u, utype.get(u), len(weeks), len(clean), ";".join(map(str, clean))])
    dest = ROOT / "data" / "interim" / "contract" / "unit_week_status.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bm_unit", "bm_unit_type", "weeks_in_count", "contract_free_weeks", "clean_week_starts"])
        w.writerows(rows)
    passing = [u for u, n in clean_counts.items() if n >= MIN_CLEAN_WEEKS]
    out = {"schema_version": SCHEMA_VERSION, "run_utc": datetime.now(timezone.utc).isoformat(),
           "weeks_counted_before": end.isoformat(), "results_loaded": awards is not None,
           "eligible_units": len(eligible),
           "units_with_2plus_contract_free_weeks": len(passing),
           "units_with_2plus_by_type": dict(Counter(utype.get(u) for u in passing)),
           "contract_free_weeks_distribution": dict(sorted(Counter(clean_counts.values()).items())),
           "threshold_units": MIN_UNITS,
           "hard_flag": "fleet result" if len(passing) >= MIN_UNITS else "case series",
           "precheck_sha256": _sha(PRECHECK),
           "note": "Upper bounds: the B1610 screen is applied only at scoring."}
    COVERAGE.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, indent=2, sort_keys=True))
    return out


if __name__ == "__main__":
    cmd = (sys.argv[1:] or [""])[0]
    commands = {"prepare": prepare, "precheck": precheck, "coverage": coverage}
    if cmd not in commands:
        sys.exit("usage: python -m src.ingest.contract_coverage [prepare|precheck|coverage]")
    commands[cmd]()
