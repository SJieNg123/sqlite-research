"""Figure 14: Warm-process end-to-end cold-start decomposition.

Single canonical batch: results/unified_v6, seed01 (2026-09-23). Stacked
absolute microseconds require one machine state, and unified_v6 measured every
arm in ONE continuous window, so the absolute stack here matches the paper's
result tables.

Each strategy is drawn TWICE, once per delivery mechanism (layout orig, medians):
  first_query (bottom, grey) + deliver (top, orange) = warm-process e2e.
  light = async     : one posix_fadvise per page
  dark  = async_win : one posix_fadvise per 32-page readahead window
Hue encodes the COMPONENT and lightness encodes the MECHANISM, because the point
of the pair is that the grey block does not move while the orange block does.
The saving scales with how much a strategy had to deliver, which is why Dump's
tower collapses and the targeted arms barely change. Green/red label = e2e_warm
vs the same-batch baseline, which is the leftmost bar of each panel.

Caveat carried from the batch: seed01's Scattered-Zipf baseline is a genuine
instantiation outlier (492 us against 828-1024 on the other nine seeds), so the
Dump percentage here reads worse than the cross-seed figure. The absolute stack
is unaffected, and the labels match Table 5, which quotes the same seed.

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

UNIFIED = ROOT / "results/unified_v6/seed01/summary.csv"

# Aligned with Figure 13's strategy set (plus the baseline reference bar).
ARMS      = ['baseline', 'layers_5', '2d', '2e_K10', '2e_K500', '2f_slru']
ARM_LABEL = {'baseline': 'baseline', 'layers_5': 'Skel-5', '2d': 'Skel',
             '2e_K10': 'Skel+10', '2e_K500': 'Skel+500', '2f_slru': 'Dump'}
# CSV keys stay legacy (A/B/C); titles resolve to canonical display names.
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {w: workload_panel_title(w) for w in ('A', 'B', 'C')}
FQ_COLOR      = '#d1d5db'   # first query (bottom), baseline bar
DELIVER_COLOR = '#f97316'   # deliver (top)
# Two delivery mechanisms side by side. Hue encodes the COMPONENT (grey = first
# query, orange = deliver) and lightness encodes the MECHANISM (light = per-page,
# dark = window-chunked). No hatching: the point of the pair is that the grey
# block does not move and the orange block does, and a fill pattern competes with
# that reading instead of supporting it.
DELIV_ARMS = ['async', 'async_win']
ARM_FQ     = {'async': '#d1d5db', 'async_win': '#9ca3af'}
ARM_DELIV  = {'async': '#fdba74', 'async_win': '#ea580c'}
ARM_TITLE  = {'async': 'per-page hint', 'async_win': 'window-chunked hint'}


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


def get(workload, strategy, arm='async'):
    arm = 'baseline' if strategy == 'baseline' else arm
    key = (workload, 'orig', strategy, arm)
    if key not in ROWS:
        sys.exit(f"FATAL: missing row {key} in {UNIFIED}")
    r = ROWS[key]
    return (float(r['fq_median']),
            float(r.get('deliver_us_median') or 0),
            float(r.get('e2e_warm_median') or 0))


fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.2), sharey=False)
x = np.arange(len(ARMS))
W = 0.38                      # paired-bar width

print("Figure 14 - plotted cells (unified_v6 seed01, async vs async_win):")
for ax, wl in zip(axes, WORKLOADS):
    baseline = get(wl, 'baseline')[0]
    tops = []
    for s in ARMS:
        if s == 'baseline':
            fq, dl, ew = get(wl, s)
            ax.bar([x[ARMS.index(s)]], [fq], width=W, color=FQ_COLOR, alpha=0.9,
                   edgecolor='black', linewidth=0.5)
            tops.append(fq)
            continue
        for j, arm in enumerate(DELIV_ARMS):
            fq, dl, ew = get(wl, s, arm)
            xi = x[ARMS.index(s)] + (j - 0.5) * W
            ax.bar([xi], [fq], width=W, color=ARM_FQ[arm], alpha=0.95,
                   edgecolor='black', linewidth=0.5)
            ax.bar([xi], [dl], width=W, bottom=[fq], color=ARM_DELIV[arm], alpha=0.95,
                   edgecolor='black', linewidth=0.5)
            warm = fq + dl
            tops.append(warm)
            wi = (ew - baseline) / baseline * 100.0
            col = '#15803d' if wi < 0 else '#dc2626'
            sign = '+' if wi >= 0 else ''
            print(f"  {wl:5s} {s:9s} {arm:9s} fq={fq:7.1f} deliver={dl:7.1f}"
                  f" warm={warm:7.1f} ({sign}{wi:.0f}%)")
            # Each label sits just above the bar it describes. The pair is only
            # 0.38 x-units wide, so the panels are given enough width that a
            # six-character label fits over its own bar instead of spilling onto
            # its taller neighbour.
            # The window-chunked label is nudged a hair right, off its taller
            # per-page neighbour and toward the gap between groups.
            xlab = xi + (0.04 if arm == 'async_win' else 0.0)
            ax.text(xlab, warm * 1.07, f'{sign}{wi:.0f}%', ha='center', va='bottom',
                    fontsize=6.0, fontweight='bold', color=col)

    ax.set_xticks(x)
    ax.set_xticklabels([ARM_LABEL[s] for s in ARMS], fontsize=8.5, rotation=0, ha='center')
    ax.set_title(WL_TITLE[wl], fontsize=10)
    ax.set_yscale('log')
    ax.set_ylim(70, max(tops) * 3.2)
    ax.grid(axis='y', alpha=0.25, which='both')
    ax.set_axisbelow(True)

from matplotlib.patches import Patch
handles = [Patch(facecolor=ARM_FQ['async'], edgecolor='black',
                 label=f"First query, {ARM_TITLE['async']}"),
           Patch(facecolor=ARM_DELIV['async'], edgecolor='black',
                 label=f"Deliver, {ARM_TITLE['async']}"),
           Patch(facecolor=ARM_FQ['async_win'], edgecolor='black',
                 label=f"First query, {ARM_TITLE['async_win']}"),
           Patch(facecolor=ARM_DELIV['async_win'], edgecolor='black',
                 label=f"Deliver, {ARM_TITLE['async_win']}")]
axes[0].set_ylabel('Warm-process end-to-end latency (µs, log scale)', fontsize=10)
# The legend gets its own strip above the panels. Inside panel A it would sit in
# the same headroom the two label rows occupy.
fig.tight_layout(rect=(0, 0, 1, 0.92))
fig.legend(handles=handles, loc='upper center', ncol=4, fontsize=8.5,
           frameon=False, bbox_to_anchor=(0.5, 1.0))
save(fig, '14_strategy_endtoend_stacked')
