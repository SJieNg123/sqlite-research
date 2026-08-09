# Full Strategy Audit

**Scope:** repository-wide, evidence-grounded, **audit-only** analysis of the complete
prefetch-strategy surface, to determine the full canonical strategy set the eventual
OpenWhisk workload×strategy matrix *should* support and in what order.

**Nothing in this document changes runtime code, `SUPPORTED_STRATEGIES`,
`DELIVERY_INVARIANTS`, `select_offsets()`, WS2 scripts, artifacts, models, or gates.**
It records what exists, what fits the accepted first-query OpenWhisk model as-is, and
what each remaining strategy would concretely require.

- Audited against commit `51d8731` (`main`; tip after the accepted WS2 milestone
  `df2ededc39c8a70f4183ba29df2b43e0d52f1769`).
- Canonical DB for every frozen input: `pipeline/preparation/layout_rewriter/runs/test.db`
  — sha256 `2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1`,
  107 851 776 bytes, `page_size=4096`, `page_count=26331`, 600 000 rows.
- Rule observed throughout: **counts that are not frozen in a pinned artifact are written
  `UNKNOWN` with a pointer to the missing source — never guessed.**

---

## Canonical Sources

The strategy universe is defined by a small number of authoritative files. Everything
else (docs, matrices, agent notes) is derived from these.

| Source | Role | What it fixes |
|---|---|---|
| `run_experiment.py` (`STRATEGIES`, `resolve_strategy()`, `select_pages()`) | **Canonical native registry** | The complete list of dispatchable strategy *kinds* and each kind's selection algorithm |
| `run_experiment_ycsb.py` | Native YCSB runner | Byte-identical selection dispatch to `run_experiment.py` (same `select_pages`/`resolve_strategy` semantics) |
| `deployment/openwhisk/action/main.py` (`SUPPORTED_STRATEGIES`, `DELIVERY_INVARIANTS`, `select_offsets()`) | **Accepted OpenWhisk runtime contract** | The strategies OpenWhisk actually serves today (`baseline`, `2d`) and their per-strategy fixed page-count contract |
| `deployment/openwhisk/config/artifacts.native_ycsb.json` | **Frozen replay pin** (`schema 1`, `replay_only`, `never_regenerate`) | Canonical workload id, seeds 1..10, strategies `[baseline,2d]`, handle-modes `[warm,standalone]`, the 12 native read configs, secondary headlines YCu/YCh01 |
| `deployment/openwhisk/ws2/matrix.example.json` | **OpenWhisk schedule template** | The scoped OpenWhisk matrix shape (workloads/strategies/seeds/handle-modes/first_operation_ids/repetitions) |
| `config/workloads.json` + `config/workload_registry.py` | Workload single-source-of-truth | The 12 native read configs (+ writes, + legacy A/B/C/C_hit/Z/YD/YE/CHURN); which have seed families |
| `overall_strategies.md`, `strategies_explained.md`, `strategies/README.md`, `strategies/*/PREFETCH_*.md`, `DESIGN_learned.md`, `DESIGN_lp.md`, `CANONICAL_SWAP.md` | Narrative provenance | *What* each strategy is and *how it was measured* natively; research role of each arm |

There is **no** single file that enumerates "the full OpenWhisk strategy matrix." The
OpenWhisk-facing matrix is deliberately narrow (`baseline`, `2d`) and lives in
`artifacts.native_ycsb.json` + `matrix.example.json`; the *native* strategy universe
lives in `run_experiment.py`. This audit bridges the two.

**Axes that are not delivery strategies (do not belong in the strategy column):**
layout (`1a orig` / `1b vacuum` / `1c ta`) is a build-time DB-geometry axis, and
memory-sharing (`4a` / `4b`) is a multi-process RAM axis. OpenWhisk pins the `orig`
layout only and runs one process; these axes are orthogonal to `select_offsets` and are
excluded from the strategy inventory below.

---

## Strategy Inventory

Every entry is a *kind* dispatched by `select_pages()` in `run_experiment.py`. For each:
canonical name, family/role, selection algorithm, delivery, required frozen inputs, the
page/interior/leaf shape, dependence, classification, and whether it is representable by
the OpenWhisk contract `select_offsets(strategy, session) -> fixed offsets, decided
before the first query`.

Shared facts (established by reading `select_pages()` and confirmed by the artifact
agents): **no** kind is online/stateful/adaptive at selection or measurement time. Every
kind returns a page set read from a **frozen, offline-computed CSV** (page numbers →
offsets). Online/learned character (SLRU recency, Markov transitions) lives entirely in
the *offline* plan-generation step, never in the measured path. None requires more than
the first query to *select*.

