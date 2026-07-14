"""OpenWhisk action entrypoint: fail-closed cold-start first-query measurement.

Warm-process, cold-data model. One long-lived container process (a ``Session``
with a canonical warm SQLite handle) serves many invocations; each invocation
cold-resets the OS page cache for the frozen reference DB (efficacy-verified),
optionally delivers the 2d interior skeleton, and times the exact requested first
query, comparing the result against a frozen oracle. Every gate fails closed:
on any artifact/identity/cold-gate/oracle failure the handler returns a complete
error envelope with the failing stage and never emits a partial record that looks
valid.

`main(params)` is the OpenWhisk handler; `handle(request, session)` is the
locally-testable core (no OpenWhisk dependency).
"""
import os
import sqlite3
import time

try:
    from . import residency, oracle
    from .session import Session, validate_request_semantics
except ImportError:  # pragma: no cover - OpenWhisk flat layout
    import residency
    import oracle
    from session import Session, validate_request_semantics

SUPPORTED_STRATEGIES = ("baseline", "2d")
HANDLE_MODES = ("warm", "standalone")
REQUIRED_REQUEST_FIELDS = ("request_id", "workload", "strategy", "seed",
                           "first_operation_id", "diagnostic_mode", "cold_reset",
                           "expected_artifact_manifest_hash")
_SESSION = None


def get_session():
    """Module-singleton warm Session. Validates artifacts and opens the warm
    handle exactly once; if validation fails the session is returned unvalidated
    so the handler refuses measured mode."""
    global _SESSION
    if _SESSION is None:
        manifest = os.environ.get("OW_ARTIFACT_MANIFEST") or os.path.join(
            os.path.dirname(__file__), "..", "config", "artifacts.json")
        s = Session(os.path.abspath(manifest))
        s.validate_artifacts()          # sets s.validated / s.validation_reasons
        if s.validated:
            s.open_warm_handle()
        _SESSION = s
    return _SESSION


def validate_request_schema(request):
    """Structural request validation (fields present + basic types)."""
    missing = [f for f in REQUIRED_REQUEST_FIELDS if f not in request]
    if missing:
        return ("missing request fields: " + ", ".join(missing),)
    problems = []
    if request["strategy"] not in SUPPORTED_STRATEGIES:
        problems.append("strategy must be one of %s" % (SUPPORTED_STRATEGIES,))
    if not isinstance(request["first_operation_id"], int) or request["first_operation_id"] < 0:
        problems.append("first_operation_id must be a non-negative int")
    hm = request.get("handle_mode", "warm")
    if hm not in HANDLE_MODES:
        problems.append("handle_mode must be one of %s" % (HANDLE_MODES,))
    return tuple(problems)


# retained for older callers/tests
def validate_request(request):
    return validate_request_schema(request)


def select_offsets(strategy, session):
    """Return the delivery offsets for a strategy from the process-init cache.
    baseline delivers nothing; 2d delivers exactly the 92 mandatory interiors.
    Fails closed on any count disagreement."""
    if strategy == "baseline":
        return []
    if strategy == "2d":
        offs = session.interior_offsets
        expected = session.manifest["interior_page_count"]
        if len(offs) != expected or expected != 92:
            raise ValueError("2d plan has %d interiors, expected 92" % len(offs))
        if any(o not in session.interior_offset_set for o in offs):
            raise ValueError("2d plan contains a non-interior offset")
        return list(offs)
    raise ValueError("unsupported strategy: %s" % strategy)


