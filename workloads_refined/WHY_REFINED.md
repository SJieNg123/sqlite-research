# 為什麼是 `workloads_refined`（而不是舊的 `workloads`）

> **回答的疑慮**：「refined 只有 6 個，舊的有一堆 distribution，是不是舊的比較強？」
>
> **不是。而且理由不是「我們篩選過」——那個說法很危險，見 §1。**
>
> 真正的理由是三個字：**出處、可複現、閘會叫。**
>
> 證據來源：舊 `workloads/` 已於 2026-07-16 刪除，以下引自 git（最後 commit `66db889`）的
> `workloads/gen_workload.py`、`workloads/README.md`，以及 `workloads_refined/raw/`、
> `gen_ycsb_trace.sh`、spec v4 §1.3 / §3.1 / §3.2 / §5。

---

## 1. 先拆掉「篩選」這個框架 —— 它會害死你

如果 refined 比較好是因為「**我們挑掉了不好的**」，reviewer 的下一句話一定是：

> **「『不好的』是哪個意思？是『壞掉的』，還是『給了你不想要的答案的』？」**

**而那個問題，正是這整個專案存在的理由。**

實情是：舊 workload C 確實出局了。**但讓它出局的不是品味，是一條規則**——

```
§1.1（寫在看到任何結果之前，有 git 時間戳）:
     notfound_rate ≤ 1%   →   超過就退場
```

然後 Tier 0 validator 量出來：

```
舊 C:  notfound_rate = 0.5000   （10 個 seed 全同，結構性）
```

**0.5 > 0.01 → 出局。沒有人做任何決定。**

> ### 所以正確的說法是：
>
> **不是「我們留下了好的」。**
> **是「我們先寫下規則，然後它自己出局了」。**

差別在哪？「篩選」把功勞放在**你的判斷**上。規則把功勞放在**制度**上。

**而這整個專案花了一個月在做的，就是把判斷從迴路裡拿掉。**

---

## 2. 兩邊到底是什麼

| | 舊 `workloads/` | `workloads_refined/` |
|---|---|---|
| **trace 從哪來** | **手寫 Python 模擬** YCSB 語意（`gen_workload.py`） | **真的跑 YCSB 0.17.0**（java Client + BasicDB verbose） |
| **自我描述** | 檔案開頭寫著：*"Reconstructed to reproduce the distributions of the original committed files… **original seeds unknown** — the distribution is [reproduced]"* | **trace 檔本身就是 seed**；raw log 有 sha256 |
| **驗證** | 信生成器，**沒有閘** | 每條過 fail-loud 閘（notfound / skew / op-mix / id 範圍 / moving-hotspot） |
| **provenance** | **無**（seed 已失傳，只保證「分布相符」） | manifest：raw load/run log 的 sha256 + YCSB commit + 完整 property 列表 |

**關鍵那一行**：舊檔**自己承認**是「重建原始分布的複製品，原始 seed 已失傳」。

> 舊的 = **一個手寫的 YCSB 仿製品**
> refined = **YCSB 本尊**

---

## 3.「只有 6 個」是誤讀

那 6 個是 **YCSB 官方命名的 workload A–F**——reviewer 一看名字就認得的正典。

**distribution 的多樣性不在「幾個檔案」，在 YCSB 自己的旋鈕**，而且變體早就在 `raw/` 裡了：

```
workloads_refined/raw/ 現有：
  YC                                          ← headline（zipfian）
  YC-u                                        ← uniform 地板
  YA, YB, YF
  YC-h-hashed-hdf{0.01, 0.05, 0.10, 0.20, 0.50}    ← hotspotdatafraction sweep
  YC-h-ordered-hdf{0.01 .. 0.50}                    ← insertorder 軸
                                              = 15 條，全部 Tier 0 PASS
```

### ✅ 真的能用的旋鈕

| 旋鈕 | 值 | 備註 |
|---|---|---|
| `requestdistribution` | `zipfian` / `uniform` / `latest` / `hotspot` | 主軸 |
| `insertorder` | `hashed` / `ordered` | ⚠️ **只在 `hotspot` / `latest` 下有效**，見下 |
| `hotspotdatafraction`<br>`hotspotopnfraction` | 0–1 連續 | 只在 `requestdistribution=hotspot` 時 |
| `recordcount` / `operationcount` / `insertproportion` | 任意 | — |

### ❌ 兩個「看起來是旋鈕、其實不是」的陷阱

