"""Effectiveness-portability COMPARISON layer (the 49-cell workstation-coverage matrix).

This guards the ANALYSIS-INTEGRATION output of the portability_ext campaign, i.e. the
comparison the fourth OpenWhisk campaign was run to enable: for every (workload,
strategy) cell that BOTH the workstation and OpenWhisk measured, is the strategy's
RELATIVE first-query reduction R = (baseline_fq - strategy_fq)/baseline_fq consistent
across the two platforms?

Why these assertions (Rule 9 -- tests verify intent, not just shape):

  * The thesis claim is DESCRIPTIVE cross-platform CONSISTENCY, not causal equivalence:
    "strategies effective on the workstation stay effective on OpenWhisk." The load-
    bearing fact is that strong strategies port (34/35) and the sole exception is a
    known position-confounded low-n static cell (C/2d) -- NOT equal absolute latency,
    equal effect size, or reproduced ranking. If a future regeneration silently drops
    a strong cell's OW effectiveness, this test must fail.
  * The count must resolve to EXACTLY 49 (the mechanical intersection of OW-standalone
    cells and same-cell workstation measurements), with the 4 OW-only YC cells
    (2f_top102 / learned_markov_102 / leaf_freq_K10 / leaf_rand_K10) excluded because
    they were never run head-to-head on the workstation. A drift off 49 means the
    intersection logic changed and the campaign framing is stale.
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

    def test_resolves_to_exactly_49_cells(self):
        # The mechanical intersection target. Not hard-coded in the generator; asserted
        # here so any drift off 49 fails loud rather than silently re-scoping the claim.
        self.assertEqual(len(self.eff), 49)

    def test_per_workload_coverage(self):
        counts = {}
        for r in self.eff:
            counts[r["workload"]] = counts.get(r["workload"], 0) + 1
        self.assertEqual(counts, {"YC": 10, "YCu": 10, "YCh01": 10, "C": 10, "C_hit": 9})

    def test_ow_only_cells_are_excluded(self):
        present = {(r["workload"], r["strategy"]) for r in self.eff}
        self.assertEqual(OW_ONLY & present, set(),
                         "OW-only cells (no workstation head-to-head) must not appear")

    def test_every_cell_uses_a_strict_same_batch_baseline(self):
        # Contaminated (cross-batch) R would not be cross-platform comparable.
        self.assertEqual(len(self.prov), 49)
        self.assertTrue(all(r["same_batch"] == "True" for r in self.prov))

    def test_strong_strategies_port(self):
        # The load-bearing descriptive claim: workstation-strong strategies stay
        # effective on OpenWhisk. 34/35, sole exception the confounded C/2d static cell.
        strong = [r for r in self.eff if float(r["R_ws"]) >= 0.30]
        self.assertEqual(len(strong), 35)
        eff_ow = [r for r in strong if r["cat_ow"] == "effective"]
        self.assertEqual(len(eff_ow), 34)
        exceptions = [(r["workload"], r["strategy"]) for r in strong
                      if r["cat_ow"] != "effective"]
        self.assertEqual(exceptions, [("C", "2d")])

    def test_direction_agreement_is_38_of_49(self):
        self.assertEqual(sum(r["sign_agree"] == "True" for r in self.eff), 38)

    def test_spearman_all_and_high_conf(self):
        # Recompute with the module's own estimator so the test moves with the code.
        allc = [(float(r["R_ws"]), float(r["R_ow"])) for r in self.eff]
        hi = [(float(r["R_ws"]), float(r["R_ow"])) for r in self.eff
              if r["low_conf"] == "False"]
        self.assertEqual(len(hi), 38)  # 49 - 11 low_conf
        rho_all = C.spearman([a for a, _ in allc], [b for _, b in allc])
        rho_hi = C.spearman([a for a, _ in hi], [b for _, b in hi])
        self.assertAlmostEqual(rho_all, 0.69, places=2)
        self.assertAlmostEqual(rho_hi, 0.78, places=2)

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


if __name__ == "__main__":
    unittest.main()
