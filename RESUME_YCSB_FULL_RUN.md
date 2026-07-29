# RESUME — 明天開跑「原生 YCSB 全套 paper 重現」

> 存檔於今天。明天用這份直接接續:把 paper 全套實驗在**全 17 個原生 YCSB workload** 上跑完。

---

## 0. 一句話狀態

**環境全部建好、runner 就緒、來源透明。明天只差「開跑 + 聚合」。**

---

## 1. 已就位(不用再建)

| 項目 | 狀態 |
|---|---|
| **透明 runner** | `run_experiment_ycsb.py`(複製自 `run_experiment.py`,**只讀 `workloads_refined/traces/`**,原生 YCSB) |
| **17 個 workload** | `workloads_refined/traces/workload_*.txt`,全部就位、Tier-0 PASS |
| **3+1 個 DB** | `pipeline/preparation/layout_rewriter/runs/{test,test_vacuum,test_typeaware,test_db_1gb}.db`(gitignore,可重建) |
| **classify CSV** | `classify_{before,vacuum,after,1gb}.csv`(已重生匹配 DB) |
| **binary** | benchmark_harness / warmer / layout_rewriter / classify_pages / residency_checker 全編好 |
| **舊 `workloads/`** | 已刪除(避免來源混淆) |

### runner 的 workload registry(17 個)
```
讀 12(→ read-latency 矩陣):
  YC(zipfian)  YCu(uniform)
  YCh01/05/10/20/50(hotspot-hashed × hdf)
  YCo01/05/10/20/50(hotspot-ordered × hdf)
寫 5(→ churn/aging):
  YA(50/50) YB(95/5) YF(rmw)  → churn
  YD(read-latest+insert) YE(scan+insert) → aging
```

---

## 2. 明天要跑的:paper 全套 × 全 17 workload

**scope = 全部(用戶要跑全部,~12-15 小時)。** 全程背景 + monitor,不用盯。

### Phase A — 讀取矩陣(12 個讀取 workload × 3 layout)Fig 13/14
```bash
export EXPERIMENT_ROOT=/home/u03/sqlite-research-fork
RD="YC,YCu,YCh01,YCh05,YCh10,YCh20,YCh50,YCo01,YCo05,YCo10,YCo20,YCo50"
python3 run_experiment_ycsb.py run --regen-hotsets --workload $RD --db orig,vacuum,ta --regen-k 10,500 --yes
python3 run_experiment_ycsb.py run --workload $RD --db orig,vacuum,ta \
   --strategy layers_5,layers_92,2d,2e_K10,2e_K500,2f_slru --outdir /tmp/ycsb_main --yes
```
> 注意:regen 後要建 access/runs 的 hotpages symlink(見 §3 踩過的坑)。

### Phase B — ablation(Fig 17,每個讀取 workload)
```bash
python3 run_experiment_ycsb.py run --workload YC,YCu,YCh01 --db orig \
   --strategy 2d,leaf_freq_K10,leaf_rand_K10,2e_K10 --outdir /tmp/ycsb_ablation --yes
```

### Phase C — RAM pressure(Fig 16)
```bash
for M in 16M 12M 8M; do
  python3 run_experiment_ycsb.py run --workload YC,YCu,YCh01 --db orig \
     --strategy 2d,2e_K10,2f_slru --mem-limit $M --outdir /tmp/ycsb_ram_$M --yes
done   # none 用不加 --mem-limit 的一次
```

### Phase D — 10-seed(Table seeds)
```bash
# 每個讀取 workload 生 10 條 fresh YCSB trace 到 workloads_refined/traces/seeds/
#   workload_<key>_1..10.txt,然後迴圈 regen+run(見 §3 的 seed_sweep.sh 模式)
```

### Phase E — size-scaling 1gb(6M-row DB 已建)
```bash
# 每個讀取 workload 需要 6M-keyspace trace(cp 到對應 workload 檔再 --db 1gb)
python3 run_experiment_ycsb.py run --workload YC --db 1gb --strategy layers_5,2d,2f_slru --yes
```

### Phase F — churn(YA/YB/YF update 流當 ager,量各讀取 workload)
```bash
for W in YA YB YF; do
  grep '^update' workloads_refined/traces/workload_$W.txt > /tmp/churn_write.txt
  # 指到 churn_write,run churn --workload YC,...
done
```

### Phase G — aging(YD/YE)
```bash
python3 run_experiment_ycsb.py aging --workload YD,YE --db orig,vacuum,ta --reps 5
```

### Phase H — cadence
```bash
python3 run_experiment_ycsb.py cadence --workload YC --db orig
```

---

## 3. 踩過的坑(明天別再踩)

1. **regen 後要建 hotpages symlink**:`strategies/access/runs/hotpages_<key>.csv` → `../../../strategies/slru/runs/hotpages_<key>.csv`(regen 只寫 slru/runs;access/runs 靠 symlink)。每個新 workload key 都要建 `""/"_vacuum"/"_ta"/"_1gb"` 四個。
2. **classify CSV 不要加 echo header**:`classify_pages` 自己輸出 header,`>` 不要再 echo。
3. **6M cap(RAM pressure)太慢**:thrash,收在 8M 即可,趨勢已足。
4. **1gb 的 2d 單次量測**受本機全-resident 影響(62GB RAM + readahead 讓整個 DB resident)→ 穩健結論是 2f deliver trap,不是 2d 回歸。
5. **drop-caches 是 setuid root**,不用 sudo。
6. **cold_pct>1% 的 cell** 由 runner 彙整時剔除(post-hoc),正常。

---

## 4. 已完成的(舊 build,可當對照/直接沿用)

**已跑過的 YCSB 結果**(單一 workload YC/B,非全 17):在 `/tmp/{refined_full,ablation_yc,ram_*,seed_*,size_1gb}/summary.csv` + `results/{aging,churn,cadence}/`。
**已產報告**:`results/refined/REPORT_REFINED.{md,pdf}` + 10 圖(fig1-4,13,14,16,17,seeds_ci,size_scaling)。
> 明天的全 17-workload 版會產一份新的 `results/refined_full/REPORT_YCSB_FULL.md`,不覆蓋舊的。

---

## 5. 聚合 + 出圖 + 報告(全跑完後)

沿用 `results/refined/` 的圖腳本模式(matplotlib + Noto CJK 字型在 `transient_method/runs/headline/fonts/`),`md2pdf` 出 PDF。每個 Phase 一組圖 + 一份 `REPORT_YCSB_FULL.md`。

---

## 6. 明天怎麼接續

跟我說「**接續 RESUME_YCSB_FULL_RUN.md 開跑**」即可。我會:
1. 確認環境沒漂(binary/DB/trace 都在)。
2. 依序啟動 Phase A-H(背景 + monitor)。
3. 全部跑完聚合成 `REPORT_YCSB_FULL`(md + PDF)。
```
export EXPERIMENT_ROOT=/home/u03/sqlite-research-fork
python3 run_experiment_ycsb.py --help   # 確認 runner 還在
```
