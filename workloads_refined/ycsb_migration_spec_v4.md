# YCSB-based Workload Generation — Migration Spec **v4**

> **v4 相對 v3 的主要修訂 —— 全部由 §10.3 的 D3 閘實測觸發**
>
> §10.3 這道閘擋下了 v3 §4.5 的核心幾何錯誤。**這是預先承諾制度第一次真正發揮作用**：v3 的紙上外插被自己訂的驗證規則否決，而不是被 1.2GB DB 建完之後的困惑否決。
>
> 1. **🔴 §4.5 幾何全面重算**：v3 算「WITHOUT ROWID 的 interior cell ≈ child ptr + key(100B) ≈ 106B → fanout 38」。**錯。index B-tree 的 interior cell 存的是完整的 key payload，而 WITHOUT ROWID 表的 key = 整列（PK + 所有欄位）。** 實測 fanout ≈ rows/leaf（33/33、27/27、16/15）正是這個機制的簽名。v3 選的參數（key 100B + value 126B）真實值是 fanout **16**、骨架 **88MB**、ρ ≈ **5.9%**。
> 2. **🔴 §3.5 天花板律升級為「兩類 schema 分割定理」**：實測對照組（key 100B + value 126B 的 **INTEGER PK** 表）fanout = **392**，與舊 DB（列寬 126B）的 392 **完全相同** → 證明 rowid table 的 interior cell **與列寬無關**（只存 child ptr + rowid varint）。**推論：ρ ≤ ~0.25% 對所有 rowid table 恆成立，無配置可逃。** 這是定理，不是量測結果。
> 3. **新增 regime 1 的全域硬上界**：SQLite 對 index B-tree 強制「單一 entry 不得超過 page 的 1/4，否則 spill 到 overflow」→ **最小 fanout = 4** → **ρ ≤ 20%，SQLite 全域,永遠**（來源見 §3.5.4）。
> 4. **✂️ 刪除 §4.5.1 的保序 key 膨脹（`inflate()`）與其單元測試**：fanout = U/(**整列寬**)，key 只是列的一部分 → **膨脹 key 完全沒有必要**。改用原生 23B YCSB key；列寬 W 由 builder 建 DB 時施加（value 大小，非 YCSB 旋鈕），正當性來自「碰不碰 key」的信封論證（§4.5.1）——value 在 YCSB 公信力信封外。少一份自訂映射、少一個 §2.3 紅線疑慮。
> 5. **⬆️ YR 從「存在性證明」升級為「ρ-sweep 迴歸」**（§4.5）：ρ 只由 W 決定、N 只決定 DB 與骨架絕對大小，**兩者正交** → **固定 leaf 頁數、掃 W**，在同一 DB 規模下取得 4 個 ρ 點（2.9% → 7.7%；選配第 5 點 R5 ≈ 11.5%）。預測從點估計變成 **benefit = α·`rho_measured`, 0 < α ≤ 1** 的迴歸（自變數用逐 trace 實測 ρ_窗口，非紙上 1/(1+f)；見 §3.5.1 覆蓋率修正）。這檢定的是律的**函數形式**，不只是效應存在。
> 6. **📄 YR 的正當性由官方文件背書**（§4.5.5）：SQLite 官方建議 WITHOUT ROWID 單列平均大小 < page 的 1/20（4KiB → ~200B）。YR 的 W ≥ 226B **踩過這條線**。YR 不是人造 strawman，是**官方明文警告的配置**。論文的適用條件因此可寫成一句話：**技術只在 schema 已違反 SQLite 自身建議、或有 cache 壓力時才有價值。**
> 7. **🐛 §10.5 新增 depth 度量校正閘**：現行 dbstat 腳本報 `sqlite_schema depth≈3`，但它只有 1 leaf / 0 interior → 真實 depth = **1**；items 報 5、真實 3 → **系統性 +2 偏移**。另一支 YR 原型腳本的偏移不同（報 6 / 算 5）。**d 直接進 §-1.4 的 (d−1)/d，必須先釘死。**
> 8. **🔧 新增 §11 執行環境實況**：`bin/ycsb`(py2) / `mvn` / `sqlite3` CLI 在本機**皆不可用**（v2 有此註記，v3 漏掉，正文會誤導照做的 agent）；`gcc` **可用**（自編 DBSTAT 那條路只是**不需要**——Python sqlite3 已含 dbstat）。cgroup `MemoryMax` **實測確認可 enforce** → YR-P 成立。FEMU-L2 要不到權限，但 v4 不需要它。
> 9. **§00 D3 重新註冊**（依 §10.3 自身規則）；D4/D6 一併定案；新增 D7（ρ-sweep 點）、D8（depth 度量）。
>
> **v3 相對 v2 的修訂（保留）**：§00 DECISIONS 制度；§3.4 回填舊 DB 實測（骨架 204KB / fanout 392）；§3.5 天花板律；§3.4 目標解耦（A 橋接 vs B 存在性）；§4.5 YR/YR-P regime arm；§8 fixed-horizon fallback；§6 進度標記；§10.3 / §10.4 驗證閘。

---

## 00. DECISIONS（decision record）—— agent 從這裡開始

> **Agent 常設規則**：
> 1. 狀態為 `CLOSED` 的決定：**直接執行，不再詢問**。
> 2. 遇到 spec 中任何未決事項或新的岔路：以本表格式 **append 一條 `status=OPEN` 的項目**（含選項與你的建議），然後**停在該任務**，繼續其他不受阻的任務。**不得在對話中口頭追問，不得代填。**
> 3. `CLOSED (pending X)`：可以開始準備工作（寫工具、寫測試），但在 X 通過之前不得跑正式實驗。

> **⚠️ 簽署規則**：本表的 `CLOSED` 只有在**研究者本人 review 並 git commit 之後**才生效。agent 起草的決定一律視為 `DRAFT`，不得據以跑正式實驗。預先承諾的效力來自簽名，不來自文字。

| # | 問題 | 選項 | 決定 | 理由 | 狀態 |
|---|---|---|---|---|---|
| D1 | §-1.1 headline field size | (i) YCSB 預設 10×100B；(ii) 對齊舊 DB 實測 | **(ii)** `fieldcount=1`，harness row payload = **126B**（對齊實測 75,600,000B / 600,000 rows） | regime 探索責任已轉移給 YR/YR-P（D3/D7），headline 不再背這個負擔；對齊是唯一不引入 confound 的選項。**預期效應 ≈ 0（§3.5 天花板 ≈ 0.27%，p=1 下界 0.25%），此 null 為 negative control，一併承諾** | **CLOSED** |
| D2 | §2.5 有 insert 的 workload（YD/YE）rowid 方案 | (a) sparse rowid；(b) 預留 rank 空間；(c) TEXT PK WITHOUT ROWID | **(b)** | (a) 的 9-byte varint 破壞與無 insert 組可比；(c) 已由 YR（D3）承擔且與 YD 的目的（moving hotspot）無關 | **CLOSED** |
| ~~D3-v3~~ | ~~YR schema：key 定長 100B 膨脹、value 126B、recordcount 5M、預期 fanout 38 / 骨架 32MB~~ | — | **❌ 作廢** | **§10.3 實測否決**：WITHOUT ROWID 的 interior 存整列，真實 fanout = 16、骨架 88MB。且「value=126B 且 fanout=38」在物理上不可同時成立（fanout = U/整列寬）。依 §10.3 自身規則重新註冊 → D3-v4 | **VOIDED (2026-07)** |
| **D3** | YR regime arm 的 schema 設計 | (1) 接受實測 fanout 16 單點；(2) 壓 W 到 ~85B 硬拿 fanout 38；(3) **ρ-sweep**：固定 leaf 頁數、掃列寬 W | **(3) ρ-sweep**。schema = `(id INTEGER PRIMARY KEY, v BLOB) WITHOUT ROWID`；查詢 = `WHERE id=?`（與 headline 同路徑）；key = dense rowid（**複用 headline 的 `keymap` 映射，§2.5**），YR **自產 4 條 trace**（N 各異，見 §4.5.3/§9，**非**複用 headline trace 檔）；列寬 W 由 Python builder 建 DB 時施加（value 大小）。固定 leaf ≈ **300,000 頁**（DB ≈ 1.2GB），4 個 W 點見 D7 | ρ 只由 W 決定、N 只決定 DB 大小 → **兩者正交**，可在同一 DB 規模下取多個 ρ 點。這把預測從點估計升級為 **benefit = α·`rho_measured` 的迴歸**（檢定律的函數形式，§4.5.4；自變數 = 實測 ρ_窗口，非紙上 ρ），成本僅增 ~40 runs。**(1) 是 (3) 的子集；(2) 已被 (3) 涵蓋且無獨立價值**。**§2.7 覆測（2026-07-16）**：4 個 W 點 f={33.1,27.0,16.0,12.0} 命中 D7、overflow=0；**INT-PK ≡ TEXT-PK 逐點相同** → 採 INTEGER-PK schema、harness 手術取消（§6.5 刪） | **CLOSED（wongzinc 2026-07-16）** |
| D4 | YR 的 `operationcount` | — | **每個 W 點 = leaf 頁數 × 2 = 600,000 ops**（L ≈ 300,000 → 2L；≈ 覆蓋 2× leaf footprint，跨 W 點恆定） | 固定 L 的設計下，ops 應綁 leaf 頁數而非 recordcount，才能讓 settling window 跨 W 點可比 | **CLOSED（wongzinc 2026-07-16）** |
| D5 | YR-P 的 `MemoryMax` 掃描點 | — | **OPEN**。建議：在 W=226 點（骨架 80MB）上掃 {∞, 256M, 96M, 32M}，對應 R = 骨架/file-cache ≈ {0, ~0.3, ~0.85, ~2.5}。R 一律以 `memory.stat` 的 file-backed 實測均值為分母回報 | 見 §4.5.6 公平性規則。**須待 §10.4 在真實 DB 尺度上覆測後定案**（目前只在 200k 原型上確認 enforce 能力） | **OPEN** |
| D6 | fixed-horizon ABC 的 K（§8） | — | **K = 該 arm 的整條 trace 長度（每個 arm 用自己的，不跨 arm 套用）**：headline **80,000 ops**；YR **600,000 ops**（= D4 全長）。**範圍僅 headline + YR；YR-P 的 K 隨 D5 一併決定（維持 OPEN）** | regime 1 下 ABC 過了 settling 即飽和 → K 取滿 = 無偏、零自由度、**無事後挑選空間**。**v4 刪去原「以 headline convergence 定錨後套用至所有 arm」句**：歧義（絕對次數？按 leaf 數換算？）且物理錯誤（headline ~2 萬 leaf、YR ~30 萬 leaf，headline 的 K 套到 YR = 還沒開始就停） | **CLOSED（wongzinc 2026-07-16）** |
| **D7** | ρ-sweep 的 W 點（新增） | — | **W ∈ {101, 126, 226, 326}**（輸入 W；~~value ≈ {78,103,203,303}B~~ 推導值·非規範，見表下 errata），對應 fanout {33, 27, 16, 12} → ρ ≳ {2.9%, 3.6%, 5.9%, 7.7%}（p=1 下界；真實天花板 = rho_measured，見 §3.5.1）。**選配第 5 點 W≈525**（ρ ≈ 11.5%）須先經 §10.3 覆測 | 前 2 點在 SQLite 官方建議的列寬內（<200B），後 2 點踩過線 → sweep 剛好跨過官方紅線，適用條件的敘述因此可對映到官方文件（§4.5.5）。低 ρ 點兼作額外 negative control 與噪音門檻估計 | **CLOSED（wongzinc 2026-07-16）** |
| **D8** | depth 度量的定義與校正（新增） | — | **採用**：depth = **`max(dbstat path 的斜線數)`，root '/'=1**（= 「root→leaf 層數，leaf 與 root 皆計入」）。三點閘實測驗證：`sqlite_schema`=1、`items`=3、`idx_items_k1`=3（✅ 全中）。canonical = `validate_trace.py`，`build_yr_prototype.py` 已統一到同式。**綁公式不綁數字**：任何 d 一律由此工具 dbstat **現量**，禁紙上外插 | d 直接進 §-1.4 的 (d−1)/d。尺已驗過 → 可簽；YR DB 未建，d 之值待量，但這**不擋簽**（綁的是公式，不是值） | **CLOSED（wongzinc 2026-07-16）** |
| **D9** | scan workload（YE）是否納入 | (i) 推導 interior→leaf readahead 的天花板；(ii) 明寫 out of scope | **OPEN**。建議 (ii) | §3.5 的律不涵蓋 scan（推論 3）。(i) 份量接近另一個研究問題 | **OPEN** |
| **D10** | YC-h 的 `hotspotdatafraction` sweep 跑哪個 `insertorder` 臂 | (i) hashed；(ii) ordered；(iii) 兩臂都掃 | **OPEN**。建議 **(ii) ordered** | §9 Tier 1b'（hdf sweep = 5 configs）沒指定 io。ordered 是空間局部性真正現形處（§3.1 hot set 物理相鄰）。**10 條 trace 已全產備用（產 trace 免費），但 sweep 跑哪臂待簽——(iii) 會多花 ~90 runs（跑 run 才貴），不得讓它默認展開** | **OPEN** |
| **D11** | headline DB 要不要建 `idx_items_k1` / `idx_items_k2` 索引 | (i) 建（對齊舊 DB 的檔案）；(ii) 不建（items-only） | **(ii) 不建**。理由（強→弱）：① D1 已簽 **`fieldcount=1`**（一個欄位）→ 建索引須加 k1/k2 欄位 = **改簽過的東西**；② ρ 是 **items-only** 的量（EXPLAIN 證明 `WHERE id=?` 只走 PK，索引一頁不碰）；③ **k1/k2 的值不在 YCSB trace 裡**（憑空捏 = §2.3 紅線邊）。items 幾何對齊完美（19,983 / depth 3 / 204KB / 75,600,000 record 全中）；§-1.1 閘 page_count = **20,035**（items 20,034 + schema 1，無索引）| **殘留**：檔案佈局與舊 DB 不同（骨架 51 頁在舊 DB 散在 26,006 頁裡）→ 可能影響 **α**（骨架實體連續性），**不影響 ρ**（頁數比）。以 `skeleton_contiguity` 定量回報（§7）；「加索引」修不了它（除非重播建構順序）| **CLOSED（wongzinc 2026-07-16）** |

