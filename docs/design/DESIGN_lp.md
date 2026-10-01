# DESIGN_lp.md — libprefetch-style baseline arm (v2)

**Task.** Port the *core mechanism* of libprefetch (VanDeBogart+09, USENIX ATC) into this
harness: **application-provided access list + sort by disk offset + batch synchronous load**.
Original gain = HDD seek ordering; purpose here = **measure that mechanism's contribution on
NVMe**. No SQLite changes, no kernel changes.

Status: **Phase 0 done. Design corrected per review. One spec-vs-Phase0 conflict flagged for
confirmation before writing code (see §Blocking).**

---

## ⚠️ Metric correction (supersedes the v1 Δ line — most important change)

v1 wrongly wrote `Δ = fq(lp_shuf) − fq(lp_sorted)`. **Wrong.** Both arms use `pread` (synchronous,
100% resident after load) → the cache state the first query faces is **identical** → **fq is
equal between the two arms (noise only).** The ordering effect lives in **`deliver_us`** (batch
load wall-time), not fq. libprefetch's HDD 20× is a reduction of **total load time (seek)**, not
of post-load query time.

- **Primary metric:** `Δdeliver = deliver_us(lp_shuf) − deliver_us(lp_sorted)`. HDD: entire gain
  source; **NVMe: expected ≈ 0.**
- **fq = control:** both arms' `fq` must match within noise (double-confirms both deliveries were
  complete / 100% resident).
- **e2e presentation:** drop into the existing `e2e_warm = deliver + fq` frame — cost accounting
  places the ordering effect naturally.

**Nuance to bake in:** a sorted full-set `pread` may trip the kernel's **sequential-readahead
detector** → even on NVMe `sorted` deliver may measure *faster*. If `Δ > 0` that is still a good
result: it **quantifies how much ordering survives on NVMe**. `ra_kb=128` is pinned and `majflt`
is recorded for both arms, so the effect is attributable. Story: **HDD Δ = orders of magnitude;
NVMe Δ = 0 or a millisecond-scale remainder — both outcomes support the paper's argument.**

---

## Phase 0 — Recon findings (unchanged)

**(a) Strategy registration** — `STRATEGIES` list `run_experiment.py:142-148`; resolver
`resolve_strategy` `:143-174` (named win, else regex); page selector `select_pages` `:246-296`
dispatches on `kind`, returns page-number set. New arm = new `kind` + registration.

**(b) ⭐ pread delivery order — the critical fact.** `warmer.c:75-84` reads the hotset CSV **line
by line in file order** and `pread`s each offset in that order. `build_hotset`
`run_experiment.py:299-306` writes rows **sorted by `file_offset` ascending**. ⇒ **offset-sorted
delivery is ALREADY the default for every existing arm.** Delivery order = line order in the
hotset file. **⇒ The newly-added thing is the UNSORTED (shuffle) arm; offset-sorted is the
existing default** (this is the "design reversed" case the task guardrail anticipated).

**(c) Hotset format + checksum.** CSV `page_number,file_offset` (`warmer.c:74-78`; harness
`--verify-hotset` accepts `is_resident|file_offset`, `benchmark_harness.c:146`). Freeze:
`_write_freeze` `:644-667` / `verify_frozen` `:670-694` (`hotset_freeze.sha256`). **Per-run
hotsets (`workdir/hotset_*.csv`, `:810-815`) are rebuilt fresh and NOT run-time checksum-gated;
freeze only covers regen-provenance residency inputs.** ⇒ a new arm deriving from an existing
residency input needs no new freeze entry.

**(d) 2f_slru / 2e_K10 generation.** Selection: `select_pages` kind `slru` `:293-295`
(`hotpages_*` resident set = full working set), kind `hot2e` `:260-262`. Materialization: run
pre-build loop `build_hotset(select_pages(...))` `:801-815`. Residency inputs from
`regen_hotsets` `:521-610`.

---

## Adjudications (locked)

1. **Access-list content = reuse `2f_slru` resident set (full working set).** Isolates ordering.
   **`lp_K10` DROPPED** — a 28/K10-page set's ordering effect is negligible by construction; the
   full 4,400-page set is the *maximum* opportunity for an ordering gain. If Δ≈0 on the full set,
   small sets follow *a fortiori*. **Scope = full set only.**
