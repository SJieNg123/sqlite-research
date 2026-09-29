"""Figure 13: Paired first-query reduction by strategy, per workload.

Single canonical batch: results/unified_v6, seed01 (2026-09-23). Every cell --
including the frequency-ranked 2e_K* arms -- was measured in ONE run with the
corrected (-count, pageno) tie-break, so no per-cell source selection is needed.
This is the same batch that backs the paper's four result tables, so the figure
and the tables cannot disagree.

Bars are still paired relative reductions against the batch's own baseline;
absolute microseconds are NOT plotted.

Metric: paired first-query change vs same-batch baseline, (fq - base)/base * 100
(negative = faster). Layout = orig, arm = async, median of 10 reps.

Styled with pub_style.py, the scientific-figure-making (figures4papers) house style.
"""

import csv, sys
from plot_utils import ROOT, save, workload_panel_title
import matplotlib.pyplot as plt
import numpy as np

from pub_style import PALETTE, apply
apply()

UNIFIED   = ROOT / "results/unified_v6/seed01/summary.csv"
ARMS      = ['layers_5', '2d', '2e_K10', '2e_K500', '2f_slru']
ARM_LABEL = {'layers_5': 'Skel-5', '2d': 'Skel', '2e_K10': 'Skel+10',
             '2e_K500': 'Skel+500', '2f_slru': 'Dump'}
ARM_COLOR = {'layers_5': PALETTE['neutral'], '2d': PALETTE['blue_main'],
             '2e_K10': PALETTE['blue_secondary'], '2e_K500': PALETTE['teal'],
             '2f_slru': PALETTE['red_strong']}
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {w: workload_panel_title(w) for w in WORKLOADS}


def load(path):
    idx = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            key = (r['workload'], r['db'], r['strategy'], r['arm'])
            if key in idx:
                sys.exit(f"FATAL: duplicate row {key} in {path}")
            idx[key] = r
    return idx


ROWS = load(UNIFIED)


def cell(workload, strategy):
    bkey = (workload, 'orig', 'baseline', 'baseline')
    skey = (workload, 'orig', strategy, 'async')
    for k in (bkey, skey):
        if k not in ROWS:
            sys.exit(f"FATAL: missing row {k} in {UNIFIED}")
    return float(ROWS[bkey]['fq_median']), float(ROWS[skey]['fq_median'])


fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), sharey=True)
x = np.arange(len(ARMS))

for ax, wl in zip(axes, WORKLOADS):
    for xi, s in zip(x, ARMS):
        base, fq = cell(wl, s)
        v = (fq - base) / base * 100.0
        ax.bar(xi, v, width=0.72, color=ARM_COLOR[s], edgecolor='black', linewidth=1.5)
        ax.text(xi, v + (-2.5 if v < 0 else 2.5), f'{v:.0f}%', ha='center',
                va='top' if v < 0 else 'bottom', fontsize=12, fontweight='bold')
    ax.axhline(0, color='black', lw=2)
    ax.set_xticks(x)
    ax.set_xticklabels([ARM_LABEL[s] for s in ARMS], fontsize=11.5)
    ax.tick_params(axis='x', length=0)
    ax.set_title(WL_TITLE[wl], fontsize=14.5)
    ax.set_ylim(-102, 12)

axes[0].set_ylabel('Paired first-query change (%)\nnegative = faster')
fig.tight_layout(pad=1.5)
save(fig, '13_strategy_firstq_bars')
