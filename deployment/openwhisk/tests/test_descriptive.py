#!/usr/bin/env python3
"""Tests for the WK1 descriptive analysis layer (analysis/descriptive.py).

These assert the SAFETY invariants the layer exists to enforce -- target-specific
baseline grouping (no pooling), order-position grouping, first-arm diagnostic
filtering, cost-vector dimensionality, matched-budget metadata, deterministic
ordering, warning flags, and fail-closed gates -- NOT any performance claim.
"""
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_OW_ROOT / "analysis"))
import descriptive as D                            # noqa: E402


def make_inv_row(strategy, paired_target, handle_mode, seed, pos_in_pair,
                 campaign="primary", rc=None, fq=100.0, page=102, interior=92,
                 leaf=10, **over):
    rc = rc or ("022f" if campaign == "primary" else "4416")
    r = {"campaign": campaign, "strategy": strategy,
         "paired_target_strategy": paired_target, "handle_mode": handle_mode,
         "seed": str(seed), "position_within_pair": pos_in_pair,
         "schedule_position": 1, "measured_valid": "true",
         "authoritative_run_config_sha256": rc,
         "selected_page_count": page, "selected_interior_count": interior,
         "selected_leaf_count": leaf, "selected_bytes": page * 4096}
    for tf in D.TIMING_FIELDS:
        r[tf] = fq if tf == "first_query_us" else 1.0
        r[tf + "_f"] = D._f(r[tf])
    r.update(over)
    return r


class TestBaselineGrouping(unittest.TestCase):
    def test_baseline_context_is_target_specific(self):
        # two baseline rows paired to DIFFERENT targets must NOT be pooled
        inv = [
            make_inv_row("baseline", "2d", "warm", 1, 2, fq=10.0),
            make_inv_row("baseline", "2e_K10", "warm", 1, 2, fq=99.0),
        ]
        rows = D.build_baseline_context(inv)
        keys = {(r["paired_target_strategy"], r["n"], r["first_query_us_median"]) for r in rows}
        self.assertIn(("2d", 1, 10.0), keys)
        self.assertIn(("2e_K10", 1, 99.0), keys)
        # never a single pooled baseline group
        self.assertEqual(len(rows), 2)

    def test_no_baseline_pooling_across_targets(self):
        # if pooling happened, one group would hold n=2; assert every group n==1
        inv = [
            make_inv_row("baseline", "2d", "warm", 1, 2),
            make_inv_row("baseline", "2e_K10", "warm", 1, 2),
        ]
        rows = D.build_baseline_context(inv)
        self.assertTrue(all(r["n"] == 1 for r in rows))

    def test_run_config_mix_within_baseline_group_raises(self):
        # a group whose rows disagree on run_config identity must fail closed
        with self.assertRaises(D.GateError):
            D._single_run_config([make_inv_row("baseline", "2d", "warm", 1, 2, rc="022f"),
                                  make_inv_row("baseline", "2d", "warm", 1, 2, rc="4416")],
                                 "ctx")


class TestOrderAndDiagnostic(unittest.TestCase):
    def test_order_position_retains_second_arm(self):
        inv = [
            make_inv_row("2d", "2d", "warm", 1, 1, fq=1.0),
            make_inv_row("2d", "2d", "warm", 1, 2, fq=2.0),   # second position
            make_inv_row("baseline", "2d", "warm", 1, 1, fq=3.0),
            make_inv_row("baseline", "2d", "warm", 1, 2, fq=4.0),
        ]
        rows = D.build_order_position_descriptives(inv)
        # all four role x position groups present -> second-position not dropped
        groups = {(r["role"], r["position_within_pair"]) for r in rows}
        self.assertEqual(groups, {("target", 1), ("target", 2),
                                  ("baseline", 1), ("baseline", 2)})

    def test_first_arm_diagnostic_filters_position_1_only(self):
        inv = [
            make_inv_row("2d", "2d", "warm", 1, 1, fq=1.0),
            make_inv_row("2d", "2d", "warm", 1, 2, fq=999.0),   # excluded
            make_inv_row("baseline", "2d", "warm", 1, 1, fq=3.0),
        ]
        rows = D.build_first_arm_diagnostic(inv)
        # only position 1 observations counted; the 999.0 (pos 2) must be absent
        for r in rows:
            self.assertNotEqual(r["first_query_us_median"], 999.0)
        self.assertTrue(all(r["view"] == "first_arm_diagnostic" for r in rows))
        # target group has n==1 (only the pos-1 target row)
        tgt = [r for r in rows if r["role"] == "target"][0]
        self.assertEqual(tgt["n"], 1)

    def test_order_audit_counts(self):
        pairs = [
            {"campaign": "primary", "paired_target_strategy": "2d",
             "handle_mode": "warm", "first_strategy": "baseline"},
            {"campaign": "primary", "paired_target_strategy": "2d",
             "handle_mode": "warm", "first_strategy": "2d"},
        ]
        rows = D.build_order_audit(pairs)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n_pairs"], 2)
        self.assertEqual(rows[0]["baseline_first_count"], 1)
        self.assertEqual(rows[0]["target_first_count"], 1)