### 1. `baseline` (a.k.a. `no_prefetch`)
- **Role:** control / no prefetch.
- **Selection:** delivers nothing.
- **Delivery:** none.
- **Frozen inputs:** none.
- **Shape:** pages 0 / interior 0 / leaf 0. **Fixed.**
- **Dependence:** none.
- **Class:** static.
- **`select_offsets` representable?** **YES — already implemented.** `main.py:107-108`
  returns `[]`. `DELIVERY_INVARIANTS["baseline"] = 0/0/0/0`.

### 2. `layers_<N>` (structural interior skeleton; canonical `layers_5`, `layers_92`)
- **Role:** structural / B-tree interior skeleton; the "how few interiors still help"
  lever. Prior/structural baseline.
- **Selection (`select_pages` kind `layers`):** classify-only. Take the interior pages
  from `classify_before.csv`, order by `(file_offset, page_number)`, take the first `N`.
  **Independent of workload, seed, trace, first_operation_id, repetition, runtime state.**
- **Delivery:** interior offsets via `MADV_WILLNEED`.
- **Frozen inputs:** `classify_before.csv` (pinned; symlinked to the canonical
  classifier). No per-seed plan.
- **Shape:** interior `N` / leaf 0 / pages `N`. **Fixed** once `N` is chosen.
  - `layers_5` → 5 interior.
  - `layers_92` → 92 interior. **On the canonical `orig` DB there are exactly 92
    interior pages** (`interior_page_count=92`), so `layers_92`'s set *equals* the full
    interior skeleton — i.e. **identical to the `2d` skeleton delivered by OpenWhisk
    today**. `layers_92` is only distinct from "all interiors" on a DB with >92 interiors.
- **Dependence:** DB geometry only.
- **Class:** static / structural.
- **`select_offsets` representable?** **YES (directly).** Interior-only, fixed count,
  seed- and workload-independent — the *closest possible* extension to `2d`. Needs a
  classify-derived offset artifact (for `N<92`; `N=92` reuses the existing 92-interior
  list) + a `select_offsets` branch + a `DELIVERY_INVARIANTS` entry `{N,N,0,N}`. No
  per-seed plumbing, no leaf machinery, no variable-count contract.

### 3. `2d` (a.k.a. `resident_interior`) — **HEADLINE**
- **Role:** the headline "targeted interior skeleton" claim.
- **Selection (kind `resident_interior`/`2d`):** natively, the **resident** interior
  pages (interior ∩ resident working set). Workload/seed-derived natively.
- **Delivery:** interior offsets via `MADV_WILLNEED`.
- **Frozen inputs (OpenWhisk):** `config/plans/interior_pages.csv` (92 offsets, sha
  `37ed5e…28745e`), pinned in the image manifest as an `interior_skeleton` plan with
  `expected_pages=92`.
- **Shape (OpenWhisk):** interior 92 / leaf 0 / pages 92. **Fixed** — OpenWhisk pins the
  *structural* interior skeleton (all 92 interiors of the `orig` DB), not a per-seed
  resident subset.
- **Native shape:** interior ≤ 92, **variable** by workload/seed (resident subset).
  UNKNOWN per-seed counts — not frozen per seed in any pinned artifact; derivable from
  `strategies/*/runs` resident CSVs.
- **Dependence (OpenWhisk):** none (structural skeleton). **Native:** workload+seed.
- **Class:** OpenWhisk = static skeleton; native = workload-specific.
- **`select_offsets` representable?** **YES — already implemented** as the structural
  skeleton. `main.py:109-116` returns `session.interior_offsets`, validated
  `len==interior_page_count(92)` and every offset ∈ `interior_offset_set`.
  `DELIVERY_INVARIANTS["2d"] = 92/92/0/92`. (The native *resident-subset* reading is a
  different, per-seed object — see Semantic Mapping.)

### 4. `2e_K<K>` (a.k.a. `hot2e`; canonical `2e_K10`, `2e_K500`; ratio variants `3a`≈`2e_K40`, `3b`≈`2e_K92`)
- **Role:** **our** primary method — interior skeleton **∪ top-K hot leaves**.
- **Selection (kind `hot2e`/`2e_K`):** resident interior ∪ the `K` highest-frequency
  leaf pages from the access dump.