**這兩個在 spec 裡各殺過一次，但它們很會復發——所以寫在這裡。**

| 假旋鈕 | 為什麼是假的 |
|---|---|
| **`zipfianconstant`** | **在 `requestdistribution=zipfian` 下是 no-op。**`CoreWorkload` 呼叫的是 `new ScrambledZipfianGenerator(min, max)`——**沒有傳這個參數**。你設 0.9 會被**靜默無視**。<br>**論文寫「we set zipfianconstant=0.99」= 寫了一句假話**（§3.2a）。skew 一律引 Tier 0 的 `measured_skew` 實測值。 |
| **`insertorder` 搭 `zipfian`** | **也是 no-op。**`ScrambledZipfianGenerator` 在 `buildKeyName()` **之前**就已經把 rank→keynum hash 打散了，所以 `ordered` 和 `hashed` 給出的熱點空間分佈**幾乎一樣**（§3.1）。<br>**要連續的熱 key，只能用 `hotspot` 或 `latest`。** |

---

## 4. 舊的每一種 distribution，refined 都有對應（而且有出處）

⚠️ **注意左欄的名字**：舊 `gen_workload.py` 的 `A`/`B`/`C` **跟 YCSB 官方的 A/B/C 完全不是同一個東西**（§1.3）。這正是它們被強制改名的原因——reviewer 看到「workload C」會以為你在報 YCSB-C 的結果。

| 舊類型 | 它實際上是什麼 | refined 對應 | 用什麼旋鈕 |
|---|---|---|---|
| **A**（→ `RO_ZIPF_SCATTER`） | 100% read, scrambled zipfian<br>（**這其實是 YCSB-C 的語意，不是 YCSB-A**） | **YC** | `workloadc` + `zipfian` + `hashed` |
| **B**（→ `RO_UNIFORM`） | 100% read, **uniform**<br>（YCSB-B 是 95/5 read/update——完全不同） | **YC-u** | `workloadc` + `uniform` |
| **Z** | low-key Zipf（熱點集中在 keyspace 一端） | **YC-h（ordered 臂）** | `hotspot` + `insertorder=ordered`<br>⚠️ **不是** `zipfian`+`ordered`（那是 no-op，見 §3） |
| **CHURN**（→ `CHURN_NOHOT`） | 宣稱「移動熱點」<br>**實測：`unique_key_ratio = 1.0`，根本沒有熱集** | **YD** | `workloadd` + `latest`（真正的 moving hotspot） |
| **C** | tail 邊界探針，50% not-found | **無對應——已退場**，見 §5 | — |
| scan | short ranges | **YE** | `workloade` |
| rmw | read-modify-write | **YF** | `workloadf` |

**每一格的差別**：舊的是「我手刻了一個我認為長這樣的分布」；refined 是「我傳了一個 YCSB 原生參數，YCSB 自己產的」。

---

## 5. 兩個出局的，以及讓它們出局的規則

**這一節是 refined 最強的證據，而且它不需要任何 timing。**

### ① 舊 workload C —— 「−75% 收益」是假訊號

```
規則（先寫）:  §1.1  notfound_rate ≤ 1%
實測（後量）:  notfound_rate = 0.5000     ← 10 個 seed 全同
```

**一半的查詢在找不存在的 key**（key range 590000–609999，但 DB 只到 600000）。

那些超出上限的查詢會**一路爬到最右邊那個葉子**才發現沒有 → 5 萬次查詢全部撞同一頁 → 那頁永遠在 cache → 幾乎免費 → **那就是「−75%」的來源**。

> **它量的不是預取效果，是「一半的查詢根本沒在查東西」。**

### ② 舊 CHURN —— 宣稱「移動熱點」，但沒有熱點

```
規則（先寫）:  §-1.3  任何形容詞都必須對應到 validator 裡的一個數字
實測（後量）:  unique_key_ratio = 1.0      ← 抽樣不放回 → 每個 key 只出現一次
              查詢 key 均勻攤在 [1, 600000]，質心 299,451 → 299,691（不動）
```

> **它號稱測「熱點會移動」。實際上沒有熱點，所以沒有東西可以動。**

### ③ 而 validator 自己也被抓到兩個洞（這是方法論貢獻，不是丟臉）

