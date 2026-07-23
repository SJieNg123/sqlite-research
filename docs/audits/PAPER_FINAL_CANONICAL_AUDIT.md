# Paper Final Canonical Audit (Phase 4)

> **Workload naming migration (2026-07-23).** Paper-visible workload identifiers
> were changed from legacy letters (A/B/C/C\_mixed/C\_hit/Z, YD/YE, CHURN) to
> descriptive display names (Scattered-Zipf, Uniform-100K, Tail-Mixed, Tail-Hit,
> Concentrated-Zipf, Latest-Aging, Short-Scan Aging, Mixed-Mutation Churn). See
> [`WORKLOAD_NAMING_MIGRATION.md`](WORKLOAD_NAMING_MIGRATION.md). **No results
> CSV or raw data changed**: this manifest and `tools/verify_paper_atomicity.py`
> intentionally keep legacy IDs in every machine-checked column (they map onto
> the immutable results files); names are normalized for display via
> `config/workload_registry.py`. The manifest gained a read-only `display_name`
> column; all pre-existing columns are unchanged and the verifier still exits 0.

## Metadata
- generated UTC: 2026-07-12
- root HEAD before: `b70447c` (descends from the frozen `098f3a2`)
- paper HEAD before: `eccc889`
- provenance authority: [`results/RESULT_PROVENANCE.md`](../../results/RESULT_PROVENANCE.md)
  with the per-scope rules of §4.2/§4.4/§4.8; prior audits
  [`PAPER_NUMERIC_ALIGNMENT.md`](PAPER_NUMERIC_ALIGNMENT.md),
  [`PAPER_FRAMING_ALIGNMENT.md`](PAPER_FRAMING_ALIGNMENT.md),
  [`STALE_NARRATIVE_AUDIT.md`](STALE_NARRATIVE_AUDIT.md),
  [`../figures/FIGURE_SOURCE_MAP.md`](../figures/FIGURE_SOURCE_MAP.md).

## Scope
- files audited: `paper/main.tex` (730 lines), all 6 paper-visible figures and
  their root scripts, the 13 table environments, every table/figure caption.
- claims inventoried: **128** (in `PAPER_CLAIM_MANIFEST.csv`) covering the
  ~180 quantitative occurrences (some occurrences repeat a claim across
  sections and are consolidated).
- tables audited: **13**.
- figures audited: **6** (2 stacked/relative result figures, 1 ablation, 1 RAM,
  1 structural, 1 qualitative matrix).

## Canonical result map (per-scope; not a global precedence)

| Result class | Canonical source | Exact scope | Supersession |
|---|---|---|---|
| Unaffected main-matrix cell | `results/unified_v2/matrix/summary.csv` | A/B/C × {orig,vacuum,ta} × non-changed strategies, single-inst | — |
| Corrected single-instantiation | `results/tiebreak_fix/master_summary.csv` | A:2e_K500; B:2e_K10/K40/K92/K500; C:2e_K10/K40/K92 | supersedes unified_v2 for those cells |
| Corrected cross-seed | `results/tiebreak_fix/seeds/` + `uncertainty.csv` | same changed cells; per-seed paired, bootstrap CI | supersedes results/seeds for those cells |
| C_mixed ablation / competitive | `results/ablation_comp_v2/uncertainty.csv` | C × orig × {2d,leaf_rand,leaf_freq,2e_K10,2f_top14/28,2f_slru} | supersedes results/ablation + results/competitive for C/orig |
| C_hit corrected freq arms | `results/c_hit_v2/uncertainty.csv` | C_hit × orig × {2e_K10,2e_K40,2e_K92,2e_K500} | supersedes c_hit for those |
| C_hit unaffected arms | `results/c_hit/uncertainty.csv` | C_hit × orig × {2d,2f_top14/28,learned,layers_92,2f_slru} | — (orig-only) |
| Prior-art baseline | `results/baselines_v2/summary.csv` | A/B/C × orig prior-art; test seed 1 | — |
| A/B competitive (independent) | `results/competitive/uncertainty.csv` | A/B × orig; relative paired only | §4.8 scope; C rows superseded by ablation_comp_v2 |
| Cross-seed unaffected structural | `results/seeds/seed*/summary.csv` | 2d/layers_N per-seed paired | §4.8; frequency arms superseded by tiebreak |
| Aging | `results/aging_v2/aging_ci.csv` | YD/YE × orig × {baseline,2e_K10_static,layers_92_static}; 11 ck | — |
| Legacy first-seen | `strategies/.../legacy_same_trace_first_seen_tiebreak/` | — | **never a current source** |