- **Delivery:** interior **and leaf** offsets via `MADV_WILLNEED`.
- **Frozen inputs:** `strategies/access/runs/hot2e_*` + leaf-frequency dump
  (`gen_hotleaves.py`). Per-seed.
- **Shape:** interior (variable) + leaf `K`. Pages = (#interior)+`K`. **Variable** across
  seed/workload; UNKNOWN exact per-seed interior count (not frozen in a pinned artifact;
  derivable from `strategies/access/runs`).
- **Dependence:** workload + seed (leaf hotset).
- **Class:** workload-specific, ranked-topK.
- **`select_offsets` representable?** **Mechanism yes, contract no as-is.** Requires
  (a) leaf-capable frozen offset artifacts **per (workload,seed)**, (b) a widened
  delivery contract with **variable** and **non-zero leaf** counts. The current single
  constant-tuple `DELIVERY_INVARIANTS` and global-per-strategy `select_offsets` cannot
  express a per-seed set.

### 5. `leaf_freq_K<K>` (S1 ablation lever)
- **Role:** ablation — leaves-only, to isolate the leaf contribution of `2e`.
- **Selection (kind `leaf_freq`):** the top-`K` leaves only (no interior).
- **Delivery:** leaf offsets.
- **Frozen inputs:** the same leaf-frequency dump; per-seed.
- **Shape:** interior 0 / leaf `K` / pages `K`. **Fixed count `K`**, but the *identity*
  of the `K` leaves is per-(workload,seed).
- **Dependence:** workload + seed.
- **Class:** workload-specific, ranked-topK.
- **`select_offsets` representable?** **Mechanism yes, contract no as-is.** Leaf-only
  delivery (interior 0), fixed count `K` but per-seed leaf identity → needs per-seed
  leaf offset artifacts + a leaf-bearing `DELIVERY_INVARIANTS` entry.

### 6. `leaf_rand_K<K>` (S1 ablation control)
- **Role:** control for `leaf_freq` — equal count of **random** leaves.
- **Selection (kind `leaf_rand`):** `K` leaves drawn by a deterministic RNG seeded
  `leafrand|{SEED}|{workload}|{layout}|{K}` (reproducible; matched to the `leaf_freq`
  subtype).
- **Delivery:** leaf offsets.
- **Frozen inputs:** none frozen as CSV — regenerated deterministically from the seed
  string. (Reproducible, but **not** a pinned artifact.)
- **Shape:** interior 0 / leaf ≈`K`. **Fixed count**, per-seed identity.
- **Dependence:** seed + workload + layout + K (via the RNG key).
- **Class:** seed-specific (deterministic control).
- **`select_offsets` representable?** **Mechanism yes, contract no as-is.** Same as
  `leaf_freq`; additionally its offsets are *generated*, so to be image-pinned it must be
  **frozen** to a CSV per (seed,workload,layout,K).

### 7. `2f_topN` (a.k.a. `freqdump`; canonical head-to-head `2f_top14`)
- **Role:** **prior-work** baseline — InnoDB-style frequency-ranked partial buffer dump
  (top-`N` most-visited pages, interior + leaf mixed).
- **Selection (kind `freqdump`/`2f_topN`):** the `N` highest-frequency pages overall.
- **Delivery:** mixed interior/leaf offsets.
- **Frozen inputs:** `strategies/access/runs/freqdump_*` (`gen_freqdump.py`); per-seed.
- **Shape:** pages `N`, **mixed** interior+leaf; the interior/leaf split is UNKNOWN
  per-seed (not frozen; derivable from the dump).
- **Dependence:** workload + seed.
- **Class:** workload-specific, ranked-topN.
- **`select_offsets` representable?** **Mechanism yes, contract no as-is.** Fixed total
  `N` but per-seed identity **and** per-seed interior/leaf split → needs per-seed frozen
  plans + per-key counts contract.

### 8. `2f_slru` (a.k.a. `slru`)
- **Role:** **our foil** — the whole resident working set (SLRU = mincore-snapshot
  analogy; see `strategies/slru/PREFETCH_SLRU.md`). Used to demonstrate the "first-query
  trap": wins TTFQ but loses cumulative e2e.
- **Selection (kind `slru`/`2f_slru`):** the entire resident page set.
- **Delivery:** the full resident set (interior + leaf).
- **Frozen inputs:** `strategies/slru/runs/hotpages_*`; per-seed.
- **Shape:** pages = |resident set| — **large and variable** by workload/seed; UNKNOWN
  exact counts (not frozen in a pinned artifact; derivable from `strategies/slru/runs`).
- **Dependence:** workload + seed.
- **Class:** workload-specific; the "online" recency framing is an **offline** mincore
  snapshot, not measured-time state.
- **`select_offsets` representable?** **Mechanism yes, contract no as-is; research role
  is e2e.** A fixed set *is* deliverable pre-first-query, but the count is large/variable
  (needs per-seed plans + variable contract), and its **claim** is cumulative-e2e, not
  TTFQ. Mechanically it produces a valid first-query number and is deliberately used as a
  first-query **foil** — so it is "implementable with work," flagged e2e.

### 9. `learned_markov_<N>` (prior-work, Chen-inspired)
- **Role:** **prior-work** baseline — first-order Markov next-page predictor, finite
  horizon, trained **offline** with **LOSO** (leave-one-seed-out).
- **Selection (kind `learned_markov`):** a **held-out, per-test-seed** frozen CSV of `N`
  predicted pages; leakage-guarded by `.meta.json train_seeds` (test seed ∉ train seeds).
- **Delivery:** mixed offsets.
- **Frozen inputs:** `strategies/learned/train_markov.py` output — **currently UNFROZEN**
  (git-ignored: `.gitignore:214-217`). Regenerable, not pinned.
- **Shape:** pages `N` budget, mixed; per-seed identity. UNKNOWN interior/leaf split.
- **Dependence:** test seed (selects the held-out plan); trained offline on disjoint
  seeds.
- **Class:** learned-offline, held-out (LOSO), **not** online/stateful at measure time.
- **`select_offsets` representable?** **Mechanism yes, contract no as-is; artifact
  unfrozen.** Needs per-test-seed frozen plans **+ frozen models with SHAs** (LOSO
  provenance) + variable/mixed counts contract.

### 10. `frequency_<N>` (prior-work analysis twin)
- **Role:** analysis baseline paired with `learned_markov` — raw visit-count ranking over
  the same held-out split (isolates "did learning beat plain frequency?").
- **Selection (kind `frequency`):** held-out, per-test-seed top-`N` by raw visit count;
  same LOSO split/guard as `learned_markov`.
- **Delivery:** mixed offsets.
- **Frozen inputs:** same generator family — **UNFROZEN** (git-ignored `.gitignore:214-217`).
- **Shape:** pages `N`, mixed; per-seed. UNKNOWN split.
- **Dependence:** test seed; offline.
- **Class:** offline held-out (LOSO).
- **`select_offsets` representable?** **Mechanism yes, contract no as-is; artifact
  unfrozen.** Same requirements as `learned_markov`.

### 11. `lp_sorted` / `lp_shuf` / `lp_desc` (prior-work, libprefetch)
- **Role:** **prior-work** baseline — libprefetch. Content is **identical to `2f_slru`**
  (the whole resident set); the arms differ **only in delivery ORDER** (sorted /
  shuffled / descending). See `DESIGN_lp.md`.
- **Selection (kind `lp`):** same page set as `slru`; the variant only re-orders the
  delivery sequence.
- **Delivery:** the resident set, in a specified order; the measured quantity is
  **`deliver_us`** (Δ delivery cost, natively 10–16×), not TTFQ.
- **Frozen inputs:** shares `slru` resident set; per-seed.
- **Shape:** pages = |resident set| (== `2f_slru`), variable; UNKNOWN counts.
- **Dependence:** workload + seed (set) + variant (order).
- **Class:** workload-specific; **metric = delivery cost**.
- **`select_offsets` representable?** **NO — metric mismatch.** The current model
  delivers an **unordered set** via `MADV_WILLNEED` and measures **first-query latency**.
  `lp`'s entire benefit lives in **delivery order → `deliver_us`**, which the first-query
  model does not observe. Delivering the same set yields a valid TTFQ but measures the
  wrong axis. Belongs in a **delivery-cost / e2e** experiment, not the first-query matrix.

**Canonical prefetch-strategy families found: 11** (`baseline`, `layers`, `2d`, `2e`,
`leaf_freq`, `leaf_rand`, `2f_topN`, `2f_slru`, `learned_markov`, `frequency`, `lp`).
Parameterized arms (`layers_5/92`, `2e_K10/K40/K92/K500`, `leaf_freq_K*`, `leaf_rand_K*`,
`2f_top14`, `learned_markov_N`, `frequency_N`, `lp_sorted/shuf/desc`) are members of
these families, not separate kinds.

---

## Artifact Audit

Provenance of the frozen inputs each strategy needs, and whether they are image-pinned,
repo-present, generated-but-unfrozen, or missing. **All frozen inputs derive from the one
canonical `test.db`** (sha `2504a6b1…`); native `strategies/*/runs/test.db` and
`classify_before.csv` are symlinks to it. The `page_count=20035` geometry-reference DB
(no secondary index, `sha256:null`) is a **separate, unmeasured** skeleton-geometry
artifact and is **not** a run DB.

| Strategy | Artifact | Status | SHA pinned? | Deterministic? |
|---|---|---|---|---|
| `baseline` | (none) | n/a | n/a | yes |
| `2d` | `config/plans/interior_pages.csv` (92 offsets) | **Image-pinned** in `artifacts.native_ycsb.json` | **Yes** (`37ed5e…28745e`) | yes (classify-derived) |
| `layers_92` | == the 92 interior offsets (same file as `2d` on `orig`) | **Present** (reuses 2d plan) | Yes (via 2d plan) | yes |
| `layers_5` / `layers_N` | first-`N`-interior offset list | **Derivable, not yet frozen** as its own artifact | No (not yet emitted) | yes (pure geometry) |
| `2e_K*` | `strategies/access/runs/hot2e_*` + leaf dump | **Repo-present, not image-pinned**, per-seed | No | yes (offline) |
| `leaf_freq_K*` | leaf-frequency dump (`gen_hotleaves.py`) | Repo-present, not pinned | No | yes |
| `leaf_rand_K*` | RNG-generated (`leafrand|seed|w|layout|K`) | **Generated, not frozen to CSV** | No | yes (deterministic RNG) |
| `2f_topN` | `strategies/access/runs/freqdump_*` (`gen_freqdump.py`) | Repo-present, not pinned | No | yes |
| `2f_slru` | `strategies/slru/runs/hotpages_*` | Repo-present, not pinned | No | yes (mincore snapshot) |
| `learned_markov_N` | plans `strategies/access/runs/learned_markov_*.csv` + models under `strategies/learned/` | **UNFROZEN — plans git-ignored** (`.gitignore:216`) | No | yes (offline, seeded) |
| `frequency_N` | plans `strategies/access/runs/frequency_*.csv` (+ `strategies/learned/`) | **UNFROZEN — plans git-ignored** (`.gitignore:217`) | No | yes |
| `lp_*` | shares `slru` resident set | Repo-present (via slru), not pinned | No | yes (set); order is the variable |

**Only `baseline` and `2d` are image-pinned and in the artifact manifest.** Everything
else is native-only: repo-present-but-unpinned, or (learned/frequency) generated-but-
git-ignored. To enter the pinned image, each needs a frozen artifact with a recorded
SHA — and, for the per-seed strategies, one artifact **per (workload,seed)**.

---

## Native vs OpenWhisk Semantic Mapping

**Native model (`run_experiment.py` / `run_experiment_ycsb.py`):** `select_pages(strategy,
workload, seed, layout, …)` returns a page set that may depend on workload, seed, layout,
and K/N. Measurement is native-harness (per-strategy metric: TTFQ for skeleton methods,
`deliver_us` for `lp`, cumulative e2e for the SLRU foil).

**OpenWhisk model (`action/main.py`):**
`select_offsets(strategy, session)` — note the signature: it takes **only the strategy
string** and the warm-process `session`. There is **no** `workload`, `seed`, or
`first_operation_id` parameter. Therefore the delivered set is **globally fixed per
strategy**. Delivery is per-page `madvise(MADV_WILLNEED)` on a fresh whole-file
`MAP_SHARED/PROT_READ` mapping (`residency.py PageMap.deliver_willneed`) — the primitive
is **offset-generic** (interior *or* leaf deliverable). Exactly one first query is
measured; all gates (artifact → request → identity → cold-reset → oracle → cold gate →
select → deliver → query → oracle+delivery validity) are fail-closed.

The delivery contract is a **single constant tuple per strategy**
(`DELIVERY_INVARIANTS[strategy] = {selected_page_count, selected_interior_count,
selected_leaf_count, delivered_page_count}`), and the runtime already partitions the
delivered set interior-vs-leaf (`selected_interior_count = |delivered ∩ interior_set|`).

| Native property | OpenWhisk today | Consequence for the matrix |
|---|---|---|
| set may vary per **workload** | `select_offsets` has no workload arg | any workload-varying set needs a **new parameterized delivery path** |
| set may vary per **seed** | no seed arg; set is global-per-strategy | any seed-varying set needs a **per-(workload,seed) plan table** |
| interior **and** leaf | primitive is offset-generic (leaves OK) | leaf delivery is *mechanically* supported; only the **counts contract** hard-wires leaf=0 today |
| counts vary per key | single constant tuple `DELIVERY_INVARIANTS` | variable/per-key counts need a **per-key counts contract** |
| some plans **unfrozen** (learned/frequency) | image-pin requires a SHA | those arms must be **frozen** before pinning |
| metric may be `deliver_us` / e2e | only first-query TTFQ is observed | `lp` (and the e2e *claim* of `2f_slru`) sits on a **different metric axis** |

**The single most consequential fact:** because `select_offsets` is global-per-strategy
and `DELIVERY_INVARIANTS` is one constant tuple, the **only** strategies that fit the
architecture *without new machinery* are those whose delivered set is a **fixed global
constant** — i.e. `baseline`, the structural `2d` skeleton, and the structural
`layers_N`. Every other strategy's set varies per seed (and often per key in its
counts), which the current contract cannot express.

