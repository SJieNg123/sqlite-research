# SQLite Cold-Start Prefetch 研究

SQLite 冷啟動後第一筆 query 特別慢:OS page cache 是空的,走訪 B+tree 必經的
**interior page** 要先從 disk 載入。Interior 只佔整個 DB 約 0.35%(~92 / 26,000 頁),
卻散布全檔,sequential readahead 救不了。

本 repo 研究:**在第一筆 query 之前先把這些關鍵 page prefetch 進 cache**,
能省多少 cold-start latency、**把 prefetch 自身的 preprocessing 成本也算進 end-to-end**,
以及哪種「選頁策略 × DB layout × workload」組合最有效。

這個問題在 **SQLite 被重新部署為 serverless / edge database** 時尤其關鍵——Cloudflare D1、Turso/libSQL 的 embedded replica、Fly.io LiteFS 都把本地 SQLite 檔跑在 commodity x86+NVMe、緊貼(常被 keep-alive 保溫的)運算。容器被保溫、開機成本攤掉後,**留在 critical path 上的就是這條資料層 cold-start**。本研究因此把 warm-process(重用 handle、≈ keep-alive 容器)當主要部署模型、standalone(冷容器)當對照。

> 完整論文:**[REPORT.md](REPORT.md)** / [REPORT.pdf](REPORT.pdf)
> 結果矩陣:[overall_results.md](overall_results.md)　策略目錄:[overall_strategies.md](overall_strategies.md)　策略怎麼測:[strategies_explained.md](strategies_explained.md)　workload 定義:[overall_workloads.md](overall_workloads.md)

## 核心發現(摘要)

baseline cold first-query @orig（canonical v2）:A 523 / B 749 / C 1087 µs。

- **first-query 變快 ≠ cold-start 真的變快(本研究主軸)**:載整份 working set 的 `2f_slru` first-query 最低(−79~91%),但它要付 ~0.8–7 ms 的 deliver 成本,反讓 end-to-end cold start **慢一個量級**——這個 trade-off 過去的 prefetch 研究長期忽略。
- **普適 robust 的贏面是 interior skeleton**:targeted prefetch 只用極少 syscall 就拿 first-query −22~83%;warm-process 部署下三個 workload 的 e2e 都改善。**穩健且普適的那根是 page-type 的 `2d`(interior skeleton)——pure-hit workload 上 ~−25~30% warm e2e**(A 2d −25% / B 2d −25% / pure-hit 控制 C_hit 2d −28%)。access-frequency 的 hot leaf **只是條件式增量**:唯有真實熱點時才加分(A 的 Zipfian skew 把 `2e_K10` 從 −25% 推到 −36%)。
- **贏在「interior 骨架」而非「照頻率挑 leaf」**:tie-break 修正後的三槓桿 ablation 顯示 **page-type(interior `2d`)才是 robust 的那根(−36%)**;access-frequency 的 leaf-only 只是 tie(且 leaf 不搭 interior 導航路徑幾乎無效),隨機 leaf 甚至淨變慢。在 C_mixed 上 `2e_K10` 與 footprint-matched 純頻率 `2f_top14` **統計不可分**。(舊的「照頻率挑 leaf −40%、access-frequency 主導」是 first-op leakage 造成的,已修正。)
- **C_mixed 的大效益是 key-range artifact,非普適**:C 的 range 有 ~50% 超出 DB 範圍的 not-found 高 key,全匯聚到最右葉形成強熱點;`2e_K10` 跨 seed 為 **−55% 雙峰**(首查是 not-found probe 的 seed ~−70%、是真 hit 的 seed 回落到 interior skeleton ~−31%),**非**通用結果。
- **跨 seed 才算數**:用 10 個 random seed 校正單一抽樣偏差——robust 的 access-pattern 贏面是(A `2e_K10` −36%、B `2d` −25%、pure-hit C_hit `2d` −28%)跨 seed **robust**(95% CI 不跨 0);C `2e_K10` −55% 為 not-found 雙峰、magnitude 不穩;structural `layers_5` 在 A/B 落在雜訊內(tie),不可恃。
- **結論在五條 robustness 軸下穩定**:50k write churn、sub-working-set RAM pressure、多 process cadence re-warm、10-seed sweep、DB 放大 10×(102 MB→~1 GiB)。RAM 壓力下小 hotset(≤2 MB)的 targeted 全程 100% delivery、first-q 不受影響,只有 `2f_slru`(整份 WS)在 cap 低於 working set 時崩潰。
- **type-aware layout 非淨贏**:把 interior 搬到 file head 雖降 first-q,卻推高 baseline(A +31% / B +4%)又讓 hotset 變大,實測沒有任何一格贏過原始 layout——**預設用原始 layout(1a)+ access-pattern prefetch** 即可。
- **多 process 免費放大**:`PRAGMA mmap_size` 開 `MAP_SHARED` 後,一個 process prefetch,所有共用同一 DB 的 process 都受惠。
- **範圍界定**:所有量測在單台 commodity x86(Ryzen 9950X)+ NVMe SSD、單一 Linux kernel——**edge/serverless 部署的同一類硬體**,但未在特定 FaaS/microVM runtime 內量測(model 其 warm-process cold-data pattern);行動裝置 / IoT 是 motivating 背景、非評估平台,絕對數字不外推到 ARM/UFS/eMMC。

