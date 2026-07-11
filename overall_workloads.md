# Overall Workloads — Workload 説明

repo 現階段使用的 workload、每個模擬什麼情境、以及分布指紋。所有 workload 跑在同一 reference DB（`testdb_builder.py` 產生的 `items(id PK, k1, k2, payload BLOB(100))`，**600,000 rows**）。measurement 權威全表見 [overall_results.md](overall_results.md)、策略結果見 [overall_strategies.md](overall_strategies.md)。

---

## Reference DB 結構

**Schema：** `items(id INTEGER PRIMARY KEY, k1 INTEGER, k2 INTEGER, payload BLOB(100))` + secondary index `idx_items_k1k2(k1,k2)`。

| 項目 | 數值 |
|---|---|
| `page_size` | 4096 bytes（SQLite 預設）|
| row 數 | 600,000 |
| page 數 | 26,331 |
| DB 大小 | ~102 MB（107,851,776 bytes）|
| **Interior pages** | **92（368 KB，0.35%）** = 51 table interior + 41 index interior |
| Leaf pages | 26,239（~102.5 MB，99.65%）|

**核心洞見：** interior 只占 0.35%，但**每筆 query 都得 root→leaf 沿路經過 interior**，cold start 時這 92 頁**每個觸發一次 4 KB random I/O**（NVMe ~50–100 µs）。interior 只有 368 KB 卻是每條 query path 的必經骨架,是最划算的 prefetch 目標;至於 leaf(占 99.65%),我們只在有頻率訊號時載最 hot 的少數,而非全部。→ **project 目標：prefetch 這 92 個 interior（只 368 KB）+ 少量 hot leaf,避開 cold-start random I/O。**（注:**每個 cold-start trial 前均 drop page cache,首查時 interior 與 leaf 皆 cold**;上述「反覆查會 warm」指的是穩態、非本研究量測的 first-query。）

**三 layout 的 interior 散佈（scatter score = interior 平均頁號的正規化位置；0=全擠檔頭、≈1=uniform 散佈）：**

| Layout | 檔案大小 | interior 位置 | scatter |
|---|---|---|---|
| 1a orig | 102.86 MiB | page 2..26,007 | **0.96**（散佈全檔）|
| 1b VACUUM | 100.05 MiB（85 interior）| 類似 1a | 1.13（反而更散）|
| 1c type-aware | 102.86 MiB | page 2..93（連續）| **0.0001**（幾乎完美 clustering）|

> 1b VACUUM 縮小的 718 page **全來自 secondary index**（table 一頁沒少）：`id` 遞增插入本就密實，但 `idx_items_k1k2` 亂序建、頁只塞 60–90% 滿，VACUUM 按 key 排序灌緊 → −711 index leaf、−7 index interior。1c 只重排位置不重塞資料，故大小/頁數同 1a。

---

## Workload 格式

