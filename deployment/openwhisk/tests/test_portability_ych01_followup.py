"""Workstation <-> OpenWhisk YCH01 TWO-CELL FOLLOW-UP campaign: the SEVENTH, INDEPENDENT
additive campaign (portability_ych01_followup, 7a3cc45d...). It is a targeted SIGN /
STABILITY check -- NOT new coverage and NOT a seventh pooled performance estimator. It
re-runs, under EXACT deterministic baseline-target position balance and STANDALONE handles
ONLY, the ONLY two (workload,strategy) cells whose LATEST workstation first-query effect is
positive but OpenWhisk is non-positive:

    YCh01/layers_5    -- R_ws +0.025 (neutral-positive), R_ow -0.243 (sixth balanced batch)
    YCh01/2f_top14    -- R_ws +0.214, R_ow -0.019 (near zero; portability_ext batch)

These tests assert the CLAIM BOUNDARY and the HARD GATES: exactly 2 target cells, both
already members of the frozen 65-cell canonical portability matrix (so coverage stays 65/65
and this campaign adds NO coverage); standalone only (no warm arm); exactly 72 pairs / 144
invocations; per-cell/per-seed EXACT position balance (18/18 for YCh01/layers_5, 6/6 for each
YCh01/2f_top14 seed) DETERMINISTICALLY enforced -- not approximately by random ordering;
REUSE ONLY (0 new keyed plans, 0 new markers -- 2f_top14 reuses the audited portability_ext
keyed plans, layers_5 reuses the committed static strategy artifact); and all SIX prior
campaign identities byte-frozen. The previously observed direction is described only as a
pair-position / short-lived execution-state / execution-storage-state effect; -0.019 is a
near-zero, not strongly harmful, result. Nothing is invoked here; WK2 runs the matrix.
"""
import json
import os
import sys
import unittest
from collections import Counter

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

IMAGE = "sha256:" + "a" * 64
os.environ.setdefault("OW_ACTION_IMAGE_DIGEST", IMAGE)

import portability_ych01_followup_manifest as YF  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
NATIVE_PIN = os.path.join(OW, "config/artifacts.native_ycsb.json")
CAMPAIGN_MATRIX = os.path.join(OW, "ws2/matrix.portability_ych01_followup.json")

# Independent identities: all SIX prior campaigns MUST remain byte-frozen.
PRIMARY_RC = "022fbeb0"
SECONDARY_RC = "441609e6"
PORTABILITY_RC = "64f44c3e"
EXT_RC = "bf504a28"
CLOSURE_RC = "a5be8f15"
REPL_RC = "a564770a"
FOLLOWUP_RC = "7a3cc45d"

SCHEDULE_SEED_FOLLOWUP = 20260901
EXPECTED_TOTAL_PAIRS = 72
EXPECTED_TOTAL_INVOCATIONS = 144

YCH01 = "native_ycsb_c_hot_hashed_01"
# (workload_id, strategy) -> expected total pairs for the cell (across its seeds)
EXPECTED_CELL_PAIRS = {
    (YCH01, "layers_5"): 36,     # 1 seed x 36
    (YCH01, "2f_top14"): 36,     # 3 seeds x 12
}
BLOCK_PAIRS = {"Y1": 36, "Y2": 36}
# every strategy this campaign schedules -- ALL must already exist (reuse-only)
REUSED_STRATEGIES = {"baseline", "layers_5", "2f_top14"}