> **D7 errata（2026-07-16，簽後澄清；非 VOID）**：D7 括號內「value ≈ {78,103,203,303}B」為**推導值、非規範**，予以劃除。**綁定內容 = `W ∈ {101,126,226,326}`（輸入，不變）。** builder 一律以 W 為輸入、value 由 builder 計算，**不得從本表轉抄**。同理 f / ρ / N / skeleton 各欄為**說明性**，規範來源：f → §10.3 gate；ρ → §5.2 `rho_measured`。**劃除一個從來不規範的推導值 = 澄清，不改變任何承諾，故不觸發 VOID**（相對地，「改成正確數字」隱含它本來規範 → 反而製造治理麻煩）。這永久解決 H1–H5 那類 update anomaly：source（W/schema）一動，冗餘副本不再需要人工同步。

> **Schema errata（2026-07-16，簽後澄清；非 VOID）**：D1「`fieldcount=1`」是 **YCSB log-size 旋鈕**（§2.2：verbose 會 toString 整個 value，10×100B 讓 load log 爆到 ~1GB；trace value-agnostic、列寬由 harness/build 施加），**不是 DB schema 宣告**。實際 DB schema（headline 與 YR 共用）= **`items(id INTEGER PRIMARY KEY, k1 TEXT, k2 TEXT, payload BLOB)`**（headline = rowid table；YR 加 `WITHOUT ROWID`、payload 調到整列=W）。理由：① harness init 時 prepare 一條引用 k1/k2 的語句，DB 必須有這兩欄（**builder↔harness 合約**，`tests/test_db_smoke.py`）；② 這正是舊 DB 126B record 的結構（k1+k2+payload+header），**builder = testdb_builder − 兩個 CREATE INDEX**（零新算術）。**規範內容是幾何/機制（126B record、INT-PK、WITHOUT ROWID、`WHERE id=?`、W 是掃描變數），不是字面欄位清單** → 澄清、非改決定，**不 VOID**。**§2.7 覆測（4 欄重跑，2026-07-16）**：多 2 欄 → header +~2B → f = {33.2, 27.2, 16.0, 12.0} ≈ 簽名 {33,27,16,12}（全 ±10% 內、overflow=0）→ **D3/D7 幾何 hold**，Round 4 的 1.2GB DB 不會撞牆。

## -1. 預先承諾（Pre-registration）—— 先讀這一節

**這一節必須在跑任何實驗之前 commit，並以 git 時間戳為證。**

v1 spec 隱含一個假設：換成 YCSB 之後，結論會保留下來。§3.1 甚至已經先寫好了勝利宣言的句型（"the benefit rises from X% to Y%"）。**v3/v4 更新：這個假設已被實測 + §3.5 天花板律直接否定**——對齊舊 DB 的配置下，骨架實測僅 204KB、fanout ≈ 392，而 §3.5.3 進一步證明 **rowid table 的 fanout 與列寬無關**，故 ρ ≤ ~0.25% 對這一整類 schema 恆成立。**headline 的 null 不再是風險，也不只是「這個配置的」理論預測，而是一個 schema 類別的定理。**

如果不預先承諾，當 headline 顯示效益 ≈ 0 時，會有強烈誘因去「再找一個設定」——**那正是這次遷移要根除的失效模式，只是換了位置重生**。換 generator 堵不住它，換規則才行。v3 的做法是反過來：**把「找一個效應存在的設定」本身變成一個預先註冊、有物理理由的 arm（YR / YR-P，§4.5），而不是事後的 fishing。**

### -1.1 承諾事項

| 項目 | 承諾內容 |
|---|---|
| **Headline 配置** | `YC-hashed`（workloadc + `requestdistribution=zipfian` + `insertorder=hashed`），schema 對齊舊 DB：dense rowid、`fieldcount=1`、row payload = **126B**（D1）。預期 leaf ≈ 20k ± 5%、depth = 3、骨架 ≈ 205KB ± 10%（以 §3.4 實測為錨） |
| **Headline 預測（新增）** | **效應 ≈ 0**（天花板 ≈ 0.27%，p=1 下界 0.25%，§3.5.1/3.5.3）。Wilcoxon 預期不顯著。此 arm 的角色 = **negative control**：若量出顯著大效應，優先懷疑 measurement pipeline，而非慶祝 |
| **Regime arm 配置** | `YR`（ρ-sweep，4 個 W 點）/ `YR-P`（cache pressure）依 §4.5 與 D3/D4/D5/D7。預測見 §-1.4 |
| **不得事後更換** | headline / YR 配置一旦 commit，不因結果好壞更換。若有正當理由更換，必須在論文中揭露原配置的結果。**例外且唯一的例外**：§10 的驗證閘依其自身預先寫好的規則否決某個配置（如 D3-v3 之於 §10.3）——此時更換是**規則的執行**，不是 fishing，但必須在 §00 留下 `VOIDED` 記錄與否決理由 |
| **主要指標** | area-between-curves（ABC），settling point 依既有 convergence-based 定義；**fallback = fixed-horizon ABC（K 依 D6，先 commit）** |
| **統計檢定** | paired Wilcoxon signed-rank，n = trace 數（見 §8）。α = 0.05，雙尾 |
| **樣本數** | 見 §9 分層表。**不得看到結果後追加 trace 直到顯著** |

### -1.2 從「負面結果預備敘述」升級為「天花板律 + schema 分割定理」（v4）

v2 在這裡放的是一段定性的降級敘述。v3 用 §3.5 的帳把它升級成定量主張。**v4 再升一級**：實測證明 rowid table 的 fanout 與列寬無關，於是這不再是「我們這個配置」的天花板，而是**一整類 schema 的定理**。論文敘述改為：

> *"For cold-start point queries with ample cache, the benefit of interior-node prefetching is structurally bounded by the interior-to-total fault ratio ρ ≈ 1/(1+f), where f is the interior fanout. SQLite's two storage classes give this bound sharply different values. In **rowid tables** — the default, and the class our production configuration belongs to — interior cells hold only a child pointer and a rowid varint, so f ≈ 400 **independently of row width**: we measure f = 392 for both a 126 B and a 226 B row. The ceiling is therefore ρ ≤ 0.25% for the entire class, and **no schema tuning escapes it**. In **WITHOUT ROWID (clustered-index) tables**, interior cells hold the full row, so f ≈ U/W is a function of row width W, and the ceiling becomes tunable — up to a hard structural limit of f = 4 (SQLite spills any index entry exceeding a quarter page to overflow), i.e. ρ ≤ 20% for SQLite at large. We verify the law's functional form by sweeping W across four operating points (nominal ρ = 2.9%–7.7%, the p=1 lower bounds) and regressing measured benefit on the per-trace measured in-window ratio ρ_measured — the nominal figures understate the true ceiling by 1.2–1.5× under sub-unit leaf coverage. Notably, ρ exceeds ~3% only once W passes ~200 B — precisely the row width beyond which SQLite's own documentation advises against WITHOUT ROWID. **The technique thus pays only where the schema already departs from SQLite's design guidance, or where the skeleton exceeds available file cache (YR-P).** We report the ceiling law and its applicability boundary rather than a single headline speedup."*

**這比一個泡沫數字、也比一段道歉式的 applicability condition 都更有價值**：它交付的是一條**有封閉形式、有硬上界、有外部文件錨點**的律，加上一條迴歸驗證。null 的角色從危機 → negative control → **定理的證明**。

### -1.3 形容詞禁令（自 v1 §5 提升為全域規則）

> **任何 workload 的宣稱（"churn-resilient"、"hot-tail"、"skewed"、"robust"）都必須對映到 Tier 0 validator 裡的一個數字。沒有對應數字的形容詞，不准出現在論文裡。**
>
> **（v4 補：閘的 fire-test 規則）每一個閘（validator 檢查、預先註冊的通過條件、任何「不符即作廢」的判準）都必須附一個證明它會在該失敗時**開火**的測試。沒有 fire test 的閘，視同不存在，不得在論文中宣稱它保護了什麼。** 代價已被 churn 證明：`hotset_jaccard` 這個**專為抓 churn 而設**的閘，因為從沒接進 verdict、也沒 fire test，反而給 churn 開了綠燈——而當時以為有保護。寫一個閘 ≠ 接上並驗過一個閘。
>
> **fire test 必須含 pass path，不只 fail path**：一個「什麼都拒絕」的閘,三條失敗路徑全綠——`hotspot_movement` 的 contiguity/concentration 用全局量就會誤殺**移動熱點**(正好是 YD,唯一真 churn arm),而三條 fail 路徑照不出來。pass path 靠一個**已知該通過**的 fixture 才驗得到。
>
> **測試 fixture ≠ 實驗 trace，不觸 §2.3 紅線**：fire test 用**已知正確答案**的合成 / 凍存 fixture 驗閘;§2.3 禁的是為**實驗**捏造 trace,不是為驗**工具**。反過來,拿真實驗資料(如 YD)測不了閘——你不知道它該給什麼答案,那正是閘要告訴你的。實作見 `tests/test_validator_gates.py`（合成 moving/static/uniform + 真實坟墓 C/churn/YC-h）與 `tests/test_keymap.py`。

補充兩條：

- **"robust" 的用法收窄**：跑 N 條 trace 只能支持「對 workload 內變異穩健」。它**不能**支持「對參數選擇穩健」。這兩件事在 reviewer 眼裡是分開的，論文中不得混用。
- **skew 一律引實測值**，不得引用 `zipfianconstant`（原因見 §3.2）。

### -1.4 各 arm 的預先註冊預測（v4 重寫，跑前 commit）

> ✅ **D8 已關（2026-07-16）→ YR-P 列解封**：depth = `max(dbstat path 斜線數)`，三點閘驗證通過（§10.5）。YR-P 列的 (d−1)/d **綁公式**：d = 建 YR DB 後 dbstat **實測**（度量這把尺已可信；d 之值待量，不擋簽——現在簽是盲的，YR 一個數據都還沒有）。

| arm | fanout | ρ 估計值（p=1 下界，§3.5） | 預測 | 若預測落空的解讀（現在寫好） |
|---|---|---|---|---|
| YC-hashed（headline） | 392（實測） | **≈ 0.27%**（p≈0.95；p=1 下界 0.25%） | 效應與 0 不可區分 | 量出顯著大效應 → **懷疑 pipeline**（drop_caches 不完全、兩臂 DB 不一致），驗 §5 的 page_count/fill/depth 三數字。**注意：這是 schema 類別的定理（§3.5.3），不是可調參數的結果——大效應在此近乎不可能為真** |
| YR@W=101 | 33（實測） | ~2.9%（p=1 下界） | 效應很可能低於偵測門檻 | 預期落在噪音內 → 兼作 negative control 與**噪音門檻估計** |
| YR@W=126 | 27（實測） | ~3.6%（p=1 下界） | 同上，臨界 | — |
| YR@W=226 | 16（實測） | ~5.9%（p=1 下界） | 效應 > 0 且顯著（若噪音 < ~1%） | 不顯著 → 報告「與天花板一致，效應量低於偵測極限」，**不追加 trace** |
| YR@W=326 | 12（實測） | ~7.7%（p=1 下界） | 效應 > 0 且顯著，且 > W=226 點 | — |
| **YR 整體（主要預測）** | — | — | **benefit = α·`rho_measured`，α ∈ (0, 1]，斜率顯著 > 0**（過原點迴歸，報 α 與 R²）。**自變數 = 各 trace 的 `rho_measured`（§5.2 實測 ρ_窗口），不是上欄印的 p=1 下界**——承諾綁在實測量、不依賴覆蓋率算術。**這是對「律」的檢定，不是對「效應存在」的檢定** | α 不穩定 / 非線性 → 函數形式需修正；報告原始 4 點與殘差，**不得只挑符合的點**。（α 略 > 1 出現 → 先查覆蓋率/量測，**非** auto pipeline-bug，見 §3.5.1） |
| YR-P@W=226 | 16 | 隨 R = 骨架/file-cache 上升；R ≥ 1 後脫離 regime 1，**per-query 上限 = (d−1)/d，d = 建 DB 後 dbstat 實測 depth**（度量已由 D8 三點閘驗證，§10.5） | **方向承諾**：效益隨 R 單調上升，R ≳ 2 時達雙位數。幅度為 exploratory，不做點預測 | 非單調 → 報告原始曲線並分析（如 WILLNEED 預讀頁被提前逐出，§4.5.6-iii，這本身是 finding） |

