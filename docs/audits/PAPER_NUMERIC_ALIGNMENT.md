# Paper Numeric Alignment (Phase 2.5)

## Metadata
- generated UTC: 2026-07-12
- root HEAD before: `b5615923f7fda7fef1dcb6d9088663f7edec3945`
- paper HEAD before: `0d3120a479aec18986cfd4ac47fed2bec59db83b`
- provenance authority: [`results/RESULT_PROVENANCE.md`](../../results/RESULT_PROVENANCE.md)
  (Phase 0, commit `cbe9423`), with Phase 1
  [`STALE_NARRATIVE_AUDIT.md`](STALE_NARRATIVE_AUDIT.md) and Phase 2
  [`PAPER_FRAMING_ALIGNMENT.md`](PAPER_FRAMING_ALIGNMENT.md).
- audited files: `paper/main.tex` (only tex file), `paper/figures/*.png`
  (visual inspection).
- source-authority order is **per-cell scope**, not a global precedence
  (RESULT_PROVENANCE §4.4): unaffected main-matrix → `unified_v2`;
  tie-break-corrected single-inst → `tiebreak_fix/master_summary.csv`;
  corrected cross-seed → `tiebreak_fix/seeds` + `uncertainty.csv`;
  C_mixed ablation/competitive → `ablation_comp_v2`; C_hit → `c_hit`/`c_hit_v2`;
  prior-art → `baselines_v2`; aging → `aging_v2`.

## Executive summary

Phase 2 ported the **framing** and the **corrected ablation/competitive/C_hit
tables** to canonical values, but left the pre-canonical **single-instantiation
number blocks** in §2 (motivation), §3 (fundamentals), §5.1 (first-query), and
§5.2 (e2e trade-off table + prose) untouched. Those blocks still carried the
v1 `results/main` batch (baselines 529/760/1096, `2f_slru` first-query
127/128/123 µs = −76/−83/−89 %, the entire `tab:e2e-ac` body, and the
`+1248 %/+843 %` regressions). This phase replaces them with the canonical
single-instantiation batch `results/unified_v2` (baselines 523/749/1087;
`2f_slru` 108/107/102 µs = −79/−86/−91 %) and the tie-break-corrected batches
for the affected cells. Two figures (`13`, `14`) embed the v1 numbers in the
image itself and are marked **Phase 3 figure-pending**.

## Numeric occurrence table

Classification key: **A** canonical-current, **C** v1-stale, **D** pre-fix-stale,
**E** correct-number/wrong-scope, **G** derived-text (verified by arithmetic).

