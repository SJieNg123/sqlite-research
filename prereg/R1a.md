# R1a：SQLite 預設設定下，存活 process 的第一個查詢時 interior 是否在 pager cache（B 組）

> **已登記。** 判定規則的數字依 2026-11-11 的決定凍結，理由附在旁邊。依護欄第 1 條，本檔 commit 之後才能跑；commit 後不再修改，需要變更時另開新的 prereg 並寫明原因。
> 起草：2026-11-11，同日修訂。repo rev `ae29344`；DB `pipeline/preparation/layout_rewriter/runs/test.db`（107,851,776 B，26,331 頁，page size 4096）。

## 要回答的問題（只有這一個）

存活的 process 保留 SQLite connection，並用 SQLite 預設設定（`mmap_size=0`、`cache_size=-2000`）。OS page cache 被清空後，它跑第一個查詢時，查詢路徑上的 interior 頁是否由 SQLite 的 pager cache 供應？

這份不回答 interior 在自然記憶體壓力下會不會被 kernel 逐出；那是 R1b 的問題。

## 組別

- **B 組（本實驗的主角）**：`PRAGMA mmap_size=0`，不設 `cache_size`（即 SQLite 預設 -2000 KiB，pager 約 480 頁），保留 connection。
- **C 組（成對對照，只用於次要指標）**：現行 harness 設定 `mmap_size=檔案大小`、`cache_size=0`。warm-up 與 probe 都和 B 組相同。C 組讀頁走 mmap 的 `xFetch`，不經過 `xRead`，所以主要指標與逐筆一致性檢查只套用在 B 組。

## 設計使然的前提：swap=0 時 B 組的 pager cache 必然存活

pager cache 位於 process 的 heap，是 anonymous memory。在 `MemorySwapMax=0`、沒有 swap 的情況下，kernel 無法回收 anon 頁；能回收的只有 file 頁。所以只要 process 沒被 OOM kill，B 組的 pager cache 在任何記憶體壓力下都會原封不動。

**這是設計使然，不是實驗發現。** 本實驗因此不施加記憶體壓力。我們只清 OS page cache（現行的 madvise 加 drop_caches），因為在 swap=0 的條件下，記憶體壓力能做到的最多也就是這樣：清掉 file 頁，碰不到 pager。

Lambda 沒有 swap，所以 swap=0 對應我們研究的平台。有 swap 的平台上 pager 可能被換出，那種情況不在本實驗範圍內。

## 每個 run 的流程

1. 開啟 connection（`before-cold`，與現行相同），做 schema init。
2. **warm-up**：在同一個 connection 上，跑 workload 串流的前 N 個 op（`--pre-cold-ops N`）。
3. **cold 事件**：現行的 reset，即 `MADV_COLD/PAGEOUT/DONTNEED` 加 setuid-root `drop_caches`，並沿用現行的 cold gate（mincore 殘留 ≤ 1%）。
4. **probe**：串流中的第 N 個 op（0-based），也就是 warm-up 之後的下一個 op。量測 first-query latency，並記錄下面的計數。
5. 照常跑完其餘 op，量 e2e（次要）。

warm-up 和 probe 都取自同一個 seed 的串流，所以 probe 的 key 不是特別挑過的。每個 (workload, seed, N) 的 probe 都是固定的，事先就知道是哪個 key。

## 指標

**主要指標（B 組，每個 run 一個二元值）**：probe 期間，查詢路徑上的 interior 頁（root page 2，以及該 key 所屬的第二層 interior 頁）**沒有一頁**是 pager miss，就算 interior hit。

- 判定依據是 probe 期間的 VFS `xRead` 追蹤：offset 對應到 page number，再對照 classify CSV。page 1 在 offset 24 讀取 16 bytes 的 change-counter，屬於檢查，不算頁擷取。
- 交叉檢查：probe 前後 `sqlite3_db_status(SQLITE_DBSTATUS_CACHE_HIT/CACHE_MISS)` 的差值。CACHE_MISS 的差值應等於 `xRead` 追蹤中的頁擷取數。這兩個依據不一致時，該 run 標為無效並回報。

**次要指標（只描述，不做判定）**：
- B 組與 C 組的 first-query latency，按 instance 成對相減，報 bootstrap CI。
- `--pre-cold-ops` 掃描結果。
- probe 的 leaf 是否 hit。

## 主要檢查：實測與模擬逐筆一致（先於判定）

`prereg/design/R1a_probe_predictions.csv` 列出每個登記 run 格的預測，在 commit 時一起凍結：3 個 workload × seed 1–10 × N ∈ {0, 1, 10, 100, 1000}，共 150 筆。每筆包含：
- probe 的 key、第二層頁、leaf 頁；
- page 1、root、第二層頁、leaf 各自是否預測為 hit；
- 預測的頁 miss 數（`pred_page_misses`）；
- 在 pager 容量 450 與 483 之間是否敏感：150 筆全部不敏感。

