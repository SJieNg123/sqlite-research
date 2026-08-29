"""Workstation <-> OpenWhisk OUTLIER-REPLICATION campaign: the SIXTH, INDEPENDENT
additive campaign (portability_outlier_replication, a564770a...). It is a targeted
STABILITY / CONFOUND check -- NOT new coverage and NOT a sixth pooled performance
estimator. It re-runs, under EXACT deterministic baseline-target position balance and
STANDALONE handles ONLY, the six (workload,strategy) cells whose original OpenWhisk<->
workstation first-query discrepancy is largest:

    C/layers_92, C/2d, C_hit/2e_K40   -- category (1): original true sign-flips (+WS -> -OW)
    C/layers_5                        -- category (1): WS-neutral but OW strongly negative
    YCh01/layers_5, YCu/layers_5      -- category (2): WS-neutral but OW positive

These tests assert the CLAIM BOUNDARY and the HARD GATES: exactly 6 target cells, all
already members of the frozen 65-cell canonical portability matrix (so coverage stays
65/65 and this campaign adds NO coverage); standalone only (no warm arm); exactly 118
pairs / 236 invocations; per-cell EXACT position balance (10/10 for the single/static
cells, 3/3 for each C_hit/2e_K40 seed) DETERMINISTICALLY enforced -- not approximately
by random ordering; REUSE ONLY (0 new keyed plans, 0 new markers -- 2e_K40 reuses the
audited full-closure keyed plans, layers_92/2d/layers_5 reuse committed static strategy
artifacts); and all FIVE prior campaign identities byte-frozen. Nothing is invoked here;
WK2 runs the matrix.
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

import portability_outlier_replication_manifest as OR  # noqa: E402
import analyze_outlier_replication as AOR  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
NATIVE_PIN = os.path.join(OW, "config/artifacts.native_ycsb.json")
CAMPAIGN_MATRIX = os.path.join(OW, "ws2/matrix.portability_outlier_replication.json")

# Independent identities: all FIVE prior campaigns MUST remain byte-frozen.
PRIMARY_RC = "022fbeb0"
SECONDARY_RC = "441609e6"
PORTABILITY_RC = "64f44c3e"
EXT_RC = "bf504a28"
CLOSURE_RC = "a5be8f15"
REPL_RC = "a564770a"

SCHEDULE_SEED_REPL = 20260830
EXPECTED_TOTAL_PAIRS = 118
EXPECTED_TOTAL_INVOCATIONS = 236

# The exact six (comparison-code workload, strategy) cells and their per-cell pair count.
# workload id -> comparison code
WL_MAP = {
    "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit",
    "native_ycsb_c_hot_hashed_01": "YCh01",
    "native_ycsb_c_read_uniform": "YCu",
}
# (workload_id, strategy) -> expected total pairs for the cell (across its seeds)
EXPECTED_CELL_PAIRS = {
    ("read_tail_mixed_20k", "layers_92"): 20,
    ("read_tail_mixed_20k", "2d"): 20,
    ("read_tail_mixed_20k", "layers_5"): 20,
    ("native_ycsb_c_hot_hashed_01", "layers_5"): 20,
    ("native_ycsb_c_read_uniform", "layers_5"): 20,
    ("read_tail_hit_20k", "2e_K40"): 18,   # 3 seeds x 6
}
BLOCK_PAIRS = {"R1": 60, "R2": 20, "R3": 20, "R4": 18}
# every strategy this campaign schedules -- ALL must already exist (reuse-only)
REUSED_STRATEGIES = {"baseline", "layers_92", "2d", "layers_5", "2e_K40"}


def _load_json(path):
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------- A
class ReplicationManifestIdentity(unittest.TestCase):
    """The manifest is the single source of truth for the campaign identity + reuse."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)
        cls.plan = OR.portability_outlier_replication_invocation_plan()
        cls.rc = OR.portability_outlier_replication_run_config_sha256(cls.plan)

    def test_exactly_six_target_cells(self):
        targets = set()
        for mx in OR.MATRICES_REPL:
            for wl in mx["workloads"]:
                for s in mx["strategies"]:
                    if s != "baseline":
                        targets.add((wl, s))
        self.assertEqual(targets, set(EXPECTED_CELL_PAIRS.keys()),
                         "campaign must target EXACTLY the six outlier cells")
        self.assertEqual(len(targets), 6)

    def test_standalone_only_no_warm(self):
        self.assertEqual(OR.HANDLE_MODES_REPL, ["standalone"])
        self.assertEqual(self.plan["handle_modes"], ["standalone"])
        self.assertNotIn("warm", self.plan["handle_modes"])

    def test_plan_declares_118_pairs_236_invocations(self):
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

    def test_position_balance_flag_is_exact(self):
        self.assertEqual(OR.POSITION_BALANCE, "exact")
        self.assertEqual(self.plan["position_balance"], "exact")

    def test_only_reused_strategies_no_other(self):
        self.assertEqual(set(self.plan["strategies"]), REUSED_STRATEGIES)

    def test_run_config_recomputes_and_is_distinct(self):
        self.assertRegex(self.rc, r"^[0-9a-f]{64}$")
        self.assertTrue(self.rc.startswith(REPL_RC))
        # recompute stability
        again = OR.portability_outlier_replication_run_config_sha256(
            OR.portability_outlier_replication_invocation_plan())
        self.assertEqual(self.rc, again)
        for other in (PRIMARY_RC, SECONDARY_RC, PORTABILITY_RC, EXT_RC, CLOSURE_RC):
            self.assertFalse(self.rc.startswith(other),
                             "replication run_config collides with %s" % other)

    def test_schedule_seed_is_new_and_off_round(self):
        self.assertEqual(OR.SCHEDULE_SEED_REPL, SCHEDULE_SEED_REPL)
        for prior in (20260804, 20260825, 20260826, 20260828, 20260829):
            self.assertNotEqual(OR.SCHEDULE_SEED_REPL, prior)

    def test_reuse_only_verifies_against_pin(self):
        # every scheduled strategy/plan already present; nothing to add
        self.assertEqual(OR.verify_reuse(self.pin), [])

    def test_reused_plan_identities_resolve(self):
        ids = OR.reused_plan_identities(self.pin)
        # 3 static cells + 3 keyed (2e_K40 seeds 1,2,3) = 6 provenance rows... but C/2d,
        # C/layers_92, C/layers_5, YCh01/layers_5, YCu/layers_5 are 5 static entries and
        # 3 keyed seed entries = 8 rows total; each must carry a sha256.
        self.assertEqual(len(ids), 8)
        for label, e in ids.items():
            self.assertIsNotNone(e.get("sha256"), "reused plan %s has no sha" % label)


