"""Workstation -> OpenWhisk PORTABILITY-FULL-CLOSURE matrix: the fifth, INDEPENDENT
additive campaign (portability_full_closure, a5be8f15...) that closes the FINAL 16
WS_ONLY cells of the 65-cell canonical portability matrix -- the cells the workstation
ran but NO prior OpenWhisk campaign (primary/secondary/portability/portability_ext)
covered.

Like the earlier portability campaigns this is a DEPLOYMENT/FEASIBILITY + relative-
effectiveness complement, not a new performance campaign; warm paired first-query
latency is NOT a strategy-performance estimate. These tests assert only structural
facts and, crucially, the CLAIM BOUNDARY: this closes CELL coverage (65/65), NOT an
exact replication of every workstation seed/repetition protocol.

The 37 closure plans (source of truth: portability_full_closure_freeze_report.json):

    strategy           workloads (seeds)                         pages   gate
    2e_K40             C(s1), C_hit(s1..3)                       132     92 interior (skeleton set-eq) + 40 leaf
    2e_K92             C(s1), C_hit(s1..3)                       184     92 interior (skeleton set-eq) + 92 leaf
    learned_markov_14  C(s1..3)  (LOSO)                          14      None (emergent split recorded)
    lp_sorted          YC/YCu/YCh01/C_hit(s1..3), C(s1)          ~2f_slru pread_ordered, offset-ascending
    lp_shuf            YC/YCu/YCh01/C_hit(s1..3), C(s1)          ~2f_slru pread_ordered, Random(424242).shuffle

plus ONE static cross-workload deployment check reused from the canonical 92-interior
skeleton: layers_92 x C (seed 1, no new frozen plan; its marker came from the ext layer).

lp is the ordered-delivery mechanism: both arms deliver the SAME resident page set as
the corresponding canonical 2f_slru working set; lp_sorted delivers offset-ascending,
lp_shuf delivers a seed-shuffled order (offset-sort then Random(424242).shuffle). The
offsets are stored IN DELIVERY ORDER, so the plan_sha256 is ORDER-SENSITIVE and the
two arms differ by sequence only. delivery_method=pread_ordered (synchronous page-sized
pread loop IN LIST ORDER) -- never async MADV_WILLNEED. lp's primary quantity is
deliver_us / e2e including delivery, NOT first_query.

Formal execution is ONE single-batch campaign (ws2/matrix.portability_full_closure.json):
the UNION of six heterogeneous BLOCKS (B12-B17) -> 228 pairs -> 456 invocations under
ONE schedule_seed=20260829, ONE run_config_key=portability_full_closure_run_config_sha256
(distinct from primary 022fbeb0..., secondary 441609e6..., portability 64f44c3e..., and
portability_ext bf504a28...), and ONE campaign fingerprint. Nothing is invoked here; WK2
runs the matrix.
"""
import csv
import hashlib
import json
import os
import random
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

import main  # noqa: E402
import residency  # noqa: E402
import session as session_mod  # noqa: E402
import portability_full_closure_manifest as FC  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
ARTIFACTS = os.path.join(OW, "config/artifacts.json")
NATIVE_PIN = os.path.join(OW, "config/artifacts.native_ycsb.json")
FREEZE = os.path.join(OW, "config/plans/keyed/portability_full_closure_freeze_report.json")
SKELETON = os.path.join(OW, "config/plans/interior_pages.csv")
DB = os.path.join(REPO, "pipeline/preparation/layout_rewriter/runs/test.db")
CAMPAIGN_MATRIX = os.path.join(OW, "ws2/matrix.portability_full_closure.json")

# Independent identities: all FOUR prior campaigns MUST remain byte-frozen.
PRIMARY_RC = "022fbeb0"
SECONDARY_RC = "441609e6"
PORTABILITY_RC = "64f44c3e"
EXT_RC = "bf504a28"
CLOSURE_RC = "a5be8f15"

SCHEDULE_SEED_CLOSURE = 20260829
LP_SHUF_SEED = 424242
CLOSURE_WORKLOADS = {
    "native_ycsb_c_hot_hashed_01", "native_ycsb_c_read_uniform",
    "native_ycsb_c_read_zipf", "read_tail_hit_20k", "read_tail_mixed_20k",
}
# The four NEW strategy markers this campaign introduces.
CLOSURE_MARKERS = ("2e_K40", "2e_K92", "lp_sorted", "lp_shuf")
LP_STRATEGIES = ("lp_sorted", "lp_shuf")
SKELETON_UNION_STRATEGIES = ("2e_K40", "2e_K92")
# derived facts (asserted against the freeze report, not the authority)
EXPECTED_BY_STRATEGY = {"2e_K40": 4, "2e_K92": 4, "learned_markov_14": 3,
                        "lp_sorted": 13, "lp_shuf": 13}
