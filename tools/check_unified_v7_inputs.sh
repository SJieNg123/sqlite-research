#!/bin/bash
# Pre-flight gate for tools/run_unified_v7.sh, as tools/check_unified_v6_inputs.sh is for v6:
# it runs the real --dry-run for every (family, workload, db, seed) the batch will run, which
# walks the same select_pages() -> _require_hotset() path the measured run does.
#
# Usage: tools/check_unified_v7_inputs.sh [seed-list]   (default "1 2 3 4 5 6 7 8 9 10")
# Exit 0 = every input present. Exit 1 = prints each missing input and the cell.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1

SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
source tools/unified_v7_matrix.sh

fails=0
check() {   # check <label> <extra run_experiment.py args...>
  local label="$1"; shift
  local out
  if ! out=$(python3 run_experiment.py run --dry-run --yes "$@" 2>&1); then
    echo "MISSING  $label"
    echo "$out" | grep -iE 'missing|error|no such|refusing' | sed 's/^/         /'
    fails=$((fails + 1))
  fi
}

echo "=== unified_v7 input gate  $(date -u +%FT%TZ)  seeds: $SEEDS ==="
for s in $SEEDS; do
  check "seed$s famA orig"  --seed "$s" --db orig --workload "$WL_A" --strategy "$STRATS_A" \
        --async-win-reps 10 --async-bulk-reps 5
  check "seed$s famB lp"    --seed "$s" --db orig --workload "$WL_A" --strategy "$STRATS_LP" \
        --no-baseline --async-reps 0
  for db in $DBS_C; do
    check "seed$s famC $db" --seed "$s" --db "$db" --workload "$WL_C" --strategy "$STRATS_C" \
          --async-win-reps 10
  done
  check "seed$s famD top15" --seed "$s" --db orig --workload "$WL_D" --strategy "$STRATS_D" \
        --no-baseline --async-win-reps 10 --async-bulk-reps 5
  check "seed$s famE whole" --seed "$s" --db orig --workload "$WL_E" --strategy "$STRATS_E" \
        --no-baseline --pread-reps 0 --async-reps 0 --async-win-reps 10 --populate-reps 10
done

if [ "$fails" -ne 0 ]; then
  echo "=== GATE FAILED: $fails cell(s) missing inputs ==="; exit 1
fi
echo "=== GATE OK: every input present ==="
