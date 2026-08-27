# Effectiveness portability: OpenWhisk vs workstation (20 comparable cells)

**Question.** Do prefetch strategies that are effective on the workstation stay
effective on the simulated serverless platform (OpenWhisk)?

**Method.** For each (workload, strategy) cell that BOTH platforms ran, compute the
relative first-query reduction versus that platform's own same-condition baseline:
`R = (baseline_fq − strategy_fq) / baseline_fq` (R>0 = faster = effective). Relative
reductions are the only cross-machine-comparable quantity; absolute microseconds are
not. OpenWhisk uses **standalone** handles only — warm handles carry a strong
positional/order effect that makes warm first_query unusable for strategy
comparison. Source: `compare_effectiveness.py`
(reads canonical workstation `results/…/summary.csv` + frozen OpenWhisk
`analysis/normalized/…_pairs.csv`, standalone only). Per-cell table:
`effectiveness_ow_vs_workstation.csv`.

**Coverage.** 20/20 comparable cells resolved (YC 7, YCu 3, YCh01 3, C 5, C_hit 2).

## Result

- **Rank correlation (Spearman, R_ws vs R_ow):** ALL 20 cells ρ = **0.74**;
  high-confidence cells (17, excluding position-confounded n≤3) ρ = **0.86**;
  YC alone (n=7) ρ = 0.75; C alone (n=5) ρ = 0.60. Strategies rank the same on both
  platforms.
- **Direction agreement:** 16/20 cells agree on category (effective / neutral /
  harmful, ±10% band); 14/17 high-confidence cells.
- **Every strongly-effective workstation strategy is also effective on OpenWhisk.**
  `2f_slru` (~0.90 both), `2e_K10`, `2e_K500`, `learned_markov_28`, `2f_top28`, and
  `2d`-on-YC all port cleanly.

## The 4 disagreements (all at the margins — no strong-strategy failure)

1. **C / 2d** — WS effective (+0.43) vs OW "harmful" (−0.64). This is the
   **position-confounded** cell: n=3 pairs, all baseline-first (0/3), so the target
   arm always ran in the polluted second slot. The negative R is the standalone
   order artifact, not a real regression. Flagged `low_conf`. Resolvable by running
   it position-balanced on WK2.
2. **YC / layers_5** — WS 0.034 (neutral) vs OW 0.147 (effective). Both hug the
   ±10% band; layers_5 is a marginal strategy on both platforms. Band-edge, not a
   contradiction.
3. **C / leaf_freq_K10** — WS 0.213 vs OW 0.081. Modest on both; band-edge.
4. **C / leaf_rand_K10** — WS 0.017 (correctly ~ineffective random control) vs OW
   0.252. The one genuine (minor) divergence: a random-leaf set shows some first-query
   benefit on OpenWhisk's cold storage that it does not show on the workstation.
   Worth noting; does not affect any real strategy.

Category agreement is threshold-sensitive for the near-zero strategies (layers_5,
leaf_freq, leaf_rand sit near the band). The threshold-free rank correlation
(0.74 all / 0.86 high-conf) is the more robust statistic and is strong.

## Conclusion (bounded)

On the 20 cells both platforms ran, **strategy effectiveness ports from the
workstation to OpenWhisk**: strong strategies stay strong, ranking is preserved
(ρ≈0.86 on clean cells), and the only sign flips are a position-confounded low-n
cell plus near-zero strategies at the neutral boundary. This validates the
effectiveness-comparison method itself; extending it to the remaining 16 cells
(WK2) would complete the 36-cell workstation-coverage matrix.

*Scope: standalone first_query only; relative reductions only; not a headline
warm-latency claim; no OpenWhisk evidence was rerun or altered.*
