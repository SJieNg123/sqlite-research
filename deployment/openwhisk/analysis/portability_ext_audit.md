# portability_ext — final validation & analysis-integration audit

Fourth additive OpenWhisk campaign (`portability_ext`) closing the workstation-coverage
effectiveness matrix from 20 → 49 cells. This record is **fail-closed**: every gate had
to pass against the frozen campaign before any REPORT.md strengthening. No OpenWhisk run
was repeated; no archived evidence was modified.

## Campaign identity (frozen; re-asserted, not recomputed)

| field | value |
|---|---|
| run_config_sha256 | `bf504a28fb0ac3cec3b189a4de1f7b8968a35bbd9866c2ae1d5784ccc3bf77da` |
| schedule_seed | 20260828 |
| live matrix fingerprint | `5ba26fe952104792a9b6803e581627c331884fe1b39b41adb6ebeddb245fe300` |
| git_sha | `d2614e8aacf9` (descendant of committed `2c3c49aa…`) |
| bundle SHA-256 | `9fd7b9f69030c6ffa71532504b8a928c00de442ddc3d0f0d2cd6fa511f84c40f` |
| invocations / pairs | 852 / 426 (426 baseline + 426 target) |
| blocks | B5=36, B6=180, B7=90, B8=72, B9=24, B10=18, B11=6 = 426 pairs |
| keyed plans / static cells | 63 (2f_top14 15, learned_markov_14 12, 2e_K500 12, 2f_top28 12, learned_markov_28 12) / 8 (layers_92, layers_5, 2d @ seed 1) |

Isolation from the three prior byte-frozen campaigns re-verified: primary `022fbeb0…`,
secondary `441609e6…`, portability `64f44c3e…` unchanged.

## Gating audit (steps 1–9) — ALL PASS

1. **Bundle immutable** — recorded bundle SHA matches; raw = 852 `req_*`/`resp_*` pairs.
2. **Single campaign** — every invocation carries `run_config_sha256 = bf504a28…`; no
   foreign run-config bleed.
3. **Fingerprint** — live matrix fingerprint `5ba26fe9…` matches the frozen schedule
   (WK1 placeholder `bb87bfcd…` deliberately NOT used as the comparand).
4. **Shape** — 852 invocations / 426 pairs / 426 baseline / 426 target.
5. **Validity gates** — all invocations passed the frozen cold/plan gates.
6. **Run-config isolation** — normalization refuses any non-`bf504a28…` row.
7. **7 blocks exact** — B5–B11 pair counts match 36/180/90/72/24/18/6.
8. **63-plan parity** — per (workload_id, seed, strategy) the frozen plan SHA-256 in
   `portability_ext_freeze_report.json` matches the pin `keyed_strategy_plans` (targeted
   per-cell lookup: 63/63). `parity_type` = exact_native_plan 51 /
   semantic_contract_reconstruction 12 (2e_K500 reconstructed) / structural_static 8.
9. **Static + LOSO** — layers_92 = 92-interior skeleton (eip==92 invariant); learned_markov
   folds leakage-clean (test seed ∉ train_seeds).

## Analysis integration (steps 10–16)

- **Normalization** (`normalize_portability_ext.py`) → 852 invocations / 426 pairs,
  all gates green, written to `analysis/normalized/portability_ext/`. Kept separate from
  the primary/secondary/portability normalized outputs.
- **Descriptive** (`descriptive_portability_ext.py`) → 142 coverage cells, 71 target
  plans, parity {exact 51, semantic 12, static 8}, in `analysis/descriptive/portability_ext/`.
- **Effectiveness comparison** (`compare_effectiveness.py`, standalone handles only):

### Cell-count gate (step 12) — resolves to EXACTLY 49

Mechanical intersection = {OW standalone (workload,strategy)} ∩ {same cell measured on
the workstation from its per-cell canonical source}. **53 OW standalone cells − 4 OW-only
(YC 2f_top102 / learned_markov_102 / leaf_freq_K10 / leaf_rand_K10, never run on the
workstation head-to-head) = 49.** Not hard-coded. `same_batch` (strategy_source ==
baseline_source, same file+db+seed/fold) = True for all 49. Per-cell provenance in
`comparison/ws_provenance.csv`; C is sourced per-cell (see VERDICT), NOT globally from
ablation_comp_v2.

### Descriptive findings (steps 13–16)

- 34/35 strongly-effective (R_ws ≥ 0.30) workstation cells are effective on OpenWhisk;
  the lone exception `C/2d` is a position-confounded 3-pair static cell (0/3, low_conf).
- Spearman ρ: ALL 49 = 0.69, high-conf 38 = 0.78; per-workload YC 0.77 / YCu 0.87 /
  YCh01 0.66 / C 0.76; C_hit 0.13 is range-restriction (9/9 agree, all effective).
- Direction agreement 38/49 (31/38 high-conf); median |R_OW − R_WS| = 0.115.
- 11 disagreements: 5 WS-eff→OW-not (4 moderate/near-band, 1 confounded C/2d),
  5 WS-neutral→OW-eff, 1 WS-neutral→OW-harmful (confounded C/layers_5). None is a
  strong-strategy portability failure. Full table: `comparison/VERDICT_effectiveness_portability.md`.

## Scientific-claim boundary (step 13/17)

This is a **descriptive cross-platform consistency** result. It does NOT assert absolute
latency equivalence, equal effect size, causal portability, hardware-independent speedup,
or reproduction of the workstation performance ranking. The four campaigns
(3600 + 468 + 852) answer distinct questions and are **never pooled** into one estimator.
OpenWhisk remains a deployment complement; native/WK1 is the primary controlled evidence.
