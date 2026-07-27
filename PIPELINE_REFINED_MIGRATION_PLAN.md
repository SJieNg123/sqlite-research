# Pipeline 遷移計畫:把 workload 來源從 `gen_workload.py` 換成 `workloads_refined`(真 YCSB)

> 目標:讓 `run_experiment.py` 的實驗矩陣改吃 **workloads_refined 的真 YCSB trace**,重跑並檢驗 paper(REPORT.md)的結論是否在**更有出處、可複現**的 workload 上仍成立。
> **本檔只是計畫,不動任何 code。** 決策點在 §3 與 §9,請你先拍板再執行。

---

## 0. 先講最重要的一句(honest scope)

**這不是「重現一模一樣的數字」,是「換掉 generator 後重跑同一個實驗設計」。**
換 `gen_workload.py`(手刻)→ 真 YCSB,數字**一定會變**(這正是 workloads_refined 存在的理由,見 `WHY_REFINED.md`)。所以「重現 paper 結果」的正確定義是:

> **同樣的 cell 矩陣、同樣的兩個 e2e 公式,在真 YCSB 上重跑,看核心結論(interior skeleton `2d` warm-e2e −25~−30%)是否 hold。**

有些 paper 結果**結構上無法重現**(見 §3):C 的 −75%/−55% 來自一個 **not-found artifact**,真 YCSB 沒有這種 workload。

---

## 1. 現況(我實際查到的)

| 事實 | 內容 |
|---|---|
| Pipeline root | `ROOT=/home/u03/sqlite-research-project-sharing`(存在);`EXPERIMENT_ROOT` 可覆蓋指向本 fork |
| Workload 讀取路徑 | `$ROOT/workloads/workload_<key>.txt`(或 `_<seed>.txt`) |
| Harness 介面 | `benchmark_harness --db <db.db> --workload <trace.txt> --readonly --require-read-first …` — 吃的是 **trace 檔** |
| **格式相容性** | harness 解析 `read <id>` / `scan <id> <len>` 等;**refined trace 同格式 → drop-in ✓** |
| **DB 對齊** | `test.db` = 600000 rows、id 1..600000 dense INTEGER PK;refined keymap id ∈ 12..599991 → **對得上 ✓**;`WHERE id=?` 只走 PK btree,不碰 `idx_items_k1k2` |
| Pipeline 已部分 YCSB 化 | `WORKLOADS` 已有 `YC`(real zipfian read-only)、`YD`、`YE`;`WRITE_WORKLOADS={YD,YE}` 走 aging 路徑 |
| 舊 workload 現狀 | 本 fork 的 `workloads/` 已被刪;sharing repo 應仍有 |
| run 矩陣限制 | `run` 子命令強制 `--readonly --require-read-first` → **YD/YE(write/scan)不能走 run,只能走 aging** |

---

## 2. 我們手上有的 refined trace(workloads_refined/traces/)

```
YA(workloada 50/50 r/u)  YB(workloadb 95/5)  YF(workloadf rmw)
YC-h-hashed-hdf{0.01,0.05,0.10,0.20,0.50}   YC-h-ordered-hdf{同5個}   ← 全 read-only hotspot
YD(read-latest 95/5)   YE(scan 95/5)
```
外加 pipeline 已接的 **YC**(real workloadc zipfian read-only,在 sharing repo 的 `workloads/`)。
**沒有的**:`YC-u`(workloadc uniform)、純 `YC`(本 fork 未凍,但 sharing 有)。

---

## 3. 【決策點 A】Workload 對應——這是整個遷移最難、也最誠實的地方

paper 的 registry key(A/B/C/C_hit/Z)**不是** YCSB 正典 A–F,對應如下:

