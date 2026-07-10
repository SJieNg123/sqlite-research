#!/bin/bash
# baselines_v2 — reimplemented prior-art baseline arms on a common substrate.
#
# ⚠️ CONFIG ONLY until the cell list is signed off. Two arm families:
#   libprefetch-style: lp_sorted, lp_shuf   (delivery-ORDER mechanism; pread-only,
#                        because libprefetch is synchronous — async is meaningless)
#   learned_markov:    learned_markov_14, learned_markov_28  (Chen-inspired first-order Markov
#                        transition model; hotset from finite-horizon expected-visit scores;
#                        LOSO held-out: measured on the master = test seed 1, trained on 2..10;
#                        a CONTENT question, so async + pread both run)
# References (same batch, paired comparison): 2f_top14, 2f_top28, 2e_K10, baseline, and
# 2f_slru ASYNC-ONLY (its pread == lp_sorted byte-identical, already in (1); its async fq is
# the Sec 4.4 machine-stability anchor ~126-130 us -> drift calibration vs results/main).
# frequency_14/28 are generated in prep for OFFLINE analysis (Jaccard/coverage), not measured.
#
# Cell count = 6 (lp pread) + 30 (learned_markov+refs x {pread,async}) + 3 (baseline) + 3
# (2f_slru async) = 42. Warmup is UNIFORM across every cell: the harness always runs rep 1 as
# a discarded warmup (dropped in aggregate) -> paired comparison is protocol-isomorphic.
#
# ⚠️ FORMAL BATCH NOT RUN as part of the learned rework. This config measures the master
# (test seed 1); full LOSO over all test seeds is the extended protocol. Output:
# results/baselines_v2/ (kept out of results/competitive, published-number provenance).
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

# (0) prep: (re)generate the learned_markov + frequency hotsets (they carry _test<T> ->
# gitignored as regenerable). LOSO: measured on the master (= test seed 1) -> train on the
# complement (seeds 2..10). Hotsets are budget-matched to 2f_topN (N=14,28).
# NB: use DBPATH/CLPATH (resolved file paths) for the generators; --db below wants the KEY.
DBPATH=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.DBS['orig']))")
CLPATH=$(python3 -c "import run_experiment as R; print(R.resolve_pointer(R.CLASSIFY['orig']))")
TEST_SEED="${TEST_SEED:-1}"
TRAIN_SEEDS="${TRAIN_SEEDS:-2 3 4 5 6 7 8 9 10}"   # LOSO complement of test seed 1
echo "--- prep: learned_markov + frequency (LOSO test=$TEST_SEED train=$TRAIN_SEEDS) ---" | tee -a "$LOG"
for w in a b c; do
  W=$(echo "$w" | tr a-z A-Z)
  python3 strategies/learned/train_markov.py --db "$DBPATH" --classify "$CLPATH" \
    --w "$W" --layout orig --test-seed "$TEST_SEED" --train-seeds $TRAIN_SEEDS \
    --budget 14,28 --workload-pattern "workloads/workload_${w}_{s}.txt" \
    --artifact-dir "$OUT/models" --runs-dir strategies/access/runs >>"$LOG" 2>&1
done

# Each `run` truncates its outdir's raw/summary, so the three families write to SEPARATE
# subdirs and are merged at the end into $OUT/{raw,summary}.csv.

# (1) libprefetch-style arms — pread-only (synchronous mechanism), no baseline here
echo "--- lp arms (pread-only) ---" | tee -a "$LOG"
python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" --strategy lp_sorted,lp_shuf --no-baseline \
  --pread-reps "$PREAD_REPS" --async-reps 0 \
  --outdir "$OUT/lp" >>"$LOG" 2>&1

# (2) learned_markov + reference arms — async + pread (baseline auto-runs). frequency_N is
# generated in prep for OFFLINE analysis (Jaccard/coverage), not a measured batch arm.
echo "--- learned_markov + references (async + pread) ---" | tee -a "$LOG"
python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" \
  --strategy learned_markov_14,learned_markov_28,2f_top14,2f_top28,2e_K10 \
  --pread-reps "$PREAD_REPS" --async-reps "$ASYNC_REPS" \
  --outdir "$OUT/learned" >>"$LOG" 2>&1

# (3) 2f_slru full-dump reference -- ASYNC ONLY (pread == lp_sorted byte-identical, in (1);
# async fq = Sec 4.4 machine-stability anchor). pread-reps 0 -> one discarded pread warmup only.
echo "--- 2f_slru (async only) ---" | tee -a "$LOG"
python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" --strategy 2f_slru --no-baseline \
  --pread-reps 0 --async-reps "$ASYNC_REPS" \
  --outdir "$OUT/anchor" >>"$LOG" 2>&1

# merge the three families into one raw.csv / summary.csv (header once, then all data rows)
echo "--- merge ---" | tee -a "$LOG"
for kind in raw summary; do
  { head -1 "$OUT/lp/$kind.csv"
    for d in lp learned anchor; do tail -n +2 "$OUT/$d/$kind.csv"; done
  } > "$OUT/$kind.csv"
done
echo "=== done $(date -u +%FT%TZ)  raw=$OUT/raw.csv summary=$OUT/summary.csv "\
"(cells: $(tail -n +2 "$OUT/summary.csv" | wc -l) summary rows) ===" | tee -a "$LOG"
