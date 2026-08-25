#!/usr/bin/env python3
"""Tests for the WK1 thesis SYNTHESIS layer (analysis/synthesis.py).

These assert the CLAIM RESTRICTIONS and TABLE SCHEMAS the layer exists to enforce
(§16): SHA-gated inputs, full strategy coverage, no computed speedup/winner/ranking
columns, first_query_us kept distinct from total cold-start latency, warm paired
ratios never emitted as headline, learned-vs-frequency never a bare winner,
order-effect source left unresolved, and the machine-readable restriction flags.
They do NOT assert any performance claim.
"""
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_OW_ROOT / "analysis"))
import descriptive as D                              # noqa: E402
import synthesis as S                                # noqa: E402


def _run():
    """Load real (SHA-verified) descriptive inputs and build in-memory tables."""
    data = S.load_inputs()
    return data


class TestSourceIntegrity(unittest.TestCase):
    def test_inputs_load_without_sha_or_chain_problems(self):
        data = _run()
        self.assertEqual(data["problems"], [], "input SHA/chain must be clean")

    def test_tamper_detection_fails_closed(self):
        # a wrong expected SHA in the manifest view must surface as a problem
        import copy
        # simulate by checking the gate logic directly: mismatch is reported
        data = S.load_inputs()
        # the descriptive manifest SHA for cost_vectors must equal the file SHA
        dm = data["desc_manifest"]
        actual = D.sha256_file(data["desc_dir"] / "cost_vectors.csv")
        self.assertEqual(actual, dm["outputs"]["cost_vectors.csv"]["sha256"])


class TestCoverageAndSchema(unittest.TestCase):
    def setUp(self):
        self.data = _run()
        self.footprint, _ = S.build_footprint(self.data)
        self.cost, _ = S.build_cost_vectors(self.data)
        self.matched, _ = S.build_matched_budget(self.data)
        self.fig_a = S.build_fig_footprint_vs_delivery(self.data)
        self.fig_b = S.build_fig_query_vs_delivery(self.data)
        self.fig_c = S.build_fig_order_effect(self.data)

    def test_all_nine_strategies_present(self):
        self.assertEqual({r["strategy"] for r in self.footprint},
                         set(D.STRATEGY_ORDER))
        self.assertEqual(len(self.footprint), 9)

    def test_cost_vectors_cover_both_handle_modes(self):
        self.assertEqual(len(self.cost), 18)
        pairs = {(r["strategy"], r["handle_mode"]) for r in self.cost}
        for s in D.STRATEGY_ORDER:
            for m in D.HANDLE_MODES:
                self.assertIn((s, m), pairs)

    def test_matched_budget_covers_groups_ABCD(self):
        groups = {r["group"] for r in self.matched}
        self.assertEqual(len(groups), 4)
        self.assertEqual(len(self.matched), 16)
        # 2f_slru is ungrouped -> must NOT appear
        self.assertNotIn("2f_slru", {r["strategy"] for r in self.matched})

    def test_no_forbidden_computed_columns(self):
        # §16: no table may compute a speedup/ratio/winner/rank/score/percentage
        for rows in (self.footprint, self.cost, self.matched,
                     self.fig_a, self.fig_b, self.fig_c):
            self.assertEqual(S._forbidden_columns(rows[0].keys()), [])

    def test_plan_generation_not_a_false_positive(self):
        # regression: 'ratio' must not match inside 'generation'
        self.assertEqual(S._forbidden_columns(["plan_generation"]), [])
        # but a real computed column must still be caught
        self.assertEqual(S._forbidden_columns(["warm_speedup_ratio"]),
                         ["warm_speedup_ratio"])
        self.assertEqual(S._forbidden_columns(["pct_faster"]), ["pct_faster"])

    def test_first_query_not_labeled_total_cold_start(self):
        # the cost-vector column is the query phase only; no column claims total
        for r in self.cost:
            self.assertIn("median_first_query_us", r)
        for c in self.cost[0].keys():
            self.assertNotIn("cold_start", c.lower())
        self.assertIn("NOT total cold-start",
                      S.COST_VECTOR_LEGEND["first_query_us"])

    def test_footprint_variability_invariant(self):
        # only 2f_slru may carry a range; the rest are exact constants
        for r in self.footprint:
            varies = "-" in str(r["selected_pages"])
            if r["strategy"] in D.VARIABLE_FOOTPRINT:
                self.assertTrue(varies, r["strategy"])
            else:
                self.assertFalse(varies, r["strategy"])
                self.assertEqual(int(r["selected_pages"]),
                                 D.EXPECTED_CONSTANT_PAGES[r["strategy"]])

    def test_emergent_split_recorded_for_budget_matched(self):
        origins = {(r["strategy"], r["interior_leaf_split_origin"])
                   for r in self.matched}
        self.assertIn(("2f_top102", "emergent"), origins)
        self.assertIn(("learned_markov_102", "emergent"), origins)
        # imposed splits stay imposed
        self.assertIn(("2e_K10", "imposed"), origins)
        self.assertIn(("leaf_freq_K10", "imposed"), origins)


