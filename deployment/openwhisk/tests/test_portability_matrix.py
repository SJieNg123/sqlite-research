"""Workstation -> OpenWhisk PORTABILITY matrix (Batch 4): the deployment-complement
matrix that carries the frozen native strategies onto four additional workloads plus
the two budget-matched YC ranked competitors, under an INDEPENDENT run-config identity.

This is a DEPLOYMENT/FEASIBILITY + footprint complement, not a new performance campaign.
Warm paired first-query latency is NOT a strategy-performance estimate (page-cache
carryover was falsified; the effect is positional/order). See the WS2 runbook /
OpenWhisk README interpretation note. These tests assert only structural facts:
frozen-plan parity, additive pin identity, fail-closed multi-workload dispatch, and an
exactly-234-pair / 468-invocation balanced schedule.

The 36 portability plans (source of truth: config/plans/keyed/portability_freeze_report.json):

    strategy           workloads (seeds 1..3)                          pages  interior gate
    2e_K10             uniform, hot01, hit_20k, mixed_20k              102    92 (skeleton set-eq)
    2f_slru            uniform, hot01, hit_20k, mixed_20k              emergent  eip (92 or 4/5)
    2f_top28           read_zipf                                       28     None (26/2 recorded)
    learned_markov_28  read_zipf (LOSO)                                28     None (26/2 recorded)
    leaf_freq_K10      mixed_20k                                       10     0 (leaf-only)
    leaf_rand_K10      mixed_20k                                       10     0 (leaf-only)

4 rectangular sub-matrices -> 234 pairs -> 468 invocations, schedule_seed=20260826,
run_config_key=portability_run_config_sha256 (distinct from the byte-frozen primary
022fbeb0... and secondary 441609e6... identities).
"""
import csv
import json
import os
import sys
import unittest

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
FREEZE = os.path.join(OW, "config/plans/keyed/portability_freeze_report.json")
SKELETON = os.path.join(OW, "config/plans/interior_pages.csv")
GATE_SCRIPT = os.path.join(OW, "ws2/05_full_matrix.sh")
MATRIX_FILES = [os.path.join(OW, "ws2/matrix.portability.m%d.json" % i)
                for i in (1, 2, 3, 4)]

# Independent identities (byte-frozen campaigns MUST remain these).
PRIMARY_RC = "022fbeb0"
SECONDARY_RC = "441609e6"

NEW_STRATEGIES = ("2f_top28", "learned_markov_28")
PORTABILITY_WORKLOADS = {
    "native_ycsb_c_hot_hashed_01", "native_ycsb_c_read_uniform",
    "native_ycsb_c_read_zipf", "read_tail_hit_20k", "read_tail_mixed_20k",
}
LEAF_ONLY = ("leaf_freq_K10", "leaf_rand_K10")


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
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- A
class FreezeReportParity(unittest.TestCase):
    """Every one of the 36 frozen plans is on disk, sha-bound, and its interior/leaf
    split -- recomputed against the 92-page skeleton -- equals the recorded value.
    The freeze report is the ONLY source; no strategy selection happens here."""

    @classmethod
    def setUpClass(cls):
        cls.fr = _load_json(FREEZE)
        cls.plans = cls.fr["plans"]
        cls.skeleton = _skeleton_offsets()

    def test_bound_db_and_skeleton(self):
        self.assertEqual(len(self.skeleton), 92)
        self.assertEqual(self.fr["bound_db_sha256"],
                         "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1")

    def test_exactly_36_plans_over_expected_axes(self):
        self.assertEqual(len(self.plans), 36)
        triples = {(p["strategy"], p["workload_id"], p["seed"]) for p in self.plans}
        self.assertEqual(len(triples), 36, "duplicate (strategy,workload,seed)")
        for p in self.plans:
            self.assertIn(p["workload_id"], PORTABILITY_WORKLOADS)
            self.assertIn(p["seed"], (1, 2, 3))

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

    def test_leaf_only_strategies_have_zero_interior(self):
        for p in self.plans:
            if p["strategy"] in LEAF_ONLY:
                self.assertEqual(p["interior"], 0, "%s must be leaf-only" % p["plan_path"])
                self.assertEqual(p["leaf"], 10)
                self.assertEqual(p["pages"], 10)

    def test_2e_k10_is_reconstructed_102_skeleton_union_ten(self):
        e = [p for p in self.plans if p["strategy"] == "2e_K10"]
        self.assertEqual(len(e), 12)  # 4 workloads x 3 seeds
        for p in e:
            self.assertTrue(p["reconstructed"], "2e_K10 must be flagged reconstructed")
            self.assertEqual((p["pages"], p["interior"], p["leaf"]), (102, 92, 10))

    def test_learned_markov_is_loso(self):
        lm = [p for p in self.plans if p["strategy"] == "learned_markov_28"]
        self.assertEqual(len(lm), 3)
        for p in lm:
            self.assertTrue(p["loso"], "learned_markov_28 must carry LOSO provenance")
            self.assertEqual(p["pages"], 28)


