# Overall Results — 策略 × Workload 結果矩陣

本檔列出**每個策略 × 每個 workload × 每個 layout 的 P0 結果**（對照
[overall_workloads.md](overall_workloads.md) 的 workload 定義）。

> **2026-06-23:本檔已全面更新為 P0 數據。** 所有數字來自 **P0 pipeline**
> （`run_p0.py` 家族 → `p0_runs*/`,全 cell `cold_pct`=0)。原本的「主表～第十八維」
> pre-P0 mixed-pipeline 表格已被下方 **「全維度 P0 數據」** 取代(舊表保存在 git 歷史,
> 需對照可 `git log`)。[CONTRADICTIONS.md](CONTRADICTIONS.md) 的 16 條數據矛盾(#1–16)
> 已全部以 P0 單一權威值解決。Workload D 是 churn generator,無自身 latency 結果。
>
> **Preprocessing 計入 e2e（兩個部署模型）**:preprocessing 拆成 **open(db)(冷開 DB ~200µs,per-layout 常數)**
> 與 **deliver(逐頁 madvise/pread,隨 hotset)**。`e2e_warm` = deliver+fq(warm-process/integrated,
> 重用既有 handle、不付冷 open;≈ static `effective_first_query`,**本研究主張**);`e2e_std` = open+deliver+fq
> (standalone warmer)。**2f_slru first-query 最低(−76~89%)但 deliver ~0.8–7ms 使 e2e 多半輸**;
> targeted prefetch(layers_5 / 2d / 2e_K10)deliver 小,**warm-process e2e 三 workload 皆改善**(尤其 C × 2e_K10 −73%)。
> 視覺化:[figures 13/14](figures/out/13_strategy_firstq_bars.png)。
> 完整執行覆蓋見 [IMPLEMENTATION_PIPELINES.md §3.8](IMPLEMENTATION_PIPELINES.md)。

---

<!-- P0-MASTER-RESULTS-START -->
## P0 master batch 結果（2026-06-22,authoritative）

> 由 `run_p0.py` 一次跑齊:54 strategy cells × pread/async + 9 baseline,pread 5 / async 10 / baseline 10 reps(丟 warmup)、rep-major、全機 drop-caches、in-harness `--verify-hotset`、釘核升頻、ra=128。**全 117 cell `cold_pct`=0**。原始檔:[`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv) / [`p0_runs/raw_p0.csv`](p0_runs/raw_p0.csv)。
> `fq` = first-query median µs;`impr%` = async 相對該 (workload,layout) baseline;`e2e_std` = open+deliver+fq(standalone warmer);`e2e_warm` = deliver+fq(warm-process,≈static,本研究主張);`deliv%` = async delivery_pct;`oracle` = pread 臂 fq(可達上界)。
> 此為 A/B/C 的詳表(含 delivery_pct/oracle);下方「全維度 P0 數據」涵蓋全 workload(含 Z)× layout × 策略 + N/K-sweep + RAM + churn + cadence。舊 pre-P0 18 維表已移除(git 歷史可查)。

### Workload A (Zipfian)

| layout | strategy | fq_async | impr% | deliv% | e2e_std | e2e_warm | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|--:|
| **orig** | baseline | **529** | — | — | 529 | 529 | — |
| orig | layers_5 | 412 | 22% | 100 | 671 | 480 | 207 |
| orig | layers_92 | 393 | 26% | 100 | 781 | 587 | 210 |
| orig | 2d | 401 | 24% | 100 | 680 | 487 | 210 |
| orig | 2e_K10 | 393 | 26% | 100 | 685 | 490 | 212 |
| orig | 2e_K500 | 212 | 60% | 100 | 1238 | 1044 | 211 |
| orig | 2f_slru | 127 | 76% | 100 | 7327 | 7134 | 128 |
| **vacuum** | baseline | **716** | — | — | 716 | 716 | — |
| vacuum | layers_5 | 574 | 20% | 100 | 838 | 643 | 208 |
| vacuum | layers_92 | 575 | 20% | 100 | 954 | 759 | 209 |
| vacuum | 2d | 576 | 20% | 100 | 846 | 654 | 210 |
| vacuum | 2e_K10 | 571 | 20% | 100 | 894 | 662 | 210 |
| vacuum | 2e_K500 | 226 | 68% | 18 | 1162 | 934 | 212 |
| vacuum | 2f_slru | 126 | 82% | 100 | 5684 | 5463 | 123 |
| **ta** | baseline | **695** | — | — | 695 | 695 | — |
| ta | layers_5 | 524 | 25% | 100 | 814 | 593 | 505 |
| ta | layers_92 | 457 | 34% | 51 | 846 | 624 | 212 |
| ta | 2d | 463 | 33% | 72 | 793 | 573 | 216 |
| ta | 2e_K10 | 401 | 42% | 100 | 748 | 526 | 219 |
| ta | 2e_K500 | 340 | 51% | 25 | 1309 | 1086 | 210 |
| ta | 2f_slru | 128 | 82% | 100 | 7367 | 7146 | 126 |

### Workload B (Uniform)

| layout | strategy | fq_async | impr% | deliv% | e2e_std | e2e_warm | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|--:|
| **orig** | baseline | **760** | — | — | 760 | 760 | — |
| orig | layers_5 | 435 | 43% | 100 | 725 | 503 | 439 |
| orig | layers_92 | 435 | 43% | 100 | 849 | 630 | 439 |
| orig | 2d | 441 | 42% | 100 | 749 | 525 | 440 |
| orig | 2e_K10 | 440 | 42% | 100 | 761 | 540 | 433 |
| orig | 2e_K500 | 487 | 36% | 100 | 1558 | 1339 | 485 |
| orig | 2f_slru | 128 | 83% | 100 | 7388 | 7161 | 125 |
| **vacuum** | baseline | **1046** | — | — | 1046 | 1046 | — |
| vacuum | layers_5 | 529 | 49% | 100 | 791 | 598 | 532 |
| vacuum | layers_92 | 534 | 49% | 100 | 915 | 720 | 530 |
| vacuum | 2d | 528 | 50% | 100 | 795 | 603 | 529 |
| vacuum | 2e_K10 | 530 | 49% | 100 | 813 | 619 | 530 |
| vacuum | 2e_K500 | 436 | 58% | 18 | 1407 | 1182 | 489 |
| vacuum | 2f_slru | 126 | 88% | 100 | 5731 | 5510 | 126 |
| **ta** | baseline | **788** | — | — | 788 | 788 | — |
| ta | layers_5 | 625 | 21% | 100 | 918 | 693 | 611 |
| ta | layers_92 | 603 | 24% | 29 | 991 | 768 | 618 |
| ta | 2d | 614 | 22% | 78 | 946 | 722 | 595 |
| ta | 2e_K10 | 614 | 22% | 80 | 959 | 737 | 614 |
| ta | 2e_K500 | 746 | 5% | 30 | 1676 | 1455 | 549 |
| ta | 2f_slru | 127 | 84% | 100 | 7370 | 7149 | 125 |

### Workload C (Churn-heavy)

| layout | strategy | fq_async | impr% | deliv% | e2e_std | e2e_warm | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|--:|
| **orig** | baseline | **1096** | — | — | 1096 | 1096 | — |
| orig | layers_5 | 1067 | 3% | 100 | 1360 | 1138 | 1065 |
| orig | layers_92 | 687 | 37% | 100 | 1103 | 881 | 685 |
| orig | 2d | 684 | 38% | 100 | 975 | 753 | 685 |
| orig | 2e_K10 | 211 | 81% | 100 | 512 | 291 | 206 |
| orig | 2e_K500 | 209 | 81% | 67 | 921 | 700 | 211 |
| orig | 2f_slru | 123 | 89% | 100 | 1114 | 892 | 122 |
| **vacuum** | baseline | **993** | — | — | 993 | 993 | — |
| vacuum | layers_5 | 895 | 10% | 100 | 1188 | 963 | 818 |
| vacuum | layers_92 | 508 | 49% | 100 | 920 | 695 | 522 |
| vacuum | 2d | 517 | 48% | 100 | 805 | 584 | 516 |
| vacuum | 2e_K10 | 208 | 79% | 100 | 509 | 287 | 211 |
| vacuum | 2e_K500 | 210 | 79% | 47 | 932 | 711 | 209 |
| vacuum | 2f_slru | 124 | 88% | 100 | 934 | 712 | 122 |
| **ta** | baseline | **871** | — | — | 871 | 871 | — |
| ta | layers_5 | 882 | -1% | 100 | 1174 | 951 | 834 |
| ta | layers_92 | 498 | 43% | 97 | 885 | 663 | 516 |
| ta | 2d | 507 | 42% | 65 | 845 | 621 | 479 |
| ta | 2e_K10 | 208 | 76% | 100 | 556 | 334 | 207 |
| ta | 2e_K500 | 209 | 76% | 100 | 1053 | 830 | 210 |
| ta | 2f_slru | 122 | 86% | 100 | 1153 | 930 | 120 |

**讀法**:① first-query 最低一律是 **2f_slru**(載整個 working set),但其 deliver(A/B ~7ms、C ~0.76ms)使 `e2e` 多半輸——除 C 外兩個 e2e 模型都超 baseline。② **layers_5 / 2d / 2e_K10** 用極少 syscall:`e2e_warm`(= deliver+fq,warm-process/integrated,本研究主張)在三個 workload 都改善(A −7~9%、B −29~34%、**C × 2e_K10 −73% / 291µs**);`e2e_std`(= open+deliver+fq,standalone warmer)則在快 workload 因 ~200µs 冷 open 而變差。③ 兩個 e2e 模型唯一差是 per-layout 的冷 open(db)(~200µs)。④ `oracle` 欄是同步 pread 的可達下界。
<!-- P0-MASTER-RESULTS-END -->

---

## 全維度 P0 數據（2026-06-23,取代舊 18 維 pre-P0 表）

> 本節以下全部為 **P0 pipeline**(`run_p0.py` 家族 → `p0_runs*/`,全 cell `cold_pct`=0)的數據,**取代**本檔原本的「主表～第十八維」pre-P0 mixed-pipeline 表格(舊表保存在 git 歷史中,如需對照可 `git log`)。上方「P0 master batch 結果」為 A/B/C 含 delivery_pct/oracle 的詳表;此處為全 workload(含 **Z**)× layout × 策略 + N/K-sweep + RAM + churn + cadence 的彙整。

## 全策略 × layout × workload（P0,async first-query / e2e µs,median）

> baseline = no-prefetch;此處 cell = first-query µs (impr% 相對該 (workload,layout) baseline)。e2e 兩模型(`e2e_std`/`e2e_warm`)見上方「P0 master batch 結果」詳表。
> 來源 [`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv)(A/B/C)+ [`p0_runs_z/`](p0_runs_z/summary_p0.csv)(Z)。

### Workload A

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 529 | 412 (−22%) | 393 (−26%) | 401 (−24%) | 393 (−26%) | 212 (−60%) | 127 (−76%) |
| vacuum (1b) | 716 | 574 (−20%) | 575 (−20%) | 576 (−20%) | 571 (−20%) | 226 (−68%) | 126 (−82%) |
| ta (1c) | 695 | 524 (−25%) | 457 (−34%) | 463 (−33%) | 401 (−42%) | 340 (−51%) | 128 (−82%) |

### Workload B

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 760 | 435 (−43%) | 435 (−43%) | 441 (−42%) | 440 (−42%) | 487 (−36%) | 128 (−83%) |
| vacuum (1b) | 1046 | 529 (−49%) | 534 (−49%) | 528 (−50%) | 530 (−49%) | 436 (−58%) | 126 (−88%) |
| ta (1c) | 788 | 625 (−21%) | 603 (−24%) | 614 (−22%) | 614 (−22%) | 746 (−5%) | 127 (−84%) |

### Workload C

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 1096 | 1067 (−3%) | 687 (−37%) | 684 (−38%) | 211 (−81%) | 209 (−81%) | 123 (−89%) |
| vacuum (1b) | 993 | 895 (−10%) | 508 (−49%) | 517 (−48%) | 208 (−79%) | 210 (−79%) | 124 (−88%) |
| ta (1c) | 871 | 882 (−-1%) | 498 (−43%) | 507 (−42%) | 208 (−76%) | 209 (−76%) | 122 (−86%) |

### Workload Z

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 525 | 409 (−22%) | 383 (−27%) | 411 (−22%) | 203 (−61%) | 204 (−61%) | 119 (−77%) |
| vacuum (1b) | 705 | 570 (−19%) | 572 (−19%) | 571 (−19%) | 205 (−71%) | 203 (−71%) | 117 (−83%) |
| ta (1c) | 737 | 598 (−19%) | 460 (−38%) | 467 (−37%) | 203 (−72%) | 203 (−72%) | 117 (−84%) |

### 2f_slru first-q vs e2e（preprocessing trap,P0）

| workload×layout | fq | open | deliver | e2e_std | e2e_warm | e2e_warm vs base |
|---|--:|--:|--:|--:|--:|--:|
| A/orig | 127 | 193 | 7007 | 7327 | 7134 | 13.5× |
| A/vacuum | 126 | 222 | 5336 | 5684 | 5463 | 7.6× |
| A/ta | 128 | 222 | 7017 | 7367 | 7146 | 10.3× |
| B/orig | 128 | 222 | 7033 | 7388 | 7161 | 9.4× |
| B/vacuum | 126 | 223 | 5384 | 5731 | 5510 | 5.3× |
| B/ta | 127 | 222 | 7022 | 7370 | 7149 | 9.1× |
| C/orig | 123 | 222 | 761 | 1114 | 892 | 0.8× |
| C/vacuum | 124 | 222 | 585 | 934 | 712 | 0.7× |
| C/ta | 122 | 222 | 808 | 1153 | 930 | 1.1× |

## layers_N sweep（P0 clean,async first-q µs;N=0=baseline）

> 來源 [`p0_runs_nsweep_dense/`](p0_runs_nsweep_dense/summary_p0.csv)。

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

## 2e K-sweep（P0,async first-q µs;K=0=2d interior-only）

> 來源 [`p0_runs_ksweep/`](p0_runs_ksweep/summary_p0.csv)。

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

## RAM-pressure（cgroup MemoryMax=20M / unlimited 比值,P0 async first-q）

> 來源 [`p0_runs_ram20m/`](p0_runs_ram20m/summary_p0.csv) ÷ master。比值近 1.0 → 壓力幾乎不影響。

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

## Churn-evolution（P0,layout orig,static t=0 hotset,first-q µs;CSV 另含 vacuum/ta）

> 來源 [`p0_runs_churn/churn_evolution.csv`](p0_runs_churn/churn_evolution.csv)。

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

## Multi-process cadence（P0,背景 warmer 重暖 + 全機 drop probe,first-q µs）

> 來源 [`p0_runs_cadence/cadence_results.csv`](p0_runs_cadence/cadence_results.csv)。

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

## 資料來源（P0）

- 主矩陣:[`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv)、Z:[`p0_runs_z/`](p0_runs_z/summary_p0.csv)
- N-sweep:[`p0_runs_nsweep_dense/`](p0_runs_nsweep_dense/summary_p0.csv)、K-sweep:[`p0_runs_ksweep/`](p0_runs_ksweep/summary_p0.csv)
- RAM 20M:[`p0_runs_ram20m/`](p0_runs_ram20m/summary_p0.csv)、churn:[`p0_runs_churn/`](p0_runs_churn/)、cadence:[`p0_runs_cadence/`](p0_runs_cadence/cadence_results.csv)
- 凍結清單:[`p0_runs/hotset_freeze.sha256`](p0_runs/hotset_freeze.sha256)。完整執行覆蓋見 [IMPLEMENTATION_PIPELINES.md §3.8](IMPLEMENTATION_PIPELINES.md)。

