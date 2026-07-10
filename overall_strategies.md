# Overall Strategies — 現有策略總覽

> 本檔講「每個策略是什麼 + 目前最新結果」。想知道「怎麼測出來的」（共用 benchmark_harness、cold-start 機制、結構派 vs 歷史派前置、每策略確切 post-cold-script），見 [strategies_explained.md](strategies_explained.md)。權威全表見 [overall_results.md](overall_results.md)。

> **數字基準（本檔統一，canonical v2）：** 延遲策略均來自**同一批 `results/unified_v2`**（A/B/C × orig/vacuum/ta，async 10 / pread 10，全機 drop-caches、`cold_pct`=0）＋ prior-art baselines `results/baselines_v2`（背靠背同機器狀態、共享 2f_slru 錨點）。**這是新的絕對值來源，不需跨批換算。** 與舊 `results/main` 的差異是**加法性的 CPU 路徑漂移（非標量乘法）**：慢路徑 baseline 幾乎不變（A 523 vs 529，−1%），只有快的 CPU-bound 路徑受影響（2f_slru async 108 vs 127，−18 µs / −15%）。**絕對 µs 不可跨批比較**；錨點讀數記錄於 `results/unified_v2`。`first-q` = async fq_median；`e2e_warm` = deliver + fq（warm-process）。

三類正交策略，可自由組合：

1. **Layout**（build-time，一次性）：1a orig / 1b VACUUM / 1c type-aware
2. **Prefetch**（runtime，每次 cold start）：2c layers_N / 2d / 2e_K* / 2f SLRU；ratio 變體 3a/3b；prior-art baselines lp_* / learned_markov
3. **Memory-sharing**（多 process RAM）：4a MAP_SHARED / 4b private buffer pool

---

## 一、Layout 策略

決定 interior pages 的物理位置。一次性決策，影響之後所有 cold start。

**baseline first-q（µs，各 layout）：**

| Workload | 1a orig | 1b VACUUM | 1c type-aware (ta) |
|---|---:|---:|---:|
| A (Zipfian) | 523 | 707（**+35% 更慢**）| 658（**+26% 更慢**）|
| B (Uniform) | 749 | 1024（**+37% 更慢**）| 770（+3%）|
| C (high-key) | 1087 | 999（**−8% 較快**）| 867（**−20% 較快**）|

- **1a orig**：SQLite 原始配置，interior 散佈全檔（scatter ≈ 0.96）。所有實驗基準。
- **1b VACUUM**：`VACUUM;` 按 insertion order 重排、**不看 page type**（scatter 0.96→1.13 反而更散）；reclaim ~3% 檔案。**A/B 上把 baseline 變慢 35/37%**，只有高鍵集中的 C 略快。**不要為 cold-start 而 VACUUM。**
- **1c type-aware**（[layout_rewriter.c](pipeline/preparation/layout_rewriter/layout_rewriter.c)）：把所有 interior 搬到 slots 2..93 連續（scatter 0.96→0.0001），patch 所有跨頁指標，`integrity_check` 通過。**A/B baseline 推高（+26/+3%）、C 較快（−20%）**。它讓 `layers_N` 的「前 N＝B+tree 前 N 層」語意成立（見 2c）。

---

## 二、Prefetch 策略

決定 cold start 後、第一筆 query 之前，主動載入哪些 page 進 OS page cache。

### 2c — Layers N（structure-based）

只 prefetch **按 file offset 升序前 N 個 interior page**（skip leaves）。[prefetch_layers.c](prefetch_vacuum/src/prefetch_layers.c)。

> **語意：** 「≈ B+tree 前 N 層」**只在 1c layout 成立**（interior collocated 到檔頭）。1a/1b 上 interior 散佈，「前 N」只是檔案中最早出現的 N 個 interior。

**first-q 改善%（async，vs 同 layout baseline）：**

| layers_N (orig) | A | B | C |
|---|---:|---:|---:|
| N=5 | −27% | −44% | −4% |
| N=92 | −30% | −44% | **−38%** |

