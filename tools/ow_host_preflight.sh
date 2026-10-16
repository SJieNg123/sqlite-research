#!/usr/bin/env bash
# Preflight for the native end-to-end run on the OpenWhisk host (paper TODO L453 (1)).
# Read-only apart from a scratch directory: it builds the harness and a small probe in
# $SCRATCH and deletes them afterwards. Needs no root and never calls sudo.
#
#   tools/ow_host_preflight.sh            # from the repo root of the clone on that host
#
# It writes everything to preflight_<host>_<UTC time>.txt in the current directory. Send
# that file back. Checks:
#   1. privilege: whether any cache-drop mechanism exists without root
#   2. system: kernel, CPU, memory, cpufreq, load, running containers
#   3. storage: the device under the repo, read_ahead_kb and max_sectors_kb (window W)
#   4. data identity: test.db (not a git-lfs pointer), workloads, frozen hotsets
#   5. toolchain: builds benchmark_harness and warmer as README.md does
#   6. cold-cache probe: which unprivileged eviction brings test.db to 0% resident
#   7. CPU clock: frequency of the pinned core after the harness's 10 ms spin
set -u
cd "$(dirname "$0")/.."
ROOT=$(pwd)
OUT="$ROOT/preflight_$(hostname -s)_$(date -u +%Y%m%dT%H%M%SZ).txt"
SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT
exec > >(tee "$OUT") 2>&1

DB=pipeline/preparation/layout_rewriter/runs/test.db
DB_SHA=2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1
DB_SIZE=107851776
WL_SHA=60e87419ed62141c4e96a4c4864885d320e26ac2540a50b0a7dc6c8504f6ebde   # workload_{a,b,c}_{1..10}
CPU=2                                                                      # run_experiment --cpu default
SUMMARY=()
pass() { echo "  PASS  $*"; SUMMARY+=("PASS  $*"); }
warn() { echo "  WARN  $*"; SUMMARY+=("WARN  $*"); }
fail() { echo "  FAIL  $*"; SUMMARY+=("FAIL  $*"); }
rd()   { [ -r "$1" ] && cat "$1" 2>/dev/null || echo "n/a"; }

echo "ow_host_preflight  $(date -u +%FT%TZ)  host=$(hostname)  user=$(id -un)"
echo "repo $ROOT  HEAD=$(git rev-parse --short HEAD 2>/dev/null)  branch=$(git branch --show-current 2>/dev/null)"
git status --short 2>/dev/null | head -5 | sed 's/^/  dirty: /'
if git merge-base --is-ancestor 24e9496 HEAD 2>/dev/null; then pass "clone contains the unified_v7 batch code (24e9496)"
else fail "clone predates 24e9496: git pull first"; fi

echo; echo "== 1. privilege"
echo "  id: $(id)"
if sudo -n true 2>/dev/null; then warn "sudo works without a password (not expected)"; else echo "  sudo: not available (expected)"; fi
if [ -u /usr/local/sbin/drop-caches ]; then pass "setuid /usr/local/sbin/drop-caches exists"
else warn "no setuid drop-caches helper: the run needs an unprivileged eviction (see section 6)"; fi
[ -w /proc/sys/vm/drop_caches ] && warn "/proc/sys/vm/drop_caches is writable" || echo "  /proc/sys/vm/drop_caches: not writable (expected)"

echo; echo "== 2. system"
echo "  kernel: $(uname -srm)"
echo "  os: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-n/a}")"
echo "  cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')  cores=$(nproc)"
echo "  memory: $(grep -E '^(MemTotal|MemAvailable)' /proc/meminfo | tr -s ' ' | tr '\n' ' ')"
C=/sys/devices/system/cpu/cpu$CPU/cpufreq
echo "  cpufreq cpu$CPU: driver=$(rd $C/scaling_driver) governor=$(rd $C/scaling_governor) epp=$(rd $C/energy_performance_preference) max_khz=$(rd $C/cpuinfo_max_freq)"
echo "  boost=$(rd /sys/devices/system/cpu/cpufreq/boost) intel_no_turbo=$(rd /sys/devices/system/cpu/intel_pstate/no_turbo) thp=$(rd /sys/kernel/mm/transparent_hugepage/enabled)"
echo "  load: $(cut -d' ' -f1-3 /proc/loadavg)"
[ "$(nproc)" -gt "$CPU" ] && pass "core $CPU exists for the harness pin" || fail "fewer than $((CPU + 1)) cores: pass --cpu"
if command -v docker >/dev/null 2>&1 && docker ps -q >/dev/null 2>&1; then
  n=$(docker ps -q | wc -l)
  [ "$n" -eq 0 ] && pass "no running containers" || warn "$n running containers: stop OpenWhisk during the run"