每個 B 組 run，都拿實測（`xRead` 追蹤中每一頁 hit 或 miss，以及 CACHE_MISS 的差值）與該格的預測逐筆比對。

- **回報**：一致的筆數與不一致的筆數，按 workload 與 N 分開列。
- **不一致的每一筆都要調查並寫明原因**，例如模擬漏了某個 SQLite 行為、儀器錯誤，或 pager 的實際容量不同。不可以把不一致的 run 直接剔除。調查結果不改變下面的判定，判定照登記的規則做。
- N=0 那幾格同時就是有效性控制：預測每一筆都是 interior miss。

模擬本身也要求可重跑：`python3 -I prereg/design/pager_lru_sim.py predict <DB> workloads <OUT.csv>` 產生的 CSV，必須與凍結的版本逐位元組相同。

## 有效性檢查（不過就作廢該 run，並回報作廢率）

- **OS cold gate**：沿用現行規則，mincore 殘留 ≤ 1%。B 組的 SQLite 不做 mmap，所以 cold gate 用的是 harness 自己對 DB 的 mmap（見〈執行前需要的工作〉）。
- **唯讀**：`--readonly`。DB 的大小與 mtime 在 run 前後必須相同。
- **`xRead` 追蹤與 `db_status` 一致**：見〈指標〉。

## `--pre-cold-ops` 怎麼決定

這是設計時的計算，不是量測：用的是 DB 結構與 workload 檔，沒有跑 benchmark。腳本與輸出放在 `prereg/design/`：
- `btree_shape.py` / `.out`：items 表的 B-tree 深度是 3，有 1 個 root（page 2）和 50 個第二層 interior。另有兩個 index B-tree（root 是 3 和 4），但所有 workload 都只做 rowid 的 point read，從不讀它們。
- `pager_lru_sim.py summary` / `pager_lru_sim.out`：把每個 key 對應到它的第二層頁與 leaf。每個 op 碰 page 1、root、第二層頁、leaf 四頁。用容量 C 的 LRU 重播 N 次 warm-up，算 probe 的 interior 在不在 cache。這個做法偏保守，因為窗口之外的舊頁也佔著 LRU 的位置。

結果（10 個 seed，每個位置都當一次 probe；C=450 與 C=483 的結果相同，表示 pager 容量不是瓶頸）：

| workload | key 範圍 | 碰到的第二層頁 | N=1 | N=10 | N=100 | N=1000 |
|---|---|---|---|---|---|---|
| A（Zipfian） | 1–100,000 | 9/50 | 0.127 | 0.723 | 0.998 | 1.000 |
| B（uniform） | 1–100,000 | 9/50 | 0.120 | 0.718 | 0.998 | 1.000 |
| C（high-key） | 590,000–609,999 | 1/50 | 1.000 | 1.000 | 1.000 | 1.000 |

表中數字是 probe 的第二層頁命中率。root 的命中率在 N ≥ 1 時一律是 1.000。

登記的 run 實際用到的逐筆預測（`R1a_probe_predictions.out`）：在 N=1000 與 N=100 時，A、B、C 都是 10/10 個 seed 預測 interior hit；N=10 時 A、B 是 8/10；N=1 時 A、B 是 1/10，C 是 10/10；N=0 時全部是 0/10。

**登記**：
- **主要 N = 1000，也是唯一用來判定的 N。** 模擬在 N=100 時已達 0.998，所有 seed 在 N=1000 都是 1.000，1000 留了 10 倍的餘裕。
- **事先登記的掃描**：N ∈ {0, 1, 10, 100, 1000}。N=0 是有效性控制，其餘只做描述。
- **N 不得在看到資料後調整。**

## 樣本與有效樣本數

每個 workload（A、B、C）× 10 個 workload instance（seed 1–10）× 每個 instance 5 個 rep，B、C 兩組都跑。掃描的其他 N 每個 instance 只跑 1 個 rep。

**主要指標的有效樣本數是 10（每個 workload 10 個 instance），不是 50。** 同一個 instance 的 5 個 rep 是同一個 probe 的重複量測：key 相同、warm-up 相同、預測也相同，彼此並不獨立。5 個 rep 用來檢查量測是否穩定：同一格的 5 個 rep 結果不同，本身就是要回報的不一致。bootstrap 以 instance 為單位重抽；每個 instance 的值是它 5 個 rep 中 interior hit 的比例。

## 預測（先於資料寫下）

依 pcache1 的機制（見 `notes/r1-why.md`）加上逐筆模擬，**我預測結果 I**：在 N=1000 時，三個 workload 的 30 個 instance 都會是 interior hit。這份 prereg 的價值在於用量測取代推理，讓審稿人看得到。

## 判定規則

每個 workload 分開判定，只用 N=1000。p = 各 instance 的 interior hit 比例的平均；95% CI 用 percentile bootstrap，以 instance 為單位（n=10）重抽 10,000 次。