`2d` deserves an explicit note: OpenWhisk serves the **structural** interior skeleton
(all 92 interiors, fixed), which is *not* the native **resident-subset** `2d` (variable
per seed). They coincide only when all interiors are resident. The OpenWhisk headline is
therefore the interior-skeleton claim, cleanly seed-independent.

---

## First-Query Compatibility

Can each strategy's page set be decided **before** the single measured first query,
purely from `(strategy, session)` state that exists prior to any query result?

**Mechanism-level answer: YES for all 11 families.** No dispatched kind reads a query
result, evolves state across queries, replaces cache entries based on a query sequence,
or trains during the measured execution. Selection is always a lookup into a frozen
(offline-computed) set. So there is **no** strategy that is first-query-incompatible on
"must observe prior queries / must run >1 query" grounds.

The compatibility gaps are therefore **not** about online adaptation. They are:

1. **Contract/plumbing gaps** (fixable with work, gates untouched): per-(workload,seed)
   plan table; widened `select_offsets` signature or per-identity plan cache; leaf-
   bearing and variable `DELIVERY_INVARIANTS`; freezing of `learned_markov`/`frequency`.
   Applies to `2e`, `leaf_freq`, `leaf_rand`, `2f_topN`, `2f_slru`, `learned_markov`,
   `frequency`.

