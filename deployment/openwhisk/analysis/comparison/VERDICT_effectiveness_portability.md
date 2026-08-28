# Effectiveness portability: OpenWhisk vs workstation (49 comparable cells)

**Question.** Do prefetch strategies that are effective on the workstation stay
effective on the simulated serverless platform (OpenWhisk)?

**Method.** For each (workload, strategy) cell that BOTH platforms ran, compute the
relative first-query reduction versus that platform's own same-condition baseline:
`R = (baseline_fq − strategy_fq) / baseline_fq` (R>0 = faster = effective). Relative
reductions are the only cross-machine-comparable quantity; absolute microseconds are
not. This is a **descriptive cross-platform consistency check, not a causal-equivalence
or absolute-latency claim.** OpenWhisk uses **standalone** handles only — warm handles
carry a strong positional/order effect that makes warm first_query unusable for
strategy comparison. Source: `compare_effectiveness.py` (reads canonical workstation
`results/…/summary.csv` + frozen OpenWhisk `analysis/normalized/…_pairs.csv`, standalone
only). Per-cell table: `effectiveness_ow_vs_workstation.csv`; per-cell workstation
provenance: `ws_provenance.csv`.

**Coverage.** **49/49 comparable cells resolved** (YC 10, YCu 10, YCh01 10, C 10,
C_hit 9), completing the workstation-coverage matrix (the earlier 20 + 29 added by the
`portability_ext` campaign). The intersection is computed **mechanically** as
{OW standalone cells} ∩ {the same cell measured on the workstation from its per-cell
canonical source}; it is not hard-coded to a target. 4 OpenWhisk cells
(YC `2f_top102`, `learned_markov_102`, `leaf_freq_K10`, `leaf_rand_K10`) have no
workstation head-to-head measurement and are correctly excluded, leaving 49.

**Per-cell workstation provenance (deterministic; strict same-batch R).** Every cell's
strategy value and its no-prefetch baseline come from the SAME file + SAME db group
(`orig`, matching the OW-pinned orig-layout `test.db`) + SAME seed/fold — asserted
`same_batch = True` for all 49. Sources: YC/YCu/YCh01 → `native_headtohead{,_YCu,_YCh01}`
(per-seed); C_hit → `chit_headtohead` (per-seed); C ablation scope
{2d, 2e_K10, 2f_slru, 2f_top14, 2f_top28, leaf_freq_K10, leaf_rand_K10} →
`ablation_comp_v2/seed{01..10}` (per-seed); **C/2e_K500 → `unified_v2/matrix` (db=orig,
tie-break-unchanged main-matrix cell per RESULT_PROVENANCE §4.2/§4.4)**; **C/layers_5 →
`results/seeds/seed{01..10}` (db=orig, per-seed cross-seed robustness §4.8)**;
**C/learned_markov_28 → `results/learned_10fold/seed{1..10}` (per-LOSO-fold, model
trained on the other 9 seeds; a later additive canonical source superseding single-fold
`baselines_v2` for the learned comparison)**. C is NOT globally sourced from
ablation_comp_v2.

## Result

- **Strong strategies port.** Of the **35** cells strongly effective on the workstation
  (R_ws ≥ 0.30), **34 are also effective on OpenWhisk.** The one exception is **C / 2d**,
  a 3-pair static cell run fully position-imbalanced (0/3 target-first), whose OpenWhisk
  "harmful" reading is the standalone order artifact, not a regression (flagged
  `low_conf`). `2f_slru` sits at ~0.90 on both platforms in every workload.
- **Rank correlation (Spearman, R_ws vs R_ow):** ALL 49 cells ρ = **0.69**;
  high-confidence cells (38, excluding position-confounded / n≤3) ρ = **0.78**;
  per-workload YC 0.77, YCu 0.87, YCh01 0.66, C 0.76. **C_hit ρ = 0.13 is a
  range-restriction artifact**: all 9 C_hit cells are effective on both platforms
  (9/9 direction agreement), so there is almost no rank spread to correlate.
- **Direction agreement:** 38/49 cells agree on category (effective / neutral / harmful,
  ±10% band); 31/38 high-confidence cells.
- **Median |R_OW − R_WS| = 0.115.**

## The 11 disagreements (none is a strong-strategy portability failure)

Five are **WS-effective → OW-not-effective** (the claim-relevant direction): four are
*moderate* workstation cells (R_ws ≈ 0.21) that fall just under the OW ±10% band —
`YCu/learned_markov_28` (0.22→0.08), `YCh01/2f_top14` (0.21→−0.02),
`YCh01/learned_markov_14` (0.21→0.07), `C/leaf_freq_K10` (0.21→0.08); the smallest-budget
N=14 variants are the ones that thin out on OpenWhisk. The fifth is the
position-confounded `C/2d` above.

Five are **WS-neutral → OW-effective** (OpenWhisk shows *more* benefit, not a failure of
the "effective ports" claim): `YC/layers_5`, `YCu/layers_5`, `YCu/learned_markov_14`,
`YCh01/layers_5`, `C/leaf_rand_K10`. One is **WS-neutral → OW-harmful**: `C/layers_5`
(0.03→−0.71), again a 3-pair static cell run 0/3 position-imbalanced (`low_conf`).

Category agreement is threshold-sensitive for the near-zero strategies (`layers_5`,
`leaf_freq_K10`, `leaf_rand_K10` sit on the band). The threshold-free rank correlation
(0.78 high-conf) is the more robust statistic.

## Conclusion (bounded, descriptive)

Across the full 49-cell workstation-coverage matrix, **strategy effectiveness is
consistent between the workstation and OpenWhisk in the descriptive sense that matters
for the thesis**: strong strategies stay strong (34/35), ranking is preserved
(ρ ≈ 0.78 on clean cells), and every sign flip is either a near-zero strategy at the
neutral boundary, a smallest-budget N=14 variant, or a position-confounded low-n static
cell. This is a cross-platform **consistency** result, NOT a claim of equal absolute
latency, equal effect size, causal equivalence, or hardware-independent speedup.

*Scope: standalone first_query only; relative reductions only; not a headline
warm-latency claim; the four OpenWhisk campaigns (3600 + 468 + 852) serve distinct
roles and are never pooled; no OpenWhisk evidence was rerun or altered.*
