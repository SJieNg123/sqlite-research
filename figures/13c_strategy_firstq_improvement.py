"""Figure 13c: First-query *improvement %* — strategy line-chart variant.

Third view of figure 13 (bars = 13_strategy_firstq_bars, absolute-us lines =
13b_strategy_firstq_lines). Here y is the first-query improvement over the
same-workload baseline, plotted positive-up so "higher = better" reads at a
glance. Being dimensionless, it is also machine-state neutral (no absolute us).
One line per strategy across the 3 workloads; baseline omitted (0% by
definition, drawn as the reference line at y=0).

Data (master batch, authoritative): results/main/summary.csv, async arm,
layout=orig, median of 10 reps (warmup dropped).
"""
from plot_utils import save, load_summary, STRAT_ORDER, STRAT_LABELS
import matplotlib.pyplot as plt
import numpy as np

DATA = load_summary("async")
# drop baseline (it is 0% by construction -> the reference line)
STRATEGIES = [s for s in STRAT_ORDER if s != "baseline"]
# distinct hues so the lines separate by colour alone (no markers)
LINE_COLORS = {
    'layers_5':  '#2563eb',  # blue
    'layers_92': '#7c3aed',  # violet
    '2d':        '#059669',  # green
    '2e_K10':    '#0891b2',  # cyan
    '2e_K500':   '#db2777',  # magenta
    '2f_slru':   '#ea580c',  # orange
}
WORKLOADS = ['A', 'B', 'C']
WL_LABEL = {'A': 'A\n(Zipfian)', 'B': 'B\n(uniform)', 'C': 'C\n(file-tail)'}

fig, ax = plt.subplots(figsize=(6.4, 4.6))
x = np.arange(len(WORKLOADS))

for s in STRATEGIES:
    y = []
    for wl in WORKLOADS:
        base = float(DATA[(wl, 'orig', 'baseline')]['fq_median'])
        val = float(DATA[(wl, 'orig', s)]['fq_median'])
        y.append((base - val) / base * 100.0)
    ax.plot(x, y, color=LINE_COLORS[s], lw=2.2, label=STRAT_LABELS[s])

ax.axhline(0, color='#9ca3af', lw=1.0, ls='--', zorder=0)
ax.text(len(WORKLOADS) - 1.02, 1.5, 'baseline (no improvement)', fontsize=7.5,
        color='#9ca3af', ha='right', va='bottom')
ax.set_xticks(x)
ax.set_xticklabels([WL_LABEL[w] for w in WORKLOADS], fontsize=9.5)
ax.set_xlim(-0.25, len(WORKLOADS) - 0.75)
ax.set_ylim(-5, 100)
ax.set_ylabel('first-query improvement vs baseline (%)', fontsize=10)
ax.set_xlabel('workload', fontsize=10)
ax.grid(axis='y', alpha=0.3)
ax.set_axisbelow(True)
ax.legend(loc='center left', bbox_to_anchor=(1.01, 0.5), fontsize=9,
          title='strategy', title_fontsize=9)
fig.tight_layout()
save(fig, '13c_strategy_firstq_improvement')
