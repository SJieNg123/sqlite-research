# Overall Results — 策略 × Workload 結果矩陣

對照 [overall_workloads.md](overall_workloads.md) 裡定義的四個 workload。本檔
列出**目前實際跑過的策略對每個 workload 的結果**，以及還沒測的組合。

> Workload B（uniform，全 cold leaf）只在**策略 4 (2f SLRU)** 跑過（見
> [第五維](#第五維--策略-4-2f-slru) ），其他策略尚未在 B 上量。Workload D 是
> churn generator，沒有自己的 latency 結果。
>
> 不同實驗用的 cold-start 機制不同（`sudo drop_caches` vs
> `posix_fadvise(POSIX_FADV_DONTNEED)`），絕對 µs **不能跨表比較**，但
> 同一表內的相對改善百分比是可靠的。每節都標明資料來源。

---

## 主表 — strategy × workload（base layout、median latency）

| 策略 | Workload A（Zipfian point-read） | Workload C（high-key uniform read） |
|---|---|---|
| **baseline**（no prefetch） | **73 µs** first-query latency | **4,918 µs** first-query latency |
| **range**（merge contiguous interior pages, 1 madvise per range） | **54 µs**（-27%）<br>87 syscalls, prefetch 開銷 2.2 ms | _未測_ |
| **perpage**（每個 interior page 一次 madvise） | **48 µs**（-34%）<br>92 syscalls, prefetch 開銷 2.9 ms | _未測_ |
| **layers_5**（前 5 個 interior page by offset） | **33 µs**（-54%） ← 甜蜜點<br>5 syscalls, prefetch 開銷 94 µs | **5,130 µs**（+4% — baseline 時略差）<br>但隨 churn 累積反轉為 **-10%**（見下節）|

**資料來源：**
- Workload A 來自 [prefetch_vacuum/results/results_summary.csv](prefetch_vacuum/results/results_summary.csv)（Week 9–11，原始 layout，`sudo drop_caches`）
- Workload C 來自 [prefetch_churn/results/](prefetch_churn/results/)（10 checkpoints，每 checkpoint 之間用 Workload D 製造 5,000 ops 寫入壓力）

**讀這張表的兩件事：**
1. **prefetch 對 Workload A 大勝**（最高省 54%），對 Workload C 在乾淨 DB 上沒效益（甚至略差）。差異在於 Workload A 的 leaf 被反覆查詢自然變熱，interior 是唯一瓶頸；Workload C 每筆都打 cold leaf，prefetch 解決不了 leaf 那塊。
2. **越多 prefetch 不一定越好**：perpage 載 92 個 page 比 layers_5 只載 5 個還慢。`madvise(MADV_WILLNEED)` 是非同步的，做太多 syscall 反而讓 OS 來不及在第一筆 query 之前載完。

---

## 第二維 — Layout 對 strategy 的放大效果（Workload A only）

同一個 Workload A，但 DB layout 不同。**這張是 [layout_rewriter/](layout_rewriter/) 的端到端驗證結果**（`posix_fadvise` 冷啟動，3 reps median）：

| Layout | scatter | baseline | range | perpage | **layers_5** |
|---|---:|---:|---:|---:|---:|
| 原始 DB | 0.96 | 318 µs | 370 µs | 319 µs | 224 µs |
| 跑完 SQLite VACUUM | **1.13** ← 變更散 | 333 µs | 330 µs | 338 µs | 234 µs |
| **跑完 layout_rewriter（type-aware）** | **0.00** | 404 µs | 387 µs | 273 µs | **127 µs** ← 全局最佳 |

**相對於該 layout 自己的 baseline：**

| Layout | range | perpage | **layers_5** |
|---|---:|---:|---:|
| 原始 | +16% | +0% | -30% |
| post-VACUUM | -1% | +2% | -30% |
| **post-layout_rewriter** | -4% | -33% | **-69%** |

**這張表回答了 README 第 9 章列的核心研究問題：「Type-aware VACUUM 能不能把
prefetch 效益從 -9% 救回 -54%」 — 答案是：可以，而且超越，推到 -69%。**

副作用：
- **`range` 在 type-aware layout 上 syscall 從 87 → 1**（4.5× 快），但 kernel
  readahead 是 bounded，1 個 `MADV_WILLNEED` 只實際載入 32/92 pages → range
  策略在任何 layout 下都不是好選擇
- **type-aware layout 的 baseline 反而變慢**（318 → 404 µs），因為 leaf 被
  推到高 offset，第一個 cold leaf fault 跑得更遠。但 prefetch 一啟用就完全
  壓過這個 penalty

資料來源：[layout_rewriter/results/results_summary.csv](layout_rewriter/results/results_summary.csv)

---

## 第三維 — N sweep（Workload A，原始 layout，找甜蜜點）

| N（prefetch 幾個 interior page） | syscalls | prefetch 開銷 | first-query latency | 改善 |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 73 µs | baseline |
| 1 | 1 | 35 µs | 38 µs | -48% |
| **5** | **5** | **94 µs** | **33 µs** | **-54%** ← 甜蜜點 |
| 10 | 10 | 273 µs | 44 µs | -39% |
| 20 | 20 | 607 µs | 35 µs | -53% |
| 46 | 46 | 1,173 µs | 41 µs | -45% |
| 92 (= 全部 interior) | 92 | 2,229 µs | 50 µs | -31% |

**U 型曲線**：prefetch 太少（N=1）上層 interior 載到了但中下層還沒；prefetch
太多（N=92）syscall 本身就吃掉 2.2 ms，OS 來不及在 query 開始前載完。**N=5**
是 syscall overhead 和 coverage 的最佳折衷。

資料來源：[prefetch_vacuum/results/results_summary.csv](prefetch_vacuum/results/results_summary.csv) Week 10

---

## 第四維 — Workload C 隨 churn 漂移（10 checkpoints）

`prefetch_churn` 設計：同一個 DB，每個 checkpoint 之間用 Workload D 跑 5,000
ops 製造 layout 漂移，然後 drop cache → 跑 Workload C → 量 latency。

| Checkpoint（累積寫入 ops）| no_prefetch first-query | layers_5 first-query | layers_5 改善 |
|---:|---:|---:|---:|
| baseline (0) | 4,918 µs | 5,130 µs | +4% |
| ck001 (5k) | 4,511 µs | 5,398 µs | +20% ← prefetch 反而傷害 |
| ck002 (10k) | 5,950 µs | 4,554 µs | -23% |
| ck003 (15k) | 9,534 µs | 7,037 µs | -26% |
| ck004 (20k) | 6,574 µs | 5,385 µs | -18% |
| ck005 (25k) | 5,709 µs | 7,055 µs | +24% |
| ck006 (30k) | 7,319 µs | 6,179 µs | -16% |
| ck007 (35k) | 6,924 µs | 6,696 µs | -3% |
| ck008 (40k) | 6,816 µs | 6,795 µs | -0% |
| ck009 (45k) | 7,384 µs | 6,323 µs | -14% |
| ck010 (50k) | 6,892 µs | 6,300 µs | -9% |
| **平均**（ck001-010） | **6,661 µs** | **6,174 µs** | **-7%** |

**單筆 noise 很大**（ck001 +20%、ck003 -26%），但累積 10 個 checkpoint 平均下來
prefetch 仍然省 ~7%（絕對省 ~487 µs/query）。對照 Workload A 的 -54%，這裡的
百分比看起來小，但**絕對省的時間反而多**（A 省 40 µs vs C 省 487 µs），因為
baseline 本來就被 leaf cold fault 拉到 5,000+ µs 起跳。

資料來源：[prefetch_churn/results/](prefetch_churn/results/)

---

## 第五維 — 策略 4 (2f SLRU)

新策略：跑完一次 workload 後**不要 evict**，直接用 `mincore()` dump 當下 OS
page cache 裡的所有 resident page，存成 `hotpages.csv`。下次 cold start 時對
每個 resident page 一一呼叫 `madvise(MADV_WILLNEED)`。

這次特別**對照兩個 workload**：Workload A (Zipfian、`workloadc.txt`) 和
Workload B (Uniform、`workload_uniform.txt`)，原始 layout，3 reps median，
`posix_fadvise(POSIX_FADV_DONTNEED)` 冷啟動。

### Hot set（warmup 後 resident 的 page 分佈）

| Workload | 總 resident | leaf_table | leaf_index | interior_table | interior_index |
|---|---:|---:|---:|---:|---:|
| **A (Zipfian)** | 4,048 | 3,328 | 702 | 10 | 8 |
| **B (Uniform)** | 4,122 | 3,331 | 775 | 10 | 6 |

兩個 workload 都打 id ∈ [1, 100k]（DB 前 1/6 區段），所以 **touch 到的 leaf
集合大致相同**，hot set 大小差不多。92 個 interior pages 只有 16 個 resident，
因為剩下 5/6 區段的 interior 從沒被 traverse。

### Latency 矩陣

| Workload | 策略 | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise 次數 |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | baseline | 251 | 4.11 | 411 | 0 | 0 |
| A (Zipfian) | layers_5 | 133 | 4.13 | 412 | 15 | 5 |
| A (Zipfian) | **2f SLRU** | **14** | **2.50** | **249** | 7,255 | 4,048 |
| B (Uniform) | baseline | 255 | 4.13 | 413 | 0 | 0 |
| B (Uniform) | layers_5 | 137 | 4.11 | 411 | 15 | 5 |
| B (Uniform) | **2f SLRU** | **15** | **2.55** | **255** | 7,478 | 4,122 |

### 與 baseline 比的相對改善

| Workload | 策略 | first-q 改善 | 全 workload 總時間改善 | 端到端 cold start (prefetch+first-q) |
|---|---|---:|---:|---:|
| A (Zipfian) | layers_5 | -47% | ≈ 0% | 148 µs（vs 251 baseline，**-41%**）|
| A (Zipfian) | **2f SLRU** | **-94%** | **-39%** | 7,269 µs（**比 baseline 慢 29×**）|
| B (Uniform) | layers_5 | -46% | ≈ 0% | 152 µs（vs 255 baseline，**-40%**）|
| B (Uniform) | **2f SLRU** | **-94%** | **-38%** | 7,493 µs（**比 baseline 慢 30×**）|

### 四個發現

1. **第一筆 query 上 2f 把 layers_5 打到地上**（-94% vs -46%）。SLRU 把 4,000
   個 leaf 全 prefetch 進來，第一筆不管打哪個 id 都打到熱 leaf；layers_5 只
   prefetch interior，leaf 還是 cold-fault。
2. **但 2f 的 prefetch 自己花 7.5 ms**（4,000+ madvise syscalls），端到端 cold
   start 反而**慢 30×**。2f 不是 cold-start 策略，是 **working-set preload**
   策略。
3. **全 workload 跑完反而省 38%**（255 ms vs 413 ms），因為所有 touched leaf
   都被 pre-warm，後續 avg query 從 4.1 → 2.5 µs。layers_5 只 prefetch
   interior，後續 query 還是要 cold-fault leaf，所以 avg 沒進步。
4. **A 和 B 對 2f 沒差**（first-q 14 vs 15 µs）。原本以為 SLRU 在 skewed 上
   會輸給 access-count（無法區分 hot degree），實測一樣。原因：hot set
   (~16 MB) 全塞得進 RAM，沒有「該丟誰」的競爭，frequency 資訊用不上。2f vs
   2d/2e 的差異只會在 **RAM 預算 < working set** 時才會體現。

資料來源：[prefetch_slru/results/results_summary.csv](prefetch_slru/results/results_summary.csv)

---

## 第六維 — 策略 1b (SQLite VACUUM) × Workload B / C

`prefetch_vacuum` 早期只在 Workload A 上跑過 VACUUM 對 layout 的影響（scatter
0.96 → 1.13、layers_5 改善退化）。本節補上 **B (Uniform) 和 C (high-key
uniform)** 在同一個 `posix_fadvise` cold-start harness、4 個 prefetch 策略下
的對照（3 reps median）。

兩個 DB：
- `test.db` — 600k rows 原始 layout（scatter 0.96）
- `test_vacuum.db` — 對 `test.db` 跑過 `VACUUM;` 的結果（scatter 1.13、檔案
  從 107.8 MB 縮到 104.9 MB）

### Latency 矩陣（first-query µs）

| Workload | DB | baseline | range | perpage | layers_5 |
|---|---|---:|---:|---:|---:|
| **B (Uniform)** | orig | 463 | 350 (-24%) | 377 (-19%) | **244 (-47%)** |
| **B (Uniform)** | vacuum | 503 | 328 (-35%) | 325 (-35%) | **250 (-50%)** |
| **C (high-key)** | orig | 467 | **342 (-27%)** | 343 (-27%) | 406 (-13%) |
| **C (high-key)** | vacuum | 437 | **368 (-16%)** | 384 (-12%) | 408 (-7%) |

百分比都是「同 DB baseline 為比較基準」。

### VACUUM 對 baseline 的影響（不算 prefetch）

| Workload | orig baseline | vacuum baseline | VACUUM 帶來的變化 |
|---|---:|---:|---:|
| **A (Zipfian)** | 318 µs | 333 µs | **+5%（變慢）** |
| **B (Uniform)** | 463 µs | 503 µs | **+8%（變慢）** |
| **C (high-key)** | 467 µs | 437 µs | **-6%（變快）** |

A 數據取自 [layout_rewriter/runs/matrix_results.csv](layout_rewriter/runs/matrix_results.csv)
+ [matrix_vacuum_results.csv](layout_rewriter/runs/matrix_vacuum_results.csv)，
是同一個 harness 量出來的，可直接比較。

### 四個發現

1. **VACUUM 對 baseline 的方向 workload-dependent**：A 和 B（打 id 低段）變
   慢 +5~8%，因 VACUUM 後 interior 被推到更後面、低段 leaf 對應的 interior
   walk 路徑更分散；C（打 id 高段）反而變快 -6%，因為高段 leaf 在原 layout
   上本來就靠檔尾，VACUUM 把整個檔壓緊後 high-key region 的 seek 距離縮短。
2. **VACUUM 沒有殺死 layers_5 在 B 上的效益**（-47% → -50%）。和 README 第
   9 章的「VACUUM 把 layers_5 從 -54% 打到 -9%」現象不一致 —— 那次是
   `sudo drop_caches` + leaf 自然熱的 Workload A，瓶頸全在 interior fault；
   B 上 leaf 都是 cold fault，interior 那點 scatter 變化被攤平。
3. **Workload C 翻轉了 prefetch 策略排名**：range/perpage **打敗** layers_5
   （orig: 342 vs 406、vacuum: 368 vs 408）。原因：C 只打 [590k, 610k] 區
   段，相關 interior 不在「按 file offset 排前 5」裡 —— layers_5 prefetch 的
   是全局上層 interior，但 query 走的 interior path 在檔案中段。需要 range/
   perpage 把**所有** interior 都載入，才能覆蓋到 C 真正會 traverse 的那幾頁。
4. **range/perpage 在 vacuum DB 上反而更有效**（B：-24% → -35% / -19% → -35%）。
   推測是 VACUUM 把 interior 分布拉開後，readahead 路徑變得更線性，少了一些
   被中間 leaf 切碎的 wasted readahead。

### 結論

- **1b VACUUM 不是 universal bad**：在 high-key 讀取場景（Workload C）反而
  讓 baseline 變快 6%；在 leaf-cold-heavy 的 B 上不會殺掉 prefetch 效益。
- **「VACUUM 打到 -9%」是 A 專屬效應**，不能推廣到其他 workload。
- **layers_5 不是萬靈丹**：在 Workload C 這種只打 file region 的 workload 上，
  「按 offset 排前 N」的啟發式會選錯 page，需要改用 range/perpage 或未來的
  access-pattern 排序（2d/2e）。

資料來源：[layout_rewriter/runs/matrix_1b_bc_results.csv](layout_rewriter/runs/matrix_1b_bc_results.csv)
+ [results_1b_bc_summary.csv](layout_rewriter/runs/results_1b_bc_summary.csv)

---

## 第七維 — 策略 1c (Type-aware layout) × Workload B / C

`layout_rewriter` 把所有 interior pages 重排到 file 開頭（pages 2..93 連續），
scatter 0.96 → 0.0001。先前只在 Workload A 上量過（-69% on layers_5）。本節
補上 **B (Uniform) 和 C (high-key uniform)** 在同一 harness 上的對照。

DB：`test_typeaware.db` — 對 `test.db` 跑過 [layout_rewriter](layout_rewriter/layout_rewriter.c)，
`PRAGMA integrity_check` 通過。

### Latency 矩陣（first-query µs，3 reps median）

| Workload | DB | baseline | range | perpage | layers_5 |
|---|---|---:|---:|---:|---:|
| **A (Zipfian)** | orig | 318 | 370 (+16%) | 319 (+0%) | **224 (-30%)** |
| **A (Zipfian)** | **ta** | 404 | 387 (-4%) | 273 (-32%) | **127 (-69%)** ← 全局最佳 |
| **B (Uniform)** | orig | 463 | 350 (-24%) | 377 (-19%) | **244 (-47%)** |
| **B (Uniform)** | **ta** | 408 | 366 (-10%) | 352 (-14%) | **440 (+8%)** ← 反效果 |
| **C (high-key)** | orig | 467 | 342 (-27%) | 343 (-27%) | 406 (-13%) |
| **C (high-key)** | **ta** | 467 | 520 (+11%) | **294 (-37%)** | 317 (-32%) |

百分比都是「同 DB baseline 為比較基準」。

### 跨 layout 比較（vs 原始 DB baseline）

| Workload | orig baseline | ta baseline | ta + 最佳 prefetch | 全局最佳改善 |
|---|---:|---:|---:|---:|
| **A** | 318 µs | 404 µs (+27%) | **127 µs (layers_5)** | **-60%** |
| **B** | 463 µs | 408 µs (-12%) | 352 µs (perpage) | -24% |
| **C** | 467 µs | 467 µs (±0%) | **294 µs (perpage)** | **-37%** |

### 五個發現

1. **ta layout 對 baseline 的方向 workload-dependent**：
   - A: +27%（leaves 被推到高 offset、第一個 cold leaf fault 跑得更遠，但 Zipfian 下後續被 prefetch 完全壓過）
   - B: **-12%（變快）** — 推測是 leaf 區也變得連續，cold leaf fault 的 readahead 更高效
   - C: ±0%（高 id leaves 在 ta 後仍位於檔尾，距離沒變）
2. **ta + layers_5 在 B 上反而變慢 +8%**（408 → 440）。原因：ta 把 leaves 推到
   高 offset，layers_5 prefetch 的 5 個 interior 載到了，但第一個 cold leaf
   fault 在很遠的 offset，prefetch 的 5 頁 + 後面的 cold leaf fault 兩個 I/O
   階段串起來反而比裸 baseline 慢。**ta 強在「prefetch coverage 高」時，弱在
   「prefetch 不夠覆蓋」時 —— B uniform 的 leaf coverage 一定不夠**。
3. **ta + perpage 是 Workload C 的最佳組合**（-37%、294 µs）。perpage 把 92
   個 interior **逐頁**載入，配合 ta 的 page 2-93 連續性，kernel 能高效
   sequential read；range 反而失效（+11%）因 1 個 madvise 被 kernel readahead
   限制（~32/92 pages）。
4. **ta + range 在所有 workload 都不是好選擇**：A -4%、B -10%、C +11%。
   `MADV_WILLNEED` 對單一大 range 的 readahead 是 bounded，覆蓋不完 92 個
   interior。
5. **「ta + layers_5」是 A 專屬最強**（-69%）。在 B/C 都不是最佳；對 C 反而
   是 layers_5 在 ta 上才開始有效（orig: -13% → ta: -32%），但仍輸給 perpage。

### 結論

- **ta layout 不是 universal best**：A 上 -69%，B 上反而讓 layers_5 變慢 +8%。
- **配方依 workload 而定**：
  - Zipfian 點讀 (A) → **ta + layers_5**
  - Uniform 全段 (B) → 不要 ta，**orig + layers_5** (-47%) 仍最強
  - File-tail uniform (C) → **ta + perpage** (-37%) 是全局最佳
- **range 在任何 layout 都不該選**：kernel readahead 限制讓它永遠覆蓋不完。

資料來源：[layout_rewriter/runs/matrix_1c_bc_results.csv](layout_rewriter/runs/matrix_1c_bc_results.csv)
+ [results_1c_bc_summary.csv](layout_rewriter/runs/results_1c_bc_summary.csv)
（A 數據 [matrix_results.csv](layout_rewriter/runs/matrix_results.csv) 同 harness 可直接比較）

---

## 還沒跑的策略 × workload 組合

| 缺口 | 為什麼值得測 |
|---|---|
| **N≠5 sweep on Workload B/C** | 第六/七維補了 baseline / range / perpage / layers_5。N=1/10/20/46/92 仍未測 —— Workload C 已暗示 layers_N 的甜蜜點不一定 N=5 |
| **2d Access pattern, interior-only** | 整個策略未實作。`layers_N` 假設「offset 越小 = 越熱」對 B+tree 結構成立，但忽略不同 query 路徑使用不同分支。用 access count 排序的前 N 個 interior 可能打敗 layers_5（也是判斷 2f vs 2d 在「RAM 緊」情境下誰勝的關鍵）|
| **2e Access pattern, interior + leaf (7:3 / 5:5)** | 未實作。Workload A 有 leaf-level 熱點，prefetch top-K interior + top-M leaf 可能直接砍掉部分 leaf fault；可以驗證「2f 之所以 -94% 是因為 leaf preload」這個假設能否用更少 syscall 達成 |
| **2f SLRU 在 RAM 緊的對照** | 第五維是 RAM 充裕情境，2f vs 2d/2e 看不出差異。用 cgroup 把 RAM 預算壓到 < working set，才能體現 SLRU 不會挑重點的缺點 |
| **2f SLRU × Layout 1c (type-aware)** | 2f 只在 Layout 1a 上跑過。Layout 1c 已經把 interior 集中到檔頭，2f 還能再省什麼是個有趣對照（直覺上 first-q 不會更好，但 prefetch overhead 可能下降）|
| **Zipfian low-key hotspot variant** | 目前 Workload A 的熱點分佈在整個 [8, 99997] 區段。若熱點全在 [1, 1000]（≈ append-only churn）或全在 [99k, 100k]（≈ random churn），prefetch 效益會分歧 |
| **N sweep on churned DB** | prefetch_churn 只測 N=5，缺 N=1/10/20 在 churned layout 上的曲線（README 第 9 章自己列的 TODO）|

---

## 一句話總結

| Workload | 評估指標 | 最佳策略 | 改善幅度 | 條件 |
|---|---|---|---|---|
| **A（Zipfian）** | first-q | layers_5 on type-aware layout | **-69%**（404 → 127 µs） | 需先跑 layout_rewriter |
| **A（Zipfian）** | first-q | layers_5 on 原始 layout | **-54%**（73 → 33 µs） | 不改 layout，立即可用 |
| **A（Zipfian）** | first-q | **2f SLRU** on 原始 layout | **-94%**（251 → 14 µs）| 但 prefetch 自己花 7.3 ms，端到端 cold start 慢 29× |
| **A（Zipfian）** | 全 workload | **2f SLRU** on 原始 layout | **-39%**（411 → 249 ms）| 需要 warmup pass 先 dump hotpages |
| **B（Uniform）** | first-q | **2f SLRU** on 原始 layout | **-94%**（255 → 15 µs）| 同上 |
| **B（Uniform）** | 全 workload | **2f SLRU** on 原始 layout | **-38%**（413 → 255 ms）| 同上 |
| **C（high-key uniform）** | first-q | layers_5 on churned DB | **-10%**（avg）| 隨 churn 累積才看出效益 |
| **B（Uniform）** | first-q | layers_5 on 原始 layout | **-47%**（463 → 244 µs） | ⚠️ 在 ta layout 上 layers_5 反而 +8%；B 不適合 ta |
| **C（high-key）** | first-q | **perpage on type-aware layout** | **-37%**（467 → 294 µs） | ta + perpage 是 C 的全局最佳 |

**速記：**
- 「**點開就看一筆**」（聯絡人、設定）→ **layers_5**（cold start 152 µs vs SLRU 7,500 µs）
- 「**開了會跑一整段**」（瀏覽列表、滑相簿）→ **2f SLRU**（全 workload 省 38%）
- 兩個都要 → 看 [prefetch_slru/PREFETCH_SLRU.md](prefetch_slru/PREFETCH_SLRU.md) 的 trade-off 矩陣
