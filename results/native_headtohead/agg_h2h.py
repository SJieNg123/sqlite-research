#!/usr/bin/env python3
"""Aggregate the native-YCSB same-batch head-to-head (results/native_headtohead/summary.csv).

Reproduces the FROZEN headline metric definition (results/ycsb_full/agg_stats.py Phase D):
  per-seed 2d async fq_median %delta vs same-fold baseline; mean +- 2*sd/sqrt(n) as 95% CI.
Extends it to every arm (ours + prior-work) so the ours-vs-prior-art comparison is same-batch.
lp arms are synchronous -> reported on their primary metric deliver_us (pread), not fq.
"""
import csv, statistics, sys
from collections import defaultdict

SUMMARY = sys.argv[1] if len(sys.argv) > 1 else "results/native_headtohead/summary.csv"
rows = list(csv.DictReader(open(SUMMARY)))
for r in rows:                      # tolerate a per-fold file (no 'seed' col) as seed '1'
    r.setdefault("seed", "1")
def fnum(x):
    try: return float(x)
    except: return None

# index: (seed, strategy, arm) -> row
idx = {(r["seed"], r["strategy"], r["arm"]): r for r in rows}
seeds = sorted({r["seed"] for r in rows}, key=int)

def baseline_fq(seed):
    b = idx.get((seed, "baseline", "baseline"))
    return fnum(b["fq_median"]) if b else None

def pct_series(strategy, arm="async", field="fq_median"):
    """per-seed %delta of strategy[field] vs same-seed baseline fq_median."""
    out = []
    for s in seeds:
        b = baseline_fq(s); r = idx.get((s, strategy, arm))
        if b and r and fnum(r[field]) is not None:
            out.append(100 * (fnum(r[field]) - b) / b)
    return out

def ci(xs):
    m = statistics.mean(xs); sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
    se2 = 2 * sd / len(xs) ** 0.5
    return m, sd, m - se2, m + se2

print(f"# native-YCSB head-to-head  seeds={seeds}  (n_seeds={len(seeds)})")
print(f"# baseline fq_median per seed: " +
      ", ".join(f"{s}:{baseline_fq(s):.0f}" for s in seeds))

# ---- HEADLINE: 2d async fq reduction (exact frozen definition) ----
h = pct_series("2d", "async", "fq_median")
m, sd, lo, hi = ci(h)
print("\n=== HEADLINE (re-canonicalized): 2d async fq reduction vs baseline, canonical YCSB-C ===")
print(f"per-seed: {['%+.0f' % x for x in h]}")
print(f"mean={m:+.1f}%  sd={sd:.1f}  95%CI=[{lo:+.1f}, {hi:+.1f}]  (n={len(h)})")

# ---- HEAD-TO-HEAD: fq %delta (async) for every arm, ours vs prior-work ----
ARMS = ["2d", "2e_K10", "2e_K500", "2f_slru", "2f_top14", "2f_top28",
        "layers_5", "layers_92", "learned_markov_14", "learned_markov_28"]
print("\n=== fq_median async %delta vs baseline (mean, 95% CI, n) ===")
print(f"{'strategy':20}{'mean%':>9}{'95% CI':>20}{'n':>4}   {'deliver_us(async)':>18}")
for st in ARMS:
    xs = pct_series(st, "async", "fq_median")
    if not xs: print(f"{st:20}{'(none)':>9}"); continue
    m, sd, lo, hi = ci(xs)
    dv = [fnum(idx[(s, st, 'async')]["deliver_us_median"]) for s in seeds if (s, st, 'async') in idx]
    dvm = statistics.mean([v for v in dv if v is not None]) if dv else float('nan')
    print(f"{st:20}{m:>+8.1f}%   [{lo:>+6.1f},{hi:>+6.1f}]{len(xs):>4}   {dvm:>18.1f}")

# ---- lp arms: synchronous -> deliver_us (pread) is the primary metric ----
# libprefetch's claim is a DELIVERY-ORDER effect: offset-sorted (lp_sorted) vs
# locality-destroying shuffle (lp_shuf) over byte-identical content. The headline is the
# lp_shuf / lp_sorted slowdown (NVMe random-read + lost readahead-coalescing penalty).
print("\n=== libprefetch arms: deliver_us median (PREAD, synchronous mechanism) ===")
print(f"{'strategy':14}{'deliver_us mean':>16}")
def pread_deliver_mean(st):
    vs = [fnum(idx[(s, st, 'pread')]["deliver_us_median"]) for s in seeds if (s, st, 'pread') in idx]
    vs = [v for v in vs if v is not None]
    return statistics.mean(vs) if vs else None
srt = pread_deliver_mean("lp_sorted"); shf = pread_deliver_mean("lp_shuf")
slru_p = pread_deliver_mean("2f_slru")
for st, dm in [("lp_sorted", srt), ("lp_shuf", shf), ("2f_slru", slru_p)]:
    if dm is None: print(f"{st:14}{'(none)':>16}"); continue
    print(f"{st:14}{dm:>16.1f}")
if srt and shf:
    print(f"-> libprefetch delivery-order effect: lp_shuf / lp_sorted = {shf/srt:.1f}x slower "
          f"(offset-sorted delivery wins on NVMe)")
if srt and slru_p:
    print(f"-> lp_sorted vs 2f_slru pread (same content, both offset-sorted): {slru_p/srt:.2f}x "
          f"(expect ~1.0, sanity check)")

# ---- delivery integrity (all prefetch arms should be 100%) ----
bad = [(r["seed"], r["strategy"], r["arm"], r["delivery_pct_median"]) for r in rows
       if r["strategy"] != "baseline" and fnum(r["delivery_pct_median"]) not in (100.0, None)]
print(f"\n=== delivery integrity: {'ALL 100%' if not bad else 'VIOLATIONS: ' + str(bad[:5])} ===")
print(f"=== cold integrity: max cold_pct = "
      f"{max((fnum(r['cold_pct_max']) or 0) for r in rows):.1f}% (expect 0) ===")
