# Workstation (unified_v7) against the second host (ow_native_e2e)

Pairs of Skel, Skel+10, Dump-14, Dump per workload (A, B, C) and delivery (per-page, window-chunked). A pair is ordered on a host when the bootstrap CI of its paired difference excludes 0. Written by tools/compare_hosts_e2e.py.

| metric | pairs | same order | tie on both | tie on one | reversed |
|---|---:|---:|---:|---:|---:|
| e2e_warm_us | 36 | 20 | 8 | 7 | 1 |
| first_query_us | 36 | 22 | 7 | 7 | 0 |

Reversed pairs (d = first minus second, points of the baseline):

- e2e_warm_us C async_win Skel vs Dump: workstation +16.3 [+11.4, +21.4], second host -61.7 [-67.0, -56.5]

Second host over workstation, medians over instances on each host: baseline first query 0.51 to 0.52, dispatch 1.10 to 2.09.
