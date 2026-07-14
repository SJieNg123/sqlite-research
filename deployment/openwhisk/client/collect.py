#!/usr/bin/env python3
"""Invocation collector for the OpenWhisk cold-start batch.

Phase 5A.2 does NOT invoke OpenWhisk. This module provides collection, hardened
retention, and warm-session classification, plus the output schema, so the next
phase drives real invocations by supplying an ``invoke_fn`` (and optional
``activation_fn``). It never calls ``wsk`` or the network itself.

Retention is strict: a row is retained only if the response is a well-formed
measured record whose identity matches the request and the run config, whose
gates all passed, and whose activation (if present) succeeded. Diagnostic rows
are never valid for performance analysis. Invoke/activation exceptions are
recorded as invalid rows without aborting the run, and duplicate request ids are
rejected.

Output layout (created only under an explicit --outdir; never a canonical
results directory):

  results/openwhisk/<run_id>/
    raw_invocations.jsonl  request + response + client timing + activation
    activation_records.jsonl
    summary.csv
    environment.txt / run_config.json / README.md
"""
import argparse
import csv
import json
import os
import time

SUMMARY_FIELDS = [
    "request_id", "invocation_counter", "process_uuid", "pid",
    "artifact_manifest_sha256", "action_image_digest", "run_config_sha256",
    "db_device", "db_inode", "db_sha256", "workload", "strategy", "handle_mode",
    "seed", "first_operation_id", "pair_id", "repetition_id", "schedule_position",
    "trace_sha256", "plan_sha256", "diagnostic_mode",
    "cold_reset_requested", "cold_reset_method", "cold_reset_succeeded",
    "relevant_pages_total", "resident_interiors_before_reset",
    "resident_interiors_after_reset", "resident_interiors_after_prefetch",
    "cold_threshold_passed", "selected_page_count", "selected_interior_count",
    "selected_leaf_count", "delivered_page_count", "delivery_valid",
    "reset_us", "open_us", "select_us", "deliver_us", "first_query_us",
    "handler_total_us", "query_hit", "result_digest",
    "oracle_expected_hit", "oracle_expected_digest", "oracle_passed",
    "sqlite_cache_miss", "measured_valid", "sqlite_error", "error", "error_stage",
    "activation_id", "activation_ok", "client_send_utc", "client_recv_utc",
    "client_elapsed_us", "warm_session_id", "valid", "exclusion_reason",
]

# request fields that must equal the response verbatim
IDENTITY_MATCH = ("request_id", "workload", "strategy", "seed",
                  "first_operation_id", "handle_mode", "pair_id")


def warm_session_id(resp):
    return "%s:%s:%s" % (resp.get("process_uuid"), resp.get("pid"),
                         resp.get("db_inode"))


def _activation_ok(activation):
    """True if the platform activation indicates success. None (local dry-run)
    is treated as 'no platform layer', i.e. not a failure."""
    if activation is None:
        return True
    if activation.get("error"):
        return False
    resp = activation.get("response") or {}
    if resp.get("success") is False:
        return False
    sc = activation.get("statusCode", activation.get("status"))
    if isinstance(sc, int) and sc != 0:
        return False
    if isinstance(sc, str) and sc not in ("", "success", "0"):
        return False
    return True


def classify(request, resp, prev_counter, run_config, activation=None):
    """Return (valid, exclusion_reason). Fully hardened per PROTOCOL. Never raises.
    run_config supplies the expected identities:
      run_config["artifact_manifest_sha256"], ["action_image_digest"],
      ["run_config_sha256"]."""
    if not isinstance(resp, dict):
        return False, "response_not_dict"
    # request/response identity
    for f in IDENTITY_MATCH:
        if resp.get(f) != request.get(f):
            return False, "identity_mismatch:%s" % f
    # diagnostic rows are never valid for performance
    if resp.get("diagnostic_mode") is not False:
        return False, "diagnostic_row"
    if resp.get("error") or resp.get("error_stage"):
        return False, "action_error:%s" % (resp.get("error_stage") or "?")
    if resp.get("sqlite_error"):
        return False, "sqlite_error"
    if not _activation_ok(activation):
        return False, "activation_failed"
    # gates
    if resp.get("cold_reset_requested") is not True:
        return False, "cold_reset_not_requested"
    if resp.get("cold_threshold_passed") is not True:
        return False, "cold_threshold_not_passed"
    if resp.get("oracle_passed") is not True:
        return False, "oracle_failed"
    if resp.get("delivery_valid") is not True:
        return False, "delivery_invalid"
    if resp.get("measured_valid") is not True:
        return False, "measured_valid_false"
    # identity vs run config
    if resp.get("artifact_manifest_sha256") != run_config.get("artifact_manifest_sha256"):
        return False, "manifest_hash_ne_run_config"
    if resp.get("action_image_digest") != run_config.get("action_image_digest"):
        return False, "image_digest_ne_run_config"
    if resp.get("run_config_sha256") != run_config.get("run_config_sha256"):
        return False, "run_config_sha_mismatch"
    # process identity + counter
    for f in ("process_uuid", "pid", "db_device", "db_inode"):
        if resp.get(f) in (None, ""):
            return False, "missing_%s" % f
    ctr = resp.get("invocation_counter")
    if not isinstance(ctr, int) or isinstance(ctr, bool) or ctr <= 0:
        return False, "bad_invocation_counter"
    sid = warm_session_id(resp)
    prev = prev_counter.get(sid)
    if prev is not None and ctr <= prev:
        return False, "non_monotonic_invocation_counter"
    return True, ""


