# Overall Results — 策略 × Workload 結果矩陣

本檔列出**每個策略 × 每個 workload × 每個 layout 的 實驗結果**（對照
[overall_workloads.md](overall_workloads.md) 的 workload 定義）。

> 本檔所有數字來自 **統一 pipeline**（`run_experiment.py` 家族,全 cell `cold_pct`=0）。跨批只比相對量（impr% / 跨-seed Δ% / ratio），絕對 µs 不跨批逐格對（見「資料可比性」）。

### Canonical source precedence（tie-break 修正後）

**Replacement is atomic at `(workload, layout, strategy, seed)` scope**：修正後的 strategy 結果、它的 same-seed baseline、以及 machine anchor（`2f_slru`）**取自同一個 rerun batch**——不跨批拼裝。逐格 canonical 來源依下表優先序：

| cell 類型 | canonical source |
|---|---|
| A/B/C 主矩陣 · tie-break **未受影響** cells | `results/unified_v2/matrix` |
| tie-break **受影響** single-instantiation cells（(A,2e_K500)/(B,2e_K10)/(B,2e_K500)/(C,2e_K10)）| `results/tiebreak_fix/master` |
| tie-break **受影響** cross-seed cells（同上）| `results/tiebreak_fix/seeds` |
| **C_hit `2e_K10`**（tie-break 修正後）| `results/c_hit_v2` |
| **C_hit** 其他 arms（2d/2f_top14/learned，hotset 未變）| `results/c_hit` |
| C_mixed ablation + competitive（tie-break 修正後）| `results/ablation_comp_v2` |
| Z / N-K-sweep / RAM / churn / cadence / size | 各自原批（`results/{z,nsweep,ksweep,ram_pressure,cadence,size_1gb}`）|
| **舊 first-seen tie-break**（`gen_hotleaves` 修正前）| **archived, non-canonical**（`legacy_same_trace_first_seen_tiebreak`）|
> Workload D 是 churn generator,無自身 latency 結果。
>
> **Preprocessing 計入 e2e（兩個部署模型）**:preprocessing 拆成 **open(db)(冷開 DB ~200µs,per-layout 常數)**
> 與 **deliver(逐頁 madvise/pread,隨 hotset)**。`e2e_warm` = deliver+fq(warm-process/integrated,
> 重用既有 handle、不付冷 open;≈ static `effective_first_query`,**本研究主張**);`e2e_std` = open+deliver+fq
> (standalone warmer)。**2f_slru first-query 最低(−79~91%)但 deliver ~0.8–7ms 使 e2e 多半輸**;
> targeted prefetch(layers_5 / 2d / 2e_K10)deliver 小,**warm-process e2e 三 workload 皆改善**——普適贏面是 interior skeleton `2d`（robust ~−25~28%）;C(mixed)× 2e_K10 single-seed −75%、跨 seed −55% 雙峰、pure-hit C_hit −27~30%（scoped,見「C_hit」節）。
> 視覺化:[figures 13/14](figures/out/13_strategy_firstq_bars.png)。
> 完整執行覆蓋見 [IMPLEMENTATION_PIPELINES.md §3.8](IMPLEMENTATION_PIPELINES.md)。

---

## 資料可比性（先讀）— 跨表/策略/workload 怎麼比才對

各批資料**在不同日期、不同機器狀態下量測**。用 machine-independent 的 `2f_slru` first-query 當錨點
(它載整個 working set,first-q 只看當下 CPU 狀態,與 workload 無關)可看出至少 **4 個狀態群**:

| 來源 | 日期 | `2f_slru` 錨點 | 狀態群 |
|---|---|--:|---|
| `nsweep` / `nsweep_dense` / `ksweep` / `ram20m` | 06-22 | ~110µs | ① 較快 |
| `z` | 06-23 | 119µs | ② 中間 |
| **`main`(master)** / `seeds/seed01–10` | 06-24 / 27 | 126–127µs | ③ 基準 |
| `size_1gb` / `seeds_1gb` | 06-28 | 96–98µs | ④ 最快 |

**規則:**
- ✅ **相對量跨任何表/策略/workload 都可比** —— `impr%`(相對同批 baseline)、跨-seed `Δ% + CI`、RAM `ratio`、
  churn 各 checkpoint 演化。**本報告所有結論都建立在相對量上,不受機器狀態影響。**
- ✅ **絕對 µs 只在「同狀態群內」可比** —— 例:`main`↔`seeds`(群③同尺度,故跨-seed 對 master 比對有效);
  `size_1gb`↔`seeds_1gb`(群④);1gb 的 100MB 對照基準用**同批 `orig` 列**(見 DB 尺寸 scaling 章)。
- ⚠️ **絕對 µs 跨群勿逐格對** —— 同一個量測 `layers_92 A/orig` 在 master(群③)= **393µs**、在 nsweep(群①)= **333µs**,
  15% 差**純機器狀態**;`z`(群②)整列比 A/B/C(群③)低 ~6%;`size_1gb`(群④)比 master 低 ~25%。這些都不是真效應。

> **特別注意 RAM-pressure 表**:其 ratio 必須用**同 session 的 unconfined** 當分母。表上 ~1.0 是當年對「同期(06-22)unconfined」算的(正確);
> 但**現在的 `results/main` 是 06-24 重跑(群③,慢 ~15%)**,若拿它當分母重算會得 ~0.85——那 0.85 是機器狀態假象,不是記憶體壓力效應。
> (`figures/06_ram_pressure_heatmap.py` 註解寫「unlimited = results/main」已過時,同理。)

---

<!-- MASTER-RESULTS-START -->
## master batch 結果

> **canonical v2 批**:由 `run_experiment.py` 一次跑齊 A/B/C × {orig, vacuum, ta} × {baseline, layers_5/92, 2d, 2e_K10/40/92/500, 2f_slru} × {async, pread},async / pread / baseline 各 **n=10**(丟 warmup)、rep-major、全機 drop-caches、in-harness `--verify-hotset`、釘核升頻、ra=128。**全 cell `cold_pct`=0**。與 `results/baselines_v2`、`results/aging_v2` 背靠背同 session、共享 `2f_slru` 錨點。原始檔:[`results/unified_v2/matrix/summary.csv`](results/unified_v2/matrix/summary.csv)。
> `fq` = first-query median µs;`impr%` = async 相對該 (workload,layout) baseline;`e2e_std` = open+deliver+fq(standalone warmer);`e2e_warm` = deliver+fq(warm-process,≈static,本研究主張);`deliv%` = async delivery_pct;`oracle` = pread 模式 fq(可達上界)。
> 此為 A/B/C 的詳表(含 delivery_pct/oracle);下方「全維度數據」涵蓋全 workload(含 Z)× layout × 策略 + N/K-sweep + RAM + churn + cadence。

### Workload A (Zipfian)

| layout | strategy | fq_async | impr% | deliv% | e2e_std | e2e_warm | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|--:|
| **orig** | baseline | **523** | — | — | 523 | 523 | — |
| orig | layers_5 | 382 | 27% | 100 | 679 | 453 | 187 |
| orig | layers_92 | 369 | 30% | 100 | 795 | 570 | 187 |
| orig | 2d | 364 | 30% | 100 | 678 | 452 | 185 |
| orig | 2e_K10 | 363 | 31% | 100 | 694 | 464 | 187 |
| orig | 2e_K500 | 190 | 64% | 100 | 1311 | 1083 | 196 |
| orig | 2f_slru | 108 | 79% | 100 | 7552 | 7324 | 110 |
| **vacuum** | baseline | **707** | — | — | 707 | 707 | — |
| vacuum | layers_5 | 553 | 22% | 100 | 854 | 623 | 186 |
| vacuum | layers_92 | 557 | 21% | 100 | 977 | 747 | 190 |
| vacuum | 2d | 555 | 22% | 100 | 863 | 633 | 190 |
| vacuum | 2e_K10 | 556 | 21% | 100 | 879 | 648 | 189 |
| vacuum | 2e_K500 | 187 | 74% | 27 | 1261 | 1032 | 204 |
| vacuum | 2f_slru | 103 | 85% | 100 | 5875 | 5677 | 106 |
| **ta** | baseline | **658** | — | — | 658 | 658 | — |
| ta | layers_5 | 501 | 24% | 100 | 764 | 569 | 486 |
| ta | layers_92 | 451 | 32% | 100 | 823 | 632 | 187 |
| ta | 2d | 453 | 31% | 72 | 762 | 568 | 196 |
| ta | 2e_K10 | 390 | 41% | 77 | 753 | 523 | 198 |
| ta | 2e_K500 | 197 | 70% | 27 | 1263 | 1034 | 195 |
| ta | 2f_slru | 109 | 84% | 100 | 7595 | 7365 | 107 |

### Workload B (Uniform)

| layout | strategy | fq_async | impr% | deliv% | e2e_std | e2e_warm | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|--:|
| **orig** | baseline | **749** | — | — | 749 | 749 | — |
| orig | layers_5 | 422 | 44% | 100 | 722 | 494 | 412 |
| orig | layers_92 | 417 | 44% | 100 | 856 | 626 | 421 |
| orig | 2d | 421 | 44% | 100 | 740 | 509 | 422 |
| orig | 2e_K10 | 421 | 44% | 100 | 765 | 528 | 419 |
| orig | 2e_K500 | 461 | 38% | 100 | 1576 | 1349 | 469 |
| orig | 2f_slru | 107 | 86% | 100 | 7561 | 7328 | 109 |
| **vacuum** | baseline | **1024** | — | — | 1024 | 1024 | — |
| vacuum | layers_5 | 510 | 50% | 100 | 814 | 579 | 515 |
| vacuum | layers_92 | 516 | 50% | 100 | 940 | 707 | 515 |
| vacuum | 2d | 509 | 50% | 100 | 820 | 588 | 513 |
| vacuum | 2e_K10 | 516 | 50% | 100 | 843 | 608 | 513 |
| vacuum | 2e_K500 | 405 | 60% | 29 | 1402 | 1168 | 473 |
| vacuum | 2f_slru | 104 | 90% | 100 | 5921 | 5688 | 105 |
| **ta** | baseline | **770** | — | — | 770 | 770 | — |
| ta | layers_5 | 605 | 21% | 100 | 908 | 675 | 593 |
| ta | layers_92 | 585 | 24% | 100 | 1003 | 767 | 595 |
| ta | 2d | 587 | 24% | 78 | 935 | 701 | 569 |
| ta | 2e_K10 | 592 | 23% | 80 | 951 | 719 | 597 |
| ta | 2e_K500 | 608 | 21% | 38 | 1633 | 1403 | 548 |
| ta | 2f_slru | 106 | 86% | 100 | 7596 | 7359 | 111 |

