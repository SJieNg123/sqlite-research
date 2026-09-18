# unified_v5 — one batch, one code version, every local axis (2026-09-18)

33,270 rows, seeds 1 to 10, zero failures, `cold_pct` max **0.000** with zero exclusions.
Window 2026-09-18T03:03:12Z to 07:14:15Z.

## Why it was run

Two reasons, one from the advisor and one from the goal of cross-table comparability.

**The advisor asked for a stronger `Dump` baseline.** The question was whether issuing one
`posix_fadvise(WILLNEED)` or `readahead(2)` over the whole file beats 4400 per-page hints that
cost 7 ms. It does not, and the reason is a kernel window. One range hint delivers
`min(range_pages, W)` pages from the head of the range and returns 0 either way, where
`W = read_ahead_kb / page_size` = 128 KB / 4096 = 32. Chunking the hint to exactly that window
is the version that works. This batch measures both, as arms `async_bulk` (one uncapped hint
per range, the naive reading of the suggestion) and `async_win` (one hint per 32-page chunk,
the strong version).

**`unified_v4` left three seams.** It covered `orig` only, so the layout paragraph at
`main.tex:505` carried an explicit non-comparability disclaimer, `layers_92` came from
`unified_v2`, and the `C_hit` control sat in its own batch. This batch runs all of it in one
window at one code version, so every absolute microsecond in the paper can be quoted against a
shared baseline.

## Scope

| family | cells | strategies | arms |
|---|---|---|---|
| A: headline | `A,B,C,C_hit` × `orig` × seeds 1-10 | 14 | pread, async, async_win, async_bulk, baseline |
| B: delivery order | `A,B,C,C_hit` × `orig` × seeds 1-10 | `lp_sorted`, `lp_shuf` | pread only |
| C: layout and size | `A,B,C` × `vacuum,ta,1gb` × seeds 1-10 | 8 | pread, async, baseline |

Resulting coverage: `orig` 244 cells over 17 strategies and 5 arms, each of `vacuum`, `ta` and
`1gb` 51 cells over 9 strategies and 3 arms. Every seed produced exactly 3327 raw rows.

`lp_sorted` and `lp_shuf` are pread-only by construction. Their page set is byte-identical to
`2f_slru` and they differ only in pread order, and the `coalesce` path qsorts offsets, which
would silently make the two identical. `run_experiment.py` now raises on the combination
rather than warning.

The coalesced arms run on `orig` only. What they vary is hint geometry, the layout axis does
not vary it, and every layout and size claim in the paper is stated under the plain `async`
arm.

## Code version: read this before quoting provenance

`batch.log` line 2 records `HEAD: b0edb8c`. **That line is wrong.** The batch ran with the
warmer and harness changes uncommitted in the working tree. The exact tree that produced these
numbers was committed immediately afterwards as **`fea7c51`**, with only the 6 code files
staged and no results files. `b0edb8c` does not contain the `async_win` or `async_bulk` arms at
all, so the discrepancy is self-evident rather than subtle, but it is recorded here because
the log cannot be edited after the fact without destroying its value as a log.

## Integrity

- 33,270 rows, 10 seeds × 3327, zero failed cells.
- `cold_pct` max 0.000 across every row, zero exclusions. The cold-clear helper held for the
  whole 4.18 h window.
- Throughput 0.289 s per row against `unified_v4`'s 0.296, so the machine was in the same
  performance regime.
- The 4.18 h window includes a 1.4 h idle gap between the seed-1 pilot and the full run. The
  measured portion is closer to 2.8 h.

### Drift

`2f_slru` under `async` is the established anchor. Spread of `first_query_us` between the
first and last seed measured:

| workload | spread across the window |
|---|---|
| A | 1.5% |
| B | 2.0% |
| C | 2.6% |
| C_hit | 4.1% |

All well inside the 10 to 15% between-session figure the paper quotes, so cells from opposite
ends of this batch are comparable.

### Cross-batch reproduction

v5 reproduces v4 seed for seed on the shared cells, for example A seed01 499.9 to 497.8, B
seed08 587.1 to 584.1, A seed04 1019.9 to 1023.8.

