# Figure Source Map (Phase 3)

Traceability for every figure referenced by `paper/main.tex`. Generated
2026-07-12. Root HEAD before Phase 3 `8a3f198`; paper HEAD before `db1095b`.

Generation environment: `/home/u03/.cache/coldstart-venv/bin/python`
(matplotlib 3.10.9, numpy 2.4.6). Root scripts write to `figures/out/`; the
paper submodule carries a copy under `paper/figures/`. Provenance authority:
[`results/RESULT_PROVENANCE.md`](../../results/RESULT_PROVENANCE.md).

## Figures referenced by the paper

| Figure | Paper label | Script | Output | Input source | Cell scope | Metric | Abs/rel | Status |
|---|---|---|---|---|---|---|---|---|
| 18 | `fig:capability` | `figures/18_capability_matrix.py` | `figures/18_capability_matrix.png` | none (hand-coded capability matrix) | prior-art positioning | qualitative ✓/◐/✗ | n/a | **no longer included by `paper/main.tex`** (PNG retained, byte-identical) |
| 1 | `fig:layout-distribution` | `figures/01_page_distribution.py` | `figures/01_page_distribution.png` | `pipeline/preparation/layout_rewriter/runs/classify_{before,vacuum,after}.csv` | static page-type placement, 3 layouts | interior-page offsets | absolute (structural, batch-independent) | current-valid (byte-identical) |
| 13 | `fig:firstq-bars` | `figures/13_strategy_firstq_bars.py` | `figures/13_strategy_firstq_bars.png` | `results/unified_v3/matrix/summary.csv` **(single source)** | A/B/C × orig × {layers_5,2d,2e_K10,2e_K500,2f_slru}, async | **paired first-query reduction %** vs same-batch baseline | **relative** (same-batch) | **re-sourced 2026-09-14** to the `unified_v3` single batch; two-source split + `//` hatch removed |
| 14 | `fig:e2e-stacked` | `figures/14_strategy_endtoend_stacked.py` | `figures/14_strategy_endtoend_stacked.png` | `results/unified_v3/matrix/summary.csv` | A/B/C × orig × {baseline,layers_5,2d,**2e_K10,2e_K500**,2f_slru}, async | first_query + deliver stack; warm % vs same-batch baseline | **absolute (single batch)** | **re-sourced 2026-09-14**; strategy set now matches Figure 13 (the `2e_K*` arms were previously unplottable) |
| 17 | `fig:ablation` | `figures/17_lever_ablation.py` | `figures/17_lever_ablation.png` | `results/ablation_comp_v2/uncertainty.csv` **only** | **C_mixed × orig** × {2d,leaf_rand_K10,leaf_freq_K10,2e_K10} | Δ% vs same-batch baseline (first-query and e2e_warm), 10-seed bootstrap 95% CI | **relative** | **corrected same-batch ablation** (Phase 3b: scoped to C_mixed; no longer reads `results/ablation`) |
| 16 | `fig:ram` | `figures/16_ram_pressure_sweep.py` | `figures/16_ram_pressure_sweep.png` | `results/ram_pressure/cap_*/summary.csv` | RAM-pressure sweep, seed 1, orig | delivery % + first-query vs cgroup cap | absolute (single RAM-axis batch) | current-valid (byte-identical) |
| 19 | `fig:portability` | `figures/19_openwhisk_effectiveness_bars.py` | `figures/19_openwhisk_effectiveness_bars.png` | `deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation_revised_freeze.csv` | 55 non-lp strategy×workload cells × orig; YC/YCu/YCh01/C/C_hit; workstation vs OpenWhisk standalone | relative first-query reduction $R$ vs same-platform baseline | **relative** (absolute µs not cross-platform comparable) | added 2026-09-01 (reads the revised freeze) |

## Per-cell canonical source rule (Figures 13 & 14) — SUPERSEDED 2026-09-14

> **No longer in force.** Both figures now read the single batch
> `results/unified_v3`, which measured every arm — `2e_K10` and `2e_K500`
> included — in one machine state under the corrected tie-break. Figure 13 no
> longer mixes sources or hatches cells, and Figure 14 no longer has to drop the
> frequency-ranked arms. Kept below as the record of what the figures did
> between the 2026-07 tie-break fix and 2026-09-14.

The tie-break impact set (RESULT_PROVENANCE §4.2) — cells whose canonical source
is the corrected rerun `results/tiebreak_fix`:

