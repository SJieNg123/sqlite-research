# runs_page_split — 會「搬動頁面」的 churn，以及它如何讓凍結的熱頁清單失效

## 背景：這個實驗要補的洞

prefetch 的做法是：在 t=0（暖機那一刻）拍下一張**靜態的 hotpages 清單**（哪些頁是熱的），之後每次冷啟動就照這張
清單把熱頁預載進來。問題是——**資料庫會一直被寫入改動，這張不再更新的清單，會不會過期、指到錯的頁？**

既有的三個 churn 系列（`runs_access_churn` / `_a` / `_b`）都重放同一份 `page_churn_write.txt`。它的寫入是
**layout-preserving（不重排頁面）**的：

- `INSERT` 的 rowid 自增、**接在檔案尾巴**（id 600001+）；
- `DELETE` 只把 cell 標成空位、**不立即合併頁**；
- `UPDATE` payload 固定 100 B，**原地改寫**。

逐 checkpoint 比對 `classify_pages` 快照可驗證：原本的 **26,331 頁從頭到尾 0 變動**，新頁全接在尾巴。也就是說，
那些實驗測出「靜態清單不 decay」，**是因為它們用的 churn 本來就動不到清單覆蓋的頁**——不是清單通過了壓力測試。

本實驗補上缺的反例：**一個會逼熱葉分裂、把既有 row 搬到新頁的 churn**，並量測清單是否因此 decay。

## 機制：怎麼讓「既有頁」真的搬動

`items` 是 rowid 表（`id INTEGER PRIMARY KEY`），60 萬筆**連續 id**，payload **固定 100 B**。一個葉頁（leaf page，
存實際 row 的 B-tree 頁）大小固定 4 KiB，裝約 22 筆（22 × ~180 B ≈ 4 KiB）——**接近全滿**。

要讓既有頁搬動，有兩條路：

1. **往熱區「中間」insert**（讓熱葉爆掉分裂）——**走不通**：harness 的 `insert_item` 忽略 workload 給的 key、改用
   自增 id 接尾巴（[sqlite_prefetch_churn_experiment.py](../sqlite_prefetch_churn_experiment.py) 的 replay 迴圈），
   你無法指定插入位置，除非改 parser。
2. **把既有 row「撐大」**——**可行且只需一個旋鈕**：`update_item` 寫的是 `--payload-size` 大小的 blob。把它從 100
   調到 **512**，`UPDATE` 就把命中的 row 從 ~180 B 撐到 ~580 B。葉頁本來近滿，多出的 ~400 B 塞不下、而頁大小固定
   不能變大 → **SQLite 觸發 leaf split：配一個新頁、把原頁約一半的 row 搬過去**。t=0 算進清單的 rowid→page 對照，
   對「搬到新頁」的那些 key 就指錯了。

所以這次 churn = **「對熱 key 做 UPDATE」+「payload 512 撐大 row」**，churn 引擎一行不用改。

## 實驗設計（3 個 arm）

共同條件：量測讀取用 Workload A（`workload_a_zipfian.txt`），prefetch 用 t=0 靜態 hotpages，10 checkpoint × 5000 ops。
寫入 workload 一律用 **`generated_workloads/page_split_write.txt`**——把 `workload_a_zipfian.txt` 的 read key 直接轉成
`update <key>`，讓寫入**精準命中清單預載的那幾個熱葉**（用原本散射式的 `page_churn_write.txt` 幾乎打不到熱葉，
coverage 不會動）。

| arm | payload | 預期 |
|---|---|---|
| `2e_k10_p512` | 512（撐大→分裂）| coverage **崩**（會搬頁的主案例）|
| `2e_k10_p100` | 100（不撐大）| **對照組**：原地改寫不分裂，coverage 應**平**（隔離出「分裂」才是主因）|
| `2d_p512` | 512 | interior-only 清單（完整 residency dump）在同樣撐大 churn 下 |

## 新增指標：`staleness_summary.csv`（`hot_key_coverage`）

既有指標（latency、majflt）量的是「快不快」，量不出「清單對不對」。因此新增
[measure_staleness.py](../measure_staleness.py)：

- 沿用 [gen_hotleaves.py](../../prefetch_access/runs/gen_hotleaves.py) 的方法（讀每個葉頁的 first_rowid、用 bisect
  做 `page_for_key`），在**當下這個 churn 過的 DB** 上重建 rowid→leaf 對照。
- 算 **`hot_key_coverage`** = Workload A 的 read ops 中，**「現在所在的葉頁仍在凍結清單內」的比例**。高 = 清單還準；
  掉 = 清單過期。
- 透過**新增、預設關閉**的 `--staleness-*` flag 接進 churn harness，每個 checkpoint 算一次。預設關 → 既有 runs
  完全不受影響（已用「不帶 flag 的原樣呼叫」回歸測試確認）。

## 結果

**`hot_key_coverage`（讀取仍命中凍結清單的比例）：**

| 寫入量 ops | `2e_k10_p512`（撐大→分裂）| `2e_k10_p100`（不撐大，對照）|
|----:|:--:|:--:|
| 0（baseline）| 0.241 | 0.241 |
| 5,000  | 0.231 | 0.241 |
| 10,000 | 0.112 | 0.241 |
| 15,000 | 0.065 | 0.241 |
| 25,000 | 0.049 | 0.241 |
| 50,000 | **0.009** | **0.241** |

→ 會搬頁的 churn 把命中率**從 24.1% 砸到 0.9%（約 27 倍衰退）**；**同樣打熱 key 但不撐大**的對照組**全程平平 24.1%**。
**所以 decay 的主因是「頁分裂」，不是「打到熱 key」。**

