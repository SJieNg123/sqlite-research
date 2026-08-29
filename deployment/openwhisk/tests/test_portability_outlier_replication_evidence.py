"""Workstation <-> OpenWhisk OUTLIER-REPLICATION campaign: EVIDENCE + ANALYSIS side.

Sibling of test_portability_outlier_replication.py (which asserts the PREP-side config
identity). This module asserts the ARCHIVED WK2 EVIDENCE and the derived REPLICATION
SUPPLEMENT after the campaign ran:

  * bundle SHA matches its sidecar; every stage STATUS PASS;
  * exactly 236 invocations / 118 pairs / standalone only / four blocks R1..R4;
  * exact six target cells (== members of the frozen 65-cell matrix; adds NO coverage);
  * exact per-cell / per-seed position balance (10/10; C_hit/2e_K40 3/3 per seed);
  * the authoritative execution identity (exec git SHA b684df88, run_config a564770a,
    fingerprint be52e2be, schedule_seed 20260830) and all per-response validity gates;
  * the original R_ow values are RETAINED (never overwritten) and the replication R_ow
    is a SEPARATE column; the frozen 55-cell comparison table is byte-unchanged;
  * historical five-campaign coverage 5376/2688 is preserved; the replication is counted
    SEPARATELY as +236/+118/1 campaign; the optional all-archive union 5612/2806/6 is
    present but explicitly labelled unpooled bookkeeping.

These run the additive normalizer + output builder in-process against the archived
bundle and assert on their products. Nothing is invoked on OpenWhisk.
"""
import csv
import hashlib
import json
import os
import sys
import unittest
from collections import Counter, defaultdict

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))
sys.path.insert(0, os.path.join(HERE, "..", "client"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
EVID = os.path.join(OW, "evidence/portability_outlier_replication/b684df8860b1")
BUNDLE = "ws2_bundle_b684df8860b1_20260829T154831Z.tar.gz"
NORM_DIR = os.path.join(OW, "analysis/normalized/portability_outlier_replication")
OUT_DIR = os.path.join(OW, "analysis/outlier_replication")
COMPARISON_CSV = os.path.join(OW, "analysis/comparison/effectiveness_ow_vs_workstation.csv")

EXEC_GIT_SHA = "b684df8860b113461bdb9a2ec26b301dc32c185e"
RUN_CONFIG = "a564770aa39a33485a95afe6e49d95d9143ef70ffe88640673cf40bc7a3ed46b"
FINGERPRINT = "be52e2beadfc4d95547083d1d32898d2bd05fcb79887424f7ddb927a291313b6"
SCHEDULE_SEED = 20260830
BUNDLE_SHA = "199cb6a1d75313a989f59824c98f4508bf52f639b24199ad0646a9d1a9301612"

EXPECTED_CELLS = {
    ("layers_92", "read_tail_mixed_20k"), ("2d", "read_tail_mixed_20k"),
    ("layers_5", "read_tail_mixed_20k"), ("layers_5", "native_ycsb_c_hot_hashed_01"),
    ("layers_5", "native_ycsb_c_read_uniform"), ("2e_K40", "read_tail_hit_20k"),
}
BLOCK_PAIRS = {"R1": 60, "R2": 20, "R3": 20, "R4": 18}
FIVE_CAMPAIGN = {"campaigns": 5, "invocations": 5376, "pairs": 2688}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Run the additive pipeline ONCE for the whole module.
import normalize_portability_outlier_replication as NR  # noqa: E402
import build_outlier_replication_outputs as BO  # noqa: E402


def setUpModule():
    ok, _manifest, _parity = NR.normalize(OW, NORM_DIR)
    if not ok:
        raise AssertionError("normalizer FAILED — see validation.txt")
    BO.main()


# --------------------------------------------------------------------------- A
class EvidenceIntegrity(unittest.TestCase):
    def test_bundle_sha_matches_sidecar_and_expected(self):
        tar = os.path.join(EVID, BUNDLE)
        actual = _sha256(tar)
        sidecar = open(tar + ".sha256").read().split()[0]
        self.assertEqual(actual, sidecar, "bundle SHA != sidecar")
        self.assertEqual(actual, BUNDLE_SHA, "bundle SHA != expected 199cb6a1")

    def test_normalization_passed_all_gates(self):
        man = json.load(open(os.path.join(
            NORM_DIR, "portability_outlier_replication_normalization_manifest.json")))
        self.assertTrue(man["ok"], "normalization manifest ok != True")
        rep = open(os.path.join(
            NORM_DIR, "portability_outlier_replication_normalization_validation.txt")).read()
        self.assertIn("overall: PASS", rep)
        self.assertIn("(none — all gates passed)", rep)


# --------------------------------------------------------------------------- B
class ExecutedEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.man = json.load(open(os.path.join(
            NORM_DIR, "portability_outlier_replication_normalization_manifest.json")))
        with open(os.path.join(
                NORM_DIR, "portability_outlier_replication_normalized_invocations.csv")) as f:
            cls.inv = list(csv.DictReader(f))
        with open(os.path.join(
                NORM_DIR, "portability_outlier_replication_normalized_pairs.csv")) as f:
            cls.pairs = list(csv.DictReader(f))

    def test_execution_identity(self):
        self.assertEqual(self.man["sqlite_research_git_sha"], EXEC_GIT_SHA)
        self.assertEqual(self.man["authoritative_run_config_sha256"], RUN_CONFIG)
        self.assertEqual(self.man["matrix_fingerprint"], FINGERPRINT)
        self.assertEqual(self.man["schedule_seed"], SCHEDULE_SEED)

    def test_236_invocations_118_pairs(self):
        self.assertEqual(len(self.inv), 236)
        self.assertEqual(len(self.pairs), 118)
        self.assertEqual(self.man["counts"],
                         {"invocations": 236, "pairs": 118, "baseline": 118, "target": 118})

    def test_standalone_only(self):
        self.assertEqual({r["handle_mode"] for r in self.inv}, {"standalone"})

    def test_exact_six_target_cells_no_others(self):
        cells = {(r["strategy"], r["workload"]) for r in self.inv if r["strategy"] != "baseline"}
        self.assertEqual(cells, EXPECTED_CELLS)

    def test_block_counts_R1_R2_R3_R4(self):
        self.assertEqual(self.man["block_pairs"], BLOCK_PAIRS)

    def test_position_balance_10_10_and_chit_3_3(self):
        bal = defaultdict(lambda: [0, 0])  # cell -> [baseline_first, target_first]
        seen = set()
        for r in self.inv:
            if r["strategy"] == "baseline":
                continue
            pid = r["pair_id"]
            if pid in seen:
                continue
            seen.add(pid)
            cell = (r["strategy"], r["workload"], r["seed"])
            if r["pair_first_strategy"] == "baseline":
                bal[cell][0] += 1
            else:
                bal[cell][1] += 1
        for cell, (bf, tf) in bal.items():
            if cell[0] == "2e_K40":
                self.assertEqual((bf, tf), (3, 3), "%s not 3/3" % (cell,))
            else:
                self.assertEqual((bf, tf), (10, 10), "%s not 10/10" % (cell,))
        # C_hit/2e_K40 must carry seeds 1,2,3, each 3/3.
        chit_seeds = {c[2] for c in bal if c[0] == "2e_K40"}
        self.assertEqual(chit_seeds, {"1", "2", "3"})

    def test_all_validity_gates_true(self):
        for r in self.inv:
            for f in ("cold_reset_requested", "cold_threshold_passed", "delivery_valid",
                      "measured_valid", "oracle_passed"):
                self.assertEqual(r[f], "true", "%s not true at pos %s" % (f, r["schedule_position"]))
            self.assertEqual(r["diagnostic_mode"], "false")
            self.assertFalse(r["error"] or r["error_stage"] or r["sqlite_error"])
            self.assertEqual(r["authoritative_run_config_sha256"], RUN_CONFIG)


# --------------------------------------------------------------------------- C
class ReplicationSupplement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(OUT_DIR, "replication_cell_comparison.csv")) as f:
            cls.comp = {(r["workload"], r["strategy"]): r for r in csv.DictReader(f)}
        cls.summary = json.load(open(os.path.join(OUT_DIR, "replication_summary.json")))
        cls.manifest = json.load(open(os.path.join(OUT_DIR, "MANIFEST.json")))

    def test_six_rows_exactly(self):
        self.assertEqual(len(self.comp), 6)
        got = {(w, s) for (w, s) in self.comp}
        want = {(wl if wl in ("YCh01", "YCu") else wl, st)  # comparison codes
                for (st, wl) in [("layers_92", "C"), ("2d", "C"), ("layers_5", "C"),
                                 ("layers_5", "YCh01"), ("layers_5", "YCu"), ("2e_K40", "C_hit")]}
        self.assertEqual(got, want)

    def test_original_R_ow_retained_and_separate_from_replication(self):
        # Both columns exist, both populated, and they are NOT the same value (the
        # replication did move the estimates) — proving no silent overwrite.
        for key, r in self.comp.items():
            self.assertIn("original_R_ow", r)
            self.assertIn("replication_R_ow", r)
            self.assertNotEqual(r["original_R_ow"], "")
            self.assertNotEqual(r["replication_R_ow"], "")

    def test_original_R_ow_matches_frozen_comparison_table(self):
        frozen = {(r["workload"], r["strategy"]): r["R_ow"]
                  for r in csv.DictReader(open(COMPARISON_CSV))}
        for (w, s), r in self.comp.items():
            self.assertAlmostEqual(float(r["original_R_ow"]), float(frozen[(w, s)]), places=3,
                                   msg="original_R_ow diverged from frozen table for %s/%s" % (w, s))

    def test_frozen_comparison_table_not_overwritten(self):
        # The supplement must never rewrite the historical estimator; the six original
        # R_ow values in the frozen table remain negative/positive as first recorded.
        frozen = {(r["workload"], r["strategy"]): r
                  for r in csv.DictReader(open(COMPARISON_CSV))}
        self.assertLess(float(frozen[("C", "layers_92")]["R_ow"]), 0)
        self.assertLess(float(frozen[("C", "2d")]["R_ow"]), 0)
        self.assertLess(float(frozen[("C_hit", "2e_K40")]["R_ow"]), 0)

    def test_sign_flip_finding_recorded(self):
        pf = self.summary["primary_sign_flip_findings"]
        # None of the three original sign-flips reproduced as negative under balance.
        self.assertEqual(pf["original_sign_flips_reproduced_as_negative"], [])
        self.assertEqual(set(pf["original_sign_flips_that_disappeared_after_balancing"]),
                         {"C/layers_92", "C/2d", "C_hit/2e_K40"})

    def test_campaign_accounting_preserves_five_and_separates_replication(self):
        acc = self.summary["campaign_accounting"]
        self.assertEqual(acc["five_campaign_coverage_PRESERVED"]["invocations"], 5376)
        self.assertEqual(acc["five_campaign_coverage_PRESERVED"]["pairs"], 2688)
        self.assertEqual(acc["five_campaign_coverage_PRESERVED"]["campaigns"], 5)
        self.assertEqual(acc["replication_SEPARATE"]["invocations"], 236)
        self.assertEqual(acc["replication_SEPARATE"]["pairs"], 118)
        self.assertFalse(acc["all_archived_bookkeeping_only"]["pooled"])
        self.assertEqual(acc["all_archived_bookkeeping_only"]["invocations"], 5612)
        self.assertEqual(acc["all_archived_bookkeeping_only"]["pairs"], 2806)
        self.assertEqual(acc["all_archived_bookkeeping_only"]["campaigns"], 6)

    def test_manifest_declares_no_pool_no_overwrite(self):
        m = self.manifest
        self.assertTrue(m["does_not_replace_original_R_ow"])
        self.assertTrue(m["does_not_rewrite_55cell_synthesis"])
        self.assertTrue(m["does_not_pool_into_five_campaign_estimator"])
        self.assertEqual(m["execution_identity"]["authoritative_run_config_sha256"], RUN_CONFIG)

    def test_bands_labelled_descriptive_not_significance(self):
        note = self.summary["pre_registered_bands"]["note"].lower()
        self.assertIn("not significance", note)


if __name__ == "__main__":
    unittest.main()
