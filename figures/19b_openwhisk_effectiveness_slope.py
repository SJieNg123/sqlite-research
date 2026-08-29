"""Fig 19b -- OpenWhisk effectiveness portability as a SLOPE chart (workstation -> OpenWhisk).

Same 55 non-lp cells as Fig 19, drawn as connected slopes instead of a scatter: within each
workload panel every strategy is one line whose left endpoint is its workstation relative
first-query reduction R_WS and whose right endpoint is its OpenWhisk R_OW (standalone). A line
that stays flat/high means the strategy is about as effective on OpenWhisk as on the
workstation -- it ports. A line that dives below zero is a direction flip (surfaced, not hidden).

Like Fig 19 this plots RELATIVE reductions only -- NOT absolute microseconds, which are not
cross-environment comparable. The 10 libprefetch cells are compared separately by delivery
order, so they are excluded here (55 + 10 = 65 matched cells).

Data source: deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation.csv
Run:  /home/u03/.cache/coldstart-venv/bin/python figures/19b_openwhisk_effectiveness_slope.py
"""
import csv
from collections import defaultdict

from matplotlib.lines import Line2D

from plot_utils import ROOT, plt, save

CSV = ROOT / "deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation.csv"

WL_ORDER = ["YC", "YCu", "YCh01", "C", "C_hit"]

# The 3 STRONG (R_ws >= 0.30) cells whose direction flips on OpenWhisk -- surfaced, not hidden.
EXCEPTIONS = {("C", "2d"), ("C", "layers_92"), ("C_hit", "2e_K40")}

AGREE = "#2563eb"   # blue  -- same direction on both platforms
FLIP = "#d62728"    # red   -- direction flips


def main():
    rows = list(csv.DictReader(open(CSV)))
    assert len(rows) == 55, f"expected 55 first-query cells, got {len(rows)}"

    by_wl = defaultdict(list)
    for r in rows:
        by_wl[r["workload"]].append(r)

    fig, axes = plt.subplots(1, len(WL_ORDER), sharey=True, figsize=(15, 4.4))

    for ax, wl in zip(axes, WL_ORDER):
        cells = by_wl[wl]
        n_port = 0
        for r in cells:
            rws, row_ = float(r["R_ws"]), float(r["R_ow"])
            agree = r["sign_agree"] == "True"
            low = r["low_conf"] == "True"
            is_exc = (wl, r["strategy"]) in EXCEPTIONS
            color = FLIP if not agree else AGREE
            lw = 2.4 if is_exc else 1.4
            alpha = 0.9 if (is_exc or not low) else 0.35
            z = 5 if is_exc else 3
            ax.plot([0, 1], [rws, row_], color=color, lw=lw, alpha=alpha,
                    marker="o", markersize=5, markeredgecolor="white",
                    markeredgewidth=0.5, zorder=z)
            if rws > 0.10 and row_ > 0.10:
                n_port += 1
            if is_exc:
                ax.annotate(r["strategy"], (1, row_), textcoords="offset points",
                            xytext=(6, 0), fontsize=7.5, color=FLIP, va="center", zorder=6)

        # effectiveness boundary (R=0) and the +0.10 "effective" threshold
        ax.axhline(0.0, color="#999999", lw=0.9, zorder=1)
        ax.axhline(0.10, color="#cccccc", lw=0.8, ls=":", zorder=1)
        ax.axhspan(-0.9, 0.10, color="#f1f5f9", zorder=0)  # shaded "not effective" zone

        ax.set_title(f"{wl}\n{n_port}/{len(cells)} effective on both", fontsize=10)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["work-\nstation", "Open-\nWhisk"], fontsize=9)
        ax.set_xlim(-0.28, 1.42)
        ax.grid(axis="x", visible=False)

    axes[0].set_ylabel("Relative first-query reduction  R\n(>0 = faster = effective)")
    axes[0].set_ylim(-0.85, 1.0)

    handles = [
        Line2D([0], [0], color=AGREE, lw=2, marker="o", label="same direction (ports)"),
        Line2D([0], [0], color=FLIP, lw=2, marker="o", label="direction flips"),
        Line2D([0], [0], color=AGREE, lw=1.4, alpha=0.35, marker="o", label="low-confidence (faded)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Effectiveness ports to OpenWhisk — each line is one strategy "
                 "(workstation → OpenWhisk relative reduction, not absolute µs)",
                 fontsize=12, y=1.02)
    fig.tight_layout()

    save(fig, "19b_openwhisk_effectiveness_slope")


if __name__ == "__main__":
    main()
