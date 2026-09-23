#!/bin/bash
# unified_v6: one batch, one COMMITTED code version, every local axis, no coverage gap.
#
# v6 exists for one reason: unified_v5 ran the 2f_topN (Dump-N) family on orig only,
# which left the database-size paragraph (main.tex:553) unable to check its "Skel+500
# from -31% to +35%" clause if that clause meant Dump-500. Running those cells as an
# addendum would put them in a different machine state, so absolute numbers could not be
# quoted alongside the rest. Re-running the whole matrix in one window is the only way to
# keep every table mutually comparable, which is the standing requirement for this study.
#
# Differences from unified_v5, and nothing else:
#   1. family C carries 12 strategies instead of 8 (the 4 Dump-N budgets are added).
#      Their inputs come from tools/gen_freqdump_layouts.sh, which must run first.
#   2. the resume threshold rises from 3000 to 3600 rows, because a complete seed is
#      now about 3940 raw rows rather than 3327.
# Reps, arms, workloads, seeds and the cold gate are untouched, so every cell v5 also
# measured is protocol-identical and v5 -> v6 reproduction is a clean drift check.
#
# Provenance note: v5 was launched with uncommitted code, so its batch.log recorded a
# HEAD that did not contain the arms it was measuring. v6 must be launched from a clean
# tree so the HEAD line below is true. Check `git status --short` before starting.
#
# Per seed, three invocations into one output tree (the repo's "one batch" shape,
# as in tools/native_headtohead_multi.sh):
#   main/   family A -- A,B,C,C_hit x orig x 14 strategies x 4 arms   (56 cells)
#   lp/     family B -- lp_sorted/lp_shuf, pread-only, no baseline     (8 cells)
#   layout/ family C -- A,B,C x vacuum,ta,1gb x 12 strategies x 2 arms (108 cells)
#
# About 3940 raw rows per seed, roughly 3.5 hours for 10 seeds at the 0.289 s/row this
# machine sustained through v5. That window is longer than one machine state, so the
# batch measures its own drift rather than assuming it away: every raw row carries a ts
# column, the baseline is re-measured in every (workload,db,seed) cell, run_experiment.py
# is rep-major so drift spreads across cells, and 2f_slru is the established anchor.
#
# Usage: tools/run_unified_v6.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/unified_v6
source tools/unified_v6_matrix.sh
mkdir -p "$OUT"
LOG="$OUT/batch.log"
ts() { date -u +%FT%TZ; }

echo "=== unified_v6 start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
echo "=== HEAD: $(git rev-parse --short HEAD) ===" | tee -a "$LOG"
echo "=== famA: $WL_A x orig x $STRATS_A ===" | tee -a "$LOG"
echo "=== famB: $WL_A x orig x $STRATS_LP (pread-only) ===" | tee -a "$LOG"
echo "=== famC: $WL_C x $DBS_C x $STRATS_C ===" | tee -a "$LOG"

# Gate first: never start a three-hour run with a missing input.
echo "--- input gate $(ts) ---" | tee -a "$LOG"
if ! tools/check_unified_v6_inputs.sh $SEEDS >>"$LOG" 2>&1; then
  echo "!!! INPUT GATE FAILED -- see $LOG. Nothing measured." | tee -a "$LOG"; exit 1
fi
echo "--- input gate OK $(ts) ---" | tee -a "$LOG"

DBS_C_CSV=$(echo "$DBS_C" | tr ' ' ',')

for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 3600 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s START $(ts) ---" | tee -a "$LOG"

  echo "--- seed $s famA main $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db orig --workload "$WL_A" \
       --strategy "$STRATS_A" \
       --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
       --async-win-reps "$WIN_REPS" --async-bulk-reps "$BULK_REPS" \
       --baseline-reps "$BASELINE_REPS" \
       --outdir "$OUT/seed${pad}/main" >>"$LOG" 2>&1; then
    echo "!!! seed $s famA FAILED $(ts) -- STOP" | tee -a "$LOG"; exit 1
  fi

  echo "--- seed $s famB lp (pread-only, no baseline) $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db orig --workload "$WL_A" \
       --strategy "$STRATS_LP" --no-baseline \
       --pread-reps "$PREAD_REPS" --async-reps 0 \
       --outdir "$OUT/seed${pad}/lp" >>"$LOG" 2>&1; then
    echo "!!! seed $s famB FAILED $(ts) -- STOP" | tee -a "$LOG"; exit 1
  fi

  echo "--- seed $s famC layout+size $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --db "$DBS_C_CSV" --workload "$WL_C" \
       --strategy "$STRATS_C" \
       --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
       --baseline-reps "$BASELINE_REPS" \
       --outdir "$OUT/seed${pad}/layout" >>"$LOG" 2>&1; then
    echo "!!! seed $s famC FAILED $(ts) -- STOP" | tee -a "$LOG"; exit 1
  fi

  # merge the 3 families for this seed (header once, then all data rows)
  for kind in raw summary; do
    { head -1 "$OUT/seed${pad}/main/$kind.csv"
      for d in main lp layout; do tail -n +2 "$OUT/seed${pad}/$d/$kind.csv"; done
    } > "$OUT/seed${pad}/$kind.csv"
  done
  echo "--- seed $s DONE $(ts)  raw=$(tail -n +2 "$raw" | wc -l) rows," \
       "summary=$(tail -n +2 "$OUT/seed${pad}/summary.csv" | wc -l) rows ---" | tee -a "$LOG"
done

# ---- one cross-seed summary view (prepend seed so seeds stay distinguishable) ----
# summary only, not raw: tools/stats_uncertainty.py pools the per-seed raw.csv files
# by design (each strategy is compared to the baseline of its OWN seed, which is what
# controls drift), and so does the ts drift regression. A cross-seed raw.csv would be
# 4 MB of duplicate with a schema no consumer wants.
echo "--- merge all seeds $(ts) ---" | tee -a "$LOG"
first=1; : > "$OUT/summary.csv"
for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  f="$OUT/seed${pad}/summary.csv"
  [ -f "$f" ] || { echo "  !! missing $f" | tee -a "$LOG"; continue; }
  if [ $first -eq 1 ]; then { printf 'seed,'; head -1 "$f"; } >> "$OUT/summary.csv"; first=0; fi
  tail -n +2 "$f" | sed "s/^/${s},/" >> "$OUT/summary.csv"
done
echo "=== unified_v6 complete $(ts)  summary=$OUT/summary.csv" \
     "($(tail -n +2 "$OUT/summary.csv" | wc -l) rows) ===" | tee -a "$LOG"
