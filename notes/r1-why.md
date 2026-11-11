# 為什麼 benchmark_harness.c 設 `cache_size=0` 並把 `mmap_size` 設成檔案大小？

調查日期：2026-11-06。repo rev：`ae29344`。方法：`/pstack:why`，由 source control 與 Claude Docs 兩個 investigator 加一個 synthesizer 完成。

2026-11-10 補查 `paper/REVISION_NOTES.md` 與 `paper/main.tex`（paper submodule `17a79ca`，branch `vldb-revision`）。主 repo 在這期間沒有新 commit。補查結果見〈論文與 REVISION_NOTES 怎麼處理這兩個設定〉。

## 答案

原作者沒有寫下為什麼要這樣設。`mmap_size` 設成檔案大小，這個指示寫在 code 之前的計畫裡，但只說要這樣設、沒說原因。`cache_size=0` 在寫入當時找不到任何出處。目前能看到的理由，都是 7 週後由另一位作者補寫的說明，大多有 AI 協作，彼此是同一條相依的詮釋鏈。

不過，直接看 vendored 的 SQLite 原始碼可以確認：這組設定確實讓資料頁直接讀 OS page cache、不在 heap 留副本，只有三個例外。

## 程式碼

位置：`pipeline/engine/benchmark_harness/benchmark_harness.c`。

- 1053–1076 `sqlite_open_if_needed()`：
  - 1071–1073 設 `PRAGMA mmap_size = opts->mmap_size`。
  - 1074 設 `PRAGMA cache_size = 0;`。
- 1357–1358：`opts.mmap_size` 為 0 時，預設改成 `dbmap.file_size`。
- harness 另外自己用 `mmap(PROT_READ, MAP_SHARED)` 映射 DB，再用 `mincore` / `madvise` 量 residency。
- 預設 `--sqlite-open-timing before-cold`（196 行）：SQLite 連線在 drop-caches 之前就已經打開。
- 1061–1080 全部出自 `3456e068`（Liu-yen-fu，2026-05-01，"Add files via upload"，PR #2，沒有 review 意見）。之後沒有人改過這幾行；`93d6fdd` 只是改名。

## 找到的證據

### `mmap_size = 檔案大小`：有出處，沒有理由

- **計畫早就寫了這個設定。** 2026-04-20 的 16 週計畫比 harness 早 11 天。
  - `1a0d8c7:16week_plan.jsx:149`：「開啟 DB 時設定 PRAGMA mmap_size = <file_size>」
  - `:152`：「同時用 perf stat -e page-faults 觀察 page fault 數量」
  - `:87`：「精讀 https://www.sqlite.org/mmap.html」
- **計畫完全沒提 `cache_size=0`。** 它反而在 `:334` 把 `PRAGMA cache_size` 當成對照組：「比較：跟每個 process 用 PRAGMA cache_size 開獨立 buffer pool 的差異」。
- **原始 commit 也沒說明理由。** `3456e068:BENCHMARK_HARNESS.md` 只寫了預設值：「| --mmap-size | database file size | SQLite PRAGMA mmap_size 目標值 |」。header 註解（`3456e068:benchmark_harness.c:11-13`）只說工具的用途："observe and cool the database file's page-cache residency … recording per-operation latency and page faults"。

### `cache_size=0`：只有事後補寫的理由

- **第一次寫出理由的文件。** `c3b1278:IMPLEMENTATION_PIPELINES.md:59-60`（sj，2026-06-22，Co-Authored-By Claude）的凍結清單：
  - F1 `PRAGMA cache_size=0`：「不讓 SQLite 在 heap 偷存頁、繞過冷啟動（已寫死 :951）」
  - F2 `mmap_size=檔案大小`：「讀走 mmap → OS page cache → drop-caches 管得到、prefetch 暖同一份（已寫死 :948）」

  「已寫死」表示寫的人是在解讀既有的 code，不是在記錄當初的決定。這份文件後來在 `85883dc` 被刪除。
