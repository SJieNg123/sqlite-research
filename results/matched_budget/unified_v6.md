# Matched budget, unified_v6

Rule: results/matched_budget/PREREG.md. d = Skel+10 minus Dump-N, in % of the same-seed baseline; negative = Skel+10 faster. Mean over 10 instances, 95% bootstrap CI. Page counts asserted on 30 of 30 seed-workload pairs.


## e2e_warm_median (primary)

| workload | arm | pages | mean d | 95% CI | Skel+10 faster | verdict |
|---|---|---|---:|---|---:|---|
| Scattered-Zipf-100K | per-page | 28 | -0.5 | [-0.9, -0.2] | 8/10 | within ±5% of baseline |
| Scattered-Zipf-100K | window-chunked | 28 | +0.4 | [-0.7, +2.1] | 7/10 | within ±5% of baseline |
| Uniform-100K | per-page | 28 | +0.8 | [-0.6, +2.5] | 6/10 | within ±5% of baseline |
| Uniform-100K | window-chunked | 28 | +0.9 | [-0.1, +2.3] | 5/10 | within ±5% of baseline |
| Tail-Mixed | per-page | 14 | +0.1 | [-0.2, +0.4] | 5/10 | within ±5% of baseline |
| Tail-Mixed | window-chunked | 14 | +0.2 | [-0.3, +1.0] | 7/10 | within ±5% of baseline |

## e2e_median (secondary)

| workload | arm | pages | mean d | 95% CI | Skel+10 faster | verdict |
|---|---|---|---:|---|---:|---|
| Scattered-Zipf-100K | per-page | 28 | -0.4 | [-0.8, -0.1] | 5/10 | within ±5% of baseline |
| Scattered-Zipf-100K | window-chunked | 28 | +0.6 | [-0.6, +2.3] | 7/10 | within ±5% of baseline |
| Uniform-100K | per-page | 28 | +0.5 | [-1.6, +2.5] | 6/10 | within ±5% of baseline |
| Uniform-100K | window-chunked | 28 | +0.2 | [-1.1, +1.7] | 6/10 | within ±5% of baseline |
| Tail-Mixed | per-page | 14 | +0.1 | [-0.2, +0.5] | 5/10 | within ±5% of baseline |
| Tail-Mixed | window-chunked | 14 | +0.2 | [-0.3, +0.9] | 6/10 | within ±5% of baseline |