```
A: 2e_K500
B: 2e_K10, 2e_K40, 2e_K92, 2e_K500
C: 2e_K10, 2e_K40, 2e_K92
```

- **Figure 13** is a *relative* chart, so per-cell mixing is safe: each bar is a
  paired reduction against its **own** same-batch baseline. Cells in the impact
  set are read from `tiebreak_fix` (marked with a `//` hatch); all others from
  `unified_v2`. Absolute µs are never plotted.
- **Figure 14** stacks *absolute* µs, which requires one machine-state batch, so
  it plots **only tie-break-unaffected strategies** (baseline, layers_5, 2d,
  2f_slru) from `unified_v2`. The corrected hotspot arms (A `2e_K500`, C `2e_K10`)
  are **excluded** from the stack and reported instead in the paper's
  `tab:corrected-arms` from `tiebreak_fix`.

## Regeneration commands

```bash
VENV=/home/u03/.cache/coldstart-venv/bin/python
$VENV figures/13_strategy_firstq_bars.py       # prints every plotted cell + source
$VENV figures/14_strategy_endtoend_stacked.py
$VENV figures/17_lever_ablation.py
# then copy figures/out/{13,14,17}_*.png -> paper/figures/
```

Both 13 and 14 scripts: read canonical CSVs directly, `sys.exit` on a missing or
duplicated source row, print the selected `(source, baseline, value)` for every
plotted cell, use deterministic strategy/workload ordering, and hard-code no bar
heights. Determinism verified: two consecutive runs produce byte-identical PNGs
(2026-07-23 workload display-name relabel: md5 `ddcbdb00…` for 13, `bda7947e…`
for 14; the pre-relabel values were `1090edc1…` and `85345090…`. Both were
superseded by the 2026-08-30 strategy display-name relabel — current md5s are in
the 2026-09-13 checksum table below).
The 2026-07-29 terminology cleanup did **not** touch any figure's rendered
output: the paper-visible scripts already resolve titles through
`workload_display_name()`, so the included PNGs remained byte-identical between
`figures/out/` and `paper/figures/` at the md5s above. (The paper-visible set has
since changed: 18 was dropped and 19 added — see the 2026-09-13 table.)
Figure 17 gained a one-line provenance comment (clarifying that its `C`
CSV filter is legacy `C_mixed` == Tail-Mixed); comments do not affect the PNG.

## Selected plotted cells (Phase-3 regeneration)

**Figure 13 — paired first-query reduction %** (source in brackets):
```
A layers_5 [unified] -27   2d [unified] -30   2e_K10 [unified] -31   2e_K500 [tiebreak] -64   2f_slru [unified] -79
B layers_5 [unified] -44   2d [unified] -44   2e_K10 [tiebreak] -44   2e_K500 [tiebreak] -38   2f_slru [unified] -86
C layers_5 [unified]  -4   2d [unified] -39   2e_K10 [tiebreak] -83   2e_K500 [unified]  -83   2f_slru [unified] -91
```

**Figure 14 — warm-process e2e vs same-batch baseline** (unified_v2 only):
```
A: layers_5 -14   2d -14   2f_slru +1300
B: layers_5 -34   2d -32   2f_slru  +879
C: layers_5  +3   2d -32   2f_slru   -12
```

## Figure 17 currency note

History: the paper submodule copy was long content-stale (a 2×2 orig+ta render
showing the *pre-fix* C/orig values: leaf_freq ≈ −32%, 2e_K10 ≈ −73%). Phase 3
first replaced it with an A/B/C orig render, but that still drew the A/B bars from
the pre-fix `results/ablation` batch, which no canonical provenance blesses.
**Phase 3b scopes the figure to C_mixed only**, reading the single canonical
corrected source `results/ablation_comp_v2/uncertainty.csv` (C × orig): 2d −43%
first-query / −36% warm e2e (robust); leaf_freq −11% / −3% (warm-e2e tie);
leaf_rand −1% / +7% (control); 2e_K10 −63% / −55%. The figure no longer reads
`results/ablation`, and the A/B "tie-break-unaffected" ablation claim is removed
(the A/B levers are characterized by the cross-seed sweep, `tab:seeds`, not by a
separate ablation figure).

## Cross-batch safety

