#!/bin/bash
# C_hit control batch: pure-hit tail workload (id in [580001,600000], all keys exist)
# as a control for C (which is ~50% not-found high-key lookups). Answers: does
# frequency-aware prefetch (2e_K10) still beat baseline once the unintended
# right-edge negative-lookup concentration is removed?
#
# orig layout only, 10 seeds x 10 reps. Per seed:
#   (1) regen C_hit residency hotsets (2f_slru whole-WS, 2e_K10, 2e_K500)
#   (2) gen 2f_topN frequency-partial-dump hotsets (N=14,28)
#   (3) train learned_markov + frequency (LOSO: test=seed, train=other 9), budget 14,28
#   (4) run matrix: 2d, layers_92, 2e_K10, 2e_K500, 2f_top14, 2f_top28,
#       learned_markov_14, learned_markov_28, 2f_slru (baseline auto)
#
# Usage: tools/run_chit.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose results/c_hit/seedNN/raw.csv already has data is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/c_hit
GEN=strategies/access/runs/gen_freqdump.py
DBPATH=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.DBS['orig']))")
CLPATH=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.CLASSIFY['orig']))")
NS="14 28"
REPS="--pread-reps 10 --async-reps 10 --baseline-reps 10"
mkdir -p "$OUT/models"
LOG="$OUT/sweep.log"
ts() { date -u +%FT%TZ; }
ALL="1 2 3 4 5 6 7 8 9 10"

echo "=== C_hit batch start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 300 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi

  # (1) regen C_hit residency hotsets (2f_slru, 2e_K10, 2e_K500) for this seed
  echo "--- seed $s regen residency $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --workload C_hit --db orig --seed "$s" \
       --regen-hotsets --yes >>"$LOG" 2>&1; then
    echo "!!! seed $s REGEN FAILED $(ts)" | tee -a "$LOG"; continue
  fi

  # (2) 2f_topN frequency partial dumps (N=14,28) from this seed's stream
  echo "--- seed $s gen freqdump $(ts) ---" | tee -a "$LOG"
  HP="strategies/slru/runs/hotpages_c_hit_seed${s}.csv"
  WLF="workloads/workload_c_hit_${s}.txt"
  ok=1
  for N in $NS; do
    if ! python3 "$GEN" "$DBPATH" "$CLPATH" "$HP" "$WLF" "$N" \
         "strategies/access/runs/freqdump_C_hit_orig_N${N}_seed${s}.csv" >>"$LOG" 2>&1; then
      echo "!!! seed $s freqdump FAILED (N$N) $(ts)" | tee -a "$LOG"; ok=0; break
    fi
  done
  [ $ok -eq 1 ] || continue

  # (3) learned_markov + frequency (LOSO: test=$s, train = the other 9)
  TRAIN=$(echo $ALL | tr ' ' '\n' | grep -vx "$s" | tr '\n' ' ')
  echo "--- seed $s train learned_markov (test=$s train=$TRAIN) $(ts) ---" | tee -a "$LOG"
  if ! python3 strategies/learned/train_markov.py --db "$DBPATH" --classify "$CLPATH" \
       --w C_hit --layout orig --test-seed "$s" --train-seeds $TRAIN \
       --budget 14,28 --workload-pattern "workloads/workload_c_hit_{s}.txt" \
       --artifact-dir "$OUT/models" --runs-dir strategies/access/runs >>"$LOG" 2>&1; then
    echo "!!! seed $s LEARNED TRAIN FAILED $(ts)" | tee -a "$LOG"; continue
  fi

  # (4) run the matrix
  echo "--- seed $s matrix $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db orig --workload C_hit \
       --strategy 2d,layers_92,2e_K10,2e_K500,2f_top14,2f_top28,learned_markov_14,learned_markov_28,2f_slru \
       $REPS --outdir "$OUT/seed${pad}" >>"$LOG" 2>&1; then
    echo "!!! seed $s RUN FAILED $(ts)" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s DONE $(ts)  rows=$([ -f "$raw" ] && wc -l < "$raw" || echo 0) ---" | tee -a "$LOG"
done
echo "=== C_hit batch complete $(ts) ===" | tee -a "$LOG"
