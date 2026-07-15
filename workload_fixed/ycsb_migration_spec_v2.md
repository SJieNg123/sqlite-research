# YCSB-based Workload Generation — Migration Spec **v2**

> **v2 相對 v1 的主要修訂**
> 1. **§3.1 核心論點修正**：`insertorder` 在 `requestdistribution=zipfian` 下**幾乎是 no-op**（ScrambledZipfianGenerator 已先 hash）。空間局部性軸改由 `hotspot` / `latest` 承載。matrix 從 16×10 縮為分層 ~50 條。
> 2. **新增 §-1 預先承諾**：公信力不來自 YCSB，來自「看到結果前先把手綁起來」。這是全文最重要的一節。
> 3. **新增 §2.5 Schema 決策**：v1 把「用 TEXT PRIMARY KEY」藏在程式碼註解裡。這一句話會換掉研究對象，必須獨立成章。
> 4. **新增 §3.3 load_order 解耦**：`insertorder` 同時汙染物理佈局（fill factor 100% vs 69%），是兩臂間最大的 confound。
> 5. **修正**：`zeropadding` 收斂為 19；`zipfianconstant` 標記為不可調；§0 表格的理由改為 rejection sampling。
> 6. **新增 §8 統計聚合**、**§9 成本分層**、**§10 十分鐘驗證清單**。

> **✅ §10 驗證已實跑（2026-07-14，真 YCSB 0.17.0）** — 完整證據見
> [`verification/VERIFICATION.md`](verification/VERIFICATION.md)。核心 YCSB 內部斷言**全部證實**:
> §3.1(`insertorder` 在 zipfian 下 no-op:ordered/hashed 兩臂 hot-100 皆 10/10 deciles、span>0.97 → **v2 的 10-config matrix 成立,不必退回 v1 的 16**)、
> §10.2(空間局部性軸確實在 `hotspot`/`latest`:hotspot ordered 1/10 vs hashed 10/10)、
> §3.2a(`zipfianconstant` 對 zipfian 無效:0.99→top1 3.87%、0.50→3.71% 不變;`CoreWorkload.java:486` 走硬編碼 0.99 的 2-arg ctor)、
> §3.2b(`zeropadding=8`+hashed→變長 key、19 才固定寬)。
> 本環境有幾處**操作面**與 spec 原假設不符,已就地修正:`bin/ycsb` 是 py2 跑不動、輕量 basic-binding tarball 404、
> YCSB stdout 把 properties banner/op/measurement export **混在一起**(§2.3 parser 會誤爆)、`dbstat` 用 Python stdlib 即可(§5.1)。逐項見下與 VERIFICATION.md。

---

## -1. 預先承諾（Pre-registration）—— 先讀這一節

**這一節必須在跑任何實驗之前 commit，並以 git 時間戳為證。**

v1 spec 隱含一個假設：換成 YCSB 之後，結論會保留下來。§3.1 甚至已經先寫好了勝利宣言的句型（"the benefit rises from X% to Y%"）。這個假設**很可能是錯的**（見 §3.4 的 fanout 試算：預設配置下 interior skeleton 只有 ~1.6MB，幾乎必然整個進 cache，prefetch 收益上限被壓得極低）。

如果不預先承諾，當 headline 顯示效益 ≈ 0 時，會有強烈誘因去「再找一個設定」——**那正是這次遷移要根除的失效模式，只是換了位置重生**。換 generator 堵不住它，換規則才行。

### -1.1 承諾事項

| 項目 | 承諾內容 |
|---|---|
| **Headline 配置** | `YC-hashed`（workloadc + `requestdistribution=zipfian` + `insertorder=hashed`），field size 依 §3.4 反推後**在跑實驗前填入此表**：`fieldcount=___`, `fieldlength=___` |
| **不得事後更換** | headline 配置一旦 commit，不因結果好壞更換。若有正當理由更換，必須在論文中揭露原配置的結果 |
| **主要指標** | area-between-curves（ABC），settling point 依既有 convergence-based 定義 |
| **統計檢定** | paired Wilcoxon signed-rank，n = trace 數（見 §8）。α = 0.05，雙尾 |
| **樣本數** | 見 §9 分層表。**不得看到結果後追加 trace 直到顯著** |

### -1.2 負面結果的預備敘述（現在就寫好）

