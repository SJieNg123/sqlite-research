#!/bin/bash
# Post-fix C_mixed ablation + competitive comparison, same-batch (fixed hotsets).
# C × orig × 10 seeds × {2d, leaf_rand_K10, leaf_freq_K10, 2e_K10, 2f_top14, 2f_top28, 2f_slru} + baseline.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1
OUT=results/ablation_comp_v2; LOG="$OUT/batch.log"; mkdir -p "$OUT"
ts(){ date -u +%FT%TZ; }
echo "=== ablation_comp_v2 start $(ts) ===" | tee -a "$LOG"
for s in 1 2 3 4 5 6 7 8 9 10; do
  pad=$(printf '%02d' "$s"); raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 80 ]; then echo "seed $s SKIP $(ts)"|tee -a "$LOG"; continue; fi
  echo "--- seed $s $(ts) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --workload C --db orig \
    --strategy 2d,leaf_rand_K10,leaf_freq_K10,2e_K10,2f_top14,2f_top28,2f_slru \
    --pread-reps 10 --async-reps 10 --baseline-reps 10 --outdir "$OUT/seed${pad}" >>"$LOG" 2>&1 \
    || echo "!! seed $s failed" | tee -a "$LOG"
done
echo "=== ablation_comp_v2 complete $(ts) ===" | tee -a "$LOG"
