"""Regression tests locking the WS2 stage-00 / stage-01 test-gate lifecycle.

The bug these guard against: 00_preflight (read-only, runs BEFORE the image build)
was running the full `tests.test_workload_naming` and
`deployment.openwhisk.tests.test_manifest_invariants` modules, which pull in

  * PaperHasNoForbiddenTerms      -> needs paper/main.tex (a paper-build concern,
                                     never a WS2 deployment requirement), and
  * TestNativeYcsbLiveManifestAgreement -> needs the live config/artifacts.json,
                                     which 01 GENERATES (absent on a clean checkout).

so 00_preflight failed on a fresh WS2 checkout for reasons unrelated to deployment
readiness. The fix keeps the lifecycle:

  00_preflight : source/frozen-artifact checks only (paper-free, live-manifest-free)
  01_build_image: generate artifacts.json -> live-manifest invariants -> build

These tests prove:
  * the selectors 00_preflight runs collect NEITHER the paper test NOR the
    live-manifest test (structural: it cannot require either),
  * those selectors still PASS with the live config/artifacts.json absent
    (functional: proves no live-manifest / no paper dependency at run time),
  * 00_preflight.sh actually runs exactly those selectors and none of the
    forbidden module-wide ones,
  * 01_build_image.sh runs the live-manifest invariant gate AFTER generating
    artifacts.json and BEFORE `docker build`.

No build/deploy/invoke is performed. The only file touched at run time is the
git-ignored config/artifacts.json (moved aside and restored); the tracked paper is
never touched -- paper independence is proven structurally, not by hiding paper.
"""
import os
import shutil
import subprocess
import unittest

import _fixture

REPO = _fixture.REPO
OW_DIR = os.path.join(REPO, "deployment", "openwhisk")
PREFLIGHT_SH = os.path.join(OW_DIR, "ws2", "00_preflight.sh")
BUILD_SH = os.path.join(OW_DIR, "ws2", "01_build_image.sh")
LIVE = os.path.join(OW_DIR, "config", "artifacts.json")

# The exact selectors 00_preflight.sh runs (kept in sync by
# test_preflight_script_runs_exactly_these_selectors below).
PREFLIGHT_SELECTORS = [
    "tests.test_workload_naming.RegistryMapping",
    "tests.test_workload_naming.NativeYcsbRegistry",
    "deployment.openwhisk.tests.test_manifest_invariants.TestPageSizeDecode",
    "deployment.openwhisk.tests.test_manifest_invariants.TestPlanInvariants",
    "deployment.openwhisk.tests.test_manifest_invariants.TestOracleSingleSource",
    "deployment.openwhisk.tests.test_manifest_invariants.TestNativeYcsbPinFrozenSources",
]

# Names that must NEVER be reachable from a 00_preflight selector: the paper test
# and the live-artifacts.json invariant test (the latter is 01's gate, not 00's).
FORBIDDEN_NAMES = ["PaperHasNoForbiddenTerms", "TestNativeYcsbLiveManifestAgreement"]
LIVE_GATE = "TestNativeYcsbLiveManifestAgreement"


class TestPreflightSelectorsAreBeforeBuildSafe(unittest.TestCase):
    """Structural: the preflight selector set cannot require paper/main.tex or the
    live config/artifacts.json, because it collects neither test."""

    def test_selectors_collect_no_paper_or_live_manifest_test(self):
        loader = unittest.TestLoader()
        collected = []

        def walk(suite):
            for t in suite:
                if isinstance(t, unittest.TestSuite):
                    walk(t)
                else:
                    collected.append(t.id())

        for sel in PREFLIGHT_SELECTORS:
            walk(loader.loadTestsFromName(sel))
        # loader errors surface as _FailedTest ids -- none of our selectors should.
        self.assertTrue(collected, "no tests were collected from the preflight selectors")
        for tid in collected:
            self.assertNotIn("loadTestsFailure", tid, "selector failed to import: %s" % tid)
            for bad in FORBIDDEN_NAMES:
                self.assertNotIn(bad, tid,
                                 "preflight selector unexpectedly collects %s (%s)" % (bad, tid))