若 headline 效益不顯著，論文主張降級為：

> *"Interior-node prefetching yields substantial benefit only when request skew maps to spatial locality on the B-tree (`hotspot`/ordered, `latest`/ordered). Under YCSB's default hashed layout — which makes no assumption about key-to-page locality — the benefit is negligible. We therefore characterize the **applicability condition** of the technique rather than report a single headline speedup."*

**這是一個完全可發表、而且比一個泡沫數字更有價值的結論**，因為它給出適用條件。把「結論可能是負的」從危機變成設計的一部分。

### -1.3 形容詞禁令（自 v1 §5 提升為全域規則）

> **任何 workload 的宣稱（"churn-resilient"、"hot-tail"、"skewed"、"robust"）都必須對映到 Tier 0 validator 裡的一個數字。沒有對應數字的形容詞，不准出現在論文裡。**

補充兩條：

- **"robust" 的用法收窄**：跑 N 條 trace 只能支持「對 workload 內變異穩健」。它**不能**支持「對參數選擇穩健」。這兩件事在 reviewer 眼裡是分開的，論文中不得混用。
- **skew 一律引實測值**，不得引用 `zipfianconstant`（原因見 §3.2）。

---

## 0. 目標

把 headline 結論的 workload 來源從「自造 generator」換成「公認 workload 的 trace」，讓下列失效模式在**結構上**不可能發生。

| 已發生的坑 | 來源 | YCSB 是否解掉 | v2 修正 |
|---|---|---|---|
| C 的 −75% 來自 out-of-range not-found 撞最右葉 | 自造 key range `[590000, 609999]` 超過 DB 上限 | ✅ 解掉，但**理由與 v1 所寫不同** | 不是靠 `recordcount` 界定。`keychooser` 的上界其實是 `insertstart + insertcount + expectednewkeys`（**刻意超出**現有 keyspace）。真正擋住 not-found 的是 `nextKeynum()` 的 **rejection loop**（`do{...}while(keynum > lastValue())`）。代價：實際分佈是「Zipf 條件於 keynum ≤ lastValue」，非純 Zipf → **只准引實測分佈** |
| churn「韌性」宣稱，實際 hot page 位移 = 0 | 自造 churn 用抽樣不放回 → 根本沒有 hot set | ⚠️ 半解 | YCSB workload D (`latest`) 有天然 moving hotspot，但**不會自動驗證**位移真的發生 → 仍需 Tier 0 檢查（`hotset_jaccard_series`） |
| tail 範圍是 knife-edge，參數在驅動結論 | 自造參數沒有外部錨點 | ⚠️ **v1 高估了** | YCSB 的公信力只覆蓋 **key 分佈**。`fieldlength` / `zeropadding` / schema / load order 仍然全部是你選的，而且**每一個都影響 page layout**。真正的解藥是 §-1 預先承諾，不是換 generator |
| — | — | ❌ **新坑（v1 已標，但機制寫錯）** | `insertorder` 對 `zipfian` **無效**，只對 `hotspot` / `latest` 有效。見 §3.1 |
| — | — | ❌ **新坑（v1 未發現）** | `insertorder` 同時決定 load 階段的物理佈局（fill factor 100% vs 69%），是兩臂間的隱藏 confound。見 §3.3 |
| — | — | ❌ **新坑（v1 未發現）** | 「用 TEXT PRIMARY KEY」會把單棵 rowid B-tree 換成「rowid table + index B-tree」= 每次查詢穿兩棵樹 → 與舊 A/B/C 完全不可比。見 §2.5 |

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

> **🔧 本環境實際做法（無 sudo、無 Java/Maven）** — 見 [`env/ycsb_env.txt`](env/ycsb_env.txt)。
> 這台機器沒有 java/mvn,故:(1) 下載可攜式 Temurin-17 **JRE** tarball 解壓到 `~/ycsb-tools/jre`;
> (2) **不 build**,直接抓 Maven Central 的 `site.ycsb:core:0.17.0` + `HdrHistogram` + `htrace-core4` 三個 jar;
> (3) **不要用 `bin/ycsb`**——它是 Python-2 腳本(`print >> sys.stderr`),py3 跑不動;輕量 `ycsb-basic-binding-0.17.0.tar.gz` **已 404 不存在**。
> `BasicDB` 就在 **core jar** 裡(`site.ycsb.BasicDB`),不需要另一個 basic binding jar。改成直接叫 `Client`:
> ```bash
> JAVA=~/ycsb-tools/jre/bin/java; CP="$HOME/ycsb-tools/jars/*"
> "$JAVA" -cp "$CP" site.ycsb.Client -load|-t -db site.ycsb.BasicDB -P <workload> -threads 1 …
> ```

