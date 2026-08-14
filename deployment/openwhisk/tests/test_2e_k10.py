"""2e_K10 keyed strategy (Batch 2): the action delivers a frozen per-(workload,seed)
plan -- the resident 92-interior 2d skeleton UNION that seed's top-10 hot leaf
pages (102 pages: 92 interior + 10 leaf).

Layers of coverage:
  * Native parity (Section K): the committed frozen delivery plan for every seed
    1..10 selects EXACTLY the canonical native `is_resident=1` pages -- pure file
    comparison, no manifest or DB needed. This is the load-bearing correctness gate:
    the OpenWhisk plan must be the research method's own selection, byte-for-byte.
  * Pure invariants (Section L): supported/keyed sets, request schema, WS2 gate, and
    the on-disk CSV shape (102 rows, page order, 92+10 split).
  * Generation gate (Section L): crosscheck_pin fails closed on a tampered keyed sha.
  * Session load + fail-closed validation (Sections C/E/K): all 10 plans cache and
    validate; the interior half == the 92-skeleton; seed 6 is the sole divergence;
    tamper (sha/count/interior-swap/leaf-out-of-range/duplicate) fails closed.
  * Runtime (Sections F/G/H): select_offsets is request-identity keyed, delivery
    invariants derive from plan metadata, static strategies are unaffected, and a
    measured invocation reports 102/92/10 with the per-seed plan sha as provenance.
The session/runtime tiers need the generated live manifest (config/artifacts.json,
gitignored) plus the canonical DB and skip cleanly when either is absent.
"""
import csv
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

IMAGE = "sha256:" + "b" * 64
os.environ["OW_ACTION_IMAGE_DIGEST"] = IMAGE

import main  # noqa: E402
import residency  # noqa: E402
import session as session_mod  # noqa: E402

REPO = _fixture.REPO
OW = os.path.join(REPO, "deployment/openwhisk")
ARTIFACTS = os.path.join(OW, "config/artifacts.json")
NATIVE_PIN = os.path.join(OW, "config/artifacts.native_ycsb.json")
GATE_SCRIPT = os.path.join(OW, "ws2/05_full_matrix.sh")
KEYED_DIR = os.path.join(OW, "config/plans/keyed")
NATIVE_MASTER = os.path.join(REPO, "strategies/access/runs/hot2e_YC_orig_K10.csv")
SEED6_NATIVE = os.path.join(KEYED_DIR, "native_source/hot2e_YC_orig_K10_seed6.csv")
WORKLOAD = "native_ycsb_c_read_zipf"
SEEDS = range(1, 11)

# import the generator module by path (it is a script, not a package member)
_spec = importlib.util.spec_from_file_location(
    "build_artifact_manifest",
    os.path.join(OW, "build_artifact_manifest.py"))
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def have_manifest():
    return os.path.exists(ARTIFACTS) and os.path.exists(_fixture.CANONICAL_DB)


def keyed_csv(seed):
    return os.path.join(KEYED_DIR,
                        "2e_K10_%s_seed%d.csv" % (WORKLOAD, seed))


def keyed_plan_pages(seed):
    """page_number set from the frozen OpenWhisk delivery plan for a seed."""
    with open(keyed_csv(seed), newline="") as f:
        return {int(r["page_number"]) for r in csv.DictReader(f)}


def native_selection_pages(seed):
    """page_number set the canonical native method selected (is_resident=1). Seed 6
    is the sole per-seed divergence and has its own committed native source; the
    other nine share the in-repo unseeded master (see keyed/native_source/
    PROVENANCE.md)."""
    src = SEED6_NATIVE if seed == 6 else NATIVE_MASTER
    with open(src, newline="") as f:
        return {int(r["page_number"]) for r in csv.DictReader(f)
                if int(r["is_resident"]) == 1}


def full_request(strategy, h, **kw):
    base = dict(request_id="k10-" + strategy, workload=WORKLOAD,
                strategy=strategy, seed=1, first_operation_id=0,
                diagnostic_mode=False, cold_reset=True,
                expected_artifact_manifest_hash=h, pair_id="pair-1",
                repetition_id=0, schedule_position=1, schedule_seed=42,
                run_config_sha256="c" * 64, expected_action_image_digest=IMAGE,
                handle_mode="warm")
    base.update(kw)
    return base


