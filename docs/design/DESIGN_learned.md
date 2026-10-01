# DESIGN_learned.md — Chen-inspired transition-based learned prefetch baseline

## 1. Baseline scope and fidelity boundary
A lightweight transition-based baseline **inspired by Chen et al.'s (ICDE 2021) formulation of
database prefetching as future-page prediction from historical access traces**. It is **not** a
reproduction of Chen et al.

- **Kept:** historical-trace training; future-page prediction; held-out evaluation.
- **Replaced:** the paper's (unavailable) neural models → a transparent **first-order Markov
  transition model** over page-access episodes.
- **Not reproduced:** the Decision Module, the background prefetch thread, the full neural
  architecture.
- **Features:** page-access context only — **no** SQL template, request key, tenant, or other
  request-level features.
- **Leaper** is related work only, **not** a source of this baseline.

We do **not** claim the first-order Markov model is equivalent to Chen's neural model; only that it
preserves the *transition-prediction abstraction*.

**Cold-start note.** Before the first SQLite page access, the transition predictor has no current
page-access context. This does **not** rule out predictors that use request-level or prior-
invocation features, which are outside this baseline's scope.

Two independent artifacts (separate code paths):
- `learned_markov_N` — hotset from the model's finite-horizon expected-visit **scores**.
- `frequency_N` — hotset from raw page-visit **counts** (an independent analysis baseline).

## 2. Sequence reconstruction  (`strategies/learned/gen_pageseq.py`)
Each query is an **independent episode** delimited by synthetic tokens (negative IDs, excluded from
any hotset): `START(-1) → root → interior(s) → leaf → END(-2)`. Reconstructed **offline** from
`(db + dbstat.path)`; key→leaf via first_rowid, leaf→ancestors via path prefixes. Output CSV:
`op_no,step,page_number,page_type`. Transitions are formed **only within one `op_no`** — never
`leaf_of_query_i → root_of_query_{i+1}`. Hard validation: episode starts at the real root, ends at
a leaf, order matches `dbstat.path`. **`scan` (workload E) fails loudly** (see §8); write ops fail
loudly unless `--reads-only` (then counted + skipped, never silently reinterpreted).

## 3. Episodic Markov model  (`strategies/learned/train_markov.py`)
Transition counts are tallied within episodes; `P(q|p) = count(p,q) / Σ_x count(p,x)`. START is a
source state (→ root), END is absorbing. No cross-op edges.

## 4. Finite-horizon expected-visit ranking
From the START state, run an **expected-visit expansion for a finite horizon** (`horizon = max
observed real-page depth + 1`; = 4 for the current 3-level tree). This is a **next-page predictor,
not iterated to a stationary distribution**. Sparse update `v ← v·T`, accumulating a score per real
page; START/END never scored. Artifacts: `*_transitions.csv`, `*_scores.csv`
(`page_number,page_type,expected_visit_score,rank`), `*_marginal.csv` (analysis only),
`*_metadata.json`. **`learned_markov_N` selects the top-N real pages from `*_scores.csv`** (tie-
break: **score desc, then page_number asc**). `*_marginal.csv` is **never** read by the
`learned_markov` hotset path.

