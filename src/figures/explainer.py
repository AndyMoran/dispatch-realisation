"""Figure 1, explainer: the tank walls, on a synthetic battery (no real data).

    uv run --with matplotlib python -m src.figures.explainer

A 100 MWh battery cycling twice a day. The meter alone fixes a lower wall (it
held at least what it later discharged); a disclosed nameplate fixes an upper
wall. An honest declaration stays between them; a unit declaring 1.25 x what it
holds breaks through the upper wall when nearly full.
Output: outputs/figures/fig1_tank_walls.png
"""
from pathlib import Path

import numpy as np

from src.figures.style import SERIES, axes, titles

ROOT = Path(__file__).resolve().parents[2]


def main() -> Path:
    t = np.linspace(0, 24, 24 * 12 + 1)                     # one day, 5-minute steps
    stock = 50 + 40 * np.sin(2 * np.pi * (t - 3) / 12)      # two cycles a day, 10-90 MWh
    nameplate = 100.0
    lower = stock - stock.min()                             # L_t = K_t - min K
    upper = nameplate - (stock.max() - stock)               # N - (max K - K_t)
    honest = stock
    over = 1.25 * stock                                     # declares 1.25 x available (f = 0.2)

    fig, ax = axes()
    ax.fill_between(t, lower, upper, color=SERIES[0], alpha=0.08, linewidth=0,
                    label="Where an honest declaration must lie")
    ax.plot(t, upper, color=SERIES[0], linewidth=2, linestyle=(0, (4, 2)),
            label="Upper wall: meter + disclosed nameplate (Claim 4)")
    ax.plot(t, lower, color=SERIES[0], linewidth=2, label="Lower wall: meter only (Claim 2)")
    ax.plot(t, honest, color=SERIES[2], linewidth=2, label="Honest declaration")
    ax.plot(t, over, color=SERIES[1], linewidth=2, label="Declares 1.25 × what it holds")
    breach = np.where(over > upper, over, np.nan)
    ax.plot(t, breach, color=SERIES[1], linewidth=5, alpha=0.35, solid_capstyle="round",
            label="…above what the tank could hold")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_ylim(0, 120)
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False,
                    fontsize=8.5, labelcolor="#0b0b0b")
    titles(fig, ax, "How the meter fences in a declaration",
           "Synthetic 100 MWh battery over one day. The meter fixes the walls; declarations must stay between them",
           "Hour of day", "Energy (MWh)",
           "Synthetic illustration, not real data. Definitions: PREREGISTRATION.md §3, §4, §6.")
    fig.set_size_inches(8, 5.2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    dest = ROOT / "outputs" / "figures" / "fig1_tank_walls.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, facecolor=fig.get_facecolor())
    return dest


if __name__ == "__main__":
    print(main())
