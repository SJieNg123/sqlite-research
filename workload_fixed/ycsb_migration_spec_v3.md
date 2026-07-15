# YCSB-based Workload Generation — Migration Spec **v3**

> **v3 相對 v2 的主要修訂**
> 1. **新增 §00 DECISIONS（decision record）**：所有未決事項集中管理。agent 規則：有記錄者直接執行，無記錄者 append 一條 `OPEN` 後停下，不得口頭追問。
> 2. **§3.4 回填舊 DB 實測值**：骨架實測 **204KB**（v2 悲觀估計 1.6MB 的 1/8），items fanout ≈ **392**。「效應在對齊配置下 ≈ 0」從擔憂升級為**理論預測**。
> 3. **新增 §3.5 效應天花板帳（ceiling law）**：冷啟動、cache 充足時 benefit ≤ ρ ≈ 1/(1+fanout)。這一條把 §-1.2 的定性敘述升級為**定量律**，並直接推出：對齊配置的天花板 ≤ ~1%，**null 是預測，不是意外**。
> 4. **§3.4 目標解耦**：「對齊舊 DB」（目標 A：歷史橋接）與「效應物理上存在」（目標 B：效應存在性）是兩個目標，v2 把它們綁在同一個 `fieldlength` 旋鈕上造成假二選一。v3 一個目標一個 config。
> 5. **新增 §4.5 YR regime arm**（Tier 1）：`WITHOUT ROWID` + 保序 key 膨脹（fanout 392→~38）＋ **YR-P cache-pressure 軸**（cgroup `MemoryMax`）。天花板從 ~1% → ~2.6%（YR）→ 每次冷 descent (d−1)/d（YR-P）。
> 6. **§-1.1 / §2.5 空格已填**（見 §00 DECISIONS）：headline field size = 對齊實測 126B；YD/YE rowid = 選項 (b)。
> 7. **§8 新增 fixed-horizon ABC fallback**：YR/YR-P 之下 convergence-based settling point 可能不觸發，預先註冊 fallback。
> 8. **§6 加入進度標記**：量測（原步驟 1）已完成，spec 從純 forward-looking 對齊實況。
> 9. **§10 新增 10.3（YR 原型驗證）與 10.4（cgroup 公平性 sanity check）**。

---

## 00. DECISIONS（decision record）—— agent 從這裡開始

> **Agent 常設規則**：
> 1. 狀態為 `CLOSED` 的決定：**直接執行，不再詢問**。
> 2. 遇到 spec 中任何未決事項或新的岔路：以本表格式 **append 一條 `status=OPEN` 的項目**（含選項與你的建議），然後**停在該任務**，繼續其他不受阻的任務。**不得在對話中口頭追問，不得代填。**
> 3. `CLOSED (pending X)`：可以開始準備工作（寫工具、寫測試），但在 X 通過之前不得跑正式實驗。

| # | 問題 | 選項 | 決定 | 理由 | 狀態 |
|---|---|---|---|---|---|
| D1 | §-1.1 headline field size | (i) YCSB 預設 10×100B；(ii) 對齊舊 DB 實測 | **(ii)** `fieldcount=1`，harness row payload = **126B**（對齊實測 75,600,000B / 600,000 rows） | regime 探索責任已轉移給 YR/YR-P（D3/D5），headline 不再背這個負擔；對齊是唯一不引入 confound 的選項。**預期效應 ≈ 0（§3.5 天花板 ≤ ~1%），此 null 為 negative control，一併承諾** | **CLOSED** |
| D2 | §2.5 有 insert 的 workload（YD/YE）rowid 方案 | (a) sparse rowid；(b) 預留 rank 空間；(c) TEXT PK WITHOUT ROWID | **(b)** | (a) 的 9-byte varint 破壞與無 insert 組可比；(c) 已由 YR（D3）承擔且與 YD 的目的（moving hotspot）無關 | **CLOSED** |
| D3 | YR regime arm 的 schema 參數 | key 寬度 × recordcount × value 大小 | **key 定長 100B（保序膨脹，§4.5）、`recordcount=5,000,000`、value=126B**（與 headline 同 payload）。預期：fanout ≈ 38、leaf ≈ 294k、interior ≈ 8k 頁 ≈ **32MB 骨架**、depth ≈ 5、DB ≈ 1.2GB | fanout 是 ρ 天花板的唯一槓桿（§3.5）；value 維持 126B 讓 YR 與 headline 之間只差 key 表示 | **CLOSED (pending §10.3 原型驗證)** |
| D4 | YR 的 `operationcount` | — | **OPEN**。建議：600,000（維持 headline 的 ops/record ≈ 13%），並以 §10.3 原型的收斂行為校正 | settling window 需要覆蓋足夠 fault-in 量 | **OPEN** |
| D5 | YR-P 的 `MemoryMax` 掃描點 | — | **OPEN**。建議：{∞, 128M, 48M, 16M}（對應 R = 骨架/file-cache ≈ {0, 0.25, ~0.7, 2}），R 以 `memory.stat` 的 file-backed 實測值為分母回報 | 見 §4.5.3 公平性規則 | **OPEN** |
| D6 | fixed-horizon ABC 的 K（§8） | — | **OPEN**。建議：前 50,000 ops（headline）／前 200,000 ops（YR），**跑實驗前 commit** | convergence 不觸發時的 fallback，不能事後選 K | **OPEN** |

---

## -1. 預先承諾（Pre-registration）—— 先讀這一節

**這一節必須在跑任何實驗之前 commit，並以 git 時間戳為證。**

v1 spec 隱含一個假設：換成 YCSB 之後，結論會保留下來。§3.1 甚至已經先寫好了勝利宣言的句型（"the benefit rises from X% to Y%"）。**v3 更新：這個假設已被實測 + §3.5 天花板帳直接否定**——對齊舊 DB 的配置下，骨架實測僅 204KB、fanout ≈ 392，冷啟動收益天花板 ≤ ~1%。**headline 的 null 不再是風險，是理論預測。**

如果不預先承諾，當 headline 顯示效益 ≈ 0 時，會有強烈誘因去「再找一個設定」——**那正是這次遷移要根除的失效模式，只是換了位置重生**。換 generator 堵不住它，換規則才行。v3 的做法是反過來：**把「找一個效應存在的設定」本身變成一個預先註冊、有物理理由的 arm（YR / YR-P，§4.5），而不是事後的 fishing。**

### -1.1 承諾事項

| 項目 | 承諾內容 |
|---|---|
| **Headline 配置** | `YC-hashed`（workloadc + `requestdistribution=zipfian` + `insertorder=hashed`），schema 對齊舊 DB：dense rowid、`fieldcount=1`、row payload = **126B**（D1）。預期 leaf ≈ 20k ± 5%、depth = 3、骨架 ≈ 205KB ± 10%（以 §3.4 實測為錨） |
| **Headline 預測（新增）** | **效應 ≈ 0**（天花板 ≤ ~1%，§3.5）。Wilcoxon 預期不顯著。此 arm 的角色 = **negative control**：若量出顯著大效應，優先懷疑 measurement pipeline，而非慶祝 |
| **Regime arm 配置** | `YR` / `YR-P` 依 §4.5 與 D3–D5。預測見 §-1.4 |
| **不得事後更換** | headline / YR 配置一旦 commit，不因結果好壞更換。若有正當理由更換，必須在論文中揭露原配置的結果 |
| **主要指標** | area-between-curves（ABC），settling point 依既有 convergence-based 定義；**fallback = fixed-horizon ABC（K 依 D6，先 commit）** |
| **統計檢定** | paired Wilcoxon signed-rank，n = trace 數（見 §8）。α = 0.05，雙尾 |
| **樣本數** | 見 §9 分層表。**不得看到結果後追加 trace 直到顯著** |

### -1.2 從「負面結果預備敘述」升級為「天花板律」（v3）

v2 在這裡放的是一段定性的降級敘述。v3 用 §3.5 的帳把它升級成**定量主張**，論文敘述改為：

> *"For cold-start point queries with ample cache, the benefit of interior-node prefetching is structurally bounded by the interior-to-total fault ratio ρ ≈ 1/(1+fanout). Our production-aligned configuration (fanout ≈ 392) has ρ ≤ ~1%; the measured null is thus a **prediction of the ceiling law**, not an absence of effect. Lowering fanout (YR: wide-key index-organized tables, fanout ≈ 38) raises the ceiling to ~2.6%, and inducing cache pressure on the skeleton (YR-P) moves the system into a re-faulting regime where each cold descent repeatedly pays serialized interior misses, with per-query ceiling (d−1)/d. We therefore report **the ceiling law plus its verification at three operating points**, rather than a single headline speedup."*

**這比一個泡沫數字、也比一段道歉式的 applicability condition 都更有價值**：它交付的是一條律 + 三個落點的驗證。null 的角色從危機 → negative control → 律的第一個資料點。

### -1.3 形容詞禁令（自 v1 §5 提升為全域規則）

> **任何 workload 的宣稱（"churn-resilient"、"hot-tail"、"skewed"、"robust"）都必須對映到 Tier 0 validator 裡的一個數字。沒有對應數字的形容詞，不准出現在論文裡。**

補充兩條：

