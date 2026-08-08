"""Regression tests for the WS2 deploy/diagnostic lifecycle fixes (the bugs found
and hand-patched during the first real OpenWhisk diagnostic):

  * the action must ship its Python sources as a zip (image alone -> "Missing
    main"); the archive is flat: main.py -> __main__.py + the four sibling modules,
  * deploy metadata records the execution TAG, the immutable RepoDigest, and the
    local image id as THREE distinct, unambiguously-named fields,
  * a RepoDigest is never fabricated from the local image id,
  * the diagnostic request carries a deterministic schedule_seed, and
  * a pre-response invocation failure is reported as an invocation/runtime error,
    NOT as a cold-reset gate failure.

Zip contents are checked functionally (the shared builder); the metadata / wiring
guarantees are checked against the scripts on disk. No build/deploy/invoke.
"""
import importlib.util
import os
import tempfile
import unittest
import zipfile

import _fixture

REPO = _fixture.REPO
OW_DIR = os.path.join(REPO, "deployment", "openwhisk")
WS2 = os.path.join(OW_DIR, "ws2")
BUILD_SH = os.path.join(WS2, "01_build_image.sh")
DEPLOY_SH = os.path.join(WS2, "02_deploy.sh")
DIAG_SH = os.path.join(WS2, "03_diagnostic.sh")
ACTION_DIR = os.path.join(OW_DIR, "action")


def _load_make_action_zip():
    spec = importlib.util.spec_from_file_location(
        "make_action_zip", os.path.join(WS2, "make_action_zip.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(path):
    with open(path) as f:
        return f.read()


class TestActionZip(unittest.TestCase):
    def setUp(self):
        self.maz = _load_make_action_zip()

    def test_zip_has_exactly_the_required_members(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "action.zip")
            names = self.maz.build(ACTION_DIR, out)
            with zipfile.ZipFile(out) as z:
                members = sorted(z.namelist())
        expected = sorted(["__main__.py", "session.py", "residency.py",
                           "sqlite_bridge.py", "oracle.py"])
        self.assertEqual(members, expected)
        self.assertEqual(sorted(names), expected)
        # main.py is shipped AS __main__.py; it must NOT appear under its own name.
        self.assertNotIn("main.py", members)

    def test_entrypoint_is_main_py_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "action.zip")
            self.maz.build(ACTION_DIR, out)
            with zipfile.ZipFile(out) as z:
                shipped = z.read("__main__.py")
        with open(os.path.join(ACTION_DIR, "main.py"), "rb") as f:
            self.assertEqual(shipped, f.read())

    def test_zip_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.zip"), os.path.join(d, "b.zip")
            self.maz.build(ACTION_DIR, a)
            self.maz.build(ACTION_DIR, b)
            with open(a, "rb") as fa, open(b, "rb") as fb:
                self.assertEqual(fa.read(), fb.read(), "action zip is not reproducible")


class TestDeployScriptWiring(unittest.TestCase):
    def setUp(self):
        self.txt = _read(DEPLOY_SH)

    def test_ships_zip_with_main_main(self):
        # deploys the packaged code archive with the OpenWhisk --main entrypoint.
        self.assertIn("make_action_zip.py", self.txt)
        self.assertIn('"$ACTION_ZIP"', self.txt)
        self.assertIn("--main main", self.txt)

    def test_executes_by_registry_tag_not_digest(self):
        # execution ref is the registry TAG; the immutable digest is only bound.
        self.assertIn('--docker "$EXEC_REF"', self.txt)
        self.assertIn('-p OW_ACTION_IMAGE_DIGEST "$IMMUTABLE_DIGEST"', self.txt)

    def test_deploy_meta_distinguishes_tag_digest_and_image_id(self):
        # three distinct, unambiguously-named fields in deploy_meta.json.
        for field in ('"execution_image_ref"', '"immutable_image_digest"',
                      '"image_id"'):
            self.assertIn(field, self.txt, "deploy_meta missing %s" % field)
        # the old conflating field name must be gone.
        self.assertNotIn('"image_digest": "%s"', self.txt)

    def test_fails_closed_on_unpinned_digest(self):
        self.assertIn("UNPINNED:*", self.txt)
        self.assertRegex(self.txt, r"UNPINNED[^\n]*ws2_die|ws2_die[^\n]*UNPINNED")

    def test_immutable_digest_repository_must_match_execution_ref(self):
        # the bound digest must belong to the same repository as the exec tag.
        self.assertIn("image_identity.py", self.txt)
        self.assertIn("same-repo", self.txt)
        self.assertIn("different repositories", self.txt)


class TestBuildScriptIdentityDistinction(unittest.TestCase):
    def setUp(self):
        self.txt = _read(BUILD_SH)

    def test_build_meta_records_four_distinct_identities(self):
        for field in ('"image_id"', '"local_image_tag"', '"execution_image_ref"',
                      '"repo_digest"'):
            self.assertIn(field, self.txt, "build_meta missing %s" % field)

    def test_repo_digest_never_fabricated_from_image_id(self):
        # The only place IMAGE_ID may touch REPO_DIGEST is the clearly-marked
        # NON-measured UNPINNED sentinel -- never a bare digest assignment.
        self.assertNotIn('REPO_DIGEST="$IMAGE_ID"', self.txt)
        self.assertIn('REPO_DIGEST="UNPINNED:$IMAGE_ID"', self.txt)
        # RepoDigest resolution comes from a real registry inspect after push.
        self.assertIn("RepoDigests", self.txt)
        self.assertIn("docker push", self.txt)

    def test_selects_exact_repository_digest_not_first_entry(self):
        # binds the exact-repository digest via the shared helper; NEVER docker's
        # first RepoDigests entry (which may be a host-less alias).
        self.assertIn("image_identity.py", self.txt)
        self.assertIn("select-digest", self.txt)
        self.assertIn("json .RepoDigests", self.txt)
        self.assertNotIn("index .RepoDigests 0", self.txt)

    def test_base_runtime_validated_by_tested_predicate(self):
        # the pinned-base check goes through the tested helper, not a weak glob that
        # accepted a bare @sha256 (empty repository).
        self.assertIn("check-base", self.txt)
        self.assertNotIn("*@sha256:[0-9a-f]*", self.txt)


class TestDiagnosticScript(unittest.TestCase):
    def setUp(self):
        self.txt = _read(DIAG_SH)

    def test_request_has_deterministic_schedule_seed(self):
        self.assertIn('"schedule_seed": 0', self.txt)

    def test_reads_immutable_image_digest_field(self):
        self.assertIn('m.get("immutable_image_digest"', self.txt)

    def test_pre_response_failure_is_not_reported_as_cold_gate(self):
        # A missing/invalid response must be reported as an invocation/runtime
        # failure, explicitly disclaiming the cold-reset gate.
        self.assertIn("INVOKE_RC", self.txt)
        self.assertIn("invocation did not return an evaluable response", self.txt)
        # the message disclaims the cold-reset gate (phrase intact on one line).
        self.assertIn("cold-reset gate failure", self.txt)
        self.assertIn("cold-data gate was", self.txt)


if __name__ == "__main__":
    unittest.main()
