"""Workstation <-> OpenWhisk YCH01 TWO-CELL FOLLOW-UP: EVIDENCE + ANALYSIS audit (SEVENTH).

Evidence/analysis side of the portability_ych01_followup campaign (7a3cc45d..., execution git
26500fe8fe57). Complements the prep-side test_portability_ych01_followup.py (structural gates,
identity freeze). These tests run the additive normalizer + output builder in-process against
the ARCHIVED bundle and assert the fail-closed audit contract:

  * bundle SHA == sidecar == expected 77e30869; execution git sha / run_config / schedule_seed;
  * exactly 144 invocations / 72 pairs; the EXACT two target cells (YCh01/layers_5,
    YCh01/2f_top14) and no others; YCh01 only; standalone only;
  * layers_5 = 36 pairs = 18/18; 2f_top14 = 36 pairs, seeds 1/2/3 = 12 each = 6/6 each;
  * 2f_top14 reuses the frozen portability_ext keyed plan identity 6bc163bd... byte-identically
    (seed-invariant); layers_5 is the committed structural-static 5-page plan;
  * the SEVENTH R_ow results are ADDITIVE ONLY: the frozen 55-cell primary comparison is
    untouched (YCh01/layers_5 R_ow stays +0.3766, YCh01/2f_top14 stays -0.0190) and the SIXTH
    outlier-replication supplement is untouched (YCh01/layers_5 balanced R_ow stays -0.2425);
  * coverage stays 65/65 (this campaign adds 0 coverage cells); the all-archive bookkeeping
    5756/2878 is explicitly NOT one pooled estimator.

The seventh R_ow is a NEW measurement reported side by side, never replacing any prior value.
The observed direction is described only as a pair-position / short-lived execution-state /
execution-storage-state effect; -0.019 is near zero, not strongly harmful.
"""
import csv
import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
EVID = os.path.join(OW, "evidence/portability_ych01_followup/26500fe8fe57")
BUNDLE = "ws2_bundle_26500fe8fe57_20260829T200658Z.tar.gz"
BUNDLE_SHA = "77e30869c7ac4d3b75c99174f9c2091320c51c7f8476580c43ddfdc5f0015925"
EXEC_GIT_SHA = "26500fe8fe5710d51b6525234dd6d736765072bb"
RUN_CONFIG = "7a3cc45d7fac26e90315b3e16cec320c48210da475d42819b8253ec53ab60437"
SCHEDULE_SEED = 20260901
FINGERPRINT = "47aab3200fbcdc3a31f5ef43a85af7a26c18385e2961ad0e9c21ee1fe8450794"
FROZEN_2F_PLAN_SHA = "6bc163bdc37961faaced818a72cf90f8eb214f319c881d7bcdb2bab3f1d991b2"

YCH01 = "native_ycsb_c_hot_hashed_01"
NORM_DIR = os.path.join(OW, "analysis/normalized/portability_ych01_followup")
NORM_PAIRS = os.path.join(NORM_DIR, "portability_ych01_followup_normalized_pairs.csv")
NORM_INV = os.path.join(NORM_DIR, "portability_ych01_followup_normalized_invocations.csv")
NORM_MANIFEST = os.path.join(NORM_DIR, "portability_ych01_followup_normalization_manifest.json")
OUT_DIR = os.path.join(OW, "analysis/ych01_followup")
FROZEN_COMPARISON = os.path.join(OW, "analysis/comparison/effectiveness_ow_vs_workstation.csv")
SIXTH_POS = os.path.join(OW, "analysis/outlier_replication/replication_position_diagnostics.csv")

import normalize_portability_ych01_followup as NR  # noqa: E402
import build_ych01_followup_outputs as BY  # noqa: E402

_STATE = {}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def setUpModule():
    ok, manifest, parity = NR.normalize(OW, NORM_DIR)
    if not ok:
        raise AssertionError("seventh-campaign normalizer FAILED — see validation.txt")
    summary, build_manifest = BY.main()
    _STATE["norm_manifest"] = manifest
    _STATE["plan_parity"] = parity
    _STATE["summary"] = summary
    _STATE["build_manifest"] = build_manifest


