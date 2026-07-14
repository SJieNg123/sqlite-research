"""Fail-closed artifact validation (incl. trace-hash), and hardened collector
retention (identity match, diagnostic/measured gates, activation failure, invoke
exceptions, duplicate request ids)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, os.path.join(HERE, "..", "client"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402
import session as session_mod  # noqa: E402
import collect  # noqa: E402

EXAMPLE = _fixture.EXAMPLE_MANIFEST
REPO = _fixture.REPO
RUN_CONFIG = {"artifact_manifest_sha256": None, "action_image_digest": "sha256:img",
              "run_config_sha256": "r" * 64}


def tampered_session(mutate):
    with open(EXAMPLE) as f:
        m = json.load(f)
    mutate(m)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(m, tmp)
    tmp.close()
    return session_mod.Session(tmp.name, resolve_root=REPO), tmp.name


@unittest.skipUnless(_fixture.have_canonical(), "canonical artifacts absent")
class TestFailClosedValidation(unittest.TestCase):
    def test_valid_passes(self):
        s = session_mod.Session(EXAMPLE, resolve_root=REPO)
        self.assertEqual(s.validate_artifacts(s.artifact_manifest_sha256), ())
        self.assertTrue(s.validated)

    def test_trace_hash_mismatch_fails(self):
        s, p = tampered_session(
            lambda m: m["workload_traces"]["A"]["seeds"]["1"].__setitem__("sha256", "0" * 64))
        try:
            reasons = s.validate_artifacts()
            self.assertTrue(any("trace sha256 mismatch" in r for r in reasons))
            self.assertFalse(s.validated)
        finally:
            os.remove(p)

    def test_db_sha_mismatch_fails(self):
        s, p = tampered_session(lambda m: m["database"].__setitem__("sha256", "0" * 64))
        try:
            self.assertIn("db sha256 mismatch", s.validate_artifacts())
        finally:
            os.remove(p)

    def test_empty_hash_fails(self):
        s = session_mod.Session(EXAMPLE, resolve_root=REPO)
        self.assertIn("empty expected_artifact_manifest_hash", s.validate_artifacts(""))

    def test_versions_present(self):
        s = session_mod.Session(EXAMPLE, resolve_root=REPO)
        f = s.identity_fields()
        self.assertIsNotNone(f["python_version"])
        self.assertIn("canonical_query", f)


class TestCollectorRetention(unittest.TestCase):
    def _pair(self, **kw):
        req = dict(request_id="r1", workload="A", strategy="2d", seed=1,
                   first_operation_id=0, handle_mode="warm", pair_id="p1")
        resp = dict(req, process_uuid="u", pid=1, db_device=1, db_inode=2,
                    invocation_counter=1, diagnostic_mode=False,
                    cold_reset_requested=True, cold_threshold_passed=True,
                    oracle_passed=True, delivery_valid=True, measured_valid=True,
                    error=None, error_stage=None, sqlite_error=None,
                    artifact_manifest_sha256="m" * 64, action_image_digest="sha256:img",
                    run_config_sha256="r" * 64)
        rc = dict(RUN_CONFIG, artifact_manifest_sha256="m" * 64)
        resp.update(kw.get("resp", {}))
        req.update(kw.get("req", {}))
        return req, resp, rc

    def test_valid_retained(self):
        req, resp, rc = self._pair()
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertTrue(ok, reason)

    def test_diagnostic_never_valid(self):
        req, resp, rc = self._pair(resp={"diagnostic_mode": True})
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertEqual(reason, "diagnostic_row")

    def test_measured_valid_false_excluded(self):
        req, resp, rc = self._pair(resp={"measured_valid": False})
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertEqual(reason, "measured_valid_false")

    def test_identity_mismatch_excluded(self):
        req, resp, rc = self._pair()
        resp["strategy"] = "baseline"   # response disagrees with request
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertTrue(reason.startswith("identity_mismatch"))

    def test_manifest_hash_ne_run_config(self):
        req, resp, rc = self._pair()
        rc["artifact_manifest_sha256"] = "z" * 64
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertEqual(reason, "manifest_hash_ne_run_config")

    def test_image_digest_ne_run_config(self):
        req, resp, rc = self._pair()
        rc["action_image_digest"] = "sha256:other"
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertEqual(reason, "image_digest_ne_run_config")

    def test_missing_counter_excluded(self):
        req, resp, rc = self._pair(resp={"invocation_counter": None})
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertEqual(reason, "bad_invocation_counter")

    def test_non_integer_counter_excluded(self):
        req, resp, rc = self._pair(resp={"invocation_counter": "5"})
        ok, reason = collect.classify(req, resp, {}, rc)
        self.assertEqual(reason, "bad_invocation_counter")

    def test_activation_failure_excluded(self):
        req, resp, rc = self._pair()
        ok, reason = collect.classify(req, resp, {}, rc,
                                      activation={"response": {"success": False}})
        self.assertEqual(reason, "activation_failed")

    def test_response_not_dict(self):
        ok, reason = collect.classify({"request_id": "x"}, None, {}, RUN_CONFIG)
        self.assertEqual(reason, "response_not_dict")


class TestCollectorRun(unittest.TestCase):
    def test_invoke_exception_recorded_not_aborting(self):
        calls = []

        def flaky(req):
            calls.append(req["request_id"])
            if req["request_id"] == "b":
                raise RuntimeError("boom")
            return dict(req, process_uuid="P", pid=1, db_device=1, db_inode=2,
                        invocation_counter=len(calls), diagnostic_mode=False,
                        cold_reset_requested=True, cold_threshold_passed=True,
                        oracle_passed=True, delivery_valid=True, measured_valid=True,
                        error=None, error_stage=None, sqlite_error=None,
                        artifact_manifest_sha256="m" * 64,
                        action_image_digest="sha256:img", run_config_sha256="r" * 64)
        reqs = [dict(request_id=x, workload="A", strategy="2d", seed=1,
                     first_operation_id=0, handle_mode="warm", pair_id="p")
                for x in ("a", "b", "c")]
        tmp = tempfile.mkdtemp()
        try:
            rc = dict(RUN_CONFIG, artifact_manifest_sha256="m" * 64)
            out = collect.collect("r", reqs, flaky, tmp, run_config=rc)
            self.assertEqual(len(calls), 3)          # run continued past the boom
            self.assertEqual(out["n_total"], 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_duplicate_request_id_rejected(self):
        def ok(req):
            return dict(req, process_uuid="P", pid=1, db_device=1, db_inode=2,
                        invocation_counter=1, diagnostic_mode=False,
                        cold_reset_requested=True, cold_threshold_passed=True,
                        oracle_passed=True, delivery_valid=True, measured_valid=True,
                        error=None, error_stage=None, sqlite_error=None,
                        artifact_manifest_sha256="m" * 64,
                        action_image_digest="sha256:img", run_config_sha256="r" * 64)
        reqs = [dict(request_id="dup", workload="A", strategy="2d", seed=1,
                     first_operation_id=0, handle_mode="warm", pair_id="p")] * 2
        tmp = tempfile.mkdtemp()
        try:
            rc = dict(RUN_CONFIG, artifact_manifest_sha256="m" * 64)
            out = collect.collect("r", reqs, ok, tmp, run_config=rc)
            import csv
            with open(os.path.join(out["run_dir"], "summary.csv")) as f:
                reasons = [r["exclusion_reason"] for r in csv.DictReader(f)]
            self.assertIn("duplicate_request_id", reasons)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEnvironmentRedaction(unittest.TestCase):
    def test_capture_script_redacts_secrets(self):
        script = os.path.join(REPO, "deployment/openwhisk/client/capture_environment.sh")
        if not (os.path.exists(script) and shutil.which("bash")):
            self.skipTest("bash or script unavailable")
        import subprocess
        env = dict(os.environ, OW_AUTH_TOKEN="supersecret123", OW_API_KEY="key-abc")
        out = subprocess.run(["bash", script], capture_output=True, text=True,
                             env=env, cwd=REPO, timeout=60).stdout
        for leak in ("supersecret123", "key-abc"):
            self.assertNotIn(leak, out)


if __name__ == "__main__":
    unittest.main()