EXPECTED_BY_WORKLOAD = {"native_ycsb_c_read_zipf": 6, "native_ycsb_c_read_uniform": 6,
                        "native_ycsb_c_hot_hashed_01": 6, "read_tail_hit_20k": 12,
                        "read_tail_mixed_20k": 7}
BLOCK_PAIRS = {"block12": 12, "block13": 36, "block14": 18,
               "block15": 6, "block16": 144, "block17": 12}
EXPECTED_TOTAL_PAIRS = 228
EXPECTED_TOTAL_INVOCATIONS = 456


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
    """Offsets IN FILE ORDER (order-preserving -- lp plans are order-sensitive)."""
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
class ClosureFreezeReportParity(unittest.TestCase):
    """Every one of the 37 closure plans is on disk, sha-bound, its recorded native
    source is sha-bound, and its interior/leaf split -- recomputed against the 92-page
    skeleton -- equals the recorded value. lp plans are checked ORDER-SENSITIVELY. The
    freeze report is the ONLY source; no strategy selection happens here."""

    @classmethod
    def setUpClass(cls):
        cls.fr = _load_json(FREEZE)
        cls.plans = cls.fr["plans"]
        cls.skeleton = _skeleton_offsets()
        cls.by_key = {(p["strategy"], p["workload_id"], p["seed"]): p for p in cls.plans}

    def test_bound_db_and_skeleton(self):
        self.assertEqual(len(self.skeleton), 92)
        self.assertEqual(self.fr["bound_db_sha256"],
                         "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1")

    def test_exactly_37_plans_over_expected_axes(self):
        self.assertEqual(len(self.plans), 37)
        triples = {(p["strategy"], p["workload_id"], p["seed"]) for p in self.plans}
        self.assertEqual(len(triples), 37, "duplicate (strategy,workload,seed)")
        for p in self.plans:
            self.assertIn(p["workload_id"], CLOSURE_WORKLOADS)
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
                             "plan sha mismatch %s (order-sensitive)" % p["plan_path"])
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
            self.assertIn("native_source/portability_full_closure/", copy_rel,
                          "durable copy must live under the closure native_source tree")

    def test_2e_kN_is_skeleton_union_bounded_leaf(self):
        # 2e_K40/2e_K92 carry the FULL 92-interior skeleton (set-equality) UNION the
        # native top-<=K hot leaves -- exactly the 2e_K500 reconstruct contract.
        for strat, kbud in (("2e_K40", 40), ("2e_K92", 92)):
            e = [p for p in self.plans if p["strategy"] == strat]
            self.assertEqual(len(e), 4, "%s must cover C(1) + C_hit(3)" % strat)
            for p in e:
                path = os.path.join(REPO, p["plan_path"])
                offs = _plan_offsets(path)
                interior = {o for o in offs if o in self.skeleton}
                self.assertEqual(interior, self.skeleton,
                                 "%s interior half must equal the 92-skeleton" % p["plan_path"])
                self.assertEqual(p["interior"], 92)
                self.assertLessEqual(p["leaf"], kbud, "%s leaf budget <= %d" % (strat, kbud))

    def test_learned_markov_14_is_loso_with_disjoint_train_test(self):
        lm = [p for p in self.plans if p["strategy"] == "learned_markov_14"]
        self.assertEqual(len(lm), 3, "C learned_markov_14 folds 1,2,3")
        for p in lm:
            self.assertEqual(p["pages"], 14, "%s must be an N=14 selection" % p["plan_path"])
            loso = p["loso"]
            self.assertIsNotNone(loso, "learned_markov_14 must carry LOSO provenance")
            self.assertEqual(loso["test_seed"], p["seed"])
            self.assertNotIn(p["seed"], loso["train_seeds"],
                             "%s: leakage -- test seed present in train set" % p["plan_path"])

    # ---- lp ordered-delivery semantics (the heart of the closure) --------------
    def _lp_pair(self, wl, seed):
        so = self.by_key[("lp_sorted", wl, seed)]
        sh = self.by_key[("lp_shuf", wl, seed)]
        so_offs = _plan_offsets(os.path.join(REPO, so["plan_path"]))
        sh_offs = _plan_offsets(os.path.join(REPO, sh["plan_path"]))
        return so, sh, so_offs, sh_offs

    def _lp_cells(self):
        return sorted({(p["workload_id"], p["seed"]) for p in self.plans
                       if p["strategy"] == "lp_sorted"})

    def test_lp_sorted_and_shuf_deliver_the_same_page_set(self):
        for wl, seed in self._lp_cells():
            _so, _sh, so_offs, sh_offs = self._lp_pair(wl, seed)
            self.assertEqual(set(so_offs), set(sh_offs),
                             "lp_sorted/lp_shuf must deliver the SAME page set (%s/s%d)"
                             % (wl, seed))
            self.assertEqual(len(so_offs), len(sh_offs))

    def test_lp_sorted_is_strictly_ascending(self):
        for wl, seed in self._lp_cells():
            _so, _sh, so_offs, _sh_offs = self._lp_pair(wl, seed)
            self.assertEqual(so_offs, sorted(so_offs),
                             "lp_sorted must be file_offset-ascending (%s/s%d)" % (wl, seed))
            self.assertEqual(len(so_offs), len(set(so_offs)), "strictly (no dups)")

    def test_lp_shuf_reproduces_seed_424242(self):
        # The frozen lp_shuf order == offset-sort(pages) then Random(424242).shuffle.
        for wl, seed in self._lp_cells():
            _so, _sh, so_offs, sh_offs = self._lp_pair(wl, seed)
            repro = list(sorted(set(so_offs)))
            random.Random(LP_SHUF_SEED).shuffle(repro)
            self.assertEqual(sh_offs, repro,
                             "lp_shuf order must reproduce Random(424242).shuffle (%s/s%d)"
                             % (wl, seed))

    def test_lp_ordered_plan_sha_is_order_sensitive(self):
        # Same unordered set, DIFFERENT ordered sequence -> DIFFERENT plan sha.
        for wl, seed in self._lp_cells():
            so, sh, so_offs, sh_offs = self._lp_pair(wl, seed)
            self.assertNotEqual(so_offs, sh_offs,
                                "sorted vs shuffled sequences must differ (%s/s%d)" % (wl, seed))
            self.assertNotEqual(so["plan_sha256"], sh["plan_sha256"],
                                "order-sensitive sha must differ (%s/s%d)" % (wl, seed))

    def test_lp_delivery_metadata_recorded(self):
        for p in self.plans:
            if p["strategy"] not in LP_STRATEGIES:
                continue
            self.assertEqual(p["delivery_order"],
                             "file_offset_ascending" if p["strategy"] == "lp_sorted"
                             else "seed_shuffled")
            self.assertIn("lp", p)
            self.assertEqual(p["lp"]["delivery_method"], "pread_ordered")


