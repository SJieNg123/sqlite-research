# Effectiveness portability: OpenWhisk vs workstation (55 first-query cells, REVISED freeze)

**Question.** Do prefetch strategies that are effective on the workstation stay
effective on the simulated serverless platform (OpenWhisk)?

**Method.** For each (workload, strategy) cell that BOTH platforms ran, compute the
relative first-query reduction versus that platform's own same-condition baseline:
`R = (baseline_fq − strategy_fq) / baseline_fq` (R>0 = faster = effective). Relative
reductions are the only cross-machine-comparable quantity; absolute microseconds are
not. This is a **descriptive cross-platform consistency check, not a causal-equivalence
or absolute-latency claim.** OpenWhisk uses **standalone** handles only — warm handles
carry a strong positional/order effect that makes warm first_query unusable for
strategy comparison.

**Frozen input (paper-facing).** This verdict is computed over the **revised** frozen
table `effectiveness_ow_vs_workstation_revised_freeze.csv` — the single authoritative
paper-facing input. Seven of the 55 cells carry their targeted, independently rebuilt,
**exactly position-balanced** replication estimates (five from the sixth campaign
`portability_outlier_replication`, two from the seventh `portability_ych01_followup`);
the other 48 are byte-carried from the historical freeze. The historical table is
preserved byte-identically at `effectiveness_ow_vs_workstation_historical_freeze.csv`
and the supersession record is `effectiveness_freeze_revision.json`. See "Freeze
revision" below.

**Coverage.** **55 first-query cells** (YC 10, YCu 10, YCh01 10, C 14, C_hit 11) + **10
libprefetch delivery-order cells = 65 matched (65/65).** 4 OpenWhisk cells
(YC `2f_top102`, `learned_markov_102`, `leaf_freq_K10`, `leaf_rand_K10`) have no
workstation head-to-head measurement and are correctly excluded from the workstation
coverage. The lp cells are compared separately by delivery order (`lp_delivery_order.csv`)
and are NOT mixed into the first-query rank correlation.

## Result (recomputed from scratch over the revised freeze)

- **Strong strategies port.** Of the **41** cells strongly effective on the workstation
  (R_ws ≥ 0.30), **all 41 are also effective on OpenWhisk (41/41).** Under the historical
  freeze three of these read "harmful" on OpenWhisk (C/2d, C/layers_92, C_hit/2e_K40);
  under exactly position-balanced replication all three are positive, so no strongly
  workstation-effective strategy is harmful on OpenWhisk. `2f_slru` sits at ~0.90 on both
  platforms in every workload.
- **Rank correlation (Spearman, R_ws vs R_ow):** ALL 55 cells ρ = **0.76**;
  high-confidence cells (46, excluding n≤3 / fully position-imbalanced) ρ = **0.79**;
  high-confidence **and non-position-sensitive** cells (42) ρ = **0.81**;
  per-workload YC 0.77, YCu 0.87, YCh01 0.82, C 0.70. **C_hit ρ = 0.25 is a
  range-restriction artifact**: all 11 C_hit cells are effective on both platforms
  (11/11 direction agreement), so there is almost no rank spread to correlate.
- **Direction agreement:** 46/55 cells agree on category (effective / neutral / harmful,
  ±10% band); 37/46 high-confidence; 34/42 high-confidence-and-non-position-sensitive.
- **Median |R_OW − R_WS| = 0.112.**

## The 9 disagreements (only one is OpenWhisk-negative, and it is workstation-neutral)

Three are **WS-effective → OW-neutral** (the claim-relevant direction): all are *moderate*
workstation cells (R_ws ≈ 0.21) that fall just under the OW ±10% band —
`YCu/learned_markov_28` (0.22→0.08), `YCh01/learned_markov_14` (0.21→0.07),
`C/leaf_freq_K10` (0.21→0.08); the smallest-budget N=14 / leaf-frequency variants are the
ones that thin out on OpenWhisk. **None is a strong (R_ws ≥ 0.30) strategy.**