2. **Unsorted control = deterministic seeded shuffle.** shuffle = extreme "destroy offset
   locality"; sorted = the other extreme. Δ≈0 between the two **brackets every intermediate order
   (incl. trace-order)** → one pair closes the whole question space. No trace-order variant.
   **Shuffle seed recorded in output** for reproducibility.
3. **Order lever = file-side** (builder `order=` kwarg). Zero C change; order is CSV-inspectable.
   **No warmer `WARM_ORDER` env.**
4. **Register BOTH `lp_sorted` + `lp_shuf`.** `lp_sorted` (content+order ≡ 2f_slru) is a built-in
   **faithfulness cross-check** (same batch: `lp_sorted ≈ 2f_slru` must hold, else port has a
   bug); the pair also reads cleaner in the paper table than borrowing 2f_slru as the sorted ref.
5. **Output = new `results/baselines_v2/`** (all new arms + reference arms in one batch dir for
   paired comparison). **Not `results/competitive/`** (published-number provenance — no mixing).

---

## Phase 1–3 — implementation-point mapping (file-side; per adjudications)

### Phase 1 — order-parameterised builder + two arms
- **Add order-preserving writer.** `build_hotset` (`:299`) always offset-sorts. Add an `order=`
  path (new `build_hotset_ordered(pages, classify, dest, order, seed=None)` or an `order=` kwarg
  on `build_hotset`, default `"offset"` so **existing callers are bit-identical**):
  - `order="offset"` → ascending (current behavior).
  - `order="offset-desc"` → descending (direction-insensitivity check — optional 3rd point).
  - `order="shuffle"` → deterministic seeded shuffle; **seed recorded**.
- **`select_pages` kind `"lp"`** (`:246`) reusing the slru resident set (source as `:293-295`),
  carrying `strat["order"]` (and `strat["seed"]` for shuffle).
- **Register** `lp_sorted` (kind lp, order=offset) + `lp_shuf` (kind lp, order=shuffle) in
  `resolve_strategy`/`STRATEGIES` (`:142`/`:143`).
- **Route order into materialization**: run pre-build loop (`:806-811`) calls the ordered writer
  **only when `kind=="lp"`**; every other kind keeps `build_hotset` untouched.

### Phase 2 — delivery (no C change) + acceptance
- Reuse `run_one(...,"pread"...)` → `write_deliver_script` → `warmer` (pread path). Order is
  baked into the file (§b) → **no `warmer.c` edit.**
- **Acceptance (upgraded from sanity):** within one 3-rep smoke, `lp_sorted` vs `2f_slru` must
  match on **both `deliver_us` and `fq`, each < noise floor** (content+order identical ⇒ must be
  bit-equivalent behavior).

