"""AWS Lambda probe for the advisor's suggestion 2: warm container, cold data.

The function carries the reference database in its deployment package. Every
invocation first measures how much of that database is still in the page cache,
and records how long this execution environment sat idle since its previous
invocation. Scheduling copies of the function at different fixed intervals and
memory sizes then shows whether a reused (warm) execution environment can still
find its data cold.

Residency is measured by timing reads, because diag.py showed Lambda leaves no
non-touching method: seccomp blocks mincore outright, the 5.10 kernel predates
cachestat, and /var/task is squashfs, which rejects RWF_NOWAIT. A timed read
separates cleanly there, about 650 to 970 us on a miss against 3 to 6 us on a
hit.

Two probe modes, selected per function by PROBE_MODE, run as separate functions
in one batch so they never share an execution environment:

  reread  times the same 100 pages at every invocation. Probing re-reads any it
          finds missing, so each invocation measures how much of the data read
          at the previous invocation survived one idle interval: data the
          function keeps using.
  once    times 4 pages per invocation, each in a 1 MB region no probe in this
          environment has touched. Every region is measured at most once, so the
          result is how much of the data read only by the cold-start warming
          read is still cached: data the function read once and left alone. The
          first pilot showed reread cannot see this, and that at 128 MB about
          half the database does not fit in the page cache at all.
"""
import json
import os
import random
import time
import uuid

DB = os.path.join(os.environ.get("LAMBDA_TASK_ROOT",
                                 os.path.dirname(os.path.abspath(__file__))), "test.db")

# Module scope runs once per execution environment. ENV_ID therefore changes on
# every cold start and stays fixed while an environment is reused, which is what
# separates "warm environment, cold data" from an ordinary cold start.
ENV_ID = uuid.uuid4().hex[:8]
BORN = time.time()
STATE = {"n": 0, "last_end": None, "used": 0}


PAGE = 4096
HIT_US = 100    # a read under this is a page-cache hit (hit 3-6 us, miss 650-970 us)
MODE = os.environ.get("PROBE_MODE", "reread")

# reread: 100 evenly spaced pages, about 1.03 MB apart on the 103 MB database.
REREAD_SAMPLES = 100
# once: squashfs blocks are at most 1 MB and aligned to the start of the file, so
# a read inside one 1 MB region cannot warm any other region. Each full region is
# one independent sample. 4 per invocation spends the 102 regions in about 24
# invocations, after which the environment reports no sample rather than reuse one.
REGION = 1 << 20
ONCE_SAMPLES = 4
N_REGIONS = os.stat(DB).st_size // REGION
ORDER = random.Random(ENV_ID).sample(range(N_REGIONS), N_REGIONS)  # seeded: replayable


def _time_pages(pages):
    """Timed read of each page number; returns latencies in us.

    Readahead is off on this fd, so a miss cannot pull neighbouring pages in.
    """
    fd = os.open(DB, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        lat = []
        for p in pages:
            t = time.perf_counter_ns()
            os.pread(fd, PAGE, p * PAGE)
            lat.append(round((time.perf_counter_ns() - t) / 1000, 1))
        return lat
    finally:
        os.close(fd)


def _probe():
    """Returns (latencies, regions probed). regions is None in reread mode."""
    if MODE == "once":
        regions = ORDER[STATE["used"]:STATE["used"] + ONCE_SAMPLES]
        STATE["used"] += len(regions)
        return _time_pages([r * (REGION // PAGE) + (REGION // PAGE) // 2 for r in regions]), regions
    stride = (os.stat(DB).st_size // PAGE) // REREAD_SAMPLES  # 263 pages, as in the pilot
    return _time_pages([i * stride + stride // 2 for i in range(REREAD_SAMPLES)]), None


def _resident_pct(lat):
    if not lat:
        return None  # once mode, regions exhausted
    return round(100.0 * sum(1 for x in lat if x < HIT_US) / len(lat), 1)


def _meminfo():
    """Guest memory as the kernel sees it, to tell memory pressure from idle time."""
    want = {"MemTotal", "MemAvailable", "Cached"}
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split(":", 1)
            if key in want:
                out[key + "_kb"] = int(val.split()[0])
    return out


def lambda_handler(event, context):
    if event.get("diag"):
        import diag  # capability probe, see diag.py; leaves the probe state untouched
        return diag.run(DB)
    start = time.time()
    STATE["n"] += 1
    idle = None if STATE["last_end"] is None else start - STATE["last_end"]

    # Measure before anything else in this invocation touches the file.
    lat, regions = _probe()
    target = os.environ.get("IDLE_MIN")
    rec = {
        "fn": context.function_name,
        "mem_mb": int(context.memory_limit_in_mb),
        "idle_target_min": int(target) if target else None,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
        "env_id": ENV_ID,
        "log_stream": context.log_stream_name,
        "invocation": STATE["n"],
        "cold_start": STATE["n"] == 1,
        "idle_s": None if idle is None else round(idle, 1),
        "env_age_s": round(start - BORN, 1),
        "mode": MODE,
        "samples": len(lat),
        "hit_threshold_us": HIT_US,
        "resident_pct": _resident_pct(lat),
        "lat_us": lat,
        "regions": regions,
    }
    rec.update(_meminfo())

    # A fresh environment reads the whole database once, so the first interval
    # starts from as warm a cache as its memory size allows. In reread mode the
    # only later reads are the probe's own. In once mode nothing re-reads a
    # region, and the probe right after the warming read is the direct measure of
    # how much of the database the page cache can hold at this memory size.
    if STATE["n"] == 1:
        t0 = time.time()
        with open(DB, "rb") as f:
            while f.read(1 << 20):
                pass
        rec["warm_read_s"] = round(time.time() - t0, 3)
        after, after_regions = _probe()
        rec["resident_after_warm_pct"] = _resident_pct(after)
        rec["after_warm_lat_us"] = after
        rec["after_warm_regions"] = after_regions

    STATE["last_end"] = time.time()
    print("RESIDENCY " + json.dumps(rec))
    return rec