# --------------------------------------------------------------------------- B
class ClosurePinParityAndIdentity(unittest.TestCase):
    """The pin gained EXACTLY the 37 closure triples + 4 markers + the closure
    top-level identity -- additively -- and ALL FOUR prior identities are byte-
    untouched. The closure run-config recomputes deterministically and is independent
    of every prior identity."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)
        cls.fr = {(p["strategy"], p["workload_id"], p["seed"]): p
                  for p in _load_json(FREEZE)["plans"]}

    def test_all_four_prior_identities_untouched(self):
        self.assertTrue(self.pin["run_config_sha256"].startswith(PRIMARY_RC))
        self.assertTrue(self.pin["secondary_run_config_sha256"].startswith(SECONDARY_RC))
        self.assertTrue(self.pin["portability_run_config_sha256"].startswith(PORTABILITY_RC))
        self.assertTrue(self.pin["portability_ext_run_config_sha256"].startswith(EXT_RC))

    def test_closure_identity_present_and_distinct(self):
        rc = self.pin["portability_full_closure_run_config_sha256"]
        self.assertTrue(rc.startswith(CLOSURE_RC))
        for prior in ("run_config_sha256", "secondary_run_config_sha256",
                      "portability_run_config_sha256", "portability_ext_run_config_sha256"):
            self.assertNotEqual(rc, self.pin[prior])

    def test_thirty_seven_closure_triples_present_with_recorded_counts(self):
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
        self.assertEqual(found, 37)

    def test_lp_pin_entries_declare_pread_ordered(self):
        ksp = self.pin["keyed_strategy_plans"]
        for (strat, wl, seed), _fp in self.fr.items():
            if strat not in LP_STRATEGIES:
                continue
            e = ksp[wl][str(seed)][strat]
            self.assertEqual(e["delivery_method"], "pread_ordered",
                             "lp pin entry must be pread_ordered, never madvise_willneed")
            self.assertEqual(e["shuffle_seed"],
                             LP_SHUF_SEED if strat == "lp_shuf" else None)

    def test_markers_present_for_new_strategies(self):
        for s in CLOSURE_MARKERS:
            self.assertIn(s, self.pin["strategy_plans"], "marker %s absent" % s)
        for s in LP_STRATEGIES:
            self.assertEqual(self.pin["strategy_plans"][s]["delivery_method"],
                             "pread_ordered")

    def test_closure_run_config_sha256_recomputes(self):
        plan = self.pin["portability_full_closure_invocation_plan"]
        blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        recomputed = hashlib.sha256(blob.encode()).hexdigest()
        self.assertEqual(recomputed, self.pin["portability_full_closure_run_config_sha256"],
                         "closure run_config_sha256 does not recompute from its plan")

    def test_closure_plan_declares_228_pairs_456_invocations(self):
        plan = self.pin["portability_full_closure_invocation_plan"]
        self.assertEqual(plan["total_pairs"], EXPECTED_TOTAL_PAIRS)
        self.assertEqual(plan["total_invocations"], EXPECTED_TOTAL_INVOCATIONS)
        self.assertEqual(plan["schedule_seed"], SCHEDULE_SEED_CLOSURE)

    def test_closure_workloads_within_frozen_workload_set(self):
        wls = set(self.pin["workload_set"])
        for wl in EXPECTED_BY_WORKLOAD:
            self.assertIn(wl, wls, "closure workload %s not in frozen workload_set" % wl)


# --------------------------------------------------------------------------- C
class ClosureCampaignSingleBatch(unittest.TestCase):
    """THE formal-execution unit: ws2/matrix.portability_full_closure.json flattens the
    six blocks (B12-B17) into ONE ordered 456-invocation schedule under ONE campaign
    fingerprint. Proves single-batch counts (228/456, per-block 12/36/18/6/144/12),
    exactly one fingerprint distinct from BOTH the portability and the portability_ext
    fingerprints, disjoint union, no unintended cells, every keyed target resolves a
    frozen plan, static seeds stay [1], and determinism. No OpenWhisk is invoked."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(OW, "client"))
        import build_schedule as BS
        import validate_schedule as VS
        cls.BS, cls.VS = BS, VS
        cls.pin = _load_json(NATIVE_PIN)
        cls.matrix = _load_json(CAMPAIGN_MATRIX)
        cls.ids = {"run_config_sha256": cls.pin["portability_full_closure_run_config_sha256"],
                   "artifact_manifest_sha256": "0" * 64,
                   "action_image_digest": "sha256:portability-full-closure-test"}
        cls.sched = cls.BS.build_campaign_schedule(cls.matrix, cls.ids)

    def test_matrix_is_one_campaign_with_six_blocks(self):
        m = self.matrix
        self.assertIn("blocks", m, "campaign matrix must be block-union shaped")
        self.assertEqual(m["schedule_seed"], SCHEDULE_SEED_CLOSURE)
        self.assertEqual(m["run_config_key"], "portability_full_closure_run_config_sha256")
        self.assertEqual([b["id"] for b in m["blocks"]], list(BLOCK_PAIRS.keys()))

    def test_static_block_keeps_seed_one(self):
        by_id = {b["id"]: b for b in self.matrix["blocks"]}
        self.assertEqual(by_id["block15"]["seeds"], [1],
                         "structural layers_92 block must not expand seeds")
        self.assertEqual([s for s in by_id["block15"]["strategies"] if s != "baseline"],
                         ["layers_92"])

    def test_campaign_self_validates_clean(self):
        problems = self.VS.validate_campaign(self.sched, self.matrix)
        self.assertEqual(problems, [], "campaign validation problems: %s" % problems)

    def test_counts_are_exactly_228_456_from_validator(self):
        self.assertEqual(self.sched["counts"],
                         {"pairs": EXPECTED_TOTAL_PAIRS, "invocations": EXPECTED_TOTAL_INVOCATIONS})
        self.assertEqual(len(self.sched["pairs"]), EXPECTED_TOTAL_PAIRS)
        self.assertEqual(len(self.sched["invocations"]), EXPECTED_TOTAL_INVOCATIONS)
        exp = self.VS.campaign_expected_counts(self.matrix)
        self.assertEqual(exp, {"pairs": EXPECTED_TOTAL_PAIRS,
                               "invocations": EXPECTED_TOTAL_INVOCATIONS})

    def test_per_block_pair_counts(self):
        got = Counter(p["block_id"] for p in self.sched["pairs"])
        self.assertEqual(dict(got), BLOCK_PAIRS)

    def test_one_fingerprint_distinct_from_portability_and_ext(self):
        fp = self.sched["matrix_fingerprint"]
        self.assertRegex(fp, r"^[0-9a-f]{64}$")
        recomputed = self.VS.campaign_fingerprint(
            self.matrix, self.ids, self.sched["invocations"])
        self.assertEqual(fp, recomputed, "single fingerprint must recompute")
        for other_matrix, other_key in (
                ("ws2/matrix.portability.json", "portability_run_config_sha256"),
                ("ws2/matrix.portability_ext.json", "portability_ext_run_config_sha256")):
            om = _load_json(os.path.join(OW, other_matrix))
            oids = dict(self.ids, run_config_sha256=self.pin[other_key])
            osched = self.BS.build_campaign_schedule(om, oids)
            self.assertNotEqual(fp, osched["matrix_fingerprint"],
                                "closure fingerprint must differ from %s" % other_matrix)

    def test_positions_contiguous_and_pairs_are_baseline_plus_one_target(self):
        inv = self.sched["invocations"]
        positions = sorted(i["schedule_position"] for i in inv)
        self.assertEqual(positions, list(range(1, EXPECTED_TOTAL_INVOCATIONS + 1)))
        by_pair = {}
        for i in inv:
            by_pair.setdefault(i["pair_id"], []).append(i)
        self.assertEqual(len(by_pair), EXPECTED_TOTAL_PAIRS)
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
        self.assertEqual(len(seen), EXPECTED_TOTAL_PAIRS)

    def test_no_unintended_cartesian_cells(self):
        allowed = set()
        for b in self.matrix["blocks"]:
            targets = [s for s in b["strategies"] if s != "baseline"]
            for wl in b["workloads"]:
                for t in targets:
                    allowed.add((t, wl))
        got = {(p["target_strategy"], p["workload"]) for p in self.sched["pairs"]}
        self.assertEqual(got, allowed, "unintended target x workload cells present")
        # concrete heterogeneity guards: lp on all five; 2e_K40/K92 only on C/C_hit;
        # learned_markov_14 & layers_92 only on C.
        self.assertIn(("lp_sorted", "native_ycsb_c_read_zipf"), got)
        self.assertNotIn(("2e_K40", "native_ycsb_c_read_zipf"), got)
        self.assertNotIn(("learned_markov_14", "read_tail_hit_20k"), got)
        self.assertNotIn(("lp_sorted", "read_tail_mixed_20k"),  # C has lp on seed 1 only
                         {(t, wl) for (t, wl) in got} - {("lp_sorted", "read_tail_mixed_20k")})

    def test_every_keyed_target_cell_resolves_a_frozen_plan(self):
        ksp = self.pin["keyed_strategy_plans"]
        statics = {"layers_92"}
        for p in self.sched["pairs"]:
            t, wl, seed = p["target_strategy"], p["workload"], p["seed"]
            if t in statics:
                continue
            self.assertIn(t, ksp.get(wl, {}).get(str(seed), {}),
                          "no frozen keyed %s plan for %s/s%d" % (t, wl, seed))

    def test_schedule_is_deterministic(self):
        again = self.BS.build_campaign_schedule(self.matrix, self.ids)
        self.assertEqual(again["matrix_fingerprint"], self.sched["matrix_fingerprint"])
        self.assertEqual(again["invocations"], self.sched["invocations"])


