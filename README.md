# SQLite Research Project

研究 SQLite cold-start 行為、page residency、prefetch 與 page layout 的工具與實驗集合。

## Repository Layout

每個實驗都是獨立的子目錄，包含自己的程式碼、文件與數據：

```
├── classify_pages/         # SQLite page-type 分類器
├── benchmark_harness/      # Cold-start workload benchmark 工具
├── residency_checker/      # Page residency 檢查工具
├── prefetch_churn/         # Prefetch + page churn 主實驗（orchestrator）
├── multiprocess/           # Multi-process mmap 實驗
├── prefetch_vacuum/        # Prefetch + VACUUM 實驗
└── frontend/               # 16-week 研究計畫 UI 元件
```

每個實驗目錄裡都同時放：
- 程式碼（C source、Python script、shell script）
- 該實驗的文件（`*.md`）
- 該實驗使用或產生的資料（`workloads/`、`results/`、`logs/` 等）

## 各實驗目錄

### [classify_pages/](classify_pages/) — SQLite Page Classifier

不依賴 libsqlite 的 page-type 分類器，直接照 SQLite file format 解析。

- `classify_pages.c` — C 分類器，輸出 CSV
- `plot_pages.py` — matplotlib 視覺化 + scatter-score 診斷
- `build_testdb.py` — 建立符合研究 schema 的 test DB

```bash
gcc -O2 -Wall -o classify_pages classify_pages/classify_pages.c
python3 classify_pages/build_testdb.py
./classify_pages test.db > pages.csv 2> stats.txt
python3 classify_pages/plot_pages.py pages.csv page_layout.png
```

### [benchmark_harness/](benchmark_harness/) — Cold-start Benchmark Harness

觀察 SQLite workload 在 cold-start 情境下的 latency / page fault / residency。詳見 [benchmark_harness/BENCHMARK_HARNESS.md](benchmark_harness/BENCHMARK_HARNESS.md)。

- `benchmark_harness.c` — 主程式
- `benchmark_harness_analyze_residency_by_page_type.py` — 配合 classify_pages 分析 residency
- `benchmark_harness_plot_latency_vs_faults.py` — latency vs faults 圖
- `benchmark_harness_plot_results.py` — 結果圖
- `benchmark_harness_residency_report.py` — residency 報告
- `workloads/workloadc.txt` — 測試用 workload

### [residency_checker/](residency_checker/) — Residency Checker

檢查 SQLite database 檔案中每個 page 是否 resident。詳見 [residency_checker/RESIDENCY_CHECKER.md](residency_checker/RESIDENCY_CHECKER.md)。

### [prefetch_churn/](prefetch_churn/) — Prefetch Churn Experiment（主實驗）

外層 orchestration script，循環執行 classify → prefetch → benchmark → 寫入造成 page churn，量測 prefetch 對 cold-start query latency 的效果如何隨 page layout churn 變化。詳見 [prefetch_churn/SQLITE_PREFETCH_CHURN_EXPERIMENT.md](prefetch_churn/SQLITE_PREFETCH_CHURN_EXPERIMENT.md)。

- `sqlite_prefetch_churn_experiment.py` — orchestration script
- `join_and_plot_pages.py` — 合併 page 與 residency 資料、繪圖
- `testdb_builder.py` — 建立 benchmark 用的大型 DB
- `drop_caches.sh` — root helper，清空 Linux page cache
- `workloads/` — page churn workload 檔案
- `results/` — 各 checkpoint 的 churn / prefetch summary CSV
- `logs/` — benchmark_harness run 紀錄

### [multiprocess/](multiprocess/) — Multi-process mmap 實驗

詳見 [multiprocess/MULTIPROCESS_MMAP.md](multiprocess/MULTIPROCESS_MMAP.md) 與 [multiprocess/MADVISE_KERNEL_NOTES.md](multiprocess/MADVISE_KERNEL_NOTES.md)。

### [prefetch_vacuum/](prefetch_vacuum/) — Prefetch + VACUUM 實驗

詳見 [prefetch_vacuum/PREFETCH_VACUUM.md](prefetch_vacuum/PREFETCH_VACUUM.md)。

### [frontend/](frontend/) — 16-week Research Plan UI

React 元件，呈現 16 週研究計畫。

## What classify_pages does

1. 讀 100-byte database header；取出 `page_size` (offset 16)、`page_count` (offset 28)、`first_freelist_trunk` (offset 32)。
2. 走 freelist trunk chain，標記所有 trunk + leaf freelist page。
3. 標記保留的 lock-byte page（若在檔案範圍內）。
4. 對其餘每個 page 讀 b-tree flag byte：
   - `0x02` → interior index
   - `0x05` → interior table
   - `0x0A` → leaf index
   - `0x0D` → leaf table
   - 其他 → overflow（b-tree cell 的內容延續）
5. 輸出 `page_number,page_type,file_offset` 每 page 一列。

Page 1 特別處理：它的 b-tree flag byte 在 file offset 100（在 100-byte db header 之後），不在 offset 0。

## Scatter score

`classify_pages/plot_pages.py` 對 interior pages 計算 scatter score：

- **0.0** = 完全集中在檔案開頭
- **1.0** = 均勻分布在整個檔案

真實世界的 database（以及 VACUUM 之後的 database）會接近 1.0 — 這正是本工具要量化的現象。type-aware layout 演算法應該能把這個數字推向 0.0。
