# Pair carryover / order effect audit — OpenWhisk first-query matrix

**Status:** audit only. No runtime code, WS2 script, manifest, artifact, or result
file was changed by this task. No OpenWhisk invocation was performed. No secondary
strategy was implemented. This document records *why* the first arm of a pair pays
a large latency and the second is ~10× faster, whether the existing 1600-run
evidence is salvageable, and the corrected protocol + minimal validation
experiment to run before any rerun.

Code cited by `file:line` at the commit under audit
(`deployment/openwhisk/action/*.py`, `deployment/openwhisk/ws2/05_full_matrix.sh`,
`deployment/openwhisk/config/artifacts.json`).

---

## 0. TL;DR

The measured "first query" is a **single point query** `SELECT payload FROM items
WHERE id=?1` for one key `K`. Its latency is dominated by whether the **leaf page
holding row `K`** is resident in the OS page cache at the instant of the measured
`sqlite3_step`.

Both arms of a pair query the **same** `K` (a pair is one
`(workload, seed, first_operation_id, handle_mode, repetition_id)` cell, split into
a baseline arm and a target arm — see `build_schedule.py:64-81`). The two arms run
**back-to-back** with no spacing (pacing is inserted only *between* pairs —
`05_full_matrix.sh:361-367`).

The per-invocation cold-reset gate certifies only that the **92 mandatory interior
pages** are evicted (`residency.py:38-42`, `cold_threshold_passed(interiors)==0`).
It never measures or requires eviction of the **leaf page for `K`**, which is not
part of the interior skeleton. So arm 1 faults `K`'s leaf into the page cache
during its measured step, the gate before arm 2 does not require that leaf gone,
and — as the observed ~10× speedup proves — it survives. Arm 2 reads `K` warm.

The strategy identity of the first arm is irrelevant (baseline-first is slow,
target-first is slow) because the effect is positional, not strategic. `2f_slru` is
the sole order-insensitive strategy because its delivery step
(`MADV_WILLNEED` over its large SLRU working set, ~103 ms) re-warms `K`'s whole
B-tree path on **every** arm before the measured step, so both arms are warm.

**Consequence:** the within-pair *paired* baseline-vs-target statistic is an order
artifact and is invalid, in both warm and standalone modes. **First-arm-only** data
is salvageable as an *unpaired* randomized between-arm comparison.

---

## 1. What state survives from arm 1 to arm 2 — WARM mode

Warm mode reuses a module-singleton `Session` and one long-lived `sqlite3*` +
prepared statement across every invocation of the container process
(`main.py:53,74-86`, `session.py:378-391`, `_run_query` warm branch
`main.py:185-194`).

Surviving state, by category:

| State | Survives arm1→arm2? | Evidence | Proven / hypothesized |
|---|---|---|---|
| **OS page cache: leaf page for key `K`** | **Yes** (the effect) | gate checks interiors only; both arms query same `K`; arm 2 is fast even for baseline (delivers nothing) | **Proven** it survives (from numbers); exact eviction-skip mechanism hypothesized (§3) |
| OS page cache: 92 interior pages | No (gate forces to 0) | `residency.py:154-184`, gate `interiors==0` | Proven |
| SQLite pager **data** cache | No | `cache_size=0` (`artifacts.json:130`), `release_memory()` each invocation (`main.py:317-318`) | Proven |
| SQLite **connection + prepared statement** | Yes (reused) | `session.py:385-391` returns existing `warmdb`; `main.py:185-194` | Proven |
| SQLite **in-memory schema/catalog** (parsed once by connection) | Yes | same long-lived connection; schema is not page-cache and not released by `release_memory` | Proven (property of a persistent connection) |
| Persistent SQLite **mmap** of the DB file | **No — none exists** | active `sqlite_pragmas.mmap_size = 0` (`artifacts.json:129-131`); the 107 MB value is `canonical_reference_pragmas`, documentation only (`artifacts.json:133-137`) | Proven (rules out an otherwise-tempting cause — see §3) |