## 5. Held-out multi-seed protocol
Smoke may use a single pair (train=2, test=1). **Formal evaluation uses leave-one-seed-out (LOSO):**
for each `test_seed`, pool all other seeds as `train_seeds`, train one model, generate the hotset,
measure on `test_seed`. Hard assertions: `test_seed ∉ train_seeds`, `len(train_seeds) ≥ 1` (enforced
in `train_markov.py`, re-checked in `run_experiment.py` against the hotset's sidecar metadata).
`*_metadata.json` records `{model, model_version, workload, layout, train_seeds, test_seed, horizon,
budget_pages, input_sha256, tie_break}`. Hotset filename encodes workload + budget + **test** seed
(`learned_markov_<w>_<layout>_N<N>_test<T>.csv`) with the full training manifest + model in the
sidecar — never a single train seed.

## 6. Budget-matched delivery
`learned_markov_N` has the **same footprint** as its comparators: identical page count → identical
selected bytes (same SQLite page size). Compared against `frequency_N`, `2f_topN`, `2e_K10`,
baseline. Budgets `N ∈ {14, 28}` (100 optional sensitivity point; no large sweep — the question is
not footprint). Runtime uses a **pre-generated static hotset**; training is offline preprocessing,
not on the critical path (training time / model size / hotset-gen time reported separately).

## 7. Metrics and validation
**Primary:** `e2e_us = deliver_us + first_query_us`. **Secondary:** `deliver_us`, `first_query_us`,
`selected_pages`, `selected_bytes`, `major_faults`, `delivery_pct`. **Offline content metrics:**
held-out page coverage (required held-out page visits covered / total; also query-level coverage),
precision / unused-prefetched-pages, and Jaccard vs `2f_topN` and `2e_K10`. **Jaccard is page-set
similarity only — not a correctness gate and not a performance metric.** Whether a workload has
learnable signal is judged by held-out coverage, top-N vs random-N improvement, frequency entropy,
and e2e latency — **not** by Jaccard under arbitrary tie-breaking.

Implementation-acceptance is **validation gates only** (no performance/Jaccard threshold):
1. sequence reconstruction matches `dbstat.path` (≥5 point queries);
2. no cross-op transitions;
3. probability normalization (`|Σ P(·|p) − 1| < 1e-9`);
4. independent model output (`learned_markov` ← scores, `frequency` ← marginal; synthetic test
   fails if the code paths are shared);
5. determinism (identical input+params → identical transition/score/hotset checksums);
6. no leakage (`test_seed ∉ train_seeds`);
7. footprint equality (matched arms: equal page count + bytes);
8. existing-arm regression (default `build_hotset` path untouched; existing hotsets byte-identical).

## 8. Supported workloads and limitations
- **Point-lookup workloads (A, B, C, and the read-only point form of D):** supported —
  `root → interior → leaf`.
- **Workload E (range scan): UNSUPPORTED / N/A.** A scan is not a 3-page episode; `gen_pageseq`
  **fails loudly** on `scan`. Supporting E requires true range-query page-sequence reconstruction
  (or a real page trace); until then `learned_markov × E` is not produced. We do **not** simplify E
  to a 3-page start-leaf episode.

## 9. Smoke results (train=2, test=1; A/B/C)
Validation gates 1–8: **all PASS** (reconstruction; no cross-op; prob-norm max `|Σ−1|≈5e-11`;
independent-output + synthetic path-independence; determinism; no-leakage assert fires; footprint
equality; existing-arm regression byte-identical). Guards verified: train-time `test∈train`
AssertionError fires; `gen_pageseq` fails loudly on `scan`.

**Observation (reported, not assumed):** on the current fixed-depth (3-level) tree, each page
occupies a single depth, so the finite-horizon expected-visit score of a page equals its normalized
per-page visit frequency; consequently `learned_markov_N` and `frequency_N` selected the **same
pages** in the A/B/C smoke. This is an empirical coincidence of *this* tree structure, computed via
two independent code paths — **not** a claim that transition prediction reduces to frequency in
general, and not asserted of any other model. No performance conclusions are drawn here; the formal
LOSO batch (§10) has not been run.

*(Deliberately not pre-written: any claim that learned ≡ frequency in general, that Jaccard will be
high, that held-out must degrade, that prediction sophistication is irrelevant, or that an online
variant must yield zero. Findings will be written only from formal-batch results.)*

## 10. Formal batch configuration (NOT run here)
Arms: `baseline`, `2f_top14`, `2f_top28`, `2e_K10`, `learned_markov_14`, `learned_markov_28` (plus
`frequency_14/28` as offline analysis). LOSO over the available seeds; one model per (workload,
test_seed) trained on the complement. Delivery: **async** (deployment-relevant) with **pread** as a
completed-delivery oracle (budget-permitting). Every matched arm runs under identical workload, test
seed, repetition count, database image, layout, delivery mode, and randomized execution block.
Report training time, model size, and hotset-generation time; state explicitly that the runtime uses
a pre-generated static hotset with no online inference. `tools/baselines_v2.sh` carries the config;
the formal batch is not executed as part of this change.
