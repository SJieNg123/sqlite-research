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
hit. The cost is that probing re-reads every sampled page it finds missing, so
what each invocation measures is how much of the data read at the previous
invocation survived the idle interval since.
"""
import json
import os
import time
import uuid

DB = os.path.join(os.environ.get("LAMBDA_TASK_ROOT",
                                 os.path.dirname(os.path.abspath(__file__))), "test.db")

# Module scope runs once per execution environment. ENV_ID therefore changes on
# every cold start and stays fixed while an environment is reused, which is what
# separates "warm environment, cold data" from an ordinary cold start.
ENV_ID = uuid.uuid4().hex[:8]
BORN = time.time()
STATE = {"n": 0, "last_end": None}


PAGE = 4096
SAMPLES = 100   # evenly spaced pages, about 1.03 MB apart on the 103 MB database
HIT_US = 100    # a read under this is a page-cache hit (hit 3-6 us, miss 650-970 us)


def _probe():
    """Timed read of SAMPLES pages spread over the database; returns latencies in us.

    squashfs decompresses whole blocks of up to 1 MB and fills the page cache with
    every page of the block, so one miss warms its neighbours. Samples are spaced
    more than 1 MB apart so no read can warm another sample, and readahead is off
    on this fd so the kernel does not either.
    """
    fd = os.open(DB, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        stride = (os.fstat(fd).st_size // PAGE) // SAMPLES
        lat = []
        for i in range(SAMPLES):
            t = time.perf_counter_ns()
            os.pread(fd, PAGE, (i * stride + stride // 2) * PAGE)
            lat.append(round((time.perf_counter_ns() - t) / 1000, 1))
        return lat
    finally:
        os.close(fd)


def _resident_pct(lat):
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
    lat = _probe()
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
        "samples": SAMPLES,
        "hit_threshold_us": HIT_US,
        "resident_pct": _resident_pct(lat),
        "lat_us": lat,
    }
    rec.update(_meminfo())

    # A fresh environment reads the whole database once, so the first interval
    # starts from as warm a cache as its memory size allows. After that the only
    # reads are the probe's own, which leave every sample resident at the end of
    # each invocation, so each measurement is what one idle interval took away.
    if STATE["n"] == 1:
        t0 = time.time()
        with open(DB, "rb") as f:
            while f.read(1 << 20):
                pass
        rec["warm_read_s"] = round(time.time() - t0, 3)
        rec["resident_after_warm_pct"] = _resident_pct(_probe())

    STATE["last_end"] = time.time()
    print("RESIDENCY " + json.dumps(rec))
    return rec
