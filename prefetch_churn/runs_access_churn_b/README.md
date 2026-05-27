# Workload B × Churn × Static t=0 Hot pages (2d / 2e_K10 / 2e_K50)

Closes the last audit gap: **B × access-pattern × churn**. The other two
access-pattern × churn cases were already done —
[C × insert-churn](../runs_access_churn/README.md) and
[A × delete-churn](../runs_access_churn_a/README.md). B was the open question.

## 為什麼 B 是最後一塊

A (Zipfian) 和 C (high-key) 都有「自然熱葉」——少數 leaf 被反覆讀。access-pattern
prefetch 靠 t=0 trace 精準挑出這些 hot leaves，所以 2e_K 能贏過 file-offset 的
layers_N。**B (uniform, keys [1, 99999]) 沒有自然熱葉**：每筆查詢打到不同的
cold leaf。

**問題**：在這種情況下，t=0 access-count 排出來的 top-K leaves 是不是退化成
「隨機挑 K 個 page」——既沒有額外效益，又會不會隨 churn 失效？

## 設計

3 arms × 10 checkpoints × 5,000 churn ops/checkpoint：

| arm | hotpages | cap_interior | cap_leaf | mode |
|---|---|---|---|---|
| `2d_static` | `hotpages_b.csv` (interior only) | unlimited | 0 | access-2d |
| `2e_k10_static` | `hot2e_B_orig_K10.csv` | unlimited | 10 | access-2e |
| `2e_k50_static` | `hot2e_B_orig_K50.csv` | unlimited | 50 | access-2e |

**Baseline / layers reuse**：n0_base、n5_layers、n92_layers 直接從
[../runs_nsweep_b/](../runs_nsweep_b/README.md) 借（同 harness、同 db、同 evict、
同 churn workload）。Static = 整個 10 checkpoint 都用 t=0 churn 前產生的
hotpages CSV，不重新 trace。

## 結果（avg first_q over 10 churn checkpoints）

| arm | avg first_q | Δ vs n0_base | drift ck001→ck010 |
|---|---|---|---|
| n0_base (no prefetch) | 499.87 µs | — | +11.2% |
| n5_layers (file-offset 5) | 270.57 µs | -45.9% | -9.8% |
| n92_layers (file-offset 92) | 254.05 µs | **-49.2%** ← 最佳 | +17.3% (噪音) |
| **2d_static** | **271.41 µs** | **-45.7%** | +35.0% (噪音) |
| **2e_k10_static** | **255.87 µs** | **-48.8%** | +9.7% |
| **2e_k50_static** | **261.31 µs** | **-47.7%** | -8.0% |

## 主要發現

1. **B 上 access-pattern 沒有比 file-offset 好**。2d_static (-45.7%) ≈ layers_5
   (-45.9%)；2e_k10_static (-48.8%) ≈ layers_92 (-49.2%)。**精準挑 hot leaf
   的優勢在 uniform workload 上完全消失**——因為根本沒有 hot leaf 可挑。
2. **多載 leaves 幾乎沒幫助**。2d (interior-only) → 2e_K10 → 2e_K50 只在
   -45.7% / -48.8% / -47.7% 之間擺動（差異在 noise 範圍內）。top-K leaves
   對 uniform reads 等同隨機選頁，命中下一筆查詢的機率極低。
3. **但它「沒有失效」**。3 個 static arm 的 ck001→ck010 drift 沒有單調惡化
   趨勢（+9.7% / -8.0% / +35.0% 都是 noise），avg 穩定落在 -46~49%。**靜態
   t=0 hotpages 在 B × churn 下不 decay——它只是不帶來額外效益，不是會壞掉。**
4. **B 的天花板由 cold-leaf fault 決定，卡在 ~-49%**。不論用 file-offset 還
   是 access-count，都只能救掉 interior path（92 個 page）；每筆 uniform 查詢
   仍要 fault 一個沒被 prefetch 到的 cold leaf。這跟乾淨 DB 上 B 的 -47~49%
   完全一致——churn 不改變這個結構性上限。

## 三種 access-pattern × churn 對照（全矩陣完成）

| 維度 | A × delete-churn | B × churn (本實驗) | C × insert-churn |
|---|---|---|---|
| Read skew | Zipfian [8, 99997] | uniform [1, 99999] | flat [590000, 609999] |
| 自然熱葉 | 有 | **無** | 有 |
| Best access-pattern Δ | 2e_K10: -92.4% | 2e_K10: **-48.8%** | 2e_K10: -91% |
| 2e_K10 vs layers_92 | 勝 (92.4 vs 91.4) | **平手** (48.8 vs 49.2) | 勝 |
| static t=0 decay | 無 | **無** | 無 |

**結論**：access-pattern × static t=0 hot 在三種 workload × churn 組合下都
**不 decay**，可放心當 production baseline。但它的 first-q 改善幅度由 workload
的 leaf-warmth 決定，不由 prefetch 策略決定：**有自然熱葉的 A/C 拿到 -91~92%，
沒有熱葉的 B 卡在 ~-49%（等同 file-offset layers_N，多挑 leaf 也沒用）**。

## Files

- `run_access_churn_b.sh` — driver (3 arms)
- `aggregate.py` — compares 3 arms vs n0_base/n5_layers/n92_layers + decay
- `{2d_static,2e_k10_static,2e_k50_static}/benchmark_summary.csv` — per-arm raw
- `matrix_first_q_us.csv` — wide-form across arms × checkpoint

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing
bash prefetch_churn/runs_access_churn_b/run_access_churn_b.sh
python3 prefetch_churn/runs_access_churn_b/aggregate.py
```

Runtime: ~1 分鐘（3 個 arm × ~17 s/arm）。需要先跑
[../runs_nsweep_b/](../runs_nsweep_b/README.md) 拿 n0_base / n5_layers /
n92_layers 做比較（不會自動跑）。