### Workload C (C_mixed) — Mixed Tail-boundary Lookup (~50% not-found)

| layout | strategy | fq_async | impr% | deliv% | e2e_std | e2e_warm | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|--:|
| **orig** | baseline | **1087** | — | — | 1087 | 1087 | — |
| orig | layers_5 | 1048 | 4% | 100 | 1352 | 1120 | 1050 |
| orig | layers_92 | 669 | 38% | 100 | 1101 | 868 | 669 |
| orig | 2d | 664 | 39% | 100 | 969 | 735 | 648 |
| orig | 2e_K10 | 186 | 83% | 100 | 501 | 268 | 186 |
| orig | 2e_K500 | 188 | 83% | 67 | 915 | 680 | 189 |
| orig | 2f_slru | 102 | 91% | 100 | 1196 | 962 | 101 |
| **vacuum** | baseline | **999** | — | — | 999 | 999 | — |
| vacuum | layers_5 | 880 | 12% | 100 | 1185 | 950 | 871 |
| vacuum | layers_92 | 494 | 50% | 100 | 913 | 680 | 481 |
| vacuum | 2d | 484 | 52% | 100 | 789 | 554 | 497 |
| vacuum | 2e_K10 | 185 | 81% | 100 | 502 | 268 | 187 |
| vacuum | 2e_K500 | 189 | 81% | 60 | 918 | 682 | 188 |
| vacuum | 2f_slru | 103 | 90% | 100 | 1014 | 784 | 104 |
| **ta** | baseline | **867** | — | — | 867 | 867 | — |
| ta | layers_5 | 835 | 4% | 100 | 1134 | 904 | 841 |
| ta | layers_92 | 475 | 45% | 100 | 875 | 644 | 489 |
| ta | 2d | 482 | 44% | 65 | 829 | 600 | 455 |
| ta | 2e_K10 | 187 | 78% | 100 | 545 | 319 | 188 |
| ta | 2e_K500 | 189 | 78% | 100 | 1079 | 850 | 190 |
| ta | 2f_slru | 102 | 88% | 100 | 1229 | 1000 | 102 |

**讀法**:① first-query 最低一律是 **2f_slru**(載整個 working set),但其 deliver(A/B ~7ms、C ~0.76ms)使 `e2e` 多半輸——除 C 外兩個 e2e 模型都超 baseline。② **layers_5 / 2d / 2e_K10** 用極少 syscall:`e2e_warm`(= deliver+fq,warm-process/integrated,本研究主張)在三個 workload 都改善(A −11~14%、B −29~34%、**C × 2e_K10 −75% / 268µs**);`e2e_std`(= open+deliver+fq,standalone warmer)則在快 workload 因 ~230µs 冷 open 而變差。③ 兩個 e2e 模型唯一差是冷 open(db):**median ~232µs、跨 72 cell 的 open_us_median stdev ~10µs、p95 ~235µs**,逐 strategy 與逐 layout 皆 ~230µs → **strategy/layout 無關的 common-mode 固定成本**,非 prefetch 獨有稅。把 baseline 也放上 standalone 基準(`baseline+open`)後 open 兩邊相消、`e2e_std` 排序重現 `e2e_warm` verdict(如 A layers_5 對 base+open **−10%**、對照 e2e_warm −14%);快 workload 在 standalone 變差是「prefetch 省下的 first-query 不足以額外 cover 它自己那次 open」,而非 open 偏袒 baseline。詳見 REPORT §5.5.1–§5.5.2。④ `oracle` 欄是同步 pread 的可達下界。
<!-- MASTER-RESULTS-END -->

---

## 全維度數據

> 本節為 **統一 pipeline**(`run_experiment.py` 家族 → `results/main*/`,全 cell `cold_pct`=0)的全 workload(含 **Z**)× layout × 策略 + N/K-sweep + RAM + churn + cadence 彙整;上方「master batch 結果」為 A/B/C 含 delivery_pct/oracle 的詳表。

## 全策略 × layout × workload（async first-query / e2e µs,median）

> baseline = no-prefetch;此處 cell = first-query µs (impr% 相對該 (workload,layout) baseline)。e2e 兩模型(`e2e_std`/`e2e_warm`)見上方「master batch 結果」詳表。
> 來源 [`results/unified_v2/matrix/summary.csv`](results/unified_v2/matrix/summary.csv)(A/B/C,canonical v2)+ [`results/z/`](results/z/summary.csv)(Z,原批,跨批只比相對量)。

### Workload A

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 523 | 382 (−27%) | 369 (−30%) | 364 (−30%) | 363 (−31%) | 190 (−64%) | 108 (−79%) |
| vacuum (1b) | 707 | 553 (−22%) | 557 (−21%) | 555 (−22%) | 556 (−21%) | 187 (−74%) | 103 (−85%) |
| ta (1c) | 658 | 501 (−24%) | 451 (−32%) | 453 (−31%) | 390 (−41%) | 197 (−70%) | 109 (−84%) |

### Workload B

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 749 | 422 (−44%) | 417 (−44%) | 421 (−44%) | 421 (−44%) | 461 (−38%) | 107 (−86%) |
| vacuum (1b) | 1024 | 510 (−50%) | 516 (−50%) | 509 (−50%) | 516 (−50%) | 405 (−60%) | 104 (−90%) |
| ta (1c) | 770 | 605 (−21%) | 585 (−24%) | 587 (−24%) | 592 (−23%) | 608 (−21%) | 106 (−86%) |

### Workload C

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 1087 | 1048 (−4%) | 669 (−38%) | 664 (−39%) | 186 (−83%) | 188 (−83%) | 102 (−91%) |
| vacuum (1b) | 999 | 880 (−12%) | 494 (−50%) | 484 (−52%) | 185 (−81%) | 189 (−81%) | 103 (−90%) |
| ta (1c) | 867 | 835 (−4%) | 475 (−45%) | 482 (−44%) | 187 (−78%) | 189 (−78%) | 102 (−88%) |

### Workload Z

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 525 | 409 (−22%) | 383 (−27%) | 411 (−22%) | 203 (−61%) | 204 (−61%) | 119 (−77%) |
| vacuum (1b) | 705 | 570 (−19%) | 572 (−19%) | 571 (−19%) | 205 (−71%) | 203 (−71%) | 117 (−83%) |
| ta (1c) | 737 | 598 (−19%) | 460 (−38%) | 467 (−37%) | 203 (−72%) | 203 (−72%) | 117 (−84%) |

### 2f_slru first-q vs e2e（preprocessing trap）

| workload×layout | fq | open | deliver | e2e_std | e2e_warm | e2e_warm vs base |
|---|--:|--:|--:|--:|--:|--:|
| A/orig | 108 | 230 | 7217 | 7552 | 7324 | 14.0× |
| A/vacuum | 103 | 190 | 5573 | 5875 | 5677 | 8.0× |
| A/ta | 109 | 230 | 7260 | 7595 | 7365 | 11.2× |
| B/orig | 107 | 234 | 7221 | 7561 | 7328 | 9.8× |
| B/vacuum | 104 | 233 | 5584 | 5921 | 5688 | 5.6× |
| B/ta | 106 | 236 | 7252 | 7596 | 7359 | 9.6× |
| C/orig | 102 | 234 | 857 | 1196 | 962 | 0.9× |
| C/vacuum | 103 | 229 | 682 | 1014 | 784 | 0.8× |
| C/ta | 102 | 229 | 898 | 1229 | 1000 | 1.2× |

## layers_N sweep（clean,async first-q µs;N=0=baseline）

> 來源 [`results/nsweep_dense/`](results/nsweep_dense/summary.csv)。

### Workload A

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 505 | 663 | 639 | 662 | 334 | 333 | 331 | 331 | 302 | 331 | 334 | 335 | 327 | 332 | 333 |
| vacuum | 702 | 961 | 962 | 968 | 556 | 549 | 556 | 555 | 552 | 552 | 555 | 552 | 548 | 552 | 558 |
| ta | 681 | 894 | 866 | 856 | 496 | 498 | 498 | 498 | 490 | 482 | 470 | 459 | 489 | 464 | 426 |

### Workload B

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 728 | 696 | 703 | 692 | 380 | 385 | 382 | 382 | 385 | 379 | 390 | 379 | 383 | 387 | 382 |
| vacuum | 1023 | 916 | 919 | 916 | 507 | 503 | 511 | 510 | 508 | 507 | 531 | 511 | 515 | 508 | 519 |
| ta | 798 | 1004 | 999 | 933 | 603 | 603 | 603 | 603 | 598 | 590 | 579 | 565 | 596 | 570 | 582 |

### Workload C

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 1074 | 1018 | 1021 | 952 | 1017 | 1021 | 1015 | 1017 | 1019 | 1017 | 1016 | 1012 | 1009 | 1008 | 633 |
| vacuum | 983 | 859 | 902 | 895 | 897 | 891 | 898 | 901 | 897 | 896 | 894 | 895 | 866 | 495 | 504 |
| ta | 872 | 858 | 830 | 821 | 832 | 838 | 844 | 826 | 824 | 824 | 811 | 788 | 890 | 796 | 474 |

