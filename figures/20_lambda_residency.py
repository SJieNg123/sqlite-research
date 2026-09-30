"""Figure 20: warm container, cold data on AWS Lambda (internal figure, not in the paper).

Batch coldprobe-b2, results/lambda/b2/, 2026-09-29/30: 36 functions, 13.8 h,
8,930 invocations after the smoke-test rows are dropped. See that README for the
method and for why the 100 us hit threshold holds at every memory size.

Three panels, one per finding:
  (a) idle time decides whether the execution environment survives: at 1 and 5
      minutes almost every invocation reuses a live environment, from 10 minutes
      up every one is a cold start, at every memory size
  (b) memory decides how much stays cached inside a live environment: data the
      function keeps using stays cached everywhere, but data read once and left
      alone is only about 70% cached at 128 MB, against 100% from 256 MB up
  (c) one cache miss costs about 19 ms at 128 MB against under 1 ms elsewhere,
      because squashfs decompression is CPU-bound and Lambda allocates CPU by
      memory

Styled with pub_style.py, the scientific-figure-making (figures4papers) house style.
"""
import csv, json, math, statistics as st
from datetime import datetime
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

from pub_style import PALETTE, apply
apply()

CSV = ROOT / "results/lambda/b2/residency_20260930T021827Z.csv"
BATCH_START = datetime(2026, 9, 29, 12, 36)   # the full deploy; earlier rows are the smoke test
MEMS = [128, 256, 512, 1024]
IDLES = [1, 5, 10, 15, 30, 60]
HIT_US = 100
# Memory is an ordered quantity, so it gets one light-to-dark ramp of the palette's
# blue, used identically in every panel.
MEM_COLOR = {128: "#C6D7EC", 256: "#8FB0D8", 512: PALETTE["blue_secondary"], 1024: PALETTE["blue_main"]}

T = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def load():
    """Rows from the batch start on. The two smoke-test cells begin at the first
    cold start after the full deploy, which gave them a fresh environment."""
    raw = list(csv.DictReader(open(CSV)))
    rows = []
    for fn in sorted({r["fn"] for r in raw}):
        rs = sorted((r for r in raw if r["fn"] == fn), key=lambda r: (T(r["ts"]), int(r["invocation"])))
        rs = [r for r in rs if T(r["ts"]) >= BATCH_START]
        while rs and rs[0]["cold_start"] != "True":
            rs.pop(0)
        rows += rs
    for r in rows:
        r["m"], r["i"] = int(r["mem_mb"]), int(r["idle_target_min"])
        r["cold"], r["lat"] = r["cold_start"] == "True", json.loads(r["lat_us"])
    return rows


