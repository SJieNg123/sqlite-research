#!/usr/bin/env bash
# verify.sh — drive run_experiment.py for verification without touching the repo's results/.
#
#   verify.sh doctor                       read-only: is this checkout + host worth driving?
#   verify.sh run <run-id> [args...]       run_experiment.py [args...] through scripts/bench_lock.sh,
#                                          --outdir forced to $VERIFY_ROOT/<run-id>/out
#   verify.sh harness <run-id> [--scope] [--bin <path>] -- <benchmark_harness args...>
#                                          run the harness binary directly through bench_lock
#                                          (--scope: inside systemd-run --user --scope, MemorySwapMax=0)
#   verify.sh prep-scratch                 create the R1b competitor files under $VERIFY_ROOT/scratch
#   verify.sh cleanup <run-id>             kill this run's leftovers, keep evidence, drop work/
#
# VERIFY_ROOT defaults to ~/verify-runs/sqlite-research (outside the repo, survives cleanup).
# Verification runs are not results: never cite them in the paper (CLAUDE.md: results come
# only from prereg'd runs under results/<date>-<git-sha>-<config-hash>/).
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
VERIFY_ROOT="${VERIFY_ROOT:-$HOME/verify-runs/sqlite-research}"
export EXPERIMENT_ROOT="$REPO"      # run_experiment.py defaults ROOT to /home/u03/..., which is wrong here
LOCK="$REPO/scripts/bench_lock.sh"
DROP=/usr/local/sbin/drop-caches
RUNS="$REPO/pipeline/preparation/layout_rewriter/runs"
HARNESS_CPU=10                      # inside bench_lock's taskset mask 8-15 (CCD1)

ok=0; bad=0; warn=0
pass() { echo "  OK    $*"; ok=$((ok+1)); }
fail() { echo "  FAIL  $*"; bad=$((bad+1)); }
note() { echo "  WARN  $*"; warn=$((warn+1)); }

fresh() { # fresh <binary> <gcc args...>: rebuild into a temp dir and byte-compare.
  # mtimes are useless here (restored checkout); gcc -O2 output is deterministic on this host.
  local b="$1"; shift
  [ -x "$b" ] || { fail "missing/not executable: ${b#$REPO/}"; return; }
  local t; t=$(mktemp -d)
  if ! (cd "$(dirname "$b")" && gcc -O2 -I. -o "$t/x" "$@" 2>"$t/err"); then
    fail "rebuild of ${b#$REPO/} failed: $(tail -1 "$t/err")"
  elif cmp -s "$b" "$t/x"; then pass "binary matches HEAD source: ${b#$REPO/}"
  else fail "stale binary: ${b#$REPO/} differs from a fresh build of HEAD (rebuild: see SKILL.md Launch)"; fi
  rm -rf "$t"
}

doctor() {
  echo "doctor: repo=$REPO"
  echo "        rev=$(git -C "$REPO" rev-parse --short HEAD) dirty=$(git -C "$REPO" status --porcelain | wc -l) files"
  echo "        VERIFY_ROOT=$VERIFY_ROOT"
  local held=0
  if [ ! -x "$LOCK" ]; then fail "missing scripts/bench_lock.sh (every benchmark must go through it)"
  elif "$LOCK" --status >/dev/null; then pass "bench_lock free"
  else fail "bench_lock held: a benchmark is running; wait for it (no builds or agents meanwhile)"; held=1; fi
  taskset -c 8-15 true 2>/dev/null && pass "CPUs 8-15 usable (bench_lock mask)" || fail "taskset -c 8-15 failed"
  if [ "$held" -eq 1 ]; then
    note "skipped binary rebuild-compare: no builds while a benchmark runs"
  else
    local H="$REPO/pipeline/engine/benchmark_harness" W="$REPO/pipeline/engine/prefetch_warmer/src" C="$REPO/pipeline/engine/residency_checker"
    fresh "$H/benchmark_harness" benchmark_harness.c sqlite3.c -lpthread -ldl -lm
    fresh "$W/warmer" warmer.c
    fresh "$C/residency_checker" residency_checker.c
  fi
  if [ -x "$DROP" ] && [ "$(stat -c '%U' "$DROP")" = root ] && [ -u "$DROP" ]; then pass "drop-caches setuid root: $DROP"
  else fail "$DROP missing or not setuid root (harness aborts without it)"; fi
  for f in test.db test_vacuum.db test_typeaware.db classify_before.csv classify_vacuum.csv classify_after.csv; do
    [ -s "$RUNS/$f" ] && pass "input: $f" || fail "missing input: $RUNS/$f"; done
  [ -s "$RUNS/test_db_1gb.db" ] && pass "input: test_db_1gb.db (optional --db 1gb)" || note "no test_db_1gb.db: --db 1gb unavailable"
  if out=$(cd "$REPO" && python3 run_experiment.py --db orig --workload A --strategy 2d --dry-run 2>&1); then
    pass "runner dry-run: $(echo "$out" | grep -o 'hotset=[0-9]* pages' | tail -1) for A/orig/2d"
  else fail "runner dry-run failed: $(echo "$out" | tail -1)"; fi
  if fz=$(cd "$REPO" && python3 run_experiment.py --verify-frozen 2>&1); then pass "frozen hotsets match manifest"
  else note "freeze manifest drift: $(echo "$fz" | tail -1) (known since a493768; see Gotchas)"; fi
  # match on argv[0] path: comm is truncated to 15 chars ("benchmark_harne")
  local mine others
  mine=$(pgrep -u "$USER" -f '^[^ ]*benchmark_harness( |$)'; pgrep -u "$USER" -f '^[^ ]*/warmer( |$)'; pgrep -u "$USER" -f 'cadence_hotset\.csv')
  [ -z "$mine" ] && pass "no harness/warmer of yours running" || fail "your harness/warmer already running (pids: $(echo $mine)); a second run would drop caches under it"
  others=$(pgrep -f '^[^ ]*benchmark_harness( |$)' | wc -l)
  [ "$others" -eq 0 ] && pass "no other benchmark_harness on host" || note "$others benchmark_harness running on host (other users drop caches too: numbers are noisy)"
  read -r l1 _ < /proc/loadavg
  awk -v l="$l1" 'BEGIN{exit !(l<2.0)}' && pass "loadavg $l1" || note "loadavg $l1 >= 2.0: latency numbers unreliable"
  echo "doctor: $ok ok, $warn warn, $bad fail"
  [ "$bad" -eq 0 ]
}

