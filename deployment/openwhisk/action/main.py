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
    from . import residency, oracle, sqlite_bridge
    from .session import Session, validate_request_semantics
except ImportError:  # pragma: no cover - OpenWhisk flat layout
    import residency
    import oracle
    import sqlite_bridge
    from session import Session, validate_request_semantics

SUPPORTED_STRATEGIES = ("baseline", "2d", "layers_5", "layers_92", "2e_K10",
                        "2f_slru", "2e_K500", "leaf_freq_K10", "leaf_rand_K10",
                        "2f_top102", "learned_markov_102", "2f_top28",
                        "learned_markov_28", "2f_top14", "learned_markov_14",
                        "2e_K40", "2e_K92", "lp_sorted", "lp_shuf")
HANDLE_MODES = ("warm", "standalone")
REQUIRED_REQUEST_FIELDS = ("request_id", "workload", "strategy", "seed",
                           "first_operation_id", "diagnostic_mode", "cold_reset",
                           "expected_artifact_manifest_hash", "pair_id",
                           "repetition_id", "schedule_position", "schedule_seed",
                           "run_config_sha256", "expected_action_image_digest")
# request identity fields echoed verbatim in the response
ECHO_FIELDS = ("pair_id", "repetition_id", "schedule_position", "schedule_seed",
               "run_config_sha256", "expected_action_image_digest", "handle_mode")
# exact per-strategy delivery invariants required for measured validity. STATIC
# strategies carry globally fixed counts here; KEYED strategies (e.g. 2e_K10) are
# per-(workload,seed) and derive their expected counts from the validated frozen
# plan metadata at request time (see delivery_invariants_for) -- not hard-coded.
DELIVERY_INVARIANTS = {
    "baseline": {"selected_page_count": 0, "selected_interior_count": 0,
                 "selected_leaf_count": 0, "delivered_page_count": 0},
    "2d": {"selected_page_count": 92, "selected_interior_count": 92,
           "selected_leaf_count": 0, "delivered_page_count": 92},
    "layers_5": {"selected_page_count": 5, "selected_interior_count": 5,
                 "selected_leaf_count": 0, "delivered_page_count": 5},
    "layers_92": {"selected_page_count": 92, "selected_interior_count": 92,
                  "selected_leaf_count": 0, "delivered_page_count": 92},
}
# strategies whose plan varies by (workload, seed); expected counts come from the
# frozen keyed plan, never a global constant. The secondary strategies are all
# keyed: their interior/leaf split is validated against the per-seed manifest
# metadata (2f_top102/learned_markov_102 carry an EMERGENT split, not the 92
# skeleton), so no DELIVERY_INVARIANTS entry and no per-strategy runtime code.
KEYED_STRATEGIES = ("2e_K10", "2f_slru", "2e_K500", "leaf_freq_K10",
                    "leaf_rand_K10", "2f_top102", "learned_markov_102",
                    "2f_top28", "learned_markov_28", "2f_top14",
                    "learned_markov_14", "2e_K40", "2e_K92",
                    "lp_sorted", "lp_shuf")
# libprefetch (lp) strategies whose delivery lever is the ORDER of synchronous
# page-sized preads (NOT async MADV_WILLNEED). They are keyed like any other keyed
# strategy for page selection, but the deliver stage dispatches to an ordered pread
# loop that preserves the frozen sequence exactly (see deliver dispatch below).
PREAD_ORDERED_STRATEGIES = ("lp_sorted", "lp_shuf")
# The frozen shuffle seed for lp_shuf's ordered plan. The action never re-shuffles
# (the order is baked into the frozen keyed plan and validated order-sensitively);
# this constant is echoed for provenance only.
LP_SHUF_SEED = 424242
_SESSION = None

# The image bakes the artifacts under a FIXED absolute root. OpenWhisk extracts
# the action code archive under a per-activation path (e.g. /action/1/), so
# __file__ and cwd point at the extracted code, NOT the baked artifacts, and must
# never be used to locate them. Resolution order is: an explicit env override (if
# the platform preserves it) else these image-absolute defaults.
IMAGE_ARTIFACT_ROOT = "/action/artifacts"
IMAGE_ARTIFACT_MANIFEST = IMAGE_ARTIFACT_ROOT + "/deployment/openwhisk/config/artifacts.json"