def _read_pairs():
    with open(NORM_PAIRS) as f:
        return [r for r in csv.DictReader(f)]


def _frozen_row(strategy):
    for r in csv.DictReader(open(FROZEN_COMPARISON)):
        if r["workload"] == "YCh01" and r["strategy"] == strategy:
            return r
    return None


# --------------------------------------------------------------------------- A
class EvidenceIntegrity(unittest.TestCase):
    def test_bundle_sha_matches_sidecar_and_expected(self):
        tar = os.path.join(EVID, BUNDLE)
        actual = _sha256(tar)
        sidecar = open(tar + ".sha256").read().split()[0]
        self.assertEqual(actual, sidecar, "bundle SHA != sidecar")
        self.assertEqual(actual, BUNDLE_SHA, "bundle SHA != expected 77e30869")

    def test_normalization_passed_all_gates(self):
        man = json.load(open(NORM_MANIFEST))
        self.assertTrue(man["ok"], "normalization manifest ok != True")
        rep = open(os.path.join(
            NORM_DIR, "portability_ych01_followup_normalization_validation.txt")).read()
        self.assertIn("overall: PASS", rep)
        self.assertIn("(none — all gates passed)", rep)

    def test_execution_identity(self):
        man = _STATE["norm_manifest"]
        self.assertEqual(man["sqlite_research_git_sha"], EXEC_GIT_SHA)
        self.assertEqual(man["authoritative_run_config_sha256"], RUN_CONFIG)
        self.assertEqual(man["schedule_seed"], SCHEDULE_SEED)
        self.assertEqual(man["matrix_fingerprint"], FINGERPRINT)
        self.assertEqual(man["matrix_fingerprint_recomputed"], FINGERPRINT)

    def test_stale_primary_bundle_manifest_quirk_is_documented_not_authoritative(self):
        # The known 06_collect packaging quirk: bundle_manifest summarizes pin PRIMARY 022fbeb0.
        # It must NOT be treated as the authoritative identity (which is the stamped 7a3cc45d).
        man = _STATE["norm_manifest"]
        self.assertTrue(man["bundle_manifest_run_config_sha256"].startswith("022fbeb0"))
        self.assertEqual(man["authoritative_run_config_sha256"], RUN_CONFIG)


# --------------------------------------------------------------------------- B
class CountsCellsBalance(unittest.TestCase):
    def test_exactly_144_invocations_72_pairs(self):
        man = _STATE["norm_manifest"]
        self.assertEqual(man["counts"]["invocations"], 144)
        self.assertEqual(man["counts"]["pairs"], 72)
        self.assertEqual(man["counts"]["baseline"], 72)
        self.assertEqual(man["counts"]["target"], 72)

    def test_exactly_two_target_cells_ych01_only(self):
        pairs = _read_pairs()
        cells = {(r["paired_target_strategy"], r["workload"]) for r in pairs}
        self.assertEqual(cells, {("layers_5", YCH01), ("2f_top14", YCH01)},
                         "target cells must be EXACTLY the two YCh01 cells")
        self.assertEqual({r["workload"] for r in pairs}, {YCH01}, "YCh01 workload only")

    def test_standalone_only(self):
        self.assertEqual({r["handle_mode"] for r in _read_pairs()}, {"standalone"})

    def test_layers5_36_pairs_18_18(self):
        bal = _STATE["norm_manifest"]["position_balance"]
        key = "layers_5/%s/1" % YCH01
        self.assertEqual(bal[key], {"baseline_first": 18, "target_first": 18})
        pairs = [r for r in _read_pairs() if r["paired_target_strategy"] == "layers_5"]
        self.assertEqual(len(pairs), 36)

    def test_2f_top14_36_pairs_seeds_12_each_6_6(self):
        bal = _STATE["norm_manifest"]["position_balance"]
        for s in ("1", "2", "3"):
            self.assertEqual(bal["2f_top14/%s/%s" % (YCH01, s)],
                             {"baseline_first": 6, "target_first": 6},
                             "2f_top14 seed %s must be 6/6" % s)
        pairs = [r for r in _read_pairs() if r["paired_target_strategy"] == "2f_top14"]
        self.assertEqual(len(pairs), 36)
        seeds = {}
        for r in pairs:
            seeds[r["seed"]] = seeds.get(r["seed"], 0) + 1
        self.assertEqual(seeds, {"1": 12, "2": 12, "3": 12})


