# Overall Workloads — Workload 說明

> **最後更新：2026-07-30**

本檔描述 repo 目前使用的**每一個 workload**：它模擬什麼情境、分布指紋、以及在實驗中的角色。命名以 **canonical / display name** 為準（單一事實來源 `config/workloads.json`，經 `config/workload_registry.py` 解析）。measurement 權威全表見 [overall_results.md](overall_results.md)、策略結果見 [overall_strategies.md](overall_strategies.md)。

所有 controlled workload 跑在同一 reference DB（`items(id PK, k1, k2, payload BLOB(100))`，600,000 rows）。

---

## Reference DB 結構

**Schema：** `items(id INTEGER PRIMARY KEY, k1 INTEGER, k2 INTEGER, payload BLOB(100))` + secondary index `idx_items_k1k2(k1,k2)`。

| 項目 | 數值（`orig`，實測 2026-07-30）|
|---|---|
| `page_size` | 4096 bytes（SQLite 預設）|
| row 數 | 600,000（max id = 600000）|
| page 數 | 26,331 |
| DB 大小 | 107,851,776 bytes（~102.86 MiB）|
| **Interior pages** | **92（0.35%）** = 51 table interior + 41 index interior |
| Leaf pages | 26,239（99.65%）|

**核心洞見：** interior 只占 0.35%（368 KB），但**每筆 query 都得 root→leaf 沿路經過 interior**；cold start 時這 92 頁每個觸發一次 4 KB random I/O（NVMe ~50–100 µs）。interior 是每條 query path 的必經骨架，是最划算的 prefetch 目標；leaf（占 99.65%）只在有頻率訊號時載最 hot 的少數。**每個 cold-start trial 前均 drop page cache，首查時 interior 與 leaf 皆 cold。**

### Layout 變體（同資料、不同頁面排列）

interior 散佈 scatter score = interior 平均頁號的正規化位置（0 = 全擠檔頭、≈1 = uniform 散佈）：

| Layout | DB key | 檔案大小 | interior 位置 | scatter |
|---|---|---|---|---|
| orig | `orig` | 102.86 MiB | page 2..26,007 | **0.96**（散佈全檔）|
| VACUUM | `vacuum` | 100.05 MiB（85 interior）| 類似 orig | 1.13（更散）|
| type-aware | `ta` | 102.86 MiB | page 2..93（連續）| **0.0001**（幾乎完美 clustering）|

> VACUUM 縮小的 718 page **全來自 secondary index**（`idx_items_k1k2` 亂序建、頁只塞 60–90% 滿，VACUUM 按 key 排序灌緊）；table 一頁沒少。type-aware 只重排位置不重塞資料，故大小/頁數同 orig。

### Size-scaling 變體

| DB key | row 數 | page 數 | 大小 |
|---|---|---|---|
| `1gb` | 6,000,000 | 263,991 | 1,081,307,136 bytes（~1.01 GiB）|

DB 放大 10×，用來量 interior 骨架槓桿隨規模的變化（size-scaling 結果見 overall_results.md）。

---

## Workload 命名（canonical ↔ 資料層 alias）

paper／figure／本檔一律用 **display name**。下表的短碼是 **immutable results CSV（`results/**` 的 `workload` 欄）的 join key**，資料層凍結、不重寫——列出僅為對照原始資料，**非展示名**（來源：`config/workloads.json`）。

| display name | canonical_id | 資料層 alias | 類別 | 有量 latency？|
|---|---|---|---|---|
| Scattered-Zipf | `read_zipf_scattered_100k` | A | controlled read | ✅ |
| Uniform-100K | `read_uniform_100k` | B | controlled read | ✅ |
| Tail-Mixed | `read_tail_mixed_20k` | C, C_mixed | controlled read | ✅ |
| Tail-Hit | `read_tail_hit_20k` | C_hit | controlled read（對照）| ✅ |
| Concentrated-Zipf | `read_zipf_concentrated_1k` | Z | controlled read（僅圖）| ✅ |
| （headline）YCSB-read | — | YC | real-YCSB 讀取 headline | ✅ |
| Latest-Aging | `py_ycsb_d_latest_aging` | YD | YCSB 重建（aging）| ✅ |
| Short-Scan Aging | `py_ycsb_e_short_scan_aging` | YE | YCSB 重建（aging）| ✅ |
| Mixed-Mutation Churn | `mutation_churn_schedule` | CHURN | mutation schedule | ❌ 不量 latency |

