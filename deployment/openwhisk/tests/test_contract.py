"""Request/response contract tests. Exercises the action handler end-to-end
against the real reference DB via a locally-constructed warm session (no
OpenWhisk, no benchmark sweep)."""
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "action"))

import main  # noqa: E402
import session as session_mod  # noqa: E402

EXAMPLE = os.path.join(REPO, "deployment/openwhisk/config/artifacts.example.json")
DB = os.path.join(REPO, "pipeline/preparation/layout_rewriter/runs/test.db")

RESPONSE_CONTRACT = [
    # identity
    "process_uuid", "pid", "process_init_monotonic_ns", "invocation_counter",
    "db_device", "db_inode", "db_sha256", "artifact_manifest_sha256",
    # input identity
    "workload", "strategy", "seed", "first_operation_id", "trace_sha256",
    "plan_sha256",
    # cold diagnostics
    "cold_reset_requested", "cold_reset_method", "cold_reset_succeeded",
    "relevant_pages_total", "resident_pages_before_reset",
    "resident_pages_after_reset", "resident_interiors_before_reset",
    "resident_interiors_after_reset", "resident_interiors_after_prefetch",
    "cold_threshold_passed",
    # strategy diagnostics
    "selected_page_count", "selected_interior_count", "selected_leaf_count",
    "delivered_page_count",
    # timings
    "reset_us", "open_us", "select_us", "deliver_us", "first_query_us",
    "handler_total_us",
    # correctness
    "query_hit", "result_digest", "sqlite_error", "error",
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
    @classmethod
    def setUpClass(cls):
        cls.session = session_mod.Session(EXAMPLE, resolve_root=REPO)
        cls.session.validate_artifacts()
        cls.h = cls.session.artifact_manifest_sha256

    # ---- request validation ----
    def test_missing_fields_rejected(self):
        self.assertTrue(main.validate_request({"request_id": "x"}))

    def test_bad_first_op_rejected(self):
        r = req("baseline", self.h)
        r["first_operation_id"] = -1
        self.assertTrue(main.validate_request(r))

    def test_unsupported_strategy_rejected(self):
        r = req("2f_slru", self.h)
        self.assertTrue(main.validate_request(r))

    def test_valid_request_accepted(self):
        self.assertEqual(main.validate_request(req("2d", self.h)), ())

    # ---- response completeness ----
    def test_response_has_all_contract_fields(self):
        resp = main.handle(req("2d", self.h), self.session)
        missing = [f for f in RESPONSE_CONTRACT if f not in resp]
        self.assertEqual(missing, [], "missing response fields: %s" % missing)

    # ---- baseline vs 2d selection ----
    def test_baseline_selects_and_delivers_zero(self):
        resp = main.handle(req("baseline", self.h), self.session)
        self.assertEqual(resp["selected_page_count"], 0)
        self.assertEqual(resp["delivered_page_count"], 0)
        self.assertIsNone(resp["error"])

    def test_2d_selects_expected_interiors(self):
        expected = self.session.manifest["interior_page_list"]["count"]
        resp = main.handle(req("2d", self.h), self.session)
        self.assertEqual(resp["selected_interior_count"], expected)
        self.assertEqual(resp["selected_page_count"], expected)

    def test_identical_query_digest_across_strategies(self):
        a = main.handle(req("baseline", self.h), self.session)
        b = main.handle(req("2d", self.h), self.session)
        self.assertEqual(a["result_digest"], b["result_digest"])
        self.assertEqual(a["query_hit"], 1)

    def test_counter_monotonic_across_invocations(self):
        a = main.handle(req("baseline", self.h), self.session)
        b = main.handle(req("2d", self.h), self.session)
        self.assertLess(a["invocation_counter"], b["invocation_counter"])

    # ---- identity gates ----
    def test_manifest_hash_mismatch_refused(self):
        resp = main.handle(req("2d", "deadbeef", diagnostic_mode=False), self.session)
        self.assertEqual(resp["error"], "expected_artifact_manifest_hash mismatch")

    def test_db_inode_change_refused(self):
        saved = self.session.db_inode
        self.session.db_inode = saved + 1  # simulate image swap / remount
        try:
            resp = main.handle(req("2d", self.h), self.session)
            self.assertEqual(resp["error"], "db device/inode changed since process init")
        finally:
            self.session.db_inode = saved

    def test_cold_gate_reflected_in_measured_valid(self):
        # non-diagnostic: measured_valid must be a strict AND of the cold gate,
        # query hit, and no error (host may or may not achieve cold state).
        resp = main.handle(req("2d", self.h, diagnostic_mode=False), self.session)
        expected = bool(resp["cold_threshold_passed"] and resp["query_hit"] == 1
                        and resp["sqlite_error"] is None)
        self.assertEqual(resp["measured_valid"], expected)


if __name__ == "__main__":
    unittest.main()