2. **Metric mismatch** (genuinely incompatible with the *first-query* claim axis):
   `lp_*`. Its benefit is delivery **order → `deliver_us`**; the first-query model
   delivers an unordered set and measures TTFQ. Delivering `lp` yields a valid but
   *meaningless-for-lp* number. `2f_slru` shares an e2e-framing caveat but is
   mechanically a first-query foil, so it stays in the "implementable" bucket with an
   e2e flag; `lp` is the one whose *primary metric* the model cannot observe.

**Summary:** incompatibility here is **metric-level and artifact/contract-level, never
mechanism-level.** Nothing requires weakening the cold/oracle/identity/delivery gates.

---

## Strategy Implementation Taxonomy

Grouping by implementation pattern (to minimize duplicate code — strategies in a group
share one delivery/artifact path).

**Pattern P0 — Fixed global constant set (implemented).**
`baseline` (empty), `2d` (92-interior skeleton). One constant offset list + one constant
`DELIVERY_INVARIANTS` tuple. **No per-seed state.**

**Pattern P1 — Fixed global *structural* set, interior-only (nearest extension).**
`layers_N`. Same shape as P0 (interior-only, fixed count, seed/workload-independent);
differs from `2d` only in *which* interiors and *how many*. Reuses P0's entire delivery
path; needs only a classify-derived offset artifact + a `DELIVERY_INVARIANTS` entry
`{N,N,0,N}`. **This is the lowest-risk new group.**