**Bottom line (warm):** the only *data-bearing* state that survives and matters is
the **page-cache leaf for `K`** (plus possibly its root/interior path pages, which
are likewise not all in the 92-interior gate set). The persistent connection and
schema cache survive but do not touch page residency; with `cache_size=0` SQLite
holds no page copies of its own.

---

## 2. What state survives — STANDALONE mode

Standalone opens a **fresh** `WarmDb` (fresh `sqlite3_open_v2` + `prepare_v2`) per
invocation and closes it after (`_run_query` standalone branch
`main.py:195-212`). So the connection, prepared statement, and any schema cache do
**not** survive between arms.

What *does* survive is exactly the piece that is not tied to the connection:

- **OS page cache: leaf page for key `K`.** The page cache is per-inode and lives
  in the kernel independent of any SQLite handle. Same carryover as warm — the same
  root cause.

The empirically **weaker** order effect in standalone is consistent with this: the
carryover is only the kernel page cache (identical mechanism), but each standalone
arm additionally performs a fresh `open_v2 + prepare_v2` between the reset and the
measured step, which faults schema/root pages via `pread` and churns kernel buffers
— extra I/O and time that plausibly gives the reset's best-effort eviction a
slightly better chance to have taken `K`'s leaf, and changes fault timing. That
weakening mechanism is **hypothesized**; the surviving-state itself (page-cache
leaf for `K`) is the **same proven** cause as warm. Standalone paired results are
therefore also invalid, just less extreme.

---

## 3. Does `POSIX_FADV_DONTNEED` evict only the Linux page cache while leaving other caches intact?

Yes — and this is central. Precise behavior of the reset path
(`residency.py:132-151`, candidate order `MADV_DONTNEED → POSIX_FADV_DONTNEED →
MADV_PAGEOUT → MADV_COLD`, each re-measured by a fresh `mmap`+`mincore`):

1. **`MADV_DONTNEED` on a file-backed `MAP_SHARED` mapping does not free page-cache
   pages** on Linux; it zaps the calling mapping's PTEs only. Because the gate
   re-measures residency on a *fresh* mapping via `mincore` (which reports
   page-cache residency, not PTE state), this candidate generally does **not** drive
   residency down, so the loop escalates.
2. **`POSIX_FADV_DONTNEED`** calls `invalidate_mapping_pages()` on the inode. It
   drops **clean, unmapped, not-under-writeback** page-cache pages — and it is
   **best-effort**: pages with a transient elevated refcount, pages still on a
   per-CPU LRU add pagevec, or recently-touched pages are **skipped**.
3. It targets the **kernel page cache for that inode only**. It does not touch:
   SQLite connection/statement/schema state; any block-device / NVMe controller
   cache *below* the page cache; nor, in a container, the host-side page cache of
   the overlay/loop backing file.

**Why the leaf survives but the interiors don't (leading hypothesis).** The 92
interior pages were faulted earlier and have "settled" onto the LRU where
`invalidate_mapping_pages` can drop them; the **leaf for `K` was faulted
milliseconds earlier by arm 1's measured step**, so at reset time it is the page
most likely to carry a transient reference / sit on a per-CPU pagevec and be
**skipped** by the best-effort invalidation. The gate stops as soon as
`interiors==0` (`residency.py:172-173`) and never checks the leaf, so this skip is
invisible. This recency-skip asymmetry is **hypothesized** (it depends on exact
kernel/pagevec timing I cannot exercise without running on WS2); the *fact* that
the leaf survives is **proven** by the ~10× second-arm speedup for baseline, which
delivers nothing and so can only be fast if `K` was already resident.

**Ruled out:** persistent-SQLite-`mmap` page pinning (which *would* make
`invalidate_mapping_pages` skip every mapped page via `page_mapped()`). The active
manifest sets `mmap_size = 0` (`artifacts.json:131`), so SQLite uses `pread`
paging and holds no persistent mapping. This is a plausible-sounding cause that the
config disproves; noting it so it is not re-proposed.

---

## 4. Is `resident_pages_after_reset == 0`… (actually `resident_interiors == 0`) sufficient to claim the next first query is independent of the prior arm?

