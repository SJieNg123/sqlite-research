# unified_v6 — one batch, one committed code version, no coverage gap (2026-09-23)

39,390 rows, seeds 1 to 10, zero failures, `cold_pct` max **0.000** with zero exclusions.
One continuous window 2026-09-23T01:54:17Z to 05:11:34Z, 3.29 h.

**Supersedes `results/unified_v5` for every claim.** It reproduces v5 on all 376 shared cells
with a median move of 1.8 points and no substantive sign flip, and it adds the one axis v5
was missing.

## Why it was run

`unified_v5` ran the `2f_topN` (`Dump-N`) family on `orig` only, on the reasoning that no
claim needed it elsewhere. That was wrong for the database-size paragraph at `main.tex:553`,
whose "Skel+500 from -31% to +35%" clause cannot be checked without `Dump-500` at `1gb`.

The alternative was to run those cells as an addendum. That would have placed them in a
different machine state, so their absolute microseconds could not be quoted alongside any
other table, which is the exact seam this line of batches exists to remove. Re-running the
whole matrix in one window was the only option that keeps every table mutually comparable.

Two defects of v5 are also fixed here. The window is continuous, where v5's spanned a 1.4 h
idle gap between its pilot and its full run. And the code was committed before launch, so the
`HEAD: f570d4c` line in `batch.log` is true, where v5's recorded a commit that did not contain
the arms it was measuring.

## Scope

| family | cells | strategies | arms |
|---|---|---|---|
| A: headline | `A,B,C,C_hit` × `orig` × seeds 1-10 | 14 | pread, async, async_win, async_bulk, baseline |
| B: delivery order | `A,B,C,C_hit` × `orig` × seeds 1-10 | `lp_sorted`, `lp_shuf` | pread only |
| C: layout and size | `A,B,C` × `vacuum,ta,1gb` × seeds 1-10 | **12** | pread, async, baseline |

Coverage: `orig` 244 cells over 17 strategies and 5 arms, each of `vacuum`, `ta` and `1gb`
**75 cells over 13 strategies** and 3 arms. v5 had 51 cells and 9 strategies on those three.
Every seed produced exactly 3939 raw rows and 461 summary rows.

The difference from v5 is family C's strategy list and nothing else. Reps, arms, workloads,
seeds and the cold gate are untouched, which is what makes the v5 to v6 comparison a clean
drift check rather than a confound.

`lp_sorted` and `lp_shuf` stay pread-only by construction. Their page set is byte-identical to
`2f_slru` and they differ only in pread order, and the `coalesce` path qsorts offsets, which
would silently make the two identical. `run_experiment.py` raises on the combination.

The coalesced arms stay on `orig` only. What they vary is hint geometry, the layout axis does
not vary it, and every layout and size claim is stated under the plain `async` arm.
`learned_markov` also stays `orig` only: it needs LOSO training per layout and no claim places
it outside `orig`, so adding it would be cost without a consumer.

## Prerequisite

`tools/gen_freqdump_layouts.sh` built the 360 frozen `Dump-N` hotsets this batch needed,
3 workloads × 3 layouts × 4 budgets × 10 seeds, using the same generator, argument order and
output naming as the `orig` files in `tools/competitive_baseline.sh`. Measured at 0.65 s per
file, 2m27s for all 360, zero failures. Pure replay with no cold-clear.

## Integrity

- 39,390 rows, 10 seeds × 3939, zero failed cells.
- `cold_pct` max 0.000 across every row, zero exclusions.
- Throughput 0.301 s/row against v5's 0.289 and v4's 0.296, so the same performance regime.
- The window is continuous. No idle gap.

### Drift

`2f_slru` under `async` is the established anchor. Spread of `first_query_us` across the window:

| workload | v6 | v5 |
|---|---|---|
| A | 1.9% | 1.5% |
| B | 0.7% | 2.0% |
| C | 4.6% | 2.6% |
| C_hit | 1.8% | 4.1% |

All well inside the 10 to 15% between-session figure the paper quotes.

### Reproduction of unified_v5

376 shared cells compared on the `e2e_warm` effect against the same-seed baseline. **Median
absolute move 1.8 points.** Eight cells change sign, every one of them sitting within 4% of
zero (`leaf_freq_K10` and `leaf_rand_K10` under the coalesced arms, `2e_K500` on `1gb`,
`layers_5` on `1gb`). No headline result moves.

The delivery-arm result reproduces to within a few points:

| Dump under | A v6 (v5) | B v6 (v5) | C v6 (v5) | C_hit v6 (v5) |
|---|---|---|---|---|
| pread | +1955 (+1997) | +1895 (+1813) | +204 (+204) | +375 (+372) |
| async | +706 (+720) | +672 (+652) | −9 (−4) | +52 (+57) |
| **async_win** | **+131** (+147) | **+122** (+122) | **−66** (−66) | **−48** (−47) |
| async_bulk | −3 (−4) | −2 (−3) | −9 (−9) | −17 (−17) |

## Result 1: the gap this batch closed

`Dump-N` across layout and size, `e2e_warm` effect vs the same-cell baseline, Tail-Mixed:

| strategy | orig | vacuum | ta | **1gb (10×)** |
|---|---|---|---|---|
| `Skel` | −38 | −38 | −32 | **−50** |
| `Skel+10` | −71 | −76 | −63 | **−80** |
| `Skel+500` (`2e_K500`) | −29 | −43 | −10 | **−32** |
| `Dump-14` | −71 | −76 | −69 | −50 |
| `Dump-500` | −9 | −39 | +5 | **−30** |
| `Dump` | −9 | −41 | +7 | **+30** |