**Pattern P2 — Per-seed frozen plan, leaf-capable, fixed *count*.**
`leaf_freq_K` (leaf-only, count K), `leaf_rand_K` (leaf-only, count K, control). One
per-(seed,workload) leaf-offset artifact + a leaf-bearing counts entry. Introduces
**per-seed plan lookup** and **leaf delivery counts** for the first time.

**Pattern P3 — Per-seed frozen plan, mixed interior+leaf, variable count.**
`2e_K` (interior∪K-leaf), `2f_topN` (top-N mixed), `2f_slru` (whole resident set). Adds
**variable and per-key** counts on top of P2. `lp_*` shares P3's *set* but not its
metric (see P4).

**Pattern P4 — Delivery-order / e2e metric (out of the first-query axis).**
`lp_sorted/shuf/desc`. Reuses P3's set; the deliverable is order, measured by
`deliver_us`. Requires an **ordered-delivery + delivery-cost** measurement path — a
different experiment, not a strategy cell in the first-query matrix.

**Pattern P5 — Offline-learned, held-out, currently unfrozen.**
`learned_markov_N`, `frequency_N`. P3-shaped delivery, **plus** a freezing step: per-
test-seed plans + models with SHAs + LOSO leakage provenance recorded in the manifest.

Reuse map: implementing **P1** once unlocks all `layers_N`. Implementing the **per-seed
plan table + leaf/variable counts contract** once (P2→P3) unlocks `leaf_freq`,
`leaf_rand`, `2e_K`, `2f_topN`, `2f_slru` together. **P5** adds a freeze/provenance step
on top of P3. **P4** is a separate measurement mode.

