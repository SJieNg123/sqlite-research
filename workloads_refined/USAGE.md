# workloads_refined — 使用指南

YCSB → SQLite workload 遷移管線。從真 YCSB 產出**帶 provenance、過驗證閘**的 harness-ready trace + headline DB + ρ 量測。

> 本檔為操作手冊。規範內容以 `ycsb_migration_spec_v4.md` 為準;本檔若與 spec 出入,以 spec + 實測為準。

---

## 0. 誠實範圍:兩半

| 半 | 狀態 | 能做什麼 |
|---|---|---|
| **Trace 遷移 + 驗證管線** | ✅ **現在就能用** | 從 YCSB 產出帶 provenance、過驗證閘的 harness-ready trace + headline DB + ρ 量測 |
| **計時實驗**(量 prefetch 效應) | 🔴 **被 Round 3a 校準擋住** | harness 會跑,但聚合延遲在本 host 上量不出 I/O 效應(正對照不動)。**還不能拿來下結論**——見 §7 與 spec §8.1 |

「產生並驗證 workload」= 可交付;「用它做計時實驗」= 尚未。下面 §1–6 是可用部分,§7 是被擋部分。

---

## 1. 管線形狀

```
真 YCSB (java Client + BasicDB verbose)
   │  -load →  raw/<NAME>_load.log   (universe,600k INSERT)
   │  -t    →  raw/<NAME>_run.log    (op stream,key-only,value-agnostic)
   ▼
[3] ycsb2trace.py   run.log → <NAME>.jsonl      (解析、fail-fast、算 op_mix)
   ▼
[4] keymap.py       jsonl + load.log → workload_<key>.txt   (YCSB key → dense rowid `read <id>`)
   ▼
[5] validate_trace.py   → .validation.json     (Tier-0 閘,fails loud)
   +  manifest.json      (sha256 provenance:raw log / trace / YCSB 版本)
```

核心紀律:**trace 檔就是 seed**(YCSB `ThreadLocalRandom` 無法設種子),所以誰產的、從哪個 raw log 來,全靠 manifest 的 sha256 追。

---

## 2. 一鍵路徑(會重跑 java)

`gen_ycsb_trace.sh` 跑完整 5 步。**注意:它重跑 YCSB java → 產生新隨機 trace**,會蓋掉 `raw/` 現有凍結 log。只有你要一條**全新** trace 時用:

```bash
cd workloads_refined
# 需 $HOME/ycsb-tools/jre/bin/java + jars(env/ycsb_env.txt 有 sha256)
./gen_ycsb_trace.sh  YC-hashed  yc  workloadc  zipfian  hashed  600000  80000
#                    <NAME>    <KEY> <WL>      <DIST>   <IO>    <REC>   <OPS>
```

參數順序:`<NAME> <KEY> <YCSB_WORKLOAD> <REQUESTDIST> <INSERTORDER> <RECORDCOUNT> <OPERATIONCOUNT> [extra -p props ...]`

> ⚠️ YR ρ-sweep 的 `RECORDCOUNT` 不手填——由 `yr_sweep.yaml` + `tools/calc_n.py` 由 W 現算(spec §2.2 / §4.5.3)。字面 N 不得出現在「給人複製」的指令裡。

---

## 3. 復用凍結 log 路徑(推薦日常用法)

`raw/` 已有凍結 log(YA / YB / YF / YC-h-hashed-hdf{0.01..0.50} / YC-h-ordered-hdf*)。**復用它們不重跑 java、保住 provenance。**

```bash
cd workloads_refined
NAME=YC-h-hashed-hdf0.10                          # raw/ 裡現成的一組
OPS=$(grep -cE '^READ ' raw/${NAME}_run.log)      # = 80000,不硬編

# [3] 解析 run.log → jsonl
python3 tools/ycsb2trace.py raw/${NAME}_run.log $OPS --workload workloadc --out /tmp/${NAME}.jsonl

# [4] key → dense rowid,產 harness 格式 `read <id>`
python3 tools/keymap.py --load raw/${NAME}_load.log --trace /tmp/${NAME}.jsonl --out /tmp/${NAME}.txt

# [5] 驗證(fails loud):notfound、skew、op_mix、id 範圍
python3 tools/validate_trace.py /tmp/${NAME}.txt --out /tmp/${NAME}.validation.json \
        --db-max-key 600000 --parse-losses 0 --label $NAME \
        --props "workload=workloadc,requestdistribution=zipfian,insertorder=hashed"
```

產物:`/tmp/YC-h-hashed-hdf0.10.txt`(80000 行 `read <id>`,id 1..600000)。

**工具 CLI 速查**

| 工具 | 必填 | 選填(default) |
|---|---|---|
| `ycsb2trace.py` | `log` `expected_ops` | `--out`(`-`)`--workload`(`''`) |
| `keymap.py` | `--load` `--trace` `--out` | `--insert-base`(None) |
| `validate_trace.py` | `trace` `--out` | `--db-max-key`(600000)`--parse-losses`(0)`--label` `--props` `--db` `--table`(items)`--claims-moving-hotspot` `--thresholds` `--hit-only` `--max-notfound`(0.01)`--segments`(10) |

RMW workload(workloadf)每 op 產 2 行(READ+UPDATE);validator 有 per-workload op-count 閘處理。

---

## 4. 建 headline DB + 幾何閘

