"""Effectiveness-portability COMPARISON layer (the 65-cell workstation-coverage matrix).

This guards the ANALYSIS-INTEGRATION output of the portability_ext + portability_full_
closure campaigns, i.e. the comparison the fourth and fifth OpenWhisk campaigns were run
to enable: for every (workload, strategy) cell that BOTH the workstation and OpenWhisk
measured, is the strategy's RELATIVE first-query reduction R = (baseline_fq -
strategy_fq)/baseline_fq consistent across the two platforms?

Why these assertions (Rule 9 -- tests verify intent, not just shape):

  * The thesis claim is DESCRIPTIVE cross-platform CONSISTENCY, not causal equivalence:
    "strategies effective on the workstation stay effective on OpenWhisk." The load-
    bearing fact is that strong strategies port (38/41) and the exceptions are known
    low-confidence single-instance flips (C/2d, C/layers_92) plus one position-
    imbalanced cell (C_hit/2e_K40) -- NOT equal absolute latency, equal effect size, or
    reproduced ranking. If a future regeneration silently drops a strong cell's OW
    effectiveness beyond those flagged exceptions, this test must fail.
  * The first-query table resolves to EXACTLY 55 cells (the mechanical intersection of
    OW-standalone first-query cells and same-cell workstation measurements); the 10 lp
    delivery-order cells go to a SEPARATE summary (compared on deliver_us, not first_
    query) and 55 + 10 = 65 is the full matched-cell union. The 4 OW-only YC cells
    (2f_top102 / learned_markov_102 / leaf_freq_K10 / leaf_rand_K10) are excluded
    because they were never run head-to-head on the workstation. A drift off 55 means
    the intersection logic changed and the campaign framing is stale.
  * Every cell's R uses a STRICT same-batch baseline (strategy value and its no-prefetch
    baseline from the SAME file + db group + seed/fold). If same_batch is ever False,
    the R is contaminated by cross-batch machine-state drift and is not comparable.
  * The comparison is RELATIVE-only: the artifact carries R_ws / R_ow, never absolute
    microseconds -- absolute latency is not cross-machine comparable and asserting on it
    would be the causal-equivalence claim the thesis explicitly disclaims.

These read the frozen committed artifacts produced by compare_effectiveness.py; the
Spearman split is recomputed with the same module's own estimator so the test tracks the
real logic, not a copied constant.
"""
import csv
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))
import compare_effectiveness as C  # noqa: E402

COMP_DIR = os.path.join(HERE, "..", "analysis", "comparison")
EFF_CSV = os.path.join(COMP_DIR, "effectiveness_ow_vs_workstation.csv")
PROV_CSV = os.path.join(COMP_DIR, "ws_provenance.csv")

# The 4 OpenWhisk-standalone cells with no workstation head-to-head measurement.
OW_ONLY = {("YC", "2f_top102"), ("YC", "learned_markov_102"),
           ("YC", "leaf_freq_K10"), ("YC", "leaf_rand_K10")}


