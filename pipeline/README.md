# pipeline/

The core machinery `run_experiment.py` drives, split into two stages.

## `engine/` — the measurement machinery
| Folder | Role |
|---|---|
| [engine/benchmark_harness/](engine/benchmark_harness/) | Core C harness: mmap → cold-clear (madvise chain + `drop-caches`) → run the post-cold prefetch script → time the first query. Ships vendored `sqlite3.c/h` (version-pinned) and the **workloads** A/B/Z under `workloads/`. |
| [engine/prefetch_warmer/](engine/prefetch_warmer/) | The **warmer** = prefetch delivery engine (`src/warmer.c`); warms a hotset and reports `warmer_us`/`open_us`/`deliver_us`. Invoked as the harness `--post-cold-script`. |
| [engine/residency_checker/](engine/residency_checker/) | `mincore()` snapshot — how much of a hotset is page-cache resident. Used by `--regen-hotsets`. |

## `preparation/` — builds the inputs the engine consumes
| Folder | Role |
|---|---|
| [preparation/layout_rewriter/](preparation/layout_rewriter/) | Builds the 3 layout DBs (`runs/test*.db` = orig/vacuum/type-aware) + `classify_*.csv` page maps — i.e. `run_experiment.py`'s `DBS` and `CLASSIFY`. |
| [preparation/classify_pages/](preparation/classify_pages/) | Page-type classifier (interior vs leaf) — the source of the classification the layouts and `layers_N` rely on. |

`run_experiment.py` points its `BH` / `WARMER` / `RESIDENCY_CHECKER` / `DBS` / `CLASSIFY` /
`WORKLOADS` (A/B/Z) constants here; strategy hotsets live under `strategies/` and Workload C
under `prefetch_churn/workloads/`.
