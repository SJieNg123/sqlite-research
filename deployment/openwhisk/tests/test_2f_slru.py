"""2f_slru keyed strategy (Batch 2, second consumer): the action delivers a frozen
per-(workload,seed) plan that is the ENTIRE resident working set (SLRU) for that
workload+seed -- a first-query foil. Unlike 2e_K10's fixed 102 pages, 2f_slru's
footprint VARIES per seed (resident 26323..26331; seed 8 = whole DB 26331). The
interior half is always the 92-page 2d skeleton (set equality); the leaf half is
total-92 and seed-dependent.

This proves the generic keyed machinery (schema, generator, session cache, runtime)
handles a large, per-seed-sized plan with NO 2f_slru-specific code path -- the same
lookup that serves 2e_K10.

Layers of coverage:
  * Native parity (Section L): the committed frozen plan for every seed 1..10 selects
    EXACTLY the canonical native `is_resident=1` pages -- pure file comparison. The
    OpenWhisk plan must be the research method's own residency selection, per seed.
  * Pure invariants (Section N): supported/keyed sets, request schema, WS2 gate, and
    the on-disk CSV shape (page order, page formula, 92 interior via skeleton, leaf =
    total-92). Counts are per-seed data, never a universal constant.
  * Generation gate (Section N): crosscheck_pin pins every seed's 2f_slru sha + per-
    seed counts and fails closed on tamper.
  * Session load + fail-closed validation (Sections C/E/F): all 10 plans cache and
    validate; the generic lookup serves BOTH 2e_K10 and 2f_slru; tamper (sha / count /
    duplicate / out-of-range / interior-swap / interior_offsets) fails closed.
  * Runtime (Sections G/H/I): select_offsets is request-identity keyed and delivers
    the per-seed footprint, delivery invariants derive per-seed from plan metadata,
    static + 2e_K10 strategies are unaffected, and a measured invocation reports the
    per-seed counts with the per-seed plan sha as provenance; truncated/extra delivery
    fails closed.
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

IMAGE = "sha256:" + "f" * 64
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
WORKLOAD = "native_ycsb_c_read_zipf"
SEEDS = range(1, 11)
INTERIOR = 92

# import the generator module by path (it is a script, not a package member)
_spec = importlib.util.spec_from_file_location(
    "build_artifact_manifest",
    os.path.join(OW, "build_artifact_manifest.py"))
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

# per-seed expected counts are DATA, sourced from the frozen pin (single source of
# truth), never hard-coded as a universal invariant.
with open(NATIVE_PIN) as _f:
    _PIN = json.load(_f)
_PIN_KEYED = _PIN["keyed_strategy_plans"][WORKLOAD]
EXPECTED_PAGES = {s: _PIN_KEYED[str(s)]["2f_slru"]["expected_pages"] for s in SEEDS}
EXPECTED_LEAF = {s: _PIN_KEYED[str(s)]["2f_slru"]["expected_leaf_pages"] for s in SEEDS}


def have_manifest():
    return os.path.exists(ARTIFACTS) and os.path.exists(_fixture.CANONICAL_DB)


def keyed_csv(seed):
    return os.path.join(KEYED_DIR, "2f_slru_%s_seed%d.csv" % (WORKLOAD, seed))


def native_csv(seed):
    return os.path.join(KEYED_DIR, "native_source/hotpages_yc_seed%d.csv" % seed)


def keyed_plan_pages(seed):
    with open(keyed_csv(seed), newline="") as f:
        return {int(r["page_number"]) for r in csv.DictReader(f)}


def native_selection_pages(seed):
    """page_number set the canonical native SLRU method marked resident."""
    with open(native_csv(seed), newline="") as f:
        return {int(r["page_number"]) for r in csv.DictReader(f)
                if int(r["is_resident"]) == 1}


def full_request(strategy, h, **kw):
    base = dict(request_id="slru-" + strategy, workload=WORKLOAD,
                strategy=strategy, seed=1, first_operation_id=0,
                diagnostic_mode=False, cold_reset=True,
                expected_artifact_manifest_hash=h, pair_id="pair-1",
                repetition_id=0, schedule_position=1, schedule_seed=42,
                run_config_sha256="c" * 64, expected_action_image_digest=IMAGE,
                handle_mode="warm")
    base.update(kw)
    return base


# --------------------------------------------------------------------------- L
class TestNativeParity(unittest.TestCase):
    """Section L -- the load-bearing gate. For every seed, the frozen OpenWhisk
    2f_slru plan must select EXACTLY the pages the canonical native SLRU method
    marked resident. Exact set equality per seed; no seed is normalized into a
    single global plan. No manifest/DB needed."""

    def test_native_sources_present(self):
        for seed in SEEDS:
            self.assertTrue(os.path.exists(native_csv(seed)), native_csv(seed))

    def test_every_seed_plan_equals_native_selection(self):
        for seed in SEEDS:
            plan = keyed_plan_pages(seed)
            native = native_selection_pages(seed)
            self.assertEqual(
                plan, native,
                "seed %d: OpenWhisk plan != native residency; diff=%s"
                % (seed, sorted(plan ^ native)[:20]))
            # total is per-seed data, cross-checked against the pin.
            self.assertEqual(len(plan), EXPECTED_PAGES[seed], "seed %d size" % seed)

    def test_footprint_varies_per_seed(self):
        # 2f_slru is per-seed; do NOT treat any single count as universal. Interior
        # is always 92; totals span a range and are not all identical.
        totals = {len(keyed_plan_pages(s)) for s in SEEDS}
        self.assertGreater(len(totals), 1, "2f_slru totals unexpectedly uniform")
        for seed in SEEDS:
            pages = keyed_plan_pages(seed)
            interior = pages & {o // 4096 + 1 for o in _interior_offsets()}
            self.assertEqual(len(interior), INTERIOR, "seed %d interior" % seed)

    def test_seed8_is_whole_db(self):
        # seed 8 happens to be the whole DB (26331) -- fine as per-seed DATA, not an
        # invariant imposed on the others.
        self.assertEqual(len(keyed_plan_pages(8)),
                         _PIN["database"]["page_count"])

    def test_all_ten_native_and_plan_shas_distinct(self):
        plan_shas = {gen.sha256_file(keyed_csv(s)) for s in SEEDS}
        native_shas = {gen.sha256_file(native_csv(s)) for s in SEEDS}
        self.assertEqual(len(plan_shas), 10, "plan shas not all distinct")
        self.assertEqual(len(native_shas), 10, "native shas not all distinct")


def _interior_offsets():
    with open(os.path.join(OW, "config/plans/interior_pages.csv"), newline="") as f:
        return [int(r["file_offset"]) for r in csv.DictReader(f)]


# --------------------------------------------------------------------------- N
class TestPureInvariants(unittest.TestCase):
    def test_supported_and_keyed_sets(self):
        self.assertIn("2f_slru", main.SUPPORTED_STRATEGIES)
        self.assertIn("2f_slru", main.KEYED_STRATEGIES)
        # keyed => must NOT carry a static global delivery invariant.
        self.assertNotIn("2f_slru", main.DELIVERY_INVARIANTS)

    def test_request_schema_accepts_2f_slru(self):
        problems = main.validate_request_schema(full_request("2f_slru", "a" * 64))
        self.assertFalse([p for p in problems if "strategy must be one of" in p],
                         problems)

    def test_ws2_gate_recognizes_2f_slru(self):
        import ast
        import re
        with open(GATE_SCRIPT) as f:
            m = re.search(r"impl = (\{[^}]*\})", f.read())
        self.assertIsNotNone(m, "impl set not found in 05_full_matrix.sh")
        self.assertIn("2f_slru", ast.literal_eval(m.group(1)))

    def test_all_ten_keyed_csvs_have_correct_shape(self):
        interior_set = set(_interior_offsets())
        for seed in SEEDS:
            path = keyed_csv(seed)
            self.assertTrue(os.path.exists(path), path)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), EXPECTED_PAGES[seed], "seed %d rows" % seed)
            offs = [(int(r["page_number"]), int(r["file_offset"])) for r in rows]
            for pn, fo in offs:
                self.assertEqual(fo, (pn - 1) * 4096, "seed %d pn=%d" % (seed, pn))
            self.assertEqual([pn for pn, _ in offs], sorted(pn for pn, _ in offs),
                             "seed %d not page-ordered" % seed)
            file_offs = {fo for _, fo in offs}
            interior_hit = file_offs & interior_set
            self.assertEqual(interior_hit, interior_set,
                             "seed %d interior half != 92-skeleton" % seed)
            self.assertEqual(len(file_offs) - INTERIOR, EXPECTED_LEAF[seed],
                             "seed %d leaf count" % seed)


class TestCrosscheckPin2fSlruFailsClosed(unittest.TestCase):
    """Section N -- crosscheck_pin pins every seed's 2f_slru sha + per-seed counts
    and must fail closed on any tamper."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _PIN
        l5 = cls.pin["strategy_plans"]["layers_5"]
        keyed = cls.pin["keyed_strategy_plans"][WORKLOAD]
        cls.good_meta = {
            strat: {s: {"sha": keyed[str(s)][strat]["sha256"],
                        "pages": keyed[str(s)][strat]["expected_pages"],
                        "interior": keyed[str(s)][strat]["expected_interior_pages"],
                        "leaf": keyed[str(s)][strat]["expected_leaf_pages"]}
                    for s in SEEDS}
            # crosscheck_pin iterates every KEYED_SPECS strategy, so the good meta must
            # carry them all (not just this module's focus), or it KeyErrors.
            for strat in (spec["strategy"] for spec in gen.KEYED_SPECS)}
        cls.good = dict(
            db_sha=cls.pin["database"]["sha256"],
            plan_sha=cls.pin["strategy_plans"]["2d"]["sha256"],
            classifier_sha=cls.pin["classifier"]["sha256"],
            trace_shas={str(e["seed"]): e["trace_sha256"]
                        for e in cls.pin["representative_workload"]["seed_family"]},
            layers5_sha=l5["sha256"],
            layers5_offsets=list(l5["offsets"]),
        )

    def _meta_copy(self):
        return {strat: {s: dict(m) for s, m in seeds.items()}
                for strat, seeds in self.good_meta.items()}

    def _call(self, keyed_meta):
        g = self.good
        return gen.crosscheck_pin(
            g["db_sha"], g["plan_sha"], g["classifier_sha"], g["trace_shas"],
            g["layers5_sha"], g["layers5_offsets"], keyed_meta)

    def test_matching_passes(self):
        self._call(self._meta_copy())  # must not raise

    def test_tampered_2f_slru_sha_fails_closed(self):
        bad = self._meta_copy()
        bad["2f_slru"][8]["sha"] = "0" * 64
        with self.assertRaises(SystemExit):
            self._call(bad)

    def test_tampered_2f_slru_count_fails_closed(self):
        bad = self._meta_copy()
        bad["2f_slru"][3]["pages"] = bad["2f_slru"][3]["pages"] + 1
        with self.assertRaises(SystemExit):
            self._call(bad)

    def test_tampered_2f_slru_leaf_fails_closed(self):
        bad = self._meta_copy()
        bad["2f_slru"][3]["leaf"] = bad["2f_slru"][3]["leaf"] - 1
        with self.assertRaises(SystemExit):
            self._call(bad)

    def test_missing_2f_slru_seed_fails_closed(self):
        bad = self._meta_copy()
        del bad["2f_slru"][10]
        with self.assertRaises((SystemExit, KeyError)):
            self._call(bad)


