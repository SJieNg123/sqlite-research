# Stale Narrative Audit (Phase 1)

## Metadata
- generated UTC: 2026-07-11T15:52:08Z
- branch: `main`
- HEAD before Phase 1: `cbe9423e64592a1a3ba065e304786b670df2085b`
- provenance authority: [`results/RESULT_PROVENANCE.md`](../../results/RESULT_PROVENANCE.md)
- files searched: `REPORT.md`, `overall_results.md`, `overall_strategies.md`,
  `overall_workloads.md`, `README.md`, `strategies_explained.md`,
  `results/c_hit/FINDINGS.md` (+ `figures/`, `tools/` for source paths). `paper/`
  is a separate git submodule (see pending).
- commands: `rg -ni` over the Phase-1 pattern set (equal-lever, never-beaten,
  38-points/page-type-irrelevant, best-stack, large-C values, C semantics,
  leaf-warm, tie-break terms, source paths, terminology).

## Canonical narrative used for audit
- **Skeleton first.** The mandatory B-tree interior path (`2d`) is the robust
  default (~−25–30% warm e2e across pure-hit workloads).
- **Leaf bonus is conditional** on a verified stable/concentrated hotspot
  (A's Zipfian skew: 2d ~−25% → 2e_K10 ~−36%).
- **Leaf-only is insufficient** when the interior navigation path stays cold.
- **Corrected C_mixed is bimodal, not-found-driven:** cross-seed 2e_K10 ≈ −55%
  [−67,−43]; miss-first seeds ~−70% (rightmost-leaf hotspot), hit-first ~−31%.
- **C_hit** is an **orig-only** pure-hit control; 2e_K10 returns to ~−27%
  (== interior-only/frequency-matched ~−29–31%).
- **Corrected 2e_K10 ≈ 2f_top14** on C_mixed (statistically indistinguishable).
- **No universal best stack.** Layout rewriter is studied, not the default.
- **Full restoration** (2f_slru) minimizes first-query but usually loses on e2e.
- **Static-plan decay depends on hotspot stationarity** (YD non-stationary decays;
  YE stationary stable).

## Findings table

| ID | Classification | File:line | Old wording | Problem | Action | Final wording |
|---|---|---|---|---|---|---|
| 1 | STALE-NARRATIVE | REPORT.md:14 | "兩個**對等**的 selection 槓桿" | equal-lever framing | fixed | "兩個**互補**的槓桿（interior skeleton 為 robust 預設、hot leaf 為條件式增量）" |
| 2 | STALE-NUMBER | overall_results.md:326 | "C 2e_K10 orig **−73%** vs ta −65%" | pre-fix C value | fixed | "orig **−55%(修正後)** vs ta −65%(pre-fix,未重跑)" |
| 3 | STALE-NARRATIVE | overall_results.md:328 | "access-frequency **解鎖 C headline**" | old causal story | fixed | "page-type 是 robust 槓桿；C 大效益是 not-found key-range 熱點，且 2e_K10 與 2f_top14 不可分" |
| 4 | STALE-NUMBER | README.md:18 | "A 529 / B 760 / C 1096 µs" | v1 baselines | fixed | "A 523 / B 749 / C 1087 µs (canonical v2)" |
| 5 | STALE-NUMBER | README.md:20 | "2f_slru first-query −76~89%" | v1 range | fixed | "−79~91%" |
| 6 | STALE-NARRATIVE+NUMBER | README.md:21 | "最佳是 C 上的 2e_K10 … 1096→291 (−73%)" | old headline + v1 nums | fixed | skeleton-first: 2d ~−25–30% robust; leaf conditional |
| 7 | STALE-NARRATIVE | README.md:22 | "C 效益來自 access-frequency（照頻率 −40%）" | reversed by fix | fixed | "page-type(2d) robust；leaf-only tie；2e_K10 ≈ 2f_top14；舊 −40% 是 leakage" |
| 8 | STALE-NUMBER | README.md:23 | "C 2e_K10 **−70%** robust" | old tight value | fixed | "C 2e_K10 −55% not-found 雙峰、magnitude 不穩"; robust list uses C_hit 2d −28% |
| 9 | STALE-NARRATIVE | README.md:29 | "每個 workload 的**最佳組合**" | best-stack | fixed | "各 workload 的**條件式建議做法**（無單一最佳；預設 orig+2d）" |
| 10 | STALE-NARRATIVE + AMBIGUOUS | REPORT.md:727 | "C (tail-region uniform) … 2e_K10 −75%" | C semantics + unscoped | fixed | "C (C_mixed, ~50% not-found) … −75%(seed-1; 跨 seed −55% 雙峰)" |
| 11 | AMBIGUOUS-SCOPE | REPORT.md:945 | "…C 2e_K10 −75%" | no seed/cross-seed scope | fixed | "(單一 workload…C 跨 seed −55% 雙峰, §6.2.8)" |
| 12 | AMBIGUOUS-SCOPE | REPORT.md:880 | "…C 2e_K10 −75%" (fig caption ctx) | no scope | fixed | "(單一 workload…C 跨 seed −55% 雙峰)" |
| 13 | AMBIGUOUS-SCOPE | REPORT.md:715 | "全矩陣最佳 e2e … −75%" | uniqueness overclaim | fixed | "seed-1 單一 workload…跨 seed −55%、與 2f_top14 不可分" |
| 14 | AMBIGUOUS-SCOPE | overall_workloads.md:60 | "…−75% 是全矩陣最佳" | overclaim | fixed | "seed-1…跨 seed −55% 雙峰、與 2f_top14 不可分" |
| 15 | AMBIGUOUS-SCOPE | REPORT.md:980 | "…−75%(268µs)，全矩陣最佳" | overclaim | fixed | "seed-1…跨 seed −55% 雙峰、與 2f_top14 不可分" |
| 16 | STALE-SOURCE | overall_results.md:271 | ablation table 來源 = `results/ablation/` | C superseded | fixed | "C/orig canonical = `results/ablation_comp_v2/`" pointer |
| 17 | STALE-SOURCE | overall_results.md:332 | competitive 來源 = `results/competitive/` | C superseded | fixed | "C/orig 2e_K10/2f_top14/28 canonical = `results/ablation_comp_v2/`" |
| 18 | STALE-NARRATIVE | REPORT.md:1000 | "A/B/C … 都不 decay" (fig 7) | unconditional | fixed | "…因 A/B/C 讀熱點平穩；非平穩 YD 是反例(§6.2.7)" |

## Valid legacy references (intentionally retained, labeled)
- **Corrected retractions** of the old ablation ("38 點全是 access-frequency /
  page-type 無關") and competitive ("2e robustly 勝 / 從未被打敗") conclusions:
  `overall_results.md:302,323,363,364`, `REPORT.md:813,815,846,848`. Each states
  the old claim only to mark it **撤回/翻轉/不成立** — safe.
- **§6.2.4 single-seed −75% with ※ footnote** (`REPORT.md:1070,1079`): explicitly
  labeled seed-1 single-instantiation vs corrected cross-seed −55%.
- **`results/c_hit/FINDINGS.md`**: the artifact write-up (Counter.most_common /
  insertion-order / first-op leakage) carries a "FIXED (de4490f)" header and is
  historical/debugging — safe.
- **`results/main` / `results/seeds` mentions** in machine-state / single-inst→
  cross-seed methodology prose (`REPORT.md:757,911,1015,1081`, `overall_results.md:
  55–56,419,548,610`): historical batch identifiers in provenance/drift context,
  not current canonical-value claims.

## Figure/script pending items (not fixed in Phase 1)
- `figures/06_ram_pressure_heatmap.py` — inline comment "unlimited = results/main"
  is stale (already flagged in `overall_results.md:56`). Comment-only; deferred to
  avoid touching a figure script this phase.
- `paper/` submodule (`paper/main.tex`) — separate git repo; not audited/edited in
  this phase. If it drafts any results, it must be audited against this document
  before submission.
- fig17 / fig18 were **already regenerated** with post-fix data (commits `30b7e86`,
  `9d8f5fe`); no action. Audit any *other* figure that consumed `results/ablation`
  or `results/competitive` before Phase 2 (none identified in the main docs).

## Unresolved questions
None. All corrections were resolvable from the canonical CSVs named in
`results/RESULT_PROVENANCE.md` (`results/tiebreak_fix`, `results/ablation_comp_v2`,
`results/c_hit_v2`, `results/unified_v2`).