No paper figure places absolute µs from two different machine-state batches in a
single directly comparable chart:
- Fig 13 is fully relative (per-cell same-batch normalization).
- Fig 14 is single-batch absolute (`unified_v2`, unaffected arms only).
- Fig 17 is single-source (`ablation_comp_v2`, C_mixed × orig), relative Δ% with
  that batch's own bootstrap CI.
- Figs 1, 16, 18 are single-source / structural / qualitative.

## Scripts not referenced by the paper (informational)

| Script | Reads | Status |
|---|---|---|
| `figures/13b_strategy_firstq_lines.py` | `results/main` (v1) | **unused variant** — not in main.tex; not regenerated |
| `figures/13c_strategy_firstq_improvement.py` | `results/main` (v1) | **unused variant** — not in main.tex |
| `figures/18_competitive_baseline.py` | `results/competitive` | **unused legacy** — the paper's Fig 18 is `18_capability_matrix`, not this |
| `figures/02–12, 15` | various (`results/main`, sweeps) | not referenced by the current `paper/main.tex` |

Only paper-visible, demonstrably-stale figures (13, 14, 17) were regenerated; no
decorative variants were added.

## Phase 4 freeze — checksums and determinism (2026-07-12)

All 6 paper-visible figures re-run from clean state; two consecutive runs give
identical md5 (deterministic), and each `paper/figures/*.png` copy is
byte-identical to its `figures/out/*.png` root output.

| Fig | Script | root/paper md5 | dimensions | status |
|---|---|---|---|---|
| 1  | `01_page_distribution.py`        | `8a9abac422…` | 1035×703  | superseded by 2026-09-13 row below |
| 13 | `13_strategy_firstq_bars.py`     | `ddcbdb00bc…` | 1935×643  | superseded by 2026-09-13 row below |
| 14 | `14_strategy_endtoend_stacked.py`| `bda7947e7c…` | 1783×764  | superseded by 2026-09-13 row below |
| 16 | `16_ram_pressure_sweep.py`       | `2c097b23ec…` | 1656×1248 | superseded by 2026-09-13 row below |
| 17 | `17_lever_ablation.py`           | `1949efebc2…` | 1485×614  | superseded by 2026-09-13 row below |
| 18 | `18_capability_matrix.py`        | `b81d89226a…` | 1198×697  | current-valid (qualitative); no longer included by `paper/main.tex` |

Env: `/home/u03/.cache/coldstart-venv/bin/python` (matplotlib 3.10.9, numpy 2.4.6).
No paper-visible figure script reads a legacy/non-canonical result source; the
unused `13b`/`13c`/`18_competitive_baseline` scripts are documented above.

**Workload display names (2026-07-23).** Figures 13/14/16/17 now resolve
workload titles through the canonical registry (`config/workloads.json` via
`config/workload_registry.py`, re-exported from `figures/plot_utils.py` as
`workload_display_name`) instead of hard-coding letters: A → Scattered-Zipf,
B → Uniform-100K, C → Tail-Mixed. The CSV reads still key on the legacy IDs
stored in the immutable results files (`workload=A/B/C`), so only the rendered
labels changed; bar values, CI whiskers, ordering, and data sources are
untouched. This is a pure-label regeneration, hence the new md5s above.

## Re-verification — current checksums (2026-09-13)

The Phase-4 table above is the 2026-07-12/07-23 freeze and is **stale**: the
2026-08-30 pass relabelled strategies to paper-facing names (`Skel-5`, `Skel`,
`Skel+10`, `Skel+500`, `Dump`), Figure 14 additionally dropped its cold-open(db)
segment (2026-08-31), Figure 16 was re-plotted, Figure 18 left `paper/main.tex`,
and Figure 19 (OpenWhisk portability) was added (2026-09-01). Current state:

| Fig | Script | root/paper md5 | dimensions | re-run byte-identical? |
|---|---|---|---|---|
| 1  | `01_page_distribution.py`             | `0e8d229ced…` | 1035×705  | no — 2 px canvas jitter, content identical |
| 13 | `13_strategy_firstq_bars.py`          | `e7a0ddb00c…` | 1935×643  | yes (re-sourced to `unified_v3`, workload rename + shared panel title 2026-09-14) |
| 14 | `14_strategy_endtoend_stacked.py`     | `6156852821…` | 1783×763  | yes (`unified_v3`, workload rename, shared panel title, canonical-estimator labels 2026-09-15) |
| 16 | `16_ram_pressure_sweep.py`            | `2feaafe598…` | 1638×1248 | yes (workload rename 2026-09-14; was `6adc990ca9…`) |
| 17 | `17_lever_ablation.py`                | `5c5365cd7b…` | 1485×614  | yes |
| 19 | `19_openwhisk_effectiveness_bars.py`  | `30000ad042…` | 2534×787  | yes (workload labels + shared panel title 2026-09-14) |
| 18 | `18_capability_matrix.py`             | `b81d89226a…` | 1198×697  | yes — but **not referenced** by `paper/main.tex` |

