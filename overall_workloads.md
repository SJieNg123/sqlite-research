# Overall Results — Workload 説明

這個檔案說明 repo 裡**現階段實際使用**的 workload，以及每個 workload 對應到哪個實驗、想模擬什麼情境。

所有 workload 都跑在同一個 reference DB 上 (`testdb_builder.py` 產生的
`items(id PK, k1, k2, payload BLOB(100))`，**600,000 rows**，~102 MiB，26,331 ×
4 KB pages，其中 92 個 interior pages)，這樣不同 workload 的結果可以橫向比較。

Workload 格式（`benchmark_harness` 讀的）每行一個 op：
```
read <id>
update <id>
insert <id>
scan <id> <len>
readmodifywrite <id>
```

---

## Workload A — Zipfian Point Read（YCSB-C 風格）

**檔案：** [benchmark_harness/workloads/workloadc.txt](benchmark_harness/workloads/workloadc.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [8, 99997]（只打 DB 前 1/6 的 id 區段）
**分佈：** 強 Zipfian skew
- 100,000 次查詢只觸及 **23,253 個 unique key**（76% 是 repeat query）
- **Top 100 個熱 key 吃掉 42.3% 的流量**
- 最熱的單一 key (`id=74406`) 被查 **7,752 次**（單 key 佔總流量 7.75%）

**模擬什麼：** 真實 App 的「熱資料反覆被打」情境 — 使用者常開的聯絡人、最近瀏覽
的相簿、首頁那幾筆 item。少數熱 key 把對應 leaf page 撐成熱頁，**leaf 自然會
warm；唯一還是 cold 的是 interior page**。所以這個 workload 是 prefetch 的最佳
舞台，會放大 interior prefetch 的效益。

**用在哪：**
- `prefetch_vacuum/` 第 9–11 週的全部實驗（baseline / range / perpage / layers N）
- `layout_rewriter/` 的 type-aware vacuum 端到端驗證

**為什麼這個 workload 會給「-54%」、「-69%」這種看起來很漂亮的數字：** 因為
冷啟動成本被拆成「interior fault + leaf fault + CPU」，Zipfian 下 leaf 部分
被反覆查詢拉進 cache，**剩下的瓶頸只有 interior**，prefetch 一解就見效。

---

## Workload B — Uniform Random Point Read

**檔案：** [benchmark_harness/workloads/workload_uniform.txt](benchmark_harness/workloads/workload_uniform.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [1, 99999]（同 Workload A 的 1/6 區段）
**分佈：** 均勻
- 100,000 次查詢觸及 **63,138 個 unique key**（多數查詢是新的）
- 最熱的 key 也只被查 7–8 次
- 每 10k id 區段平均 ~10,000 次（誤差 < 5%）

**模擬什麼：** 沒有熱點的 OLTP/批次掃描情境，例如「按 id 一筆筆檢查」、隨機
sampling、爬蟲式存取。**每筆 query 都打到沒看過的 leaf**，leaf fault 不可避免。

**用在哪：** 對照組。當 Workload A 量出來「prefetch 省了 54%」，我們需要
Workload B 來回答「這效益是不是只在熱點工作負載下才有意義」 — 答案是 prefetch
仍然有效，但比例會被「無法被解決的 leaf fault」攤薄（章節 8 的 prefetch_churn
結果就是這個現象）。

---

## Workload C — High-key Uniform Read（churn 後段查詢）

**檔案：** [prefetch_churn/workloads/page_churn_benchmark_high.txt](prefetch_churn/workloads/page_churn_benchmark_high.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [590000, 609999]（**只打 DB 末段 20k id**，含 churn 後新增的 id）
**分佈：** 均勻覆蓋這 20k 個 id（剛好每個 id 平均被打 5 次）

**模擬什麼：** 「新加入的資料馬上被讀取」— 例如剛收到的訊息、剛拍的照片、剛
push 的 commit。**重點不是熱點，而是 id 落在哪個 file region**。Churn 過程持續
INSERT 會把新資料放在檔尾，這個 workload 就在量「檔尾新資料的冷啟動 latency
怎麼隨 churn 累積而漂移」。

**用在哪：** `prefetch_churn/` 的 10 個 checkpoint，每個 checkpoint 之間先用
Workload D 製造寫入壓力，然後 drop cache，再跑這個 workload 量 cold-start
latency。

**為什麼選 high-key 而不是低 key：** 因為 prefetch_churn 想觀察 layout 隨寫入
漂移的效果，而新 interior page 都會配在檔尾（id 590k+），打這段最能看到 layout
惡化的影響。

---

## Workload D — Mixed Write-heavy Churn Generator

**檔案：** [prefetch_churn/workloads/page_churn_write.txt](prefetch_churn/workloads/page_churn_write.txt)
**規模：** 100,000 ops，混合操作
**Op 組成：**

| op | 次數 | 佔比 |
|---|---:|---:|
| `update` | 30,000 | 30% |
| `insert` | 20,000 | 20% |
| `read` | 20,000 | 20% |
| `readmodifywrite` | 20,000 | 20% |
| `scan <len>` | 10,000 | 10% |

**Key 行為：**
- `insert` 從 id = 600,001 開始往上長（DB 原本 600k 筆，所以每 batch 都是真
  新資料、不是 overwrite）
- `update` / `read` / `rmw` / `scan` 都打既有 id 範圍

**模擬什麼：** **不是用來測 latency 的**。它是 churn generator — 製造大量
INSERT/UPDATE/DELETE 的寫入壓力，讓 SQLite freelist 重新分配、interior pages
分裂、layout 隨時間漂移。

**用在哪：** `prefetch_churn/` 的 checkpoint 之間。每個 checkpoint 之間執行
5,000 ops 的這個 workload（取前 5,000 行），跑 10 次累積 50,000 ops。然後在每個
checkpoint 用 Workload C 量 cold-start latency，看「prefetch 在被 churn 過的
layout 上還剩多少效益」。

---

## Workload 與實驗的對照表

| 實驗 | 用的 workload | 想回答的問題 |
|---|---|---|
| `prefetch_vacuum/` (Week 9–11) | A (Zipfian) | Prefetch interior pages 在熱點 workload 下能省多少？甜蜜點是 N=幾個 page？|
| `layout_rewriter/` (type-aware vacuum 驗證) | A (Zipfian) | 把 interior 重排到檔頭，能不能救回 prefetch 效益？|
| `prefetch_churn/` 量測 | C (high-key uniform) | Layout 隨 churn 漂移後，prefetch 效益怎麼變？|
| `prefetch_churn/` churn 生成 | D (mixed write) | 製造真實的 layout 漂移壓力（不量 latency）|
| `multiprocess/` | 不用 workload（只測 residency / RSS）| MAP_SHARED 是否真的跨 process 共享 page cache？|
| Workload B (uniform read) | — | 對照用：證明「prefetch 效益」不是只在熱點下才出現的假象 |

---

## 為什麼需要這四種 workload，而不是只用一個

不同 workload 拆解 cold-start latency 的不同 component，缺一不可：

```
[Interior page fault]  +  [Leaf page fault]  +  [SQLite CPU]
        ↑                          ↑
   prefetch 能解決              prefetch 解決不了
                                （workload-dependent）
```

- **Workload A (Zipfian)** 把「leaf fault」這項壓低（leaf 自然熱），讓 interior
  fault 成為唯一瓶頸 → 量出 prefetch 的**上界效益**
- **Workload B (uniform)** 讓「leaf fault」這項變最大，prefetch 只能解決剩下
  的 interior 部分 → 量出 prefetch 的**下界效益**
- **Workload C (high-key uniform)** 同 B 的分佈但鎖定檔尾，跟 Workload D 配合 →
  量「layout 漂移」隨時間的影響
- **Workload D** 不為了 latency 而存在，純粹是製造寫入歷史，讓 layout 偏離
  testdb_builder 剛建好的乾淨狀態

---

## 已知缺口（README 第 9 章列的 TODO）

- **Zipfian「low-key hotspot」變體**：目前的 Workload A 雖然 Zipfian，但熱點
  分佈在 8..99k 整個區段裡。若把熱點壓到 [1, 1000] 這種極窄區，prefetch 效益
  會跟 [99k, 100k] 完全不同（前者 ≈ append-only churn pattern，後者 ≈ random
  churn pattern）。**這兩個變體還沒測**。
- **N 在 churned DB 上的曲線**：`prefetch_churn` 只用了 N=5；缺 N=1/10/20
  在 Workload C 上的對照曲線。
