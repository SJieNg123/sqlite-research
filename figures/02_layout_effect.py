"""Figure 2: Layout × strategy effect on first-query latency (Workload A).

Story: VACUUM alone barely helps (1b baseline 333 vs 1a 318); the win
comes from combining type-aware layout (1c) with layers_5 prefetch —
404 us → 127 us = -69%. layers_5 also wins on the orig layout (-30%).
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

CSV = ROOT / "layout_rewriter/results/matrix_results.csv"
LAYOUTS = [("orig", "1a (orig)"), ("vacuum", "1b (VACUUM)"), ("ta", "1c (type-aware)")]
STRATS  = ["baseline", "range", "perpage", "layers5"]
LABELS  = {"baseline": "baseline\n(no prefetch)", "range": "range",
           "perpage": "perpage", "layers5": "layers_5"}
COLORS  = {"baseline": "#9ca3af", "range": "#94a3b8",
           "perpage": "#cbd5e1", "layers5": "#3b82f6"}

rows = list(csv.DictReader(open(CSV)))
med = defaultdict(dict)
for r in rows:
    med.setdefault((r["db"], r["strategy"]), []).append(float(r["first_query_us"]))
medianed = {k: statistics.median(v) for k, v in med.items()}

fig, ax = plt.subplots(figsize=(8.5, 4.2))
x = np.arange(len(LAYOUTS))
w = 0.20
for i, s in enumerate(STRATS):
    vals = [medianed[(layout, s)] for layout, _ in LAYOUTS]
    bars = ax.bar(x + (i - 1.5) * w, vals, w, color=COLORS[s], label=LABELS[s])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + 5, f"{v:.0f}",
                ha="center", va="bottom", fontsize=8)

# delta callouts
for j, (layout, lname) in enumerate(LAYOUTS):
    base = medianed[(layout, "baseline")]
    best = medianed[(layout, "layers5")]
    pct = (best - base) / base * 100
    ax.annotate(f"Δ {pct:+.0f}%", xy=(j, best), xytext=(j + 0.05, base + 50),
                fontsize=10, color="#1d4ed8", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#1d4ed8", lw=0.8))

ax.set_xticks(x, [n for _, n in LAYOUTS])
ax.set_ylabel("first-query latency (µs, median of 3 reps)")
ax.set_title("Layout × prefetch strategy · Workload A · cold start")
ax.legend(loc="upper center", ncol=4, bbox_to_anchor=(0.5, -0.12))
ax.set_ylim(0, max(medianed.values()) * 1.20)
fig.tight_layout()
save(fig, "02_layout_effect")