| ID | paper file:line | Current value | Meaning/scope | Class | Canonical source | Canonical value | Action |
|---|---|---:|---|---|---|---:|---|
| N1 | main.tex:101 | 529 to 1096 µs | cold first-query range, motivation | C | unified_v2 baseline fq (orig) | 523 to 1087 | fixed |
| N2 | main.tex:212 | 529 to 1096 µs | cold-start range, mechanics | C | unified_v2 | 523 to 1087 | fixed |
| N3 | main.tex:241 | 529 to 1096 µs | cold baseline, meas. model | C | unified_v2 | 523 to 1087 | fixed |
| N4 | main.tex:446 | 529 / 760 / 1096 µs | per-workload baselines (denominators) | C | unified_v2 baseline fq | 523 / 749 / 1087 | fixed |
| N5 | main.tex:452 | 529/760/1096; 2f 127(−76%)/128(−83%)/123(−89%) | §5.1 baselines + 2f_slru first-q | C | unified_v2 orig async | 523/749/1087; 108(−79%)/107(−86%)/102(−91%) | fixed |
| N6 | main.tex:452 | targeted −22% to −81% | targeted first-q span | G | unified_v2 (A layers_5 → C 2e_K10) | −27% to −83% | fixed |
| N7 | main.tex:454 | A −22 to −26; 2e_K500 −60; dump −76; B −83; C −38/−81 | first-q ceiling prose | C/G | unified_v2 (C 2e_K10 = tiebreak) | A −27–30/−64/−79; B −86; C −39/−83 | fixed |
| N8 | main.tex:465–467 | A −26/−60/−76; B −43/−83; C −38/−81/−89 | `tab:ceiling` | C/G | unified_v2 (+tiebreak C 2e_K10) | A −30/−64/−79; B −44/−86; C −39/−83/−91 | fixed |
| N9 | main.tex:474 | −22% to −26% (A); −43% (B) | layers_N plateau prose | G | unified_v2 | −27% to −30% (A); −44% (B) | fixed |
| N10 | main.tex:479 | 123 to 128 µs; −22% to −81% | `fig:firstq-bars` caption | C | (figure embeds v1) | pointer + pending note | fixed (caption) / figure pending |
| N11 | main.tex:483 | 123–128; 529–1096; C 2e_K10 211 (−81%) | fig prose | C | unified_v2 / tiebreak | 102–108; 523–1087; C 2e_K10 184 (−83%) | fixed + pending note |
| N12 | main.tex:487 | −76% to −89% | 2f_slru first-q reduction span | C | unified_v2 | −79% to −91% | fixed |
| N13 | main.tex:516,519 | baseline 529 / 1096 | `tab:e2e-ac` header + baseline row | C | unified_v2 | 523 / 1087 | fixed |
| N14 | main.tex:520–524 | entire A/C body (480,487,490,291,7134,…) | `tab:e2e-ac` single-inst e2e | C | unified_v2 for unaffected rows; impact rows (C 2e_K10, A 2e_K500) moved to `tab:corrected-arms` from `tiebreak_fix` (Phase 2.5b) | rebuilt + split | fixed |
| N15 | main.tex:524 | C 2f_slru verdict −9% | cross-seed | E | ablation_comp_v2 C 2f_slru e2e_warm | −7% | fixed |
| N16 | main.tex:531 | 7134 vs 529; +1248%; +1285%; 402 µs; −19%(−9%) | §5.2 prose | C/G | unified_v2 (A/C single-inst) + ablation_comp_v2 | 7324 vs 523; +1300%; +1343%; 415 µs; −12%(−7%) | fixed |
| N17 | main.tex (tab:corrected-arms + §5.2 prose) | 1071 → 265 µs, −75% | C 2e_K10 single-inst, labeled | A | `tiebreak_fix/master_summary.csv` (baseline 1070.68; 2e_K10 warm 265.44; paired −75.2%) | reported in `tab:corrected-arms` (Phase 2.5b) | verified |
| N18 | main.tex:544 | +1248%(A)/+843%(B); −7 to −9 (A); −73 (C) | fig:e2e-stacked prose | C/G | unified_v2 single-inst | +1300%/+879%; −11 to −14 (A); −75 (C) | fixed + pending note |
| N19 | main.tex:539 | (narrative caption) | fig:e2e-stacked caption | A | — | pending note added | fixed (note) / figure pending |
| N20 | main.tex:596,610 | +1248% (×2) | reconciliation to single-inst | G | unified_v2 A 2f_slru warm | +1300% | fixed |
| N21 | main.tex:607 | C 2f_slru −12% [−17,−7] | `tab:competitive` C column | D | ablation_comp_v2 C 2f_slru e2e_warm | −7% [−12,−2] | fixed |
| N22 | main.tex:604–607 | A/B columns; 2f_top500 row | prior-art competitive | E-scope | results/competitive (A/B, indep. batch); 2f_top500 not in corrected rerun | retained + per-source caption note | fixed (note) |
| N23 | main.tex:52,121,129,674,678,702 | −79 to −91; 25–30%; 0.8–7 ms; A −25→−36; −27 to −30 | abstract/contrib/guidance/conclusion | A | unified_v2 / ablation_comp_v2 / c_hit | (already canonical) | verified, unchanged |
| N24 | main.tex:569–572 | `tab:ablation` (2d −43/−36; leaf_rand −1/+7; leaf_freq −11/−3; 2e_K10 −63/−55) | corrected ablation C | A | ablation_comp_v2 | (matches) | verified, unchanged |
| N25 | main.tex:592 | C_hit 2e_K10 ≈−27; 2d −28.5; 2f_top14 −30.6 | pure-hit control | A | c_hit_v2 (−27.24) / c_hit (−28.54, −30.61) | (matches) | verified, unchanged |
| N26 | main.tex:604–605 | C 2e_K10 −55[−67,−42]; 2f_top14 −55[−67,−43] | competitive C indistinguishable | A | ablation_comp_v2 (−54.5 / −55.25) | (matches) | verified, unchanged |
| N27 | main.tex:628 | 452/523; 509/701; 265/317; 658; 187/187 | layout comparison (single-inst) | A | A/B `unified_v2` orig vs ta; **C 2e_K10 pair from `tiebreak_fix` (265/317, Phase 2.5b)** | (matches) | verified |
| N28 | main.tex:509 | open cost | open-cost stats | F→resolved | `unified_v2/matrix/raw.csv` (median 231.6) | **Phase 2.5b/2.6**: unreproducible 221/17/231/810 triple removed; §5.2 states ≈230 µs canonical median; `tab:overhead` 193–222 marked independent batch | fixed |
| N29 | main.tex:660,662,649,658 | cadence 26/29 µs; size 1GiB −70/−68; RAM 98→500 µs | robustness axes (indep. batches) | A | aging_v2 / size / cadence / RAM batches | not v1; within-axis | verified, unchanged |

