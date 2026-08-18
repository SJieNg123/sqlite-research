"""Regression coverage for the multi-target schedule balance bug.

A malformed schedule can preserve the grand total (1600) and the paired-baseline
total (800) while relabelling/reusing a handful of target arms, yielding per-target
counts like 198/198/198/206 instead of 200/200/200/200. Such a schedule executes
faithfully and passes a naive total-count / response-identity audit, yet is invalid
as a balanced primary matrix. These tests pin:

  * the generator emits an exactly balanced schedule for 1, 2, and 4 targets;
  * every Cartesian cell (workload, seed, first_op, handle_mode, rep, target) has
    exactly one pair = one baseline + one target arm; baseline is never a target;
  * schedule_seed changes AB/BA ORDER only -- never any marginal count or pair
    membership; regeneration with the same seed is byte-identical;
  * the fail-closed validator REJECTS the 198/198/198/206 fixture and every other
    imbalance/duplication/mislabel class, and binds a schedule to its matrix
    fingerprint so a stale/foreign schedule cannot be reused.
"""
import copy
import json
import os
import sys
import unittest
from collections import Counter

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "client"))
import build_schedule  # noqa: E402
import validate_schedule as vs  # noqa: E402

IDS = {"run_config_sha256": "a" * 64, "artifact_manifest_sha256": "b" * 64,
       "action_image_digest": "sha256:img"}
WL = "native_ycsb_c_read_zipf"
SEEDS = list(range(1, 11))
MODES = ["warm", "standalone"]
PRIMARY_TARGETS = ["2d", "layers_5", "2e_K10", "2f_slru"]


def build(targets, seeds=SEEDS, modes=MODES, first_ops=(0,), reps=10,
          seed=20260804, workloads=(WL,)):
    return build_schedule.build_schedule(
        list(workloads), list(seeds), list(first_ops), list(modes),
        list(targets), reps, seed, IDS)


def contract(targets, seeds=SEEDS, modes=MODES, first_ops=(0,), reps=10,
             seed=20260804, workloads=(WL,)):
    return vs.normalized_contract(list(workloads), list(seeds), list(first_ops),
                                  list(modes), list(targets), reps, seed)


def marginals(sched):
    inv = sched["invocations"]
    by_strat = Counter(i["strategy"] for i in inv)
    by_seed = Counter(i["seed"] for i in inv)
    by_ts = Counter((i["strategy"], i["seed"]) for i in inv
                    if i["strategy"] != "baseline")
    return by_strat, by_seed, by_ts


class TestBalancedGeneration(unittest.TestCase):
    def _assert_valid(self, sched, targets, **kw):
        problems = vs.validate_schedule(sched, contract(targets, **kw))
        self.assertEqual(problems, [], problems)

    def test_A_single_target_400(self):
        # [baseline, 2d]: 10 seeds x 2 modes x 10 reps x 2 arms = 400.
        sched = build(["2d"])
        self.assertEqual(len(sched["invocations"]), 400)
        by_strat, by_seed, by_ts = marginals(sched)
        self.assertEqual(by_strat, Counter({"baseline": 200, "2d": 200}))
        self.assertTrue(all(by_seed[s] == 40 for s in SEEDS))
        self.assertTrue(all(by_ts[("2d", s)] == 20 for s in SEEDS))
        self._assert_valid(sched, ["2d"])

    def test_B_two_targets_800(self):
        # [baseline, 2d, layers_5]: 2 targets x 10 seeds x 2 modes x 10 reps = 400
        # pairs -> 800 invocations; baseline 400; each target 200; each seed 80.
        sched = build(["2d", "layers_5"])
        self.assertEqual(len(sched["invocations"]), 800)
        by_strat, by_seed, by_ts = marginals(sched)
        self.assertEqual(by_strat["baseline"], 400)
        self.assertEqual(by_strat["2d"], 200)
        self.assertEqual(by_strat["layers_5"], 200)
        self.assertTrue(all(by_seed[s] == 80 for s in SEEDS))
        self._assert_valid(sched, ["2d", "layers_5"])

    def test_C_four_targets_exact_primary_matrix(self):
        sched = build(PRIMARY_TARGETS)
        inv = sched["invocations"]
        self.assertEqual(len(inv), 1600)
        by_strat, by_seed, by_ts = marginals(sched)
        self.assertEqual(by_strat["baseline"], 800)
        for t in PRIMARY_TARGETS:
            self.assertEqual(by_strat[t], 200, t)
        for s in SEEDS:
            self.assertEqual(by_seed[s], 160, "seed %d" % s)
        for t in PRIMARY_TARGETS:
            for s in SEEDS:
                self.assertEqual(by_ts[(t, s)], 20, "%s x seed%d" % (t, s))
        # target x seed x mode == 10; and exactly one target arm per rep.
        tsm = Counter((i["strategy"], i["seed"], i["handle_mode"]) for i in inv
                      if i["strategy"] != "baseline")
        self.assertTrue(all(v == 10 for v in tsm.values()))
        tsmr = Counter((i["strategy"], i["seed"], i["handle_mode"],
                        i["repetition_id"]) for i in inv
                       if i["strategy"] != "baseline")
        self.assertTrue(all(v == 1 for v in tsmr.values()))
        # every pair is exactly baseline + its target, same non-arm identity.
        pairs = {p["pair_id"]: p for p in sched["pairs"]}
        by_pair = {}
        for i in inv:
            by_pair.setdefault(i["pair_id"], []).append(i)
        self.assertEqual(len(by_pair), 800)
        for pid, arms in by_pair.items():
            self.assertEqual(len(arms), 2)
            self.assertIn("baseline", [a["strategy"] for a in arms])
            tgt = [a for a in arms if a["strategy"] != "baseline"]
            self.assertEqual(len(tgt), 1)
            self.assertEqual(tgt[0]["strategy"], pairs[pid]["target_strategy"])
            b = [a for a in arms if a["strategy"] == "baseline"][0]
            for f in ("workload", "seed", "first_operation_id", "handle_mode",
                      "repetition_id"):
                self.assertEqual(b[f], tgt[0][f], "%s %s" % (pid, f))
        self._assert_valid(sched, PRIMARY_TARGETS)


