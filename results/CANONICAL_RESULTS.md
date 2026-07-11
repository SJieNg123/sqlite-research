# Canonical Result Provenance (freeze)

Machine-readable source of truth: [`CANONICAL_RESULTS.yaml`](CANONICAL_RESULTS.yaml).
This file is the human summary. It concerns **provenance only** — not the study's
findings. Generated at HEAD `9d8f5fe` (branch `main`).

## Canonical vs legacy

**Canonical** result directories:

- `results/unified_v2` — main matrix (A/B/C × orig/vacuum/ta), single-instantiation.
- `results/baselines_v2` — prior-art arms (libprefetch, learned_markov), orig.
- `results/aging_v2` — cross-seed YCSB D/E self-aging (10 seeds × 11 checkpoints).
- `results/tiebreak_fix` — tie-break-corrected cells (master + `seeds/`).
- `results/c_hit` — C_hit control, arms **unaffected** by the tie-break fix.
- `results/c_hit_v2` — C_hit control, **corrected** 2e_K* cells (orig-only).
- `results/ablation_comp_v2` — C_mixed three-lever ablation + competitive (post-fix, orig).

**Legacy (non-canonical, MUST NOT support any headline)**:

- `strategies/access/runs/legacy_same_trace_first_seen_tiebreak/` — archived
  first-seen / insertion-order tie-break hotset artifacts. Citeable only for
  provenance/debugging history, always labeled legacy.

## Atomic replacement

The atomic unit of a canonical value is **`(workload, layout, strategy, seed)`**.

When a cell was superseded by a corrected rerun, the corrected **strategy
measurement, its paired same-seed baseline, and its machine-state anchor
(`2f_slru`) all come from the same rerun batch**. Values are never assembled
across batches.

- **Absolute µs** must not be compared across machine-state batches.
- **Relative metrics** (impr% / cross-seed Δ% / ratio) must use that batch's own
  paired baseline.
- **Legacy fallback is not allowed** (`legacy_fallback_allowed: false`).

## When to read which source

- **Main matrix cell (A/B/C × orig/vacuum/ta)**: read `results/unified_v2`
  **unless** it is in the superseded set below → then read `results/tiebreak_fix`.
- **Cross-seed CI for a corrected cell** (C 2e_K10, B 2e_K10, A/B 2e_K500): read
  `results/tiebreak_fix/seeds`.
- **C_hit**: read `results/c_hit` for `2d / layers_92 / 2f_top14 / 2f_top28 /
  learned_markov_* / 2f_slru`; read `results/c_hit_v2` for `2e_K10 / 2e_K40 /
  2e_K92 / 2e_K500`. C_hit is **orig-only** — do not claim layout robustness.
- **C_mixed ablation (2d / leaf_rand / leaf_freq / 2e_K10) and competitive
  (2e_K10 vs 2f_top14/28), orig**: read `results/ablation_comp_v2`.
- **Prior art / aging**: `results/baselines_v2` / `results/aging_v2` (independent scope).

## Precedence / scope table

| Result class | Canonical source | Scope | Supersedes |
|---|---|---|---|
| Main matrix (uncorrected cells) | `results/unified_v2` | A/B/C × orig/vacuum/ta, single-inst | — |
| Main matrix (corrected, single-inst) | `results/tiebreak_fix` (`master_summary.csv`) | A:2e_K500; B:2e_K10/40/92/500; C:2e_K10/40/92 × all layouts | `results/unified_v2` |
| Cross-seed (corrected) | `results/tiebreak_fix/seeds` | A:2e_K500; B:2e_K10/2e_K500; C:2e_K10 × all layouts | `results/seeds` (pre-fix, non-canonical) |
| C_hit (unaffected arms) | `results/c_hit` | C_hit/orig: 2d, layers_92, 2f_top14/28, learned_*, 2f_slru | — |
| C_hit (corrected arms) | `results/c_hit_v2` | C_hit/orig: 2e_K10/40/92/500 | `results/c_hit` (those arms) |
| C_mixed ablation + competitive | `results/ablation_comp_v2` | C/orig: 2d, leaf_rand/freq_K10, 2e_K10, 2f_top14/28 | `results/ablation`, `results/competitive` (C/orig) |
| Prior art | `results/baselines_v2` | A/B/C/orig prior-art arms | — |
| Aging | `results/aging_v2` | YD/YE, 10 seeds × 11 ckpt | — |
| **Legacy tie-break** | `…/legacy_same_trace_first_seen_tiebreak` | pre-fix hotsets | **non-canonical** |

The impact-audit selectors above are encoded verbatim in
`CANONICAL_RESULTS.yaml → superseded_cells`.
