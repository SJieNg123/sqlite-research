# DESIGN_learned.md — learned-style baseline arm (Phase 0 recon + plan)

**Task.** Port the *core* of the learned-prefetcher lineage (Chen+21 ICDE; Leaper) onto the
cold-start critical path: **learn page-transition patterns from a historical access trace, predict
the next pages to access.** Use a **transparent first-order Markov page-transition table**, not a
NN (Chen+21's own conclusion: model type is not the key; 8–20 M params here would be over-
engineering and irreproducible). Same harness as the libprefetch arm (DESIGN_lp.md recon applies).

**The paradigm question this arm exists to measure.** A transition predictor needs a **conditioning
context** — the *current* access — to predict the next. **Cold start at t=0 has no such context**
(no query has run yet). This arm quantifies how that paradigm **degrades at t=0**.

Status: **Phase 0 done — awaiting confirmation before Phase 1–3.**

---

## Phase 0 — Recon findings

### (a) Does the existing replay yield an ordered page sequence? — **No (snapshot only), but it is
### offline-reconstructable.**
- **Harness `--output` ops.csv** (`benchmark_harness.c:1152-1155`) = per-op metrics only:
  `op_no,op_type,target_id,rows_returned,bytes_returned,elapsed_ns,majflt_delta,minflt_delta`. It
  records the **key** (`target_id`) but **no per-op page list**.
- **regen Step A → residency_checker** (`residency_checker.c:67-95`) emits
  `page_number,is_resident` — a **SET (residency snapshot)**, not a sequence.
- ⇒ **No ordered page sequence exists today.** But it does **not** need harness instrumentation:
  for a read-only point query SQLite descends **root → interior → leaf** along a deterministic
  path, so the ordered page chain is reconstructable **offline** from `(workload trace + dbstat)`.

**Feasibility proven (this recon):** `dbstat` exposes a **`path`** column (columns:
`name,path,pageno,pagetype,ncell,...`). The `items` B-tree is **3 levels**: root `/`=pg2
(`internal`), 50 interiors (`/000/`=pg674, …), ~20k leaves (`/000/000/`=pg5, …); 20,034 pages
total. Reconstruction:
- **key → leaf**: reuse `gen_hotleaves.py:44-59` (first_rowid ranges + bisect).
- **leaf → ordered chain**: build `path → pageno` from all dbstat rows; the leaf's path prefixes
  give the ancestor chain. Verified: `key 20648 → leaf pg880 (/001/0dd/) → [2, 675, 880]`;
  `key 1 → [2, 674, 5]` (root→interior→leaf). Deterministic, no replay.

### (b) Sequence production point + format (proposal)
- **New offline generator `strategies/access/runs/gen_pageseq.py`** (sibling of `gen_hotleaves.py`,
  same key→leaf machinery): `gen_pageseq.py <db> <classify> <workload> <out>` → emits the ordered
  page-access stream.
- **Format**: CSV `op_no,page_number,page_type` — one row per page touched, in traversal order,
  `op_no` grouping the root→interior→leaf triple of each query. `op_no` lets the trainer choose
  **within-op** vs **cross-op** transitions without regenerating.

### (c) Train/test split (no leakage — mirrors Chen+21 warm-trace training)
- **10 seeded traces exist** (`workloads/workload_a_1..10.txt`, likewise b/c). So:
  **train on seed T, measure on seed M, T ≠ M, same distribution.** The transition table is built
  from the **train** seed's page sequence; the hotset it yields is delivered/measured against the
  **measure** seed's cold start. Training on the measured trace would be cheating.
- Proposed pair: **train = seed 2, measure = seed 1** (seed 1 is the master `results/main` stream).
  The learned hotset filename encodes the train seed for provenance.

---

## Central hypothesis — the t=0 paradigm degradation (grounded in the tree shape)

The `items` B-tree is only **3 levels**. A first-order Markov table `T[p→q]` trained on the page
stream has, **from the root (the only t=0 context — every query starts at root)**:
- root's successors = the **50 interior pages** = the *interior skeleton* — already captured by
  structural `layers_N`/`2d`.
