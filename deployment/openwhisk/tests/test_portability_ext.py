"""Workstation -> OpenWhisk PORTABILITY-EXTENSION matrix: the deployment-complement
campaign that carries the remaining 29 (workload, strategy) cells the workstation ran
-- but the primary/secondary/portability OpenWhisk campaigns did NOT -- onto OpenWhisk
under a fourth, INDEPENDENT run-config identity (portability_ext, bf504a28...).

Like the portability campaign this is a DEPLOYMENT/FEASIBILITY + relative-effectiveness
complement, not a new performance campaign. Warm paired first-query latency is NOT a
strategy-performance estimate (page-cache carryover was falsified; the effect is
positional/order). These tests assert only structural facts: 63-plan freeze parity,
additive pin identity (all THREE prior identities byte-untouched), LOSO leakage gates,
action dispatch for the new keyed + static strategies, and an exactly-426-pair /
852-invocation balanced single-batch schedule.

The 63 ext plans (source of truth: config/plans/keyed/portability_ext_freeze_report.json):

    strategy           workloads (seeds 1..3)                          pages  gate
    2f_top14           read_zipf,uniform,hot01,hit_20k,mixed_20k       14     None (emergent split recorded)
    learned_markov_14  read_zipf,uniform,hot01,hit_20k (LOSO)          14     None (emergent split recorded)
    2e_K500            uniform,hot01,hit_20k,mixed_20k                 592    92 interior (skeleton set-eq) + <=500 leaf
    2f_top28           uniform,hot01,hit_20k,mixed_20k                 28     None (recorded)
    learned_markov_28  uniform,hot01,hit_20k,mixed_20k (LOSO)          28     None (recorded)

plus three STATIC inline-offset cross-workload deployment checks (seed 1 only):
layers_92 (92-interior skeleton, == 2d page content, distinct name) x 4 workloads,
layers_5 (5-interior prefix) x 3 workloads, 2d x read_tail_hit_20k.

Formal execution is ONE single-batch campaign (ws2/matrix.portability_ext.json): the
UNION of seven heterogeneous rectangular BLOCKS (B5-B11) -> 426 pairs -> 852 invocations
under ONE schedule_seed=20260828, ONE run_config_key=portability_ext_run_config_sha256
(distinct from primary 022fbeb0..., secondary 441609e6..., and portability 64f44c3e...),
and ONE campaign fingerprint. Nothing is invoked here; WK2 runs the matrix.
"""
import csv
import hashlib
import json
import os
import sys
import unittest
from collections import Counter

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

IMAGE = "sha256:" + "a" * 64
os.environ.setdefault("OW_ACTION_IMAGE_DIGEST", IMAGE)

import main  # noqa: E402
import session as session_mod  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
ARTIFACTS = os.path.join(OW, "config/artifacts.json")
NATIVE_PIN = os.path.join(OW, "config/artifacts.native_ycsb.json")
FREEZE = os.path.join(OW, "config/plans/keyed/portability_ext_freeze_report.json")
SKELETON = os.path.join(OW, "config/plans/interior_pages.csv")
CAMPAIGN_MATRIX = os.path.join(OW, "ws2/matrix.portability_ext.json")

# Independent identities: all THREE prior campaigns MUST remain byte-frozen.
PRIMARY_RC = "022fbeb0"
SECONDARY_RC = "441609e6"
PORTABILITY_RC = "64f44c3e"
EXT_RC = "bf504a28"

SCHEDULE_SEED_EXT = 20260828
PORTABILITY_WORKLOADS = {
    "native_ycsb_c_hot_hashed_01", "native_ycsb_c_read_uniform",
    "native_ycsb_c_read_zipf", "read_tail_hit_20k", "read_tail_mixed_20k",
}
# The three NEW strategy markers this campaign introduces.
EXT_MARKERS = ("2f_top14", "learned_markov_14", "layers_92")
KEYED_EXT_STRATEGIES = ("2f_top14", "learned_markov_14", "2e_K500",
                        "2f_top28", "learned_markov_28")
LOSO_STRATEGIES = ("learned_markov_14", "learned_markov_28")
EXPECTED_BY_STRATEGY = {"2f_top14": 15, "learned_markov_14": 12, "2e_K500": 12,
                        "2f_top28": 12, "learned_markov_28": 12}
EXPECTED_BY_WORKLOAD = {"native_ycsb_c_read_zipf": 6, "native_ycsb_c_read_uniform": 15,
                        "native_ycsb_c_hot_hashed_01": 15, "read_tail_hit_20k": 15,
                        "read_tail_mixed_20k": 12}