## Canonical headline table

| Claim | Canonical value | Scope | Source |
|---|---:|---|---|
| orig baseline first-query | A **523** / B **749** / C_mixed **1087** µs | single-inst, orig, 1a | `unified_v2` baseline |
| 2f_slru first-query | A **108** / B **107** / C **102** µs; **−79% to −91%** (A −79, B −86, C −91) | single-inst, orig async | `unified_v2` 2f_slru |
| interior skeleton (2d) warm e2e | ≈ **−25%** (A, B cross-seed); C_hit **−28.5%** [−34.9,−19.6] | cross-seed; C_hit orig-only | `tiebreak`/`seeds`; `c_hit` |
| A genuine-skew leaf bonus | 2d ≈ **−25%** → 2e_K10 ≈ **−36%** [−50,−23] | cross-seed, A orig | `tab:seeds` (Phase 2) |
| C_mixed 2e_K10 (cross-seed) | **−54.5%** (≈−55%) [−66.6,−42.2] | bimodal: miss-first ≈−70%, hit-first ≈−31% | `ablation_comp_v2` |
| competitive C | 2e_K10 **−54.5%** [−66.6,−42.2] ≈ 2f_top14 **−55.2%** [−66.8,−43.2] → **statistically indistinguishable** | cross-seed, C orig | `ablation_comp_v2` |
| corrected ablation C | 2d **−36%** robust; leaf_freq_K10 **−3%** (tie); leaf_rand_K10 **+7%** (worse); 2e_K10 **−55%** bimodal | cross-seed, C orig | `ablation_comp_v2` |
| C_hit | 2e_K10 **−27.2%** [−34.6,−17.7]; 2d **−28.5%** [−34.9,−19.6]; 2f_top14 **−30.6%** [−37.1,−22.4]; learned **−29.0%** [−36.1,−19.4] | orig-only, 10×10 | `c_hit_v2` (2e); `c_hit` (rest) |
| C_mixed 2e_K10 (single-inst) | 1071 → 265 µs, −75% | seed-1 single-instantiation, labeled | `tiebreak_fix/master_summary.csv` |
| layout best warm e2e (single-inst) | A 452/523 · B 509/701 (orig/ta) `unified_v2`; C_mixed 265/317 (orig/ta) `tiebreak_fix` | single-instantiation, per-workload same-batch | `unified_v2` (A/B) + `tiebreak_fix` (C) |
| 2f_slru delivery | 0.8 to 7 ms (A/B ≈7 ms; C ≈0.76 ms) | preprocessing | `unified_v2` deliver_us |
| open cost | ≈ 230 µs (canonical per-rep median 231.6, `unified_v2`); `tab:overhead`'s 193–222 is an independent overhead batch | constant, common-mode | `unified_v2/matrix/raw.csv` open_us |
| LibPrefetch | Δdeliver 10–16× ordering; "consistent with" | mechanism | `baselines_v2` lp |
| aging | YD static-freq decays; YE/structural stable | orig, 11 checkpoints | `aging_v2` |

## Historical Phase 2.5a snapshot — SUPERSEDED by Phase 2.5b (not current guidance)

> **⚠ This table is a historical record of the Phase 2.5a `tab:e2e-ac` rebuild,
> which still included the tie-break-impact cells (C `2e_K10`, A `2e_K500`) sourced
> from `unified_v2` on a "materially identical" rationale. That rationale was
> RETRACTED in Phase 2.5b: those two rows were removed from the absolute table and
> moved to `tab:corrected-arms` (from `tiebreak_fix`). The current paper table
> lists only baseline / layers_5 / 2d / 2f_slru. Do not use the `2e_K10` / `2e_K500`
> rows below as canonical.**

Baseline A = 523 µs, C = 1087 µs. Parenthetical = paired % vs same-workload
same-batch baseline.

