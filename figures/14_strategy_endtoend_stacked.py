"""Figure 14: Warm-process end-to-end cold-start decomposition.

Single canonical batch: results/unified_v3 (2026-09-14). Stacked absolute
microseconds require one machine state, which previously forced this chart to
drop the frequency-ranked 2e_K* arms (their corrected values lived in the
separate results/tiebreak_fix batch). unified_v3 measured every arm -- including
2e_K10/2e_K500 under the corrected (-count, pageno) tie-break -- in ONE run, so
the strategy set here now matches Figure 13.

Stack per strategy (layout orig, arm async, medians):
  first_query (bottom) + deliver (top) = warm-process / integrated e2e.
Green/red label = warm-process e2e vs the same-batch baseline.

Note: the stack height is median(first_query) + median(deliver), i.e. the bar is
the sum of the two plotted medians. The CSV also carries e2e_warm_median (the
median of the per-repetition sums), which the paper's tables use; the two differ
by <0.4% here and every printed label is unchanged, but they are not the same
estimator.
"""
import csv, sys
from plot_utils import ROOT, save, STRATEGY_COLORS, workload_panel_title
import matplotlib.pyplot as plt
import numpy as np

UNIFIED = ROOT / "results/unified_v3/matrix/summary.csv"

# Aligned with Figure 13's strategy set (plus the baseline reference bar).
ARMS      = ['baseline', 'layers_5', '2d', '2e_K10', '2e_K500', '2f_slru']
ARM_LABEL = {'baseline': 'baseline', 'layers_5': 'Skel-5', '2d': 'Skel',
             '2e_K10': 'Skel+10', '2e_K500': 'Skel+500', '2f_slru': 'Dump'}
# CSV keys stay legacy (A/B/C); titles resolve to canonical display names.
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {w: workload_panel_title(w) for w in ('A', 'B', 'C')}


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
            float(r.get('open_us_median') or 0))


fig, axes = plt.subplots(1, 3, figsize=(12, 5.2), sharey=False)
x = np.arange(len(ARMS))

print("Figure 14 — plotted cells (unified_v3 absolute stack):")
for ax, wl in zip(axes, WORKLOADS):
    fqs, dels = [], []
    for s in ARMS:
        fq, dl, _op = get(wl, s)
        fqs.append(fq); dels.append(dl)
    warm     = [f + d for f, d in zip(fqs, dels)]
    baseline = fqs[0]
    colors = [STRATEGY_COLORS.get(s, '#3b82f6') for s in ARMS]

    ax.bar(x, fqs, color=colors, alpha=0.9, edgecolor='black', linewidth=0.5,
           label='First query')
    ax.bar(x, dels, bottom=fqs, color='#dc2626', alpha=0.95, edgecolor='black',
           linewidth=0.5, label='Deliver')
    ax.axhline(baseline, color='#9ca3af', ls='--', lw=1.0, alpha=0.7, zorder=0)

    for xi, wv, s in zip(x, warm, ARMS):
        if s == 'baseline':
            continue
        wi = (wv - baseline) / baseline * 100.0
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
