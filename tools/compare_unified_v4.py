#!/usr/bin/env python3
"""Compare the paper's four main tables against the unified_v4 single batch.

tab:e2e-ac, tab:ablation, tab:competitive and tab:seeds currently draw on five
batches and two code versions (see results/RESULT_PROVENANCE.md 4.2/4.8).
results/unified_v4 re-measures every cell they print in one contiguous window
with one harness version. This script prints, per cell, the value main.tex
displays today, the batch it came from, and what unified_v4 now measures, and
flags sign flips and verdict changes.

Standard library only.

Usage:
  python3 tools/compare_unified_v4.py [--batch results/unified_v4]
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CACHE = {}


def load(path):
    p = path if isinstance(path, Path) else ROOT / path
    key = str(p)
    if key not in _CACHE:
        if not p.exists():
            sys.exit(f"FATAL: missing source {p}")
        _CACHE[key] = list(csv.DictReader(open(p)))
    return _CACHE[key]


def single(summary, wl, strat, col, arm=None):
    """One cell from a matrix summary.csv (db=orig)."""
    arm = arm or ("baseline" if strat == "baseline" else "async")
    for r in load(summary):
        if (r["workload"] == wl and r["strategy"] == strat
                and r["arm"] == arm and r.get("db", "orig") == "orig"):
            return float(r[col])
    return None


def cross(unc, wl, strat, metric):
    """One cross-seed row: (mean, ci_lo, ci_hi, sign, verdict)."""
    for r in load(unc):
        if (r["workload"] == wl and r["strategy"] == strat
                and r["arm"] == "async" and r["metric"] == metric
                and r.get("db", "orig") == "orig"):
            return (float(r["mean_pct"]), float(r["ci_lo"]), float(r["ci_hi"]),
                    r["sign_consistency"], r["verdict"])
    return None


def pct(new, base):
    return 100.0 * (new - base) / base


def flag(old, new):
    if old is None or new is None:
        return ""
    if (old < 0) != (new < 0):
        return "  <<< SIGN FLIP"
    d = abs(new - old)
    if d >= 10:
        return f"  <<< moved {d:.0f} pt"
    if d >= 5:
        return f"  <  moved {d:.0f} pt"
    return ""


# ---------------------------------------------------------------- printed cells
# (workload, strategy, printed e2e_ext us, printed e2e_warm us, pct_ext, pct_warm)
E2E_AC = [
    ("A", "baseline",  503,  503,  None,  None),
    ("A", "layers_5",  617,  435,   23,   -13),
    ("A", "2d",        620,  439,   23,   -13),
    ("A", "2f_slru",  7319, 7140, 1355,  1319),
    ("C", "baseline", 1072, 1072,  None,  None),
    ("C", "layers_5", 1286, 1107,   20,     3),
    ("C", "2d",        907,  729,  -15,   -32),
    ("C", "2f_slru",  1074,  897,    0,   -16),
]
# (strategy, printed fq mean, lo, hi, printed e2e_warm mean, printed verdict word)
ABLATION = [
    ("2d",            -43, -46, -41, -36, "robust"),
    ("leaf_rand_K10",  -1,  -2,   1,   7, "worse"),
    ("leaf_freq_K10", -11, -22,   0,  -3, "tie"),
    ("2e_K10",        -63, -75, -51, -55, "bimodal"),
]
# (strategy, {workload: (mean, lo, hi)}, current source per workload)
COMPETITIVE = [
    ("2e_K10",    {"A": (-38, -53, -25), "B": (-24, -31, -12), "C": (-55, -67, -42)},
                  {"A": "competitive PRE-FIX", "B": "competitive PRE-FIX", "C": "ablation_comp_v2"}),
    ("2f_top14",  {"A": (-33, -43, -24), "B": (-27, -34, -16), "C": (-55, -67, -43)},
                  {"A": "competitive PRE-FIX", "B": "competitive PRE-FIX", "C": "ablation_comp_v2"}),
    ("2f_top500", {"A": (81, 34, 151),   "B": (44, 28, 60),    "C": (-13, -17, -8)},
                  {"A": "competitive PRE-FIX", "B": "competitive PRE-FIX", "C": "competitive PRE-FIX"}),
    ("2f_slru",   {"A": (762, 674, 899), "B": (730, 644, 848), "C": (-7, -12, -2)},
                  {"A": "competitive PRE-FIX", "B": "competitive PRE-FIX", "C": "ablation_comp_v2"}),
]
# (workload, strategy, printed single, printed cross mean, lo, hi, sign, cross source)
SEEDS = [
    ("C", "2e_K10",   -76, -55, -67, -43, "",      "tiebreak_fix"),
    ("C", "2d",       -32, -36, -39, -33, "10/10", "stats PRE-FIX"),
    ("A", "2e_K10",    -9, -36, -50, -23, "10/10", "stats PRE-FIX"),
    ("A", "2d",       -13, -25, -29, -20, "10/10", "stats PRE-FIX"),
    ("B", "2d",       -32, -25, -32, -16, "9/10",  "stats PRE-FIX"),
    ("B", "2e_K10",   -31, -25, -32, -15, "9/10",  "tiebreak_fix"),
    ("A", "layers_5", -13,  -5, -16,   4, "6/10",  "stats PRE-FIX"),
    ("B", "layers_5", -34,  -1, -12,   7, "8/10",  "stats PRE-FIX"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="results/unified_v4")
    a = ap.parse_args()
    batch = ROOT / a.batch
    summ = batch / "seed01" / "summary.csv"
    unc = batch / "uncertainty.csv"

    print(f"# {a.batch} vs the four tables in paper/main.tex\n")

    print("## tab:e2e-ac  (single instantiation, absolute us, async; was unified_v3 2026-09-14)\n")
    print(f"{'cell':16} {'e2e_ext':>22} {'e2e_warm':>22}")
    for wl, s, pe, pw, qe, qw in E2E_AC:
        ne = single(summ, wl, s, "e2e_median")
        nw = single(summ, wl, s, "e2e_warm_median")
        be = single(summ, wl, "baseline", "e2e_median")
        bw = single(summ, wl, "baseline", "e2e_warm_median")
        se = f"{pe} -> {ne:.0f}" if ne is not None else f"{pe} -> MISSING"
        sw = f"{pw} -> {nw:.0f}" if nw is not None else f"{pw} -> MISSING"
        extra = ""
        if qe is not None and ne is not None:
            extra = (f"   ({qe:+d}% -> {pct(ne, be):+.0f}%)"
                     f"  ({qw:+d}% -> {pct(nw, bw):+.0f}%)")
        print(f"{wl+' '+s:16} {se:>22} {sw:>22}{extra}")

    print("\n## tab:ablation  (Tail-Mixed cross-seed; was ablation_comp_v2 2026-07-11, post-fix)\n")
    print(f"{'arm':16} {'first-query d%':>34} {'e2e_warm d%':>30}")
    for s, pm, plo, phi, pw, pv in ABLATION:
        f = cross(unc, "C", s, "first_query_us")
        e = cross(unc, "C", s, "e2e_warm_us")
        fs = (f"{pm}% [{plo},{phi}] -> {f[0]:.0f}% [{f[1]:.0f},{f[2]:.0f}]"
              if f else f"{pm}% -> MISSING")
        es = (f"{pw}% ({pv}) -> {e[0]:.0f}% ({e[4]})" if e else f"{pw}% -> MISSING")
        print(f"{s:16} {fs:>34} {es:>30}{flag(pw, e[0] if e else None)}")

    print("\n## tab:competitive  (cross-seed e2e_warm; was competitive PRE-FIX + ablation_comp_v2)\n")
    for s, printed, srcs in COMPETITIVE:
        print(f"  {s}")
        for wl in ("A", "B", "C"):
            pm, plo, phi = printed[wl]
            n = cross(unc, wl, s, "e2e_warm_us")
            ns = (f"{n[0]:+.0f}% [{n[1]:+.0f},{n[2]:+.0f}] {n[4]}" if n else "MISSING")
            print(f"    {wl}  {pm:+4d}% [{plo:+d},{phi:+d}]  ({srcs[wl]:19})"
                  f"  ->  {ns}{flag(pm, n[0] if n else None)}")

    print("\n## tab:seeds  (single = seed01 of this batch; cross-seed = this batch)\n")
    print(f"{'cell':18} {'single':>18} {'cross-seed':>40}")
    for wl, s, ps, pm, plo, phi, psign, src in SEEDS:
        nv = single(summ, wl, s, "e2e_warm_median")
        bw = single(summ, wl, "baseline", "e2e_warm_median")
        ns = f"{ps}% -> {pct(nv, bw):+.0f}%" if nv is not None else f"{ps}% -> MISSING"
        c = cross(unc, wl, s, "e2e_warm_us")
        cs = (f"{pm}% [{plo},{phi}] {psign} ({src}) -> {c[0]:+.0f}% "
              f"[{c[1]:+.0f},{c[2]:+.0f}] {c[3]} {c[4]}" if c else f"{pm}% -> MISSING")
        print(f"{wl+' '+s:18} {ns:>18} {cs:>40}")

    print("\n## machine state")
    env = batch / "seed01" / "env.txt"
    if env.exists():
        print("  seed01: " + env.read_text().strip())
    old = ROOT / "results/unified_v3/matrix/env.txt"
    if old.exists():
        print("  v3    : " + old.read_text().strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
