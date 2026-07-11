# Paper Framing Alignment (Phase 2)

## Metadata
- generated UTC: 2026-07-11T19:14:52Z
- branch: `main`
- HEAD before Phase 2: `547c389c307d8d0e6c5f6408057802dc6c7fe950`
- Phase 0 provenance authority: `results/RESULT_PROVENANCE.md`
- Phase 1 narrative audit authority: `docs/audits/STALE_NARRATIVE_AUDIT.md`
- submodule: `paper/` initialized and clean at Phase-2 start → audited and edited
  (see Paper-submodule status).

## Before/after thesis

**Old / risky thesis.** A non-intrusive *dual-lever* prefetch framework where
page-type and access-frequency are co-equal targeting levers; the flagship result
is a robust −70% end-to-end improvement on a "tail-heavy" workload C; type-aware
selection uniquely wins on C and is never beaten by a tuned dump; access-frequency
is the source of the headline gain (a 38-point ablation gap); the layout rewriter
is part of the targeting story.

**Canonical thesis (this Phase).** *Skeleton-first, cost-accounted* prefetch. The
mandatory B+tree interior navigation skeleton is the robust default (~25–30%
warm-process e2e across the evaluated pure-hit workloads); hot-leaf frequency
selection is a **conditional** add-on that helps only under a verified concentrated
hotspot (genuine Zipfian skew: A −25%→−36%). A corrected estimator (trace-order-
independent tie-break) shows leaf-frequency alone is ≈ a tie and a footprint-matched
frequency dump is statistically indistinguishable from the type-aware selector.
Workload C's larger number is a scoped, bimodal, not-found/rightmost-leaf effect;
a pure-hit control (C_hit, orig-only) returns to ~−27–30%. Layout rewriting is a
studied design alternative / negative result, not the default. No single best stack.

## RQ alignment table

| RQ | Final wording (REPORT §1.1) | Evidence sections | Supported claim |
|---|---|---|---|
| RQ1 | Which pages form the mandatory navigation skeleton, and under what access distributions does leaf-frequency selection add value **beyond** it? | §5.1 first-query ceilings; §5.4.1 corrected ablation; §6.2.8 C_hit control | Skeleton-first; conditional leaf bonus |
| RQ2 | After open+deliver preprocessing cost, which strategies reduce **end-to-end** cold start? | §5.5 preprocessing trade-off; §5.5.3 two deployment models | Cost accounting; full dump loses on e2e |
| RQ3 | How much benefit is selection vs delivery mechanism/ordering? | §3.5 selection–delivery; §5.4.1 ablation; §6.2.6 libprefetch delivery-order | Selection vs delivery separation |
| RQ4 | Robustness under layout, RAM, DB scaling, multiprocess, write aging, and **hotspot drift** (churn ≠ non-stationarity) | §6.2.1–§6.2.5, §6.2.7 aging | Robustness + stationarity-dependent staleness |

## Contribution alignment table

| Contribution | Final wording | Evidence | Scope/limitation |
|---|---|---|---|
| C1 (REPORT) | Type-aware layout rewriter **as a design alternative / negative result**, not flagship | §6.1 layout comparison | orig+access-pattern dominates; 1c never wins |
| C2 (REPORT) | Two selection levers: page-type **universal robust**, access-frequency **hotspot-conditional** | §5.4.1 corrected ablation; §6.2.8 | leaf bonus only under real hotspot |
| C3 (REPORT) | OS-syscall cost-accounting (open/deliver) + two deployment models | §5.5 | narrowly-stated novelty (flag for citation check) |
| C4 (REPORT) | Robustness five axes incl. stationarity-dependent decay | §6.2 | absolute µs within-batch only |
| paper C1 | **Skeleton-first targeting with conditional leaf bonus** (corrected ablation) | paper §6.3 | leaf-only ≈ tie; freq dump matches type-aware |
| paper C2 | OS-syscall cost accounting, two deployment models | paper §6.2 | — |
| paper C3 | Non-intrusive deployable toolchain | paper §3 | — |

Novelty claim retained (narrow): *first SQLite OS-page-cache cold-start evaluation to
separate open, delivery, and first-query terms and align them with integrated and
standalone deployment boundaries.* **Flagged for later citation/novelty verification
(no web search this Phase).**

## Section consistency table

