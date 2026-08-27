"""layers_5 strategy (Batch 1): the action delivers the frozen 5-interior prefix.

Pure tests cover the static invariants (supported set, delivery invariant, request
schema, and that the WS2 implementation gate stays in sync with the action). The
runtime tests need the generated live manifest (config/artifacts.json, gitignored)
plus the canonical DB and skip cleanly when either is absent.
"""
import ast
import csv
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

IMAGE = "sha256:" + "a" * 64
os.environ["OW_ACTION_IMAGE_DIGEST"] = IMAGE

import main  # noqa: E402
import residency  # noqa: E402
import session as session_mod  # noqa: E402

REPO = _fixture.REPO
ARTIFACTS = os.path.join(REPO, "deployment/openwhisk/config/artifacts.json")
GATE_SCRIPT = os.path.join(REPO, "deployment/openwhisk/ws2/05_full_matrix.sh")
L5_OFFSETS = [4096, 8192, 12288, 2756608, 2760704]


def have_layers_manifest():
    return os.path.exists(ARTIFACTS) and os.path.exists(_fixture.CANONICAL_DB)


def full_request(strategy, h, **kw):
    base = dict(request_id="l5-" + strategy, workload="native_ycsb_c_read_zipf",
                strategy=strategy, seed=1, first_operation_id=0,
                diagnostic_mode=False, cold_reset=True,
                expected_artifact_manifest_hash=h, pair_id="pair-1",
                repetition_id=0, schedule_position=1, schedule_seed=42,
                run_config_sha256="c" * 64, expected_action_image_digest=IMAGE,
                handle_mode="warm")
    base.update(kw)
    return base


class TestLayersFivePureInvariants(unittest.TestCase):
    """No canonical artifacts needed."""

    def test_supported_strategies_include_layers5(self):
        self.assertEqual(main.SUPPORTED_STRATEGIES,
                         ("baseline", "2d", "layers_5", "layers_92", "2e_K10",
                          "2f_slru", "2e_K500", "leaf_freq_K10", "leaf_rand_K10",
                          "2f_top102", "learned_markov_102", "2f_top28",
                          "learned_markov_28", "2f_top14", "learned_markov_14"))

    def test_delivery_invariant_is_five_five_zero_five(self):
        self.assertEqual(main.DELIVERY_INVARIANTS["layers_5"],
                         {"selected_page_count": 5, "selected_interior_count": 5,
                          "selected_leaf_count": 0, "delivered_page_count": 5})

    def test_request_schema_accepts_layers5_rejects_unknown(self):
        req = full_request("layers_5", "a" * 64)
        problems = main.validate_request_schema(req)
        self.assertFalse([p for p in problems if "strategy must be one of" in p],
                         problems)
        bad = main.validate_request_schema(full_request("frequency_14", "a" * 64))
        self.assertTrue([p for p in bad if "strategy must be one of" in p])


class TestWs2ImplementationGate(unittest.TestCase):
    """The WS2 implementation gate must recognize exactly the action's supported
    set, and reject anything else."""

    def _gate_impl_set(self):
        with open(GATE_SCRIPT) as f:
            text = f.read()
        m = re.search(r"impl = (\{[^}]*\})", text)
        self.assertIsNotNone(m, "impl set not found in 05_full_matrix.sh")
        return ast.literal_eval(m.group(1))

    def test_gate_impl_matches_action_supported(self):
        self.assertEqual(self._gate_impl_set(), set(main.SUPPORTED_STRATEGIES))

    def test_gate_accepts_batch1_and_gates_others(self):
        impl = self._gate_impl_set()
        self.assertEqual([s for s in ("baseline", "2d", "layers_5") if s not in impl],
                         [])
        self.assertEqual([s for s in ("baseline", "frequency_14") if s not in impl],
                         ["frequency_14"])


@unittest.skipUnless(have_layers_manifest(),
                     "live artifacts.json / canonical DB absent")
class TestLayersFiveSessionLoading(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.pc = self.s.manifest["database"]["page_count"]

    def test_loads_exactly_five_offsets(self):
        offs = self.s.static_plan_offsets["layers_5"]
        self.assertEqual(offs, L5_OFFSETS)
        self.assertEqual(
            offs, self.s.manifest["strategy_plans"]["layers_5"]["offsets"])
        self.assertTrue(set(offs).issubset(self.s.interior_offset_set))

    def test_tampered_plan_sha_rejected(self):
        self.s.manifest["strategy_plans"]["layers_5"]["sha256"] = "0" * 64
        reasons = self.s._validate_static_plans(4096, self.pc)
        self.assertTrue([r for r in reasons if "sha256 mismatch" in r], reasons)

    def test_wrong_offset_count_rejected(self):
        self.s.static_plan_offsets["layers_5"] = L5_OFFSETS[:4]
        reasons = self.s._validate_static_plans(4096, self.pc)
        self.assertTrue([r for r in reasons if "expected 5" in r], reasons)

    def test_non_interior_offset_rejected(self):
        # keep CSV/inline consistent but drop one selected page from the interior
        # skeleton -> the interior-membership branch must fail closed.
        self.s.interior_offset_set = self.s.interior_offset_set - {L5_OFFSETS[0]}
        reasons = self.s._validate_static_plans(4096, self.pc)
        self.assertTrue([r for r in reasons if "not an interior" in r], reasons)


@unittest.skipUnless(have_layers_manifest(),
                     "live artifacts.json / canonical DB absent")
class TestLayersFiveSelectOffsets(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)

    def test_baseline_unchanged(self):
        self.assertEqual(main.select_offsets("baseline", self.s), [])

    def test_2d_unchanged_92(self):
        self.assertEqual(len(main.select_offsets("2d", self.s)), 92)

    def test_layers5_returns_exact_five(self):
        self.assertEqual(main.select_offsets("layers_5", self.s), L5_OFFSETS)


@unittest.skipUnless(have_layers_manifest(),
                     "live artifacts.json / canonical DB absent")
class TestLayersFiveMeasured(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.s.open_warm_handle()
        self.s.deployment_image_digest = IMAGE
        self.h = self.s.artifact_manifest_sha256
        self.addCleanup(self.s.close_warm_handle)

    def test_measured_layers5_valid(self):
        r = main.handle(full_request("layers_5", self.h), self.s)
        self.assertIsNone(r.get("error_stage"), r.get("error"))
        self.assertEqual((r["selected_page_count"], r["selected_interior_count"],
                          r["selected_leaf_count"], r["delivered_page_count"]),
                         (5, 5, 0, 5))
        self.assertTrue(r["delivery_valid"])
        self.assertTrue(r["measured_valid"])
        self.assertEqual(
            r["plan_sha256"],
            self.s.manifest["strategy_plans"]["layers_5"]["sha256"])

    def test_2d_regression_still_92(self):
        r = main.handle(full_request("2d", self.h), self.s)
        self.assertEqual(r["selected_interior_count"], 92)
        self.assertTrue(r["measured_valid"])

    def test_incomplete_layers5_delivery_not_measured_valid(self):
        with mock.patch.object(residency.PageMap, "deliver_willneed", return_value=4):
            r = main.handle(full_request("layers_5", self.h), self.s)
        self.assertFalse(r["delivery_valid"])
        self.assertFalse(r["measured_valid"])


if __name__ == "__main__":
    unittest.main()