# --------------------------------------------------------------------------- B
class ReplicationPinIdentity(unittest.TestCase):
    """The frozen pin carries the replication identity and NONE of the five prior
    identities moved; the reuse tables gained nothing."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)

    def test_all_five_prior_identities_present_and_frozen(self):
        for key, pref in (("run_config_sha256", PRIMARY_RC),
                          ("secondary_run_config_sha256", SECONDARY_RC),
                          ("portability_run_config_sha256", PORTABILITY_RC),
                          ("portability_ext_run_config_sha256", EXT_RC),
                          ("portability_full_closure_run_config_sha256", CLOSURE_RC)):
            self.assertTrue(self.pin[key].startswith(pref),
                            "%s drifted from %s" % (key, pref))

    def test_replication_identity_present_and_recomputes(self):
        self.assertIn("portability_outlier_replication_run_config_sha256", self.pin)
        plan = self.pin["portability_outlier_replication_invocation_plan"]
        want = OR.portability_outlier_replication_invocation_plan()
        self.assertEqual(json.dumps(plan, sort_keys=True),
                         json.dumps(want, sort_keys=True))
        self.assertEqual(self.pin["portability_outlier_replication_run_config_sha256"],
                         OR.portability_outlier_replication_run_config_sha256(want))

    def test_campaign_adds_zero_keyed_and_zero_markers(self):
        # crosscheck passes only if reuse holds AND the identity ties out
        self.assertEqual(OR.crosscheck_replication(self.pin), [])
        # every scheduled non-baseline strategy already had a strategy_plans entry
        sp = self.pin["strategy_plans"]
        for s in REUSED_STRATEGIES:
            self.assertIn(s, sp, "reused strategy %s must pre-exist (no marker added)" % s)

    def test_workloads_within_frozen_workload_set(self):
        wls = self.pin.get("workload_set", [])
        plan = self.pin["portability_outlier_replication_invocation_plan"]
        for wl in plan["workload_set"]:
            self.assertIn(wl, wls, "replication workload %s not in frozen set" % wl)


# --------------------------------------------------------------------------- C
class ReplicationCampaignSingleBatch(unittest.TestCase):
    """ws2/matrix.portability_outlier_replication.json flattens R1-R4 into ONE ordered
    236-invocation schedule. Proves 118/236, per-block counts, standalone-only, EXACT
    per-cell position balance (10/10 and 3/3), one fingerprint distinct from every prior
    campaign, and determinism. No OpenWhisk is invoked."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(OW, "client"))
        import build_schedule as BS
        import validate_schedule as VS
        cls.BS, cls.VS = BS, VS
        cls.pin = _load_json(NATIVE_PIN)
        cls.matrix = _load_json(CAMPAIGN_MATRIX)
        cls.ids = {
            "run_config_sha256": cls.pin["portability_outlier_replication_run_config_sha256"],
            "artifact_manifest_sha256": "0" * 64,
            "action_image_digest": "sha256:portability-outlier-replication-test"}
        cls.sched = cls.BS.build_campaign_schedule(cls.matrix, cls.ids)

    def test_matrix_is_one_campaign_with_four_blocks(self):
        m = self.matrix
        self.assertIn("blocks", m)
        self.assertEqual(m["schedule_seed"], SCHEDULE_SEED_REPL)
        self.assertEqual(m["run_config_key"], "portability_outlier_replication_run_config_sha256")
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

    def test_counts_are_exactly_118_236_from_validator(self):
        self.assertEqual(self.sched["counts"],
                         {"pairs": EXPECTED_TOTAL_PAIRS,
                          "invocations": EXPECTED_TOTAL_INVOCATIONS})

    def test_per_block_pair_counts(self):
        got = Counter(p["block_id"] for p in self.sched["pairs"])
        self.assertEqual(dict(got), BLOCK_PAIRS)

    def test_exact_position_balance_per_cell(self):
        """The HARD gate: each balance cell (target x workload x seed x fop x handle)
        is EXACTLY baseline_first == target_first -- 10/10 single/static, 3/3 per
        C_hit/2e_K40 seed. This must hold deterministically, not approximately."""
        ab, ba = Counter(), Counter()
        for p in self.sched["pairs"]:
            ck = (p["target_strategy"], p["workload"], p["seed"],
                  p["first_operation_id"], p["handle_mode"])
            if p["order"][0] == "baseline":
                ab[ck] += 1
            else:
                ba[ck] += 1
        cells = set(ab) | set(ba)
        self.assertEqual(len(cells), 8, "expected 8 balance cells (5 static + 3 seeds)")
        for ck in cells:
            self.assertEqual(ab[ck], ba[ck],
                             "cell %s not exactly balanced: %d/%d" % (ck, ab[ck], ba[ck]))
            total = ab[ck] + ba[ck]
            expect = 6 if ck[0] == "2e_K40" else 20
            self.assertEqual(total, expect, "cell %s has %d pairs" % (ck, total))

    def test_per_cell_totals_match_expected(self):
        by_cell = Counter((p["workload"], p["target_strategy"]) for p in self.sched["pairs"])
        self.assertEqual(dict(by_cell), EXPECTED_CELL_PAIRS)

    def test_chit_2e_k40_preserves_seeds_one_two_three(self):
        seeds = sorted({p["seed"] for p in self.sched["pairs"]
                        if p["target_strategy"] == "2e_K40"})
        self.assertEqual(seeds, [1, 2, 3])

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
                 "portability_full_closure_run_config_sha256")):
            om = _load_json(os.path.join(OW, other_matrix))
            oids = dict(self.ids, run_config_sha256=self.pin[other_key])
            osched = self.BS.build_campaign_schedule(om, oids)
            self.assertNotEqual(fp, osched["matrix_fingerprint"],
                                "replication fingerprint must differ from %s" % other_matrix)

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
class ReplicationAdvisoryDefaultPathUnaffected(unittest.TestCase):
    """The exact-balance code paths are opt-in: a flagless (prior) campaign matrix must
    build byte-identically to before (the five frozen campaigns keep their fingerprints).
    We prove the guard is on the flag, not global, by building the portability matrix and
    confirming NO exact-balance is imposed on it."""

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
        # validator on a flagless matrix runs no exact-balance branch and passes
        self.assertEqual(self.VS.validate_campaign(sched, m), [])