# --------------------------------------------------------------------------- C
class PlanIdentityReuse(unittest.TestCase):
    def test_2f_top14_reuses_frozen_ext_plan_identity_seed_invariant(self):
        # plan parity from the normalizer: every 2f_top14 seed matches the frozen ext plan.
        rows = [p for p in _STATE["plan_parity"] if p["strategy"] == "2f_top14"]
        self.assertEqual(len(rows), 3, "expected 2f_top14 for seeds 1,2,3")
        shas = {p["plan_sha256"] for p in rows}
        self.assertEqual(shas, {FROZEN_2F_PLAN_SHA}, "2f_top14 plan sha must be frozen 6bc163bd, seed-invariant")
        for p in rows:
            self.assertTrue(p["matches_frozen"], "2f_top14 must match frozen ext report")
            self.assertEqual((p["pages"], p["interior"], p["leaf"]), (14, 14, 0))
            self.assertEqual(p["parity_type"], "exact_native_plan")

    def test_layers5_is_structural_static(self):
        rows = [p for p in _STATE["plan_parity"] if p["strategy"] == "layers_5"]
        self.assertEqual(len(rows), 1)
        p = rows[0]
        self.assertEqual(p["parity_type"], "structural_static")
        self.assertEqual((p["pages"], p["interior"], p["leaf"]), (5, 5, 0))


# --------------------------------------------------------------------------- D
class SeventhAnalysisAdditive(unittest.TestCase):
    def test_seventh_layers5_R_ow(self):
        c = _STATE["summary"]["cells"]["YCh01/layers_5"]
        self.assertAlmostEqual(c["seventh_R_ow"], -0.5961, delta=5e-4)
        self.assertAlmostEqual(c["seventh_baseline_first_R"], -0.7423, delta=5e-4)
        self.assertAlmostEqual(c["seventh_target_first_R"], -0.4466, delta=5e-4)
        # both position subsets negative -> §7 decision C
        self.assertEqual(c["section7_decision"], "C")
        self.assertTrue(c["negative_behavior_reproduced"])

    def test_seventh_2f_top14_R_ow_and_position_split(self):
        c = _STATE["summary"]["cells"]["YCh01/2f_top14"]
        self.assertAlmostEqual(c["seventh_R_ow"], 0.2815, delta=5e-4)
        self.assertAlmostEqual(c["seventh_baseline_first_R"], -1.0188, delta=5e-4)
        self.assertAlmostEqual(c["seventh_target_first_R"], 0.6151, delta=5e-4)
        # subsets strongly oppose (sign-agree 0.56 < 0.60) -> §8 decision D
        self.assertEqual(c["section8_decision"], "D")
        self.assertTrue(c["position_sensitive"])
        self.assertLess(c["seventh_sign_agree_frac"], 0.60)

    def test_2f_top14_near_zero_not_strongly_harmful(self):
        # -0.019 historical is near zero; the follow-up must NOT be recorded as strongly harmful.
        c = _STATE["summary"]["cells"]["YCh01/2f_top14"]
        self.assertAlmostEqual(c["historical_current_R_ow"], -0.0190, delta=5e-4)
        self.assertIn("near zero", c["historical_note"])

    def test_seed_medians_reported(self):
        c = _STATE["summary"]["cells"]["YCh01/2f_top14"]
        self.assertEqual(set(c["seed_R"].keys()), {"1", "2", "3"})

    def test_side_by_side_prior_generations_present_and_labelled(self):
        c = _STATE["summary"]["cells"]["YCh01/layers_5"]
        self.assertAlmostEqual(c["R_ws"], 0.0252, delta=5e-4)
        self.assertAlmostEqual(c["historical_primary_R_ow"], 0.3766, delta=5e-4)
        self.assertAlmostEqual(c["sixth_balanced_R_ow"], -0.2425, delta=5e-4)
        self.assertAlmostEqual(c["sixth_baseline_first_R"], -0.7620, delta=5e-4)
        self.assertAlmostEqual(c["sixth_target_first_R"], 0.5020, delta=5e-4)
        s = _STATE["summary"]
        self.assertTrue(s["does_not_replace_prior_R_ow"])
        self.assertTrue(s["does_not_alter_frozen_55_cell_comparison"])
        self.assertTrue(s["not_pooled"])

    def test_mechanism_framing_is_pair_position_not_carryover_attribution(self):
        # The observed direction must be framed as pair-position / short-lived
        # execution-state, and any mention of page-cache carryover must be a DISCLAIMER
        # (never appears as an attribution).
        lang = _STATE["summary"]["mechanism_language"].lower()
        self.assertIn("pair-position", lang)
        self.assertIn("execution-state", lang)
        blob = json.dumps(_STATE["summary"]).lower()
        # carryover may only appear negated ("no page-cache carryover ...").
        idx = 0
        while True:
            idx = blob.find("carryover", idx)
            if idx == -1:
                break
            self.assertIn("no page-cache carryover", blob[max(0, idx - 20):idx + 9],
                          "page-cache carryover must only appear as a disclaimer")
            idx += 1