**No.** The gate is `cold_threshold_passed(resident_interiors_after_reset) ==
(interiors == 0)` (`residency.py:38-42`, `main.py:342`). It certifies only the
**92-interior skeleton**. A point query's latency is dominated by the **leaf page
for the specific queried row** (and the non-interior pages on its root→leaf path),
none of which the gate measures or requires evicted. `resident_interiors==0` is
**necessary but not sufficient** for a genuinely cold first query. (Note the field
`resident_pages_after_reset` — total residency — *is* recorded
(`residency.py:181`) but is **not** part of the pass condition; requiring
`total==0` would have caught this.)

---

## 5. Why the first arm pays ~2–3 ms and the second ~0.3 ms

- **Arm 1** runs after a reset that evicts the interior skeleton. Its measured
  `sqlite3_step` faults `K`'s leaf (and any cold path pages) from cold storage →
  ~2–3 ms.
- Arm 1's step leaves `K`'s leaf resident in the page cache.
- **Arm 2** runs after another reset that again drives interiors to 0 **but leaves
  `K`'s leaf resident** (§3). Its measured step reads `K` warm → ~0.3 ms.
- The order is randomized per pair (`_order` = `sha256(schedule_seed|pair_id)` →
  AB/BA, `build_schedule.py:36-40`), giving the observed ~48/52 split for 2d; the
  slow arm is always whichever ran **first**, regardless of its strategy. This
  matches every reported pair:

  | Strategy | baseline-first: baseline / target | target-first: baseline / target |
  |---|---|---|
  | 2d | 3346 / 318 µs | 395 / 2269 µs |
  | layers_5 | 3334 / 273 µs | 314 / 2632 µs |
  | 2e_K10 | 3332 / 312 µs | 395 / 2229 µs |

  In every row the **first** arm ≈ 2.2–3.3 ms and the **second** ≈ 0.3 µs-scale,
  independent of which strategy is first — a positional, not strategic, effect.

The magnitude (~2–3 ms for a single cold 4 KiB leaf fault) reflects a real
storage/device fetch under the container; only the **relative** ~10× is the signal.

---

## 6. Why `2f_slru` is insensitive to order

`2f_slru` delivers its full plan — interior offsets **∪** leaf offsets — via
per-page `MADV_WILLNEED` (`select_offsets` returns `plan["offsets"]`
`main.py:138-157`; `deliver_willneed` `residency.py:85-93`). Its delivery median is
~**103 ms**, i.e. it faults essentially its whole resident working set — including
`K`'s leaf and its path — into the page cache **on every arm, after the reset,
before the measured step**. So both arms are warm and the measured query is ~37 µs
in both orders. Order cannot matter because delivery re-warms `K` every time. This
is a legitimate property of that strategy (its delivery includes leaves), not
carryover — and it is the control that confirms the mechanism: the strategies that
are order-sensitive (baseline/2d/layers_5/2e_K10) all deliver **no** leaf on `K`'s
path (baseline delivers nothing; 2d and layers_5 deliver interiors only; 2e_K10's
top-K hot leaves generally do not include the first-op key), so they depend on
carryover; the one strategy that delivers `K`'s leaf itself does not.

---

## 7. Is pair adjacency scientifically valid under the intended cold-start model?

**No.** The intended model is: each measured first query faults from cold storage,
independently. Pairing two **same-key** queries **adjacently** (arms at
`schedule_position` `p`, `p+1`, no spacing — `05_full_matrix.sh:361-367`) with a
reset that does not evict the queried leaf structurally violates that: the second
arm is not a cold start. Adjacency is what turns a harmless "both cold" design into
"second arm always warm." The design couples the two arms exactly on the variable
(the key `K`) that dominates the measurement.

---

## 8. Can the existing 1600-run dataset support a valid first-period-only randomized analysis?

**Yes, with strict exclusions.** Take only each pair's **first-executed arm** (the
lower `schedule_position` of the pair). That arm is genuinely cold with respect to
*its own pair* (nothing in the pair preceded it), and the reported previous-strategy
audit shows first-arm latency is essentially independent of the *previous pair's*
strategy — consistent with the inter-pair delay + different key per pair breaking
inter-pair carryover. So first arms are clean cold-start measurements.