完整數字與各 workload 的**條件式建議做法**（沒有單一「最佳組合」——預設 orig + `2d` interior skeleton，有已驗證的穩定 skew 才加少量 top-K leaf）見 [overall_results.md](overall_results.md)。

## Repo 結構

```
run_experiment.py          # ⭐ 統一實驗入口(run / churn / cadence 子命令)
churn.py  cadence.py       #    churn / cadence 子命令實作(import run_experiment)
env.sh                     #    每次 run 前釘核升頻 + 設 read_ahead_kb

pipeline/
  preparation/
    classify_pages/        # 不依賴 libsqlite 的 page-type 分類器 → classify CSV
    layout_rewriter/       # type-aware layout 重寫器 + test.db / *_vacuum / *_typeaware
  engine/
    benchmark_harness/     # cold-start 量測儀器(C);所有正式數字都跑在這
    prefetch_warmer/       # warmer(投遞 hotset 進 page cache)+ Level-1 真系統實驗
    residency_checker/     # mincore 殘留檢查

strategies/
  slru/                    # 2f SLRU(mincore working-set preload)
  access/                  # 2d / 2e access-pattern prefetch + gen_hotleaves

workloads/                 # workload_a/b/c/z.txt(各 10 萬筆)+ churn write 流
results/                   # 所有實驗輸出(main / churn / cadence / nsweep_dense / ksweep /
                           #   ram_pressure / size_1gb / seeds / stats / ablation / competitive / ...)
figures/                   # 論文用圖(01–18)+ plot_utils.py
tools/                     # 掃描/統計腳本(ram_pressure / run_seed_sweep / stats_uncertainty /
                           #   ablation_levers / competitive_baseline / deliver_sweep)
legacy/                    # 已退場的早期實驗(multiprocess / prefetch_vacuum / calibration)
```

## 前置(只需一次)

三個 C binary 必須先編譯好(本 checkout 已附):

```bash
cd pipeline/engine/benchmark_harness && gcc -O2 -o benchmark_harness benchmark_harness.c sqlite3.c -lpthread -ldl -lm && cd -
gcc -O2 -o pipeline/engine/prefetch_warmer/src/warmer        pipeline/engine/prefetch_warmer/src/warmer.c
gcc -O2 -o pipeline/engine/residency_checker/residency_checker pipeline/engine/residency_checker/residency_checker.c
```

冷清快取需要 `/usr/local/sbin/drop-caches`(setuid root helper)。沒有它,harness 會
**大聲報錯中止**,絕不默默量到 warm cache。DB(`test.db` / `_vacuum` / `_typeaware`)與
classify CSV 由 `layout_rewriter` 另外建,是實驗的前置輸入。

## 怎麼跑實驗

