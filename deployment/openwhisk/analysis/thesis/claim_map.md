# OpenWhisk thesis claim map

Every proposed OpenWhisk-facing statement is classified **SAFE**, **QUALIFIED**,
or **DO_NOT_CLAIM**. OpenWhisk is a deployment complement, not the primary
controlled performance evidence; the systematic short-lived execution/storage-state
or order effect (exact source outside scope) is why warm paired latency is never a
headline. This map is machine-checked by `test_synthesis.py`.


## A_deployment_feasibility

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | All nine page-prefetch strategy families were represented and executed inside the OpenWhisk/serverless action across 3600 formal invocations. | normalized/normalization_manifest.json; strategy_metadata.csv | -- | Direct execution record; feasibility is demonstrated by the runs themselves, independent of any latency interpretation. |

## B_validity_correctness

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | The 3600 invocations passed the frozen validity gates under two byte-frozen run-config identities (primary 022fbeb0..., secondary 441609e6...), with 1800 baseline-target pairs. | normalized/normalization_manifest.json | -- | Recorded gate pass and identity binding; provenance fact, not a performance claim. |

## C_footprint_differences

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | Strategy families produce materially different selected-page footprints (5 to ~26k pages) and selected bytes. | openwhisk_strategy_footprint.csv | -- | Footprint is a frozen plan property (deployment-side), unaffected by the order/state effect. |

## D_delivery_cost_differences

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | Strategies with larger selected-page footprints incur larger deployment page-delivery work (median deliver_us) in this implementation. | openwhisk_cost_vectors.csv; figure_footprint_vs_delivery | Descriptive of this implementation's page-delivery mechanism; deliver_us is a delivery-work count, not a strategy speedup. | deliver_us is handle-mode-independent and monotone in footprint here; it is a deployment cost, not a query-latency effect. |

## E_first_query_descriptive

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **QUALIFIED** | Selected plans are associated with different median instrumented SQLite first_query_us values; selected plans can lower the instrumented first_query_us phase. | openwhisk_cost_vectors.csv; standalone_decomposition.csv | OpenWhisk absolute/paired first_query latency is NOT the primary controlled estimate because of the documented systematic short-lived execution/storage-state or order effect; these are descriptive medians, not causal speedups. first_query_us is the query phase only, NOT total cold-start latency. | The order/state effect confounds absolute and paired warm latency; native/WK1 remains the controlled estimate. |

## F_end_to_end_interpretation

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **QUALIFIED** | The deployment results are consistent with the project's cost-accounting view that reducing first-query latency does not automatically reduce end-to-end handler cost (e.g. 2f_slru has the lowest first_query_us but the largest delivery and handler_total). | openwhisk_cost_vectors.csv | An ADDITIONAL deployment-side illustration only. The causal/mechanism claim is established primarily by the native/WK1 experiments and PREDATES OpenWhisk (REPORT.md title). OpenWhisk did not discover this relation. | Section 11 constraint: do not rewrite thesis history. |
| **DO_NOT_CLAIM** | The OpenWhisk experiment revealed/discovered that faster first query does not imply faster end-to-end performance. | -- | -- | The relation was a core research question / thesis before OpenWhisk (REPORT.md title); attributing discovery to OpenWhisk would rewrite thesis history. |

## G_matched_budget_selection

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | Among the N_YC=102 budget-matched strategies, the frequency-ranked (2f_top102) and learned-LOSO (learned_markov_102) plans exhibit an EMERGENT (not page-type-imposed) ~51/51 interior/leaf split. | strategy_metadata.csv | -- | Recorded provenance fact about the frozen plans (page composition), not a latency comparison. |
| **DO_NOT_CLAIM** | The learned strategy is definitively better/worse than the frequency strategy based on these OpenWhisk latencies. | -- | -- | A winner claim over confounded warm latency / non-primary evidence; matched-budget table reports composition + descriptive medians only, no winner. |

## H_leaf_only_controls

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | leaf_freq_K10 and leaf_rand_K10 each select 10 leaf pages with zero interior pages (leaf-only frequency-vs-random ablation). | openwhisk_strategy_footprint.csv; matched_budget_descriptives.csv | -- | Frozen plan property (page composition). |
| **DO_NOT_CLAIM** | Frequency leaf selection beats random leaf selection (or vice versa) in cold-start latency, per these OpenWhisk numbers. | -- | -- | Winner claim over confounded warm latency; native/WK1 is the controlled arm for the frequency-vs-random lever. |

## I_warm_paired_latency

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **DO_NOT_CLAIM** | The warm baseline->target adjacent-pair latency ratio is the causal speedup of the target strategy. | order_position_descriptives.csv (shows the position effect) | -- | A systematic short-lived execution/storage-state or order effect makes position, not strategy, dominate adjacent warm pairs. |

## J_standalone_timing

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **QUALIFIED** | The standalone decomposition reports median open/select/deliver/first_query/handler_total per strategy. | standalone_decomposition.csv | Descriptive medians only, not a causal effect; open_us is a separately instrumented phase and is NOT folded into first_query_us. | Reporting the phase decomposition is safe; interpreting a phase as a strategy speedup is not. |