## Claim inventory summary
- total claims: **128**
- recomputed from canonical CSVs (PASS): **111**
- scope-checked (structural / cited / qualitative / range): **17**
- FAIL after fixes: **0**
- historical/retracted (kept only in labeled context): pre-fix −40% (leaf_freq),
  −72%/−57% (competitive), −70%/−68% (size-scaling 2e_K10) — each appears solely
  inside an explicit "pre-fix / diagnostic" clause.
- unresolved: **0** current-paper numeric claims.

## Atomic checking (`tools/verify_paper_atomicity.py`)
- absolute claims: recomputed as the exact `median` column of the unique matching
  row; a `compare_group` check confirms every absolute stack is single-batch
  (`tab:e2e-ac` → unified_v2 only; `tab:corrected-arms` → tiebreak_fix only).
- relative claims: recomputed `(strategy−baseline)/baseline×100` with the
  **same-file (same-batch) baseline**; the verifier rejects a baseline drawn from
  a different batch.
- cross-seed claims: recomputed as the **per-seed paired mean** across the seed
  batch (`seeds_mean`), enforcing n=10; CIs are read from the batch's own
  `uncertainty.csv` (never re-derived from aggregate means).
- corrected cells: the verifier FAILS if a `(workload,strategy)` in the tie-break
  impact set is sourced from `unified_v2` or `results/seeds` — **even when the
  number is identical** (verified by a negative test: C 2e_K10 pointed at
  unified_v2 → exit 1, "changed cell uses superseded source").
- C_hit: verifier FAILS if a c_hit_v2-corrected arm is sourced from `c_hit`, and
  if a C_hit claim is on a non-orig layout.
- **violations found and fixed: 1** — `tab:seeds` B `2e_K10` single-workload
  printed **−29%** (superseded unified_v2); B 2e_K10 is a changed cell, so the
  atomic-correct value is **−30%** from `tiebreak_fix`. Fixed in `main.tex`.

Verifier result: `claims: 128 | recomputed: 111 | scope-checked: 17 | FAIL: 0`
→ **ALL CLAIMS PASS** (exit 0).

## Table audit

| Table | Purpose | Metric | Abs/Rel | Scope | Source batch | Comparable? | Status |
|---|---|---|---|---|---|---|---|
| `tab:measurement-model` | layer states | — | — | — | none | n/a | OK |
| `tab:delivery-modes` | pread vs async | — | — | — | none | n/a | OK |
| `tab:protocol-phases` | harness phases | — | — | — | none | n/a | OK |
| `tab:strategies` | hotset sizes | footprint | abs | structural | classify | within-table | OK |
| `tab:workloads` | workload defs | — | — | A/B/C_mixed/D | — | n/a | OK (C=C_mixed) |
| `tab:ceiling` | first-q ceiling | reduction % | rel | A/B/C_mixed orig | unified_v2 (+tiebreak C 2e_K10, A 2e_K500) | per-cell same-batch | OK |
| `tab:overhead` | open/deliver | latency | abs | per-strategy | **independent overhead batch** | within-table only | OK (caption marks independent) |
| `tab:e2e-ac` | e2e trade-off | abs+rel | abs | A/C orig | **unified_v2 only** | single machine-state batch | OK (unaffected arms only) |
| `tab:corrected-arms` | corrected hotspot | abs+rel | rel | A 2e_K500, C_mixed 2e_K10 | **tiebreak_fix only** | own same-batch baseline; no cross-table abs | OK |
| `tab:ablation` | lever ablation | Δ%+CI | rel | **C_mixed × orig only** | **ablation_comp_v2 only** | within-batch | OK |
| `tab:competitive` | targeted vs dump | Δ%+CI | rel (paired only) | A/B/C orig | **A/B=competitive; C=ablation_comp_v2; 2f_top500=competitive** | paired relative only, no cross-batch abs | OK (per-row source note) |
| `tab:seeds` | cross-seed valid. | Δ%+CI | rel | A/B/C orig | single: unified/tiebreak; cross: seeds/tiebreak-seeds | single & cross columns separated | OK (B 2e_K10 single fixed) |
| `tab:guidance` | recommendations | mixed | rel | — | derived (relative) | no abs compare | OK |

