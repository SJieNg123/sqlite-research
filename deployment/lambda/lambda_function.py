"""AWS Lambda probe for the advisor's suggestion 2: warm container, cold data.

The function carries the reference database in its deployment package. Every
invocation first measures, with mincore and before anything reads the file, how
much of that database is still in the page cache, and records how long this
execution environment sat idle since its previous invocation. Scheduling copies
of the function at different fixed intervals and memory sizes then shows whether
a reused (warm) execution environment can still find its data cold.

The residency primitive is deployment/openwhisk/action/residency.py, copied into
the package unchanged by build.sh, so Lambda and OpenWhisk measure the same way.
"""
import json
import os
import time
import uuid

import residency

DB = os.path.join(os.environ.get("LAMBDA_TASK_ROOT",
                                 os.path.dirname(os.path.abspath(__file__))), "test.db")

# Module scope runs once per execution environment. ENV_ID therefore changes on
# every cold start and stays fixed while an environment is reused, which is what
# separates "warm environment, cold data" from an ordinary cold start.
ENV_ID = uuid.uuid4().hex[:8]
BORN = time.time()
STATE = {"n": 0, "last_end": None}


def _resident_pages():
    with residency.PageMap(DB) as pm:
        vec = pm.residency_vector()
        return sum(b & 1 for b in vec), pm.npages


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
    start = time.time()
    STATE["n"] += 1
    idle = None if STATE["last_end"] is None else start - STATE["last_end"]

    # Measure before this invocation touches the file.
    resident, total = _resident_pages()
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
        "resident_pages": resident,
        "total_pages": total,
        "resident_pct": round(100.0 * resident / total, 2),
    }
    rec.update(_meminfo())

    # A fresh environment reads the whole database once, so every later
    # invocation in it starts from as warm a cache as its memory size allows and
    # measures only what the idle interval took away. Later invocations read
    # nothing, so residency can only hold or fall.
    if STATE["n"] == 1:
        t0 = time.time()
        with open(DB, "rb") as f:
            while f.read(1 << 20):
                pass
        rec["warm_read_s"] = round(time.time() - t0, 3)
        after, _ = _resident_pages()
        rec["resident_after_warm_pct"] = round(100.0 * after / total, 2)

    STATE["last_end"] = time.time()
    print("RESIDENCY " + json.dumps(rec))
    return rec