# --------------------------------------------------------------------------- E
class AccountingUnpooled(unittest.TestCase):
    def test_coverage_still_65_65_zero_added(self):
        acc = _STATE["summary"]["accounting"]
        self.assertEqual(acc["coverage"]["cells"], 65)
        self.assertEqual(acc["coverage"]["of"], 65)
        self.assertEqual(acc["coverage"]["followup_adds_coverage_cells"], 0)

    def test_all_archive_bookkeeping_5756_2878_unpooled(self):
        acc = _STATE["summary"]["accounting"]
        b = acc["all_archive_bookkeeping"]
        self.assertEqual(b["campaigns"], 7)
        self.assertEqual(b["invocations"], 5756)
        self.assertEqual(b["pairs"], 2878)
        self.assertFalse(b["pooled"])
        self.assertFalse(b["is_one_estimator"])
        self.assertTrue(acc["never_call_5756_2878_one_estimator"])

    def test_five_campaign_coverage_preserved(self):
        fc = _STATE["summary"]["accounting"]["five_campaign_coverage"]
        self.assertEqual((fc["invocations"], fc["pairs"]), (5376, 2688))
        self.assertFalse(fc["pooled"])

    def test_layer_sums_are_consistent(self):
        acc = _STATE["summary"]["accounting"]
        fc, s6, s7 = acc["five_campaign_coverage"], acc["sixth_outlier_replication"], acc["seventh_ych01_followup"]
        b = acc["all_archive_bookkeeping"]
        self.assertEqual(fc["invocations"] + s6["invocations"] + s7["invocations"], b["invocations"])
        self.assertEqual(fc["pairs"] + s6["pairs"] + s7["pairs"], b["pairs"])


# --------------------------------------------------------------------------- F
class PriorEvidenceUntouched(unittest.TestCase):
    def test_frozen_55_cell_ych01_rows_unchanged(self):
        l5 = _frozen_row("layers_5")
        f2 = _frozen_row("2f_top14")
        self.assertIsNotNone(l5); self.assertIsNotNone(f2)
        # historical primary R_ow must be the ORIGINAL values, not replaced by 6th/7th.
        self.assertAlmostEqual(float(l5["R_ow"]), 0.3766, delta=5e-4)
        self.assertAlmostEqual(float(f2["R_ow"]), -0.0190, delta=5e-4)

    def test_sixth_replication_layers5_untouched(self):
        val = None
        for r in csv.DictReader(open(SIXTH_POS)):
            if r["workload"] == "YCh01" and r["strategy"] == "layers_5":
                val = float(r["all_balanced_R"])
        self.assertIsNotNone(val)
        self.assertAlmostEqual(val, -0.2425, delta=5e-4)


if __name__ == "__main__":
    unittest.main()
