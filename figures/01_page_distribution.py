"""Figure 1: Interior-page placement across the 3 layouts.

Story: 1a (orig) scatters interior pages across all ~103 MiB → layers_N
prefetch must do many small reads. 1b (VACUUM) packs them mid-file. 1c
(type-aware) packs all 92 interior pages into the first ~400 KB —
making layers_92 collapse from 92 syscalls to 1 contiguous read.

Styled with pub_style.py, the scientific-figure-making (figures4papers) house style.
"""
import csv
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np
from pub_style import PALETTE, apply
apply()

LAYOUTS = [
    ("Default",       ROOT / "pipeline/preparation/layout_rewriter/runs/classify_before.csv",  PALETTE["neutral_dark"]),
    ("Vacuum",     ROOT / "pipeline/preparation/layout_rewriter/runs/classify_vacuum.csv",  PALETTE["blue_main"]),
    ("Clustered", ROOT / "pipeline/preparation/layout_rewriter/runs/classify_after.csv",   PALETTE["red_strong"]),
]
DB_SIZE_MIB = 103  # 102.9 MiB (107,851,776 bytes) rounded for axis scaling

def load_interior(p):
    out = []
    with open(p) as f:
        for r in csv.DictReader(f):
            if r["page_type"].startswith("interior"):
                out.append(int(r["file_offset"]) / (1024*1024))
    return out

fig, axes = plt.subplots(3, 1, figsize=(8.5, 5.4), sharex=True)
for ax, (name, path, color) in zip(axes, LAYOUTS):
    pos = load_interior(path)
    ax.eventplot(pos, lineoffsets=0, linelengths=0.8, linewidths=1.2, colors=color)
    ax.set_yticks([])
    ax.set_xlim(-1, DB_SIZE_MIB + 1)
    ax.set_ylim(-0.6, 0.6)

    n = len(pos)
    span = max(pos) - min(pos) if pos else 0
    ax.set_title(
        f"{name} · {n} interior pages · "
        f"span = {span:.1f} MiB ({span/DB_SIZE_MIB*100:.0f}% of file)",
        loc="left", fontsize=13, color=color, fontweight="bold", pad=4)
    ax.grid(False)

axes[-1].set_xlabel("file offset (MiB) · DB size ≈ 103 MiB", fontsize=15)
fig.tight_layout()
save(fig, "01_page_distribution")