# --------------------------------------------------------------------------- K
class TestNativeParity(unittest.TestCase):
    """Section K -- the load-bearing gate. For every seed, the frozen OpenWhisk
    2e_K10 delivery plan must select EXACTLY the pages the canonical native method
    marked resident. Exact set equality; any drift means the served plan is not the
    research selection and the strategy is invalid on OpenWhisk. No manifest/DB
    needed -- this compares committed artifacts directly."""

    def test_native_sources_present(self):
        self.assertTrue(os.path.exists(NATIVE_MASTER), NATIVE_MASTER)
        self.assertTrue(os.path.exists(SEED6_NATIVE), SEED6_NATIVE)

    def test_every_seed_plan_equals_native_selection(self):
        for seed in SEEDS:
            plan = keyed_plan_pages(seed)
            native = native_selection_pages(seed)
            self.assertEqual(len(plan), 102, "seed %d plan size" % seed)
            # exact set equality -- STOP semantics: the assertion fails on the first
            # diverging seed, naming the symmetric difference.
            self.assertEqual(
                plan, native,
                "seed %d: OpenWhisk plan != native selection; diff=%s"
                % (seed, sorted(plan ^ native)))

    def test_seed6_is_the_sole_divergence(self):
        # Seeds 1-5,7-10 share one native selection; seed 6 swaps 24837 -> 18314.
        common = native_selection_pages(1)
        for seed in (2, 3, 4, 5, 7, 8, 9, 10):
            self.assertEqual(native_selection_pages(seed), common,
                             "seed %d unexpectedly differs from the common-9" % seed)
        six = native_selection_pages(6)
        self.assertNotEqual(six, common)
        self.assertEqual(common - six, {24837})
        self.assertEqual(six - common, {18314})


# --------------------------------------------------------------------------- L
class TestPureInvariants(unittest.TestCase):
    """No canonical artifacts needed."""

    def test_supported_and_keyed_sets(self):
        self.assertIn("2e_K10", main.SUPPORTED_STRATEGIES)
        self.assertEqual(main.KEYED_STRATEGIES, ("2e_K10",))
        # 2e_K10 is keyed, so it must NOT carry a static global delivery invariant.
        self.assertNotIn("2e_K10", main.DELIVERY_INVARIANTS)

    def test_request_schema_accepts_2e_k10(self):
        problems = main.validate_request_schema(full_request("2e_K10", "a" * 64))
        self.assertFalse([p for p in problems if "strategy must be one of" in p],
                         problems)

    def test_ws2_gate_recognizes_2e_k10(self):
        import ast
        import re
        with open(GATE_SCRIPT) as f:
            m = re.search(r"impl = (\{[^}]*\})", f.read())
        self.assertIsNotNone(m, "impl set not found in 05_full_matrix.sh")
        self.assertIn("2e_K10", ast.literal_eval(m.group(1)))

    def test_all_ten_keyed_csvs_have_correct_shape(self):
        for seed in SEEDS:
            path = keyed_csv(seed)
            self.assertTrue(os.path.exists(path), path)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 102, "seed %d row count" % seed)
            offs = [(int(r["page_number"]), int(r["file_offset"])) for r in rows]
            # page_number,file_offset obey the page formula and are in page order.
            for pn, fo in offs:
                self.assertEqual(fo, (pn - 1) * 4096, "seed %d pn=%d" % (seed, pn))
            self.assertEqual([pn for pn, _ in offs], sorted(pn for pn, _ in offs),
                             "seed %d not page-ordered" % seed)


class TestCrosscheckPinKeyedFailsClosed(unittest.TestCase):
    """Section L -- the generation-time pin cross-check explicitly pins every seed's
    keyed 2e_K10 plan sha and must fail closed on any tamper, not lean on transitive
    provenance."""

    @classmethod
    def setUpClass(cls):
        with open(NATIVE_PIN) as f:
            cls.pin = json.load(f)
        l5 = cls.pin["strategy_plans"]["layers_5"]
        keyed = cls.pin["keyed_strategy_plans"][WORKLOAD]
        cls.good = dict(
            db_sha=cls.pin["database"]["sha256"],
            plan_sha=cls.pin["strategy_plans"]["2d"]["sha256"],
            classifier_sha=cls.pin["classifier"]["sha256"],
            trace_shas={str(e["seed"]): e["trace_sha256"]
                        for e in cls.pin["representative_workload"]["seed_family"]},
            layers5_sha=l5["sha256"],
            layers5_offsets=list(l5["offsets"]),
            keyed_shas={s: keyed[str(s)]["2e_K10"]["sha256"] for s in SEEDS},
        )

    def _call(self, keyed_shas):
        g = self.good
        return gen.crosscheck_pin(
            g["db_sha"], g["plan_sha"], g["classifier_sha"], g["trace_shas"],
            g["layers5_sha"], g["layers5_offsets"], keyed_shas)

    def test_matching_keyed_shas_pass(self):
        self._call(dict(self.good["keyed_shas"]))  # must not raise

    def test_tampered_keyed_sha_fails_closed(self):
        bad = dict(self.good["keyed_shas"])
        bad[6] = "0" * 64
        with self.assertRaises(SystemExit):
            self._call(bad)

    def test_missing_keyed_seed_fails_closed(self):
        bad = dict(self.good["keyed_shas"])
        del bad[10]
        with self.assertRaises((SystemExit, KeyError)):
            self._call(bad)