Order is randomized per pair and balanced across the matrix
(`_order` hash, ~50/50), so across the full design the "pairs whose first arm is
baseline" and "pairs whose first arm is target" cover comparable
`(workload, seed, mode, rep)` cells. That makes an **unpaired** between-arm
comparison of first-arm latencies defensible. What is *not* defensible is the
within-pair paired ratio (the contaminated `0.0954` / `5.6995`).

Caveat: because order is fixed per cell, a given cell contributes its first arm to
only one group; balance holds at the group/marginal level, not cell-by-cell. Use a
stratified estimator (below) rather than a naive pooled median.

---

## 9. Precise defensible estimator + what must be excluded

**Include only:** invocations that are the **first arm** of their pair
(min `schedule_position` within `pair_id`), with `measured_valid == True`
(`cold_threshold_passed` true, oracle passed, delivery valid — `main.py:400-404`).

**Exclude:** every **second arm** of every pair; the warmup invocation
(`build_schedule.py:82-90`); any invocation failing the cold gate or oracle; and —
critically — **do not compute the within-pair paired ratio** at all.

**Estimator:** an **unpaired** target-vs-baseline contrast on first-arm
`first_query_us`, **stratified by `(workload, seed, handle_mode)`** to respect the
matrix structure:

- Per stratum, form the two first-arm groups (first-arm-baseline vs
  first-arm-target) and compute a **Hodges–Lehmann shift** (median of pairwise
  differences) or a **ratio of medians**; aggregate across strata (e.g. weighted by
  stratum size) with a **bootstrap CI** resampling whole pairs within stratum.
- Equivalently, a stratified **Mann–Whitney / rank** test for significance, or a
  mixed model `log(first_query_us) ~ arm + (1 | workload:seed)` with `handle_mode`
  as a fixed effect — both are legitimate because arm order was randomized within
  the balanced design.
- Report warm and standalone **separately** (they are different mechanisms and
  different absolute regimes).

This estimates the *cold-start* target-vs-baseline effect, which is the scientific
question, from uncontaminated observations only.

---

## 10. Recommended corrected protocol for the final experiment

Evidence supports a combination, not a single lettered option:

- **Primary recommendation — D + A + strengthened gate:**
  - **(D) Randomize individual arms, not adjacent same-key pairs.** Break the
    structural coupling: baseline and target for a cell should be far apart in the
    schedule, separated by other keys and resets, so no shared-key carryover exists.
    Analyze **unpaired** (as in §9).
  - **(A) Strengthen the cold gate to the queried key's path, not just the interior
    skeleton.** Require, and *verify by re-measured `mincore`*, that the **leaf page
    for `K` (and its root→leaf path)** — not only the 92 interiors — is non-resident
    before the measured step. Concretely: add `K`'s leaf offset(s) to the residency
    probe and make the pass condition include them (or require total
    `resident_pages_after_reset == 0`, which the code already records but does not
    enforce — `residency.py:181`).
  - Because `mmap_size = 0`, there is no persistent mapping to unpin; the remaining
    gap is purely the best-effort eviction skipping the just-touched leaf. If
    strengthening the gate cannot reliably evict a recently-touched leaf without
    root, add a deterministic non-root eviction of `K`'s path (e.g. `MADV_PAGEOUT`
    scoped to the path pages with re-measured verification) rather than trusting the
    escalation to stop at `interiors==0`.

- **If pairing must be retained for logistics — B (equal strong inter-arm
  separation/reset):** insert the *same* strong reset **between the two arms** as
  before the first, verifying whole-path residency `== 0`, and add inter-arm spacing
  equal to inter-pair spacing so the two arms are not privileged relative to each
  other. This is strictly weaker than D+A and still leaves the same-key coupling; use
  only as a fallback.

- **C (separate process/container per arm)** would also remove connection/schema
  carryover, but with `mmap_size=0` and `cache_size=0` the connection carries **no
  data state**, so C's marginal benefit over "strengthened gate + randomized arms"
  is small and its cost (cold container per arm) is large. Not recommended as the
  primary lever; the page-cache carryover — which C does *not* by itself remove
  unless each container also has a private page cache — is the real issue.

