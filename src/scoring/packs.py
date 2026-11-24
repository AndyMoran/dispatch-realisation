"""Private packs: one file per lead party, from the pinned run's per-unit table.

    uv run python -m src.scoring.packs --reply-by YYYY-MM-DD

Reads only `data/interim/scoring/unit_results.json` and the run record, and
writes `data/interim/packs/<lead party>.md`, gitignored, never committed. The
contents are PROJECT.md §7a's list and nothing else:

- each of the lead party's BM units, by ID;
- Claim 1's score and interval, under both branches, labelled descriptive, with
  no flag, because Claim 1's known-answer gate failed at every tested length;
- Claim 2's lower-wall status over weeks not certified contract-free, labelled
  as not proof of under-declaration (deviation 6; ASSUMPTIONS P11);
- Claim 5's latency for each unit (PREREGISTRATION §7), with its bounds;
- the method, by DOI; that Claim 3 was dropped under §8, and that Claim 4 was not
  run on real units in version 1. No flag of any claim appears.

Only the preregistered settings reach a pack (reading (f)); the per-unit table
holds nothing else. Each pack is checked before it is written: it may name only
its own lead party and that party's units. The reply date must be at least 10
working days after the packs are prepared (§7a), counting England and Wales bank
holidays.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.ingest import pull
from src.scoring.run import PRIVATE_OUT, RECORD_OUT

PACKS_DIR = Path("data/interim/packs")
METHOD_DOI = "10.5281/zenodo.24484015"  # v1.0.7-lock, the latest lock
REPOSITORY = "https://github.com/AndyMoran/dispatch-realisation"
REPLY_WORKING_DAYS = 10
LONDON = ZoneInfo("Europe/London")  # working days are counted on UK dates
# England and Wales bank holidays, 1 Nov 2026 to 31 Jan 2027 (gov.uk, read 24 Nov
# 2026: none in November). Dates outside that range stop the run: extend the list.
BANK_HOLIDAYS = frozenset({date(2026, 12, 25), date(2026, 12, 28), date(2027, 1, 1)})
HOLIDAYS_KNOWN = (date(2026, 11, 1), date(2027, 1, 31))


class PackError(RuntimeError):
    """Stops the packs before any is written."""


# ------------------------------------------------------------------ dates


def working_days_between(start: date, end: date) -> int:
    """Return the working days after `start` up to and including `end`."""
    if not (HOLIDAYS_KNOWN[0] <= start <= end <= HOLIDAYS_KNOWN[1]):
        raise PackError("dates outside the bank holidays listed in the code")
    days = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in BANK_HOLIDAYS:
            days += 1
    return days


# ------------------------------------------------------------------ text


def slug(name: str) -> str:
    """Return a file name for a lead party: letters, digits and hyphens."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    if not s:
        raise PackError("a lead party name gives an empty file name")
    return s


def num(value: object, places: int = 3) -> str:
    """Return a number to fixed places, or a dash."""
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PackError("a figure is not a number")
    return f"{value:.{places}f}"


