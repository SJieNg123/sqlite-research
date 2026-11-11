---
name: verify
description: Drive the SQLite cold-start prefetch experiment runner (run_experiment.py — run / churn / aging / cadence subcommands) for real on this host, through scripts/bench_lock.sh, and capture proof — cold gate, delivery %, first-query µs, summary CSVs — without touching the repo's results/. Use to prove a change to the runner, a strategy, a workload, the C harness/warmer, or the hotset inputs actually runs end to end. Not a source of paper numbers.
---

# verify — SQLite cold-start prefetch runner

The surface is a CLI: `python3 run_experiment.py [run|churn|aging|cadence] ...` at the repo root. Every measurement drops the **whole machine's** page cache through `/usr/local/sbin/drop-caches` (setuid root), runs the C `benchmark_harness` on a DB under `pipeline/preparation/layout_rewriter/runs/`, and optionally lets `warmer` prefetch a hotset first. There is no server: "launch" means the binaries and inputs are ready, and each drive is one short CLI invocation.

All driving goes through the helper next to this file:

```bash
V=.claude/skills/verify/verify.sh      # from the repo root
$V doctor                               # read-only readiness check (~12 s; rebuilds binaries into a temp dir to compare, skipped while a benchmark runs)
$V run <run-id> [run_experiment.py args...]
$V harness <run-id> [--scope] [--bin <path>] -- <benchmark_harness args...>   # the C harness directly (R1 flags)
$V prep-scratch                         # R1b competitor files: $VERIFY_ROOT/scratch/{stream.bin 2 GiB, hot.bin 128 MiB}
$V cleanup <run-id>
```

## Project rules this skill obeys (CLAUDE.md)

Read `CLAUDE.md` before driving. Four rules bind every verification run:

- **One benchmark at a time, through `scripts/bench_lock.sh`.** The script takes a per-user flock and execs the command under `taskset -c 8-15`. CPUs 8–15 are the first threads of CCD1, sharing one L3; their SMT siblings 24–31 are outside the mask. `$V run` wraps the runner in it and refuses if the lock is held (exit 75). `scripts/bench_lock.sh --status` prints `free` or `held` without taking the lock.
- **While a benchmark runs, the agent only waits.** Run `$V run` in the foreground and wait for it. Don't start builds, subagents, arena, or a second benchmark meanwhile. For the same reason, `doctor` skips its rebuild-compare while the lock is held.
- **Verification runs are not results.** They go to `~/verify-runs/sqlite-research/<run-id>/` and must never be cited in the paper or `main.tex`.
  - Paper numbers come only from runs registered in `prereg/<id>.md`, committed before the run, with output under `results/<date>-<git-sha>-<config-hash>/`. That directory is append-only.
  - This skill never writes to `results/`.
- **A change to the measurement path needs more than this skill.** That means a diff touching `benchmark_harness.c`, the reset logic, or the analysis scripts. Such a diff also needs `/pstack:interrogate`, `/pstack:blast-radius`, and a small rerun with the old settings that lands inside the original CI. A verify run proves the pipeline executes and its gates pass. It does not prove the numbers are unchanged.

What the helper sets for you:
- `EXPERIMENT_ROOT=<this checkout>`. Without it the runner reads inputs from `/home/u03/sqlite-research-project-sharing` (its hardcoded default) and fails with `FileNotFoundError ... classify_before.csv`.
- `--outdir $VERIFY_ROOT/<run-id>/out` (default `VERIFY_ROOT=~/verify-runs/sqlite-research`), so the committed `results/` tree is never written.
- For the default `run` subcommand, `--no-pin-env`, so `env.sh` only records and never tries to write the CPU governor, `read_ahead_kb` or THP sysfs knobs.
- For the default `run` subcommand, `--cpu 10` unless you pass a `--cpu` in 8–15. Any `--cpu` outside the mask is refused.
  - The runner's own default, `--cpu 2`, lies outside bench_lock's mask. `sched_setaffinity` then fails with only a stderr warning that the runner swallows, and the harness runs unpinned.
  - `churn` and `cadence` hardcode `--cpu 2` (`churn.py:27,62,212`, `cadence.py:22`), so their pinning is never achieved under bench_lock. `$V run` records that in `meta.txt` (`pinning=NOT ACHIEVED ...`). Treat their latencies as unpinned.

