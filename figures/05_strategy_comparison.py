"""Figure 5: Strategy comparison across workloads × layouts (no RAM limit).

Story: no single best strategy — best choice depends on workload skew
and layout. Type-aware (1c) + layers_5/2e_K10 dominates on C; 2f_SLRU
wins on A; 2e_K500 wins on A under RAM pressure (covered in fig 6).
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

CSV = ROOT / "prefetch_access/runs/matrix_ram_full_results.csv"
LAYOUTS = [("orig","1a"), ("vacuum","1b"), ("ta","1c")]
STRATS  = ["base", "2d", "2e_K10", "2e_K50", "2e_K100", "2e_K500", "2f_SLRU"]
WORKLOADS = ["A", "B", "C"]
COLORS = {
    "base":     "#9ca3af",
    "2d":       "#10b981",
    "2e_K10":   "#34d399",
    "2e_K50":   "#059669",
    "2e_K100":  "#047857",
    "2e_K500":  "#065f46",
    "2f_SLRU":  "#f59e0b",
}

rows = [r for r in csv.DictReader(open(CSV)) if r["mem_limit"] == "none"]
med = defaultdict(list)
for r in rows:
    med[(r["workload"], r["db"], r["strategy"])].append(float(r["first_query_us"]))
medianed = {k: statistics.median(v) for k, v in med.items()}

fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), sharey=True)
n_strats = len(STRATS)
n_layouts = len(LAYOUTS)
gap = 0.15
group_w = 1 - gap
bar_w = group_w / n_strats

for ax, w in zip(axes, WORKLOADS):
    x = np.arange(n_layouts)
    for i, s in enumerate(STRATS):
        vals = [medianed.get((w, l, s), 0) for l, _ in LAYOUTS]
        offset = (i - (n_strats - 1) / 2) * bar_w
        ax.bar(x + offset, vals, bar_w, color=COLORS[s], label=s if w == "A" else None)
    ax.set_title(f"Workload {w}")
    ax.set_xticks(x, [n for _, n in LAYOUTS])
    ax.set_xlabel("layout")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)

axes[0].set_ylabel("first-query latency (µs, median of 6 reps)")
axes[0].set_ylim(0, max(medianed.values()) * 1.05)
fig.legend(loc="upper center", ncol=n_strats, bbox_to_anchor=(0.5, 1.03),
           fontsize=9, frameon=False)
fig.suptitle("All strategies × layouts × workloads · no RAM limit · 6 reps median",
             fontsize=12, y=1.08)
fig.tight_layout()
save(fig, "05_strategy_comparison")
