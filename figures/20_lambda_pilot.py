"""Lambda pilot: warm container, cold data (internal figure, not in the paper).

Pilot run, results/lambda/pilot/, 2026-09-26/27, 14 hours, 4,509 invocations
after the smoke-test rows are dropped. The pilot is not citable: its reread probe
keeps its own samples hot, so it cannot see data read once and then left alone.
Batch coldprobe-b2 is the citable run. The figure says so on its face.

Three panels, one per pilot finding:
  (a) idle time decides whether the execution environment survives: at 1 and 5
      minutes almost every invocation reuses a live environment, from 15 minutes
      up every one is a cold start, at every memory size
  (b) memory decides how much of the database the page cache can hold: from
      256 MB up the whole database stays cached, at 128 MB about 50 MB of it does
      not fit
  (c) a cold start's read of the database costs CPU, and Lambda allocates CPU by
      memory: the time halves as memory doubles

Styled with pub_style.py, the scientific-figure-making (figures4papers) house style.
"""
import csv, statistics as st
from datetime import datetime
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

from pub_style import PALETTE, apply
apply()

CSV = ROOT / "results/lambda/pilot/residency_20260927T054002Z.csv"
BATCH_START = datetime(2026, 9, 26, 15, 24)   # rows before this are the smoke test
MEMS = [128, 256, 512, 1024]
IDLES = [1, 5, 15, 30, 60]
# Memory is an ordered quantity, so it gets one light-to-dark ramp of the palette's
# blue, used identically in every panel.
MEM_COLOR = {128: "#C6D7EC", 256: "#8FB0D8", 512: PALETTE["blue_secondary"], 1024: PALETTE["blue_main"]}
DB_MB = 103

T = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
rows = [r for r in csv.DictReader(open(CSV)) if T(r["ts"]) >= BATCH_START]
cell = lambda m, i: [r for r in rows if int(r["mem_mb"]) == m and int(r["idle_target_min"]) == i]

fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(19, 6.2),
                                       gridspec_kw={"width_ratios": [1.5, 1, 1]})

# ---- (a) cold-start share by idle interval ---------------------------------
x = np.arange(len(IDLES)); w = 0.2
for k, m in enumerate(MEMS):
    share = [100 * sum(r["cold_start"] == "True" for r in cell(m, i)) / len(cell(m, i)) for i in IDLES]
    ax_a.bar(x + (k - 1.5) * w, share, w, color=MEM_COLOR[m], edgecolor="black",
             linewidth=1, label=f"{m} MB")
warm = [float(r["resident_pct"]) for r in rows if r["cold_start"] == "False"]
ax_a.text(0.5, 60, f"reused environments:\n{st.fmean(warm):.1f}% of data resident",
          ha="center", va="center", fontsize=12.5)
ax_a.text(3, 108, "every invocation\na cold start", ha="center", va="bottom", fontsize=12.5)
ax_a.set_xticks(x); ax_a.set_xticklabels([f"{i} min" for i in IDLES])
ax_a.tick_params(axis="x", length=0)
ax_a.set_xlabel("Idle interval between invocations")
ax_a.set_ylabel("Invocations that were cold starts (%)")
ax_a.set_ylim(0, 128); ax_a.set_yticks([0, 25, 50, 75, 100])
ax_a.set_title("(a) Idle time decides whether the environment survives", fontsize=14.5, loc="left")
ax_a.legend(title="function memory", loc="upper left", fontsize=12, title_fontsize=12)

# ---- (b) page cache held in a live environment -----------------------------
xm = np.arange(len(MEMS)); wb = 0.36
before = [st.median(int(r["Cached_kb"]) / 1024 for r in rows if int(r["mem_mb"]) == m
                    and r["cold_start"] == "True") for m in MEMS]
steady = [st.median(int(r["Cached_kb"]) / 1024 for r in rows if int(r["mem_mb"]) == m
                    and int(r["invocation"]) >= 20) for m in MEMS]
ax_b.bar(xm - wb / 2, before, wb, color=PALETTE["neutral"], edgecolor="black", linewidth=1,
         label="before reading the DB")
ax_b.bar(xm + wb / 2, steady, wb, color=[MEM_COLOR[m] for m in MEMS], edgecolor="black",
         linewidth=1, label="live environment")
full = st.median(steady[1:])
ax_b.axhline(full, color=PALETTE["ink"], lw=1.5, ls="--")
ax_b.text(-0.8, full + 4, "whole DB cached", fontsize=12, ha="left", va="bottom")
for xi, v in zip(xm, steady):
    ax_b.text(xi + wb / 2, v + 3, f"{v:.0f}", ha="center", va="bottom", fontsize=12, fontweight="bold")
short = full - steady[0]
ax_b.annotate("", xy=(0.5, steady[0]), xytext=(0.5, full - 1),   # in the gap beside the 128 MB bar
              arrowprops=dict(arrowstyle="<->", color=PALETTE["red_strong"], lw=2))
ax_b.text(0.42, 176, f"{short:.0f} MB short\n(~half the DB)", fontsize=11.5,
          color=PALETTE["red_strong"], fontweight="bold", ha="right", va="top")
ax_b.set_xticks(xm); ax_b.set_xticklabels([f"{m} MB" for m in MEMS]); ax_b.tick_params(axis="x", length=0)
ax_b.set_xlabel("Function memory")
ax_b.set_ylabel("Page cache in use (MB)")
ax_b.set_ylim(0, 230)
ax_b.set_xlim(-0.85, 3.55)   # room left of the arrow for its note
ax_b.set_title("(b) Memory decides how much stays cached", fontsize=14.5, loc="left")
ax_b.legend(loc="upper right", fontsize=12)

# ---- (c) cost of reading the DB at a cold start -----------------------------
read_s = [st.median(float(r["warm_read_s"]) for r in rows if int(r["mem_mb"]) == m
                    and r["cold_start"] == "True" and r["warm_read_s"]) for m in MEMS]
ax_c.bar(xm, read_s, 0.6, color=[MEM_COLOR[m] for m in MEMS], edgecolor="black", linewidth=1)
for xi, v in zip(xm, read_s):
    ax_c.text(xi, v + 0.15, f"{v:.2f} s", ha="center", va="bottom", fontsize=12, fontweight="bold")
ax_c.set_xticks(xm); ax_c.set_xticklabels([f"{m} MB" for m in MEMS]); ax_c.tick_params(axis="x", length=0)
ax_c.set_xlabel("Function memory")
ax_c.set_ylabel("Reading the 103 MB DB at cold start (s)")
ax_c.set_ylim(0, 10)
ax_c.set_title("(c) Cold-start read cost", fontsize=14.5, loc="left")

# The pilot caveat rides as a footer rather than a suptitle, which tight_layout
# pads with a wide empty band.
fig.tight_layout(pad=1.5, rect=(0, 0.045, 1, 1))
fig.text(0.995, 0.005, "AWS Lambda pilot, 14 h, 4,509 invocations  ·  pilot run, not citable",
         ha="right", va="bottom", fontsize=12, color=PALETTE["neutral_dark"])
save(fig, "20_lambda_pilot")