Five are **WS-neutral → OW-effective** (OpenWhisk shows *more* benefit, not a failure of
the "effective ports" claim): `YC/layers_5`, `YCu/layers_5`, `YCu/learned_markov_14`,
`C/layers_5`, `C/leaf_rand_K10`.

One is **WS-neutral → OW-harmful**: `YCh01/layers_5` (R_ws ≈ 0.025 → R_ow −0.596). This is
the **only** OpenWhisk-negative cell in the table. Its 36-pair, exactly position-balanced
seventh-campaign replication is reproducibly negative (both position subsets negative:
baseline-first −0.742, target-first −0.447). Because R_ws ≈ +0.025 is approximately
neutral, this is an OpenWhisk-negative result for a **workstation-neutral** strategy — NOT
the failure of a strongly workstation-effective strategy.

**Position-sensitive cells (4).** `C/layers_92`, `C/2d`, `YCu/layers_5`, `YCh01/2f_top14`
carry a positive *balanced aggregate* whose baseline-first and target-first subsets
disagree in sign. Their aggregate is a **descriptive balanced-batch estimate**, not a
clean position-independent causal effect; the dependence is a pair-position / short-lived
execution-state / execution-storage-state effect (not attributed to page-cache carryover).
They are flagged `position_sensitive` and are excluded from the ρ = 0.81
high-confidence-and-non-position-sensitive subset.

Category agreement remains threshold-sensitive for the near-zero strategies (`layers_5`,
`leaf_freq_K10`, `leaf_rand_K10` sit on the band). The threshold-free rank correlation
(0.81 on clean cells) is the more robust statistic.

## Freeze revision (provenance)

The revised freeze supersedes exactly seven cells (precedence seventh > sixth > historical,
applied per cell only where a later campaign targeted that cell). Nothing else moved.

| cell | historical R_ow | revised R_ow | campaign | pairs / balance | position-sensitive |
|---|---|---|---|---|---|
| C/layers_92 | −0.7363 | +0.3832 | sixth | 20 / 10-10 | yes |
| C/2d | −0.6360 | +0.4316 | sixth | 20 / 10-10 | yes |
| C_hit/2e_K40 | −0.4844 | +0.4865 | sixth | 18 / 9-9 | no |
| C/layers_5 | −0.7129 | +0.4185 | sixth | 20 / 10-10 | no |
| YCu/layers_5 | +0.3760 | +0.2900 | sixth | 20 / 10-10 | yes |
| YCh01/layers_5 | +0.3766 | −0.5961 | seventh | 36 / 18-18 | no |
| YCh01/2f_top14 | −0.0190 | +0.2815 | seventh | 36 / 18-18 | yes |

Targeted, independently rebuilt, exactly position-balanced replications were run because
these initial cells had low sample counts or pair-position imbalance; the campaigns and
per-cell precedence rules were pre-registered before the evidence was inspected. Under
balanced replication the several WS-positive / OW-negative sign reversals disappeared;
YCh01/layers_5 remained reproducibly OpenWhisk-negative but is workstation-neutral.

## Conclusion (bounded, descriptive)

Across the full 55-cell first-query matrix, **strategy effectiveness is consistent between
the workstation and OpenWhisk in the descriptive sense that matters for the thesis**:
strong strategies stay strong (41/41), ranking is preserved (ρ ≈ 0.81 on clean cells), and
the single OpenWhisk-negative cell is a workstation-neutral strategy, not a strong one.
This is a cross-platform **consistency** result, NOT a claim of equal absolute latency,
equal effect size, causal equivalence, or hardware-independent speedup.

*Scope: standalone first_query only; relative reductions only; not a headline warm-latency
claim; the seven OpenWhisk campaigns (3600 + 468 + 852 + 456 + 236 + 144) serve distinct
roles and are **never pooled** (5756 invocations / 2878 pairs is unpooled accounting, not
one estimator); the revision selects which audited per-cell estimate is used for 7 cells
and does not change coverage (65/65); no OpenWhisk evidence was rerun or altered.*
