# R1b：C 組（mmap 加 cache_size=0）在 cgroup 自然記憶體壓力下的 reclaim

> **已登記。** 判定規則的數字依 2026-11-11 的決定凍結，理由附在旁邊。依護欄第 1 條，本檔 commit 之後才能跑；commit 後不再修改，需要變更時另開新的 prereg 並寫明原因。
> 起草：2026-11-11，同日修訂。repo rev `ae29344`；DB `pipeline/preparation/layout_rewriter/runs/test.db`。S_db = 107,851,776 B（102.86 MiB，26,331 頁）。

## 要回答的問題

在現行 harness 設定（`mmap_size=檔案大小`、`cache_size=0`、保留 connection）下，量測時不用 `drop_caches`，改由 cgroup 內的競爭記憶體造成自然 reclaim。到了下一次請求的第一個查詢時，root、interior、leaf 三層各自還有多少頁留在 page cache？之後的 recovery（第一個查詢的 latency）又如何？

C 組的 pager 不留頁（`cache_size=0`，見 `notes/r1-why.md`），所以 page cache 的 residency 就等於查詢能不能不碰 disk。B 組不在這份的範圍內：swap=0 時它的 pager 必然存活，見 R1a。

## 頁的分層（從 `sqlite_schema.rootpage` 與 B-tree 結構取得）

`prereg/design/btree_shape.out`：

| 層 | 頁 | 數量 |
|---|---|---|
| root | `sqlite_schema.rootpage`：2（items）、3（idx_items_k1）、4（idx_items_k2） | 3 |
| interior（非 root） | items 第二層 50 頁、兩個 index 的第二層 19 + 20 頁 | 89 |
| leaf | 其餘頁，含 page 1 | 26,239 |

所有 workload 都只做 rowid 的 point read，所以實際會碰到的只有 items 這棵樹。每層再分「路徑上」與「路徑外」：
- **A、B**（key 1–100,000）：路徑上的 interior 是 page 2 加 9 個第二層頁，路徑上的 leaf 約 3,316 頁（約 13.0 MiB）。
- **C**（key 590,000–609,999）：路徑上的 interior 是 page 2 加 1 個第二層頁，leaf 約 334 頁（約 1.3 MiB）。

數字來自 `prereg/design/pager_lru_sim.out`，是 10 個 seed 的聯集。實跑時，路徑上的頁集合以該 run 的 seed 串流重新計算。

## 壓力等級（相對於 DB 大小，commit 時凍結）

file 頁預算 = r × S_db，r ∈ {1.0, 0.5, 0.25, 0.1}：

| r | 預算 | 與 A、B 路徑上 working set（約 13 MiB）比較 |
|---|---|---|
| 1.0 | 102.9 MiB | 遠大於 |
| 0.5 | 51.4 MiB | 大於 |
| 0.25 | 25.7 MiB | 大於 |
| 0.1 | 10.3 MiB | **小於**，leaf 必然放不下 |

另外加一個成對控制組 **r = ∞**，用來滿足 paired baseline 的規定。

r = 0.1 正式加入，是因為前三個等級都比路徑上的 working set 大，只用它們幾乎無法對 interior 造成壓力。**這四個等級在 commit 時凍結，之後不再往下加等級**，不能為了「找到」會變冷的條件而追加。

## 兩組壓力（arm）

兩組都用同一個 anon 競爭者來設定預算，差別在於 idle 期間是什麼在跟 DB 的頁競爭：

- **stream 組**：file streamer 用 `read()` 循序讀 scratch file，每頁只讀一次。跑 A、B、C 的所有等級。
- **hot 組**：hot competitor 對另一個 scratch file 做 mmap，在 idle 期間以固定速率反覆存取。跑 A 的所有等級。

加 hot 組的原因：MGLRU 對經由 file descriptor 讀進來、只用一次的頁，本來就會優先回收；而 interior 是經由 mmap、頻繁存取的頁。只有 stream 組時，被逐出的幾乎必然是 streamer 自己的頁，結果 S 等於由設計決定。FaaS 真實的鄰居（其他 action 的程式碼與 mmap 的資料）也是 mapped 的熱頁，hot 組測的是這種壓力。