else echo "  docker: not reachable from this user"; fi
echo "  top CPU users:"; ps -eo pcpu,comm --sort=-pcpu | sed -n '2,6p' | sed 's/^/    /'

echo; echo "== 3. storage"
SRC=$(df --output=source "$ROOT" | tail -1); PART=$(basename "$SRC")
if [ -e "/sys/block/$PART/queue" ]; then DISK=$PART; else DISK=$(lsblk -no pkname "$SRC" 2>/dev/null | head -1); fi
Q=/sys/block/$DISK/queue
echo "  repo on $SRC ($(df --output=fstype "$ROOT" | tail -1)), disk=$DISK model=$(rd /sys/block/$DISK/device/model | xargs)"
echo "  read_ahead_kb=$(rd $Q/read_ahead_kb) max_sectors_kb=$(rd $Q/max_sectors_kb) max_hw_sectors_kb=$(rd $Q/max_hw_sectors_kb) scheduler=$(rd $Q/scheduler) rotational=$(rd $Q/rotational)"
echo "  free: $(df -h --output=avail "$ROOT" | tail -1 | xargs)"
[ "$(rd $Q/read_ahead_kb)" = 128 ] && pass "read_ahead_kb=128, window W=32 pages as on the workstation" \
  || warn "read_ahead_kb=$(rd $Q/read_ahead_kb): the window differs from the workstation's 32 pages"
[ "$(rd $Q/max_sectors_kb)" = 128 ] || warn "max_sectors_kb=$(rd $Q/max_sectors_kb), the workstation has 128"

echo; echo "== 4. data identity"
if [ ! -f "$DB" ]; then fail "$DB missing"
elif head -c 40 "$DB" | grep -q 'git-lfs'; then fail "$DB is a git-lfs pointer: install git-lfs and run git lfs pull"
else
  sz=$(stat -c %s "$DB"); sha=$(sha256sum "$DB" | cut -c1-64)
  echo "  test.db size=$sz sha256=$sha"
  [ "$sz" = "$DB_SIZE" ] && [ "$sha" = "$DB_SHA" ] && pass "test.db is the workstation's file" || fail "test.db differs from the workstation's"
fi
wl=$(for w in a b c; do for i in $(seq 1 10); do sha256sum "workloads/workload_${w}_${i}.txt" 2>/dev/null; done; done | awk '{print $1}' | sha256sum | cut -c1-64)
[ "$wl" = "$WL_SHA" ] && pass "workloads A, B, C seeds 1 to 10 match" || fail "workload files differ ($wl)"
for s in 2d 2e_K10 2f_top14 2f_slru; do
  n=$(ls results/unified_v7/seed*/main/work/hotset_[ABC]_orig_"$s".csv 2>/dev/null | wc -l)
  echo "  frozen v7 hotsets $s: $n of 30"
done

echo; echo "== 5. toolchain"
echo "  gcc: $(gcc --version 2>/dev/null | head -1)"
echo "  python3: $(python3 --version 2>&1)  git: $(git --version)  git-lfs: $(git lfs version 2>/dev/null | head -1 || echo none)"
t0=$(date +%s)
if gcc -O2 -I pipeline/engine/benchmark_harness -o "$SCRATCH/benchmark_harness" pipeline/engine/benchmark_harness/benchmark_harness.c \
     pipeline/engine/benchmark_harness/sqlite3.c -lpthread -ldl -lm 2>"$SCRATCH/bh.err"; then
  pass "benchmark_harness builds ($(( $(date +%s) - t0 )) s)"
else fail "benchmark_harness does not build:"; head -5 "$SCRATCH/bh.err" | sed 's/^/    /'; fi
if gcc -O2 -o "$SCRATCH/warmer" pipeline/engine/prefetch_warmer/src/warmer.c 2>"$SCRATCH/w.err"; then
  pass "warmer builds"
