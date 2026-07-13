"""Tests for warm-process identity, artifact validation, and collector session
classification. Uses the committed example manifest resolved against the repo."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, os.path.join(HERE, "..", "client"))

import session as session_mod  # noqa: E402
import collect  # noqa: E402

EXAMPLE = os.path.join(REPO, "deployment/openwhisk/config/artifacts.example.json")


def make_session():
    return session_mod.Session(EXAMPLE, resolve_root=REPO)


@unittest.skipUnless(os.path.exists(EXAMPLE), "example manifest not generated")
class TestSessionIdentity(unittest.TestCase):
    def test_uuid_stable_within_process_object(self):
        s = make_session()
        self.assertEqual(s.process_uuid, s.identity_fields()["process_uuid"])

    def test_counter_increments(self):
        s = make_session()
        self.assertEqual([s.next_invocation() for _ in range(3)], [1, 2, 3])

    def test_new_session_new_uuid(self):
        self.assertNotEqual(make_session().process_uuid,
                            make_session().process_uuid)

    def test_validate_artifacts_ok(self):
        s = make_session()
        self.assertEqual(s.validate_artifacts(s.artifact_manifest_sha256), ())

    def test_manifest_hash_mismatch_detected(self):
        s = make_session()
        r = s.validate_artifacts("deadbeef")
        self.assertIn("artifact_manifest_hash mismatch", r)

    def test_tampered_db_hash_fails(self):
        # Point a session at a manifest whose db sha256 is wrong.
        with open(EXAMPLE) as ef:
            m = json.load(ef)
        m["database"]["sha256"] = "0" * 64
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(m, tmp)
        tmp.close()
        try:
            s = session_mod.Session(tmp.name, resolve_root=REPO)
            self.assertIn("db sha256 mismatch", s.validate_artifacts())
        finally:
            os.remove(tmp.name)


class TestCollectorClassification(unittest.TestCase):
    def _resp(self, **kw):
        base = dict(process_uuid="u1", pid=100, db_inode=5,
                    invocation_counter=1, cold_threshold_passed=True,
                    query_hit=1, error=None, sqlite_error=None)
        base.update(kw)
        return base

    def test_valid_invocation_retained(self):
        ok, reason = collect.classify(self._resp(), {})
        self.assertTrue(ok, reason)

    def test_cold_gate_excludes(self):
        ok, reason = collect.classify(self._resp(cold_threshold_passed=False), {})
        self.assertFalse(ok)
        self.assertEqual(reason, "cold_threshold_not_passed")

    def test_action_error_excludes(self):
        ok, reason = collect.classify(self._resp(error="boom"), {})
        self.assertFalse(ok)

    def test_query_miss_excludes(self):
        ok, reason = collect.classify(self._resp(query_hit=0), {})
        self.assertFalse(ok)

    def test_non_monotonic_counter_excludes(self):
        prev = {}
        r1 = self._resp(invocation_counter=5)
        collect.classify(r1, prev)
        prev[collect.warm_session_id(r1)] = 5
        ok, reason = collect.classify(self._resp(invocation_counter=5), prev)
        self.assertFalse(ok)
        self.assertEqual(reason, "non_monotonic_invocation_counter")

    def test_session_id_separates_processes(self):
        a = collect.warm_session_id(self._resp(process_uuid="A", pid=1, db_inode=9))
        b = collect.warm_session_id(self._resp(process_uuid="B", pid=1, db_inode=9))
        self.assertNotEqual(a, b)


class TestCollectorDryRun(unittest.TestCase):
    def test_collect_writes_schema_to_tempdir_only(self):
        # Fake invoke_fn returns handler-shaped responses; NO OpenWhisk, NO
        # network, and output goes only under a temp dir (never results/).
        def fake_invoke(req):
            return dict(process_uuid="P", pid=7, db_inode=3,
                        invocation_counter=req["_ctr"],
                        cold_threshold_passed=True, query_hit=1,
                        error=None, sqlite_error=None,
                        strategy=req["strategy"], workload="A", seed=1,
                        first_operation_id=0, first_query_us=100.0 + req["_ctr"])
        reqs = [dict(request_id="r%d" % i, strategy=s, _ctr=i + 1)
                for i, s in enumerate(["baseline", "2d"])]
        tmp = tempfile.mkdtemp()
        try:
            out = collect.collect("dryrun", reqs, fake_invoke, tmp)
            self.assertEqual(out["n_total"], 2)
            self.assertEqual(out["n_valid"], 2)
            for name in ("raw_invocations.jsonl", "activation_records.jsonl",
                         "summary.csv", "README.md"):
                self.assertTrue(os.path.exists(os.path.join(out["run_dir"], name)))
            # never wrote into a canonical results directory
            self.assertNotIn(os.path.join("results", "openwhisk"), out["run_dir"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestEnvironmentRedaction(unittest.TestCase):
    def test_capture_script_redacts_secrets(self):
        script = os.path.join(REPO, "deployment/openwhisk/client/capture_environment.sh")
        if not (os.path.exists(script) and shutil.which("bash")):
            self.skipTest("bash or script unavailable")
        env = dict(os.environ, OW_AUTH_TOKEN="supersecret123",
                   OW_API_KEY="key-abc", WHISK_SECRET="nope")
        out = subprocess.run(["bash", script], capture_output=True, text=True,
                             env=env, cwd=REPO, timeout=60).stdout
        self.assertNotIn("supersecret123", out)
        self.assertNotIn("key-abc", out)
        self.assertNotIn("nope", out)


if __name__ == "__main__":
    unittest.main()
