#!/bin/bash
# unified_v5 -- one contiguous batch, one code version, covering every locally
# runnable cell the paper quotes.
#
# Why: unified_v4 already gave Tables 3-6 one batch, but three seams remain.
#   (1) main.tex:505 carries an explicit disclaimer, "the layout-pair batch, whose
#       absolute values are not comparable with Table~\ref{tab:e2e-ac}".
#   (2) the C_hit control (main.tex:606) is its own batch, results/c_hit{,_v2}.
#   (3) the database-size paragraph is its own batch, results/size_1gb.
# Folding all three in lets every absolute microsecond in the paper be quoted
# against one shared baseline.
#
# It also adds the two coalesced delivery arms that answer the "why not one bulk
# posix_fadvise(WILLNEED)?" objection. async_bulk is the naive one hint per
# contiguous range; async_win re-cuts each hint to the kernel readahead window
# (32 pages here, read_ahead_kb=128) so the hints actually land. On this host a
# single hint delivers only min(range_pages, 32) pages regardless of its length,
# so the two arms differ by about 70x in delivered pages at nearly equal cost.
#
# Hotsets are NOT regenerated: the frozen per-seed inputs are already post
# tie-break-fix, exactly as tools/run_unified_v4.sh:12-17 records. The only new
# inputs are freqdump_C_hit_orig_N{100,500}_seed*, generated from the existing
# frozen hotpages_c_hit_seed* by the same gen_freqdump.py call tools/run_chit.sh
# uses, so C_hit carries the same 14-strategy set as A/B/C.
#
# Per seed, three invocations into one output tree (the repo's "one batch" shape,
# as in tools/native_headtohead_multi.sh):
#   main/   family A -- A,B,C,C_hit x orig x 14 strategies x 4 arms  (56 cells)
#   lp/     family B -- lp_sorted/lp_shuf, pread-only, no baseline    (8 cells)
#   layout/ family C -- A,B,C x vacuum,ta,1gb x 8 strategies x 2 arms (72 cells)
# Family B is separate because coalescing sorts offsets, which would silently turn
# lp_shuf into lp_sorted; run_experiment.py refuses that combination outright.
#
# About 3320 raw rows per seed, about 18 minutes per seed, about 3 hours for 10.
# That window is longer than one machine state, so the batch measures its own
# drift rather than assuming it away: every raw row carries a ts column, the
# baseline is re-measured in every (workload,db,seed) cell, run_experiment.py is
# rep-major so drift spreads across cells, and 2f_slru is the established anchor.
#
# Usage: tools/run_unified_v5.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/unified_v5
source tools/unified_v5_matrix.sh
mkdir -p "$OUT"
LOG="$OUT/batch.log"
ts() { date -u +%FT%TZ; }

echo "=== unified_v5 start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
echo "=== HEAD: $(git rev-parse --short HEAD) ===" | tee -a "$LOG"
echo "=== famA: $WL_A x orig x $STRATS_A ===" | tee -a "$LOG"
echo "=== famB: $WL_A x orig x $STRATS_LP (pread-only) ===" | tee -a "$LOG"
echo "=== famC: $WL_C x $DBS_C x $STRATS_C ===" | tee -a "$LOG"

# Gate first: never start a three-hour run with a missing input.
echo "--- input gate $(ts) ---" | tee -a "$LOG"
if ! tools/check_unified_v5_inputs.sh $SEEDS >>"$LOG" 2>&1; then
  echo "!!! INPUT GATE FAILED -- see $LOG. Nothing measured." | tee -a "$LOG"; exit 1
fi
echo "--- input gate OK $(ts) ---" | tee -a "$LOG"

DBS_C_CSV=$(echo "$DBS_C" | tr ' ' ',')

for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  raw="$OUT/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 3000 ]; then
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
echo "=== unified_v5 complete $(ts)  summary=$OUT/summary.csv" \
     "($(tail -n +2 "$OUT/summary.csv" | wc -l) rows) ===" | tee -a "$LOG"
