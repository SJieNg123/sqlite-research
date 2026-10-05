#!/bin/bash
# unified_v7: one batch, one committed code version, every local axis, no coverage gap.
#
# v7 exists because three measurements the paper now needs would otherwise be addenda in a
# different machine state, which is the seam this line of batches exists to remove:
#   1. family C (vacuum, ta, 1gb) also runs the window-chunked arm, so the 10x database and
#      the layouts are measured under both delivery mechanisms.
#   2. family D: Dump-15 on Tail-Hit, the matched budget for Skel+10 there
#      (results/matched_budget/PREREG.md, whose rule applies to v7 unchanged).
#   3. family E: the profile-free whole-file baselines, window-chunked hints over all 26,331
#      pages and a synchronous MAP_POPULATE (results/pilot_whole_file_delivery).
# Everything else repeats unified_v6: same reps, arms, workloads, seeds, cold gate, so the
# shared cells are a drift check against v6. e2e_warm charges parse_us to the coalesced arms
# (run_experiment.py since 111b8ae).
#
# Per seed, five invocations into one output tree:
#   main/   family A -- A,B,C,C_hit x orig x 14 strategies x 4 arms        (as v6)
#   lp/     family B -- lp_sorted/lp_shuf, pread-only, no baseline          (as v6)
#   layout/ family C -- A,B,C x vacuum,ta,1gb x 12 strategies x 3 arms     (+ async_win)
#   top15/  family D -- C_hit x orig x 2f_top15 x 4 arms, no baseline      (new)
#   whole/  family E -- A,B,C,C_hit x orig x whole_file x async_win,populate, no baseline (new)
# Families B, D and E use family A's baseline: same seed, same window, merged per seed.
# About 5,260 raw rows per seed, roughly 5 hours for 10 seeds.
#
# Usage: tools/run_unified_v7.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1
SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/unified_v7
source tools/unified_v7_matrix.sh
ts() { date -u +%FT%TZ; }

# The HEAD line must be true: refuse to run from a dirty tree.
if [ -n "$(git status --short -- run_experiment.py pipeline tools)" ]; then
  echo "!!! uncommitted changes in run_experiment.py, pipeline/ or tools/ -- commit first"; exit 1
fi
mkdir -p "$OUT"
LOG="$OUT/batch.log"
echo "=== unified_v7 start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
echo "=== HEAD: $(git rev-parse --short HEAD) ===" | tee -a "$LOG"
echo "=== famA: $WL_A x orig x $STRATS_A ===" | tee -a "$LOG"
echo "=== famB: $WL_A x orig x $STRATS_LP (pread-only) ===" | tee -a "$LOG"
echo "=== famC: $WL_C x $DBS_C x $STRATS_C (+async_win) ===" | tee -a "$LOG"
echo "=== famD: $WL_D x orig x $STRATS_D ===" | tee -a "$LOG"
echo "=== famE: $WL_E x orig x $STRATS_E (async_win, populate) ===" | tee -a "$LOG"

echo "--- input gate $(ts) ---" | tee -a "$LOG"
if ! tools/check_unified_v7_inputs.sh $SEEDS >>"$LOG" 2>&1; then
  echo "!!! INPUT GATE FAILED -- see $LOG. Nothing measured." | tee -a "$LOG"; exit 1
fi
echo "--- input gate OK $(ts) ---" | tee -a "$LOG"

DBS_C_CSV=$(echo "$DBS_C" | tr ' ' ',')

fam() {   # fam <seed> <label> <subdir> <run_experiment.py args...>
  local s="$1" label="$2" sub="$3"; shift 3
  local pad; pad=$(printf '%02d' "$s")
  echo "--- seed $s $label $(ts) ---" | tee -a "$LOG"
  if ! python3 run_experiment.py run --seed "$s" --outdir "$OUT/seed${pad}/$sub" "$@" >>"$LOG" 2>&1; then
    echo "!!! seed $s $label FAILED $(ts) -- STOP" | tee -a "$LOG"; exit 1
  fi
}

for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 5000 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s START $(ts) ---" | tee -a "$LOG"
  fam "$s" "famA main" main --db orig --workload "$WL_A" --strategy "$STRATS_A" \
      --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
      --async-win-reps "$WIN_REPS" --async-bulk-reps "$BULK_REPS" --baseline-reps "$BASELINE_REPS"
  fam "$s" "famB lp" lp --db orig --workload "$WL_A" --strategy "$STRATS_LP" --no-baseline \
      --pread-reps "$PREAD_REPS" --async-reps 0
  fam "$s" "famC layout+size" layout --db "$DBS_C_CSV" --workload "$WL_C" --strategy "$STRATS_C" \
      --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" --async-win-reps "$WIN_REPS" \
      --baseline-reps "$BASELINE_REPS"
  fam "$s" "famD top15" top15 --db orig --workload "$WL_D" --strategy "$STRATS_D" --no-baseline \
      --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
      --async-win-reps "$WIN_REPS" --async-bulk-reps "$BULK_REPS"
  fam "$s" "famE whole" whole --db orig --workload "$WL_E" --strategy "$STRATS_E" --no-baseline \
      --pread-reps 0 --async-reps 0 --async-win-reps "$WIN_REPS" --populate-reps "$POPULATE_REPS"

  # merge the five families for this seed (header once, then all data rows)
  for kind in raw summary; do
    { head -1 "$OUT/seed${pad}/main/$kind.csv"
      for d in main lp layout top15 whole; do tail -n +2 "$OUT/seed${pad}/$d/$kind.csv"; done
    } > "$OUT/seed${pad}/$kind.csv"
  done
  echo "--- seed $s DONE $(ts)  raw=$(tail -n +2 "$raw" | wc -l) rows," \
       "summary=$(tail -n +2 "$OUT/seed${pad}/summary.csv" | wc -l) rows ---" | tee -a "$LOG"
done

# ---- one cross-seed summary view (prepend seed so seeds stay distinguishable) ----
echo "--- merge all seeds $(ts) ---" | tee -a "$LOG"
first=1; : > "$OUT/summary.csv"
for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  f="$OUT/seed${pad}/summary.csv"
  [ -f "$f" ] || { echo "  !! missing $f" | tee -a "$LOG"; continue; }
  if [ $first -eq 1 ]; then { printf 'seed,'; head -1 "$f"; } >> "$OUT/summary.csv"; first=0; fi
  tail -n +2 "$f" | sed "s/^/${s},/" >> "$OUT/summary.csv"
done
python3 tools/stats_uncertainty.py --seeds "$OUT"/seed[0-9][0-9] \
  --out "$OUT/uncertainty.csv" --md "$OUT/uncertainty.md" >>"$LOG" 2>&1
echo "=== unified_v7 complete $(ts)  summary=$OUT/summary.csv" \
     "($(tail -n +2 "$OUT/summary.csv" | wc -l) rows) ===" | tee -a "$LOG"