- **同一條說法的其他副本**（不是彼此獨立的佐證）：
  - `legacy/P0_HANDOFF.md:18`（AI handoff）
  - `static_experiment-copy1/EXPERIMENT_CONDITIONS.md:95`（不在 git 裡，作者不明）：「關閉 SQLite 自有 cache,使冷啟動成本完全反映在 OS page fault 上」
  - REPORT.md：`dbc8b1d`、`8a24f77`、`ad74cdb`
- **OpenWhisk 移植版刻意走不同的讀取路徑。** `deployment/openwhisk/build_artifact_manifest.py:919-927`（`b01e3c1`，sj，2026-07-14）：
  - `cache_size=0` "matches benchmark_harness.c (the OS page cache is the only data cache)"
  - `mmap_size=0` 是 "deliberate departure … a persistent SQLite mmap pins the pages it traverses, which blocks non-root re-eviction"

## SQLite 3.46.1 實際上怎麼做

依據 vendored 的 `pipeline/engine/benchmark_harness/sqlite3.c`，直接看原始碼確認，信心高。

- **`cache_size=0` 不保留任何頁。**
  - `numberOfCachePages()`（約 54495 行）回傳 0，`pcache1Cachesize()`（55970 行）把 `nMax` 和 `nMaxPage` 設為 0。
  - `pcache1Unpin()`（約 56252 行）：頁一 unpin 就呼叫 `pcache1RemoveFromHash(pPage, 1)` 釋放，不進 LRU。
  - `nMin = 10`（55949 行）只限制同時能 pin 幾頁，不是保底保留。
- **開了 mmap 之後，唯讀頁不會複製進 heap。**
  - `pagerFixMaplimit()`（60636 行）在 `szMmap>0` 時打開 `bUseFetch`。
  - `getPageMMap()`（62721 行）透過 `unixFetch()`（43798 行）讀頁，回傳的指標直接指向 `MAP_SHARED` 映射。
  - `pagerAcquireMapPage()`（61154 行）只 malloc 一個 `PgHdr`，`pData` 直接指向映射本身。
- **三個例外會用 pread 讀進 heap**（unpin 後立刻釋放）：
  1. page 1。
  2. 檔案的最後一頁：mmap 長度最多等於 `st_size`，而 `unixFetch` 要多 256 bytes 餘量。
  3. WAL 裡有 frame 的頁。
- **交易進行中被 pin 住的頁會暫時留在 heap**，例如 cursor 從 root 到 leaf 的路徑。
- **mmap 有上限。** `SQLITE_MAX_MMAP_SIZE` 是 `0x7fff0000`，約 2 GiB（15113 行）。目前的 DB 約 103 MiB，1gb 版本約 1 GiB，都在範圍內。

## 實測：before-cold open 會不會讓 drop 清不乾淨？

harness 預設在 drop-caches 之前就打開 SQLite，所以 drop 的時候 SQLite 已經映射著檔案。2026-11-06 我用 verify skill 跑了一次 A/orig/2d（1 rep）。harness log 顯示：

- `drop_caches_script_result=success`
- drop 之後，hotset 量到 `verify_cold_pct=0.0 resident=0/18`
- 送完 hotset 後，整個 DB 只有 35/26331 頁在記憶體裡

所以至少在這次實跑中，SQLite 的映射沒有擋住 drop。這是單次觀察，kernel 層面的行為沒有另外驗證。

## 論文與 REVISION_NOTES 怎麼處理這兩個設定

`paper/REVISION_NOTES.md` 沒有交代這兩個 pragma 的理由。它的作者是 Yun-Chih Chen，寫於 2026-09-18 至 09-24；最後一次修改是 `f9fce90`。`main.tex` 裡也找不到 `cache_size`、`mmap_size` 或 `pager` 這幾個字。和本題相關的有四點：