- **"robust" 的用法收窄**：跑 N 條 trace 只能支持「對 workload 內變異穩健」。它**不能**支持「對參數選擇穩健」。這兩件事在 reviewer 眼裡是分開的，論文中不得混用。
- **skew 一律引實測值**，不得引用 `zipfianconstant`（原因見 §3.2）。

### -1.4 各 arm 的預先註冊預測（v3 新增，跑前 commit）

| arm | ρ 天花板（§3.5） | 預測 | 若預測落空的解讀（現在寫好） |
|---|---|---|---|
| YC-hashed（headline） | ≤ ~1%（fanout 392） | 效應與 0 不可區分 | 量出顯著大效應 → **懷疑 pipeline**（如 drop_caches 不完全、兩臂 DB 不一致），驗 §5 的 page_count/fill/depth 三數字 |
| YR | ≤ ~2.6%（fanout ~38） | 效應 ∈ (0, 2.6%]，若量測噪音 < ~1% 則顯著 | 不顯著 → 報告「與天花板一致，效應量低於偵測極限」，**不追加 trace** |
| YR-P | 隨 R = 骨架/file-cache 上升；R ≥ 2 時每次冷 descent 上限 (d−1)/d = 80% | **方向承諾**：效益隨 R 單調上升，R ≥ 2 時達雙位數。幅度為 exploratory，不做點預測 | 非單調 → 報告原始曲線並分析（如 WILLNEED 預讀頁被提前逐出，§4.5.3-iii，這本身是 finding） |

---

## 0. 目標

把 headline 結論的 workload 來源從「自造 generator」換成「公認 workload 的 trace」，讓下列失效模式在**結構上**不可能發生。

| 已發生的坑 | 來源 | YCSB 是否解掉 | v2/v3 修正 |
|---|---|---|---|
| C 的 −75% 來自 out-of-range not-found 撞最右葉 | 自造 key range `[590000, 609999]` 超過 DB 上限 | ✅ 解掉，但**理由與 v1 所寫不同** | 不是靠 `recordcount` 界定。`keychooser` 的上界其實是 `insertstart + insertcount + expectednewkeys`（**刻意超出**現有 keyspace）。真正擋住 not-found 的是 `nextKeynum()` 的 **rejection loop**（`do{...}while(keynum > lastValue())`）。代價：實際分佈是「Zipf 條件於 keynum ≤ lastValue」，非純 Zipf → **只准引實測分佈** |
| churn「韌性」宣稱，實際 hot page 位移 = 0 | 自造 churn 用抽樣不放回 → 根本沒有 hot set | ⚠️ 半解 | YCSB workload D (`latest`) 有天然 moving hotspot，但**不會自動驗證**位移真的發生 → 仍需 Tier 0 檢查（`hotset_jaccard_series`） |
| tail 範圍是 knife-edge，參數在驅動結論 | 自造參數沒有外部錨點 | ⚠️ **v1 高估了** | YCSB 的公信力只覆蓋 **key 分佈**。`fieldlength` / `zeropadding` / schema / load order 仍然全部是你選的，而且**每一個都影響 page layout**。真正的解藥是 §-1 預先承諾，不是換 generator |
| — | — | ❌ **新坑（v1 已標，但機制寫錯）** | `insertorder` 對 `zipfian` **無效**，只對 `hotspot` / `latest` 有效。見 §3.1 |
| — | — | ❌ **新坑（v1 未發現）** | `insertorder` 同時決定 load 階段的物理佈局（fill factor 100% vs 69%），是兩臂間的隱藏 confound。見 §3.3 |
| — | — | ❌ **新坑（v1 未發現）** | 「用 TEXT PRIMARY KEY」會把單棵 rowid B-tree 換成「rowid table + index B-tree」= 每次查詢穿兩棵樹 → 與舊 A/B/C 完全不可比。見 §2.5 |
| **headline 效應在對齊配置下物理上趨近 0** | **舊 DB 自身處於 null regime（骨架 204KB、fanout 392）** | ❌ **v3 新坑（v2 §3.4 有預感，實測證實且加重 8 倍）** | **不能靠「換設定」解，靠 §3.5 天花板律 + §4.5 YR/YR-P 把 regime 本身變成自變數。§-1.4 預先承諾各 arm 預測** |

---

## 1. 架構：三層，不要混

```
Tier 0  Trace Validator   ── 所有 trace（不論來源）都必須通過，才能進實驗
Tier 1  YCSB-generated    ── 唯一可以做「一般性宣稱」的來源（headline / abstract / 摘要圖）
Tier 2  自造 mechanism probe ── 只能做機制敘述，論文中必須標 "mechanism probe, not a general result"
```

### 1.1 規則

- **Tier 2 的數字不得出現在 abstract、結論、或任何沒有 "probe" 字樣的圖表 caption 裡。**
- **Tier 2 的入場條件（v2 收緊）**：每一條 Tier 2 workload 必須
  1. 通過 Tier 0 validator 的**全部**檢查（不是子集）；
  2. 其「所探討的機制」對應到 validator 的一個具體數字；
  3. **`notfound_rate ≤ 1%`**。未通過者一律退場，**不得以 probe 名義保留**。

> **為什麼收緊**：v1 允許舊 workload C 降級為 Tier 2 保留。但 C 的 −75% probe 的不是「一個機制」，而是「一個實作錯誤造成的偽訊號」。把它留在 Tier 2 等於給錯誤數字一個合法的續命位置。
> **按 v2 規則，舊 C 出局。** `C_HIT` 可進 Tier 2，前提是先修正下列 confound。

> **v3 註**：YR / YR-P 是 **Tier 1**，不是 Tier 2——trace 仍完全由 YCSB core 產生（只是 `recordcount` 與 schema 不同），pread vs fadvise 的配對在 arm 內完成。它唯一不能做的宣稱是「與舊 A/B/C 可比」，但那本來就是 headline（目標 A）的職責，見 §3.4。

### 1.2 `C_HIT` 的必要修正（進 Tier 2 的前置條件）

現況 key 數未配平：

| | key range | 真實 key 數 | leaf page footprint |
|---|---|---|---|
| 舊 C | `590000..609999` | `590000..600000` = **10,001** | 1× |
| `C_HIT` | `580001..600000` | **20,000** | **2×** |

`C_HIT` 要 fault-in 的 leaf 數是 C 的兩倍。在 cold-start / ABC 這種對「總共要載入幾頁」極度敏感的指標上，這個 footprint 差異會和「negative lookup 效應」混在一起。

**修正**：`C_HIT_LO = 590000`（→ 11,001 keys，配平頁數）。若不修正，必須在論文明寫此 confound。

### 1.3 舊 `gen_workload.py` 的處置

| workload | 處置 |
|---|---|
| `A` / `B` / `Z` | 降級 Tier 2，改名（見下）。headline 不得引用 |
| `C` | **退場**（違反 §1.1 的 `notfound_rate ≤ 1%`） |
| `C_HIT` | 修正 key range 後進 Tier 2 |
| `CHURN` | 降級 Tier 2，**docstring 頂端加大寫警告**：`THIS WORKLOAD HAS NO HOT SET BY DESIGN (sample-without-replacement). MUST NOT BE USED FOR ANY CLAIM ABOUT HOT PAGE MIGRATION.` 由 `YD` 接班 |
| `YD` / `YE` | **退場**。這兩個是「模仿 YCSB」而非 YCSB，保留只會混淆 Tier 1/2 界線。由真 YCSB 取代 |

**改名（強制）**：`A`/`B`/`C` 在文獻中有固定含義，與你的用法全部不符——

| | 真正的 YCSB | 舊 gen_workload.py |
|---|---|---|
| A | 50% read + 50% update, zipfian | 100% read, scrambled zipfian |
| B | 95% read + 5% update, zipfian | 100% read, **uniform** |
| C | 100% read, zipfian | tail 邊界探針，**50% not-found** |

reviewer 看到「workload C」會預期 YCSB-C，**會以為你在報 YCSB 的結果**。改名為 `RO_ZIPF_SCATTER` / `RO_UNIFORM` / `TAIL_HIT` / `CHURN_NOHOT`，或至少在論文表格首行標明「以下為 local convention，與 YCSB core workload 無對應關係」。

---

## 2. 方案：用真 YCSB 當 trace generator，不當 runner

pipeline 是 trace-driven（`workload_*.txt` → harness → FEMU），所以不要跑 YCSB 對 SQLite 做 online benchmark。
用 YCSB 的 `BasicDB` binding：它不做任何 IO，只把 CoreWorkload 決定的每個 operation 印出來。
**key 分佈、zipfian 抽樣、insertorder、request distribution 全部由 YCSB core 決定，你一行都不寫。**

### 2.1 取得與建置

```bash
git clone https://github.com/brianfrankcooper/YCSB.git
cd YCSB
git rev-parse HEAD > /tmp/ycsb_commit.txt     # 記進 manifest
mvn -pl site.ycsb:core,site.ycsb:basic -am clean package -DskipTests
# 或直接抓 release tarball（不需要 build）：
#   https://github.com/brianfrankcooper/YCSB/releases  → ycsb-0.17.0.tar.gz
```

> ⚠️ **在寫任何 parser 之前，先跑 §10 的驗證清單。** 本 spec 對 YCSB 內部行為的所有斷言都必須自己確認過。花十分鐘，省掉一輪實驗。

### 2.2 產生 trace

