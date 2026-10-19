# Grace-period check with the unified_v7 code (2026-10-19)

This reruns `results/unified_v5/grace_check`, so that the sentence in Section 3 rests on the
code version of the unified_v7 batch rather than on v5's: "with a 5 ms grace period between
dispatch and query, the chunked mode also reaches 100%, and first-query latency is flat at
about 100 us under both modes at every grace period". The question is the same as v5's. Is
`async_win`'s delivery shortfall at the first query lost pages, or readahead that has not
landed yet? See the v5 README for the reasoning.

## Method

run_experiment.py and pipeline/engine are unchanged since 24e9496, the unified_v7 batch
code. This is the same workstation as v7, run 2026-10-19 01:50:05 to 01:50:44 UTC, outside
the v7 window. It uses v5's design with v7's repetitions (10 kept plus 1 warmup per cell,
where v5 had 3):

```
run_experiment.py run --seed 1 --db orig --workload A,B --strategy 2f_slru --no-baseline \
  --pread-reps 0 --async-reps 10 --async-win-reps 10 --deliver-sleep-ms {0,5,20} \
  --discard-records --outdir results/grace_check_v7/sleep{0,5,20}ms
```

`--deliver-sleep-ms` sleeps between the end of dispatch and the first query, outside the
timed section. Every repetition was 0% resident after the reset.

## Result (medians of 10 reps, `sleep*ms/summary.csv`)

| sleep | workload | arm | delivery % | deliver_us | first query us |
|---|---|---|---:|---:|---:|
| 0 ms | A | async | 100.0 | 6842 | 97.1 |
| 0 ms | A | async_win | 83.7 | 1966 | 96.8 |
| 0 ms | B | async | 100.0 | 6818 | 99.2 |
| 0 ms | B | async_win | 86.9 | 1990 | 98.2 |
| 5 ms | A | async | 100.0 | 6852 | 97.1 |
| 5 ms | A | async_win | 100.0 | 2004 | 96.8 |
| 5 ms | B | async | 100.0 | 6831 | 97.4 |
| 5 ms | B | async_win | 100.0 | 1987 | 97.0 |
| 20 ms | A | async | 100.0 | 6854 | 97.0 |
| 20 ms | A | async_win | 100.0 | 1999 | 97.3 |
| 20 ms | B | async | 100.0 | 6860 | 97.4 |
| 20 ms | B | async_win | 100.0 | 1993 | 97.8 |

It reproduces v5. Chunked delivery reads 84 to 87% with no grace period and 100% after
5 ms. The first query stays at 96.8 to 99.2 us in every cell, so the shortfall is landing
time, not lost pages. tools/paper_refresh_claims.py (claim s3-grace) asserts both
statements from these files.
