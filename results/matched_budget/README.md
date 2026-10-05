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

## Still to come

unified_v7 reruns these cells and adds Dump-15 for Tail-Hit, under the same rule.