- each interior's successors = its leaves, weighted by **access frequency** = the *marginal* — already
  captured by `2f_topN`.

⇒ **Prediction:** a Markov-from-root expansion at t=0 collapses to *(interior skeleton) ∪
(frequency-weighted leaves)* — i.e. it reproduces what `2e`/`2f_topN` already select, adding
**≈ nothing**, because there is no runtime context to condition on beyond "start at root." The
experiment's job is to **quantify that ≈0 gain** (learned_N ≈ 2f_topN / 2e within noise) — a clean,
honest negative result that sharpens the paper's "cost accounting on the critical path, not
prediction sophistication, is what matters" thesis.

### Theoretical backbone — the t=0 collapse is a structural necessity, not a weak-Markov artifact
Under **cross-op transitions** (leaf → next query's root; adjudicated), the page-transition chain is
**ergodic**, and an ergodic chain's **stationary distribution = long-run visit frequency = the
marginal**. A root-seeded expected-visit expansion **converges to the stationary distribution** as
step count grows ⇒ the t=0 expansion collapses to frequency ranking **for any context-free
transition model**, not merely our first-order table. This **pre-empts the "first-order Markov is a
strawman" objection**: swap in an LSTM or an n-gram — with **no conditioning context at t=0** they
all collapse to the marginal. This is the argumentative spine of the learned-style section:
`Jaccard(ml_static, 2f_topN)` is expected `> 0.9`, and if observed, the paper's conclusion is
"the *usable* part of the learned lineage in the cold-start regime is exactly the frequency ranking
`2f_topN` already covers; its true differentiator (conditional prediction) is **structurally absent
at t=0**."

---

## Phase 1–3 — implementation-point mapping (proposed; not yet built)

### Phase 1 — offline sequence + Markov trainer + hotset (mirrors freqdump/2f_top wiring)
- `gen_pageseq.py` (§b) — ordered page stream from the **train** trace.
- `strategies/learned/gen_pageseq.py <db> <classify> <workload> <out_seq.csv>` — reconstruct the
  ordered page stream (`op_no,page_number,page_type`); importable `reconstruct()` + CLI.
- `strategies/learned/train_markov.py <seq.csv> <out_prefix> --hotset-n 14,28 [--top-m 8]
  --w A --layout orig --train-seed 2`:
  1. build first-order Markov `T[p][q]` top-M successors → `<prefix>_trans.csv`;
  2. build the **marginal** (page visit-count ranking) → `<prefix>_marginal.csv`;
  3. for each N: emit `strategies/access/runs/learned_<w>_<layout>_N<N>_seed<T>.csv` =
     **marginal top-N** (= the expected-visit expansion at t=0, per adjudication 3),
     `page_number,is_resident` — **same format as `hot2e_*`/`freqdump_*`**;
  4. record train-seed + input sha256 in every artifact header (freeze standard).
- **`select_pages` kind `"learned"`** (`run_experiment.py:246`) reads that file via `_resident_pages`
  (like `freqdump` `:290-292`).
- **Register** `learned_<N>` in `resolve_strategy` (`:143`, regex like `2f_top<N>`), **not** in the
  default `STRATEGIES` matrix (explicit selection only).

### Phase 2 — delivery + schema
- Reuse the existing arms (pread/async) via `build_hotset`(offset) → `warmer`. Output schema
  identical to every other cell (`first_query_us`, `deliver_us`, `delivery_pct`, `majflt`).
- Delivery order is irrelevant to the learned *content* question, so it uses the default offset
  order (no interaction with the lp order lever).

### Phase 3 — validation (no formal batch)
- **Regression gate:** unchanged arms bit-identical (build_hotset default path untouched).
- **Reconstruction check:** `gen_pageseq` on a 5-op slice → verify each op emits exactly
  `[root, interior, leaf]` matching the dbstat path.
- **No-leakage check:** confirm train seed ≠ measure seed in the wiring (hard-asserted).
- **Hypothesis check (the finding):** `learned_N` vs **both** `2f_topN` **and** `2e_K10` — report
  **two Jaccard numbers** (vs 2f_topN = direct evidence of "collapse to frequency ranking"; vs
  2e_K10 = "what learned can pick, the dual-lever already covers"), plus first-query/deliver within
  noise. **Acceptance tripwire:** if `Jaccard(ml_static, 2f_topN) ≤ 0.8`, **STOP and investigate**
  (possible expansion bug, or small-denominator effect on the narrow workload C — check per-workload
  before proceeding).
- **Batch config:** add `learned_<N>` + reference cells to `tools/baselines_v2.sh` (config only).

---

## Adjudications (locked)
1. **Cross-op transitions** counted (the leaf→next-root back-edge makes root the stationary
   attractor; the root-seeded t=0 expansion depends on it; faithful to the real page stream).
2. **Root-only t=0 conditioning**; no warmup-context variant (would violate t=0). The "what if there
   *were* context" question is covered by the ml_online downgrade archive below.
3. **Expansion = expected-visit top-N** (greedy max-prob is a worse single DFS path; by the
   ergodicity backbone both collapse to frequency — that IS the finding). For ml_static, t=0 ⇒ the
   expected-visit expansion **equals the marginal top-N**, so ml_static's hotset = marginal top-N.
4. **train = seed 2, measure = seed 1.** Archive note: a future 10-seed CI generalizes the split to
   `train = (measure+1) mod 10`; not done now.
5. **Provenance + freeze:** learned hotsets under `strategies/access/runs/`, filename carries the
   train seed, added to the freeze manifest; results into `results/baselines_v2/`.

### Phase 1 additions (locked)
- **N ∈ {14, 28}** to start (matched footprint to `2f_topN` — the validity premise of the
  comparison), 100 optional. **Do not sweep large N** — learned's problem is not footprint.
- **Overlap metric = Jaccard, reported vs BOTH `2f_topN` and `2e_K10`** (they answer different
  questions, see Phase 3).
- **Batch modes:** `lp_*` stays **pread-only** (mechanism). `learned_N` is a *content* question →
  the deployment-relevant mode is **async**, so in `baselines_v2` `learned_N` + its references
  (`2f_topN`, `2e_K10`, baseline) run **async + pread** (pread as the oracle reference). Trim pread
  if the cell count exceeds budget.

## ml_online — downgraded to analytical argument (archived per the downgrade clause)
The secondary `ml_online` arm (query-time: on each fault to page p, look up the table and
`madvise` its top-M successors) **triggers the downgrade clause**: intercepting per-fault events
needs SQLite or kernel changes → not permitted. **Downgraded to an upper-bound argument** (itself
paper material):

> The fault chain is only **3 pages** (root→interior→leaf). The best online case is "after the
> interior fault, predict and prefetch the leaf." But consecutive faults in the chain are separated
> only by **µs-scale CPU work — there is no think-time window to hide prefetch latency**: an issued
> `madvise` needs tens of µs for readahead to land, while the demand fetch fires within a few µs.
> So online mode's theoretical ceiling ≈ **saving one fault (~60 µs, the per-fault cost measured via
> lp_shuf)**, and its realistic gain ≈ **0** (no overlap window). **Conclusion:** on a 3-level tree
> at cold start, online conditioning is **profitless even if implemented for free** — the second
> half of the paradigm argument (stronger than "we didn't build it").

