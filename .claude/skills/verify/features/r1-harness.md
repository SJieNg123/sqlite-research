# R1 harness modes

`benchmark_harness` can reproduce the cache states that prereg/R1a.md and prereg/R1b.md define:
- a warm SQLite connection whose OS page cache is then cleared;
- natural reclaim inside a memory-capped cgroup;
- a fresh process on a warm page cache.

Each run reports page-cache residency per B-tree layer: root (from `sqlite_schema.rootpage`), interior and leaf. In pager mode it also reports which layers the probe query fetched from disk. With every new flag at its default, the harness behaves exactly as before.

## Sub-features

- `r1-pager` is pager mode (`--mmap-size 0`). A counting VFS shim and `sqlite3_db_status` produce one `pager_probe` line for the probe op.
- `r1-warmup` (`--pre-cold-ops N`) runs ops 0..N−1 on the measuring connection. Op N becomes the probe.
- `r1-reset-drop` (`--reset drop_caches`, the default) is the original madvise plus setuid drop helper.
- `r1-reset-fresh` (`--reset fresh-process`) forks. The child opens a new connection, so the pager is empty, and the page cache is left as is.
- `r1-reset-cgroup` (`--reset cgroup-pressure`) is prereg R1b:
  - a setup drop, then `memory.max = M_base + DB + 16 MiB` and `memory.swap.max = 0`;
  - a full-file init read and a memcg charge check;
  - K invocations of Q ops, each followed by a T s idle with competitors.
- `r1-layers` prints `layer_residency` (mincore through the harness's own mapping) at each checkpoint.
- `r1-memstat` writes one row per checkpoint of the run's cgroup `memory.stat` and `memory.events` to `<record>.memstat.csv`.

## How to get to it (user POV)

- `benchmark_harness --db <db> --workload <file> [R1 flags] ...` directly; `benchmark_harness --help` lists the flags.
- Registered runs only through `scripts/run_r1.sh`, which writes `results/<date>-<git-sha>-<config-hash>/`.

## Driving it with verify.sh

Preconditions:

- `$V doctor` ends `0 fail`, and `scripts/bench_lock.sh --status` says `free`.
- For cgroup-pressure: `$V prep-scratch` has created `~/verify-runs/sqlite-research/scratch/{stream.bin,hot.bin}`.
- `C="--db pipeline/preparation/layout_rewriter/runs/test.db --readonly --require-read-first --warm-cpu-ms 10 --drop-caches-script /usr/local/sbin/drop-caches"`.

Steps:

- **Pager probe after warm-up (R1a B).** Run `$V harness r1a-B-A-N1000 -- $C --workload workloads/workload_a_1.txt --mmap-size 0 --cache-size -2000 --pre-cold-ops 1000`.
  - The record shows `layer_residency point=after-reset ... root=0/3 interior=0/89 path_interior=0/10 leaf=0/26239`.
  - It also shows `pager_probe op=1000 key=... probe_l2=... probe_leaf=... page1_reads=0 ... root_reads=0 interior_reads=0 ... leaf_reads=0 partial_reads=1 cache_hit=4 cache_miss=0`, which says the probe path was served by the pager.
  - Check the line against the row `A,1,1000` of `prereg/design/R1a_probe_predictions.csv`.
- **mmap config with warm-up (R1a C).** Run `$V harness r1a-C-A-N1000 -- $C --workload workloads/workload_a_1.txt --pre-cold-ops 1000`.
  - `after-reset` still shows `root=3/3`, a `path_interior` of up to 10/10, and thousands of leaves. See Gotchas.
- **Fresh process.** Run `$V harness fresh-B -- $C --workload workloads/workload_a_1.txt --mmap-size 0 --cache-size -2000 --pre-cold-ops 1000 --reset fresh-process`.
  - The record shows `fresh_process child_pid=...: cold advice and drop script not applied`.
  - `pager_probe` shows `root_reads=1 interior_reads=1 leaf_reads=1`, because the new connection has an empty pager.
- **Natural pressure (R1b).** Run `$V harness r1b-stream-A-0.25 --scope -- $C --workload workloads/workload_a_1.txt --reset cgroup-pressure --pressure-ratio 0.25 --competitor stream --invocations 5 --ops-per-invocation 200 --idle-s 60 --quiesce-s 2 --scratch-dir $HOME/verify-runs/sqlite-research/scratch --measure-ops 200`. It takes about 5 minutes.
  - The record shows `cgroup_limits m_base=... memory_max=...` and `cpus who=anon ... allowed=12`.
  - It shows `cgroup_charge_check=pass`, then `layer_residency point=idle-1..5`. `after-reset` here means just before the probe.
  - `memstat ... oom_kill=0` appears at every checkpoint. `--competitor hot` adds `hot_file=x/y` to each residency line.
- **Defaults unchanged.** Run the `run-cell` recipe once with the old binary and once with the new one. The `harness --bin` option drives either binary directly. Compare `parse_metrics` keys and medians.
  - Measured on 2026-11-11 with 10 reps per arm: the new medians 382.2 / 145.4 / 302.1 µs fell inside the old 95% CIs [378.3, 383.6] / [142.7, 153.7] / [299.7, 304.5].
- **Proof.** Copy the `layer_residency`, `pager_probe` and `memstat` lines and `meta.txt`. Cleanup keeps `out/records/`.

## Gotchas

- **The mmap config cannot be cooled after a warm-up.** Pages that SQLite has mapped survive `drop_caches`, and `MADV_DONTNEED` only drops the harness's own mapping. A run with `--pre-cold-ops N` (N ≥ 1) and mmap on therefore fails any cold gate. The registered R1a group C hits this; it is a prereg design issue, not a harness bug.
- **Page 1 is already in the pager at N=0.** Schema init (before-cold) loads it, so `page1_reads=0` at N=0, while `prereg/design` predicts a miss. `pager_probe` counts page 1 separately (`page1_reads`).
- **The B group needs an explicit cache size.** The harness default `--cache-size 0` is F1. Pass `--cache-size -2000`, SQLite's default.
- **A pager hit is not free.** Even with every page served from the pager, the probe pays one disk read: the 16-byte change-counter read of page 1 (`partial_reads=1`) after a drop.
- **Rejected combinations.** `--pre-cold-ops` and cgroup-pressure are refused with after-cold open or schema timing, which segfaulted before the fix. Negative counts, a ratio outside [0,1], and `--idle-s` below `--quiesce-s` are refused too.
- **A missing layer map aborts R1 flags.** If the O_DIRECT open fails (for example a DB on tmpfs), any R1 flag aborts rather than printing counts that cannot be attributed.
- **cgroup-pressure needs its scope.** Without `--scope` it fails with "needs a cgroup v2 memory controller".
- **`path_interior` and `path_leaf` are unions.** They cover every rowid the workload touches. The probe's own path is `probe_l2` and `probe_leaf` on the `pager_probe` line.