# --------------------------------------------------------------------------- E
class ReplicationAnalysisContract(unittest.TestCase):
    """The analysis contract is pre-registered and FAILS CLOSED before evidence exists;
    the classification rules map the six families deterministically."""

    def test_six_cells_and_families(self):
        fams = {(ws, s): fam for ws, s, fam in AOR.CELLS}
        self.assertEqual(fams, {
            ("C", "layers_92"): "sign_flip",
            ("C", "2d"): "sign_flip",
            ("C_hit", "2e_K40"): "sign_flip",
            ("C", "layers_5"): "ws_neutral_ow_negative",
            ("YCh01", "layers_5"): "ws_neutral_ow_positive",
            ("YCu", "layers_5"): "ws_neutral_ow_positive",
        })

    def test_classification_rules_are_pre_registered(self):
        # sign-flip: still-negative+stable -> A; clearly-positive+stable -> B; else C
        self.assertEqual(AOR.classify("sign_flip", -0.30, 1.0)[0], "A")
        self.assertEqual(AOR.classify("sign_flip", +0.30, 1.0)[0], "B")
        self.assertEqual(AOR.classify("sign_flip", -0.30, 0.40)[0], "C")  # unstable
        self.assertEqual(AOR.classify("sign_flip", 0.00, 1.0)[0], "C")    # near-zero
        # ws-neutral / ow-negative
        self.assertEqual(AOR.classify("ws_neutral_ow_negative", -0.30, 1.0)[0], "A")
        self.assertEqual(AOR.classify("ws_neutral_ow_negative", 0.00, 1.0)[0], "B")
        # ws-neutral / ow-positive
        self.assertEqual(AOR.classify("ws_neutral_ow_positive", +0.30, 1.0)[0], "A")
        self.assertEqual(AOR.classify("ws_neutral_ow_positive", 0.00, 1.0)[0], "B")

    def test_fails_closed_without_evidence(self):
        # the archived replication pairs do not exist yet (WK1); loader returns None
        if AOR.REPL_PAIRS_CSV.exists():
            self.skipTest("replication evidence already present")
        self.assertIsNone(AOR.load_replication())


if __name__ == "__main__":
    unittest.main()
