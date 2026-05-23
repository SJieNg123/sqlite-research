# Prefetch SLRU — 策略 2f：mincore-approximated 工作集 prefetch

`prefetch_slru` 用 SLRU 的「protected segment」概念近似 hot set：跑完一次
workload 後，**直接用 `mincore()` 把當下還在 OS page cache 裡的 page list
存下來**（叫做 `hotpages.csv`），下次 cold start 時對這些 page 一一呼叫
`madvise(MADV_WILLNEED)`。

對照 [overall_strategies.md](../overall_strategies.md) 的編號，這是 **2c
Layers N**、**2d/2e Access-pattern-based** 之外的新軸線，編號 **2f**，補進
prefetch 策略的最末項。

## 與其他策略的差別

| 策略 | 資料來源 | 精度 |
|---|---|---|
| 2c Layers N | classify_pages（只看 page 類型 + offset）| 假設「offset 小 = 上層 = 熱」|
| 2d Access pattern, interior only（未實作）| 攔截每次 page read，存 access count | 區分 1 次 vs 100 次 |
| 2e Access pattern, interior+leaf（未實作）| 同上但含 leaf | 同上 |
| **2f SLRU**（本檔）| 跑完 workload 後 `mincore()` dump residency | **只知道 hot/cold，不知道 hot degree** |

策略 2f 的優勢：**完全不用攔截 SQLite 的內部呼叫**——residency_checker 已經
有現成的 mincore 邏輯。實作就是一個 ~70 行 C 程式。

## Build

```bash
gcc -O2 -Wall -o src/prefetch_slru src/prefetch_slru.c
```

## 使用

```
prefetch_slru <database.db> <residency.csv> <page_size>
```

`residency.csv` 是 [residency_checker](../residency_checker/) 的標準輸出
（`page_number,is_resident`）。工具會跳過 header，對每個 `is_resident=1` 的
page 算 file offset 並呼叫 `madvise(MADV_WILLNEED)`。

完整流程（以 Workload A = Zipfian 為例）：

```bash
# 1. WARMUP — evict + 跑 workload + dump residency
./runs/warmup.sh ./runs/workload_a_zipfian.txt ./runs/hotpages_a.csv

# 2. MEASUREMENT — 用 hotpages_a.csv 餵 prefetch_slru
benchmark_harness \
  --db test.db --workload workload_a_zipfian.txt \
  --cold-advice dontneed \
  --drop-caches-script ./runs/evict_helper.sh \
  --post-cold-script ./runs/prefetch_slru_a.sh
```

## 實測結果

Reference DB：600,000 rows, 26,331 × 4 KB pages (其中 92 interior)。
冷啟動方式：`posix_fadvise(POSIX_FADV_DONTNEED)`（無 sudo）。
3 reps median。

> Workload 命名沿用 [overall_workloads.md](../overall_workloads.md)：
> - **Workload A** = Zipfian point-read (`workloadc.txt`)
> - **Workload B** = Uniform random point-read (`workload_uniform.txt`)

### Hot set 大小（warmup 後的 resident page 分佈）

| Workload | 總 resident pages | leaf_table | leaf_index | interior_table | interior_index |
|---|---:|---:|---:|---:|---:|
| **A (Zipfian)** | 4,048 | 3,328 | 702 | 10 | 8 |
| **B (Uniform)** | 4,122 | 3,331 | 775 | 10 | 6 |

**觀察 1：兩個 workload 的 resident set 大小幾乎一樣（4,048 vs 4,122）**，但組成
邏輯不同 — A 是「23k unique key、最熱的被打 7,752 次」、B 是「63k unique key、
每個只被打 1-2 次」。共同點：**兩者都打 DB 前 1/6 的 id 區段**，所以 touch 到
的 leaf 頁面大致相同。

**觀察 2：92 interior pages 只有 16 個 resident**。因為 workload 只查 id ∈ [1,
99999]（DB 前 1/6），剩下 5/6 區段的 interior 從沒被 traverse 到。

### Latency 矩陣（first query / 平均 / 全 workload 總時間 / prefetch 開銷）

| Workload | Strategy | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise syscalls |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | 1a baseline | 251 | 4.11 | 411 | 0 | 0 |
| A (Zipfian) | 2c Layers N=5 | 133 | 4.13 | 412 | 15 | 5 |
| A (Zipfian) | **2f SLRU** | **14** | **2.50** | **249** | 7,255 | 4,048 |
| B (Uniform) | 1a baseline | 255 | 4.13 | 413 | 0 | 0 |
| B (Uniform) | 2c Layers N=5 | 137 | 4.11 | 411 | 15 | 5 |
| B (Uniform) | **2f SLRU** | **15** | **2.55** | **255** | 7,478 | 4,122 |

