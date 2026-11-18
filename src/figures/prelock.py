"""Pre-lock fleet charts from data already examined: declarations, reference data,
NESO auction results. Fleet level only: no BM unit or auction unit is labelled.

    uv run --with matplotlib python -m src.figures.prelock

Figure 2: Claim 3 power bound, per-unit share of declaration-minutes within reach.
Figure 3: declared duration, per-unit median MDO / registered MW, in hours.
Figure 4: in-scope auction units holding awards each week, by service.
Outputs: outputs/figures/fig2_power_bound.png, fig3_declared_duration.png,
         fig4_contract_awards.png
"""

from __future__ import annotations

import csv
import json
import tomllib
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median

import numpy as np

from src.figures.style import SERIES, axes, titles

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "figures"


# ------------------------------------------------------------------ drawing (testable)


def draw_power_bound(
    shares_main: list[float],
    shares_v: list[float],
    n_no_mw: int,
    n_eligible: int,
    threshold: float = 0.10,
) -> Path:
    bins = np.arange(0, 1.05, 0.05)
    fig, ax = axes()
    ax.hist(
        [shares_main, shares_v],
        bins=bins,
        stacked=True,
        color=SERIES[:2],
        edgecolor="#fcfcfb",
        linewidth=2,
        label=[
            f"Non-secondary units ({len(shares_main)})",
            f"Secondary units ({len(shares_v)})",
        ],
    )
    ax.axvline(threshold, color="#52514e", linewidth=1.2, linestyle=(0, (3, 2)))
    passing = sum(s >= threshold for s in shares_main + shares_v)
    ax.annotate(
        f"Pre-registered bar: 10%\n{passing} of {n_eligible} eligible units pass "
        f"(needed 30)",
        (threshold, ax.get_ylim()[1] * 0.92),
        xytext=(8, 0),
        textcoords="offset points",
        fontsize=8.5,
        color="#0b0b0b",
        va="top",
    )
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    titles(
        fig,
        ax,
        "Claim 3 can reach most units: the power bound",
        "Share of each unit's declarations small enough for a one-hour "
        "full-power instruction to reach half its MDO",
        "Share of declaration-minutes with 1 MWh ≤ MDO ≤ 2 × MW × 1 h",
        "Units",
        f"Eligible units with a registered MW; {n_no_mw} without one count as "
        "not identifiable. "
        "Source: BMRS MDO, reference data. outputs/lock/power_bound.json",
    )
    return _save(fig, "fig2_power_bound.png")


def draw_duration(hours_main: list[float], hours_v: list[float]) -> Path:
    bins = np.arange(0, 4.25, 0.25)
    fig, ax = axes()
    ax.hist(
        [np.clip(hours_main, 0, 4), np.clip(hours_v, 0, 4)],
        bins=bins,
        stacked=True,
        color=SERIES[:2],
        edgecolor="#fcfcfb",
        linewidth=2,
        label=[
            f"Non-secondary units ({len(hours_main)})",
            f"Secondary units ({len(hours_v)})",
        ],
    )
    ax.set_xlim(0, 4)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:g} h" if v < 4 else "≥4 h")
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    titles(
        fig,
        ax,
        "How long batteries say they could run",
        "Each unit's median MDO divided by its registered MW: "
        "hours of full-power export declared",
        "Median declared duration (hours)",
        "Units",
        "Eligible units with a registered MW, minutes after the adoption week. "
        "MDO is net of protected energy, so this understates tank size. "
        "Source: BMRS MDO, reference data.",
    )
    return _save(fig, "fig3_declared_duration.png")


def draw_awards(weeks: list[date], by_service: dict[str, list[int]]) -> Path:
    fig, ax = axes()
    x = np.arange(len(weeks))
    bottom = np.zeros(len(weeks))
    for i, (name, vals) in enumerate(by_service.items()):
        ax.bar(
            x,
            vals,
            bottom=bottom,
            color=SERIES[i],
            width=0.8,
            edgecolor="#fcfcfb",
            linewidth=2,
            label=name,
        )
        bottom += np.array(vals)
    step = max(1, len(weeks) // 8)
    ax.set_xticks(x[::step], [w.strftime("%d %b") for w in weeks[::step]])
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=3)
    ax.set_ylim(0, bottom.max() * 1.18 if len(weeks) else 1)
    titles(
        fig,
        ax,
        "Why no battery-week could be certified contract-free",
        "In-scope auction units (battery or unidentified technology) "
        "holding awards, per ISO week",
        "Week starting",
        "Auction units with awards",
        "Units holding several services count once per service. "
        "Source: NESO EAC and Static FFR results by unit.",
    )
    return _save(fig, "fig4_contract_awards.png")


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / name
    fig.savefig(dest, facecolor=fig.get_facecolor())
    return dest


# ------------------------------------------------------------------ data (run locally)