def _load_json(path):
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------- A
class FollowupManifestIdentity(unittest.TestCase):
    """The manifest is the single source of truth for the campaign identity + reuse."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)
        cls.plan = YF.portability_ych01_followup_invocation_plan()
        cls.rc = YF.portability_ych01_followup_run_config_sha256(cls.plan)

    def test_exactly_two_target_cells(self):
        targets = set()
        for mx in YF.MATRICES_FOLLOWUP:
            for wl in mx["workloads"]:
                for s in mx["strategies"]:
                    if s != "baseline":
                        targets.add((wl, s))
        self.assertEqual(targets, set(EXPECTED_CELL_PAIRS.keys()),
                         "campaign must target EXACTLY the two YCh01 follow-up cells")
        self.assertEqual(len(targets), 2)

    def test_only_ych01_workload(self):
        self.assertEqual(set(self.plan["workload_set"]), {YCH01})

    def test_standalone_only_no_warm(self):
        self.assertEqual(YF.HANDLE_MODES_FOLLOWUP, ["standalone"])
        self.assertEqual(self.plan["handle_modes"], ["standalone"])
        self.assertNotIn("warm", self.plan["handle_modes"])

    def test_plan_declares_72_pairs_144_invocations(self):
        self.assertEqual(self.plan["total_pairs"], EXPECTED_TOTAL_PAIRS)
        self.assertEqual(self.plan["total_invocations"], EXPECTED_TOTAL_INVOCATIONS)
        # recomputed from the block product, not hard-coded in the assertion
        derived = 0
        for mx in self.plan["matrices"]:
            T = len([s for s in mx["strategies"] if s != "baseline"])
            derived += len(mx["workloads"]) * len(mx["seeds"]) * mx["reps"] * T
        self.assertEqual(derived, EXPECTED_TOTAL_PAIRS)

    def test_per_block_pairs(self):
        got = {mx["name"]: mx["pairs"] for mx in self.plan["matrices"]}
        self.assertEqual(got, BLOCK_PAIRS)

    def test_per_block_per_cell_balance_half_half(self):
        for mx in self.plan["matrices"]:
            self.assertEqual(mx["per_cell_baseline_first"], mx["per_cell_target_first"])
            self.assertEqual(mx["per_cell_baseline_first"] + mx["per_cell_target_first"],
                             mx["per_cell_pairs"])
            self.assertEqual(mx["per_cell_pairs"], mx["reps"])  # W=F=M=1

    def test_position_balance_flag_is_exact(self):
        self.assertEqual(YF.POSITION_BALANCE, "exact")
        self.assertEqual(self.plan["position_balance"], "exact")

    def test_only_reused_strategies_no_other(self):
        self.assertEqual(set(self.plan["strategies"]), REUSED_STRATEGIES)

    def test_run_config_recomputes_and_is_distinct(self):
        self.assertRegex(self.rc, r"^[0-9a-f]{64}$")
        self.assertTrue(self.rc.startswith(FOLLOWUP_RC))
        # recompute stability
        again = YF.portability_ych01_followup_run_config_sha256(
            YF.portability_ych01_followup_invocation_plan())
        self.assertEqual(self.rc, again)
        for other in (PRIMARY_RC, SECONDARY_RC, PORTABILITY_RC, EXT_RC, CLOSURE_RC, REPL_RC):
            self.assertFalse(self.rc.startswith(other),
                             "follow-up run_config collides with %s" % other)

    def test_schedule_seed_is_new_and_off_round(self):
        self.assertEqual(YF.SCHEDULE_SEED_FOLLOWUP, SCHEDULE_SEED_FOLLOWUP)
        for prior in (20260804, 20260825, 20260826, 20260828, 20260829, 20260830):
            self.assertNotEqual(YF.SCHEDULE_SEED_FOLLOWUP, prior)

    def test_reps_must_be_even_for_exact_balance(self):
        self.assertTrue(all(mx["reps"] % 2 == 0 for mx in YF.MATRICES_FOLLOWUP))

    def test_reuse_only_verifies_against_pin(self):
        # every scheduled strategy/plan already present; nothing to add
        self.assertEqual(YF.verify_reuse(self.pin), [])

    def test_reused_plan_identities_resolve(self):
        ids = YF.reused_plan_identities(self.pin)
        # 1 static (layers_5) + 3 keyed (2f_top14 seeds 1,2,3) = 4 provenance rows.
        self.assertEqual(len(ids), 4)
        for label, e in ids.items():
            self.assertIsNotNone(e.get("sha256"), "reused plan %s has no sha" % label)

    def test_2f_top14_keyed_plan_seed_invariant(self):
        ids = YF.reused_plan_identities(self.pin)
        keyed = {k: v for k, v in ids.items() if "2f_top14" in k}
        self.assertEqual(len(keyed), 3)
        shas = {v["sha256"] for v in keyed.values()}
        self.assertEqual(len(shas), 1, "top-14 selection is seed-invariant (one plan sha)")


# --------------------------------------------------------------------------- B
class FollowupPinIdentity(unittest.TestCase):
    """The frozen pin carries the follow-up identity and NONE of the six prior identities
    moved; the reuse tables gained nothing."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)

    def test_all_six_prior_identities_present_and_frozen(self):
        for key, pref in (("run_config_sha256", PRIMARY_RC),
                          ("secondary_run_config_sha256", SECONDARY_RC),
                          ("portability_run_config_sha256", PORTABILITY_RC),
                          ("portability_ext_run_config_sha256", EXT_RC),
                          ("portability_full_closure_run_config_sha256", CLOSURE_RC),
                          ("portability_outlier_replication_run_config_sha256", REPL_RC)):
            self.assertTrue(self.pin[key].startswith(pref),
                            "%s drifted from %s" % (key, pref))

    def test_followup_identity_present_and_recomputes(self):
        self.assertIn("portability_ych01_followup_run_config_sha256", self.pin)
        plan = self.pin["portability_ych01_followup_invocation_plan"]
        want = YF.portability_ych01_followup_invocation_plan()
        self.assertEqual(json.dumps(plan, sort_keys=True),
                         json.dumps(want, sort_keys=True))
        self.assertEqual(self.pin["portability_ych01_followup_run_config_sha256"],
                         YF.portability_ych01_followup_run_config_sha256(want))

    def test_campaign_adds_zero_keyed_and_zero_markers(self):
        # crosscheck passes only if reuse holds AND the identity ties out
        self.assertEqual(YF.crosscheck_followup(self.pin), [])
        # every scheduled non-baseline strategy already had a strategy_plans entry
        sp = self.pin["strategy_plans"]
        for s in REUSED_STRATEGIES:
            self.assertIn(s, sp, "reused strategy %s must pre-exist (no marker added)" % s)

    def test_workloads_within_frozen_workload_set(self):
        wls = self.pin.get("workload_set", [])
        plan = self.pin["portability_ych01_followup_invocation_plan"]
        for wl in plan["workload_set"]:
            self.assertIn(wl, wls, "follow-up workload %s not in frozen set" % wl)