Specific required checks (STEP 6):
- **A. tab:e2e-ac** — only unaffected absolute rows (baseline, layers_5, 2d,
  2f_slru); one `unified_v2` batch; no impact-set hotspot arm. ✓
- **B. tab:corrected-arms** — A 2e_K500 and C 2e_K10 each paired with their own
  `tiebreak_fix` baseline; caption forbids column-wise absolute comparison. ✓
- **C. tab:ablation** — C_mixed × orig only, `ablation_comp_v2` only. ✓
- **D. tab:competitive** — A/B (competitive) vs C (ablation_comp_v2) split stated
  in caption; paired relative only; 2f_top500-C flagged prior-art. ✓
- **E. tab:seeds** — single-inst and cross-seed columns separated; changed
  frequency arms (B/C 2e_K10) use the corrected source; unaffected structural
  arms use results/seeds. ✓ (B 2e_K10 single −29→−30 fixed this phase.)

## Figure audit

| Fig | Label | Script | Source | Metric | Abs/Rel | root md5 | paper md5 | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | `fig:layout-distribution` | `01_page_distribution.py` | layout classify CSVs (structural) | interior offsets | abs (structural) | 8a9abac422 | 8a9abac422 | current-valid |
| 13 | `fig:firstq-bars` | `13_strategy_firstq_bars.py` | unified_v2 + tiebreak_fix (per-cell) | paired first-q reduction % | **relative** | 1090edc11f | 1090edc11f | regenerated (Phase 3) |
| 14 | `fig:e2e-stacked` | `14_strategy_endtoend_stacked.py` | unified_v2 only | fq+deliver+open stack | **abs single-batch** | 8534509086 | 8534509086 | regenerated (Phase 3) |
| 16 | `fig:ram` | `16_ram_pressure_sweep.py` | results/ram_pressure cap_* (seed 1) | delivery % / first-q | abs (RAM axis) | 0b5fbb7243 | 0b5fbb7243 | current-valid |
| 17 | `fig:ablation` | `17_lever_ablation.py` | **ablation_comp_v2 only** | Δ% + 95% CI | relative | e8c25599d1 | e8c25599d1 | regenerated (Phase 3b, C_mixed-only) |
| 18 | `fig:capability` | `18_capability_matrix.py` | none (hand-coded) | qualitative | n/a | b81d89226a | b81d89226a | current-valid |

- Every generated figure is **deterministic** (two consecutive runs → identical
  md5) and the paper copy is **byte-identical** to the root output.
- Fig 13: per-cell relative normalization; changed cells (hatched) from
  tiebreak_fix; C label = C_mixed. ✓
- Fig 14: single unified_v2 absolute batch; only baseline/layers_5/2d/2f_slru; no
  corrected 2e arm; C label = C_mixed; A/B +1300/+879 regression and C −12%
  exception annotated. ✓
- Fig 17: `ablation_comp_v2` only, C_mixed × orig, arms 2d/leaf_rand/leaf_freq/
  2e_K10, first-query + e2e_warm panels, 95% CI, no A/B panel, no `results/ablation`
  source. ✓
- Fig 16: inputs `cap_{unlimited,16M,12M,8M,6M}` all exist; no stale
  "unlimited = results/main" (uses `cap_unlimited`); text scoped as seed-1. ✓
- Fig 18: qualitative matrix inspected — marks show OS-readahead/libprefetch/
  learned/`.dbi` vs "our work"; it does **not** claim type-aware uniquely wins,
  learned-beats-frequency, a universal best stack, layout-as-flagship, or
  always-valid static frequency. ✓

Non-paper legacy scripts (`13b`, `13c`, `18_competitive_baseline`) read
`results/main`/`results/competitive` but are **not referenced by main.tex** and
produce differently-named outputs; documented UNUSED in FIGURE_SOURCE_MAP.

