#!/bin/bash
# unified_v6_1gb_chunked: the 10x database under window-chunked delivery.
#
# unified_v6 ran the coalesced arms on orig only, so the paper's database-size paragraph
# rests on per-page delivery alone. This batch runs family C's 1gb cells again with the
# per-page and window-chunked arms and a baseline side by side, so the per-page vs chunked
# comparison sits in one window. Its absolute microseconds are a separate machine state
# from unified_v6; quote only effects against this batch's own baseline.
#
# Matrix: A,B,C x 1gb x the 12 family-C strategies x {async, async_win} + baseline,
# reps as unified_v6 (tools/unified_v6_matrix.sh), no pread arm. --pread-reps 0 still runs
# pread's one warmup per cell (run_experiment keeps pread and async in the arm list); those
# rows carry warmup=1 and aggregate() drops them. About 860 raw rows per seed; 1gb rows ran
# at about 0.9 s/row in unified_v6, so 1 to 2 hours for 10 seeds.
# e2e_warm_us already charges parse_us to the chunked arm (run_experiment.py since 111b8ae),
# so no re-derivation is needed afterwards.
#
# Usage: tools/run_1gb_chunked.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1
SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/unified_v6_1gb_chunked
source tools/unified_v6_matrix.sh
ts() { date -u +%FT%TZ; }

# The HEAD line must be true: refuse to run from a dirty tree.
if [ -n "$(git status --short -- run_experiment.py pipeline tools)" ]; then
  echo "!!! uncommitted changes in run_experiment.py, pipeline/ or tools/ -- commit first"; exit 1
fi
mkdir -p "$OUT"
LOG="$OUT/batch.log"
echo "=== unified_v6_1gb_chunked start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
echo "=== HEAD: $(git rev-parse --short HEAD) ===" | tee -a "$LOG"
echo "=== $WL_C x 1gb x $STRATS_C x {async, async_win} ===" | tee -a "$LOG"
if ! tools/check_unified_v6_inputs.sh $SEEDS >>"$LOG" 2>&1; then
  echo "!!! INPUT GATE FAILED -- see $LOG. Nothing measured." | tee -a "$LOG"; exit 1
fi

for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 800 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s START $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db 1gb --workload "$WL_C" \
       --strategy "$STRATS_C" \
       --pread-reps 0 --async-reps "$ASYNC_REPS" --async-win-reps "$WIN_REPS" \
       --baseline-reps "$BASELINE_REPS" \
       --outdir "$OUT/seed${pad}" >>"$LOG" 2>&1; then
    echo "!!! seed $s FAILED $(ts) -- STOP" | tee -a "$LOG"; exit 1
  fi
  echo "--- seed $s DONE $(ts)  raw=$(tail -n +2 "$raw" | wc -l) rows ---" | tee -a "$LOG"
done

python3 tools/stats_uncertainty.py --seeds "$OUT"/seed[0-9][0-9] \
  --out "$OUT/uncertainty.csv" --md "$OUT/uncertainty.md" | tee -a "$LOG"
echo "=== unified_v6_1gb_chunked complete $(ts) ===" | tee -a "$LOG"