# --------------------------------------------------------------------------- C
class FollowupCampaignSingleBatch(unittest.TestCase):
    """ws2/matrix.portability_ych01_followup.json flattens Y1-Y2 into ONE ordered
    144-invocation schedule. Proves 72/144, per-block counts, standalone-only, EXACT
    per-cell/per-seed position balance (18/18 and 6/6), one fingerprint distinct from every
    prior campaign, and determinism. No OpenWhisk is invoked."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(OW, "client"))
        import build_schedule as BS
        import validate_schedule as VS
        cls.BS, cls.VS = BS, VS
        cls.pin = _load_json(NATIVE_PIN)
        cls.matrix = _load_json(CAMPAIGN_MATRIX)
        cls.ids = {
            "run_config_sha256": cls.pin["portability_ych01_followup_run_config_sha256"],
            "artifact_manifest_sha256": "0" * 64,
            "action_image_digest": "sha256:portability-ych01-followup-test"}
        cls.sched = cls.BS.build_campaign_schedule(cls.matrix, cls.ids)

    def test_matrix_is_one_campaign_with_two_blocks(self):
        m = self.matrix
        self.assertIn("blocks", m)
        self.assertEqual(m["schedule_seed"], SCHEDULE_SEED_FOLLOWUP)
        self.assertEqual(m["run_config_key"], "portability_ych01_followup_run_config_sha256")
        self.assertEqual(m["position_balance"], "exact")
        self.assertEqual([b["id"] for b in m["blocks"]], list(BLOCK_PAIRS.keys()))

    def test_standalone_only_in_every_block(self):
        for b in self.matrix["blocks"]:
            self.assertEqual(b["handle_modes"], ["standalone"],
                             "block %s must be standalone-only" % b["id"])
        self.assertEqual(sorted({p["handle_mode"] for p in self.sched["pairs"]}),
                         ["standalone"])

    def test_campaign_self_validates_clean(self):
        problems = self.VS.validate_campaign(self.sched, self.matrix)
        self.assertEqual(problems, [], "campaign validation problems: %s" % problems)

    def test_counts_are_exactly_72_144_from_validator(self):
        self.assertEqual(self.sched["counts"],
                         {"pairs": EXPECTED_TOTAL_PAIRS,
                          "invocations": EXPECTED_TOTAL_INVOCATIONS})

    def test_per_block_pair_counts(self):
        got = Counter(p["block_id"] for p in self.sched["pairs"])
        self.assertEqual(dict(got), BLOCK_PAIRS)

    def test_exact_position_balance_per_cell(self):
        """The HARD gate: each balance cell (target x workload x seed x fop x handle) is
        EXACTLY baseline_first == target_first -- 18/18 for YCh01/layers_5, 6/6 for each
        YCh01/2f_top14 seed. This must hold deterministically, not approximately."""
        ab, ba = Counter(), Counter()
        for p in self.sched["pairs"]:
            ck = (p["target_strategy"], p["workload"], p["seed"],
                  p["first_operation_id"], p["handle_mode"])
            if p["order"][0] == "baseline":
                ab[ck] += 1
            else:
                ba[ck] += 1
        cells = set(ab) | set(ba)
        self.assertEqual(len(cells), 4, "expected 4 balance cells (1 static + 3 seeds)")
        for ck in cells:
            self.assertEqual(ab[ck], ba[ck],
                             "cell %s not exactly balanced: %d/%d" % (ck, ab[ck], ba[ck]))
            total = ab[ck] + ba[ck]
            expect = 12 if ck[0] == "2f_top14" else 36
            self.assertEqual(total, expect, "cell %s has %d pairs" % (ck, total))

    def test_per_cell_totals_match_expected(self):
        by_cell = Counter((p["workload"], p["target_strategy"]) for p in self.sched["pairs"])
        self.assertEqual(dict(by_cell), EXPECTED_CELL_PAIRS)

    def test_2f_top14_preserves_seeds_one_two_three(self):
        seeds = sorted({p["seed"] for p in self.sched["pairs"]
                        if p["target_strategy"] == "2f_top14"})
        self.assertEqual(seeds, [1, 2, 3])

    def test_layers_5_is_seed_one_only(self):
        seeds = sorted({p["seed"] for p in self.sched["pairs"]
                        if p["target_strategy"] == "layers_5"})
        self.assertEqual(seeds, [1])

    def test_exact_balance_requires_even_reps(self):
        """An odd repetitions_per_cell under position_balance=exact must fail closed."""
        bad_matrix = json.loads(json.dumps(self.matrix))
        bad_matrix["blocks"][0]["repetitions_per_cell"] = 5  # odd
        with self.assertRaises(Exception):
            self.BS.build_campaign_schedule(bad_matrix, self.ids)

    def test_one_fingerprint_distinct_from_all_prior_campaigns(self):
        fp = self.sched["matrix_fingerprint"]
        self.assertRegex(fp, r"^[0-9a-f]{64}$")
        recomputed = self.VS.campaign_fingerprint(
            self.matrix, self.ids, self.sched["invocations"])
        self.assertEqual(fp, recomputed)
        for other_matrix, other_key in (
                ("ws2/matrix.portability.json", "portability_run_config_sha256"),
                ("ws2/matrix.portability_ext.json", "portability_ext_run_config_sha256"),
                ("ws2/matrix.portability_full_closure.json",
                 "portability_full_closure_run_config_sha256"),
                ("ws2/matrix.portability_outlier_replication.json",
                 "portability_outlier_replication_run_config_sha256")):
            om = _load_json(os.path.join(OW, other_matrix))
            oids = dict(self.ids, run_config_sha256=self.pin[other_key])
            osched = self.BS.build_campaign_schedule(om, oids)
            self.assertNotEqual(fp, osched["matrix_fingerprint"],
                                "follow-up fingerprint must differ from %s" % other_matrix)

    def test_positions_contiguous_and_pairs_are_baseline_plus_one_target(self):
        inv = self.sched["invocations"]
        positions = sorted(i["schedule_position"] for i in inv)
        self.assertEqual(positions, list(range(1, EXPECTED_TOTAL_INVOCATIONS + 1)))
        by_pair = {}
        for i in inv:
            by_pair.setdefault(i["pair_id"], []).append(i)
        self.assertEqual(len(by_pair), EXPECTED_TOTAL_PAIRS)
        for pid, arms in by_pair.items():
            self.assertEqual(len(arms), 2)
            self.assertEqual(sum(1 for a in arms if a["strategy"] == "baseline"), 1)

    def test_schedule_is_deterministic(self):
        again = self.BS.build_campaign_schedule(self.matrix, self.ids)
        self.assertEqual(json.dumps(self.sched["pairs"], sort_keys=True),
                         json.dumps(again["pairs"], sort_keys=True))
        self.assertEqual(self.sched["matrix_fingerprint"], again["matrix_fingerprint"])


# --------------------------------------------------------------------------- D
class FollowupPriorCampaignsUnaffected(unittest.TestCase):
    """The exact-balance code paths are opt-in and the seventh campaign changes nothing about
    prior campaigns: a flagless (prior) portability matrix still builds and validates clean,
    and the sixth (outlier_replication) matrix keeps its own identity."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(OW, "client"))
        import build_schedule as BS
        import validate_schedule as VS
        cls.BS, cls.VS = BS, VS
        cls.pin = _load_json(NATIVE_PIN)

    def test_flagless_campaign_has_no_position_balance_key(self):
        m = _load_json(os.path.join(OW, "ws2/matrix.portability.json"))
        self.assertNotIn("position_balance", m)
        ids = {"run_config_sha256": self.pin["portability_run_config_sha256"],
               "artifact_manifest_sha256": "0" * 64,
               "action_image_digest": "sha256:x"}
        sched = self.BS.build_campaign_schedule(m, ids)
        self.assertEqual(self.VS.validate_campaign(sched, m), [])

    def test_sixth_campaign_identity_unchanged(self):
        self.assertTrue(self.pin["portability_outlier_replication_run_config_sha256"]
                        .startswith(REPL_RC))


