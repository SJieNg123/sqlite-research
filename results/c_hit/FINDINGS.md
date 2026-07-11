# C_hit control — findings

> **UPDATE (commit de4490f + a493768): the 2e_K10 tie-break was subsequently FIXED, not just
> disclosed.** `gen_hotleaves` now ranks by `(-count, pageno)` (trace-order-independent;
> regression test). After the fix + rerun (`results/c_hit_v2`, `results/tiebreak_fix`):
> **C_hit 2e_K10 = −27.2% [−34.6,−17.7]** (== interior skeleton, artifact gone);
> **C (mixed) 2e_K10 cross-seed = −55% [−67,−43]**, bimodal (miss-first-op ~−70% genuine
> rightmost-leaf hotspot; hit-first-op ~−31% interior). The analysis below describes the
> PRE-FIX artifact that motivated the fix; the mechanism conclusions still hold.

**Question.** C's headline (2e_K10 e2e_warm −75%) is now known to sit on top of a
key-range artifact: C's range [590000,609999] exceeds the DB max id 600000, so ~50%
of its queries are not-found high-key lookups that all descend the right edge to the
**rightmost leaf**, concentrating traffic there. Does frequency-aware prefetch still
help once that unintended concentration is removed?

**Control.** `C_hit` = id ∈ [580001,600000], 20,000 keys each ×5, uniform — same
key-space size, tail-region locality, but **all keys exist** (0 not-found). orig
layout, 10 seeds × 10 reps. Batch: `results/c_hit/`.

## Cross-seed result (10 seeds, vs same-seed baseline, e2e_warm)

| strategy | first-q | e2e_warm | verdict | note |
|---|---:|---:|---|---|
| 2d (interior only) | −36.6% | **−28.5%** [−34.9,−19.6] | robust | interior skeleton |
| 2f_top14 (freq leaves, page tie-break) | −39.9% | **−30.6%** [−37.1,−22.4] | robust | genuine frequency |
| learned_markov_14 (LOSO held-out) | −38.2% | **−29.0%** [−36.1,−19.4] | robust | genuine, no leakage |
| **2e_K10 (freq leaves, insertion tie-break)** | −79.0% | **−69.6%** [−73.6,−64.2] | robust | **tie-break artifact** |
| 2f_slru (whole WS dump) | −88.8% | +76.5% | robust(worse) | deliver trap |

## The 2e_K10 −69.6% is a tie-break artifact, not frequency selection

On C_hit every leaf is touched ~equally (each of ~668 touched leaves ≈150 ops; counts
**tied**). With tied counts, the "top-K hot leaves" is decided purely by tie-break:

- `gen_hotleaves.py` (2e_K10) builds `leafcnt` in **first-seen order** and calls
  `Counter.most_common(K)` → ties resolve to insertion order → **the K earliest-seen
  leaves**. The measured first query IS the first op of the same seed's stream → its
  leaf is first-seen → **always selected**. Verified: for seed 1,
  `2e_K10 leaves == most_common(10) == first-10-distinct-leaves-seen` (identical sets).
- `gen_freqdump.py` (2f_top14) ranks with `sorted(key=lambda pn:(-cnt[pn],pn))` →
  **page-number tie-break** → the lowest-offset leaves (25460,25461,…), which do **not**
  track the measured first op.

**10-fold offline coverage** (`results/loso/coverage_c_hit.csv`): first-op leaf covered
by **2e_K10 10/10**, by **2f_top14 / learned_markov / frequency 0/10**. The 2e_K10
coverage is a same-seed insertion-order alignment; the LOSO-held-out learned baseline
(trained on the other 9 seeds) gets no such alignment → 0/10 → it measures the genuine
level.

## Honest conclusion

- On a **pure-hit uniform tail** workload there is **no genuine leaf hotspot**. The
  robust, tie-break-independent benefit is the **interior skeleton**: ~**−29 to −31%
  e2e_warm** (2d −28.5%, 2f_top14 −30.6%, LOSO learned −29.0%, all robust). The extra
  "hot-leaf bonus" over interior-only is ~2 points — negligible.
- C's **−75%** headline is therefore driven by C's **not-found rightmost-leaf
  concentration** (a real but key-range-induced hotspot), not by frequency selection on
  genuine tail reads. The `2e_K10` number is additionally inflated on tied-count
  workloads (C, C_hit) by the insertion-order tie-break coinciding with the measured
  first op.

## Three-stage mechanism (B → C_hit → C)

- **B (global uniform):** leaf counts low & spread → no leaf hotspot → small leaf hotset
  useless; interior skeleton is the whole story.
- **C_hit (tail-local uniform):** leaf counts tied high, still no real hotspot → genuine
  frequency selection ≈ interior skeleton (~−30% e2e_warm); the −70% is a tie-break
  artifact.
- **C (mixed, 50% not-found):** the rightmost leaf absorbs ~50k not-found lookups → a
  genuine dominant hotspot → small hotset especially effective (−75%), but the hotspot
  is a key-range artifact.
- **A (Zipfian):** genuine key-frequency skew → real hot leaves → 2e_K10 −36% (robust,
  modest, tie-break-independent).

**Takeaway for the paper.** Access-frequency *leaf* selection genuinely helps only when
there is a real access hotspot (A's skew, C's not-found concentration). On uniform tail
hits the honest, robust benefit is the **page-type-aware interior skeleton (~−30%
e2e_warm)**. The −75% should be presented as C's mixed-workload / not-found case, not as
a general targeted-prefetch result; and the `2e_K10` tie-break inflation on tied-count
workloads should be disclosed.
