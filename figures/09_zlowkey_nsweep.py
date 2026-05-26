"""Figure 9: Workload Z (Zipfian low-key) N-sweep — layers_N is hotspot-agnostic.

Story: Workload A's hot keys live mid-range (Zipfian over [8, 99997]);
Workload Z places the same Zipfian skew at the LOW end of the key space.
If layers_N depended on hotspot location, the plateau height/shape would
move. It doesn't — Z plateaus at 218–225 µs (orig), 244–254 µs (vacuum),
115–130 µs (type-aware), with the same N≥5 elbow as A/B/C.
Conclusion: layers_N is a layout property, not a workload property.
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, LAYOUT_COLORS, save
import matplotlib.pyplot as plt

CSV = ROOT / "layout_rewriter/runs/matrix_Nsweep_zlowkey_results.csv"

# (db, N) -> [first_query_us, ...]
g = defaultdict(list)
for r in csv.DictReader(open(CSV)):
    g[(r["db"], int(r["N"]))].append(float(r["first_query_us"]))

DBS = [("orig", "1a"), ("vacuum", "1b"), ("ta", "1c")]
Ns  = sorted({k[1] for k in g})

fig, ax = plt.subplots(figsize=(8.5, 4.6))
for db, lbl in DBS:
    ys = [statistics.median(g[(db, n)]) for n in Ns]
    ax.plot(Ns, ys, "-o", color=LAYOUT_COLORS[db], lw=1.7, ms=5,
            label=f"layout {lbl}")
    # Annotate plateau value at N=92
    ax.text(Ns[-1] * 1.05, ys[-1], f"{ys[-1]:.0f} µs",
            color=LAYOUT_COLORS[db], fontsize=9, va="center")

ax.set_xscale("symlog", linthresh=1)
ax.set_xticks([0, 1, 5, 10, 20, 46, 92])
ax.set_xticklabels(["0", "1", "5", "10", "20", "46", "92"])
ax.set_xlabel("N (number of interior pages prefetched)")
ax.set_ylabel("first-query latency (µs, median of 3 reps)")
ax.set_xlim(-0.3, 140)
ax.set_ylim(0, 460)
ax.legend(loc="upper right")
ax.set_title("Workload Z (Zipfian low-key) N-sweep · same plateau shape as A/B/C\n"
             "layers_N is a layout property — hotspot location does not matter",
             fontsize=11)
fig.tight_layout()
save(fig, "09_zlowkey_nsweep")