class TestCostVectorAndMetadata(unittest.TestCase):
    def test_cost_vector_keeps_separate_dimensions(self):
        inv = [make_inv_row("2e_K10", "2e_K10", "warm", 1, 1)]
        rows = D.build_cost_vectors(inv)
        r = rows[0]
        for dim in ("selected_page_count", "selected_bytes",
                    "selected_interior_count", "selected_leaf_count",
                    "median_select_us", "median_deliver_us",
                    "median_first_query_us", "median_open_us",
                    "median_handler_total_us"):
            self.assertIn(dim, r)
        # no universal 'score' / 'rank' column is emitted
        self.assertNotIn("score", r)
        self.assertNotIn("rank", r)
        self.assertNotIn("speedup", r)

    def test_offline_generation_not_charged_per_invocation(self):
        # learned_markov is offline/LOSO; cost vector must expose plan_generation
        # and must NOT invent a training-cost column
        inv = [make_inv_row("learned_markov_102", "learned_markov_102", "warm", 1, 1,
                            campaign="secondary", interior=51, leaf=51)]
        rows = D.build_cost_vectors(inv)
        r = rows[0]
        self.assertIn("offline", r["plan_generation"])
        self.assertFalse(any("train" in k.lower() for k in r))

    def test_matched_budget_metadata(self):
        g = D.COMPARISON_GROUPS
        self.assertEqual(g["N_YC"], 102)
        self.assertEqual(set(g["groups"]["A_matched_total_budget_102"]["members"]),
                         {"2f_top102", "learned_markov_102"})
        self.assertEqual(set(g["groups"]["B_leaf_only_controls_10"]["members"]),
                         {"leaf_freq_K10", "leaf_rand_K10"})
        # 2f_slru is intentionally NOT forced into a group
        self.assertIn("2f_slru", g["ungrouped"])

    def test_emergent_split_recorded_for_ranked_strategies(self):
        for s in ("2f_top102", "learned_markov_102"):
            self.assertIn("emergent", D.STRATEGY_METADATA[s]["interior_leaf_split"])


class TestFailClosed(unittest.TestCase):
    def _base_data(self):
        """Load the real normalized inputs once for mutation tests."""
        return D.load_inputs(D._NORM_DIR)

    def test_unknown_strategy_fails_closed(self):
        data = self._base_data()
        data["inv_rows"][0]["strategy"] = "totally_unknown"
        problems, _ = D.validate_source(data)
        self.assertTrue(any("unknown strategy" in p for p in problems))

    def test_selected_page_invariant_failure(self):
        data = self._base_data()
        # break a constant-footprint strategy (2e_K10 must be 102 everywhere)
        for r in data["inv_rows"]:
            if r["strategy"] == "2e_K10":
                r["selected_page_count"] = 999
                break
        problems, _ = D.validate_source(data)
        self.assertTrue(any("constant selected_page_count" in p for p in problems))

    def test_baseline_missing_paired_target_fails(self):
        data = self._base_data()
        for r in data["inv_rows"]:
            if r["strategy"] == "baseline":
                r["paired_target_strategy"] = ""
                break
        problems, _ = D.validate_source(data)
        self.assertTrue(any("paired_target_strategy" in p for p in problems))

    def test_missing_position_fails(self):
        data = self._base_data()
        data["inv_rows"][0]["position_within_pair"] = None
        problems, _ = D.validate_source(data)
        self.assertTrue(any("missing position_within_pair" in p for p in problems))

    def test_run_config_mix_within_group_raises(self):
        rows = [make_inv_row("2d", "2d", "warm", 1, 1, rc="AAAA"),
                make_inv_row("2d", "2d", "warm", 1, 1, rc="BBBB")]
        with self.assertRaises(D.GateError):
            D.build_strategy_descriptives(rows)


class TestGeneratedOutputs(unittest.TestCase):
    OUT = _OW_ROOT / "analysis" / "descriptive"

    @unittest.skipUnless((_OW_ROOT / "analysis" / "descriptive" /
                          "analysis_manifest.json").exists(),
                         "run analysis/descriptive.py first")
    def test_warning_flags_present_and_true(self):
        man = json.loads((self.OUT / "analysis_manifest.json").read_text())
        w = man["methodological_warnings"]
        self.assertTrue(w["no_naive_warm_paired_headline"])
        self.assertTrue(w["order_effect_present"])
        self.assertFalse(w["exact_order_effect_source_resolved"])
        self.assertTrue(w["first_arm_view_is_diagnostic_only"])
        self.assertTrue(w["openwhisk_not_primary_native_performance_evidence"])

    def test_deterministic_ordering_and_bytes(self):
        import tempfile
        import descriptive as DD
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            ok1, m1 = DD.run(DD._NORM_DIR, t1)
            ok2, m2 = DD.run(DD._NORM_DIR, t2)
            self.assertTrue(ok1 and ok2)
            self.assertEqual(m1["outputs"], m2["outputs"])

    def test_full_run_passes_gates(self):
        import tempfile
        import descriptive as DD
        with tempfile.TemporaryDirectory() as t:
            ok, m = DD.run(DD._NORM_DIR, t)
            self.assertTrue(ok, "descriptive layer should pass on real evidence")
            self.assertEqual(m["group_counts"]["strategy_descriptives.csv"], 18)


if __name__ == "__main__":
    unittest.main()