---

## Proposed Final Matrix

The intended full OpenWhisk matrix, partitioned by readiness. Counts that are not frozen
are marked **UNKNOWN** with their derivation source.

**Fixed axes (from `matrix.example.json` + `artifacts.native_ycsb.json`):**
- handle-modes: `{warm, standalone}` (2)
- first_operation_ids: `[0]` (1) — first-query-only measurement
- repetitions: 10
- schedule: baseline+target pairing, deterministic AB/BA (`build_schedule.py`)

**Workload axis (from `config/workloads.json`; seed families from
`workloads_refined/traces/seeds/`):**
- **Ready now:** `native_ycsb_c_read_zipf` (`YC`) — 10-seed family present, OpenWhisk
  oracle pinned.
- **Traces frozen, oracle needed:** `YCu` (uniform), `YCh01` (hot-01) — 10-seed families
  present; need OpenWhisk oracle generation.
- **Remaining:** the other 9 of the 12 native read configs + write configs + legacy
  (A/B/C/C_hit/Z/YD/YE/CHURN) — most lack 10-seed LOSO families.

**Strategy axis, partitioned:**

### Group A — ready now (fits the accepted first-query model as-is)
| Strategy | Status |
|---|---|
| `baseline` | Implemented, pinned |
| `2d` (interior skeleton) | Implemented, pinned |
| `layers_N` (esp. `layers_5`) | **P1 — directly implementable**; interior-only, fixed, seed-independent |

`layers_92` on the `orig` DB **≡ `2d` skeleton** (all 92 interiors) → it adds no new
evidence on this DB; `layers_5` (strict interior subset) is the genuinely new arm.

### Group B — needs implementation/artifact work first
| Strategy | Blocking work |
|---|---|
| `2e_K` (K10/K40/K92/K500) | per-seed frozen plans (repo→pinned) + leaf delivery + variable counts (P3) |
| `leaf_freq_K` | per-seed frozen leaf plans + leaf counts (P2) |
| `leaf_rand_K` | **freeze** RNG output to per-seed CSV + leaf counts (P2) |
| `2f_topN` (2f_top14) | per-seed frozen plans + per-key split contract (P3) |
| `2f_slru` | per-seed frozen plans + variable counts (P3); flag e2e claim |
| `learned_markov_N` | **freeze** plans+models (currently git-ignored) + LOSO provenance (P5) |
| `frequency_N` | **freeze** plans (currently git-ignored) + LOSO provenance (P5) |

### Group C — semantically outside the first-query matrix
| Strategy | Reason |
|---|---|
| `lp_sorted` / `lp_shuf` / `lp_desc` | benefit = delivery order → `deliver_us`; first-query model measures TTFQ, not delivery cost (P4). Belongs in a delivery-cost / e2e experiment. |

**Full-matrix cell count: UNKNOWN by design.** It is fixed only once (a) the workload set
is chosen (YC ready; YCu/YCh01 pending oracle; others pending seed families) and (b) each
Group-B strategy's per-seed plans are frozen (the interior/leaf/total counts are not
pinned anywhere today — derivable from `strategies/*/runs`). The *ready-now* sub-matrix is
concrete: **{baseline, 2d, layers_5} × YC × seeds 1..10 × {warm,standalone} × first_op 0 ×
10 reps.**

---

## Implementation Roadmap

Ordered, lowest-risk-first, each step preserving every accepted gate and touching no
existing baseline/2d semantics.

