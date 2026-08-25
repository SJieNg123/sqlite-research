# OpenWhisk thesis notes (deployment complement)

Concise, thesis-ready notes for later integration. Descriptive only; no speedup,
winner, ranking, Pareto frontier, percentage, or significance is asserted here.

## Purpose

OpenWhisk was used to test whether the project's page-prefetch strategies can be
**represented and executed inside a real serverless/FaaS deployment**, and to
observe the deployment-side cost structure (footprint, page-delivery work, and the
instrumented query phase) that the strategies imply. It is a **deployment
complement** to the controlled native/WK1 experiments, not a replacement for them.

## Experimental coverage

- 9 target strategy families (primary: 2d, layers_5, 2e_K10, 2f_slru; secondary:
  2e_K500, leaf_freq_K10, leaf_rand_K10, 2f_top102, learned_markov_102).
- 3600 formal invocations; 1800 baseline-target pairs.
- Canonical YC workload (`native_ycsb_c_read_zipf`), 10 seeds.
- Two handle modes: warm (keep-alive process) and standalone (fresh process).
- Two byte-frozen run-config identities (primary `022fbeb0...`, secondary
  `441609e6...`); all invocations passed the frozen validity gates.

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
