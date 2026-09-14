"""Figure 13: Paired first-query reduction by strategy, per workload.

Single canonical batch: results/unified_v3 (2026-09-14). Every cell -- including
the frequency-ranked 2e_K* arms -- was measured in ONE run with the corrected
(-count, pageno) tie-break, so no per-cell source selection is needed and the
former two-source split (unified_v2 + tiebreak_fix) no longer applies.

Bars are still paired relative reductions against the batch's own baseline;
absolute microseconds are NOT plotted.

Metric: paired first-query change vs same-batch baseline, (fq - base)/base * 100
(negative = faster). Layout = orig, arm = async, median of 10 reps.
"""
import csv, sys
from plot_utils import ROOT, save, STRATEGY_COLORS, workload_display_name
import matplotlib.pyplot as plt
import numpy as np

UNIFIED   = ROOT / "results/unified_v3/matrix/summary.csv"

ARMS      = ['layers_5', '2d', '2e_K10', '2e_K500', '2f_slru']
ARM_LABEL = {'layers_5': 'Skel-5', '2d': 'Skel', '2e_K10': 'Skel+10',
             '2e_K500': 'Skel+500', '2f_slru': 'Dump'}
# CSV keys stay legacy (A/B/C); titles resolve to canonical display names.
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {'A': workload_display_name('A'),
             'B': workload_display_name('B'),
             'C': workload_display_name('C') + ' — ~50% not-found tail-boundary'}


def load(path):
    """Index one summary CSV as {(workload, db, strategy, arm): row}; fail on dup."""
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
    """Return (baseline_fq, strategy_fq) from the single canonical batch."""
    bkey = (workload, 'orig', 'baseline', 'baseline')
    skey = (workload, 'orig', strategy, 'async')
    if bkey not in ROWS:
        sys.exit(f"FATAL: missing baseline {bkey} in {UNIFIED}")
    if skey not in ROWS:
        sys.exit(f"FATAL: missing strategy row {skey} in {UNIFIED}")
    return float(ROWS[bkey]['fq_median']), float(ROWS[skey]['fq_median'])


fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), sharey=True)
x = np.arange(len(ARMS))

print("Figure 13 — plotted cells (paired first-query reduction %):")
for ax, wl in zip(axes, WORKLOADS):
    vals = []
    for s in ARMS:
        base, fq = cell(wl, s)
        pct = (fq - base) / base * 100.0
        vals.append(pct)
        print(f"  {wl:1s} {s:9s} base={base:7.1f} fq={fq:7.1f}  {pct:+6.1f}%")
    for xi, v, s in zip(x, vals, ARMS):
        ax.bar(xi, v, color=STRATEGY_COLORS.get(s, '#3b82f6'), alpha=0.9,
               edgecolor='black', linewidth=0.6)
        off = -2.0 if v < 0 else 2.0
        ax.text(xi, v + off, f'{v:.0f}%', ha='center',
                va='top' if v < 0 else 'bottom', fontsize=8, fontweight='bold')
    ax.axhline(0, color='#374151', lw=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([ARM_LABEL[s] for s in ARMS], fontsize=9, rotation=25, ha='right')
    ax.set_title(WL_TITLE[wl], fontsize=11)
    ax.set_ylim(-100, 12)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)

axes[0].set_ylabel('paired first-query change vs\nsame-batch baseline (%)  [negative = faster]', fontsize=9)
fig.tight_layout()
save(fig, '13_strategy_firstq_bars')
