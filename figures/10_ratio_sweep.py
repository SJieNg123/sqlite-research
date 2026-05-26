"""Figure 10: Strategy 3a/3b realised via K-sweep — explicit ratio mapping.

Original spec defined Strategy 3a (interior:leaf = 7:3) and 3b (5:5).
Implementation parameterises by K (top-K leaves), so we mapped:
   K=40 → 3a (since 92 interior × 30/70 ≈ 40)
   K=92 → 3b (since 92 interior × 50/50 = 92)

The *actual* interior:leaf ratio depends on layout because 2e only marks
INTERIOR pages that were resident after warmup (4 → 32 pages, not the
full 92). This figure shows both the K-sweep AND a side panel with the
actual realised ratios so the reader can re-interpret the points.
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, LAYOUT_COLORS, save
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

CSV_FULL  = ROOT / "prefetch_access/runs/matrix_ram_full_results.csv"
CSV_RATIO = ROOT / "prefetch_access/runs/matrix_2e_ratio_results.csv"

STRAT_K = {"2d": 0, "2e_K10": 10, "2e_K40": 40, "2e_K50": 50,
           "2e_K92": 92, "2e_K100": 100, "2e_K500": 500}

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
LAYOUTS = [("orig", "1a"), ("vacuum", "1b"), ("ta", "1c")]

# Resident interior counts (computed from gen_hotleaves.py stderr earlier):
# (workload, layout) -> interior_count
INTERIOR = {
    ("A","orig"):18, ("A","vacuum"):12, ("A","ta"):31,
    ("B","orig"):16, ("B","vacuum"):12, ("B","ta"):31,
    ("C","orig"): 4, ("C","vacuum"): 4, ("C","ta"):32,
}

fig = plt.figure(figsize=(15, 5.4))
gs = gridspec.GridSpec(1, 4, width_ratios=[3, 3, 3, 2.2], wspace=0.32)

# --- 3 K-sweep subplots ---
for i, w in enumerate(WORKLOADS):
    ax = fig.add_subplot(gs[0, i])
    for db, lbl in LAYOUTS:
        ys = [statistics.median(g[(w, db, k)]) if g.get((w, db, k)) else None for k in Ks]
        ax.plot(Ks, ys, "-o", color=LAYOUT_COLORS[db], lw=1.7, ms=5,
                label=f"layout {lbl}")
    ax.axvspan(38, 42, color="#fb923c", alpha=0.18, zorder=0)
    ax.axvspan(89, 95, color="#a855f7", alpha=0.18, zorder=0)
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xticks([0, 10, 40, 50, 92, 100, 500])
    ax.set_xticklabels(["0\n(2d)", "10", "40", "50", "92", "100", "500"], fontsize=8)
    ax.set_xlabel("K (top hot-leaf pages prefetched)")
    ax.set_ylim(0, 470)
    ax.set_title(f"Workload {w}")
    ax.grid(True, linestyle=":", alpha=0.4)
    # Explicit ratio labels above the bands
    ax.text(40, 455, "3a\n7:3", color="#c2410c", fontsize=8.5, ha="center", va="top",
            fontweight="bold",
            bbox=dict(facecolor="white", edgecolor="#fb923c", lw=0.5, pad=1.5))
    ax.text(92, 455, "3b\n5:5", color="#7e22ce", fontsize=8.5, ha="center", va="top",
            fontweight="bold",
            bbox=dict(facecolor="white", edgecolor="#a855f7", lw=0.5, pad=1.5))
    if i == 0:
        ax.set_ylabel("first-query latency (µs, median of 6 reps)")
        ax.legend(loc="lower left", fontsize=8)

# --- Right side: actual ratio table ---
ax_tab = fig.add_subplot(gs[0, 3])
ax_tab.axis("off")

# Build table content
rows = []
for w in WORKLOADS:
    for db, lbl in LAYOUTS:
        n_int = INTERIOR[(w, db)]
        r_3a = f"{n_int}:{40}"        # K=40
        r_3b = f"{n_int}:{92}"        # K=92
        pct_3a = 100*n_int/(n_int+40)
        pct_3b = 100*n_int/(n_int+92)
        rows.append((f"{w}·{lbl}", n_int, f"{r_3a}\n({pct_3a:.0f}:{100-pct_3a:.0f})",
                     f"{r_3b}\n({pct_3b:.0f}:{100-pct_3b:.0f})"))

# Render as text (manual layout for clarity)
ax_tab.set_title("Actual interior:leaf ratio\n(2e only marks RESIDENT interior, 4–32 not 92)",
                 fontsize=9.5)
header_y = 0.92
ax_tab.text(0.02, header_y, "cell",   fontweight="bold", fontsize=8)
ax_tab.text(0.27, header_y, "int#",   fontweight="bold", fontsize=8)
ax_tab.text(0.46, header_y, "K=40 (3a)", fontweight="bold", fontsize=8, color="#c2410c")
ax_tab.text(0.76, header_y, "K=92 (3b)", fontweight="bold", fontsize=8, color="#7e22ce")
row_y = header_y - 0.07
for label, n_int, r3a, r3b in rows:
    # Multi-line cell renders centered on its slot
    ax_tab.text(0.02, row_y,        label, fontsize=8, va="top")
    ax_tab.text(0.30, row_y,        f"{n_int}", fontsize=8, va="top")
    ax_tab.text(0.46, row_y,        r3a, fontsize=7.6, va="top", color="#c2410c")
    ax_tab.text(0.76, row_y,        r3b, fontsize=7.6, va="top", color="#7e22ce")
    row_y -= 0.10

ax_tab.text(0.02, row_y - 0.02,
            "Target spec: 3a=70:30, 3b=50:50\nClosest to spec: ta layouts\n(31:40≈44:56, 32:40≈44:56)",
            fontsize=7.5, va="top", style="italic", color="#374151")

fig.suptitle("Strategy 3a (7:3) and 3b (5:5) realised via K-sweep · K=40 / K=92 newly added\n"
             "Actual ratio is workload×layout dependent because 2e only prefetches RESIDENT interior",
             fontsize=11, y=1.04)
fig.tight_layout()
save(fig, "10_ratio_sweep")
