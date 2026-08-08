"""Runtime fixes for the OpenWhisk lifecycle (WS2-observed bugs):

  * Artifacts resolve from the FIXED image root, never __file__/cwd -- OpenWhisk
    extracts the action archive under a per-activation path (/action/<N>/), so
    __file__-derived paths point at the extracted code, not the baked artifacts.
  * The deployment-bound immutable image identity arrives as an action INPUT
    PARAMETER (OW_ACTION_IMAGE_DIGEST), not an env var, and main() binds it to the
    session before measured validation.

These run against the canonical DB + example manifest; they skip cleanly if absent
(the params-binding proof needs the bridge-backed pipeline like test_contract).
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

import main  # noqa: E402
import session as session_mod  # noqa: E402

EXAMPLE = _fixture.EXAMPLE_MANIFEST


class TestArtifactResolutionIgnoresExtractedCodePath(unittest.TestCase):
    """The extracted-code path (/action/1 style, == __file__/cwd) must not be able
    to redirect where the action looks for the baked artifacts."""

    def test_defaults_are_image_absolute_regardless_of_cwd(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OW_ARTIFACT_ROOT", None)
            os.environ.pop("OW_ARTIFACT_MANIFEST", None)
            prev = os.getcwd()
            tmp = tempfile.mkdtemp(prefix="ow_extracted_code_")
            try:
                os.chdir(tmp)  # stand in for the /action/<N>/ extraction dir
                self.assertEqual(main.artifact_root(), "/action/artifacts")
                self.assertEqual(
                    main.artifact_manifest_path(),
                    "/action/artifacts/deployment/openwhisk/config/artifacts.json")
                # cwd (the extraction path) must not leak into resolution.
                self.assertNotIn(tmp, main.artifact_root())
                self.assertNotIn(tmp, main.artifact_manifest_path())
            finally:
                os.chdir(prev)
                os.rmdir(tmp)

    def test_paths_are_absolute_and_not_derived_from_file(self):
        # The resolver must never fall back to a __file__-relative location.
        here = os.path.dirname(main.__file__)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OW_ARTIFACT_ROOT", None)
            os.environ.pop("OW_ARTIFACT_MANIFEST", None)
            self.assertTrue(os.path.isabs(main.artifact_manifest_path()))
            self.assertNotIn(here, main.artifact_manifest_path())

    def test_env_override_is_honoured(self):
        with mock.patch.dict(os.environ, {"OW_ARTIFACT_ROOT": "/somewhere/else",
                                          "OW_ARTIFACT_MANIFEST": "/m/x.json"}):
            self.assertEqual(main.artifact_root(), "/somewhere/else")
            self.assertEqual(main.artifact_manifest_path(), "/m/x.json")


@unittest.skipUnless(_fixture.have_canonical(), "canonical DB / example manifest absent")
class TestDeploymentImageDigestFromParams(unittest.TestCase):
    """OW_ACTION_IMAGE_DIGEST supplied as an action PARAMETER is bound to the
    session and used for measured identity validation."""

    A_DIGEST = "sha256:" + "a" * 64
    B_DIGEST = "sha256:" + "b" * 64

    def setUp(self):
        self.s = session_mod.Session(EXAMPLE, resolve_root=_fixture.REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.s.open_warm_handle()
        # Clear whatever the env-default captured so the proof is purely param-driven.
        self.s.deployment_image_digest = None
        self.h = self.s.artifact_manifest_sha256
        self.addCleanup(self.s.close_warm_handle)

    def _params(self, expected_digest, **kw):
        p = dict(request_id="rt-1", workload="A", strategy="2d", seed=1,
                 first_operation_id=0, diagnostic_mode=False, cold_reset=True,
                 expected_artifact_manifest_hash=self.h, pair_id="pair-1",
                 repetition_id=0, schedule_position=1, schedule_seed=0,
                 run_config_sha256="c" * 64,
                 expected_action_image_digest=expected_digest, handle_mode="warm")
        p.update(kw)
        return p

    def test_param_digest_is_bound_and_mismatch_is_rejected(self):
        # deploy binds A via -p; the request expects B -> identity mismatch, and
        # the session must show A was bound from the param (not from env).
        params = self._params(self.B_DIGEST, OW_ACTION_IMAGE_DIGEST=self.A_DIGEST)
        with mock.patch.object(main, "get_session", return_value=self.s):
            r = main.main(params)
        self.assertEqual(self.s.deployment_image_digest, self.A_DIGEST,
                         "param OW_ACTION_IMAGE_DIGEST was not bound to the session")
        self.assertEqual(r["error_stage"], "request")
        self.assertIn("image digest", r["error"])

    def test_param_digest_match_validates(self):
        # deploy binds A and the request expects A -> identity passes and the
        # measured run completes valid (proves the bound param is what's checked).
        params = self._params(self.A_DIGEST, OW_ACTION_IMAGE_DIGEST=self.A_DIGEST)
        with mock.patch.object(main, "get_session", return_value=self.s):
            r = main.main(params)
        self.assertEqual(self.s.deployment_image_digest, self.A_DIGEST)
        self.assertNotIn("error", r)
        self.assertIsNone(r.get("error_stage"))
        self.assertTrue(r["measured_valid"])


if __name__ == "__main__":
    unittest.main()
