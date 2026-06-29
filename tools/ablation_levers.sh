#!/bin/bash
# S1 three-lever ablation (review item R2 W4 / CONSENSUS-2 #9).
# Question: is the headline win (C x 2e_K10) driven by PAGE-TYPE awareness, or by
# ACCESS-FREQUENCY leaf selection? 2e_K's hotset = resident interior u top-K hot leaves,
# i.e. set-theoretically  2e_K = 2d  u  leaf_freq_K.  We split it and add a control:
#   2d            interior-only            -> page-type lever (ii)
#   leaf_freq_K   top-K hot leaves only    -> access-frequency lever (iii)
#   leaf_rand_K   equal-count random leaves (subtype-matched) -> null control for (iii)
#   2e_K          interior u hot leaves    -> combined (ii)+(iii)
# baseline auto-runs as the denominator. orig-vs-ta isolates the layout-clustering lever (i):
# on ta the interior is collocated, so the same selection rule pays a cheaper deliver_us.
#
# All arms run in ONE batch per seed so absolute us are directly comparable (same machine
# state); cross-seed bootstrap CI comes from tools/stats_uncertainty.py over seeds 1..10.
# No --regen-hotsets needed: leaf_freq derives from the existing frozen hot2e_*_K<K>.csv,
# leaf_rand is generated deterministically from classify, 2d/2e from existing hotpages/hot2e.
#
# Usage: tools/ablation_levers.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Resumable: a seed whose raw.csv already looks complete is skipped.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
CORE=results/ablation          # K10 core: A,B,C x orig,ta x {2d,leaf_rand,leaf_freq,2e}
K500=results/ablation_k500     # A-only K=500 add (A is not saturated at K=10)
mkdir -p "$CORE" "$K500"
LOG="$CORE/sweep.log"
REPS="--pread-reps 5 --async-reps 8 --baseline-reps 8"
ts() { date -u +%FT%TZ; }

echo "=== ablation start $(ts)  seeds: $SEEDS ===" | tee -a "$LOG"
for n in $SEEDS; do
  pad=$(printf '%02d' "$n")

  # --- K10 core ---------------------------------------------------------------
  raw="$CORE/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 400 ]; then
    echo "--- seed $n core SKIP ($(wc -l < "$raw") rows) $(ts) ---" | tee -a "$LOG"
  else
    echo "--- seed $n core $(ts) ---" | tee -a "$LOG"
    if ! python3 run_experiment.py run --seed "$n" --db orig,ta --workload A,B,C \
        --strategy 2d,leaf_rand_K10,leaf_freq_K10,2e_K10 $REPS \
        --outdir "$CORE/seed${pad}" >>"$LOG" 2>&1; then
      echo "!!! seed $n CORE FAILED $(ts)" | tee -a "$LOG"; continue
    fi
  fi

  # --- A-only K500 add --------------------------------------------------------
  raw5="$K500/seed${pad}/raw.csv"
  if [ -f "$raw5" ] && [ "$(wc -l < "$raw5")" -gt 80 ]; then
    echo "--- seed $n k500 SKIP ($(wc -l < "$raw5") rows) $(ts) ---" | tee -a "$LOG"
  else
    echo "--- seed $n k500 $(ts) ---" | tee -a "$LOG"
    if ! python3 run_experiment.py run --seed "$n" --db orig,ta --workload A \
        --strategy leaf_rand_K500,leaf_freq_K500,2e_K500 $REPS \
        --outdir "$K500/seed${pad}" >>"$LOG" 2>&1; then
      echo "!!! seed $n K500 FAILED $(ts)" | tee -a "$LOG"; continue
    fi
  fi

  rows=$( [ -f "$raw" ] && wc -l < "$raw" || echo 0 )
  echo "--- seed $n DONE $(ts)  core_rows=$rows ---" | tee -a "$LOG"
done
echo "=== ablation complete $(ts) ===" | tee -a "$LOG"
