#!/bin/bash
# native_headtohead — same-batch head-to-head of OUR strategies vs PRIOR-WORK on the
# canonical native YCSB-C 10-seed family. Fills the one audited matrix hole: lp_sorted/
# lp_shuf (libprefetch) and learned_markov_14/28 (Chen-inspired first-order Markov) were
# only ever measured on synthetic A/B/C -- never on a real YCSB trace. This batch runs
# baseline + ours + prior-work per fold in one machine state so the native ours-vs-prior-art
# comparison is internally comparable (relative % is machine-state-portable).
#
# Protocol (mirrors tools/baselines_v2.sh's 3-family split, retargeted to the native
# executor run_experiment_ycsb.py + the frozen native traces workloads_refined/traces/):
#   MASTER hotsets + PER-SEED traces -- exactly how the frozen native seed sweep was run
#   (no _seed{N} native hotsets exist; fig17_abl_YC_orig_s{N}.csv rows say workload=YC).
#   => NO --regen-hotsets, NO DROP_CACHES, NO root needed.
#
# Per fold N (one machine state):
#   Run-A  ours + budget-matched refs, baseline auto  (SEED=None, trace shimmed to seed N)
#          2d,2e_K10,2e_K500,2f_slru,2f_top14,2f_top28,layers_5,layers_92   async+pread
#   Run-B  lp arms, pread-only (libprefetch is synchronous), no baseline  (SEED=None, shim)
#          lp_sorted,lp_shuf                                                pread only
#   Run-C  learned LOSO, no baseline  (--seed N: apply_seed repoints YC + keys test{N} model)
#          learned_markov_14,learned_markov_28                             async+pread
# baseline (no-prefetch) is hotset-independent and replays the same seed-N trace in Run-A,
# so it is the valid same-fold reference for every arm incl. learned.
#
# Writes ONLY to results/native_headtohead/. Touches no frozen results/ycsb_full CSV.
# Learned model hotsets land in strategies/access/runs/ (gitignored: learned_markov_*.csv).
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

OUT=results/native_headtohead
SEEDS="${SEEDS:-1 2 3 4 5 6 7 8 9 10}"
PREAD_REPS="${PREAD_REPS:-10}"
ASYNC_REPS="${ASYNC_REPS:-10}"
OURS="2d,2e_K10,2e_K500,2f_slru,2f_top14,2f_top28,layers_5,layers_92"
LP="lp_sorted,lp_shuf"
LEARNED="learned_markov_14,learned_markov_28"
LOG="$OUT/batch.log"
mkdir -p "$OUT/models"
echo "=== native_headtohead batch $(date -u +%FT%TZ)  seeds={$SEEDS} reps=$PREAD_REPS/$ASYNC_REPS ===" | tee -a "$LOG"

DBPATH=$(python3 -c "import run_experiment_ycsb as R; print(R.resolve_pointer(R.DBS['orig']))")
CLPATH=$(python3 -c "import run_experiment_ycsb as R; print(R.resolve_pointer(R.CLASSIFY['orig']))")
AR=strategies/access/runs
SR=strategies/slru/runs

# ---- (0) prep: native learned_markov LOSO hotsets, one per fold (train = all seeds != N) ----
echo "--- prep: learned_markov LOSO hotsets (native YC) ---" | tee -a "$LOG"
for N in $SEEDS; do
  csv="$AR/learned_markov_YC_orig_N14_test${N}.csv"
  if [[ -f "$csv" ]]; then echo "  fold $N: learned hotset present, reuse" | tee -a "$LOG"; continue; fi
  TRAIN=$(python3 -c "print(' '.join(str(s) for s in range(1,11) if s!=$N))")
  echo "  fold $N: train on {$TRAIN}" | tee -a "$LOG"
  python3 strategies/learned/train_markov.py --db "$DBPATH" --classify "$CLPATH" \
    --w YC --layout orig --test-seed "$N" --train-seeds $TRAIN \
    --budget 14,28 --workload-pattern 'workloads_refined/traces/seeds/workload_YC_{s}.txt' \
    --artifact-dir "$OUT/models" --runs-dir "$AR" >>"$LOG" 2>&1 \
    || { echo "  !! train_markov FAILED fold $N -- STOP" | tee -a "$LOG"; exit 1; }
done

