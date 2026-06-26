# workloads/

The workloads the pipeline runs. Each is 100k operations, one per line; `run_experiment.py`
takes the registry **key** (A/B/C/Z) via `--workload` and maps it to the file here.

| key | file | what it is |
|---|---|---|
| **A** | [workload_a.txt](workload_a.txt) | Zipfian read (hot/cold skew) — the main skewed workload |
| **B** | [workload_b.txt](workload_b.txt) | Uniform random read |
| **C** | [workload_c.txt](workload_c.txt) | High-key / high-churn read |
| **Z** | [workload_z.txt](workload_z.txt) | Low-key Zipfian read — robustness check vs A (hotspot location moved) |
| — | [workload_churn_write.txt](workload_churn_write.txt) | Write/mutation stream replayed by `run_experiment.py churn` to age the DB between checkpoints (not an `--workload` key) |

`run_experiment.py`'s `WORKLOADS` and `churn.py`'s `CHURN_SRC` point here. The legacy strategy
scripts under `strategies/` still reference the old alias names (`workload_a_zipfian.txt`,
`workload_b_uniform.txt`, `workload_c_highkey.txt`) via symlinks that now redirect to these files.