def artifact_root():
    """Image-absolute artifact root, never derived from __file__/cwd."""
    return os.environ.get("OW_ARTIFACT_ROOT") or IMAGE_ARTIFACT_ROOT


def artifact_manifest_path():
    """Image-absolute manifest path, never derived from __file__/cwd."""
    return os.environ.get("OW_ARTIFACT_MANIFEST") or IMAGE_ARTIFACT_MANIFEST


def get_session():
    """Module-singleton warm Session. Validates artifacts and opens the warm
    handle exactly once; if validation fails the session is returned unvalidated
    so the handler refuses measured mode. Artifacts are resolved against the
    fixed image root, not the OpenWhisk-extracted code path."""
    global _SESSION
    if _SESSION is None:
        s = Session(artifact_manifest_path(), resolve_root=artifact_root())
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
    if not isinstance(request["first_operation_id"], int) or isinstance(
            request["first_operation_id"], bool) or request["first_operation_id"] < 0:
        problems.append("first_operation_id must be a non-negative int")
    hm = request.get("handle_mode", "warm")
    if hm not in HANDLE_MODES:
        problems.append("handle_mode must be one of %s" % (HANDLE_MODES,))
    return tuple(problems)


# retained for older callers/tests
def validate_request(request):
    return validate_request_schema(request)


def select_offsets(strategy, session, workload=None, seed=None):
    """Return the delivery offsets for a request from the process-init cache.
    STATIC strategies ignore workload/seed: baseline delivers nothing; 2d delivers
    exactly the 92 mandatory interiors; layers_5 delivers the frozen 5-interior
    prefix. KEYED strategies (2e_K10) select the frozen plan for the exact request
    (workload, seed). No FS parsing or plan generation happens here -- every plan
    was parsed + cached at process init. Fails closed on any count or
    interior/leaf-membership disagreement."""
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
    if strategy == "layers_5":
        offs = session.static_plan_offsets.get("layers_5")
        expected = session.manifest["strategy_plans"]["layers_5"]["expected_pages"]
        if offs is None or len(offs) != expected or expected != 5:
            raise ValueError("layers_5 plan has %s offsets, expected 5"
                             % (None if offs is None else len(offs)))
        if any(o not in session.interior_offset_set for o in offs):
            raise ValueError("layers_5 plan contains a non-interior offset")
        return list(offs)
    if strategy == "layers_92":
        offs = session.static_plan_offsets.get("layers_92")
        expected = session.manifest["strategy_plans"]["layers_92"]["expected_pages"]
        if offs is None or len(offs) != expected or expected != 92:
            raise ValueError("layers_92 plan has %s offsets, expected 92"
                             % (None if offs is None else len(offs)))
        if any(o not in session.interior_offset_set for o in offs):
            raise ValueError("layers_92 plan contains a non-interior offset")
        return list(offs)
    if strategy in KEYED_STRATEGIES:
        plan = session.strategy_plan(strategy, workload, seed)
        if plan is None:
            raise ValueError("no keyed %s plan for workload=%r seed=%r"
                             % (strategy, workload, seed))
        offs = plan["offsets"]
        exp = plan["expected_pages"]
        if exp is not None and len(offs) != exp:
            raise ValueError("%s plan has %d offsets, expected %s"
                             % (strategy, len(offs), exp))
        interior = sum(1 for o in offs if o in session.interior_offset_set)
        leaf = len(offs) - interior
        eip = plan["expected_interior_pages"]; elp = plan["expected_leaf_pages"]
        if eip is not None and interior != eip:
            raise ValueError("%s plan has %d interiors, expected %s"
                             % (strategy, interior, eip))
        if elp is not None and leaf != elp:
            raise ValueError("%s plan has %d leaves, expected %s"
                             % (strategy, leaf, elp))
        return list(offs)
    raise ValueError("unsupported strategy: %s" % strategy)


def delivery_invariants_for(strategy, session, workload, seed):
    """Expected delivery counts for a request. STATIC strategies use the global
    DELIVERY_INVARIANTS; KEYED strategies derive the four counts from the validated
    frozen plan metadata for the exact (workload, seed). Fails closed if a keyed
    plan is absent."""
    if strategy in DELIVERY_INVARIANTS:
        return DELIVERY_INVARIANTS[strategy]
    plan = session.strategy_plan(strategy, workload, seed)
    if plan is None:
        raise ValueError("no keyed %s plan for workload=%r seed=%r"
                         % (strategy, workload, seed))
    return {"selected_page_count": plan["expected_pages"],
            "selected_interior_count": plan["expected_interior_pages"],
            "selected_leaf_count": plan["expected_leaf_pages"],
            "delivered_page_count": plan["expected_pages"]}


