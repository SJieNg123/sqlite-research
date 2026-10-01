#!/bin/bash
# Re-measure the cells whose hot2e hotset changed under the (-count,pageno) tie-break
# fix. Each batch carries its own baseline + 2f_slru anchor so improvement% is computed
# vs a same-batch baseline (drift-robust). Hotsets already regenerated in place.
#   (M) master single-instantiation  -> results/tiebreak_fix/master/
#   (S) cross-seed 10 seeds           -> results/tiebreak_fix/seeds/seedNN/
#   (H) C_hit post-fix, orig, 10 seeds-> results/c_hit_v2/seedNN/
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1
REPS="--pread-reps 10 --async-reps 10 --baseline-reps 10"
OUT=results/tiebreak_fix
mkdir -p "$OUT" results/c_hit_v2
LOG="$OUT/rerun.log"; ts(){ date -u +%FT%TZ; }
echo "=== rerun-tiebreak start $(ts) ===" | tee -a "$LOG"

# ---- (M) master: changed strategies per workload, all 3 layouts ----
# A: only K500 changed. B: K10..K500. C: K10..K100 (K500 unchanged).
echo "--- (M) master A K500 $(ts) ---" | tee -a "$LOG"
python3 run_experiment.py run --workload A --db orig,vacuum,ta \
  --strategy 2e_K500,2f_slru $REPS --outdir "$OUT/master_A" >>"$LOG" 2>&1 || echo "!!M A failed"|tee -a "$LOG"
echo "--- (M) master B K10..K500 $(ts) ---" | tee -a "$LOG"
python3 run_experiment.py run --workload B --db orig,vacuum,ta \
  --strategy 2e_K10,2e_K40,2e_K50,2e_K92,2e_K100,2e_K500,2f_slru $REPS --outdir "$OUT/master_B" >>"$LOG" 2>&1 || echo "!!M B failed"|tee -a "$LOG"
echo "--- (M) master C K10..K100 $(ts) ---" | tee -a "$LOG"
python3 run_experiment.py run --workload C --db orig,vacuum,ta \
  --strategy 2e_K10,2e_K40,2e_K50,2e_K92,2e_K100,2f_slru $REPS --outdir "$OUT/master_C" >>"$LOG" 2>&1 || echo "!!M C failed"|tee -a "$LOG"

# merge master subdirs
for kind in raw summary; do
  { head -1 "$OUT/master_A/$kind.csv"; for d in master_A master_B master_C; do tail -n +2 "$OUT/$d/$kind.csv"; done; } > "$OUT/master_$kind.csv"
done
echo "--- (M) merged: $(tail -n +2 "$OUT/master_summary.csv"|wc -l) rows $(ts) ---" | tee -a "$LOG"

# ---- (S) cross-seed: 2e_K10 (B,C) + 2e_K500 (A,B); rerun A/B/C all 3 layouts ----
for s in 1 2 3 4 5 6 7 8 9 10; do
  pad=$(printf '%02d' "$s"); raw="$OUT/seeds/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 100 ]; then echo "--- S seed $s SKIP $(ts) ---"|tee -a "$LOG"; continue; fi
  echo "--- (S) seed $s $(ts) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --workload A,B,C --db orig,vacuum,ta \
    --strategy 2e_K10,2e_K500,2f_slru $REPS --outdir "$OUT/seeds/seed${pad}" >>"$LOG" 2>&1 \
    || echo "!!S seed $s failed" | tee -a "$LOG"
done

# ---- (H) C_hit post-fix: 2e_K10/K40/K92/K500 + 2f_slru, orig, 10 seeds ----
for s in 1 2 3 4 5 6 7 8 9 10; do
  pad=$(printf '%02d' "$s"); raw="results/c_hit_v2/seed${pad}/raw.csv"
  if [ -f "$raw" ] && [ "$(wc -l < "$raw")" -gt 100 ]; then echo "--- H seed $s SKIP $(ts) ---"|tee -a "$LOG"; continue; fi
  echo "--- (H) C_hit seed $s $(ts) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --workload C_hit --db orig \
    --strategy 2e_K10,2e_K40,2e_K92,2e_K500,2f_slru $REPS --outdir "results/c_hit_v2/seed${pad}" >>"$LOG" 2>&1 \
    || echo "!!H seed $s failed" | tee -a "$LOG"
done
echo "=== rerun-tiebreak complete $(ts) ===" | tee -a "$LOG"
