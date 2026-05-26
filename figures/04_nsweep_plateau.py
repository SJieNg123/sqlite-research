"""Figure 4: N-sweep plateau shapes — clean DB vs churned DB, all 3 workloads.

Story: layers_N first-query latency drops as N grows (more interior pages
prefetched) and plateaus where remaining cost is leaf faults. The plateau
HEIGHT and SHAPE are workload-dependent — A (Zipfian) drops to ~25 µs at
N=5 because hot leaves are already warm; B/C (uniform / high-key) plateau
much higher (250–300 µs) because every read is a cold leaf fault. Churn
does not change the plateau shape.
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, WORKLOAD_COLORS, save
import matplotlib.pyplot as plt

# Clean-DB results: median across 3 reps per workload × N
CLEAN_CSVS = {
    "A": ROOT / "layout_rewriter/runs/matrix_Nsweep_orig_a_results.csv",
    "B": ROOT / "layout_rewriter/runs/matrix_Nsweep_bc_results.csv",
    "C": ROOT / "layout_rewriter/runs/matrix_Nsweep_bc_results.csv",
}

def load_clean(csv_path, workload):
    g = defaultdict(list)
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            if r["workload"] != workload: continue
            g[int(r["N"])].append(float(r["first_query_us"]))
    return {n: statistics.median(v) for n, v in g.items()}

# Churned-DB matrices: cols are N0,N1,N5,N10,N20,N46,N92 — avg over 10 checkpoints (skip baseline row)
CHURN_CSVS = {
    "A": ROOT / "prefetch_churn/runs_nsweep_a/matrix_first_q_us.csv",
    "B": ROOT / "prefetch_churn/runs_nsweep_b/matrix_first_q_us.csv",
    "C": ROOT / "prefetch_churn/runs_nsweep/matrix_first_q_us.csv",
}

def load_churn(csv_path):
    rows = list(csv.DictReader(open(csv_path)))
    # Skip "baseline" row (some matrices use 'checkpoint', others 'label')
    label_col = "checkpoint" if "checkpoint" in rows[0] else "label"
    rows = [r for r in rows if not r[label_col].startswith("baseline")]
    out = {}
    for col in rows[0].keys():
        # column is N0/N1/... or N=0/N=1/...
        if not col.startswith("N"): continue
        try:
            n = int(col.lstrip("N=").lstrip("N"))
        except ValueError:
            continue
        out[n] = statistics.mean(float(r[col]) for r in rows)
    return out

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)

# Pre-load to find common N axis
clean_by_w = {w: load_clean(p, w) for w, p in CLEAN_CSVS.items()}
churn_by_w = {w: load_churn(p) for w, p in CHURN_CSVS.items()}

for ax, data, title in [
    (ax1, clean_by_w, "Clean DB (median of 3 reps)"),
    (ax2, churn_by_w, "Churned DB (avg of 10 checkpoints × 50k ops)"),
]:
    for w in ["A", "B", "C"]:
        d = data[w]
        ns = sorted(d.keys())
        ys = [d[n] for n in ns]
        ax.plot(ns, ys, "-o", color=WORKLOAD_COLORS[w], lw=1.7, ms=5,
                label=f"Workload {w}")
    ax.set_xlabel("N (number of interior pages prefetched)")
    ax.set_title(title)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xticks([0, 1, 5, 10, 20, 46, 92])
    ax.set_xticklabels(["0", "1", "5", "10", "20", "46", "92"])
    ax.legend(loc="upper right")

ax1.set_ylabel("first-query latency (µs)")
ax1.set_ylim(0, max(max(d.values()) for d in clean_by_w.values()) * 1.1)
fig.suptitle("layers_N plateau · workload-dependent shape, churn-robust",
             fontsize=12, y=1.0)
fig.tight_layout()
save(fig, "04_nsweep_plateau")
