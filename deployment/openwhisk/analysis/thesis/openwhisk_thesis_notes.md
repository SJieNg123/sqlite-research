# OpenWhisk thesis notes (deployment complement)

Concise, thesis-ready notes for later integration. Descriptive only; no speedup,
winner, ranking, Pareto frontier, percentage, or significance is asserted here.

## Purpose

OpenWhisk was used to test whether the project's page-prefetch strategies can be
**represented and executed inside a real serverless/FaaS deployment**, and to
observe the deployment-side cost structure (footprint, page-delivery work, and the
instrumented query phase) that the strategies imply. It is a **deployment
complement** to the controlled native/WK1 experiments, not a replacement for them.

## Five OpenWhisk campaigns (do not pool)

Across the completed OpenWhisk evaluation, **5376 formal invocations** were
executed across **five byte-frozen campaigns**: **3600** in the **YC deployment /
strategy-space campaign** (primary 1600 + secondary 2000), **468** in the
**cross-workload portability campaign**, **852** in the additive
**cross-workload portability-extension campaign**, and **456** in the
additive **cross-workload portability-full-closure campaign** (which closes the
final uncovered cells so all 65 canonical retained workstation cells at orig layout
have OpenWhisk execution coverage). These span two ROLES answering DIFFERENT
questions -- the strategy-space cost structure on one canonical workload, and
cross-workload deployment portability of representative mechanisms. They are reported
separately and **must not be pooled into a single effect estimate**, and none is a
warm-latency ranking.

## Experimental coverage (Role A -- YC strategy-space campaign)

- 9 target strategy families (primary: 2d, layers_5, 2e_K10, 2f_slru; secondary:
  2e_K500, leaf_freq_K10, leaf_rand_K10, 2f_top102, learned_markov_102).
- 3600 formal invocations; 1800 baseline-target pairs.
- Canonical YC workload (`native_ycsb_c_read_zipf`), 10 seeds.
- Two handle modes: warm (keep-alive process) and standalone (fresh process).
- Two byte-frozen run-config identities (primary `022fbeb0...`, secondary
  `441609e6...`); all invocations passed the frozen validity gates.

## Cross-workload portability (Role B -- second OpenWhisk role)

- A single-batch, block-union campaign: **468 formal invocations /
  234 baseline-target pairs**, one live matrix fingerprint
  (`a3274bc9...`), one run-config identity (`64f44c3e...`), bundle
  `a7c9736cc65e...`.
- **5 representative workload families**: C (read_tail_mixed_20k), C_hit (read_tail_hit_20k), YC (native_ycsb_c_read_zipf), YCh01 (native_ycsb_c_hot_hashed_01), YCu (native_ycsb_c_read_uniform).
- 39 distinct executed target plans, each with proven page-set + offset
  parity against the frozen keyed contract: 24 exact-native-plan,
  12 semantic-2e-contract-reconstruction, 3 structural-static.
- Every invocation passed the same frozen validity gates (cold reset, delivery,
  oracle, measured-valid) as Role A.
- Portability here means **deployment execution + correctness + workload/plan
  binding across workloads** -- NOT a latency comparison, ranking, or warm
  speedup. The five families are **representative** coverage, not exhaustive.

## Cross-workload portability extension (Role B -- fourth campaign)

- An additive single-batch, block-union campaign completing the
  workstation-coverage matrix: **852 formal invocations /
  426 baseline-target pairs** (7 blocks), one live matrix
  fingerprint (`5ba26fe9...`), its OWN run-config identity
  (`bf504a28...`), bundle `9fd7b9f69030...` -- distinct from the three
  prior campaigns, which are byte-unchanged.
- 71 distinct executed target plans across the same 5
  families, each with proven page-set + offset parity against the frozen keyed
  contract: 51 exact-native-plan, 12
  semantic-2e-contract-reconstruction, 8 structural-static.
- It runs the 29 previously-uncovered (strategy, workload) cells, taking the
  workstation-vs-OpenWhisk comparable-cell coverage from 20 to **49 cells**. The
  effectiveness comparison over those 49 cells is a **descriptive cross-platform
  consistency** check of relative first-query reductions (standalone handles),
  **not** an absolute-latency, causal-equivalence, or ranking-reproduction claim.
- Like the other three campaigns it passed the same frozen validity gates and is
  **never pooled** into a single effect estimate.

## Cross-workload portability full closure (Role B -- fifth campaign)

