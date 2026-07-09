#!/usr/bin/env python3
"""Figure 18 — Capability matrix positioning our work against prior prefetching.

A schematic (no data) for the Introduction/Contribution: it lines up representative
prior approaches against the three capabilities an ideal serverless cold-start
prefetcher must have simultaneously. The story the grid tells at a glance:
  * every prior row misses at least one column,
  * the CRITICAL-PATH COST-ACCOUNTING column is empty for everyone but us (the
    headline gap this paper fills),
  * only our row is full across all three -- the "solving any two without the
    third" argument in Section 1.3, made visual.

Run:  python3 figures/18_capability_matrix.py
"""
from plot_utils import save
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

# columns = the three interdependent challenges (Sec 1.3) / contributions (Sec 1.4)
COLS = [
    "Structural\ntargeting\n(B+tree page-type /\naccess-freq)",
    "Critical-path\ncost accounting\n(open + deliver\ncounted in E2E)",
    "Non-intrusive\ndeployment\n(no SQLite / kernel /\nFTL source mod)",
]

# rows = representative prior work + ours, grounded in Sec 2 (Related Work)
ROWS = [
    "OS readahead\n[Smith'78, Iyer'01]",
    "libprefetch\n[VanDeBogart'09]",
    "Learned prefetch\n[Chen'21, Yi'26]",
    "sqlite_web_vfs .dbi\n[SQLite Web VFS]",
    "Our work",
]

# 2 = full, 1 = partial, 0 = none
#            targeting  cost-acct  deployable
M = [
    [0,        0,        2],   # OS readahead: blind/sequential; cheap-but-blind; app-transparent
    [2,        0,        0],   # libprefetch: app-directed targeting, but HDD-era & ~500 LOC SQLite patch
    [1,        0,        0],   # learned: ML targeting (partial); overhead ignored/backgrounded; heavy+intrusive
    [1,        0,        2],   # .dbi: page-type only (partial), no access-freq; no published cost accounting
    [2,        2,        2],   # ours: dual-lever targeting + syscall cost accounting + POSIX-only
]

# fill / glyph / ink per level
CELL = {
    2: dict(fill="#d1fae5", ink="#047857", mark="✓"),   # check
    1: dict(fill="#fef3c7", ink="#b45309", mark="◐"),   # half circle = partial
    0: dict(fill="#fee2e2", ink="#b91c1c", mark="✗"),   # cross
}


def main():
    nr, nc = len(ROWS), len(COLS)
    row_h = 1.0
    lab_w = 2.7          # left label column width (in cell units)
    col_w = 2.1
    fig_w = (lab_w + nc * col_w) * 0.9
    fig_h = (nr + 1.6) * 0.72
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, lab_w + nc * col_w)
    ax.set_ylim(-1.0, (nr + 2.4) * row_h)
    ax.axis("off")

    header_y = nr * row_h
    # --- column headers ---
    for c, title in enumerate(COLS):
        x = lab_w + c * col_w
        ax.text(x + col_w / 2, header_y + 0.75, title, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color="#111827", linespacing=1.25)

    # --- rows ---
    for r in range(nr):
        # y so that row 0 (first ROW) is at top, "Ours" (last) at bottom
        y = (nr - 1 - r) * row_h
        is_ours = (r == nr - 1)

        # row label
        lab_bg = "#eef2ff" if is_ours else "none"
        if is_ours:
            ax.add_patch(Rectangle((0, y), lab_w, row_h, facecolor=lab_bg,
                                   edgecolor="none", zorder=0))
        ax.text(0.12, y + row_h / 2, ROWS[r], ha="left", va="center",
                fontsize=9.5, fontweight=("bold" if is_ours else "normal"),
                color="#111827", linespacing=1.15)

        for c in range(nc):
            x = lab_w + c * col_w
            lvl = M[r][c]
            st = CELL[lvl]
            ax.add_patch(Rectangle((x + 0.06, y + 0.08), col_w - 0.12, row_h - 0.16,
                                   facecolor=st["fill"], edgecolor="white",
                                   linewidth=1.4, zorder=1))
            ax.text(x + col_w / 2, y + row_h / 2, st["mark"], ha="center",
                    va="center", fontsize=17, color=st["ink"], zorder=2)

    # --- highlight the "Ours" row with an outline spanning the whole grid ---
    ax.add_patch(FancyBboxPatch((0.02, 0.03), lab_w + nc * col_w - 0.04, row_h - 0.06,
                                boxstyle="round,pad=0.0,rounding_size=0.06",
                                facecolor="none", edgecolor="#4f46e5",
                                linewidth=2.0, zorder=3))

    # --- highlight the cost-accounting COLUMN as the key gap (vertical frame) ---
    gap_x = lab_w + 1 * col_w
    ax.add_patch(FancyBboxPatch((gap_x + 0.02, 0.03), col_w - 0.04, nr * row_h - 0.06,
                                boxstyle="round,pad=0.0,rounding_size=0.06",
                                facecolor="none", edgecolor="#4f46e5",
                                linewidth=2.0, zorder=3))
    ax.text(gap_x + col_w / 2, header_y + 1.9,
            "the gap this paper fills",
            ha="center", va="center", fontsize=17, style="italic", color="#4f46e5")

    # --- legend strip ---
    ly = -0.55
    items = [("✓", "#047857", "full"),
             ("◐", "#b45309", "partial"),
             ("✗", "#b91c1c", "absent")]
    lx = lab_w
    for mark, ink, txt in items:
        ax.text(lx, ly, mark, ha="left", va="center", fontsize=20, color=ink)
        ax.text(lx + 0.34, ly, txt, ha="left", va="center", fontsize=17, color="#374151")
        lx += 2.0

    fig.tight_layout()
    save(fig, "18_capability_matrix")


if __name__ == "__main__":
    main()