dbstat() { stat -c '%n size=%s mtime=%Y' "$RUNS"/test.db "$RUNS"/test_vacuum.db "$RUNS"/test_typeaware.db; }

run() {
  local id="${1:?usage: verify.sh run <run-id> [run_experiment.py args...]}"; shift
  case "$id" in */*|.*|"") echo "bad run-id: $id" >&2; return 2;; esac
  local D="$VERIFY_ROOT/$id"
  [ -e "$D" ] && { echo "run dir exists: $D (pick a new run-id)" >&2; return 2; }
  [ -x "$LOCK" ] || { echo "missing $LOCK" >&2; return 2; }
  "$LOCK" --status >/dev/null || { echo "bench_lock held: another benchmark is running; wait for it" >&2; return 75; }
  local sub=() extra=() pin
  case "${1:-}" in churn|aging|cadence) sub=("$1"); shift;; run) shift;; esac
  if [ ${#sub[@]} -eq 0 ]; then
    extra=(--no-pin-env)            # never let env.sh touch sysfs governor/readahead
    local a prev="" cpu=""
    for a in "$@"; do [ "$prev" = "--cpu" ] && cpu="$a"; prev="$a"; done
    if [ -z "$cpu" ]; then extra+=(--cpu "$HARNESS_CPU"); cpu=$HARNESS_CPU; fi
    [ "$cpu" -ge 8 ] 2>/dev/null && [ "$cpu" -le 15 ] || {
      echo "--cpu $cpu is outside bench_lock's mask 8-15: the harness would run unpinned" >&2; return 2; }
    pin="harness pinned to cpu $cpu (inside mask 8-15)"
  else
    pin="NOT ACHIEVED: ${sub[0]} hardcodes harness --cpu 2, outside bench_lock mask 8-15; harness runs unpinned on 8-15"
    echo "verify: WARN pinning $pin" >&2
  fi
  mkdir -p "$D/out"
  local cmd=(python3 run_experiment.py "${sub[@]}" "$@" "${extra[@]}" --outdir "$D/out")
  { echo "run_id=$id"; echo "rev=$(git -C "$REPO" rev-parse HEAD)"; echo "started=$(date -u +%FT%TZ)"
    echo "cmd=EXPERIMENT_ROOT=$REPO scripts/bench_lock.sh ${cmd[*]}"; echo "pinning=$pin"
    echo "repo_dirty_before=$(git -C "$REPO" status --porcelain | wc -l)"
    echo "db_before:"; dbstat; } > "$D/meta.txt"
  echo "verify: $D"
  ( cd "$REPO" && "$LOCK" "${cmd[@]}" ) 2>&1 | tee "$D/transcript.txt"
  local rc=${PIPESTATUS[0]}
  { echo "exit=$rc"; echo "ended=$(date -u +%FT%TZ)"; echo "db_after:"; dbstat
    echo "repo_dirty_after=$(git -C "$REPO" status --porcelain | wc -l)"; } >> "$D/meta.txt"
  echo "verify: exit=$rc  evidence=$D"
  return "$rc"
}

cleanup() {
  local id="${1:?usage: verify.sh cleanup <run-id>}"
  case "$id" in */*|.*|"") echo "bad run-id: $id" >&2; return 2;; esac
  local D="$VERIFY_ROOT/$id"
  [ -d "$D" ] || { echo "no run dir: $D" >&2; return 2; }
  # kill only processes whose command line names this run's dir (e.g. cadence's setsid warmer loop)
  local pids; pids=$(pgrep -u "$USER" -f "$D/out" || true)
  [ -n "$pids" ] && { echo "cleanup: killing leftovers $pids"; kill $pids 2>/dev/null; }
  if [ -d "$D/out/work" ]; then
    mkdir -p "$D/logs"
    for r in "$D"/out/work/rec*; do      # keep every harness run log as proof
      [ -d "$r" ] || continue
      for l in "$r"/run-*.log "$r"/run-*.memstat.csv; do [ -f "$l" ] && cp "$l" "$D/logs/$(basename "$r")__$(basename "$l")"; done
    done
    du -sh "$D/out/work" | sed 's/^/cleanup: removing scratch work dir /'
    rm -rf "$D/out/work"
  fi
  echo "cleanup: evidence kept in $D"; ls "$D" "$D/out"
}