def cell(text: object) -> str:
    """Return text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|")


def pct(value: object) -> str:
    """Return a share as a percentage to one place, or a dash."""
    if value is None:
        return "—"
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PackError("a share is not a number")
    return f"{100 * value:.1f}%"


CLAIM1_LABEL = (
    "Descriptive only. How closely the unit's declarations tracked its metered "
    "flows. No Claim 1 flag is given: Claim 1's known-answer test failed at "
    "every tested length."
)
CLAIM2_LABEL = (
    "Not proof of under-declaration. A low declaration can reflect reserve or "
    "response protection, and Claim 2's known-answer test flagged honest "
    "synthetic batteries. Weeks are not certified contract-free; version 1 "
    "cannot separate contract-exposed weeks from those of unknown status."
)
CLAIM5_LABEL = (
    "L is the time from each accepted instruction to the unit's next MDO/MDB "
    "record. That record need not respond to the instruction, so L is an upper "
    "bound on the time to respond, and the share within the benchmark a lower "
    "bound. BMRS publish times may record publication rather than receipt."
)


def unit_section(u: Mapping[str, Any]) -> list[str]:
    """Return the Markdown lines for one unit.

    The keys are those `src/scoring/run.py` writes and, for Claim 5,
    `src/claims/claim5.py: summarise`; the end-to-end test is the guard.
    """
    lines = [f"### {u['unit']}", ""]
    mw = u.get("registered_mw")
    lines.append(
        f"Registered capacity: {num(mw, 1)} MW. Secondary BM unit: "
        f"{'yes' if u.get('secondary') else 'no'}. Adoption week starts "
        f"{str(u['adoption_week_start'])[:10]}."
    )
    lines += ["", "**Claim 1: tracking error.** " + CLAIM1_LABEL, ""]
    lines += ["| Branch | η̂ | Weeks | Error ratio | 95% interval | Signed ratio |"]
    lines += ["|---|---|---|---|---|---|"]
    for b in ("A", "B"):
        br = u["branches"][b]
        c1 = br["claim1"]
        if c1["score"] is None:
            lines.append(
                f"| {b} | {num(br['eta_hat'])} | {c1['scored_weeks']} | not scored: "
                f"{cell(c1['reason'])} | — | — |"
            )
            continue
        low, high = c1["interval_95"] or (None, None)
        lines.append(
            f"| {b} | {num(br['eta_hat'])} | {c1['scored_weeks']} | {num(c1['score'])} "
            f"| {num(low)} to {num(high)} | {num(c1['signed'])} |"
        )
    lines += ["", "**Claim 2: lower-wall violations.** " + CLAIM2_LABEL, ""]
    lines += [
        "| Branch | Weeks | Share of periods in violation | Median weekly share |"
    ]
    lines += ["|---|---|---|---|"]
    for b in ("A", "B"):
        c2 = u["branches"][b]["claim2"]
        if c2["violation_share_pooled"] is None:
            lines.append(
                f"| {b} | {c2['scored_weeks']} | not scored: {cell(c2['reason'])} | — |"
            )
            continue
        lines.append(
            f"| {b} | {c2['scored_weeks']} | {pct(c2['violation_share_pooled'])} "
            f"| {pct(c2['median_weekly_share'])} |"
        )
    c5 = u["claim5"]
    lines += ["", "**Claim 5: redeclaration latency.** " + CLAIM5_LABEL, ""]
    if not c5["boas"]:
        lines.append("No accepted instruction in the scoring window.")
    else:
        censored = ", ".join(f"{k}: {v}" for k, v in sorted(c5["censored"].items()))
        lines.append(
            f"{c5['boas']} accepted instructions; {c5['observed']} followed by a "
            f"record within the window ({censored} censored). Median L "
            f"{num(c5['median_min'], 1)} min; 75th percentile {num(c5['p75_min'], 1)}"
            f" min; 90th percentile {num(c5['p90_min'], 1)} min. Share within "
            f"{c5['benchmark_min']:g} min: {pct(c5['share_within_benchmark'])}."
        )
    lines.append("")
    return lines


def render(
    party: str,
    units: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any],
    prepared: date,
    reply_by: date,
) -> str:
    """Return one lead party's pack as Markdown."""
    lines = [
        f"# Private results pack: {party}",
        "",
        "*Dispatch Realisation of GB Batteries*, version 1. Confidential to the "
        "lead party named above. It is not published.",
        "",
        f"- Prepared {prepared.isoformat()} from the pinned scoring run of "
        f"{str(record['finished_utc'])[:10]} (code commit "
        f"`{str(record['code_commit'])[:12]}`).",
        f"- Please reply by {reply_by.isoformat()} with any error in data or "
        "method. A demonstrated error is fixed before fleet results are "
        "published, and logged publicly without naming the unit.",
        f"- Method: the preregistration and its deviations, DOI {METHOD_DOI}; "
        f"code and fleet results: {REPOSITORY}.",
        "- This pack goes to each unit's lead party, who may not be its "
        "operator or owner.",
        "",
        "## What these results are",
        "",
        "They test whether the unit's MDO/MDB declarations are physically "
        "coherent with its metered flows. They do not establish misconduct, and "
        "no over- or under-declaration flag is given for any claim.",
        "",
        "Each result is shown under two readings of how declarations relate to "
        "stored energy (Branches A and B), because which one the declarations "
        "follow is not yet confirmed. η̂ is the round-trip efficiency estimated "
        "from the unit's own metered flows.",
        "",
        "- **Claim 1** error ratio: the gap between the change in declared "
        "energy and the change the metered flows imply, summed over usable "
        "half-hours and divided by the energy that flowed; the median over "
        "weeks. 0 is perfect tracking. The signed ratio keeps the sign: "
        "positive means declared energy rose more than the meter implies.",
        "- **Claim 2** share: the share of settlement periods in which declared "
        "energy sat below the lowest level the metered flows allow, by more "
        "than 2% of that week's range.",
        "- **Claim 5** L: minutes from an accepted instruction to the unit's "
        "next MDO/MDB record; default records (±9999) are not counted.",
        "",
        f"## Your units ({len(units)})",
        "",
    ]
    for u in units:
        lines += unit_section(u)
    lines += [
        "## Claims not reported per unit",
        "",
        "- Claim 3 was dropped under §8 of the preregistration: no Claim 3 "
        "result or flag is given for any unit.",
        "- Claim 4 was not run on real units in version 1: its meter-flow gate "
        "failed to give a reliable upper bound under the tested efficiency "
        "estimation and data conditions.",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ checks


def mentions(text: str, name: str) -> bool:
    """Return whether the text names `name` as a whole token."""
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def check_pack(
    text: str, party: str, own: set[str], all_units: set[str], parties: set[str]
) -> None:
    """Stop unless a pack names only its own lead party and that party's units."""
    for u in all_units - own:
        if mentions(text, u):
            raise PackError("a pack names another lead party's unit")
    # The pack's own party name is removed first, so another party's name inside
    # it ("Alpha" in "Alpha Energy Ltd") is not mistaken for a leak, while a bare
    # "Alpha" anywhere else still is.
    rest = re.sub(rf"(?<![\w-]){re.escape(party)}(?![\w-])", " ", text)
    for p in parties - {party}:
        if p and mentions(rest, p):
            raise PackError("a pack names another lead party")
    for u in own:
        if not mentions(text, u):
            raise PackError("a pack leaves out one of its own units")


def build(
    table: Mapping[str, Any], record: Mapping[str, Any], prepared: date, reply_by: date
) -> dict[str, str]:
    """Return every pack's text by file name, checked; nothing is written."""
    if working_days_between(prepared, reply_by) < REPLY_WORKING_DAYS:
        raise PackError(
            f"the reply date is fewer than {REPLY_WORKING_DAYS} working days away"
        )
    units = list(table["units"])
    by_party: dict[str, list[Mapping[str, Any]]] = {}
    for u in units:
        party = str(u.get("lead_party") or "").strip()
        if not party:
            raise PackError("a unit has no lead party")
        by_party.setdefault(party, []).append(u)
    all_units = {str(u["unit"]) for u in units}
    if len(all_units) != len(units):
        raise PackError("a unit appears twice in the per-unit table")
    parties = set(by_party)
    files: dict[str, str] = {}
    for party in sorted(by_party):
        own = sorted(by_party[party], key=lambda u: str(u["unit"]))
        text = render(party, own, record, prepared, reply_by)
        check_pack(text, party, {str(u["unit"]) for u in own}, all_units, parties)
        name = f"{slug(party)}.md"
        if name in files:
            raise PackError("two lead parties give the same file name")
        files[name] = text
    return files


def write_all(files: Mapping[str, str], out: Path, partial: Path) -> None:
    """Write every pack or none: into a side folder, then rename it into place.

    A failure while writing leaves only the side folder, which the next run
    refuses until it is removed; the packs folder never holds part of a set.
    """
    partial.mkdir(parents=True)
    for name, text in files.items():
        (partial / name).write_text(text, encoding="utf-8")
    if out.exists():
        out.rmdir()  # empty: checked before writing
    partial.rename(out)


def main(
    argv: Sequence[str] | None = None,
    root: Path = pull.ROOT,
    today: date | None = None,
) -> int:
    """Write the packs; print counts only."""
    parser = argparse.ArgumentParser(description="Private packs, one per lead party")
    parser.add_argument("--reply-by", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    try:
        table = json.loads((root / PRIVATE_OUT).read_text(encoding="utf-8"))
        record = json.loads((root / RECORD_OUT).read_text(encoding="utf-8"))
        prepared = today or datetime.now(LONDON).date()
        files = build(table, record, prepared, args.reply_by)
        out = root / PACKS_DIR
        partial = out.with_name(out.name + ".partial")
        if out.exists() and any(out.iterdir()):
            raise PackError(
                f"{PACKS_DIR} is not empty: remove the previous packs before a new run"
            )
        if partial.exists():
            raise PackError(f"{partial.name} exists: an earlier run was cut short")
    except (PackError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"stopped: {exc!r}", file=sys.stderr)
        return 1
    write_all(files, out, partial)
    units = sum(text.count("\n### ") for text in files.values())
    print(json.dumps({"packs": len(files), "units": units}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
