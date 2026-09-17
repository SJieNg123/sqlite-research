# unified_v4 — one batch, one code version, for all four main tables (2026-09-17)

Ten seeds, one contiguous window, one machine state, every arm the paper's four
main tables need. This batch exists to remove a provenance split that the tables
had carried since the tie-break fix.

## Why it was run

An audit of `tab:e2e-ac`, `tab:ablation`, `tab:competitive` and `tab:seeds` found
the twelve printed cells drawing on **five batches across two code versions**:

| table | sources before this batch |
|---|---|
| `tab:e2e-ac` | `unified_v3` (post-fix) for absolutes, plus `stats` / `competitive` / `ablation_comp_v2` for the verdict column |
| `tab:ablation` | `ablation_comp_v2` (post-fix) |
| `tab:competitive` | `competitive` (**pre-fix**) for A and B, `ablation_comp_v2` for most of C, `competitive` again for C `Dump-500` |
| `tab:seeds` | `unified_v3` single, `tiebreak_fix` for two cross-seed cells, `stats` (**pre-fix**) for the other six |

Two concrete defects followed from the mixing, and both are closed by this batch:

1. Scattered-Zipf-100K `Skel+10` cross-seed printed as **-36%** in `tab:seeds`
   and **-38%** in `tab:competitive`, and the prose quoted both within adjacent
   paragraphs. Here both read **-38% [-52,-24]**, because they are now one number.
2. Tail-Mixed `Dump-500` and `Dump` deliver a **byte-identical 483-page hotset**,
   yet printed -13% and -7%, a six point gap for the same page set. Here they read
   **-9% [-13,-5]** and **-10% [-14,-5]**, a one point gap with overlapping CIs.

## Scope

```
tools/run_unified_v4.sh 1 2 3 4 5 6 7 8 9 10
  -> run_experiment.py run --seed <s> --db orig --workload A,B,C \
       --strategy layers_5,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,\
                  2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10 \
       --outdir results/unified_v4/seed<ss>
```

A/B/C x orig x {baseline + 11 strategies}, arms baseline/async/pread, reps
pread 5+1, async 10+1, baseline 10+1. Per seed: 595 raw rows, 70 summary rows.
Ten seeds, 5940 raw rows, zero failures.

`2e_K500`, `2f_top28` and `2f_top100` are not printed in the four tables. They are
carried so that Figures 13 and 14 and the Section 6.3 Dump-N sweep can be served
from this same batch rather than recreating the split later.

## Hotsets were reused, not regenerated

The frozen inputs are already corrected, so regenerating them would have changed
two things at once. `hot2e_*_seed*` was regenerated on 2026-07-11 after `de4490f`,
and `gen_freqdump.py` has ranked by `(-count, pageno)` since its first commit
`b64d10f` on 2026-06-29, so `2f_top*` was never affected by the tie-break bug.
Reusing them isolates machine state and harness version as the only variables.

Verified: `work/hotset_{A,C}_orig_{layers_5,2d,2f_slru}.csv` are **byte-identical**
to the same files in `results/unified_v3/matrix/work`.

## Single-batch evidence

- One contiguous window: 2026-09-17T07:23:00Z -> 07:52:21Z, about 3 minutes per seed.
- The `ENV` line is identical across all ten seeds apart from `loadavg` and `memavail_kb`.
- Cold gate clean: `cold_pct` max is **0.000** on all 5940 raw rows, nothing excluded.
- Baseline and the `2f_slru` anchor are measured inside the batch, per seed.
- `HEAD` at run time: `ee75df1`.

```
ENV kernel=6.17.0-41-generic disk=nvme2n1 ra_kb=128 governor=powersave
    driver=amd-pstate-epp epp=balance_performance boost=1 maxfreq_khz=5756452
    thp=madvise loadavg=0.06 memavail_kb=19415320
```

## Reproduction of the prior result: no conclusion moved

**Zero sign flips** across all four tables. Largest moves:

