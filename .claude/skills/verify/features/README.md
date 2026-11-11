# Cold-start prefetch runner verification map

This directory is the maintained source for verifying what a user of this repo does: run `run_experiment.py` to measure cold first-query latency with and without a prefetch strategy, and run the churn and cadence robustness experiments. Read this index, run `verify.sh doctor`, then use the matching feature file as the recipe.

## Baseline preconditions

- Work from the repo root. `V=.claude/skills/verify/verify.sh`.
- `$V doctor` ends `0 fail`. Record its `WARN` lines next to any latency number you report.
- Every measuring command goes through `$V run <run-id> ...`. It sets `EXPERIMENT_ROOT` to this checkout, forces `--outdir` under `~/verify-runs/sqlite-research/<run-id>/out`, and runs the runner through `scripts/bench_lock.sh` (flock, `taskset -c 8-15`). For the `run` subcommand it also pins the harness to cpu 10.
- Planning-only commands (`--dry-run`, `--list`, `--verify-frozen`, `--regen-hotsets` without `--yes`) run directly as `EXPERIMENT_ROOT=$PWD python3 run_experiment.py ...`. They never drop caches and need no lock.
- Never drive while another benchmark is running. Doctor fails in that case and `run` refuses on bench_lock. While a run is going, only wait: no builds, no subagents.
- Verification runs are never paper results. See the project rules in [../SKILL.md](../SKILL.md).

## Driving conventions

- Registry keys are literal. Use `--db` `orig|vacuum|ta|1gb`, `--workload` `A|B|C|Z|YC|YD|YE`, and `--strategy` `layers_<N>|2d|2e_K<K>|2f_slru|leaf_freq_K<K>|leaf_rand_K<K>|2f_top<N>|lp_sorted|lp_shuf|whole_file|...` (see `resolve_strategy()`).
- Use the smallest reps that still exercise every arm (`--pread-reps 1 --async-reps 1 --baseline-reps 1`). The runner always adds one warmup rep, which `summary.csv` drops.
- Use a fresh run-id per attempt. `run` refuses an existing one.
- Run `$V cleanup <run-id>` after every attempt, including failed ones.

## Proof and skip reporting

- A measurement counts only with `cold=0.0` in the transcript and `drop_caches_script_result=success` in its harness log.
- A prefetch arm's proof is `delivery=100.0` plus its `fq=`, next to the same run's baseline `fq=`.
- Side-effect proof is in `meta.txt`: `db_before` equals `db_after`, and `repo_dirty_after` equals `repo_dirty_before`.
- Pinning proof: the transcript's `bench_lock: holding ... cpus=8-15` line and `meta.txt`'s `pinning=` line. `churn` and `cadence` are always `NOT ACHIEVED`; report their latencies as unpinned.
- Include `meta.txt`, the transcript's measurement lines, and the `out/` CSV with every claim.
- One-rep numbers prove the pipeline ran. They are not speedup claims.
- Report a cell that `summary.csv` excluded (cold gate) as excluded. Report an unrun subcommand as unverified, never as covered by another subcommand.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order: `Sub-features`, `How to get to it (user POV)`, `Driving it with verify.sh`, and `Gotchas`.

## Features

- [Measure a cell](./run-cell.md): the main `run` matrix. It covers baseline and prefetch arms, planning (`--list`, `--dry-run`), and `summary.csv`.
- [Cadence](./cadence.md): a background re-warmer at different cadences against cold probes.
- [Churn](./churn.md): a static t=0 hotset re-measured as a DB copy is mutated.
- [Hotset inputs](./hotset-inputs.md): the freeze manifest check and the regen preview. Real regen is a guarded write to committed inputs.
- [R1 harness modes](./r1-harness.md): the C harness driven directly with the prereg R1a/R1b flags. It covers pager mode with warm-up, the three resets, per-layer residency, `memory.stat` records and the R1b competitors.

Not yet mapped (unverified by this skill): `aging` (YD/YE self-aging, `churn.py:add_aging_parser`), `run_experiment_ycsb.py`, `--seed`, `--mem-limit` RAM-pressure runs, and the coalesced/populate arms (`--async-win-reps`, `--async-bulk-reps`, `--populate-reps`).
