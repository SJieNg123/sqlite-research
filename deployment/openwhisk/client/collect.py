#!/usr/bin/env python3
"""Invocation collector for the OpenWhisk cold-start batch.

Phase 5A does NOT invoke OpenWhisk. This module provides the collection and
warm-session-classification logic and its output schema so the next phase can
drive real invocations by supplying an ``invoke_fn``. It never calls ``wsk`` or
the network itself; a local dry-run passes a fake ``invoke_fn`` that returns a
handler response dict.

Output layout (created only under an explicit --outdir; never auto-writes to a
canonical results directory):

  results/openwhisk/<run_id>/
    raw_invocations.jsonl      one line per invocation: request, response, client timing
    activation_records.jsonl   one line per activation-metadata blob (platform)
    summary.csv                per-invocation flattened key fields + validity
    environment.txt            captured by capture_environment.sh
    run_config.json            the run configuration used
    README.md                  provenance note
"""
import argparse
import csv
import json
import os
import time
import uuid

# Fields copied verbatim from the action response into summary.csv.
SUMMARY_FIELDS = [
    "request_id", "invocation_counter", "process_uuid", "pid",
    "artifact_manifest_sha256", "action_image_digest", "db_device", "db_inode",
    "db_sha256", "workload", "strategy", "handle_mode", "seed",
    "first_operation_id", "trace_sha256", "plan_sha256",
    "cold_reset_requested", "cold_reset_method", "cold_reset_succeeded",
    "relevant_pages_total", "resident_pages_before_reset",
    "resident_pages_after_reset", "resident_interiors_before_reset",
    "resident_interiors_after_reset", "resident_interiors_after_prefetch",
    "cold_threshold_passed", "selected_page_count", "selected_interior_count",
    "selected_leaf_count", "delivered_page_count",
    "reset_us", "open_us", "select_us", "deliver_us", "first_query_us",
    "handler_total_us", "query_hit", "result_digest",
    "oracle_expected_hit", "oracle_expected_digest", "oracle_passed",
    "measured_valid", "sqlite_error", "error", "error_stage",
    "client_send_utc", "client_recv_utc", "client_elapsed_us",
    "warm_session_id", "valid", "exclusion_reason",
]


def warm_session_id(resp):
    """Derive a stable warm-session id from process identity (NOT the activation
    id). Invocations sharing (process_uuid, pid, db_inode) are one session."""
    return "%s:%s:%s" % (resp.get("process_uuid"), resp.get("pid"),
                         resp.get("db_inode"))


def classify(resp, prev_counter_by_session):
    """Return (valid, exclusion_reason). Applies the retention rules of
    PROTOCOL.md without interpreting latency."""
    if resp.get("error"):
        return False, "action_error:%s" % resp.get("error_stage", "?")
    if resp.get("sqlite_error"):
        return False, "sqlite_error"
    if not resp.get("process_uuid"):
        return False, "no_process_identity"
    if not resp.get("cold_threshold_passed"):
        return False, "cold_threshold_not_passed"
    # correctness is the frozen oracle (exact expected hit/not-found + digest),
    # NOT a hard-coded query_hit == 1.
    if resp.get("oracle_passed") is not True:
        return False, "oracle_failed"
    sid = warm_session_id(resp)
    ctr = resp.get("invocation_counter")
    prev = prev_counter_by_session.get(sid)
    if prev is not None and ctr is not None and ctr <= prev:
        return False, "non_monotonic_invocation_counter"
    return True, ""


def collect(run_id, requests, invoke_fn, outdir, run_config=None,
            activation_fn=None):
    """Drive a sequence of requests through invoke_fn, writing the output schema.

    invoke_fn(request) -> response dict (handler contract).
    activation_fn(request, response) -> platform activation metadata dict | None.
    """
    run_dir = os.path.join(outdir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    raw_p = os.path.join(run_dir, "raw_invocations.jsonl")
    act_p = os.path.join(run_dir, "activation_records.jsonl")
    sum_p = os.path.join(run_dir, "summary.csv")

    prev_counter = {}
    n_valid = 0
    with open(raw_p, "w") as raw, open(act_p, "w") as act, \
            open(sum_p, "w", newline="") as sumf:
        writer = csv.DictWriter(sumf, fieldnames=SUMMARY_FIELDS,
                                extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for req in requests:
            send = time.time()
            send_ns = time.monotonic_ns()
            resp = invoke_fn(req)
            recv_ns = time.monotonic_ns()
            recv = time.time()
            activation = activation_fn(req, resp) if activation_fn else None

            valid, reason = classify(resp, prev_counter)
            sid = warm_session_id(resp)
            if resp.get("invocation_counter") is not None:
                prev_counter[sid] = resp["invocation_counter"]

            record = {"request": req, "response": resp,
                      "client_send_utc": send, "client_recv_utc": recv,
                      "client_elapsed_us": (recv_ns - send_ns) / 1000.0}
            raw.write(json.dumps(record) + "\n")
            act.write(json.dumps({"request_id": req.get("request_id"),
                                  "activation": activation}) + "\n")

            flat = dict(resp)
            flat.update({"client_send_utc": send, "client_recv_utc": recv,
                         "client_elapsed_us": record["client_elapsed_us"],
                         "warm_session_id": sid, "valid": valid,
                         "exclusion_reason": reason})
            writer.writerow(flat)
            n_valid += int(valid)

    if run_config is not None:
        with open(os.path.join(run_dir, "run_config.json"), "w") as f:
            json.dump(run_config, f, indent=2)
    with open(os.path.join(run_dir, "README.md"), "w") as f:
        f.write("# OpenWhisk cold-start run `%s`\n\nSeparate result batch; "
                "absolute latencies are NOT comparable to the local benchmark "
                "batches. See deployment/openwhisk/PROTOCOL.md.\n" % run_id)
    return {"run_dir": run_dir, "n_total": len(requests), "n_valid": n_valid}


def main():  # pragma: no cover - Phase 5A never invokes OpenWhisk
    ap = argparse.ArgumentParser(description="Collector (no OpenWhisk in 5A).")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--run-id", default=None)
    ap.parse_args()
    raise SystemExit("Phase 5A: real invocation is out of scope. Provide an "
                     "invoke_fn via collect() from the next-phase driver.")


if __name__ == "__main__":
    main()
