#!/bin/bash
# baselines_v2 — reimplemented prior-art baseline arms on a common substrate.
#
# ⚠️ CONFIG ONLY. Phase 3 (validation) does NOT execute this. It is the batch
# definition for the future run once all v2 baseline arms (libprefetch-style now;
# learned-style later) are in place. Run it explicitly during an announced window.
#
# Cells (this batch): {lp_sorted, lp_shuf} + reference arms {2f_slru, 2e_K10, baseline}
#   x workloads {A,B,C} x layout {orig} x arm {pread}.
# libprefetch is a SYNCHRONOUS system -> async arm is meaningless for it, so async
# is disabled (--async-reps 0; one discarded warmup remains, no async summary row).
#
# Primary metric: deliver_us (batch load time). fq is a control (equal within noise
# across lp_sorted/lp_shuf/2f_slru confirms full delivery). lp_sorted MUST match
# 2f_slru (content+order byte-identical) -> built-in faithfulness cross-check.
#
# Output: results/baselines_v2/  (kept out of results/competitive/, which holds
# published-number provenance).
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

OUT=results/baselines_v2
STRATS="lp_sorted,lp_shuf,2f_slru,2e_K10"   # baseline auto-runs (no --no-baseline)
WORKLOADS="A,B,C"
DB="orig"
PREAD_REPS="${PREAD_REPS:-10}"              # match results/main pread reps for comparability
LOG="$OUT/batch.log"

mkdir -p "$OUT"
echo "=== baselines_v2 batch $(date -u +%FT%TZ) ===" | tee -a "$LOG"
echo "strategies=$STRATS workloads=$WORKLOADS db=$DB pread_reps=$PREAD_REPS (async disabled)" | tee -a "$LOG"

python3 run_experiment.py run \
  --workload "$WORKLOADS" --db "$DB" --strategy "$STRATS" \
  --pread-reps "$PREAD_REPS" --async-reps 0 \
  --outdir "$OUT" >>"$LOG" 2>&1

echo "=== done $(date -u +%FT%TZ)  raw=$OUT/raw.csv summary=$OUT/summary.csv ===" | tee -a "$LOG"
