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
| N14 | main.tex:520–524 | entire A/C body (480,487,490,291,7134,…) | `tab:e2e-ac` single-inst e2e | C | unified_v2 (C 2e_K10, A 2e_K500 ≡ tiebreak, materially identical) | rebuilt (see table) | fixed |
| N15 | main.tex:524 | C 2f_slru verdict −9% | cross-seed | E | ablation_comp_v2 C 2f_slru e2e_warm | −7% | fixed |
| N16 | main.tex:531 | 7134 vs 529; +1248%; +1285%; 402 µs; −19%(−9%) | §5.2 prose | C/G | unified_v2 (A/C single-inst) + ablation_comp_v2 | 7324 vs 523; +1300%; +1343%; 415 µs; −12%(−7%) | fixed |
| N17 | main.tex:534 | 1087 → 268 µs, −75% | C 2e_K10 single-inst, labeled | A | unified_v2 C 2e_K10 warm (267.7); tiebreak paired −75.2% | retained (canonical) | verified |
| N18 | main.tex:544 | +1248%(A)/+843%(B); −7 to −9 (A); −73 (C) | fig:e2e-stacked prose | C/G | unified_v2 single-inst | +1300%/+879%; −11 to −14 (A); −75 (C) | fixed + pending note |
| N19 | main.tex:539 | (narrative caption) | fig:e2e-stacked caption | A | — | pending note added | fixed (note) / figure pending |
| N20 | main.tex:596,610 | +1248% (×2) | reconciliation to single-inst | G | unified_v2 A 2f_slru warm | +1300% | fixed |
| N21 | main.tex:607 | C 2f_slru −12% [−17,−7] | `tab:competitive` C column | D | ablation_comp_v2 C 2f_slru e2e_warm | −7% [−12,−2] | fixed |
| N22 | main.tex:604–607 | A/B columns; 2f_top500 row | prior-art competitive | E-scope | results/competitive (A/B, indep. batch); 2f_top500 not in corrected rerun | retained + per-source caption note | fixed (note) |
| N23 | main.tex:52,121,129,674,678,702 | −79 to −91; 25–30%; 0.8–7 ms; A −25→−36; −27 to −30 | abstract/contrib/guidance/conclusion | A | unified_v2 / ablation_comp_v2 / c_hit | (already canonical) | verified, unchanged |
| N24 | main.tex:569–572 | `tab:ablation` (2d −43/−36; leaf_rand −1/+7; leaf_freq −11/−3; 2e_K10 −63/−55) | corrected ablation C | A | ablation_comp_v2 | (matches) | verified, unchanged |
| N25 | main.tex:592 | C_hit 2e_K10 ≈−27; 2d −28.5; 2f_top14 −30.6 | pure-hit control | A | c_hit_v2 (−27.24) / c_hit (−28.54, −30.61) | (matches) | verified, unchanged |
| N26 | main.tex:604–605 | C 2e_K10 −55[−67,−42]; 2f_top14 −55[−67,−43] | competitive C indistinguishable | A | ablation_comp_v2 (−54.5 / −55.25) | (matches) | verified, unchanged |
| N27 | main.tex:616 | 452/523; 509/701; 268/319; 658; 187/187 | layout comparison (single-inst) | A | unified_v2 orig vs ta | (matches) | verified, unchanged |
| N28 | main.tex:507 | open 221 µs median, sd 17, p95 231, 810 reps | open-cost stats | A | (raw per-rep; unified_v2 open medians 226–236, ≈200) | retained (defensible; not v1) | verified |
| N29 | main.tex:660,662,649,658 | cadence 26/29 µs; size 1GiB −70/−68; RAM 98→500 µs | robustness axes (indep. batches) | A | aging_v2 / size / cadence / RAM batches | not v1; within-axis | verified, unchanged |

## Canonical headline table

