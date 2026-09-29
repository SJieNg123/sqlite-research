"""Figure 16: sub-working-set RAM-pressure sweep (review item R3 W3).

Steps the cgroup memory cap BELOW the ~17.3 MB resident working set (A/B) and shows, per
strategy, how much of the prefetched hotset stays resident to first-query (delivery_pct =
mincore residual) and what that does to first-q. Story (all targeted strategies swept, so
"small hotset -> robust" is measured, not deduced):
  - layers_5/2d/2e_K10/layers_92/2e_K500 (20 KB .. 2 MB hotsets) stay 100% delivered and flat
    -> RAM-robust by construction (hotset far below any viable cap, never evicted).
  - 2f_slru (17.7 MB dump = whole WS) cannot fit < ~16M: delivery collapses, first-q climbs
    from its ~94 us floor back toward baseline -> the cache-dump strategy breaks under pressure.

Data: results/ram_pressure/cap_<tag>/summary.csv (async arm + baseline), seed 1, layout orig.

Styled with pub_style.py, the scientific-figure-making (figures4papers) house style.
"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_utils import save, STRATEGY_COLORS, workload_display_name, strat_display
from pub_style import PALETTE, apply
apply()
# Skel family in blues and greens, Skel-5 neutral (not recommended), Dump red.
F4P_COLORS = {"layers_5": PALETTE["neutral_dark"], "2d": PALETTE["blue_main"],
              "2e_K10": PALETTE["blue_secondary"], "layers_92": PALETTE["green_3"],
              "2e_K500": PALETTE["teal"], "2f_slru": PALETTE["red_strong"]}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP = os.path.join(ROOT, "results/ram_pressure")
WS_MB = 17.3                                  # A/B resident working set
# cap tag -> (MB for ×WS label, x position). unlimited drawn at the left as the control.
CAPS = [("unlimited", None), ("16M", 16), ("12M", 12), ("8M", 8), ("6M", 6)]
STRATS = ["layers_5", "2d", "2e_K10", "layers_92", "2e_K500", "2f_slru"]
# CSV keys stay legacy (A/B); titles resolve to canonical display names.
WORKLOADS = ["A", "B"]
WL_TITLE = {"A": workload_display_name("A"), "B": workload_display_name("B")}


def load(tag):
    out = {}
    p = os.path.join(SWEEP, f"cap_{tag}", "summary.csv")
    with open(p) as f:
        for r in csv.DictReader(f):
            out[(r["workload"], r["strategy"], r["arm"])] = r
    return out


DATA = {tag: load(tag) for tag, _ in CAPS}
xpos = list(range(len(CAPS)))
xlabels = ["∞\n(unlim)"] + [f"{mb}M\n{mb/WS_MB:.2f}×WS" for _, mb in CAPS[1:]]

fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True)
for col, wl in enumerate(WORKLOADS):
    ax_d, ax_f = axes[0][col], axes[1][col]
    base_fq = [float(DATA[t].get((wl, "baseline", "baseline"), {}).get("fq_median", "nan"))
               for t, _ in CAPS]
    for s in STRATS:
        col_s = F4P_COLORS[s]
        dpct = [float(DATA[t].get((wl, s, "async"), {}).get("delivery_pct_median", "nan"))
                if (wl, s, "async") in DATA[t] else float("nan") for t, _ in CAPS]
        fq = [float(DATA[t].get((wl, s, "async"), {}).get("fq_median", "nan"))
              if (wl, s, "async") in DATA[t] else float("nan") for t, _ in CAPS]
        ax_d.plot(xpos, dpct, "o-", color=col_s, lw=2.5, ms=7, label=strat_display(s))
        ax_f.plot(xpos, fq, "o-", color=col_s, lw=2.5, ms=7, label=strat_display(s))
    ax_f.plot(xpos, base_fq, "--", color=PALETTE["ink"], lw=2, label="baseline (no prefetch)")
    ax_d.axvline(0.5, color="#9ca3af", ls=":", lw=1)   # mark "cap < WS" region start
    ax_d.set_title(WL_TITLE[wl], fontsize=14.5)
    ax_d.set_ylim(0, 108)
    ax_f.set_yscale("log")
    ax_f.axvline(0.5, color="#9ca3af", ls=":", lw=1)
    if col == 0:
        ax_d.set_ylabel("hotset delivery_pct\n(mincore residual @ first-q)", fontsize=13)
        ax_f.set_ylabel("first-query latency (µs, log)", fontsize=13)
    ax_f.set_xticks(xpos); ax_f.set_xticklabels(xlabels, fontsize=11.5)

handles, labels = axes[1][0].get_legend_handles_labels()
fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=13,
           bbox_to_anchor=(0.5, -0.02), frameon=False)
fig.tight_layout(rect=[0, 0.11, 1, 1])
save(fig, "16_ram_pressure_sweep")