class TestPreflightSelectorsPassWithoutLiveManifest(unittest.TestCase):
    """Functional: run the preflight selectors with config/artifacts.json absent and
    assert they PASS -- proving 00_preflight does not require the generated manifest
    (nor paper: the run never references main.tex)."""

    def setUp(self):
        if not shutil.which("python3"):
            self.skipTest("python3 unavailable")
        # Move the git-ignored live manifest aside so the run happens with it ABSENT.
        self._bak = LIVE + ".preflight_gate_bak"
        if os.path.lexists(self._bak):
            os.remove(self._bak)
        self._moved = False
        if os.path.exists(LIVE):
            os.rename(LIVE, self._bak)
            self._moved = True
        self.addCleanup(self._restore)

    def _restore(self):
        if self._moved and not os.path.exists(LIVE) and os.path.exists(self._bak):
            os.rename(self._bak, LIVE)
        elif os.path.exists(self._bak):
            os.remove(self._bak)

    def test_preflight_selectors_pass_without_paper_or_artifacts(self):
        self.assertFalse(os.path.exists(LIVE),
                         "live manifest should be absent for this proof")
        r = subprocess.run(
            ["python3", "-m", "unittest", "-v", *PREFLIGHT_SELECTORS],
            cwd=REPO, capture_output=True, text=True)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0,
                         "preflight selectors failed with artifacts.json absent:\n%s" % out)
        # It must not have exercised the paper test or the live-manifest gate.
        self.assertNotIn("main.tex", out)
        for bad in FORBIDDEN_NAMES:
            self.assertNotIn(bad, out, "preflight run touched %s" % bad)


class TestGateWiringInScripts(unittest.TestCase):
    """The scripts on disk must actually implement the lifecycle: 00 runs exactly the
    before-build selectors; 01 runs the live-manifest gate after generation, before
    build."""

    @staticmethod
    def _read(path):
        with open(path) as f:
            return f.read()

    @staticmethod
    def _run_unittest_lines(txt):
        # Only actual invocations, not the run_unittest() function definition or comments.
        return [ln.strip() for ln in txt.splitlines()
                if ln.strip().startswith("run_unittest ")
                and "local mod=" not in ln and "run_unittest()" not in ln]

    def test_preflight_script_runs_exactly_these_selectors(self):
        txt = self._read(PREFLIGHT_SH)
        invoked = self._run_unittest_lines(txt)
        self.assertEqual([ln[len("run_unittest "):] for ln in invoked], PREFLIGHT_SELECTORS,
                         "00_preflight.sh run_unittest selectors drifted from the "
                         "before-build set:\n%s" % "\n".join(invoked))
        # No run_unittest invocation may name a forbidden (paper / live-manifest) test,
        # nor a module-wide suite that would pull one in.
        for ln in invoked:
            for bad in FORBIDDEN_NAMES:
                self.assertNotIn(bad, ln, "00_preflight runs a forbidden test: %s" % ln)
            self.assertNotIn("run_unittest tests.test_workload_naming\n", ln + "\n")
            self.assertRegex(ln, r"\.[A-Z]\w+$",
                             "00_preflight run_unittest target is not class-scoped: %s" % ln)

    def test_build_script_runs_live_gate_after_generation_before_build(self):
        txt = self._read(BUILD_SH)
        gen = txt.find('build_artifact_manifest.py" --out')
        gate = txt.find('python3 -m unittest "$LIVE_INV"')
        build = txt.rfind("docker build --no-cache")  # the real build, last occurrence
        self.assertNotEqual(gen, -1, "01 does not generate artifacts.json")
        self.assertNotEqual(gate, -1, "01 does not run the live-manifest invariant gate")
        self.assertNotEqual(build, -1, "01 has no docker build")
        self.assertLess(gen, gate, "live-manifest gate runs before artifacts.json is generated")
        self.assertLess(gate, build, "live-manifest gate runs after docker build")
        # The gate must target exactly the live-manifest invariant class.
        self.assertIn('LIVE_INV="deployment.openwhisk.tests.test_manifest_invariants.%s"' % LIVE_GATE,
                      txt, "01's live gate does not target %s" % LIVE_GATE)


if __name__ == "__main__":
    unittest.main()
