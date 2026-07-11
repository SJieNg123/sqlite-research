# Result Provenance (freeze)

Human-readable provenance for the canonical result set after the first-op
tie-break leakage fix. **Provenance only** — this file does not restate the
study's conclusions. It is the single, self-contained source of truth for which
result directory is canonical per cell; the explicit supersession selectors live
in §4.2 below.

## 4.1 Freeze metadata

| field | value |
|---|---|
| generated (UTC) | 2026-07-11T14:21:51Z |
| branch | `main` |
| HEAD | `8761a882f9e7a75aac7e1cf837aa458eb5ebb0ef` |
| ancestor commits checked | `4516662`, `28ac866`, `de4490f`, `a493768`, `8e34721` — **all ancestors (exit 0)** |
| working tree | no modified/staged **tracked** files; 47 untracked rerun byproducts (`env.txt`, `nohup.out`, `results/tiebreak_fix/master_{A,B,C}/`, `results/*/models/`) — unrelated, left untouched |
| raw CSVs modified | none |

**Real-path notes** (the request used two approximate names):
- `results/tiebreak_fix/master` — no such directory; the canonical merged file is
  **`results/tiebreak_fix/master_summary.csv`** (per-workload intermediates live in
  `master_{A,B,C}/`, untracked).
- `legacy_same_trace_first_seen_tiebreak` — real path is
  **`strategies/access/runs/legacy_same_trace_first_seen_tiebreak/`**.

## 4.2 Canonical result source table

| Result class | Canonical source | Exact scope | Replaces / supersedes | Notes |
|---|---|---|---|---|
| Main matrix (uncorrected cells) | `results/unified_v2/matrix/summary.csv` (+ `raw.csv`) | A/B/C × {orig,vacuum,ta} × {baseline, layers_5, layers_92, 2d, 2e_K10, 2e_K40, 2e_K92, 2e_K500, 2f_slru}; arms async+pread+baseline; single-instantiation (n=10 reps) | — | Canonical only for cells **not** in the tie-break impact-audit changed set below |
| Corrected single-instantiation | `results/tiebreak_fix/master_summary.csv` (+ `master_raw.csv`) | A:`2e_K500`; B:`2e_K10,2e_K40,2e_K92,2e_K500`; C:`2e_K10,2e_K40,2e_K92` — × {orig,vacuum,ta}; single-inst | **supersedes** `results/unified_v2` for exactly these cells | Same-batch baseline + `2f_slru` anchor in the same run |
| Corrected cross-seed | `results/tiebreak_fix/seeds/seed{01..10}/summary.csv` (CI: `results/tiebreak_fix/uncertainty.csv`) | A:`2e_K500`; B:`2e_K10,2e_K500`; C:`2e_K10` — × {orig,vacuum,ta}; seeds 1–10 | **supersedes** pre-fix cross-seed `results/seeds` (non-canonical) for these cells | Each seed's corrected strategy paired with its same-seed baseline |
| C_hit — unaffected arms | `results/c_hit/seed{01..10}/summary.csv` (`FINDINGS.md`) | C_hit × orig × {2d, layers_92, 2f_top14, 2f_top28, learned_markov_14, learned_markov_28, 2f_slru}; seeds 1–10 | — | **orig-only**; no layout-robustness claim |
| C_hit — corrected arms | `results/c_hit_v2/seed{01..10}/summary.csv` (CI: `uncertainty.csv`) | C_hit × orig × {2e_K10, 2e_K40, 2e_K92, 2e_K500}; seeds 1–10 (+ `2f_slru` as same-batch anchor only) | **`2e_K10`, `2e_K500` supersede** `results/c_hit` (leaky); **`2e_K40`, `2e_K92` are newly measured** here (absent from the old `results/c_hit` batch) | **orig-only**; the canonical C_hit `2f_slru` stays in `results/c_hit` (anchor note below) |
| C_mixed ablation + competitive | `results/ablation_comp_v2/uncertainty.csv` (seeds `seed{01..10}/summary.csv`) | C (=C_mixed) × orig × {2d, leaf_rand_K10, leaf_freq_K10, 2e_K10, 2f_top14, 2f_top28, 2f_slru}; seeds 1–10 | **supersedes** pre-fix `results/ablation` + `results/competitive` for C/orig | Same-batch three-lever ablation + footprint-matched competitor |
| Prior-art baselines | `results/baselines_v2/summary.csv` (+ `raw.csv`) | A/B/C × orig × {lp_sorted, lp_shuf, learned_markov_14/28, 2f_top14/28, 2e_K10, 2f_slru anchor}; test seed 1 | — | Not affected by leaf tie-break. `results/baselines_v2/models/` = optional learned-model reproducibility artifact (model inputs), **not** a canonical measurement source |
| Aging | `results/aging_v2/aging_ci.csv` (per-seed `seed{01..10}/aging_evolution.csv`) | YD/YE × orig × {baseline, 2e_K10_static, layers_92_static}; seeds 1–10; **11 checkpoints ck0–ck10** (10 aging increments); bootstrap CI | — | Independent workload axis |
| **Legacy first-seen tie-break** | `strategies/access/runs/legacy_same_trace_first_seen_tiebreak/` (`README.md` + regen recipe) | archived pre-fix `hot2e_*.csv` hotsets | — | **canonical = NO.** Provenance/debugging only |