BLOCK_PAIRS = {"block5": 36, "block6": 180, "block7": 90, "block8": 72,
               "block9": 24, "block10": 18, "block11": 6}


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def _skeleton_offsets():
    offs = set()
    with open(SKELETON, newline="") as f:
        for row in csv.DictReader(f):
            offs.add(int(row["file_offset"]))
    return offs


def _plan_offsets(path):
    offs = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            offs.append(int(row["file_offset"]))
    return offs


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- A
class ExtFreezeReportParity(unittest.TestCase):
    """Every one of the 63 ext plans is on disk, sha-bound, its recorded native-source
    copy is sha-bound too, and its interior/leaf split -- recomputed against the 92-page
    skeleton -- equals the recorded value. The freeze report is the ONLY source; no
    strategy selection happens here."""

    @classmethod
    def setUpClass(cls):
        cls.fr = _load_json(FREEZE)
        cls.plans = cls.fr["plans"]
        cls.skeleton = _skeleton_offsets()

    def test_bound_db_and_skeleton(self):
        self.assertEqual(len(self.skeleton), 92)
        self.assertEqual(self.fr["bound_db_sha256"],
                         "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1")

    def test_exactly_63_plans_over_expected_axes(self):
        self.assertEqual(len(self.plans), 63)
        triples = {(p["strategy"], p["workload_id"], p["seed"]) for p in self.plans}
        self.assertEqual(len(triples), 63, "duplicate (strategy,workload,seed)")
        for p in self.plans:
            self.assertIn(p["workload_id"], PORTABILITY_WORKLOADS)
            self.assertIn(p["seed"], (1, 2, 3))

    def test_per_strategy_and_per_workload_counts(self):
        self.assertEqual(dict(Counter(p["strategy"] for p in self.plans)),
                         EXPECTED_BY_STRATEGY)
        self.assertEqual(dict(Counter(p["workload_id"] for p in self.plans)),
                         EXPECTED_BY_WORKLOAD)

    def test_each_plan_sha_count_and_split(self):
        for p in self.plans:
            path = os.path.join(REPO, p["plan_path"])
            self.assertTrue(os.path.exists(path), "missing plan %s" % p["plan_path"])
            self.assertEqual(_sha256_file(path), p["plan_sha256"],
                             "plan sha mismatch %s" % p["plan_path"])
            offs = _plan_offsets(path)
            self.assertEqual(len(offs), p["pages"],
                             "%s: %d rows != pages %d" % (p["plan_path"], len(offs), p["pages"]))
            self.assertEqual(len(set(offs)), len(offs), "duplicate offset in %s" % p["plan_path"])
            interior = sum(1 for o in offs if o in self.skeleton)
            leaf = len(offs) - interior
            self.assertEqual(interior, p["interior"], "%s interior" % p["plan_path"])
            self.assertEqual(leaf, p["leaf"], "%s leaf" % p["plan_path"])
            self.assertEqual(p["pages"], p["interior"] + p["leaf"])

    def test_native_source_copy_is_sha_bound(self):
        for p in self.plans:
            copy_rel = p["native_source_copy"]
            copy_path = os.path.join(REPO, copy_rel)
            self.assertTrue(os.path.exists(copy_path),
                            "missing durable native-source copy %s" % copy_rel)
            self.assertEqual(_sha256_file(copy_path), p["native_source_sha256"],
                             "native-source copy sha mismatch %s" % copy_rel)
            self.assertIn("native_source/portability_ext/", copy_rel,
                          "durable copy must live under the ext native_source tree")

    def test_2e_k500_is_reconstructed_skeleton_union_bounded_leaf(self):
        e = [p for p in self.plans if p["strategy"] == "2e_K500"]
        self.assertEqual(len(e), 12)  # uniform,hot01,hit_20k,mixed_20k x 3 seeds
        for p in e:
            self.assertTrue(p["reconstructed"], "2e_K500 must be flagged reconstructed")
            self.assertEqual(p["interior"], 92, "2e_K500 must carry the full skeleton")
            self.assertLessEqual(p["leaf"], 500, "2e_K500 leaf budget is <=500")
            self.assertEqual(p["pages"], p["interior"] + p["leaf"])

    def test_budget_variants_total_pages(self):
        for p in self.plans:
            if p["strategy"] in ("2f_top14", "learned_markov_14"):
                self.assertEqual(p["pages"], 14, "%s must be an N=14 selection" % p["plan_path"])
            if p["strategy"] in ("2f_top28", "learned_markov_28"):
                self.assertEqual(p["pages"], 28, "%s must be an N=28 selection" % p["plan_path"])

    def test_learned_markov_is_loso_with_disjoint_train_test(self):
        for strat in LOSO_STRATEGIES:
            lm = [p for p in self.plans if p["strategy"] == strat]
            self.assertTrue(lm, "no %s plans" % strat)
            for p in lm:
                loso = p["loso"]
                self.assertIsNotNone(loso, "%s must carry LOSO provenance" % strat)
                self.assertEqual(loso["test_seed"], p["seed"],
                                 "LOSO test_seed must equal the plan seed")
                self.assertNotIn(p["seed"], loso["train_seeds"],
                                 "%s: leakage -- test seed present in train set" % p["plan_path"])


