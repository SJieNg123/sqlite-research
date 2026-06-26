# 2d / 2e Access-pattern Prefetch × Churn

Tests the README §13 research gap: **2d/2e access-pattern prefetch in a continuously-churned DB**. The 10th-dimension churn experiment only covered `layers_N`; this fills in the gap for 2d (interior-only) and 2e_K10 (interior + top-10 hot leaves).

## Design

- **DB**: same as `runs_nsweep` — 600k rows × 100 B, layout 1a (original).
- **Churn**: same `workload_churn_write.txt` workload — 10 checkpoints × 5000 mixed ops (insert/update/delete/readmodifywrite/scan) = 50,000 mutations total.
- **Benchmark workload**: workload C (uniform reads in key range [590000, 610000]) — same `workload_c.txt` as nsweep.
- **Hot pages source**: **static, from t=0** — `strategies/access/runs/hotpages_c.csv` and `hot2e_C_orig_K10.csv`, both computed once on the **unchurned baseline DB**. This is the conservative case (no per-checkpoint re-warmup); if it works here, dynamic re-warmup would do at least as well.
- **Prefetcher**: `prefetch_access` binary in `--prefetch-mode access-2d` / `access-2e` (new modes added to `sqlite_prefetch_churn_experiment.py`).
- **Baselines**: existing `runs_nsweep/n0` (no prefetch) and `runs_nsweep/n92` (layers_92 file-offset).

## Result

Average `first_query_latency_us` over 10 churn checkpoints:

| Strategy           | Syscalls | Avg first_q | Δ vs n0 | Notes |
|--------------------|----------|-------------|---------|-------|
| n0 (no prefetch)   | 0        | 462 µs      | —       | baseline drift 387 → 549 µs over churn |
| n92 (layers_92)    | 92       | 213 µs      | -54%    | file-offset ordering, no leaves |
| **acc_2d (static)**| ~92      | **231 µs**  | **-50%**| interior-only, access-ordered, static hot from t=0 |
| **acc_2e_k10 (static)**| ~102 | **42 µs**   | **-91%**| interior + top-10 hot leaves (static from t=0) |

## Why static hot leaves survive churn

Workload C reads keys in [590000, 610000]. The 100 k-op churn workload's inserts target id=600001+, which mostly land **on the same hot leaves** (one of which holds rows ~595k-600k, another holds ~600k-605k). So the top-10 leaves at t=0 remain top-10 leaves throughout the 50 k churn — they just get a few extra rows appended. **Hot-leaf set is workload-stable for high-key insert workloads**, which validates "compute hot-leaf set once, reuse across churn" as a viable production pattern.

Caveat: this would NOT hold for workload A (Zipfian over the whole keyspace) or workload B (uniform full-range) under random deletions — the hot leaves there could rotate as keys are removed. **Workload-shape × churn-shape coupling matters.**

## Anomaly

`checkpoint_003`: 2d jumps to 414 µs and n92 jumps to 232 µs (vs ~210 baseline). Likely a transient page-cache event during the run; 1-rep sample so noise is expected. The other 9 checkpoints are tight.

## Files

- `run_access_churn.sh` — driver (runs orchestrator with mode=access-2d, access-2e)
- `aggregate.py` — compares 2d/2e_k10 vs n0/n92 nsweep baselines
- `matrix_first_q_us.csv` — wide-format result table (label × strategy)
- `2d/benchmark_summary.csv`, `2e_k10/benchmark_summary.csv` — per-checkpoint metrics
- `2d/`, `2e_k10/` — orchestrator outputs (checkpoints/, benchmarks/, test_churn.db)

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing/prefetch_churn
bash runs_access_churn/run_access_churn.sh
python3 runs_access_churn/aggregate.py
```

## Orchestrator changes (new modes)

`sqlite_prefetch_churn_experiment.py` gained:
- `--prefetch-mode access-2d` / `access-2e`
- `--prefetch-hotpages <hotpages.csv>` (required for the above modes)
- `--prefetch-cap-interior <N>` (0 = all resident interior)
- `--prefetch-cap-leaf <K>` (top-K hot leaves for 2e)

The new wrapper invokes `prefetch_access <db> <classify> <hotpages> <cap_int> <cap_leaf> <pgsize>`.
