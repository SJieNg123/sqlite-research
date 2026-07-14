"""Request/response contract, gate, correctness-oracle, and delivery-validity
tests for the hardened action. Runs against the canonical DB + example manifest;
skips cleanly if they are absent."""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

# the action captures the observed image digest at Session init from the env
IMAGE = "sha256:" + "a" * 64
os.environ["OW_ACTION_IMAGE_DIGEST"] = IMAGE

import main  # noqa: E402
import residency  # noqa: E402
import session as session_mod  # noqa: E402

EXAMPLE = _fixture.EXAMPLE_MANIFEST
DB = _fixture.CANONICAL_DB

RESPONSE_CONTRACT = [
    "process_uuid", "pid", "process_init_monotonic_ns", "invocation_counter",
    "db_device", "db_inode", "db_sha256", "artifact_manifest_sha256",
    "action_image_digest", "repository_commit", "sqlite_library_version",
    "python_version", "canonical_query", "workload", "strategy", "seed",
    "first_operation_id", "handle_mode", "pair_id", "repetition_id",
    "schedule_position", "schedule_seed", "run_config_sha256",
    "expected_action_image_digest", "trace_sha256", "plan_sha256",
    "cold_reset_requested", "cold_reset_method", "cold_threshold_passed",
    "attempted_methods", "selected_page_count", "selected_interior_count",
    "selected_leaf_count", "delivered_page_count", "delivery_valid",
    "reset_us", "open_us", "select_us", "deliver_us", "first_query_us",
    "handler_total_us", "query_hit", "result_digest", "oracle_expected_hit",
    "oracle_expected_digest", "oracle_passed", "sqlite_cache_miss",
    "measured_valid", "sqlite_error", "error", "error_stage",
]


def mreq(strategy, h, **kw):
    """A full measured request."""
    base = dict(request_id="t-" + strategy, workload="A", strategy=strategy,
                seed=1, first_operation_id=0, diagnostic_mode=False,
                cold_reset=True, expected_artifact_manifest_hash=h,
                pair_id="pair-1", repetition_id=0, schedule_position=1,
                schedule_seed=42, run_config_sha256="c" * 64,
                expected_action_image_digest=IMAGE, handle_mode="warm")
    base.update(kw)
    return base