| paper key | 它是什麼 | refined 對應 | 能不能乾淨換 |
|---|---|---|---|
| **A** | Zipfian scramble read(熱點散全 keyspace) | **YC**(workloadc zipfian,已接) | ✅ **乾淨** |
| **B** | Uniform random read | **YC-u**(workloadc uniform)← **需生成** | ⚠️ 要補生一條 |
| **Z** | low-key Zipfian(不 scramble,熱點在低 id) | **YC-h-ordered** 或 non-scramble zipfian | ⚠️ 近似 |
| **C** | tail-boundary,~50% not-found(range 超出 max key) | **無 YCSB 對應** | ❌ **無法** |
| **C_hit** | C 的 pure-hit 對照 | **無 YCSB 對應** | ❌ **無法** |

**關鍵誠實點:C / C_hit 是自造 tail-boundary probe,YCSB 沒有這種 workload。** paper 的 C 結果(−75% not-found probe、−55% 雙峰)**結構上依賴那個 not-found artifact**,真 YCSB 重現不了。→ 見 §9 決策:C/C_hit 要 (a) 保留為 Tier-2 mechanism probe(標「非 YCSB」)、(b) 丟掉、還是 (c) 用別的 YCSB workload 換角度。

**能乾淨重跑 headline 的,是 A(→YC)+ B(→YC-u)。** 外加可以把整個 YCSB 正典 roster(YA/YB/YC-h/YD/YE/YF)當**新 workload** 加進矩陣,擴大 coverage。

---

## 4. 遷移步驟(概念流程)

```
[決策 §3 對應表]
   ↓
(1) 補生缺的 trace:YC-u(uniform),必要時 Z 的替身
   ↓
(2) 把 refined trace 放進 pipeline 讀得到的位置
     選項 α:複製到 $ROOT/workloads/workload_<key>.txt（改名對齊 registry key）
     選項 β:改 run_experiment.py 的 WORKLOADS 常數,直接指向 workloads_refined/traces/
   ↓
(3) 凍結 provenance:sha256 + manifest + Tier-0 validator（reuse workloads_refined/tools/validate_trace.py）
   ↓
(4) 【必做】重生 hotset：2d/2e/2f 的 hotset 是「跑 workload → mincore」得來的
     → 換 workload 必須重生（run_experiment.py --regen-hotsets）
   ↓
(5) 跑矩陣：run_experiment.py run --workload <keys> --strategy <strats> --db orig,vacuum,ta
     write workload（YD/YE）走 aging 路徑
   ↓
(6) 聚合 + 重畫 paper 圖表，比對結論是否 hold
```

---

## 5. 【最容易被漏】Hotset 必須重生

prefetch 策略分兩類,遷移影響完全不同:

| 策略 | 選頁依據 | 換 workload 要重生嗎 |
|---|---|---|
| `layers_N`(2c) / 2a / 2b | **結構**(interior 頁按 offset),**不看 workload** | ❌ 不用(workload-independent) |
| **2d / 2e / 2f** | **access-pattern**(跑一次 workload → `mincore` 抓 resident 頁) | ✅ **必須重生**(hotset 綁 workload) |

→ 換成 refined 之後,**2d/2e/2f 的 hotset 全部作廢,必須用新 workload 重跑 `--regen-hotsets`**,否則你會拿舊 workload 的 hotset 去暖新 workload = 錯。這一步漏了,整個 e2e 結果無效。

---

## 6. 執行指令骨架(遷移後)

```bash
export EXPERIMENT_ROOT=/home/u03/sqlite-research-fork    # 指向本 repo 的 DB/workloads

# (4) 重生 hotset（新 workload 的 access-pattern hotset）
python3 run_experiment.py --regen-hotsets --workload YC,YC_u,...

# (5) 跑 read-only 矩陣（headline：A→YC, B→YC-u）
python3 run_experiment.py run \
    --workload YC,YC_u \
    --strategy baseline,layers_5,2d,2e_K10,2f \
    --db orig,vacuum,ta

# write workload 走 aging（YD/YE，不進 run 矩陣）
python3 run_experiment.py aging --workload YD --db orig

# (6) 聚合 + 重畫
python3 figures/01_page_distribution.py   # 等
```