else fail "warmer does not build:"; head -5 "$SCRATCH/w.err" | sed 's/^/    /'; fi

echo; echo "== 6. cold-cache probe (unprivileged)"
cat > "$SCRATCH/probe.c" <<'C'
/* Warm test.db through a shared read-only mapping, then try each unprivileged eviction and
 * report page-cache residency with mincore. Order A then B is the harness order: madvise on
 * its mapping, then the helper it runs in place of drop-caches. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#ifndef MADV_COLD
#define MADV_COLD 20
#endif
#ifndef MADV_PAGEOUT
#define MADV_PAGEOUT 21
#endif
static size_t len, pg, npg; static unsigned char *vec; static char *map; static int fd;
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec / 1e6; }
static double resident(void) {
    if (mincore(map, len, vec)) { perror("mincore"); exit(1); }
    size_t r = 0; for (size_t i = 0; i < npg; i++) r += vec[i] & 1; return 100.0 * r / npg;
}
static void warm(void) { volatile char s = 0; for (size_t i = 0; i < len; i += pg) s += map[i]; (void)s; }
static void step(const char *name, int how) {
    double t = now();
    if (how == 0) { madvise(map, len, MADV_COLD); madvise(map, len, MADV_PAGEOUT); madvise(map, len, MADV_DONTNEED); }
    if (how == 1) posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED);
    printf("    %-44s resident %7.3f%%  (%.1f ms)\n", name, resident(), now() - t);
}
int main(int argc, char **argv) {
    struct stat st; fd = open(argv[1], O_RDONLY); if (fd < 0 || fstat(fd, &st)) { perror("open"); return 1; }
    len = st.st_size; pg = sysconf(_SC_PAGESIZE); npg = (len + pg - 1) / pg; vec = malloc(npg);
    map = mmap(NULL, len, PROT_READ, MAP_SHARED, fd, 0); if (map == MAP_FAILED) { perror("mmap"); return 1; }
    for (int trial = 1; trial <= 3; trial++) {
        printf("  trial %d\n", trial);
        warm(); printf("    %-44s resident %7.3f%%\n", "warm (every page read through the mapping)", resident());
        step("A  madvise COLD+PAGEOUT+DONTNEED", 0);
        step("A+B  then posix_fadvise(DONTNEED)", 1);
        warm(); step("B alone  posix_fadvise(DONTNEED), still mapped", 1);
    }
    return 0;
}
C
if gcc -O2 -o "$SCRATCH/probe" "$SCRATCH/probe.c" 2>"$SCRATCH/p.err"; then
  "$SCRATCH/probe" "$DB" | tee "$SCRATCH/probe.out"
  if grep 'A+B' "$SCRATCH/probe.out" | grep -q 'resident   0.000%'; then
    if [ "$(grep 'A+B' "$SCRATCH/probe.out" | grep -vc 'resident   0.000%')" = 0 ]; then
      pass "madvise then posix_fadvise(DONTNEED) reaches 0.000% in every trial"
    else warn "madvise then posix_fadvise(DONTNEED) reaches 0% only in some trials"; fi
  else fail "no unprivileged eviction reached 0%: something else maps or holds test.db"; fi
else fail "probe does not build:"; head -5 "$SCRATCH/p.err" | sed 's/^/    /'; fi

echo; echo "== 7. CPU clock on core $CPU after a 10 ms spin"
python3 - "$CPU" <<'PY'
import os, sys, time
cpu = int(sys.argv[1]); base = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/"
try:
    os.sched_setaffinity(0, {cpu})
except OSError as e:
    print(f"  cannot pin to core {cpu}: {e}"); sys.exit()
def read(name):
    try:
        return int(open(base + name).read())
    except OSError:
        return None
idle = read("scaling_cur_freq")
t = time.perf_counter()
while time.perf_counter() - t < 0.010:
    pass
spun, top = read("scaling_cur_freq"), read("cpuinfo_max_freq")
print(f"  idle {idle} kHz, after spin {spun} kHz, cpuinfo_max {top} kHz")
if spun and top:
    print(f"  after spin = {100 * spun / top:.0f}% of max")
PY

echo; echo "== summary"
for s in "${SUMMARY[@]}"; do echo "  $s"; done
echo; echo "written to $OUT"
