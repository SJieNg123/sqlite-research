# Matched budget, unified_v7

Rule: results/matched_budget/PREREG.md. d = Skel+10 minus Dump-N, in % of the same-seed baseline; negative = Skel+10 faster. Mean over 10 instances, 95% bootstrap CI. Page counts asserted on 40 of 40 seed-workload pairs.


## e2e_warm_median (primary)

| workload | arm | pages | mean d | 95% CI | Skel+10 faster | verdict |
|---|---|---|---:|---|---:|---|
| Scattered-Zipf-100K | per-page | 28 | +0.0 | [-1.6, +1.5] | 5/10 | within ±5% of baseline |
| Scattered-Zipf-100K | window-chunked | 28 | -1.4 | [-2.6, -0.6] | 9/10 | within ±5% of baseline |
| Uniform-100K | per-page | 28 | +0.8 | [-0.0, +1.8] | 5/10 | within ±5% of baseline |
| Uniform-100K | window-chunked | 28 | -0.0 | [-0.6, +0.6] | 5/10 | within ±5% of baseline |
| Tail-Mixed | per-page | 14 | +0.1 | [-0.2, +0.4] | 6/10 | within ±5% of baseline |
| Tail-Mixed | window-chunked | 14 | +0.3 | [-0.9, +1.8] | 7/10 | within ±5% of baseline |
| Tail-Hit | per-page | 15 | +1.5 | [-1.3, +4.4] | 6/10 | within ±5% of baseline |
| Tail-Hit | window-chunked | 15 | +0.5 | [-0.6, +1.9] | 6/10 | within ±5% of baseline |

## e2e_median (secondary)

| workload | arm | pages | mean d | 95% CI | Skel+10 faster | verdict |
|---|---|---|---:|---|---:|---|
| Scattered-Zipf-100K | per-page | 28 | +0.3 | [-1.3, +1.8] | 5/10 | within ±5% of baseline |
| Scattered-Zipf-100K | window-chunked | 28 | -1.4 | [-2.7, -0.5] | 9/10 | within ±5% of baseline |
| Uniform-100K | per-page | 28 | +0.9 | [+0.0, +1.9] | 4/10 | within ±5% of baseline |
| Uniform-100K | window-chunked | 28 | +0.0 | [-0.6, +0.6] | 4/10 | within ±5% of baseline |
| Tail-Mixed | per-page | 14 | +0.1 | [-1.1, +1.2] | 7/10 | within ±5% of baseline |
| Tail-Mixed | window-chunked | 14 | +0.3 | [-0.6, +1.7] | 8/10 | within ±5% of baseline |
| Tail-Hit | per-page | 15 | +13.3 | [+9.6, +17.2] | 0/10 | Dump-N faster by more than 5% |
| Tail-Hit | window-chunked | 15 | +12.3 | [+9.7, +14.8] | 0/10 | Dump-N faster by more than 5% |
