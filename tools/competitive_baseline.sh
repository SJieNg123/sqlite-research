#!/bin/bash
# RR1 / S4 competitive baseline: is the e2e win "targeted MECHANISM beats dump
# mechanism", or merely "ranked-partial beats unranked-full"? 2f_slru dumps the
# WHOLE resident working set; 2e_K10 delivers ~14-28 pages. We add a TUNED dump --
# 2f_topN = the top-N pages of the resident WS ranked by traversal frequency
# (InnoDB dump_pct analog, NO page-type knowledge) -- and put it in the same e2e
# accounting. If 2e_K10 still beats a tuned 2f_topN, the targeting mechanism is real;
# if a tuned 2f_topN matches it, the win was "rank + dump fewer", not page-type.
#
# Per seed: (1) generate the 2f_topN frozen hotsets from that seed's query stream
# (strategies/access/runs/gen_freqdump.py, restricted to the resident set =
# 2f_slru's dump), (2) run A/B/C x orig x {2e_K10, 2f_top{14,28,100,500}, 2f_slru}.
# baseline auto-runs. Same harness / reps / cold gate as the rest of the study;
# cross-seed bootstrap CI via tools/stats_uncertainty.py over seeds 1..10.
#
# Usage: tools/competitive_baseline.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/competitive
GEN=strategies/access/runs/gen_freqdump.py
DB=pipeline/preparation/layout_rewriter/runs/test.db
CL=pipeline/preparation/layout_rewriter/runs/classify_before.csv
NS="14 28 100 500"
REPS="--pread-reps 5 --async-reps 8 --baseline-reps 8"
mkdir -p "$OUT"
LOG="$OUT/sweep.log"
ts() { date -u +%FT%TZ; }

echo "=== competitive-baseline start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 300 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi

  # (1) build 2f_topN frozen hotsets for this seed (orig)
  echo "--- seed $s gen freqdump $(ts) ---" | tee -a "$LOG"
  ok=1
  for W in A B C; do
    wl=$(echo "$W" | tr 'A-Z' 'a-z')
    HP="strategies/slru/runs/hotpages_${wl}_seed${s}.csv"
    WLF="workloads/workload_${wl}_${s}.txt"
    for N in $NS; do
      if ! python3 "$GEN" "$DB" "$CL" "$HP" "$WLF" "$N" \
           "strategies/access/runs/freqdump_${W}_orig_N${N}_seed${s}.csv" >>"$LOG" 2>&1; then
        echo "!!! seed $s gen FAILED ($W N$N) $(ts)" | tee -a "$LOG"; ok=0; break
      fi
    done
    [ $ok -eq 1 ] || break
  done
  [ $ok -eq 1 ] || continue

  # (2) run the matrix
  echo "--- seed $s matrix $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db orig --workload A,B,C \
       --strategy 2e_K10,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru $REPS \
       --outdir "$OUT/seed${pad}" >>"$LOG" 2>&1; then
    echo "!!! seed $s RUN FAILED $(ts)" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s DONE $(ts)  rows=$([ -f "$raw" ] && wc -l < "$raw" || echo 0) ---" | tee -a "$LOG"
done
echo "=== competitive-baseline complete $(ts) ===" | tee -a "$LOG"