| table | cell | before | after |
|---|---|---|---|
| `tab:e2e-ac` | A `Skel-5` `e2e_ext` | 617 (+23%) | 581 (+16%) |
| `tab:e2e-ac` | C `Dump` `e2e_ext` | 1074 (+0%) | 1000 (-6%) |
| `tab:competitive` | C `Dump-500` | -13% [-17,-8] | -9% [-13,-5] |
| `tab:competitive` | B `Dump` | +730% [+644,+848] | +722% [+641,+827] |
| `tab:ablation` | `leaf_rand_K10` first-query | -1% [-2,1] | -2% [-4,-0] |

Every other cell moved by two points or less. The `leaf_rand_K10` row is the only
one whose statistical status changed: its first-query CI used to cover zero and
now just excludes it, at a magnitude of two percent that is still substantively
"random leaves do nothing".

The `verdict` column is unchanged arm for arm against `ablation_comp_v2`
(robust / robust / tie / robust). The words "bimodal" and "worse" in
`tab:ablation` are hand-written narrative, not tool output.

## Delivery loss is a result, not a defect

220 of 5610 non-baseline rows have `delivery_pct` below 99.9%. This is the
quantity the study measures. `delivery_pct` is the mincore residency of the hotset
taken immediately before the first query, and the harness comment at
`benchmark_harness.c:1454` states the measurement is deliberately taken with no
grace period, so `POSIX_FADV_WILLNEED` gets no extra time to land.

- Every one of the 24 cells printed in the four tables has `delivery_pct_median`
  of **100.0**, in this batch and in the batches it replaces.
- The loss is **seed-clustered and reproduces across batches and code versions**.
  A `Dump-500` collapses to **7.2%** at seed06 in both this batch and
  `results/competitive`, B `Dump-500` to **12.4%** at seed09 in both, and the
  seeds that are clean here are clean there.
- Four rows out of 5940 read 0.0%. Each is a different seed, workload and
  strategy, each has `deliver_us` near 350 microseconds so the warmer did run,
  and each has `cold_pct` of 0.00.

## Open item: the cold-open term is not controlled

`open_us` is **strategy dependent within this batch** and carries a **per-batch
offset that neither batch's own variance reveals**. This reaches `e2e_ext` and
`e2e_std` only. `e2e_warm` does not include the open and is unaffected.

Within seed01, `open_us` is tightly reproducible per cell across all 11 rep blocks,
yet differs by cell: A `Skel-5` sits at 142 to 149 in every block, C `Dump-100` at
71 to 131, while every other cell sits at 170 to 185. The mechanism is visible in
the harness: `sqlite_open` runs **after** `post_cold_script`, so a hotset that
covers the open path makes the open cheaper.

That does not explain the batch offset. A `Skel-5` measured 178.5 [171-182] in
`unified_v3` and 147.4 [142-149] here, both tight, with byte-identical hotsets, an
identical `ENV` line and identical code. The 36 microsecond drop in that cell's
`e2e_ext` sits entirely in `open_us`, since `deliver_us` moved 69.1 -> 69.9 and
first-query moved 365.8 -> 362.1. **Unexplained.** Treat `e2e_ext` and `e2e_std`
absolutes as carrying an uncontrolled cold-open term of roughly 30 microseconds
until this is resolved.

## Status

**Adopted 2026-09-17.** `paper/main.tex` now reads this batch for all four
tables (`tab:e2e-ac`, `tab:ablation`, `tab:competitive`, `tab:seeds`), for
`tab:ceiling`, for Figures 13 and 14, and for the Section 5 and 6 prose that
quotes their numbers. `RESULT_PROVENANCE.md` 4.2 names it canonical and
`PAPER_CLAIM_MANIFEST.csv` was regenerated against it: 132 claims, 111
independently recomputed from the CSVs, 0 fail.

Three things deliberately did **not** move to this batch, because it cannot
supply them: the Section 6 layout comparison (needs `vacuum`/`ta`), the
`layers_92` static-plan arm, and the Tail-Hit control (`c_hit`/`c_hit_v2`).
Each names its own batch in the text.

Other-axis results (`ram_pressure`, `cadence`, `size_1gb`, `c_hit*`, `aging_v2`)
are untouched and cannot be folded into this batch by construction.