| Strategy | A e2e_std | A e2e_warm | C e2e_std | C e2e_warm | Cross-seed verdict |
|---|---:|---:|---:|---:|---|
| Baseline | 523 | 523 | 1087 | 1087 | — |
| layers_5 | 679 (+30%) | 453 (−14%) | 1352 (+24%) | 1120 (+3%) | A tie; C robust (worse) |
| 2d | 678 (+30%) | 452 (−14%) | 969 (−11%) | 735 (−32%) | A robust (−25%); C robust (−36%) |
| 2e_K10 | 694 (+33%) | 464 (−11%) | 501 (−54%) | 268 (−75%) | A robust (−36%); C robust, bimodal (−55%) |
| 2e_K500 | 1311 (+150%) | 1083 (+107%) | 915 (−16%) | 680 (−37%) | A robust (worse); C robust (−31%) |
| 2f_slru | 7552 (+1343%) | 7324 (+1300%) | 1196 (+10%) | 962 (−12%) | A robust (worse); C robust (−7%) |

**Corrected-cell note.** C `2e_K10` and A `2e_K500` are in the tie-break impact
set. Their single-instantiation values are materially unchanged by the
correction (C `2e_K10`: `unified_v2` 267.7 µs vs `tiebreak` 265.4 µs, both −75%;
A `2e_K500`: 1083 vs 1079 µs). The correction's material effect is cross-seed
(`tab:ablation`, `tab:seeds`); the verdict column carries the corrected
cross-seed direction. The table is therefore presented from the single
`unified_v2` machine-state batch to keep absolute µs same-batch-comparable.

## Programmatic verification (STEP 5)

Percentage formula (uniform): `improvement_pct = (baseline − strategy) / baseline × 100`,
paired within batch. Cross-seed values are the pipeline's per-seed paired means
+ bootstrap CI read directly from the canonical `uncertainty.csv` (not recomputed
from aggregated absolute means).

- 2f_slru first-q: A (523.36−108.25)/523.36 = **−79.3%**; B (748.81−106.77)/748.81 = **−85.7%**; C (1086.82−101.50)/1086.82 = **−90.7%** → range **−79% to −91%** ✓ (matches abstract).
- C 2e_K10 single-inst warm: unified (1086.82−267.70)/1086.82 = **−75.4%**; tiebreak (1070.68−265.44)/1070.68 = **−75.2%** → **−75%** ✓.
- A 2f_slru warm single-inst: (7324.38−523.36)/523.36 = **+1299.5% → +1300%**; std (7551.70−523.36)/523.36 = **+1342.9% → +1343%** ✓.
- A 2f_slru first-q improvement (abs): 523.36−108.25 = **415 µs** ✓ (was 402).
- B 2f_slru warm single-inst: (7328.21−748.81)/748.81 = **+878.6% → +879%** ✓.
- C 2f_slru warm: single-inst unified **−11.5% → −12%**; cross-seed ablation_comp_v2 **−7.06% → −7%** ✓.
- ablation_comp_v2 read-back: 2d e2e_warm −35.89 (−36); leaf_freq −3.06 (−3, tie); leaf_rand +7.35 (+7); 2e_K10 −54.5 (−55) ✓.
- competitive read-back: C 2e_K10 −54.5 [−66.56,−42.19]; C 2f_top14 −55.25 [−66.84,−43.19] → indistinguishable ✓.
- C_hit read-back: 2e_K10 −27.24 [−34.6,−17.7]; 2d −28.54 [−34.93,−19.55]; 2f_top14 −30.61 [−37.09,−22.42]; learned_14 −29.01 [−36.11,−19.38] ✓.
- layout: A orig best 452.04 / ta 523.14; B 508.69 / 701.33; C 267.70 / 318.78; A ta baseline 658.33 ( +25.8% vs 523.36 → +26%); pread floor A orig 187.02 / ta 186.86 ✓.

Commands used: one-off `python3` `csv` readers over the canonical CSVs
(`unified_v2/matrix/summary.csv`, `tiebreak_fix/master_summary.csv`,
`ablation_comp_v2/uncertainty.csv`, `c_hit/uncertainty.csv`,
`c_hit_v2/uncertainty.csv`, `competitive/uncertainty.csv`); no permanent
dependency added; no CSV modified.

## Tables audited