## Narrative reconciliation (by section)
- **Abstract / Contributions** — skeleton-first; 2d 25–30% warm e2e; conditional
  leaf bonus (A −25→−36); full dump −79~91% first-q but A/B ~order-of-magnitude
  e2e regression with C the narrow exception; open ≈230 µs; "to our knowledge …
  first" (hedged). ✓
- **Fundamentals / Methodology** — 92 interior / 26,239 leaf / 600k rows / 102 MB
  are fixed structure; cost model open+deliver+first-query; n=10, 10 seeds,
  10,000-resample bootstrap. ✓
- **First-query eval** — baselines 523/749/1087; 2f_slru −79/−86/−91; ceilings
  −30/−44/−39; C 2e_K10 −83 (corrected). ✓
- **e2e eval** — tab:e2e-ac unaffected single-batch; corrected arms in
  tab:corrected-arms; full-dump A +1300 / B +879 / C −12. ✓
- **Ablation** — C_mixed-only; 2d robust (−43/−36), leaf_freq tie (−3), leaf_rand
  control (+7), 2e_K10 −63/−55; fig 17 C_mixed-only. ✓
- **Competitive** — 2e_K10 ≈ 2f_top14 on C statistically indistinguishable; A/B
  independent-batch relative-only. ✓
- **C_hit** — orig-only; 2e_K10 −27, 2d −28.5, 2f_top14 −30.6, learned −29.0; no
  universal separation. ✓
- **C_mixed** — ~50% not-found; not-found probes → right edge; cross-seed −55
  bimodal; seed-1 −75 labeled single-inst; not a general pure-hit tail result. ✓
- **Layout / RAM / size / cadence / aging** — layout = negative/design-space;
  RAM seed-1-scoped; size 2e_K10 −70/−68 marked pre-fix diagnostic; aging
  stationarity-dependent (YD decays, YE stable). ✓
- **Guidance / Discussion / Conclusion** — default orig+2d; leaf only with
  validated skew; moving hotspot → structural/refresh; commodity x86+NVMe;
  no FaaS/OpenWhisk result claimed. ✓

## Validation
- verifier: 128 claims, 111 recomputed + 17 scope, **0 FAIL**, exit 0; negative
  test confirms atomic enforcement independent of numeric closeness.
- stale scan: **no** current-paper match for
  529/760/1096/127/128/123/211/+1248/+843/churn-heavy/file-tail/recently-ingested/
  full-table-scan/consistently-fails/robustly-beats/never-beaten/results-main; the
  only `128` hits are `read_ahead_kb = 128`.
- figures: all 6 deterministic + byte-identical copies (table above).
- LaTeX: no `latexmk`/`pdflatex`/`xelatex` available (environment limitation) →
  strongest static checks performed: `git diff --check` clean; braces balanced
  (0); `\begin`/`\end` balanced; 0 duplicate labels; 0 dangling refs; 0 missing
  citations; all 6 `\includegraphics` targets present.

## Pre-OpenWhisk scope cleanup (Phase 4.1)

Submission-wording and churn-provenance scoping pass; **no result, figure, CSV,
or headline number changed.** Paper edits are confined to `main.tex` prose.

- **Internal novelty TODO removed from paper.** The conclusion parenthetical
  "(a positioning we flag as pending fuller literature verification)" was deleted.
  The hedged "To our knowledge, this is the first work …" wording is retained;
  the literature-review limitation is now recorded only in internal audit docs,
  not as a TODO/reviewer-note in the paper text.
