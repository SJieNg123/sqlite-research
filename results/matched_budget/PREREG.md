# Pre-registration: matched-budget comparison of Skel+10 and Dump-N (2026-10-05)

Written and committed **before any paired difference was computed**, so the margin and the
decision rule cannot have been chosen after seeing the result. Answers the TODO at the
page-budget paragraph of `paper/main.tex` (Section 6).

## Question

At an exactly matched page budget, does page-type selection (`Skel+10`, the profiled interior
pages plus the 10 most frequent leaves) differ in warm-process end-to-end latency from
frequency selection (`Dump-N`, the top N pages by visit count)?

## Pairs

`Skel+10` has the same size in all ten instances of each workload (checked from the
unified_v6 hotsets): 28 pages on Scattered-Zipf-100K and Uniform-100K, 14 on Tail-Mixed, 15 on
Tail-Hit. The advisor's TODO lists "18, 28, and 14"; 18 is the size of `Skel` on
Scattered-Zipf-100K, not of `Skel+10`. The matched pairs are therefore:

| workload | Skel+10 | matched frequency set |
|---|---|---|
| A, Scattered-Zipf-100K | `2e_K10`, 28 pages | `2f_top28` |
| B, Uniform-100K | `2e_K10`, 28 pages | `2f_top28` |
| C, Tail-Mixed | `2e_K10`, 14 pages | `2f_top14` |

Tail-Hit is not tested: its matched set would be `Dump-15`, which no batch has measured, and
the TODO names three workloads. The tool asserts the page counts against the hotset files
whenever the batch's `work/` directories are present.

## Measure

For each instance (seed) s, workload w, and delivery arm (`async` per-page, `async_win`
window-chunked):

    d_s = 100 * (e2e(Skel+10)_s - e2e(Dump-N)_s) / baseline_s

where e2e is the per-seed median `e2e_warm_median` (warm-process boundary; parsing charged to
both arms, main repo 111b8ae) and baseline_s is that seed's no-prefetch `fq_median`. d is in
percentage points of the baseline; negative means `Skel+10` is faster. Secondary, reported
but not used for the decision: the same with `e2e_median` (external-warmer boundary).

Estimate: the mean of d over the ten instances, with a 95% percentile bootstrap CI of the
mean (10,000 resamples, seed 42, `tools/stats_uncertainty.bootstrap_ci`, the method behind
every other CI in the paper). Six primary tests: three workloads by two arms.

## Margin and decision rule

Margin M = **5** percentage points of the baseline, the value the advisor proposed. For each
test:

| 95% CI of the mean of d | wording |
|---|---|
| inside [-5, +5] | "the difference is within ±5% of the baseline" |
| entirely below -5 | "Skel+10 is faster by more than 5% of the baseline" |
| entirely above +5 | "Dump-N is faster by more than 5% of the baseline" |
| anything else | "we cannot distinguish the two within ±5%" |

No test is dropped, merged or re-run on the basis of its outcome.

## Disclosure

The per-cell means of `Skel+10` and `Dump-14` on Tail-Mixed were already visible in Table
competitive before this note (about -57% and -56% of baseline). Their paired difference was
not computed. No `Dump-28` result had been looked at.

## Data and code

- Data: `results/unified_v6` after the 111b8ae re-derivation. unified_v7 will rerun the same
  cells, add `Dump-15` for Tail-Hit, and this rule applies to it unchanged.
- Code: `tools/matched_budget.py <batch>`, committed with this note and run only afterwards.
