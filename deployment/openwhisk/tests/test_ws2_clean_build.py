"""Prove 01_build_image.sh works from a clean checkout: config/artifacts.json and
_image_stage/ absent at the start.

01 must regenerate the live manifest from the frozen inputs (git-ignored, never
required to pre-exist), verify it against the pin, and record its sha256 -- all
before any staging or build. We exercise that path with DRY_RUN=1 (no docker, no
deploy), a temporary run-root, and a stubbed preflight PASS, then assert:
  * the script exits 0,
  * config/artifacts.json now exists and its DB / classifier / 2d-plan / 10 trace
    hashes equal the frozen pin,
  * _image_stage/ is still absent (DRY_RUN must not stage).

The real repo's git-ignored config/artifacts.json and _image_stage/ are moved
aside in setUp and restored in tearDown so the test leaves the tree unchanged.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _fixture

OW_DIR = os.path.join(_fixture.REPO, "deployment", "openwhisk")
SCRIPT = os.path.join(OW_DIR, "ws2", "01_build_image.sh")
PIN = os.path.join(OW_DIR, "config", "artifacts.native_ycsb.json")
LIVE = os.path.join(OW_DIR, "config", "artifacts.json")
STAGE = os.path.join(OW_DIR, "_image_stage")
# A syntactically-pinned base digest (@sha256:<hex>); never pulled under DRY_RUN.
FAKE_BASE = "example.invalid/openwhisk/action-python-v3.11@sha256:" + "0" * 64


def _have(cmd):
    return shutil.which(cmd) is not None


class TestWs2CleanBuild(unittest.TestCase):
    def setUp(self):
        if not _fixture.have_canonical() or not os.path.exists(PIN):
            self.skipTest("canonical DB / pin absent")
        if not (_have("bash") and _have("git") and os.path.exists(SCRIPT)):
            self.skipTest("bash/git/01_build_image.sh unavailable")

        # Move the git-ignored live manifest + stage tree aside; restore on teardown.
        self._live_bak = LIVE + ".clean_build_bak"
        self._stage_bak = STAGE + ".clean_build_bak"
        for path, bak in ((LIVE, self._live_bak), (STAGE, self._stage_bak)):
            if os.path.lexists(bak):
                (shutil.rmtree if os.path.isdir(bak) else os.remove)(bak)
            if os.path.lexists(path):
                os.rename(path, bak)
        self.addCleanup(self._restore, LIVE, self._live_bak)
        self.addCleanup(self._restore, STAGE, self._stage_bak)

        # Temp run-root with a stubbed preflight PASS for this exact checkout.
        self.run_root = tempfile.mkdtemp(prefix="ws2_clean_build_")
        self.addCleanup(shutil.rmtree, self.run_root, ignore_errors=True)
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_fixture.REPO,
                                      text=True).strip()[:12]
        pre = os.path.join(self.run_root, sha, "00_preflight")
        os.makedirs(pre)
        with open(os.path.join(pre, "STATUS"), "w") as f:
            f.write("status=done\nresult=PASS\ngit_sha=%s\n" % sha)

    @staticmethod
    def _restore(path, bak):
        if os.path.lexists(path):
            (shutil.rmtree if os.path.isdir(path) else os.remove)(path)
        if os.path.lexists(bak):
            os.rename(bak, path)

    def test_dry_run_from_clean_checkout(self):
        # Precondition: a clean checkout has neither of these.
        self.assertFalse(os.path.exists(LIVE), "live manifest should be absent at start")
        self.assertFalse(os.path.exists(STAGE), "_image_stage/ should be absent at start")

        env = dict(os.environ)
        env.update(DRY_RUN="1", WS2_RUN_ROOT=self.run_root, WS2_ALLOW_DIRTY="1",
                   OW_BASE_IMAGE_DIGEST=FAKE_BASE)
        r = subprocess.run(["bash", SCRIPT], cwd=_fixture.REPO, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         "01 DRY_RUN failed from clean checkout:\n%s" % r.stderr)

        # It regenerated the manifest before validating, and did NOT stage.
        self.assertTrue(os.path.exists(LIVE), "01 did not generate config/artifacts.json")
        self.assertFalse(os.path.exists(STAGE), "DRY_RUN must not create _image_stage/")
        self.assertIn("generating live manifest", r.stderr)
        self.assertIn("pin-verified", r.stderr)

        # The live-manifest invariant gate ran AFTER generation and BEFORE any build
        # (DRY_RUN exits before staging/build, so its presence proves the ordering).
        self.assertIn("live-manifest invariants PASS", r.stderr,
                      "01 did not run the live-manifest invariant gate")
        self.assertLess(r.stderr.find("generating live manifest"),
                        r.stderr.find("live-manifest invariants PASS"),
                        "live-manifest gate ran before generation")

        # The generated manifest is byte-tied to the frozen pin.
        with open(LIVE) as f:
            man = json.load(f)
        with open(PIN) as f:
            pin = json.load(f)
        self.assertEqual(man["database"]["sha256"], pin["database"]["sha256"])
        self.assertEqual(man["classifier"]["sha256"], pin["classifier"]["sha256"])
        self.assertEqual(man["strategy_plans"]["2d"]["sha256"],
                         pin["strategy_plans"]["2d"]["sha256"])
        wl = pin["representative_workload"]["canonical_workload_id"]
        seeds = man["workload_traces"][wl]["seeds"]
        for e in pin["representative_workload"]["seed_family"]:
            self.assertEqual(seeds[str(e["seed"])]["sha256"], e["trace_sha256"],
                             "trace seed %s hash != pin" % e["seed"])


if __name__ == "__main__":
    unittest.main()