### Workload Z

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 509 | 676 | 676 | 638 | 356 | 335 | 381 | 368 | 364 | 364 | 339 | 381 | 376 | 364 | 382 |
| vacuum | 708 | 968 | 963 | 964 | 543 | 554 | 555 | 555 | 552 | 552 | 559 | 555 | 552 | 552 | 562 |
| ta | 728 | 901 | 835 | 905 | 575 | 571 | 576 | 575 | 572 | 562 | 552 | 558 | 564 | 540 | 438 |

## 2e K-sweep（async first-q µs;K=0=2d interior-only）

> 來源 [`results/ksweep/`](results/ksweep/summary.csv)。

### Workload A

| layout | K=0 | K=10 | K=40 | K=50 | K=92 | K=100 | K=500 |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 332 | 335 | 331 | 333 | 244 | 248 | 156 |
| vacuum | 560 | 557 | 554 | 552 | 348 | 348 | 188 |
| ta | 453 | 398 | 393 | 395 | 786 | 512 | 201 |

### Workload B

| layout | K=0 | K=10 | K=40 | K=50 | K=92 | K=100 | K=500 |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 385 | 385 | 381 | 387 | 383 | 382 | 429 |
| vacuum | 509 | 519 | 508 | 507 | 517 | 512 | 409 |
| ta | 590 | 595 | 596 | 593 | 593 | 592 | 611 |

### Workload C

| layout | K=0 | K=10 | K=40 | K=50 | K=92 | K=100 | K=500 |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 636 | 153 | 153 | 152 | 154 | 154 | 155 |
| vacuum | 493 | 187 | 185 | 186 | 185 | 187 | 188 |
| ta | 480 | 189 | 189 | 188 | 189 | 188 | 189 |

## 三槓桿 ablation（S1：勝利來自哪個 selection 槓桿）

> 來源 [`results/ablation/`](results/ablation/) + [`results/ablation_k500/`](results/ablation_k500/);跨-seed CI 由 [`tools/stats_uncertainty.py`](tools/stats_uncertainty.py) 產 [`results/ablation/uncertainty.csv`](results/ablation/uncertainty.csv)、表由 [`tools/ablation_table.py`](tools/ablation_table.py) 產。
> 把 2e_K 的 hotset 拆成兩個 selection 槓桿並加對照組,**同 layout、同一批跑、10-seed bootstrap 95% CI**。集合上 `2e_K = 2d ∪ leaf_freq_K`,故為 exact 分解。
> - **2d** = 只載 interior（page-type 槓桿 (ii)）
> - **leaf_freq_K** = 只載 top-K 熱 leaf（access-frequency 槓桿 (iii)，= 2e_K 扣 interior）
> - **leaf_rand_K** = 同型別(leaf_table)、同張數、但隨機抽的非熱 leaf（**對照組**:只差「有沒有照頻率挑」）
> - **2e_K** = interior ∪ 熱 leaf（合併 (ii)+(iii)）
>
> 關鍵讀法:**leaf_rand vs leaf_freq**——同 page-type、同張數,任何差距就是 access-frequency 訊號。

效應 = strategy median vs **同 seed baseline** median,跨 seed mean Δ%、bootstrap 95% CI（async arm）。

### layout orig

| workload | arm | 槓桿 | pages | first-q Δ% [CI] | e2e_warm Δ% [CI] |
|---|---|---|--:|---|---|
| A | 2d | (ii) page-type | 18 | −37% [−41,−34] robust | −27% [−31,−22] robust |
| A | **leaf_rand_K10** | 對照 | 10 | **+0% [−2,+3] tie** | +10% [+7,+12] robust |
| A | **leaf_freq_K10** | (iii) access-freq | 10 | **−13% [−26,−1] robust** | −4% [−18,+8] directional |
| A | 2e_K10 | 合併 | 28 | −50% [−63,−37] robust | −38% [−52,−25] robust |
| A | leaf_rand_K500 | 對照 | 500 | −3% [−7,+1] dir. | +99% [+87,+116] robust |
| A | leaf_freq_K500 | (iii) access-freq | 500 | +21% [−26,+98] dir. | +114% [+62,+191] robust |
| A | 2e_K500 | 合併 | 518 | −17% [−62,+58] dir. | +81% [+34,+151] robust |
| B | 2d | (ii) page-type | 18 | −36% [−43,−25] robust | −26% [−34,−14] robust |
| B | **leaf_rand_K10** | 對照 | 10 | **−2% [−3,−1] robust** | +7% [+6,+8] robust |
| B | **leaf_freq_K10** | (iii) access-freq | 10 | **−3% [−4,−2] robust** | +6% [+5,+7] robust |
| B | 2e_K10 | 合併 | 28 | −37% [−43,−28] robust | −26% [−32,−15] robust |
| C | 2d | (ii) page-type | 4 | −43% [−46,−41] robust | **−36% [−38,−34] robust** |
| C | **leaf_rand_K10** | 對照 | 10 | −1% [−2,+1] dir. | **+7% [+6,+10] robust(worse)** |
| C | **leaf_freq_K10** | (iii) access-freq | 10 | **−11% [−22,−0] robust** | **−3% [−14,+8] tie** |
| C | 2e_K10 | 合併 | 14 | **−63% [−75,−51] robust** | **−55% [−67,−42] robust·雙峰** |

> **C 列為 tie-break 修正後 `results/ablation_comp_v2`**（其餘 A/B 為 pre-fix 方向性對照）。**修正後 C 的 `leaf_freq_K10` 從舊 −40% 掉到 tie（−3%）**——舊值幾乎全是 first-op leakage（§C_hit / REPORT §6.2.8）。**結論反轉**：page-type(2d −36%) 是 robust 那根;access-frequency leaf-only 只是 tie(且 leaf-only 沒 interior path、只在首查是 not-found probe 時靠最右葉得利);隨機 leaf 淨變慢(+7%)。**競品同批**：C_mixed warm e2e `2e_K10 −54.5% [−66.6,−42.2]` vs 純頻率 `2f_top14 −55.2% [−66.8,−43.2]`／`2f_top28 −58.3%`——**CI 重疊、type-aware 沒有勝過 footprint-matched 頻率排名**（舊「2e 從未被打敗」撤回）。

### layout ta

| workload | arm | 槓桿 | pages | first-q Δ% [CI] | e2e_warm Δ% [CI] |
|---|---|---|--:|---|---|
| A | 2d | (ii) page-type | 43 | −37% [−44,−30] robust | −24% [−33,−16] robust |
| A | leaf_rand_K10 | 對照 | 10 | −2% [−3,+0] dir. | +8% [+6,+9] robust |
| A | leaf_freq_K10 | (iii) access-freq | 10 | −12% [−25,−0] robust | −3% [−17,+9] dir. |
| A | 2e_K10 | 合併 | 53 | −48% [−63,−34] robust | −34% [−51,−18] robust |
| A | 2e_K500 | 合併 | 543 | −51% [−66,−35] robust | +39% [+20,+57] robust |
| B | 2d | (ii) page-type | 40 | −36% [−44,−28] robust | −22% [−32,−13] robust |
| B | leaf_rand_K10 | 對照 | 10 | −1% [−3,+0] dir. | +8% [+6,+10] robust |
| B | leaf_freq_K10 | (iii) access-freq | 10 | −1% [−3,+3] dir. | +9% [+6,+13] robust |
| B | 2e_K10 | 合併 | 50 | −37% [−44,−30] robust | −22% [−31,−14] robust |
| C | 2d | (ii) page-type | 48 | −44% [−45,−43] robust | −31% [−32,−29] robust |
| C | leaf_rand_K10 | 對照 | 10 | −2% [−3,−1] robust | +7% [+5,+8] robust |
| C | leaf_freq_K10 | (iii) access-freq | 10 | −32% [−36,−29] robust | −24% [−28,−20] robust |
| C | 2e_K10 | 合併 | 58 | −80% [−81,−79] robust | −65% [−67,−64] robust |

**讀法總結:**
1. **C_mixed（tie-break 修正後，`ablation_comp_v2`）**:`leaf_rand_K10` +7%(對照,淨變慢)、`leaf_freq_K10` **−3% e2e_warm（tie）**——**修正後 access-frequency leaf-only 不再是 robust 訊號**（其舊 −40% 幾乎全是 first-op leakage）。robust 的那根是 **page-type `2d`（−36%）**;`2e_K10 −55%` 雙峰且**與 footprint-matched 純頻率 `2f_top14 −55%` 統計不可分**。**pre-fix 的「page-type-aware 命名對不上 headline / 38 點全是 access-frequency」結論已撤回。**
2. **B(uniform)**:無熱 leaf → `leaf_freq ≈ leaf_rand ≈ 0`,改善全由 **2d(interior, page-type, −36%)** 提供;2e_K10 ≈ 2d。
3. **A(zipfian)**:居中——leaf_freq_K10 −13%(robust、真有頻率訊號)但主力仍是 2d(−37%);**K=500 的 leaf-only 在 orig 反而 +21%(載 500 散落 leaf 的 deliver 成本壓過紅利)**,且所有 K500 的 `e2e_warm` 皆轉正(+39~114%,deliver ~0.8 ms 吃掉一切)——**access-frequency 的價值在於「小而準」(K=10),不在「多」**。
4. **layout 槓桿(orig→ta)**:只改 deliver 成本、不改 selection 故事;ta collocate interior 卻使 2d/2e 的 interior 集合變大(C 4→48 頁),warm e2e 反略遜(C 2e_K10 orig −73% vs ta −65%),呼應 §6.1「type-aware layout 非淨贏」。

