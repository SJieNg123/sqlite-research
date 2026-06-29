#!/bin/bash
# S5 intermediate delivery-point sweep.
# For each sleep value T, measure fq under the async (fadvise) arm with a T-ms pause
# AFTER the per-page WILLNEED hints but BEFORE the first query, so kernel readahead has
# T ms to land. pread arm (sleep-independent) = oracle upper bound; baseline = no prefetch.
# Question (R3 W5): is the reported async delivery loss (fq_async - fq_pread) a tight-timing
# artifact that vanishes once readahead is given time? Sweep T to find out.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=results/deliver_sweep
mkdir -p "$OUT"
SEED=1
WL="A,C"                      # A = the workload with the async/pread gap; C = winner-cell control
STR="layers_5,2d,2e_K10"
for T in 0 5 20 50; do
  echo "=== deliver-sleep-ms=$T ===" >&2
  python3 run_experiment.py run --seed "$SEED" --db orig \
      --workload "$WL" --strategy "$STR" \
      --deliver-sleep-ms "$T" \
      --async-reps 8 --pread-reps 5 --baseline-reps 5 \
      --outdir "$OUT/sleep_$(printf '%02d' "$T")" >/dev/null 2>"$OUT/sleep_$(printf '%02d' "$T").log"
  echo "done sleep=$T -> $OUT/sleep_$(printf '%02d' "$T")/summary.csv" >&2
done
echo "ALL_DONE deliver_sweep" >&2