```bash
# ── load phase ──
# 注意：load 階段 keysequence = CounterGenerator(insertstart)，完全確定性、零隨機性。
# 每個 insertorder 只需要 **一份** load trace，不需要 N 個 seed。
bin/ycsb load basic \
  -P workloads/workloadc \
  -threads 1 \
  -p recordcount=600000 \
  -p insertorder=hashed \
  -p zeropadding=19 \
  -p fieldcount=1 -p fieldlength=1 \
  -p basicdb.verbose=true \
  -p basicdb.simulatedelay=0 \
  > raw/load_hashed.log

# ── run phase ──
bin/ycsb run basic \
  -P workloads/workloadc \
  -threads 1 \
  -p recordcount=600000 \
  -p operationcount=80000 \
  -p requestdistribution=zipfian \
  -p insertorder=hashed \
  -p zeropadding=19 \
  -p fieldcount=1 -p fieldlength=1 \
  -p basicdb.verbose=true \
  -p basicdb.simulatedelay=0 \
  > raw/YC_hashed_run_01.log

# ── v3 新增：YR arm（regime arm，參數依 §00 D3/D4）──
bin/ycsb load basic -P workloads/workloadc -threads 1 \
  -p recordcount=5000000 -p insertorder=hashed -p zeropadding=19 \
  -p fieldcount=1 -p fieldlength=1 \
  -p basicdb.verbose=true -p basicdb.simulatedelay=0 \
  > raw/load_hashed_YR.log

bin/ycsb run basic -P workloads/workloadc -threads 1 \
  -p recordcount=5000000 -p operationcount=${YR_OPCOUNT:?見 D4} \
  -p requestdistribution=zipfian -p insertorder=hashed -p zeropadding=19 \
  -p fieldcount=1 -p fieldlength=1 \
  -p basicdb.verbose=true -p basicdb.simulatedelay=0 \
  > raw/YR_hashed_run_01.log
```

**v2 相對 v1 的指令變更**

| 變更 | 理由 |
|---|---|
| `-threads 1` **寫死** | BasicDB verbose 用 `System.out.println`，`-threads > 1` 會讓行交錯甚至撕裂。這是**正確性**問題，不是效能問題 |
| `zeropadding=8` → **`19`** | 見 §3.2。`8` + hashed 會產生變長 key → fanout 不穩定 → 破壞 spec 自己訂的目標 |
| `fieldcount=1 fieldlength=1` | verbose 會 `toString()` 整個 value；預設 10×100B 會讓 load log 膨脹到 600MB–1GB。**trace 是 value-agnostic**，row size 由 harness 參數決定（見 §3.4），必須在 manifest 明記此事 |
| 移除 `-p zipfianconstant=0.99` | **它是 no-op**（見 §3.2）。留著等於在論文裡寫一句假話 |

### 2.3 Parser（YCSB log → 你現有的 trace 格式）

```python
# tools/ycsb2trace.py
"""YCSB BasicDB verbose log -> trace (JSONL).

紅線：parser 只做格式轉換。任何「key 重新映射」「key 排序」「補 not-found key」
都會把剛拿回來的公信力吐掉。

唯一允許的映射是 §2.5 的 order-preserving dense rowid 與 §4.5 的
order-preserving key 膨脹，且它們必須在**獨立的** tools/keymap.py 中實作，
並附保序性的單元測試。不得混進 parser。
"""
import re, sys, json

OP = re.compile(
    r'^(READ|UPDATE|INSERT|DELETE|SCAN|READMODIFYWRITE)\s+'
    r'(\S+)\s+'                 # table
    r'(\S+)'                    # key, e.g. user0000000000123456789
    r'(?:\s+(\d+))?'            # scan length (SCAN only)
)

def main(path, expected_ops):
    n_ok = n_bad = 0
    out = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        m = OP.match(line)
        if not m:
            n_bad += 1                      # ← v1 用 `continue` 靜默吞掉損壞的行
            continue                        #    這正是「敘事沒有物理量佐證」的同一個錯
        op, table, key, scanlen = m.groups()
        assert key.startswith('user'), f"unexpected key form: {key!r}"
        out.append({"op": op.lower(), "key": key,
                    "scanlen": int(scanlen) if scanlen else None})
        n_ok += 1

    # ── fail-fast：不合就非零退出，不得靜默 ──
    if n_bad:
        raise SystemExit(f"FAIL: {n_bad} unparsable lines "
                         f"(threads>1? format drift?)")
    if n_ok != expected_ops:
        raise SystemExit(f"FAIL: parsed {n_ok} ops, expected {expected_ops}")

    for rec in out:
        print(json.dumps(rec))

if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
```

### 2.4 Reproducibility 的實話

官方 YCSB 的 `CoreWorkload` 用 `ThreadLocalRandom`，**沒有可靠的全域 seed 控制**（不同版本 / fork 行為不同；先實測手上版本有無 `randomseed` property）。

> **trace 檔本身就是你的 seed。** 生成一次、存檔、hash、version control。
> `.manifest.json` 記：YCSB **commit hash**、完整 property 列表（含未指定而採預設的值）、輸出 sha256、生成時間、`-threads` 值。
> 論文寫「traces are released」而不是「seed = 42」。

### 2.5 🔴 Schema 決策 —— v1 最大的洞

v1 把這個決定藏在 §2.3 的一句 docstring 註解裡：

> ~~正確做法：SQLite schema 用 TEXT PRIMARY KEY 直接存 key string~~

**這一句話會換掉研究對象。**

| Schema | 實際結構 | 一次點查走幾棵樹 | 與舊 A/B/C 可比？ |
|---|---|---|---|
| `id INTEGER PRIMARY KEY`（現況） | 1 棵 rowid B-tree | **1** | — |
| `key TEXT PRIMARY KEY` | rowid table **+ 一棵 index B-tree** | **2**（index 找 rowid → table 找 row） | ❌ **災難** |
| `key TEXT PRIMARY KEY) WITHOUT ROWID` | 1 棵 index-organized B-tree | 1，但 cell 變大、fanout 掉、1KB row 易 overflow | ⚠️ 對目標 A 勉強；**對目標 B（§3.4）反而是唯一可行解 → 由 YR 採用，見 §4.5** |

中間那個是災難：你的研究對象是「interior node skeleton」，改用 TEXT PK 之後**每次查詢要穿過兩棵樹的 interior**。§3 表格「`recordcount` 對齊 600000 → 讓 YCSB 結果能跟舊 A/B/C 對照」這個理由**直接失效**。

#### 決策：order-preserving dense rowid（headline 採用）

`insertorder` 的作用只是決定 **keynum → B-tree 位置的排列**。這個排列可以在保持 `INTEGER PRIMARY KEY` 的前提下完整重現：

```
ordered:  rowid = keynum + 1                       # 恆等排列
hashed:   rowid = rank of Utils.hash(keynum)       # 把 N 個 hash 值排序後取名次，dense 1..N
```

**這不是 §2.3 紅線禁止的「key 重新映射」——它是保序同構（order-preserving bijection）。** B-tree 上誰跟誰相鄰、熱點集中或散開，完全保留；被消掉的只有「key 是字串」這個對本研究無關的表象。

好處：

- Schema 不動 → 跟舊 A/B/C 直接可比
- 兩臂 key encoding **完全相同**（dense int、同 varint 寬度、同 fanout）→ **唯一差異就是「哪些 key 相鄰」= 真正的自變數**
- 不用 TEXT PK、不用 WITHOUT ROWID、不用重跑 baseline

⚠️ **限制**：dense rank 需要**預先知道全部 key**，只適用於**無 insert 的 workload**（`YC` / `YC-u` / `YC-h` / `YA` / `YB` / `YF`）。

#### 有 insert 的 workload（`YD` / `YE`）

新 key 必須插進 B-tree 中間 → dense rank 不可用。三選一：

| 選項 | 做法 | 代價 |
|---|---|---|
| (a) sparse rowid | `rowid = Utils.hash(keynum)`（64-bit 正整數） | 9-byte varint → interior cell 7B→13B → fanout ~500→~290 → **與無 insert 組不可比** |
| (b) 預留 rank 空間 | load 時對 `keynum ∈ [0, recordcount + expectednewkeys)` **全部**取 rank，只插入前 `recordcount` 個 | 保持 dense-ish，insert 的 rowid 已預先決定 → **推薦** |
| (c) TEXT PK WITHOUT ROWID | 照 YCSB 原樣 | fanout 大跌、需重跑全部 baseline |

**決定：(b)**（§00 D2，CLOSED）。

#### 保序性單元測試（強制）

```python
# tests/test_keymap.py
def test_order_preserving():
    keys = [buildKeyName(i, insertorder) for i in range(N)]
    rowids = [keymap(i, insertorder) for i in range(N)]
    # 字典序（YCSB 世界的 B-tree 順序）必須與 rowid 序（我們的 B-tree 順序）一致
    assert sorted(range(N), key=lambda i: keys[i]) == sorted(range(N), key=lambda i: rowids[i])

def test_dense_bijection():
    rowids = [keymap(i, insertorder) for i in range(N)]
    assert sorted(rowids) == list(range(1, N + 1))
```

**這兩個測試不過，整個 mapping 方案作廢，退回選項 (c)。**

---

## 3. 參數決策表 —— 每一格都要有理由，不要抄預設