→ 命名校正:本框架是 **type-aware(interior)＋ access-frequency-aware(hot leaf) 的複合 targeting**;page-type 扛 B/A 主力、access-frequency 解鎖 C headline。圖見 [figures/out/17_lever_ablation.png](figures/out/17_lever_ablation.png)。

## 競爭性 baseline（RR1 / S4：targeted vs 調校過的 ranked dump）

> 來源 [`results/competitive/`](results/competitive/)；`2f_topN` 由 [`strategies/access/runs/gen_freqdump.py`](strategies/access/runs/gen_freqdump.py) 產（replay 每筆 read 的 B+tree path 計次、按頻率排序 resident WS 取前 N，**不用 page-type**），CI 由 `tools/stats_uncertainty.py` 出。
> 問題：§5.5 的「targeted > dump」是「機制贏」還是只是「dump 少一點」？對照 `2f_topN`（tuned ranked partial dump）掃 footprint {14,28,100,500,full}，同 e2e accounting、10-seed CI。

跨 10 seed mean Δ% vs 同 seed baseline [95% CI]（async、orig；皆 robust）：

### first-query

| arm（footprint） | A | B | C |
|---|---:|---:|---:|
| 2e_K10（targeted, 14–28p） | −50 [−64,−38] | −35 [−42,−25] | **−63 [−75,−51]**† |
| 2f_top14 | −42 [−52,−35] | −36 [−43,−27] | **−64 [−76,−52]**† |
| 2f_top28 | −49 [−63,−37] | −37 [−43,−29] | **−69 [−79,−58]**† |
| 2f_top100 | −56 [−68,−44] | −41 [−53,−30] | −70 [−80,−60] |
| 2f_top500 | −16 [−62,+58] | −50 [−63,−37] | −90 [−90,−90] |
| 2f_slru（full） | −88 [−89,−86] | −89 [−90,−87] | −90 [−90,−90] |

### e2e_warm（本研究主張的部署模型）

| arm（footprint） | A | B | C |
|---|---:|---:|---:|
| **2e_K10（targeted, 14–28p）** | **−38 [−53,−25]** | **−24 [−31,−12]** | **−55 [−67,−42]**† |
| 2f_top14 | −33 [−43,−24] | −27 [−34,−16] | **−55 [−67,−43]**† |
| 2f_top28 | −37 [−52,−24] | −26 [−32,−16] | **−58 [−68,−47]**† |
| 2f_top100 | −32 [−45,−19] | −18 [−32,−4] | −52 [−60,−42] |
| 2f_top500 | **+81 [+34,+151]** | **+44 [+28,+60]** | −13 [−17,−8] |
| 2f_slru（full, ~4400p） | **+762 [+674,+899]** | **+730 [+644,+848]** | −12 [−17,−7] |

**讀法：**
1. **first-q 看 footprint 越大越低**（2f_slru 全載 → −88~90% 最低），但 **e2e_warm 越大越糟**（deliver 成本）——正是 §5.5「first-q ≠ e2e」的 trade-off。sweet spot 在小 footprint（N≈14–28）。
> † C 列為 **tie-break 修正後同批** `results/ablation_comp_v2`（2e_K10 + 2f_top14/28 背靠背）；A/B 列為 `results/competitive`（其 hotset 未受 tie-break 影響，見 precedence 表）。
2. **broad A/B**：tuned `2f_topN`（純頻率）在 matched footprint 下 e2e_warm **追平** `2e_K10`（CI 重疊）→ **page-type 非必要**，與 §5.4.1 ablation 一致。
3. **narrow C（修正後翻轉）**：`2e_K10` **−55%[−67,−42]** vs matched `2f_top14` **−55%[−67,−43]**——**CI 幾乎完全重疊、統計不可分**。舊表的「2e_K10 −72% robustly 勝 2f_top14 −57%」是 **first-op leakage** 造成的假象（§6.2.8）；修正後**沒有證據 type-aware `2e_K10` 勝過 footprint-matched 純頻率排名**。
4. **結論（修正後）**：`2e_K10` 與 tuned dump 在 A/B/C **全面相當**（無一格 robustly 勝）→ 機制歸因＝「**小 footprint + frequency ranking**」；page-type 的價值在**保證載入 interior skeleton**（robust、且是 leaf prefetch 生效的前提），**不是**在 C 上勝過純頻率。⚠ [figures/out/18_competitive_baseline.png] 為 pre-fix、待重生。

## Prior-art baselines v2（在同一 harness 重現 libprefetch / learned 核心）

> 資料 `results/baselines_v2`（canonical v2 批，A/B/C × orig，n=10；機器狀態見 [overall_strategies.md](overall_strategies.md) 錨點註記，絕對 µs 批內比）。方法見 repo `DESIGN_lp.md` / `DESIGN_learned.md`。**重現核心、剝除編排、非跑本尊。**

### libprefetch delivery-order（`lp_sorted` / `lp_shuf`）— Δdeliver（pread）

hotset 內容≡`2f_slru`（checksum 同），只差 warmer pread **遞送順序**。主度量 Δdeliver（fq 為 control、兩 arm 相等）。

| workload | deliver sorted µs | deliver shuf µs | **ratio** |
|---|---:|---:|---:|
| A | 17,953 | 280,281 | **15.6×** |
| B | 18,176 | 274,965 | **15.1×** |
| C | 2,775 | 29,175 | **10.5×** |

**NVMe 上 offset 排序遞送快 10–16×，效應全在 deliver、fq 不變**（診斷：兩 arm 讀相同裝置位元組 ~18MB,排除資料量差異;結果**與 sequential readahead + 隱式 coalescing 一致**,惟未取 block trace,不宣稱證明 coalescing 機制本身）。async(fadvise) 無此效應 → 專屬同步 pread（libprefetch 模型）。

### learned_markov（Chen-inspired 一階 Markov，held-out）— async fq / e2e_warm

**latency 只在單一 held-out fold**（test seed 1、train seeds 2..10）量測；**first-query coverage 另做跨 10 test seed 的 offline LOSO**（`results/loso/coverage.csv`，完整 10-fold latency 未跑）。hotset 取 finite-horizon expected-visit scores top-N；footprint 對齊 `2f_topN`。

| workload | learned_markov_14 | 2f_top14 | 2e_K10 |
|---|---:|---:|---:|
| A | 391 / 474 | 391 / 473 | 356 / 458 |
| B | 414 / 496 | 415 / 497 | 414 / 519 |
| C | 186 / 267 | 185 / 268 | 186 / 268 |

- **learned_markov 三 workload async fq/e2e 都 ≈ 2f_topN**（逐格幾乎相同）→ 此 transition baseline 冷啟動可用輸出落在頻率排名範圍。
- **C 的 caveat（key-range artifact）**：C 的 key range [590000,609999] **超出初始 DB 最大 key 600000 → 半數(9,999/20,000 unique)為 not-found 高 key**（每 seed ~50% miss）。miss 查詢全沿右緣落到**最右葉**、該葉吸收 ~50k miss 流量成為壓倒性單一 hot leaf；hit 查詢散在頻率相近的真葉。offline coverage 的雙峰因此拆解為 **miss first-op 5/5 覆蓋、hit first-op 1/5 覆蓋**（合計 **6/10**，`results/loso/coverage.csv`）。C leaf score 平（每真 key 恰 5 次），learned/2f_topN 統一 tie-break 選同 hotset → fq 必等（186≈185）。**coverage 只能預測、非量到 latency regime**（seed 1 hit+覆蓋實測 186；not-covered 的 ~660 interior 地板是**推導預測**，10-fold latency 未跑）。held-out precision：**C=100%、A/B=43%**。A/B first-op 0/10 覆蓋但 interior 撐住。**勿讀成「learned 在 C 有效」。**
- **Jaccard**（hotset 相似度、離線分析、非性能）：區分兩個 frequency 對象——**同一訓練資料** `J(learned_markov, frequency_train)=1.0`（traces 2–10 塌縮到 marginal frequency；此 3 層固定深度 tree 的觀測性質、非普遍宣稱）；**held-out 量測種子** `J(learned_markov, 2f_topN_test)` A/B N14 0.47/0.56、**C 1.0**（out-of-sample ranking 位移，C 因 leaf score 全平仍 =1.0）。兩者不矛盾。
- **Workload E 未支援**（scan 非 3-page episode，`gen_pageseq` fail-loud）。

### C_hit control — pure-hit tail（隔離 not-found 熱點，`results/c_hit/`，orig，10 seeds × 10 reps）

C_hit（`id∈[580001,600000]`、同 20k key-space、tail locality、uniform ×5，但**全部存在、0 not-found**）移除 C 的 ~50% not-found 最右葉超熱點。跨 seed warm-process e2e（vs same-seed baseline，皆 robust）：

| strategy | first-q | e2e_warm | 這是什麼 |
|---|--:|--:|---|
| 2d（interior only）| −36.6% | **−28.5%** [−34.9,−19.6] | interior skeleton |
| 2f_top14（freq, page tie-break）| −39.9% | **−30.6%** [−37.1,−22.4] | 真實 frequency |
| learned_markov_14（LOSO）| −38.2% | **−29.0%** [−36.1,−19.4] | 真實、無 leakage |
| **2e_K10（tie-break 修正後）**| −36.6% | **−27.2%** [−34.6,−17.7] | **== interior skeleton** |
| 2f_slru | −88.8% | +76.5% | deliver trap |

> `2e_K10` 為 tie-break 修正後 `results/c_hit_v2`；其餘列 `results/c_hit`（其 hotset 修正前後不變）。

