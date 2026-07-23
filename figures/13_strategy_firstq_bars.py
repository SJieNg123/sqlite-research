"""Figure 13: Paired first-query reduction by strategy, per workload.

Canonical (Phase 3). Each (workload, strategy) cell is read from its own
canonical per-cell source and normalized against *that same batch's* baseline,
so every bar is a paired relative reduction. Absolute microseconds are NOT
plotted and NOT compared across batches.

Sources (RESULT_PROVENANCE.md 4.2 / 4.4):
  - tie-break-unaffected cells -> results/unified_v2/matrix/summary.csv
  - tie-break-corrected cells  -> results/tiebreak_fix/master_summary.csv
    (impact set: A 2e_K500; B 2e_K10/K40/K92/K500; C 2e_K10/K40/K92)

Metric: paired first-query change vs same-batch baseline, (fq - base)/base * 100
(negative = faster). Layout = orig, arm = async, median of 10 reps.
"""
import csv, sys
from plot_utils import ROOT, save, STRATEGY_COLORS, workload_display_name
import matplotlib.pyplot as plt
import numpy as np

UNIFIED   = ROOT / "results/unified_v2/matrix/summary.csv"
TIEBREAK  = ROOT / "results/tiebreak_fix/master_summary.csv"

# tie-break impact set (cells whose canonical source is the corrected rerun)
CHANGED = {('A', '2e_K500'),
           ('B', '2e_K10'), ('B', '2e_K40'), ('B', '2e_K92'), ('B', '2e_K500'),
           ('C', '2e_K10'), ('C', '2e_K40'), ('C', '2e_K92')}

ARMS      = ['layers_5', '2d', '2e_K10', '2e_K500', '2f_slru']
ARM_LABEL = {'layers_5': 'layers_5', '2d': '2d', '2e_K10': '2e_K10',
             '2e_K500': '2e_K500', '2f_slru': '2f_slru'}
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


UROWS = load(UNIFIED)
TROWS = load(TIEBREAK)


def cell(workload, strategy):
    """Return (source_tag, baseline_fq, strategy_fq) from the canonical per-cell batch."""
    rows, tag = (TROWS, 'tiebreak') if (workload, strategy) in CHANGED else (UROWS, 'unified')
    bkey = (workload, 'orig', 'baseline', 'baseline')
    skey = (workload, 'orig', strategy, 'async')
    if bkey not in rows:
        sys.exit(f"FATAL: missing baseline {bkey} in {tag}")
    if skey not in rows:
        sys.exit(f"FATAL: missing strategy row {skey} in {tag}")
    return tag, float(rows[bkey]['fq_median']), float(rows[skey]['fq_median'])


fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), sharey=True)
x = np.arange(len(ARMS))

print("Figure 13 — plotted cells (paired first-query reduction %):")
for ax, wl in zip(axes, WORKLOADS):
    vals, tags = [], []
    for s in ARMS:
        tag, base, fq = cell(wl, s)
        pct = (fq - base) / base * 100.0
        vals.append(pct)
        tags.append(tag)
        print(f"  {wl:1s} {s:9s} [{tag:8s}] base={base:7.1f} fq={fq:7.1f}  {pct:+6.1f}%")
    for xi, v, s, tag in zip(x, vals, ARMS, tags):
        hatch = '//' if tag == 'tiebreak' else None
        ax.bar(xi, v, color=STRATEGY_COLORS.get(s, '#3b82f6'), alpha=0.9,
               edgecolor='black', linewidth=0.6, hatch=hatch)
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
from matplotlib.patches import Patch
axes[2].legend(handles=[Patch(facecolor='#d1d5db', edgecolor='black', hatch='//',
                              label='tie-break-corrected cell\n(tiebreak_fix batch)')],
               loc='lower left', fontsize=8)
fig.tight_layout()
save(fig, '13_strategy_firstq_bars')