- The final additive single-batch, block-union campaign closing the last uncovered
  cells: **456 formal invocations / 228 baseline-target
  pairs** (6 blocks, B12-B17), one live matrix fingerprint (`d35708b7...`), its
  OWN run-config identity (`a5be8f15...`), bundle `c8ef0cbe16c3...` --
  distinct from the four prior campaigns, which are byte-unchanged.
- 38 distinct executed target plans across the same 5
  families, each with proven page-set + offset parity against the frozen keyed
  contract: 29 exact-native-plan, 8
  semantic-2e-contract-reconstruction, 1 structural-static. The two
  libprefetch delivery-order variants (lp_sorted, lp_shuf) deliver the same
  canonical resident page set via `pread_ordered`; their cost lever is delivery
  order (`deliver_us`), analysed separately, not first-query.
- It runs the final 16 previously-uncovered (strategy, workload) cells, so **all 65
  canonical retained workstation cells at orig layout have OpenWhisk execution
  coverage** (BOTH=65, WS_ONLY=0; 4 OpenWhisk-only YC cells remain, never counted
  as workstation coverage). This is **CELL coverage** -- execution / correctness /
  workload+plan binding -- **not** protocol, layout, or performance equivalence,
  and **not** a latency or ranking claim. Native/WK1 remains the primary evidence.
- Like the other four campaigns it passed the same frozen validity gates and is
  **never pooled** into a single effect estimate.

## Deployment feasibility

Every strategy family -- structural skeletons, skeleton+hot-leaf unions, leaf-only
controls, a full resident working set, and the two budget-matched ranked/learned
plans -- was expressed as a frozen delivery plan and executed by the OpenWhisk
action under the same validity gates. This establishes that the strategy space is
**deployable**, not merely a native-benchmark construct.

## Footprint and delivery cost

Footprint spans three orders of magnitude (5 pages for layers_5 to ~26k pages for
2f_slru). Deployment page-delivery work (`deliver_us`) grows with footprint: from
~36 us (layers_5) to ~103 ms (2f_slru). Delivery work is handle-mode-independent
(the same pages are fetched); this is a **deployment cost vector**, reported per
phase and never collapsed to a single score. Offline plan/model generation is
**not** charged per invocation -- only the online select/deliver/query phases are.

Cost-vector column legend (`openwhisk_cost_vectors.csv`):
- `select_us`  -- online plan-selection phase (offline generation not charged).
- `deliver_us` -- page-delivery phase (fetching the selected pages).
- `first_query_us` -- instrumented SQLite **first-query phase only** (NOT total
  cold-start latency).
- `open_us` -- separately instrumented open/prepare phase.
- `handler_total_us` -- total action handler wall time.

## Query-phase metric

`first_query_us` measures only the first SQLite query after page delivery. It is
**not** total cold-start latency and **not** a strategy speedup. Across strategies,
`deliver_us` and `first_query_us` vary largely independently (2f_slru has the
smallest `first_query_us` but by far the largest `deliver_us` and
`handler_total_us`). That independence is the point: **query latency alone is an
incomplete deployment metric**.

## Relationship to the native results

The **native/WK1 experiments are the primary controlled performance/mechanism
evidence.** The OpenWhisk deployment complements them: it shows the strategies run
in a serverless setting and reproduces the same qualitative cost structure. It does
not, and is not used to, establish causal strategy performance on its own.

## Measurement limitation

A systematic short-lived execution/storage-state or order effect is present in the
OpenWhisk timings: within a warm baseline-target pair, the first-executed arm
(position 1) shows much larger `first_query_us` than the second, regardless of
which strategy occupies which position. The exact lower-level source was not
resolved and is outside current scope. Consequently, **adjacent warm pair ratios
are not used as strategy-performance estimates**, and the first-arm view is a
diagnostic only.

## What we do NOT claim

- No causal warm paired-speedup estimate for any strategy.
- No resolved hardware root cause for the order/state effect (and it is **not**
  random hardware noise; the page-cache-carryover explanation was specifically
  investigated and falsified).
- No claim that OpenWhisk alone establishes the optimal strategy, or that the
  learned plan beats the frequency plan (or vice versa).
- No claim that the first-arm diagnostic is a corrected treatment effect.
- No claim that OpenWhisk *discovered* the faster-first-query-vs-end-to-end
  relation -- that is a pre-existing core thesis result (REPORT.md title).