| 參數 | 選什麼 | 為什麼 / 對 page layout 的影響 |
|---|---|---|
| `insertorder` | **只在 `hotspot` / `latest` 上當自變數**（見 §3.1） | 在 `zipfian` 下**是 no-op**。v1 把它當全域自變數是錯的 |
| `requestdistribution` | `zipfian`（主）+ `uniform`（floor）+ `latest`（moving hotspot）+ `hotspot`（fixed hotspot） | uniform = 「沒有 locality 時的地板」，最誠實的對照 |
| `zipfianconstant` | **不設定。標記為「YCSB 內部常數，非本研究可調參數」** | 見 §3.2：對 `requestdistribution=zipfian` **無效** |
| `recordcount` | headline：600000（對齊舊 DB row 數）；**YR：5,000,000（D3）** | 對齊的真正對象是 **page count / B-tree 層數 / fanout**，見 §3.4 |
| `zeropadding` | **19**（兩臂統一，不再是「8 或 19」） | 見 §3.2 |
| `fieldcount` / `fieldlength` | **不抄預設**：headline row payload = **126B**（D1，對齊實測）；YR value = 126B + key 100B（D3） | 決定 leaf 塞幾筆 → 直接決定 leaf/interior 比例與 B-tree 層數 |
| `operationcount` | headline：80000（對齊現有）；YR：D4（OPEN） | — |
| `maxscanlength` / `scanlengthdistribution` | workload E 預設（100 / uniform） | — |
| `insertproportion` | workload D/E 預設 5% | 唯一會讓 DB 長大的旋鈕 |
| `hotspotdatafraction` / `hotspotopnfraction` | 只在 `requestdistribution=hotspot` 時。**掃一整條線，不能只報一個點** | 固定熱點，取代自造「tail 區間」的公認做法 |
| **`load_order`** | 見 §3.3 | **從 `insertorder` 解耦出來的獨立變數** |

### 3.1 ⚠️ `insertorder` × `requestdistribution` 的交互作用 —— v1 此節論點錯誤

`CoreWorkload.java` 建構 keychooser 時：

```java
} else if (requestdistrib.equals("zipfian")) {
  int expectednewkeys = (int)(opcount * insertproportion * 2.0);
  keychooser = new ScrambledZipfianGenerator(insertstart, insertstart + insertcount + expectednewkeys);
}
```

`ScrambledZipfianGenerator.nextValue()`：

```java
long ret = gen.nextValue();               // Zipf over ranks
ret = min + Utils.hash(ret) % itemcount;  // ← rank → keynum 已經 hash 散開了
```

接著 `buildKeyName()` 才做第二次 hash：

```java
if (!orderedinserts) { keynum = Utils.hash(keynum); }
```

**推論：**

| requestdistribution | keychooser | 熱 keynum 是否連續 | `insertorder` 影響熱點空間分佈？ |
|---|---|---|---|
| `zipfian` | **Scrambled**Zipfian | ❌ 已散開 | **幾乎無影響** |
| `uniform` | UniformLong | 無熱點 | 無（但影響物理佈局，見 §3.3） |
| `latest` | `SkewedLatestGenerator`（`lastValue - zipf(...)`，**無 scramble**） | ✅ 尾端連續一段 | **影響巨大** |
| `hotspot` | `HotspotIntegerGenerator`（連續 keynum 區間） | ✅ 連續 | **影響巨大** |

所以：

- v1 §3.1 寫的「ordered → 熱 key 全部集中在 keyspace 左端」**對 `zipfian` 不成立**，因為 scrambler 在 `buildKeyName` 之前就先打散了。
- v1 §4 的「每個 ID × insertorder = 16 條」**有一半是浪費**：`YA`/`YB`/`YC`/`YC-u`/`YE` 的兩臂在熱點空間分佈上幾乎相同。
- **真正的 `insertorder` 軸只在 `YC-h` 和 `YD` 上有意義**——而那正好是唯二真正在測「空間局部性」的 workload。

#### 修正後的論文寫法

> *"`insertorder` interacts with `requestdistribution`: under `zipfian`, YCSB's `ScrambledZipfianGenerator` already hashes rank→keynum, so `insertorder` does not affect hot-key spatial locality. The spatial-locality axis is therefore realized through `hotspot` and `latest`, whose key choosers preserve keynum contiguity. When request skew maps to spatial locality on the B-tree (`hotspot`/ordered, `latest`/ordered), the benefit rises from X% to Y%. We report `zipfian`/hashed as our headline because it is YCSB's default and makes no assumption about key-to-page locality."*

這比 v1 的「掃 16 條」有說服力得多：它是**兩個變數（skew 來源 × key 編碼）的交互作用**，而不是一條盲目的參數線。這句話一寫出來，「參數在驅動結論」就從弱點變成 contribution。

### 3.2 `zipfianconstant` 與 `zeropadding` 的兩個陷阱

#### (a) `-p zipfianconstant=0.99` 很可能是 no-op

上面的建構呼叫 `new ScrambledZipfianGenerator(min, max)` — **沒有傳 zipfianconstant**。它走預設建構子，用硬編碼的 `ZipfianGenerator.ZIPFIAN_CONSTANT = 0.99`，且 `ScrambledZipfianGenerator` 為效能預先算好 `ZETAN = 26.46902820178302`（對應 `ITEM_COUNT = 10_000_000_000L`）。

兩個後果：

1. **命令列寫 `-p zipfianconstant=0.99` 大概什麼也沒做。** 剛好值一樣所以結果對，但論文寫「we set zipfianconstant=0.99」是**錯誤敘述**。而且改成 0.9 會被**靜默無視**。
2. **ScrambledZipfian 的 skew ≠ Zipf(0.99, N=600000)。** 它在 10^10 個 rank 上抽 Zipf，再 `hash(rank) % 600000` 折疊回來 → 每個 key 平均吸收約 16,667 個 rank 的機率質量 → **實際傾斜度低於 Zipf(0.99, 600k)，尾巴沒那麼冷**。任何基於 `H_N` 的解析試算（如「top 1% ≈ 65%」）**對 ScrambledZipfian 不適用**。

**規則**：論文正文一律引 Tier 0 的 `measured_skew` 實測值。`zipfianconstant` 只出現在 config 附錄，並註明「YCSB 內部常數，非本研究可調參數」。

#### (b) `zeropadding=8` 與 `insertorder=hashed` 互斥

`buildKeyName()`：

```java
String value = Long.toString(keynum);
int fill = zeropadding - value.length();   // fill < 0 時不截斷，直接不補
```

`Utils.hash()` 是 FNV-1a 64-bit（取正）→ 最長 19 位數。所以 `zeropadding=8` + hashed 會產生 **`user` + 8～19 位變長 key**：

1. 破壞 spec 自己訂的「固定寬度 → fanout 穩定」目標
2. **字典序 ≠ 數值序**（`"user9"` > `"user10000000000"`）→ scan 語義與 B-tree 佈局都跟你以為的不同
3. **兩臂 key 長度不同 → cell 大小不同 → fanout 不同 → interior skeleton 大小不同**，這正是你要比的東西

**決定：`zeropadding=19`，兩臂統一。** ordered 臂雖只需 6 位，仍必須補到 19 以保持 fanout 可比。

### 3.3 `load_order` 解耦 —— 兩臂間最大的 confound

`insertorder` 不只影響「誰跟誰相鄰」，還影響 **load 階段是循序 append 還是隨機插入**：

| Load 順序 | B-tree 行為 | 結果 |
|---|---|---|
| ordered（循序遞增） | 純右邊 append，quick-balance | page fill ≈ **100%**，DB 最小，零碎片 |
| hashed（隨機） | 到處 split | page fill ≈ **69%**（隨機插入的漸近值），DB 大 ~45%，leaf 數多 ~45% |

也就是 v1 的兩臂**同時**差了兩件事：

1. 熱點空間分佈（**你想測的**）
2. DB 總頁數、fill factor、B-tree 層數（**confound**）

對 cold-start / ABC 這種對「總共要 fault-in 幾頁」極度敏感的指標，**這個 confound 可能比主效應還大**。

> **v3 佐證**：舊 DB 實測 leaf_fill = 96.8%（§3.4）——正是 sorted-load 的簽名。任何 as-generated load 的臂都會落到 ~69%，兩臂頁數差 ~40%，直接觸發 headline 作廢條款。

#### 解法：拆成兩個獨立變數

```
key_layout ∈ {ordered, hashed}      # 熱點空間分佈（= YCSB 的 insertorder）
load_order ∈ {as-generated, sorted} # 物理佈局
```

Load 階段的內容是一個**集合**，不是分佈——用什麼順序插入不改變 DB 的邏輯內容，只改變物理佈局。**這不違反 §2.3 紅線**：紅線禁的是竄改 run-phase 的存取分佈；load order 是建 DB 的手法，與「VACUUM 後再測」同類。

| | headline | sensitivity axis |
|---|---|---|
| `load_order` | **`sorted`**（兩臂都循序建 DB → fill factor 一致、頁數一致 → 隔離主效應） | `as-generated`（測 fragmentation 的影響） |

**最低限度（若不做完整解耦）**：兩臂都 `VACUUM` 後再跑，且 manifest 必須記錄 `page_count` / `fill_factor` / `depth`。若兩臂這三個數字不一致，**headline 作廢**。