This settles `main.tex:553`. Its clause "Dump goes from −9% to +139% and Skel+500 from −31% to
+35%" has an **exactly correct** −9% starting point for `Dump`, a 10× endpoint of +30% rather
than +139%, and a `Skel+500` clause that fails under either reading: `2e_K500` is −29% to −32%
and `Dump-500` is −9% to −30%, both improving rather than regressing.

Delivery cost on Tail-Mixed from `orig` to `1gb`: `Dump` 749 to 1534 µs (**2.05×**, the
paper's "doubles" is exact), `Skel+500` 454 to 686 (1.51×), `Skel` 67.5 to 72.5 (**1.07×**).
The skeleton barely grows, which is why targeted prefetch improves at scale.

## Result 2: delivery is an axis separate from selection

Workload A, `orig`, cross-seed medians:

| strategy | arm | deliver_us | delivery_pct | first_query_us |
|---|---|---|---|---|
| `2f_slru` (Dump, 4400 pages) | async | 6982 | 100.0 | 97 |
| `2f_slru` | **async_win** | **1937** | 83.5 | 97 |
| `2f_slru` | async_bulk | 80 | **1.4** | **764** |
| `2e_K10` (ours, small) | async | 98 | 100.0 | 488 |
| `2e_K10` | **async_win** | **33** | 100.0 | 502 |

Window chunking is a 3.6× cut in delivery cost for a large set at no cost in first-query
latency. The naive bulk hint genuinely fails, 1.4% delivered because the kernel honours only
the first 32 pages of each hint. For `2e_K10` the ranges already sit at or below the window,
so chunking barely matters. **A mechanism that makes delivery cheap helps whoever was
delivering the most.**

Head to head with the mechanism held fixed, using the Skel family alone as ours:

| workload | ours | Dump | ratio | seeds we win |
|---|---|---|---|---|
| A | Skel −35% | +131% | 0.27× | 10/10 |
| B | Skel −38% | +122% | 0.28× | 10/10 |
| C | Skel+10 −78% | −66% | 0.62× | 6/10 |
| C_hit | Skel −38% | −48% | **1.15×** | 1/10 |

The pure-hit control is the one workload where the full dump wins, which is expected where
every query hits and the question of which pages to fetch carries least weight.

## Result 3: two layout claims fail, in both batches

- **`main.tex:505`'s "baseline raised by 26%" is wrong.** Clustered *lowers* the cold baseline
  on every workload: 881/920/910 µs on Default against 802/812/835 on Clustered. v5 gave
  879/956/911 against 788/806/854. `vacuum` is the layout that raises it, to 985/1034/1147.
- **"In no cell does Clustered beat Default" is wrong.** Paired per seed over 36 cells,
  Clustered wins 12, most clearly Tail-Mixed `Skel-92` at **0.90× on 10 of 10 seeds** in both
  batches.
- The interior page count claim, 4 pages to 48 on Tail-Mixed, **reproduces exactly** from the
  frozen hotsets.
- New here: with `Dump-14` now available on Clustered, the Tail-Mixed layout comparison is a
  **tie** at seed 1, 253 versus 253 µs, rather than a Default win.

## `delivery_pct` is not a comparable metric

It is `mincore` sampled with deliberately zero grace, so it measures how much asynchronous
readahead has *completed*, which scales with issue duration. `async_win` reads 83.5% on A and
100% on C while delivering every page. The same artifact appears across layouts: a 500-page
scattered set reads 20 to 57% on the reordered layouts, and one such cell moved from 100% to
57% between v5 and v6 under identical code. Use `first_query_us` and `e2e_warm_us` instead.

The grace-period evidence is in `results/unified_v5/grace_check/`, run under the same code but
not repeated inside this window. It is the only number cited in the drafts that is not from
this batch, and it is a mechanism check rather than a reported result.

## Files

- `seed{01..10}/raw.csv` — 3939 rows each, per-rep measurements merged from the three families.
- `seed{01..10}/summary.csv` — 461 rows each, per-cell aggregates.
- `seed{01..10}/{main,lp,layout}/` — the three per-family invocations the merge was built from,
  each with its own `env.txt`. Kept because they record which invocation produced which rows.
  The merge is lossless, families and merged both 3939 rows.
- `summary.csv` — 4610 rows, all seeds merged with a prepended `seed` column.
- `uncertainty.csv` and `uncertainty.md` — 1344 rows, bootstrap 95% CIs from
  `tools/stats_uncertainty.py`. **Pass seed directories, not `raw.csv` paths**: the tool labels
  each input by `Path.stem`, so a glob of `seed*/raw.csv` collapses all ten to one label and
  silently reports `n_seeds=1` with no CIs.
- `batch.log` — the run log. Not tracked, per the repo-wide `*.log` rule.

There is deliberately no cross-seed `raw.csv`. `tools/stats_uncertainty.py` pools the per-seed
files by design, and a merged one would be duplicate with a schema no consumer wants.

## Status

Supersedes `results/unified_v5` entirely, and through it `unified_v4`, `unified_v2`,
`tiebreak_fix`, `size_1gb` and the standalone `C_hit` batch. Not for the `aging`, `churn`,
`cadence` or `ram_pressure` axes, which use other subcommands, and not for OpenWhisk or Lambda.
See `results/RESULT_PROVENANCE.md` §4.2.