One thing that looks like a defect and is not: the seed01 `A` baseline is 497.8 µs while seeds
2 to 10 run 828 to 1024 µs. Seed01 is a genuine workload-instantiation outlier, not drift, and
v4 shows the same outlier at the same seed. Any cross-seed aggregate of `A` absolutes will
therefore sit well above the seed01 number that `compare_unified_v4.py` prints.

## Result 1: the delivery mechanism is a separate axis from the strategy

Workload A, medians over 10 seeds, `orig`:

| strategy | arm | deliver_us | ranges | delivery_pct | first_query_us |
|---|---|---|---|---|---|
| `2f_slru` (Dump, 4400 pages) | pread | 18112.3 | — | 100.0 | 97.3 |
| `2f_slru` | async | 7088.2 | — | 100.0 | 98.5 |
| `2f_slru` | **async_win** | **2020.3** | 138 | 88.3 | 98.0 |
| `2f_slru` | async_bulk | 80.5 | 2 | **1.4** | **771.6** |
| `2e_K10` (ours, small) | pread | 2533.9 | — | 100.0 | 504.0 |
| `2e_K10` | async | 101.0 | — | 100.0 | 474.1 |
| `2e_K10` | **async_win** | **35.8** | 23 | 100.0 | 473.6 |
| `2e_K10` | async_bulk | 35.5 | 23 | 100.0 | 472.7 |

Three things follow.

1. **Window chunking is a real 3.4× cut in delivery cost** for a large set, 7088 µs to 2020 µs,
   and it costs nothing in first-query latency.
2. **The naive bulk hint genuinely fails.** 1.4% delivered on a 4400-page set, because the
   kernel honours only the first 32 pages of each of the 2 hints issued, and `first_query_us`
   pays for it, 772 µs against 98.
3. **The mechanism only matters when there is a lot to deliver.** For `2e_K10` the ranges are
   already at or under the 32-page window, so `async_win` and `async_bulk` are the same
   measurement, 35.8 against 35.5 µs. Targeted prefetch is nearly insensitive to the delivery
   mechanism precisely because its whole point is delivering little.

## Result 2: the strong baseline closes most of the gap and reverses one workload

Same-arm comparison, so both sides get the identical delivery mechanism. Ratio is our best
strategy over `Dump` on absolute `e2e_warm`, below 1 means we win. Per-seed medians, n=10.

| workload | ours | arm `async` ratio | arm `async_win` ratio | seeds we win under `async_win` |
|---|---|---|---|---|
| A | `2e_K10` | 0.08× | **0.25×** | 10/10 |
| B | `2f_top14` | 0.09× | **0.27×** | 10/10 |
| C | `2e_K10` | 0.32× | **0.62×** | 6/10 |
| C_hit | `2f_top28` | 0.44× | **1.05×** | 2/10 |

As effects against the same-seed baseline, median of per-seed medians:

| workload | Dump pread | Dump async | Dump **async_win** | Dump async_bulk | our best, `async_win` |
|---|---|---|---|---|---|
| A | +1996.9% | +720.5% | **+147.0%** | −3.8% | `2e_K10` −38.6% |
| B | +1812.9% | +652.0% | **+122.0%** | −3.3% | `2f_top14` −40.8% |
| C | +203.6% | −3.7% | **−65.6%** | −9.2% | `2e_K10` −77.0% |
| C_hit | +371.6% | +57.2% | **−47.4%** | −17.3% | `2f_top28` −44.4% |

So the honest reading is that the advisor's suggestion, in its strong form, is a large
improvement to the baseline that the paper had dismissed at `main.tex:222` as outside scope.
It does not overturn the targeted-prefetch claim on A and B, where reading everything still
costs 2 ms of I/O for pages nobody needs and loses by 4×. It narrows C from 3.1× to 1.6×. And
on `C_hit` it wins outright.

`C_hit` losing is mechanically sensible. It is the pure-hit tail control, so the question of
*which* pages to fetch matters least there, and once delivery is cheap enough, fetching all of
them wins.

### The C result is bimodal and that is the more important caveat

Per-seed `e2e_warm_us` on C, sorted:

```
2e_K10 / async_win   194 195 196 196 197 197 | 580 593 650 658
Dump   / async_win   308 310 312 314 317 317   321 329 371 371
```