> 📌 **上表的 ρ 是 p=1 下界估計，不是天花板、也不是告警門檻。** 真實天花板 = §5.2 逐 trace 實測的 `rho_measured`（= §3.5.1 的 ρ_窗口，已含覆蓋率 p），它同時是**主要迴歸（§4.5.4）的自變數**與告警線：效益量出 **> 該 trace 的 rho_measured** 才是 pipeline bug 的訊號。zipfian 短窗下 ρ_窗口 可比印出的下界高 **1.2–1.5×**（§3.5.1）——拿效益去比印在紙上的 ρ 會誤報，且會讓 α 虛高 > 1。

---

## 0. 目標

把 headline 結論的 workload 來源從「自造 generator」換成「公認 workload 的 trace」，讓下列失效模式在**結構上**不可能發生。

| 已發生的坑 | 來源 | YCSB 是否解掉 | v2/v3 修正 |
|---|---|---|---|
| C 的 −75% 來自 out-of-range not-found 撞最右葉 | 自造 key range `[590000, 609999]` 超過 DB 上限 | ✅ 解掉，但**理由與 v1 所寫不同** | 不是靠 `recordcount` 界定。`keychooser` 的上界其實是 `insertstart + insertcount + expectednewkeys`（**刻意超出**現有 keyspace）。真正擋住 not-found 的是 `nextKeynum()` 的 **rejection loop**（`do{...}while(keynum > lastValue())`）。代價：實際分佈是「Zipf 條件於 keynum ≤ lastValue」，非純 Zipf → **只准引實測分佈**。**實測 notfound = 0.5000（10 seeds 全同）** —— 半數查詢結構上撞最右葉 = −75% 之源（rightmost_leaf_share 精確值待建 DB，§5.5b） |
| churn「韌性」宣稱，實際 hot page 位移 = 0 | 自造 churn 用抽樣不放回 → 根本沒有 hot set | ✅ **已解（v4 validator 修復）** | 舊 `hotset_jaccard_series`（「Jaccard<1」）會**誤放行**：Jaccard≈0 分不出「飛得快」與「沒熱點」。改為**前置條件保護的 `hotspot_movement`**（先驗 hotset_present，無則移動宣稱 FAIL）。churn 現以 `--claims-moving-hotspot` 實測 **FAIL（10 seeds 全同，unique_key_ratio=1.0、hotset_present=False）**。**方法論貢獻：我們自己的 validator 有一個檢查在無熱點時誤放行，已用前置條件補上——這寫進論文** |
| tail 範圍是 knife-edge，參數在驅動結論 | 自造參數沒有外部錨點 | ⚠️ **v1 高估了** | YCSB 的公信力只覆蓋 **key 分佈**。`fieldlength` / `zeropadding` / schema / load order 仍然全部是你選的，而且**每一個都影響 page layout**。真正的解藥是 §-1 預先承諾，不是換 generator |
| — | — | ❌ **新坑（v1 已標，但機制寫錯）** | `insertorder` 對 `zipfian` **無效**，只對 `hotspot` / `latest` 有效。見 §3.1 |
| — | — | ❌ **新坑（v1 未發現）** | `insertorder` 同時決定 load 階段的物理佈局（fill factor 100% vs 69%），是兩臂間的隱藏 confound。見 §3.3 |
| — | — | ❌ **新坑（v1 未發現）** | 「用 TEXT PRIMARY KEY」會把單棵 rowid B-tree 換成「rowid table + index B-tree」= 每次查詢穿兩棵樹 → 與舊 A/B/C 完全不可比。見 §2.5 |
| **headline 效應在對齊配置下物理上趨近 0** | **舊 DB 自身處於 null regime（骨架 204KB、fanout 392）** | ❌ **v3 新坑（v2 §3.4 有預感，實測證實且加重 8 倍）** | **不能靠「換設定」解，靠 §3.5 天花板律 + §4.5 YR/YR-P 把 regime 本身變成自變數。§-1.4 預先承諾各 arm 預測** |
| — | — | ❌ **v4 新坑（v3 §4.5 自己踩的）** | **紙上外插的 fanout 幾何是錯的**：WITHOUT ROWID 的 interior 存整列，不是只存 key。**這個坑是被 spec 自己的 §10.3 驗證閘擋下的，不是被 reviewer 擋下的**——這正是驗證閘存在的理由，也是「先驗證再花錢」（§6 排序）的實證。v4 把所有 fanout 數字換成實測，並把「紙上外插不得進入 §-1.4」立為規則（§10 前言） |

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

> 🔧 **本機不可跑 `mvn` / `bin/ycsb`（無 maven、`bin/ycsb` 走 py2；見 §11）。** 實際建置與產 trace 走 `gen_ycsb_trace.sh`（`java -cp` + BasicDB verbose）。本節指令為 canonical 形式。

> ⚠️ **在寫任何 parser 之前，先跑 §10 的驗證清單。** 本 spec 對 YCSB 內部行為的所有斷言都必須自己確認過。花十分鐘，省掉一輪實驗。

### 2.2 產生 trace

> 🔧 **canonical 形式；本機用 `gen_ycsb_trace.sh` 實跑（`bin/ycsb` 不可用，見 §11）。** headline 與 YR 走同一支腳本，差別只在 recordcount，以及 YR 的列寬 W 於下游建 DB 時施加（非 YCSB 旋鈕）。

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

# ── YR arm（regime arm，ρ-sweep，參數依 §00 D3/D7）──
# ρ-sweep = 固定 leaf ≈300k 頁、掃列寬 W → 每個 W 點 recordcount(N) 不同 → 4 條 load+run trace。
# 注意：YCSB 這步只產生 key 存取序列，fieldlength 固定=1（trace 不帶 payload）。
#       列寬 W ∈ {101,126,226,326}B 於 harness 建 DB 時施加，非此處旋鈕。見 D3/D7、§4.5.3。
# 🔴 唯一真相來源 = yr_sweep.yaml（W / leaf_pages / ops_per_point）。
#    N 一律由 tools/calc_n.py 由 W 現算，**不得在此或任何地方寫死字面 N**
#    （抄了會建出 leaf≠300k 的 DB，且 Tier 0 全過 = 靜默錯）。
YAML=workloads_refined/yr_sweep.yaml
OPS=$(sed -n 's/^ops_per_point:[[:space:]]*\([0-9]*\).*/\1/p' "$YAML")
python3 workloads_refined/tools/calc_n.py --all | while read -r W N; do   # 每行 = "W<TAB>N"
  bin/ycsb load basic -P workloads/workloadc -threads 1 \
    -p recordcount=$N -p insertorder=hashed -p zeropadding=19 \
    -p fieldcount=1 -p fieldlength=1 \
    -p basicdb.verbose=true -p basicdb.simulatedelay=0 \
    > raw/load_hashed_YR_W${W}.log

  bin/ycsb run basic -P workloads/workloadc -threads 1 \
    -p recordcount=$N -p operationcount=$OPS \
    -p requestdistribution=zipfian -p insertorder=hashed -p zeropadding=19 \
    -p fieldcount=1 -p fieldlength=1 \
    -p basicdb.verbose=true -p basicdb.simulatedelay=0 \
    > raw/YR_hashed_run_W${W}.log
done
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
| `key TEXT PRIMARY KEY) WITHOUT ROWID` | 1 棵 index-organized B-tree | 1，但 **interior cell 存整列** → fanout = U/整列寬（§3.5.2）、列 > ~1002B 即 overflow | ⚠️ 對目標 A 勉強；**對目標 B（§3.4）是唯一可行解 → 由 YR 採用，見 §4.5** |

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
| `recordcount` | headline：600000（對齊舊 DB row 數）；**YR：leaf 固定 ≈300k 頁；N 由 `yr_sweep.yaml` + `tools/calc_n.py` 由 W 現算（不列數字，見 §4.5.3）** | 對齊的真正對象是 **page count / B-tree 層數 / fanout**，見 §3.4 |
| `zeropadding` | **19**（兩臂統一，不再是「8 或 19」） | 見 §3.2 |
| `fieldcount` / `fieldlength` | **不抄預設**：headline row payload = **126B**（D1，對齊實測）；**YR：`fieldlength` 固定 = 1（trace 只帶 key）；列寬 W ∈ {101,126,226,326}B 由 harness 建 DB 時掃（D3/D7），非 YCSB 旋鈕** | 決定 leaf 塞幾筆 → 直接決定 leaf/interior 比例與 B-tree 層數 |
| `operationcount` | headline：80000（對齊現有）；YR：600,000（D4：= 2×L，L=300k leaf；**CLOSED 2026-07-16**） | — |
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
| B（存在性）| **YR ρ-sweep / YR-P（§4.5）** | 天花板律的**函數形式檢定**（4 點迴歸）+ regime 2 |

#### 反推工作單（v3：已填）

| 量 | 舊 DB 實測 | headline 目標 | 達成手段 |
|---|---|---|---|
| items leaf 頁數 | 19,983 | 20k ± 5% | `fieldcount=1`，row payload 126B |
| B-tree depth | 3 | 3 | 同上 |
| interior skeleton | 204KB | 205KB ± 10% | 同上 |
| leaf fill | 96.8% | 一致 | `load_order=sorted`（§3.3） |
| **決定** | — | — | **D1（CLOSED）** |

### 3.5 天花板律與 schema 分割定理 —— 這一節決定整個實驗的形狀，也是論文的主結論

#### 3.5.1 命題

冷啟動、cache 充足（骨架與熱 leaf 集合皆放得進 OS page cache + SQLite pager cache）時，interior prefetch 對 ABC 的收益上限為

> **ρ ≈ I / (I + L) ≈ 1 / (1 + f)**

其中 I = settling window 內 fault-in 的 distinct interior 頁數、L = distinct leaf 頁數、f = interior fanout。

**推導（三行）**：cache 充足時每個 distinct page 恰好 fault 一次；prefetch 骨架能做的極致，是把 descent 上那 I 次**序列相依**的 random read（B-tree descent 是 pointer-chasing：讀完 interior 才知下一頁讀哪）**一批 async 並行發出**，把序列的 (I+L) 跳壓成「I 個並行 interior + leaf 一跳」。理想上那 I 跳的延遲全被藏掉，故收益佔比 ≤ I/(I+L)。**⚠️ 機制是去序列化 / 平行度,不是局部性**——省的是**佇列深度（序列延遲）,不是磁碟臂移動；不需要骨架實體連續**（實測 `skeleton_contiguity` 最大連續段 = 2/51，根本沒有 sequential read 可言,但去序列化照樣成立）。而每 fault 一個新 interior 平均服務 ~f 個新 leaf，故（滿覆蓋時）I/L ≈ 1/f，**與 DB 大小、記錄數無關**——這是結構性的。

> **🔴 覆蓋率修正（v4，跑前補；agent 的 concern #2 指到的正是這個洞，只是深度被低估了）**：上式 I/L ≈ 1/f 偷偷假設**每個 leaf 都被碰到**（覆蓋率 p = 1）。zipfian 的全部意義就是只碰一部分——而「牌子」和「書架」縮水程度不同：**leaf 只有被碰到的才 fault（L_w = p·L）；一塊 interior 管 ~f 個 leaf，碰到其中任一個就得爬它 → interior 幾乎全被碰到（I_w ≈ I）**。故窗口內真實比例：
>
> **ρ_窗口 = I / (I + p·L)，p ∈ (0, 1]**　→　分母隨 p 縮水 → **ρ_窗口 ≥ 1/(1+f)**
>
> 所以 **1/(1+f) 是 p=1 的下界，不是天花板**。真實天花板由 §5.2 的 `rho_measured` 逐 trace 量出（它量的正是 ρ_窗口，一直都對）。
> - **headline**：p ≈ 0.95（80k 查詢、每 leaf ~30 列、key 打散 → 幾乎每個 leaf 都被碰到）→ 0.25% → **0.27%**。**分割定理毫髮無傷**——這也是為什麼此洞在 f=392 幾乎不存在，直到 YR（f=12–33）才顯著。
> - **YR**：p ≈ 0.76–0.79 → 真實天花板 ≈ 印出值的 **1.2–1.5 倍**。**故 §-1.4 / §4.5.4 的迴歸一律對 `rho_measured` 跑，不對印在紙上的 ρ 跑**——否則實測 benefit 對著偏小的紙上 ρ 迴歸會使 **α 虛高 > 1**，依 §00 規則觸發一次**假的「推翻」警報**。改對 rho_measured 跑後，承諾綁的是實測量、不是這裡的算術（順帶：D4 的 opcount 選多少只影響 sweep 跨度，不再透過 p 影響效度）。

#### 3.5.2 f 由什麼決定：兩種 B-tree，兩種答案（v4 實測釘死）

SQLite 有兩種儲存類別，interior cell 的內容完全不同：

