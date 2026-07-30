# learned_markov — full 10-fold LOSO latency (run-completeness closure)

**Batch:** `results/learned_10fold/` · 2026-07-30 · one machine state (all 10 folds
contiguous, so relative %s are horizontally comparable per the machine-state rule).
**Protocol:** leave-one-seed-out. For each test seed N∈1..10, learned_markov is trained
on the 9-seed complement and measured on held-out seed N's trace. Reference arms
(`2f_top14`, `2f_top28`, `2e_K10`, no-prefetch baseline) measured in the *same* fold for
paired comparison. n=10 reps/cell, async + pread arms, A/B/C × orig.
**Integrity:** all 300 prefetch cells delivery=100 %, all 330 cells cold_pct=0 (genuinely cold).

## Why this batch exists

`tools/baselines_v2.sh` measured learned_markov latency on **test seed 1 only** — its own
header called full LOSO "the extended protocol". This batch closes that gap. It touches no
canonical CSV; it only adds `results/learned_10fold/` + gitignored regenerable hotsets.

## Result — fq_median (cold first-query latency), async arm, rel% vs no-prefetch baseline

| WL | learned_14 | learned_28 | 2f_top14 | 2f_top28 | 2e_K10 |
|----|-----------|-----------|----------|----------|--------|
| A  | −39.6 ±3.6 | −40.1 ±3.4 | −43.0 ±10.1 | **−50.6 ±14.9** | **−50.8 ±14.9** |
| B  | −36.6 ±9.8 | −38.0 ±10.3 | −36.3 ±9.8 | −36.9 ±8.3 | −36.6 ±8.6 |
| C  | −65.4 ±13.3 | −68.9 ±12.9 | −64.6 ±14.1 | −69.9 ±11.8 | −64.0 ±14.7 |

(± = 95 % CI, t-dist df=9. Negative = faster. Warm-process e2e in `batch.log`; same ranking,
smaller magnitudes: A ≈ −30 %, B ≈ −27 %, C ≈ −57 %.)

## Two findings

**1. The improvement is real and statistically robust.** Every arm's CI excludes 0 on all
three workloads. learned_markov delivers −37 % to −69 % cold first-query latency depending
on workload, with 100 % delivery and genuinely cold caches.

**2. learned_markov buys nothing over simple frequency top-N.** It *ties* 2f_topN / 2e_K10
on B and C (CIs overlap heavily) and is **worse on A** (Scattered-Zipf): −40 % vs −51 % for
2f_top28 / 2e_K10, the frequency/hot arms. The first-order Markov model's sophistication does
not beat a static frequency dump of the same budget. (Confirms the prior "learned ≈ 2f_topN"
read; the earlier "marginal-collapse" superiority claim was already retracted.)

## Why single-fold overstated the case

The single-fold protocol tested on seed 1 — which the 10-fold distribution reveals is the
**most optimistic held-out seed**:

| WL | seed-1 fq (async, learned_14) | 10-fold mean | seed-1 rank (1=fastest of 10) |
|----|------|------|------|
| A  | 354.5 µs | 524.6 µs | **1 / 10** |
| B  | 412.7 µs | 558.7 µs | **1 / 10** |
| C  | 180.6 µs | 336.0 µs (sd 200) | 3 / 10 |

Seed 1 is the fastest fold on A and B and near-fastest on C. Workload C is highly
seed-sensitive (sd 200 µs, range 180–629 µs) — a single fold there is nearly meaningless.
Reporting only seed 1 systematically flattered every arm; the 10-fold mean + CI is the
defensible number.

## Scope (unchanged, deferred by design)

Workload E for learned (needs a code change to gen_pageseq scan handling), lp-arm extension,
and native-YCSB merge are **out of this batch** by the batch's own charter — code-free,
A/B/C only. This batch closes exactly the learned_markov LOSO run-completeness gap.