# --------------------------------------------------------------------------- D
class ClosureLpRuntimeSupport(unittest.TestCase):
    """The lp ordered-delivery mechanism exists in the action and is confined to the
    two lp strategies. Every OTHER strategy keeps async MADV_WILLNEED delivery."""

    def test_pread_ordered_strategy_set_is_exactly_lp(self):
        self.assertEqual(tuple(main.PREAD_ORDERED_STRATEGIES), LP_STRATEGIES)
        self.assertEqual(main.LP_SHUF_SEED, LP_SHUF_SEED)

    def test_non_lp_strategies_are_not_pread_ordered(self):
        # existing strategies retain their existing (madvise_willneed) delivery
        for s in main.SUPPORTED_STRATEGIES:
            if s in LP_STRATEGIES:
                continue
            self.assertNotIn(s, main.PREAD_ORDERED_STRATEGIES,
                             "%s must keep madvise_willneed delivery" % s)

    def test_pagemap_exposes_deliver_pread_ordered(self):
        self.assertTrue(hasattr(residency.PageMap, "deliver_pread_ordered"))
        self.assertTrue(hasattr(residency.PageMap, "deliver_willneed"),
                        "the willneed path must still exist for every other strategy")

    @unittest.skipUnless(os.path.exists(DB), "reference DB missing")
    def test_deliver_pread_ordered_delivers_in_order_and_counts_bytes(self):
        offs = [p * residency.PAGE for p in range(1, 9)]  # 8 valid page offsets
        pm = residency.PageMap(DB)
        try:
            delivered, delivered_bytes = pm.deliver_pread_ordered(offs)
        finally:
            pm.close()
        self.assertEqual(delivered, len(offs))
        self.assertEqual(delivered_bytes, len(offs) * residency.PAGE)

    @unittest.skipUnless(os.path.exists(DB), "reference DB missing")
    def test_deliver_pread_ordered_fails_closed_on_bad_offset(self):
        pm = residency.PageMap(DB)
        try:
            with self.assertRaises((OSError, ValueError)):
                pm.deliver_pread_ordered([3])  # misaligned (not a page multiple)
        finally:
            pm.close()


