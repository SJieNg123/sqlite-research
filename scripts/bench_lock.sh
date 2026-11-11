#!/usr/bin/env bash
# bench_lock.sh — run one benchmark at a time, pinned to CCD1 (CPUs 8-15).
#
#   scripts/bench_lock.sh <command> [args...]   take the lock, then exec taskset -c 8-15 <command>
#   scripts/bench_lock.sh --status              print "free" or "held" and exit 0 / 1; takes no lock
#
# Every benchmark in this repo goes through this wrapper (CLAUDE.md, Measurement protocol).
# CPUs 8-15 are the first threads of CCD1 (one L3); their SMT siblings 24-31 are outside the
# mask, so no two pinned processes share a physical core. Processes inherit the mask, so a
# harness --cpu must be in 8-15 (sched_setaffinity outside it only warns and leaves it unpinned).
#
# BENCH_LOCK_FILE  lock path (default: $XDG_RUNTIME_DIR or /tmp, per user)
# BENCH_LOCK_WAIT  seconds to wait for the lock; 0 = fail at once (default 0)
set -u
LOCK="${BENCH_LOCK_FILE:-${XDG_RUNTIME_DIR:-/tmp}/sqlite-research-bench.lock}"
WAIT="${BENCH_LOCK_WAIT:-0}"
CPUS=8-15

exec 9>"$LOCK"
if [ "${1:-}" = "--status" ]; then
  if flock -n 9; then echo free; exit 0; else echo held; exit 1; fi
fi
[ $# -gt 0 ] || { sed -n '2,15p' "$0"; exit 2; }

if [ "$WAIT" -gt 0 ]; then flock -w "$WAIT" 9; else flock -n 9; fi || {
  echo "bench_lock: $LOCK is held by another benchmark; refusing to run two at once" >&2; exit 75; }
echo "bench_lock: holding $LOCK, cpus=$CPUS, pid=$$" >&2
exec taskset -c "$CPUS" "$@"