> ⚠️ **在寫任何 parser 之前，先跑 §10 的驗證清單。** 本 spec 對 YCSB 內部行為的所有斷言都必須自己確認過。花十分鐘，省掉一輪實驗。（**本 repo 已跑完,結果見 [`verification/VERIFICATION.md`](verification/VERIFICATION.md)。**）

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
```

> **本環境的等價指令**(`bin/ycsb` py2 不可用 → 直接叫 `Client`,見 §2.1):
> `bin/ycsb load basic -P W …` ≡ `"$JAVA" -cp "$CP" site.ycsb.Client -load -db site.ycsb.BasicDB -P W …`;
> `bin/ycsb run basic …` ≡ `… site.ycsb.Client -t -db site.ycsb.BasicDB …`。其餘 `-p` 參數原封不動。
> 實測 verbose 行格式(driver §2.3 parser):`OP usertable user<19位> [SCAN 時此處是 <len>] [ <fields> ]`,
> table token 恆為 `usertable`,SCAN 長度在 `[` 之前。

**v2 相對 v1 的指令變更**

| 變更 | 理由 |
|---|---|
| `-threads 1` **寫死** | BasicDB verbose 用 `System.out.println`，`-threads > 1` 會讓行交錯甚至撕裂。這是**正確性**問題，不是效能問題 |
| `zeropadding=8` → **`19`** | 見 §3.2。`8` + hashed 會產生變長 key → fanout 不穩定 → 破壞 spec 自己訂的目標 |
| `fieldcount=1 fieldlength=1` | verbose 會 `toString()` 整個 value；預設 10×100B 會讓 load log 膨脹到 600MB–1GB。**trace 是 value-agnostic**，row size 由 harness 參數決定（見 §3.4），必須在 manifest 明記此事 |
| 移除 `-p zipfianconstant=0.99` | **它是 no-op**（見 §3.2）。留著等於在論文裡寫一句假話 |

### 2.3 Parser（YCSB log → 你現有的 trace 格式）

> **⚠️ 實測修正:YCSB stdout 是三種 stream 混在一起的**——啟動時的 `***properties***` banner、
> BasicDB 的 verbose op 行、跑完的 measurement export(`[READ], Operations, …`、GC 統計)全在 stdout。
> 下面這版 parser 的 `if not m: n_bad += 1` **會把 banner/export 每一行都算成壞行而誤爆**。正解:把每行分類為
> **op / 已知雜訊(banner=`*`或`"k"="v"`、export=`[...],`) / 未知**,只在「未知」時 fail,並仍斷言
> `#ops == operationcount`(這樣既不誤爆、又不會靜默漏真 op)。實作見 `tools/ycsb2trace.py`。

```python
# tools/ycsb2trace.py
"""YCSB BasicDB verbose log -> trace (JSONL).

紅線：parser 只做格式轉換。任何「key 重新映射」「key 排序」「補 not-found key」
都會把剛拿回來的公信力吐掉。

唯一允許的映射是 §2.5 的 order-preserving dense rowid，且它必須在**獨立的**
tools/keymap.py 中實作，並附保序性的單元測試。不得混進 parser。
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
| `key TEXT PRIMARY KEY) WITHOUT ROWID` | 1 棵 index-organized B-tree | 1，但 cell 變大、fanout 掉、1KB row 易 overflow | ⚠️ 勉強 |

中間那個是災難：你的研究對象是「interior node skeleton」，改用 TEXT PK 之後**每次查詢要穿過兩棵樹的 interior**。§3 表格「`recordcount` 對齊 600000 → 讓 YCSB 結果能跟舊 A/B/C 對照」這個理由**直接失效**。

#### 決策：order-preserving dense rowid（推薦）

`insertorder` 的作用只是決定 **keynum → B-tree 位置的排列**。這個排列可以在保持 `INTEGER PRIMARY KEY` 的前提下完整重現：

```
ordered:  rowid = keynum + 1                       # 恆等排列
hashed:   rowid = rank of Utils.hash(keynum)       # 把 N 個 hash 值排序後取名次，dense 1..N
```

> **🔧 實作改進(避免重寫 FNV hash)**:不要在 Python 裡重新實作 `Utils.hash`,而是**直接讀 YCSB 自己的
> load-phase dump**——load 階段會把全部 `recordcount` 個 key 以 `INSERT usertable user… ` 印出,那就是
> ground-truth 的 key 字串宇集。因為 `zeropadding=19` 使 key 定長,**字典序 == 數值序 == B-tree on-disk 序**,
> 所以 `sorted(load 的 user… 字串)` 取名次即 dense rowid。這消掉「自己實作 hash 可能跟 YCSB 不一致」的風險,
> 保序性也因此是 by-construction。`tools/keymap.py` 吃 (load dump, run trace) 兩檔輸出 int-key trace。

**這不是 §2.3 紅線禁止的「key 重新映射」——它是保序同構（order-preserving bijection）。** B-tree 上誰跟誰相鄰、熱點集中或散開，完全保留；被消掉的只有「key 是字串」這個對本研究無關的表象。

好處：

- Schema 不動 → 跟舊 A/B/C 直接可比
- 兩臂 key encoding **完全相同**（dense int、同 varint 寬度、同 fanout）→ **唯一差異就是「哪些 key 相鄰」= 真正的自變數**
- 不用 TEXT PK、不用 WITHOUT ROWID、不用重跑 baseline

⚠️ **限制**：dense rank 需要**預先知道全部 key**，只適用於**無 insert 的 workload**（`YC` / `YC-u` / `YC-h` / `YA` / `YB` / `YF`）。

#### 有 insert 的 workload（`YD` / `YE`）

新 key 必須插進 B-tree 中間 → dense rank 不可用。三選一，**必須在此表填入決定**：

| 選項 | 做法 | 代價 |
|---|---|---|
| (a) sparse rowid | `rowid = Utils.hash(keynum)`（64-bit 正整數） | 9-byte varint → interior cell 7B→13B → fanout ~500→~290 → **與無 insert 組不可比** |
| (b) 預留 rank 空間 | load 時對 `keynum ∈ [0, recordcount + expectednewkeys)` **全部**取 rank，只插入前 `recordcount` 個 | 保持 dense-ish，insert 的 rowid 已預先決定 → **推薦** |
| (c) TEXT PK WITHOUT ROWID | 照 YCSB 原樣 | fanout 大跌、需重跑全部 baseline |

**決定：______**（跑實驗前填）

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
| `recordcount` | 600000（對齊現有 DB **row 數**） | ⚠️ 不夠。真正要對齊的是 **page count / B-tree 層數**，見 §3.4 |
| `zeropadding` | **19**（兩臂統一，不再是「8 或 19」） | 見 §3.2 |
| `fieldcount` / `fieldlength` | **不抄預設**，由 §3.4 反推 | 決定 leaf 塞幾筆 → 直接決定 leaf/interior 比例與 B-tree 層數 |
| `operationcount` | 80000（對齊現有） | — |
| `maxscanlength` / `scanlengthdistribution` | workload E 預設（100 / uniform） | — |
| `insertproportion` | workload D/E 預設 5% | 唯一會讓 DB 長大的旋鈕 |
| `hotspotdatafraction` / `hotspotopnfraction` | 只在 `requestdistribution=hotspot` 時。**掃一整條線，不能只報一個點** | 固定熱點，取代自造「tail 區間」的公認做法 |
| **`load_order`（新增）** | 見 §3.3 | **從 `insertorder` 解耦出來的獨立變數** |

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

### 3.4 `fieldlength` 決定 B-tree 有幾層 —— 先算再選

v1 寫「預設 10 × 100B（≈1KB/row）… 任何偏離都要說明」。但預設值會給你什麼？

以 `page_size=4096`、`recordcount=600000`、row ≈ 1KB、usable ≈ 4061：

| 量 | INTEGER PK（dense rowid） | TEXT PK WITHOUT ROWID（19 字元 key） |
|---|---|---|
| leaf 每頁筆數 | ~3 | ~3 |
| leaf 總數 | ~200,000 | ~200,000 |
| interior cell 大小 | 4 + 3 varint ≈ **7B** | 4 + ~24 ≈ **28B** |
| interior fanout | **~500** | **~145** |
| B-tree 層數 | root → 400 → 200k = **3 層** | root → 10 → 1400 → 200k = **4 層** |
| interior skeleton 總量 | ~400 pages ≈ **1.6 MB** | ~1400 pages ≈ **5.7 MB** |
| DB 大小 | ~**800 MB** | ~800 MB |

兩個致命推論：

1. **1.6MB 的 skeleton 幾乎必然整個進 cache** → prefetch 它的收益上限被壓得極低 → **你的效應可能在 YCSB 預設下直接消失**。這不是壞事（那就是誠實的答案，見 §-1.2），但要**事先知道**，而不是跑完全部 trace 才發現。
2. **舊 DB 多大？** 若舊 A/B/C 的 DB 只有幾十 MB，換成 800MB 之後你不只換了 workload，還換了**整個 regime**（DB : RAM 比例、B-tree 層數、skeleton 是否 cacheable）。「對齊 recordcount」根本不夠。

#### 規則

> `fieldcount × fieldlength` **由「要對齊舊 DB 的 page count / B-tree 層數」反推**，不抄 YCSB 預設。

論文理由：*"we set field size to preserve storage-layout comparability with our prior configuration"* ——這比抄預設更站得住腳，因為 **field size 不是 YCSB 的公信力來源，key 分佈才是**。

#### 反推工作單（跑實驗前填）

| 量 | 舊 DB 實測 | YCSB 目標 | 需要的 `fieldcount × fieldlength` |
|---|---|---|---|
| page_count | ______ | 對齊 | |
| leaf page 數 | ______ | 對齊 | |
| B-tree depth | ______ | 對齊 | |
| interior skeleton (MB) | ______ | 對齊 | |
| DB size | ______ | — | **→ 決定：______** |

---

## 4. Workload matrix（v2：分層，非全展開）

`insertorder` 只在 `hotspot` / `latest` 上是自變數（§3.1），因此 v1 的 16 條縮減如下。

| ID | YCSB base | `insertorder` 臂 | 覆蓋什麼 | 取代誰 |
|---|---|---|---|---|
| **YC** | workloadc (100% read, zipfian) | **hashed only** | **HEADLINE**：純讀熱點，無 key-to-page locality 假設 | 舊 C（含 −75% artifact） |
| YC-u | workloadc + `requestdistribution=uniform` | hashed only | **no-locality 地板** | 新增，必要 |
| **YC-h** | workloadc + `requestdistribution=hotspot` | **hashed × ordered** | 固定熱點。**空間局部性軸之一** | 舊 C 的 tail 區間 |
| **YD** | workloadd (read-latest + 5% insert) | **hashed × ordered** | 移動熱點 = 真正的 churn。**空間局部性軸之二** | 舊 churn（hot set 位移 = 0 的那個） |
| YA | workloada (50/50 R/U, zipfian) | hashed only | 寫入混合 | 舊 A |
| YB | workloadb (95/5, zipfian) | hashed only | 讀為主 | 舊 B |
| YE | workloade (short scan + insert, zipfian) | hashed only | range 存取 | 舊 scan |
| YF | workloadf (RMW, zipfian) | hashed only | RMW | 舊 rmw |

**臂數**：6 (hashed only) + 2×2 (spatial axis) = **10 configs**（v1 為 16）。
**`YC-h` 額外要求**：`hotspotdatafraction` 掃一整條線（如 0.01 / 0.05 / 0.1 / 0.2 / 0.5），**不能只報一個點**——否則就是舊「tail 區間 knife-edge」的重演。

---

## 5. Tier 0 Validator — 這才是真正堵住坑的東西

**YCSB 不會幫你檢查任何東西。** 它只保證 key 分佈是公認的。
被咬的兩次（churn 位移 = 0、C 的 not-found）都是「敘事沒有物理量佐證」，**換 generator 不會自動解決**。

### 5.1 前置條件（v1 未列）

`rightmost_leaf_share` 與 `hotset_jaccard_series` 都需要 **key → page 映射**。取得方式：

> **🔧 實測修正:不必自編 sqlite。** 本機 **Python stdlib `sqlite3`(3.46.1)已內建 `dbstat` vtab**,
> 直接用即可,不需要 `gcc -DSQLITE_ENABLE_DBSTAT_VTAB`。另注意本機**沒有 `sqlite3` CLI**,所以下面的 shell
> `sqlite3 … "SELECT … FROM dbstat"` 跑不起來 → validator 一律走 Python。(既有 repo 另有一支 raw-header C
> parser `pipeline/preparation/classify_pages` 也可分類 interior/leaf,但頁計數本來就用 `PRAGMA page_count`。)

```python
# 每個 page 的 payload / cell 數 / 名稱（Python，dbstat 已內建）
import sqlite3
con = sqlite3.connect(db_path)
con.execute("SELECT name, path, pageno, pagetype, ncell, payload, unused "
            "FROM dbstat WHERE name='items'").fetchall()