def _run_query(session, key, handle_mode):
    """Execute the exact first query and return
    (row, open_us, query_us, sqlite_error). Warm mode reuses the process handle
    (no open cost on the critical path); standalone opens a fresh connection with
    the canonical pragmas and pays open_us."""
    err = None
    if handle_mode == "warm":
        conn = session.open_warm_handle()
        open_us = 0.0
        tq = time.monotonic_ns()
        try:
            row = oracle.run_read(conn, key)
        except sqlite3.Error as e:  # pragma: no cover
            return None, open_us, (time.monotonic_ns() - tq) / 1000.0, str(e)
        return row, open_us, (time.monotonic_ns() - tq) / 1000.0, err
    # standalone: fresh connection, measured open cost, same pragmas
    pragmas = session.manifest.get("sqlite_pragmas", {"cache_size": 0,
                                                      "mmap_size": session.manifest["database"]["byte_size"]})
    t0 = time.monotonic_ns()
    conn = sqlite3.connect(session.db_path)
    conn.execute("PRAGMA cache_size = %d" % int(pragmas.get("cache_size", 0)))
    conn.execute("PRAGMA mmap_size = %d" % int(pragmas.get("mmap_size",
                                                           session.manifest["database"]["byte_size"])))
    open_us = (time.monotonic_ns() - t0) / 1000.0
    tq = time.monotonic_ns()
    try:
        row = oracle.run_read(conn, key)
    except sqlite3.Error as e:  # pragma: no cover
        conn.close()
        return None, open_us, (time.monotonic_ns() - tq) / 1000.0, str(e)
    q_us = (time.monotonic_ns() - tq) / 1000.0
    conn.close()
    return row, open_us, q_us, err


def _envelope(session, request, stage, message, base=None):
    """Complete error envelope; measured_valid is always False."""
    resp = base or {}
    resp.setdefault("request_id", request.get("request_id"))
    if session is not None:
        resp.setdefault("process_uuid", session.process_uuid)
        resp.setdefault("pid", session.pid)
    resp["error"] = message
    resp["error_stage"] = stage
    resp["measured_valid"] = False
    return resp


