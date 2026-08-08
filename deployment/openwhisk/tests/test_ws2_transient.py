"""Regression tests for Stage 05 transient-invocation handling (rate-limit safety).

The bug: Apache OpenWhisk Standalone rate-limits to ~60 requests/minute. When the
client tripped that limit ("Too many requests in the last minute"), the invocation
produced no handler response, and 05 misclassified the transport/rate-limit failure
as a "response lacks measured_valid" / identity-or-session violation and hard-stopped
the run.

These tests pin the fail-closed fix:

  * a rate-limit / transport stderr is classified TRANSIENT (retryable), never an
    identity/session violation -- `response_gate.is_transient_invocation_error`;
  * pacing is applied BETWEEN complete pairs, never between a pair's two arms, so
    within-pair adjacency and the frozen AB/BA order are preserved;
  * a bounded retry re-invokes the SAME schedule position / request identity, never
    advancing or reordering, and never leaves a completed resp_*.json unless a real
    handler response was written;
  * a transient failure that never yields a real response cannot become a resumable
    completed measurement (resume still requires a validated real response);
  * a genuine identity / process_uuid session break still hard-stops; and
  * the warm-session ledger reads the runtime `process_uuid` field (fixing the
    "session None" log that read a nonexistent `warm_session_id`).

Genuine logic (transient detection) is imported and exercised functionally; the
shell wiring (pacing gate, retry loop, process_uuid ledger, transient hard-stop
that is NOT labelled identity/session) is pinned against the script on disk, per the
codebase's test conventions.
"""
import importlib.util
import os
import unittest

import _fixture