```

或自行 parse b-tree page header。**這是 §6 步驟 3 的硬前置條件，沒有它 validator 只是半個。**

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

  # ── 新增：堵 §3.3 的物理佈局 confound ──
  "page_count":     "DB 總頁數。同一組實驗的兩臂必須一致，否則 headline 作廢",
  "fill_factor":    "leaf page 平均填充率。ordered load ≈ 100%，random load ≈ 69%",
  "btree_depth":    "B-tree 層數。跨設定不一致 = 不可直接比",
  "skeleton_bytes": "interior page 總量。決定 prefetch 的收益上限（§3.4）",

  # ── 新增：堵 §3.1 的 no-op 自變數 ──
  "hot_key_contiguity": "top-1% key 在 rowid 空間的相鄰程度（如平均 gap / 佔用 leaf 數）。"
                        "若 ordered 與 hashed 兩臂此值相近 → insertorder 是 no-op，"
                        "該條 sensitivity axis 作廢，不得在論文中宣稱它是變數",

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

## 6. 遷移步驟（v2 重排：驗證優先）

| # | 步驟 | 產出 / 通過條件 |
|---|---|---|
| **0** | **跑 §10 驗證清單** | 確認 A1（insertorder 是否 no-op）、A2（zipfianconstant）、格式。**這一步會決定 §3.1 和 §4 要不要再改寫** |
| **1** | **量舊 DB 的 page_count / depth / skeleton_bytes**，填 §3.4 反推工作單 | 決定 `fieldcount × fieldlength` |
| **2** | **決定 schema（§2.5）**，寫 `tools/keymap.py` + 保序性單元測試 | 兩個測試必須綠 |
| **3** | **先寫 `validate_trace.py`（含 dbstat 前置），回頭跑舊的 A/B/C/churn** | ⭐ **這一步把已知的兩個坑變成硬數字，是給老師看的最強證據。做在遷移之前，不是之後** |
| **4** | **寫 §-1 預先承諾並 commit** | git 時間戳。**必須在步驟 5 之前** |
| 5 | 跑一次 `basicdb.verbose=true`，寫 `ycsb2trace.py`，產 1 條 YC-hashed，跟舊 workload 並排比對統計 | parse_losses == 0 |
| 6 | 生成完整 matrix（§4 × §9 分層），每條配 manifest + validation | 全部通過 Tier 0 |
| 7 | 重跑 A3/A4，headline 只引用 Tier 1 | 依 §8 聚合 |
| 8 | 舊自造 workload 依 §1.3 處置（C 退場，其餘降級 Tier 2 + 改名） | — |

---

## 7. 誠實的限制（論文 threats to validity 直接寫）

- YCSB 是 KV API 層，**表達不出 page-layout 語意**。任何關於 interior node 結構的細緻機制探討仍需 Tier 2 probe。這不是弱點，是分工。
- YCSB 沒有「hot set 在 keyspace 中間搬移」的 workload（`latest` 只往尾端長）。要測這個只能自造 → Tier 2。
- 用 BasicDB dump trace = 不含真實 client 的 timing / concurrency。實驗是 storage-layout 導向，通常可接受，但要寫明。
- `zeropadding` / `fieldlength` 一動 fanout 就變，跨設定不可直接比。已固定（§3.2 / §3.4）。
- **（新增）** YCSB 的公信力**只覆蓋 key 分佈**。`fieldlength` / `zeropadding` / schema / load order / rowid mapping 全部是我們的選擇，且每一個都影響 page layout。**這些選擇的公信力來自 §-1 預先承諾與 §5 validator，不來自 YCSB。**
- **（新增）** `requestdistribution=zipfian` 的實際分佈是「Zipf 條件於 keynum ≤ acknowledged insert counter」（rejection sampling），且經過 ScrambledZipfian 的 rank→keynum hash 折疊。**它不是 Zipf(0.99, N=recordcount)**，任何解析式試算不適用；一律引實測值。
- **（新增）** 用 order-preserving dense rowid 取代 TEXT key（§2.5）保留了 B-tree 的相鄰關係，但改變了 key 的物理表示（string → int）。cell 大小與 fanout 因此與原生 YCSB-on-SQLite 不同。此舉是為了與 prior configuration 可比；trade-off 明寫。

---

## 8. 統計聚合（v1 完全缺）

v1 只寫「× 10 seeds」，沒說怎麼合成一個數。

| 項目 | 方案 |
|---|---|
| **配對** | 同一條 trace 上跑 pread 與 fadvise → **天然 paired design**，消掉 trace 間變異。**不得跨 trace 比較** |
| **報告單位** | **per-trace ABC 差值的分佈**（N 個點），不是只報平均。畫 dot plot 或 paired slope chart |
| **檢定** | paired **Wilcoxon signed-rank**（N 小，不假設常態）。報 effect size 與 CI，不只報 p |
| **重複** | 每條 trace × 每策略跑 3 次 cold-start，取 median 作為該 trace 的代表值（消掉 run-to-run 噪音，再進 paired 檢定） |
| **⚠️ 語意紅線** | N 條 trace 檢定的是 **workload 內變異**，不是**參數敏感度**。這兩件事在 reviewer 眼裡是分開的。**論文中不得用同一個 "robust" 涵蓋兩者**（= §-1.3） |

---

## 9. 成本分層（v1 完全缺）

v1 的 `16 × 10 = 160` × `{pread, fadvise}` × cold-start × repeat 3 = **~960 次冷啟動 run**，每次還要還原 800MB DB 到 FEMU。粗估 3 分鐘/次 → **~48 小時純跑**，未計失敗重跑。

配合 §3.1（zipfian 下 insertorder 是 no-op）與分層，可砍到 ~1/3，**而且更有論證力**——每一條都有存在的理由。

| 層 | 內容 | traces | configs | runs（×2 策略 ×3 repeat） |
|---|---|---|---|---|
| **Tier 1a** | **headline**：YC-hashed | **10** | 1 | 60 |
| **Tier 1b** | **spatial axis**：YC-h × {hashed, ordered}、YD × {hashed, ordered} | **5** | 4 | 120 |
| **Tier 1c** | 其餘：YA / YB / YE / YF / YC-u | **3** | 5 | 90 |
| **Tier 1b'** | `hotspotdatafraction` sweep（YC-h，5 點） | 3 | 5 | 90 |
| | | | **合計** | **~360 runs ≈ 18 小時** |

**load trace 只需 2 條**（每個 `insertorder` 一條），不需 10 條 —— load 階段 keysequence = `CounterGenerator`，**零隨機性**（v1 的「16 × 10」把 load 也算進去了）。

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
| `ordered` 的 top-100 key **也散佈在整個 keyspace** | ✅ §3.1 成立（ScrambledZipfian 先 hash 了）→ 依 v2 的 §4 matrix 執行 |
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

---

## 附錄 A：v1 → v2 修訂對照

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

---

## 附錄 B：核心命題

> **公信力不來自 YCSB。**

v1 的隱含理論是「用公認 workload 就能取得公信力」。但如 §3.1 / §3.2 所示，YCSB 綁得沒你以為的緊——它只覆蓋 key 分佈，而 `fieldlength`、`zeropadding`、schema、load order、rowid mapping 每一個都影響 page layout，每一個都還是你選的。

真正的繩子是：

1. **§-1 預先承諾** —— 在看到結果之前把手綁起來
2. **§5 Tier 0 validator** —— 每個形容詞對應一個數字

這兩個都是你自己造的，而且是這份 spec 裡最好的部分。YCSB 只是第三條繩子。