Every `paper/figures/*.png` is byte-identical to its `figures/out/*.png` root
output. Re-run in the canonical env (matplotlib 3.10.9, numpy 2.4.6) reproduces
13/14/16/17/18/19 exactly (13 and 14 were regenerated here on 2026-09-14, which
also cleared 14's old jitter); **1 still differs by 2 px of canvas size only** — those
two committed PNGs were generated in a session with slightly different font
metrics (2026-08-30 22:25 and 2026-08-31 08:00), their plotted values, labels and
data sources are unchanged, and their inputs have not moved (Figure 1's
`classify_*.csv` are from 2026-05-23). Not a data drift; regenerate them if a
byte-exact artifact check is required.

Figure 19 source: `deployment/openwhisk/analysis/comparison/effectiveness_ow_vs_workstation_revised_freeze.csv`
(paper label `fig:portability`; 55 non-lp strategy×workload cells at orig across
YC/YCu/YCh01/C/C_hit; metric = relative first-query reduction R vs same-platform
baseline, so the two platforms are comparable despite different absolute µs).

Figure 13 was re-verified cell-by-cell on 2026-09-13 against its then-canonical
sources (`unified_v2` + `tiebreak_fix`) and reproduced byte-for-byte. **On
2026-09-14 both 13 and 14 were re-sourced** to the new single batch
`results/unified_v3` (see `results/unified_v3/README.md`): Figure 13 lost its
two-source split and `//` hatching, and Figure 14 gained `Skel+10`/`Skel+500`,
so its strategy set now matches Figure 13's. Relative values moved by at most
2.4 pt (first-query) and 6.4 pt (warm e2e) with **no sign flips**; absolute µs
are ~1–9% faster and must not be mixed with `unified_v2` readings.

**Figure 19 workload-label collision, fixed 2026-09-14.** `19_openwhisk_effectiveness_bars.py`
hard-coded its panel titles instead of resolving them through the canonical
registry, and the names it hard-coded were the wrong ones: `YC` was labelled
"Scattered-Zipf" and `YCu` "Uniform-100K" — the registry display names of the
*controlled* workloads `A` and `B` that Figures 13/14 plot. One name therefore
meant two different workloads in the same paper (a synthetic generator in
Figure 13, a native YCSB 0.17.0 trace in Figure 19), directly against the
registry's own `external_validity_counterpart: "... NOT equated"` annotation on
both records and against its rule that consumers "MUST resolve display names
through `config/workload_registry.py` rather than hard-coding the mapping".
`YCh01` was additionally shown as the invented name "Hashed-Hotspot". The script
now calls `workload_display_name()` like every other paper-visible figure.

The registry's own names for those three were then reworded, because `YCSB-C` /
`YCSB-Cu` / `YCSB-Ch-hashed-01` tell a reader nothing about the access pattern.
They now follow the key-space-size convention already used by `Uniform-100K`,
which makes the pairing legible without reusing the controlled workloads' names:

| key | was | now | controlled counterpart |
|---|---|---|---|
| `YC` | `YCSB-C` | **`Scattered-Zipf-600K`** | `Scattered-Zipf` (A, 100K) |
| `YCu` | `YCSB-Cu` | **`Uniform-600K`** | `Uniform-100K` (B) |
| `YCh01` | `YCSB-Ch-hashed-01` | **`Hotspot-1%-scattered`** | — (`-scattered` leaves room for the `YCo*` ordered siblings as `-clustered`) |

The old names stay resolvable as `legacy_aliases`, so docs, manifests and older
result filters that still say `YCSB-C` keep working. `tests/test_workload_naming.py`
gained two guards (display names must differ from the controlled workloads'; old
names must still normalize) and its `standard_workload` check was re-keyed from
`display_name` to `canonical_id` — a spec fact should not ride on a presentation
string. 13 tests green.

Strategy labels were already correct — all figures share `STRAT_DISPLAY`, and the
five arms common to Figures 13/14/19 agree.

**Counterpart pairs named symmetrically, 2026-09-14.** `Uniform-100K` already
carried a key-space suffix but `Scattered-Zipf` did not, so one counterpart pair
read as a pair and the other did not — `Scattered-Zipf` next to
`Scattered-Zipf-600K` invited reading the former as the general case. `A` now
displays as **`Scattered-Zipf-100K`**, giving two symmetric pairs:

```
Scattered-Zipf-100K  <->  Scattered-Zipf-600K     (controlled A / native YC)
Uniform-100K         <->  Uniform-600K            (controlled B / native YCu)
Tail-Mixed, Tail-Hit, Hotspot-1%-scattered        (no counterpart, no suffix)
```

The suffix earns its place by disambiguating a pair, so workloads without a
counterpart keep bare names. `Scattered-Zipf` remains a `legacy_alias`.
Figures 13, 14 and 16 re-rendered (17 and 19 plot no `A` panel and are
byte-identical); `main.tex` updated in 76 places, with the two
`Scattered-Zipf-600K` mentions left intact. `tests/test_workload_naming.py` is
at 14, adding `test_counterpart_pairs_are_symmetrically_named`.

**One panel title per workload, 2026-09-14.** The same workload was labelled
three different ways: Figure 13 appended "— ~50% not-found tail-boundary",
Figure 14 appended "(~50% not-found)", and Figure 19 showed a bare `Tail-Mixed`,
which also silently ignored the registry's `must_annotate` requirement on that
record ("Always mark ~50% not-found and right-boundary (rightmost-leaf) probe
concentration"). Each figure was building its own title string.

`plot_utils.workload_panel_title()` now renders it once for every figure, keyed
by `canonical_id` so aliases resolve the same way:

```
Tail-Mixed (~50% not-found, right-boundary)
Tail-Hit (pure-hit control)
```

`Tail-Hit` carries an annotation for the same reason — the registry flags it
`must_annotate` too, and Figure 19 was showing it bare. Every other workload has
no `must_annotate` and renders as its plain display name. Figure 14's panel title
dropped to fontsize 10 (matching Figure 19) so the longer Tail-Mixed title clears
the axes edge.

The three figures plot the *same* Tail-Mixed workload — one registry record, one
generator spec, same key range, same DB, `orig` layout. What differs is the seed
protocol per cell, which is a measurement choice Figure 19 records in its own
`seed_protocol` column (Figures 13/14 are single-instantiation seed 1; Figure 19
mixes seeds 1-10, single-instantiation, seed-1-only and LOSO across its cells).

**Unverified:** no LaTeX toolchain here, so the wider name has not been checked
against `tab:ceiling`'s narrow `p{0.15\linewidth}` column. It is ragged-right so
it wraps rather than overflows, but the wrap has not been seen.

**Still to fix in prose:** `paper/main.tex` §5.6's per-workload portability table
(L720–724) and the discussion around it still use the old colliding names
(`Scattered-Zipf`, `Uniform-100K`, `Hashed-Hotspot`) for the `YC`/`YCu`/`YCh01`
rows. The table therefore still collides with Figures 13/14 and no longer matches
Figure 19's panels; it should read `Scattered-Zipf-600K` / `Uniform-600K` /
`Hotspot-1%-scattered`.

**Estimator split resolved in Figure 14, 2026-09-15.** The bar height is
`median(first_query) + median(deliver)` — it has to be, the bar is a stack of
those two medians — but the percentage label now comes from `e2e_warm_median`,
the median of the per-repetition sums, which is the canonical column the paper's
tables read. The two differ by <0.4%, invisible on a log axis, but under
`unified_v3` they round differently in three cells (Scattered-Zipf-100K
`Skel-5` -14/-13, `Skel+500` +109/+110, Tail-Mixed `Skel+500` -41/-40), which
would have put the figure and `tab:e2e-ac` one point apart. The label follows the
tables: a label is a claim, the bar is a picture.

**Not yet propagated:** `paper/main.tex` still carries the old captions (Figure
13's hatch legend, Figure 14's "tie-break-unaffected strategies only" and
"not stacked here" sentences) and the 53 single-instantiation claims in
`docs/audits/PAPER_CLAIM_MANIFEST.csv` still cite `unified_v2`/`tiebreak_fix`
absolute values. The figures and the prose therefore disagree until that
propagation is done.
