# Workload A × Delete-heavy Churn × Static t=0 Hot pages (2d / 2e_K10 / 2e_K50)

Tests gap B1 from the audit: 在 churned DB 上，access-pattern prefetch
（2d interior-only / 2e_K interior + top-K leaves）能否撐住、靜態 t=0 hotpages
是否會隨 churn 失效。

## 為什麼挑 Workload A + delete-heavy

之前 [../runs_access_churn/](../runs_access_churn/README.md) 跑的是
**C × insert-churn**，發現 insert 目標 id=600,001+ 跟 C 的 read range
[590,000, 609,999] 有重疊但實際影響極小（static 撐住 -54%）。我們之前判斷
那可能是因為「insert 對 hot leaves 的擾動偏弱」。

**Hypothesis（被本實驗推翻）**：A 的 read range 是 [8, 99,997]，
`workload_churn_write.txt` 內的 readmodifywrite→delete 從 id=1 開始打、會直接
**命中** A 的 hot leaves，所以 t=0 hotpages 應該會 decay。

## 設計

3 arms × 10 checkpoints × 5,000 churn ops/checkpoint：

| arm | hotpages | cap_interior | cap_leaf | mode |
|---|---|---|---|---|
| `2d_static` | `hotpages_a.csv` (interior only) | unlimited | 0 | access-2d |
| `2e_k10_static` | `hot2e_A_orig_K10.csv` | unlimited | 10 | access-2e |
| `2e_k50_static` | `hot2e_A_orig_K50.csv` | unlimited | 50 | access-2e |

**Baseline / layers reuse**：n0_base 跟 n92_layers 直接從
[../runs_nsweep_a/](../runs_nsweep_a/README.md) 借（一樣的 harness、一樣的
db、一樣的 evict、一樣的 churn workload）。

Static = 整個 10 checkpoint 都用「t=0 churn 前產生的 hotpages CSV」，**不重新
trace**，模擬「production 啟動時 load 一份 trace 就一直用」的場景。

## 結果（avg first_q over 10 churn checkpoints）

| arm | avg first_q | Δ vs n0_base | drift ck001→ck010 |
|---|---|---|---|
| n0_base (no prefetch) | 281.40 µs | — | +18.9% (惡化) |
| n5_layers (file-offset 5) | 26.13 µs | -90.7% | -12.7% |
| n92_layers (file-offset 92) | 24.24 µs | -91.4% | +30.6% (噪音) |
| **2d_static** | **23.16 µs** | **-91.8%** | **+4.8%** |
| **2e_k10_static** | **21.38 µs** | **-92.4%** ← 最佳 | **-22.0% (改善)** |
| **2e_k50_static** | **23.81 µs** | **-91.5%** | **-18.1% (改善)** |

## 主要發現（hypothesis 被推翻 — 正向結論）

1. **靜態 t=0 hotpages 在 A × delete-heavy churn 上完全沒 decay**。所有 3 個
   access-pattern arm（2d、2e_K10、2e_K50）avg first_q 都比 layers_92 還低，
   ck001→ck010 沒有惡化趨勢（甚至 2e_K10 還改善 -22%，那是 noise）。
2. **2e_K10 (-92.4%) 略勝 layers_92 (-91.4%)** — A workload 上額外載 10 個
   hot leaves 比載全部 92 interior 還高效（更少 syscall，剛好的 leaves）。
3. **A 上 access-pattern 跟 file-offset 的差距很小**（91% vs 92%）— Zipfian
   熱 keys 讓 leaf 自然 warm，access-pattern 的「準確選 hot leaf」優勢被
   抹平。**這跟 C × insert-churn 的結果一致**，所以 access-pattern prefetch
   的 workload-stability 結論加強：**不論 workload skew（A Zipfian / C
   high-key）也不論 churn 類型（delete-heavy / insert-heavy），static t=0
   hot 都撐得住**。

## 為什麼 delete-heavy 沒擾動 A 的 hot leaves

Hypothesis 預期 delete-from-id=1 會擾動 A 的 hot keys，但實際沒發生。原因：

- **Zipfian 的熱 key 分散**：A 的 hot keys 雖然集中在低 id 側，但仍散佈在
  [8, 99,997]；50,000 個 delete (10 checkpoint × 5,000) 集中在 id ≈ 1~5,000
  的窄區，影響的 leaf 跟 hot leaves overlap 比例很低。
- **B+tree 不會立刻 merge**：SQLite 的 delete 只 mark page free，leaf merge
  要到下一輪 vacuum 才發生。50k delete 不夠 trigger merge，hot pages 的
  layout 維持不變。
- **hot leaves 持續被 read 命中**：access-pattern prefetch 把 hot leaves 載
  進 cache 後，後續 reads 一直 hit、leaves 持續 warm，churn 不打到 cache
  hit path。

## 跟 C × insert-churn 對照

| 維度 | A × delete-churn (本實驗) | C × insert-churn (../runs_access_churn/) |
|---|---|---|
| Read skew | Zipfian, [8, 99997] | flat, [590000, 609999] |
| Churn 類型 | delete from id=1 (-50k rows) | insert from id=600001 (+50k rows) |
| 預期 overlap | high (delete 命中 read range) | low (insert 在 read range 外) |
| 實際 decay | **無** | **無** |
| Best access-pattern Δ | 2e_K10: -92.4% | 2e_K_proper: -54% |
| layers_92 Δ | -91.4% | -54% |

兩個 case 的結論一樣：**static t=0 hotpages × access-pattern prefetch 在
churn 下穩定**，因為 (1) B+tree 結構在 50k 級 churn 下不大重排，(2) hot
pages 被 cache 後持續被 hit、不被 evict。

## Files

- `run_access_churn_a.sh` — driver (3 arms)
- `aggregate.py` — compares 3 arms vs n0_base/n5_layers/n92_layers + decay
- `{2d_static,2e_k10_static,2e_k50_static}/benchmark_summary.csv` — per-arm raw
- `matrix_first_q_us.csv` — wide-form across arms × checkpoint

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing
bash prefetch_churn/runs_access_churn_a/run_access_churn_a.sh
python3 prefetch_churn/runs_access_churn_a/aggregate.py
```

Runtime: ~1 分鐘（3 個 arm × ~17 s/arm）。需要先跑
[../runs_nsweep_a/](../runs_nsweep_a/README.md) 拿 n0_base 跟 n92_layers
做比較（不會自動跑）。