# --------------------------------------------------------------------------- E
def _have_live_manifest():
    return os.path.exists(ARTIFACTS)


@unittest.skipUnless(_have_live_manifest(), "live artifacts.json absent")
class ClosureActionDispatch(unittest.TestCase):
    """Action-level dispatch over the live manifest: the new keyed strategies resolve
    their per-(workload,seed) frozen plan with the recorded split; lp offsets come back
    IN DELIVERY ORDER (sorted ascending for lp_sorted; the frozen shuffle for lp_shuf);
    2e_K40/2e_K92 resolve the 92-interior union; a cell absent for the exact triple
    fails closed. No OpenWhisk is invoked."""

    @classmethod
    def setUpClass(cls):
        cls.sess = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        reasons = cls.sess.validate_artifacts()
        cls.reasons = tuple(reasons) if reasons else ()
        cls.skeleton = _skeleton_offsets()
        cls.fr = _load_json(FREEZE)["plans"]
        cls.by_key = {(p["strategy"], p["workload_id"], p["seed"]): p for p in cls.fr}

    def test_session_validates(self):
        self.assertEqual(self.reasons, (), "validation failed: %s" % (self.reasons,))

    def test_new_keyed_strategies_resolve_recorded_counts(self):
        for p in self.fr:
            wl, seed, strat = p["workload_id"], p["seed"], p["strategy"]
            offs = main.select_offsets(strat, self.sess, workload=wl, seed=seed)
            self.assertEqual(len(offs), p["pages"],
                             "%s/%s/s%d page count" % (strat, wl, seed))
            interior = sum(1 for o in offs if o in self.skeleton)
            self.assertEqual(interior, p["interior"],
                             "%s/%s/s%d interior split" % (strat, wl, seed))
            self.assertEqual(len(offs) - interior, p["leaf"],
                             "%s/%s/s%d leaf split" % (strat, wl, seed))

    def test_2e_kN_resolve_full_skeleton_union(self):
        for strat in SKELETON_UNION_STRATEGIES:
            for p in [q for q in self.fr if q["strategy"] == strat]:
                offs = main.select_offsets(strat, self.sess,
                                           workload=p["workload_id"], seed=p["seed"])
                interior = {o for o in offs if o in self.skeleton}
                self.assertEqual(interior, self.skeleton,
                                 "%s must resolve the full 92-skeleton" % strat)

    def test_lp_offsets_dispatch_in_delivery_order(self):
        # select_offsets returns keyed offsets IN PLAN ORDER -> the exact pread order.
        for p in self.fr:
            if p["strategy"] not in LP_STRATEGIES:
                continue
            wl, seed = p["workload_id"], p["seed"]
            offs = main.select_offsets(p["strategy"], self.sess, workload=wl, seed=seed)
            if p["strategy"] == "lp_sorted":
                self.assertEqual(offs, sorted(offs),
                                 "lp_sorted must dispatch offset-ascending (%s/s%d)" % (wl, seed))
            else:
                repro = list(sorted(set(offs)))
                random.Random(LP_SHUF_SEED).shuffle(repro)
                self.assertEqual(offs, repro,
                                 "lp_shuf must dispatch the frozen shuffle (%s/s%d)" % (wl, seed))
            # sorted and shuffled arms carry the SAME page set
            other = "lp_shuf" if p["strategy"] == "lp_sorted" else "lp_sorted"
            other_offs = main.select_offsets(other, self.sess, workload=wl, seed=seed)
            self.assertEqual(set(offs), set(other_offs))

    def test_closure_keyed_dispatch_fails_closed(self):
        # 2e_K40 was never frozen on YC; a seed outside 1..3 is absent everywhere.
        with self.assertRaises(ValueError):
            main.select_offsets("2e_K40", self.sess,
                                workload="native_ycsb_c_read_zipf", seed=1)
        with self.assertRaises(ValueError):
            main.select_offsets("lp_sorted", self.sess,
                                workload="native_ycsb_c_read_zipf", seed=4)