## 記憶體設定

- transient scope：`systemd-run --user --scope -p MemoryMax=<M> -p MemorySwapMax=0`，與現行 `--mem-limit` 的機制相同。swap=0 與 Lambda 一致；在 swap=0 下，anon 頁回收不了，競爭者佔用的記憶體會全部轉成 file 頁的壓力。
- `MemoryMax = M_base + S_db + 16 MiB`：
  - M_base 是 harness 和競爭者都啟動、還沒讀任何 DB 頁時，scope 的 `memory.current`。
  - 多留 16 MiB 的餘裕，是為了讓 init 階段的整檔讀取不被截斷。
- anon 競爭者在第一次 idle 時，把 anon 增加到 `A_comp = (1 − r) × S_db + 16 MiB`，剩下給 file 頁的就是 r × S_db。之後一直持有到 probe，沒有任何記憶體存取。
- streamer 與 hot competitor 的 scratch file 頁也算在同一個 file 預算裡。

## r = ∞ 控制組的行為

r = ∞ 時：
- **不設 MemoryMax**。
- **anon 競爭者、file streamer、hot competitor 都不啟動**：r = ∞ 時 streamer 的速率公式沒有定義，所以明確規定不啟動。
- setup、init、K 次 invocation、idle 長度與 probe 都和其他等級相同。

stream 組與 hot 組共用 A 的 r = ∞ 控制組。

## memcg 計費（避免假的存活）

page cache 的頁算在第一個讀到它的 cgroup 名下。如果 DB 頁先前已經被別的 cgroup 讀進來，在 scope 裡施加壓力也逐不掉它們。因此：
- **setup**：scope 建立之前跑一次 `drop_caches`，DB 和兩個 scratch file 的頁都會被清掉。這只是 setup，不是量測；量測期間不再呼叫 `drop_caches`。
- **計費檢查**：init 讀完之後，scope 的 `memory.stat` `file` 必須 ≥ 0.9 × S_db，否則該 run 作廢，代表頁算到別處去了。

## 每個 run 的流程

1. setup：做一次 `drop_caches`，建立 scope，啟動 harness（開啟 DB 並做 mmap，`before-cold`），以及該組的競爭者。競爭者先閒置。記錄 M_base。
2. **init**：透過 harness 自己的 mapping 循序讀一次整個 DB。這對應 Lambda probe 的「environment 第一次被呼叫時讀整個檔」。
3. **K = 5 次 invocation**。每次先跑 Q = 200 個 workload op（取自同一個 seed 串流），再 idle T = 60 s：
   - 第一次 idle 時，anon 競爭者以 32 MiB/s 增加到 A_comp，之後一直持有。
   - stream 組：streamer 在每次 idle 讀 1 × r × S_db。
   - hot 組：hot competitor 在每次 idle 以下面的速率存取它的 mapping。
   - streamer 與 hot competitor 都在 idle 結束前 2 s 停止，讓 I/O 與 L3 的干擾靜下來。
   - 每次 idle 結束時，記錄 `memory.stat` 和分層 residency（mincore）。
4. **probe**（第 6 次 invocation 的第一個 op）：
   - op 之前：記錄分層 residency 和 `memory.stat`。
   - 量測 first-query latency 和 majflt。
   - 跑完這次 invocation 的 Q 個 op，量 e2e。
   - 之後再記錄一次分層 residency，這就是 recovery。

## 綁核（與 `scripts/bench_lock.sh` 一致）

`lscpu -e`（2026-11-11 確認；AMD Ryzen 9 9950X，2 個 CCD，SMT 開啟）：
- CCD0：CPU 0–7，L3 #0；它們的 SMT 兄弟是 CPU 16–23。
- CCD1：CPU 8–15，L3 #1；它們的 SMT 兄弟是 CPU 24–31。

`bench_lock.sh` 用 `taskset -c 8-15`，也就是 CCD1 每個實體核的第一個 thread。`systemd-run --scope` 會繼承這個 affinity 遮罩，所以每個 process 都必須選在 8–15 之內：

| process | CPU | 實體核 |
|---|---|---|
| harness（`--cpu 10`） | 10 | core 10 |
| anon 競爭者 | 12 | core 12 |
| file streamer（stream 組）或 hot competitor（hot 組），同一個 run 只會有其中一個 | 14 | core 14 |