# --------------------------------------------------------------------------- B
class ExtPinParityAndIdentity(unittest.TestCase):
    """The pin gained EXACTLY the 63 ext keyed triples + the 3 markers + the ext
    top-level identity -- additively -- and ALL THREE prior identities
    (primary/secondary/portability) are byte-untouched. The ext run-config recomputes
    deterministically and is independent of every prior identity."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)
        cls.fr = {(p["strategy"], p["workload_id"], p["seed"]): p
                  for p in _load_json(FREEZE)["plans"]}

    def test_all_prior_identities_untouched(self):
        self.assertTrue(self.pin["run_config_sha256"].startswith(PRIMARY_RC))
        self.assertTrue(self.pin["secondary_run_config_sha256"].startswith(SECONDARY_RC))
        self.assertTrue(self.pin["portability_run_config_sha256"].startswith(PORTABILITY_RC))

    def test_ext_identity_present_and_distinct(self):
        rc = self.pin["portability_ext_run_config_sha256"]
        self.assertTrue(rc.startswith(EXT_RC))
        self.assertNotEqual(rc, self.pin["run_config_sha256"])
        self.assertNotEqual(rc, self.pin["secondary_run_config_sha256"])
        self.assertNotEqual(rc, self.pin["portability_run_config_sha256"])

    def test_sixty_three_ext_triples_present_with_recorded_counts(self):
        ksp = self.pin["keyed_strategy_plans"]
        found = 0
        for (strat, wl, seed), fp in self.fr.items():
            entry = ksp.get(wl, {}).get(str(seed), {}).get(strat)
            self.assertIsNotNone(entry, "pin missing %s/%s/s%d" % (strat, wl, seed))
            self.assertEqual(entry["expected_pages"], fp["pages"])
            self.assertEqual(entry["expected_interior_pages"], fp["interior"])
            self.assertEqual(entry["expected_leaf_pages"], fp["leaf"])
            self.assertEqual(entry["sha256"], fp["plan_sha256"])
            found += 1
        self.assertEqual(found, 63)

    def test_markers_present_for_new_strategies(self):
        for s in EXT_MARKERS:
            self.assertIn(s, self.pin["strategy_plans"], "marker %s absent" % s)

    def test_ext_run_config_sha256_recomputes(self):
        plan = self.pin["portability_ext_invocation_plan"]
        blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        recomputed = hashlib.sha256(blob.encode()).hexdigest()
        self.assertEqual(recomputed, self.pin["portability_ext_run_config_sha256"],
                         "portability_ext_run_config_sha256 does not recompute from its plan")

    def test_ext_plan_declares_426_pairs_852_invocations(self):
        plan = self.pin["portability_ext_invocation_plan"]
        self.assertEqual(plan["total_pairs"], 426)
        self.assertEqual(plan["total_invocations"], 852)
        self.assertEqual(plan["schedule_seed"], SCHEDULE_SEED_EXT)

    def test_ext_workloads_within_frozen_workload_set(self):
        # ext adds NO new workloads -- every ext workload already resolves.
        wls = set(self.pin["workload_set"])
        for wl in EXPECTED_BY_WORKLOAD:
            self.assertIn(wl, wls, "ext workload %s not in frozen workload_set" % wl)


# --------------------------------------------------------------------------- C
class ExtCampaignSingleBatch(unittest.TestCase):
    """THE formal-execution unit: ws2/matrix.portability_ext.json flattens the seven
    heterogeneous blocks (B5-B11) into ONE ordered 852-invocation schedule under ONE
    campaign fingerprint. Proves single-batch counts (426/852, per-block
    36/180/90/72/24/18/6), exactly one fingerprint distinct from the portability
    fingerprint, cross-block disjoint union, no unintended cells, every keyed target
    resolves a frozen plan, static seeds stay [1], and determinism. No OpenWhisk is
    invoked."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(OW, "client"))
        sys.path.insert(0, os.path.join(REPO, "config"))
        import build_schedule as BS
        import validate_schedule as VS
        cls.BS, cls.VS = BS, VS
        cls.pin = _load_json(NATIVE_PIN)
        cls.matrix = _load_json(CAMPAIGN_MATRIX)
        cls.ids = {"run_config_sha256": cls.pin["portability_ext_run_config_sha256"],
                   "artifact_manifest_sha256": "0" * 64,
                   "action_image_digest": "sha256:portability-ext-test"}
        cls.sched = cls.BS.build_campaign_schedule(cls.matrix, cls.ids)

    def test_matrix_is_one_campaign_with_seven_blocks(self):
        m = self.matrix
        self.assertIn("blocks", m, "campaign matrix must be block-union shaped")
        self.assertEqual(m["schedule_seed"], SCHEDULE_SEED_EXT)
        self.assertEqual(m["run_config_key"], "portability_ext_run_config_sha256")
        self.assertEqual([b["id"] for b in m["blocks"]], list(BLOCK_PAIRS.keys()))

    def test_static_blocks_keep_seed_one(self):
        # B9/B10/B11 are structural cross-workload deployment checks; their seed axis
        # must stay [1] and never expand to 1,2,3.
        by_id = {b["id"]: b for b in self.matrix["blocks"]}
        for bid, target in (("block9", "layers_92"), ("block10", "layers_5"),
                            ("block11", "2d")):
            self.assertEqual(by_id[bid]["seeds"], [1],
                             "structural %s must not expand seeds" % bid)
            self.assertEqual([s for s in by_id[bid]["strategies"] if s != "baseline"],
                             [target])

    def test_campaign_self_validates_clean(self):
        problems = self.VS.validate_campaign(self.sched, self.matrix)
        self.assertEqual(problems, [], "campaign validation problems: %s" % problems)

    def test_counts_are_exactly_426_852(self):
        self.assertEqual(self.sched["counts"], {"pairs": 426, "invocations": 852})
        self.assertEqual(len(self.sched["pairs"]), 426)
        self.assertEqual(len(self.sched["invocations"]), 852)
        exp = self.VS.campaign_expected_counts(self.matrix)
        self.assertEqual(exp, {"pairs": 426, "invocations": 852})

    def test_per_block_pair_counts(self):
        got = Counter(p["block_id"] for p in self.sched["pairs"])
        self.assertEqual(dict(got), BLOCK_PAIRS)

    def test_exactly_one_fingerprint_distinct_from_portability(self):
        fp = self.sched["matrix_fingerprint"]
        self.assertRegex(fp, r"^[0-9a-f]{64}$")
        recomputed = self.VS.campaign_fingerprint(
            self.matrix, self.ids, self.sched["invocations"])
        self.assertEqual(fp, recomputed, "single fingerprint must recompute")
        # distinct from the archived portability campaign fingerprint
        port_matrix = _load_json(os.path.join(OW, "ws2/matrix.portability.json"))
        port_ids = dict(self.ids,
                        run_config_sha256=self.pin["portability_run_config_sha256"])
        port_sched = self.BS.build_campaign_schedule(port_matrix, port_ids)
        self.assertNotEqual(fp, port_sched["matrix_fingerprint"],
                            "ext fingerprint must differ from portability's")

    def test_positions_contiguous_and_pairs_are_baseline_plus_one_target(self):
        inv = self.sched["invocations"]
        positions = sorted(i["schedule_position"] for i in inv)
        self.assertEqual(positions, list(range(1, 853)))
        by_pair = {}
        for i in inv:
            by_pair.setdefault(i["pair_id"], []).append(i)
        self.assertEqual(len(by_pair), 426)
        for pid, arms in by_pair.items():
            self.assertEqual(len(arms), 2, "pair %s must have exactly 2 arms" % pid)
            strategies = sorted(a["strategy"] for a in arms)
            self.assertEqual(strategies.count("baseline"), 1,
                             "pair %s must have exactly one baseline arm" % pid)

    def test_cross_block_union_is_disjoint(self):
        blocks = self.VS.blocks_from_matrix(self.matrix)
        seen = {}
        for b in blocks:
            for cell in self.VS.block_cells(b):
                self.assertNotIn(cell, seen,
                                 "cell %s appears in both %s and %s"
                                 % (cell, seen.get(cell), b["id"]))
                seen[cell] = b["id"]
        self.assertEqual(len(seen), 426)

    def test_no_unintended_cartesian_cells(self):
        allowed = set()
        for b in self.matrix["blocks"]:
            targets = [s for s in b["strategies"] if s != "baseline"]
            for wl in b["workloads"]:
                for t in targets:
                    allowed.add((t, wl))
        got = {(p["target_strategy"], p["workload"]) for p in self.sched["pairs"]}
        self.assertEqual(got, allowed, "unintended target x workload cells present")
        # Concrete guards on the heterogeneity the union protects:
        # C (mixed_20k) has NO N=14 learned cell; layers_92 never on mixed_20k.
        self.assertNotIn(("learned_markov_14", "read_tail_mixed_20k"), got)
        self.assertNotIn(("layers_92", "read_tail_mixed_20k"), got)

    def test_every_keyed_target_cell_resolves_a_frozen_plan(self):
        ksp = self.pin["keyed_strategy_plans"]
        statics = {"layers_92", "layers_5", "2d"}
        for p in self.sched["pairs"]:
            t, wl, seed = p["target_strategy"], p["workload"], p["seed"]
            if t in statics:
                continue  # inline-static, workload/seed independent
            self.assertIn(t, ksp.get(wl, {}).get(str(seed), {}),
                          "no frozen keyed %s plan for %s/s%d" % (t, wl, seed))

    def test_schedule_is_deterministic(self):
        again = self.BS.build_campaign_schedule(self.matrix, self.ids)
        self.assertEqual(again["matrix_fingerprint"], self.sched["matrix_fingerprint"])
        self.assertEqual(again["invocations"], self.sched["invocations"])