def _rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class TestEffectivenessComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eff = _rows(EFF_CSV)
        cls.prov = _rows(PROV_CSV)

    def test_resolves_to_exactly_55_first_query_cells(self):
        # The mechanical intersection target for the first-query table (lp's 10 cells
        # are compared separately on deliver_us). Not hard-coded in the generator;
        # asserted here so any drift off 55 fails loud rather than silently re-scoping.
        self.assertEqual(len(self.eff), 55)

    def test_per_workload_coverage(self):
        counts = {}
        for r in self.eff:
            counts[r["workload"]] = counts.get(r["workload"], 0) + 1
        self.assertEqual(counts, {"YC": 10, "YCu": 10, "YCh01": 10, "C": 14, "C_hit": 11})

    def test_ow_only_cells_are_excluded(self):
        present = {(r["workload"], r["strategy"]) for r in self.eff}
        self.assertEqual(OW_ONLY & present, set(),
                         "OW-only cells (no workstation head-to-head) must not appear")

    def test_every_cell_uses_a_strict_same_batch_baseline(self):
        # Contaminated (cross-batch) R would not be cross-platform comparable.
        self.assertEqual(len(self.prov), 55)
        self.assertTrue(all(r["same_batch"] == "True" for r in self.prov))

    def test_strong_strategies_port(self):
        # The load-bearing descriptive claim: workstation-strong strategies stay
        # effective on OpenWhisk. 38/41; the 3 exceptions are two low-confidence
        # single-instance flips (C/2d, C/layers_92) and one position-imbalanced cell
        # (C_hit/2e_K40) -- all surfaced, none silently dropped.
        strong = [r for r in self.eff if float(r["R_ws"]) >= 0.30]
        self.assertEqual(len(strong), 41)
        eff_ow = [r for r in strong if r["cat_ow"] == "effective"]
        self.assertEqual(len(eff_ow), 38)
        exceptions = sorted((r["workload"], r["strategy"]) for r in strong
                            if r["cat_ow"] != "effective")
        self.assertEqual(exceptions,
                         [("C", "2d"), ("C", "layers_92"), ("C_hit", "2e_K40")])

    def test_direction_agreement_is_42_of_55(self):
        self.assertEqual(sum(r["sign_agree"] == "True" for r in self.eff), 42)

    def test_spearman_all_and_high_conf(self):
        # Recompute with the module's own estimator so the test moves with the code.
        allc = [(float(r["R_ws"]), float(r["R_ow"])) for r in self.eff]
        hi = [(float(r["R_ws"]), float(r["R_ow"])) for r in self.eff
              if r["low_conf"] == "False"]
        self.assertEqual(len(hi), 41)  # 55 - 14 low_conf
        rho_all = C.spearman([a for a, _ in allc], [b for _, b in allc])
        rho_hi = C.spearman([a for a, _ in hi], [b for _, b in hi])
        self.assertAlmostEqual(rho_all, 0.67, places=2)
        self.assertAlmostEqual(rho_hi, 0.75, places=2)

    def test_comparison_is_relative_only_not_absolute_latency(self):
        # Descriptive-not-causal boundary: the artifact must carry relative reductions,
        # never absolute microseconds (which are not cross-machine comparable).
        header = self.eff[0].keys()
        self.assertIn("R_ws", header)
        self.assertIn("R_ow", header)
        for col in header:
            self.assertNotIn("_us", col.lower())
            self.assertNotIn("absolute", col.lower())

    def test_artifacts_have_lf_line_endings(self):
        # Guards the CRLF regression: git diff --check must stay clean.
        for path in (EFF_CSV, PROV_CSV):
            with open(path, "rb") as f:
                self.assertNotIn(b"\r", f.read(), f"{path} has CR bytes")


LP_CSV = os.path.join(COMP_DIR, "lp_delivery_order.csv")


class TestLpDeliveryOrderSeparation(unittest.TestCase):
    """The libprefetch (lp) cells are NOT in the first-query table: they are compared on
    delivery ORDER (deliver_us), because both arms deliver the same page set and the
    post-delivery first-query is warm for both. This guards the §4/§7 boundary -- lp's 10
    cells (5 workloads x {sorted, shuf}) live in a SEPARATE delivery-order summary, and
    55 (first-query) + 10 (lp) = 65 is the full matched-cell union. The mechanism ports:
    shuffled delivery is slower than sorted on BOTH platforms (order_ratio > 1), while
    first-query stays within a few microseconds (the control)."""

    @classmethod
    def setUpClass(cls):
        cls.lp = _rows(LP_CSV)

    def test_lp_cells_absent_from_first_query_table(self):
        fq = {(r["workload"], r["strategy"]) for r in _rows(EFF_CSV)}
        for wl in ("YC", "YCu", "YCh01", "C", "C_hit"):
            for strat in ("lp_sorted", "lp_shuf"):
                self.assertNotIn((wl, strat), fq,
                                 "lp cells must be compared on deliver_us, not first_query")

    def test_five_workloads_ten_lp_cells_sum_to_65(self):
        # one delivery-order row per workload (each row folds the sorted+shuf pair)
        self.assertEqual(len(self.lp), 5)
        lp_cells = 2 * len(self.lp)            # sorted + shuf per workload
        self.assertEqual(len(_rows(EFF_CSV)) + lp_cells, 65)

    def test_shuffle_slower_on_both_platforms(self):
        # mechanism portability: order matters, and it matters the same direction on both
        for r in self.lp:
            self.assertGreater(float(r["ow_order_ratio_shuf_over_sorted"]), 1.0)
            self.assertGreater(float(r["ws_order_ratio_shuf_over_sorted"]), 1.0)
            self.assertEqual(r["order_ratio_agreement"], "both>1")

    def test_first_query_is_the_control_not_the_lever(self):
        # post-delivery first-query stays within a few microseconds between arms:
        # lp's effect is delivery order, NOT first-query.
        for r in self.lp:
            self.assertLess(abs(float(r["ow_first_query_delta_us"])), 5.0)

    def test_artifact_has_lf_line_endings(self):
        with open(LP_CSV, "rb") as f:
            self.assertNotIn(b"\r", f.read(), "lp_delivery_order.csv has CR bytes")


if __name__ == "__main__":
    unittest.main()
