# A3 — 結果：Level-1 prefetch warmer 的 ablation 量測

第一批跑出來的真實數據。量測遵守 [../README.md](../README.md) §2 的嚴謹度與誠實規則：
**每臂 30 reps、報 median/p95/p99/min/stdev、cold start 看尾端、TTFQ 報樂觀＋保守兩版、null result 照實寫。**

## 設定

- DB：`prefetch_access/runs/test.db`（60 萬列、~103 MiB、4 KiB 頁）。
- workload：`workload_a_zipfian.txt`（Zipfian point read）。
- 每 rep：`evict`（posix_fadvise DONTNEED，無 sudo）冷快取 → warmer（post-cold-script，獨立 process、自己的 fd）
  → `benchmark_harness` 開 SQLite 量 first-query / avg / majflt。同一支 warmer，只切 env（§0.2 原則 1）。
- 量測機：kernel 6.17.0、gcc 15.2、非 root（見 [../PLAN.md](../PLAN.md)）。

## Ablation ladder（首批：L0 / L1 / L5；L2 tree-top、L3/L4 線上預取見「未做」）

| 臂 | 暖什麼 / 怎麼暖 | n | median | p95 | p99 | min | stdev | warm_us | majflt | **TTFQ 樂觀** | **TTFQ 保守** |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **L0_off** | baseline，不暖 | 30 | 508.4 | 517.8 | 529.7 | 435.7 | 29.7 | 0 | 180 | 508 | 508 |
| **L1_int_pread** | 92 個 interior，**pread**（阻塞） | 30 | **118.1** | 139.5 | 141.4 | 108.7 | 9.4 | **8028** | 177 | **118 (−77%)** | **8146 (＋1503%)** |
| **L1_int_fadvise** | 92 個 interior，**fadvise**（非阻塞） | 30 | 339.7 | 353.0 | 360.7 | 289.7 | 20.8 | 161 | 178 | **340 (−33%)** | **500 (−2%)** |
| **L5_intleaf_pread** | 92 interior ＋ 10 hot leaf，pread | 30 | 116.9 | 141.9 | 158.5 | 109.1 | 12.2 | 8767 | 181 | 117 (−77%) | 8883 |
| **L5_intleaf_fadvise** | 92 interior ＋ 10 hot leaf，fadvise | 30 | 338.8 | 357.9 | 390.8 | 291.1 | 25.8 | 168 | 181 | 339 (−33%) | 507 |

> TTFQ 樂觀 = 只算 first-query（假設 warmer 在背景/啟動空檔跑完）；TTFQ 保守 = first-query ＋ warmer wall-clock
> （假設 warmer 卡在關鍵路徑）。`vs base` 對 L0 median。

## 怎麼讀這張表（誠實版）

1. **暖 interior 確實把 TTFQ 砍很多**：508 → 118 µs（**−77%**），而且很穩（stdev 9.4、p99 才 141）。這是 warmer 的主要價值。

2. **但 pread vs fadvise 是整個故事的核心 —— 「暖」不是免費的**：
   - **pread（阻塞）**：first-query 118 µs 很漂亮，**但暖 92 個冷頁要花 8 ms**。一旦 warmer 卡在關鍵路徑，
     **保守 TTFQ = 8146 µs，比 baseline 還慢 16 倍**。pread 暖法**只有在有啟動空檔可重疊時才贏**。
   - **fadvise（非阻塞）**：暖只花 161 µs（發提示就回），保守 TTFQ ≈ 500 µs ≈ **打平 baseline**；代價是 first-query
     只降到 340 µs（**−33%**，因為 async readahead 在第一個 query 來之前還沒讀完）。
   - → **真相落在兩版之間**：要「保證便宜」選 fadvise（−33%、近乎免費）；要「最快 TTFQ」且有啟動空檔才選 pread。

3. **hot leaf 對 TTFQ 幾乎沒用（null result）**：L5 比 L1 只差 118→117 / 340→339 µs。因為第一個 query 是單點查詢、
   只碰**一個** leaf，那一個剛好是不是熱葉是碰運氣——所以多暖 10 個熱葉對「第一筆」幾乎沒幫助。
   （這呼應紅線 F10：沒幫助就照實寫。hot leaf 要有意義得攤在多筆查詢上、且須 train/test 切分才不算作弊。）

4. **warmer 是把 I/O「搬走」不是「消滅」**：`majflt` 五臂幾乎不動（177–181），而且 **avg 穩態延遲五臂都是 2.04 µs**
   —— warmer 對整段 workload 的吞吐毫無影響，**好處 100% 集中在第一筆查詢（TTFQ）**。pread 那 8 ms 就是被搬到
   warmer 階段的冷讀 I/O。所以這招只對「反覆冷啟動、在意第一筆延遲」的場景（serverless / 短命 process）有意義。

## 一句話

**暖 interior 能把冷啟動第一筆查詢砍 33–77%，但「砍多少」與「划不划算」完全取決於暖法與有沒有啟動空檔：**
pread 砍最多卻可能在關鍵路徑上淨虧、fadvise 近乎免費但只砍一半；而 hot-leaf 對第一筆是 null result。
兩版 TTFQ 都報，才不會只挑 −77% 那個好看的講。

## 未做（下一步，scaffolding 已在）

- **L2 tree-top 暖法**：只同步暖 root + 上 1–2 層（頁數極少 → warm_us 從 8 ms 砍到 ~µs 級），預期能把 pread 的保守
  TTFQ 問題大幅緩解。需先算每頁 tree level（b-tree 淺層 BFS）。
- **L3/L4 線上語意預取（pointer-ahead / fan-out）**：要 hook SQLite 讀路徑（VFS xRead 解析 child 頁號後 async 預取），
  比 batch warmer 侵入性高。
- **A1 shadow-tagging VFS**：目前 hotset 走 `classify_pages` oracle 路徑（結構派、無作弊）；live 活表是 production 路徑。
- **decay 對照**：接 `measure_staleness.py` + `runs_page_split`，驗 file change counter 偵測過期 → 降級。

## 重現

```sh
cd /home/u03/sqlite-research-project-sharing/prefetch_warmer/runs
# 產 hotset（結構派 interior + 史派 hot2e 熱葉）見本目錄 hotset_*.csv（由 classify_pages 產）
bash run_ablation.sh            # 5 臂 × 30 reps（~5 分）
python3 aggregate.py ablation_raw.csv
```