harness() {
  local id="${1:?usage: verify.sh harness <run-id> [--scope] [--bin <path>] -- <harness args>}"; shift
  case "$id" in */*|.*|"") echo "bad run-id: $id" >&2; return 2;; esac
  local D="$VERIFY_ROOT/$id" scope=0 bin="$REPO/pipeline/engine/benchmark_harness/benchmark_harness"
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    case "$1" in --scope) scope=1;; --bin) bin="$2"; shift;; *) echo "unknown option $1" >&2; return 2;; esac; shift
  done
  [ "${1:-}" = "--" ] && shift
  [ -e "$D" ] && { echo "run dir exists: $D (pick a new run-id)" >&2; return 2; }
  "$LOCK" --status >/dev/null || { echo "bench_lock held: another benchmark is running; wait for it" >&2; return 75; }
  local a prev="" cpu="" extra=()
  for a in "$@"; do [ "$prev" = "--cpu" ] && cpu="$a"; prev="$a"; done
  if [ -z "$cpu" ]; then extra+=(--cpu "$HARNESS_CPU"); cpu=$HARNESS_CPU; fi
  [ "$cpu" -ge 8 ] 2>/dev/null && [ "$cpu" -le 15 ] || { echo "--cpu $cpu is outside bench_lock's mask 8-15" >&2; return 2; }
  mkdir -p "$D/out/records"
  local wrap=()
  [ "$scope" -eq 1 ] && wrap=(systemd-run --user --scope -q -p MemorySwapMax=0 --)
  local cmd=("${wrap[@]}" "$bin" "$@" "${extra[@]}" --record-dir "$D/out/records" --output "$D/out/ops.csv")
  { echo "run_id=$id"; echo "rev=$(git -C "$REPO" rev-parse HEAD)"; echo "started=$(date -u +%FT%TZ)"
    echo "bin=$bin sha256=$(sha256sum "$bin" | cut -c1-16)"
    echo "cmd=scripts/bench_lock.sh ${cmd[*]}"; echo "pinning=harness pinned to cpu $cpu (inside mask 8-15)"
    echo "repo_dirty_before=$(git -C "$REPO" status --porcelain | wc -l)"
    echo "db_before:"; dbstat; } > "$D/meta.txt"
  echo "verify: $D"
  ( cd "$REPO" && "$LOCK" "${cmd[@]}" ) 2>&1 | tee "$D/transcript.txt"
  local rc=${PIPESTATUS[0]}
  { echo "exit=$rc"; echo "ended=$(date -u +%FT%TZ)"; echo "db_after:"; dbstat
    echo "repo_dirty_after=$(git -C "$REPO" status --porcelain | wc -l)"; } >> "$D/meta.txt"
  echo "verify: exit=$rc  evidence=$D"
  return "$rc"
}

prep_scratch() {
  local S="$VERIFY_ROOT/scratch"
  "$LOCK" --status >/dev/null || { echo "bench_lock held: no heavy I/O while a benchmark runs" >&2; return 75; }
  mkdir -p "$S"
  [ "$(stat -c %s "$S/stream.bin" 2>/dev/null)" = 2147483648 ] || dd if=/dev/urandom of="$S/stream.bin" bs=1M count=2048 conv=fsync status=none
  [ "$(stat -c %s "$S/hot.bin" 2>/dev/null)" = 134217728 ] || dd if=/dev/urandom of="$S/hot.bin" bs=1M count=128 conv=fsync status=none
  ls -l "$S"
}

case "${1:-}" in
  doctor) doctor ;;
  run) shift; run "$@" ;;
  harness) shift; harness "$@" ;;
  prep-scratch) prep_scratch ;;
  cleanup) shift; cleanup "$@" ;;
  *) sed -n '2,14p' "$0"; exit 2 ;;
esac