| | interior cell 內容 | f 的函數形式 | 實測 |
|---|---|---|---|
| **rowid table**（`INTEGER PRIMARY KEY`，SQLite 預設） | child pointer(4B) + **rowid varint**（~2–5B） ≈ 7–9B | **f ≈ U/9 ≈ 400–500，與列寬無關** | 舊 DB（列寬 126B）：**392**<br>對照組（列寬 226B）：**392** ← 列寬近乎翻倍，f 不動 |
| **WITHOUT ROWID**（clustered index） | child pointer(4B) + **完整 key payload = 整列**（PK + 所有欄位） | **f ≈ U/(W+overhead)，W = 整列寬** | W=101→33、W=126→27、W=226→16、W=326→12 |

**實測簽名**：WITHOUT ROWID 表的 `f ≈ rows/leaf`（33/33、27/27、16/15）。interior cell 與 leaf cell 存的是同一個東西，只差一個 4B child pointer——這就是機制的指紋。

> **v3 在此犯的錯**：算「interior cell ≈ 4 + varint + key(100B) ≈ 106B → f ≈ 38」，漏了 value。真實 cell ≈ 4 + varint + **整列(226B)** → f = 16。**推論**：在 WITHOUT ROWID 表裡，f 與 leaf payload 是**同一個 cell**，無法獨立設定。v3「用寬 key 壓低 f、同時 value 保持 126B 對齊 headline」的前提在物理上不成立。

#### 3.5.3 🔴 分割定理（論文主結論）

由 3.5.1 + 3.5.2 直接得到：

> **對所有 rowid table（4KB page），ρ ≈ 1/400 ≈ 0.25%（p=1 下界；實際覆蓋率下 headline ≈ 0.27%，見 §3.5.1 覆蓋率修正）——量級與列寬、記錄數、workload 皆無關（skew 僅透過覆蓋率 p 微幅進入，仍遠 < 1%），無任何 schema 配置逃得出 sub-percent。**

這不是「我們量到 0」，是「這一整類 schema 在物理上不可能超過 0.25%」。而 rowid table 是 SQLite 的**預設**，也是舊 DB 與 headline 所屬的類別。

> **對 WITHOUT ROWID table，ρ ≈ (W+c)/(U+W+c) 可調**——W 是設計者選的，故天花板可設計。

**這條分割線就是論文的 contribution**：interior prefetching 在 SQLite 的適用範圍不是一個經驗觀察，是一個可從 page format 推導、且已實測驗證的**類別判準**。

#### 3.5.4 regime 1 的硬上界：overflow 地板 f = 4

W 不能無限放大。SQLite 對 index B-tree（含 WITHOUT ROWID）強制：**單一 entry 不得佔用超過 page 的 1/4，超過即 spill 到 overflow page，因此最小 fanout = 4**（官方說明見 §4.5.5）。對應的門檻（`U` = usable size）：

```
maxLocal = ((U-12)*64/255)-23   ≈ 1002B  （4096 page，超過此值開始 spill）
minLocal = ((U-12)*32/255)-23   ≈  489B  （spill 後 local 部分的下限）
```

三個後果：

1. **regime 1 的全域天花板：ρ ≤ 1/(1+4) = 20%**，SQLite 上，永遠。想要更高只能進 regime 2（cache pressure）。
2. **f 對 W 非單調**：W 逼近 1002B 時 f → ~4；越過門檻後 cell 寬度被 clamp 回 [489, 1002]，f **跳回 ~4–8**。所以「W 越大 ρ 越高」只在 W < ~1000B 成立。
3. **overflow 會反噬 ρ**：spill 後每列多出 overflow page 讀取 → 灌大分母 L → ρ 下降。**故 D7 的 sweep 一律限制在 W ≤ ~525B，且 validator 必須檢查 `overflow_pages == 0`。**

#### 3.5.5 四個推論

1. **「把 DB 弄大」這條路是死的**：ρ ≈ 1/f 與 DB 大小無關。把對齊配置放大 1000 倍，天花板還是 0.25%。v2 §-1.2 / §6 的「放大 DB 逃離 null regime」直覺只對了一半——真正的槓桿是 **(i) f**（→ YR）與 **(ii) cache pressure**（→ YR-P），兩者都與 recordcount 正交。
2. **ρ 與 N 正交 → sweep 設計成立**：ρ 只由 W 決定，N 只決定 DB 與骨架的絕對大小。因此可以**固定 leaf 頁數（= 固定 DB 規模與總 fault 量）、只掃 W**，取得多個 ρ 點。這是 §4.5 ρ-sweep 的物理基礎。
3. **regime 2 需要兩層 cache 同時受限**：骨架必須同時超過 OS file cache 配額（cgroup `MemoryMax`）**與** SQLite pager cache（`PRAGMA cache_size`）。204KB 的骨架掐不出壓力（會先把整個 process 掐死）；80MB 的可以。**這就是 YR-P 必須疊在 YR 上、而不能疊在 headline 上的原因。**
4. **scan/range workload（YE）走不同機制**：interior 的內容可用來對 leaf 做 readahead，收益不受 1/f 界。→ D9（OPEN）。

### 3.6 舊 §3.4 解析試算表（v2 遺留，僅存檔供對照，數字已被實測取代）

以 `page_size=4096`、`recordcount=600000`、row ≈ 1KB（**此假設已證偽：實測 126B**）、usable ≈ 4061：

| 量 | INTEGER PK（dense rowid） | TEXT PK WITHOUT ROWID（19 字元 key） |
|---|---|---|
| leaf 每頁筆數 | ~3 | ~3 |
| leaf 總數 | ~200,000 | ~200,000 |
| interior cell 大小 | 4 + 3 varint ≈ **7B** | 4 + ~24 ≈ **28B** ← **v2 也犯了 v3 的同一個錯**：漏了 value，真實應為 4 + varint + 整列 |
| interior fanout | **~500** | **~145**（錯，應為 ~4061/1046 ≈ 4，且已觸發 overflow） |
| B-tree 層數 | 3 層 | 4 層 |
| interior skeleton 總量 | ~1.6 MB | ~5.7 MB |
| DB 大小 | ~800 MB | ~800 MB |

> **教訓已立為規則**（§10 前言）：「interior cell 只有 key」這個直覺在 v2 與 v3 各害了一次。**任何 fanout 數字進入 §-1.4 之前，必須有 dbstat 實測背書。**

---

## 4. Workload matrix（v4：分層 + regime sweep）

`insertorder` 只在 `hotspot` / `latest` 上是自變數（§3.1），因此 v1 的 16 條縮減如下。

| ID | YCSB base | schema / regime | `insertorder` 臂 | 覆蓋什麼 | 取代誰 |
|---|---|---|---|---|---|
| **YC** | workloadc (100% read, zipfian) | headline（rowid，對齊，D1） | **hashed only** | **HEADLINE + negative control**：純讀熱點，無 key-to-page locality 假設 | 舊 C（含 −75% artifact） |
| YC-u | workloadc + `requestdistribution=uniform` | headline | hashed only | **no-locality 地板**（✅ 已產、Tier 0 PASS） | 新增，必要 |
| **YC-h** | workloadc + `requestdistribution=hotspot` | headline | **hashed × ordered** | 固定熱點。**空間局部性軸之一** | 舊 C 的 tail 區間 |
| **YD** | workloadd (read-latest + 5% insert) | headline + rowid 方案 (b)（D2） | **hashed × ordered** | 移動熱點 = 真正的 churn。**空間局部性軸之二** | 舊 churn（hot set 位移 = 0 的那個） |
| YA | workloada (50/50 R/U, zipfian) | headline | hashed only | 寫入混合 | 舊 A |
| YB | workloadb (95/5, zipfian) | headline | hashed only | 讀為主 | 舊 B |
| YE | workloade (short scan + insert, zipfian) | headline + rowid 方案 (b) | hashed only | range 存取（§3.5.5 推論 4；**scope 待 D9**） | 舊 scan |
| YF | workloadf (RMW, zipfian) | headline | hashed only | RMW | 舊 rmw |
| **YR** | workloadc | **regime arm：WITHOUT ROWID，ρ-sweep 4 點（§4.5，D3/D7）** | hashed only | **天花板律的函數形式檢定**（f = 33/27/16/12 → ρ = 2.9–7.7%） | v3 新增，v4 重算 |
| **YR-P** | workloadc（與 YR@W=226 同 trace 同 DB） | YR × cgroup `MemoryMax` sweep（D5） | hashed only | **regime 2：骨架 re-fault** | v3 新增 |

**`YC-h` 額外要求**：`hotspotdatafraction` 掃一整條線（如 0.01 / 0.05 / 0.1 / 0.2 / 0.5），**不能只報一個點**——否則就是舊「tail 區間 knife-edge」的重演。

### 4.5 YR / YR-P regime arm 規格（v4 重寫）

#### 4.5.1 YR schema：`WITHOUT ROWID` + INTEGER dense rowid，**列寬 W 為自變數**

```sql
CREATE TABLE items_yr (
  id  INTEGER PRIMARY KEY,  -- dense rowid，複用 headline 的 keymap 映射（§2.5）；查詢 = WHERE id=?，與 headline 同路徑
  v   BLOB                  -- 由 D7 的 W 決定：value ≈ W − id 寬（Python builder 建 DB 時施加）
) WITHOUT ROWID;
-- §2.7 實測：INT-PK 與 TEXT-PK 幾何逐點相同（f={33,27,16,12}）→ 免 harness 手術、消 int-vs-text confound
```

**✂️ v3 的 `inflate()` 保序 key 膨脹與其兩個單元測試整組刪除。**
真正的分界線**不是**「原生旋鈕 vs 自訂 `inflate()`」——是**碰不碰 key**：

- **key 在 YCSB 的公信力信封內**（附錄 B：YCSB 只覆蓋 **key 分佈**）。動 key → 必須付「保序證明 + §2.3 紅線論證」的代價。`inflate()` 正是在動 key，所以才背這個負擔。
- **value 的大小從來不在信封內**。動 value → **免費，而且誰施加的都無所謂**：不論是 YCSB `fieldlength` 還是 harness 建 DB 時灌寬列（§2.2：trace value-agnostic），對 YCSB 公信力的減損都是 **零**。

既然 f ≈ U/(**整列寬**)（§3.5.2），膨脹 key 與加大 value 對 f **完全等價**，就該選在信封外、免付證明的那條路：**完全不碰 key（複用 headline 的 dense rowid 映射，§2.5），只掃 value 寬度 W（Python builder 建 DB 時施加）**。這也正是「W 由 harness 施加不減損正當性」的原因——value 本來就在信封外。刪 `inflate()` 因此**更**站得住：key 在信封內、動它要付證明；value 在信封外、動它免費。

> 附帶更正一個誤判：「要 f ≈ 38 就得把 value 壓到 ~1B」是把 key 錯誤地固定在 100B 才會得到的結論。任何窄列 W ≈ 85B 都能得到 f ≈ 38（與 key 型別無關，f = U/整列寬）。但 D3 選 sweep，此點已被涵蓋，不另設。

**保留的紅線**：run-phase 的 op 序列與 key 分佈一個 bit 都不動；改變的只有 value 大小（trace 本來就是 value-agnostic，§2.2）與 schema 宣告。**YR 自產 4 條 trace**（每點 N 由 `yr_sweep.yaml` + `calc_n.py` 現算，見 §4.5.3/§9），複用的是 §2.5 的 dense-rowid **映射邏輯（`keymap.py`），而非 headline 的 600k trace 檔**——直接拿 headline 600k trace 跑 YR 的大 DB 只會碰到前 60 萬列、工作集全錯，且會**靜默通過** Tier 0 的 `key_range_subset`（最危險的錯）。manifest 必須明記 **W 與 f 是本 arm 的實驗控制變數**。

#### 4.5.2 實測幾何（§10.3，key=100B + value 掃描；W = 100 + value）

| value | **W（整列寬）** | **f（實測）** | rows/leaf | 骨架（20 萬列） |
|---|---|---|---|---|
| 1B | 101 | **33.1** | 33 | 740KB |
| 26B | 126 | **27.0** | 27 | 1.1MB |
| 126B | 226 | **16.0** | 15 | 3.3MB |
| 226B | 326 | **12.0** | 11 | 6.1MB |
| **對照組**：同樣 100B key + 126B value，但 **INTEGER PRIMARY KEY** rowid table | 226 | **392** | 15 | — |

**對照組是全篇最重要的一個數字**：列寬 226B 的 rowid table，f = 392；舊 DB 列寬 126B，f = 392。**列寬近乎翻倍，f 不動** → rowid table 的 interior cell 與列內容無關 → §3.5.3 分割定理。

#### 4.5.3 ρ-sweep 設計（D3/D7）：固定 leaf 頁數、掃 W

物理基礎見 §3.5.5 推論 2：**ρ 只由 W 決定，N 只決定 DB 與骨架的絕對大小**。因此固定 **leaf ≈ 300,000 頁**（DB ≈ 1.2GB，總 fault 量跨點恆定），讓 N 隨 W 浮動：

| 點 | W（輸入） | f | ρ（p=1 下界·說明） | 骨架（說明） | SQLite 官方建議（§4.5.5） |
|---|---|---|---|---|---|
| R1 | 101 | 33 | **2.9%** | ~38MB | ✅ 建議範圍內 |
| R2 | 126 | 27 | **3.6%** | ~46MB | ✅ 建議範圍內 |
| R3 | 226 | 16 | **5.9%** | ~80MB | ❌ **踩線**（>200B） |
| R4 | 326 | 12 | **7.7%** | ~109MB | ❌ 明顯越線 |
| R5（選配） | ~525 | ~7.7 | **~11.5%** | ~180MB | ❌ 遠越線；**須先經 §10.3 覆測，且 `overflow_pages` 必須 = 0** |