def _run_query(session, key, handle_mode):
    """Execute the exact canonical query via the ctypes bridge and return
    (hit, payload, open_us, query_us, sqlite_error, cache_hit, cache_miss).
    Warm mode reuses the process handle + prepared statement (no open cost on the
    critical path); standalone opens a fresh read-only handle (prepare included)
    and pays open_us. The query timing is the sqlite3_step boundary only."""
    p = session.pragmas()
    if handle_mode == "warm":
        wdb = session.open_warm_handle()
        open_us = 0.0
        try:
            wdb.cache_hit_miss(reset=True)   # zero the counters around this query
            hit, payload, q_us = wdb.query(key)
            ch, cm = wdb.cache_hit_miss(reset=True)
        except sqlite_bridge.SqliteError as e:
            return 0, None, open_us, 0.0, str(e), None, None
        return hit, payload, open_us, q_us, None, ch, cm
    # standalone: fresh handle, measured open cost (open_v2 + prepare_v2)
    t0 = time.monotonic_ns()
    try:
        wdb = sqlite_bridge.WarmDb(session.db_path,
                                   cache_size=int(p.get("cache_size", 0)),
                                   mmap_size=int(p.get("mmap_size", 0)))
    except sqlite_bridge.SqliteError as e:
        return 0, None, 0.0, 0.0, str(e), None, None
    open_us = (time.monotonic_ns() - t0) / 1000.0
    try:
        wdb.cache_hit_miss(reset=True)
        hit, payload, q_us = wdb.query(key)
        ch, cm = wdb.cache_hit_miss(reset=True)
    except sqlite_bridge.SqliteError as e:
        wdb.close()
        return 0, None, open_us, 0.0, str(e), None, None
    wdb.close()
    return hit, payload, open_us, q_us, None, ch, cm


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
        # A successful response carries NO top-level "error" key: OpenWhisk treats
        # any top-level "error" (even null) as an application error. "error" is
        # added only by _envelope() on an actual failure. error_stage stays None
        # on success (not the platform-magic key).
        resp = {"error_stage": None, "sqlite_error": None}

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
        # echo pair/schedule/run-config/image identity verbatim
        for f in ("pair_id", "repetition_id", "schedule_position", "schedule_seed",
                  "run_config_sha256", "expected_action_image_digest"):
            resp[f] = request.get(f)

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
        # plan sha for the requested strategy: static plans carry one on the
        # strategy_plans entry; keyed plans (2e_K10) carry a per-(workload,seed) sha
        # on the frozen keyed plan; baseline has none.
        kp = session.strategy_plan(strategy, workload, seed)
        if kp is not None:
            resp["plan_sha256"] = kp["plan_sha256"] or ""
        else:
            splan = session.manifest["strategy_plans"].get(strategy, {})
            resp["plan_sha256"] = splan.get("sha256") or ""
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
                # release reclaimable pager heap so SQLite-held page copies do not
                # defeat the OS cold reset (documented mechanism).
                if session.warmdb is not None:
                    resp["sqlite_released_bytes"] = session.warmdb.release_memory()
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
            offsets = select_offsets(strategy, session, workload, seed)
            inv = delivery_invariants_for(strategy, session, workload, seed)
            resp["select_us"] = (time.monotonic_ns() - t0) / 1000.0
        except ValueError as e:
            return _envelope(session, request, "select", str(e), resp)
        resp["selected_page_count"] = len(offsets)
        resp["selected_interior_count"] = sum(1 for o in offsets
                                              if o in session.interior_offset_set)
        resp["selected_leaf_count"] = len(offsets) - resp["selected_interior_count"]

        # ---- stage: deliver (fresh mapping) ----
        # Two delivery mechanisms coexist. Every existing strategy keeps its async
        # per-page MADV_WILLNEED delivery (delivery_method=madvise_willneed). The
        # libprefetch (lp) strategies use a synchronous ORDERED page-sized pread
        # loop (delivery_method=pread_ordered): lp's experimental lever is the ORDER
        # of the preads (offset-ascending for lp_sorted, seed-shuffled for lp_shuf),
        # so the frozen sequence is delivered exactly and NEVER coalesced/async/
        # mmap-touched. The order is baked into the frozen keyed plan (offsets are
        # returned by select_offsets in plan order) and validated order-sensitively
        # by session._validate_keyed_plans; deliver_us is measured around the whole
        # ordered loop (lp's primary quantity -- see the lp metric note).
        is_lp = strategy in PREAD_ORDERED_STRATEGIES
        try:
            pm = residency.PageMap(session.db_path)
            try:
                if is_lp:
                    kp = session.strategy_plan(strategy, workload, seed)
                    t0 = time.monotonic_ns()
                    delivered, delivered_bytes = (
                        pm.deliver_pread_ordered(offsets) if offsets else (0, 0))
                    resp["deliver_us"] = (time.monotonic_ns() - t0) / 1000.0
                    resp["delivery_method"] = "pread_ordered"
                    resp["delivery_order"] = ("file_offset_ascending"
                                              if strategy == "lp_sorted"
                                              else "seed_shuffled")
                    resp["shuffle_seed"] = (LP_SHUF_SEED if strategy == "lp_shuf"
                                            else None)
                    resp["delivered_page_count"] = delivered
                    resp["delivered_bytes"] = delivered_bytes
                    resp["ordered_plan_sha256"] = (kp.get("plan_sha256")
                                                   if kp else None)
                else:
                    t0 = time.monotonic_ns()
                    delivered = pm.deliver_willneed(offsets) if offsets else 0
                    resp["deliver_us"] = (time.monotonic_ns() - t0) / 1000.0
                    resp["delivery_method"] = "madvise_willneed"
                    resp["delivered_page_count"] = delivered
                # residency/correctness gates run for BOTH mechanisms
                vec = pm.residency_vector()
                resp["resident_interiors_after_prefetch"] = residency.count_in(
                    vec, session.interior_offset_set)
            finally:
                pm.close()
        except OSError as e:
            return _envelope(session, request, "deliver",
                             "delivery failed: %s" % e, resp)

        # ---- stage: query (warm or standalone) via canonical bridge ----
        try:
            hit, payload, open_us, q_us, sqlite_err, ch, cm = _run_query(
                session, key, handle_mode)
        except Exception as e:  # pragma: no cover
            return _envelope(session, request, "query", "query failed: %s" % e, resp)
        resp["open_us"] = open_us
        resp["first_query_us"] = q_us
        resp["sqlite_error"] = sqlite_err
        resp["sqlite_cache_hit"] = ch
        resp["sqlite_cache_miss"] = cm
        hit, digest = oracle.digest_payload(hit, payload)
        resp["query_hit"] = hit
        resp["result_digest"] = digest

        # ---- stage: correctness oracle + strategy delivery validity ----
        oracle_ok = (hit == oc["expected_hit"] and digest == oc["expected_digest"]
                     and sqlite_err is None)
        resp["oracle_passed"] = oracle_ok
        delivery_ok = all(resp.get(k) == v for k, v in inv.items())
        resp["delivery_valid"] = delivery_ok
        resp["handler_total_us"] = (time.monotonic_ns() - t_handler) / 1000.0
        if diagnostic:
            resp["measured_valid"] = None
        else:
            resp["measured_valid"] = bool(diag["cold_threshold_passed"] and oracle_ok
                                          and delivery_ok and sqlite_err is None)
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
    # The deployment binds the immutable image identity via `wsk ... -p
    # OW_ACTION_IMAGE_DIGEST <digest>`, which OpenWhisk delivers as an action
    # INPUT PARAMETER (not an OS env var). Bind it as the session's
    # deployment-bound image identity before any measured validation.
    bound_digest = params.get("OW_ACTION_IMAGE_DIGEST")
    if bound_digest:
        session.bind_deployment_image_digest(bound_digest)
    if not session.validated:
        return {"error": "artifact validation failed: "
                + "; ".join(session.validation_reasons),
                "error_stage": "artifact_validation", "measured_valid": False,
                "request_id": params.get("request_id")}
    out = handle(params, session)
    out["request_id"] = params.get("request_id")
    return out