- **C 的大效益是 not-found 驅動**：pure hit 上穩健效益是 **interior skeleton ~−28%**；frequency leaf 對 interior-only 幾乎不加分（uniform tail 無真實 leaf 熱點）。
- **`2e_K10` 的舊 −69.6% 是 first-op leakage，已修正**：leaf count 打平（~150）→ 舊 `gen_hotleaves` 的 `Counter.most_common` insertion-order tie-break → 最早出現的 K 葉 → 恰含被測 first-op（`gen_freqdump` 用 page-number tie-break 則不追）。10-fold coverage `results/loso/coverage_c_hit.csv`：first-op 覆蓋 **2e_K10(舊) 10/10 vs 2f_top14/learned/frequency 0/10**。改成 `(-count, pageno)` tie-break（commit `de4490f`）後 `2e_K10` = **−27.2%**（== 2d/learned）。
- **三個 access regime**：無真實 leaf 熱點（B、C_hit）→ interior skeleton ~−28%、frequency leaf 不加分；真實 skew（A）→ frequency leaf 加分（2e_K10 −36%）；key-range 集中（C mixed 的 not-found probe）→ 最右葉超熱 ~−70%。C（mixed）整體 = hit/miss first-op 混合 → 雙峰 −55% [−67,−43]（`results/tiebreak_fix`）。**page-type interior skeleton 才是普適 robust 贏面。** 完整 [`results/c_hit/FINDINGS.md`](results/c_hit/FINDINGS.md)。

## RAM-pressure（cgroup MemoryMax=20M / unlimited 比值,async first-q）

> 來源 [`results/ram20m/`](results/ram20m/summary.csv)(20M cgroup)÷ **同期(06-22)unconfined** baseline。比值近 1.0 → 壓力幾乎不影響。
> ⚠️ **20M cap 在 working set(A/B ≈ 17.3 MB)之上 → 沒有實質施壓**，故比值近 1.0。要看真壓力見下方「sub-working-set sweep」。
> ⚠️ 分母**必須是同 session** 的 unconfined run(群①);**勿** ÷ 現在的 `results/main`(06-24 重跑、群③、慢 ~15%)——那會得 ~0.85 的**機器狀態假象**,非壓力效應。詳見上方「資料可比性」。

| workload×layout | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|
| A/orig | 1.05 | 1.00 | 1.00 | 0.98 | 1.01 | 1.03 |
| A/vacuum | 1.00 | 1.00 | 1.01 | 1.00 | 1.00 | 1.00 |
| A/ta | 1.00 | 1.01 | 1.01 | 1.01 | 0.95 | 1.03 |
| B/orig | 1.01 | 1.00 | 1.01 | 1.00 | 1.00 | 1.07 |
| B/vacuum | 1.00 | 1.00 | 1.01 | 1.00 | 1.01 | 0.98 |
| B/ta | 1.01 | 1.01 | 1.01 | 1.00 | 1.00 | 1.02 |
| C/orig | 1.00 | 1.00 | 0.99 | 0.98 | 1.01 | 1.01 |
| C/vacuum | 1.00 | 1.00 | 1.00 | 1.01 | 1.00 | 1.00 |
| C/ta | 0.99 | 1.01 | 0.99 | 1.00 | 1.00 | 1.00 |

## RAM-pressure（sub-working-set sweep；cap 壓到 working set 以下）

> 來源 [`results/ram_pressure/`](results/ram_pressure/analysis.csv)(`tools/ram_pressure.sh`,seed 1,layout orig,async)。
> working set ≈ **A/B 17.3 MB、C 1.8 MB**。cap ladder `{∞,16M,12M,8M,6M}` = `{∞,0.92,0.69,0.46,0.35}×WS`。
> **量 `delivery_pct`**（prefetch 過的 page 在 first-query 前的 mincore 殘留率）+ first-q。可量測下限 ≈ 6M；4M 以下 cold gate 全排除。
> hotset 大小決定誰被壓到：2e_K10 ≈ 112 KB、2e_K500 ≈ 2.07 MB、**2f_slru ≈ 17.7 MB（＝整個 WS）**。

**delivery_pct（%，async,first-query 前 mincore 殘留率）**

| workload × strategy | ∞ | 16M (0.92×) | 12M (0.69×) | 8M (0.46×) | 6M (0.35×) |
|---|--:|--:|--:|--:|--:|
| A 2e_K10 | 100 | 100 | 100 | 100 | 100 |
| A 2e_K500 | 100 | 100 | 100 | 100 | 100 |
| **A 2f_slru** | 100 | **77.4** | **54.3** | **32.2** | **18.7** |
| B 2e_K10 | 100 | 100 | 100 | 100 | 100 |
| B 2e_K500 | 100 | 100 | 100 | 100 | 100 |
| **B 2f_slru** | 100 | **77.9** | **55.9** | **31.2** | **17.1** |

**first-query latency（µs,async）**

| workload × strategy | ∞ | 16M | 12M | 8M | 6M | baseline |
|---|--:|--:|--:|--:|--:|--:|
| A 2e_K10 | 402 | 362 | 353 | 372 | 357 | 502 |
| A 2e_K500 | 179 | 183 | 178 | 180 | 179 | 502 |
| **A 2f_slru** | **95** | **490** | **487** | **484** | **489** | 502 |
| B 2e_K10 | 408 | 411 | 405 | 404 | 406 | 723 |
| B 2e_K500 | 452 | 453 | 448 | 451 | 451 | 723 |
| **B 2f_slru** | **96** | **741** | **735** | **724** | **716** | 723 |

> 讀法：**targeted（2e_K10/2e_K500）delivery 全程 100%、first-q 全程平** → hotset 太小、reclaim 碰不到 → RAM-robust by construction。
> **2f_slru（dump＝整個 WS）delivery 隨 cap 線性塌（≈ cap/WS）**，且 first-q 一旦 delivery 跌破 100% 就**直跳回 baseline 並維持**（all-or-nothing,無 graceful degradation）。
> 即「小而準 > 大而全」在記憶體受限裝置上成立。圖見 `figures/out/16_ram_pressure_sweep.png`。

## Churn-evolution（layout orig,static t=0 hotset,first-q µs;CSV 另含 vacuum/ta）

> 來源 [`results/churn/churn_evolution.csv`](results/churn/churn_evolution.csv)。

### Workload A

| strategy | ck0 | ck1 | ck2 | ck3 | ck4 | ck5 | ck6 | ck7 | ck8 | ck9 | ck10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| baseline | 378 | 407 | 369 | 360 | 377 | 329 | 368 | 369 | 347 | 362 | 327 |
| 2e_K10_static | 241 | 271 | 339 | 277 | 271 | 309 | 271 | 230 | 230 | 225 | 228 |
| layers_92_static | 254 | 278 | 278 | 276 | 270 | 309 | 270 | 231 | 229 | 244 | 230 |

### Workload B

| strategy | ck0 | ck1 | ck2 | ck3 | ck4 | ck5 | ck6 | ck7 | ck8 | ck9 | ck10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| baseline | 531 | 547 | 571 | 517 | 559 | 507 | 514 | 508 | 543 | 475 | 493 |
| 2e_K10_static | 253 | 252 | 302 | 280 | 305 | 302 | 295 | 265 | 276 | 235 | 246 |
| layers_92_static | 259 | 252 | 283 | 298 | 339 | 299 | 295 | 266 | 278 | 248 | 253 |

### Workload C

| strategy | ck0 | ck1 | ck2 | ck3 | ck4 | ck5 | ck6 | ck7 | ck8 | ck9 | ck10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| baseline | 592 | 563 | 616 | 564 | 565 | 587 | 611 | 586 | 543 | 528 | 544 |
| 2e_K10_static | 86 | 89 | 83 | 81 | 265 | 86 | 82 | 88 | 86 | 84 | 82 |
| layers_92_static | 252 | 245 | 278 | 274 | 303 | 309 | 268 | 592 | 265 | 264 | 266 |

> 上面 C（churn，**平穩**熱點 [590000,609999] 固定）下 `2e_K10_static` **不 decay**（~82–89 全程）——這是「static t=0 hotset 不 decay」的原始結論。下面 YCSB D 是它的**第一個反例**。

## YCSB D/E self-aging（read-latest 熱點非平穩 → static hotset decay）

> 資料 `results/aging_v2/aging_ci.csv`（10 checkpoints × **10 reps × 10 seeds**，mean ± 95% CI，first-q µs）。方法：workload 自身 insert 流 age 可寫副本、**per-checkpoint probe**（隨 insert frontier 移動）對**凍結 t=0 hotset** 量。與上面 churn **互補**：churn 證平穩不衰、aging 證非平穩衰。

### YD（read-latest，**非平穩**）

| static t=0 hotset | ck0 | ck5 | ck10 | 收益 ck0→ck10 |
|---|---:|---:|---:|---|
| baseline | 538±16 | 557 | 570±24 | — |
| **2e_K10_static**（access-freq）| **267±110** | 313 | **382±78** | **−50% → −33%（衰減 ~half）**|
| layers_92_static（structural）| 252±9 | 265 | 270±12 | robust（+7%）|

- **頻率派 `2e_K10_static` 衰減**（−50%→−33%，erodes ~half、非歸零）；ck0 CI 大（初始匹配跨 seed 不穩）。
- **結構派 `layers_92_static` robust 且從 ck1 起反超 2e**（~250–278 vs ~310–420）→ **read-latest aging 下結構 > 頻率**。機制：頻率綁「哪些 key 熱」（非平穩失效），結構綁「樹形」（漂移緩慢）。

### YE（zipfian，**平穩**）

| static t=0 hotset | ck0 | ck10 |
|---|---:|---:|
| baseline | 550±16 | 601±43 |
| 2e_K10_static | 260±3（−53%）| 273±39（−55%）**不衰** |
| layers_92_static | 260±3 | 292±20（微升）|

- YE 平穩 → `2e_K10_static` **不衰、全程仍優於 layers_92**（同 C churn）。**decay 由 hotspot 平穩性決定，非 aging 本身。**
- **維度並存**：`layers_*` 在 cross-seed first-q *level* 不可恃（見 §三槓桿 / 10-seed CI），卻在 aging *robustness* 軸最耐久——不同軸、不矛盾。

