#!/usr/bin/env python3
"""Tests for the cross-workload portability ANALYSIS pipeline (§11-§13, §19).

These cover the parallel analysis chain that turns the completed single-batch
portability campaign into thesis-facing evidence, WITHOUT re-running OpenWhisk:

  normalize_portability.py  (§11 additive normalizer, fail-closed gates)
    -> descriptive_portability.py  (§12 coverage / plan-parity / workload CSVs)
      -> synthesis.py campaign weave  (§13/§19/§20 3600 + 468 + 852 + 456 =
         5376 across five byte-frozen campaigns, never pooled)

They assert deployment / correctness / binding parity ONLY. No latency claim,
no ranking, no speedup. The matrix/schedule/execution side is covered separately
by test_portability_matrix.py; this file does NOT duplicate that.
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_OW_ROOT / "analysis"))
import normalize_portability as NP                    # noqa: E402
import descriptive_portability as DP                  # noqa: E402
import synthesis as S                                 # noqa: E402


class TestNormalizePortability(unittest.TestCase):
    """§11: the additive normalizer must reproduce the frozen campaign shape
    and pass every fail-closed gate with zero problems."""

    @classmethod
    def setUpClass(cls):
        cls.facts, cls.problems = S.load_portability()

    def test_load_is_clean(self):
        self.assertIsNotNone(self.facts, "portability facts must load")
        self.assertEqual(self.problems, [], "SHA/chain/shape gates must be clean")

    def test_counts_are_468_234(self):
        self.assertEqual(self.facts["invocations"], 468)
        self.assertEqual(self.facts["pairs"], 234)

    def test_block_pairs_are_108_72_36_18(self):
        self.assertEqual(
            self.facts["block_pairs"],
            {"block1": 108, "block2": 72, "block3": 36, "block4": 18})

    def test_identity_is_the_frozen_single_batch(self):
        self.assertEqual(self.facts["matrix_fingerprint"],
                         NP.PORTABILITY["expected_matrix_fingerprint"])
        self.assertEqual(self.facts["run_config_sha256"],
                         NP.PORTABILITY["expected_run_config_sha256"])

    def test_foreign_run_configs_are_not_the_binding(self):
        # the primary/secondary run_configs must never be the portability binding
        for foreign in NP.PORTABILITY["foreign_run_configs"]:
            self.assertNotEqual(self.facts["run_config_sha256"], foreign)

    def test_five_workload_families(self):
        self.assertEqual(len(self.facts["workload_families"]), 5)


class TestDescriptivePortability(unittest.TestCase):
    """§12: coverage / plan-parity / workload-summary CSVs must reconcile to the
    frozen campaign, and the parity taxonomy must classify 24/12/3."""

    @classmethod
    def setUpClass(cls):
        import csv
        import io
        base = _OW_ROOT / "analysis" / "descriptive" / "portability"

        def _rows(name):
            return list(csv.DictReader(
                io.StringIO((base / name).read_text())))
        cls.coverage = _rows("portability_coverage.csv")
        cls.parity = _rows("portability_plan_parity.csv")
        cls.workloads = _rows("portability_workload_summary.csv")

    def test_coverage_block_pairs_sum_to_234(self):
        from collections import Counter
        bc = Counter()
        for r in self.coverage:
            bc[r["block_id"]] += int(r["n_pairs"])
        self.assertEqual(dict(bc),
                         {"block1": 108, "block2": 72, "block3": 36, "block4": 18})
        self.assertEqual(sum(bc.values()), 234)

    def test_parity_taxonomy_is_24_12_3(self):
        from collections import Counter
        c = Counter(r["parity_type"] for r in self.parity)
        self.assertEqual(c["exact_native_plan"], 24)
        self.assertEqual(c["semantic_contract_reconstruction"], 12)
        self.assertEqual(c["structural_static"], 3)
        self.assertEqual(len(self.parity), 39)

    def test_2e_k10_is_semantic_reconstruction_not_exact(self):
        # 2e_K10 is the approved contract reconstruction, never mislabeled exact
        for r in self.parity:
            if r["strategy"] == "2e_K10":
                self.assertEqual(r["parity_type"],
                                 "semantic_contract_reconstruction")

    def test_2d_is_structural_static_only(self):
        for r in self.parity:
            if r["parity_type"] == "structural_static":
                self.assertEqual(r["strategy"], "2d")

    def test_workloads_are_the_five_families(self):
        fams = {r["workload_family"] for r in self.workloads}
        self.assertEqual(fams, {"YC", "YCu", "YCh01", "C", "C_hit"})
        self.assertEqual(sum(int(r["n_pairs"]) for r in self.workloads), 234)


class TestTwoRoleSynthesis(unittest.TestCase):
    """§13/§19/§20: synthesis must weave the campaigns as 3600 + 468 + 852 + 456
    = 5376 formal invocations across five byte-frozen campaigns that are explicitly
    NOT pooled, expose the L + M claim categories, and set the machine-readable
    restriction flags."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp(prefix="port_synth_")
        cls.manifest, cls.ok = _run_synthesis(cls.tmp)
        cls.notes = (Path(cls.tmp) / "openwhisk_thesis_notes.md").read_text()
        cls.threats = (Path(cls.tmp) / "threats_to_validity.md").read_text()

    def test_run_passes(self):
        self.assertTrue(self.ok, "synthesis must PASS with portability present")

    def test_manifest_two_role_summary(self):
        tr = self.manifest["two_role_summary"]
        self.assertEqual(tr["strategy_space_formal_invocations"], 3600)
        self.assertEqual(tr["portability_formal_invocations"], 468)
        self.assertEqual(tr["portability_ext_formal_invocations"], 852)
        self.assertEqual(tr["portability_full_closure_formal_invocations"], 456)
        self.assertEqual(tr["total_formal_invocations"], 5376)
        self.assertEqual(tr["total_formal_pairs"], 2688)
        self.assertEqual(tr["campaigns"], 5)
        self.assertFalse(tr["pooled"], "the five campaigns must never be pooled")

    def test_manifest_records_portability_ext_chain(self):
        ps = self.manifest["portability_ext_source"]
        self.assertTrue(ps["portability_ext_present"])
        self.assertEqual(
            ps["matrix_fingerprint"],
            "5ba26fe952104792a9b6803e581627c331884fe1b39b41adb6ebeddb245fe300")
        self.assertEqual(
            ps["run_config_sha256"],
            "bf504a28fb0ac3cec3b189a4de1f7b8968a35bbd9866c2ae1d5784ccc3bf77da")

    def test_manifest_records_portability_chain(self):
        ps = self.manifest["portability_source"]
        self.assertTrue(ps["portability_present"])
        self.assertEqual(ps["matrix_fingerprint"],
                         NP.PORTABILITY["expected_matrix_fingerprint"])
        self.assertEqual(ps["run_config_sha256"],
                         NP.PORTABILITY["expected_run_config_sha256"])

    def test_restriction_flags_present(self):
        cr = S.CLAIM_RESTRICTIONS
        self.assertIs(
            cr["portability_is_execution_binding_not_latency_ranking"], True)
        self.assertIs(
            cr["portability_and_strategy_space_campaigns_not_pooled"], True)

    def test_L_category_has_safe_and_do_not_claim(self):
        cats = {(e["category"], e["classification"]) for e in S.CLAIM_MAP}
        self.assertIn(("L_cross_workload_portability", "SAFE"), cats)
        self.assertIn(("L_cross_workload_portability", "DO_NOT_CLAIM"), cats)

    def test_thesis_notes_state_5376_and_do_not_pool(self):
        self.assertIn("5376", self.notes)
        self.assertIn("3600", self.notes)
        self.assertIn("468", self.notes)
        self.assertIn("852", self.notes)
        self.assertIn("456", self.notes)
        self.assertIn("do not pool", self.notes.lower())

    def test_thesis_notes_do_not_pool_into_one_effect(self):
        # the framing must explicitly forbid pooling into a single effect, and
        # must NOT imply all 5376 estimate one effect
        low = self.notes.lower()
        self.assertIn("not be pooled into a single effect", low)
        self.assertNotIn("5376 invocations estimate", low)
        self.assertNotIn("5376 formal invocations estimate", low)

    def test_L_and_M_categories_present(self):
        cats = {(e["category"], e["classification"]) for e in S.CLAIM_MAP}
        # fourth-campaign SAFE row + effectiveness-portability descriptive rows
        self.assertIn(("L_cross_workload_portability", "SAFE"), cats)
        self.assertIn(("M_effectiveness_portability", "QUALIFIED"), cats)
        self.assertIn(("M_effectiveness_portability", "DO_NOT_CLAIM"), cats)

    def test_threats_carry_portability_paragraph(self):
        low = self.threats.lower()
        self.assertIn("portability", low)
        self.assertIn("468", self.threats)
        # portability latency must be explicitly disclaimed, never a speedup
        self.assertIn("not", low)
        self.assertTrue("latency" in low or "ranking" in low or "speedup" in low)


