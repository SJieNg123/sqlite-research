# unified_v7 — one batch, one committed code version, no coverage gap (2026-10-08)

52,570 rows, seeds 1 to 10, zero failures, `cold_pct` max **0.000** with zero exclusions.
One continuous window 2026-10-08T14:13:38Z to 20:27:19Z, 6.2 h, with the batch code of 24e9496.
`batch.log` names HEAD a78aa8a, a local commit that added only the `tools/matched_budget.py`
change and was reorganized into the commits that publish this batch.

**Supersedes `results/unified_v6` for every claim.** It reproduces v6 on all 448 shared
cells (median move 1.2 points, no robust sign flip) and adds three axes v6 lacked.

## Why it was run

Three measurements the paper needed would otherwise have been addenda in another machine
state, which is the seam this line of batches exists to remove:

1. Family C (vacuum, ta, 1gb) also runs the window-chunked arm, so the 10x database and the
   layouts are measured under both delivery mechanisms.
2. Family D: `Dump-15` on Tail-Hit, the matched budget for `Skel+10` there
   (`results/matched_budget/PREREG.md`, whose rule applies here unchanged).
3. Family E: the profile-free whole-file baselines, window-chunked hints over all 26,331 pages
   (`whole_file` under `async_win`) and a synchronous `MAP_POPULATE` (`populate` arm), chosen
   by `results/pilot_whole_file_delivery` (one whole-file `readahead(2)` delivers 32 pages and
   gets no arm).

Since v6, `e2e_warm_us` charges `parse_us` to the coalesced arms (111b8ae), so the two
delivery mechanisms pay for the same work.

## Scope

| family | dir | cells | arms |
|---|---|---|---|
| A: headline | `main/` | `A,B,C,C_hit` × `orig` × 14 strategies | pread, async, async_win, async_bulk, baseline |
| B: delivery order | `lp/` | `A,B,C,C_hit` × `lp_sorted`, `lp_shuf` | pread only |
| C: layout and size | `layout/` | `A,B,C` × `vacuum,ta,1gb` × 12 strategies | pread, async, **async_win**, baseline |
| D: matched budget | `top15/` | `C_hit` × `2f_top15` | pread, async, async_win, async_bulk |
| E: whole file | `whole/` | `A,B,C,C_hit` × `whole_file` | **async_win, populate** |

Families B, D and E have no baseline of their own; they use family A's, same seed and window,
through the per-seed merge. Reps as v6: pread 5, async 10, async_win 10, async_bulk 5,
populate 10, baseline 10, each plus one dropped warmup. `whole_file` also carries the single
pread and async warmup that `run_experiment.py` always schedules; those rows are warmups and
never reach a summary. 5,257 raw rows and 581 summary rows per seed. Every invocation passed
`--discard-records`.

## Integrity

- 52,570 rows, 10 seeds × 5,257; every one of the 5,810 cells has its designed rep count.
- `cold_pct` max 0.000, zero exclusions, no missing first query.
- **Disk-stall check**: first queries above 3 ms are 0.05% of all rows (26 of 52,570), at most
  0.5% in any 10-minute bucket. unified_v6: 0.13%.
- **Per-seed consistency** (the check attempt 3 failed): the cold read of the hotset file
  (`parse_us`, `2d` window-chunked, A) is 62 to 63 us in every seed, and per-page `2d`
  dispatch is 86 to 90 us on A and 69 to 72 us on C_hit in every seed.
- Seeds 6 to 10 ran in about 30 minutes each against about 45 for seeds 1 to 5. The rows per
  seed and every per-seed value above are unchanged, and the batch's own read rate rose in
  step (855 to 1,298 MB per 30 s), so the time went out of the harness's overhead between
  measurements, most likely the system-wide cache drop, not out of what it measures.
- `diskstats.log` records nvme1n1 activity every 30 s; writes stayed at 15 to 28 MB per 30 s.

### Attempts 1 to 3 (not used)

Three earlier launches of this matrix were stopped or discarded.

- **Attempts 1 and 2**: the harness wrote a fresh 3.2 MB `ops-N.csv` and a `run-*.log` per run,
  about 16 GB per seed, onto the NVMe the batch measures. After a few hours cold first queries
  stalled for 4 to 9 ms: attempt 1 went from 0% of first queries above 3 ms in seeds 1-4 to
  25-64% in seeds 6-10; attempt 2 reached 7.9% in its third hour. `--discard-records`
  (24e9496) deletes those files as soon as the harness returns.
- **Attempt 3** (committed locally, then replaced before publishing): launched 40 minutes after deleting the
  210 GB of records the first two attempts left. Family A of seed 1, its first 20 minutes, read
  the hotset file in 94 us against 63 in every other seed and every other batch, adding about
  32 us to every prefetch arm's dispatch but not to the baseline. The batch-level checks passed;
  the per-seed check above was added because of it.

All three survive locally as `results/unified_v7_attempt{1,2,3}` (raw, summary, hotsets;
records deleted), are not tracked, and are not to be cited.

### Reproduction of unified_v6

448 shared cells, ten-seed mean effect against the same-seed baseline:

| metric | median move | robust sign flips |
|---|---|---|
| `e2e_warm_us` | 1.2 points | 0 |
| `first_query_us` | 0.6 points | 0 |
| `e2e_us` | 1.6 points | 0 |

Per seed, the median move is 3.1 points in seeds 1-5 and 2.8 in seeds 6-10. All 8 cells that
move more than 50 points (at most 1,070) are synchronous pread cells at 18 to 328 times the
baseline, and they move 0.4 to 5.3% in relative terms. Every hotset file is byte-identical to v6's (1,720 of
1,720); families D and E add 50.

## First look at the new cells

Ten-seed means, warm-process end-to-end change vs baseline, 95% CI:

| cells | SZ (A) | U (B) | TM (C) | TH (C_hit) |
|---|---|---|---|---|
| `whole_file`, window-chunked | +1711 [+1533, +1981] | +1668 [+1488, +1917] | +1537 [+1451, +1618] | +1670 [+1446, +1959] |
| `whole_file`, MAP_POPULATE | +12266 [+11010, +13983] | +11940 [+10609, +14031] | +10996 [+10317, +11661] | +11870 [+10414, +13635] |
| `Dump`, window-chunked (scale) | +200 | +187 | −54 | −27 |

Both whole-file baselines cut the first query by 88 to 90% and lose it all to dispatch.

On the 10x database the small sets read the same under both mechanisms (Skel −51 / −50% on A,
per-page / chunked); chunking shrinks the dump's regression (+499 / +109% on A) and turns
Tail-Mixed into a gain (+35 / −45%), still short of `Skel+10` there (−79 / −79%).

`Dump-15` and `Skel+10` on Tail-Hit: −30 / −29% per-page, −26 / −25% chunked; the paired test
is in `results/matched_budget/`.

## Files

- `seed{01..10}/{main,lp,layout,top15,whole}/` — the five per-family invocations, each with
  `raw.csv`, `summary.csv`, `env.txt`.
- `seed{01..10}/raw.csv`, `summary.csv` — the five families merged, 5,257 and 581 rows.
- `summary.csv` — 5,810 rows, all seeds with a prepended `seed` column.
- `uncertainty.csv`, `uncertainty.md` — 1,704 rows from `tools/stats_uncertainty.py`, seed
  directories as input.
- `batch.log`, `diskstats.log` — local only, per the `*.log` rule.

Launcher `tools/run_unified_v7.sh`, matrix `tools/unified_v7_matrix.sh`, input gate
`tools/check_unified_v7_inputs.sh`.
