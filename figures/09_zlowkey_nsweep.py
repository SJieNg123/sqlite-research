"""Figure 9: Workload Z is a robustness check on Workload A's main result.

A = Zipfian over keys [8, 99997] (mid-range hotspot)
Z = Zipfian over keys [1, 1000] (low-key hotspot — SAME skew, different
     hotspot LOCATION in the B+tree)

If layers_N's win on A came from the specific hot LEAVES happening to be
nearby, Z would plateau at a different height/shape. It doesn't:
   - N=5 elbow is identical
   - Plateau ordering 1c < 1a < 1b is identical
   - Plateau heights differ by <10%

Conclusion: layers_N's gain is structural (interior tree shape + layout),
NOT dependent on which subset of leaves the workload happens to hit.
This is one of two robustness checks (the other: 50k-op churn, Figure 7).
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, LAYOUT_COLORS, save
import matplotlib.pyplot as plt

CSV_Z = ROOT / "layout_rewriter/runs/matrix_Nsweep_zlowkey_results.csv"
CSV_A = ROOT / "layout_rewriter/runs/matrix_Nsweep_orig_a_results.csv"
CSV_BC = ROOT / "layout_rewriter/runs/matrix_Nsweep_bc_results.csv"
CSV_VAC = ROOT / "layout_rewriter/runs/matrix_Nsweep_vac_results.csv"
CSV_TA  = ROOT / "layout_rewriter/runs/matrix_Nsweep_ta_results.csv"

def load(path, workload, db_filter=None):
    g = defaultdict(list)
    for r in csv.DictReader(open(path)):
        if r["workload"] != workload: continue
        if db_filter and r.get("db") != db_filter: continue
        g[int(r["N"])].append(float(r["first_query_us"]))
    return {n: statistics.median(v) for n, v in g.items()}

# Workload Z across 3 layouts (single CSV, has db column)
z_by_db = {db: load(CSV_Z, "Z", db) for db in ["orig", "vacuum", "ta"]}

# Workload A across 3 layouts — A's orig is in matrix_Nsweep_orig_a_results.csv,
# vacuum/ta are in matrix_Nsweep_{vac,ta}_results.csv
a_orig   = load(CSV_A, "A")
a_vacuum = load(CSV_VAC, "A")
a_ta     = load(CSV_TA, "A")
a_by_db  = {"orig": a_orig, "vacuum": a_vacuum, "ta": a_ta}

DBS = [("orig", "1a"), ("vacuum", "1b"), ("ta", "1c")]
Ns = sorted(set(z_by_db["orig"]) & set(a_orig))

fig, (ax_z, ax_cmp) = plt.subplots(1, 2, figsize=(13, 4.6))

# --- Left panel: Z N-sweep across 3 layouts ---
for db, lbl in DBS:
    d = z_by_db[db]
    ys = [d[n] for n in Ns]
    ax_z.plot(Ns, ys, "-o", color=LAYOUT_COLORS[db], lw=1.7, ms=5,
              label=f"Z · layout {lbl}")
    ax_z.text(Ns[-1] * 1.07, ys[-1], f"{ys[-1]:.0f}",
              color=LAYOUT_COLORS[db], fontsize=8.5, va="center")

ax_z.set_xscale("symlog", linthresh=1)
ax_z.set_xticks([0, 1, 5, 10, 20, 46, 92])
ax_z.set_xticklabels(["0", "1", "5", "10", "20", "46", "92"])
ax_z.set_xlabel("N (interior pages prefetched)")
ax_z.set_ylabel("first-query latency (µs, median of 3 reps)")
ax_z.set_xlim(-0.3, 150)
ax_z.set_ylim(0, 470)
ax_z.legend(loc="upper right", fontsize=8.5)
ax_z.set_title("Workload Z (Zipfian, keys 1–1000) · N-sweep")

# --- Right panel: A vs Z plateau overlay, shows same shape ---
for db, lbl in DBS:
    ys_a = [a_by_db[db].get(n) for n in Ns]
    ys_z = [z_by_db[db].get(n) for n in Ns]
    ax_cmp.plot(Ns, ys_a, "--o", color=LAYOUT_COLORS[db], lw=1.5, ms=4,
                alpha=0.55, label=f"A · {lbl}")
    ax_cmp.plot(Ns, ys_z, "-s", color=LAYOUT_COLORS[db], lw=1.7, ms=5,
                label=f"Z · {lbl}")

ax_cmp.set_xscale("symlog", linthresh=1)
ax_cmp.set_xticks([0, 1, 5, 10, 20, 46, 92])
ax_cmp.set_xticklabels(["0", "1", "5", "10", "20", "46", "92"])
ax_cmp.set_xlabel("N (interior pages prefetched)")
ax_cmp.set_xlim(-0.3, 130)
ax_cmp.set_ylim(0, 470)
ax_cmp.legend(loc="upper right", fontsize=7.5, ncol=2)
ax_cmp.set_title("Robustness: A (--) vs Z (—) plateaus overlay\n"
                 "same N=5 elbow · same layout ordering · heights within 10%",
                 fontsize=10.5)

fig.suptitle("Workload Z robustness check on Workload A — hotspot LOCATION does not matter",
             fontsize=12, y=1.02)
fig.tight_layout()
save(fig, "09_zlowkey_nsweep")