> **C_hit `2f_slru` anchor note.** The `2f_slru` rows in `results/c_hit_v2` are
> same-batch machine-state anchors only. The canonical C_hit `2f_slru` result
> remains sourced from `results/c_hit`.

## 4.3 Atomic replacement rule

**Atomic replacement unit:** `(workload, layout, strategy, seed)`.
For single-instantiation cells (no seed dimension) the unit is
`(workload, layout, strategy, canonical instance)`.

When a cell is replaced by a corrected rerun, the **corrected strategy
measurement, its paired baseline, and its machine-state anchor (`2f_slru`) must
all come from the same rerun batch.**

Prohibited:
- taking the strategy value from a corrected batch but the **baseline** from
  `results/unified_v2` or the old `results/seeds` batch;
- taking the **anchor** from a different machine-state batch;
- assembling a cell's numbers across batches in any other way.

## 4.4 Source-selection rules (per cell, by scope — not a vague global order)

1. Determine whether the cell is in the tie-break **impact-audit changed set**
   (§4.2 "supersedes" rows).
2. **Changed** main-matrix cell → `results/tiebreak_fix` (`master_summary.csv` for
   single-inst; `seeds/` for cross-seed).
3. **Unchanged** main-matrix cell → `results/unified_v2`.
4. C_hit `2e_K10`/`2e_K40`/`2e_K92`/`2e_K500` → `results/c_hit_v2`
   (`2e_K10`/`2e_K500` supersede `results/c_hit`; `2e_K40`/`2e_K92` exist only
   here). C_hit `2f_slru` → `results/c_hit` (the `c_hit_v2` `2f_slru` is an
   anchor only).
5. C_hit **unaffected** arms (`2d`, `2f_top14/28`, `learned_*`, `layers_92`,
   `2f_slru`) → `results/c_hit`.
6. C_mixed **ablation / competitive** (C/orig) → `results/ablation_comp_v2`.
7. Prior-art comparison → `results/baselines_v2` (`summary.csv`/`raw.csv`;
   `models/` is a reproducibility artifact, not a measurement source).
8. Aging → `results/aging_v2`.
9. **Legacy directory must never be a fallback.**

## 4.5 Absolute and relative metric rules

- **Absolute µs** may be compared **only within the same machine-state batch**.
- **Relative improvement** must use that batch's own **same-batch paired baseline**.
- **Cross-seed improvement** is computed **per seed against its same-seed
  baseline, then aggregated** (bootstrap mean + 95% CI).
- A corrected strategy's improvement must **not** be recomputed against a
  different batch's baseline.
- The `2f_slru` machine anchor is used only to **identify drift** — never as a
  cross-batch numeric conversion factor.

