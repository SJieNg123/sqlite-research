# unified_v3 — single-batch matrix for Figures 13 & 14 (2026-09-14)

One run, one machine state, every arm. This batch exists to remove the
two-source split that Figures 13 and 14 previously had to work around.

## Why it was run

Figure 13 needed five strategy arms; Figure 14 could only show three of them.
The reason was provenance, not plotting: the corrected frequency-ranked arms
(`2e_K10`, `2e_K500`) lived in `results/tiebreak_fix`, a different machine-state
batch from `results/unified_v2`, and Figure 14 stacks **absolute** microseconds,
which may not mix batches. Neither existing batch could supply all five arms:

| batch | all arms? | corrected tie-break? |
|---|---|---|
| `unified_v2` | yes | **no** — `2e_K*` impact-set cells are pre-fix (leaky) |
| `tiebreak_fix` | **no** — no `layers_5`, no `2d` | yes |

`unified_v3` has both.

## Scope

```
run_experiment.py run --workload A,B,C --db orig \
  --strategy layers_5,2d,2e_K10,2e_K500,2f_slru \
  --outdir results/unified_v3/matrix
```

A/B/C x orig x {baseline, layers_5, 2d, 2e_K10, 2e_K500, 2f_slru};
arms baseline/async/pread; reps pread 5+1, async 10+1, baseline 10+1
(same protocol as `unified_v2`). 33 summary rows.

Traces: `workloads/workload_{a,b,c}_1.txt` — byte-identical to the
`workload_{a,b,c}.txt` that `unified_v2` used (renamed into the seed-1
namespace by commit `dfc7f25`; sha256 `d8ff6a5d…` / `11edb4e3…` / `ddf83aee…`).

## Single-batch evidence

- `matrix/env.txt` is a **single line** shared by all 33 rows.
- One contiguous window: 2026-09-14T02:35:28Z -> 02:36:53Z (85 s).
- Cold gate clean: `cold_pct_max = 0.0` on every cell, nothing excluded.
- Baseline and the `2f_slru` anchor are measured inside the batch.

```
ENV kernel=6.17.0-41-generic disk=nvme2n1 ra_kb=128 governor=powersave
    driver=amd-pstate-epp epp=balance_performance boost=1 maxfreq_khz=5756452
    thp=madvise loadavg=0.09 memavail_kb=19354184
```

## Corrected tie-break, verified by delivered page set

The run's delivered hotsets were compared against both the current (corrected)
and the archived pre-fix hotsets. File hashes are not comparable across the two
formats — the run writes `(page_number, file_offset)`, the source is
`(page_number, is_resident)` — so the **page sets** were compared:

| cell | delivered | == corrected | == legacy |
|---|---|---|---|
| C `2e_K10` | 14 pages | yes | no |
| B `2e_K10` | 28 pages | yes | no |
| A `2e_K500` | 518 pages | yes | no |

## Reproduction of the prior result: no conclusion moved

Relative (paired vs same-batch baseline) values against the per-cell canonical
sources they replace (`unified_v2` + `tiebreak_fix`):

| metric | max \|delta\| | sign flips |
|---|---|---|
| first-query | 2.4 pt (A `2e_K10`) | **0 / 15** |
| warm e2e | 6.4 pt (B `2e_K500`, +79% -> +85%) | **0 / 15** |

Borderline cells held: Tail-Mixed `layers_5` is still a warm-e2e regression
(+3%), Scattered-Zipf/Uniform-100K `layers_5` still -14%/-34%, and the corrected
arms reproduced (Tail-Mixed `2e_K10` first-query -82.8% -> -83.1%, warm e2e
-75.3% -> -75.7%).

## Absolute microseconds moved — do not mix with unified_v2

Everything is faster, in the additive-CPU-path shape that `CANONICAL_SWAP.md` §1
describes (I/O-bound baseline barely moves; the ~100 us CPU path moves most):

| | unified_v2 | unified_v3 | delta |
|---|---:|---:|---:|
| baseline fq (A/B/C) | 523 / 749 / 1087 | 503 / 733 / 1072 | -3.9% / -2.1% / -1.3% |
| `2f_slru` fq (A/B/C) | 108 / 107 / 102 | 98 / 100 / 97 | -9.3% / -6.8% / -4.9% |
| **cold open** | ~230 | **~179** | **-22%** |

The cold-open drop is the largest single change and is the one that reaches the
paper's `e2e_std` claims.

Machine-state notes: the kernel moved 6.17.0-19 -> 6.17.0-41; `disk` reads
`nvme2n1` rather than `nvme0n1`, but both are the same model (KINGSTON
SKC3000D 2 TB) and the repo lives on `/home` = `nvme2n1`, so this is most likely
NVMe renumbering across the upgrade rather than different media; `epp` reads
`balance_performance` rather than `performance` — `env.sh` **records** EPP but
never pins it (it only attempts the governor, and only when writable), so EPP is
an uncontrolled variable by design.

## Status

**Superseded 2026-09-17 by `results/unified_v4`.** This batch was canonical for
Figures 13 and 14 from 2026-09-14, and from 2026-09-15 for Section 5's
single-instantiation numbers. It was replaced because it covers only five
strategy arms at one seed, so the paper's four result tables still had to draw
their cross-seed columns from `ablation_comp_v2`, `competitive`, `seeds` and
`tiebreak_fix/seeds` — five batches across two code versions. `unified_v4` runs
all twelve arms over ten seeds in one window, which closes that split. Its
relative values reproduce this batch with no sign flips. Kept as the record of
the 2026-09-14/15 propagation and as a second machine state for the cold-open
drift documented in `results/unified_v4/README.md`.

Cross-seed results (`seeds`, `tiebreak_fix/seeds`, `competitive`,
`ablation_comp_v2`, `c_hit*`, `aging_v2`) and other-axis results
(`ram_pressure`, `cadence`, `size_1gb`) are **not** affected and cannot be
folded into a single batch by construction.

## Known gap

`run_experiment.py run --verify-frozen` reports 13 changed hotsets and 3 missing
workload files against the freeze manifest. Both are stale-manifest artifacts,
not data problems: the manifest's expected hashes match the archived pre-fix
files in `strategies/access/runs/legacy_same_trace_first_seen_tiebreak/`, and
the "missing" workloads are the seed-1 rename above. The manifest has not been
re-frozen since the 2026-07 tie-break fix. Re-freeze it if this batch is
promoted further.