class TestABBAOrderOnly(unittest.TestCase):
    def _cell_multiset(self, sched):
        # (target, wl, seed, fop, mode, rep) -> count of pairs; plus per-strategy.
        pairs = sched["pairs"]
        cells = Counter((p["target_strategy"], p["workload"], p["seed"],
                         p["first_operation_id"], p["handle_mode"],
                         p["repetition_id"]) for p in pairs)
        strat = Counter(i["strategy"] for i in sched["invocations"])
        return cells, strat

    def test_D_seed_changes_order_not_counts(self):
        a = build(PRIMARY_TARGETS, seed=1)
        b = build(PRIMARY_TARGETS, seed=999)
        ca, sa = self._cell_multiset(a)
        cb, sb = self._cell_multiset(b)
        # identical cell membership and marginals...
        self.assertEqual(ca, cb)
        self.assertEqual(sa, sb)
        # ...but at least one pair's AB/BA order flipped.
        oa = {p["pair_id"]: p["order"] for p in a["pairs"]}
        ob = {p["pair_id"]: p["order"] for p in b["pairs"]}
        self.assertEqual(set(oa), set(ob))
        self.assertTrue(any(oa[k] != ob[k] for k in oa),
                        "schedule_seed change flipped no AB/BA order")
        # every pair still exactly {baseline, its target} in both.
        for sched in (a, b):
            pairs = {p["pair_id"]: p for p in sched["pairs"]}
            for p in sched["pairs"]:
                self.assertEqual(sorted(p["order"]),
                                 sorted(["baseline", p["target_strategy"]]))

    def test_E_same_seed_byte_identical(self):
        a = build(PRIMARY_TARGETS, seed=20260804)
        b = build(PRIMARY_TARGETS, seed=20260804)
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))
        self.assertEqual(a["matrix_fingerprint"], b["matrix_fingerprint"])