- **E (first-period-only)** is the correct way to **salvage the existing data**
  (§8–9), and can also be run prospectively, but for a *new* experiment D+A is
  cleaner because it lets every invocation count instead of discarding half.

**Recommended:** design the final run as **D (individual randomized arms) + A
(gate verifies the queried key's leaf/path is evicted, enforce total residency==0)**,
analyzed unpaired and stratified; keep **E** as the salvage path for the 1600-run
data already collected.

---

## Naming audit — "warm" and "standalone"

- **"warm"** accurately describes a warm **process + warm connection** (persistent
  `sqlite3*` + prepared statement reused, `cache_size=0`, `mmap_size=0`), with
  **cold data** intended per invocation. The name is directionally right but risks
  being read as "warm **data**"; and the cold-data guarantee is in fact **not
  delivered** for the queried leaf (§3–5). Recommend documenting it as
  **"warm-process / warm-connection, cold-data (attempted)"** and fixing the gate so
  the cold-data claim is true.
- **"standalone"** is **misleading**. It denotes only a **fresh SQLite connection
  per invocation** (`main.py:195-212`); it is the **same process, same container,
  same page cache**. It is not a standalone process or container and provides no
  storage/cache isolation. Recommend renaming to **"fresh_connection"** (or
  "cold-connection") to avoid implying isolation the implementation does not provide.

---

## Validity assessment of the existing 1600-run dataset

- **Warm paired results — INVALID** for paired target-vs-baseline inference. The
  paired ratio is dominated by within-pair order/carryover; `0.0954` (baseline-first)
  and `5.6995` (target-first) are order artifacts, not strategy effects.
- **Standalone paired results — INVALID** as paired (weaker but substantial order
  effect; same page-cache root cause).
- **First-arm-only (both modes) — SALVAGEABLE** as an unpaired, stratified
  randomized between-arm comparison (§8–9). This is the only defensible use of the
  1600-run evidence. **Do not discard the data** — it retains ~800 clean first-arm
  cold-start observations.
- **`2f_slru`** is order-insensitive by construction; its first-arm values are valid
  and its paired values happen to be uncontaminated, but for consistency analyze it
  with the same first-arm-only estimator.

---

## Minimal validation experiment before rerunning the 1600 (WS2)

Small, cheap, decisive — proves the mechanism and the fix without a full rerun. No
pairing needed.

1. **Instrument residency of the queried leaf.** Extend the diagnostic to report,
   for one `(workload, seed)`, the residency of `K`'s **leaf page** (and its path)
   *after* the cold reset, alongside the existing `resident_interiors_after_reset`.
   Expect: `interiors == 0` **while the leaf for `K` remains resident** after arm 1
   — the direct proof that the gate misses the leaf.
2. **Reproduce the effect in isolation (no pairing).** Fire ~20 **back-to-back
   same-key** measured invocations (e.g. all baseline) for one cell under the current
   protocol. Expect: first ≈ 2–3 ms, remainder ≈ 0.3 ms — the order effect reproduced
   from adjacency + shared key alone, independent of AB/BA pairing.
3. **Apply the candidate fix and re-run step 2.** With the strengthened gate (verify
   `K`'s leaf/path evicted, enforce total residency `== 0`) — and/or randomized
   individual arms — expect **all** invocations ≈ 2–3 ms (each genuinely cold): the
   speedup disappears. This confirms the fix removes carryover.
4. **Cross-check the salvage estimator.** On one balanced cell, compute the
   first-arm-only unpaired estimate (§9) under the *current* data and confirm it
   agrees with the fully-cold measurements from step 3 (within CI). This validates
   that first-period-only analysis recovers the true cold-start effect.

Only after steps 1–3 pass should the full matrix be regenerated (with
`WS2_FORCE=1`, per the schedule-balance guard) under the corrected protocol.

---

## Are historical baseline/2d acceptance runs affected?

Any historical run that measured **adjacent same-key baseline/target pairs** under
this reset gate carries the **identical** carryover, and its **paired** numbers are
suspect to the same degree. Runs that measured **single cold first queries** (e.g.
one-shot diagnostic acceptance invocations, or the native head-to-head if it did not
use adjacent same-key pairing) are **not** affected by the within-pair mechanism.

This audit did **not** re-run or re-examine every historical artifact; the specific
prior acceptance runs must be checked against the test above (did they place two
same-key measured arms back-to-back?). Any that did should be re-analyzed first-arm-
only or rerun under the corrected protocol; any that measured isolated cold queries
stand. Flag, don't assume.

---

### Proven vs hypothesized — summary

**Proven (code + reported numbers):** pairs are same-key
(`build_schedule.py:64-81`); arms adjacent, pacing only between pairs
(`05_full_matrix.sh:361-367`); gate certifies interiors only, not the leaf
(`residency.py:38-42,172-181`, `main.py:342`); warm reuses one connection/stmt,
standalone opens fresh (`main.py:185-212`); `cache_size=0`, `mmap_size=0`, no
persistent SQLite mmap (`artifacts.json:129-137`); baseline delivers nothing and
2f_slru delivers leaves (`main.py:119-157`); the leaf for `K` survives the reset
(from the ~10× second-arm speedup, incl. baseline).

**Hypothesized (kernel/timing detail I could not exercise without WS2):** the exact
reason the *recently-touched* leaf is skipped by best-effort
`invalidate_mapping_pages` while settled interiors are dropped; the precise reason
standalone's effect is weaker; the absolute ~2–3 ms cold-fault cost. None of these
change the conclusions; they refine the eviction story.

---

## Addendum (2026-08-25) — how to read the YC SECONDARY matrix

The original audit above stands unchanged. A **secondary** matrix was subsequently
added — five more strategies (`2e_K500`, `leaf_freq_K10`, `leaf_rand_K10`,
`2f_top102`, `learned_markov_102`) on the same canonical workload
`native_ycsb_c_read_zipf`, seeds 1..10, warm+standalone, 10 reps, under a **new**
`schedule_seed=20260825` (5 × 10 × 2 × 10 × 2 = **2000 invocations**;
`secondary_run_config_sha256=441609e6…`). The primary 1600-run YC matrix
(`run_config_sha256=022fbeb0…`) is **untouched immutable evidence**. Interpretation
constraints carry over verbatim:

- **The positional effect is real and systematic, not noise.** The primary audit
  found a strong *immediate positional* effect in warm-handle `first_query_us` even
  though the per-invocation gate certifies zero Linux DB page-cache residency
  (interiors == 0) after reset. This is a **systematic short-lived
  execution/storage-state or order effect** — explicitly **NOT** random hardware
  fluctuation. The exact mechanism (which non-page-cache state, or which recently
  touched leaf, survives the reset) is unresolved and **out of scope** here.

- **Warm paired ratios are not headline strategy estimates.** As established above,
  the within-pair baseline-vs-target statistic is an order artifact. The secondary
  strategies inherit this: do **not** read their warm paired ratios as strategy
  speedups. First-arm-only, between-arm randomized comparison is the salvageable
  reading, subject to the same §8–§9 exclusions.

- **This does not change the cost-accounting thesis.** "Faster first query ≠ faster
  end-to-end performance" is unaffected. The secondary matrix does not attempt to
  overturn or restate that thesis.

- **What the secondary matrix IS for.** Deployment/feasibility (the generic keyed
  machinery serves 5 more strategies with no per-strategy runtime code), delivery
  correctness, and **footprint / qualitative mechanism-space** characterization
  around the 2e_K10 headline — deep leaf union (`2e_K500`), the leaf-only
  frequency-vs-random ablation (`leaf_freq_K10` / `leaf_rand_K10`), and the
  budget-matched (N=102) ranked / learned competitors (`2f_top102`,
  `learned_markov_102`). The last two rank with **no page-type knowledge** yet land
  on an emergent, seed-uniform **51 interior / 51 leaf** split — a recorded property,
  never imposed by the gate. These are qualitative/feasibility results, **not** new
  warm-latency claims.

None of the fail-closed identity gates were weakened to admit the five strategies;
the primary run identity is byte-frozen.