- **A/B**：N=5 即 plateau（A −27%、B −44%）；再加 interior 無感。
- **C**：**N≤46 幾乎沒用、N=92 才 −38%**（熱 interior 在檔案中段、按 offset 取前 N 選錯頁）。
- **N=1 普遍比 baseline 慢**（warmer/madvise 開銷 > coverage 受益）。
- 最佳 N 與 layout/workload 強耦合，非 universal。

### 2d — Access pattern，只 interior

跑一次 workload 後 `mincore()` dump residency，只 prefetch **走過的** interior（~4–30 syscall，deliver 可忽略）。[prefetch_access.c](strategies/access/src/prefetch_access.c)。hotset 由 `run_experiment.py --regen-hotsets` 凍結。

| (orig) | first-q | e2e_warm |
|---|---:|---:|
| A | −30% | **452 µs（−14%）** |
| B | −44% | **509 µs（−32%）** |
| C | −39% | **735 µs（−32%）** |

- first-q 與 layers_92 同級，但 deliver 更省（只載走過的 interior）。
- **e2e_warm 三 workload 皆改善（−14/−32/−32%）** — warm-process 下（不含冷 open）targeted interior 預熱有實質效益。

### 2e — Access pattern，interior + top-K leaves

2d 集合再加 top-K hot leaf（`gen_hotleaves.py`：key→leaf 頻率取前 K）。

**first-q 改善%（async，orig）＋ e2e_warm：**

| (orig) | 2e_K10 | 2e_K500 | e2e_warm 最佳 |
|---|---:|---:|---|
| A | −31% | **−64%** | 2d/2e_K10 −11~14%（K500 deliver 太重 → e2e +107%）|
| B | −44% | −38% | 2e_K10 −29%（uniform 無 hot leaf，K 無增益）|
| **C** | **−83%** | −83% | **2e_K10：e2e_warm 268 µs（−75%）— 全矩陣最佳 e2e** |

- **C：top-K hot leaf 解鎖 first-q −83%，K=10 即 saturate**，且 **e2e_warm −75%（268 µs）是全矩陣最佳**。
- **A：要 K=500 才 first-q −64%**，但 deliver ~0.8 ms → e2e_warm 反而 +107%；小 K 不夠、大 K 太貴。
- **B（uniform）沒有 hot leaf**，K 無增益，卡在 −44%。

### 2f — SLRU prefetch（整個 resident working set）

`mincore()` dump 全部 resident page，逐頁 `madvise/pread`。[prefetch_slru.c](strategies/slru/src/prefetch_slru.c)。**不碰 SQLite 內部**，但只知有無被用、不知次數。

| (orig) | first-q | e2e_warm |
|---|---:|---:|
| A | **−79%** | +1299%（13.5×，deliver ~7 ms）|
| B | **−86%** | +879%（deliver ~7 ms）|
| C | **−91%** | **−12%**（deliver ~0.76 ms 小）|

- **first-q 全矩陣最低（−79~91%）、layout-agnostic**；但 **deliver 由 hot set 大小決定** → **e2e 多半不具優勢**（A/B 慢一個數量級），只有 C（working set 小）warm-process e2e −12% 小贏。
- 適用「batch / avg latency」或 C 類小 working set，非一般 cold-start critical path。對照 [Figure 14](figures/out/14_strategy_endtoend_stacked.png)。
- **RAM-pressure（cgroup 20M）：** first-q「20M/unlimited」ratio 全落 0.95–1.07（working set ~17 MB < 20M cap），詳見 [overall_results.md](overall_results.md)。

### 3a / 3b — Access-pattern ratio 變體（= 2e_K40 / 2e_K92）

驗證「ratio 是不是 first-q 主軸」。3a = interior:leaf 7:3（K=40）、3b = 5:5（K=92）。

**first-q 改善%（async）：**

| | orig | vacuum | ta |
|---|---|---|---|
| 2e_K40 (3a) | A−28 B−44 **C−83** | A−22 B−50 C−81 | A−40 B−22 C−78 |
| 2e_K92 (3b) | A−52 B−44 C−83 | A−50 B−50 C−81 | **A +19（hump）** B−22 C−78 |