`benchmark_harness` 每行一 op：`read <id>` / `update <id>` / `insert <id>` / `scan <id> <len>` / `readmodifywrite <id>`。op string 格式參照 [YCSB-cpp](https://github.com/ls4154/YCSB-cpp)。

---

## Workload A — Zipfian Point Read

**規模：** 100,000 ops 全 `read`。**Key：** id ∈ [8, 99997]（DB 前 1/6 區段）。**分佈：** Zipf α=0.99、scramble（熱 key 散佈全 key space）。
- unique **23,253**（76% repeat）；top-100 熱 key 吃 **42.3%** 流量；最熱單 key 被查 **7,752 次（7.75%）**。

**模擬：** 熱資料反覆被打（常開聯絡人、首頁 item）。**Zipfian skew 把 first-query 機率集中在少數 leaf**,使一個小的 frequency-derived hotset 較可能覆蓋首查 → prefetch 的最佳舞台,放大 targeted prefetch 效益。**（量測時所有頁——interior 與 leaf——在首查前皆 cold;skew 影響的是「小 hotset 能否覆蓋首查」,不是「leaf 是否已 warm」。）** robustness 變體 **Workload Z**：α=0.99 但 `rank=key` 不 scramble、熱點落在低 id，REPORT §A.2。

## Workload B — Uniform Random Point Read

**規模：** 100,000 ops 全 `read`。**Key：** id ∈ [1, 99999]。**分佈：** 均勻。
- unique **63,138**（多數是新查詢）；最熱 key 也只 7–8 次。

**模擬：** 無熱點的 OLTP/批次掃描（逐筆檢查、隨機 sampling）。**uniform 讀把 first-query 機率攤到大量 leaf** → 小 leaf hotset 的**期望覆蓋率低**、leaf fault 不可避免、攤薄 targeted prefetch 效益（量 prefetch 的**下界**;所有頁在首查前皆 cold）。

## Workload C（C_mixed）— Mixed Tail-boundary Lookup（~50% not-found）

**規模：** 100,000 ops 全 `read`。**Key：** id ∈ [590000, 609999]（20,000 unique，每 id 平均 5 次）。**分佈：** 均勻。

> **⚠️ key-range audit（重要）：** 初始 DB 最大 key 僅 **600000**，而 C 的 range 上界是 **609999** → **恰半數（9,999 / 20,000 unique key）超出初始資料範圍**。在 clean DB 上（未經 aging）每個 seed 的 op 流因此約 **50% hit（≤600000，真存在）+ 50% miss（>600000，not-found 高 key）**（seed 1..10 實測皆 50,005 hit / 49,995 miss）。所以 C **不是**「新加入資料馬上被讀」——在 clean DB 上半數是 **not-found 高 key lookup**。**hit 與 miss 走相同的 B+tree 右緣 interior 路徑**：miss 查詢一律下降到**最右葉**（600000 所在葉）再回報不存在，故該最右葉吸收全部 ~50k miss 流量、成為**壓倒性單一 hot leaf**；hit 查詢（真 key ∈ [590000,600000]）散落在頻率相近的多個真葉。seed 1 的 first op 是 `read 590000`（**hit**）；跨 10 seed 的 first-op hit/miss 為 5 hit / 5 miss（見 §learned C caveat 與 `results/loso/coverage.csv`）。這正是 C 上 learned first-op coverage 呈 6/10（miss first-op 5/5 覆蓋、hit 1/5）的機制根源。

**模擬：** existence check / 稀疏 ID lookup / tail-boundary 讀取，其中半數為超出資料範圍的 not-found lookup。因 leaves 高度集中檔尾、且最右葉被 miss 流量灌成單一超熱 leaf，C 是 2f SLRU 最小 hot set（~1.7 MB）的對照點，且 2e_K10 在 C 上 first-q −83% / e2e_warm −75% 是全矩陣最佳（**但此優勢主要來自上述 not-found 熱點 key-range artifact，非 uniform tail 讀取的普適性質——見下方 C_hit 控制**）。

## Workload C_hit — Pure-hit Tail Control（C 的對照）

**規模：** 100,000 ops 全 `read`。**Key：** id ∈ **[580001, 600000]**（20,000 unique，每 id ×5）。**分佈：** 均勻。**全部 key 存在**（max=600000=db max）→ **0 not-found**（manifest hit_ratio=1.0，`HIT_ONLY` 硬 assert 把關）。

**用途：** C 的 pure-hit 控制——**同 20k key-space、同 tail-region locality、同 uniform ×5 結構，唯一差別是把 range 收進 DB 範圍**，移除 C 那 ~50% not-found 高 key 造成的最右葉超熱點。回答：「拿掉 not-found 集中後，frequency-aware prefetch 還有效嗎？」

**結果（orig，10 seeds × 10 reps，跨 seed warm-process e2e、皆 robust；`2e_K10` 為 tie-break 修正後 `results/c_hit_v2`，其餘 `results/c_hit`）：**

| strategy | e2e_warm | 這是什麼 |
|---|---:|---|
| 2d（interior only）| **−28.5%** [−34.9,−19.6] | interior skeleton |
| 2f_top14（freq, page tie-break）| **−30.6%** [−37.1,−22.4] | 真實 frequency |
| learned_markov_14（LOSO held-out）| **−29.0%** [−36.1,−19.4] | held-out |
| **2e_K10（tie-break 修正後）**| **−27.2%** [−34.6,−17.7] | **== interior skeleton** |
| 2f_slru | +76.5% | deliver trap |

- **C 的大效益是 not-found 驅動**：pure hit 上穩健效益是 **interior skeleton ~−28%**；frequency leaf 相對 interior-only 幾乎不加分（**uniform tail 無真實 leaf 熱點**）。
- **`2e_K10` 的舊 −69.6% 是 first-op leakage，已修正**：C_hit 每葉 count 打平（~150），舊 `gen_hotleaves` 的 `Counter.most_common` 用 insertion-order tie-break → 最早出現的 K 葉 → 恰含被測 first-op 葉（10-fold coverage `results/loso/coverage_c_hit.csv`：2e_K10 10/10 vs 2f_top14/learned/frequency 0/10）。改成 `(-count, pageno)` deterministic tie-break（commit `de4490f`）後 `2e_K10` = **−27.2%**，落進 interior-skeleton band。
- **三個 access regime**：無真實 leaf 熱點（**B、C_hit**）→ interior skeleton ~−25~28%，frequency leaf 不加分；真實 skew（**A**）→ frequency leaf 加分（2e_K10 −36%）；key-range 集中（**C mixed** 的 not-found probe）→ 最右葉超熱、~−70%。C（mixed）整體 = hit(regime 1)/miss(regime 3) first-op 混合 → 雙峰 −55%。**page-type interior skeleton 才是普適 robust 贏面。** 完整見 [`results/c_hit/FINDINGS.md`](results/c_hit/FINDINGS.md)、`results/c_hit_v2`、`results/tiebreak_fix`。

## Workload D — Mixed Write-heavy Churn Generator

**規模：** 100,000 ops 混合（`update` 30% / `insert` 20% / `read` 20% / `readmodifywrite` 20% / `scan` 10%）。**不量 latency**，是 churn generator：製造 INSERT/UPDATE/DELETE 壓力讓 layout 隨時間漂移。
- `insert` 從 id=600,001 起（真新資料）；`readmodifywrite` 被 harness remap 成 DELETE（見 [project-churn-rmw-delete-remap](memory/project-churn-rmw-delete-remap.md)）。
- 用在 `churn` 實驗的 checkpoint 之間（每 checkpoint 灌 5,000 ops、共 10 個），再用 Workload C 量 cold-start latency 隨 churn 的漂移。

---

## 為什麼需要多種 workload

不同 workload 拆解 cold-start latency 的不同 component：

```
[Interior fault]  +  [Leaf fault]  +  [SQLite CPU]
      ↑                   ↑
 prefetch 能解決      prefetch 解決不了（workload-dependent）
```

- **A（Zipfian）** 壓低 leaf fault（leaf 自然熱）→ interior 成唯一瓶頸 → prefetch **上界效益**。
- **B（uniform）** 放大 leaf fault → prefetch 只能解 interior → **下界效益**。
- **C（high-key）** 同 B 分佈但鎖檔尾，配合 D 量 **layout 漂移**隨時間的影響。
- **D** 不為 latency，純製造寫入歷史讓 layout 偏離乾淨狀態。

---

## YCSB core D / E（寫入型）

> ⚠️ **命名：** 本節 **YCSB D / E**（registry key `YD` / `YE`）是 YCSB 標準 core workload（read-latest / short-ranges），**與上面「Workload D＝churn generator」不同東西**，勿混。

**產生器：** `workloads/gen_workload.py`（type `YD`/`YE`，各 10 seeds `workload_{yd,ye}_1..10.txt`，比例參照 [YCSB-cpp](https://github.com/ls4154/YCSB-cpp)）。兩者**含 insert（寫入型）**：insert 從 **600001** 起（超過 DB 密集 max id 600000，否則 upsert 只改列不長大）→ DB 隨時間 aging。首 op 強制 `read`（供唯讀 TTFQ probe 過 `--require-read-first`）。

### YCSB D（`YD`）— read-latest
op-mix（seed 1 實測）：`read` **95,108** + `insert` **4,892**（≈95/5）。`requestdistribution=latest`：讀熱點集中最近插入 key（Zipf α=0.99 對 recency rank、`key=cur_max−zipf_rank`）。
- reads：unique **37,456**、range **[106, 604892]**；**57%（53,996 筆）落在 >600000 新插入區** → **移動的 hotset**（top-1 單 key 僅 28 次，因最熱 key 隨 cur_max 漂）。inserts **600001–604892**（DB 長大 ~4.9k 列）。
- **模擬：** timeline / 最新事件——寫入不斷產生新熱 key，這是 A/B/C/Z（靜態熱點）沒有的軸，壓測 static/history 派預取。

### YCSB E（`YE`）— short-ranges
op-mix（seed 1 實測）：`scan` **94,975** + `insert` **5,024** + `read` 1。`requestdistribution=zipfian`、`maxscanlength=100`。
- scans：start = scrambled Zipf α=0.99 over [1..600000]（散佈，同 A），start unique **34,756**、range [29, 599899]、top-1 6,429 次；**scan length ∈ [1,100]，mean 50.5**。inserts **600001–605024**。
- **模擬：** 短範圍掃描為主（訊息佇列尾端連續讀）+ 5% 插入 aging。

### aging 量測（自 self-aging 路徑）
YD/YE 含寫入、不能走唯讀 `run`，走 **`run_experiment.py aging`**（`WRITE_WORKLOADS={YD,YE}`）：workload 自身 insert 流灌**可寫副本**做 aging。**關鍵方法學**：每 checkpoint 用**反映當下 hotspot 的 probe**（= 該 chunk 的 reads，隨 insert frontier 移動），對**凍結在 t=0 的 hotset** 量 TTFQ。這樣才測得到「frozen hotset 被移走的 hotspot 拋離」的 decay——**單一全 trace 固定 probe 測不到**（其 first query 永不移動）。實作 commit `d110e3d` + `3889f09`（per-checkpoint probe 修正見 churn.py `_probe_from_lines`）。

**實測 aging 演化（orig，**11 個 measurement checkpoint ck0–ck10**（= **10 個 aging increment** × 5,000 ops）× **10 reps × 10 seeds**，`results/aging_v2/aging_ci.csv`；first_query_us，mean ± 95% CI）：**

| static t=0 hotset | YD（read-latest，非平穩）| YE（zipfian，平穩）|
|---|---|---|
| baseline（no prefetch）| 538±16 → 570±24（平）| 550±16 → 601±43（平）|
| **2e_K10_static（access-freq）** | **267±110（−50%）→ 382±78（−33%）** 衰減 | 260±3（−53%）→ 273±39（−55%）**穩定不衰**|
| layers_92_static（structural）| **252±9 → 270±12**（robust）| 260±3 → 292±20（微升）|

- **decay 由 hotspot 平穩性決定**（釘出「static t=0 hotset 不 decay」結論的適用邊界）：
  - **YD（read-latest，非平穩）**：熱點跟著 insert frontier 移動 → **access-frequency 派 `2e_K10_static` 收益從 ck0 的 −50% 衰到 ck10 的 −33%（erodes by ~half，仍優於 baseline、非歸零）**；ck0 CI 很大（±110），反映初始匹配跨 seed 不穩。
  - **structural `layers_92_static` robust（252→270，+7%，CI 緊）**，且 **從 ck1 起 layers_92（~250–278）反超 2e（~310–420）** → **read-latest aging 下結構派 > 頻率派**。機制：頻率 hotset 綁「哪些 key 熱」（非平穩下失效），結構 skeleton 綁「樹長什麼樣」（漂移緩慢）。
  - **YE（zipfian，平穩）**：熱點不隨 insert 移動 → `2e_K10_static` **不衰（−53%→−55%）、全程仍優於 layers_92**，同 C 的平穩情形。
- **對照 C/A/B**：key range 固定、churn 下熱頁不動，`2e_K10_static` 不 decay（見 §6.2.1）；**YD 是此結論的第一個反例**——衰不衰取決於 hotspot 平穩性，且**頻率派衰、結構派耐衰並反超**。
- **維度並存（勿當矛盾）**：`layers_*` 在 cross-seed first-query *level* 上「不可恃」（§7.3 tie/directional），卻在 aging *robustness* 軸上最耐久——兩個不同軸的結論並存。
- **已完成：** 跨 seed aging — **10 seeds × 10 reps × 11 checkpoint**（`results/aging_v2/aging_ci.csv`）。**未跑：** 更深 checkpoint / 更長 aging horizon、YCSB E 的 scan-based learned baseline。

> **資料出處：** 分布數字由 `workloads/workload_{yd,ye}_1.txt` 統計；aging 演化由 `results/aging_v2/aging_ci.csv`（10 seeds × 10 reps，per-checkpoint probe，cross-seed 95% CI）。絕對 µs 批內自洽（演化比較），非跨批。
