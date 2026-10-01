#!/usr/bin/env python3
"""S1 three-lever ablation -> markdown decomposition table.

Reads the cross-seed uncertainty CSV(s) produced by stats_uncertainty.py over the
ablation tree(s) and renders, per (layout, workload), one row per arm with the lever
it isolates, the prefetch footprint (pages, deterministic), and the first-query /
e2e_warm effect vs same-seed baseline (mean Δ% + bootstrap 95% CI + verdict).

  2d            page-type (interior)        lever (ii)
  leaf_rand_K   random equal-count leaves   null control for (iii)
  leaf_freq_K   access-frequency hot leaves lever (iii)
  2e_K          interior u hot leaves       combined (ii)+(iii)

Usage:
  tools/ablation_table.py                                  # core (K10) -> stdout + results/ablation/ablation_table.md
  tools/ablation_table.py --unc results/ablation/uncertainty.csv \
                          --unc-k500 results/ablation_k500/uncertainty_k500.csv
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path("/home/u03/sqlite-research-project-sharing")
sys.path.insert(0, str(ROOT))

LEVER = {
    "2d":            "(ii) page-type · interior-only",
    "leaf_rand_K10": "control · random leaves (= freq count)",
    "leaf_freq_K10": "(iii) access-frequency · hot leaves",
    "2e_K10":        "(ii)+(iii) combined",
    "leaf_rand_K500":"control · random leaves (= freq count)",
    "leaf_freq_K500":"(iii) access-frequency · hot leaves",
    "2e_K500":       "(ii)+(iii) combined",
}
CORE_ORDER  = ["2d", "leaf_rand_K10", "leaf_freq_K10", "2e_K10"]
K500_ORDER  = ["leaf_rand_K500", "leaf_freq_K500", "2e_K500"]


def hotset_sizes(layout, k_for_workload):
    """Deterministic prefetch footprint (pages) per (workload, strategy), via the runner."""
    import run_experiment as R
    R.SEED = None
    cl = R.load_classify(layout)
    out = {}
    for w in ("A", "B", "C"):
        for s in CORE_ORDER + (K500_ORDER if w == "A" else []):
            try:
                out[(w, s)] = len(R.select_pages(R.resolve_strategy(s), w, layout, cl))
            except SystemExit:
                out[(w, s)] = None
    return out


def load_unc(path):
    """(workload, db, strategy, arm, metric) -> row."""
    idx = {}
    if not Path(path).exists():
        return idx
    for r in csv.DictReader(open(path)):
        idx[(r["workload"], r["db"], r["strategy"], r["arm"], r["metric"])] = r
    return idx


def cell(idx, w, ly, s, metric, arm="async"):
    r = idx.get((w, ly, s, arm, metric))
    if not r:
        return "—"
    ci = "—" if r["ci_lo"] in ("", "None", None) else f"[{float(r['ci_lo']):+.0f},{float(r['ci_hi']):+.0f}]"
    return f"{float(r['mean_pct']):+.0f}% {ci} ({r['verdict']})"


def render(idx, layout, sizes, arm="async"):
    out = [f"#### layout {layout} — async arm (cross-seed mean Δ% vs baseline, 95% CI)", "",
           "| workload | arm | lever isolated | pages | first-query Δ% | e2e_warm Δ% |",
           "|---|---|---|---:|---|---|"]
    for w in ("A", "B", "C"):
        order = CORE_ORDER + (K500_ORDER if w == "A" else [])
        for s in order:
            n = sizes.get((w, s))
            out.append(f"| {w} | `{s}` | {LEVER.get(s, '')} | {('' if n is None else n)} | "
                       f"{cell(idx, w, layout, s, 'first_query_us', arm)} | "
                       f"{cell(idx, w, layout, s, 'e2e_warm_us', arm)} |")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unc", default=str(ROOT / "results/ablation/uncertainty.csv"))
    ap.add_argument("--unc-k500", default=str(ROOT / "results/ablation_k500/uncertainty_k500.csv"))
    ap.add_argument("--out", default=str(ROOT / "results/ablation/ablation_table.md"))
    args = ap.parse_args()

    idx = load_unc(args.unc)
    idx.update(load_unc(args.unc_k500))   # fold A's K500 rows in
    if not idx:
        raise SystemExit(f"no uncertainty rows in {args.unc} (run stats first)")

    parts = ["# S1 three-lever ablation — lever decomposition\n",
             "Effect = strategy median vs **same-seed baseline** median, mean over seeds, "
             "bootstrap 95% CI. `leaf_freq` vs `leaf_rand` (same page-type, same count) "
             "isolates the access-frequency signal; `2d` isolates page-type; orig-vs-ta the "
             "layout-clustering lever.\n"]
    for ly in ("orig", "ta"):
        parts.append(render(idx, ly, hotset_sizes(ly, None)))
    text = "\n".join(parts) + "\n"
    Path(args.out).write_text(text)
    print(text)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
