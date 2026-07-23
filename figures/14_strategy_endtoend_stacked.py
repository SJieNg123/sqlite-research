"""Figure 14: End-to-end cold-start decomposition under two deployment models.

Canonical (Phase 3). Stacked absolute microseconds require a single
machine-state batch, so this chart plots ONLY the tie-break-unaffected
strategies (baseline, layers_5, 2d, 2f_slru) from results/unified_v2. The
tie-break-corrected hotspot arms (A 2e_K500, C_mixed 2e_K10) belong to a
different batch (results/tiebreak_fix) and are reported separately in the
paper's Table tab:corrected-arms; they are deliberately NOT stacked here.

Stack per strategy (layout orig, arm async, medians):
  first_query (bottom) + deliver + cold open(db) (top).
  warm-process / integrated e2e = first_query + deliver          (bar minus grey)
  standalone-warmer e2e         = first_query + deliver + open    (full bar)
Green/red label = warm-process e2e vs the same-batch baseline.
"""
import csv, sys
from plot_utils import ROOT, save, STRATEGY_COLORS, workload_display_name
import matplotlib.pyplot as plt
import numpy as np

UNIFIED = ROOT / "results/unified_v2/matrix/summary.csv"

ARMS      = ['baseline', 'layers_5', '2d', '2f_slru']   # tie-break-unaffected only
ARM_LABEL = {'baseline': 'baseline', 'layers_5': 'layers_5', '2d': '2d', '2f_slru': '2f_slru'}
# CSV keys stay legacy (A/B/C); titles resolve to canonical display names.
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {'A': workload_display_name('A'),
             'B': workload_display_name('B'),
             'C': workload_display_name('C') + ' (~50% not-found)'}


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

print("Figure 14 — plotted cells (unified_v2 absolute stack):")
for ax, wl in zip(axes, WORKLOADS):
    fqs, dels, opens = [], [], []
    for s in ARMS:
        fq, dl, op = get(wl, s)
        fqs.append(fq); dels.append(dl); opens.append(op)
    warm       = [f + d for f, d in zip(fqs, dels)]
    standalone = [w + o for w, o in zip(warm, opens)]
    baseline   = fqs[0]
    colors = [STRATEGY_COLORS.get(s, '#3b82f6') for s in ARMS]

    ax.bar(x, fqs, color=colors, alpha=0.9, edgecolor='black', linewidth=0.5,
           label='first-query (SQL latency)')
    ax.bar(x, dels, bottom=fqs, color='#fbbf24', alpha=0.95, edgecolor='black',
           linewidth=0.5, hatch='///', label='deliver (prefetch syscalls)')
    ax.bar(x, opens, bottom=warm, color='#d1d5db', alpha=0.95, edgecolor='black',
           linewidth=0.5, hatch='xx', label='cold open(db) — saved if integrated')
    ax.axhline(baseline, color='#9ca3af', ls='--', lw=1.0, alpha=0.7, zorder=0)

    for xi, wv, sv, s in zip(x, warm, standalone, ARMS):
        if s == 'baseline':
            continue
        wi = (wv - baseline) / baseline * 100.0
        col = '#15803d' if wi < 0 else '#dc2626'
        sign = '+' if wi >= 0 else ''
        print(f"  {wl:1s} {s:9s} fq={fqs[ARMS.index(s)]:7.1f} deliver={dels[ARMS.index(s)]:7.1f}"
              f" open={opens[ARMS.index(s)]:6.1f} warm={wv:7.1f} ({sign}{wi:.0f}%)")
        ax.text(xi, sv * 1.07, f'{sign}{wi:.0f}%', ha='center', va='bottom',
                fontsize=8.5, fontweight='bold', color=col)

    ax.set_xticks(x)
    ax.set_xticklabels([ARM_LABEL[s] for s in ARMS], fontsize=9, rotation=25, ha='right')
    ax.set_title(WL_TITLE[wl], fontsize=11)
    ax.set_yscale('log')
    ax.set_ylim(80, max(standalone) * 4.0)
    ax.grid(axis='y', alpha=0.25, which='both')
    ax.set_axisbelow(True)

axes[0].set_ylabel('end-to-end cold start (µs, log scale)', fontsize=10)
axes[0].legend(loc='upper left', fontsize=8)
fig.tight_layout()
save(fig, '14_strategy_endtoend_stacked')