> 📌 **骨架欄是固定 300k-leaf 設計下的值（R3 = ~80MB）。** 文件他處（§00 header、D3-void、§10.3）出現的 **88MB** 是 v3「5M 列」配置的外插參考值（不同 N），非本 sweep 的骨架 —— 兩數不衝突。

> 📌 **rho_measured 事前估計（p ≈ 0.75–0.79，跑前寫下以免跑出來時被誤判為壞掉）**：ρ_實測 ≈ 1/(1 + f·p)，對 f = {33, 27, 16, 12} 約為 **{4.0, 4.8, 7.6, 9.5}%**，系統性高於上表的 p=1 下界 {2.9, 3.6, 5.9, 7.7}%（因 zipfian 只碰約 3/4 的 leaf，§3.5.1）。跨度從 2.7× 微縮到 **~2.4×**，對迴歸無妨。**這串是估計；§4.5.4 的迴歸吃的是逐 trace 實測值（§5.2 `rho_measured`），不是這裡的數字。**

> 📌 **正規化（v4）：`value` 與 `N` 欄已從本表刪除**（不只加註——真的刪）。推導值不印，避免**原地無法驗算的陷阱**：舊表寫 N=300k×rows/leaf，但表裡沒有 rows/leaf、旁邊是 f，而 f≠rows/leaf（R3：f=16，rows/leaf=15）→ 想驗算的人用 f 得到 4.8M，以為表錯了。唯一規範輸入 = **`W`（本欄，鏡像簽署的 D7）+ `leaf≈300k`**；機器來源 = `yr_sweep.yaml`。保留的 `f / ρ / 骨架` 為**說明性**（ρ 可就地驗：1/(1+f)；規範來源 f → §10.3 gate、ρ → §5.2 `rho_measured`、骨架 → builder）。**N 為 view：`tools/calc_n.py --W <W>` 現算，不轉抄。**

**為什麼固定 L 而非固定 N**：ABC 對「總共要 fault-in 幾頁」極度敏感（§1.2 的同一個理由）。固定 L → 分母恆定，跨點只有骨架與 depth 在變，正是 ρ 的分子。
**代價（明寫進 threats）**：N 跨點不同 → zipfian 下的熱 leaf 集合絕對大小不同。ρ 與 benefit 都是比值故已正規化，但 settling window 的長度可能跨點不同 → 這正是 D6 的 fixed-horizon fallback 必須綁在 leaf 頁數（D4：ops = 2×L）而非 recordcount 的原因。

> 🔴 **regime-1 純度閘（跑前，四點皆須通過，否則迴歸無效）**：每個 W 點在 timing 前量 **`R_ratio = skeleton_bytes / file-backed cache 實測值`（§5.2）**，**四點必須全部 ≈ 0**（骨架 ≪ cache）。理由：R4 骨架 ~109MB 若掉進 regime 2 → benefit 被 cache 壓力灌大，而**汙染與 ρ 同向** → 迴歸會擬合得異常漂亮（R²→0.98、α 完美）**卻是假的**。**分佈不會露餡——有相關 confound 時它只會變得更漂亮，不觸發任何警報；只有這個 gate 擋得住。** 任一點 R_ratio 非 ≈ 0 → 該點退出 regime-1 迴歸，改記入 regime-2（YR-P）分析。

#### 4.5.4 主要預測：律的迴歸檢定（取代 v3 的點估計）

> **benefit(W) = α · `rho_measured`(W)，α ∈ (0, 1]**　（自變數 = §5.2 逐 trace 實測的 ρ_窗口，**非**紙上 1/(1+f)）

- 過原點的線性迴歸，4 點（R1–R4），報 **α、R²、殘差圖**。**x 軸 = 各點的 `rho_measured`**（§5.2），不是印在 §4.5.3 的 p=1 下界。
- **為什麼對 rho_measured 而非印出的 ρ 跑**：印出的 1/(1+f) 假設 p=1（滿覆蓋）；zipfian 覆蓋率 p<1 讓真實 ρ_窗口 高 **1.2–1.5×**（§3.5.1）。對偏小的紙上 ρ 迴歸會使 α 虛高、甚至 > 1（假推翻）。綁 `rho_measured` 後，**D4 的 opcount 選值只改 sweep 跨度、不影響效度**。
- **這檢定的是律的函數形式，不只是「效應存在」。** α 是「實際能兌現多少天花板」的一個可解釋量（< 1 的部分 = **prefetch 自身的 upfront 成本**〔骨架越散越貴,見 `skeleton_contiguity`,§7〕+ 序列延遲沒完全藏住）。**⚠️ 機制是去序列化(平行度),不是局部性**：prefetch 買的是把 pointer-chasing 的序列 descent 變成一批並行讀,省的是佇列深度、非磁碟臂。**骨架散開不會讓 α 歸零**（去序列化照樣有效),只是吃掉 upfront 成本 → `skeleton_contiguity` 是 α 的**物理預告**（方向:散開 → α 較低,但 > 0）。（v4：此詮釋由 validator 實測 skeleton_contiguity=0.04 觸發重寫,推翻了原「sequential vs random」的敘述——在任何 timing 之前。）
- **低 ρ 點（R1/R2）兼三重角色**：額外的 negative control、噪音門檻的實測估計、迴歸的低端錨點。
- **禁令**：不得因某點不合預期而剔除。4 點全報，殘差全報。

#### 4.5.5 YR 的外部正當性：官方文件背書（v4 新增，改寫 threats）

v3 把 YR 標為「人為壓低 fanout，不代表典型部署」——**這個自我批評過重了**。實情是：

- SQLite 官方對 WITHOUT ROWID 的使用建議是：**單列平均大小應小於 page 的 1/20**（4KiB page → 約 200 bytes）。理由正是 rowid table 用 B*-tree 把內容全放 leaf，而 WITHOUT ROWID 用普通 B-tree、**內容同時存在 leaf 與中間節點**，撐大中間節點並提高搜尋成本。
  → 來源：<https://sqlite.org/withoutrowid.html>（"Clustered Indexes and the WITHOUT ROWID Optimization"）
- SQLite 官方論壇（file format 說明）：index entry **超過 page 的 1/4 即 spill 到 overflow，藉此保證最小 fan-out = 4**。
  → 來源：<https://sqlite.org/forum/forumpost/ad86fbaa04>

**因此 YR 不是人造 strawman，是官方明文警告的配置**，且 sweep 的 R1/R2 落在建議範圍內、R3/R4 踩過線。論文的適用條件可以寫成一句對映到官方文件的話：

> *"Benefit exceeds ~3% only for row widths beyond ~200 B in WITHOUT ROWID tables — the very regime SQLite's own documentation advises against. Within SQLite's recommended design space, and across the entire rowid-table class, interior prefetching is bounded below the noise floor."*

#### 4.5.6 YR-P：cache-pressure 軸的公平性規則（違反任一條 → 該 run 作廢）

**基底 = R3（W=226，骨架 ~80MB）**——骨架夠大才掐得動（§3.5.5 推論 3）。

1. **兩策略同 limit**：pread 與 fadvise 臂必須在**完全相同**的 `MemoryMax` 下配對比較；不得各自取最優 limit。執行：`systemd-run --scope -p MemoryMax=$M -p MemoryHigh=$M ...`（cgroup v2）。**✅ v4：本機實測確認 `MemoryMax` 可 enforce（§11）**。
2. **兩層 cache 都要記錄與控制**：`PRAGMA cache_size` 在所有 arm 固定為同一值並記入 manifest；R 的分母不是 `MemoryMax`，是 run 期間 `memory.stat` 的 **file-backed 頁實測均值**（`MemoryMax` 還含 anon：SQLite heap、pager cache 本體）。
3. **`fadvise(WILLNEED)` 預讀頁在壓力下先被逐出是預期現象，不是 bug**：這正是 regime 2 裡 fadvise 策略的真實行為，settling-point 方法論剛好能量到它。已寫進 §-1.4 的預測欄，事後不得以此為由剔除 run。
4. **每個 (limit, strategy, repeat) 之間**：drop_caches（本機經 `/usr/local/sbin/drop-caches` wrapper，§11）+ 重建 scope，杜絕殘留。
5. **每個 limit 的 R 值**（骨架 ~80MB / file-cache 實測）與效益一起畫成曲線進論文；單點不得單獨引用。

---

## 5. Tier 0 Validator — 這才是真正堵住坑的東西

**YCSB 不會幫你檢查任何東西。** 它只保證 key 分佈是公認的。
被咬的兩次（churn 位移 = 0、C 的 not-found）都是「敘事沒有物理量佐證」，**換 generator 不會自動解決**。

### 5.1 前置條件（v1 未列）

`rightmost_leaf_share` 與 `hotset_jaccard_series` 都需要 **key → page 映射**。取得方式：

```bash
# 需要編譯旗標（🔧 本機不可用，見 §11 —— 改用 tools/ 下已備妥的路徑）
gcc -DSQLITE_ENABLE_DBSTAT_VTAB ...
```

```sql
-- 每個 page 的 payload / cell 數 / 名稱
SELECT name, path, pageno, pagetype, ncell, payload, unused FROM dbstat WHERE name='items';
```

或自行 parse b-tree page header。**這是 §6 步驟 3 的硬前置條件，沒有它 validator 只是半個。**

> **v4 進度註**：dbstat 管線已可用（舊 DB 量測與 §10.3 的 YR 幾何皆由此產出）。**但 🔧 取得路徑不是上面那條**：本機無 `sqlite3` CLI、無 `gcc` 編 dbstat 擴充、無 `mvn` —— 實際走法見 §11。上方指令僅為 canonical 形式，照抄會失敗。
>
> **⚠️ D8（OPEN）**：現行 dbstat 腳本的 `depth` 有系統性偏移（`sqlite_schema`：1 leaf / 0 interior → 真實 depth 1，報 3）。`btree_depth` 檢查項在 D8 定案前**回報的數字不得引用**。

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
  "hotspot_movement":      "移動熱點宣稱的『前置條件保護』診斷（取代舊 hotset_jaccard_series）。"
                           "⚠️ 舊檢查『Jaccard 必須 < 1』會誤放行——Jaccard≈0 既可能『熱點飛得快』，也可能"
                           "『根本沒熱點』（均勻流下每段 top-1% 是新鮮隨機抽樣，相鄰段幾乎不重疊）。修正："
                           "step1 hotset_present?（unique_key_ratio<0.98 且 top-1% 集中度>3×均勻）；"
                           "step2 才問位移（top-1% 質心隨時間）+ Jaccard；**無熱集 → 移動宣稱一律 FAIL、Jaccard 不予解讀**。"
                           "位移對『散開』熱集無意義（質心≈中央±抽樣噪音）→ 加**第2層 `hot_key_contiguity`** 前置："
                           "散開（hot_span_frac ≥ 門檻）則位移不予解讀。**用數字判定、不靠臂名**。三個門檻在 "
                           "`validator_thresholds.yaml`（啟發式，非推導），validator **報餘裕**（離門檻多遠）而非只報 pass/fail",
  "unique_key_ratio":      "unique_keys / total_ops。接近 1 = 抽樣不放回 = 根本沒有熱點，此時任何 locality/"
                           "移動宣稱一律 fail（現由 `--claims-moving-hotspot` 的前置條件**強制執行**，非只報數字）",
  "measured_skew":         "回報**兩個**數字，**不可混用**：`top1_key_share` = 最熱**單一 key** 佔比（≈3.8%）；"
                           "`top1pct_keys_share` = **前 1% key 集合**佔比（≈25%）。**論文的『skew』一律引 `top1pct_keys_share`**"
                           "（§3.2 規則）；`top1_key` 只是單點健康檢查，不是 skew。**不得引用 zipfianconstant（no-op，§3.2）**",

  # ── 堵 §3.3 的物理佈局 confound ──
  "page_count":     "DB 總頁數。同一組實驗的兩臂必須一致，否則 headline 作廢",
  "fill_factor":    "leaf page 平均填充率。ordered load ≈ 100%，random load ≈ 69%",
  "btree_depth":    "B-tree 層數。跨設定不一致 = 不可直接比",
  "skeleton_bytes": "interior page 總量。決定 prefetch 的收益上限（§3.5）",
  "row_width_W":    "整列平均寬度（payload/cells）。WITHOUT ROWID 表的 f 由它決定（§3.5.2）；"
                    "rowid 表則必須驗證 f 與它無關（分割定理的重複驗證）",
  "fanout_measured":"interior fanout = leaf 頁數 / L1-interior 頁數，dbstat 實測。"
                    "**任何進入 §-1.4 的 fanout 必須來自這裡，不得來自紙上外插（v2/v3 各錯一次）**",
  "overflow_pages": "必須 == 0。> 0 → W 越過 maxLocal(~1002B)，ρ 的分母被 overflow 讀取灌大，"
                    "該點的天花板計算失效（§3.5.4）",

  # ── 堵 §3.1 的 no-op 自變數 ──
  "hot_key_contiguity": "top-1% key 在 rowid 空間的相鄰程度 = `hot_span_frac` = span(top-1%)/span(all)。"
                        "**v4 已實作**（實測 ordered=0.0099 / hashed=0.9947，門檻 0.10 穩落空檔）。兩用："
                        "(a) `hotspot_movement` 位移的**第2層前置**（散開則質心=回歸均值噪音，不予解讀）；"
                        "(b) §3.1——若 ordered 與 hashed 兩臂此值相近 → insertorder 是 no-op，sensitivity axis 作廢。"
                        "門檻 `max_hot_span_frac` 在 validator_thresholds.yaml",

  # ── v3/v4 新增：堵 §3.5 / §4.5 ──
  "rho_measured":   "settling window 內 interior fault 佔全部 fault 的實測比例（= §3.5.1 的 ρ_窗口，已含覆蓋率 p）。"
                    "**§-1.4 / §4.5.4 benefit=α·ρ 迴歸的自變數來源**（非紙上 1/(1+f) 下界估計）；亦為告警線：效益量出 > 該 trace 的 rho_measured → pipeline bug",
  "cache_config":   "PRAGMA cache_size、MemoryMax、run 期間 memory.stat file-backed 均值。"
                    "三者缺一，該 run 不得進聚合",
  "R_ratio":        "skeleton_bytes / file-backed cache 實測值。YR-P 的自變數（逐 run 記錄）；"
                    "**亦為 regime-1 純度閘：4 個 sweep 點跑前皆須 ≈ 0，否則 regime-2 汙染與 ρ 同向、迴歸假漂亮（§4.5.3）**",
  "dbstat_path":    "DB 的 dbstat 快照來源。§6 step 3.5 的靜態工具由此算各 trace 的 rho_measured（§4.5.4 迴歸自變數）"
                    "與 R_ratio（regime-1 閘），皆在 timing 前完成",
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