### 3.4 `fieldlength`：實測回填 + 目標解耦（v3 重寫）

#### 舊 DB 實測（2026-07，dbstat，`page_size=4096`，全檔 26,331 頁 ≈ 107.9MB 含 k1/k2 兩個 index）

| 量 | items（研究對象，rowid table） | idx_items_k1 | idx_items_k2 | v2 的解析估計（供對照） |
|---|---|---|---|---|
| leaf 頁數 | **19,983** | 3,106 | 3,149 | ~200,000（誤以 row≈1KB） |
| interior 頁數 | **51** | 20 | 21 | ~400 |
| depth | **3** | 3 | 3 | 3 |
| interior fanout（leaf/interior） | **≈ 392** | ≈ 155 | ≈ 150 | ~500 |
| leaf 每頁筆數 | **~30**（payload/row ≈ **126B**） | — | — | ~3 |
| leaf fill | **96.8%**（sorted-load 簽名） | 87.3% | 85.9% | — |
| **interior skeleton** | **51 頁 = 204KB** | 80KB | 84KB | **1.6MB** |

> 若 run-phase 只走 PK 點查，k1/k2 的骨架不在 critical path 上；若任何 workload 走 secondary index，其骨架（各 ~80KB）一併計入 ρ 的分子。manifest 必須記錄 query plan 用到哪些 B-tree。

實測**證實並加重**了 v2 的擔憂：骨架不是估計的 1.6MB，是 **204KB——比悲觀估計還小 8 倍**。連同 SQLite 自身的 pager cache（預設 `cache_size` ≈ 2MB）一起看，這個骨架在任何正常配置下都**必然**全量快取。

#### 🔴 目標解耦 —— v2 此節的設計缺口

v2 的規則「`fieldlength` 由對齊舊 DB 反推」把兩個目標綁在同一個旋鈕上：

- **目標 A（歷史橋接）**：讓 YCSB 結果能與舊 A/B/C 對照 → 需要對齊。
- **目標 B（效應存在性）**：讓 prefetch 有非零收益天花板 → 需要**離開**舊 DB 所在的 null regime。

兩者對 `fieldlength` 的要求直接衝突，v2 的反推工作單假設「對齊 = 好事」，等於默默把目標 B 犧牲掉、把 null 烤進 headline。**但關鍵觀察是：headline 的統計效度來自 paired design（§8）——同一條 trace 上比 pread vs fadvise，配對發生在單一 DB 內部——它根本不需要「對齊舊 DB」。對齊只服務目標 A。** 所以正解不是二選一，而是一個目標一個 config：

| 目標 | config | 角色 |
|---|---|---|
| A（橋接）| **headline = YC-hashed，對齊實測**（126B payload → leaf ≈ 20k、depth 3、骨架 ≈ 205KB） | 與舊 A/B/C 可比 + **negative control**（§-1.4） |
| B（存在性）| **YR / YR-P（§4.5）** | 天花板律的第二、三個落點 |

#### 反推工作單（v3：已填）

| 量 | 舊 DB 實測 | headline 目標 | 達成手段 |
|---|---|---|---|
| items leaf 頁數 | 19,983 | 20k ± 5% | `fieldcount=1`，row payload 126B |
| B-tree depth | 3 | 3 | 同上 |
| interior skeleton | 204KB | 205KB ± 10% | 同上 |
| leaf fill | 96.8% | 一致 | `load_order=sorted`（§3.3） |
| **決定** | — | — | **D1（CLOSED）** |

### 3.5 效應天花板帳（ceiling law）—— v3 新增，這一節決定整個實驗的形狀

**命題**：冷啟動、cache 充足（骨架與熱 leaf 集合皆放得進 OS page cache + SQLite pager cache）時，interior prefetch 對 ABC 的收益上限為

> **ρ ≈ I / (I + L) ≈ 1 / (1 + f_eff)**

其中 I = settling window 內 fault-in 的 distinct interior 頁數、L = distinct leaf 頁數、f_eff ≈ interior fanout。

**推導（三行）**：cache 充足時每個 distinct page 恰好 fault 一次；prefetch 骨架能做的極致，是把那 I 次散落在 descent critical path 上的 random read 換成一次 upfront 的 sequential read（成本 ≪ I 次 random）；省下的量 ≤ I × t_rand，總量 ≈ (I+L) × t_rand，故收益佔比 ≤ I/(I+L)。而每 fault 一個新 interior 平均服務 ~fanout 個新 leaf，故 I/L ≈ 1/f_eff，**與 settling window 長短、skew 形狀基本無關**——這是結構性的。

**三個落點：**

| 配置 | fanout | ρ 天花板 | 備註 |
|---|---|---|---|
| headline（對齊，D1） | ≈ 392 | **≤ ~1%**（窗口越長越趨近 51/20034 ≈ 0.25%） | null 是預測 |
| YR（D3） | ≈ 38 | **≈ 2.6%** | 一個數量級的提升，但仍個位數 |
| YR-P（D5，R = 骨架/file-cache ≥ 1） | — | **脫離 regime 1**：interior 被逐出後 re-fault，每次冷 descent 反覆付 (d−1) 次序列化 interior miss，per-query 上限 (d−1)/d（YR depth≈5 → 80%） | 效益可望達雙位數 |

**三個推論：**

1. **「把 DB 弄大」這條路本身是死的**：ρ ≈ 1/fanout 與 DB 大小無關。把對齊配置放大 1000 倍，天花板還是 0.25%。v2 §-1.2 / §6 的「放大 DB 逃離 null regime」直覺只對了一半——真正的槓桿是 **(i) fanout**（→ YR）與 **(ii) cache pressure**（→ YR-P），兩者都與 recordcount 正交。
2. **regime 2 需要兩層 cache 同時受限**：骨架必須同時超過 OS file cache 配額（cgroup `MemoryMax`）**與** SQLite pager cache（`PRAGMA cache_size`）。204KB 的骨架掐不出壓力（會先把整個 process 掐死）；32MB 的可以。**這就是 YR-P 必須疊在 YR 上、而不能疊在 headline 上的原因。**
3. **scan/range workload（YE）走不同機制**：interior 的內容可用來對 leaf 做 readahead，收益不受 1/fanout 界。若既有 prefetch 策略含此機制，YE 是天花板律之外的獨立敘事線；若不含，明寫「out of scope」。→ 若要納入，開一條 `OPEN` decision。

### 3.6 舊 §3.4 解析試算表（v2 遺留，僅存檔供對照，數字已被實測取代）

以 `page_size=4096`、`recordcount=600000`、row ≈ 1KB（**此假設已證偽：實測 126B**）、usable ≈ 4061：

| 量 | INTEGER PK（dense rowid） | TEXT PK WITHOUT ROWID（19 字元 key） |
|---|---|---|
| leaf 每頁筆數 | ~3 | ~3 |
| leaf 總數 | ~200,000 | ~200,000 |
| interior cell 大小 | 4 + 3 varint ≈ **7B** | 4 + ~24 ≈ **28B** |
| interior fanout | **~500** | **~145** |
| B-tree 層數 | 3 層 | 4 層 |
| interior skeleton 總量 | ~1.6 MB | ~5.7 MB |
| DB 大小 | ~800 MB | ~800 MB |

---

## 4. Workload matrix（v3：分層 + regime arm）

`insertorder` 只在 `hotspot` / `latest` 上是自變數（§3.1），因此 v1 的 16 條縮減如下。

| ID | YCSB base | schema / regime | `insertorder` 臂 | 覆蓋什麼 | 取代誰 |
|---|---|---|---|---|---|
| **YC** | workloadc (100% read, zipfian) | headline（對齊，D1） | **hashed only** | **HEADLINE + negative control**：純讀熱點，無 key-to-page locality 假設 | 舊 C（含 −75% artifact） |
| YC-u | workloadc + `requestdistribution=uniform` | headline | hashed only | **no-locality 地板** | 新增，必要 |
| **YC-h** | workloadc + `requestdistribution=hotspot` | headline | **hashed × ordered** | 固定熱點。**空間局部性軸之一** | 舊 C 的 tail 區間 |
| **YD** | workloadd (read-latest + 5% insert) | headline + rowid 方案 (b)（D2） | **hashed × ordered** | 移動熱點 = 真正的 churn。**空間局部性軸之二** | 舊 churn（hot set 位移 = 0 的那個） |
| YA | workloada (50/50 R/U, zipfian) | headline | hashed only | 寫入混合 | 舊 A |
| YB | workloadb (95/5, zipfian) | headline | hashed only | 讀為主 | 舊 B |
| YE | workloade (short scan + insert, zipfian) | headline + rowid 方案 (b) | hashed only | range 存取（§3.5 推論 3） | 舊 scan |
| YF | workloadf (RMW, zipfian) | headline | hashed only | RMW | 舊 rmw |
| **YR** | workloadc | **regime arm（§4.5，D3）** | hashed only | **天花板律第二落點**（fanout 392→38） | v3 新增 |
| **YR-P** | workloadc（與 YR 同 trace） | YR × cgroup `MemoryMax` sweep（D5） | hashed only | **天花板律第三落點**（regime 2：re-fault） | v3 新增 |

