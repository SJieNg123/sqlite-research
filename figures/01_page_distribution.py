"""Figure 1: Interior-page placement across the 3 layouts.

Story: 1a (orig) scatters interior pages across all 103 MB → layers_N
prefetch must do many small reads. 1b (VACUUM) packs them mid-file. 1c
(type-aware) packs all 92 interior pages into the first ~400 KB —
making layers_92 collapse from 92 syscalls to 1 contiguous read.
"""
import csv
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

LAYOUTS = [
    ("1a (orig)",       ROOT / "pipeline/preparation/layout_rewriter/runs/classify_before.csv",  "#888888"),
    ("1b (VACUUM)",     ROOT / "pipeline/preparation/layout_rewriter/runs/classify_vacuum.csv",  "#1f77b4"),
    ("1c (type-aware)", ROOT / "pipeline/preparation/layout_rewriter/runs/classify_after.csv",   "#d62728"),
]
DB_SIZE_MB = 103

def load_interior(p):
    out = []
    with open(p) as f:
        for r in csv.DictReader(f):
            if r["page_type"].startswith("interior"):
                out.append(int(r["file_offset"]) / (1024*1024))
    return out

fig, axes = plt.subplots(3, 1, figsize=(7, 4.8), sharex=True)
for ax, (name, path, color) in zip(axes, LAYOUTS):
    pos = load_interior(path)
    ax.eventplot(pos, lineoffsets=0, linelengths=0.8, linewidths=0.8, colors=color)
    ax.set_yticks([])
    ax.set_xlim(-1, DB_SIZE_MB + 1)
    ax.set_ylim(-0.6, 0.6)

    n = len(pos)
    span = max(pos) - min(pos) if pos else 0
    ax.set_title(
        f"{name} · {n} interior pages · "
        f"span = {span:.1f} MB ({span/DB_SIZE_MB*100:.0f}% of file)",
        loc="left", fontsize=10, color=color, fontweight="bold", pad=4)
    ax.grid(False)

axes[-1].set_xlabel("file offset (MB) · DB size = 103 MB")
fig.tight_layout()
save(fig, "01_page_distribution")