# ---- fail-loud gate: every hotset/model an arm will read must exist BEFORE any measure ----
require() { [[ -f "$1" ]] || { echo "  !! MISSING required hotset: $1 -- STOP" | tee -a "$LOG"; exit 1; }; }
echo "--- gate: master hotsets + per-fold learned models ---" | tee -a "$LOG"
require "$AR/hot2e_YC_orig_K10.csv";  require "$AR/hot2e_YC_orig_K500.csv"
require "$SR/hotpages_yc.csv"
require "$AR/freqdump_YC_orig_N14.csv"; require "$AR/freqdump_YC_orig_N28.csv"
for N in $SEEDS; do
  require "$AR/learned_markov_YC_orig_N14_test${N}.csv"
  require "$AR/learned_markov_YC_orig_N28_test${N}.csv"
done
echo "  gate OK" | tee -a "$LOG"

# ---- (1) measure: per fold, 3 families, merged into seed{N}/summary.csv ----
for N in $SEEDS; do
  if [[ -f "$OUT/seed${N}/summary.csv" ]]; then
    echo "--- fold $N: SKIP (summary present) ---" | tee -a "$LOG"; continue
  fi
  echo "--- fold $N: Run-A ours+refs (baseline auto) ---" | tee -a "$LOG"
  python3 -c "
import sys, run_experiment_ycsb as R
R.WORKLOADS['YC'] = R.ROOT / 'workloads_refined/traces/seeds/workload_YC_${N}.txt'
sys.argv = ['run_experiment_ycsb.py','run','--workload','YC','--db','orig',
            '--strategy','$OURS','--pread-reps','$PREAD_REPS','--async-reps','$ASYNC_REPS',
            '--outdir','$OUT/seed${N}/main']
R.main()
" >>"$LOG" 2>&1 || { echo "  !! Run-A FAILED fold $N -- STOP" | tee -a "$LOG"; exit 1; }

  echo "--- fold $N: Run-B lp (pread-only, no baseline) ---" | tee -a "$LOG"
  python3 -c "
import sys, run_experiment_ycsb as R
R.WORKLOADS['YC'] = R.ROOT / 'workloads_refined/traces/seeds/workload_YC_${N}.txt'
sys.argv = ['run_experiment_ycsb.py','run','--workload','YC','--db','orig','--no-baseline',
            '--strategy','$LP','--pread-reps','$PREAD_REPS','--async-reps','0',
            '--outdir','$OUT/seed${N}/lp']
R.main()
" >>"$LOG" 2>&1 || { echo "  !! Run-B FAILED fold $N -- STOP" | tee -a "$LOG"; exit 1; }

  echo "--- fold $N: Run-C learned (--seed $N, no baseline) ---" | tee -a "$LOG"
  python3 run_experiment_ycsb.py run --seed "$N" --workload YC --db orig --no-baseline \
    --strategy "$LEARNED" --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
    --outdir "$OUT/seed${N}/learned" >>"$LOG" 2>&1 \
    || { echo "  !! Run-C FAILED fold $N -- STOP" | tee -a "$LOG"; exit 1; }

  # merge the 3 families for this fold (header once, then all data rows)
  for kind in raw summary; do
    { head -1 "$OUT/seed${N}/main/$kind.csv"
      for d in main lp learned; do tail -n +2 "$OUT/seed${N}/$d/$kind.csv"; done
    } > "$OUT/seed${N}/$kind.csv"
  done
  echo "  fold $N done: $(tail -n +2 "$OUT/seed${N}/summary.csv" | wc -l) summary rows" | tee -a "$LOG"
done

# ---- (2) merge all folds (prepend seed column so folds are distinguishable) ----
echo "--- merge all folds ---" | tee -a "$LOG"
for kind in raw summary; do
  first=1; : > "$OUT/$kind.csv"
  for N in $SEEDS; do
    f="$OUT/seed${N}/$kind.csv"
    [[ -f "$f" ]] || { echo "  !! missing $f" | tee -a "$LOG"; continue; }
    if [[ $first -eq 1 ]]; then { printf 'seed,'; head -1 "$f"; } >> "$OUT/$kind.csv"; first=0; fi
    tail -n +2 "$f" | sed "s/^/${N},/" >> "$OUT/$kind.csv"
  done
done
echo "=== done $(date -u +%FT%TZ)  summary=$OUT/summary.csv "\
"($(tail -n +2 "$OUT/summary.csv" | wc -l) rows) ===" | tee -a "$LOG"
