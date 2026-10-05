#!/usr/bin/env python3
"""Matched-budget comparison of Skel+10 and Dump-N, as pre-registered in
results/matched_budget/PREREG.md (margin and decision rule fixed there first).

Per instance s: d_s = 100 * (e2e(Skel+10)_s - e2e(Dump-N)_s) / baseline_s, from the per-seed
medians in <batch>/seedNN/main/summary.csv. Mean over instances with the paper's bootstrap
CI (tools/stats_uncertainty.bootstrap_ci). Primary metric e2e_warm_median, secondary
e2e_median; arms async and async_win.

Usage: tools/matched_budget.py results/unified_v6
Writes results/matched_budget/<batch name>.csv and .md.
"""
import csv
import importlib.util
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARGIN = 5.0
PAIRS = {"A": ("2e_K10", "2f_top28", 28), "B": ("2e_K10", "2f_top28", 28),
         "C": ("2e_K10", "2f_top14", 14)}
ARMS = ("async", "async_win")
METRICS = (("e2e_warm_median", "primary"), ("e2e_median", "secondary"))
NAME = {"A": "Scattered-Zipf-100K", "B": "Uniform-100K", "C": "Tail-Mixed",
        "async": "per-page", "async_win": "window-chunked"}

_spec = importlib.util.spec_from_file_location("su", ROOT / "tools/stats_uncertainty.py")
su = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(su)


def verdict(lo, hi):
    if -MARGIN <= lo and hi <= MARGIN:
        return f"within ±{MARGIN:g}% of baseline"
    if hi < -MARGIN:
        return f"Skel+10 faster by more than {MARGIN:g}%"
    if lo > MARGIN:
        return f"Dump-N faster by more than {MARGIN:g}%"
    return f"cannot distinguish within ±{MARGIN:g}%"


def check_sizes(seed_dir, w, ours, theirs, n):
    """Assert both hotsets hold n pages, when the untracked work/ directory exists."""
    work = seed_dir / "main" / "work"
    if not work.is_dir():
        return False
    for s in (ours, theirs):
        with open(work / f"hotset_{w}_orig_{s}.csv") as f:
            pages = sum(1 for _ in f) - 1
        if pages != n:
            raise SystemExit(f"{seed_dir.name} {w} {s}: {pages} pages, expected {n}")
    return True


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    batch = Path(sys.argv[1])
    seeds = sorted(p for p in batch.glob("seed[0-9][0-9]") if p.is_dir())
    rows = {}
    checked = 0
    for sd in seeds:
        with open(sd / "main" / "summary.csv") as f:
            for r in csv.DictReader(f):
                if r["db"] == "orig":
                    rows[(sd.name, r["workload"], r["strategy"], r["arm"])] = r
        for w, (ours, theirs, n) in PAIRS.items():
            checked += check_sizes(sd, w, ours, theirs, n)

    out = []
    for metric, role in METRICS:
        for w, (ours, theirs, n) in PAIRS.items():
            for arm in ARMS:
                d = []
                for sd in seeds:
                    base = float(rows[(sd.name, w, "baseline", "baseline")]["fq_median"])
                    a = float(rows[(sd.name, w, ours, arm)][metric])
                    b = float(rows[(sd.name, w, theirs, arm)][metric])
                    d.append(100.0 * (a - b) / base)
                lo, hi = su.bootstrap_ci(d)
                out.append({"metric": metric, "role": role, "workload": w, "arm": arm,
                            "pages": n, "matched": theirs, "n_seeds": len(d),
                            "mean_d": round(statistics.mean(d), 2),
                            "ci_lo": round(lo, 2), "ci_hi": round(hi, 2),
                            "skel_faster": sum(x < 0 for x in d),
                            "verdict": verdict(lo, hi),
                            "per_seed": ";".join(f"{x:.1f}" for x in d)})

    dest = ROOT / "results/matched_budget"
    dest.mkdir(parents=True, exist_ok=True)
    with open(dest / f"{batch.name}.csv", "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=list(out[0]))
        w_.writeheader()
        w_.writerows(out)
    md = [f"# Matched budget, {batch.name}",
          f"\nRule: results/matched_budget/PREREG.md. d = Skel+10 minus Dump-N, in % of the "
          f"same-seed baseline; negative = Skel+10 faster. Mean over {len(seeds)} instances, "
          f"95% bootstrap CI. Page counts asserted on {checked} of {len(seeds) * len(PAIRS)} "
          f"seed-workload pairs.\n"]
    for metric, role in METRICS:
        md += [f"\n## {metric} ({role})\n", "| workload | arm | pages | mean d | 95% CI | Skel+10 faster | verdict |",
               "|---|---|---|---:|---|---:|---|"]
        md += [f"| {NAME[r['workload']]} | {NAME[r['arm']]} | {r['pages']} | {r['mean_d']:+.1f} | "
               f"[{r['ci_lo']:+.1f}, {r['ci_hi']:+.1f}] | {r['skel_faster']}/{r['n_seeds']} | {r['verdict']} |"
               for r in out if r["metric"] == metric]
    (dest / f"{batch.name}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