# --------------------------------------------------------------------------- D
def _have_live_manifest():
    return os.path.exists(ARTIFACTS)


@unittest.skipUnless(_have_live_manifest(), "live artifacts.json absent")
class ExtActionDispatch(unittest.TestCase):
    """Action-level dispatch over the live manifest: layers_92 resolves as a static
    92-interior selection; the new keyed strategies resolve their per-(workload,seed)
    frozen plan; a keyed cell absent for the exact triple fails closed. No OpenWhisk."""

    @classmethod
    def setUpClass(cls):
        cls.sess = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        reasons = cls.sess.validate_artifacts()
        cls.reasons = tuple(reasons) if reasons else ()
        cls.skeleton = _skeleton_offsets()
        cls.fr = _load_json(FREEZE)["plans"]

    def test_session_validates(self):
        self.assertEqual(self.reasons, (), "validation failed: %s" % (self.reasons,))

    def test_layers_92_is_static_full_skeleton(self):
        # layers_92 is workload/seed independent; it must select exactly the 92
        # interior-skeleton offsets on any workload (same page content as 2d).
        for wl in ("native_ycsb_c_read_zipf", "read_tail_hit_20k"):
            offs = main.select_offsets("layers_92", self.sess, workload=wl, seed=1)
            self.assertEqual(len(offs), 92, "layers_92 must select 92 pages on %s" % wl)
            self.assertEqual(set(offs), self.skeleton,
                             "layers_92 must equal the interior skeleton on %s" % wl)

    def test_new_keyed_strategies_resolve_recorded_counts(self):
        for p in self.fr:
            if p["strategy"] not in KEYED_EXT_STRATEGIES:
                continue
            wl, seed = p["workload_id"], p["seed"]
            plan = self.sess.strategy_plan(p["strategy"], wl, seed)
            self.assertIsNotNone(plan, "no keyed plan %s/%s/s%d"
                                 % (p["strategy"], wl, seed))
            offs = main.select_offsets(p["strategy"], self.sess, workload=wl, seed=seed)
            self.assertEqual(len(offs), p["pages"],
                             "%s/%s/s%d page count" % (p["strategy"], wl, seed))
            interior = sum(1 for o in offs if o in self.skeleton)
            self.assertEqual(interior, p["interior"],
                             "%s/%s/s%d interior split" % (p["strategy"], wl, seed))
            self.assertEqual(len(offs) - interior, p["leaf"],
                             "%s/%s/s%d leaf split" % (p["strategy"], wl, seed))

    def test_ext_keyed_dispatch_fails_closed(self):
        # An ext keyed strategy on a workload it was never frozen for must raise --
        # never fall back. C (mixed_20k) has no N=14 learned cell.
        with self.assertRaises(ValueError):
            main.select_offsets("learned_markov_14", self.sess,
                                workload="read_tail_mixed_20k", seed=1)
        # seed 4 is outside the frozen 1..3 axis for every ext keyed cell.
        with self.assertRaises(ValueError):
            main.select_offsets("2e_K500", self.sess,
                                workload="native_ycsb_c_read_uniform", seed=4)


if __name__ == "__main__":
    unittest.main()