def _power_inputs():
    from src.ingest.lock_counts import full_weeks_after, mw_source, week_start
    from src.ingest.power_bound import _load_segments, minute_values, unit_shares

    cfg = tomllib.loads((ROOT / "config" / "gate_a1.toml").read_text())
    snap = sorted((ROOT / "data" / "raw" / "reference").glob("bmunits__dl*.json"))[-1]
    ref = json.loads(snap.read_bytes())
    ref = {
        str(r["elexonBmUnit"]): r
        for r in (ref.get("data", ref) if isinstance(ref, dict) else ref)
    }
    rows = [
        r
        for r in csv.DictReader(
            open(ROOT / "outputs" / "gate_a1" / "adoption_dates.csv")
        )
        if r["status"] == "adopted" and full_weeks_after(r["cohort"]) >= 4
    ]
    end = datetime.combine(
        date.fromisoformat(cfg["data"]["data_cutoff"]) + timedelta(days=1),
        datetime.min.time(),
        UTC,
    )
    segs, _ = _load_segments(cfg["api"])
    by_unit = defaultdict(list)
    for s in segs["MDO"]:
        by_unit[s.unit].append(s)
    share = {"main": [], "v": []}
    hours = {"main": [], "v": []}
    no_mw = 0
    for r in rows:
        rr = ref.get(r["bm_unit"]) or {}
        src = mw_source(rr)
        mw = (
            float(rr["generationCapacity"])
            if src == "gc"
            else abs(float(rr["demandCapacity"]))
            if src == "dc"
            else None
        )
        if not mw:
            no_mw += 1
            continue
        first = datetime.combine(
            week_start(r["cohort"]) + timedelta(days=7),
            datetime.min.time(),
            UTC,
        )
        mins = minute_values(by_unit[r["bm_unit"]], end)
        s = unit_shares(mins, first, end, mw, cfg["data"]["default_abs_mwh"])
        if not s:
            continue
        g = "v" if str(rr.get("bmUnitType")) == "V" else "main"
        share[g].append(s["k2_t60"])
        vals = [abs(v) for t, v in mins.items() if first <= t < end and abs(v) < 9999]
        hours[g].append(median(vals) / mw)
    return share, hours, no_mw, len(rows)


def _award_inputs():
    """Weekly in-scope auction units with awards, by service.

    Written in the same plain form as contract_coverage._awards, which NESO's
    firewall accepts: no technology clause in the SQL (OR/IS NULL/IN clauses are
    refused), GROUP BY only. Scope uses contract_sources.in_scope, as the coverage
    run did; distinct units are counted in Python.
    """
    from src.ingest.contract_coverage import SQL_ROW_LIMIT
    from src.ingest.contract_sources import (
        RESOURCES,
        WINDOW_START,
        _check_resource,
        _sql,
        in_scope,
    )

    units: dict[str, dict[date, set]] = defaultdict(lambda: defaultdict(set))
    for key, spec in RESOURCES.items():
        _check_resource(key)
        qty = (
            f'"{spec["qty"]}"::numeric > 0'
            if key == "eac"
            else f'"Status" = \'Accepted\' AND "{spec["qty"]}"::numeric > 0'
        )
        svc = f'"{spec["service"]}"' if key == "eac" else "'Static FFR'"
        recs = _sql(
            f'SELECT "{spec["unit"]}" AS u, {svc} AS s, "{spec["tech"]}" AS t, '
            f"date_trunc('week', \"{spec['start']}\"::timestamp) AS w "
            f'FROM "{spec["id"]}" WHERE "{spec["start"]}" >= \'{WINDOW_START}\' '
            f"AND {qty} GROUP BY 1, 2, 3, 4"
        )
        if len(recs) >= SQL_ROW_LIMIT:
            raise RuntimeError(
                f"{key}: {len(recs)} rows hit the SQL cap; results truncated."
            )
        for r in recs:
            if not in_scope({str(r["t"] if r["t"] is not None else "")}):
                continue
            name = (
                "Static FFR"
                if key == "sffr"
                else (
                    "Response (DC, DM, DR)"
                    if r["s"] == "Response"
                    else "Reserve (QR, SR, BR)"
                )
            )
            units[name][date.fromisoformat(str(r["w"])[:10])].add((key, r["u"]))
    today = datetime.now(UTC).date()
    last = today - timedelta(days=today.weekday())  # exclude the current week
    weeks = sorted({w for c in units.values() for w in c if w < last})
    order = ["Response (DC, DM, DR)", "Reserve (QR, SR, BR)", "Static FFR"]
    return weeks, {
        k: [len(units[k].get(w, ())) for w in weeks] for k in order if k in units
    }


def main() -> None:
    import sys

    if "--awards-only" not in sys.argv:
        share, hours, no_mw, n = _power_inputs()
        print(draw_power_bound(share["main"], share["v"], no_mw, n))
        print(draw_duration(hours["main"], hours["v"]))
    print(draw_awards(*_award_inputs()))


if __name__ == "__main__":
    main()