# ----------------------------------------------------------- session (needs manifest)
@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestSessionKeyedLoad(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)

    def test_all_ten_plans_cache_with_per_seed_counts(self):
        for seed in SEEDS:
            plan = self.s.strategy_plan("2f_slru", WORKLOAD, seed)
            self.assertIsNotNone(plan, "seed %d not cached" % seed)
            self.assertEqual(len(plan["offsets"]), EXPECTED_PAGES[seed])
            interior = sum(1 for o in plan["offsets"]
                           if o in self.s.interior_offset_set)
            self.assertEqual(interior, INTERIOR, "seed %d interior" % seed)
            self.assertEqual(len(plan["offsets"]) - interior, EXPECTED_LEAF[seed],
                             "seed %d leaf" % seed)

    def test_generic_lookup_serves_both_strategies(self):
        # The SAME cache/lookup returns both keyed consumers -- no strategy-specific
        # loader. This is the abstraction claim.
        k10 = self.s.strategy_plan("2e_K10", WORKLOAD, 1)
        slru = self.s.strategy_plan("2f_slru", WORKLOAD, 1)
        self.assertIsNotNone(k10)
        self.assertIsNotNone(slru)
        self.assertEqual(len(k10["offsets"]), 102)
        self.assertEqual(len(slru["offsets"]), EXPECTED_PAGES[1])
        self.assertNotEqual(k10["plan_sha256"], slru["plan_sha256"])

    def test_lookup_miss_returns_none(self):
        self.assertIsNone(self.s.strategy_plan("2f_slru", WORKLOAD, 99))
        self.assertIsNone(self.s.strategy_plan("2f_slru", "workload_a", 1))

    def test_interior_half_is_the_92_skeleton(self):
        for seed in SEEDS:
            plan = self.s.strategy_plan("2f_slru", WORKLOAD, seed)
            interior = {o for o in plan["offsets"]
                        if o in self.s.interior_offset_set}
            self.assertEqual(interior, self.s.interior_offset_set,
                             "seed %d interior half != skeleton" % seed)

    def test_all_ten_shas_distinct(self):
        shas = {self.s.strategy_plan("2f_slru", WORKLOAD, s)["plan_sha256"]
                for s in SEEDS}
        self.assertEqual(len(shas), 10, "2f_slru per-seed shas not all distinct")

    def test_session_offsets_match_native_selection(self):
        for seed in SEEDS:
            offs = self.s.strategy_plan("2f_slru", WORKLOAD, seed)["offsets"]
            pages = {o // 4096 + 1 for o in offs}
            self.assertEqual(pages, native_selection_pages(seed),
                             "seed %d session offsets != native residency" % seed)


@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestKeyedValidationFailsClosed(unittest.TestCase):
    """Section N -- _validate_keyed_plans must reject every tamper class for 2f_slru."""

    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)
        self.pc = self.s.manifest["database"]["page_count"]
        self.entry = self.s.manifest["keyed_strategy_plans"][WORKLOAD]["1"]["2f_slru"]

    def _reasons(self):
        return self.s._validate_keyed_plans(4096, self.pc)

    def test_baseline_validates_clean(self):
        self.assertEqual(self._reasons(), [])

    def test_tampered_sha_rejected(self):
        self.entry["sha256"] = "0" * 64
        self.assertTrue([r for r in self._reasons() if "sha256 mismatch" in r],
                        self._reasons())

    def test_page_count_mismatch_rejected(self):
        self.entry["expected_pages"] = self.entry["expected_pages"] - 1
        self.assertTrue([r for r in self._reasons() if "offsets, expected" in r],
                        self._reasons())

    def test_interior_count_mismatch_rejected(self):
        self.entry["expected_interior_pages"] = 91
        self.assertTrue([r for r in self._reasons() if "interior count" in r],
                        self._reasons())

    def test_leaf_count_mismatch_rejected(self):
        self.entry["expected_leaf_pages"] = self.entry["expected_leaf_pages"] + 1
        self.assertTrue([r for r in self._reasons() if "leaf count" in r],
                        self._reasons())

    def test_interior_swap_breaks_skeleton_equality(self):
        interior_off = next(o for o in self.s.keyed_plans[("2f_slru", WORKLOAD, "1")]
                            ["offsets"] if o in self.s.interior_offset_set)
        self.s.interior_offset_set = self.s.interior_offset_set - {interior_off}
        reasons = self._reasons()
        self.assertTrue([r for r in reasons if "skeleton" in r or "interior count" in r],
                        reasons)

    def test_duplicate_offset_rejected(self):
        cached = self.s.keyed_plans[("2f_slru", WORKLOAD, "1")]
        cached["offsets"] = cached["offsets"][:-1] + [cached["offsets"][0]]
        self.assertTrue([r for r in self._reasons() if "duplicate offsets" in r],
                        self._reasons())

    def test_out_of_range_offset_rejected(self):
        cached = self.s.keyed_plans[("2f_slru", WORKLOAD, "1")]
        cached["offsets"] = cached["offsets"][:-1] + [self.pc * 4096 + 4096]
        self.assertTrue(
            [r for r in self._reasons() if "misaligned/out-of-range" in r],
            self._reasons())

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

    def test_keyed_select_is_per_seed(self):
        for seed in (1, 6, 8):
            offs = main.select_offsets("2f_slru", self.s, WORKLOAD, seed)
            self.assertEqual(len(offs), EXPECTED_PAGES[seed], "seed %d" % seed)
            interior = sum(1 for o in offs if o in self.s.interior_offset_set)
            self.assertEqual(interior, INTERIOR, "seed %d interior" % seed)
            self.assertEqual(len(offs) - interior, EXPECTED_LEAF[seed],
                             "seed %d leaf" % seed)

    def test_select_is_request_identity_keyed(self):
        # different seeds have different resident sets -> different delivery.
        self.assertNotEqual(main.select_offsets("2f_slru", self.s, WORKLOAD, 6),
                            main.select_offsets("2f_slru", self.s, WORKLOAD, 8))

    def test_missing_keyed_plan_fails_closed(self):
        with self.assertRaises(ValueError):
            main.select_offsets("2f_slru", self.s, WORKLOAD, 99)
        with self.assertRaises(ValueError):
            main.select_offsets("2f_slru", self.s, "workload_a", 1)

    def test_static_and_2e_k10_unaffected(self):
        self.assertEqual(main.select_offsets("baseline", self.s, WORKLOAD, 1), [])
        self.assertEqual(len(main.select_offsets("2d", self.s, WORKLOAD, 1)), 92)
        self.assertEqual(len(main.select_offsets("layers_5", self.s, WORKLOAD, 1)), 5)
        self.assertEqual(len(main.select_offsets("2e_K10", self.s, WORKLOAD, 1)), 102)

    def test_delivery_invariants_derive_per_seed(self):
        for seed in (1, 6, 8):
            inv = main.delivery_invariants_for("2f_slru", self.s, WORKLOAD, seed)
            self.assertEqual(inv, {
                "selected_page_count": EXPECTED_PAGES[seed],
                "selected_interior_count": INTERIOR,
                "selected_leaf_count": EXPECTED_LEAF[seed],
                "delivered_page_count": EXPECTED_PAGES[seed]}, "seed %d" % seed)
        self.assertNotIn("2f_slru", main.DELIVERY_INVARIANTS)


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

    def test_measured_2f_slru_valid(self):
        r = main.handle(full_request("2f_slru", self.h, seed=1), self.s)
        self.assertIsNone(r.get("error_stage"), r.get("error"))
        self.assertEqual(
            (r["selected_page_count"], r["selected_interior_count"],
             r["selected_leaf_count"], r["delivered_page_count"]),
            (EXPECTED_PAGES[1], INTERIOR, EXPECTED_LEAF[1], EXPECTED_PAGES[1]))
        self.assertTrue(r["delivery_valid"])
        self.assertTrue(r["measured_valid"])
        self.assertEqual(
            r["plan_sha256"],
            self.s.strategy_plan("2f_slru", WORKLOAD, 1)["plan_sha256"])

    def test_seed_provenance_distinct(self):
        r6 = main.handle(full_request("2f_slru", self.h, seed=6,
                                      request_id="slru-s6"), self.s)
        r8 = main.handle(full_request("2f_slru", self.h, seed=8,
                                      request_id="slru-s8"), self.s)
        self.assertTrue(r6["measured_valid"] and r8["measured_valid"])
        self.assertNotEqual(r6["plan_sha256"], r8["plan_sha256"])
        self.assertNotEqual(r6["selected_page_count"], r8["selected_page_count"])

    def test_truncated_delivery_not_measured_valid(self):
        with mock.patch.object(residency.PageMap, "deliver_willneed",
                               return_value=EXPECTED_PAGES[1] - 1):
            r = main.handle(full_request("2f_slru", self.h, seed=1), self.s)
        self.assertFalse(r["delivery_valid"])
        self.assertFalse(r["measured_valid"])

    def test_extra_delivery_not_measured_valid(self):
        with mock.patch.object(residency.PageMap, "deliver_willneed",
                               return_value=EXPECTED_PAGES[1] + 1):
            r = main.handle(full_request("2f_slru", self.h, seed=1), self.s)
        self.assertFalse(r["delivery_valid"])
        self.assertFalse(r["measured_valid"])

    def test_2e_k10_and_2d_regression(self):
        r10 = main.handle(full_request("2e_K10", self.h, seed=1,
                                       request_id="slru-k10"), self.s)
        self.assertEqual(r10["selected_page_count"], 102)
        self.assertTrue(r10["measured_valid"])
        r2d = main.handle(full_request("2d", self.h, request_id="slru-2d"), self.s)
        self.assertEqual(r2d["selected_interior_count"], 92)
        self.assertTrue(r2d["measured_valid"])


if __name__ == "__main__":
    unittest.main()