- **"Deployable" claims scoped to design/mechanism compatibility.** Contribution 3
  title → "Non-intrusive, deployment-compatible toolchain"; its "directly
  deployable in production FaaS environments" → "compatible with the execution
  restrictions of production FaaS environments without requiring platform
  modification or privileged access." Intro summary "deployable solution that
  works within the constraints of production FaaS" → "application-layer design
  that operates within the execution constraints of restricted FaaS environments
  without privileged platform changes." Conclusion "deployable in production FaaS
  and edge environments" → "designed to operate within the execution constraints
  of FaaS and edge environments." No claim of a measured production-FaaS/OpenWhisk
  deployment remains. (Challenge 3's "not deployable in production FaaS settings"
  describes prior invasive designs' constraint and is retained.)
- **OpenWhisk runtime validation is the immediate next experiment.** A limitation
  sentence was added: "Direct validation inside a FaaS runtime is not included in
  the current evaluation; an OpenWhisk deployment is the immediate next
  experimental step."
- **Churn batch scoped as pre-fix diagnostic.** The Write-churn paragraph now
  states the batch predates the trace-order-independent tie-break correction; the
  absolute ~82–89 µs / ~580 µs levels are labeled pre-fix diagnostic values (not a
  corrected 2e_K10 magnitude); the only retained conclusion is within-batch
  checkpoint flatness under a **stationary** read hotspot, explicitly distinguished
  from the moving-hotspot YD vs stationary YE aging axis. The strong wording
  "recomputation is unnecessary for at least 50k write mutations" was replaced with
  "Under this stationary-read-hotspot configuration, no plan refresh was needed to
  preserve the within-batch trend over 50k mutations." Historical values unchanged;
  not promoted to a corrected magnitude.
- **Manifest** (`PAPER_CLAIM_MANIFEST.csv`, now 131 claims): the churn claim row is
  re-scoped to within-batch flatness / pre-fix diagnostic (forbidden conclusion =
  corrected selector magnitude); three claims added — a hedged-novelty row (no
  internal pending-note), a FaaS deployment-compatibility row (status: not a
  measured OpenWhisk result), and an OpenWhisk-pending limitation row. No source
  value was altered to make the verifier pass; verifier still exits 0.

## Pre-OpenWhisk editorial cleanup (Phase 4.1b)

Editorial and scope-of-portability pass; **no result, figure, CSV, or headline
number changed.** `main.tex` prose edits only: fixed the ``warm containe''→``warm
container'' typo; added the missing abstract comma ("To our knowledge, this is");
labeled the Write-churn workload as \emph{C\_mixed}; and rewrote the cross-platform
limitations paragraph. The prior claim that "the relative ordering of strategies
are portable across platforms" is **removed**; the paper now states only that the
cost-accounting methodology is intended to transfer to same warm-process/cold-data
platforms, and frames strategy-ordering portability as an untested empirical
question that the OpenWhisk validation will test. The duplicate FaaS next-step
sentences were merged so "immediate next" appears once in Limitations. Manifest
(now 132 claims) gains an `ordering-portability-untested` row and updates the
`openwhisk-pending` row wording; no numeric source changed; verifier still exits 0.

## Remaining limitations
- **OpenWhisk / FaaS runtime not yet evaluated.** The paper measures the
  local-storage tier on commodity x86 + NVMe and explicitly frames direct FaaS
  runtime validation as the immediate next experiment; no OpenWhisk code or
  result exists yet. Whether the locally observed strategy ordering carries over
  to a FaaS runtime is stated as an untested empirical question, not a claim.
- **Literature novelty review pending internally.** The "to our knowledge … first"
  claim is hedged; a full novelty review has not been run. This is retained in the
  internal audit only and is **no longer stated as a TODO in the paper text**.
- **Intentionally seed-1 / single-axis limitations** (retained, scoped as such):
  RAM-pressure sweep and the single-instantiation layout/overhead comparisons; the
  size-scaling 2e_K10 magnitude is retained only as a labeled pre-fix diagnostic;
  the churn batch is likewise a labeled pre-fix within-batch-flatness axis.

## Decision
**PASS.** Every quantitative claim maps to a canonical source; every relative
value uses a same-batch baseline; every corrected cell uses its corrected source;
no absolute comparison crosses machine-state batches; single-inst and cross-seed
are distinguished; C_hit is orig-only; C_mixed is scoped to ~50% not-found; the
six figures obey the per-figure atomic rules, are deterministic, and are
byte-identical between root and paper; the atomic verifier exits 0; the stale
scan is clean; and no CSV/result was modified and no benchmark/OpenWhisk ran.
One residual atomic violation (tab:seeds B 2e_K10 single −29→−30) was found and
fixed. The paper's text, numbers, tables, and figures are frozen against the
canonical result set.

**Phase 4.1 (pre-OpenWhisk scope cleanup) preserves this PASS.** It changed only
submission wording and churn-provenance scoping in `main.tex`, plus the manifest
and audit docs; it altered no result, figure, CSV, or headline number, the atomic
verifier still exits 0 (131 claims, 0 FAIL), and static/`git diff --check`
validation remains clean. OpenWhisk validation is not started and is recorded as
the immediate next experimental step.
