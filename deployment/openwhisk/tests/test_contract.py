"""Request/response contract, gate, and correctness-oracle tests. Exercises the
hardened handler end-to-end against the real reference DB via a locally
constructed warm session (no OpenWhisk, no benchmark sweep)."""
import os
import sys
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "action"))

import main  # noqa: E402
import residency  # noqa: E402
import session as session_mod  # noqa: E402

EXAMPLE = os.path.join(REPO, "deployment/openwhisk/config/artifacts.example.json")
DB = os.path.join(REPO, "pipeline/preparation/layout_rewriter/runs/test.db")

RESPONSE_CONTRACT = [
    "process_uuid", "pid", "process_init_monotonic_ns", "invocation_counter",
    "db_device", "db_inode", "db_sha256", "artifact_manifest_sha256",
    "action_image_digest", "workload", "strategy", "seed", "first_operation_id",
    "handle_mode", "trace_sha256", "plan_sha256",
    "cold_reset_requested", "cold_reset_method", "cold_reset_succeeded",
    "relevant_pages_total", "resident_pages_before_reset",
    "resident_pages_after_reset", "resident_interiors_before_reset",
    "resident_interiors_after_reset", "resident_interiors_after_prefetch",
    "cold_threshold_passed", "attempted_methods", "selected_page_count",
    "selected_interior_count", "selected_leaf_count", "delivered_page_count",
    "reset_us", "open_us", "select_us", "deliver_us", "first_query_us",
    "handler_total_us", "query_hit", "result_digest", "oracle_expected_hit",
    "oracle_expected_digest", "oracle_passed", "measured_valid", "sqlite_error",
    "error", "error_stage",
]


def req(strategy, h, **kw):
    base = dict(request_id="t-" + strategy, workload="A", strategy=strategy,
                seed=1, first_operation_id=0, diagnostic_mode=True,
                cold_reset=True, expected_artifact_manifest_hash=h)
    base.update(kw)
    return base


@unittest.skipUnless(os.path.exists(EXAMPLE) and os.path.exists(DB),
                     "example manifest / reference DB not available")
