# ow_native_e2e — the warm-process end-to-end matrix on the OpenWhisk host (2026-10-18)

The native run that paper TODO L453 (1) asked for. It uses the second host of the OpenWhisk
campaigns, outside OpenWhisk, so the end-to-end ranking there can be compared with the
workstation's `results/unified_v7`. Only relative effects cross the hosts.

## Run

- Host `ian-comp`: AMD Ryzen 7 7700 (8 cores, 16 threads), 32 GB, Linux 7.0.0-38, Ubuntu 24.04.
  Predator SSD GM7 2 TB on ext4, `read_ahead_kb` 128 (window W = 32 pages, as on the
  workstation), amd-pstate-epp with EPP performance and boost on. Preflight:
  `preflight_ian-comp_20261017T193947Z.txt` at the repo root (`tools/ow_host_preflight.sh`),
  all checks passed. The only container running was the image registry.
- `tools/run_ow_native_e2e.sh`, HEAD dee4cd1, 2026-10-18 20:38 to 21:14 UTC. A first attempt at
  19:51 stopped before measuring because `EXPERIMENT_ROOT` was not set (batch.log keeps it).
- Matrix: A, B, C x orig x Skel (2d), Skel+10 (2e_K10), Dump-14 (2f_top14), Dump (2f_slru)
  x per-page and window-chunked delivery, plus the baseline. Seeds 1 to 10, 10 kept reps and
  1 warmup per cell as in unified_v7 family A, 309 runs per seed.
- Same code path as unified_v7. run_experiment.py is unchanged, the warmer is the committed
  binary, and the harness was built there from the committed source (gcc 13.3). The cache is
  reset by the host's setuid `/usr/local/sbin/drop-caches`. Records were discarded.
- Every seed's 12 page lists equal the frozen v7 hotsets byte for byte. Post-reset residency
  was 0% in every repetition, and 0.00% of first queries took longer than 3 ms.

## Result (`host_comparison.{md,csv,json}`, `tools/compare_hosts_e2e.py`)

36 strategy pairs per metric (6 pairs x 3 workloads x 2 mechanisms). A pair is ordered on a
host when the bootstrap CI of its paired per-instance difference excludes 0.

| metric | same order | tie on both | tie on one | reversed |
|---|---:|---:|---:|---:|
| warm end-to-end | 20 | 8 | 7 | 1 |
| first query | 22 | 7 | 7 | 0 |

- The one reversal: on Tail-Mixed, window-chunked Dump is 16.3 points of the baseline faster
  than Skel on the workstation but 61.7 points slower on the second host.
- Dump is the slowest strategy end to end in all six workload and mechanism cells on the
  second host (+3,259% and +3,022% per-page on A and B), so the reversal is stronger there.
- The precise sets' gain shrinks. Skel's end-to-end change is -6% [-12, +1] on A, -7% [-15, +7]
  on B and -22% [-31, -12] on C, against -28%, -26% and -37% on the workstation.
- Why: on the second host a cold first query takes 0.51 to 0.52 of the workstation's time, and
  dispatch takes 1.10 to 1.45 times as long for the small sets and 1.60 to 2.09 times for Dump
  (medians over instances, each host's own cells).

## Files

- `seed{01..10}/{raw,summary}.csv`, `env.txt` — written by run_experiment.py on the host.
- `uncertainty.{csv,md}` — tools/stats_uncertainty.py over the ten seeds.
- `host_comparison.{csv,json,md}` — tools/compare_hosts_e2e.py.
- `batch.log` — both attempts.