## Multi-process cadence（背景 warmer 重暖 + 全機 drop probe,first-q µs）

> 來源 [`results/cadence/cadence_results.csv`](results/cadence/cadence_results.csv)。

| cadence | round | first_q_us | delivery_pct |
|---|---|---|---|
| 1.0 | 0 | 27.03 | 100.0 |
| 1.0 | 1 | 25.76 | 100.0 |
| 1.0 | 2 | 25.16 | 100.0 |
| 1.0 | 3 | 36.74 | 100.0 |
| 1.0 | 4 | 26.10 | 100.0 |
| 1.0 | 5 | 29.93 | 100.0 |
| 1.0 | 6 | 26.07 | 100.0 |
| 1.0 | 7 | 25.46 | 100.0 |
| 5.0 | 0 | 262.38 | 0.7 |
| 5.0 | 1 | 25.80 | 100.0 |
| 5.0 | 2 | 24.71 | 100.0 |
| 5.0 | 3 | 273.25 | 0.7 |

## DB 尺寸 scaling（orig 100MB vs 1gb,6M row ~1 GiB）— size sensitivity

> 為回答「**當 DB 遠大於 hot working set 時,prefetch 還靈不靈**」,新建 `test_db_1gb.db`
> (6,000,000 row、263,991 page、~1 GiB、`classify_1gb.csv`),與 100MB `orig`(600k row)用
> **同一份 seed-1 query stream** 跑全 matrix(4 workload × 6 策略 × pread/async + 4 baseline,
> **全 cell `cold_pct`=0**)。來源 [`results/size_1gb/`](results/size_1gb/summary.csv)。
> ℹ️ 此處 seed-1 query stream **就是原始 100MB 的 master workload**(原始檔 renamed 成 `workload_*_1.txt`,
> 日期 2026-05-23;`results/seeds/seed01` 跑這份 orig 的數字與上方 master 表幾乎一致 → 證實同源)。
> 本節 orig 與 1gb 在**同一批次、rep-major 交錯**量測,是原始 workload 上的 apples-to-apples 尺寸比較。
> **本節是一個自足的 full-boost 批次**(機器滿頻乾淨狀態):machine-independent 的 `2f_slru` first-query
> 全格落在 **88–98µs**——這是 CPU 滿頻 boost(cpu2 ~5.6 GHz)下「乾淨」的冷啟動下界。
> 上方 master / cross-seed 表的 `2f_slru` ~122–130µs 則是當時**長時間連跑 sweep、boost 被熱/功耗壓低**的數字
> (兩者皆有效,只是機器狀態不同;本機無 root 可釘頻,兩態無法互相重現)。
> 因此**本節絕對 µs 自成一個尺度,不與上方 master / cross-seed 表逐格比**;1gb 的 100MB 對照基準
> **就是本節同批的 `orig` 列**(同態量測)。**尺寸的相對結論不受機器狀態影響**(下方跨-seed 章用相對 Δ%,更已把此抵消)。
> cell = async first-query µs(括號 impr% 相對該 (workload,layout) baseline)。

### Workload A（Zipfian）

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 487 | 380 (−22%) | 399 (−18%) | 359 (−26%) | 357 (−27%) | 180 (−63%) | 96 (−80%) |
| 1gb | 550 | 459 (−17%) | 456 (−17%) | 288 (−48%) | 288 (−48%) | 151 (−72%) | 98 (−82%) |

### Workload B（Uniform）

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 735 | 404 (−45%) | 405 (−45%) | 406 (−45%) | 404 (−45%) | 451 (−39%) | 96 (−87%) |
| 1gb | 722 | 483 (−33%) | 482 (−33%) | 318 (−56%) | 314 (−56%) | 394 (−45%) | 98 (−86%) |

### Workload C（窄域 5×）

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 1041 | 1032 (−1%) | 654 (−37%) | 650 (−38%) | 176 (−83%) | 174 (−83%) | 88 (−92%) |
| 1gb | 711 | 639 (−10%) | 476 (−33%) | 308 (−57%) | 143 (−80%) | 144 (−80%) | 91 (−87%) |

### Workload Z（低 key Zipf）

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 499 | 379 (−24%) | 352 (−29%) | 378 (−24%) | 173 (−65%) | 174 (−65%) | 88 (−82%) |
| 1gb | 546 | 453 (−17%) | 451 (−17%) | 281 (−48%) | 142 (−74%) | 144 (−74%) | 90 (−83%) |

### 2f_slru：first-q vs deliver/e2e（resident-set 隨 DB 變大）

> deliver = async 逐頁 fadvise 的耗時;e2e_warm = deliver+fq(warm-process,本研究主張)。resident pages = 跑完該 seed-1 workload 後常駐的 working-set 頁數(2f hotset 大小)。

| workload×layout | resident pages | fq | deliver | e2e_warm | e2e_warm vs base |
|---|--:|--:|--:|--:|--:|
| A/orig | 4416 | 96 | 7058 | 7152 | 14.7× |
| A/1gb | 4448 | 98 | 7004 | 7100 | 12.9× |
| B/orig | 4420 | 96 | 7000 | 7096 | 9.7× |
| B/1gb | 4452 | 98 | 7039 | 7139 | 9.9× |
| C/orig | 483 | 88 | 800 | 888 | 0.9× |
| C/1gb | 984 | 91 | 1706 | 1798 | 2.5× |
| Z/orig | 112 | 88 | 185 | 273 | 0.5× |
| Z/1gb | 144 | 90 | 222 | 313 | 0.6× |

**讀法**:① **first-query 上 prefetch 的效益在 1GB 守得住、小 hotset 策略甚至放大**——`2f_slru` 兩尺寸都收斂到 ~96–98µs(−80~87%),first-query 只看 hot working set、與 DB 大小無關;`2d` / `2e_K10` 在 A/B/Z 於 1GB 反而改善更大(A 2d −26%→−48%、B 2d −45%→−56%、Z 2d −24%→−48%),因為**同一批 hot key 散到 6M-row DB 的更多 page,no-prefetch baseline 的冷讀更分散更貴,targeted prefetch 相對更划算**。② **e2e_warm(部署指標)上 2f 的 deliver 成本跟著 resident-set、不是 DB 大小走**:A/B 的 working set ~4.4k page 兩尺寸幾乎不變 → deliver ~7ms 不變 → e2e_warm 仍 ~10–15× baseline 慘輸;但 **C 是警訊**——resident set 483→**984** page 翻倍(窄域 key 在大 DB 散得更開)→ deliver 800→1706µs → e2e_warm 0.9×→**2.5× baseline**,C 在 100MB 是 2f 唯一能贏的格,到 1GB 也由贏轉輸。③ `layers_5/92`(固定 5/92 interior page)結構派與 working-set 無關,跨尺寸 deliver 幾乎不變。④ C baseline 在 1gb 反而較低(1041→711)屬 first-query 落點雜訊,不影響相對排序。**結論:targeted prefetch 的 first-query 優勢 size-robust;2f 的 e2e 陷阱在窄域 workload 會隨 DB 變大而惡化。**

## 資料來源

- **主矩陣（canonical）:[`results/unified_v2/matrix/summary.csv`](results/unified_v2/matrix/summary.csv)**；tie-break 修正後受影響 cell:`results/tiebreak_fix`、`results/c_hit_v2`（見文件開頭 provenance precedence 表）。Z:[`results/z/`](results/z/summary.csv)。legacy 單批（pre-canonical）:`results/main/summary.csv`
- DB 尺寸 scaling(orig vs 1gb,seed-1):[`results/size_1gb/`](results/size_1gb/summary.csv)
- DB 尺寸 × 跨-seed(1gb,A/B/C × 10 seed):[`results/seeds_1gb/`](results/seeds_1gb/) → [`results/stats/uncertainty_1gb.csv`](results/stats/uncertainty_1gb.csv)(腳本 `tools/run_seed_sweep_1gb.sh` + `tools/stats_uncertainty.py`)
- N-sweep:[`results/nsweep_dense/`](results/nsweep_dense/summary.csv)、K-sweep:[`results/ksweep/`](results/ksweep/summary.csv)
- RAM 20M:[`results/ram20m/`](results/ram20m/summary.csv)、churn:[`results/churn/`](results/churn/)、cadence:[`results/cadence/`](results/cadence/cadence_results.csv)
- 凍結清單:[`results/main/hotset_freeze.sha256`](results/main/hotset_freeze.sha256)。完整執行覆蓋見 [IMPLEMENTATION_PIPELINES.md §3.8](IMPLEMENTATION_PIPELINES.md)。


## Cross-seed workload-sensitivity (10 seeds) — R3

10 個 random seed 各重生成 A/B/C（同一份 DB、同 reps），各跑一次完整 matrix；
per-seed 效應 = 同 seed 內 strategy vs baseline 的 Δ%，下表報跨 10 seed 的 **mean、
bootstrap 95% CI of the mean、符號一致性 (n/10)、verdict**（robust=CI 不跨 0；
directional=CI 跨 0 但 ≥7/10 同號；tie=否則）。完整 54-cell×3-metric 見 
[`results/stats/uncertainty.csv`](results/stats/uncertainty.csv)；分析腳本 `tools/stats_uncertainty.py`。**註（tie-break 修正）**：`(A,2e_K500)`、`(B,2e_K10)`、`(B,2e_K500)`、`(C,2e_K10)` 這幾格的 hotset 在 `gen_hotleaves` tie-break 修正後改變（commit `de4490f`），其列已換成**修正後重測值** `results/tiebreak_fix`；其餘格 hotset 未變、沿用原 `results/seeds`。**C 2e_K10 −55% 為雙峰**（首查 not-found probe ~−70% / 真 hit ~−31%，§6.2.8）。

