#!/bin/bash
# Pre-flight gate for tools/run_unified_v5.sh: prove every frozen hotset input the
# batch will touch is present BEFORE the first drop-caches, so a missing file costs
# seconds instead of surfacing three hours in.
#
# It does not reimplement the filename rules. It runs the real --dry-run for every
# (family, workload, db, seed) the batch will run, which walks the same select_pages()
# -> _require_hotset() path the measured run does, so the gate cannot drift from it.
#
# Usage: tools/check_unified_v5_inputs.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Exit 0 = every input present. Exit 1 = prints each missing input and the cell.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
source tools/unified_v5_matrix.sh

fails=0
check() {   # check <label> <extra run_experiment.py args...>
  local label="$1"; shift
  local out
  if ! out=$(python3 run_experiment.py run --dry-run --yes "$@" 2>&1); then
    echo "MISSING  $label"
    echo "$out" | grep -iE 'missing|error|no such' | sed 's/^/         /'
    fails=$((fails + 1))
  fi
}

echo "=== unified_v5 input gate  $(date -u +%FT%TZ)  seeds: $SEEDS ==="
for s in $SEEDS; do
  check "seed$s famA orig"  --seed "$s" --db orig --workload "$WL_A" --strategy "$STRATS_A" \
        --async-win-reps 10 --async-bulk-reps 5
  check "seed$s famB lp"    --seed "$s" --db orig --workload "$WL_A" --strategy "$STRATS_LP" \
        --no-baseline --async-reps 0
  for db in $DBS_C; do
    check "seed$s famC $db" --seed "$s" --db "$db" --workload "$WL_C" --strategy "$STRATS_C"
  done
done

if [ "$fails" -ne 0 ]; then
  echo "=== GATE FAILED: $fails cell group(s) missing inputs -- not starting the batch ==="
  exit 1
fi
echo "=== gate OK: every input present for seeds $SEEDS ==="