| 洞 | 症狀 | 修法 |
|---|---|---|
| RMW op-count 守衛 | 硬編「1 op = 1 行」，但 read-modify-write 印 2 行 → YF 誤報 | 改成 per-workload 預期 |
| **moving-hotspot 檢查** | **從沒接進 verdict**，而且 jaccard 分不出「熱點飛得快」vs「根本沒熱點」（兩者都 = 0）→ **churn 一路 PASS** | 三層前置閘：**有熱集？→ 聚攏？→ 動嗎？** churn 現在實測 **FAIL** |

> **你專門為了抓 churn 而設計的檢查，曾經給 churn 開綠燈。**
> 而抓到這件事的，是「每個閘都必須有一個證明它會開火的測試」這條規則。

---

## 6. 舊的靈活性去哪了？—— 沒有失去，降級成 Tier 2

**這不是取捨，是分工。** §1 的三層架構早就處理了：

```
Tier 0  Trace Validator      ── 所有 trace 都要過，才能進實驗
Tier 1  YCSB-generated       ── 唯一能做「一般性宣稱」的來源（headline / abstract）
Tier 2  自造 mechanism probe ── 能做，但只能講機制
```

**自造 generator 沒有被禁止。** 它是 Tier 2：

- ✅ **可以用**——任意 α、任意 keyspace、bimodal、自訂 churn，秒出，不用 java
- ✅ **論文可以放**——但圖表 caption 必須標 `"mechanism probe, not a general result"`
- ❌ **不能進 abstract / 結論 / headline**
- ⚠️ **入場要過全部 Tier 0 檢查 + `notfound_rate ≤ 1%`**（這條就是舊 C 出局的地方）

**而 §7 threats 甚至明寫**：

> 「YCSB 沒有『熱點在 keyspace 中間搬移』的 workload（`latest` 只往尾端長）。要測這個只能自造 → Tier 2。」

> **所以舊的靈活性是一個 feature，不是被丟掉的東西。**
> **它只是不能拿來當 headline——因為它的參數是你選的，沒有外部錨點。**

---

## 7. 但也別高估 refined —— 這是核心命題

> ### 公信力不來自 YCSB。（附錄 B）

YCSB 綁得沒你以為的緊。**它只覆蓋 key 的分佈。**

而 `fieldlength`、`zeropadding`、schema、load order、rowid mapping——**每一個都影響 page layout，每一個都還是你選的。**

**真正的繩子是這五條：**

| # | 是什麼 |
|---|---|
| 1 | **§-1 預先承諾** —— 看到結果之前把手綁起來 |
| 2 | **§5 Tier 0 validator** —— 每個形容詞對應一個數字 |
| 3 | **§3.5 天花板律 + 分割定理** —— 每個效益數字對照一個物理上界 |
| 4 | **§10 驗證閘** —— 在花錢之前，讓 spec 有機會否決自己 |
| 5 | **YCSB** ← **只是第五條** |

**前四條都是你自己造的。**

---

## 8. 一句話

> **refined 不是「distribution 變少了」。**
> **是「同樣的 distribution，換成有出處、可複現、過驗證的來源」。**

「6」是 **YCSB 正典的類別數**，不是能力數。多樣性由原生旋鈕展開（`requestdistribution` × `insertorder` × `hotspot` 比例），`raw/` 裡已經有 **15 條**。

用舊的靈活性，換到的是：**seed 可追、閘會叫、名字 reviewer 認得。**

**探索期舊的方便（→ Tier 2）。要寫進論文，refined 才站得住（→ Tier 1）。**

---

## 附錄：這份文件自己的教訓

這份文件的**第一版**寫錯了三件事，全部被 spec 攔下來：

| 寫錯的 | 被什麼攔下 |
|---|---|
| 「Z → `zipfian` + `insertorder=ordered`」 | **§3.1**：那是 v1 的原始錯誤，一字不差。zipfian 下 insertorder 是 no-op |
| 把 `zipfianconstant` 列成可用旋鈕 | **§3.2a**：它是 no-op，寫進論文就是假話 |
| 「舊 C → YCSB workload C」 | **§1.3**：舊 C ≠ YCSB C，而且舊 C 已經退場 |

**三個都是同一個直覺的復發**：「這是我能調的旋鈕」。

跟 fanout 那個「interior cell 只有 key」的直覺一樣——**你以為殺掉的錯誤直覺，會在另一份文件裡重新長出來。**

> **這就是為什麼那些「看起來很囉唆」的規則要寫下來：**
> **它們現在正在當免疫系統用。**