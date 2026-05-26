"""Figure 8: Multi-process prefetch cadence — first-query latency vs cadence.

Story: with a writer thread continuously churning + a probe reading
3 s after each round, the prefetcher cadence is the gating factor.
At cadence=1 s the interior pages are always fresh in cache → 16 µs;
at cadence=5 s only ~50% hit rate → 164 µs; at cadence ≥ 30 s the
prefetcher is no help at all (~315–357 µs, same as never).
Rule of thumb: cadence ≤ gap_s.
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

CSV = ROOT / "multiprocess/runs_prefetch_cadence/cadence_results.csv"

g = defaultdict(list)
for r in csv.DictReader(open(CSV)):
    g[r["cadence"]].append(float(r["first_q_us"]))

def kf(k):
    try: return float(k)
    except: return 1e9

cadences = sorted(g.keys(), key=kf)
xs = list(range(len(cadences)))
meds = [statistics.median(g[c]) for c in cadences]
lo   = [min(g[c]) for c in cadences]
hi   = [max(g[c]) for c in cadences]
labels = [f"{c} s" if c != "never" else "never\n(no prefetcher)" for c in cadences]

fig, ax = plt.subplots(figsize=(8, 4.5))
err_lo = [m - l for m, l in zip(meds, lo)]
err_hi = [h - m for h, m in zip(hi, meds)]
bars = ax.bar(xs, meds, color=["#10b981", "#34d399", "#fbbf24", "#9ca3af"],
              yerr=[err_lo, err_hi], capsize=4, edgecolor="white")
for b, m in zip(bars, meds):
    ax.text(b.get_x() + b.get_width()/2, m + 8, f"{m:.0f} µs",
            ha="center", va="bottom", fontsize=10, fontweight="bold")

# Annotate the rule-of-thumb gap
ax.axhline(meds[-1], color="#9ca3af", lw=0.6, ls=":", alpha=0.6)
ax.text(len(xs) - 0.5, meds[-1] - 30, f"baseline (no prefetcher) = {meds[-1]:.0f} µs",
        color="#6b7280", fontsize=8, ha="right")

ax.set_xticks(xs, labels)
ax.set_xlabel("prefetcher cadence  (1 fire / cadence sec)")
ax.set_ylabel("first-query latency (µs, median; bars = min/max of 4 rounds)")
ax.set_title("Multi-process prefetch cadence · writer + prefetcher + probe\n"
             "probe reads 3 s after each round  →  rule of thumb: cadence ≤ gap_s",
             fontsize=11)
ax.set_ylim(0, max(hi) * 1.18)
fig.tight_layout()
save(fig, "08_cadence_comparison")