**臂數**：6 (hashed only) + 2×2 (spatial axis) + YR + YR-P sweep = 依 §9。
**`YC-h` 額外要求**：`hotspotdatafraction` 掃一整條線（如 0.01 / 0.05 / 0.1 / 0.2 / 0.5），**不能只報一個點**——否則就是舊「tail 區間 knife-edge」的重演。

### 4.5 YR / YR-P regime arm 規格（v3 新增）

#### 4.5.1 YR schema：`WITHOUT ROWID` + 保序 key 膨脹

```sql
CREATE TABLE items_yr (
  k   TEXT PRIMARY KEY,     -- 定長 100B（見下）
  v   BLOB                  -- 126B，與 headline 同 payload
) WITHOUT ROWID;
```

key 膨脹在 `tools/keymap.py` 實作（**不在 parser**）：

```
inflate(key) = key + PAD                # key 全部定長 23B（"user"+19 位，zeropadding=19 保證）
                                        # PAD = 77 個固定位元組 → 定長 100B
```

**合法性論證（與 §2.5 dense rowid 同一條路徑）**：等長字串加相同定長後綴是 order-preserving injection——字典序完全不變，B-tree 上誰跟誰相鄰、熱點集中或散開完全保留。被改變的只有 interior cell 的物理寬度（≈ 4 + varint + 100 ≈ 106B → **fanout ≈ 4061/106 ≈ 38**）。**fanout 在此 arm 是實驗控制變數，manifest 明記。** 不觸 §2.3 紅線（run-phase 存取分佈一個 bit 都沒動）。

保序測試追加：

```python
def test_inflate_order_preserving():
    keys = [buildKeyName(i, 'hashed') for i in range(N)]
    assert sorted(keys) == [k[:23] for k in sorted(inflate(k) for k in keys)]

def test_inflate_fixed_length():
    assert all(len(inflate(buildKeyName(i, 'hashed'))) == 100 for i in range(N))
```

#### 4.5.2 預期幾何（D3，須經 §10.3 原型驗證後才算數）

| 量 | 預期值 | 算式 |
|---|---|---|
| leaf cell | ≈ 230B（key 100 + value 126 + header） | → ~17 rows/leaf |
| leaf 頁數 | ≈ 294k | 5M / 17 |
| interior 頁數 | ≈ 8k（L1 ≈ 7.7k + 上層 ≈ 210） | leaf / 38 |
| **skeleton** | **≈ 32MB** | 8k × 4KB |
| depth | ≈ 5 | 294k → 7.7k → 204 → 6 → root |
| DB | ≈ 1.2GB | — |
| **ρ 天花板** | **≈ 2.6%** | 1/(1+38) |

> depth 3 → 5 的副作用要明寫：YR 的每次冷 descent 有 4 個 interior miss（headline 為 2），這在 regime 2（YR-P）裡直接放大 per-query 收益上限至 (d−1)/d = 80%。

#### 4.5.3 YR-P：cache-pressure 軸的公平性規則（違反任一條 → 該 run 作廢）

1. **兩策略同 limit**：pread 與 fadvise 臂必須在**完全相同**的 `MemoryMax` 下配對比較；不得各自取最優 limit。執行：`systemd-run --scope -p MemoryMax=$M -p MemoryHigh=$M ...`（cgroup v2）。
2. **兩層 cache 都要記錄與控制**：`PRAGMA cache_size` 在所有 arm 固定為同一值並記入 manifest（現行 cold-start harness 的值照舊，但必須明記）；R 的分母不是 `MemoryMax`，是 run 期間 `memory.stat` 的 **file-backed 頁實測均值**（`MemoryMax` 還含 anon：SQLite heap、pager cache 本體）。
3. **`fadvise(WILLNEED)` 預讀頁在壓力下先被逐出是預期現象，不是 bug**：這正是 regime 2 裡 fadvise 策略的真實行為，settling-point 方法論剛好能量到它。預先寫進 §-1.4 的預測欄，事後不得以此為由剔除 run。
4. **每個 (limit, strategy, repeat) 之間**：`echo 3 > /proc/sys/vm/drop_caches` + 重建 scope，杜絕殘留。
5. **每個 limit 的 R 值**（骨架 32MB / file-cache 實測）與效益一起畫成曲線進論文；單點不得單獨引用。

---

## 5. Tier 0 Validator — 這才是真正堵住坑的東西

**YCSB 不會幫你檢查任何東西。** 它只保證 key 分佈是公認的。
被咬的兩次（churn 位移 = 0、C 的 not-found）都是「敘事沒有物理量佐證」，**換 generator 不會自動解決**。

### 5.1 前置條件（v1 未列）

`rightmost_leaf_share` 與 `hotset_jaccard_series` 都需要 **key → page 映射**。取得方式：

```bash
# 需要編譯旗標
gcc -DSQLITE_ENABLE_DBSTAT_VTAB ...
```

```sql
-- 每個 page 的 payload / cell 數 / 名稱
SELECT name, path, pageno, pagetype, ncell, payload, unused FROM dbstat WHERE name='items';
```

或自行 parse b-tree page header。**這是 §6 步驟 3 的硬前置條件，沒有它 validator 只是半個。**

> **v3 進度註**：dbstat 管線已可用（舊 DB 量測即由此產出，§3.4）。

### 5.2 檢查項

```python
# tools/validate_trace.py
# 對任何 trace（YCSB 或自造）強制執行。CI 上跑，不過就 fail（非零退出）。

CHECKS = {
  # ── 堵 concern #3（out-of-range artifact）──
  "key_range_subset":     "所有 read/update/scan 的 key ∈ DB 現存 key set（insert 除外）",
  "notfound_rate":        "實際對 DB 跑一遍，統計 not-found 比例。"
                          "> 1% → Tier 2 直接退場（§1.1）；Tier 1 必須在論文明寫，不得沉默",
  "rightmost_leaf_share": "落在最右葉的 op 佔比。異常高 = 又中了同一個坑",

  # ── 堵 concern #2（宣稱 churn 但 hot page 沒動）──
  "hotset_jaccard_series": "trace 切 N 段，每段取 top-1% page 集合，算相鄰段 Jaccard。"
                           "宣稱 churn/moving hotspot → Jaccard 必須顯著 < 1，且畫成圖進論文",
  "unique_key_ratio":      "unique_keys / total_ops。接近 1 = 抽樣不放回 = 根本沒有熱點，"
                           "此時任何 locality 宣稱一律 fail",
  "measured_skew":         "實測 top-1% key 佔多少 op。"
                           "**不得引用 zipfianconstant（它是 no-op，§3.2），一律引實測值**",

  # ── 堵 §3.3 的物理佈局 confound ──
  "page_count":     "DB 總頁數。同一組實驗的兩臂必須一致，否則 headline 作廢",
  "fill_factor":    "leaf page 平均填充率。ordered load ≈ 100%，random load ≈ 69%",
  "btree_depth":    "B-tree 層數。跨設定不一致 = 不可直接比",
  "skeleton_bytes": "interior page 總量。決定 prefetch 的收益上限（§3.5）",

  # ── 堵 §3.1 的 no-op 自變數 ──
  "hot_key_contiguity": "top-1% key 在 rowid 空間的相鄰程度（如平均 gap / 佔用 leaf 數）。"
                        "若 ordered 與 hashed 兩臂此值相近 → insertorder 是 no-op，"
                        "該條 sensitivity axis 作廢，不得在論文中宣稱它是變數",

  # ── v3 新增：堵 §3.5 / §4.5 ──
  "rho_measured":   "settling window 內 interior fault 佔全部 fault 的實測比例。"
                    "與 §-1.4 各 arm 的天花板並列回報；效益若量出 > ρ_measured → pipeline bug",
  "cache_config":   "PRAGMA cache_size、MemoryMax、run 期間 memory.stat file-backed 均值。"
                    "三者缺一，該 run 不得進聚合",
  "R_ratio":        "skeleton_bytes / file-backed cache 實測值。YR-P 的自變數，逐 run 記錄",
  "trees_touched":  "query plan 實際走過的 B-tree 集合（items? k1? k2?）。ρ 的分子依此計",

  # ── 一般衛生 ──
  "db_growth":     "insert 造成的 page 數變化，明確記錄",
  "op_mix_actual": "實測 op 比例 vs 宣稱比例",
  "parse_losses":  "parser 丟棄的行數。必須 == 0（§2.3）",
}

# 輸出：每條 trace 一份 validation.json，跟 .manifest.json 並排存。
# 論文的每張圖，caption 裡引用對應 trace 的 validation hash。
```

### 5.3 規則

> 任何 workload 的宣稱都必須對映到 validator 裡的一個**數字**。沒有對應數字的形容詞，不准出現在論文裡。（= §-1.3）

---

## 6. 遷移步驟（v3：驗證優先 + 進度標記）