## 6. 遷移步驟（v4：驗證優先 + 進度標記）

| # | 步驟 | 產出 / 通過條件 | 狀態 |
|---|---|---|---|
| **0** | **跑 §10 驗證清單（10.1–10.2）** | 確認 A1（insertorder 是否 no-op）、A2（zipfianconstant）、格式 | ☐ |
| **1** | **量舊 DB 的 page_count / depth / skeleton_bytes**，填 §3.4 反推工作單 | 已填：leaf 19,983 / 真實 depth 3 / 骨架 204KB / f = 392 | ✅ **完成（2026-07）** |
| **2** | **決定 schema（§2.5 = D1/D2）**，寫 `tools/keymap.py` + 保序性單元測試 | 決定已 CLOSED；測試必須綠。**v4：§4.5.1 的 `inflate()` 及其兩個測試已刪除，不必實作** | ✅ **決策 CLOSED；`tests/test_keymap.py` 兩測全綠（2026-07-16 實跑：`order_preserving` + `dense_bijection` PASS）→ 依賴此映射的 15 條 trace 有效** |
| **2.5** | **§10.3 YR 原型驗證** | ✅ **完成，並否決 D3-v3**（f=16 不是 38）。機制已釘死：WITHOUT ROWID interior 存整列；rowid 對照組 f=392 與列寬無關 | ✅ **完成（2026-07）** |
| **2.6** | **§10.5 depth 度量校正（D8）** | 兩支工具的 depth 定義統一，回頭校正所有已報數字 | ☐ **只擋 §-1.4 的 YR-P (d−1)/d 列**（headline + YR sweep 已簽） |
| **2.7** | **§10.3 覆測 D7 的 sweep 點**（R1–R4 各建一次 200k 原型，驗 f 與 `overflow_pages==0`；R5 選配） | 4 點的 f 落在實測表 ±10% 內 → D7 轉正 | ✅ **完成（2026-07-16）**：f = {33.1, 27.0, 16.0, 12.0} 全 PASS、overflow=0；順帶確認 **INT-PK WITHOUT ROWID 同 regime** → harness 手術候選取消（R5 未測） |
| **3** | **寫 `validate_trace.py`（含 dbstat 前置與 v3/v4 新檢查項），回頭跑舊的 A/B/C/churn** | ⭐ **把已知的兩個坑變成硬數字，是給老師看的最強證據。做在遷移之前，不是之後** | ☐ |
| **3.5** | **`tools/calc_rho_measured.py`（靜態，由 dbstat 算）**：逐 trace 算 `rho_measured`（§4.5.4 迴歸自變數）與 `R_ratio`（§4.5.3 regime-1 閘） | 4 點 R_ratio 皆 ≈ 0 才可進 regime-1 迴歸；rho_measured 逐 trace 落地。**跑 timing 前完成** | ☐ |
| **4** | **§00 全表 + §-1 全文（含 §-1.4 預測）由研究者本人 git commit** | git 時間戳。**必須在步驟 5 之前。** | ✅ **已簽（2026-07-16，commit `1a65af3`；D3/D4/D6/D7 → CLOSED）**；D5/D8/D9 維持 OPEN、不擋 sweep（D8 只擋 §-1.4 的 YR-P 列） |
| 5 | 產 headline 家族 trace（YC / YC-h / YA / YB / YF / YC-u；YD/YE 需接 `--insert-base`），逐條過 Tier 0 | parse_losses == 0 | 🟡 **YC-u 完成**（real YCSB → parse_losses=0 → dense rowid → Tier 0 PASS），其餘待產 |
| 5.5 | 編 `benchmark_harness`（🔧 §11：gcc 可用、免權限），跑 **YC 的 negative control**：實際把「效應 ≈ 0」量出來 | 效應與 0 不可區分 → §3.5.3 分割定理的第一個實證 | ☐ **建議下一步** |
| 6 | 生成完整 matrix（§4 × §9 分層，含 YR ρ-sweep / YR-P），每條配 manifest + validation | 全部通過 Tier 0 | ☐ |
| 7 | 重跑 A3/A4，headline 只引用 Tier 1；效益逐 arm 對照 `rho_measured`（§5.2）回報；YR 跑 §4.5.4 迴歸 | 依 §8 聚合 | ☐ |
| 8 | 舊自造 workload 依 §1.3 處置（C 退場，其餘降級 Tier 2 + 改名） | — | ☐ |

## 7. 誠實的限制（論文 threats to validity 直接寫）

- YCSB 是 KV API 層，**表達不出 page-layout 語意**。任何關於 interior node 結構的細緻機制探討仍需 Tier 2 probe。這不是弱點，是分工。
- YCSB 沒有「hot set 在 keyspace 中間搬移」的 workload（`latest` 只往尾端長）。要測這個只能自造 → Tier 2。
- 用 BasicDB dump trace = 不含真實 client 的 timing / concurrency。實驗是 storage-layout 導向，通常可接受，但要寫明。
- `zeropadding` / `fieldlength` 一動 fanout 就變，跨設定不可直接比。已固定（§3.2 / §3.4）。
- YCSB 的公信力**只覆蓋 key 分佈**。`fieldlength` / `zeropadding` / schema / load order / rowid mapping 全部是我們的選擇，且每一個都影響 page layout。**這些選擇的公信力來自 §-1 預先承諾與 §5 validator，不來自 YCSB。**
- `requestdistribution=zipfian` 的實際分佈是「Zipf 條件於 keynum ≤ acknowledged insert counter」（rejection sampling），且經過 ScrambledZipfian 的 rank→keynum hash 折疊。**它不是 Zipf(0.99, N=recordcount)**，任何解析式試算不適用；一律引實測值。
- 用 order-preserving dense rowid 取代 TEXT key（§2.5）保留了 B-tree 的相鄰關係，但改變了 key 的物理表示（string → int）。cell 大小與 fanout 因此與原生 YCSB-on-SQLite 不同。此舉是為了與 prior configuration 可比；trade-off 明寫。
- **（v4 新增）INT-PK 的生態效度**：YR 用 `(id INTEGER PRIMARY KEY, v BLOB) WITHOUT ROWID` + dense rowid（複用 headline 映射），是為了**消掉 int-vs-text-key confound、與 headline 走同一查詢路徑**。代價：真實 YCSB 部署多用 TEXT key，本 arm 的 key 表示因此非典型。§2.7 已實測 INT-PK 與 TEXT-PK 幾何**逐點相同**（f 一致），故**幾何結論可外推到 TEXT-PK**；但「典型部署即 dense int rowid」不成立，明寫。
- **（v4 改寫）** YR 的低 fanout 是**設計變數**，不是缺陷：W 由 builder 建 DB 時施加（value 大小，非 YCSB 旋鈕；§4.5.1 信封論證），schema 是 SQLite 原生的 WITHOUT ROWID。R3/R4 的列寬確實超出 SQLite 官方建議的 ~200B（§4.5.5），**但這正是論文的適用條件敘述，不是需要道歉的偏差**：技術只在官方建議之外的設計空間才有價值。仍須明寫：YR 不宣稱典型部署能拿到 5.9%。
- **（v4 新增）** ρ-sweep 固定 leaf 頁數、讓 N 隨 W 浮動（§4.5.3），因此跨點的 record 數不同 → zipfian 下熱 leaf 集合的絕對大小不同。ρ 與 benefit 皆為比值故已正規化，但 settling window 長度可能跨點不同；D4 將 ops 綁在 leaf 頁數（2×L）而非 recordcount 以緩解，殘餘影響在殘差圖中檢視。
- **（v4 新增）** 分割定理（§3.5.3）的 f ≈ 400 是 4KB page 下的值。page_size 改變 f 亦變（f ≈ U/9），但結論的**形式**（rowid table 的 f 與列寬無關）與 page_size 無關。本研究只在 4KB 下驗證。
- **（v3 新增，保留）** YR-P 的雙位數效益僅適用於「骨架 > 可用 file cache」的記憶體受限部署（多租戶、容器配額），適用條件以 R 值定量給出。
- **（v3 新增，保留）** §3.5 的天花板律假設點查、忽略 random vs sequential 讀的成本差與 prefetch 自身的 CPU/IO 開銷（兩者都讓實際收益**更低**，故上界方向安全——這兩項正是 §4.5.4 迴歸裡 α < 1 的來源）；scan workload（YE）的 interior→leaf readahead 機制不受此律約束（D9）。
- **（v4 新增）headline DB 無 secondary index（D11）→ 檔案佈局與舊 A/B/C 的 108MB 檔案不同**。骨架的 51 個 interior 頁，在舊 DB 散在 26,006 頁裡（`skeleton_contiguity` largest_run = 2/51 = 0.04），headline DB 散在 20,035 頁裡——實體連續性不同。**這不影響 ρ**（頁數比），但**影響 α 的 upfront 成本**。prefetch 的機制是**去序列化**（把 descent 的序列 pointer-chasing 變成一批並行讀,§3.5.1）——骨架**散開照樣去序列化有效,α 不歸零**；但那 51 頁若實體聚攏 → 一次循序讀就發完（upfront 便宜）,散開 → ~51 次並行隨機讀（upfront 貴）→ α 較低。**「加索引」修不了**（版面本來就不會一樣）→ 依 §-1.3 把形容詞變數字：`skeleton_contiguity`（§-1.1 閘一併回報,非通過條件）逐 DB 定量,作為 α 的物理解釋。
- **（v4 新增）** 本 spec 的 fanout 幾何在 v2 與 v3 各錯過一次（皆為「interior cell 只有 key」的直覺）。現行所有 f 數字均為 dbstat 實測，且 validator 的 `fanout_measured` 強制此來源。但這也提醒：**任何未經實測的 page-format 推理在本研究中都應視為不可信**。

---

## 8. 統計聚合

v1 只寫「× 10 seeds」，沒說怎麼合成一個數。

| 項目 | 方案 |
|---|---|
| **配對** | 同一條 trace 上跑 pread 與 fadvise → **天然 paired design**，消掉 trace 間變異。**不得跨 trace 比較** |
| **報告單位** | **per-trace ABC 差值的分佈**（N 個點），不是只報平均。畫 dot plot 或 paired slope chart。**每張圖並列該 arm 的 `rho_measured` 橫線**（v4：實測 ρ_窗口，非紙上 p=1 下界） |
| **檢定** | paired **Wilcoxon signed-rank**（N 小，不假設常態）。報 effect size 與 CI，不只報 p |
| **重複** | 每條 trace × 每策略跑 3 次 cold-start，取 median 作為該 trace 的代表值（消掉 run-to-run 噪音，再進 paired 檢定） |
| **⚠️ settling point fallback（v3 新增）** | YR / YR-P 之下骨架大、收斂慢，convergence-based settling point 可能**不觸發或觸發過晚**。**預先註冊 fixed-horizon ABC（前 K ops，K 依 D6 跑前 commit）為 fallback**；兩種定義都回報，不得事後挑對自己有利的那個。convergence 是否觸發本身記入 validation.json |
| **⚠️ YR 的主檢定不是 Wilcoxon（v4）** | YR 的主要預測是 **benefit = α·ρ 的迴歸**（§4.5.4），跨 4 個 W 點。每個 W 點內部仍用 paired 設計取該點的代表 benefit，再把 4 個點（x = 該點的 `rho_measured`，§5.2；**非**紙上 ρ）餵進**過原點的線性迴歸**，報 α、R²、殘差圖。**Wilcoxon 只用於「該點效應是否 > 0」的次要檢定** |
| **⚠️ 語意紅線** | N 條 trace 檢定的是 **workload 內變異**，不是**參數敏感度**。這兩件事在 reviewer 眼裡是分開的。**論文中不得用同一個 "robust" 涵蓋兩者**（= §-1.3）。**v4 補充**：ρ-sweep 是**參數線**，它支持的宣稱是「律的函數形式在此範圍內成立」，**不是** "robust"。第三種東西，第三種措辭 |

