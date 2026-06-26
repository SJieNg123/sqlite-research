# Prefetch strategies

每個 strategy = 一條「**該預載哪些 page**」的規則。`run_experiment.py` 把該規則選出的
page 與該 layout 的 `classify_*.csv`（在 `layout_rewriter/runs/`）join 成 warmer 格式的
hotset（`page_number,file_offset`），再交給 `prefetch_warmer/src/warmer` 交付。

`--strategy <key>` 接以下 registry key（見 `run_experiment.py` 的 `STRATEGIES` /
`select_pages()`）：

| strategy key | kind | 預載哪些 page | 輸入來源 |
|---|---|---|---|
| `baseline` | —（不預載）| 無 — 改善 % 的分母 | 無 |
| `layers_<N>` | structural | 依 file offset 取前 N 個 interior page | 由 `classify_*.csv` 即時算出（無檔）|
| `2d` | resident_interior | 跑過 workload 後仍 resident 的 interior page | [`slru/runs/hotpages_{w}{layout}.csv`](slru/runs/)（`access/runs/` 那份是 symlink）→ 過濾 interior |
| `2e_K<K>` | hot2e | resident interior ∪ workload 頻率最高的前 K 個 leaf | [`access/runs/hot2e_{W}_{layout}_K{K}.csv`](access/runs/)（由 [`access/runs/gen_hotleaves.py`](access/runs/gen_hotleaves.py) 產生）|
| `2f_slru` | slru | 整個 resident working set | [`slru/runs/hotpages_{w}{layout}.csv`](slru/runs/) |

## 兩個資料夾

- **`access/`** — 原 `prefetch_access` 實驗（2d / 2e 的 access-pattern hotset + `gen_hotleaves.py`）。
- **`slru/`** — 原 `prefetch_slru` 實驗（2f 的 mincore-dumped resident working set；2d 也共用這份 base，`access/runs/` 內是 symlink 指回來）。

兩個資料夾除了上述 hotset，也保留各自早期 standalone 實驗的 matrix CSV / 腳本（沿革）。

歷史派 hotset（2d/2e/2f）以 `python3 run_experiment.py --regen-hotsets`（全機 `drop-caches`
warmup → mincore 快照）重產並 checksum 凍結（`results/main/hotset_freeze.sha256`）。