## REPORT.md arm-definition stub (ready to paste) — three-layer evidence chain

> **learned-style arm (`ml_static` = `learned_N`).** 在同一基底重現 learned-prefetcher lineage
> （Chen+21 ICDE、Leaper）的**遞送核心**於 cold-start critical path。**Port 的核心** = 從歷史
> access trace 學 page 轉移、預測下一批頁（透明 **first-order Markov page-transition table**；
> Chen+21 自述模型類型非關鍵）。**剝除的編排** = NN(8–20M 參數)、Decision Module、背景預取執行緒。
> 訓練用**另一 seed 的同分佈 trace**（train=seed2 / measure=seed1，防 leakage——這是 learned 範式的
> *定義*：Chen+21 本身即 warm-trace 訓練、部署面對新流量）。
>
> **關鍵差異（冷啟動悖論）以三層證據呈現：**
>
> | w | N | Jaccard 同seed(ml,2f) | Jaccard 跨seed(ml_s2,2f_s1) | interior 吻合 | leaf 吻合(同seed) |
> |---|---|---|---|---|---|
> | A | 14 | **1.000** | 0.474 | 1.00 | 1.00 |
> | A | 28 | **1.000** | 0.217 | 1.00 | 1.00 |
> | B | 14 | **1.000** | 0.556 | 1.00 | 1.00 |
> | B | 28 | 0.931 | 0.217 | 1.00 | 0.89 |
> | C | 14 | 0.167 | 0.167 | 1.00 | 0.09 |
> | C | 28 | 0.098 | 0.098 | 1.00 | 0.06 |
>
> C 行註：**uniform-per-key (每 key 恰 5 次): no frequency signal, top-N leaves tie-broken
> arbitrarily** — 0.098 是「無信號」的直接觀測，非實作問題。
>
> 1. **方法層 — t=0 預測 ≡ 頻率排名。** 同 seed Jaccard=1.000（A/B, N=14）是 stationary 塌縮論證的
>    實測封印：expected-visit expansion 與頻率 dump 選出**逐頁相同**的集合。t=0 的 learned **恰好做
>    2f_topN 已做的事、一頁不多**。（cross-op chain ergodic ⇒ stationary=邊際；換 LSTM/n-gram 亦然，
>    非 first-order 太弱。）
> 2. **可用性層 — held-out 使 leaf 預測退化為「用過期樣本猜頻率」。** 跨 seed Jaccard 0.2–0.56，而
>    **interior 吻合恆=1.00**：結構性知識跨 seed 完美遷移，頻率知識跨 seed 漂移。誠實部署下 learned 的
>    leaf 選擇**嚴格不優於**同批頻率 dump 且更吵——實測延遲亦然（learned_14 fq≈383 µs vs 2e_K10 187、
>    2f_slru 94，其 stale leaf 未覆蓋 measure-seed 熱葉）。
> 3. **信號存在性層（C）— 有些 workload 根本無頻率信號可學。** C 同 seed Jaccard 都僅 0.1，interior
>    仍 1.00：唯一能穩定命中的是結構。強化 §7.3——C 的解鎖靠 access-frequency 槓桿**加 page-type
>    保底 path coverage**；任何頻率學習法（learned 或 dump）在 C 的 leaf 上都是擲骰子。
>
> **論文級結論句**：*At t=0, a transition model's usable output provably collapses to the marginal
> frequency ranking (same-seed Jaccard = 1.0); under honest held-out training that ranking degrades
> into a stale-sample estimate (cross-seed 0.2–0.56) while structural knowledge transfers perfectly
> (interior overlap = 1.0); and on uniform-per-key workloads there is no frequency signal to learn
> at all (C, Jaccard ≈ 0.1). Prediction sophistication is not the missing ingredient for cold-start
> prefetch — context is, and at t=0 context does not exist.*
>
> **誠實邊界（務必附）**：第二層的跨 seed 漂移幅度 **0.2–0.56 是單一 train→measure pair（seed 2→1）
> 的例示**，非普遍量；結論錨在「held-out 必然引入漂移、結構遷移/頻率漂移」這個**結構性事實**。日後
> 若加固，泛化切分（train=(measure+1) mod 10，已歸檔）跑幾個 pair 取分佈即可，現在不做。
>
> **online 變體**（見上節降級歸檔）即使免費實作，在 3 層 fault chain 上亦無可藏延遲窗口（上界 ≈ 省
> 一次 fault ~60 µs、實際 ≈ 0）。