| Table | Rows | Batch source(s) | Absolute values mixed? | Relative only? | Action |
|---|---|---|---|---|---|
| `tab:measurement-model` | layer states | none | no | n/a | unchanged |
| `tab:strategies` | hotset sizes | structural (368 KB, 17.7 MB…) | no | n/a | unchanged |
| `tab:ceiling` | first-q ceiling | unified_v2 (+tiebreak C 2e_K10) | single batch | mixed (abs+%) | numbers fixed (N7–N8) |
| `tab:overhead` | open/deliver | unified_v2 | single batch | n/a | unchanged (open/deliver already canonical) |
| `tab:e2e-ac` | A/C single-inst e2e | unified_v2 (single machine state) | single batch after rebuild | abs+% same-batch | **rebuilt** (N13–N15) |
| `tab:ablation` | corrected ablation C | ablation_comp_v2 | single batch | relative | unchanged (canonical) |
| `tab:competitive` | A/B + C competitive | **mixed**: A/B `results/competitive`; C `ablation_comp_v2` (2f_top500 = prior-art) | **cross-batch** | relative paired only | C 2f_slru fixed; per-source caption note added |
| `tab:seeds` | cross-seed | tiebreak/seeds (Phase 2) | relative only | yes | unchanged (canonical) |
| `tab:guidance` | recommendations | mixed relative | no absolute compare | relative | unchanged (already canonical) |

## Cross-batch table decisions

1. **`tab:e2e-ac`** — kept as a single-batch (`unified_v2`) absolute-µs table
   containing **only tie-break-unaffected strategies** (baseline, `layers_5`,
   `2d`, `2f_slru`). **[RETRACTED / superseded by Phase 2.5b — see below.]** The
   Phase 2.5a version left the two impact-set cells (C `2e_K10`, A `2e_K500`) in
   this table sourced from `unified_v2` on a "materially identical" rationale.
   That exception is **withdrawn**: canonical supersession is not waived by
   numerical closeness. Phase 2.5b removes those two rows from the `unified_v2`
   table entirely and reports them from their own corrected batch in a separate
   relative table (`tab:corrected-arms`).
2. **`tab:competitive`** — genuinely cross-batch and cannot be made single-batch
   (A/B cross-seed competitive exists only in the prior-art `results/competitive`
   batch; `baselines_v2` is single-seed with no CI). Resolution per STEP 10:
   present **relative paired improvements only** (the table already does), fix
   the one C cell that has a canonical corrected value (`2f_slru` −12→−7), and
   add a **per-source caption note** marking A/B as the prior-art batch, the C
   `2e_K10`/`2f_top14`/`2f_slru` as the corrected `ablation_comp_v2` rerun, and
   `2f_top500` as a prior-art-only arm (not re-measured in the corrected rerun).
   No absolute µs are compared across columns; the `2f_slru` anchor is not used
   as a conversion factor.

## Values changed

- Baselines 529/760/1096 → **523/749/1087** (N1–N5, N13).
- 2f_slru first-query 127/128/123 µs (−76/−83/−89 %) → **108/107/102 µs (−79/−86/−91 %)**; span −76~89 → **−79~91** (N5, N12).
- First-query ceilings/plateaus (N6–N9): A −22–26 → −27–30; A 2e_K500 −60→−64; A dump −76→−79; B −83→−86; C −38→−39; C 2e_K10 −81→−83.
- `tab:e2e-ac` full A/C body rebuilt from `unified_v2` (N14); C 2f_slru verdict −9→−7 (N15).
- §5.2 prose (N16, N18): 7134/529→7324/523; +1248→+1300; +1285→+1343; 402→415 µs; +843(B)→+879; C 2f_slru −19(−9)→−12(−7); A targeted −7~−9→−11~−14; C −73→−75.
- Reconciliation +1248 → +1300 (N20).
- `tab:competitive` C 2f_slru −12→−7 [−12,−2] (N21); per-source caption note (N22).

## Values retained intentionally

- **Abstract/contribution/conclusion/guidance** (N23): already canonical
  (−79~91, 25–30%, 0.8–7 ms, A −25→−36, C_hit −27~30); untouched.
- **`tab:ablation`, `tab:competitive` C 2e_K10/2f_top14, C_hit prose,
  layout comparison** (N24–N27): verified against source CSVs, already canonical.
- **C 2e_K10 single-inst 1071→265 −75%** (N17): reported from `tiebreak_fix` in
  `tab:corrected-arms`, labeled single-instantiation with the corrected cross-seed
  −55% in the same paragraph. *(Phase 2.5b changed the value/source from the
  earlier `1087→268` unified_v2 snapshot; the old snapshot is no longer used.)*
- **Robustness-axis numbers** (N29): not v1 artifacts, each within its own batch;
  retained. *(Open-cost is no longer a "retained" item — see below.)*