| 結果 | 條件 | 理由 |
|---|---|---|
| **I：interior 在 pager** | CI 下界 ≥ 0.95 | 模擬預測 10/10；低於 0.95 代表機制和我們的理解不同，應先查原因，而不是宣稱結果 |
| **II：interior 不在 pager** | CI 上界 ≤ 0.50 | 過半數的第一個查詢拿不到 interior，這個 state 在預設設定下也常見 |
| **未定** | 其他情況 | 照實回報，不追加 run，由 PI 決定 |

如果 10 個 instance 全都是 1，bootstrap CI 會退化成 [1, 1]。這種情況照實回報，並註明 n=10。

## 兩種結果各自對論文的影響

**論文只能引用有登記判定的 N（N=1000）。** N ∈ {1, 10, 100} 的掃描結果只能當描述性資料放在 artifact 或附錄，不能寫成「只要查過 X 次以上」這類主張。

- **結果 I（預測的結果）**：
  - 論文可以寫：在 SQLite 預設設定、swap=0 的條件下，存活的 process 在同一個 connection 上做過 1,000 次 lookup 之後清掉 OS page cache，第一個查詢路徑上的 interior 全部由 pager 供應；OS page cache 冷不冷，碰不到 interior。
  - `main.tex:136` 的 "a surviving 128 MB environment keeps a live handle over a partially cold file" 要加上限定：那個情況下冷掉的是 leaf，不是 interior，除非應用自己設了 `cache_size=0`（或很小）、pager 的記憶體被回收，或 process 重開。
  - 論文的 state 要改寫成「何時存在」：(a) fresh environment，handle 在 init 打開、檔案從沒被讀過，這時 pager 也是空的；(b) 使用 mmap 且不留 pager cache 的應用設定；(c) 有 swap、pager 會被換出的平台（本實驗沒測）。
  - 依護欄第 5 條，改寫範圍由 PI 決定，agent 不繼續調參。
  - Table 的 no-prefetch baseline 加一列 B 組數字。
- **結果 II**：
  - 在 N=1000 下，預設設定的 interior 也不在 pager，現行 harness 的設定不是製造出這個 state 的原因。
  - Table 加一列 B 組數字，§2.1 寫明 `cache_size=0` 加 mmap 是量測上與預設行為等價的設定，並引用本實驗。
  - 這個結果會和逐筆模擬大量不一致，論文發表前要把原因查清楚，寫進 artifact。
- **未定**：照實寫出比例、CI 與不一致的筆數，由 PI 決定論文怎麼寫。

## 完成條件（依護欄第 2 條：不寫結果方向）

- 所有事先登記的 run 都跑完，或作廢並記錄原因。
- 原始資料存在 `results/<date>-<git-sha>-<config-hash>/`。
- 逐筆一致性已回報，每一筆不一致都附上調查結果。
- 依上表判定每個 workload，並把結果（包括作廢率）寫進回報。

## 執行前需要的工作（未實作；依護欄第 4 條要先過 interrogate、blast-radius，以及舊設定小規模重跑落在原 CI 內）

- harness 新增 `--cache-size N`，預設 0，保持 F1 不變。
- `--mmap-size 0` 可以明確指定，不能再被改成檔案大小（`benchmark_harness.c:1357`）。
- 新增 `--pre-cold-ops N`。
- probe 前後記錄 `sqlite3_db_status`。
- probe 期間的 `xRead` 追蹤：包一層 unix VFS shim，記錄 offset 與長度。
- **B 組 cold gate 用的 mmap**：B 組的 SQLite 不做 mmap，所以 cold gate 與 residency 的 mincore，必須用 harness 另外對 DB 做的 mapping。現行程式碼已經無條件做了這個 mapping（`benchmark_harness.c:498`，`mmap(NULL, file_size, PROT_READ, MAP_SHARED, fd, 0)`，與 `PRAGMA mmap_size` 無關）。要做的是驗證：在 `mmap_size=0` 下這個 mapping 仍然存在；mincore 讀到的確實是 OS page cache；而且它不會讀到任何頁，也就是不會替 SQLite 把頁讀進來。
- `scripts/bench_lock.sh`（flock，`taskset -c 8-15`）。harness 的 `--cpu` 要改在 8–15 之間，登記為 10；目前 `run_experiment.py` 的預設 `--cpu 2` 在這個遮罩下會失敗。跑測期間 agent 只等待。

## 時數

每個 run 約 1.5 s（現行 verify 實測：一個 cell 6 次量測約 9 s）。主要部分 3 × 10 × 5 × 2 組 = 300 run；掃描 3 × 10 × 4 個 N × 1 × 2 組 = 240 run。合計約 540 run，約 15 分鐘。

## 範圍外

- 有 swap 的平台。
- 寫入型 workload：寫入會改 change counter，SQLite 會丟掉 pager cache，那是另一個 state。
- 多 process。
- R1b 的自然壓力。