| # | 步驟 | 產出 / 通過條件 | 狀態 |
|---|---|---|---|
| **0** | **跑 §10 驗證清單（10.1–10.2）** | 確認 A1（insertorder 是否 no-op）、A2（zipfianconstant）、格式 | ☐ |
| **1** | **量舊 DB 的 page_count / depth / skeleton_bytes**，填 §3.4 反推工作單 | 已填：leaf 19,983 / depth 3 / 骨架 204KB / fanout 392 | ✅ **完成（2026-07）** |
| **2** | **決定 schema（§2.5 = D1/D2）**，寫 `tools/keymap.py` + 保序性單元測試（含 §4.5.1 inflate 測試） | 決定已 CLOSED；測試必須綠 | ☐（決策 ✅ / 實作 ☐） |
| **2.5** | **§10.3 YR 原型驗證**（200k rows 小樣，dbstat 對照 §4.5.2 預期幾何） | fanout ∈ [33, 43]、depth 與外插一致 → D3 轉正；否則調 key 寬度重跑 | ☐ |
| **3** | **先寫 `validate_trace.py`（含 dbstat 前置與 v3 新檢查項），回頭跑舊的 A/B/C/churn** | ⭐ **這一步把已知的兩個坑變成硬數字，是給老師看的最強證據。做在遷移之前，不是之後** | ☐ |
| **4** | **補完 D4–D6，§-1 全文（含 §-1.4 預測）commit** | git 時間戳。**必須在步驟 5 之前** | ☐ |
| 5 | 跑一次 `basicdb.verbose=true`，寫 `ycsb2trace.py`，產 1 條 YC-hashed，跟舊 workload 並排比對統計 | parse_losses == 0 | ☐ |
| 6 | 生成完整 matrix（§4 × §9 分層，含 YR/YR-P），每條配 manifest + validation | 全部通過 Tier 0 | ☐ |
| 7 | 重跑 A3/A4，headline 只引用 Tier 1；效益逐 arm 對照 ρ 天花板回報 | 依 §8 聚合 | ☐ |
| 8 | 舊自造 workload 依 §1.3 處置（C 退場，其餘降級 Tier 2 + 改名） | — | ☐ |

---

## 7. 誠實的限制（論文 threats to validity 直接寫）

- YCSB 是 KV API 層，**表達不出 page-layout 語意**。任何關於 interior node 結構的細緻機制探討仍需 Tier 2 probe。這不是弱點，是分工。
- YCSB 沒有「hot set 在 keyspace 中間搬移」的 workload（`latest` 只往尾端長）。要測這個只能自造 → Tier 2。
- 用 BasicDB dump trace = 不含真實 client 的 timing / concurrency。實驗是 storage-layout 導向，通常可接受，但要寫明。
- `zeropadding` / `fieldlength` 一動 fanout 就變，跨設定不可直接比。已固定（§3.2 / §3.4）。
- YCSB 的公信力**只覆蓋 key 分佈**。`fieldlength` / `zeropadding` / schema / load order / rowid mapping 全部是我們的選擇，且每一個都影響 page layout。**這些選擇的公信力來自 §-1 預先承諾與 §5 validator，不來自 YCSB。**
- `requestdistribution=zipfian` 的實際分佈是「Zipf 條件於 keynum ≤ acknowledged insert counter」（rejection sampling），且經過 ScrambledZipfian 的 rank→keynum hash 折疊。**它不是 Zipf(0.99, N=recordcount)**，任何解析式試算不適用；一律引實測值。
- 用 order-preserving dense rowid 取代 TEXT key（§2.5）保留了 B-tree 的相鄰關係，但改變了 key 的物理表示（string → int）。cell 大小與 fanout 因此與原生 YCSB-on-SQLite 不同。此舉是為了與 prior configuration 可比；trade-off 明寫。
- **（v3 新增）** YR 的 fanout 是人為壓低的（保序 key 膨脹），不代表典型 SQLite 部署；它的角色是驗證天花板律的第二個落點，不是宣稱「一般 SQLite 能拿到 2.6%」。YR-P 的雙位數效益僅適用於「骨架 > 可用 file cache」的記憶體受限部署（多租戶、容器配額），適用條件以 R 值定量給出。
- **（v3 新增）** §3.5 的天花板律假設點查、忽略 random vs sequential 讀的成本差與 prefetch 自身的 CPU/IO 開銷（兩者都讓實際收益**更低**，故上界方向安全）；scan workload（YE）的 interior→leaf readahead 機制不受此律約束，需另行論述或明寫 out of scope。

---

## 8. 統計聚合

v1 只寫「× 10 seeds」，沒說怎麼合成一個數。

| 項目 | 方案 |
|---|---|
| **配對** | 同一條 trace 上跑 pread 與 fadvise → **天然 paired design**，消掉 trace 間變異。**不得跨 trace 比較** |
| **報告單位** | **per-trace ABC 差值的分佈**（N 個點），不是只報平均。畫 dot plot 或 paired slope chart。**v3：每張圖並列該 arm 的 ρ 天花板橫線** |
| **檢定** | paired **Wilcoxon signed-rank**（N 小，不假設常態）。報 effect size 與 CI，不只報 p |
| **重複** | 每條 trace × 每策略跑 3 次 cold-start，取 median 作為該 trace 的代表值（消掉 run-to-run 噪音，再進 paired 檢定） |
| **⚠️ settling point fallback（v3 新增）** | YR / YR-P 之下骨架大、收斂慢，convergence-based settling point 可能**不觸發或觸發過晚**。**預先註冊 fixed-horizon ABC（前 K ops，K 依 D6 跑前 commit）為 fallback**；兩種定義都回報，不得事後挑對自己有利的那個。convergence 是否觸發本身記入 validation.json |
| **⚠️ 語意紅線** | N 條 trace 檢定的是 **workload 內變異**，不是**參數敏感度**。這兩件事在 reviewer 眼裡是分開的。**論文中不得用同一個 "robust" 涵蓋兩者**（= §-1.3） |

---

## 9. 成本分層（v3 更新）

配合 §3.1（zipfian 下 insertorder 是 no-op）與分層，v1 的 ~960 runs 砍到如下，**而且每一條都有存在的理由**。

| 層 | 內容 | traces | configs | runs（×2 策略 ×3 repeat） | 備註 |
|---|---|---|---|---|---|
| **Tier 1a** | **headline**：YC-hashed | **10** | 1 | 60 | DB 108MB，還原快 |
| **Tier 1b** | **spatial axis**：YC-h × {hashed, ordered}、YD × {hashed, ordered} | **5** | 4 | 120 | — |
| **Tier 1c** | 其餘：YA / YB / YE / YF / YC-u | **3** | 5 | 90 | — |
| **Tier 1b'** | `hotspotdatafraction` sweep（YC-h，5 點） | 3 | 5 | 90 | — |
| **Tier 1r（v3）** | **YR**（regime arm，無壓力） | **5** | 1 | 30 | ⚠️ DB ≈ 1.2GB，冷啟動還原成本 ~數倍；load trace 1 條 |
| **Tier 1r'（v3）** | **YR-P**（`MemoryMax` sweep，D5 的非 ∞ 3 點） | 3 | 3 | 54 | 與 YR 共用 trace 與 DB image |
| | | | **合計** | **~444 runs** | headline 部分 ≈ 18 小時 + YR 系 ≈ 8–10 小時（含還原） |

**load trace 需求**：headline 系 2 條（每個 `insertorder` 一條，`CounterGenerator` 零隨機）+ YR 1 條 = **3 條**。

---

## 10. 動工前的十分鐘驗證清單 ⚠️ 先跑這個

**本 spec 對 YCSB 內部的所有斷言都必須自己確認。** 在寫任何一行 `ycsb2trace.py` 之前：

```bash
# 1. zipfianconstant 到底有沒有被 requestdistribution=zipfian 吃掉？（§3.2a）
grep -n "zipfianconstant\|ScrambledZipfianGenerator\|ZIPFIAN_CONSTANT\|ZETAN" \
  core/src/main/java/site/ycsb/workloads/CoreWorkload.java \
  core/src/main/java/site/ycsb/generator/ScrambledZipfianGenerator.java \
  core/src/main/java/site/ycsb/generator/ZipfianGenerator.java

# 2. buildKeyName 的 hash / zeropadding 行為（§3.2b）
sed -n '/buildKeyName/,/^  }/p' core/src/main/java/site/ycsb/workloads/CoreWorkload.java

# 3. nextKeynum 的 rejection loop（§0 表格）
sed -n '/long nextKeynum/,/^  }/p' core/src/main/java/site/ycsb/workloads/CoreWorkload.java

# 4. 有沒有 randomseed property？（§2.4）
grep -rn "randomseed\|ThreadLocalRandom\|new Random(" core/src/main/java/site/ycsb/

# 5. 實測 verbose 格式（不要照 spec 假設寫 parser）
bin/ycsb run basic -P workloads/workloadc -threads 1 \
  -p recordcount=1000 -p operationcount=20 \
  -p fieldcount=1 -p fieldlength=1 \
  -p insertorder=hashed -p zeropadding=19 \
  -p basicdb.verbose=true -p basicdb.simulatedelay=0 2>/dev/null | head -25
```

### 10.1 🔴 關鍵實驗：證偽 / 證實 §3.1

**這一條會在十分鐘內告訴你，這份 spec 的核心自變數是不是一個 no-op。**

```bash
for io in ordered hashed; do
  bin/ycsb run basic -P workloads/workloadc -threads 1 \
    -p recordcount=600000 -p operationcount=80000 \
    -p fieldcount=1 -p fieldlength=1 \
    -p insertorder=$io -p zeropadding=19 \
    -p basicdb.verbose=true -p basicdb.simulatedelay=0 2>/dev/null \
  | awk '/^READ/{print $3}' | sort | uniq -c | sort -rn | head -100 \
  | awk '{print $2}' > /tmp/top100_$io.txt
  echo "=== $io: top-100 hot keys (前 5) ==="; head -5 /tmp/top100_$io.txt
done
```