@unittest.skipUnless(_fixture.have_canonical(), "canonical DB / example manifest absent")
class TestContract(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(EXAMPLE, resolve_root=_fixture.REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.s.open_warm_handle()
        self.h = self.s.artifact_manifest_sha256

    def tearDown(self):
        self.s.close_warm_handle()

    def test_response_has_all_contract_fields(self):
        r = main.handle(mreq("2d", self.h), self.s)
        missing = [f for f in RESPONSE_CONTRACT if f not in r]
        self.assertEqual(missing, [], "missing: %s" % missing)

    def test_measured_2d_valid(self):
        r = main.handle(mreq("2d", self.h), self.s)
        self.assertEqual(r.get("error_stage"), None, r.get("error"))
        self.assertTrue(r["cold_threshold_passed"])
        self.assertTrue(r["measured_valid"])

    def test_echo_pair_fields(self):
        r = main.handle(mreq("2d", self.h, pair_id="XYZ", repetition_id=3,
                             schedule_position=9), self.s)
        self.assertEqual((r["pair_id"], r["repetition_id"], r["schedule_position"]),
                         ("XYZ", 3, 9))

    # ---- strategy delivery invariants ----
    def test_baseline_invariants(self):
        r = main.handle(mreq("baseline", self.h), self.s)
        self.assertEqual((r["selected_page_count"], r["delivered_page_count"]), (0, 0))
        self.assertTrue(r["delivery_valid"])

    def test_2d_invariants(self):
        r = main.handle(mreq("2d", self.h), self.s)
        self.assertEqual(r["selected_interior_count"], 92)
        self.assertEqual(r["selected_leaf_count"], 0)
        self.assertEqual(r["delivered_page_count"], 92)
        self.assertTrue(r["delivery_valid"])

    def test_incomplete_2d_delivery_not_measured_valid(self):
        with mock.patch.object(residency.PageMap, "deliver_willneed", return_value=90):
            r = main.handle(mreq("2d", self.h), self.s)
        self.assertFalse(r["delivery_valid"])
        self.assertFalse(r["measured_valid"])

    # ---- correctness oracle (payload) ----
    def test_oracle_payload_passes(self):
        r = main.handle(mreq("2d", self.h), self.s)
        self.assertTrue(r["oracle_passed"])
        self.assertEqual(r["result_digest"], r["oracle_expected_digest"])

    def test_wrong_expected_digest_fails(self):
        self.s.manifest["first_query_oracle"]["A"]["1"]["0"]["expected_digest"] = "0" * 64
        r = main.handle(mreq("2d", self.h), self.s)
        self.assertFalse(r["oracle_passed"])
        self.assertFalse(r["measured_valid"])

    # ---- identity gates ----
    def test_image_digest_required_and_matched(self):
        r = main.handle(mreq("2d", self.h, expected_action_image_digest="sha256:" + "b" * 64), self.s)
        self.assertEqual(r["error_stage"], "request")

    def test_empty_image_digest_refused(self):
        r = main.handle(mreq("2d", self.h, expected_action_image_digest=""), self.s)
        self.assertEqual(r["error_stage"], "request")

    def test_manifest_hash_mismatch_refused(self):
        r = main.handle(mreq("2d", "b" * 64), self.s)
        self.assertEqual(r["error_stage"], "identity")

    def test_bad_run_config_sha_refused(self):
        r = main.handle(mreq("2d", self.h, run_config_sha256="nothex"), self.s)
        self.assertEqual(r["error_stage"], "request")

    def test_cold_reset_false_unmeasured(self):
        r = main.handle(mreq("2d", self.h, cold_reset=False), self.s)
        self.assertEqual(r["error_stage"], "cold_reset_required")

    def test_cold_gate_failure_runs_no_query(self):
        fail = {"resident_pages_before_reset": 1, "resident_interiors_before_reset": 92,
                "attempted_methods": [], "cold_reset_method": "MADV_DONTNEED",
                "resident_pages_after_reset": 1, "resident_interiors_after_reset": 92,
                "cold_reset_succeeded": False, "cold_threshold_passed": False}
        with mock.patch.object(residency, "cold_reset_and_verify", return_value=fail):
            r = main.handle(mreq("2d", self.h), self.s)
        self.assertEqual(r["error_stage"], "cold_gate")
        self.assertNotIn("first_query_us", r)

    def test_unvalidated_session_refused(self):
        s = session_mod.Session(EXAMPLE, resolve_root=_fixture.REPO)
        r = main.handle(mreq("2d", s.artifact_manifest_sha256), s)
        self.assertEqual(r["error_stage"], "artifact_validation")

    def test_overlap_rejected(self):
        self.s.critical_lock.acquire()
        try:
            r = main.handle(mreq("2d", self.h), self.s)
            self.assertEqual(r["error_stage"], "concurrency")
        finally:
            self.s.critical_lock.release()

    def test_diagnostic_relaxes_pair_requirements(self):
        # diagnostic mode does not require pair identity and is never measured
        r = main.handle(dict(request_id="d", workload="A", strategy="2d", seed=1,
                             first_operation_id=0, diagnostic_mode=True,
                             cold_reset=True, expected_artifact_manifest_hash=self.h,
                             handle_mode="warm"), self.s)
        self.assertIsNone(r["measured_valid"])

    # ---- canonical query recorded ----
    def test_canonical_query_is_payload_select(self):
        r = main.handle(mreq("2d", self.h), self.s)
        self.assertEqual(r["canonical_query"], "SELECT payload FROM items WHERE id=?1")


if __name__ == "__main__":
    unittest.main()