三個 process 各在不同的實體核上，SMT 兄弟（26、28、30）在遮罩外，不會被用到。它們仍然共用 CCD1 的 L3，這會影響 first-query latency（次要指標）；因此競爭者在 probe 前 2 s 停止，而 anon 競爭者在增加完之後就不再存取記憶體。剩下的 L3 影響照實回報。

目前 `run_experiment.py` 的預設 `--cpu 2` 在這個遮罩下會失敗，必須改成 10。跑測期間 agent 只等待。

## 競爭者參數與理由

| 參數 | 登記值 | 理由 |
|---|---|---|
| anon 增加速率 | 32 MiB/s，敏感度用 512 MiB/s | 0.1x 時要增加約 109 MiB，約 3.4 s，遠短於 60 s 的 idle。慢速增加讓 reclaim 逐步發生，依 LRU 的老化順序挑頁；快速增加會觸發 direct reclaim，留作對照。 |
| anon 持有 | 到 probe 都不釋放，也不再存取 | 在 swap=0 下，它就是固定的預算縮減，對應 runtime 或其他 tenant 佔著的記憶體。 |
| file streamer（stream 組） | 每個 idle 讀 1 × r × S_db，敏感度用 4× | 用預算的倍數表示，讓各等級的換手程度一致。 |
| **hot competitor 的檔案大小 H**（hot 組） | **0.5 × S_db = 51.4 MiB（13,166 頁），所有等級都固定** | 鄰居的大小不會因為我們的預算而改變，所以固定。H 加上 A 路徑上的 working set 約 64 MiB：r = 1.0 時放得下，0.5x 以下放不下，這樣四個等級會形成一個劑量梯度。 |
| **hot competitor 的存取方式** | mmap（`PROT_READ, MAP_SHARED`），每頁讀 1 byte，頁的順序均勻隨機 | 和 SQLite 讀 interior 的路徑同一類（page table 的 accessed bit），不受 use-once 優先回收的影響。 |
| **hot competitor 的速率** | **500 頁/s（約 2 MiB/s）**，只在 idle 期間存取 | 60 s 的 idle 內，每頁平均被碰約 2.3 次，至少兩次存取讓它成為「熱」頁。DB 的 interior 最後一次被碰是在 invocation 期間（idle 之前），所以到了 probe 時，競爭者的頁比 interior 更新近，對 interior 是嚴格的測試。在低預算下競爭者會自己 thrash，速率上限也讓它的 disk I/O 控制在約 2 MiB/s，不會讓 NVMe 的爭用失控。 |
| idle T | 60 s，敏感度用 300 s | Lambda probe 顯示 environment 在 1 到 5 分鐘的 idle 之間會存活（`main.tex:136`），論文也是用 1 和 5 分鐘量的。 |
| invocation 數 K | 5 | 讓頁在 probe 之前經過多次「讀取、閒置」的循環，MGLRU 的 generation 才有機會分層。 |
| 每次 op 數 Q | 200 | 依 R1a 的模擬，100 個 op 就能讓路徑上的第二層頁覆蓋率達到 0.998。200 讓每次 invocation 都碰過全部路徑上的 interior，這是「存活且有在服務」的 environment。 |

## 每個 run 都要記錄

- `memory.stat`：`file`（同時換算成頁數，bytes / 4096）、`file_mapped`、`active_file`、`inactive_file`、`anon`、`workingset_refault_file`、`workingset_activate_file`、`pgscan`、`pgsteal`。
- `memory.events`：`high`、`max`、`oom`、`oom_kill`。
- 記錄時間點：M_base、init 後、每次 idle 結束、probe 前、probe 後。
- 分層 residency：root、路徑上 interior、路徑外 interior、路徑上 leaf、路徑外 leaf，各自的 resident 頁數與總頁數。hot 組另外記錄 hot competitor 檔案的 resident 頁數。
- 環境：kernel、`/sys/kernel/mm/lru_gen/enabled`（目前是 `0x0007`，也就是 MGLRU 開著；`min_ttl_ms=0`）、swappiness、`lscpu -e`，以及 `env.sh` 的那一行輸出。