def handle(request, session):
    """Fail-closed core handler. Enforces every gate regardless of caller."""
    t_handler = time.monotonic_ns()

    # ---- stage: overlap guard (serialize the whole measured critical section) ----
    if not session.critical_lock.acquire(blocking=False):
        return _envelope(session, request, "concurrency",
                         "overlapping invocation rejected (concurrency must be 1)")
    try:
        resp = {"error": None, "error_stage": None, "sqlite_error": None}

        # ---- stage: artifact validation (fail closed) ----
        if not session.validated:
            return _envelope(session, request, "artifact_validation",
                             "session not validated: " + "; ".join(session.validation_reasons),
                             resp)

        # ---- stage: request semantics ----
        sem = validate_request_semantics(request, session)
        if sem:
            return _envelope(session, request, "request", "; ".join(sem), resp)

        strategy = request["strategy"]
        workload = request["workload"]
        seed = request["seed"]
        first_op = request["first_operation_id"]
        diagnostic = request["diagnostic_mode"]
        cold_reset_requested = request["cold_reset"]
        handle_mode = request.get("handle_mode", "warm")

        resp.update(session.identity_fields())
        resp["invocation_counter"] = session.next_invocation()
        resp.update({"workload": workload, "strategy": strategy, "seed": seed,
                     "first_operation_id": first_op, "handle_mode": handle_mode,
                     "diagnostic_mode": diagnostic})

        if strategy not in SUPPORTED_STRATEGIES:
            return _envelope(session, request, "request",
                             "unsupported strategy: %s" % strategy, resp)

        # ---- stage: identity gate ----
        if session.db_identity_changed():
            return _envelope(session, request, "identity",
                             "db device/inode changed since process init", resp)
        exp = request.get("expected_artifact_manifest_hash")
        if not exp or exp != session.artifact_manifest_sha256:
            return _envelope(session, request, "identity",
                             "expected_artifact_manifest_hash empty or mismatch", resp)

        # ---- stage: measured mode requires cold_reset=True ----
        if not cold_reset_requested and not diagnostic:
            return _envelope(session, request, "cold_reset_required",
                             "measured mode requires cold_reset=true", resp)

        # trace / oracle metadata (cached at init; select is off the critical path)
        trace_rel, trace_sha = session.trace_meta(workload, seed)
        resp["trace_sha256"] = trace_sha
        plan = session.manifest["strategy_plans"]["2d"]
        resp["plan_sha256"] = plan["sha256"] if strategy == "2d" else ""
        oc = session.oracle_for(workload, seed, first_op)
        if oc is None:
            return _envelope(session, request, "oracle",
                             "no oracle entry for %s/%s/%s" % (workload, seed, first_op), resp)
        key = oc["key"]
        resp["oracle_expected_hit"] = oc["expected_hit"]
        resp["oracle_expected_digest"] = oc["expected_digest"]
        resp["relevant_pages_total"] = session.manifest["expected_relevant_page_count"]
        resp["cold_reset_requested"] = cold_reset_requested

        # ---- stage: cold reset + efficacy verification ----
        try:
            if cold_reset_requested:
                t0 = time.monotonic_ns()
                diag = residency.cold_reset_and_verify(session.db_path,
                                                       session.interior_offsets)
                resp["reset_us"] = (time.monotonic_ns() - t0) / 1000.0
            else:
                diag = {"resident_pages_before_reset": None,
                        "resident_interiors_before_reset": None,
                        "attempted_methods": [], "cold_reset_method": "none",
                        "resident_pages_after_reset": None,
                        "resident_interiors_after_reset": None,
                        "cold_reset_succeeded": False, "cold_threshold_passed": False}
                resp["reset_us"] = 0.0
        except OSError as e:
            return _envelope(session, request, "cold_reset",
                             "cold reset failed: %s" % e, resp)
        resp.update({k: diag[k] for k in (
            "resident_pages_before_reset", "resident_interiors_before_reset",
            "attempted_methods", "cold_reset_method", "resident_pages_after_reset",
            "resident_interiors_after_reset", "cold_reset_succeeded",
            "cold_threshold_passed")})

        # fail closed: if the cold gate fails and we are NOT diagnostic, return
        # BEFORE any select/deliver/open/query.
        if not diag["cold_threshold_passed"] and not diagnostic:
            resp["measured_valid"] = False
            resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
            resp["error_stage"] = "cold_gate"
            return resp

        # ---- stage: select (cached plan; off critical path) ----
        try:
            t0 = time.monotonic_ns()
            offsets = select_offsets(strategy, session)
            resp["select_us"] = (time.monotonic_ns() - t0) / 1000.0
        except ValueError as e:
            return _envelope(session, request, "select", str(e), resp)
        resp["selected_page_count"] = len(offsets)
        resp["selected_interior_count"] = sum(1 for o in offsets
                                              if o in session.interior_offset_set)
        resp["selected_leaf_count"] = len(offsets) - resp["selected_interior_count"]

        # ---- stage: deliver (fresh mapping) ----
        try:
            pm = residency.PageMap(session.db_path)
            try:
                t0 = time.monotonic_ns()
                delivered = pm.deliver_willneed(offsets) if offsets else 0
                resp["deliver_us"] = (time.monotonic_ns() - t0) / 1000.0
                resp["delivered_page_count"] = delivered
                vec = pm.residency_vector()
                resp["resident_interiors_after_prefetch"] = residency.count_in(
                    vec, session.interior_offset_set)
            finally:
                pm.close()
        except OSError as e:
            return _envelope(session, request, "deliver",
                             "delivery failed: %s" % e, resp)

        # ---- stage: query (warm or standalone) ----
        try:
            row, open_us, q_us, sqlite_err = _run_query(session, key, handle_mode)
        except Exception as e:  # pragma: no cover
            return _envelope(session, request, "query", "query failed: %s" % e, resp)
        resp["open_us"] = open_us
        resp["first_query_us"] = q_us
        resp["sqlite_error"] = sqlite_err
        hit, digest = oracle.digest_row(row)
        resp["query_hit"] = hit
        resp["result_digest"] = digest

        # ---- stage: correctness oracle ----
        oracle_ok = (hit == oc["expected_hit"] and digest == oc["expected_digest"]
                     and sqlite_err is None)
        resp["oracle_passed"] = oracle_ok
        resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
        if diagnostic:
            resp["measured_valid"] = None
        else:
            resp["measured_valid"] = bool(diag["cold_threshold_passed"] and oracle_ok)
        return resp
    finally:
        session.critical_lock.release()


def main(params):
    """OpenWhisk entrypoint."""
    params = params or {}
    schema = validate_request_schema(params)
    if schema:
        return {"error": "; ".join(schema), "error_stage": "request",
                "measured_valid": False, "request_id": params.get("request_id")}
    session = get_session()
    if not session.validated:
        return {"error": "artifact validation failed: "
                + "; ".join(session.validation_reasons),
                "error_stage": "artifact_validation", "measured_valid": False,
                "request_id": params.get("request_id")}
    out = handle(params, session)
    out["request_id"] = params.get("request_id")
    return out
