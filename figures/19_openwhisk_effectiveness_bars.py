"""Fig 19 -- OpenWhisk vs workstation effectiveness as grouped BARS (baseline = 0).

The 55 non-lp (strategy x workload) cells both platforms ran at orig. The y-axis is the *relative* first-query
reduction R = (baseline_fq - strategy_fq)/baseline_fq, i.e. how much faster than baseline
the first query is -- so the BASELINE sits at 0 by construction. Blue bar = workstation,
orange bar = OpenWhisk (standalone). Bars above 0 = faster than baseline (effective); bars
that dip below 0 = slower than baseline (a direction flip). One panel per workload; within a
panel strategies are sorted by workstation R.

Why relative and not absolute microseconds: absolute µs are systematically different across
the two environments (different machine state + delivery mechanism) and must NOT be compared
cell-for-cell. Reduction-vs-baseline cancels that offset, so blue and orange ARE comparable.
The 10 libprefetch cells are compared separately by delivery order (55 + 10 = 65 matched).

Data source: the revised freeze
deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation_revised_freeze.csv
(7 cells carry exactly position-balanced replication values; a `*` on the strategy label
marks a position_sensitive cell -- positive balanced aggregate, subsets disagree in sign).
Run:  /home/u03/.cache/coldstart-venv/bin/python figures/19c_openwhisk_effectiveness_bars.py
"""
import csv
from collections import defaultdict

import numpy as np

from plot_utils import ROOT, plt, save, strat_display

CSV = ROOT / "deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation_revised_freeze.csv"

WL_ORDER = ["YC", "YCu", "YCh01", "C", "C_hit"]
WS_COLOR = "#1f77b4"   # blue   = workstation
OW_COLOR = "#ff7f0e"   # orange = OpenWhisk
WIDTH = 0.40


def main():
    rows = list(csv.DictReader(open(CSV)))
    assert len(rows) == 55, f"expected 55 first-query cells, got {len(rows)}"

    by_wl = defaultdict(list)
    for r in rows:
        by_wl[r["workload"]].append(r)

    # width ratios so every panel's bars are the same physical width
    ncells = [len(by_wl[w]) for w in WL_ORDER]
    fig, axes = plt.subplots(1, len(WL_ORDER), sharey=True, figsize=(17, 5.2),
                             gridspec_kw={"width_ratios": ncells})

    for ax, wl in zip(axes, WL_ORDER):
        cells = sorted(by_wl[wl], key=lambda r: -float(r["R_ws"]))
        x = np.arange(len(cells))
        rws = [float(r["R_ws"]) for r in cells]
        row = [float(r["R_ow"]) for r in cells]

        ax.bar(x - WIDTH / 2, rws, WIDTH, color=WS_COLOR, label="workstation", zorder=3)
        ax.bar(x + WIDTH / 2, row, WIDTH, color=OW_COLOR, label="OpenWhisk", zorder=3)

        # baseline reference (0) + faint effective threshold
        ax.axhline(0.0, color="#333333", lw=1.1, zorder=4)
        ax.axhline(0.10, color="#cccccc", lw=0.8, ls=":", zorder=2)

        ax.set_title(wl, fontsize=11)
        ax.set_xticks(x)
        labels = [strat_display(r["strategy"]) + ("*" if str(r.get("position_sensitive", "")).strip().lower() == "true" else "")
                  for r in cells]
        ax.set_xticklabels(labels, rotation=90, fontsize=7.5)
        ax.set_xlim(-0.7, len(cells) - 0.3)
        ax.grid(axis="x", visible=False)
        ax.margins(x=0)

    axes[0].set_ylabel("First-query reduction vs baseline\n"
                       "(baseline = 0; higher = faster; <0 = slower than baseline)")
    axes[0].set_ylim(-0.85, 1.0)
    axes[0].legend(loc="upper right", fontsize=9)

    fig.suptitle("Workstation (blue) vs OpenWhisk (orange): first-query speed-up over "
                 "baseline — relative reduction, not absolute µs", fontsize=12, y=1.00)
    fig.tight_layout()

    save(fig, "19_openwhisk_effectiveness_bars")


if __name__ == "__main__":
    main()
