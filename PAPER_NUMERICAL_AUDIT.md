# Paper Numerical / Provenance Audit — `paper/main.tex`

**Scope:** fail-closed numerical and provenance audit of every quantitative claim in
`paper/main.tex`, checked against authoritative on-disk sources (result batches,
freeze CSVs, stats JSONs, classifier outputs, OpenWhisk normalization manifests).

**Rules honored:** no experiments run, no OpenWhisk invoked, no frozen evidence
changed, no numbers invented or averaged to force prose consistency, no silent
repair — every patched claim names its source and every unresolved claim carries a
loud `%TODO` in the tex plus a row here.

**Companion file:** `PAPER_NUMERICAL_AUDIT.csv` (machine-readable, one row per
claim, exact column schema: paper_location, exact_claim, metric, claimed_value,
authoritative_source, source_batch, aggregation_unit, recomputed_value, status,
notes).

**Status vocabulary:** PASS · ROUNDING_OK · STALE · WRONG_SOURCE ·
CROSS_BATCH_INVALID · UNSUPPORTED · CAUSAL_OVERCLAIM · NEEDS_QUALIFICATION.

---

## 1. Verdict

The workstation numerical core of the paper is **sound**. Every headline
first-query and end-to-end reduction, every page-count / footprint figure, the
learned-Markov LOSO numbers, and the full §10 cross-platform effectiveness table
recomputed to the claimed values (PASS / ROUNDING_OK).

The defects were **not** in the numbers — they were in **provenance wording** around
the OpenWhisk validation:

1. **§5 handle-mode mislabel (WRONG_SOURCE → patched).** The paper called the
   OpenWhisk estimator the *"warm paired first-query."* The estimator source
   (`compare_effectiveness.py:324`, `build_revised_freeze.py:149`,
   `lp_delivery_order.py:59`) filters to **`standalone`** handles and *rejects*
   warm handles (their reused handle carries a positional/order effect that makes
   warm first-query unusable). The correct word is **standalone**. "Paired" (the
   block-union *scheduling*) is orthogonal and stays.

2. **§6/§8 hardware-equivalence overclaim (UNSUPPORTED → patched).** The paper
   claimed OpenWhisk ran on *"the same bare-metal host,"* sharing *"x86 and NVMe
   hardware,"* so the deployment *"isolates the container-runtime dimension."* The
   captured environments show two different machines: workstation = Ryzen 9950X /
   kernel 6.17 / 62 GiB; OpenWhisk host `ian-comp` = Ryzen 7 7700 / kernel 7.0.0-28
   / 30 GiB. Different CPU **and** kernel on both captured sides. The test therefore
   varies runtime **and** host together and **cannot** isolate the runtime
   dimension. Only **relative** R is compared across platforms (absolute µs never
   is), which the bounded replacement wording now states.

3. **§8 hardware-generality clause (NEEDS_QUALIFICATION → patched).** A single
   workstation plus one second consumer x86 desktop does not establish that results
   are "not artifacts of a particular hardware configuration." Clause dropped;
   hardware portability left explicitly as future work (§7 conclusion / discussion).

Three residual items are **judgment calls left as loud `%TODO`** (not mechanically
resolvable without new figures or a rewrite the user must own): the learned-Markov
"worse on Scattered-Zipf" comparative, the Fig. 1 102-vs-103 MB caption/axis
mismatch, and the drift magnitude-scope footnote.

---

## 2. What PASSED (recomputed, no change needed)