# --------------------------------------------------------------------------- B
class PinParityAndIdentity(unittest.TestCase):
    """The pin gained EXACTLY the 36 keyed triples + the 2 markers + the portability
    top-level blocks -- additively -- and the frozen primary/secondary identities are
    untouched. The portability run-config identity recomputes deterministically and is
    independent."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _load_json(NATIVE_PIN)
        cls.fr = {(p["strategy"], p["workload_id"], p["seed"]): p
                  for p in _load_json(FREEZE)["plans"]}

    def test_frozen_identities_untouched(self):
        self.assertTrue(self.pin["run_config_sha256"].startswith(PRIMARY_RC))
        self.assertTrue(self.pin["secondary_run_config_sha256"].startswith(SECONDARY_RC))

    def test_workload_set_is_the_five(self):
        self.assertEqual(set(self.pin["workload_set"]), PORTABILITY_WORKLOADS)
        self.assertEqual(len(self.pin["workload_set"]), 5)

    def test_thirty_six_portability_triples_present_with_recorded_counts(self):
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
        self.assertEqual(found, 36)

    def test_markers_present_for_new_strategies(self):
        for s in NEW_STRATEGIES:
            self.assertIn(s, self.pin["strategy_plans"], "marker %s absent" % s)

    def test_portability_run_config_sha256_recomputes(self):
        import hashlib
        plan = self.pin["portability_invocation_plan"]
        blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        recomputed = hashlib.sha256(blob.encode()).hexdigest()
        self.assertEqual(recomputed, self.pin["portability_run_config_sha256"],
                         "portability_run_config_sha256 does not recompute from its plan")

    def test_portability_identity_is_distinct(self):
        rc = self.pin["portability_run_config_sha256"]
        self.assertNotEqual(rc, self.pin["run_config_sha256"])
        self.assertNotEqual(rc, self.pin["secondary_run_config_sha256"])

    def test_plan_declares_234_pairs_468_invocations(self):
        plan = self.pin["portability_invocation_plan"]
        self.assertEqual(plan["total_pairs"], 234)
        self.assertEqual(plan["total_invocations"], 468)
        self.assertEqual(plan["schedule_seed"], 20260826)


# --------------------------------------------------------------------------- C
class ScheduleBalance(unittest.TestCase):
    """The four matrix manifests build into strictly rectangular, per-cell-balanced
    schedules whose totals sum to EXACTLY 234 pairs / 468 invocations. Every
    (workload, seed, target) has a keyed plan (2d excepted -- it is inline-static).
    No OpenWhisk is invoked."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(OW, "client"))
        sys.path.insert(0, os.path.join(REPO, "config"))
        import build_schedule as BS
        import validate_schedule as VS
        cls.BS, cls.VS = BS, VS
        cls.pin = _load_json(NATIVE_PIN)
        cls.ids = {"run_config_sha256": cls.pin["portability_run_config_sha256"],
                   "artifact_manifest_sha256": "0" * 64,
                   "action_image_digest": "sha256:portability-test"}

    def _build(self, mf):
        m = _load_json(mf)
        contract = self.VS.contract_from_matrix(m)
        wls = [self.VS.normalize_workload_id(w) for w in m["workloads"]]
        targets = [s for s in m["strategies"] if s != "baseline"]
        sched = self.BS.build_schedule(
            wls, m["seeds"], m["first_operation_ids"], m["handle_modes"],
            targets, m["repetitions_per_cell"], m["schedule_seed"], self.ids)
        return m, contract, wls, targets, sched

    def test_each_matrix_balances_and_aggregate_is_234_468(self):
        total_pairs = total_inv = 0
        fingerprints = set()
        for mf in MATRIX_FILES:
            m, contract, wls, targets, sched = self._build(mf)
            problems = self.VS.validate_schedule(sched, contract)
            self.assertEqual(problems, [], "%s: %s" % (os.path.basename(mf), problems))
            self.assertEqual(m["schedule_seed"], 20260826)
            self.assertEqual(m["run_config_key"], "portability_run_config_sha256")
            total_pairs += sched["counts"]["pairs"]
            total_inv += sched["counts"]["invocations"]
            fingerprints.add(sched["matrix_fingerprint"])
        self.assertEqual(total_pairs, 234, "aggregate pairs must be exactly 234")
        self.assertEqual(total_inv, 468, "aggregate invocations must be exactly 468")
        self.assertEqual(len(fingerprints), 4, "the four sub-matrices must be distinct")

    def test_every_cell_maps_to_a_keyed_plan(self):
        ksp = self.pin["keyed_strategy_plans"]
        for mf in MATRIX_FILES:
            m, _c, wls, targets, _s = self._build(mf)
            for wl in wls:
                for seed in m["seeds"]:
                    for t in targets:
                        if t == "2d":
                            continue  # inline-static, workload/seed independent
                        self.assertIn(t, ksp.get(wl, {}).get(str(seed), {}),
                                      "no keyed %s plan for %s/s%d" % (t, wl, seed))


