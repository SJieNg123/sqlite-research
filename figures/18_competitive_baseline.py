#!/usr/bin/env python3
"""Figure 18 — RR1/S4 competitive baseline: targeted prefetch vs a *tuned* dump.

Is the e2e win "page-type mechanism beats dump mechanism", or merely "small,
frequency-ranked dump beats the full dump"? We sweep a frequency-ranked PARTIAL
dump (2f_topN, no page-type knowledge) across footprints and overlay 2e_K10.

x = dump footprint (pages, log); y = cross-seed mean Δ% vs baseline (95% CI):
the 2f_topN points trace the partial-dump trade-off curve; 2e_K10 (★) lands ON
that curve at the small-N sweet spot — so the win is the footprint+ranking, not
the page-type mechanism. As N grows, deliver cost climbs and e2e_warm blows up
(full dump 2f_slru off the top).

Data: results/competitive/uncertainty.csv. Run: python3 figures/18_competitive_baseline.py
"""
import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from plot_utils import ROOT, WORKLOAD_COLORS, save
import matplotlib.pyplot as plt

SERIES = ["2f_top14", "2f_top28", "2f_top100", "2f_top500", "2f_slru"]
WORKLOADS = ["A", "B", "C"]
METRICS = [("first_query_us", "first-query Δ% vs baseline"),
           ("e2e_warm_us", "e2e_warm Δ% vs baseline")]


def footprints():
    """Deterministic page count per (workload, strategy), seed 1 (files exist)."""
    import run_experiment as R
    R.SEED = 1
    cl = R.load_classify("orig")
    fp = {}
    for w in WORKLOADS:
        for s in SERIES + ["2e_K10"]:
            try:
                fp[(w, s)] = len(R.select_pages(R.resolve_strategy(s), w, "orig", cl))
            except SystemExit:
                fp[(w, s)] = None
    return fp


def load_unc(path):
    idx = {}
    for r in csv.DictReader(open(path)):
        idx[(r["workload"], r["strategy"], r["arm"], r["metric"])] = r
    return idx


def main():
    unc = ROOT / "results/competitive/uncertainty.csv"
    if not unc.exists():
        sys.exit("no results/competitive/uncertainty.csv — run the sweep + stats first")
    idx = load_unc(unc)
    # tie-break fix (commit de4490f): C/orig 2e_K10 + 2f_top14/28 were re-measured in
    # the same post-fix batch (results/ablation_comp_v2). Override the pre-fix C cells
    # (2e_K10's old -72% was first-op leakage -> now -55%, matching 2f_top14).
    comp2 = ROOT / "results/ablation_comp_v2/uncertainty.csv"
    if comp2.exists():
        for r in csv.DictReader(open(comp2)):
            if r["db"] == "orig":
                idx[(r["workload"], r["strategy"], r["arm"], r["metric"])] = r
    fp = footprints()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, (metric, ylabel) in zip(axes, METRICS):
        for w in WORKLOADS:
            xs, ys, los, his = [], [], [], []
            for s in SERIES:
                r = idx.get((w, s, "async", metric))
                n = fp.get((w, s))
                if not r or n is None:
                    continue
                m = float(r["mean_pct"])
                xs.append(n); ys.append(m)
                los.append(0 if r["ci_lo"] in ("", "None", None) else max(0, m - float(r["ci_lo"])))
                his.append(0 if r["ci_hi"] in ("", "None", None) else max(0, float(r["ci_hi"]) - m))
            c = WORKLOAD_COLORS[w]
            ax.errorbar(xs, ys, yerr=[los, his], marker="o", ms=4, lw=1.4, capsize=2,
                        color=c, label=f"{w}: 2f_topN (ranked dump)")
            # overlay 2e_K10 as a star at its footprint
            r = idx.get((w, "2e_K10", "async", metric)); n = fp.get((w, "2e_K10"))
            if r and n is not None:
                ax.plot([n], [float(r["mean_pct"])], marker="*", ms=15, color=c,
                        markeredgecolor="black", markeredgewidth=0.6, zorder=5,
                        label=f"{w}: 2e_K10 (targeted) ★")
        ax.axhline(0, color="#222", lw=0.8)
        ax.set_xscale("log")
        ax.set_xlabel("dump footprint (pages, log)")
        ax.set_ylabel(ylabel)
        ax.set_title(metric.replace("_us", ""))
    axes[1].legend(fontsize=7, ncol=1, loc="upper left")
    fig.suptitle("Competitive baseline (post tie-break fix): a tuned ranked dump (2f_topN) matches 2e_K10 (★) "
                 "on A/B AND narrow C; type-aware gives no win over footprint-matched ranking; "
                 "full dump explodes (e2e, right)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, "18_competitive_baseline")


if __name__ == "__main__":
    main()
