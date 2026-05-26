"""Figure 3: Cumulative latency over the first 50 queries (warmup region).

Story: the cold→warm transition is where prefetch saves you time. After
~50 queries the page cache is fully warm and every strategy converges
to ~1.5 µs/query. The figure shows cumulative-time-to-Nth-query so
the slope = current per-query latency. Baseline has a steep slope for
the first ~10 queries (cold faults); 2e_K500 and 2f_SLRU keep the
slope shallow from query 1 because the hot leaves are already mapped.
"""
import csv
import numpy as np
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

DIR = ROOT / "prefetch_access/runs/ops_csv_ram"
ARMS = [
    ("base",       "baseline (no prefetch)",   "#9ca3af", "-"),
    ("2d",         "2d (interior-only)",       "#10b981", "-"),
    ("2e_K500",    "2e_K500 (interior + 500 hot leaves)", "#047857", "-"),
    ("2f_SLRU",    "2f_SLRU (mincore dump)",   "#f59e0b", "-"),
]
REPS = 6
N_WARMUP = 50

def load_first_n(strategy, n):
    """Return array (REPS, n) of per-query elapsed_us for the first n queries."""
    runs = []
    for r in range(1, REPS + 1):
        p = DIR / f"ops_A_orig_{strategy}_none_r{r}.csv"
        if not p.exists():
            continue
        with p.open() as f:
            rd = csv.reader(f); next(rd)
            lat = []
            for row in rd:
                lat.append(int(row[5]) / 1000.0)
                if len(lat) == n: break
            runs.append(lat)
    return np.asarray(runs)

fig, ax = plt.subplots(figsize=(9, 4.6))

end_vals = []
for strat, label, color, ls in ARMS:
    lat = load_first_n(strat, N_WARMUP)
    if lat.size == 0: continue
    cum_each = np.cumsum(lat, axis=1)
    med = np.median(cum_each, axis=0)
    lo = np.percentile(cum_each, 25, axis=0)
    hi = np.percentile(cum_each, 75, axis=0)
    x = np.arange(1, len(med) + 1)
    ax.plot(x, med, label=label, color=color, lw=1.8, ls=ls)
    ax.fill_between(x, lo, hi, color=color, alpha=0.12)
    end_vals.append((med[-1], color))

# Stagger labels vertically so close values don't overlap
end_vals.sort(key=lambda t: -t[0])
y_min_sep = 320
last_y = None
for v, color in end_vals:
    y = v
    if last_y is not None and (last_y - y) < y_min_sep:
        y = last_y - y_min_sep
    ax.text(N_WARMUP + 0.6, y, f"{v:.0f} µs",
            color=color, fontsize=9, va="center", fontweight="bold")
    last_y = y

ax.set_xlabel("query #")
ax.set_ylabel("cumulative latency to N-th query (µs)")
ax.set_title("Cold→warm transition · Workload A · layout 1a · no RAM limit\n"
             "(shaded = IQR across 6 reps; right-margin labels = cumulative time at query 50)")
ax.set_xlim(0, N_WARMUP + 7)
ax.legend(loc="upper left", fontsize=9)
fig.tight_layout()
save(fig, "03_latency_cdf")
