#!/bin/bash
# Native end-to-end run on the OpenWhisk host (paper TODO L453 (1)): the warm-process matrix
# outside OpenWhisk, so the end-to-end ranking there can be compared with unified_v7's.
#
#   A, B, C x orig x Skel (2d), Skel+10 (2e_K10), Dump-14 (2f_top14), Dump (2f_slru)
#   x per-page (async) and window-chunked (async_win) delivery, with the no-prefetch
#   baseline, ten instances, the same reps as unified_v7 family A (10 + 1 warmup each)
#
# Same code path as unified_v7: run_experiment.py rebuilds each page list from the committed
# base inputs with select_pages(), and this script checks every one against the frozen v7
# hotset, so both hosts prefetch the same pages. The warmer is the committed binary v7 used;
# the harness is built here from the committed source. Records are discarded, as in v7.
#
# Usage (repo root of the clone on that host, OpenWhisk stopped):
#   tools/run_ow_native_e2e.sh [seed-list]          # default "1 2 3 4 5 6 7 8 9 10"
# 309 runs per seed, roughly 20 minutes in all. Resumable: a complete seed is skipped.
# Then commit and push results/ow_native_e2e/ with batch.log (the last line prints the commands).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# run_experiment.py defaults ROOT to the workstation path; point it at this clone
export EXPERIMENT_ROOT="$(pwd)"
SEEDS="${*:-1 2 3 4 5 6 7 8 9 10}"
OUT=results/ow_native_e2e
WL="A,B,C"
STRATS="2d,2e_K10,2f_top14,2f_slru"
BH=pipeline/engine/benchmark_harness/benchmark_harness
WARMER=pipeline/engine/prefetch_warmer/src/warmer
mkdir -p "$OUT"
LOG="$OUT/batch.log"
ts() { date -u +%FT%TZ; }
die() { echo "!!! $* $(ts)" | tee -a "$LOG"; exit 1; }

echo "=== ow_native_e2e start $(ts)  host=$(hostname)  seeds: $SEEDS ===" | tee -a "$LOG"
[ -n "$(git status --short -- run_experiment.py pipeline tools)" ] && \
  die "uncommitted changes in run_experiment.py, pipeline/ or tools/: the HEAD line must be true"
echo "=== HEAD $(git rev-parse --short HEAD)  kernel $(uname -r)  $(gcc --version | head -1) ===" | tee -a "$LOG"
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Image}}' 2>/dev/null | grep -qv '^registry:'; then
  die "containers other than the image registry are running: stop OpenWhisk first"
fi

# binaries: the harness from source (untracked), the warmer as committed
gcc -O2 -I pipeline/engine/benchmark_harness -o "$BH" pipeline/engine/benchmark_harness/benchmark_harness.c \
    pipeline/engine/benchmark_harness/sqlite3.c -lpthread -ldl -lm || die "harness build failed"
"$WARMER" >/dev/null 2>&1; [ $? -eq 127 ] && die "committed warmer does not run on this host"
echo "=== harness sha256 $(sha256sum "$BH" | cut -c1-16)  warmer sha256 $(sha256sum "$WARMER" | cut -c1-16) ===" | tee -a "$LOG"
/usr/local/sbin/drop-caches || die "/usr/local/sbin/drop-caches failed"
echo "=== drop-caches works ===" | tee -a "$LOG"

for s in $SEEDS; do
  pad=$(printf '%02d' "$s")
  dir="$OUT/seed${pad}"
  if [ -f "$dir/raw.csv" ] && [ "$(wc -l < "$dir/raw.csv")" -gt 290 ]; then
    echo "--- seed $s SKIP ($(wc -l < "$dir/raw.csv") rows) $(ts) ---" | tee -a "$LOG"; continue
  fi
  echo "--- seed $s START $(ts) ---" | tee -a "$LOG"
  python3 run_experiment.py run --seed "$s" --outdir "$dir" --discard-records \
      --db orig --workload "$WL" --strategy "$STRATS" \
      --pread-reps 0 --async-reps 10 --async-win-reps 10 --async-bulk-reps 0 --populate-reps 0 \
      --baseline-reps 10 >>"$LOG" 2>&1 || die "seed $s run_experiment failed"
  # the page lists must be the frozen v7 ones, byte for byte
  for w in A B C; do
    for st in 2d 2e_K10 2f_top14 2f_slru; do
      f="hotset_${w}_orig_${st}.csv"
      cmp -s "$dir/work/$f" "results/unified_v7/seed${pad}/main/work/$f" || die "seed $s $f differs from the frozen v7 hotset"
    done
  done
  # contamination watch (NVMe record incident): share of first queries above 3 ms
  python3 - "$dir/raw.csv" <<'PY' | tee -a "$LOG"
import csv, sys
fq = [float(r["first_query_us"]) for r in csv.DictReader(open(sys.argv[1])) if r["first_query_us"]]
print(f"--- {sys.argv[1]}: {len(fq)} runs, {100 * sum(x > 3000 for x in fq) / max(len(fq), 1):.2f}% first queries > 3 ms")
PY
  echo "--- seed $s DONE $(ts), 12 hotsets equal v7 ---" | tee -a "$LOG"
done

python3 tools/stats_uncertainty.py --seeds "$OUT"/seed[0-9][0-9] \
  --out "$OUT/uncertainty.csv" --md "$OUT/uncertainty.md" >>"$LOG" 2>&1 || die "stats failed"
echo "=== ow_native_e2e complete $(ts): $OUT/uncertainty.csv ===" | tee -a "$LOG"
echo "Now: git add $OUT && git add -f $LOG && git commit -m 'ow_native_e2e results' && git push"
