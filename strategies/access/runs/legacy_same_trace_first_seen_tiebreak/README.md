# Legacy hot2e hotsets — same-trace first-seen tie-break (PRE-FIX)

These are the `hot2e_*` hotsets produced by the OLD `gen_hotleaves.py` that ranked
leaves with `Counter.most_common(TOPK)` (insertion-order = first-seen tie-break). On
tied-count workloads (C / C_hit) that leaked the measured first-op leaf into the hotset
(see REPORT §6.2.8 / results/c_hit/FINDINGS.md). Fixed in commit de4490f
(deterministic `(-count, pageno)` tie-break).

The pre-fix MEASUREMENTS that used these hotsets are still in git:
`results/main`, `results/unified_v2`, `results/seeds`, `results/c_hit`.

The CSVs themselves are gitignored (26k rows each, regenerable). To reproduce any of
them exactly:

    git show de4490f^:strategies/access/runs/gen_hotleaves.py > /tmp/gen_old.py
    python3 /tmp/gen_old.py <db> <classify.csv> <base_hotpages.csv> <workload.txt> <K> <out.csv>

Post-fix hotsets (current, `(-count,pageno)` tie-break) live in
`strategies/access/runs/hot2e_*.csv`; post-fix measurements in
`results/tiebreak_fix` (A/B/C matrix + cross-seed) and `results/c_hit_v2` (C_hit).
