"""OpenWhisk action entrypoint: cold-start first-query measurement.

Warm-process, cold-data model. One long-lived container process (a `Session`)
serves many invocations; each invocation cold-resets the OS page cache for the
frozen reference DB, optionally delivers a prefetch plan, and times the exact
requested first query. Only baseline and 2d (interior skeleton) are implemented
in Phase 5A; both reuse the frozen artifacts and the canonical non-root
primitives in `residency.py`. No latency is interpreted here — the action emits a
complete, atomically-scoped record and the client/collector aggregates later.

`main(params)` is the OpenWhisk handler. `handle(request, session)` is the pure,
locally-testable core (no OpenWhisk dependency).
"""
import csv
import hashlib
import os
import sqlite3
import time

try:  # allow both `python -m action.main` and OpenWhisk's flat import
    from . import residency
    from .session import Session
except ImportError:  # pragma: no cover - OpenWhisk flat layout
    import residency
    from session import Session

SUPPORTED_STRATEGIES = ("baseline", "2d")
_SESSION = None


def get_session():
    """Module-singleton Session, created on first invocation of the warm process."""
    global _SESSION
    if _SESSION is None:
        manifest = os.environ.get("OW_ARTIFACT_MANIFEST") or os.path.join(
            os.path.dirname(__file__), "..", "config", "artifacts.json")
        _SESSION = Session(os.path.abspath(manifest))
        _SESSION.validate_artifacts()
    return _SESSION


# --------------------------------------------------------------------------- IO
def load_interior_offsets(plan_path):
    """Load the frozen interior-page plan (page_number,file_offset). Fails loudly
    on duplicate page numbers. Returns an ordered, de-duplicated offset list."""
    seen = set()
    offsets = []
    with open(plan_path, newline="") as f:
        for row in csv.DictReader(f):
            pn = int(row["page_number"])
            if pn in seen:
                raise ValueError("duplicate page in plan: %d" % pn)
            seen.add(pn)
            offsets.append(int(row["file_offset"]))
    return offsets


def select_pages(strategy, interior_offsets, expected_interior_count):
    """Return the offsets to deliver for a strategy. baseline delivers nothing;
    2d delivers every mandatory interior page exactly once. Fails if the plan
    size disagrees with the manifest (STEP 8)."""
    if strategy == "baseline":
        return []
    if strategy == "2d":
        if len(interior_offsets) != expected_interior_count:
            raise ValueError("2d plan has %d interiors, manifest expects %d"
                             % (len(interior_offsets), expected_interior_count))
        return list(interior_offsets)
    raise ValueError("unsupported strategy: %s" % strategy)


def read_first_operation(trace_path, first_operation_id):
    """Return the integer key of the requested first operation (YCSB `read <k>`)."""
    with open(trace_path) as f:
        for i, line in enumerate(f):
            if i == first_operation_id:
                parts = line.split()
                if len(parts) < 2 or parts[0] != "read":
                    raise ValueError("unsupported op at %d: %r" % (i, line))
                return int(parts[1])
    raise ValueError("first_operation_id %d beyond trace" % first_operation_id)


def run_first_query(db_path, key):
    """Execute the exact first query and return (hit, result_digest, open_us,
    query_us, sqlite_error). Identical logic for baseline and 2d."""
    err = None
    t0 = time.monotonic_ns()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA mmap_size=0")  # exercise the pager read() path
    open_us = (time.monotonic_ns() - t0) / 1000.0
    hit, digest = 0, ""
    tq = time.monotonic_ns()
    try:
        cur = conn.execute("SELECT id,k1,k2,payload FROM items WHERE id=?", (key,))
        row = cur.fetchone()
        query_us = (time.monotonic_ns() - tq) / 1000.0
        if row is not None:
            hit = 1
            h = hashlib.sha256()
            for col in row:
                h.update(str(col).encode() if not isinstance(col, (bytes, bytearray))
                         else col)
                h.update(b"\x1f")
            digest = h.hexdigest()
        else:
            digest = "NOTFOUND"
    except sqlite3.Error as e:  # pragma: no cover
        query_us = (time.monotonic_ns() - tq) / 1000.0
        err = str(e)
    finally:
        conn.close()
    return hit, digest, open_us, query_us, err