### 8.1 儀器校準（Round 3a，**實測 2026-07-16，未簽——校準非預測**）

> **🔴 更正（2026-07-16，晚於下方初稿；trace-over-clean：不刪初稿，標作廢）**
> 下方「正對照推不動聚合的尺」的結論**錯了，成因是 tmpfs 假象**。初稿的 DB 建在 `/tmp`——而 `df -T /tmp` = **tmpfs（RAM-backed）**：tmpfs 檔案不是 page cache，是檔案本體，`drop-caches` 驅逐不了它 → `majflt` 恆 0，與 prefetch 無關。
> **把同一個 DB 建到真磁碟（`/home`，xfs on nvme）後，同一 harness、同一 `--cold-advice dontneed --drop-caches-script`：`majflt` 0→**871**、`first_query` 14→**543µs**（≈38×）、`avg` 2.04→3.38µs。尺會動，動很大。**
> 修正後的三點:(1) 聚合 `avg` 仍是弱訊號（871/80000 個 op 才冷讀，其餘被暖迴圈攤銷,2.04→3.38µs）;(2) **訊號住在 transient——`first_query` 冷/暖差 ≈38×**;(3) **Round 3b/4 不再被擋,唯一鐵律:DB 必須在磁碟路徑（非 `/tmp`），且開跑前驗 `majflt>0`**。A/A 噪聲地板（CV 0.49%）仍成立，但那是**全快取暖區**的地板。
> ⚠️ 操作紅線:**任何計時實驗的 DB 一律放 `/home`（xfs），never `/tmp`；pre-flight 必須 assert `df -T` 非 tmpfs 且 baseline `majflt>0`。**

先量儀器再信讀數。headline DB（600k rows，79MB，過 §-1.1 閘 5/5）+ YC-hashed-hdf0.10 trace（80000 read，經 `ycsb2trace`→`keymap` 管線產出）在本機（60GB RAM）上量：

- **A/A 噪聲地板（全快取區）**：同組態 warm 重跑 6 次（棄首次暖機），`avg_latency` mean **2.04µs**、**CV 0.49%**、half-range/mean 0.74%。→ 聚合層 run-to-run 噪聲 < 1%。

- **🔴 正對照推不動聚合的尺**〔**⚠️ 作廢——見上方更正,此為 tmpfs 假象**〕：試遍所有驅逐槓桿——`madvise(dontneed)`、`madvise(pageout)`、setuid `/usr/local/sbin/drop-caches`（全域 cache 49.6GB→2.3GB 確實清掉）、cgroup `MemoryMax=48M`（< 79M DB）、以上組合、`mmap` on/off、open before/after-cold——**聚合 `avg_latency` 鐵打在 2.2–2.3µs、`majflt`=0、跑完 20035/20035 頁全駐**。唯一動的是 `first_query_latency`（11–46µs，冷約 2–4×，單一讀）。

- **機制**：60GB RAM ≫ 79M DB；SQLite 開檔走 `pread()` 把頁灌回 page cache（計 **minflt**，1253→18574，**非 majflt**），mmap 存取隨即命中 = minor；80000 個查詢的暖工作集把少數冷讀**攤銷**掉。用戶態槓桿的驅逐速度追不上重快取。

- **🔴 後果（擋住 Round 3b/4，非改任何簽名決定）**〔**⚠️ 作廢——tmpfs 假象;磁碟路徑上尺會動,見上方更正**〕：**聚合 `avg_latency` 儀器在 headline DB 尺寸、本 host 上，對 I/O 效應無已證的動態範圍**。此時量到「效應≈0」與 §-1.1 的 headline 預測（ρ≈0.27%、效應與 0 不可區分）**在數字上一致，但成因被混淆**：分不清「prefetch 效應本就小」還是「計時迴圈裡根本沒有磁碟 I/O 可 prefetch」。§8 line 909 的「3 次 **cold-start**」前提**尚未證成真的是冷的**。→ **Round 3b（YC 負對照）與 Round 4 的計時,開跑前必須先讓正對照動**（候選協定:小批冷讀、每批間 `drop_caches`；或 DB ≫ RAM;或在 `drop_caches` 後於記憶體受限 scope 內重讀並驗 majflt>0）。**在正對照證明尺會動之前,任何聚合計時結果不可解讀。** 此為 measured 校準,不觸發簽名,但為 Round 3b/4 的前置閘。

---

## 9. 成本分層（v4 更新）

配合 §3.1（zipfian 下 insertorder 是 no-op）與分層，v1 的 ~960 runs 砍到如下，**而且每一條都有存在的理由**。

| 層 | 內容 | traces | configs | runs（×2 策略 ×3 repeat） | 備註 |
|---|---|---|---|---|---|
| **Tier 1a** | **headline**：YC-hashed | **10** | 1 | 60 | DB 108MB，還原快 |
| **Tier 1b** | **spatial axis**：YC-h × {hashed, ordered}、YD × {hashed, ordered} | **5** | 4 | 120 | — |
| **Tier 1c** | 其餘：YA / YB / YE / YF / YC-u | **3** | 5 | 90 | — |
| **Tier 1b'** | `hotspotdatafraction` sweep（YC-h，5 點） | 3 | 5 | 90 | — |
| **Tier 1r（v4 改）** | **YR ρ-sweep**：R1–R4 各一 config | **3** | 4 | **72** | ⚠️ 每點 DB ≈ 1.2GB；4 個 DB 要各建一次。load trace 4 條（N 各不同） |
| **Tier 1r'（v4）** | **YR-P**：R3 基底 × `MemoryMax` 非 ∞ 3 點（D5） | 3 | 3 | 54 | 與 R3 共用 trace 與 DB image |
| | | | **合計** | **~486 runs** | headline 系 ≈ 18h + YR 系 ≈ 10–12h（含 4 個 1.2GB DB 的建置與還原） |

**v3 → v4 的成本變動**：+42 runs（YR 從單點升級為 4 點 sweep）+ 3 個額外的 1.2GB DB 建置。**買到的是律的函數形式檢定（迴歸）而非存在性檢定**，以及兩個免費的額外 negative control（R1/R2）。這是本 spec 裡投報率最高的一筆增支。

**每點 traces 只用 3 條的理由**：主檢定已從「該點是否顯著 > 0」轉為「跨 4 點的迴歸斜率」，統計力來自點數 × 每點精度，不是單點的 n。每點 3 條 × 3 repeat 取 median 已足以壓住 run-to-run 噪音。

**load trace 需求**：headline 系 2 條（每個 `insertorder` 一條，`CounterGenerator` 零隨機）+ YR 4 條（R1–R4 的 N 不同）= **6 條**。

---

## 10. 動工前的十分鐘驗證清單 ⚠️ 先跑這個

**本 spec 對 YCSB 內部與 SQLite page format 的所有斷言都必須自己確認。** 在寫任何一行 `ycsb2trace.py` 之前：

> 🔴 **v4 立為規則（因為 v2 與 v3 各犯了一次同樣的錯）**：
> **任何 fanout / 骨架 / depth 數字進入 §-1.4 預先承諾之前，必須有 dbstat 實測背書。紙上外插只能當假設，不能當承諾。**
> v2 估骨架 1.6MB（實測 204KB，錯 8 倍）；v3 估 YR fanout 38（實測 16）。兩次都是同一個直覺——「interior cell 只有 key」——在不同地方復發。
>
> 🔧 **本節所有指令為 canonical 形式，本機不可直接執行**（無 `bin/ycsb` py2 執行環境、無 `mvn`、無 `sqlite3` CLI）。實際走法見 **§11**。

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

### 10.3 🔴 YR 原型驗證 —— ✅ 已執行，並否決了 D3-v3

**§4.5.2 的幾何全是紙上外插。在建 1.2GB DB 之前，先用 200k rows 驗算。**

```bash
# 1. 建小樣（200k rows、掃 value 大小、sorted load）
python3 workload_fixed/tools/build_yr_prototype.py --rows 200000 --db /tmp/yr_proto.db

# 2. dbstat 對照（🔧 經 python sqlite3 module，非 CLI，見 §11）
#    SELECT pagetype, count(*) pages, sum(ncell) cells
#    FROM dbstat WHERE name='items_yr' GROUP BY pagetype;
```

#### 執行結果（2026-07）：**D3-v3 遭否決**

| 檢查 | v3 預期 | **實測** | 判定 |
|---|---|---|---|
| interior fanout（W=226） | 38 | **16.0** | ❌ 落在容忍區間 [33,43] 之外 |
| 骨架（外插 5M） | 32MB | **88MB** | ❌ |
| ρ 天花板 | 2.6% | **5.9%** | ❌（方向對 YR 有利，但仍違反預先註冊） |
| overflow 頁 | 0 | 0 | ✅ |

**根因**：WITHOUT ROWID 的 interior cell 存**整列**（key+value），不是只有 key。簽名證據：**f ≈ rows/leaf**（33/33、27/27、16/15）。詳見 §3.5.2。

**連帶發現（比否決本身更重要）**：INTEGER PK 對照組（同樣 100B key + 126B value）f = **392**，與舊 DB（列寬 126B）的 392 **相同** → rowid table 的 f 與列寬無關 → **§3.5.3 分割定理**。

**處置**：依本節自身規則「任一不符 → 更新 D3 後重跑」→ D3-v3 標記 `VOIDED`，重新註冊為 **D3-v4（ρ-sweep）**。**這是預先承諾制度的一次成功執行，不是違反**（§-1.1 的唯一例外條款）。

#### 10.3.1 D7 sweep 點覆測 —— ✅ 已執行（阻擋解除）

R1–R4（W = 101/126/226/326）各建一次 200k 原型，通過條件：

| 量 | 通過條件 |
|---|---|
| f | 落在 §4.5.2 實測表 ±10% |
| `overflow_pages` | **必須 == 0**（W 越過 ~1002B 才會觸發，但仍要驗，§3.5.4） |
| rows/leaf | 與 f 之差 ≤ 2（機制簽名的重複確認） |
| depth | **待 D8 定義統一後才回報**（§10.5） |

R5（W≈525）為選配，須額外驗 `overflow_pages == 0`，因為它離 minLocal(~489B) 已不遠。

#### 執行結果（2026-07-16，`tools/verify_yr_geometry_v4.py`，200k rows/點）

**① D7 sweep gate（原生 23B key）—— ✅ 全數 PASS：**

| 點 | W | 預期 f | **實測 f** | rows/leaf | overflow | 判定 |
|---|---|---|---|---|---|---|
| R1 | 101 | 33 | **33.1** | 33 | 0 | ✅ |
| R2 | 126 | 27 | **27.0** | 27 | 0 | ✅ |
| R3 | 226 | 16 | **16.0** | 15 | 0 | ✅ |
| R4 | 326 | 12 | **12.0** | 11 | 0 | ✅ |

4 點全部命中 §4.5.2 實測表、overflow 全 0 → **D7 的預先註冊幾何成立，解除「阻擋 YR」**。D3/D4/D7 已具備簽署條件（簽署仍為 §00 的人工動作；D8 depth 只擋 §-1.4 的 YR-P 列，不擋 sweep 幾何）。

**② INTEGER-PK WITHOUT ROWID 探測（同 W 對照）—— ✅ 與 TEXT-PK 幾乎逐點相同：**

| W | TEXT-PK f | **INT-PK f** | 同 regime? |
|---|---|---|---|
| 101 | 33.1 | **32.9** | ✅ |
| 126 | 27.0 | **27.0** | ✅ |
| 226 | 16.0 | **16.0** | ✅ |
| 326 | 12.0 | **12.0** | ✅ |

`CREATE TABLE items_yr (id INTEGER PRIMARY KEY, v BLOB) WITHOUT ROWID` 走同一條 index-b-tree、interior 存整列，f 與 PK 型別無關（機制見 §3.5.2；rowid table 的 f=392 是唯一例外）。**後果**：YR **複用 headline 的 dense-rowid 映射邏輯（`keymap.py`，§2.5）自產 4 條 trace**（N 各異，**非**複用 headline 的 trace 檔——見下方 ④ 警告）、查詢仍是 `WHERE id = ?`（整數綁定，與 headline 同路徑）→ **`benchmark_harness.c` 的 TEXT-PK 手術不需要，且消掉「int key vs text key」這個 confound**。**已併入 D3**（TEXT-PK → INTEGER-PK；§6.5 手術條已刪），D3 待簽。

> ④ **警告（會靜默通過檢查的錯）**：複用的是 §2.5 的**映射邏輯**，**不是 headline 的 600k trace 檔**。YR 四點 N 由 W 決定（`yr_sweep.yaml` + `calc_n.py` 現算）；若拿 headline 的 600k trace 去跑 YR 的大 DB，查詢只碰到前 60 萬列 → 工作集全錯，而 Tier 0 的 `key_range_subset` 仍會**通過**（那些 key 確實存在）。故 YR 必須自產 4 條 trace（§4.5.3/§9）。