- **C**：任一 ratio 都 saturate（2e_K10 已夠 −83%）。
- **A × ta × K=92 = +19%（非單調 hump）**：ta 集中 interior 後加 92 leaf 引發 readahead pollution，K=500 才回穩。此 hump 為 ta 特有。
- **結論：K（leaf 數）才是主軸，ratio 只是 K 的副產品**（[Figure 10](figures/out/10_ratio_sweep.png)）。

### Prior-art baseline arms（baselines_v2 — 在同一基底重現既有做法的核心）

把外部 prior-art 的**選頁/遞送核心**移植到同一 harness，做同批配對比較。**不跑對方系統本尊，只重現核心 + 剝除編排。** 資料 `results/baselines_v2`（`tools/baselines_v2.sh`，orig）。

#### libprefetch-style — `lp_sorted` / `lp_shuf`（VanDeBogart+09）

核心：application-provided access list ＋ **offset 排序** ＋ 批次同步載入（sync pread）。**選頁與遞送分離**：兩 arm hotset 內容≡`2f_slru`（checksum 相同），只差 warmer pread **順序**（sorted=offset 升序 / shuf=打亂）。file-side `build_hotset(order=)`，warmer.c 不改。commit `5ac88da`/`850b27b`。

**主度量 Δdeliver = deliver(shuf) − deliver(sorted)**（fq 為 control，兩 arm 應相等）：

| (pread) | deliver sorted | deliver shuf | **ratio** |
|---|---:|---:|---:|
| A | 17,953 µs | 280,281 µs | **15.6×** |
| B | 18,176 µs | 274,965 µs | **15.1×** |
| C | 2,775 µs | 29,175 µs | **10.5×** |

- **NVMe 上 offset 排序遞送快 10–16×**，效應**全在 deliver、fq 不變**（載完 cache 相同）。診斷（rusage File system inputs）：sorted 與 shuf 讀**相同裝置位元組（~18 MB ≈ 工作集）** → 15× 純為順序（readahead 合併成大 I/O）vs 隨機 4KB IOPS，**readahead 即隱式 coalesce**。async(fadvise) 無此效應（僅發 hint）→ 專屬同步 pread 路徑。

#### learned-style — `learned_markov`（Chen-inspired transition baseline）+ `frequency`

**Chen 等（ICDE 2021）formulation 啟發**的輕量 baseline（**非重現**）：保留「歷史 trace 學 page 轉移、預測下一批頁 + held-out」，把不可得 neural model 換成透明**一階 Markov**；未重現 Decision Module/背景執行緒/neural 架構；只用 page-access context。實作 `strategies/learned/`：每 query 獨立 episode `START→root→interior→leaf→END`（僅 op 內 transition）、`P(q|p)=count/Σ`、從 START 做 **finite-horizon expected-visit**（horizon=max深度+1，非 stationary）；hotset 取 `_scores.csv` top-N。**held-out LOSO**（測 master=seed1、訓練 seeds 2..10，硬 assert `test∉train`）。`frequency_N` 為**獨立 code path** 分析臂（取 `_marginal.csv`）。footprint 對齊 `2f_topN`。commit `a98e673`（8 validation gate 全過）。

**async fq / e2e_warm（orig）：**

| | learned_markov_14 | 2f_top14 | 2e_K10 |
|---|---:|---:|---:|
| A | 391 / 474 | 391 / 473 | 356 / 458 |
| B | 414 / 496 | 415 / 497 | 414 / 519 |
| C | 186 / 267 | 185 / 268 | 186 / 268 |

**Jaccard（hotset 相似度，離線分析、非性能指標）：** `J(learned_markov, frequency)=1.000`（全 workload/N）；`J(learned_markov, 2f_topN)` A/B N14 0.47/0.56、N28 0.22、**C=1.00**。