---

## 7. Provenance / 驗證閘(遷移不能破壞的東西)

1. 每條 refined trace:`raw log sha256 + trace sha256 + manifest`(已有,gen_de.sh / gen_ycsb_trace.sh 產)。
2. 進矩陣前過 **Tier-0 validator**(notfound≤1%、op-mix、id 範圍)。
3. hotset 重生後 `--verify-frozen`(checksum)把關。
4. cold-clear 每 cell `verify_cold_pct≈0`,>1% 剔除(harness built-in)。
5. **10-seed sweep + bootstrap CI**(paper 的統計基準)——refined 每個 config 生 10 條 seed 變體(`gen_ycsb_trace.sh` 重跑 = fresh seed;凍結)。

---

## 8. 會變 / 不會變(預期)

| | 預期 |
|---|---|
| **會 hold** | interior skeleton `2d` 是 robust 贏家(結構性天花板律,§3.5)→ YC/YC-u 上應仍 −25~−30% warm e2e |
| **會變** | 絕對數字(換 generator);A 的 zipfian skew bonus(−36%)幅度依 YCSB scramble 分布而定 |
| **無法重現** | C 的 −75%/−55%(not-found artifact,真 YCSB 無此 workload) |
| **新增** | 整個 YCSB 正典 roster 的 coverage(YA/YB/YC-h sweep/YD/YE/YF)——比舊的更廣、有出處 |

---

## 9. 需要你拍板的決策

1. **決策 A(§3):C / C_hit 怎麼辦?**
   - (a) 保留為 Tier-2 mechanism probe,caption 標「非 YCSB / not-found artifact」;
   - (b) 從矩陣移除,headline 只跑 A→YC、B→YC-u;
   - (c) 換一個 YCSB workload 從別的角度測 tail-read(例如 YE scan,但那要 scan harness)。
   - **建議 (a)**:保留但誠實標,不丟資訊也不冒充 YCSB。

2. **決策 B:放置方式(§4 step 2)——複製到 `workloads/`(選項 α)vs 改 `WORKLOADS` 常數(選項 β)?**
   - **建議 α**:複製 + 改名對齊 registry key,`run_experiment.py` 一行都不改(surgical),舊 seed 機制照用。

3. **決策 C:roster 範圍——只重跑 headline(A→YC, B→YC-u),還是連整個 YCSB 正典(YA/YB/YC-h/YD/YE/YF)都跑?**
   - 前者快、對齊 paper;後者是 workloads_refined 的完整價值,但成本 ×N。

4. **決策 D:跑在哪個 root?** `EXPERIMENT_ROOT` 指向本 fork(有 test.db + refined traces)還是 sharing repo?

---

## 10. 交付物(執行後)

```
workloads/(或 workloads_refined/traces/)  ← 對齊 registry key 的 refined trace + sha256 + manifest
results/refined/                          ← 新矩陣的 per-cell 輸出(fq/e2e/majflt…)
results/refined/figures/                  ← 重畫的 paper 圖(page_distribution、e2e bar…)
REPORT_REFINED.md                          ← 「真 YCSB 上結論是否 hold」的對照報告
```

---

## 11. 一句話總結

**技術上 refined trace 是 pipeline 的 drop-in(格式相容 + DB id 對齊,都已驗證)。真正的工作不是「接線」,是三件事:(1) 把 paper 的 A/B/C/Z 對應到 YCSB——A/B 可以、C/C_hit 不行(§3);(2) 換 workload 後必須重生 2d/2e/2f 的 hotset(§5);(3) 誠實面對「數字會變、C 的 artifact 無法重現、但 interior skeleton 的結構性結論應該 hold」(§8)。** 先回答 §9 的四個決策,我就照這份計畫執行。