### 與 baseline 比的相對改善

| Workload | Strategy | first-q 改善 | 全 workload 總時間改善 | 端到端 cold start (prefetch+first) |
|---|---|---:|---:|---:|
| A (Zipfian) | 2c Layers N=5 | -47% | ≈ 0% | 148 µs（vs 251 baseline，**-41%**）|
| A (Zipfian) | **2f SLRU** | **-94%** | **-39%** | 7,269 µs（**+2,800%**，比 baseline 慢 29×）|
| B (Uniform) | 2c Layers N=5 | -46% | ≈ 0% | 152 µs（vs 255 baseline，**-40%**）|
| B (Uniform) | **2f SLRU** | **-94%** | **-38%** | 7,493 µs（**+2,840%**，比 baseline 慢 30×）|

## 四個發現

### 1. 策略 2f 第一筆 query 把 2c 打到地上（-94% vs -46%）

`madvise(MADV_WILLNEED)` 對單一 leaf page 是 kernel 確實會 load 的。SLRU 把
4,000 個 leaf 全 prefetch 進來，第一筆 query 不管打哪個 id 都打到熱 leaf。
2c 只 prefetch interior，leaf 還是 cold-fault → 落在 130–137 µs。

### 2. **但** 2f 的 prefetch 自己花 7.5 ms — cold start 端到端慢 30×

4,000+ 個 madvise syscall 在這台機器上花 1.8 µs/個。對使用者來說，
**cold-tap 到「螢幕看到第一筆結果」的時間反而從 251 µs → 7,269 µs**。

這是 2f 的核心 trade-off：**它不是「降低 cold start」的策略，是「升級成
working set preload」的策略**。如果應用情境是 "App 開了之後會跑很久的
workload"，2f 把整個 workload 提前 warm 起來；如果是 "點開就只看一個
聯絡人"，2f 直接是反指標。

### 3. 全 workload 累積下來，2f 反而省 38%

```
總時間（cold start + 100k queries）：
  baseline : 0 + 411 ms = 411 ms
  2c       : 0.015 + 412 ms = 412 ms（≈ baseline）
  2f       : 7.3 + 249 ms = 256 ms ← 比 baseline 省 38%
```

因為 SLRU 把整個 working set（不只第一筆 query 路徑上的 page）都拉進
cache，所以**後續每一筆 query 也快**（avg 2.5 µs vs 4.1 µs）。2c 只 prefetch
interior，**leaf 還是要 page fault**，所以 avg 沒進步。

### 4. Workload A vs B 對 2f 沒差（推翻原本預測）

原本預期：2f 在 uniform B 上 ≈ 2d/2e（access count），在 skewed A 上
**劣於** 2d/2e，因為 SLRU 不會區分「打 7,752 次」 vs 「打 1 次」。

實測：A 和 B 結果幾乎相同（first-q 14 vs 15 µs、resident set 4048 vs 4122）。
原因：
- 兩個 workload 都打 id ∈ [1, 100k]，touch 到的**唯一 leaf 集合差不多**
- mincore 只能說 hot/cold，不能說 hot-degree，但這裡 hot set 全塞得進 RAM
  (4,000 × 4 KB ≈ 16 MB)，所以**沒有「該丟掉哪個」的競爭**，frequency 資訊
  用不上
- 2f vs 2d/2e 的差異只會在 **resident set 大於 RAM 預算** 時體現
  （RAM 預算 < 16 MB 時 access count 才能挑出最熱的 K 個）

## Trade-off 矩陣（誰該用哪個策略）

| 應用情境 | 建議策略 | 為什麼 |
|---|---|---|
| 點開 App 馬上要看到第一筆（聯絡人、設定）| **2c Layers N=5** | cold-start 148 µs vs 2f 7,269 µs |
| 開啟後會跑一整段 workload（瀏覽相簿、滑訊息列表）| **2f SLRU** | 全 workload 時間 -38% |
| RAM 充裕、想最少程式碼實作 prefetch | **2f SLRU** | 不用攔截 SQLite，~70 行 C |
| RAM 緊（< working set）| 待測 **2d / 2e**（access count） | 2f 不會挑重點 |

## Files

```
src/prefetch_slru.c    — 70 行 C，讀 residency CSV + madvise
runs/                  — warmup.sh、prefetch wrappers、runmatrix.sh、raw results
  workload_a_zipfian.txt → ../../benchmark_harness/workloads/workloadc.txt
  workload_b_uniform.txt → ../../benchmark_harness/workloads/workload_uniform.txt
  hotpages_a.csv        — Workload A (Zipfian) warmup residency
  hotpages_b.csv        — Workload B (Uniform) warmup residency
results/               — results_summary.csv 等
```