# --------------------------------------------------------------------------- F
class ClosureCoverageAudit(unittest.TestCase):
    """The WS-denominator coverage audit AFTER the closure executed: 65 canonical cells,
    ALL 65 now executed BOTH, zero WS_ONLY gaps, exactly 4 OW_ONLY; the closure campaign
    targeted exactly the 16 formerly-WS_ONLY cells and they are all now in BOTH. Claim
    boundary: this is CELL coverage, NOT protocol/layout/performance replication. Also
    pins C/2e_K500's canonical source to unified_v2 (corrected §4.4 provenance,
    unchanged by this closure)."""

    @classmethod
    def setUpClass(cls):
        import full_matrix_gap_audit as GAP
        cls.GAP = GAP

    def test_denominator_and_partition(self):
        # closure executed: BOTH is now the full matrix, no WS_ONLY gap remains
        self.assertTrue(self.GAP.CLOSURE_EXECUTED)
        self.assertEqual(len(self.GAP.WS_CELLS), 65)
        self.assertEqual(len(self.GAP.BOTH), 65)
        self.assertEqual(len(self.GAP.WS_ONLY), 0)
        self.assertEqual(len(self.GAP.OW_ONLY), 4)

    def test_planned_closure_covers_exactly_the_gap(self):
        # the closure targeted 16 cells; post-execution every one is in BOTH
        self.assertEqual(len(self.GAP.PLANNED_CLOSURE), 16)
        self.assertTrue(self.GAP.PLANNED_CLOSURE <= self.GAP.BOTH,
                        "every planned closure cell must now be executed BOTH")
        self.assertEqual(self.GAP.BOTH, self.GAP.WS_CELLS,
                         "executed BOTH must span the full 65-cell matrix")
        self.assertEqual(self.GAP.WS_ONLY, set(),
                         "no WS_ONLY gap may remain after closure")

    def test_executed_both_is_full_65(self):
        # Claim boundary: executed coverage is now 65/65 (cell coverage only). This test
        # guards against silently regressing the executed count below the full matrix.
        self.assertEqual(len(self.GAP.BOTH), 65)
        self.assertEqual(len(self.GAP.WS_CELLS), 65)

    def test_c_2e_k500_sourced_from_unified_v2(self):
        self.assertEqual(self.GAP.WS[("C", "2e_K500")]["source_batch"], "unified_v2/matrix")