- **README 那段多 process 共用的說法，已經從論文拿掉。** REVISION_NOTES:18 把「cadence 與 shared cache」列為「刪除或降級的內容」；§五 也說 cadence 是「確定刪除」。所以 README:27 的「PRAGMA mmap_size 開 MAP_SHARED 後，一個 process prefetch，所有共用同一 DB 的 process 都受惠」不是論文的主張。它的來源是 `a0ab189` 的 multiprocess 實驗，而那個實驗的 residency 測試用的是原生 mmap，沒經過 SQLite。這段論述沒有任何一處成為 `mmap_size` 的理由。
- **論文定義的量測狀態，其實依賴這兩個設定，但沒有寫出來。** `main.tex:134`（§2.1）："The SQLite handle, prepared statements, and virtual-memory mapping remain available, but the database pages are absent from the operating system page cache." 要讓「頁不在 page cache」等於「頁是冷的」，前提是 SQLite 沒有私有的 pager cache（`cache_size=0`），而且讀取走 OS page cache（mmap）。§2.1 沒有提到這兩個 pragma。
- **cache 清除方式的待辦（REVISION_NOTES 待辦 10，§3.4 TODO）已經寫進正文。** 這條 TODO 在 `46f9433`（sj，2026-10-13）處理掉，現在是 `main.tex:241`：先對 mapping 做 `MADV_COLD`、`MADV_PAGEOUT`、`MADV_DONTNEED`，再呼叫 setuid-root helper 寫 `/proc/sys/vm/drop_caches`，並以 mincore 驗證「post-reset residency was 0% in every repetition」。我核對過 code：`--cold-advice dontneed` 確實依序做這三步（`benchmark_harness.c:152`、`849-871`），和論文描述一致。這裡和 `mmap_size` 有關聯：OpenWhisk 版改用 `mmap_size=0` 的理由，正是 SQLite 常駐的 mmap 會讓非 root 環境無法重新清掉頁（`build_artifact_manifest.py:919-927`）。所以這套 harness 必須仰賴 root helper，至少部分原因在 `mmap_size=檔案大小`。這是推論，REVISION_NOTES 和論文都沒有把兩者連起來。
- **MAP_POPULATE baseline（待辦 3）** 已經以 `Populate` 這一列進了 Table 2（`main.tex:193`、`203`）。它和 harness 的 `mmap_size` 無關。

## 推論與假說

- **[推論] `mmap_size=檔案大小` 很可能是照計畫第 5 週實作的。** 計畫的用詞和 1357 行的預設值一致，時間也在 code 之前。
- **[推論] `cache_size=0` 的效果符合 header 寫的量測目標。** 它讓 page fault 和 mincore 成為唯一的快取訊號。但沒有任何當時的文字證明這就是動機。
- **H1：量測隔離**（F1/F2 的說法）。程式機制和 header 都支持，但支持它的文字全是事後寫的。
- **H2：配合「多 process 共用 OS page cache」的研究主軸。** 計畫 `:334` 與 `a0ab189 multiprocess/MULTIPROCESS_MMAP.md`（對照組是 "private buffer pool (mmap_size=0, cache_size=N)"）支持這個說法。但那是另一個實驗，不是 harness 本身，而且它的 residency 測試用的是原生 mmap，沒經過 SQLite。
- **H3：mmap 比較快**（只針對 mmap）。只有計畫引用 sqlite.org/mmap.html 這一點，沒有任何文字提到效能。
- **`cache_size=0` 不是隨手的習慣。** 同一位作者在非量測用的連線上設過 `cache_size=-200000`（`prefetch_churn/sqlite_prefetch_churn_experiment.py:530`，`8d33846`）。

### 互相矛盾的說法

- `workloads_refined/ycsb_migration_spec_v3.md:494` 和 `v4.md:538`（`13e0bd5`）推論「SQLite 自身的 pager cache（預設 cache_size ≈ 2MB）」會保留 interior skeleton。這和 harness 的 `cache_size=0` 衝突。依上面的機制，交易和交易之間 interior 頁不會被保留。
- REPORT.md:150 說「process 以下的每一層 software cache 在每次量測前都歸零」，但 :456 又把 `cache_size=0` 歸在 warm-process 設定下。
- `deployment/openwhisk/action/session.py:11-12` 說 warm handle 用 `mmap_size=<file size>`，但同一個 commit 的 manifest 和 `session.py:399` 用的是 0。