### Phase 3 — validation only (no formal batch)
- **Regression gate (3.9, hard):** `2f_slru` + `2e_K10` 3-rep smoke — numbers same order of
  magnitude as recent records (proves Phase 1 didn't touch existing paths).
- **Order check:** `lp_sorted` 1 rep — log first-5 / last-5 emitted offsets = strictly ascending;
  `lp_shuf` — not monotonic.
- **Protocol check:** `lp_full`/`lp_sorted` 1 cold cell — mincore cold `< 1%`, `delivery_pct =
  100` (sync pread), `majflt > 0`.
- **Batch config only (don't run):** `results/baselines_v2/` cells = `{lp_sorted, lp_shuf} × {A,
  B, C} × orig × pread`. **No async arm** (libprefetch is synchronous; async is meaningless for
  it).

---

## Guardrails
- **No existing arm's behavior / hotset / checksum changes one bit** — hard acceptance (3.9). All
  new code sits behind the `order=`/`kind=="lp"` path; under defaults the harness is byte-identical.
- **Do not run the full batch; do not touch `results/main`.**
- On any Phase-0-vs-spec conflict: **stop and report** (see §Blocking).

---

## Phase 3 — smoke results (validation; A × orig × pread, 3 reps)

| arm | deliver_us (median) | fq (median / min) | majflt | cold% | delivery% |
|---|---|---|---|---|---|
| **lp_sorted** | **17,608** | 103.5 / 98.9 | 0 | 0.0 | 100 |
| **lp_shuf**   | **271,317** | 110.2 / 96.6 | 0 | 0.0 | 100 |
| 2f_slru (ref) | 18,395 | 99.1 / 97.1 | 0 | 0.0 | 100 |
| 2e_K10 (ref)  | 2,519  | 180.8 | 181 | 0.0 | 100 |

**Acceptance — all pass:**
1. **Regression gate** — 2f_slru fq≈99, 2e_K10 fq≈181: same order of magnitude as prior records;
   existing offset path proven **byte-identical** (`cmp` lp_sorted vs default-build = identical).
2. **lp_sorted ≈ 2f_slru** — deliver 17.6 vs 18.4 ms (pread-deliver noise), fq_min 98.9 vs 97.1;
   content+order byte-identical ⇒ behavioral equivalence. ✓
3. **lp_shuf order** — CSV non-monotonic, same multiset, strictly-ascending lp_sorted; seed=424242
   logged. ✓
- **majflt note:** full-set arms (lp_*/2f_slru) → majflt=0 is *expected* (whole working set
  prefetched → query faults nothing). majflt>0 only for partial hotsets (2e_K10=181). The Phase-3
  "majflt>0" line was written for the dropped `lp_K10` (partial); N/A to the full-set arms.

**Headline finding (updates the v2 "NVMe Δ≈0" expectation):** on NVMe, **Δdeliver =
deliver_us(lp_shuf) − deliver_us(lp_sorted) ≈ 254 ms ≈ 15×** (271 ms vs 17.6 ms), while **fq is
equal within noise** (both ~99 µs, majflt=0). So the offset-sort mechanism contributes *massively*
even on NVMe — not from HDD seek time (none here) but from **kernel sequential-readahead firing on
ascending offsets + random 4 KB preads being far slower than streamed sequential reads**. The
metric correction is fully vindicated: **the entire effect is in `deliver_us`, none in `fq`.** The
async (fadvise) arm shows *no* order effect (all ~7 ms) — the penalty is specific to the
**synchronous pread** path, i.e. exactly libprefetch's model. Both HDD (seek) and NVMe (readahead
+ random-read) outcomes support the paper's cost-accounting thesis; the NVMe magnitude is a strong,
non-obvious result.

### Diagnostic rep — what "sorted" actually does (diskstats / rusage inputs)
Measured with `/usr/bin/time -v` "File system inputs" (512 B blocks the process read from device),
cold-dropped before each run, A/orig:

| arm | device reads (blocks / MB) | deliver_us |
|---|---|---|
| lp_sorted | 35,976 blk / **18.4 MB** | 18,310 |
| lp_shuf   | 36,296 blk / **18.6 MB** | 272,172 |
| working set (theory) | 35,328 blk / 18.09 MB | — |

**Verdict: `sorted` STREAMS the same ~17 MB working set — it is NOT readahead scanning a larger
span.** Both arms move the same device bytes (<1% apart, ≈ the working set); the working set's
offset span is 18.4 MB with 4,416 pages nearly densely filling the file's first 18 MB. The 15×
is therefore **sequential (readahead-coalesced into few large I/Os) vs random 4 KB IOPS on the same
data**, not an over-read. (This is the evidence behind the Phase 1b "readahead = implicit coalesce"
rationale above.)

### Smoke/diagnostic machine identity (record with the numbers)
`meow1`; AMD Ryzen 9 9950X (16C); kernel 6.17.0-19-generic; DB on `/dev/nvme0n1` = **KINGSTON
KC3000 (SKC3000D2048G) NVMe SSD**, `rotational=0`, `read_ahead_kb=128` (matches the harness's pinned
`ra_kb=128`); DB file 107.9 MB, working set 18.09 MB (A/orig). Absolute µs are machine-state
specific — cross-arm *within this batch* is the valid comparison.

## REPORT.md arm-definition stub (ready to paste; three-piece, InnoDB/Pre-Buffer 格式)

> **libprefetch-style delivery arm（`lp_sorted` / `lp_shuf`）。** 我們在同一基底（SQLite + OS
> page cache、cold-start critical path）重現 libprefetch（VanDeBogart+09）的**遞送核心**，以量測
> 其機制在 NVMe 上的貢獻。**選頁與遞送嚴格分離**（呼應 §4.2）：兩個 arm 的 hotset **內容完全等同
> `2f_slru`**（整個 resident working set，checksum 亦相同），差別**只在 warmer 的 pread 遞送順序**。
>
> - **Port 的核心**：application-provided access list ＋ **按磁碟 offset 排序** ＋ **批次同步載入**
>   （sync `pread`）。`lp_sorted` = offset 升序（libprefetch 的 C-LOOK 精神）；`lp_shuf` =
>   seeded shuffle（摧毀 offset locality 的對照極端，seed 記於輸出）。
> - **剝除的編排**：kernel-side reorder buffer、infill、AIMD contention controller 等 libprefetch
>   的 HDD 時代機制——我們只保留 selection→delivery，不改 SQLite、不碰 kernel。
> - **關鍵差異**：**遞送時長 `deliver_us` 被計入 e2e**，而原系統的 HDD 20× 正是**遞送時長的縮減**
>   （seek）。故主度量為 **Δdeliver = deliver_us(lp_shuf) − deliver_us(lp_sorted)**，`fq` 為
>   control（兩 arm 恆等於噪音內）。實測（A/orig）：**NVMe 上 Δdeliver ≈ 254 ms ≈ 15×**（sorted
>   17.6 ms vs shuffled 271 ms），`fq` 皆 ~99 µs、`majflt`=0——效應**全部落在遞送、無一在查詢**。此
>   NVMe 收益源非 seek（NVMe 無 seek），而是**順序存取觸發 kernel sequential-readahead ＋ 隨機
>   4 KB pread 遠慢於串流順序讀**；診斷實測兩 arm 讀取的裝置位元組相同（~18 MB ≈ 工作集），故
>   sorted 是「串流工作集」而非「掃更大 span 過度讀取」。
>
> **Caveats（與數字並列時必附）**：
> 1. **機器身份**：`meow1` / AMD Ryzen 9 9950X / kernel 6.17.0-19 / DB 在 **KINGSTON KC3000 NVMe**
>    (`/dev/nvme0n1`, rotational=0, `read_ahead_kb=128`)。絕對 µs 屬機器狀態；有效比較是**本 batch
>    內跨 arm**。
> 2. **`lp_*` 的 `deliver_us` 量的是同步 pread 的實際資料傳輸時長**；而 **async(fadvise) arm 的
>    `deliver_us` 量的是 hint 發射時長**——`posix_fadvise(WILLNEED)` 立即返回、真正的讀取在其後由
>    kernel 於**被測路徑之外**完成，故 async 的遞送順序**天生無效應**（非「無差異」，而是它根本沒在計
>    傳輸）。這是 async 恆 ~7 ms 的原因。
> 3. **與 §7.2 已發表的 0.6–7 ms 並列時務必標明 mode**：那些是 **async 發射時長**；本處 `lp_sorted`/
>    `lp_shuf` 的 17.6 ms / 271 ms 是 **pread 同步載入時長**（含實際傳輸）。兩者是**不同量**，不可直接
>    相比——並列時各自標 `(fadvise-issue)` / `(pread-sync-load)`。

---

## Resolved — spec-vs-Phase0 conflict (both confirmed)

- **(A) Order lever = file-side** (`build_hotset` `order=` kwarg), warmer C untouched. The initial
  spec's warmer-side `--delivery-order` is superseded by adjudication #3.
- **(B) `--coalesce` dropped from v1, deferred to optional Phase 1b.** Coalescing preads is a
  second mechanism independent of ordering (batching vs ordering); folding it into the same arm
  would make `Δ` unattributable. It must carry its own arm (`lp_coalesce`) + its own acceptance.

### Deferred — Phase 1b coalesce (archival rationale, updated post-diagnostic)
- **Kernel readahead already IS the implicit coalesce, and it is the source of the 15×.** The
  diskstats/rusage diagnostic (see below) shows `lp_sorted` and `lp_shuf` move the **same ~18 MB**
  of device bytes; the 15× comes purely from the sorted case's sequential preads being
  **readahead-coalesced into a few large device transfers**, vs the shuffled case's 4,416 random
  4 KB IOPS. An explicit `WARM_COALESCE` (merge offset-adjacent pages into one large `pread`) would
  therefore mostly **replicate what readahead already delivers for the sorted arm** — it is not a
  new optimization, only a way to *decompose* how much of the 15× is coalescing vs raw
  sequential-vs-random. **We do not open it** as an optimization arm.
- If a **mechanism-decomposition** study is later wanted, the correct site is a `WARM_COALESCE` env
  in `warmer.c` as its own arm `lp_coalesce` (verify merged `(offset,length)` pairs, `majflt`,
  `delivery_pct=100`), reported only as an attribution breakdown, not a performance claim.
