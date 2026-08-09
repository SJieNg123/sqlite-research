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

---
---

# Follow-up Audit — 2d Identity & Concrete Arm Inventory

*Added after a focused second-pass audit (three parallel evidence sweeps + first-hand
code reading + direct measurement of the frozen residency CSVs). Where this pass corrects
or sharpens a statement in the first audit above, it is marked **CORRECTION** or
**SHARPENING** with the reason. The first audit is not removed; only proven errors are
flagged.*

## 2d Semantic Resolution

**There are two distinct constructions both called "2d" in this repository, and they are
not the same object.**

**Native `2d` (`kind: resident_interior`)** — `run_experiment.py:295-301`
(byte-identical `run_experiment_ycsb.py:294-300`):
```
if kind == "resident_interior":   # 2d: resident interior pages
    root = SLRU_RUNS if SEED is not None else ACCESS_RUNS
    src = root / f"hotpages_{w.lower()}{SLRU_SUFFIX[layout]}{_seed_suffix()}.csv"
    res = _resident_pages(_require_hotset(src))
    return {pn for pn in res if classify.get(pn, ("", 0))[0].startswith("interior")}
```
= **resident ∩ interior**, read from a **per-workload, per-seed** mincore residency CSV.
Interpretation **A (resident-interior subset)**, `interior_count ≤ 92`, workload/seed
dependent. Corroborated: `strategies/access/PREFETCH_ACCESS.md:29,137` ("4~32 interior…只
prefetch resident interior，不是全部 92"); `REPORT.md:682` ("只 prefetch resident 的
interior"). **The headline result plots use this construction** —
`figures/13_strategy_firstq_bars.py:21` and `figures/14_strategy_endtoend_stacked.py:21`
read `results/unified_v2/matrix/summary.csv`, whose `2d` column is the resident-subset
selection.

**OpenWhisk `2d`** — `build_artifact_manifest.py:82-109` derives the plan by taking
**every** `page_type.startswith("interior")` from the classifier and asserting the count
is exactly 92; `action/main.py:109-116` delivers `session.interior_offsets` and *raises*
unless `len == 92`. This is the **full structural interior skeleton**, workload/seed
independent. Interpretation **B**. It is mechanically **native `layers_92`**
(`run_experiment.py:291-294`: first-N interiors by offset; N=92 = all 92), **not** native
`2d`. This relabel is **intentional and documented**, not an accidental simplification:
`artifacts.native_ycsb.json:37,41` pins it as `kind: "interior_skeleton"`,
"workload-independent"; `build_artifact_manifest.py:8` calls it "the mandatory-interior
(2d) skeleton from the classifier"; `main.py:105` "92 mandatory interiors".

**Do they coincide? Yes — but only on residency-saturating workloads, which YC is.**
Measured directly from the frozen CSVs against `classify_before.csv` (92 interior pages
total):

| workload | resident pages | resident∩interior (native 2d) | == structural 92? |
|---|---|---|---|
| **YC** (`hotpages_yc.csv`) | **26331 (entire DB)** | **92** | **YES** |
| YCh01 (`hotpages_ych01.csv`) | 26295 | 92 | YES |
| C (`hotpages_c.csv`) | 483 | **4** | no (strict subset) |
| A (`hotpages_a.csv`) | 4416 | **18** | no (strict subset) |

YC (YCSB-C zipf over 600 000 rows) touches essentially the whole B-tree, so **every** one
of the 92 interior pages becomes resident → native `2d` = 92 = `layers_92` = the structural
skeleton **exactly**. On non-saturating workloads (C→4, A→18) native `2d` is a strict
subset and the structural pin would **over-deliver**.

**SHARPENING of the first audit** (Strategy Inventory §3, Semantic Mapping): the first
audit correctly said OpenWhisk-2d is structural and native-2d is a variable resident
subset "coinciding only when all interiors are resident." This pass **quantifies** that:
on the pinned OpenWhisk workload YC they coincide at 92 (so the pin is *faithful to native
2d for YC*), and it is a real divergence only if workload breadth expands to
non-saturating workloads.

**Answers.**
1. **Canonical native meaning of 2d:** resident-interior subset (A), per-workload/seed,
   `≤92`; strongest citation `run_experiment.py:295-301`.
2. **Meaning in headline plots:** same (A) — `figures/13,14` read the resident-subset
   `summary.csv`. Narrative hazard: `REPORT.md` repeatedly calls resident-2d "interior
   skeleton," a label that structurally belongs to `layers_92`.
3. **OpenWhisk structural-92:** an **intentional, documented** redefinition (kind
   `interior_skeleton`, "workload-independent"), faithful to native 2d **only because YC
   saturates residency**. Not an accidental acceptance-stage simplification.
4. **If native semantics must be preserved elsewhere:** the structural arm already has a
   canonical repo name — **`layers_92`** (a.k.a. OpenWhisk `interior_skeleton`). The
   resident arm is **`2d`/`resident_interior`**. For YC no rename is required (they are
   equal); for non-saturating workloads, deliver the resident subset under the name `2d`
   and reserve `layers_92`/`interior_skeleton` for the full 92.
5. **Distinct names (only needed if the structural arm is ever run under the "2d" label on
   a non-saturating workload):** keep `2d` = resident-interior (native claim);
   `layers_92` / `interior_skeleton` = full structural skeleton. Both names already exist
   in-repo — **no PROPOSED new name is required.**

## Concrete Arm Inventory

Roles are evidence-based: "final-figure" = appears in `paper/figures/` and/or the canonical
figure order `figures/plot_utils.py:75`
`STRAT_ORDER = [baseline, layers_5, layers_92, 2d, 2e_K10, 2e_K500, 2f_slru]`; "native
head-to-head" = `results/native_headtohead`.

| Arm | Family | Param | Role | In final figures/tables? | Canonical source |
|---|---|---|---|---|---|
| `baseline` | baseline | — | CONTROL (denominator) | yes (every fig; STRAT_ORDER) | `main.py:107`; pinned |
| `layers_5` | layers | 5 | HEADLINE (structural cheap pick) | yes (figs 13/14/16; STRAT_ORDER) | `run_experiment.py:157` |
| `layers_92` | layers | 92 | STRUCTURAL (**≡ `2d` skeleton on orig**) | yes (STRAT_ORDER) | `run_experiment.py:158,291` |
| `2d` | resident_interior | — | HEADLINE (targeted interior skeleton; the OpenWhisk claim) | yes (figs 13/14/17; STRAT_ORDER; h2h) | `run_experiment.py:159,295` |
| `2e_K10` | hot2e | 10 | HEADLINE (**primary method**) | yes (figs 13/14/17/18; STRAT_ORDER; h2h) | `run_experiment.py:160` |
| `2e_K500` | hot2e | 500 | HEADLINE-adjacent (large-K) | yes (figs 13/15/16; STRAT_ORDER) | `run_experiment.py:161` |
| `2e_K40`,`2e_K50`,`2e_K92`,`2e_K100` | hot2e | 40/50/92/100 | SENSITIVITY (K-sweep, tie-break) | measured, **not** plotted arms | regex `run_experiment.py:178`; `results/ksweep` |
| `leaf_freq_K10` | leaf_freq | 10 | ABLATION lever (tied to `2e_K10`) | yes (**paper fig 17**) | `run_experiment.py:185`; `17_lever_ablation.py:24` |
| `leaf_rand_K10` | leaf_rand | 10 | CONTROL (equal-count random leaves) | yes (**paper fig 17**) | `run_experiment.py:188` |
| `leaf_freq_K500`,`leaf_rand_K500` | leaf_* | 500 | ABLATION replicate | no (`results/ablation_k500`) | `run_experiment.py:185,188` |
| `2f_top14` | freqdump | 14 | PRIOR_WORK (InnoDB dump, **budget-matched to `2e_K10` on C = 14 pp**) | yes (**paper fig 18**; h2h) | `run_experiment.py:194`; `18_competitive_baseline.py:22` |
| `2f_top28` | freqdump | 28 | PRIOR_WORK (2× budget) | yes (fig 18; h2h) | `18_competitive_baseline.py:22` |
| `2f_top100`,`2f_top500` | freqdump | 100/500 | SENSITIVITY (fig-18 curve points) | curve only | `18_competitive_baseline.py:22` |
| `2f_slru` | slru | — | FOIL (first-query trap) | yes (figs 13/14/15/18; STRAT_ORDER) | `run_experiment.py:162` |
| `learned_markov_14`,`learned_markov_28` | learned_markov | 14/28 | PRIOR_WORK (Chen 1st-order Markov, LOSO) | yes (**native h2h table**; not a paper figure) | `run_experiment.py:201`; **UNFROZEN** `.gitignore:216` |
| `frequency_14`,`frequency_28` | frequency | 14/28 | PRIOR_WORK analysis twin | **NO — defined but never run** (no results CSV) | `run_experiment.py:204`; **UNFROZEN** `.gitignore:217` |
| `lp_sorted`,`lp_shuf` | lp | order | PRIOR_WORK (libprefetch; metric `deliver_us`) | yes (native h2h; **separate metric axis**) | `run_experiment.py:210,212`; `DESIGN_lp.md` |
| `lp_desc` | lp | order | DEBUG — **defined but never run** | no | `run_experiment.py:214` |
| `layers_{1..64}` (dense) | layers | dense | SENSITIVITY (plateau curve) | curve lines only (figs 04/11/09) | regex `run_experiment.py:175`; `results/nsweep_dense` |
| `*_static` (`2d_static`, `2e_K10_static`, …) | delivery-mode × strategy | — | SENSITIVITY (aging/churn robustness — **separate experiment axis**) | figs 07/12 | `churn.py`; `results/aging*` |

**The "14" budget is derived, not arbitrary, and is workload-specific.** `2e_K10`'s
footprint on legacy **C** = 14 pages (4 interior + 10 leaf), which is what `2f_top14` and
`learned_markov_14` are budget-matched to (`18_competitive_baseline.py:35-37`;
`overall_strategies.md:155`). **Measured on YC, `2e_K10` = 102 pages (92 interior + 10
leaf)** — so a YC budget-matched dump would be ≈`2f_top102`, **not** `2f_top14`. The
existing `2f_top14`/`learned_markov_14` are **C-calibrated**; the YC-matched N must be
re-derived (≈102) and is **UNKNOWN as a pre-existing named arm** — not guessed here.

**CORRECTION to the first audit's Strategy Inventory.** The first audit listed
`frequency_N` as a strategy family "requiring implementation/artifact work" (a Group-B
member). Deeper evidence shows `frequency_N` (a) selects **byte-identical page sets to
`learned_markov_N` in all 140 orig cells** and (b) **has no committed result rows at all**.
It is therefore a **duplicate cell**, not an independent arm — it should be **excluded**
from the matrix and kept only as a narrative twin (see below). The count of families
"requiring work" drops accordingly.

## Duplicate / Equivalent Arms

Proven from the selection code (`select_pages`, `run_experiment.py:288-348`) and direct
measurement on the canonical orig DB / YC residency.

| Relationship | Sets identical? | Order differs? | Metric differs? | Verdict for a first-query matrix |
|---|---|---|---|---|
| OpenWhisk structural `2d` **vs** `layers_92` | **YES** (both = the 92 interiors) | no | no | **Alias.** `layers_92` is the in-repo executable twin of the pinned skeleton. |
| native `2d` (resident) **vs** `layers_92` | **on YC: YES (both 92)**; on C/A: strict subset (4/18) | no | no | On YC they are **one cell** → do not include both. |
| `2e_K` **vs** `2d(interior) ∪ leaf_freq_K` | **YES by construction** (same `hot2e_*_K.csv`; interior part == 2d) | no | no | `leaf_freq_K` is a *component* of `2e_K`, not a duplicate; keep as ablation lever. |
| `lp_sorted` **vs** `2f_slru` | **YES** (byte-identical hotset, same offset order) | no | no | **Duplicate cell.** `lp_sorted` is a same-batch faithfulness cross-check only. |
| `lp_shuf`/`lp_desc` **vs** `2f_slru` | YES (same set) | **yes** | **yes** (`deliver_us`) | Delivery-order probe → **out of the first-query axis** (P4). |
| `frequency_N` **vs** `learned_markov_N` | **YES — all 140 orig cells** (empirical) | no | no | **Duplicate cell.** Keep one; the pair *is* the finding ("learning didn't change the set"). |
| `2f_topN` **vs** `2f_slru` | subset (top-N ⊂ resident) | n/a | no | Keep — partial-dump baseline vs full dump. |
| native `2d` **vs** `2f_slru` | subset (interiors ⊂ resident) | n/a | no | Keep — skeleton vs whole set. |

**True duplicate cells to collapse in the YC first-query matrix:** `layers_92`≡`2d`
(on YC), `lp_sorted`≡`2f_slru`, `frequency_N`≡`learned_markov_N`. Everything else is a
genuine subset/lever/order relationship, not a duplicate.

*(Caveat, Rule 12: `frequency ≡ learned_markov` is proven on orig 140/140 cells,
empirical not structural — the code paths are distinct and could diverge on another DB or
larger N. It holds for the arms and DB in scope.)*

## Resolved Primary First-Query Matrix

Concrete arms (not families), partitioned. Measured YC footprints shown as the
`{selected,interior,leaf}` a `DELIVERY_INVARIANTS` entry *would* carry (master/seed-1
residency; on YC the 92-interior half is seed-stable, only leaf identity varies per seed).

### A. MUST INCLUDE — the minimal set the stated first-query claims require
| Arm | YC footprint (measured) | Why it must be in | Canonical citation |
|---|---|---|---|
| `baseline` | 0 | no-prefetch denominator for every ratio | `plot_utils.py:75`; already pinned |
| `2d` | 92 / 92 / 0 | **headline** targeted interior skeleton; already implemented; on YC = the structural 92 | `run_experiment.py:159`; figs 13/14 |
| `2e_K10` | **102 / 92 / 10** | **primary method** (interior ∪ hot leaves) | `run_experiment.py:160`; figs 13/14/17/18 |
| `2f_slru` | **26331 / 92 / 26239** | **first-query-trap FOIL** — the reason a first-query matrix that also records e2e exists | `run_experiment.py:162`; figs 13/14 |
| `layers_5` | 5 / 5 / 0 | structural "how few interiors still help"; the **only `layers` arm distinct from `2d` on YC**; lowest-risk to add | `run_experiment.py:157`; figs 13/14/16 |

`baseline` and `2d` are already implemented/pinned; the three new MUST arms are `2e_K10`,
`2f_slru`, `layers_5`.

### B. SECONDARY / SENSITIVITY — strengthen the claims; belong in a separate sweep/table
| Arm | Note |
|---|---|
| `2e_K500` (YC 592/92/500) | large-K point of our method; in STRAT_ORDER + paper figs → strong secondary |
| `leaf_freq_K10`, `leaf_rand_K10` | paper fig-17 leaf-lever ablation + control; first-query-compatible; need leaf delivery |
| `2f_top{N}` prior-work dump | **N must be re-derived for YC (≈102 to match `2e_K10`, not 14)**; `2f_top14/28` are C-calibrated |
| `learned_markov_{N}` | prior-work; **UNFROZEN** (`.gitignore:216`); N likewise YC-specific; blocked on freeze |

### C. EXCLUDE from the first-query matrix
| Arm | Reason |
|---|---|
| `layers_92` | **duplicate-equivalent of `2d` on YC** (same 92 interiors); keep only as explanatory alias |
| `lp_sorted` | **duplicate of `2f_slru`** (byte-identical) |
| `lp_shuf`, `lp_desc` | **metric mismatch** — benefit is delivery order → `deliver_us` (P4); `lp_desc` also never run |
| `frequency_14/28` | **duplicate of `learned_markov`** (140/140) **and never run** in committed results |
| `2e_K40/50/92/100`, `layers_{1..64}` dense, `2f_top100/500`, `leaf_*_K500` | sensitivity sweeps → separate tables, not primary cells |
| `*_static` | different (aging/churn) experiment axis, not first-query |

```
FINAL_FIRST_QUERY_STRATEGIES (MUST) = [baseline, 2d, 2e_K10, 2f_slru, layers_5]
SECONDARY = [2e_K500, leaf_freq_K10, leaf_rand_K10, 2f_top<N_YC>, learned_markov_<N_YC>]
EXCLUDED  = [layers_92 (alias of 2d on YC), lp_sorted (=2f_slru), lp_shuf, lp_desc,
             frequency_14, frequency_28, 2e_K40/50/92/100, layers_dense,
             2f_top100/500, leaf_freq_K500, leaf_rand_K500, *_static]
```

**Remaining ambiguity (not guessed):** the YC budget-matched dump/learned N (≈102) is not
a pre-existing named arm; and per-seed leaf identity for `2e_K`/`2f_slru`/`learned_markov`
is not frozen in any pinned artifact (derivable from `strategies/access/runs/*_seed*.csv`).

## Matrix Size Impact

Pairing (`client/build_schedule.py:55-78`): one `pair_id` per
`(workload, seed, first_operation_id, handle_mode, repetition_id, target)`, each pair =
**2 invocations** (a `baseline` arm + the `target` arm, order AB/BA from `schedule_seed`).
`baseline` is never a standalone target — it is the paired reference. So

```
pairs        = workloads × seeds × first_ops × handle_modes × repetitions × |targets|
invocations  = 2 × pairs         (targets = the non-baseline MUST arms)
```

Fixed YC axes (`matrix.example.json`): workloads=1 (YC), seeds=10, first_ops=1 (id 0),
handle_modes=2 (warm, standalone), repetitions=10.

**Sanity check against the accepted milestone:** current pinned targets = {`2d`} (1) →
pairs = 1·10·1·2·10·1 = **200**, invocations = **400**, baseline=200, 2d=200, 40 per seed
— exactly the accepted WS2 acceptance counts. Formula validated.

**MUST INCLUDE** — non-baseline targets = {`2d`, `2e_K10`, `2f_slru`, `layers_5`} = 4:
```
pairs        = 1·10·1·2·10·4 = 800
invocations  = 1600            (800 baseline references + 200 each × 4 targets)
```
Incremental over the accepted 400: **+1200 invocations** (adds `layers_5`, `2e_K10`,
`2f_slru` as targets).

**MUST + SECONDARY** — add {`2e_K500`, `leaf_freq_K10`, `leaf_rand_K10`, `2f_top<N>`,
`learned_markov_<N>`} = 5 more targets → 9 targets:
```
pairs        = 1·10·1·2·10·9 = 1800
invocations  = 3600
```
(Several secondary targets are **gated**: `learned_markov` is unfrozen; `2f_top<N>` needs
the YC budget re-derived. The 3600 is the count *if implemented*.) Workload breadth is not
expanded here (YC only), per instruction.

## Revised Implementation Priority

**CORRECTION to the first audit's roadmap.** The first audit recommended `layers_5` as the
first batch on a **lowest-coding-risk** basis. Weighting by **final-arm importance** (as
instructed) changes the emphasis: `layers_5` is the lowest-risk *mechanism*, but its
research value is small (a structural reference point, not a headline claim). The
highest-value OpenWhisk arms are `2e_K10` (our primary method) and `2f_slru` (the
first-query-trap foil) — and both require the same new machinery.

1. **Lowest-risk implementation:** `layers_5`. Interior-only (0 leaf), seed/workload-
   independent, fixed count — reuses the exact `2d` skeleton delivery + cold-gate path;
   needs only a classify-derived 5-offset artifact, a `select_offsets` branch, and a
   `DELIVERY_INVARIANTS` entry `{5,5,0,5}`. **No per-seed or leaf machinery.**
2. **Highest-value implementation:** `2e_K10` (primary method) and `2f_slru` (foil). On
   YC these are 102 pages (92 interior + 10 leaf) and 26331 pages (whole DB) respectively
   — both need **leaf delivery + per-(workload,seed) plans + a variable/per-key
   `DELIVERY_INVARIANTS`**.
3. **Shared machinery to build first (minimizes throwaway):** the **per-(workload,seed)
   frozen plan table + leaf-capable, variable delivery-counts contract** (widen
   `select_offsets` to read a per-identity cached offset array; per-key counts). This one
   piece unlocks `2e_K10`, `2f_slru`, and every secondary prior-work/ablation arm. Build
   it once; do not special-case per strategy.
4. **Recommended order:**
   - **Do NOT lead with native-faithful-2d rework** — on YC the current structural `2d`
     already equals native `2d` (both 92), so there is nothing to fix for the pinned
     workload. Defer that only to if/when a non-saturating workload enters the matrix.
   - **Batch 1 (de-risk the extension pattern):** `layers_5` — a small PR that establishes
     the full "add an arm" path (`SUPPORTED_STRATEGIES` + `select_offsets` branch +
     `DELIVERY_INVARIANTS` + manifest-builder derivation + tests) **without** yet needing
     per-seed/leaf machinery. Low value but low cost and it proves the plumbing.
   - **Batch 2 (the real headline):** build the shared per-(workload,seed) leaf/variable
     machinery with **`2e_K10` as first consumer**, then **`2f_slru`**. This is where the
     paper's OpenWhisk claim actually lands.
   - **Batch 3:** ablation levers (`leaf_freq_K10`, `leaf_rand_K10`) and prior-work
     (`2f_top<N_YC>` after re-deriving N; `learned_markov_<N_YC>` after **freezing** its
     plans/models with LOSO provenance).
   - **Separate track:** `lp_*` delivery-cost (`deliver_us`) experiment — not the
     first-query matrix.

   **Net recommendation:** keep `layers_5` as the first (cheap, pattern-establishing) PR,
   but treat it as a warm-up — the priority in *value* terms is Batch 2 (`2e_K10` +
   `2f_slru` via the shared per-seed leaf machinery), which is the actual paper headline on
   OpenWhisk. This supersedes the first audit's "`layers_5` first" as the *value* ranking
   while preserving it as the *risk* ranking.