## K_first_arm_diagnostic

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **DO_NOT_CLAIM** | The first-arm (position-1) medians are a corrected / true-cold treatment effect. | first_arm_diagnostic.csv | -- | AB/BA are not exactly 50/50 and second-position observations are retained; the first-arm view is a diagnostic, not a deconfounded estimator -- medians must not be subtracted. |

## L_cross_workload_portability

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **SAFE** | The representative strategy mechanisms were executed and validated across five workload families (YC, YCu, YCh01, C, C_hit) in a separate single-batch OpenWhisk campaign of 468 formal invocations / 234 baseline-target pairs, with per-plan page-set + offset parity (exact native, semantic 2e contract, or structural-static) proven against the frozen keyed contract. | normalized/portability/portability_normalization_manifest.json; descriptive/portability/portability_plan_parity.csv; portability_workload_summary.csv | Portability = deployment execution / correctness / workload + plan binding across workloads. It is NOT a latency, ranking, or warm-speedup result, and the five families are representative coverage, not exhaustive. | Demonstrated by the runs themselves (execution + SHA-bound plan parity), independent of any latency interpretation; native/WK1 remains the primary performance evidence. |
| **DO_NOT_CLAIM** | The 468 portability, 852 portability-extension, 456 portability-full-closure, and 3600 strategy-space invocations jointly estimate a single cross-workload performance effect (5376 pooled measurements of one quantity). | -- | -- | The five campaigns answer different questions (strategy-space cost structure on YC vs. cross-workload deployment portability, its coverage extension, and its final cell closure) and are reported separately; they must never be pooled into one effect estimate, and none is a warm-latency ranking. |
| **SAFE** | A fourth additive OpenWhisk campaign (portability_ext, run_config bf504a28...) executed the 29 remaining (strategy, workload) cells as 852 formal invocations / 426 baseline-target pairs under its own byte-frozen identity, with per-plan page-set + offset parity proven against the frozen keyed contract, completing the workstation-coverage matrix to 49 comparable cells. | normalized/portability_ext/portability_ext_normalization_manifest.json; descriptive/portability_ext/portability_ext_plan_parity.csv | Execution / correctness / workload+plan binding only, under a distinct frozen identity; NOT a latency, ranking, or warm-speedup result, and NOT pooled with the other three campaigns. | Demonstrated by the runs themselves (execution + SHA-bound plan parity), independent of any latency interpretation; a fourth byte-frozen campaign, additive like primary->secondary. |
| **SAFE** | A fifth additive OpenWhisk campaign (portability_full_closure, run_config a5be8f15...) executed the final 16 uncovered (strategy, workload) cells as 456 formal invocations / 228 baseline-target pairs under its own byte-frozen identity, with per-plan page-set + offset parity proven against the frozen keyed contract, so all 65 canonical retained workstation cells at orig layout have OpenWhisk execution coverage. | normalized/portability_full_closure/portability_full_closure_normalization_manifest.json; descriptive/portability_full_closure/portability_full_closure_plan_parity.csv | CELL coverage (execution / correctness / workload+plan binding) only, under a distinct frozen identity. It is NOT protocol, layout, or performance equivalence, NOT a latency, ranking, or warm-speedup result, and NOT pooled with the other four campaigns. Native/WK1 remains primary. | Demonstrated by the runs themselves (execution + SHA-bound plan parity), independent of any latency interpretation; a fifth byte-frozen campaign, additive like the prior four. |

## M_effectiveness_portability

| classification | claim | support | qualification | reason |
|---|---|---|---|---|
| **QUALIFIED** | Across the 65 comparable (strategy, workload) cells (55 compared by relative first-query reduction; 10 lp cells compared by delivery order, reported separately), prefetch strategies that are effective on the workstation stay effective on OpenWhisk in the DESCRIPTIVE sense of relative first-query reduction vs each platform's own same-condition baseline (high-confidence workstation-effective strategies 32/37 effective on both; Spearman rho 0.67 all / 0.75 high-confidence). | comparison/VERDICT_effectiveness_portability.md; comparison/effectiveness_ow_vs_workstation.csv; comparison/ws_provenance.csv | Descriptive cross-platform CONSISTENCY of relative reductions only (standalone handles; same-batch R). It is NOT a claim of equal absolute latency, equal effect size, causal equivalence, hardware-independent speedup, or reproduction of the workstation performance ranking. | Relative reductions are the only cross-machine-comparable quantity; absolute microseconds are not, and OpenWhisk warm latency carries the order/state effect. Native/WK1 remains the primary controlled evidence. |
| **DO_NOT_CLAIM** | The OpenWhisk and workstation first-query latencies are equal / OpenWhisk reproduces the workstation absolute speedup for each strategy. | -- | -- | Only relative-reduction direction/consistency is comparable across machines; absolute latency and effect size differ by platform and are never asserted equal. |
