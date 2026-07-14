"""Warm-process identity, fail-closed artifact validation, collector session
classification, and the atomic pairing-key definition."""
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
import summarize  # noqa: E402

EXAMPLE = os.path.join(REPO, "deployment/openwhisk/config/artifacts.example.json")


def make_session():
    return session_mod.Session(EXAMPLE, resolve_root=REPO)


def tampered_session(mutate):
    with open(EXAMPLE) as f:
        m = json.load(f)
    mutate(m)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(m, tmp)
    tmp.close()
    return session_mod.Session(tmp.name, resolve_root=REPO), tmp.name


@unittest.skipUnless(os.path.exists(EXAMPLE), "example manifest not generated")
class TestSessionIdentity(unittest.TestCase):
    def test_counter_increments(self):
        s = make_session()
        self.assertEqual([s.next_invocation() for _ in range(3)], [1, 2, 3])

    def test_new_session_new_uuid(self):
        self.assertNotEqual(make_session().process_uuid, make_session().process_uuid)

    def test_activation_id_not_used_as_identity(self):
        s = make_session()
        f = s.identity_fields()
        self.assertIn("process_uuid", f)
        self.assertNotIn("activation_id", f)


@unittest.skipUnless(os.path.exists(EXAMPLE), "example manifest not generated")
class TestFailClosedValidation(unittest.TestCase):
    def test_valid_manifest_passes(self):
        s = make_session()
        self.assertEqual(s.validate_artifacts(s.artifact_manifest_sha256), ())
        self.assertTrue(s.validated)

    def test_empty_expected_hash_fails(self):
        s = make_session()
        r = s.validate_artifacts("")
        self.assertIn("empty expected_artifact_manifest_hash", r)
        self.assertFalse(s.validated)

    def test_manifest_hash_mismatch_fails(self):
        s = make_session()
        self.assertIn("artifact_manifest_hash mismatch", s.validate_artifacts("d" * 64))

    def test_db_sha_mismatch_fails(self):
        s, p = tampered_session(lambda m: m["database"].__setitem__("sha256", "0" * 64))
        try:
            self.assertIn("db sha256 mismatch", s.validate_artifacts())
            self.assertFalse(s.validated)
        finally:
            os.remove(p)

    def test_device_mismatch_fails(self):
        s, p = tampered_session(lambda m: m["database"].__setitem__("device", 999999999))
        try:
            self.assertIn("db device != manifest", s.validate_artifacts())
        finally:
            os.remove(p)

    def test_inode_mismatch_fails(self):
        s, p = tampered_session(lambda m: m["database"].__setitem__("inode", 999999999))
        try:
            self.assertIn("db inode != manifest", s.validate_artifacts())
        finally:
            os.remove(p)

    def test_non_4096_manifest_page_size_fails(self):
        s, p = tampered_session(lambda m: m.__setitem__("os_page_size_expected", 8192))
        try:
            self.assertIn("manifest os_page_size_expected != 4096", s.validate_artifacts())
        finally:
            os.remove(p)

    def test_db_page_size_field_non_4096_fails(self):
        s, p = tampered_session(lambda m: m["database"].__setitem__("page_size", 8192))
        try:
            self.assertIn("db page_size != 4096", s.validate_artifacts())
        finally:
            os.remove(p)

    def test_relevant_denominator_is_page_count(self):
        s = make_session()
        self.assertEqual(s.manifest["expected_relevant_page_count"],
                         s.manifest["database"]["page_count"])
        self.assertNotEqual(s.manifest["expected_relevant_page_count"], 92)
        self.assertEqual(s.manifest["interior_page_count"], 92)


class TestCollectorClassification(unittest.TestCase):
    def _resp(self, **kw):
        base = dict(process_uuid="u1", pid=100, db_inode=5, invocation_counter=1,
                    cold_threshold_passed=True, oracle_passed=True,
                    error=None, sqlite_error=None)
        base.update(kw)
        return base

    def test_valid_retained(self):
        ok, reason = collect.classify(self._resp(), {})
        self.assertTrue(ok, reason)

    def test_cold_gate_excludes(self):
        ok, reason = collect.classify(self._resp(cold_threshold_passed=False), {})
        self.assertEqual(reason, "cold_threshold_not_passed")

    def test_oracle_fail_excludes_not_hardcoded_hit(self):
        # oracle_passed False (e.g. wrong digest) must exclude even if a naive
        # query_hit==1 would have retained it.
        ok, reason = collect.classify(self._resp(oracle_passed=False, query_hit=1), {})
        self.assertFalse(ok)
        self.assertEqual(reason, "oracle_failed")

    def test_non_monotonic_counter_excludes(self):
        prev = {}
        r1 = self._resp(invocation_counter=5)
        collect.classify(r1, prev)
        prev[collect.warm_session_id(r1)] = 5
        ok, reason = collect.classify(self._resp(invocation_counter=5), prev)
        self.assertEqual(reason, "non_monotonic_invocation_counter")

    def test_session_separates_processes(self):
        a = collect.warm_session_id(self._resp(process_uuid="A"))
        b = collect.warm_session_id(self._resp(process_uuid="B"))
        self.assertNotEqual(a, b)


class TestPairingKey(unittest.TestCase):
    def test_pair_key_excludes_strategy_requires_session(self):
        self.assertNotIn("strategy", summarize.PAIR_KEY)
        self.assertIn("warm_session_id", summarize.PAIR_KEY)

    def test_observation_key_includes_strategy(self):
        self.assertIn("strategy", summarize.OBSERVATION_KEY)

    def test_pairing_uses_same_session_baseline(self):
        rows = [
            dict(strategy="baseline", warm_session_id="S1", workload="A", seed="1",
                 first_operation_id="0", first_query_us="500", valid="True"),
            dict(strategy="2d", warm_session_id="S1", workload="A", seed="1",
                 first_operation_id="0", first_query_us="360", valid="True"),
            # a 2d in a DIFFERENT session must NOT pair with S1's baseline
            dict(strategy="2d", warm_session_id="S2", workload="A", seed="1",
                 first_operation_id="0", first_query_us="999", valid="True"),
        ]
        deltas = summarize.paired_deltas(rows)
        paired = {(d["warm_session_id"], round(d["paired_pct"])) for d in deltas}
        self.assertIn(("S1", -28), paired)          # 360 vs 500
        self.assertTrue(all(d["warm_session_id"] == "S1" for d in deltas))  # S2 unpaired


class TestCollectorDryRun(unittest.TestCase):
    def test_collect_writes_schema_to_tempdir_only(self):
        def fake_invoke(req):
            return dict(process_uuid="P", pid=7, db_inode=3,
                        invocation_counter=req["_ctr"], cold_threshold_passed=True,
                        oracle_passed=True, error=None, sqlite_error=None,
                        strategy=req["strategy"], workload="A", seed=1,
                        first_operation_id=0, first_query_us=100.0 + req["_ctr"])
        reqs = [dict(request_id="r%d" % i, strategy=s, _ctr=i + 1)
                for i, s in enumerate(["baseline", "2d"])]
        tmp = tempfile.mkdtemp()
        try:
            out = collect.collect("dryrun", reqs, fake_invoke, tmp)
            self.assertEqual((out["n_total"], out["n_valid"]), (2, 2))
            for name in ("raw_invocations.jsonl", "activation_records.jsonl",
                         "summary.csv", "README.md"):
                self.assertTrue(os.path.exists(os.path.join(out["run_dir"], name)))
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
        for leak in ("supersecret123", "key-abc", "nope"):
            self.assertNotIn(leak, out)


if __name__ == "__main__":
    unittest.main()