| Area | Claim | Recomputed | Source |
|---|---|---|---|
| Baselines | A/B/C cold first-query 523 / 749 / 1087 µs | 523.36 / 748.81 / 1086.82 | `unified_v2/matrix/summary.csv` |
| Dump fq | −79% / −86% / −91% | −79.3 / −85.7 / −90.7 | same batch, same-arm anchor |
| Skel+10 C fq | −83% largest targeted (corrected batch) | −82.8% (1070.68→183.91) | `tiebreak_fix/master_summary.csv` |
| Skel+10 C warm e2e | −75% | −75.2% (1070.68→265.44) | same-batch, not cross-batch |
| Skel warm e2e | −25 / −25 / −28.5% pure-hit | matches (2d tie-break-unaffected) | `stats` + `c_hit` |
| Skel+10 C e2e | −55% bimodal | −54.5% [−66.6,−42.2] | `ablation_comp_v2` (corrected, not leaky `stats` −70.5%) |
| learned-Markov | −39.6 / −36.6 / −65.4% LOSO | matches; all CIs exclude 0; no leak | `learned_10fold/summary.csv` |
| Pages | 92 / 26 239 / 26 331; 368 KB; 0.35%; VACUUM 25 613 | exact | `layout_rewriter/runs/classify_before.csv` |
| 1 GiB DB | ~1 GiB / 6M rows / 263 991 pages | 1 081 307 136 B / 4096 = 263 991 exact | `runs/test_db_1gb.db` |
| §10 ρ | 0.76 / 0.79 / 0.81; dir 46/55; \|ΔR\|≈0.11 | 0.7611 / 0.7851 / 0.8103; 46/55; 0.1122 | `effectiveness_revised_stats.json` |
| §10 strong-WS | 41 of 41 effective | n_strong=41, effective 41/41 | same |
| §10 harmful cell | Skel-5/Hashed +0.03→−0.60 | 0.0252 → −0.5961 (WS-neutral) | `..._revised_freeze.csv` |
| §9 accounting | 7 campaigns / 5756 inv / 2878 pairs / never pooled | 5376/2688 + 236/118 + 144/72 = 5756/2878; pooled=false ×≥5 | OW normalization manifests |

The §9 reconciliation in full: primary 1600/800 + secondary 2000/1000 +
portability 468/234 + portability_ext 852/426 + full_closure 456/228 = 5376/2688
(five additive campaigns) + outlier_replication 236/118 + ych01_followup 144/72 =
**5756 invocations / 2878 pairs**, and `pooled=false` is asserted independently in
each normalization manifest — the two-role split is never averaged into a single
pooled number.

Note on "65 cells": that is **coverage** (55 first-query cells + 10 LP
ordered-delivery cells). Every ρ / direction / 41-of-41 statistic is over the
**55 first-query domain only** — the paper states this and it is correct. The
old three-sign-flip / 42-of-55 / 0.67-0.75 formulations are **absent** (verified by
grep); the revised freeze narrative is the only one present.

---

## 3. What was PATCHED in `main.tex` (mechanical, source-named)

All edits are wording/provenance only. **No number was altered.**

### §5 — handle mode: "warm" → "standalone"  (WRONG_SOURCE)
- **L494:** "We report the warm paired first-query…" → "standalone paired
  first-query".
- **L756–757:** "…the warm paired\nfirst-query is a deployment-feasibility…" →
  "standalone paired first-query" (the string is broken across the line wrap;
  patched as its own edit).
- **L858** (discussion): "the OpenWhisk warm paired first-query…" → "standalone".
- Authority: estimator filters `handle_mode != 'standalone'` and documents warm
  handles as unusable. **L543** "paired first-query reductions" has no "warm" and was
  left untouched (correct as-is).

### §6 / §8 — hardware-equivalence claim: FALSE → bounded  (UNSUPPORTED)
- **L483–485:** removed "on the same bare-metal host … no hardware or kernel
  changes are introduced, so the deployment isolates the container-runtime and
  deployment dimension rather than a new hardware configuration." Replaced with a
  bounded statement: a separate commodity x86 host with its own consumer NVMe and a
  different kernel; only relative first-query reductions are compared across
  platforms; the deployment exercises the serverless runtime and its host together
  and does not isolate the runtime dimension.
- **L758–759** and **L858:** same false "shares x86 and NVMe hardware … isolates
  the runtime" sentence → same bounded wording.
