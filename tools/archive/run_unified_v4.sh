#!/bin/bash
# unified_v4 — one contiguous batch covering every cell the paper's four main
# tables need (tab:e2e-ac, tab:ablation, tab:competitive, tab:seeds).
#
# Why: those four tables currently span five batches and two code versions.
# tab:competitive's Scattered-Zipf-100K / Uniform-100K columns come from
# results/competitive (2026-06-29, pre-de4490f) while its Tail-Mixed column
# comes from results/ablation_comp_v2 (post-fix); tab:seeds mixes
# results/stats (pre-fix) with results/tiebreak_fix (post-fix). This batch
# replaces all of it with one machine state and one code version.
#
# Hotsets are NOT regenerated: the frozen per-seed inputs are already corrected
# (hot2e_*_seed* regenerated 2026-07-11 by regen_hot2e_tiebreak.sh, after
# de4490f; gen_freqdump.py has used the deterministic (-count,pageno) rank
# since its first commit b64d10f and was never affected by the tie-break bug).
# So this run isolates machine state + harness version, nothing else.
#
# seed01 doubles as the single-instantiation main batch (tab:e2e-ac absolutes,
# tab:seeds "Single workload" column); seeds 01..10 give the cross-seed columns.
# Reps are the study defaults (pread 5+1, async 10+1, baseline 10+1), same
# protocol as results/seeds and results/unified_v3.
#
# Usage: tools/run_unified_v4.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/unified_v4
STRATS=layers_5,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10
mkdir -p "$OUT"
LOG="$OUT/batch.log"
ts() { date -u +%FT%TZ; }

echo "=== unified_v4 start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
echo "=== strategies: $STRATS ===" | tee -a "$LOG"
echo "=== HEAD: $(git rev-parse --short HEAD) ===" | tee -a "$LOG"
for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 500 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db orig --workload A,B,C \
       --strategy "$STRATS" --outdir "$OUT/seed${pad}" >>"$LOG" 2>&1; then
    echo "!!! seed $s RUN FAILED $(ts)" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s DONE $(ts)  rows=$([ -f "$raw" ] && wc -l < "$raw" || echo 0) ---" | tee -a "$LOG"
done
echo "=== unified_v4 complete $(ts) ===" | tee -a "$LOG"
