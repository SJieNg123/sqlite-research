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
| 18 | `fig:capability` | `figures/18_capability_matrix.py` | `figures/18_capability_matrix.png` | none (hand-coded capability matrix) | prior-art positioning | qualitative ✓/◐/✗ | n/a | current-valid (byte-identical to committed) |
| 1 | `fig:layout-distribution` | `figures/01_page_distribution.py` | `figures/01_page_distribution.png` | `pipeline/preparation/layout_rewriter/runs/classify_{before,vacuum,after}.csv` | static page-type placement, 3 layouts | interior-page offsets | absolute (structural, batch-independent) | current-valid (byte-identical) |
| 13 | `fig:firstq-bars` | `figures/13_strategy_firstq_bars.py` | `figures/13_strategy_firstq_bars.png` | `results/unified_v2/matrix/summary.csv` + `results/tiebreak_fix/master_summary.csv` | A/B/C × orig × {layers_5,2d,2e_K10,2e_K500,2f_slru}, async | **paired first-query reduction %** vs same-batch baseline | **relative** (per-cell same-batch) | **regenerated** (was v1 `results/main`) |
| 14 | `fig:e2e-stacked` | `figures/14_strategy_endtoend_stacked.py` | `figures/14_strategy_endtoend_stacked.png` | `results/unified_v2/matrix/summary.csv` | A/B/C × orig × {baseline,layers_5,2d,2f_slru}, async | first_query + deliver + open stack; warm % vs same-batch baseline | **absolute (single batch)** | **regenerated** (was v1 `results/main`) |
| 17 | `fig:ablation` | `figures/17_lever_ablation.py` | `figures/17_lever_ablation.png` | `results/ablation_comp_v2/uncertainty.csv` **only** | **C_mixed × orig** × {2d,leaf_rand_K10,leaf_freq_K10,2e_K10} | Δ% vs same-batch baseline (first-query and e2e_warm), 10-seed bootstrap 95% CI | **relative** | **corrected same-batch ablation** (Phase 3b: scoped to C_mixed; no longer reads `results/ablation`) |
| 16 | `fig:ram` | `figures/16_ram_pressure_sweep.py` | `figures/16_ram_pressure_sweep.png` | `results/ram_pressure/cap_*/summary.csv` | RAM-pressure sweep, seed 1, orig | delivery % + first-query vs cgroup cap | absolute (single RAM-axis batch) | current-valid (byte-identical) |

## Per-cell canonical source rule (Figures 13 & 14)

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
(md5 `ddcbdb00…` for 13, `bda7947e…` for 14 after the 2026-07-23 workload
display-name relabel; the pre-relabel values were `1090edc1…` and `85345090…`).

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
| 1  | `01_page_distribution.py`        | `8a9abac422…` | 1035×703  | current-valid |
| 13 | `13_strategy_firstq_bars.py`     | `ddcbdb00bc…` | 1935×643  | regenerated (workload display-name relabel, 2026-07-23) |
| 14 | `14_strategy_endtoend_stacked.py`| `bda7947e7c…` | 1783×764  | regenerated (workload display-name relabel, 2026-07-23) |
| 16 | `16_ram_pressure_sweep.py`       | `2c097b23ec…` | 1656×1248 | regenerated (workload display-name relabel, 2026-07-23; seed-1 RAM axis) |
| 17 | `17_lever_ablation.py`           | `1949efebc2…` | 1485×614  | regenerated (workload display-name relabel, 2026-07-23; Tail-Mixed-only, ablation_comp_v2) |
| 18 | `18_capability_matrix.py`        | `b81d89226a…` | 1198×697  | current-valid (qualitative) |

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