## 不知道的部分

- Liu-yen-fu 本人的理由：git、PR #2、他附的文件裡都沒有。
- `cache_size=0` 是誰、什麼時候提的：計畫沒提，2026-06-18 之前的文件也都沒提。
- 2026-04-20 到 05-01 之間的團隊聊天紀錄：沒有對應的 MCP。
- PR #3–#28 的 review 意見：這台機器沒裝 `gh`。
- T210 的 review briefing（`cos/briefings/2026-11-05-sqlite-paper-vldb-review/`）：不在 repo 裡，也不在 claude.ai 的 artifact 裡。
- 當初是否知道 page 1 與最後一頁會走 pread：沒有任何紀錄。

## Sources Consulted

- **Source control**：
  - blame，以及這些 commit：`3456e068`、`93d6fdd`、`1a0d8c7`、`c3b1278`、`dbc8b1d`、`8a24f77`、`ad74cdb`、`691bd6b`、`a0ab189`、`b01e3c1`/`d192dbd`、`13e0bd5`、`8d33846`、`85883dc`。
  - PR #2（透過 WebFetch）、sibling clone、vendored `sqlite3.c`。
  - 這兩個 pragma 旁邊沒有任何註解。
  - 2026-11-10 補查：`paper/REVISION_NOTES.md`（全文）、`paper/main.tex`（grep `pager|cache_size|mmap|drop_cache|privileged|page cache`，並查了 §3.4 TODO 的 `git log -L`），以及 `README.md:27`。都沒有新的原始理由。
- **Long-form docs（Claude Docs）**：8 份 artifact，沒有一份和這個專案相關。
- **Issue tracker、聊天、observability、error tracking、analytics**：這個環境沒有對應的 MCP，所以沒查，算是缺口。

## 信心

- `mmap_size` 的出處有直接證據，但它的理由沒有。
- `cache_size=0` 的原始意圖查不到。現有的理由是同一條事後、由 AI 協作寫成的詮釋鏈。
- 程式機制是直接看原始碼確認的，信心高。

## 對 VLDB revision 的建議

- **Preserve**：
  - 保留 F1/F2 的值。改任一項都要整個矩陣重跑（`c3b1278` §3.0）。
  - 保留 `cold_pct` / `delivery_pct` 的 mincore 檢查，它是實際量測上的防線。
- **Change**：
  - 論文裡把這兩個 pragma 寫成方法論上的選擇，用上面的程式機制來論證，不要說成是原作者的意圖。最自然的位置是 §2.1（`main.tex:134`）的狀態定義：那裡說 handle 與 mapping 保留、頁不在 page cache，但沒說 SQLite 的 pager cache 是關掉的。
  - 替 C harness 補一個「pager cache 沒有在供應查詢」的測試。目前只有 OpenWhisk bridge 在 `mmap_size=0` 下有這個測試（`test_pager_cache_not_serving`）。
- **Avoid**：
  - 不加限定地說「所有 software cache 都歸零」。page 1、最後一頁、交易中被 pin 的頁仍會短暫留在 heap。
  - 沿用 ycsb spec v3/v4 裡「pager cache 保留 interior」的推論。
  - 把 `c3b1278` 當成原始意圖的證據。
- **Risk**：
  - DB 超過約 2 GiB 時，超出的部分會改用 pread。
  - OpenWhisk 用 `mmap_size=0`，讀取路徑和 C harness 不同，跨平台比較時要講清楚。
  - before-cold open 時 SQLite 映射與 drop_caches 的互動，目前只有單次實測支持，需要持續靠 `cold_pct` 數據佐證。