- **learned_markov 三 workload 的 async fq/e2e 都 ≈ 2f_topN（逐格幾乎相同）** — 此 transition baseline 在冷啟動 regime 的可用輸出，落在 `2f_topN` 已覆蓋的頻率排名範圍。
- **learned_markov 與 frequency 選同一組頁（J=1.0）**：當前 3 層固定深度 tree 的**觀測性質**（每頁單一深度 → expected-visit score = 正規化 visit frequency），由兩條獨立 code path 算出 — **非**普遍宣稱、不外推其他模型。
- **C 的 caveat（J(lm,2f_top)=1.0）**：C leaf score 平（每 key 恰 5 次），兩 arm 在統一 tie-break 下選出**相同 hotset** → fq 必然相等（186≈185）；186 遠低於 interior-only 地板意味被測 first op 恰落在此任意選擇裡——**tie-break 運氣、非 selection 能力**。full-LOSO 掃全 seed 時 C 應呈雙峰/高變異。**勿讀成「learned 在 C 有效」。**
- **Workload E 未支援**：range scan 非 3-page episode，`gen_pageseq` 對 scan fail-loud（需真正 range 頁序列重建）。

---

## 三、Memory-sharing 策略（4a / 4b）

> 這是 **RAM 用量實驗（multiprocess），非延遲批** — 數字來源與上面不同，不對齊 unified_v2。

- **4a MAP_SHARED**：所有 process `mmap(MAP_SHARED)` 開同一 DB，共享同一份 OS page cache（SQLite `PRAGMA mmap_size` 走此路）。實測 3 child 各讀 1/3，最後 mincore 全 resident；任一 process 的 `MADV_WILLNEED` 其他立即受惠。**prefetch 成本 O(1)、效益隨 process 數 O(N) 放大** — mobile/embedded 的天然 multiplier。
- **4b Private buffer pool**（對照）：每 process 獨立 buffer pool。process 少時反而省 RAM（只 cache working set）；但 process→∞ 時總 RAM 爆量（100 proc ≈ 1 GB vs MAP_SHARED ~100 MB）→ **多 process 一定要走 mmap**。

---

## 組合策略 — 目前最佳堆疊

```
Layout:   type-aware (1c)   ← scatter 0.00
Prefetch: 2e_K10            ← C 上 first-q −83% / e2e_warm 268 µs（−75%）
Memory:   MAP_SHARED (4a)   ← 多 process 自動受惠
```

慢 workload C 上 2e_K10 把 first-q 從 1087 → ~185 µs（**−83%**）、warm-process e2e **268 µs（−75%）**，且少數 prefetch syscall 可由任一 process 出資、整個 fleet 共享。

---

## 策略狀態總覽

| 類別 | 策略 | 狀態（first-q，orig）|
|---|---|---|
| Layout | 1a orig | baseline（A 523 / B 749 / C 1087 µs）|
| Layout | 1b VACUUM | A/B baseline 變慢（+35/+37%）、C 略快（−8%）|
| Layout | 1c type-aware | A/B baseline 推高（+26/+3%）、C 較快（−20%）|
| Prefetch | 2c Layers N | A −27~30% / B −44% / C −38%（需 N=92）；最佳 N 與 layout 耦合 |
| Prefetch | 2d interior-only | A −30 / B −44 / C −39%；**e2e_warm 三 workload 皆改善（−14~32%）**|
| Prefetch | 2e interior+top-K | **C：K=10 first-q −83%（e2e_warm 268 µs / −75%）**；A 需 K=500 −64% |
| Prefetch | 2f SLRU | first-q −79~91%（最低），deliver 太重 → e2e 多半不利（C 例外 −12%）|
| Prefetch | 3a/3b ratio（K40/K92）| K（leaf 數）才是主軸；A×ta×K92 有 +19% hump |
| Baseline-v2 | lp_sorted / lp_shuf（libprefetch）| **offset 排序遞送 Δdeliver 10–16×**，全在 deliver、fq 不變 |
| Baseline-v2 | learned_markov（Chen-inspired）| async fq/e2e **≈ 2f_topN**；hotset≡frequency(J=1.0，tree 性質)；E 未支援 |
| Memory | 4a MAP_SHARED | 成本 O(1)、效益隨 process 數放大（RAM 實驗）|
| Memory | 4b Private buffer pool | 對照（process 多時 RAM 爆量）|

> pread（oracle 上限）與 async（madvise 實際交付）為兩獨立比較組，定義見 REPORT §3。權威全表見 [overall_results.md](overall_results.md)。