def wilson(k, n, z=1.96):
    """95% Wilson interval for a proportion, in percent."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


rows = load()
fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(20, 6.2),
                                       gridspec_kw={"width_ratios": [1.6, 1.1, 1]})

# ---- (a) cold-start share by idle interval (reread functions) ---------------
x = np.arange(len(IDLES)); w = 0.2
for k, m in enumerate(MEMS):
    share = []
    for i in IDLES:
        rs = [r for r in rows if r["mode"] == "reread" and r["m"] == m and r["i"] == i]
        share.append(100 * sum(r["cold"] for r in rs) / len(rs))
    ax_a.bar(x + (k - 1.5) * w, share, w, color=MEM_COLOR[m], edgecolor="black",
             linewidth=1, label=f"{m} MB")
ax_a.text(0.5, 60, "reused\nenvironments", ha="center", va="center", fontsize=12.5)
ax_a.text(3.5, 108, "every invocation a cold start", ha="center", va="bottom", fontsize=12.5)
ax_a.set_xticks(x); ax_a.set_xticklabels([f"{i} min" for i in IDLES]); ax_a.tick_params(axis="x", length=0)
ax_a.set_xlabel("Idle interval between invocations")
ax_a.set_ylabel("Invocations that were cold starts (%)")
ax_a.set_ylim(0, 128); ax_a.set_yticks([0, 25, 50, 75, 100])
ax_a.set_title("(a) Idle time decides whether the environment survives", loc="left")
ax_a.legend(title="function memory", loc="upper left", fontsize=12, title_fontsize=12)

# ---- (b) residency inside a live environment, by probe -----------------------
xm = np.arange(len(MEMS)); wb = 0.36
series = [("reread", "data in use (re-read each call)", PALETTE["neutral"]),
          ("once", "data read once, then left alone", None)]
for k, (mode, label, color) in enumerate(series):
    vals, lo, hi = [], [], []
    for m in MEMS:
        lat = [v for r in rows if r["mode"] == mode and not r["cold"] and r["m"] == m and r["i"] in (1, 5)
               for v in r["lat"]]
        hits = sum(v < HIT_US for v in lat)
        a, b = wilson(hits, len(lat))
        vals.append(100 * hits / len(lat)); lo.append(vals[-1] - a); hi.append(b - vals[-1])
    xs = xm + (k - 0.5) * wb
    ax_b.bar(xs, vals, wb, color=color or [MEM_COLOR[m] for m in MEMS], edgecolor="black",
             linewidth=1, label=label, yerr=[lo, hi] if mode == "once" else None,
             error_kw=dict(ecolor=PALETTE["ink"], capsize=4, lw=1.5))
    if mode == "once":
        for xi, v in zip(xs, vals):
            ax_b.text(xi, v + (hi[0] if xi == xs[0] else 1) + 2, f"{v:.0f}%", ha="center",
                      va="bottom", fontsize=12, fontweight="bold")
ax_b.annotate("~30% of the DB\ncold in a live\n128 MB environment", xy=(xm[0] + wb / 2, 80),
              xytext=(-0.5, 146), fontsize=11.5, color=PALETTE["red_strong"], fontweight="bold",
              va="top", arrowprops=dict(arrowstyle="->", color=PALETTE["red_strong"], lw=1.5))
ax_b.set_xticks(xm); ax_b.set_xticklabels([f"{m} MB" for m in MEMS]); ax_b.tick_params(axis="x", length=0)
ax_b.set_xlabel("Function memory")
ax_b.set_ylabel("Pages still cached (%)")
ax_b.set_ylim(0, 150); ax_b.set_yticks([0, 25, 50, 75, 100])
ax_b.set_title("(b) Memory decides what stays cached", loc="left")
ax_b.legend(loc="upper right", fontsize=11.5)

# ---- (c) cost of one cache miss ----------------------------------------------
miss = [st.median(v for r in rows if r["cold"] and r["m"] == m for v in r["lat"]) / 1000 for m in MEMS]
ax_c.bar(xm, miss, 0.6, color=[MEM_COLOR[m] for m in MEMS], edgecolor="black", linewidth=1)
for xi, v in zip(xm, miss):
    ax_c.text(xi, v * 1.12, f"{v:.1f} ms" if v >= 10 else f"{v:.2f} ms", ha="center",
              va="bottom", fontsize=12, fontweight="bold")
ax_c.set_yscale("log"); ax_c.set_ylim(0.3, 80)
ax_c.set_xticks(xm); ax_c.set_xticklabels([f"{m} MB" for m in MEMS]); ax_c.tick_params(axis="x", length=0)
ax_c.set_xlabel("Function memory")
ax_c.set_ylabel("One cache miss, median (ms, log)")
ax_c.set_title("(c) What one miss costs", loc="left")

fig.tight_layout(pad=1.5, rect=(0, 0.045, 1, 1))
fig.text(0.995, 0.005, f"AWS Lambda, batch coldprobe-b2, 13.8 h, {len(rows):,} invocations",
         ha="right", va="bottom", fontsize=12, color=PALETTE["neutral_dark"])
save(fig, "20_lambda_residency")