Our strategy is either much better than `Dump` or clearly worse, depending on the seed, while
`Dump` under the strong arm is uniform. The median favours us, 6 seeds out of 10 favour us, and
the variance does not. This is a strategy-selection instability on the tail workload, and it is
a more substantive finding than the median comparison.

## Delivery_pct is not a fair metric across these arms

`async_win` reads 88.3% on A and 68 to 83% on A and B at the per-cell level, against 100% for
the per-page `async` arm. That is not lost pages. `delivery_pct` is sampled by `mincore` with
deliberately zero grace, as `pipeline/engine/benchmark_harness/benchmark_harness.c:1455` states,
so what it measures is how much asynchronous readahead has *completed* by that instant, which
scales with how long the arm spent issuing. The per-page arm scores 100 partly because it is
slow enough for its own readahead to finish.

Five milliseconds of grace takes `async_win` to 100.0 on both workloads and 20 ms adds nothing,
with `deliver_us` flat and `first_query_us` flat at about 100 µs throughout. Full evidence in
[`grace_check/README.md`](grace_check/README.md).

The batch itself ran at the default `--deliver-sleep-ms 0`, unchanged from every prior batch,
so the cells shared with `unified_v4` stay protocol-identical.

Practical consequence: comparisons between `async` and `async_win` must use `first_query_us` and
`e2e_warm_us`, never `delivery_pct`. The 1.4% that `async_bulk` reads is a different thing and
is a real failure, confirmed by its 772 µs first query.

## What moved against the paper

From `tools/compare_unified_v4.py --batch results/unified_v5`, on the shared `async` cells:

| table | cell | before | after |
|---|---|---|---|
| `tab:competitive` | C `2f_top500` | −13% | −4%, now a tie |
| `tab:competitive` | A `2f_slru` | +762% | +769% |
| `tab:competitive` | B `2f_slru` | +730% | +722% |
| `tab:ablation` | `leaf_rand_K10` e2e_warm | 7% worse | 8% worse, now robust |
| `tab:ablation` | `2e_K10` | bimodal | robust |
| `tab:seeds` | all cells | — | reproduce |

No sign flips on the shared cells.

## The layout seam is closed

Seed01 reproduces the Default and Clustered pair that `main.tex:505` quotes, confirming that
the paper's "Clustered" is the `ta` key:

| workload | paper Default/Clustered | v5 Default/Clustered |
|---|---|---|
| A | 452 / 523 | 441 / 512 |
| B | 509 / 701 | 481 / 671 |
| C | 265 / 317 | 256 / 304 |

Because `orig`, `vacuum`, `ta` and `1gb` now share one batch, the non-comparability disclaimer
in that paragraph no longer has a premise.

## Files

- `seed{01..10}/raw.csv` — 3327 rows each, the per-rep measurements, merged from the three
  families. Carries the new `parse_us`, `ranges` and `ts` columns.
- `seed{01..10}/summary.csv` — 389 rows each, per-cell aggregates.
- `summary.csv` — 3890 rows, all seeds merged with a prepended `seed` column.
- `uncertainty.csv` and `uncertainty.md` — 1128 rows, bootstrap 95% CIs from
  `tools/stats_uncertainty.py`.
- `seed{01..10}/{main,lp,layout}/` — the three per-family invocations the merge was built
  from, each with its own `env.txt`. Kept rather than ignored because they record which
  invocation produced which rows. The merge is lossless, families and merged both 3327 rows.
- `batch.log` — the run log. **Not tracked**, per the repo-wide `*.log` rule, same as
  `unified_v4`'s. See the code-version note above, which is why that note lives here.
- `grace_check/` — the side diagnostic on `delivery_pct`.

There is deliberately no cross-seed `raw.csv`. `tools/stats_uncertainty.py` pools the per-seed
files by design, and a merged one would be 4 MB of duplicate with a schema no consumer wants.

## Status

Supersedes `results/unified_v4` for every `orig` claim, and additionally covers the
`vacuum`/`ta`/`1gb` layout and size axes, `layers_92`, and the full `C_hit` set, none of which
`unified_v4` ran. See `results/RESULT_PROVENANCE.md` §4.2.