單一入口 `run_experiment.py`,registry 驅動。`--workload` / `--db` / `--strategy`
都吃 registry key,可給單一 key、comma-list,或省略(= 全部)。

```bash
# 一個組合(workload A × orig layout × 2e_K10 策略)
python3 run_experiment.py --db orig --workload A --strategy 2e_K10

# 子矩陣
python3 run_experiment.py --workload A,C --db orig,ta --strategy layers_5,2e_K10

# 完整矩陣(全 workload × 全 layout × 全策略)
python3 run_experiment.py

# 先看計畫不真跑 / 列出所有 cell
python3 run_experiment.py --db orig --workload A --strategy 2e_K10 --dry-run
python3 run_experiment.py --list
```

每個 cell 都跑兩臂(`pread` oracle / `async` 真實 hint)+ 每 (workload,layout) 一個
no-prefetch baseline 當分母。輸出在 `--outdir`(預設 `results/main/`):

| 檔案 | 內容 |
|---|---|
| `raw.csv` | 每 (workload,db,strategy,arm,rep) 一列 |
| `summary.csv` | 每 cell 的 median/p95/min;warmup 丟棄、cold check 不過的剔除 |
| `env.txt` | 開跑時擷取的環境(核、頻率、read_ahead_kb) |

三個軸的可用 key:`--db` = `orig` / `vacuum` / `ta`(layout 1a / 1b / 1c);
`--workload` = `A` / `B` / `C` / `Z`;`--strategy` = `layers_<N>` / `2d` / `2e_K<K>` / `2f_slru`。
其他子命令:

```bash
python3 run_experiment.py churn   --workload A --db orig   # DB 被持續寫入後重測同一靜態 hotset
python3 run_experiment.py cadence --workload A --db orig   # 背景 warmer 不同 cadence 的冷探針
```

## 怎麼加一個 workload

1. 在 `workloads/` 放一個檔,每行一筆 op(harness 格式:`read <id>` / `update <id>` /
   `insert <id>` / `scan <id> <len>` / `readmodifywrite <id>`)。慣例 10 萬筆。
2. 在 `run_experiment.py` 的 `WORKLOADS` registry 加一行:
   ```python
   WORKLOADS = {
       ...
       "D": ROOT / "workloads/workload_d.txt",
   }
   ```
3. 結構派策略(`layers_<N>`)立刻可用:`python3 run_experiment.py --workload D --strategy layers_5`。
4. 歷史派策略(`2d` / `2e_K*` / `2f_slru`)需要該 workload 的 residency / hot-leaf 輸入,
   先冷清重建一次:
   ```bash
   python3 run_experiment.py --regen-hotsets --workload D --db orig --yes
   ```
   (不加 `--yes` 是 dry-run;`--regen-k` 控制 2e 的 K 值。)

## 怎麼加一個新策略

一個「策略」= 一條**選出 page numbers 的規則**;runner 會自動把選中的頁 join classify CSV
變成 warmer 格式的 hotset,再交給同一套量測引擎。**不需要動 harness**。

1. 在 `run_experiment.py` 的 `STRATEGIES` 加一筆,自訂一個 `kind`:
   ```python
   STRATEGIES = [
       ...
       {"name": "myrule", "kind": "myrule", "param": 8},
   ]
   ```
2. 在 `select_pages()` 加對應分支,回傳一個 page-number 集合:
   ```python
   def select_pages(strat, w, layout, classify):
       kind = strat["kind"]
       ...
       if kind == "myrule":
           # classify: {page_number: (page_type, file_offset)}
           # 也可讀 strategies/.../runs/ 下的 residency CSV(見 _resident_pages)
           return { pn for pn, (t, off) in classify.items()
                    if t.startswith("interior") }   # ← 你的選頁邏輯
   ```
3. 跑:`python3 run_experiment.py --strategy myrule`。

若是現有 kind 的參數掃描(如不同 N / K),不必加 `STRATEGIES`——在 `resolve_strategy()`
加一條 regex 即可,例如現成的 `layers_<N>` 與 `2e_K<K>` 就是這樣動態解析的。