| Section/file | Framing before | Change applied | Final status |
|---|---|---|---|
| REPORT abstract | already skeleton-first (Phase 1) | RQ/C tweaks only | aligned |
| REPORT §1.1 RQ1/RQ4 | RQ1 targeting-only; RQ4 no hotspot-drift | RQ1 mandatory+conditional; RQ4 churn≠non-stationarity | aligned |
| REPORT C1 | layout rewriter first/flagship | de-flagshipped (design alternative / negative) | aligned |
| paper abstract | dual-lever, −70% headline, −76~89 | skeleton-first, corrected, scoped C | aligned |
| paper Contribution 1 | dual-lever (equal) | skeleton-first + conditional leaf | aligned |
| paper §6.3 ablation | leaf_freq −40%, 38-pt "all frequency", page-type-base | REVERSED: 2d robust, leaf-only tie, +C_hit control | aligned |
| paper §6.3 competitive | "2e_K10 −72% robustly beats 2f_top14 −57% / never beaten" | REVERSED: −55%==−55% indistinguishable | aligned |
| paper §6.2/§6.4 headline+tables | flagship C −70% robust | scoped single-seed −75% / cross-seed −55% bimodal | aligned |
| paper §6.1 ceiling | "hot leaves warm naturally", C file-tail | cold-page corrected; C→C_mixed not-found | aligned (framing); **numbers pending** |
| paper recommendation table | 2e_K10 for file-tail as default | default orig+2d; C_mixed scoped; moving-hotspot row | aligned |
| paper conclusion | dual-lever, −73%/−70% headline | skeleton-first | aligned |

## Evaluation-to-RQ map (Step 8)

| Evaluation section | Main evidence | RQ | Contribution |
|---|---|---|---|
| First-query vs e2e trade-off | 2f_slru min first-q but +7–10× e2e | RQ2 | C3 / paper C2 |
| Corrected selection ablation | 2d robust; leaf_rand +7%; leaf_freq tie | RQ1, RQ3 | C2 / paper C1 |
| C_hit control | 2e_K10 → −27% == 2d/learned | RQ1 | C2 (removes not-found artifact) |
| C_mixed mechanism | ~50% not-found → rightmost-leaf; bimodal −55% | RQ1 | C2 (scoped, not general) |
| Competitive / prior-art | 2e_K10 ≈ 2f_top14; full dump regresses | RQ2, RQ3 | C2/C3 (equivalence under matched coverage) |
| Delivery ordering (libprefetch) | offset-sort Δdeliver 10–16× | RQ3 | C3 |
| Layout comparison | orig+access-pattern dominates 1c | RQ4 | C1 (mixed/negative design-space) |
| RAM pressure | small hotset 100% delivery; 2f_slru collapses | RQ4 | C4 |
| Size scaling | first-q size-robust; 2f deliver trap worsens | RQ4 | C4 |
| Multiprocess cadence | MAP_SHARED O(1) cost, O(N) benefit | RQ4 | C4 |
| Aging / stationarity | frozen frequency plan decays under YD; structural stable | RQ4 | C4 (stationarity-dependent) |

No evaluation subsection is now presented as supporting a claim it no longer supports
(ablation → mandatory skeleton, not frequency dominance; C_mixed → concentrated
negative lookups, not general uniform-tail prediction; 2e_K10 ≈ 2f_top14 → equivalence
under similar coverage; layout → negative design-space result).

## Paper-submodule status
- **Audited and modified.** Framing + tie-break-reversal edits committed inside the
  submodule as `8a31bcd` ("paper: align framing with skeleton-first findings"). The
  root repository records the updated submodule pointer in this Phase's root commit.

## Remaining framing risks
1. **[Pending, large] paper v1→v2 canonical number swap.** The paper submodule still
   carries the pre-canonical baseline first-query numbers (A 529 / B 760 / C 1096 µs;
   2f_slru first-q −76% / −83% / −89%) in §2 (motivation/mechanics), §6.1 (ceilings),
   and the §6.2 trade-off tables, while the Phase-2 edits use the canonical v2 values
   (523/749/1087; −79/−86/−91; C headline 1087→268). This is the same v1→v2 swap
   applied to the root docs in the earlier canonical-swap; it was never ported to the
   submodule. The paper is therefore internally number-inconsistent and **not yet
   submission-ready**; a dedicated numeric-swap pass (Phase 3 or a scoped follow-up)
   should port every §2/§6.1/§6.2 baseline and first-query figure to the canonical
   sources named in `results/RESULT_PROVENANCE.md`.
2. **fig 17 / fig 18** already regenerated with post-fix data (prior phase); the paper
   references them. No action.
3. **Novelty/citation wording** ("first to separate open/deliver/first-query …") is
   narrowly stated but unverified against the literature; flag for a citation check
   (no web search this Phase).