def collect(run_id, requests, invoke_fn, outdir, run_config=None,
            activation_fn=None):
    """Drive requests through invoke_fn, writing the output schema. Catches
    invoke/activation exceptions (records an invalid row, continues) and rejects
    duplicate request ids."""
    run_config = run_config or {}
    run_dir = os.path.join(outdir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    raw_p = os.path.join(run_dir, "raw_invocations.jsonl")
    act_p = os.path.join(run_dir, "activation_records.jsonl")
    sum_p = os.path.join(run_dir, "summary.csv")

    prev_counter = {}
    seen_request_ids = set()
    n_valid = 0
    with open(raw_p, "w") as raw, open(act_p, "w") as act, \
            open(sum_p, "w", newline="") as sumf:
        writer = csv.DictWriter(sumf, fieldnames=SUMMARY_FIELDS,
                                extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for req in requests:
            rid = req.get("request_id")
            if rid in seen_request_ids:
                row = {"request_id": rid, "valid": False,
                       "exclusion_reason": "duplicate_request_id"}
                writer.writerow(row)
                raw.write(json.dumps({"request": req, "error": "duplicate_request_id"}) + "\n")
                continue
            seen_request_ids.add(rid)

            send, send_ns = time.time(), time.monotonic_ns()
            resp, invoke_err = None, None
            try:
                resp = invoke_fn(req)
            except Exception as e:  # invoke failure must not abort the run
                invoke_err = repr(e)
            recv_ns, recv = time.monotonic_ns(), time.time()

            activation = None
            if activation_fn is not None and invoke_err is None:
                try:
                    activation = activation_fn(req, resp)
                except Exception as e:
                    activation = {"error": "activation_fn_exception:%s" % e}

            if invoke_err is not None:
                valid, reason, resp = False, "invoke_exception", {}
            else:
                valid, reason = classify(req, resp, prev_counter, run_config, activation)
                if resp.get("invocation_counter") is not None:
                    prev_counter[warm_session_id(resp)] = resp["invocation_counter"]

            record = {"request": req, "response": resp, "activation": activation,
                      "invoke_error": invoke_err, "client_send_utc": send,
                      "client_recv_utc": recv,
                      "client_elapsed_us": (recv_ns - send_ns) / 1000.0}
            raw.write(json.dumps(record, default=str) + "\n")
            act.write(json.dumps({"request_id": rid, "activation": activation},
                                 default=str) + "\n")

            flat = dict(resp) if isinstance(resp, dict) else {}
            flat.update({"request_id": rid,
                         "activation_id": (activation or {}).get("activationId")
                         if isinstance(activation, dict) else None,
                         "activation_ok": _activation_ok(activation),
                         "client_send_utc": send, "client_recv_utc": recv,
                         "client_elapsed_us": record["client_elapsed_us"],
                         "warm_session_id": warm_session_id(resp) if isinstance(resp, dict) else None,
                         "valid": valid, "exclusion_reason": reason})
            writer.writerow(flat)
            n_valid += int(valid)

    if run_config:
        with open(os.path.join(run_dir, "run_config.json"), "w") as f:
            json.dump(run_config, f, indent=2, default=str)
    with open(os.path.join(run_dir, "README.md"), "w") as f:
        f.write("# OpenWhisk cold-start run `%s`\n\nSeparate result batch; "
                "absolute latencies are NOT comparable to the local benchmark "
                "batches. See deployment/openwhisk/PROTOCOL.md.\n" % run_id)
    return {"run_dir": run_dir, "n_total": len(requests), "n_valid": n_valid}


def main():  # pragma: no cover - Phase 5A.2 never invokes OpenWhisk
    ap = argparse.ArgumentParser(description="Collector (no OpenWhisk in 5A.2).")
    ap.add_argument("--outdir", required=True)
    ap.parse_args()
    raise SystemExit("Phase 5A.2: real invocation is out of scope. Provide an "
                     "invoke_fn via collect() from the next-phase driver.")


if __name__ == "__main__":
    main()
