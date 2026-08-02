#!/bin/bash
# chit_headtohead -- same-batch head-to-head of OUR strategies vs PRIOR-WORK on the synthetic
# C_hit control (pure-hit tail: id in [580001,600000], all keys exist). C_hit already had
# baseline + ours + learned_markov in results/c_hit/, but NEVER libprefetch (lp_sorted/lp_shuf).
# This driver fills that one cell WITH same-batch comparability: it re-measures baseline + our
# anchors + lp + learned in ONE machine state per seed, so every arm's %delta is vs a baseline
# from its own batch (no cross-batch additive drift). Mirrors tools/native_headtohead_multi.sh
# but on the SYNTHETIC executor (run_experiment.py) with PER-SEED hotsets (--seed s -> _seed{s}).
#
# All prereqs (hotpages_c_hit_seed{s}, hot2e_C_hit_orig_K{10,500}_seed{s}, freqdump_C_hit_*_seed{s},
# learned_markov_C_hit_orig_N{14,28}_test{s}) already exist from the frozen C_hit batch -> NO
# --regen-hotsets, NO DROP_CACHES, NO root. Per seed (one machine state): Run-main ours+refs
# (baseline auto), Run-lp lp (pread-only, synchronous), Run-learned learned_markov. Merge 3
# families -> seed{NN}/summary.csv. Writes ONLY to results/chit_headtohead/ (frozen results/c_hit
# untouched).
#
# Usage: tools/chit_headtohead.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose seed{NN}/summary.csv already exists is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

OUT=results/chit_headtohead
SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
PREAD_REPS="${PREAD_REPS:-10}"
ASYNC_REPS="${ASYNC_REPS:-10}"
OURS="2d,2e_K10,2e_K500,2f_slru,2f_top14,2f_top28,layers_92"   # same panel as frozen C_hit matrix
LP="lp_sorted,lp_shuf"
LEARNED="learned_markov_14,learned_markov_28"
AR=strategies/access/runs
SR=strategies/slru/runs
LOG="$OUT/batch.log"
mkdir -p "$OUT"
echo "=== chit_headtohead $(date -u +%FT%TZ)  seeds={$SEEDS} reps=$PREAD_REPS/$ASYNC_REPS ===" | tee -a "$LOG"

require() { [[ -f "$1" ]] || { echo "  !! MISSING required file: $1 -- STOP" | tee -a "$LOG"; exit 1; }; }

for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  sd="$OUT/seed${pad}"
  if [[ -f "$sd/summary.csv" ]]; then
    echo "--- seed $s: SKIP (summary present) ---" | tee -a "$LOG"; continue
  fi

  # ---- fail-loud gate: every per-seed hotset/model an arm reads must exist BEFORE measure ----
  echo "--- seed $s: gate ---" | tee -a "$LOG"
  require "$SR/hotpages_c_hit_seed${s}.csv"                 # 2f_slru + lp source
  require "$AR/hot2e_C_hit_orig_K10_seed${s}.csv"
  require "$AR/hot2e_C_hit_orig_K500_seed${s}.csv"
  require "$AR/freqdump_C_hit_orig_N14_seed${s}.csv"
  require "$AR/freqdump_C_hit_orig_N28_seed${s}.csv"
  require "$AR/learned_markov_C_hit_orig_N14_test${s}.csv"
  require "$AR/learned_markov_C_hit_orig_N28_test${s}.csv"

  echo "--- seed $s: Run-main ours+refs (baseline auto) $(date -u +%FT%TZ) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --db orig --workload C_hit \
    --strategy "$OURS" --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" --baseline-reps "$ASYNC_REPS" \
    --outdir "$sd/main" >>"$LOG" 2>&1 \
    || { echo "  !! Run-main FAILED seed $s -- STOP" | tee -a "$LOG"; exit 1; }

  echo "--- seed $s: Run-lp (pread-only, no baseline) $(date -u +%FT%TZ) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --db orig --workload C_hit --no-baseline \
    --strategy "$LP" --pread-reps "$PREAD_REPS" --async-reps 0 \
    --outdir "$sd/lp" >>"$LOG" 2>&1 \
    || { echo "  !! Run-lp FAILED seed $s -- STOP" | tee -a "$LOG"; exit 1; }

  echo "--- seed $s: Run-learned (--seed $s, no baseline) $(date -u +%FT%TZ) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --db orig --workload C_hit --no-baseline \
    --strategy "$LEARNED" --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
    --outdir "$sd/learned" >>"$LOG" 2>&1 \
    || { echo "  !! Run-learned FAILED seed $s -- STOP" | tee -a "$LOG"; exit 1; }

  # merge the 3 families for this seed (header once, then all data rows)
  for kind in raw summary; do
    { head -1 "$sd/main/$kind.csv"
      for d in main lp learned; do tail -n +2 "$sd/$d/$kind.csv"; done
    } > "$sd/$kind.csv"
  done
  echo "  seed $s done: $(tail -n +2 "$sd/summary.csv" | wc -l) summary rows $(date -u +%FT%TZ)" | tee -a "$LOG"
done

# ---- merge all seeds (prepend seed column) ----
echo "--- merge all seeds ---" | tee -a "$LOG"
for kind in raw summary; do
  first=1; : > "$OUT/$kind.csv"
  for s in $SEEDS; do
    pad=$(printf '%02d' "$s"); f="$OUT/seed${pad}/$kind.csv"
    [[ -f "$f" ]] || { echo "  !! missing $f" | tee -a "$LOG"; continue; }
    if [[ $first -eq 1 ]]; then { printf 'seed,'; head -1 "$f"; } >> "$OUT/$kind.csv"; first=0; fi
    tail -n +2 "$f" | sed "s/^/${s},/" >> "$OUT/$kind.csv"
  done
done
echo "=== done $(date -u +%FT%TZ)  summary=$OUT/summary.csv "\
"($(tail -n +2 "$OUT/summary.csv" | wc -l) rows) ===" | tee -a "$LOG"
