"""Figure 10: Ratio-based 3a/3b mapped onto K-sweep — interior:leaf ratio matters.

Story: original spec defined Strategy 3a (interior:leaf = 7:3) and 3b (5:5).
Implementation parameterised by K (leaf count) instead, then we added the
canonical points K=40 (7:3 if all 92 interior were prefetched) and K=92
(5:5). This figure plots the full K-sweep {2d=0, 10, 40, 50, 92, 100, 500}
× 3 workloads × 3 layouts so the ratio story is visible alongside the
empirical K-sweep.
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, LAYOUT_COLORS, save
import matplotlib.pyplot as plt

# K=0 (2d) and K∈{10,50,100,500} live in matrix_ram_full (mem_limit=none)
# K∈{40,92} live in matrix_2e_ratio
CSV_FULL  = ROOT / "prefetch_access/runs/matrix_ram_full_results.csv"
CSV_RATIO = ROOT / "prefetch_access/runs/matrix_2e_ratio_results.csv"

# Strategy -> K leaves
STRAT_K = {"2d": 0, "2e_K10": 10, "2e_K40": 40, "2e_K50": 50,
           "2e_K92": 92, "2e_K100": 100, "2e_K500": 500}

# (workload, db, K) -> [first_query_us, ...]
g = defaultdict(list)

for r in csv.DictReader(open(CSV_FULL)):
    if r["mem_limit"] != "none": continue
    K = STRAT_K.get(r["strategy"])
    if K is None: continue
    g[(r["workload"], r["db"], K)].append(float(r["first_query_us"]))

for r in csv.DictReader(open(CSV_RATIO)):
    K = STRAT_K.get(r["strategy"])
    if K is None: continue
    g[(r["workload"], r["db"], K)].append(float(r["first_query_us"]))

Ks = sorted({k[2] for k in g})
WORKLOADS = ["A", "B", "C"]
LAYOUTS = [("orig","1a"), ("vacuum","1b"), ("ta","1c")]

fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=False)
for ax, w in zip(axes, WORKLOADS):
    for db, lbl in LAYOUTS:
        ys = [statistics.median(g[(w, db, k)]) if g.get((w, db, k)) else None for k in Ks]
        ax.plot(Ks, ys, "-o", color=LAYOUT_COLORS[db], lw=1.7, ms=5,
                label=f"layout {lbl}")
    # Highlight the two canonical "ratio" points (full-height span)
    ax.axvspan(38, 42, color="#fb923c", alpha=0.12, zorder=0)
    ax.axvspan(89, 95, color="#a855f7", alpha=0.12, zorder=0)
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xticks([0, 10, 40, 50, 92, 100, 500])
    ax.set_xticklabels(["0\n(2d)", "10", "40\n(3a)", "50", "92\n(3b)", "100", "500"], fontsize=8)
    ax.set_xlabel("K (top hot-leaf pages prefetched)")
    ax.set_title(f"Workload {w}")
    ax.grid(True, linestyle=":", alpha=0.4)

# Per-subplot y-axes (A/B around 0-450, C around 0-450 too for fair compare)
for ax in axes:
    ax.set_ylim(0, 470)

# Legend at top-center of figure
axes[2].legend(loc="upper right", fontsize=8)
axes[0].set_ylabel("first-query latency (µs, median of 6 reps)")

# Annotate ratio markers above each subplot
for ax in axes:
    ax.text(40, 460, "3a (7:3)", color="#c2410c", fontsize=8, ha="center", va="top",
            bbox=dict(facecolor="white", edgecolor="none", pad=1, alpha=0.85))
    ax.text(92, 460, "3b (5:5)", color="#7e22ce", fontsize=8, ha="center", va="top",
            bbox=dict(facecolor="white", edgecolor="none", pad=1, alpha=0.85))

fig.suptitle("2e ratio sweep · K=40 ≈ Strategy 3a (7:3), K=92 ≈ Strategy 3b (5:5)\n"
             "K=500 dominates A · 1c shows non-monotonic K=92/100 hump · C saturates at any K",
             fontsize=11, y=1.02)
fig.tight_layout()
save(fig, "10_ratio_sweep")
