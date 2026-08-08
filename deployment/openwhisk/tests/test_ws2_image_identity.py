"""Functional tests for the WS2 registry image-identity helpers
(deployment/openwhisk/ws2/image_identity.py) -- the logic behind the identity
bugs found during the first real OpenWhisk deploy:

  * docker lists several RepoDigests (a registry-less `name@sha256:` alias AND the
    host-qualified `host:port/name@sha256:` we pushed); binding the FIRST entry
    dropped the registry host. Selection must return the EXACT-repository digest.
  * the bound immutable digest must belong to the SAME repository as the execution
    tag OpenWhisk runs.
  * `FROM ${BASE_RUNTIME}` must be a COMPLETE pinned reference; a bare
    `@sha256:...` (empty repository) or a mutable tag is not acceptable.
"""
import importlib.util
import os
import unittest

import _fixture

WS2 = os.path.join(_fixture.REPO, "deployment", "openwhisk", "ws2")
REPO = "localhost:5000/sqlite-coldstart"
A64 = "a" * 64
B64 = "b" * 64


def _load():
    spec = importlib.util.spec_from_file_location(
        "image_identity", os.path.join(WS2, "image_identity.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ii = _load()


class TestSelectRepoDigest(unittest.TestCase):
    def test_prefers_host_qualified_over_local_alias(self):
        # docker's FIRST entry here is the registry-less alias; the exact push
        # target is the second, host-qualified one -- that is what must be bound.
        digs = ["sqlite-coldstart@sha256:" + A64, REPO + "@sha256:" + A64]
        self.assertEqual(ii.select_repo_digest(REPO, digs), REPO + "@sha256:" + A64)

    def test_untags_target_repo_before_matching(self):
        # OW_IMAGE_REPO may arrive with a tag; selection matches the untagged repo.
        digs = [REPO + "@sha256:" + A64]
        self.assertEqual(ii.select_repo_digest(REPO + ":ws2", digs), digs[0])

    def test_requires_exact_repository(self):
        # neither a different path nor a different host may satisfy the match.
        digs = ["localhost:5000/other-coldstart@sha256:" + A64,
                "registry.example:5000/sqlite-coldstart@sha256:" + A64]
        with self.assertRaises(ValueError):
            ii.select_repo_digest(REPO, digs)

    def test_zero_matches_fails_closed(self):
        with self.assertRaises(ValueError):
            ii.select_repo_digest(REPO, [])

    def test_multiple_distinct_matches_fails_closed(self):
        digs = [REPO + "@sha256:" + A64, REPO + "@sha256:" + B64]
        with self.assertRaises(ValueError):
            ii.select_repo_digest(REPO, digs)

    def test_ignores_malformed_entries(self):
        digs = [REPO + ":sometag", REPO + "@sha256:tooShort", REPO + "@sha256:" + A64]
        self.assertEqual(ii.select_repo_digest(REPO, digs), REPO + "@sha256:" + A64)


class TestSameRepository(unittest.TestCase):
    def test_same_repository_matches(self):
        self.assertTrue(ii.same_repository(REPO + ":e3723577ebf7", REPO + "@sha256:" + A64))

    def test_different_repository_rejected(self):
        self.assertFalse(ii.same_repository(
            REPO + ":e3723577ebf7",
            "registry.example:5000/sqlite-coldstart@sha256:" + A64))

    def test_malformed_digest_is_not_same(self):
        self.assertFalse(ii.same_repository(REPO + ":e37", REPO + "@sha256:short"))
        self.assertFalse(ii.same_repository(REPO + ":e37", REPO + ":e37"))


class TestPinnedBaseReference(unittest.TestCase):
    def test_full_repo_at_sha_accepted(self):
        self.assertTrue(ii.is_pinned_base_reference(
            "openwhisk/action-python-v3.11@sha256:" + A64))

    def test_bare_sha_rejected(self):
        self.assertFalse(ii.is_pinned_base_reference("@sha256:" + A64))

    def test_mutable_tag_rejected(self):
        self.assertFalse(ii.is_pinned_base_reference("openwhisk/action-python-v3.11:1.11"))

    def test_empty_and_short_sha_rejected(self):
        self.assertFalse(ii.is_pinned_base_reference(""))
        self.assertFalse(ii.is_pinned_base_reference("openwhisk/x@sha256:tooShort"))


if __name__ == "__main__":
    unittest.main()