機器穩定性對照：2f_slru first-query 跨 10 seed 維持 125.9–130.2 µs（與第一筆查哪個 key 無關），
證明 sweep 期間無 CPU throttle、跨 seed 變異來自 workload 抽樣。

### warm-process e2e（本研究主張的部署指標）（async arm）

| layout | workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---|---:|---|---:|---|
| orig | A | layers_5 | -5.12 | [-15.94, 4.42] | 6/10 | tie |
| orig | A | layers_92 | -12.5 | [-18.05, -5.7] | 9/10 | robust |
| orig | A | 2d | -24.95 | [-29.44, -19.83] | 10/10 | robust |
| orig | A | 2e_K10 | -36.01 | [-49.98, -23.07] | 10/10 | robust |
| orig | A | 2e_K500 | 78.01 | [37.44, 136.87] | 10/10 | robust |
| orig | A | 2f_slru | 744.14 | [661.67, 870.21] | 10/10 | robust |
| orig | B | layers_5 | -1.27 | [-11.71, 6.68] | 8/10 | directional |
| orig | B | layers_92 | -13.17 | [-20.45, -1.74] | 9/10 | robust |
| orig | B | 2d | -25.44 | [-31.56, -16.18] | 9/10 | robust |
| orig | B | 2e_K10 | -25.15 | [-31.58, -14.69] | 9/10 | robust |
| orig | B | 2e_K500 | 43.06 | [26.01, 59.68] | 10/10 | robust |
| orig | B | 2f_slru | 703.6 | [631.93, 799.01] | 10/10 | robust |
| orig | C | layers_5 | 4.78 | [3.75, 6.06] | 10/10 | robust |
| orig | C | layers_92 | -20.62 | [-21.97, -19.22] | 10/10 | robust |
| orig | C | 2d | -35.88 | [-38.54, -33.07] | 10/10 | robust |
| orig | C | 2e_K10 | -55.42 | [-67.23, -43.41] | 10/10 | robust |
| orig | C | 2e_K500 | -30.63 | [-34.07, -27.27] | 10/10 | robust |
| orig | C | 2f_slru | -9.0 | [-13.87, -4.07] | 8/10 | robust |
| vacuum | A | layers_5 | -15.12 | [-26.52, -5.1] | 10/10 | robust |
| vacuum | A | layers_92 | -25.97 | [-31.6, -17.69] | 9/10 | robust |
| vacuum | A | 2d | -36.73 | [-42.2, -29.38] | 10/10 | robust |
| vacuum | A | 2e_K10 | -44.4 | [-56.62, -31.94] | 10/10 | robust |
| vacuum | A | 2e_K500 | 19.03 | [4.19, 33.80] | 7/10 | robust |
| vacuum | A | 2f_slru | 458.24 | [411.07, 517.75] | 10/10 | robust |
| vacuum | B | layers_5 | -10.5 | [-21.56, -2.45] | 10/10 | robust |
| vacuum | B | layers_92 | -22.49 | [-28.33, -13.41] | 9/10 | robust |
| vacuum | B | 2d | -34.55 | [-39.89, -26.47] | 10/10 | robust |
| vacuum | B | 2e_K10 | -33.58 | [-39.41, -24.17] | 9/10 | robust |
| vacuum | B | 2e_K500 | 15.76 | [0.75, 30.17] | 7/10 | robust |
| vacuum | B | 2f_slru | 435.43 | [386.88, 506.03] | 10/10 | robust |
| vacuum | C | layers_5 | -2.46 | [-3.64, -1.3] | 9/10 | robust |
| vacuum | C | layers_92 | -28.5 | [-29.81, -27.19] | 10/10 | robust |
| vacuum | C | 2d | -39.87 | [-41.77, -38.11] | 10/10 | robust |
| vacuum | C | 2e_K10 | -62.99 | [-73.43, -52.32] | 10/10 | robust |
| vacuum | C | 2e_K500 | -38.06 | [-41.01, -34.89] | 10/10 | robust |
| vacuum | C | 2f_slru | -34.3 | [-38.2, -30.02] | 10/10 | robust |
| ta | A | layers_5 | 0.69 | [-9.73, 12.63] | 6/10 | tie |
| ta | A | layers_92 | -15.66 | [-23.43, -8.19] | 9/10 | robust |
| ta | A | 2d | -22.52 | [-29.98, -15.6] | 10/10 | robust |
| ta | A | 2e_K10 | -31.82 | [-47.58, -16.92] | 9/10 | robust |
| ta | A | 2e_K500 | 44.60 | [22.87, 66.25] | 9/10 | robust |
| ta | A | 2f_slru | 722.16 | [635.81, 811.01] | 10/10 | robust |
| ta | B | layers_5 | 12.99 | [-1.13, 28.32] | 5/10 | tie |
| ta | B | layers_92 | -14.02 | [-24.63, -3.65] | 7/10 | robust |
| ta | B | 2d | -19.86 | [-29.43, -10.27] | 9/10 | robust |
| ta | B | 2e_K10 | -21.08 | [-29.78, -12.77] | 10/10 | robust |
| ta | B | 2e_K500 | 46.98 | [36.02, 58.40] | 10/10 | robust |
| ta | B | 2f_slru | 755.75 | [642.34, 878.62] | 10/10 | robust |
| ta | C | layers_5 | 5.57 | [5.18, 5.96] | 10/10 | robust |
| ta | C | layers_92 | -24.64 | [-25.72, -23.65] | 10/10 | robust |
| ta | C | 2d | -29.65 | [-30.77, -28.64] | 10/10 | robust |
| ta | C | 2e_K10 | -50.57 | [-59.82, -41.15] | 10/10 | robust |
| ta | C | 2e_K500 | -10.64 | [-15.03, -6.36] | 9/10 | robust |
| ta | C | 2f_slru | 4.61 | [-1.06, 10.02] | 6/10 | tie |

### first-query latency（async arm）

| layout | workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---|---:|---|---:|---|
| orig | A | layers_5 | -13.23 | [-24.37, -3.26] | 8/10 | robust |
| orig | A | layers_92 | -35.62 | [-39.58, -31.36] | 10/10 | robust |
| orig | A | 2d | -35.09 | [-38.86, -31.02] | 10/10 | robust |
| orig | A | 2e_K10 | -47.72 | [-60.85, -35.79] | 10/10 | robust |
| orig | A | 2e_K500 | -22.25 | [-62.10, 40.39] | 9/10 | directional |
| orig | A | 2f_slru | -84.9 | [-86.35, -82.64] | 10/10 | robust |
| orig | B | layers_5 | -9.04 | [-19.35, -0.92] | 7/10 | robust |
| orig | B | layers_92 | -34.88 | [-40.91, -25.61] | 9/10 | robust |
| orig | B | 2d | -35.13 | [-40.78, -26.81] | 10/10 | robust |
| orig | B | 2e_K10 | -36.52 | [-42.45, -27.39] | 9/10 | robust |
| orig | B | 2e_K500 | -55.74 | [-67.83, -44.46] | 10/10 | robust |
| orig | B | 2f_slru | -85.73 | [-87.03, -84.03] | 10/10 | robust |
| orig | C | layers_5 | -2.39 | [-3.52, -0.95] | 9/10 | robust |
| orig | C | layers_92 | -41.11 | [-43.19, -38.96] | 10/10 | robust |
| orig | C | 2d | -42.93 | [-45.89, -39.83] | 10/10 | robust |
| orig | C | 2e_K10 | -63.91 | [-75.97, -51.61] | 10/10 | robust |
| orig | C | 2e_K500 | -78.67 | [-79.73, -77.66] | 10/10 | robust |
| orig | C | 2f_slru | -87.63 | [-88.22, -87.09] | 10/10 | robust |
| vacuum | A | layers_5 | -22.18 | [-33.39, -12.72] | 10/10 | robust |
| vacuum | A | layers_92 | -44.82 | [-49.73, -38.12] | 10/10 | robust |
| vacuum | A | 2d | -44.62 | [-49.87, -37.95] | 10/10 | robust |
| vacuum | A | 2e_K10 | -53.61 | [-65.6, -41.77] | 10/10 | robust |
| vacuum | A | 2e_K500 | -62.12 | [-72.57, -50.79] | 10/10 | robust |
| vacuum | A | 2f_slru | -86.98 | [-88.05, -85.61] | 10/10 | robust |
| vacuum | B | layers_5 | -17.2 | [-28.01, -9.29] | 10/10 | robust |
| vacuum | B | layers_92 | -40.35 | [-44.98, -33.4] | 10/10 | robust |
| vacuum | B | 2d | -42.1 | [-46.88, -34.97] | 10/10 | robust |
| vacuum | B | 2e_K10 | -42.43 | [-47.53, -34.14] | 10/10 | robust |
| vacuum | B | 2e_K500 | -58.54 | [-70.25, -47.12] | 10/10 | robust |
| vacuum | B | 2f_slru | -87.61 | [-88.69, -86.03] | 10/10 | robust |
| vacuum | C | layers_5 | -8.71 | [-10.1, -7.32] | 10/10 | robust |
| vacuum | C | layers_92 | -45.81 | [-47.79, -44.07] | 10/10 | robust |
| vacuum | C | 2d | -46.04 | [-48.24, -44.02] | 10/10 | robust |
| vacuum | C | 2e_K10 | -70.44 | [-80.65, -60.02] | 10/10 | robust |
| vacuum | C | 2e_K500 | -81.14 | [-82.13, -80.06] | 10/10 | robust |
| vacuum | C | 2f_slru | -89.12 | [-89.71, -88.49] | 10/10 | robust |
| ta | A | layers_5 | -7.26 | [-18.05, 4.73] | 7/10 | directional |
| ta | A | layers_92 | -34.76 | [-40.81, -28.96] | 10/10 | robust |
| ta | A | 2d | -34.8 | [-41.04, -29.01] | 10/10 | robust |
| ta | A | 2e_K10 | -45.74 | [-60.56, -31.84] | 10/10 | robust |
| ta | A | 2e_K500 | -47.63 | [-63.26, -30.50] | 10/10 | robust |
| ta | A | 2f_slru | -85.25 | [-86.77, -83.68] | 10/10 | robust |
| ta | B | layers_5 | 4.79 | [-8.6, 19.22] | 6/10 | tie |
| ta | B | layers_92 | -33.82 | [-41.87, -26.03] | 10/10 | robust |
| ta | B | 2d | -32.89 | [-40.9, -25.04] | 10/10 | robust |
| ta | B | 2e_K10 | -35.89 | [-43.07, -29.07] | 10/10 | robust |
| ta | B | 2e_K500 | -41.99 | [-53.75, -29.56] | 10/10 | robust |
| ta | B | 2f_slru | -84.76 | [-86.76, -82.61] | 10/10 | robust |
| ta | C | layers_5 | -1.89 | [-2.29, -1.52] | 10/10 | robust |
| ta | C | layers_92 | -43.41 | [-44.44, -42.31] | 10/10 | robust |
| ta | C | 2d | -42.6 | [-43.69, -41.45] | 10/10 | robust |
| ta | C | 2e_K10 | -65.06 | [-75.00, -54.97] | 10/10 | robust |
| ta | C | 2e_K500 | -77.09 | [-78.16, -76.1] | 10/10 | robust |
| ta | C | 2f_slru | -86.9 | [-87.49, -86.34] | 10/10 | robust |