# ----------------------------------------------------------- session (needs manifest)
@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestSessionKeyedLoad(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)

    def test_all_ten_plans_cache_with_counts(self):
        for seed in SEEDS:
            plan = self.s.strategy_plan("2e_K10", WORKLOAD, seed)
            self.assertIsNotNone(plan, "seed %d not cached" % seed)
            self.assertEqual(len(plan["offsets"]), 102)
            interior = sum(1 for o in plan["offsets"]
                           if o in self.s.interior_offset_set)
            self.assertEqual(interior, 92, "seed %d interior" % seed)
            self.assertEqual(len(plan["offsets"]) - interior, 10,
                             "seed %d leaf" % seed)

    def test_lookup_miss_returns_none(self):
        # wrong seed span, wrong workload, unsupported strategy -> None (fail closed
        # at the caller, never a stale hit).
        self.assertIsNone(self.s.strategy_plan("2e_K10", WORKLOAD, 99))
        self.assertIsNone(self.s.strategy_plan("2e_K10", "workload_a", 1))
        self.assertIsNone(self.s.strategy_plan("2f_slru", WORKLOAD, 1))

    def test_interior_half_is_the_92_skeleton(self):
        for seed in SEEDS:
            plan = self.s.strategy_plan("2e_K10", WORKLOAD, seed)
            interior = {o for o in plan["offsets"]
                        if o in self.s.interior_offset_set}
            self.assertEqual(interior, self.s.interior_offset_set,
                             "seed %d interior half != skeleton" % seed)

    def test_seed6_offsets_diverge_from_common(self):
        common = self.s.strategy_plan("2e_K10", WORKLOAD, 1)["plan_sha256"]
        for seed in (2, 3, 4, 5, 7, 8, 9, 10):
            self.assertEqual(
                self.s.strategy_plan("2e_K10", WORKLOAD, seed)["plan_sha256"],
                common, "seed %d sha should equal common-9" % seed)
        self.assertNotEqual(
            self.s.strategy_plan("2e_K10", WORKLOAD, 6)["plan_sha256"], common)

    def test_session_offsets_match_native_selection(self):
        # The cached, validated offsets round-trip to page numbers that equal the
        # canonical native selection -- parity survives the manifest/page-formula
        # path, not just the raw CSV.
        for seed in SEEDS:
            offs = self.s.strategy_plan("2e_K10", WORKLOAD, seed)["offsets"]
            pages = {o // 4096 + 1 for o in offs}
            self.assertEqual(pages, native_selection_pages(seed),
                             "seed %d session offsets != native selection" % seed)


@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestKeyedValidationFailsClosed(unittest.TestCase):
    """Section K/L -- _validate_keyed_plans must reject every tamper class."""

    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.pc = self.s.manifest["database"]["page_count"]
        self.entry = self.s.manifest["keyed_strategy_plans"][WORKLOAD]["1"]["2e_K10"]

    def _reasons(self):
        return self.s._validate_keyed_plans(4096, self.pc)

    def test_baseline_validates_clean(self):
        self.assertEqual(self._reasons(), [])

    def test_tampered_sha_rejected(self):
        self.entry["sha256"] = "0" * 64
        self.assertTrue([r for r in self._reasons() if "sha256 mismatch" in r],
                        self._reasons())

    def test_page_count_mismatch_rejected(self):
        self.entry["expected_pages"] = 101
        self.assertTrue([r for r in self._reasons() if "offsets, expected" in r],
                        self._reasons())

    def test_interior_count_mismatch_rejected(self):
        self.entry["expected_interior_pages"] = 91
        self.assertTrue([r for r in self._reasons() if "interior count" in r],
                        self._reasons())

    def test_leaf_count_mismatch_rejected(self):
        self.entry["expected_leaf_pages"] = 11
        self.assertTrue([r for r in self._reasons() if "leaf count" in r],
                        self._reasons())

    def test_interior_swap_breaks_skeleton_equality(self):
        # Drop one interior offset from the validated skeleton: an interior page in
        # the plan now classifies as a leaf -> counts shift AND the interior half no
        # longer equals the 92-skeleton.
        interior_off = next(o for o in self.s.keyed_plans[("2e_K10", WORKLOAD, "1")]
                            ["offsets"] if o in self.s.interior_offset_set)
        self.s.interior_offset_set = self.s.interior_offset_set - {interior_off}
        reasons = self._reasons()
        self.assertTrue([r for r in reasons if "skeleton" in r or "interior count" in r],
                        reasons)

    def test_manifest_interior_offsets_disagreement_rejected(self):
        self.entry["interior_offsets"] = self.entry["interior_offsets"][:-1] + [999999]
        self.assertTrue(
            [r for r in self._reasons() if "interior_offsets disagree" in r],
            self._reasons())


# ----------------------------------------------------------- runtime (needs manifest)
@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestKeyedSelectOffsets(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)

    def test_keyed_select_is_102_92_10(self):
        offs = main.select_offsets("2e_K10", self.s, WORKLOAD, 1)
        self.assertEqual(len(offs), 102)
        interior = sum(1 for o in offs if o in self.s.interior_offset_set)
        self.assertEqual((interior, len(offs) - interior), (92, 10))

    def test_select_is_request_identity_keyed(self):
        # seed 6 must select a different plan than the common-9.
        self.assertNotEqual(main.select_offsets("2e_K10", self.s, WORKLOAD, 6),
                            main.select_offsets("2e_K10", self.s, WORKLOAD, 1))

    def test_missing_keyed_plan_fails_closed(self):
        with self.assertRaises(ValueError):
            main.select_offsets("2e_K10", self.s, WORKLOAD, 99)
        with self.assertRaises(ValueError):
            main.select_offsets("2e_K10", self.s, "workload_a", 1)

    def test_static_strategies_unaffected(self):
        self.assertEqual(main.select_offsets("baseline", self.s, WORKLOAD, 1), [])
        self.assertEqual(len(main.select_offsets("2d", self.s, WORKLOAD, 1)), 92)
        self.assertEqual(len(main.select_offsets("layers_5", self.s, WORKLOAD, 1)), 5)

    def test_delivery_invariants_derive_from_plan(self):
        inv = main.delivery_invariants_for("2e_K10", self.s, WORKLOAD, 1)
        self.assertEqual(inv, {"selected_page_count": 102,
                               "selected_interior_count": 92,
                               "selected_leaf_count": 10,
                               "delivered_page_count": 102})
        # 102 is derived, not a hard-coded global.
        self.assertNotIn("2e_K10", main.DELIVERY_INVARIANTS)


@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestKeyedMeasured(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.s.open_warm_handle()
        self.s.deployment_image_digest = IMAGE
        self.h = self.s.artifact_manifest_sha256
        self.addCleanup(self.s.close_warm_handle)

    def test_measured_2e_k10_valid(self):
        r = main.handle(full_request("2e_K10", self.h, seed=1), self.s)
        self.assertIsNone(r.get("error_stage"), r.get("error"))
        self.assertEqual((r["selected_page_count"], r["selected_interior_count"],
                          r["selected_leaf_count"], r["delivered_page_count"]),
                         (102, 92, 10, 102))
        self.assertTrue(r["delivery_valid"])
        self.assertTrue(r["measured_valid"])
        # provenance: the response carries the per-(workload,seed) plan sha.
        self.assertEqual(
            r["plan_sha256"],
            self.s.strategy_plan("2e_K10", WORKLOAD, 1)["plan_sha256"])

    def test_seed6_provenance_distinct(self):
        r1 = main.handle(full_request("2e_K10", self.h, seed=1,
                                      request_id="k10-s1"), self.s)
        r6 = main.handle(full_request("2e_K10", self.h, seed=6,
                                      request_id="k10-s6"), self.s)
        self.assertTrue(r1["measured_valid"] and r6["measured_valid"])
        self.assertNotEqual(r1["plan_sha256"], r6["plan_sha256"])

    def test_incomplete_delivery_not_measured_valid(self):
        with mock.patch.object(residency.PageMap, "deliver_willneed",
                               return_value=101):
            r = main.handle(full_request("2e_K10", self.h, seed=1), self.s)
        self.assertFalse(r["delivery_valid"])
        self.assertFalse(r["measured_valid"])

    def test_2d_regression_still_92(self):
        r = main.handle(full_request("2d", self.h), self.s)
        self.assertEqual(r["selected_interior_count"], 92)
        self.assertTrue(r["measured_valid"])


if __name__ == "__main__":
    unittest.main()