**Batch 1 (recommended first — lowest risk): `layers_N`, starting with `layers_5`.**
Why first: interior-only (0 leaf) → reuses the exact `2d` delivery + cold-gate path;
seed- and workload-independent → no per-seed plumbing; fixed count → fits the single-
constant `DELIVERY_INVARIANTS` contract unchanged in shape; artifact is a pure classify-
derivation of the already-pinned classifier; native parity exists (`layers_92` is in the
native YCSB suite). Concretely: emit a `layers_5` interior-offset artifact (first 5
interiors by `(offset,page)`), add a `select_offsets` branch, add
`DELIVERY_INVARIANTS["layers_5"]={5,5,0,5}`, extend `build_artifact_manifest.py`
derivation (currently hard-wired to 92) to emit the layers plan + expected count, add
tests. `layers_92` may be added for cross-DB generality but is documented as ≡`2d` on the
canonical DB.

**Batch 2: per-seed plan table + leaf/variable counts contract (unlocks P2/P3 as a
group).** Build the one piece of shared machinery: a per-(workload,seed) frozen plan
lookup + a leaf-bearing, variable `DELIVERY_INVARIANTS` (per-key counts). Land it first
with the simplest consumer — `leaf_freq_K` (leaf-only, fixed count) — then `leaf_rand_K`
(after freezing its RNG output). This is the single largest architectural step; it is
**work, not a gate change**.

**Batch 3: mixed interior+leaf variable-count strategies.** `2e_K` (our method),
`2f_topN`, `2f_slru` — they reuse Batch-2 machinery; each needs its per-seed plans frozen
and pinned. Flag `2f_slru`'s e2e claim in its metadata.

**Batch 4: learned/frequency freezing (P5).** Freeze `learned_markov_N` and
`frequency_N` plans **and models** per test seed, record SHAs + LOSO `train_seeds`
provenance in the manifest, then pin. Reuses Batch-3 delivery.

**Separate track (not the first-query matrix): `lp_*` delivery-cost experiment (P4).**
A distinct measurement mode observing `deliver_us` / ordered delivery. Do not shoehorn
into the first-query matrix.

**Workload breadth (parallel to strategy batches):** YC ready → add YCu, YCh01 by
generating their OpenWhisk oracles (traces already frozen) → then broaden to remaining
read configs as seed families are built.

---

## Unknowns / Blockers

**Hard blockers (must be resolved before the named arms can be *pinned*):**
- `learned_markov_N`, `frequency_N` plans/models are **UNFROZEN** (git-ignored,
  `.gitignore:214-217`). They cannot be image-pinned (no SHA) until frozen with LOSO
  provenance. — *Blocks Batch 4 only.*

**Architectural work items (not blockers, not gate changes):**
- `select_offsets(strategy, session)` is **global-per-strategy** (no workload/seed arg)
  and `DELIVERY_INVARIANTS` is a **single constant tuple**. Every seed-varying strategy
  (`2e`, `leaf_freq`, `leaf_rand`, `2f_topN`, `2f_slru`, `learned_markov`, `frequency`)
  needs a per-(workload,seed) plan table + a variable/per-key counts contract. — *Batch 2.*
- Leaf delivery is *mechanically* supported (`deliver_willneed` is offset-generic), but
  the counts contract hard-wires leaf=0; `build_artifact_manifest.py` hard-codes
  `EXPECTED_INTERIORS=92`, interior-only. — *Batch 2/3.*

**Workload unknowns:**
- YCu / YCh01 traces are frozen but have **no OpenWhisk oracle** yet. — *Group B workload.*
- Only `YC`, `YCu`, `YCh01` have 10-seed families; the other 9 read configs + writes +
  legacy lack them. — *Group C workload.*

**Count unknowns (never guessed):**
- Per-seed interior/leaf/total page counts for `2e_K`, `2f_topN`, `2f_slru`,
  `learned_markov_N`, `frequency_N`, and native-resident `2d` are **UNKNOWN** — not
  frozen in any pinned artifact. Source to derive: `strategies/access/runs/`,
  `strategies/slru/runs/`, `strategies/learned/` (regenerate/inspect). `leaf_freq_K` /
  `leaf_rand_K` totals are the chosen `K`, but per-seed leaf **identity** is UNKNOWN
  until frozen.
- The full-matrix total cell count is **UNKNOWN by design** until workloads and per-seed
  plans are fixed (see Proposed Final Matrix).

**No correctness blocker in the accepted infrastructure was found.** The clause "do not
modify the accepted OpenWhisk model unless the audit discovers a concrete correctness
blocker" is **not triggered**: identity/cold/oracle/delivery gates, first-query
semantics, and pairing/pacing are internally consistent and sufficient for the ready-now
sub-matrix. All expansion is additive.
