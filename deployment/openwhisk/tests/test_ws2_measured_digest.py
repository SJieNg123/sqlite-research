"""Regression tests for the bound-image-digest wiring in the measured WS2 stages.

02_deploy writes the bound image identity under `immutable_image_digest`, but the
measured stages (04_feasibility, 05_full_matrix) still read the legacy
`image_digest` key -> every generated request got an empty
`expected_action_image_digest` and all invocations failed with "empty
expected_action_image_digest". These tests pin the fix:

  * the measured stages read `immutable_image_digest` (not the legacy key),
  * they fail closed on that digest BEFORE the schedule is built/invoked,
  * build_schedule stamps that EXACT value onto every generated request, and
  * no measured stage still reads the legacy deploy_meta `image_digest` key.

The collect stage's provenance record is also checked (it must source the current
key rather than emit null).
"""
import importlib.util
import os
import unittest

import _fixture

REPO = _fixture.REPO
WS2 = os.path.join(REPO, "deployment", "openwhisk", "ws2")
CLIENT = os.path.join(REPO, "deployment", "openwhisk", "client")
FEAS = os.path.join(WS2, "04_feasibility.sh")
MATRIX = os.path.join(WS2, "05_full_matrix.sh")
COLLECT = os.path.join(WS2, "06_collect.sh")


def _read(p):
    with open(p) as f:
        return f.read()


def _load_build_schedule():
    spec = importlib.util.spec_from_file_location(
        "build_schedule", os.path.join(CLIENT, "build_schedule.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMeasuredStagesReadCurrentDigestKey(unittest.TestCase):
    def setUp(self):
        self.feas = _read(FEAS)
        self.matrix = _read(MATRIX)

    def test_04_consumes_immutable_image_digest(self):
        self.assertIn('m.get("immutable_image_digest"', self.feas)

    def test_05_consumes_immutable_image_digest(self):
        self.assertIn('m.get("immutable_image_digest"', self.matrix)

    def test_no_measured_stage_reads_legacy_image_digest(self):
        # neither measured stage may read the legacy deploy_meta key.
        self.assertNotIn('m.get("image_digest"', self.feas)
        self.assertNotIn('m.get("image_digest"', self.matrix)

    def test_04_fails_closed_on_digest_before_building_schedule(self):
        # the pinned-digest validation + die must precede the schedule build/invoke.
        self.assertIn("check-base", self.feas)
        self.assertIn("immutable_image_digest", self.feas)  # in the die message
        self.assertLess(self.feas.index("check-base"),
                        self.feas.index("build_schedule.py"),
                        "digest validation must run before the schedule is built")

    def test_05_fails_closed_on_digest_before_building_schedule(self):
        self.assertIn("check-base", self.matrix)
        self.assertLess(self.matrix.index("check-base"),
                        self.matrix.index("build_schedule.py"))


class TestScheduleStampsExactDigest(unittest.TestCase):
    """build_schedule must place the EXACT deploy-bound digest on every request so a
    correctly-read `immutable_image_digest` reaches expected_action_image_digest."""

    def setUp(self):
        self.bs = _load_build_schedule()
        self.digest = "localhost:5000/sqlite-coldstart@sha256:" + "a" * 64
        self.ids = {"run_config_sha256": "c" * 64,
                    "artifact_manifest_sha256": "d" * 64,
                    "action_image_digest": self.digest}

    def test_every_invocation_and_warmup_carries_exact_digest(self):
        sched = self.bs.build_schedule(
            workloads=["native_ycsb_c_read_zipf"], seeds=[1], first_ops=[0],
            handle_modes=["warm"], targets=["2d"], repetitions=3,
            schedule_seed=20260804, ids=self.ids)
        self.assertTrue(sched["invocations"])
        for inv in sched["invocations"]:
            self.assertEqual(inv["expected_action_image_digest"], self.digest)
        self.assertEqual(sched["warmup"]["expected_action_image_digest"], self.digest)

    def test_empty_digest_would_propagate_as_empty(self):
        # documents the failure mode the stage fix prevents: a blank bound digest
        # yields blank request identities (which the runtime rejects). The stage now
        # fails closed before reaching this point.
        ids = dict(self.ids, action_image_digest="")
        sched = self.bs.build_schedule(
            workloads=["native_ycsb_c_read_zipf"], seeds=[1], first_ops=[0],
            handle_modes=["warm"], targets=["2d"], repetitions=1,
            schedule_seed=20260804, ids=ids)
        self.assertEqual(sched["invocations"][0]["expected_action_image_digest"], "")


class TestCollectSourcesCurrentDigestKey(unittest.TestCase):
    def test_06_sources_immutable_image_digest_not_legacy(self):
        txt = _read(COLLECT)
        self.assertIn('d.get("immutable_image_digest")', txt)
        self.assertNotIn('d.get("image_digest")', txt)


if __name__ == "__main__":
    unittest.main()