```bash
# 建(schema id/k1/k2/payload,無 index);建完自動跑 §-1.1 幾何閘
python3 tools/build_headline_db.py --db /tmp/headline.db --rows 600000
#   → [PASS]×5: leaf_pages / depth=3 / skeleton / dbstat_record_bytes=75.6M / page_count=20035

# 單獨對任意 DB 跑閘
python3 tools/headline_db_gate.py --db /tmp/headline.db
```

閘擋:leaf 數、深度、骨架 bytes、**每列 record 寬(126B,唯一不量化的 row-width 檢查)**、整檔 page_count。任何一個超容忍 → FAIL。

> schema 說明:`fieldcount=1` 是 YCSB log-size 旋鈕(spec §2.2),**不是** DB schema 宣告。真實 DB = `items(id INTEGER PRIMARY KEY, k1 TEXT, k2 TEXT, payload BLOB)`(headline = rowid table;YR 加 `WITHOUT ROWID`)。harness init 會 prepare 引用 k1/k2 的語句,故這兩欄必須存在(builder↔harness 合約,見 `tests/test_db_smoke.py`)。

---

## 5. 量 ρ(interior-fault fraction,§4.5.4 迴歸的 x 軸)

```bash
python3 tools/calc_rho_measured.py --db /tmp/headline.db --trace /tmp/YC-h-hashed-hdf0.10.txt
#   → ρ = |interior| / (|interior|+|leaf|) 觸及頁,headline ≈ 0.27%
```

先斷言查詢是 INT-PK point query(EXPLAIN QUERY PLAN 無 INDEX、無多樹),再從 dbstat 建 dense-rowid key→page 映射,不解析 b-tree。

---

## 6. YR ρ-sweep 工具(WITHOUT ROWID,幾何驗證)

```bash
# 每個 W 的 fanout f、overflow、depth(200k 原型,幾分鐘)
python3 tools/verify_yr_geometry_v4.py --tol 0.1
#   → W=101→f≈33, 126→27, 226→16, 326→12(±10%,overflow=0)= 簽名 D7

# 由 W 現算 N(不硬編;N = leaf_pages × rows_per_leaf(W))
python3 tools/calc_n.py --all --yaml yr_sweep.yaml

# 單一原型(自訂列寬)
python3 tools/build_yr_prototype.py --db /tmp/yr.db --rows 200000 --keylen 100 --vlen 126
```

---

## 7. 🔴 harness:會跑,但**還不能用來下計時結論**

```bash
# 編(免權限)
gcc -O2 -D_GNU_SOURCE -I static_experiment/tools/vendor/sqlite \
    static_experiment/tools/src/benchmark_harness.c \
    static_experiment/tools/vendor/sqlite/sqlite3.c -o /tmp/bh -lpthread -ldl -lm

# 跑一條 trace
/tmp/bh --db /tmp/headline.db --workload /tmp/YC-h-hashed-hdf0.10.txt \
        --cold-advice none --output /tmp/op.csv --record-dir /tmp/runs
```

輸出:per-op CSV(`op_no,op_type,target_id,rows_returned,bytes_returned,elapsed_ns,majflt_delta,minflt_delta`)+ stderr summary(`ops= avg_latency_us= total_majflt= total_minflt= first_query_latency_us=`)。

`--cold-advice`:`none`(現狀)/ `cold`(MADV_COLD)/ `pageout`(+PAGEOUT)/ `dontneed`(+DONTNEED,最冷)。root 級全域清快取走 `--drop-caches-script /usr/local/sbin/drop-caches`(setuid,免 sudo)。

**🔴 為什麼還不能下結論(spec §8.1,measured 未簽)**
本 host(60GB RAM)上 79MB DB 全駐 page cache。試遍 `madvise(dontneed/pageout)` / setuid `drop-caches`(全域 cache 49.6→2.3GB 確清)/ cgroup `MemoryMax=48M` / 組合——**聚合 `avg_latency` 鐵打 2.2–2.3µs、`majflt`=0、跑完 20035/20035 全駐**。只有 `first_query`(單一冷讀)動(2–4×)。

- 機制:SQLite 開檔走 `pread()` 把頁灌回 cache(計 minflt 非 majflt),80k 暖查詢攤銷冷讀。
- 後果:量到「效應≈0」與 headline 預測(ρ≈0.27%)**數字一致但成因混淆**——分不清「prefetch 本就小」還是「根本沒 I/O 可量」。
- **前置閘**:Round 3b/4 計時開跑前,正對照必須先動。候選協定:
  1. 小批冷讀:每批 K 個冷讀、批間 `drop_caches`,量批冷延遲(不靠 80k 暖迴圈)。
  2. DB ≫ RAM:工作集大到裝不進 60GB(Round 4 的 1.2GB 仍不夠)。
  3. `drop_caches` 後於記憶體受限 scope 內重讀 + 驗 `majflt>0` 或 child 的 `/proc/self/io read_bytes>0`。

---

## 8. 測試(改工具後先跑)

```bash
cd workloads_refined
for t in db_smoke headline_db_gate calc_rho_measured validator_gates keymap; do
  python3 tests/test_$t.py
done
```

每個閘都有 fire test(證它會 FIRE + pass-path 證不誤殺)。`test_db_smoke.py` 是 builder↔harness 合約閘(跑真 harness,good DB→exit 0、少一欄的 grave→非零)。

---

## 一句話總結

- **要一條可信、可複現、帶 provenance 的 YCSB→SQLite workload trace + DB + 幾何/ρ 數字** → 現在就能用,走 §3–6。
- **要用它量 prefetch 值不值得(計時)** → 先過 §7 的正對照閘,否則數字不可解讀。
