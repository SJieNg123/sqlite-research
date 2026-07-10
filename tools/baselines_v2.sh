#!/bin/bash
# baselines_v2 — reimplemented prior-art baseline arms on a common substrate.
#
# ⚠️ CONFIG ONLY until the cell list is signed off. Two arm families:
#   libprefetch-style: lp_sorted, lp_shuf   (delivery-ORDER mechanism; pread-only,
#                        because libprefetch is synchronous — async is meaningless)
#   learned-style:     learned_14, learned_28  (ml_static = Markov marginal top-N,
#                        trained on seed 2, measured on the master = seed 1; a CONTENT
#                        question, so async + pread both run)
# References (same batch, paired comparison): 2f_top14, 2f_top28, 2e_K10, baseline, and
# 2f_slru ASYNC-ONLY (its pread == lp_sorted byte-identical, already in (1); its async fq is
# the Sec 4.4 machine-stability anchor ~126-130 us -> drift calibration vs results/main).
#
# Cell count = 6 (lp pread) + 30 (learned+refs x {pread,async}) + 3 (baseline) + 3 (2f_slru
# async) = 42. Warmup is UNIFORM across every cell: the harness always runs rep 1 as a
# discarded warmup (dropped in aggregate), for all arms -> paired comparison is protocol-
# isomorphic by construction.
#
# Measure on the MASTER stream (no --seed): learned trains on seed 2 -> no leakage
# (train 2 != measure 1). Output: results/baselines_v2/ (kept out of results/competitive,
# which holds published-number provenance).
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

OUT=results/baselines_v2
WORKLOADS="A,B,C"
DB="orig"
PREAD_REPS="${PREAD_REPS:-10}"
ASYNC_REPS="${ASYNC_REPS:-10}"
LOG="$OUT/batch.log"
mkdir -p "$OUT"
echo "=== baselines_v2 batch $(date -u +%FT%TZ) ===" | tee -a "$LOG"

# (0) prep: (re)generate the learned ml_static hotsets (they carry _seed2 -> gitignored
# as regenerable). Trains on seed 2; measured on the master (=seed 1) below -> no leakage.
DB=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.DBS['orig']))")
CL=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.CLASSIFY['orig']))")
echo "--- prep: learned hotsets (train seed 2) ---" | tee -a "$LOG"
for w in a b c; do
  W=$(echo "$w" | tr a-z A-Z)
  python3 strategies/learned/gen_pageseq.py "$DB" "$CL" "workloads/workload_${w}_2.txt" "$OUT/seq_${w}.csv" >>"$LOG" 2>&1
  python3 strategies/learned/train_markov.py "$OUT/seq_${w}.csv" "$OUT/mk_${w}" \
    --w "$W" --layout orig --train-seed 2 --hotset-n 14,28 >>"$LOG" 2>&1
done

# (1) libprefetch-style arms — pread-only (synchronous mechanism), no baseline here
echo "--- lp arms (pread-only) ---" | tee -a "$LOG"
python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" --strategy lp_sorted,lp_shuf --no-baseline \
  --pread-reps "$PREAD_REPS" --async-reps 0 \
  --outdir "$OUT" >>"$LOG" 2>&1

# (2) learned-style + reference arms — async + pread (baseline auto-runs)
echo "--- learned + references (async + pread) ---" | tee -a "$LOG"
python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" \
  --strategy learned_14,learned_28,2f_top14,2f_top28,2e_K10 \
  --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
  --outdir "$OUT" >>"$LOG" 2>&1

# (3) 2f_slru full-dump reference -- ASYNC ONLY (pread == lp_sorted byte-identical, in (1);
# async fq = Sec 4.4 machine-stability anchor). pread-reps 0 -> one discarded pread warmup only.
echo "--- 2f_slru (async only) ---" | tee -a "$LOG"
python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" --strategy 2f_slru --no-baseline \
  --pread-reps 0 --async-reps "$ASYNC_REPS" \
  --outdir "$OUT" >>"$LOG" 2>&1

echo "=== done $(date -u +%FT%TZ)  raw=$OUT/raw.csv summary=$OUT/summary.csv ===" | tee -a "$LOG"
