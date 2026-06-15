# N-sweep × Workload B (Uniform) × Churned DB

Tests gap B2 from the audit: 之前 N sweep × churn 只在 Workload C (high-key) 上
跑過，現用 **Workload B (Uniform, keys [1, 99999])** 重跑 N ∈ {0, 1, 5, 10, 20,
46, 92} × 10 checkpoints × 5,000 ops/checkpoint。跟同目錄
[runs_nsweep_a/README.md](../runs_nsweep_a/README.md) 比較 plateau 形狀。

## 設計

- DB: `test.db` (600k rows × ~100 B = 103 MB, scatter 0.96)
- Reads: `workload_b_uniform.txt` (100k uniform reads on keys [1, 99999])
- Writes per checkpoint: `page_churn_write.txt` (5,000-op chunk;
  30% update / 20% insert / 20% rmw→delete / 20% read / 10% scan)
- Strategies: layers_N (file-offset based, prefetch 前 N 個 interior pages)
- Evict: `posix_fadvise(POSIX_FADV_DONTNEED)` via `runs_nsweep/evict`

## 結果

| N | avg first_q (10 checkpoints) | Δ vs N=0 |
|---|---|---|
| 0 (baseline) | 499.87 µs | — |
| 1 | 494.30 µs | -1.1% |
| **5** | **270.57 µs** | **-45.9%** ← 已接近 plateau |
| 10 | 280.19 µs | -43.9% |
| 20 | 277.49 µs | -44.5% |
| 46 | 270.47 µs | -45.9% |
| **92** | **254.05 µs** | **-49.2%** |

**形狀**：N=1 幾乎無效（只載 root），N=5 之後在 254–280 µs 區間震盪、再加 N
邊際效益很小。**layers_5 已拿到 layers_92 的 93%** ((45.9/49.2)≈93%)，跟
Workload C × churn 的形狀類似（C 上 layers_5 也已拿到 layers_92 的大部分）。

## 跟 Workload A × churn 對照

| Workload | leaf 是否自然熱 | layers_5 Δ | layers_92 Δ | 絕對 avg @ layers_92 |
|---|---|---|---|---|
| A (Zipfian, [8, 99997]) | ✅ 熱 keys 反覆 hit | **-90.7%** | -91.4% | 24.24 µs |
| **B (Uniform, [1, 99999])** | ❌ 每筆都 cold leaf fault | -45.9% | **-49.2%** | **254.05 µs** |
| C (high-key, [590k, 610k]) | ❌ 同上 | (~-50%, 見第十維) | -54% (見 [runs_nsweep/](../runs_nsweep/README.md)) | (~290 µs) |

兩個 cold-leaf workload（B, C）的 plateau 都在 -45 ~ -54%，剩下 ~50% 的成本
是 leaf fault — file-offset prefetch 的天花板。要繼續壓榨 B/C 必須加 access-
pattern 2e_K（top-K hot leaves），這在
[../runs_access_churn/](../runs_access_churn/README.md)（C × insert-churn）和
[../runs_access_churn_a/](../runs_access_churn_a/README.md)（A × delete-churn）
已驗證。**B × access-pattern × churn 也已補完**（[../runs_access_churn_b/](../runs_access_churn_b/README.md)）：
2d_static -45.7% / 2e_K10_static -48.8% / 2e_K50_static -47.7%——access-pattern
跟 file-offset 打平、多載 leaf 沒增益（uniform 沒 hot leaf 可挑），但 drift 沒
單調惡化，static t=0 hot 在 B 上同樣不 decay。B 的 ~-49% 天花板由 cold-leaf
fault 鎖死、不由 prefetch 策略決定。

## Churn 影響

| N | clean DB Δ (參考第十維) | churn Δ (本實驗) |
|---|---|---|
| 5 | -45 ~ -48% | -45.9% |
| 92 | -49 ~ -54% | -49.2% |

**Churn 不改變 B 的 layers_N 形狀** — uniform reads 不會因 churn 而失去
prefetch 命中（interior 都被 prefetch 進 cache，不被 churn 動到），跟 A
（churn 不改 plateau 高度 -91%）、C（churn 不改 plateau 高度 -54%）一致。

## Files

- `run_nsweep_b.sh` — driver
- `aggregate.py` — summarize per-N avg first_q + Δ vs baseline
- `n{0,1,5,10,20,46,92}/benchmark_summary.csv` — per-N raw（每 N 11 個 checkpoint）
- `matrix_first_q_us.csv` — wide-form first_q across N × checkpoint

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing
bash prefetch_churn/runs_nsweep_b/run_nsweep_b.sh 0 1 5 10 20 46 92
python3 prefetch_churn/runs_nsweep_b/aggregate.py
```

Runtime: ~2 分鐘（7 個 N × ~17 s/N）。
