"""Figure 14: Warm-process end-to-end cold-start decomposition.

Single canonical batch: results/unified_v4, seed01 (2026-09-17). Stacked
absolute microseconds require one machine state, which previously forced this
chart to drop the frequency-ranked 2e_K* arms (their corrected values lived in
the separate results/tiebreak_fix batch). unified_v4 measured every arm --
including 2e_K10/2e_K500 under the corrected (-count, pageno) tie-break -- in
ONE run, and it is the batch the paper's four result tables also report, so the
absolute stack here matches Table 5's absolute columns.

Stack per strategy (layout orig, arm async, medians):
  first_query (bottom) + deliver (top) = warm-process / integrated e2e.
Green/red label = warm-process e2e vs the same-batch baseline.

Estimators: the bar HEIGHT is median(first_query) + median(deliver), because the
bar is a stack of those two plotted medians. The percentage LABEL is computed
from e2e_warm_median (the median of the per-repetition sums), which is the
canonical column the paper's tables use. The two differ by <0.4%, invisible on a
log axis, but they round differently in three cells, so the label follows the
tables rather than the drawn height -- a label is a claim, the bar is a picture.
"""
import csv, sys
from plot_utils import ROOT, save, workload_panel_title
import matplotlib.pyplot as plt
import numpy as np

UNIFIED = ROOT / "results/unified_v4/seed01/summary.csv"

# Aligned with Figure 13's strategy set (plus the baseline reference bar).
ARMS      = ['baseline', 'layers_5', '2d', '2e_K10', '2e_K500', '2f_slru']
ARM_LABEL = {'baseline': 'baseline', 'layers_5': 'Skel-5', '2d': 'Skel',
             '2e_K10': 'Skel+10', '2e_K500': 'Skel+500', '2f_slru': 'Dump'}
# CSV keys stay legacy (A/B/C); titles resolve to canonical display names.
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {w: workload_panel_title(w) for w in ('A', 'B', 'C')}
FQ_COLOR      = '#d1d5db'   # first query (bottom)
DELIVER_COLOR = '#f97316'   # deliver (top)


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


def get(workload, strategy):
    arm = 'baseline' if strategy == 'baseline' else 'async'
    key = (workload, 'orig', strategy, arm)
    if key not in ROWS:
        sys.exit(f"FATAL: missing row {key} in {UNIFIED}")
    r = ROWS[key]
    return (float(r['fq_median']),
            float(r.get('deliver_us_median') or 0),
            float(r.get('e2e_warm_median') or 0))


fig, axes = plt.subplots(1, 3, figsize=(12, 5.2), sharey=False)
x = np.arange(len(ARMS))

print("Figure 14 — plotted cells (unified_v4 absolute stack):")
for ax, wl in zip(axes, WORKLOADS):
    fqs, dels, canon = [], [], []
    for s in ARMS:
        fq, dl, ew = get(wl, s)
        fqs.append(fq); dels.append(dl); canon.append(ew)
    warm     = [f + d for f, d in zip(fqs, dels)]   # drawn stack height
    baseline = fqs[0]

    ax.bar(x, fqs, color=FQ_COLOR, alpha=0.9, edgecolor='black', linewidth=0.5,
           label='First query')
    ax.bar(x, dels, bottom=fqs, color=DELIVER_COLOR, alpha=0.95, edgecolor='black',
           linewidth=0.5, label='Deliver')

    for xi, wv, ew, s in zip(x, warm, canon, ARMS):
        if s == 'baseline':
            continue
        wi = (ew - baseline) / baseline * 100.0   # label from the canonical column
        col = '#15803d' if wi < 0 else '#dc2626'
        sign = '+' if wi >= 0 else ''
        print(f"  {wl:1s} {s:9s} fq={fqs[ARMS.index(s)]:7.1f} deliver={dels[ARMS.index(s)]:7.1f}"
              f" warm={wv:7.1f} ({sign}{wi:.0f}%)")
        ax.text(xi, wv * 1.07, f'{sign}{wi:.0f}%', ha='center', va='bottom',
                fontsize=8.5, fontweight='bold', color=col)

    ax.set_xticks(x)
    ax.set_xticklabels([ARM_LABEL[s] for s in ARMS], fontsize=9, rotation=25, ha='right')
    ax.set_title(WL_TITLE[wl], fontsize=10)
    ax.set_yscale('log')
    ax.set_ylim(80, max(warm) * 3.0)
    ax.grid(axis='y', alpha=0.25, which='both')
    ax.set_axisbelow(True)

axes[0].set_ylabel('Warm-process end-to-end latency (µs, log scale)', fontsize=10)
axes[0].legend(loc='upper left', fontsize=8)
fig.tight_layout()
save(fig, '14_strategy_endtoend_stacked')
