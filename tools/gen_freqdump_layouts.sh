#!/bin/bash
# Prerequisite for tools/run_unified_v6.sh: build the 2f_topN frozen hotsets for the
# NON-orig layouts. unified_v5 ran 2f_topN on orig only, which left the Dump-N family
# absent from the layout and size axes -- the one cell the database-size paragraph
# (main.tex:553) may need and the only coverage gap in that batch.
#
# Same generator, same argument order and same output naming as the orig files in
# tools/competitive_baseline.sh:40-52, so the new inputs are interchangeable with the
# ones every prior batch used. The workload stream is layout-independent (run_experiment.py
# resolves WORKLOADS before DBS), so only the db, classify and resident-hotpages inputs
# change per layout.
#
# 360 files (3 workloads x 3 layouts x 4 budgets x 10 seeds) at about 0.65 s each,
# roughly 4 minutes serially. Pure replay: no cold-clear, no measurement, so it is safe
# to run while anything else is running. Idempotent: an existing non-empty file is kept.
#
# Usage: tools/gen_freqdump_layouts.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
GEN=strategies/access/runs/gen_freqdump.py
R=pipeline/preparation/layout_rewriter/runs
NS="14 28 100 500"
LOG=strategies/access/runs/gen_freqdump_layouts.log
ts() { date -u +%FT%TZ; }

# db key -> db file, classify file, hotpages suffix (mirrors run_experiment.py DBS/CLASSIFY/SLRU_SUFFIX)
dbfile()  { case "$1" in vacuum) echo "$R/test_vacuum.db";; ta) echo "$R/test_typeaware.db";; 1gb) echo "$R/test_db_1gb.db";; esac; }
clfile()  { case "$1" in vacuum) echo "$R/classify_vacuum.csv";; ta) echo "$R/classify_after.csv";; 1gb) echo "$R/classify_1gb.csv";; esac; }
slrusuf() { case "$1" in vacuum) echo "_vacuum";; ta) echo "_ta";; 1gb) echo "_1gb";; esac; }

echo "=== gen_freqdump_layouts start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
made=0; kept=0; fail=0
for s in $SEEDS; do
  for W in A B C; do
    w=$(echo "$W" | tr 'A-Z' 'a-z')
    WLF="workloads/workload_${w}_${s}.txt"
    for db in vacuum ta 1gb; do
      HP="strategies/slru/runs/hotpages_${w}$(slrusuf "$db")_seed${s}.csv"
      for N in $NS; do
        OUT="strategies/access/runs/freqdump_${W}_${db}_N${N}_seed${s}.csv"
        if [ -s "$OUT" ]; then kept=$((kept+1)); continue; fi
        if python3 "$GEN" "$(dbfile "$db")" "$(clfile "$db")" "$HP" "$WLF" "$N" "$OUT" >>"$LOG" 2>&1; then
          made=$((made+1))
        else
          echo "!!! FAILED $W $db N$N seed$s" | tee -a "$LOG"; fail=$((fail+1)); rm -f "$OUT"
        fi
      done
    done
  done
  echo "--- seed $s done $(ts)  made=$made kept=$kept fail=$fail ---" | tee -a "$LOG"
done
echo "=== gen_freqdump_layouts complete $(ts)  made=$made kept=$kept fail=$fail ===" | tee -a "$LOG"
[ "$fail" -eq 0 ] || exit 1