# --------------------------------------------------------------------------- D
class RuntimeAdmissionInvariants(unittest.TestCase):
    """The action admits the two new strategies as keyed, and the WS2 implementation
    gate stays in sync. Offline (no manifest / DB needed)."""

    def test_new_strategies_supported_and_keyed(self):
        for s in NEW_STRATEGIES:
            self.assertIn(s, main.SUPPORTED_STRATEGIES)
            self.assertIn(s, main.KEYED_STRATEGIES)

    def test_ws2_gate_impl_set_admits_new_strategies(self):
        with open(GATE_SCRIPT) as f:
            text = f.read()
        import re
        mm = re.search(r"impl = (\{.*?\})", text, re.S)
        self.assertIsNotNone(mm, "impl set not found in 05_full_matrix.sh")
        impl = mm.group(1)
        for s in NEW_STRATEGIES:
            self.assertIn(s, impl, "WS2 gate does not admit %s" % s)


# --------------------------------------------------------------------------- E
@unittest.skipUnless(_fixture.have_canonical(),
                     "canonical DB + live manifest required")
class SessionLoadAndDispatch(unittest.TestCase):
    """Against the live manifest: the session validates with the workload_set gate,
    resolves all 36 portability plans through the SAME generic lookup that serves the
    YC campaigns, exposes the per-workload oracle, and dispatches the two new
    strategies -- while failing closed on any out-of-set / absent (workload, seed)."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(ARTIFACTS):
            raise unittest.SkipTest("live manifest config/artifacts.json absent")
        cls.sess = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        cls.reasons = cls.sess.validate_artifacts()
        cls.fr = _load_json(FREEZE)["plans"]

    def test_manifest_validates_with_workload_set_gate(self):
        self.assertEqual(self.reasons, (), "validation failed: %s" % (self.reasons,))
        self.assertEqual(self.sess.workload_set, PORTABILITY_WORKLOADS)

    def test_all_36_plans_resolve_and_select(self):
        for p in self.fr:
            strat, wl, seed = p["strategy"], p["workload_id"], p["seed"]
            plan = self.sess.strategy_plan(strat, wl, seed)
            self.assertIsNotNone(plan, "no keyed plan %s/%s/s%d" % (strat, wl, seed))
            offs = main.select_offsets(strat, self.sess, workload=wl, seed=seed)
            self.assertEqual(len(offs), p["pages"],
                             "%s/%s/s%d delivered %d != %d" % (strat, wl, seed, len(offs), p["pages"]))
            interior = sum(1 for o in offs if o in self.sess.interior_offset_set)
            self.assertEqual(interior, p["interior"])
            self.assertEqual(len(offs) - interior, p["leaf"])

    def test_leaf_strategies_deliver_zero_interior(self):
        for p in self.fr:
            if p["strategy"] in LEAF_ONLY:
                offs = main.select_offsets(p["strategy"], self.sess,
                                           workload=p["workload_id"], seed=p["seed"])
                interior = sum(1 for o in offs if o in self.sess.interior_offset_set)
                self.assertEqual(interior, 0)

    def test_oracle_present_for_every_portability_cell(self):
        for wl in PORTABILITY_WORKLOADS:
            for seed in (1, 2, 3):
                self.assertIsNotNone(self.sess.oracle_for(wl, seed, 0),
                                     "oracle absent for %s/s%d" % (wl, seed))

    def test_multiworkload_dispatch_fails_closed(self):
        # A keyed plan absent for the exact (strategy, workload, seed) must raise --
        # never fall back to the canonical YC plan or any other workload.
        with self.assertRaises(ValueError):
            main.select_offsets("2f_top28", self.sess,
                                workload="read_tail_mixed_20k", seed=1)  # 2f_top28 only on read_zipf
        with self.assertRaises(ValueError):
            main.select_offsets("learned_markov_28", self.sess,
                                workload="read_tail_hit_20k", seed=1)  # LOSO only on read_zipf
        with self.assertRaises(ValueError):
            main.select_offsets("2e_K10", self.sess,
                                workload="no_such_workload", seed=1)  # unknown workload


if __name__ == "__main__":
    unittest.main()
