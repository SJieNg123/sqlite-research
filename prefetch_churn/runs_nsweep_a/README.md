# N-sweep × Workload A (Zipfian) × Churned DB

Tests gap B2 from the audit: 之前 N sweep × churn 只測過 Workload C (high-key)。
本實驗用 **Workload A (Zipfian, keys [8, 99997])** 重跑 N ∈ {0, 1, 5, 10, 20, 46, 92}
× 10 checkpoints × 5,000 ops/checkpoint，驗證 layers_N 在不同 access pattern 下
是否一樣 churn-robust。

## 設計

- DB: `test.db` (600k rows × ~100 B = 103 MB, scatter 0.96)
- Reads: `workload_a_zipfian.txt` (100k Zipfian reads on keys [8, 99997])
- Writes per checkpoint: `workload_churn_write.txt` (5,000-op chunk; mix: 30% update,
  20% insert, 20% readmodifywrite→delete, 20% read, 10% scan)
- Strategies: layers_N (file-offset based, prefetch 前 N 個 interior pages)
- Evict: `posix_fadvise(POSIX_FADV_DONTNEED)` via `runs_nsweep/evict`
  (跟 runs_nsweep/、runs_nsweep_b/、runs_access_churn_a/ 同 harness)

## 結果

| N | avg first_q (10 checkpoints) | Δ vs N=0 |
|---|---|---|
| 0 (baseline) | 281.40 µs | — |
| 1 | 255.75 µs | -9.1% |
| **5** | **26.13 µs** | **-90.7%** ← 已到 plateau |
| 10 | 24.72 µs | -91.2% |
| 20 | 25.28 µs | -91.0% |
| 46 | 26.95 µs | -90.4% |
| **92** | **24.24 µs** | **-91.4%** |

**形狀**：N=1 幾乎無效（只載 root），N=5 就已經到 plateau（-90.7%），N=10/20/46/92
全部在 24-27 µs 之間 — **layers_5 是 A workload 的甜蜜點**，跟乾淨 DB 上的結
論一致（[overall_results.md 第三維](../../overall_results.md)），churn 不
改變 A 上的 prefetch 形狀。

## 為什麼 A × churn 比 B/C × churn 更乾淨

| Workload | leaf 是否自然熱 | prefetch 上限 |
|---|---|---|
| A (Zipfian) | ✅ 熱 keys 反覆被打、leaf 自然 warm | -91%（interior 是唯一瓶頸） |
| B (Uniform) | ❌ 每筆都 cold leaf fault | -49% (見 [runs_nsweep_b/README.md](../runs_nsweep_b/README.md)) |
| C (high-key) | ❌ 同上 | -54% (見 [runs_nsweep/README.md](../runs_nsweep/README.md) 或 第十維) |

Zipfian 的熱 key 性質讓 leaf fault 自然壓低，剩下的 cold start 成本幾乎全在
interior — N=5 全部解掉。**churn 不會改變 Zipfian 的熱點分佈**（熱 keys 都
是 long-lived 的），所以 layers_5 跨 10 checkpoint 從頭 plateau 到尾。

## 跟 layers_92 × C × churn 對照

| | A × layers_5 × churn | C × layers_92 × churn (runs_nsweep/) |
|---|---|---|
| Δ vs baseline | **-91%** | -54% |
| Syscall 數 | **5** | 92 |
| Prefetch 開銷 | ~94 µs | ~2 ms |

**A workload 上 layers_5 用 5 個 syscall 拿到比 C × layers_92 還好的相對改善**
（雖然絕對 µs 不同 harness 不能直接比較，相對改善百分比是可信的）。

## Files

- `run_nsweep_a.sh` — driver
- `aggregate.py` — summarize per-N avg first_q + Δ vs baseline
- `n{0,1,5,10,20,46,92}/benchmark_summary.csv` — per-N raw（每 N 11 個 checkpoint）
- `matrix_first_q_us.csv` — wide-form first_q across N × checkpoint

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing
bash prefetch_churn/runs_nsweep_a/run_nsweep_a.sh 0 1 5 10 20 46 92
python3 prefetch_churn/runs_nsweep_a/aggregate.py
```

Runtime: ~2 分鐘（7 個 N × ~17 s/N）。