## Launch

Nothing to start. The three binaries ship prebuilt in the checkout (gitignored). If doctor reports one as stale or missing, rebuild it in place, only while `scripts/bench_lock.sh --status` says `free`. The README's harness command lacks `-I.` and fails with `sqlite3.h: No such file`, so use these:

```bash
(cd pipeline/engine/benchmark_harness && gcc -O2 -I. -o benchmark_harness benchmark_harness.c sqlite3.c -lpthread -ldl -lm)
gcc -O2 -o pipeline/engine/prefetch_warmer/src/warmer pipeline/engine/prefetch_warmer/src/warmer.c
gcc -O2 -o pipeline/engine/residency_checker/residency_checker pipeline/engine/residency_checker/residency_checker.c
```

Ready means `$V doctor` ends `0 fail`. The inputs (test.db / test_vacuum.db / test_typeaware.db / test_db_1gb.db, classify CSVs, `strategies/*/runs/` residency and hot-leaf CSVs, `workloads/*.txt`) are committed or shipped and are only read. No step regenerates them; see `features/hotset-inputs.md` before touching `--regen-hotsets`.

## Doctor

`$V doctor` answers "is this checkout and host worth driving?" and changes nothing in the repo. It checks:

- that `scripts/bench_lock.sh` exists and the lock is free (FAIL if held), and that CPUs 8–15 are usable.
- that each binary is byte-identical to a fresh `gcc -O2` build of HEAD source. mtimes are useless in this restored checkout, and the build is deterministic here. This check is skipped, with a WARN, while the lock is held.
- that `drop-caches` is setuid root.
- that every DB and classify CSV exists.
- that a `--dry-run` of A/orig/2d plans a hotset (`hotset=18 pages`).
- the freeze manifest (`--verify-frozen`).
- that no harness/warmer of yours is running.
- whether other users' harnesses are running, and the load average.

`WARN` lines don't block a run, but they qualify any latency number. `FAIL` lines do block it.

## Drive

One verify run = one `run-id` = one directory. `run` refuses to reuse an existing run-id and refuses while bench_lock is held.

Use the smallest rep counts that still exercise every arm. The runner always does 1 warmup rep plus N kept reps.

```bash
$V run cell-A-orig-2d --db orig --workload A --strategy 2d --pread-reps 1 --async-reps 1 --baseline-reps 1     # ~9 s, harness on cpu 10
$V run cadence-A cadence --workload A --db orig --cadences 0.5,never --rounds 2 --gap 1.5                        # ~8 s, unpinned (see above)
$V run churn-A churn --workload A --db orig --checkpoints 1 --reps 1                                             # ~15 s, unpinned (see above)
```

`$V harness` runs `benchmark_harness` itself through bench_lock, without the runner. Use it for the R1 flags:
- `--cache-size`, `--mmap-size 0` (pager mode), `--pre-cold-ops`, `--measure-ops`, and `--reset drop_caches|cgroup-pressure|fresh-process`.
- It adds `--cpu 10` unless you give one in 8–15, and `--record-dir`/`--output` under the run directory.
- `--scope` wraps the harness in `systemd-run --user --scope -p MemorySwapMax=0`. `--reset cgroup-pressure` needs it.
- `--bin <path>` drives another build, for example an old binary in a before/after comparison.

Recipes and expected output are in [features/r1-harness.md](features/r1-harness.md). Registered R1a/R1b runs never go through this skill: they go through `scripts/run_r1.sh` into `results/`.

Plan without measuring (no drop-caches, no writes, no lock needed) with `python3 run_experiment.py ... --dry-run` or `--list` run directly, with `EXPERIMENT_ROOT=$PWD` set. Per-feature recipes and expected outputs are in [features/README.md](features/README.md).