- **A/B competitive columns + 2f_top500** (N22): no canonical corrected
  replacement exists; retained under an explicit independent-batch caption note.

## Figure-internal stale numbers — RESOLVED in Phase 3

Full traceability: [`docs/figures/FIGURE_SOURCE_MAP.md`](../figures/FIGURE_SOURCE_MAP.md).

- **`figures/13_strategy_firstq_bars.png`** — **regenerated** (Phase 3). Redesigned
  as a *paired first-query reduction* chart: each bar is normalized to its own
  same-batch baseline, per-cell canonical source (`unified_v2` unaffected;
  `tiebreak_fix` for impact-set cells, hatched). No absolute µs; no v1 values.
  Caption/prose (`fig:firstq-bars`) rewritten to the relative metric; pending
  note removed.
- **`figures/14_strategy_endtoend_stacked.png`** — **regenerated** (Phase 3).
  Single-batch absolute stack (`unified_v2`) restricted to the tie-break-unaffected
  arms (baseline, layers_5, 2d, 2f_slru); corrected hotspot arms are *excluded*
  and reported in `tab:corrected-arms`. C panel correctly titled
  **C\_mixed (~50% not-found)** (no "churn-heavy"). Warm % from same-batch
  baseline: A `2f_slru` +1300%, B +879%, C −12%. Caption/prose updated; pending
  note removed.
- **`figures/17_lever_ablation.png`** — **regenerated and scoped to C_mixed**
  (Phase 3 fixed a content-stale paper copy; **Phase 3b** then removed the A/B
  panels). Now a **C_mixed-only** corrected same-batch ablation from the single
  canonical source `results/ablation_comp_v2` (2d −43%/−36%; leaf_freq
  −11%/−3% tie; leaf_rand −1%/+7% control; 2e_K10 −63%/−55%), two panels
  (first-query and warm e2e). The script no longer reads `results/ablation`, and
  the earlier "A/B pre-fix ablation is tie-break-unaffected/canonical" claim is
  **withdrawn** — the A/B levers are characterized by the cross-seed sweep
  (`tab:seeds`), not by this figure. Caption/prose updated to match.
- `18_capability_matrix.png` (qualitative), `01_page_distribution.png`
  (structural), `16_ram_pressure_sweep.png` (RAM axis) — verified byte-identical
  to the committed copies; current-valid, not regenerated.

## Validation

- **`git diff --check`** (paper): clean, no whitespace/conflict errors.
- **Brace balance**: 983 `{` / 983 `}` (escaped braces stripped), diff 0.
- **Table column counts**: `tab:e2e-ac` 5 `&` per row → 6 columns (matches the
  `\multicolumn{2}` A/C + verdict header); `tab:competitive` 4 `&` per row → 5
  columns (Arm, Footprint, A, B, C). Consistent.
- **Duplicate `\label`**: none (0).
- **Dangling `\ref`/`\eqref`**: none — all 41 references resolve to the 60
  defined labels. No new labels/refs were introduced by this phase (edits are
  numeric + caption text; the figure-note `\ref`s reuse existing labels
  `sec:eval-fq`, `tab:e2e-ac`).
- **Citations**: all 24 `\cite` keys present in `sample.bib` (0 missing).
- **LaTeX compile**: **environment limitation** — no `latexmk`/`pdflatex`/`tex`
  and no `Makefile` in the container; a full PDF build could not be run. The
  strongest available static validation (above) was performed instead. Edits are
  confined to text/number tokens and table cell bodies inside otherwise-unchanged
  environments, so no structural (compile-breaking) change was made.

## Unresolved numeric issues

1. ~~Figures 13 and 14 remain v1 internally; figure 14's C panel mistitled
   "churn-heavy"~~ → **RESOLVED in Phase 3**: figures 13, 14 (and the
   content-stale paper copy of 17) regenerated from canonical sources; C panels
   correctly labelled C\_mixed; captions/prose updated; pending notes removed.
   See the "Figure-internal stale numbers — RESOLVED in Phase 3" section above
   and [`docs/figures/FIGURE_SOURCE_MAP.md`](../figures/FIGURE_SOURCE_MAP.md).
   **No paper-visible stale figure remains.**

The three Phase 2.5a provenance blockers below are **RESOLVED in Phase 2.5b**
(see next section):

2. ~~A/B cross-seed competitive numbers have no canonical source~~ → **resolved**:
   `results/competitive` added to `RESULT_PROVENANCE.md` §4.8 as an independent,
   relative-only source, with evidence it is tie-break-unaffected for A/B.
