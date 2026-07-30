#!/bin/bash
# learned_10fold — complete the learned_markov LATENCY protocol from single-fold
# (test seed 1 only, results/baselines_v2) to the full 10-fold LOSO.
#
# Gap closed: tools/baselines_v2.sh measured latency on the master (test seed 1) only;
# its own header says "full LOSO over all test seeds is the extended protocol". This
# script runs all 10 folds in ONE batch so every number shares one machine state and
# the relative %s are horizontally comparable (per machine-state-comparability rule).
#
# Protocol per fold N in 1..10 (LOSO):
#   train learned_markov on the 9-seed complement, MEASURE latency on held-out seed N's
#   trace (--seed N repoints the workload trace + all per-seed hotsets + the learned
#   test{N} hotset; the leakage guard in select_pages asserts N not in train_seeds).
# Reference arms measured in the SAME fold for paired comparison: 2f_top14, 2f_top28,
#   2e_K10, baseline (auto). freqdump + hot2e per-seed hotsets already exist for all 10
#   seeds; only learned_markov test2..10 need generating (test1 reused).
#
# Writes ONLY to results/learned_10fold/ (new) + gitignored learned hotsets in
# strategies/access/runs/. Touches no existing canonical result CSV.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

OUT=results/learned_10fold
WORKLOADS="A,B,C"
DB="orig"
PREAD_REPS="${PREAD_REPS:-10}"
ASYNC_REPS="${ASYNC_REPS:-10}"
SEEDS="${SEEDS:-1 2 3 4 5 6 7 8 9 10}"
LOG="$OUT/batch.log"
mkdir -p "$OUT/models"
echo "=== learned_10fold batch $(date -u +%FT%TZ)  seeds={$SEEDS} reps=$PREAD_REPS/$ASYNC_REPS ===" | tee -a "$LOG"

DBPATH=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.DBS['orig']))")
CLPATH=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.CLASSIFY['orig']))")

# --- (0) prep: train learned_markov for every fold whose hotset is missing ---
# test1 already exists (canonical); train 2..10. train_seeds = all seeds EXCEPT N.
echo "--- prep: learned_markov LOSO hotsets ---" | tee -a "$LOG"
for N in $SEEDS; do
  csv="strategies/access/runs/learned_markov_A_orig_N14_test${N}.csv"
  if [[ -f "$csv" ]]; then echo "  fold $N: learned hotset present, reuse" | tee -a "$LOG"; continue; fi
  TRAIN=$(python3 -c "print(' '.join(str(s) for s in range(1,11) if s!=$N))")
  echo "  fold $N: train on {$TRAIN}" | tee -a "$LOG"
  for w in a b c; do
    W=$(echo "$w" | tr a-z A-Z)
    python3 strategies/learned/train_markov.py --db "$DBPATH" --classify "$CLPATH" \
      --w "$W" --layout orig --test-seed "$N" --train-seeds $TRAIN \
      --budget 14,28 --workload-pattern "workloads/workload_${w}_{s}.txt" \
      --artifact-dir "$OUT/models" --runs-dir strategies/access/runs >>"$LOG" 2>&1 \
      || { echo "  !! train_markov failed fold $N $W" | tee -a "$LOG"; exit 1; }
  done
done

# --- (1) measure: one fold per seed, learned + reference arms, same batch ---
# NB: apply_seed() loops the FULL workload registry and exits if any key lacks a
# seed-N trace. YC (native-YCSB headline, added after the seed sweep) is correctly
# non-seedable, so it blocks --seed N>=2 even though we only run A/B/C. The shim
# drops registry keys with no seed-N trace BEFORE dispatch -- touches no shared code,
# fabricates no data, and only removes workloads we are not measuring.
for N in $SEEDS; do
  if [[ -f "$OUT/seed${N}/summary.csv" ]]; then
    echo "--- fold $N: SKIP (summary present) ---" | tee -a "$LOG"; continue
  fi
  echo "--- fold $N: measure (async+pread) ---" | tee -a "$LOG"
  python3 -c "
import sys, run_experiment as R
seed = $N
for k in list(R.WORKLOADS):
    if not (R.ROOT / f'workloads/workload_{k.lower()}_{seed}.txt').exists():
        del R.WORKLOADS[k]
sys.argv = ['run_experiment.py','run','--seed','$N',
            '--workload','$WORKLOADS','--db','$DB',
            '--strategy','learned_markov_14,learned_markov_28,2f_top14,2f_top28,2e_K10',
            '--pread-reps','$PREAD_REPS','--async-reps','$ASYNC_REPS',
            '--outdir','$OUT/seed${N}']
R.main()
" >>"$LOG" 2>&1 \
    || { echo "  !! run failed fold $N" | tee -a "$LOG"; exit 1; }
done

# --- (2) merge: prepend a seed column so folds are distinguishable ---
echo "--- merge ---" | tee -a "$LOG"
for kind in raw summary; do
  first=1
  : > "$OUT/$kind.csv"
  for N in $SEEDS; do
    f="$OUT/seed${N}/$kind.csv"
    [[ -f "$f" ]] || { echo "  !! missing $f" | tee -a "$LOG"; continue; }
    if [[ $first -eq 1 ]]; then
      { printf 'seed,'; head -1 "$f"; } >> "$OUT/$kind.csv"; first=0
    fi
    tail -n +2 "$f" | sed "s/^/${N},/" >> "$OUT/$kind.csv"
  done
done
echo "=== done $(date -u +%FT%TZ)  raw=$OUT/raw.csv summary=$OUT/summary.csv "\
"($(tail -n +2 "$OUT/summary.csv" | wc -l) summary rows) ===" | tee -a "$LOG"