**判讀**：

| 觀察 | 結論 |
|---|---|
| `ordered` 的 top-100 key **也散佈在整個 keyspace** | ✅ §3.1 成立（ScrambledZipfian 先 hash 了）→ 依 v3 的 §4 matrix 執行 |
| `ordered` 的 top-100 key **集中在 keyspace 一端** | ❌ §3.1 不成立 → **v1 的 16 條 matrix 是對的**，回頭改寫 §3.1 / §4 |

同一實驗對 `latest` / `hotspot` 重跑（把 `-p requestdistribution=` 換掉），預期**兩臂差異巨大**——這會確認空間局部性軸應該掛在哪裡。

### 10.2 對照組

```bash
# hotspot：預期 ordered 臂的 top-100 連續，hashed 臂散開
for io in ordered hashed; do
  bin/ycsb run basic -P workloads/workloadc -threads 1 \
    -p recordcount=600000 -p operationcount=80000 \
    -p requestdistribution=hotspot \
    -p hotspotdatafraction=0.01 -p hotspotopnfraction=0.8 \
    -p fieldcount=1 -p fieldlength=1 \
    -p insertorder=$io -p zeropadding=19 \
    -p basicdb.verbose=true -p basicdb.simulatedelay=0 2>/dev/null \
  | awk '/^READ/{print $3}' | sort -u | head -5
done
```

### 10.3 🔴 YR 原型驗證（v3 新增，D3 轉正的前置條件）

**§4.5.2 的幾何全是紙上外插。在建 1.2GB DB 之前，先用 200k rows 驗算。**

```bash
# 1. 建小樣（200k rows、key 定長 100B、value 126B、sorted load）
python3 tools/build_yr_prototype.py --rows 200000 --db /tmp/yr_proto.db

# 2. dbstat 對照
sqlite3 /tmp/yr_proto.db <<'SQL'
SELECT pagetype, count(*) pages, sum(ncell) cells
FROM dbstat WHERE name='items_yr' GROUP BY pagetype;
SQL
```

**通過條件**（任一不符 → 調 key 寬度或 value 大小，更新 D3 後重跑）：

| 量 | 預期（200k rows 外插） | 容忍 |
|---|---|---|
| interior fanout（leaf/L1-interior） | ≈ 38 | [33, 43] |
| leaf 每頁筆數 | ≈ 17 | [15, 19]（overflow 頁必須 = 0） |
| depth | 4（200k 規模）；外插至 5M → 5 | 精確 |

### 10.4 cgroup 公平性 sanity check（v3 新增，YR-P 開跑前）

```bash
# 確認 MemoryMax 真的在掐 file cache，且 memory.stat 可讀出分母
systemd-run --scope -p MemoryMax=48M --wait bash -c '
  cat /tmp/yr_proto.db > /dev/null
  grep -E "^(file|anon) " /sys/fs/cgroup/$(cat /proc/self/cgroup | cut -d: -f3)/memory.stat
'
# 預期：file 值被壓在 limit 之下、遠小於 DB 大小；anon 為 process 自身開銷
# 並確認 drop_caches 後重跑，file 從 0 開始長
```

---

## 附錄 A：修訂對照

### A.1 v1 → v2（保留原文）

| v1 位置 | v1 說法 | v2 修正 | 嚴重度 |
|---|---|---|---|
| §3.1 | `insertorder` 是全域自變數，ordered → 熱點集中左端 | 對 `zipfian` **無效**（ScrambledZipfian 先 hash）。軸改掛 `hotspot` / `latest` | 🔴 會讓 headline 自變數變成 no-op |
| §2.3 註解 | 「用 TEXT PRIMARY KEY」（一句話帶過） | 獨立成 §2.5。TEXT PK = 查詢穿兩棵樹 → 與舊 baseline 不可比。改用 order-preserving dense rowid | 🔴 換掉研究對象 |
| §2.2 / §3 | `zeropadding=8`（表格寫「8 或 19」） | **19**，兩臂統一。8 + hashed = 變長 key = fanout 不穩 | 🟠 一行改動，不改整個 fanout 分析報廢 |
| §3 | `-p zipfianconstant=0.99`（勿動） | **移除**。它是 no-op；論文寫「we set」是假話。skew 一律引實測值 | 🟠 論文事實錯誤 |
| §0 | 「CoreWorkload 的 key 一律由 recordcount / insertcount 界定」 | 錯。keychooser 上界**刻意超出** keyspace；靠 `nextKeynum()` 的 rejection loop 擋 | 🟡 結論對，理由錯 |
| （無） | — | **§3.3 `load_order` 解耦**：ordered load fill≈100% vs random load fill≈69% → 兩臂頁數差 45% | 🔴 confound 可能大於主效應 |
| §3 | `fieldcount/fieldlength` 用預設 10×100B | 由「對齊舊 DB page count」反推。預設 → skeleton 僅 1.6MB → 效應可能直接消失 | 🔴 決定效應是否物理上存在 |
| §4 | 16 configs × 10 traces = 160 | 10 configs，分層 traces ≈ 360 runs（v1 ≈ 960） | 🟡 成本 |
| §1 | Tier 2 = 自造 probe | Tier 2 入場需通過**全部** Tier 0 + `notfound_rate ≤ 1%`。**舊 C 出局** | 🟠 否則錯誤數字續命 |
| §2.3 | `if not m: continue` | fail-fast + `parse_losses == 0`。`-threads 1` 寫死 | 🟠 靜默吞掉損壞資料 |
| （無） | — | **§-1 預先承諾**、**§8 統計聚合**、**§9 成本分層**、**§10 驗證清單** | 🔴 |
| （無） | 「× 10 seeds」 | seed sweep ≠ parameter sweep。"robust" 語意收窄 | 🟠 |

### A.2 v2 → v3

| v2 位置 | v2 說法 / 缺口 | v3 修正 | 嚴重度 |
|---|---|---|---|
| §3.4 | 反推工作單留白；估計骨架 1.6MB | 實測回填：**204KB / fanout 392 / depth 3 / fill 96.8%**。估計錯 8 倍的根因（row≈1KB 假設 vs 實測 126B）明寫 | 🔴 |
| §3.4 / §-1.2 | 「對齊舊 DB」與「逃離 null regime」的衝突未點破；工作單預設對齊是好事 | **目標解耦**：目標 A（橋接）→ headline；目標 B（存在性）→ YR/YR-P。paired design 不需要對齊，對齊只服務目標 A | 🔴 假二選一，是 v2 最大的設計缺口 |
| §-1.2 | 定性的 applicability-condition 降級敘述 | **§3.5 天花板律**：benefit ≤ ρ ≈ 1/(1+fanout)（regime 1）。headline null 從風險變成理論預測 + negative control | 🔴 |
| （隱含） | 「把 DB 弄大到骨架不可快取」被當成可行出路 | **證明此路不通**：ρ 與 DB 大小無關。真正的槓桿 = fanout（YR）與 cache pressure（YR-P） | 🔴 省下一條註定失敗的實驗線 |
| §2.5 | 選項 (c) WITHOUT ROWID 被評「勉強」後擱置 | (c) 對目標 B 是唯一可行解 → **§4.5 YR arm**（保序 key 膨脹、fanout ≈ 38、骨架 ≈ 32MB），Tier 1 | 🟠 |
| （無） | — | **YR-P cache-pressure 軸** + §4.5.3 公平性五規則 + §10.4 sanity check | 🟠 |
| §-1.1 / §2.5 | 兩個空格（headline field size、YD/YE 方案）未填 | **§00 DECISIONS**：D1/D2/D3 CLOSED，D4–D6 OPEN 且集中列管；agent 常設規則杜絕反覆詢問 | 🟠 流程 |
| §8 | settling point 只有 convergence 定義 | **fixed-horizon ABC fallback（D6）**，兩定義並報 | 🟠 YR-P 下 convergence 可能不觸發 |
| §5 | — | 新增 `rho_measured` / `cache_config` / `R_ratio` / `trees_touched` 檢查 | 🟡 |
| §6 | 純 forward-looking | 進度標記（步驟 1 ✅），新增步驟 2.5（YR 原型） | 🟡 |
| §9 | 未含 YR | +Tier 1r / 1r'（~84 runs，DB 1.2GB 的還原成本明列） | 🟡 |

---

## 附錄 B：核心命題

> **公信力不來自 YCSB。**

v1 的隱含理論是「用公認 workload 就能取得公信力」。但如 §3.1 / §3.2 所示，YCSB 綁得沒你以為的緊——它只覆蓋 key 分佈，而 `fieldlength`、`zeropadding`、schema、load order、rowid mapping 每一個都影響 page layout，每一個都還是你選的。

真正的繩子是：

1. **§-1 預先承諾** —— 在看到結果之前把手綁起來
2. **§5 Tier 0 validator** —— 每個形容詞對應一個數字
3. **§3.5 天花板律（v3）** —— 每個效益數字對照一個物理上界。量出超過上界的「好結果」不是驚喜，是 bug 警報

這三個都是你自己造的，而且是這份 spec 裡最好的部分。YCSB 只是第四條繩子。