**Workload 格式：** `benchmark_harness` 每行一 op：`read <id>` / `update <id>` / `insert <id>` / `scan <id> <len>` / `readmodifywrite <id>`（op string 格式參照 [YCSB-cpp](https://github.com/ls4154/YCSB-cpp)）。

---

## Controlled read workloads（`gen_workload.py`，Python 產生、有量 latency）

> ⚠️ 這五個是 `workloads/gen_workload.py` 產生的 **Python trace**，複刻 YCSB 的*語意*（Zipf / uniform / tail），**非原生 YCSB trace**。真原生 YCSB 見下方「Real-YCSB」與「原生 YCSB 全套」節。各 10 seeds（Concentrated-Zipf 僅 1 seed，僅供 figure）。

### Scattered-Zipf
- **op-mix：** 100% read。**Key domain：** ids 1..100,000（全在 DB max 600000 內，**0 not-found**）。
- **分布：** scrambled Zipf α=0.99——rank→亂序 permutation，**熱 key 散佈全 key range**。~23k unique；top-1 key ~7.8% 流量、top-100 吃 ~42%。
- **模擬：** 有真實 skew 的寬 working-set（常開熱資料）。skew 把 first-query 機率集中在少數 leaf → 小的 frequency-derived hotset 較可能覆蓋首查 → **targeted prefetch 的最佳舞台**（frequency leaf 有加分）。

### Uniform-100K
- **op-mix：** 100% read。**Key domain：** ids 1..100,000（**0 not-found**）。
- **分布：** uniform random。~63k unique、無自然熱點，最熱 key 也只 7–8 次。
- **模擬：** 無熱點的 OLTP／批次掃描。uniform 把 first-query 機率攤到大量 leaf → 小 leaf hotset 期望覆蓋率低 → **量 targeted prefetch 的下界**（靠 interior skeleton）。

### Tail-Mixed
- **op-mix：** 100% read。**Key range：** ids 590,000..609,999（20,000 unique，每 id ×5），**跨過 DB max id 600000**。
- **分布：** uniform。**hit semantics = MIXED**：上界 609,999 > DB max 600,000 → **~50% not-found**（600,001..609,999 為超範圍負向查詢；seed 1..10 實測皆 ~50,005 hit / ~49,995 miss）。
- **關鍵機制：** hit 與 miss 走**相同的 B+tree 右緣 interior 路徑**；每個 miss 一律下降到**最右葉**（600000 所在葉）再回報不存在 → 該最右葉吸收全部 ~50k miss 流量、成為**壓倒性單一 hot leaf**（key-range 誘發的 right-boundary hotspot），hit 查詢散落頻率相近的多個真葉。
- **模擬：** existence check / tail-boundary lookup。**必標註**：其大效益由 ~50% not-found 的 right-boundary probe 集中驅動，**跨 seed 為雙峰（e2e_warm −55%）、與 footprint-matched `2f_top14` 統計不可分**，非 uniform tail 讀取的普適性質（對照見 Tail-Hit）。

### Tail-Hit — Tail-Mixed 的 pure-hit 對照
- **op-mix：** 100% read。**Key range：** ids 580,001..600,000（20,000 unique，每 id ×5），**全在 DB 範圍內**。
- **分布：** uniform。**hit semantics = pure hit**（max=600000=db max → **0 not-found**，manifest `HIT_ONLY` 硬 assert 把關）。
- **用途：** 同 20k key-space、同 tail-region locality、同 uniform ×5，**唯一差別是把 range 收進 DB 範圍**，移除 not-found 最右葉超熱點。回答「拿掉 not-found 集中後，frequency-aware prefetch 還有效嗎？」
- **結果（orig，10 seeds × 10 reps，warm-process e2e，`2e_K10` 為 tie-break 修正後 `results/c_hit_v2`、其餘 `results/c_hit`）：**

  | strategy | e2e_warm | 這是什麼 |
  |---|---:|---|
  | 2d（interior only）| **−28.5%** [−34.9,−19.6] | interior skeleton |
  | 2f_top14（freq, page tie-break）| **−30.6%** [−37.1,−22.4] | 真實 frequency |
  | learned_markov_14（LOSO held-out）| **−29.0%** [−36.1,−19.4] | held-out |
  | 2e_K10（tie-break 修正後）| **−27.2%** [−34.6,−17.7] | == interior skeleton |
  | 2f_slru | +76.5% | deliver trap |

  → **拿掉 not-found 後，穩健效益是 interior skeleton ~−28%；frequency leaf 相對 interior-only 幾乎不加分**（uniform tail 無真實 leaf 熱點）。完整見 [`results/c_hit/FINDINGS.md`](results/c_hit/FINDINGS.md)。

### Concentrated-Zipf（僅供 figure，1 seed）
- **op-mix：** 100% read。**Key domain：** ids 1..1,000（**0 not-found**）。
- **分布：** Zipf α=0.99 **不 scramble**（rank == key）→ 熱 key 落在低 id、群聚；1000 unique、top-1 key ~13%。
- **用途：** hotspot-location 對照——與 Scattered-Zipf 對比，證明 N-sweep plateau 形狀不隨熱點位置改變。

---

## Real-YCSB headline（原生 YCSB 0.17.0，有量 latency）

### YCSB-read headline（main branch）
- **來源：** 真原生 YCSB 0.17.0 產生器（`workload_fixed/`），**非 `gen_workload.py`**。string key 映射到 dense rowid 1..600000。provenance：`workloads/workload_yc_1.txt.manifest.json`。
- **op-mix：** 100% read，zipfian，`insertorder=hashed`，`recordcount=600000`，`ops=80000`，**notfound=0**。
- **角色：** headline（上摘要、講故事的那組）改用學術界公認標準工具產生，使分布不是手調的。跑通 harness、已接進 registry。

> 這是 main branch 上唯一的原生 YCSB latency workload。完整 17-workload 原生 YCSB 重現在 **speculation branch**（見下節）。

---

## YCSB 重建 — aging（`gen_workload.py`，含寫入、有量 latency）

> ⚠️ **命名：** Latest-Aging / Short-Scan Aging 是 **YCSB-D/E 語意的 deterministic Python 重建**，**不是**官方 YCSB-D/E trace，也**不是**上面「Mixed-Mutation Churn」。兩者含 `insert`（從 600001 起、超過 DB max，使 DB 隨時間 aging），首 op 強制 `read`（供唯讀 TTFQ probe）。各 10 seeds。

### Latest-Aging — read-latest
- **op-mix（seed 1 實測）：** `read` 95,108 + `insert` 4,892（≈95/5）。
- **分布：** `requestdistribution=latest`——讀熱點集中最近插入 key（Zipf α=0.99 對 recency rank、`key = cur_max − zipf_rank`）。reads unique ~37k、57% 落在 >600000 新插入區 → **移動的 hotset**（非平穩）。
- **模擬：** timeline／最新事件——寫入不斷產生新熱 key。壓測 static/history 派預取（A/B/C/Z 靜態熱點沒有的軸）。

### Short-Scan Aging — short-ranges
- **op-mix（seed 1 實測）：** `scan` 94,975 + `insert` 5,024 + `read` 1（≈95/5）。
- **分布：** scan start = scrambled Zipf α=0.99 over [1..600000]（散佈，同 Scattered-Zipf）；scan length uniform [1,100]、mean 50.5——**靜止熱點（平穩）**。
- **模擬：** 短範圍掃描（訊息佇列尾端連續讀）+ 5% 插入 aging。作為 Latest-Aging 的**平穩對照**。

**aging 量測路徑：** 含寫入、不走唯讀 `run`，走 `run_experiment.py aging`。每 checkpoint 用**反映當下 hotspot 的 probe**（隨 insert frontier 移動）對**凍結在 t=0 的 hotset** 量 TTFQ，才測得到「frozen hotset 被移走的 hotspot 拋離」的 decay。**核心結論**：decay 由 hotspot 平穩性決定——Latest-Aging（移動）下 access-frequency 派衰減、structural `layers_92_static` 反超；Short-Scan Aging（平穩）下 frequency 派不衰。完整 CI 演化表見 [overall_results.md](overall_results.md) 的「YCSB D/E self-aging」節（`results/aging_v2/aging_ci.csv`，10 seeds × 10 reps × 11 checkpoint）。

---

## Mutation schedule（不量 latency）

### Mixed-Mutation Churn
- **這不是被量測的 workload**，而是**製造 DB 演化壓力**的 mutation schedule。
- **op-mix：** 重複 10-op block `[rmw, insert, update, update, read, rmw, insert, update, scan, read]`；harness 把 `readmodifywrite` **remap 成 DELETE**（見 [project-churn-rmw-delete-remap](memory/project-churn-rmw-delete-remap.md)）。inserts 從 600001 起；rmw/update/read/scan 的 key uniform-without-replacement over [1,600000]；scan count 128。
- **用途：** 在被量測的 read probe 之間灌入 INSERT/UPDATE/DELETE，讓 layout 隨時間漂移；churn 實驗用它在 checkpoint 之間 aging DB，再用 Tail-Mixed 量 cold-start latency 隨 churn 的漂移。

---

## 原生 YCSB 全套（speculation branch，17 workload）

除了 main 上的 headline YC，另有一套**完整原生 YCSB A–F 重現**，資料與報告在 **`speculation` branch** `results/ycsb_full/`（`REPORT_YCSB_FULL.md`，2026-07-24 同機、**尚未併入 main**；為獨立機器狀態，絕對 µs 只批內比、相對量跨表比）。執行器 `run_experiment_ycsb.py` / `churn_ycsb.py` / `cadence_ycsb.py`（只讀 `workloads_refined/traces/`）。共 **17 workload**（原生 YCSB 無 `writeproportion`，寫入類走 churn/aging）：

| 原生 YCSB | 操作組合 | 角色 |
|---|---|---|
| **YC** | 100% read, zipfian | 讀取矩陣主軸 |
| **YCu** | 100% read, uniform | 讀取矩陣 |
| **YCh01–50 / YCo01–50** | read, hotspot-hashed / hotspot-ordered × hot-fraction {1,5,10,20,50}% | 讀取矩陣（熱點掃描，共 12 讀）|
| **YA**(50/50) / **YB**(95/5) / **YF**(rmw) | read+update | churn（改列→頁翻動）ager |
| **YD**(read-latest+insert) / **YE**(scan+insert) | read+insert | aging（append→DB 成長）ager |

> ⚠️ 這裡的 YC/YD/YE 是**原生 YCSB**，與 main 的 headline YC（real-YCSB 但單一 headline trace）、及上面的 Latest-Aging/Short-Scan Aging（Python 重建）**不同來源，勿混**。逐 phase 判定與數字見 [overall_results.md](overall_results.md)「原生 YCSB 全套重現」節、[overall_strategies.md](overall_strategies.md)「原生 YCSB 驗證」節。

---

## 為什麼需要多種 workload

不同 workload 拆解 cold-start latency 的不同 component：

```
[Interior fault]  +  [Leaf fault]  +  [SQLite CPU]
      ↑                   ↑
 prefetch 能解決      prefetch 解決不了（workload-dependent）
```

（每個 cold-start trial 前均 drop caches → 首查時 interior 與 leaf **皆 cold**；以下講「小 leaf hotset 能否覆蓋首查」而非「leaf 是否已 warm」。）

controlled read 四者正好覆蓋**三個 access regime**：

| regime | workload | 首查機制 | 最佳槓桿 |
|---|---|---|---|
| 無真實 leaf 熱點 | **Uniform-100K、Tail-Hit** | 機率攤到大量 leaf | interior skeleton（2d ~−25~28%），frequency leaf 不加分 |
| 真實 skew | **Scattered-Zipf** | 集中少數 leaf | frequency leaf 加分（2e_K10 −36%）|
| key-range 集中 | **Tail-Mixed** 的 not-found probe | ~50% miss 匯聚最右葉 | 首查是 not-found probe 時 2e_K10 可達 ~−70%，跨 seed 雙峰 −55% |

**page-type interior skeleton 才是普適 robust 贏面。** aging 軸（Latest-Aging / Short-Scan Aging）另加一層：static plan 的衰減 iff 熱點非平穩，且非平穩下結構派耐衰、反超頻率派。
