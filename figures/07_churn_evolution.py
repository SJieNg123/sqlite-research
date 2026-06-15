"""Figure 7: First-query latency evolution across 10 churn checkpoints.

Story: static t=0 hotpages survive 10 × 5000 = 50k churn ops on three
orthogonal churn settings — C × insert-churn, A × delete-churn, and
B × mixed churn. Baseline (no prefetch) drifts upward; prefetch arms
hold flat — proving the hot-page set is workload-stable under realistic
churn. On A/C (which have hot leaves) access-pattern (2d/2e_K) beats
file-offset layers_N; on B (uniform, no hot leaf) the two are tied
because top-K leaves degenerate to a near-random pick — but neither
decays.
"""
import csv
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

CSV_C = ROOT / "prefetch_churn/runs_access_churn/matrix_first_q_us.csv"
CSV_A = ROOT / "prefetch_churn/runs_access_churn_a/matrix_first_q_us.csv"
CSV_B = ROOT / "prefetch_churn/runs_access_churn_b/matrix_first_q_us.csv"

def load(path):
    rows = list(csv.DictReader(open(path)))
    label_col = list(rows[0].keys())[0]
    cols = [c for c in rows[0].keys() if c != label_col]
    labels = [r[label_col] for r in rows]
    series = {c: [float(r[c]) for r in rows] for c in cols}
    return labels, series

def cpx(labels):
    # baseline + 10 checkpoints; x = 0, 5, 10, ..., 50 (k ops)
    return list(range(0, 5 * len(labels), 5))

NAME_MAP = {
    "n0_base":     ("baseline (no prefetch)", "#9ca3af", "-"),
    "n5_layers":   ("layers_5",                "#3b82f6", "-"),
    "n92_layers":  ("layers_92",               "#1e3a8a", "-"),
    "acc_2d":      ("2d (interior-only)",      "#10b981", "-"),
    "2d_static":   ("2d (interior-only)",      "#10b981", "-"),
    "acc_2e_k10":  ("2e_K10 (+ 10 hot leaves)","#059669", "-"),
    "2e_k10_static":("2e_K10 (+ 10 hot leaves)","#059669","-"),
    "2e_k50_static":("2e_K50 (+ 50 hot leaves)","#047857","-"),
}

fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), sharey=True)

for ax, (path, title) in zip(axes, [
    (CSV_C, "Workload C · insert-heavy churn (id 600001+)"),
    (CSV_A, "Workload A · delete-heavy churn (id 1+, Zipfian reads)"),
    (CSV_B, "Workload B · mixed churn (uniform reads, no hot leaf)"),
]):
    labels, series = load(path)
    x = cpx(labels)
    for k, vals in series.items():
        if k not in NAME_MAP: continue
        nm, color, ls = NAME_MAP[k]
        ax.plot(x, vals, ls, marker="o", ms=4, color=color, lw=1.6, label=nm)
    ax.set_xlabel("cumulative churn ops (thousands)")
    ax.set_title(title, fontsize=10)
    ax.set_yscale("log")
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    ax.legend(loc="center right", fontsize=8)
    ax.set_ylim(10, 1000)

axes[0].set_ylabel("first-query latency (µs, log scale)")
fig.suptitle("Static t=0 hot-pages survive 50 k-op churn across 3 workloads · "
             "access-pattern matches file-offset on B (no hot leaf)",
             fontsize=11, y=1.0)
fig.tight_layout()
save(fig, "07_churn_evolution")