| Claim | Canonical value | Scope | Source |
|---|---:|---|---|
| orig baseline first-query | A **523** / B **749** / C_mixed **1087** µs | single-inst, orig, 1a | `unified_v2` baseline |
| 2f_slru first-query | A **108** / B **107** / C **102** µs; **−79% to −91%** (A −79, B −86, C −91) | single-inst, orig async | `unified_v2` 2f_slru |
| interior skeleton (2d) warm e2e | ≈ **−25%** (A, B cross-seed); C_hit **−28.5%** [−34.9,−19.6] | cross-seed; C_hit orig-only | `tiebreak`/`seeds`; `c_hit` |
| A genuine-skew leaf bonus | 2d ≈ **−25%** → 2e_K10 ≈ **−36%** [−50,−23] | cross-seed, A orig | `tab:seeds` (Phase 2) |
| C_mixed 2e_K10 (single-inst) | 1087 → **268 µs**, **−75%** | seed-1 single-instantiation only | `unified_v2` 267.7 / `tiebreak` paired −75.2% |
| C_mixed 2e_K10 (cross-seed) | **−54.5%** (≈−55%) [−66.6,−42.2] | bimodal: miss-first ≈−70%, hit-first ≈−31% | `ablation_comp_v2` |
| competitive C | 2e_K10 **−54.5%** [−66.6,−42.2] ≈ 2f_top14 **−55.2%** [−66.8,−43.2] → **statistically indistinguishable** | cross-seed, C orig | `ablation_comp_v2` |
| corrected ablation C | 2d **−36%** robust; leaf_freq_K10 **−3%** (tie); leaf_rand_K10 **+7%** (worse); 2e_K10 **−55%** bimodal | cross-seed, C orig | `ablation_comp_v2` |
| C_hit | 2e_K10 **−27.2%** [−34.6,−17.7]; 2d **−28.5%** [−34.9,−19.6]; 2f_top14 **−30.6%** [−37.1,−22.4]; learned **−29.0%** [−36.1,−19.4] | orig-only, 10×10 | `c_hit_v2` (2e); `c_hit` (rest) |
| layout best warm e2e (single-inst) | A 452/523 · B 509/701 · C_mixed 268/319 (orig/ta) | single-instantiation | `unified_v2` |
| 2f_slru delivery | 0.8 to 7 ms (A/B ≈7 ms; C ≈0.76 ms) | preprocessing | `unified_v2` deliver_us |
| open cost | ≈ 200 µs (median ≈221) per layout | constant | raw / `unified_v2` open_us |
| LibPrefetch | Δdeliver 10–16× ordering; "consistent with" | mechanism | `baselines_v2` lp |
| aging | YD static-freq decays; YE/structural stable | orig, 11 checkpoints | `aging_v2` |

## Rebuilt `tab:e2e-ac` (single-instantiation, `unified_v2`; orig, async)

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

1. **`tab:e2e-ac`** — kept as a single-batch (`unified_v2`) absolute-µs table.
   The two tie-break-set cells (C `2e_K10`, A `2e_K500`) are materially
   identical at single-instantiation to their `tiebreak_fix` values, so no
   cross-batch mixing of absolute µs is introduced; the corrected cross-seed
   direction is carried in the verdict column and cited to §6.2/§6.3. This
   satisfies the atomic rule (baseline, strategy, and `2f_slru` anchor all from
   the same `unified_v2` batch).
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
- **C 2e_K10 single-inst 1087→268 −75%** (N17): correctly labeled
  single-instantiation with the corrected cross-seed −55% in the same paragraph;
  retained.
- **Open-cost 221 µs / robustness-axis numbers** (N28–N29): not v1 artifacts,
  each within its own batch; retained.
- **A/B competitive columns + 2f_top500** (N22): no canonical corrected
  replacement exists; retained under an explicit independent-batch caption note.

## Figure-internal stale numbers pending Phase 3

- **`figures/13_strategy_firstq_bars.png`** — bars are labeled with v1 values:
  baselines **529/760/1096**, `2f_slru` **127/128/123**, C `2e_K10` **211**, etc.
  Cannot be regenerated in Phase 2.5 (no re-run / no figure regeneration).
  Caption (`main.tex:479`) and referencing prose (`:483`) updated to canonical
  values **with an explicit note that the image itself still shows the
  pre-canonical batch**.
- **`figures/14_strategy_endtoend_stacked.png`** — bars labeled with v1
  single-instantiation e2e: A `2f_slru` **+1248%**, B **+843%**, C `2e_K10`
  **−73%**, A `2e_K10`/`2d`/`layers_5` **−7/−8/−9%**, etc.; the C panel is also
  **mistitled "churn-heavy"** (C is file-tail / C_mixed). Caption (`:539`) and
  prose (`:544`) updated to canonical with a pending note. **Both figures must be
  regenerated from the canonical batches in Phase 3.**
- `figures/17_lever_ablation.png` and `18_capability_matrix.png` were already
  regenerated with post-fix data (RESULT_PROVENANCE §4.7); `01`, `16` are
  structural/other-axis and not affected by the v1→v2 swap.

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

1. **Figures 13 and 14 remain v1 internally** (image pixels), and figure 14's C
   panel is mistitled "churn-heavy". These are the only remaining paper-visible
   stale numbers; they are **out of scope for Phase 2.5** (no figure
   regeneration) and are explicitly deferred to Phase 3. Text/captions no longer
   claim the figures are canonical.
2. **A/B cross-seed competitive numbers** (`tab:competitive`, +762%/+730%,
   2e_K10/2f_top14/2f_top500 on A/B) have **no canonical corrected source** —
   they exist only in the prior-art `results/competitive` batch (`baselines_v2`
   is single-seed). `2f_slru` and the `2f_topN` dumps are frequency- or
   dump-based; `2f_slru` (a full dump) is not affected by the leaf tie-break, so
   its A/B values are sound; the A/B `2f_topN` values are retained under the
   independent-batch caption note but were not independently re-verified against
   a corrected A/B rerun (none exists). Flagged for a future A/B competitive
   rerun if the competitive table is promoted to a headline claim.
3. **Open-cost 221 µs** (`:507`) is a raw-per-rep statistic ("810 reps") that is
   not reproducible from the summary CSVs alone (summary open medians cluster at
   226–236 µs); the "≈200 µs" headline is safe, but the exact 221/17/231 triple
   should be re-derived from `raw.csv` before camera-ready.