## Evidence

`$VERIFY_ROOT/<run-id>/` holds:

| file | what it proves |
|---|---|
| `meta.txt` | git rev, exact command (including `scripts/bench_lock.sh`), `pinning=` status, exit code, size+mtime of the three source DBs before and after, `repo_dirty_before` / `repo_dirty_after` |
| `transcript.txt` | full runner stdout+stderr: the `bench_lock: holding ... cpus=8-15` line, then one `[repN warm/keep] ... fq= delivery= cold=` line per measurement |
| `out/` | the runner's own outputs (`raw.csv`, `summary.csv`, `env.txt` / `cadence_results.csv` / `churn_*.csv`) |
| `out/records/` | (`$V harness` runs) the harness `run-*.log` and `run-*.memstat.csv`: `layer_residency` lines per checkpoint, `pager_probe` in pager mode, `memstat` rows of the run's cgroup |
| `logs/` | (after cleanup) every harness `run-*.log` and `run-*.memstat.csv`, with `drop_caches_script_result=success`, `verify_cold_pct=… resident=a/b`, `verify_delivery_pct=… resident=a/b`, and `first_query_latency_us=` |

Proof standards for this repo:

- **Drive the real path.** Use the real runner, real drop-caches, and the real harness. A `--dry-run` proves planning only, never measurement. Don't call `select_pages()` or other internals and report that as "works".
- **Cold gate.** A measurement counts only if `cold=0.0` (no hotset page was resident after the drop, before delivery) and the log shows `drop_caches_script_result=success`. `summary.csv` drops cells above `--cold-pct-max` (default 1.0). Report a missing cell as excluded, never as passed.
- **Action and resulting state.** For a prefetch arm, show `delivery=100.0` (the warmer actually put the hotset in cache) next to the `fq=` it produced, and the baseline `fq=` from the same run as the denominator. The baseline's delivery is ~0 by design.
- **Side effects.** In `meta.txt`, `db_before` equals `db_after` (measurement opens are `--readonly`) and `repo_dirty_after` equals `repo_dirty_before`, so the run left no file in the checkout. Churn and aging mutate a *copy* under `out/work/`. Check that the copy changed size (in the transcript or `ls` before cleanup) and that the source didn't.
- **Pinning.** The transcript shows `bench_lock: holding ... cpus=8-15`, and `meta.txt` shows `pinning=harness pinned to cpu N`. A run marked `NOT ACHIEVED` proves the pipeline ran, not a pinned latency.
- **Numbers are not results.** One rep on a shared host proves the pipeline runs and the gates pass. It does not prove a speedup.
  - Canonical `results/main` ran the harness on cpu 2 (CCD0). Verify runs use cpu 10 (CCD1), so compare against them for direction only.
  - Claims about effects go through a prereg, never through this skill.

## Cleanup

```bash
$V cleanup <run-id>
```

This kills only processes whose command line names this run's directory (cadence's `setsid` background warmer loop is the one that can outlive an interrupted run). It copies every harness `run-*.log` into `logs/`, then deletes the scratch `out/work/` (hotsets, per-rep `ops-N.csv`, churn DB copies, 13–160 MB). It keeps `meta.txt`, `transcript.txt`, `out/*.csv` and `logs/`. It never touches `results/`.

Never `pkill warmer` or `pkill benchmark_harness`: other users on this host run the same tools.

## Helpers

- `verify.sh` (this directory, executable): `doctor`, `run <run-id> [args...]`, `harness <run-id> [--scope] [--bin <path>] -- <args>`, `prep-scratch`, `cleanup <run-id>`. Running it without arguments prints its usage.
- `scripts/bench_lock.sh` (repo): `scripts/bench_lock.sh <cmd...>` or `scripts/bench_lock.sh --status`. Running it without arguments prints its usage. `BENCH_LOCK_WAIT=<s>` waits instead of failing at once.