class TestContract(unittest.TestCase):
    def setUp(self):
        self.session = session_mod.Session(EXAMPLE, resolve_root=REPO)
        self.session.validate_artifacts()
        self.assertTrue(self.session.validated, self.session.validation_reasons)
        self.session.open_warm_handle()
        self.h = self.session.artifact_manifest_sha256

    def tearDown(self):
        self.session.close_warm_handle()

    # ---- request schema ----
    def test_missing_fields_rejected(self):
        self.assertTrue(main.validate_request_schema({"request_id": "x"}))

    def test_bad_first_op_rejected(self):
        r = req("baseline", self.h)
        r["first_operation_id"] = -1
        self.assertTrue(main.validate_request_schema(r))

    def test_unsupported_strategy_rejected(self):
        self.assertTrue(main.validate_request_schema(req("2f_slru", self.h)))

    def test_bad_handle_mode_rejected(self):
        self.assertTrue(main.validate_request_schema(req("2d", self.h, handle_mode="x")))

    def test_valid_request_accepted(self):
        self.assertEqual(main.validate_request_schema(req("2d", self.h)), ())

    # ---- response completeness (diagnostic mode reaches every stage) ----
    def test_response_has_all_contract_fields(self):
        resp = main.handle(req("2d", self.h), self.session)
        missing = [f for f in RESPONSE_CONTRACT if f not in resp]
        self.assertEqual(missing, [], "missing: %s" % missing)

    # ---- strategy invariants ----
    def test_baseline_selects_and_delivers_zero(self):
        resp = main.handle(req("baseline", self.h), self.session)
        self.assertEqual(resp["selected_page_count"], 0)
        self.assertEqual(resp["delivered_page_count"], 0)
        self.assertEqual(resp["selected_interior_count"], 0)

    def test_2d_selects_92_all_interior_no_leaf(self):
        resp = main.handle(req("2d", self.h), self.session)
        self.assertEqual(resp["selected_page_count"], 92)
        self.assertEqual(resp["selected_interior_count"], 92)
        self.assertEqual(resp["selected_leaf_count"], 0)
        self.assertEqual(resp["delivered_page_count"], 92)

    # ---- correctness oracle ----
    def test_oracle_passes_on_correct_result(self):
        resp = main.handle(req("2d", self.h), self.session)
        self.assertTrue(resp["oracle_passed"])
        self.assertEqual(resp["query_hit"], resp["oracle_expected_hit"])
        self.assertEqual(resp["result_digest"], resp["oracle_expected_digest"])

    def test_wrong_expected_digest_fails_oracle(self):
        # tamper the frozen oracle digest -> observed result won't match
        self.session.manifest["first_query_oracle"]["A"]["1"]["0"]["expected_digest"] = "0" * 64
        resp = main.handle(req("2d", self.h, diagnostic_mode=False), self.session)
        self.assertFalse(resp["oracle_passed"])
        self.assertFalse(resp["measured_valid"])

    # ---- identity gates ----
    def test_manifest_hash_mismatch_refused(self):
        resp = main.handle(req("2d", "b" * 64, diagnostic_mode=False), self.session)
        self.assertEqual(resp["error_stage"], "identity")
        self.assertFalse(resp["measured_valid"])

    def test_empty_hash_refused(self):
        r = req("2d", "", diagnostic_mode=False)
        # schema catches empty/!64hex first
        self.assertTrue(main.validate_request_schema(r) or
                        main.handle(r, self.session)["error"])

    def test_db_inode_change_refused(self):
        saved = self.session.db_inode
        self.session.db_inode = saved + 1
        try:
            resp = main.handle(req("2d", self.h), self.session)
            self.assertEqual(resp["error_stage"], "identity")
        finally:
            self.session.db_inode = saved

    # ---- cold_reset gate ----
    def test_cold_reset_false_cannot_be_measured(self):
        resp = main.handle(req("2d", self.h, cold_reset=False, diagnostic_mode=False),
                           self.session)
        self.assertEqual(resp["error_stage"], "cold_reset_required")
        self.assertFalse(resp["measured_valid"])

    def test_cold_gate_failure_runs_no_select_deliver_query(self):
        fail = {"resident_pages_before_reset": 100,
                "resident_interiors_before_reset": 92, "attempted_methods": [],
                "cold_reset_method": "MADV_DONTNEED",
                "resident_pages_after_reset": 100,
                "resident_interiors_after_reset": 92,
                "cold_reset_succeeded": False, "cold_threshold_passed": False}
        with mock.patch.object(residency, "cold_reset_and_verify", return_value=fail):
            resp = main.handle(req("2d", self.h, diagnostic_mode=False), self.session)
        self.assertEqual(resp["error_stage"], "cold_gate")
        self.assertFalse(resp["measured_valid"])
        for f in ("selected_page_count", "delivered_page_count", "first_query_us"):
            self.assertNotIn(f, resp)

    def test_reset_chain_continues_after_ineffective_success(self):
        # on this host MADV_DONTNEED returns rc=0 but leaves pages resident;
        # the chain must move on to a further candidate.
        resp = main.handle(req("2d", self.h), self.session)
        methods = resp["attempted_methods"]
        self.assertGreaterEqual(len(methods), 1)
        first = methods[0]
        if first["resident_interiors_after"] > 0:
            self.assertEqual(first["rc"], 0)          # advice "succeeded"
            self.assertGreaterEqual(len(methods), 2)  # yet the chain continued

    # ---- warm vs standalone ----
    def test_warm_mode_pays_no_open_cost(self):
        resp = main.handle(req("2d", self.h, handle_mode="warm"), self.session)
        self.assertEqual(resp["open_us"], 0.0)

    def test_standalone_mode_pays_open_cost(self):
        resp = main.handle(req("2d", self.h, handle_mode="standalone"), self.session)
        self.assertGreater(resp["open_us"], 0.0)

    # ---- semantic errors ----
    def test_unknown_workload_structured_error(self):
        resp = main.handle(req("2d", self.h, workload="Z"), self.session)
        self.assertEqual(resp["error_stage"], "request")
        self.assertFalse(resp["measured_valid"])

    def test_unknown_seed_structured_error(self):
        resp = main.handle(req("2d", self.h, seed=99), self.session)
        self.assertEqual(resp["error_stage"], "request")

    # ---- concurrency ----
    def test_overlapping_invocation_rejected(self):
        self.session.critical_lock.acquire()
        try:
            resp = main.handle(req("2d", self.h), self.session)
            self.assertEqual(resp["error_stage"], "concurrency")
            self.assertFalse(resp["measured_valid"])
        finally:
            self.session.critical_lock.release()

    # ---- counter monotonic ----
    def test_counter_monotonic(self):
        a = main.handle(req("baseline", self.h), self.session)
        b = main.handle(req("2d", self.h), self.session)
        self.assertLess(a["invocation_counter"], b["invocation_counter"])


class TestArtifactValidationFailClosed(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(EXAMPLE), "example manifest missing")
    def test_unvalidated_session_refuses_handler(self):
        s = session_mod.Session(EXAMPLE, resolve_root=REPO)
        # never called validate_artifacts -> validated is False
        resp = main.handle(req("2d", s.artifact_manifest_sha256, diagnostic_mode=False), s)
        self.assertEqual(resp["error_stage"], "artifact_validation")
        self.assertFalse(resp["measured_valid"])


if __name__ == "__main__":
    unittest.main()
