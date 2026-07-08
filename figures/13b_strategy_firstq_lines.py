"""Figure 13b: First-query latency — strategy line-chart variant of figure 13.

Line version of figure 13 (bar chart kept as 13_strategy_firstq_bars). Each of
the 7 strategies is one line across the 3 workloads (x axis), log y, so the
strategies compare directly: 2f_slru sits lowest on every workload, while
2e_K10 only reaches the floor on C and layers_N clusters mid-range. More
compact than the 3-panel bar chart for the two-column VLDB layout.

Data (master batch, authoritative): results/main/summary.csv, async arm,
layout=orig, median of 10 reps (warmup dropped).
"""
from plot_utils import save, load_summary, STRAT_ORDER, STRAT_LABELS, STRATEGY_COLORS
import matplotlib.pyplot as plt
import numpy as np

DATA = load_summary("async")
STRATEGIES = STRAT_ORDER
# (linestyle, marker) per strategy — breaks up the blue (structural) and green
# (access-pattern) colour families so overlapping lines stay traceable.
STYLE = {
    'baseline': ('-', 'o'), 'layers_5': ('-', 's'), 'layers_92': ('--', '^'),
    '2d': ('-', 'D'), '2e_K10': ('--', 'v'), '2e_K500': (':', 'P'),
    '2f_slru': ('-', 'X'),
}
WORKLOADS = ['A', 'B', 'C']
WL_LABEL = {'A': 'A\n(Zipfian)', 'B': 'B\n(uniform)', 'C': 'C\n(file-tail)'}

fig, ax = plt.subplots(figsize=(6.4, 4.6))
x = np.arange(len(WORKLOADS))

for s in STRATEGIES:
    ls, mk = STYLE[s]
    y = [float(DATA[(wl, 'orig', s)]['fq_median']) for wl in WORKLOADS]
    ax.plot(x, y, ls=ls, marker=mk, color=STRATEGY_COLORS.get(s, '#3b82f6'),
            lw=1.8, ms=7, label=STRAT_LABELS[s])

ax.set_yscale('log')
ax.set_xticks(x)
ax.set_xticklabels([WL_LABEL[w] for w in WORKLOADS], fontsize=9.5)
ax.set_xlim(-0.25, len(WORKLOADS) - 0.75)
ax.set_ylabel('first-query latency (µs, log scale)', fontsize=10)
ax.set_xlabel('workload', fontsize=10)
ax.grid(axis='y', alpha=0.3, which='both')
ax.set_axisbelow(True)
ax.legend(loc='center left', bbox_to_anchor=(1.01, 0.5), fontsize=9,
          title='strategy', title_fontsize=9)
fig.tight_layout()
save(fig, '13b_strategy_firstq_lines')