# ------------------------------------------------------------------- handler
def handle(request, session):
    """Core handler. `request` is the validated JSON dict; `session` the warm
    process singleton. Returns the response-contract dict."""
    t_handler = time.monotonic_ns()
    resp = {"error": None, "sqlite_error": None}

    # ---- identity ----
    resp.update(session.identity_fields())
    resp["invocation_counter"] = session.next_invocation()

    strategy = request["strategy"]
    workload = request["workload"]
    seed = request["seed"]
    first_op = request["first_operation_id"]
    diagnostic = bool(request.get("diagnostic_mode", False))
    cold_reset_requested = bool(request.get("cold_reset", True))

    resp.update({"workload": workload, "strategy": strategy, "seed": seed,
                 "first_operation_id": first_op})

    if strategy not in SUPPORTED_STRATEGIES:
        resp["error"] = "unsupported strategy in Phase 5A: %s" % strategy
        resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
        return resp

    # ---- artifact identity gate (refuse measured mode on any mismatch) ----
    if session.db_identity_changed():
        resp["error"] = "db device/inode changed since process init"
        resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
        return resp
    exp_hash = request.get("expected_artifact_manifest_hash")
    if exp_hash and exp_hash != session.artifact_manifest_sha256:
        resp["error"] = "expected_artifact_manifest_hash mismatch"
        resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
        return resp

    m = session.manifest
    trace_rel = m["workload_traces"][workload]["seeds"][str(seed)]["path"]
    trace_sha = m["workload_traces"][workload]["seeds"][str(seed)]["sha256"]
    plan_rel = m["strategy_plans"]["2d"]["path"]
    plan_sha = m["strategy_plans"]["2d"]["sha256"]
    tp = session.validate_trace_plan(trace_rel, trace_sha,
                                     plan_rel if strategy == "2d" else None,
                                     plan_sha if strategy == "2d" else None)
    if tp:
        resp["error"] = "; ".join(tp)
        resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
        return resp
    resp["trace_sha256"] = trace_sha
    resp["plan_sha256"] = plan_sha if strategy == "2d" else ""

    interior_offsets = m["interior_page_list"]["offsets"]
    expected_interiors = m["interior_page_list"]["count"]
    relevant_total = m.get("expected_relevant_page_count", expected_interiors)
    interior_set = set(interior_offsets)

    db_path = session.db_path
    key = read_first_operation(session._abspath(trace_rel), first_op)

    # ---- cold reset + residency verification ----
    pm = residency.PageMap(db_path)
    try:
        vec_before = pm.residency_vector()
        resp["resident_pages_before_reset"] = sum(b & 1 for b in vec_before)
        resp["resident_interiors_before_reset"] = residency.count_in(vec_before, interior_set)
        resp["cold_reset_requested"] = cold_reset_requested
        if cold_reset_requested:
            t0 = time.monotonic_ns()
            method = pm.cold_reset()
            resp["reset_us"] = (time.monotonic_ns() - t0) / 1000.0
            resp["cold_reset_method"] = method
        else:
            resp["reset_us"] = 0.0
            resp["cold_reset_method"] = "none"
        vec_after = pm.residency_vector()
        resp["resident_pages_after_reset"] = sum(b & 1 for b in vec_after)
        resp["resident_interiors_after_reset"] = residency.count_in(vec_after, interior_set)
        resp["relevant_pages_total"] = relevant_total
        cold_ok = residency.cold_threshold_passed(resp["resident_interiors_after_reset"])
        resp["cold_reset_succeeded"] = cold_ok
        resp["cold_threshold_passed"] = cold_ok

        # ---- select ----
        t0 = time.monotonic_ns()
        plan_path = session._abspath(plan_rel)
        offsets = ([] if strategy == "baseline"
                   else select_pages("2d", load_interior_offsets(plan_path),
                                     expected_interiors))
        resp["select_us"] = (time.monotonic_ns() - t0) / 1000.0
        resp["selected_page_count"] = len(offsets)
        resp["selected_interior_count"] = sum(1 for o in offsets if o in interior_set)
        resp["selected_leaf_count"] = len(offsets) - resp["selected_interior_count"]

        # ---- deliver ----
        t0 = time.monotonic_ns()
        delivered = pm.deliver_willneed(offsets) if offsets else 0
        resp["deliver_us"] = (time.monotonic_ns() - t0) / 1000.0
        resp["delivered_page_count"] = delivered
        vec_pf = pm.residency_vector()
        resp["resident_interiors_after_prefetch"] = residency.count_in(vec_pf, interior_set)
    finally:
        pm.close()

    # ---- open + first query (identical logic across strategies) ----
    hit, digest, open_us, query_us, sqlite_err = run_first_query(db_path, key)
    resp["open_us"] = open_us
    resp["first_query_us"] = query_us
    resp["query_hit"] = hit
    resp["result_digest"] = digest
    resp["sqlite_error"] = sqlite_err

    resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
    if not diagnostic:
        # keep the record complete but flag when cold gate failed
        resp["measured_valid"] = bool(resp["cold_threshold_passed"]
                                      and sqlite_err is None and hit == 1)
    else:
        resp["measured_valid"] = None
    return resp


REQUIRED_REQUEST_FIELDS = ("request_id", "workload", "strategy", "seed",
                           "first_operation_id", "diagnostic_mode", "cold_reset",
                           "expected_artifact_manifest_hash")


def validate_request(request):
    """Return () if valid, else a tuple of missing/invalid-field messages."""
    missing = [f for f in REQUIRED_REQUEST_FIELDS if f not in request]
    if missing:
        return ("missing request fields: " + ", ".join(missing),)
    problems = []
    if not isinstance(request["first_operation_id"], int) or request["first_operation_id"] < 0:
        problems.append("first_operation_id must be a non-negative int")
    if request["strategy"] not in SUPPORTED_STRATEGIES:
        problems.append("strategy must be one of %s" % (SUPPORTED_STRATEGIES,))
    return tuple(problems)


def main(params):
    """OpenWhisk entrypoint."""
    problems = validate_request(params or {})
    if problems:
        return {"error": "; ".join(problems), "request_id": (params or {}).get("request_id")}
    session = get_session()
    out = handle(params, session)
    out["request_id"] = params.get("request_id")
    return out