class TestValidatorFailsClosed(unittest.TestCase):
    """The validator must reject imbalance, not just wrong totals."""

    def setUp(self):
        self.sched = build(PRIMARY_TARGETS)
        self.contract = contract(PRIMARY_TARGETS)
        self.assertEqual(vs.validate_schedule(self.sched, self.contract), [])

    def _mutate_to_198_206(self):
        """Reproduce the observed failure: move 6 target arms so per-target becomes
        198/198/198/206 while total stays 1600 and baseline stays 800. Relabel the
        *target* arm of 2 pairs each from {2d,layers_5,2e_K10}@seed1 into 2f_slru,
        redistributing across seed1/seed8 (identity of the reused arm changes)."""
        sched = copy.deepcopy(self.sched)
        inv = sched["invocations"]

        def target_arms(strat, seed):
            return [i for i in inv
                    if i["strategy"] == strat and i["seed"] == seed]
        # 2 from each of 2d/layers_5/2e_K10 at seed1 -> relabel strategy to 2f_slru.
        moved = []
        for strat in ("2d", "layers_5", "2e_K10"):
            for i in target_arms(strat, 1)[:2]:
                i["strategy"] = "2f_slru"
                moved.append(i)
        # place 2 of the moved at seed1, 4 at seed8 (the observed 22/24 split).
        for i in moved[2:]:
            i["seed"] = 8
        return sched

    def test_F_rejects_198_198_198_206_fixture(self):
        bad = self._mutate_to_198_206()
        # sanity: the fixture really is the observed shape.
        by_strat = Counter(i["strategy"] for i in bad["invocations"])
        self.assertEqual(len(bad["invocations"]), 1600)   # total still correct
        self.assertEqual(by_strat["baseline"], 800)       # baseline still correct
        self.assertEqual(by_strat["2d"], 198)
        self.assertEqual(by_strat["layers_5"], 198)
        self.assertEqual(by_strat["2e_K10"], 198)
        self.assertEqual(by_strat["2f_slru"], 206)
        problems = vs.validate_schedule(bad, self.contract)
        self.assertTrue(problems, "validator accepted the 198/198/198/206 schedule")
        joined = " | ".join(problems)
        self.assertIn("count 198 != expected 200", joined)
        self.assertIn("count 206 != expected 200", joined)

    def test_rejects_wrong_total(self):
        bad = copy.deepcopy(self.sched)
        bad["invocations"] = bad["invocations"][:-2]
        self.assertTrue(vs.validate_schedule(bad, self.contract))

    def test_rejects_baseline_relabelled_as_target(self):
        bad = copy.deepcopy(self.sched)
        # flip one baseline arm into a target -> baseline 799, breaks its pair.
        for i in bad["invocations"]:
            if i["strategy"] == "baseline":
                i["strategy"] = "2d"
                i["arm"] = "2d"
                break
        self.assertTrue(vs.validate_schedule(bad, self.contract))

    def test_rejects_duplicate_schedule_position(self):
        bad = copy.deepcopy(self.sched)
        bad["invocations"][5]["schedule_position"] = \
            bad["invocations"][6]["schedule_position"]
        problems = vs.validate_schedule(bad, self.contract)
        self.assertTrue(any("schedule_position" in p for p in problems), problems)

    def test_rejects_duplicate_request_id(self):
        bad = copy.deepcopy(self.sched)
        bad["invocations"][5]["request_id"] = bad["invocations"][6]["request_id"]
        problems = vs.validate_schedule(bad, self.contract)
        self.assertTrue(any("request_id" in p for p in problems), problems)

    def test_rejects_pair_arms_disagree_on_seed(self):
        # An arm reused across cells: baseline says seed1, target says seed2.
        bad = copy.deepcopy(self.sched)
        # find a full pair and corrupt the target arm's seed.
        by_pair = {}
        for i in bad["invocations"]:
            by_pair.setdefault(i["pair_id"], []).append(i)
        pid = next(iter(by_pair))
        for a in by_pair[pid]:
            if a["strategy"] != "baseline":
                a["seed"] = a["seed"] + 100
        problems = vs.validate_schedule(bad, self.contract)
        self.assertTrue(any("disagree on seed" in p or "seed set" in p
                            or "count" in p for p in problems), problems)

    def test_fingerprint_binds_schedule_to_matrix(self):
        c4 = contract(PRIMARY_TARGETS)
        c3 = contract(["2d", "layers_5", "2e_K10"])
        fp4 = vs.matrix_fingerprint(c4, IDS)
        fp3 = vs.matrix_fingerprint(c3, IDS)
        self.assertNotEqual(fp4, fp3)
        # order-independent: same contract, shuffled lists -> same fingerprint.
        c4b = contract(list(reversed(PRIMARY_TARGETS)), seeds=list(reversed(SEEDS)))
        self.assertEqual(vs.matrix_fingerprint(c4b, IDS), fp4)
        # identity change (different pin) -> different fingerprint.
        other = dict(IDS, run_config_sha256="c" * 64)
        self.assertNotEqual(vs.matrix_fingerprint(c4, other), fp4)
        # the built schedule stores the matching fingerprint.
        self.assertEqual(self.sched["matrix_fingerprint"], fp4)


class TestGeneratorSelfDefends(unittest.TestCase):
    def test_build_returns_fingerprint_and_contract(self):
        sched = build(PRIMARY_TARGETS)
        self.assertIn("matrix_fingerprint", sched)
        self.assertEqual(sched["contract"]["targets"], PRIMARY_TARGETS)
        self.assertEqual(sched["schema_version"], 2)


if __name__ == "__main__":
    unittest.main()
