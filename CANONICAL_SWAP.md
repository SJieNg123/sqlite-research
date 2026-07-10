# CANONICAL_SWAP.md — v2 canonical batch: scope, casualties, methodology revisions

Guide for the §7 rewrite. `results/unified_v2` (+ `results/baselines_v2`, back-to-back,
shared 2f_slru anchor, all n=10) is the **new canonical single-instantiation source**.
This is NOT a global find-replace: v2's matrix does not cover every old-batch number the
paper cites. Below: the drift correction, the casualty list (what v2 covers / doesn't),
the YD decay finding, and the methodology revisions to log.

## 0. Machine-state drift is ADDITIVE, not a scalar multiplier (do NOT reintroduce "1.2×")
The anchor difference between v2 and `results/main` is an **additive CPU-path offset**, not a
multiplicative factor:

| path | v2 (A) | main (A) | Δ |
|---|---:|---:|---:|
| baseline (slow, I/O-bound) | 523 | 529 | **−6 µs (−1%)** |
| 2f_slru async (fast, CPU-bound) | 108 | 127 | **−18 µs (−15%)** |

A scalar "×1.2" is wrong: at baseline (~500 µs) the same machine difference is −1%, at the
100-µs path it is −15% — i.e. a ~10–20 µs additive offset concentrated on the CPU path.
**Since v2 is the new absolute source, no cross-batch conversion is needed at all.** Any
methodology sentence must say "absolute values are not cross-batch comparable; the drift is
an additive CPU-path offset", never a multiplier.

## 1. Casualty list — old numbers the paper cites that v2 does NOT cover
Swap decision per item (writing agent: know which tables change and which don't):

| old datum | paper use | v2 coverage | decision |
|---|---|---|---|
| **2a range-hint 32/92 pages** | §4.2 readahead-cap empirical value | ❌ 2a/2b removed from strategy docs; v2 matrix has no 2a cell | **choose one:** (a) v2 re-runs one 2a cell; (b) keep old 32/92 with a batch-provenance note; (c) rewrite §4.2 qualitatively. First casualty — do not drop silently. |
| **RAM-pressure (cgroup 20M)** | §6.2.2 | ❌ not rerun in v2 | keep at original batch numbers + provenance note (§7.4 batch discipline allows) |
| **cadence (multiprocess re-warm)** | §6.2.x | ❌ | keep + provenance note |
| **size-scaling (1 GiB)** | §6.x | ❌ | keep + provenance note |
| **sleep-sweep (S5 deliver point)** | §5 | ❌ | keep + provenance note |
| **old churn (A/B/C × D-generator)** | §6.2.1 churn | ❌ (v2 has aging YD/YE, not old churn) | **KEEP — complementary, not replaced** (see §2) |

Everything in v2's matrix (A/B/C × orig/vacuum/ta × {baseline, layers_5/92, 2d,
2e_K10/K40/K92/K500, 2f_slru}) + baselines_v2 (lp_*, learned_markov, 2f_topN, anchor):
**swap to v2 numbers.** Everything else: **keep + provenance note.**

## 2. Old churn vs new aging are COMPLEMENTARY (both kept)
- **Old churn** (A/B/C read workloads, aged by the D-generator write stream): the read
  hotspot is **stationary** (fixed key range) → static t=0 hotset does **not** decay. §6.2.1.
- **New aging** (YD/YE self-aging): YD is **read-latest = non-stationary** → static hotset
  **decays** (§3). Together they establish the full statement: **decay is governed by
  hotspot stationarity**, not "static hotsets never decay".

## 3. YD decay finding — with the structural-resistance twist (cross-seed, paper-grade)
Corrected aging (per-checkpoint probe; see §4). orig, **10 reps × 10 seeds**,
`results/aging_v2/aging_ci.csv` (mean ± 95% CI):

- **YD access-frequency hotset (`2e_K10_static`) decays**: gain **−50% at ck0 (267±110) →
  −33% at ck10 (382±78)**. It **erodes by ~half — NOT to zero** (still below baseline
  ~540–570). ck0 CI is large (±110): the initial match is seed-variable. Word it "gain
  erodes by ~half", not "decays to baseline".
- **YD structural hotset (`layers_92_static`) resists AND overtakes**: 252±9 → 270±12
  (+7%, tight CI), and **from ck1 onward layers_92 (~250–278) is lower than 2e (~310–420)**
  → under read-latest aging the structural skeleton becomes the better static hotset.
  Frequency hotsets bind to *which keys are hot* (fails under non-stationarity); the skeleton
  binds to *what the tree looks like* (drifts slowly).
- **YE (zipfian, stationary)**: `2e_K10_static` **does not decay** (−53%→−55%, stays below
  layers_92 throughout) → like C. Confirms decay is a non-stationarity property, not aging
  per se.

**Paper upgrades:**
- **§7.4 churn:** "static t=0 hotset does not decay" → "**decay is governed by hotspot
  stationarity — access-frequency hotsets decay, structural skeletons resist**".
- **§7.5 guidance:** add — read-latest / append-heavy workloads (the typical serverless
  event/log-store shape) → prefer a **structural skeleton or periodic hotset refresh** over a
  frozen access-frequency hotset.
- **Dimension caveat (present side by side, else it reads as contradiction):** `layers_*` is
  *unreliable* on cross-seed first-query (§7.3, tie/directional) yet the *most durable* under
  aging (§7.4). Both hold — different axes: first-query *level* vs aging *robustness*.

## 4. Methodology revisions to log in REPORT
- **Aging probe bug (must leave a trace):** the aging TTFQ originally used a **single
  whole-trace probe** at every checkpoint → its first query never moved with the insert
  frontier → it structurally could not observe a frozen hotset decaying. Fixed to a
  **per-checkpoint probe** (chunk-k reads reflect the hotspot at checkpoint k). **Pre-fix
  aging numbers are void** (they showed a false "no decay"). Commit `ae45523`.
- **Canonical batch:** single-instantiation numbers now sourced from `results/unified_v2`
  (n=10) + `results/baselines_v2`; cross-seed CI (A/B/C 10-seed) and YD/YE aging cross-seed
  (`results/aging_v2`, reps=10 × seeds 1..10) are separate, self-contained batches.

## 5. Material-map / memory sync (todo alongside this)
- add the YD decay finding (frequency decays / structural resists / stationarity axis);
- confirm the learned-v1 retraction marker is present (v1 marginal-collapse design → replaced
  by the Chen-inspired v2, commit `a98e673`);
- attach this casualty list as the map's canonical-swap appendix.