在 MGLRU 開著的情況下，`active_file` 和 `inactive_file` 只是近似值，只做描述用。

## 指標

- **主要指標**：probe 前，**路徑上 interior**（page 2 加路徑上的第二層頁）的 resident 比例。每個 run 一個值。
- **次要指標（只描述）**：
  - root 與其他分層的 residency。
  - probe 的 first-query latency 和 e2e，與 r = ∞ 按 instance 成對相減，報 bootstrap CI。
  - recovery 後的 residency。
  - refault 與 activate 的計數。

## 有效性檢查（不過就作廢該 run，並回報作廢率）

- r = ∞ 控制組的路徑上 interior residency ≥ 0.95，否則就是 setup 漏了。
- memcg 計費檢查通過（見上）。
- 沒有發生 `oom_kill`；被 kill 的 run 照實回報。
- 唯讀：DB 的大小與 mtime 在 run 前後必須相同。
- 每個 process 的實際 CPU 與上表一致，以 `/proc/<pid>/status` 的 `Cpus_allowed_list` 記錄。

## 預測（先於資料寫下）

- **stream 組**：
  - 在 1.0x、0.5x、0.25x 下，A、B、C 路徑上的 working set 都放得下預算，而 page 2 每個 op 都會碰到、路徑上的第二層頁大約每 9 個 op 碰一次（A、B）。我預測這三個等級都判 S。
  - 0.1x 下 A、B 的 leaf 放不下，但 interior 只有 10 頁，而且最常被碰到；我預測 interior 仍判 S，leaf 的 residency 會明顯下降。
  - 整體預測：stream 組在 A、B、C 都是「沒有」變冷的等級。
- **hot 組（A）**：不確定性比較高。
  - 我預測 1.0x 判 S。
  - 0.25x 與 0.1x 判 E：idle 期間競爭者的頁比 interior 更新近，又都是 mapped 頁。
  - 0.5x 無法有把握地預測。
  - 整體預測：變冷的最高等級是 0.25x 或 0.5x。
  - 這是在沒有實測過 MGLRU 細節行為的情況下所做的預測。
- 預測與 Lambda 的觀察（每次呼叫都會再讀的頁，在所有記憶體大小下都留著，`main.tex:136`）並不衝突：Lambda probe 的鄰居壓力是什麼樣子並不知道。

## 判定規則

**每個 (組, workload, 等級) 各自判定 S、E 或未定**，不跨等級合併。主要指標以 instance 為單位（n=10）做 percentile bootstrap（10,000 次），取 95% CI。

| 判定 | 條件 | 理由 |
|---|---|---|
| **S：interior 存活** | CI 下界 ≥ 0.90 | A、B 路徑上 interior 有 10 頁，0.90 大約等於平均最多少一頁 |
| **E：interior 變冷** | CI 上界 ≤ 0.50 | 過半數路徑上的 interior 不在了，第一個查詢必然要等 interior 的 miss |
| **未定** | 其他情況 | 照實回報，不追加 run |

**整體結論（每個組、每個 workload 一句）：變冷的最高等級，或沒有。**
- 等級依預算由大到小排：1.0 > 0.5 > 0.25 > 0.1。「變冷的最高等級」是判 E 的等級中 r 最大的那一個，也就是從這個預算開始，interior 在自然壓力下會變冷。
- 沒有任何等級判 E：結論是「沒有」。
- 判 E 的等級上方如果有未定的等級，照實寫出，例如「變冷的最高等級是 0.25x；0.5x 未定」。
- 如果不單調，例如 0.5x 判 E 但 0.25x 判 S，照實列出每個等級的判定並標明不單調，不做平滑或重新詮釋。

**例子**：只有 0.1x 判 E，0.25x、0.5x、1.0x 都判 S，結論就是「變冷的最高等級是 0.1x（預算 10.3 MiB）」。

## 兩種結果各自對論文的影響

論文要寫出的正是這個邊界：這個 state 在多大的預算之下、面對哪一種鄰居時才會出現。