class TestPortabilityExtSynthesis(unittest.TestCase):
    """§19: the fourth campaign (portability_ext) must load + SHA-gate clean and
    reproduce the frozen 852/426 shape and identity."""

    @classmethod
    def setUpClass(cls):
        cls.facts, cls.problems = S.load_portability_ext()

    def test_load_is_clean(self):
        self.assertIsNotNone(self.facts, "portability_ext facts must load")
        self.assertEqual(self.problems, [], "SHA/chain/shape gates must be clean")

    def test_counts_are_852_426(self):
        self.assertEqual(self.facts["invocations"], 852)
        self.assertEqual(self.facts["pairs"], 426)

    def test_block_pairs_are_the_seven_ext_blocks(self):
        self.assertEqual(
            self.facts["block_pairs"],
            {"block5": 36, "block6": 180, "block7": 90, "block8": 72,
             "block9": 24, "block10": 18, "block11": 6})

    def test_identity_is_the_frozen_ext_batch(self):
        self.assertEqual(
            self.facts["matrix_fingerprint"],
            "5ba26fe952104792a9b6803e581627c331884fe1b39b41adb6ebeddb245fe300")
        self.assertEqual(
            self.facts["run_config_sha256"],
            "bf504a28fb0ac3cec3b189a4de1f7b8968a35bbd9866c2ae1d5784ccc3bf77da")

    def test_run_config_is_not_a_prior_campaign(self):
        # the ext run_config must never collide with the three prior campaigns
        for foreign in (
                "022fbeb01a8d9d45686e56823eca1e1ef30712f2a13c4a878cb5f7ef0097b5b7",
                "441609e6"[:8],  # secondary prefix guard
                "64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947"):
            self.assertNotEqual(self.facts["run_config_sha256"], foreign)

    def test_five_workload_families(self):
        self.assertEqual(len(self.facts["workload_families"]), 5)


def _run_synthesis(out_dir):
    """Run the real synthesis into out_dir and return (manifest, ok)."""
    import json
    S.run(out_dir=Path(out_dir))
    manifest = json.loads(
        (Path(out_dir) / "synthesis_manifest.json").read_text())
    return manifest, manifest["ok"]


if __name__ == "__main__":
    unittest.main()
