# Matched-budget comparison: Skel+10 vs Dump-N

Design, margin and decision rule: `PREREG.md`, committed (a6b943c) before anything was
computed. `tools/matched_budget.py results/unified_v6` produced `unified_v6.csv` and
`unified_v6.md`.

## Result on unified_v6

**All six pre-registered tests fall within ±5% of the baseline.** At an exactly matched page
budget, page-type selection and frequency selection give the same warm-process end-to-end
latency, under both delivery mechanisms:

| workload | pages | per-page: mean d [95% CI] | window-chunked: mean d [95% CI] |
|---|---|---|---|
| Scattered-Zipf-100K | 28 | −0.5 [−0.9, −0.2] | +0.4 [−0.7, +2.1] |
| Uniform-100K | 28 | +0.8 [−0.6, +2.5] | +0.9 [−0.1, +2.3] |
| Tail-Mixed | 14 | +0.1 [−0.2, +0.4] | +0.2 [−0.3, +1.0] |

d is Skel+10 minus Dump-N in percentage points of the same-seed baseline, mean over ten
instances. Every interval lies inside [−0.9, +2.5], well within the margin. The secondary
external-warmer metric gives the same verdict in all six cells (`unified_v6.md`).

## Descriptive, not pre-registered: the two sets mostly coincide

| workload | pages shared by Skel+10 and Dump-N |
|---|---|
| Scattered-Zipf-100K | 20 of 28, in all ten instances |
| Uniform-100K | 20 of 28, in all ten instances |
| Tail-Mixed | 12 of 14, in all ten instances |

Every query traverses the interior pages, so a visit count ranks them near the top, and a
frequency selector at this budget picks most of the same pages a page-type selector does. The
equivalence therefore says the two rules converge at small budgets, not that page-type
knowledge is irrelevant to finding them.

## Result on unified_v7: replicated, and Tail-Hit added

`tools/matched_budget.py results/unified_v7` (it reads each seed's merged summary, so family D's
`Dump-15` is found; rerun on unified_v6 it reproduces `unified_v6.csv` byte for byte). **All
eight primary tests fall within ±5% of the baseline:**

| workload | pages | per-page: mean d [95% CI] | window-chunked: mean d [95% CI] |
|---|---|---|---|
| Scattered-Zipf-100K | 28 | +0.0 [−1.6, +1.5] | −1.4 [−2.6, −0.6] |
| Uniform-100K | 28 | +0.8 [−0.0, +1.8] | −0.0 [−0.6, +0.6] |
| Tail-Mixed | 14 | +0.1 [−0.2, +0.4] | +0.3 [−0.9, +1.8] |
| Tail-Hit | 15 | +1.5 [−1.3, +4.4] | +0.5 [−0.6, +1.9] |

These are the final unified_v7 numbers (2026-10-08). An earlier version of this section quoted
attempt 3 of the batch, which was discarded (`results/unified_v7/README.md`); its verdicts were
the same.

### The secondary metric on Tail-Hit is a harness artifact

The external-warmer metric agrees in six cells but reads "Dump-N faster by more than 5%" on
Tail-Hit (+13.3 and +12.3 points). The gap is the warmer's open cost, which depends on the
directory its hotset file sits in, not on the pages selected. After the cache drop the warmer
opens that file cold, and the harness keeps each family's hotsets in its own `work/`:

| hotset directory | entries | warmer `open_us` on Tail-Hit, median over seeds |
|---|---|---|
| `main/work/` (Skel+10, Dump-14, Skel and the other 11 strategies) | 117 | 204 to 225 us |
| `top15/work/` (Dump-15) | 2 | 117 us |
| `whole/work/` (whole_file) | 8 | 146 us |

Skel+10 at 225 us against Dump-15 at 117 us is 108 us, 10 to 18% of the Tail-Hit baseline
across instances (587 to 1,070 us), which brackets the observed gap. The three other workloads' pairs both live in `main/` and agree, and the
warm-process primary metric excludes the open cost by definition. A like-for-like
external-warmer comparison for Tail-Hit would need Dump-15's hotset in the same directory;
the pre-registered decision rests on the primary metric and stands.
