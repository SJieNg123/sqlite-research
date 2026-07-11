#!/usr/bin/env python3
"""Figure 17 — S1 three-lever ablation.

Where does the targeted-prefetch win come from? Each arm isolates one selection lever;
bars show the cross-seed mean first-query / e2e_warm reduction vs baseline (async arm)
with bootstrap 95% CI whiskers. POST-FIX (tie-break): on C_mixed the page-type lever
(2d) is the robust one; leaf_freq (access-frequency, leaf-only) is a TIE -- its pre-fix
-40% was first-op leakage. leaf_rand is a net-slower control. orig-only.

Data: results/ablation/uncertainty.csv (A/B) + results/ablation_comp_v2/uncertainty.csv
(C/orig, post-fix).
Run:  python3 figures/17_lever_ablation.py
"""
import csv
import sys
from pathlib import Path
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

ARMS   = ["2d", "leaf_rand_K10", "leaf_freq_K10", "2e_K10"]
LABELS = {"2d": "2d (interior · page-type)", "leaf_rand_K10": "leaf_rand (control)",
          "leaf_freq_K10": "leaf_freq (access-freq)", "2e_K10": "2e_K10 (combined)"}
# colour by ARM so the lever meaning is consistent across workload groups:
# the control is grey, the access-frequency lever is the green that pops.
ARM_COLOR = {"2d": "#3b82f6", "leaf_rand_K10": "#9ca3af",
             "leaf_freq_K10": "#059669", "2e_K10": "#111827"}
WORKLOADS = ["A", "B", "C"]
METRICS = [("first_query_us", "first-query"), ("e2e_warm_us", "e2e_warm")]


def load(path):
    idx = {}
    if Path(path).exists():
        for r in csv.DictReader(open(path)):
            idx[(r["workload"], r["db"], r["strategy"], r["arm"], r["metric"])] = r
    return idx


def val(idx, w, ly, s, metric, arm="async"):
    r = idx.get((w, ly, s, arm, metric))
    if not r:
        return None, None, None
    mean = float(r["mean_pct"])
    lo = None if r["ci_lo"] in ("", "None", None) else float(r["ci_lo"])
    hi = None if r["ci_hi"] in ("", "None", None) else float(r["ci_hi"])
    return mean, lo, hi


def main():
    idx = load(ROOT / "results/ablation/uncertainty.csv")
    idx.update(load(ROOT / "results/ablation_k500/uncertainty_k500.csv"))
    # tie-break fix (commit de4490f): C/orig lever arms were re-measured with the
    # deterministic (-count,pageno) hotset in results/ablation_comp_v2. Overriding
    # the pre-fix C/orig rows (leaf_freq's old -40% was first-op leakage -> now a tie).
    idx.update(load(ROOT / "results/ablation_comp_v2/uncertainty.csv"))
    if not idx:
        sys.exit("no results/ablation/uncertainty.csv — run the sweep + stats first")

    # orig only: the post-fix rerun (ablation_comp_v2) is orig-only, so we drop the
    # pre-fix C/ta row rather than mix a leaky cell into the figure.
    layouts = ["orig"]
    fig, axes = plt.subplots(len(layouts), len(METRICS),
                             figsize=(11, 4.2), sharex=True, squeeze=False)
    x = list(range(len(WORKLOADS)))
    w_bar = 0.2

    for ri, ly in enumerate(layouts):
        for ci, (metric, mlabel) in enumerate(METRICS):
            ax = axes[ri][ci]
            for ai, s in enumerate(ARMS):
                means, los, his = [], [], []
                for w in WORKLOADS:
                    m, lo, hi = val(idx, w, ly, s, metric)
                    means.append(0 if m is None else m)
                    # asymmetric whisker = distance from mean to CI bound
                    los.append(0 if (m is None or lo is None) else max(0, m - lo))
                    his.append(0 if (m is None or hi is None) else max(0, hi - m))
                ax.bar([xi + (ai - 1.5) * w_bar for xi in x], means, w_bar,
                       yerr=[los, his], capsize=2, color=ARM_COLOR[s],
                       edgecolor="white", linewidth=0.4,
                       error_kw=dict(lw=0.8, ecolor="#666"),
                       label=LABELS[s] if (ri == 0 and ci == 0) else None)
            ax.axhline(0, color="#222", lw=0.8)
            ax.set_xticks(x)
            ax.set_xticklabels(WORKLOADS)
            ax.set_title(f"{mlabel} Δ% — layout {ly}")
            if ci == 0:
                ax.set_ylabel(f"{ly}\nΔ% vs baseline (− = faster)")

    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "17_lever_ablation")


if __name__ == "__main__":
    main()
