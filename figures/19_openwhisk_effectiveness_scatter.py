"""Fig 19 -- OpenWhisk vs workstation effectiveness portability (relative, not absolute).

Scatter of the *relative* first-query reduction R = (baseline_fq - strategy_fq)/baseline_fq
for the 55 non-lp (strategy x workload) cells that BOTH platforms ran at orig layout:
x = workstation R, y = OpenWhisk R (standalone handle). Points on the y=x diagonal mean the
strategy is equally effective on both platforms; the cluster along the diagonal is the
portability result. This figure deliberately plots RELATIVE reductions against each other --
NOT absolute microseconds, which are systematically different across the two environments
and must not be compared cell-for-cell.

The 10 libprefetch (lp_sorted/lp_shuf) cells are compared separately by delivery ORDER
(deliver_us), not by first-query R, so they are excluded here (55 + 10 = 65 matched cells).

Data source: deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation.csv
Run:  /home/u03/.cache/coldstart-venv/bin/python figures/19_openwhisk_effectiveness_scatter.py
"""
import csv
import numpy as np
from plot_utils import ROOT, plt, save

CSV = ROOT / "deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation.csv"

# 5 comparison workloads (local palette; plot_utils only carries the legacy A/B/C/Z).
WL_COLOR = {
    "YC":    "#1f77b4",
    "YCu":   "#17becf",
    "YCh01": "#9467bd",
    "C":     "#d62728",
    "C_hit": "#ff7f0e",
}
WL_ORDER = ["YC", "YCu", "YCh01", "C", "C_hit"]

# The 3 STRONG (R_ws >= 0.30) cells whose direction flips on OpenWhisk -- surfaced, not hidden.
EXCEPTIONS = {("C", "2d"), ("C", "layers_92"), ("C_hit", "2e_K40")}


def spearman(x, y):
    """Rank correlation without scipy: Pearson on the ranks."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def main():
    rows = list(csv.DictReader(open(CSV)))
    assert len(rows) == 55, f"expected 55 first-query cells, got {len(rows)}"

    R_ws = np.array([float(r["R_ws"]) for r in rows])
    R_ow = np.array([float(r["R_ow"]) for r in rows])
    low_conf = np.array([r["low_conf"] == "True" for r in rows])
    agree = np.array([r["sign_agree"] == "True" for r in rows])

    rho_all = spearman(R_ws, R_ow)
    hi = ~low_conf
    rho_hi = spearman(R_ws[hi], R_ow[hi])
    n_agree = int(agree.sum())
    med_abs = float(np.median(np.abs(R_ow - R_ws)))

    fig, ax = plt.subplots(figsize=(6.4, 6.0))

    # reference geometry: y=x diagonal + zero axes (quadrant separators)
    lo, hi_lim = -0.85, 1.0
    ax.plot([lo, hi_lim], [lo, hi_lim], color="#555555", lw=1.2, ls="--",
            zorder=1, label="y = x (equal effectiveness)")
    ax.axhline(0, color="#bbbbbb", lw=0.8, zorder=0)
    ax.axvline(0, color="#bbbbbb", lw=0.8, zorder=0)

    # points: filled = high-confidence, hollow = low-confidence; colour = workload
    for wl in WL_ORDER:
        c = WL_COLOR[wl]
        idx_hi = [i for i, r in enumerate(rows) if r["workload"] == wl and not low_conf[i]]
        idx_lo = [i for i, r in enumerate(rows) if r["workload"] == wl and low_conf[i]]
        if idx_hi:
            ax.scatter(R_ws[idx_hi], R_ow[idx_hi], s=48, color=c, edgecolor="white",
                       linewidth=0.6, zorder=4, label=wl)
        if idx_lo:
            ax.scatter(R_ws[idx_lo], R_ow[idx_lo], s=48, facecolor="none", edgecolor=c,
                       linewidth=1.3, zorder=4,
                       label=f"{wl} (low-conf)" if not idx_hi else None)

    # ring + label the 3 strong exceptions (labels pushed right, into empty space)
    for i, r in enumerate(rows):
        if (r["workload"], r["strategy"]) in EXCEPTIONS:
            ax.scatter(R_ws[i], R_ow[i], s=200, facecolor="none", edgecolor="#d62728",
                       linewidth=1.6, zorder=5)
            ax.annotate(f"{r['workload']}/{r['strategy']}",
                        (R_ws[i], R_ow[i]), textcoords="offset points",
                        xytext=(14, 0), fontsize=8, color="#b91c1c", zorder=6,
                        va="center")
    ax.text(0.60, -0.34, "strong on workstation,\nbut flips sign on OpenWhisk\n(all low-n / position-imbalanced)",
            transform=ax.transData, fontsize=7.5, color="#b91c1c", ha="left", va="top")

    # stats box
    txt = (f"Spearman $\\rho$ = {rho_all:.2f} (all, n=55)\n"
           f"          = {rho_hi:.2f} (high-conf, n={int(hi.sum())})\n"
           f"direction agree: {n_agree}/55\n"
           f"median |$R_{{OW}}-R_{{WS}}$| = {med_abs:.3f}")
    ax.text(0.03, 0.97, txt, transform=ax.transAxes, va="top", ha="left", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="#f8fafc", ec="#cbd5e1"))

    ax.set_xlim(lo, hi_lim)
    ax.set_ylim(lo, hi_lim)
    ax.set_xlabel("Workstation relative first-query reduction  $R_{WS}$")
    ax.set_ylabel("OpenWhisk relative first-query reduction  $R_{OW}$")
    ax.set_title("Effectiveness ports to OpenWhisk (relative reduction, not absolute µs)")
    ax.legend(loc="lower left", fontsize=8, ncol=1)
    ax.set_aspect("equal", adjustable="box")

    save(fig, "19_openwhisk_effectiveness_scatter")
    print(f"  rho_all={rho_all:.4f} rho_hi={rho_hi:.4f} agree={n_agree}/55 median|d|={med_abs:.4f}")


if __name__ == "__main__":
    main()