## 4.6 Terminology

- **C_mixed** — mixed tail-boundary lookup; ~50% not-found high-key lookups
  (range `[590000,609999]` exceeds DB max id 600000). Data-file label is `C`.
- **C_hit** — pure-hit uniform-tail control (`id ∈ [580001,600000]`, all keys
  exist); **orig layout only**.
- **Corrected `2e_K` (incl. leaf_freq/leaf_rand)** — deterministic,
  trace-order-independent tie-break; ordering **count descending, then page
  number ascending**; fixed in commit `de4490f`.
- **Legacy `2e_K`** — insertion-order / first-seen tie-break; **non-canonical**.

## 4.7 Known non-canonical data (with corrected replacement)

| Non-canonical item | Archived / located at | Why non-canonical | Corrected replacement |
|---|---|---|---|
| Old first-seen hotsets | `…/legacy_same_trace_first_seen_tiebreak/hot2e_*.csv` | insertion-order tie-break leaked the measured first-op leaf | current `strategies/access/runs/hot2e_*.csv` (`(-count,pageno)`) |
| Old leaky C `2e_K10` (single-inst / cross-seed) | `results/unified_v2`, `results/seeds` (those specific cells) | leaky hotset | `results/tiebreak_fix` (master + seeds) |
| Old leaky C_hit `2e_K10/K500` | `results/c_hit` (those columns) | leaky hotset | `results/c_hit_v2` |
| Old competitive conclusion ("2e_K10 robustly beats tuned dump on C / never beaten") | pre-fix `results/competitive` | first-op leakage inflated C `2e_K10` | `results/ablation_comp_v2` (2e_K10 ≈ 2f_top14, indistinguishable) |
| Old ablation conclusion ("38 pts all access-frequency; page-type irrelevant") | pre-fix `results/ablation` | leaky `leaf_freq_K10` (−40% → tie) | `results/ablation_comp_v2` (page-type is the robust lever) |
| Pre-fix figures fig17 / fig18 | `figures/out/17_lever_ablation.png`, `18_competitive_baseline.png` | plotted leaky data | **already regenerated** with post-fix data (commits `30b7e86`, `9d8f5fe`) |

## Pending narrative audit (for Phase 1)

Provenance is frozen; the numeric corrections and the two reversed conclusions
(competitive, ablation) have already been propagated to `REPORT.md` /
`overall_*.md` and the figures regenerated (commits `28ac866`, `30b7e86`,
`9d8f5fe`, `4516662`, `5959f26`). Items a *Phase 1 narrative audit* should still
verify (not changed here):

- Confirm every `2e_K10` / `2f_top` number in `REPORT.md` §5.4.1/§5.4.2/§6.2.x and
  `overall_results.md` reads from the source dictated by §4.4 (no leftover
  pre-fix value outside an explicitly-labeled "legacy/old" clause).
- Confirm the abstract's "interior skeleton" headline uses `2d` (not A `2e_K10`,
  which is the Zipfian skew bonus).
- Confirm no current recommendation implies a single "best stack" or C
  layout-robustness for C_hit.
- Regenerate any *other* figures that consumed pre-fix ablation/competitive data
  (fig17/fig18 already done; audit the rest of `figures/` for the same inputs).
- Legacy-reference scan (§ below) is clean at freeze time; re-run before Phase 1
  sign-off.

## Legacy-reference scan (freeze-time result)

`grep` over `REPORT.md overall_*.md tools figures results` for
`legacy_same_trace_first_seen_tiebreak | first-seen | Counter.most_common |
insertion-order tie | first-op leakage`: **all matches are in allowed contexts**
— the provenance table (labeled non-canonical), "how the artifact was found &
fixed" descriptions (headlines themselves use the *corrected* numbers), the
archival tooling (`tools/regen_hot2e_tiebreak.sh`), and unrelated VACUUM
"insertion order" mentions. **No** legacy reference is a current headline source,
canonical-table source, current recommendation, or figure input.