- Authority: OW campaign env captures (host `ian-comp`), `WS2_RUNBOOK.md`,
  `README.md` two-machine (WS1/WS2) design.

### §8 — hardware-generality clause dropped  (NEEDS_QUALIFICATION)
- **L128:** "…not artifacts of a single workload sample, deployment platform, or a
  particular hardware configuration." → the hardware-configuration clause removed;
  the sentence now claims only workload- and platform-robustness, which the evidence
  supports.
- **L819 / L858 future-work hedge:** adjusted to "systematic portability across
  diverse hardware classes … remains future work," consistent with OW having crossed
  to a *second* consumer desktop while not being a hardware sweep.

---

## 4. Loud `%TODO` left in the tex (judgment calls — NOT auto-resolved)

1. **L692 — learned-Markov "worse on Scattered-Zipf."** Point estimate −39.6% vs
   −50.6/−50.8% for the frequency/hot-leaf arms, but the **95% CIs overlap**
   ([−43.2,−36.0] vs [−65.5,−35.7]). By the paper's *own* overlapping-CI rule (the
   one it uses to call the B/C comparisons statistical ties), this is a **tie**, not
   "worse." The batch `FINDINGS.md #2` shares the overstatement. Resolution requires
   the user to decide whether to soften to "statistically indistinguishable" — a
   claim change, not a number fix.

2. **L434 / Fig. 1 — 102 MB vs 103 MB.** True size 107 851 776 B = 102.857 MiB. The
   caption/body floor to 102 MB; the rendered figure axis (and its generating
   script) round to 103 MB. Both are roundings of the same true value. Cannot
   regenerate the figure inside this audit; flagged for the user to reconcile the
   axis label to 102 MB (or the caption to 103 MB).

3. **L860 — drift "10–15%, attributable to SSD internal state and CPU thermal."**
   The **cause is supported** (`REPORT.md:1312`: SSD internal SLC/wear + CPU
   boost/thermal + background load; `CANONICAL_SWAP.md:9`: additive CPU-path
   offset), so this is **NEEDS_QUALIFICATION, not CAUSAL_OVERCLAIM.** The one
   nuance: 10–15% is the **Dump-anchor fast-path** figure; because the offset is
   *additive*, general cross-session **cell** drift can reach 30–70% on fast paths.
   A light `%TODO` notes the scope; the substance is not rewritten.

Additional disclosed-but-fine items (no patch, recorded in CSV): `tab:overhead`
open medians 193–222 µs are an independent overhead-decomposition batch (canonical
open ≈230 µs) already labeled independent in the paper; the warm-fault /
process-init / per-page / object-storage micro-numbers are stated as **estimates**
and are acceptable as such; L723 Skel+10-on-A "−36%" traces to the pre-fix seeds
aggregation (corrected canonical −37.9≈−38%, admissible because A/2e_K10 is
tie-break-unaffected per RESULT_PROVENANCE §4.8) — recommend citing −38% but not a
correctness defect.

---

## 5. Provenance rules applied (so a re-audit is cheap)

- **Atomic replacement unit** = (workload, layout, strategy, seed). A strategy
  arm, its baseline, and the 2f_slru drift anchor must come from the **same batch**.
- **2f_slru anchor identifies drift, never multiplies** across batches
  (drift is additive CPU-path offset, not a ×1.2 scalar).
- **Tie-break-affected arms** (A 2e_K500; B 2e_K10/K40/K92/K500; C
  2e_K10/K40/K92) take their canonical value from `tiebreak_fix` /
  `ablation_comp_v2`, never from the pre-fix `stats`/`seeds`/`unified_v2` cells.
- **2d / layers_5 / layers_92** are tie-break-**un**affected, so `stats` remains
  canonical for them.
- **LP** cells are compared by ordered synchronous `pread` delivery order
  (`deliver_us`), excluded from the first-query ρ domain.

---

PAPER NUMERICAL PROVENANCE AUDIT COMPLETE