REPO = _fixture.REPO
WS2 = os.path.join(REPO, "deployment", "openwhisk", "ws2")
MATRIX = os.path.join(WS2, "05_full_matrix.sh")


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "response_gate", os.path.join(WS2, "response_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(p):
    with open(p) as f:
        return f.read()


GATE = _load_gate()


class TestTransientDetection(unittest.TestCase):
    """Case 1: a rate-limit / transport stderr is transient, not identity/session."""

    def test_openwhisk_per_minute_rate_limit_is_transient(self):
        stderr = ("error: Unable to invoke action 'sqlite-coldstart': Too many "
                  "requests in the last minute (count: 61, allowed: 60).")
        self.assertTrue(GATE.is_transient_invocation_error(stderr))

    def test_rate_limit_is_case_insensitive(self):
        self.assertTrue(GATE.is_transient_invocation_error(
            "TOO MANY REQUESTS IN THE LAST MINUTE"))

    def test_generic_429_and_503_are_transient(self):
        for s in ("429 Too Many Requests", "503 Service Unavailable",
                  "connection reset by peer", "connection refused",
                  "connection timed out", "i/o timeout"):
            self.assertTrue(GATE.is_transient_invocation_error(s), s)

    def test_empty_stderr_is_not_transient(self):
        self.assertFalse(GATE.is_transient_invocation_error(""))
        self.assertFalse(GATE.is_transient_invocation_error(None))

    def test_identity_and_semantic_failures_are_not_transient(self):
        # These are real handler-side failures and must NOT be retried as transient.
        for s in ("expected_action_image_digest mismatch",
                  "process_uuid changed mid-session",
                  "unknown workload native_ycsb_c_read_zipf",
                  "measured_valid is False"):
            self.assertFalse(GATE.is_transient_invocation_error(s), s)


class TestTransientCliContract(unittest.TestCase):
    """The shell wiring shells out to `response_gate.py is-transient <file>`."""

    def test_is_transient_subcommand_exists(self):
        txt = _read(os.path.join(WS2, "response_gate.py"))
        self.assertIn('cmd == "is-transient"', txt)
        # exit 0 transient / 1 non-transient / 2 unreadable is the documented contract.
        self.assertIn('print("transient")', txt)
        self.assertIn('print("non-transient")', txt)


class TestPacingBetweenPairs(unittest.TestCase):
    """Case 3: pacing occurs between pairs, never between the two arms of a pair."""

    def setUp(self):
        self.txt = _read(MATRIX)

    def test_delay_is_configurable_with_documented_default(self):
        self.assertIn('WS2_INTER_PAIR_DELAY_SEC="${WS2_INTER_PAIR_DELAY_SEC:-2.2}"', self.txt)

    def test_pacing_is_gated_on_a_pair_transition(self):
        # sleep only when the current pair_id differs from the last INVOKED pair --
        # i.e. never between the two arms that share one pair_id.
        self.assertIn('[ "$cur_pair" != "$LAST_INVOKED_PAIR" ]', self.txt)
        self.assertIn('sleep "$WS2_INTER_PAIR_DELAY_SEC"', self.txt)
        self.assertIn("LAST_INVOKED_PAIR=", self.txt)

    def test_cur_pair_is_derived_from_the_request_pair_id(self):
        self.assertIn('.get("pair_id"', self.txt)

    def test_pacing_recorded_in_stage_metadata(self):
        self.assertIn("pacing.txt", self.txt)

    def test_pacing_is_documented_as_outside_the_measured_action(self):
        # the sleep must be provably outside first_query_us/deliver_us/open_us.
        self.assertIn("first_query_us", self.txt)
        self.assertIn("OUTSIDE the measured action", self.txt)


class TestBoundedRetrySamePosition(unittest.TestCase):
    """Case 2: retry keeps the identical schedule_position / request_id."""

    def setUp(self):
        self.txt = _read(MATRIX)

    def test_retry_helper_reinvokes_same_req_and_resp(self):
        self.assertIn("ws2_invoke_with_retry()", self.txt)
        # the loop passes the SAME $req/$resp for the current position; the helper
        # loops on those exact paths (no re-derivation, no advance).
        self.assertIn('ws2_invoke_with_retry "$OW_ACTION_NAME" "$req" "$resp"', self.txt)

    def test_retry_is_bounded_and_backs_off(self):
        self.assertIn('WS2_MAX_INVOKE_RETRIES="${WS2_MAX_INVOKE_RETRIES:-5}"', self.txt)
        self.assertIn("WS2_RETRY_BACKOFF_BASE_SEC", self.txt)
        self.assertIn("WS2_RETRY_BACKOFF_CAP_SEC", self.txt)
        self.assertIn('[ "$attempt" -ge "$WS2_MAX_INVOKE_RETRIES" ]', self.txt)

    def test_transient_stderr_is_preserved_for_provenance(self):
        self.assertIn(".transient.", self.txt)

    def test_retry_never_keeps_a_partial_response(self):
        # no completed resp until a real handler response exists.
        self.assertIn('rm -f "$resp"', self.txt)


class TestTransientNeverResumableCompletion(unittest.TestCase):
    """Case 4: a transient failure cannot become a resumable completed measurement."""

    def setUp(self):
        self.txt = _read(MATRIX)

    def test_exhausted_transient_hard_stops_without_writing_a_response(self):
        # helper returns 2 on exhaustion; the loop hard-stops and states the schedule
        # was NOT advanced and no resp was created.
        self.assertIn('if [ "$irc" = 2 ]', self.txt)
        self.assertIn("re-run 05 to resume", self.txt)
        self.assertIn("No \\\nresp_${pos}.json was created", self.txt)

    def test_transient_hard_stop_is_not_labelled_identity_or_session(self):
        # the transient die must explicitly disclaim identity/session so provenance
        # is not corrupted.
        i = self.txt.index('if [ "$irc" = 2 ]')
        window = self.txt[i:i + 600]
        self.assertIn("NOT an identity/session violation", window)

    def test_resume_still_requires_a_validated_real_response(self):
        # resume skips only on a classified-valid response; a bare/missing/partial
        # response is never resumed.
        self.assertIn("has a validated real response", self.txt)
        self.assertNotIn("already has a response; skipping", self.txt)


class TestGenuineSessionBreakStillHardStops(unittest.TestCase):
    """Case 5 + 6: process_uuid is read/logged; a real session break hard-stops."""

    def setUp(self):
        self.txt = _read(MATRIX)

    def test_ledger_reads_runtime_process_uuid_not_warm_session_id(self):
        # the "session None" bug read a nonexistent field; the fix reads process_uuid.
        self.assertIn('resp.get("process_uuid")', self.txt)
        self.assertNotIn("warm_session_id", self.txt)

    def test_missing_process_uuid_hard_stops(self):
        self.assertIn("lacks process_uuid", self.txt)

    def test_process_uuid_change_is_a_session_break(self):
        self.assertIn("different process_uuid (session break)", self.txt)

    def test_identity_mismatch_still_hard_stops(self):
        # classify_response still gates the fresh response; a non-valid status dies.
        self.assertIn('if status != "valid":', self.txt)
        self.assertIn('ws2_mark_status "$WS2_STAGEDIR" failed FAIL', self.txt)

    def test_classify_still_flags_a_real_identity_mismatch(self):
        # functional backstop: the classifier the loop relies on still catches a
        # foreign-cell response.
        def _req(seed):
            return {
                "request_id": "r-s%d" % seed, "pair_id": "p-s%d" % seed,
                "schedule_position": seed, "run_config_sha256": "c" * 64,
                "expected_action_image_digest": "img@sha256:" + "a" * 64,
                "workload": "native_ycsb_c_read_zipf", "strategy": "2d", "seed": seed,
                "first_operation_id": 0, "handle_mode": "warm", "repetition_id": 0,
                "schedule_seed": 20260804,
            }
        req, foreign = _req(1), _req(2)
        resp = {f: foreign[f] for f in GATE.IDENTITY_FIELDS}
        resp["measured_valid"] = True
        status, _ = GATE.classify_response(req, resp, "img@sha256:" + "a" * 64)
        self.assertEqual(status, "mismatch")


class TestResumeAfterTransientStopContinues(unittest.TestCase):
    """Case 7: after a transient stop, a re-run resumes safely from the same point."""

    def test_verify_complete_reports_only_the_unmeasured_positions(self):
        import json
        import tempfile
        image = "img@sha256:" + "a" * 64

        def _req(pos):
            return {
                "request_id": "r%d" % pos, "pair_id": "p%d" % ((pos + 1) // 2),
                "schedule_position": pos, "run_config_sha256": "c" * 64,
                "expected_action_image_digest": image,
                "workload": "native_ycsb_c_read_zipf", "strategy": "2d", "seed": pos,
                "first_operation_id": 0, "handle_mode": "warm", "repetition_id": 0,
                "schedule_seed": 20260804,
            }

        def _resp(req):
            r = {f: req[f] for f in GATE.IDENTITY_FIELDS}
            r["measured_valid"] = True
            r["process_uuid"] = "proc-1"
            return r

        with tempfile.TemporaryDirectory() as d:
            # positions 1-2 measured (a completed pair), 3-4 not yet (transient stop).
            for pos in range(1, 5):
                req = _req(pos)
                with open(os.path.join(d, "req_%06d.json" % pos), "w") as f:
                    json.dump(req, f)
                if pos <= 2:
                    with open(os.path.join(d, "resp_%06d.json" % pos), "w") as f:
                        json.dump(_resp(req), f)
            bad = GATE.verify_complete(d, image)
            # verify_complete reports the position token as it appears in the filename.
            self.assertEqual(sorted(p for p, _, _ in bad), ["000003", "000004"])
            self.assertTrue(all(status == "missing" for _, status, _ in bad))

    def test_transient_stderr_files_do_not_block_resume(self):
        # resume keys on resp_*.json only; leftover .transient.N.stderr artifacts are
        # provenance, never mistaken for a completed measurement.
        txt = _read(MATRIX)
        self.assertIn('resp="$RAW/resp_${pos}.json"', txt)
        self.assertIn('if [ -f "$resp" ]', txt)


if __name__ == "__main__":
    unittest.main()