**頁面佈局（`interior_summary.csv`）：** `page_count` 在 p512 下 26,331 → **28,779**，而 p100 下只到 26,619；且
**`row_count` 全程 600,000 不變**（沒有 insert/delete），所以多出來的 ~2,448 頁**純粹來自 split**。對照最良性的
`runs_access_churn_a`：只有尾巴 append、coverage 平 0.241。

**`2d_p512`**（interior-only，frozen 清單是完整 residency dump、含 3,327 個葉頁）：coverage **1.00 → 0.59**——比
2e 的 top-10 緩（清單越大越有冗餘），但仍是明確的真實 decay。

**VACUUM（更極端的 bonus，零 churn）：** 對一個**完全沒被 churn 過**的 DB 直接 `VACUUM`——**一筆 row 都沒改、只重編
所有頁號**——coverage **0.241 → 0.003** 瞬間崩。靜態的「頁號清單」撐不過一次重建。

### 注意：latency / `majflt` 在這裡**不是乾淨的訊號**

`first_query_latency_us` 在 ~15–25 µs 噪動、`total_major_page_faults` 只小幅上升（181 → 287，跟著變大的 DB 走），
**並沒有清楚反映 decay**。原因是這台 harness 的無 sudo 冷啟動（`posix_fadvise`/`madvise`）沒把撐大的 DB 完全趕出
page cache，benchmark 跑得偏 warm，清單失準在 wall-clock 上沒被罰到。**decay 的結論請看 `hot_key_coverage`（直接量
清單正確性），不要看 latency 欄。**

## 重現步驟

```sh
cd /home/u03/sqlite-research-project-sharing/prefetch_churn

# (1) 生成「打熱 key 的 UPDATE」寫入 workload（若不存在）
python3 - <<'PY'
n=0
with open("generated_workloads/workload_a_zipfian.txt") as f, open("generated_workloads/page_split_write.txt","w") as o:
    for line in f:
        p=line.split()
        if len(p)>=2 and p[0]=="read":
            o.write(f"update {p[1]}\n"); n+=1
            if n>=60000: break
PY

# (2) 跑 3 個 arm（~15 分鐘）
bash runs_page_split/run_page_split.sh

# (3) 看 decay：p512 一路下掉、p100 全程平
column -t -s, runs_page_split/2e_k10_p512/staleness_summary.csv
column -t -s, runs_page_split/2e_k10_p100/staleness_summary.csv

# (4) VACUUM demo：未 churn 的 DB，VACUUM 前後比對
cp test.db /tmp/v.db
python3 measure_staleness.py /tmp/v.db ../prefetch_access/runs/hot2e_A_orig_K10.csv generated_workloads/workload_a_zipfian.txt 20000
python3 -c "import sqlite3;c=sqlite3.connect('/tmp/v.db');c.execute('VACUUM');c.close()"
python3 measure_staleness.py /tmp/v.db ../prefetch_access/runs/hot2e_A_orig_K10.csv generated_workloads/workload_a_zipfian.txt 20000
```

## 結論

凍結 hotpages 清單**只在「churn 不重排頁面」時才安全**。一旦寫入真的搬動熱 row——**row growth 造成的 leaf split，
或一次 VACUUM**——靜態清單就會嚴重 decay（coverage 24% → 0.9%；VACUUM 下 → 0.3%）。原本「churn 下不 decay」的結論，
是 layout-preserving 寫入組合的產物，**不是一個普遍性質**。

---

## 附錄：實作過程（含走過的彎路）

照真實順序記錄，包含失敗的第一次：

1. **先確認引擎能不能表達「搬頁」**：讀 schema 與 replay 迴圈，判斷「插中間」走不通、「撐大 row 觸發 split」可行且
   只需 `--payload-size` 一個旋鈕。
2. **補一把直接量 decay 的尺**：寫 `measure_staleness.py`，用 additive、預設關閉的 flag 接進 harness。先單獨驗證——
   對未 churn 與「良性 churn」的 DB 量都是 0.241（尺正確，也復現「良性 churn 不 decay」）。
3. **第一次 smoke test 失敗**：偷懶用舊的 `page_churn_write.txt` + payload 512，coverage **卡在 0.241 不動**。診斷：
   舊 workload 的 UPDATE 均勻散射，那 10 個熱葉只佔全部葉頁 ~0.05%，幾千筆改動幾乎碰不到 → **「有頁分裂」不等於
   「熱葉分裂」**。
4. **對症下藥**：生成 `page_split_write.txt`（把 Workload A 的熱 key 轉成 `update`），讓寫入精準命中熱葉。再試：
   coverage 24% → 11% → 6.5%，decay 出現。同時發現 majflt=0（冷啟動沒真冷）→ 確定 **latency 不可信、只認 coverage**。
5. **加對照組釘死因果**：`2e_k10_p100`（同樣打熱 key、payload 100、不分裂）coverage 全程平 → 證明**兇手是 split，
   不是 hot-key targeting**。
6. **跑全量 + VACUUM bonus**：3 arm × 10 checkpoint 背景跑；VACUUM 對未 churn DB → 0.3%。
7. **回歸測試 + 誠實標註**：用不帶 staleness flag 的原樣呼叫確認既有 runs 行為不變；把「latency 不可信」「先前
   runs_access_churn 那根 212 µs 不是 split、只是雜訊（佈局快照顯示無頁移動）」如實寫進結論。