3. ~~Open-cost 221/17/231/810 triple not reproducible~~ → **resolved**: the exact
   triple is removed from the paper; replaced with the reproducible approximate
   envelope (≈200–235 µs, common-mode).
4. ~~`tab:e2e-ac` used superseded `unified_v2` cells for C `2e_K10` / A
   `2e_K500`~~ → **resolved**: those rows removed; corrected arms reported from
   `tiebreak_fix` in `tab:corrected-arms`.

## Phase 2.5b corrections

### tab:e2e-ac atomic fix
- Removed the two impact-set rows from the `unified_v2` absolute table: the
  `2e_K10` row (its C cell is superseded) and the `2e_K500` row (its A cell is
  superseded). The table now lists only tie-break-unaffected strategies:
  **baseline, `layers_5`, `2d`, `2f_slru`** — every absolute µs from one batch.
- Added **`tab:corrected-arms`** (relative table) reporting the corrected hotspot
  arms from `results/tiebreak_fix/master_summary.csv`, each paired with its own
  same-batch baseline: A `2e_K500` (512 → 1079 µs, **+111%**), C\_mixed `2e_K10`
  (1071 → 265 µs, **−75%**). Caption forbids column-wise absolute comparison with
  `tab:e2e-ac`.
- **Retracted** the "materially identical, therefore keep in unified_v2" caption
  exception; new caption states the impact arms are reported separately so every
  µs in `tab:e2e-ac` is single-batch.

### Corrected C single-instantiation value
- Prose (§5.2) now reads **1071 → 265 µs (−75%)** sourced from `tiebreak_fix`
  (same-batch baseline 1070.68, `2e_K10` warm 265.44, paired −75.2%), replacing
  the `unified_v2`-batch snapshot `1087 → 268`. All `1087→268` current-value
  occurrences removed; the residual `268` (layout comparison `tab`/`:616`) is a
  different arm/statistic (best-warm layout comparison) and unaffected.

### A 2e_K500
- Retained as a supported point in `tab:corrected-arms` (illustrates leaf-budget
  over-provisioning: +111% regression on A), sourced from `tiebreak_fix`. Its
  first-query −64% in `tab:ceiling` is a relative reduction that reads identically
  from the corrected batch (tiebreak paired −64.3%).

### tab:seeds single-workload consistency
- The rebuilt `tab:e2e-ac` exposed that `tab:seeds`' *single-workload* column
  still held old `results/main` single-inst values (A `2d` −8, A `2e_K10` −7, A
  `layers_5` −9, B `2d` −31, C `2d` −31) that contradicted the new `unified_v2`
  table. Aligned the column to `unified_v2`: **A `2d` −14, A `2e_K10` −11, A
  `layers_5` −14, B `2d` −32, C `2d` −32** (C `2e_K10` single stays −75 from
  `tiebreak`). Narrative "single-instantiation estimate of −7%" → **−11%**. The
  *cross-seed* column is unchanged (its frequency arms C/B `2e_K10` already match
  `tiebreak` exactly; `2d`/`layers_5` cross-seed are the tie-break-unaffected
  `results/seeds` arms now blessed in §4.8).