> ⚠️ 尺度註記：原型用 200k rows（dense id varint ≈3B）；真實 sweep 的 N 顯著大於 200k（最大點 id varint ≈4B），對 W=101 點的整列寬影響 ≈1% → f 幾乎不變（f = U/整列寬，由 value 主導）。**R5（W≈525）尚未覆測**。

### 10.4 cgroup 公平性 sanity check —— 🟡 能力已確認，尺度覆測待做

```bash
# 確認 MemoryMax 真的在掐 file cache，且 memory.stat 可讀出分母
systemd-run --scope -p MemoryMax=48M --wait bash -c '
  cat /tmp/yr_proto.db > /dev/null
  grep -E "^(file|anon) " /sys/fs/cgroup/$(cat /proc/self/cgroup | cut -d: -f3)/memory.stat
'
# 預期：file 值被壓在 limit 之下、遠小於 DB 大小；anon 為 process 自身開銷
# 並確認 drop_caches 後重跑，file 從 0 開始長
```

**執行結果（2026-07）**：✅ **`MemoryMax` 實測可 enforce，`memory.stat` 的 file/anon 可讀** → **YR-P 這條軸成立**（v3 寫的是「可能」，v4 改為「已確認」）。
**⚠️ 尚待覆測**：目前只在 200k 原型（DB ~50MB）上確認**能力**。D5 的 limit 點必須在**真實 R3 尺度（DB 1.2GB / 骨架 80MB）**上重測 R = 骨架/file-backed 的實際換算後才能定案。

### 10.5 🐛 depth 度量校正（v4 新增，D8，只擋 §-1.4 的 YR-P 列）

**現行工具的 depth 不可信，且兩支工具偏移不同。**

| 對象 | 真實 depth（可由 dbstat 頁數推定） | 工具回報 | 偏移 |
|---|---|---|---|
| `sqlite_schema` | **1**（1 leaf、0 interior——不可能更深） | 3 | **+2** |
| `items` | **3**（root → 50 L1 → 19,983 leaf；f=392） | 5 | **+2** |
| `idx_items_k1` | **3**（20 interior、3,106 leaf；f=155） | 5 | **+2** |
| YR 原型（W=226, 200k rows） | **5**（我方外插：13.3k leaf → 833 → 52 → 4 → root） | 6 | **+1**？ |

`sqlite_schema` 這一列是鐵證：**一個只有單一 leaf 頁的 B-tree，depth 必為 1**。dbstat 腳本穩定 +2；YR 原型腳本偏移不同 → **兩支工具的 depth 定義不一致**。

**通過條件**：
1. 統一定義為 **「root 到 leaf 的頁面層數，leaf 與 root 皆計入」**（單頁樹 = 1）。
2. 兩支工具在 `sqlite_schema`(=1)、`items`(=3)、`idx_items_k1`(=3) 三個已知答案上全部吻合。
3. 回頭校正 §3.4、§-1.4、§10.5 原型中所有已報的 depth 數字（§4.5.2 表無 depth 欄，不涉及）。

**為什麼阻擋**：d 直接進 §-1.4 的 YR-P per-query 上限 (d−1)/d，也決定每次冷 descent 的 interior miss 數。d=6 → 83%、d=8 → 87.5%——一個沒被發現的 +2 會讓論文的預先承諾數字與物理不符，而且是**朝有利方向**的不符。



---

## 11. 🔧 執行環境實況（v4 新增 —— v2 有此註記，v3 漏掉）

**本節存在的理由**：v3 正文的指令全部退回 canonical 形式（`bin/ycsb`、`mvn`、`sqlite3` CLI），**而這台機器上沒有一條跑得動**（`gcc` 是唯一例外：可用，只是自編 DBSTAT 那條路不需要）。工具本身是對的（`workload_fixed/tools/` 下的東西都能用），但正文會誤導照做的 agent 去撞牆。

### 11.1 不可用 / 可用清單（實測）

| 能力 | 狀態 | 替代路徑 |
|---|---|---|
| `bin/ycsb`（官方 wrapper） | ❌ Python 2 腳本，本機無 py2 | 直接以 `java -cp <core+basic jars>` 呼叫 `site.ycsb.Client`；**properties 語意完全相同**，§2.2 的參數表照用 |
| `mvn` | ❌ 不可用 | 用 release tarball 的預編 jar（§2.1 已列此路徑） |
| `sqlite3` CLI | ❌ 不可用 | Python `sqlite3` module（dbstat 查詢照跑，§10.3 即由此產出） |
| `gcc -DSQLITE_ENABLE_DBSTAT_VTAB` 自編 SQLite | ➖ **不需要**（`gcc` 本身可用，實測 15.2.0） | 系統 Python 的 sqlite3 已含 dbstat（實測可查）——這條路**不必走**，不是 gcc 缺席 |
| `gcc` 編 `benchmark_harness.c` | ✅ **可用，免權限** | 直接編 |
| cgroup v2 `MemoryMax` enforce | ✅ **實測確認**（§10.4） | `systemd-run --scope` |
| `memory.stat` file/anon 讀取 | ✅ 實測確認 | R 的分母來源（§4.5.6-2） |
| drop_caches | ✅ 可用 | 經 `/usr/local/sbin/drop-caches` wrapper（**非** `echo 3 > /proc/sys/vm/drop_caches`） |
| FEMU Level 2 | ❌ 要不到權限 | **v4 不需要它**——§9 的所有 arm 皆不依賴 FEMU-L2 |

### 11.2 規則

1. **正文的指令區塊一律視為 canonical 形式（規範參數，不是可執行腳本）。** 凡標 🔧 者，實際執行走 `workload_fixed/tools/` 下的對應包裝。
2. **agent 不得因為 canonical 指令跑不動就改變 spec 的參數語意。** 換的是呼叫方式，不是 `-p` 的值。
3. **manifest 必須記錄實際的呼叫方式**（java classpath / jar 版本 / commit hash），因為 §2.4 的 reproducibility 主張建立在「trace 檔就是 seed」上，而 trace 是誰產的必須可查。
4. 本節與 `workload_fixed/tools/README` 若有出入，**以實測為準**，並回頭更新本節。

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
| §2.5 | 選項 (c) WITHOUT ROWID 被評「勉強」後擱置 | (c) 對目標 B 是唯一可行解 → **§4.5 YR arm**，Tier 1（*此列的 fanout 38 / 骨架 32MB 已被 v4 否決，見 A.3*） | 🟠 |
| （無） | — | **YR-P cache-pressure 軸** + §4.5.3 公平性五規則 + §10.4 sanity check | 🟠 |
| §-1.1 / §2.5 | 兩個空格（headline field size、YD/YE 方案）未填 | **§00 DECISIONS**：D1/D2/D3 CLOSED，D4–D6 OPEN 且集中列管；agent 常設規則杜絕反覆詢問 | 🟠 流程 |
| §8 | settling point 只有 convergence 定義 | **fixed-horizon ABC fallback（D6）**，兩定義並報 | 🟠 YR-P 下 convergence 可能不觸發 |
| §5 | — | 新增 `rho_measured` / `cache_config` / `R_ratio` / `trees_touched` 檢查 | 🟡 |
| §6 | 純 forward-looking | 進度標記（步驟 1 ✅），新增步驟 2.5（YR 原型） | 🟡 |
| §9 | 未含 YR | +Tier 1r / 1r'（~84 runs，DB 1.2GB 的還原成本明列） | 🟡 |

### A.3 v3 → v4

| v3 位置 | v3 說法 | v4 修正 | 嚴重度 |
|---|---|---|---|
| §4.5.1 | WITHOUT ROWID 的 interior cell ≈ 4 + varint + **key**(100B) ≈ 106B → f ≈ 38 | **錯。index B-tree 的 interior cell 存完整 key payload = 整列（key+value）。** 實測 f = **16**、骨架 88MB、ρ = 5.9%。簽名：f ≈ rows/leaf | 🔴 §10.3 閘擋下 |
| §4.5 前提 | 「用寬 key 壓低 f、同時 value 保持 126B 對齊 headline」 | **物理上不可能同時成立**：f = U/整列寬，f 與 leaf payload 是同一個 cell | 🔴 |
| §3.5 | ρ ≤ ~1%（僅針對「對齊配置」） | **升級為分割定理**：rowid table 的 interior cell 與列寬無關（對照組實測 f=392 = 舊 DB 的 392）→ **ρ ≲ 0.27% 對整類 schema 恆成立（p=1 下界 0.25%），無配置可逃** | 🔴 這是論文主結論 |
| §3.5 | 無全域上界 | **新增 overflow 地板**：SQLite 強制 index entry ≤ 1/4 page → 最小 f = 4 → **ρ ≤ 20%，SQLite 全域** | 🟠 |
| §4.5.1 | `inflate()` 保序 key 膨脹 + 2 個單元測試 | **✂️ 整組刪除**。f 由整列寬決定，key 膨脹與加大 value 等價，但後者只掃 value 寬度（builder 施加、value 在 YCSB 信封外，§4.5.1）→ 少一份自訂映射、少一個紅線疑慮 | 🟠 淨簡化 |
| §4.5 / §-1.4 | YR = 單點（f=38），預測「效應 ∈ (0, 2.6%]」 | **升級為 ρ-sweep**：固定 leaf 頁數、掃 W（ρ 與 N 正交）→ 4 點（ρ 2.9–7.7%，p=1 下界），預測改為 **benefit = α·`rho_measured` 的過原點迴歸**（自變數 = 實測 ρ_窗口，§3.5.1）。檢定律的**函數形式**而非存在性；低 ρ 點兼作 negative control 與噪音門檻 | 🔴 contribution 升級 |
| §7 | 「YR 的 fanout 是人為壓低的，不代表典型部署」 | **自我批評過重**。SQLite 官方建議 WITHOUT ROWID 單列 < page/20（4KiB → ~200B），YR 的 R3/R4 正好踩過線 → **YR 是官方明文警告的配置，不是人造 strawman**；適用條件可對映官方文件 | 🟠 論文敘述強化 |
| §-1.4 | (d−1)/d 用 depth 5/7 | **d 不可信**：dbstat 腳本 +2 系統性偏移（`sqlite_schema` 1 leaf 報 depth 3），YR 原型腳本偏移不同 → **D8 只擋 §-1.4 的 YR-P (d−1)/d 列**（headline + YR sweep 已簽） | 🟠 會讓承諾數字朝有利方向失真 |
| §2 / §5.1 / §10 | canonical 指令（`bin/ycsb` / `mvn` / `sqlite3`；`gcc dbstat` 自編路徑不需要） | **前三者本機不可用**（v2 有 🔧 註記，v3 漏掉；`gcc` 本身可用）→ **新增 §11 執行環境實況**；cgroup `MemoryMax` 由「可能」改為「實測確認」 | 🟠 會誤導照做的 agent |
| §00 | 決定即 CLOSED | **新增簽署規則**：agent 起草 = `DRAFT`，須研究者 git commit 才生效 | 🟡 |
| §9 | YR 84 runs | +42 runs（sweep 4 點）+ 3 個 1.2GB DB。**買到迴歸而非存在性檢定** | 🟡 成本 |

---

## 附錄 B：核心命題

> **公信力不來自 YCSB。**

v1 的隱含理論是「用公認 workload 就能取得公信力」。但如 §3.1 / §3.2 所示，YCSB 綁得沒你以為的緊——它只覆蓋 key 分佈，而 `fieldlength`、`zeropadding`、schema、load order、rowid mapping 每一個都影響 page layout，每一個都還是你選的。

真正的繩子是：

1. **§-1 預先承諾** —— 在看到結果之前把手綁起來
2. **§5 Tier 0 validator** —— 每個形容詞對應一個數字
3. **§3.5 天花板律 + 分割定理** —— 每個效益數字對照一個物理上界。量出超過上界的「好結果」不是驚喜，是 bug 警報
4. **§10 驗證閘（v4 新增的自覺）** —— **在花錢之前，讓 spec 有機會否決自己**

這四個都是你自己造的，而且是這份 spec 裡最好的部分。YCSB 只是第五條繩子。

### v4 的後記：制度第一次真的動了

v3 §4.5 的幾何是錯的。它沒有被 reviewer 抓到、沒有被 1.2GB DB 建完之後的困惑抓到、也沒有被「怎麼結果怪怪的」抓到——**它被 spec 自己在 §10.3 事先寫好的通過條件抓到，在花任何一分鐘算力之前。**

這件事比 v4 修正的任何一個數字都重要，因為它證明了三件事：

1. **§6「驗證優先」的排序是對的**（把驗證閘放在建 DB 之前，而不是之後）。
2. **預先寫下容忍區間**（「f ∈ [33,43]」）比預先寫下期望值有用得多——期望值只會讓你事後合理化，區間會讓你出局。
3. **附錄 B 的命題可以再推進一步**：公信力不只不來自 YCSB，也不來自「這份 spec 寫得很仔細」。v2 和 v3 都寫得很仔細，然後**兩次都栽在同一個直覺上**（「interior cell 只有 key」）。公信力只來自**能否決自己的機制**。

所以 v4 的規則加了一條，放在 §10 前言：**任何 fanout / 骨架 / depth 數字進入預先承諾之前，必須有實測背書。紙上外插只能當假設。** 這條規則的成本是幾個 200k rows 的原型，收益是不用重跑 486 個 run。