- **兩組都是「沒有」**：
  - 在四個預算等級（包括低於 working set 的 0.1x）下，不論鄰居是只讀一次的串流還是熱的 mapped 頁，自然 reclaim 都不會讓存活 process 的 interior 變冷；冷掉的是 leaf 和沒在用的頁。
  - 論文目前依靠 `drop_caches` 造出「interior 也冷」的 state，在存活的 environment 中找不到自然的對應；這正是審稿人的疑慮。
  - 依護欄第 5 條，論文改寫成「這個 state 何時存在」：fresh environment（handle 在 init 打開、檔案從沒被讀過），或是 process、容器重開但 page cache 也被清掉的情況。interior prefetch 的價值要放在這些情境裡談。
  - 改寫範圍由 PI 決定，agent 不調整等級或參數來找出「會變冷」的條件。
- **stream 組「沒有」，hot 組有一個變冷的最高等級 X**：
  - interior 撐得過只讀一次的串流，但撐不過預算 ≤ X 時熱的 mapped 鄰居。
  - 論文寫明：這個 state 在「鄰居的熱 working set 加上我們的 working set，超過預算 X」時出現，並把 X 與 H 寫出來。
  - 自然壓力下 prefetch 策略的比較另寫 prereg（R1c），只在 hot 組、≤ X 的等級做。
- **stream 組本身就有變冷的等級**：
  - 連只讀一次的串流都足以讓 interior 變冷。harness 的 `drop_caches` 重現的是一個實際會發生的 state；論文加入分三層的自然壓力 residency 表，並在 §3.4 說明 `drop_caches` 是這個 state 的可控代理。
  - 接著另寫 R1c。
- **未定或不單調**：照實寫出每個等級的判定，由 PI 決定論文怎麼寫。

## 完成條件（依護欄第 2 條：不寫結果方向）

- 所有事先登記的 run 都跑完，或作廢並記錄原因。
- 原始資料，包括每個時間點的 `memory.stat` 與分層 residency，都存在 `results/<date>-<git-sha>-<config-hash>/`。
- 依上表判定每個 (組, workload, 等級)，寫出每個組、每個 workload 的整體結論，並把作廢率與 OOM 次數寫進回報。

## 時數

每個 run 約 5.5 分鐘：setup 約 20 s，加上 5 次 invocation 各約 60 s，加上 init 與 probe。

| 部分 | 計算 | run 數 | 時數 |
|---|---|---|---|
| stream 組主要 | A、B、C × {1.0, 0.5, 0.25, 0.1, ∞} × 10 | 150 | 13.8 h |
| hot 組主要 | A × {1.0, 0.5, 0.25, 0.1} × 10（共用 A 的 r = ∞） | 40 | 3.7 h |
| 敏感度：T = 300 s | stream 組，A，0.1x × 10；每個 run 約 25.5 分鐘 | 10 | 4.3 h |
| 敏感度：anon 512 MiB/s | stream 組，A，0.1x × 10 | 10 | 0.9 h |
| 敏感度：streamer 4× | stream 組，A，0.1x × 10 | 10 | 0.9 h |
| **合計** | | **220** | **約 23.6 h** |

敏感度分析只跑最低等級，也就是 0.1x；結果只做描述，不做判定。R1a 另外約 15 分鐘。

## 執行前需要的工作（未實作；依護欄第 4 條要先過 interrogate、blast-radius，以及舊設定小規模重跑落在原 CI 內）

- harness 新增 invocation 與 idle 排程模式：init 整檔讀取、K 次 invocation，每次 Q 個 op，量測期間不呼叫 `drop_caches`。
- 每個時間點都做分層 residency（mincore，對照 classify CSV 與 rootpage 集合）。
- 三支小工具：anon 競爭者、file streamer、hot competitor，都要能設定速率、大小與綁核。
- `memory.stat` 與 `memory.events` 的取樣。
- scope 的建立與 M_base 的量測，以及 memcg 計費檢查。
- `scripts/bench_lock.sh`（flock，`taskset -c 8-15`），以及 harness 的 `--cpu 10`。

## 範圍外

- 有 swap 的平台。
- B 組（見 R1a）。
- 寫入型 workload。
- 多 process 共用同一份 DB。
- 自然壓力下 prefetch 策略之間的比較（R1c 的範圍）。
