#!/usr/bin/env python3
"""Figure 17 — corrected selection-lever ablation on C_mixed (orig layout only).

Where does the targeted-prefetch win on C_mixed come from? Each arm isolates one
selection lever; bars show the cross-seed mean reduction vs the same-batch
baseline (async arm) with bootstrap 95% CI whiskers. Two panels: first-query Δ%
and warm-process e2e Δ%. POST-FIX (tie-break, commit de4490f): the page-type
lever (2d) is the robust one; leaf_freq (access-frequency, leaf-only) is a TIE on
e2e_warm -- its pre-fix -40% was first-op leakage; leaf_rand is a net-slower
control; 2e_K10 (combined) is the not-found-inflated headline.

Single canonical source: results/ablation_comp_v2/uncertainty.csv (C_mixed x orig,
10-seed bootstrap 95% CI). No other batch is read.
Run:  python3 figures/17_lever_ablation.py
"""
import csv
import sys
from pathlib import Path
from plot_utils import ROOT, save, workload_display_name
import matplotlib.pyplot as plt

SOURCE = ROOT / "results/ablation_comp_v2/uncertainty.csv"

ARMS   = ["2d", "leaf_rand_K10", "leaf_freq_K10", "2e_K10"]
LABELS = {"2d": "2d\n(interior · page-type)", "leaf_rand_K10": "leaf_rand\n(control)",
          "leaf_freq_K10": "leaf_freq\n(access-freq)", "2e_K10": "2e_K10\n(combined)"}
ARM_COLOR = {"2d": "#3b82f6", "leaf_rand_K10": "#9ca3af",
             "leaf_freq_K10": "#059669", "2e_K10": "#111827"}
METRICS = [("first_query_us", "first-query"), ("e2e_warm_us", "warm-process e2e")]
WORKLOAD, LAYOUT, PARM = "C", "orig", "async"


def load(path):
    """Index {(workload, db, strategy, arm, metric): row}; fail on duplicate key."""
    idx = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            key = (r["workload"], r["db"], r["strategy"], r["arm"], r["metric"])
            if key in idx:
                sys.exit(f"FATAL: duplicate row {key} in {path}")
            idx[key] = r
    return idx


def cell(idx, strategy, metric):
    key = (WORKLOAD, LAYOUT, strategy, PARM, metric)
    if key not in idx:
        sys.exit(f"FATAL: missing row {key} in {SOURCE}")
    r = idx[key]
    return float(r["mean_pct"]), float(r["ci_lo"]), float(r["ci_hi"]), r["verdict"]


IDX = load(SOURCE)

fig, axes = plt.subplots(1, len(METRICS), figsize=(10, 4.2), sharex=True, squeeze=False)
x = list(range(len(ARMS)))

print("Figure 17 — C_mixed corrected ablation (results/ablation_comp_v2):")
for ci, (metric, mlabel) in enumerate(METRICS):
    ax = axes[0][ci]
    means, los, his = [], [], []
    for s in ARMS:
        m, lo, hi, verdict = cell(IDX, s, metric)
        means.append(m)
        los.append(max(0.0, m - lo))
        his.append(max(0.0, hi - m))
        print(f"  {mlabel:16s} {s:14s} {m:+7.2f}%  [{lo:+6.2f}, {hi:+6.2f}]  ({verdict})")
    ax.bar(x, means, 0.62, yerr=[los, his], capsize=3,
           color=[ARM_COLOR[s] for s in ARMS], edgecolor="white", linewidth=0.5,
           error_kw=dict(lw=0.9, ecolor="#555"))
    ax.axhline(0, color="#222", lw=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([LABELS[s] for s in ARMS], fontsize=8.5)
    ax.set_title(rf"{workload_display_name(WORKLOAD)} — {mlabel} $\Delta$% (orig)", fontsize=11)
    ax.set_ylabel("Δ% vs same-batch baseline (− = faster)", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

fig.tight_layout()
save(fig, "17_lever_ablation")