### Open-cost
- The exact `221 µs / sd 17 / p95 231 / 810 reps` triple is **not reproducible**
  from the canonical batch. `results/unified_v2/matrix/raw.csv` (non-warmup,
  non-baseline, `open_us>0`) gives **n=1440, median 231.6, sd 9.9 (CV 4%), p95
  236.8, 5th–95th 223–237 µs** — a different count and centre; `tab:overhead`'s
  per-strategy 193–222 is from yet another batch. Statistical basis (the 810
  count) is therefore unclear. Per the "口徑不明" branch, the precise triple is
  **removed**. *(Phase 2.6 finalized the wording:* §5.2 now states the canonical
  per-rep median **≈230 µs** (`unified_v2`), and `tab:overhead`'s caption marks
  its per-strategy 193–222 µs as an **independent overhead-decomposition batch**,
  distinct from the canonical open median — the two batches are not merged into a
  single range.* No pending note remains.
  - Reproduction command: `python3` over `results/unified_v2/matrix/raw.csv`
    filtering `warmup==0 && strategy!='baseline' && open_us>0`, `statistics`
    module. Output above.

### A/B competitive provenance (RESULT_PROVENANCE.md §4.8)
- **Option A (provenance-valid).** `results/competitive` is a complete 10-seed
  batch (per-seed paired vs same-seed baseline, bootstrap 95% CI, `2f_slru`
  anchor, `sweep.log` reproducible; arms `2e_K10`, `2f_top14/28/100/500`,
  `2f_slru`). Added as a new canonical class in §4.8 for the **A/B within-batch
  competitive comparison**, relative-only, with C superseded by
  `ablation_comp_v2`. Evidence it is tie-break-unaffected for A/B: the corrected
  `tiebreak_fix` rerun reproduces A/B `2e_K10` within noise (A −38.2 vs −37.9; B
  −23.8 vs −25.2) and `2f_slru` is a ranking-free full dump. Also blessed
  `results/seeds` (tie-break-unaffected `2d`/`layers_N` arms) for the `tab:seeds`
  cross-seed column.
- **RESULT_PROVENANCE.md modified**: yes — §4.8 scope addenda only (two new
  canonical-class rows + rationale). No §4.2 freeze row altered; no CSV/result
  touched.

## Phase 2.6 corrections (residual narrative & scope cleanup)

Text/scope-only pass; no numbers rest on a superseded source after this.

1. **Workload setup** — `tab:workloads` and §7 prose corrected: C relabelled
   **C\_mixed** (mixed tail-boundary, ~50% not-found); removed the
   "recently-ingested event data / log-stream" scenario and the "full-table scan"
   scenario for B; the blanket "all draw from the full 600k range" now split
   (A/B full range; C\_mixed high-key tail, upper half beyond max id). Added
   **C\_hit** (orig-only pure-hit control) and **YD/YE** (read-latest /
   short-ranges) workload definitions.
2. **Skeleton range** — §6.2 "2d −25% to −36% across A/B/pure-hit" → **−25% to
   −30%** (A −25, B −25, C\_hit −28.5); the −36% is explicitly attributed to A's
   `2e_K10` skew bonus and C\_mixed's not-found-inflated `2d`, not the general
   skeleton.
3. **Aging** — added a **"Static-plan staleness under a moving hotspot"**
   robustness subsection from `results/aging_v2/aging_ci.csv`: under YD
   (non-stationary) the frozen frequency plan decays (**−50%→−33%** ck0→ck10)
   while the structural plan holds (**−53%→−53%**); under stationary YE both stay
   flat. The 50k-churn "no decay / recomputation unnecessary" claim is now scoped
   to a **stationary read hotspot**.
4. **Size scaling** — the pre-fix C `2e_K10` −70/−68 figures are marked
   **diagnostic only** (corrected leaf-selector magnitude not re-validated across
   sizes); the size claim now rests on the tie-break-unaffected `2d` and the
   deliver-cost trend.
5. **Recommendation** — §6.4 prose: default = **`1a` + `2d`**; `2e_K10` only with
   independently validated stable skew; moving hotspot → structural coverage /
   refresh (matching `tab:guidance`).
6. **Open cost** — §5.2 states canonical per-rep median **≈230 µs**
   (`unified_v2`); `tab:overhead` caption marks its 193–222 µs as an independent
   overhead-decomposition batch (not merged into one canonical range).
7. **Competitive caption** — notes A/B come from a pre-fix independent batch and
   the corrected rerun reproduces A/B `2e_K10` within noise (A −37.9 vs −38.2; B
   −25.2 vs −23.8); relative-only, no cross-batch absolute comparison.
8. **Novelty** — conclusion "This work is the first" → **"To our knowledge, this
   is the first … (pending fuller literature verification)"**; contribution
   "for the first time" → "to our knowledge for the first time".

## Phase 4 freeze (2026-07-12)

Paper-wide canonical freeze completed. Every quantitative claim is inventoried in
[`PAPER_CLAIM_MANIFEST.csv`](PAPER_CLAIM_MANIFEST.csv) (128 claims) and machine-
verified by [`tools/verify_paper_atomicity.py`](../../tools/verify_paper_atomicity.py)
— 111 recomputed from canonical CSVs + 17 scope-checked, **0 FAIL**. Full audit:
[`PAPER_FINAL_CANONICAL_AUDIT.md`](PAPER_FINAL_CANONICAL_AUDIT.md).

One residual atomic violation was found and fixed: `tab:seeds` B `2e_K10`
single-workload printed **−29%** (superseded unified_v2); B 2e_K10 is a tie-break
changed cell, so the atomic-correct value is **−30%** from `tiebreak_fix`. Fixed.

All figure/numeric pending items from earlier phases are now resolved; no
paper-visible stale figure or number remains.