# --------------------------------------------------------------------------- G
class PriorFreezeReportsUntouched(unittest.TestCase):
    """The closure layer must not perturb the prior freeze reports: portability stays
    36 plans, portability_ext stays 63. (Identity byte-freeze is proven in class B.)"""

    def test_portability_freeze_still_36(self):
        fr = _load_json(os.path.join(OW, "config/plans/keyed/portability_freeze_report.json"))
        self.assertEqual(len(fr["plans"]), 36)

    def test_portability_ext_freeze_still_63(self):
        fr = _load_json(os.path.join(OW, "config/plans/keyed/portability_ext_freeze_report.json"))
        self.assertEqual(len(fr["plans"]), 63)


# --------------------------------------------------------------------------- H
class ClosureExecutedEvidenceGates(unittest.TestCase):
    """The ARCHIVED, EXECUTED closure evidence (normalized + descriptive) must gate to
    the frozen single-batch identity: bundle SHA == sidecar; 456/228; B12-B17; the LIVE
    schedule fingerprint d35708b7...; run_config a5be8f15...; and run-config isolation
    from all four prior campaigns. Descriptive parity: 38 target plans (37 keyed +
    layers_92 static), lp delivered via pread_ordered only. Fail-closed: any drift here
    means the evidence and the framing have diverged."""

    NORM_DIR = os.path.join(OW, "analysis/normalized/portability_full_closure")
    DESC_DIR = os.path.join(OW, "analysis/descriptive/portability_full_closure")
    LIVE_FINGERPRINT = \
        "d35708b781f29c0609da6f702b5e11599e10aff5d16a0c5fa1aa0253d079f0ec"
    RUN_CONFIG = \
        "a5be8f150bc87182d3a158ff580b83a04073a84ff258cde07d78a73e35f60faf"
    BUNDLE_SHA = \
        "c8ef0cbe16c3b8e09aa501d90991fc7197c6014119b6b880d087b498e0011dd1"

    @classmethod
    def setUpClass(cls):
        cls.norm = _load_json(os.path.join(
            cls.NORM_DIR, "portability_full_closure_normalization_manifest.json"))
        cls.desc = _load_json(os.path.join(
            cls.DESC_DIR, "portability_full_closure_descriptive_manifest.json"))

    def test_normalization_ok_and_counts(self):
        self.assertTrue(self.norm["ok"])
        self.assertEqual(self.norm["counts"]["invocations"], EXPECTED_TOTAL_INVOCATIONS)
        self.assertEqual(self.norm["counts"]["pairs"], EXPECTED_TOTAL_PAIRS)
        self.assertEqual(self.norm["counts"]["baseline"], EXPECTED_TOTAL_PAIRS)
        self.assertEqual(self.norm["counts"]["target"], EXPECTED_TOTAL_PAIRS)

    def test_block_pairs_are_B12_to_B17(self):
        self.assertEqual(self.norm["block_pairs"], BLOCK_PAIRS)

    def test_live_fingerprint_and_run_config(self):
        self.assertEqual(self.norm["matrix_fingerprint"], self.LIVE_FINGERPRINT)
        self.assertEqual(self.norm["authoritative_run_config_sha256"], self.RUN_CONFIG)

    def test_bundle_sha_matches_sidecar(self):
        self.assertEqual(self.norm["source_bundle_sha256"], self.BUNDLE_SHA)
        self.assertEqual(self.norm["source_bundle_sha256_sidecar"], self.BUNDLE_SHA)

    def test_run_config_isolated_from_all_prior_campaigns(self):
        rc = self.norm["authoritative_run_config_sha256"]
        for prior in (PRIMARY_RC, SECONDARY_RC, PORTABILITY_RC, EXT_RC):
            self.assertFalse(rc.startswith(prior),
                             "closure run_config must not collide with %s" % prior)
        self.assertTrue(rc.startswith(CLOSURE_RC))

    def test_descriptive_plan_taxonomy(self):
        # 38 = 37 keyed + layers_92 static; lp (26) via pread_ordered, rest willneed
        self.assertEqual(self.desc["distinct_target_plans"], 38)
        self.assertEqual(self.desc["workloads"], 5)
        self.assertEqual(self.desc["parity_type_counts"],
                         {"exact_native_plan": 29,
                          "semantic_contract_reconstruction": 8,
                          "structural_static": 1})
        self.assertEqual(self.desc["delivery_method_counts"],
                         {"pread_ordered": 26, "madvise_willneed": 12})

    def test_synthesis_loader_gates_clean(self):
        import synthesis as S
        facts, problems = S.load_portability_full_closure()
        self.assertIsNotNone(facts, "closure facts must load")
        self.assertEqual(problems, [], "SHA/chain/shape gates must be clean")
        self.assertEqual(facts["invocations"], EXPECTED_TOTAL_INVOCATIONS)
        self.assertEqual(facts["pairs"], EXPECTED_TOTAL_PAIRS)
        self.assertEqual(facts["run_config_sha256"], self.RUN_CONFIG)


if __name__ == "__main__":
    unittest.main()
