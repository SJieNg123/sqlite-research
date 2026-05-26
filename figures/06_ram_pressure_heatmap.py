"""Figure 6: RAM-pressure ratio heatmap (20M cgroup / no limit).

Story: the 63-cell RAM-pressure matrix — for each (workload × layout ×
strategy), ratio of first-query latency at 20 MB cap vs unlimited RAM.
Ratios in [0.90, 1.19] mean RAM pressure barely changes first-query
performance — surprising, because conventional wisdom says cgroup
pressure destroys prefetch. The dominant axis is workload, not RAM.
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

CSV = ROOT / "prefetch_access/runs/matrix_ram_full_results.csv"
LAYOUTS = ["orig", "vacuum", "ta"]
LAYOUT_LBL = {"orig": "1a", "vacuum": "1b", "ta": "1c"}
STRATS = ["base", "2d", "2e_K10", "2e_K50", "2e_K100", "2e_K500", "2f_SLRU"]
WORKLOADS = ["A", "B", "C"]

# (workload, db, strategy) -> {"20M": med, "none": med}
g = defaultdict(lambda: defaultdict(list))
for r in csv.DictReader(open(CSV)):
    g[(r["workload"], r["db"], r["strategy"])][r["mem_limit"]].append(float(r["first_query_us"]))
med = {k: {m: statistics.median(v) for m, v in lim.items()} for k, lim in g.items()}

# Build a 7 (strategy rows) × 9 (workload×layout cols) ratio matrix
M = np.zeros((len(STRATS), len(WORKLOADS) * len(LAYOUTS)))
col_labels = []
for ci, w in enumerate(WORKLOADS):
    for cj, l in enumerate(LAYOUTS):
        col_labels.append(f"{w}\n{LAYOUT_LBL[l]}")
        for ri, s in enumerate(STRATS):
            cell = med.get((w, l, s), {})
            if "20M" in cell and "none" in cell and cell["none"] > 0:
                M[ri, ci * len(LAYOUTS) + cj] = cell["20M"] / cell["none"]
            else:
                M[ri, ci * len(LAYOUTS) + cj] = np.nan

fig, ax = plt.subplots(figsize=(11, 4.4))
# Diverging colormap centred at 1.0; ratio<1 = pressure helped (rare), >1 = hurt
vmin, vmax = 0.85, 1.25
im = ax.imshow(M, cmap="RdBu_r", vmin=vmin, vmax=vmax, aspect="auto")
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        v = M[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if (v > 1.15 or v < 0.92) else "black")
ax.set_xticks(np.arange(M.shape[1]), col_labels, fontsize=9)
ax.set_yticks(np.arange(M.shape[0]), STRATS)
ax.set_xlabel("workload × layout")
ax.set_ylabel("strategy")

# Group separators
for k in range(1, len(WORKLOADS)):
    ax.axvline(k * len(LAYOUTS) - 0.5, color="black", lw=1.0)

cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cbar.set_label("first-query latency ratio (20 MB cap / unlimited)")
ax.set_title("RAM-pressure ratio · 63 cells × 6 reps (756 measurements)\n"
             "values near 1.0 → RAM pressure barely affects first-query latency",
             fontsize=11)
fig.tight_layout()
save(fig, "06_ram_pressure_heatmap")