# --------------------------------------------------------------------------- E
class FollowupNormalizerRegistry(unittest.TestCase):
    """The WK1-authored normalizer's expected-value registry must not silently drift from the
    manifest: the run_config, schedule seed, target cells, block pairs and per-cell/per-seed
    position balance it asserts are exactly the ones the manifest produces. (The normalizer
    itself fails loud until WK2 evidence is wired -- proven here too.)"""

    @classmethod
    def setUpClass(cls):
        import normalize_portability_ych01_followup as NZ
        cls.NZ = NZ
        cls.FU = NZ.FU
        cls.plan = YF.portability_ych01_followup_invocation_plan()

    def test_run_config_and_seed_match_manifest(self):
        self.assertEqual(self.FU["expected_run_config_sha256"],
                         YF.portability_ych01_followup_run_config_sha256(self.plan))
        self.assertEqual(self.FU["expected_schedule_seed"], YF.SCHEDULE_SEED_FOLLOWUP)

    def test_expected_counts_and_blocks(self):
        self.assertEqual(self.FU["expected"],
                         {"invocations": 144, "pairs": 72, "baseline": 72, "target": 72})
        self.assertEqual(self.FU["expected_block_pairs"], BLOCK_PAIRS)

    def test_expected_target_cells(self):
        self.assertEqual(self.FU["expected_target_cells"],
                         {("layers_5", YCH01), ("2f_top14", YCH01)})
        self.assertEqual(self.FU["static_strategies"], {"layers_5"})
        self.assertEqual(self.FU["keyed_strategies"], {"2f_top14"})

    def test_expected_position_balance(self):
        self.assertEqual(self.FU["expected_position_balance"], {
            ("layers_5", YCH01, 1): (18, 18),
            ("2f_top14", YCH01, 1): (6, 6),
            ("2f_top14", YCH01, 2): (6, 6),
            ("2f_top14", YCH01, 3): (6, 6),
        })

    def test_foreign_run_configs_cover_all_six_priors(self):
        self.assertEqual(len(self.FU["foreign_run_configs"]), 6)

    def test_keyed_freeze_report_is_portability_ext(self):
        self.assertEqual(self.FU["keyed_freeze_report_rel"],
                         "config/plans/keyed/portability_ext_freeze_report.json")

    def test_post_wk2_evidence_fields_are_wired(self):
        # WK2 has run: evidence_dir/bundle/fingerprint are now filled from the archived bundle
        # (execution git 26500fe8fe57). Before WK2 these were None; the wiring below is the
        # post-execution state.
        self.assertEqual(self.FU["evidence_dir"],
                         "evidence/portability_ych01_followup/26500fe8fe57")
        self.assertEqual(self.FU["bundle"],
                         "ws2_bundle_26500fe8fe57_20260829T200658Z.tar.gz")
        self.assertEqual(self.FU["expected_matrix_fingerprint"],
                         "47aab3200fbcdc3a31f5ef43a85af7a26c18385e2961ad0e9c21ee1fe8450794")

    def test_normalizer_fails_loud_without_evidence(self):
        # The fail-loud guard must still refuse if the evidence identity is cleared.
        saved = {k: self.FU[k] for k in ("evidence_dir", "bundle", "expected_matrix_fingerprint")}
        try:
            self.FU["evidence_dir"] = None
            self.FU["bundle"] = None
            self.FU["expected_matrix_fingerprint"] = None
            with self.assertRaises(SystemExit):
                self.NZ.normalize(os.path.join(REPO, "deployment/openwhisk"), "/tmp/should_not_write")
        finally:
            self.FU.update(saved)


if __name__ == "__main__":
    unittest.main()
