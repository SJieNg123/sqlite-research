# Grace-period check: is `async_win`'s delivery shortfall lost pages or landing time?

Side diagnostic for `results/unified_v5`, run 2026-09-18 between seed01 and seed02
of the same batch, same code version, same machine state.

## The question

The `async_win` arm issues one `posix_fadvise(WILLNEED)` per 32-page chunk, 32 being
`read_ahead_kb / page_size` = 128 KB / 4096, the largest hint this kernel honours in
full. On the 4400-page `2f_slru` set it cuts delivery cost from about 6.8 ms to about
2.0 ms, a 3.4x reduction.

But the batch reads `delivery_pct` of only 68 to 83 percent for `async_win` on A and B,
where the plain per-page `async` arm reads 100. Taken at face value that says chunking
loses a fifth of the pages, which would undercut the whole point of the arm.

It does not. `delivery_pct` is `mincore` sampled at a fixed point with deliberately no
grace period, as `pipeline/engine/benchmark_harness/benchmark_harness.c:1455` states:
"hotset residency immediately before the first query (~us mincore, so async readahead
gets no meaningful extra time to land)". `POSIX_FADV_WILLNEED` is asynchronous, so what
that sample measures is how much readahead has completed by then, which depends on how
long the arm spent issuing. The per-page arm scores 100 partly **because** it is slow:
4400 separate calls occupy 6.8 ms, during which its own readahead finishes.

## Method

`--deliver-sleep-ms` already exists for this question and is what the sleep experiment
in `paper/main.tex:224` used. It inserts a sleep between hint dispatch and the first
query, after the warmer's timed section, so `deliver_us` is unaffected by construction.

```
run_experiment.py run --seed 1 --db orig --workload A,B --strategy 2f_slru \
  --no-baseline --pread-reps 0 --async-reps 3 --async-win-reps 3 \
  --deliver-sleep-ms {0,5,20} --outdir /tmp/v5_sleep{0,5,20}
```

n=3 kept reps per cell, medians below.

## Result

| sleep | wl | arm | delivery\_pct | deliver\_us | first\_query\_us |
|---|---|---|---|---|---|
| 0 ms | A | async | 100.0 | 6838.7 | 103.9 |
| 0 ms | A | async\_win | **82.6** | 2004.5 | 100.6 |
| 0 ms | B | async | 100.0 | 6768.1 | 103.2 |
| 0 ms | B | async\_win | **68.1** | 1933.6 | 100.5 |
| 5 ms | A | async | 100.0 | 6797.1 | 97.8 |
| 5 ms | A | async\_win | **100.0** | 1985.7 | 97.6 |
| 5 ms | B | async | 100.0 | 6825.8 | 100.1 |
| 5 ms | B | async\_win | **100.0** | 1990.2 | 97.2 |
| 20 ms | A | async\_win | 100.0 | 1988.4 | 99.7 |
| 20 ms | B | async\_win | 100.0 | 2003.4 | 101.7 |

Five milliseconds of grace takes `async_win` to 100.0 on both workloads. Twenty adds
nothing. `deliver_us` is flat at about 1990 across all three sleeps, confirming the
sleep sits outside the timed section.

## What follows

1. **The shortfall is landing time, not lost pages.** Every chunked hint is honoured in
   full, which is what the standalone `residency_checker` sweep also found, because that
   sweep samples residency from a separate process after the warmer exits and so already
   includes a few milliseconds of grace.
2. **`delivery_pct` is not a fair metric across arms that differ in issue duration.** It
   conflates "were the pages delivered" with "has the asynchronous I/O finished yet",
   and the second term scales with how long the arm took to issue. Comparisons between
   `async` and `async_win` must use `first_query_us` and `e2e_warm_us`.
3. **The outcome metric is untouched either way.** `first_query_us` is about 100 us for
   both arms at every sleep value, so the pages still in flight at the zero-grace sample
   land during query setup and cost nothing. The 3.4x cut in delivery cost is real and
   is not paid for in first-query latency.
4. **`async_bulk` is a different story and genuinely fails.** It reads 1.4 percent on A
   and B with `first_query_us` of 326 to 393 us against about 97. That is not landing
   time, it is the kernel honouring only the first 32 pages of each of the 2 hints it
   issues. See the batch README.

The main batch therefore runs at the default `--deliver-sleep-ms 0`, unchanged from every
prior batch, so the shared cells stay protocol-identical to `results/unified_v4`. This
directory is the record of why the zero-grace `delivery_pct` for `async_win` should be
read as a measurement artifact rather than a result.