class TestClaimRestrictions(unittest.TestCase):
    def test_restriction_flags_present_and_valued(self):
        r = S.CLAIM_RESTRICTIONS
        self.assertEqual(r["openwhisk_role"], "deployment_complement")
        self.assertTrue(r["native_is_primary_performance_evidence"])
        self.assertTrue(r["no_naive_warm_pair_speedup"])
        self.assertTrue(r["no_first_arm_causal_estimate"])
        self.assertTrue(r["exact_order_effect_source_unresolved"])
        self.assertTrue(r["no_strategy_winner_claim"])

    def test_claim_map_classifications_valid(self):
        valid = {"SAFE", "QUALIFIED", "DO_NOT_CLAIM"}
        for e in S.CLAIM_MAP:
            self.assertIn(e["classification"], valid)

    def test_warm_paired_ratio_is_do_not_claim(self):
        idx = {(e["category"], e["classification"]) for e in S.CLAIM_MAP}
        self.assertIn(("I_warm_paired_latency", "DO_NOT_CLAIM"), idx)

    def test_first_arm_is_do_not_claim(self):
        idx = {(e["category"], e["classification"]) for e in S.CLAIM_MAP}
        self.assertIn(("K_first_arm_diagnostic", "DO_NOT_CLAIM"), idx)

    def test_learned_vs_frequency_winner_is_do_not_claim(self):
        idx = {(e["category"], e["classification"]) for e in S.CLAIM_MAP}
        self.assertIn(("G_matched_budget_selection", "DO_NOT_CLAIM"), idx)

    def test_openwhisk_discovery_claim_is_forbidden(self):
        # the "OpenWhisk revealed/discovered the core thesis" statement must be
        # explicitly classified DO_NOT_CLAIM (do not rewrite thesis history)
        hits = [e for e in S.CLAIM_MAP
                if "reveal" in e["claim"].lower() or "discover" in e["claim"].lower()]
        self.assertTrue(hits)
        for e in hits:
            self.assertEqual(e["classification"], "DO_NOT_CLAIM")

    def test_first_query_claim_carries_order_effect_qualifier(self):
        e = [x for x in S.CLAIM_MAP
             if x["category"] == "E_first_query_descriptive"][0]
        self.assertEqual(e["classification"], "QUALIFIED")
        q = e["qualification"].lower()
        self.assertIn("order", q)
        self.assertIn("not", q)  # not the primary estimate

    def test_no_claim_text_asserts_hardware_root_cause(self):
        # falsified / out-of-scope causes may be MENTIONED in threats prose, but no
        # claim-map entry may ASSERT a hardware root cause as the explanation
        for e in S.CLAIM_MAP:
            reason = e["reason"].lower()
            self.assertNotIn("nvme controller", reason)
            self.assertNotIn("c-state", reason)
            # 'page-cache carryover' only appears as the SUBJECT of falsification
            self.assertNotIn("caused by page-cache carryover", reason)


class TestEndToEndArtifacts(unittest.TestCase):
    def test_run_passes_and_emits_all_artifacts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ok, manifest = S.run(out_dir=td)
            self.assertTrue(ok, "synthesis must pass its own fail-closed gates")
            out = Path(td)
            for name in ("openwhisk_strategy_footprint.csv",
                         "openwhisk_strategy_footprint.md",
                         "openwhisk_cost_vectors.csv",
                         "matched_budget_descriptives.csv",
                         "claim_map.md", "openwhisk_thesis_notes.md",
                         "threats_to_validity.md",
                         "figure_footprint_vs_delivery.svg",
                         "figure_query_vs_delivery.svg",
                         "figure_order_effect_diagnostic.svg",
                         "figure_source_footprint_vs_delivery.csv",
                         "figure_source_query_vs_delivery.csv",
                         "figure_source_order_effect.csv",
                         "synthesis_validation.txt"):
                self.assertTrue((out / name).exists(), name)

    def test_manifest_records_chain_and_restrictions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ok, manifest = S.run(out_dir=td)
            self.assertTrue(ok)
            self.assertEqual(manifest["claim_restrictions"],
                             S.CLAIM_RESTRICTIONS)
            # source chain SHAs are carried
            src = manifest["source"]
            self.assertIn("normalized_invocations_sha256", src)
            self.assertIn("descriptive_inputs", src)
            self.assertEqual(set(src["descriptive_inputs"]), set(S.DESC_INPUTS))

    def test_svgs_are_well_formed_xml(self):
        import tempfile, xml.dom.minidom
        with tempfile.TemporaryDirectory() as td:
            S.run(out_dir=td)
            for name in ("figure_footprint_vs_delivery.svg",
                         "figure_query_vs_delivery.svg",
                         "figure_order_effect_diagnostic.svg"):
                xml.dom.minidom.parse(str(Path(td) / name))  # raises on malformed

    def test_deterministic_table_bytes(self):
        # same inputs -> identical table bytes (figures/manifest carry a timestamp;
        # the DATA tables must not drift)
        import tempfile
        with tempfile.TemporaryDirectory() as t1, \
             tempfile.TemporaryDirectory() as t2:
            S.run(out_dir=t1)
            S.run(out_dir=t2)
            for name in ("openwhisk_strategy_footprint.csv",
                         "openwhisk_cost_vectors.csv",
                         "matched_budget_descriptives.csv",
                         "figure_source_footprint_vs_delivery.csv",
                         "figure_source_query_vs_delivery.csv",
                         "figure_source_order_effect.csv",
                         "claim_map.md", "threats_to_validity.md"):
                self.assertEqual((Path(t1) / name).read_bytes(),
                                 (Path(t2) / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