## DB 尺寸 × 跨-seed 不確定性（orig 100MB vs 1gb,各 10 seed）— R3 size × uncertainty

把上面的跨-seed 不確定性方法**原封不動套到 1gb**:A/B/C 各 10 seed 重跑 1gb full matrix
(`results/seeds_1gb/`),per-seed 效應 = 同 seed 內 strategy vs baseline 的 Δ%,報跨 10 seed 的
**mean、bootstrap 95% CI、符號一致性、verdict**。因為效應是「同 seed 相對量」,先前那個機器狀態偏移
**自動消掉**(本 sweep 的 machine anchor `2f_slru` first-q 跨 10 seed 維持 **98.4–100.2µs**,內部穩定)。
orig 欄取自已 commit 的 [`results/stats/uncertainty.csv`](results/stats/uncertainty.csv),1gb 欄取自
[`results/stats/uncertainty_1gb.csv`](results/stats/uncertainty_1gb.csv);格式 `meanΔ% [95% CI] 符號 verdict`。
> ⚠ 欄 = orig 與 1gb 的**方向/verdict 不同**(非雜訊,下方逐項說明);✓ = 兩尺寸同向且都非 tie。

### first-query latency（async)— prefetch 對冷啟動的效益

| wl | strategy | orig (100MB) | 1gb | size 一致? |
|---|---|---|---|:--:|
| A | layers_5 | −13% [−24,−3] 8/10 robust | −17% [−23,−11] 10/10 robust | ✓ |
| A | layers_92 | −36% [−40,−31] 10/10 robust | −31% [−32,−27] 10/10 robust | ✓ |
| A | 2d | −35% [−39,−31] 10/10 robust | −55% [−56,−53] 10/10 robust | ✓ |
| A | 2e_K10 | −48% [−61,−36] 10/10 robust | −61% [−69,−55] 10/10 robust | ✓ |
| A | 2e_K500 | −18% [−59,+49] 9/10 **directional** | −66% [−73,−60] 10/10 **robust** | ✓ |
| A | 2f_slru | −85% [−86,−83] 10/10 robust | −86% [−86,−85] 10/10 robust | ✓ |
| B | layers_5 | −9% [−19,−1] 7/10 robust | −15% [−22,−11] 10/10 robust | ✓ |
| B | layers_92 | −35% [−41,−26] 9/10 robust | −31% [−34,−26] 10/10 robust | ✓ |
| B | 2d | −35% [−41,−27] 10/10 robust | −55% [−57,−52] 10/10 robust | ✓ |
| B | 2e_K10 | −36% [−41,−28] 10/10 robust | −55% [−57,−52] 10/10 robust | ✓ |
| B | 2e_K500 | −53% [−65,−41] 10/10 robust | −64% [−71,−57] 10/10 robust | ✓ |
| B | 2f_slru | −86% [−87,−84] 10/10 robust | −86% [−86,−85] 10/10 robust | ✓ |
| C | layers_5 | −2% [−4,−1] 9/10 robust | −11% [−11,−10] 10/10 robust | ✓ |
| C | layers_92 | −41% [−43,−39] 10/10 robust | −22% [−29,−15] 10/10 robust | ✓ |
| C | 2d | −43% [−46,−40] 10/10 robust | −57% [−57,−57] 10/10 robust | ✓ |
| C | 2e_K10 | −79% [−80,−78] 10/10 robust | −80% [−80,−80] 10/10 robust | ✓ |
| C | 2e_K500 | −79% [−80,−78] 10/10 robust | −80% [−80,−79] 10/10 robust | ✓ |
| C | 2f_slru | −88% [−88,−87] 10/10 robust | −87% [−87,−87] 10/10 robust | ✓ |

**18/18 方向一致**,且 1gb 全部 `robust`。**prefetch 的冷啟動 first-query 優勢完全 size-robust**:符號全部一致、CI 都不跨 0;`2e_K500/A` 甚至從 orig 的 `directional`(CI [−59,+49] 跨 0)在 1gb 收成 `robust`——**大 DB 讓效應更乾淨**。小 hotset 的 `2d`/`2e_K10` 在 1gb 改善幅度更大(A 2d −35%→−55%、B 2e_K10 −36%→−55%),CI 仍緊。

### warm-process e2e（async)— 本研究主張的部署指標

| wl | strategy | orig (100MB) | 1gb | size 一致? |
|---|---|---|---|:--:|
| A | layers_5 | −5% [−16,+4] 6/10 tie | −7% [−13,−1] 7/10 robust | ⚠ |
| A | layers_92 | −12% [−18,−6] 9/10 robust | −1% [−4,+4] 9/10 directional | ✓ |
| A | 2d | −25% [−29,−20] 10/10 robust | −42% [−43,−39] 10/10 robust | ✓ |
| A | 2e_K10 | −36% [−50,−23] 10/10 robust | −47% [−55,−39] 10/10 robust | ✓ |
| A | 2e_K500 | +79% [+37,+141] 10/10 robust | +47% [+40,+55] 10/10 robust | ✓ |
| A | 2f_slru | +744% [+662,+870] 10/10 robust | +930% [+894,+993] 10/10 robust | ✓ |
| B | layers_5 | −1% [−12,+7] 8/10 directional | −5% [−12,−1] 10/10 robust | ✓ |
| B | layers_92 | −13% [−20,−2] 9/10 robust | −2% [−6,+5] 9/10 directional | ✓ |
| B | 2d | −25% [−32,−16] 9/10 robust | −42% [−45,−38] 10/10 robust | ✓ |
| B | 2e_K10 | −25% [−30,−16] 9/10 robust | −41% [−43,−37] 10/10 robust | ✓ |
| B | 2e_K500 | +40% [+24,+55] 10/10 robust | +47% [+39,+56] 10/10 robust | ✓ |
| B | 2f_slru | +704% [+632,+799] 10/10 robust | +917% [+881,+979] 10/10 robust | ✓ |
| C | layers_5 | +5% [+4,+6] 10/10 robust | −1% [−1,−1] 9/10 robust | ⚠ |
| C | layers_92 | −21% [−22,−19] 10/10 robust | +7% [+0,+13] 5/10 robust | ⚠ |
| C | 2d | −36% [−39,−33] 10/10 robust | −47% [−47,−46] 10/10 robust | ✓ |
| C | 2e_K10※ | −70% [−72,−69] 10/10 robust | −68% [−68,−68] 10/10 robust | ✓ |
| C | 2e_K500 | −31% [−34,−27] 10/10 robust | +35% [+34,+37] 10/10 robust | ⚠ |
| C | 2f_slru | −9% [−14,−4] 8/10 robust | +139% [+135,+143] 10/10 robust | ⚠ |

**13/18 一致;5 個 ⚠ 全部集中在窄域 workload C**(以及 A/layers_5 那格其實是 orig=tie→1gb 變乾淨,非真矛盾)。原因一致:**C 的 working set 隨 DB 變大而膨脹**(resident set 483→984 page),deliver 成本翻倍,把幾個「靠少量 deliver 取勝」的策略由贏轉輸,且跨 10 seed `robust`(非雜訊):
- **`2f_slru/C`:−9% → +139%**——100MB 唯一能讓 2f 在 e2e 取勝的格,到 1GB 確定變成大輸。
- **`2e_K500/C`:−31% → +35%**、**`layers_92/C`:−21% → +7%**——同樣由贏轉小輸。
- 對照:小 hotset 的 `2d`/`2e_K10` 兩尺寸 e2e 都穩贏(C 2e_K10 −70%/−68%,此為 1gb size-sweep 的 pre-fix 值;C 2e_K10 現知為 not-found 雙峰、§6.2.8,但 size-robust 結論不受影響),size-robust。

**結論(對齊後)**:① **冷啟動 first-query 的效益 size-robust**——18/18 跨尺寸方向一致、1gb 全 robust。② **部署 e2e 的 size 敏感性集中在窄域 workload**:DB 變大會放大 working set→deliver,使 `2f_slru`/`2e_K500`/`layers_92` 在 C 由贏轉輸(robust);**小而準的 hotset(2d / 2e_K10)是唯一兩尺寸 e2e 都穩贏的策略**。
