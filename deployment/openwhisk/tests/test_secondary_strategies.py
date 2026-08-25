"""YC SECONDARY keyed strategies (Batch 3): five more consumers of the same generic
keyed-plan machinery, on the canonical workload native_ycsb_c_read_zipf, seeds 1..10.
These characterize the mechanism space around the 2e_K10 headline; they are NOT new
headline warm-latency claims (see WS2 runbook / OpenWhisk README interpretation note).

    strategy             kind                      total   interior gate
    2e_K500              hot2e k=500               592      92 (skeleton set-equality)
    leaf_freq_K10        leaf-only frequency        10       0 (leaf-only)
    leaf_rand_K10        leaf-only random           10       0 (leaf-only)
    2f_top102            freqdump ranked partial   102      None (emergent, recorded)
    learned_markov_102   learned Markov partial    102      None (emergent, recorded)

N_YC = 102 = 92 interior + 10 leaf, frozen from the 2e_K10 artifact; 2f_top102 and
learned_markov_102 are the total-page-budget-matched competitors to 2e_K10. Both rank
with NO page-type knowledge, yet empirically land on an emergent 51 interior / 51 leaf
split (uniform across all 10 seeds) -- validating the None gate class: total==102 is
enforced, the interior/leaf split is recorded (from the pin), never imposed.

Coverage (mirrors test_2f_slru.py, adapted for the 3 gate classes):
  * Native parity (Section L): for the direct-selection strategies (2e_K500, 2f_top102,
    learned_markov_102) every seed's frozen plan == the native is_resident selection,
    exact set equality per seed. leaf_freq_K10 == the 10 hot leaves derived from the
    committed 2e_K10 native source (resident minus the 92-skeleton). leaf_rand_K10 is
    10 leaves, interior-free, disjoint from the frequency leaves (the ablation contrast).
  * Pure invariants (Section N): supported/keyed sets, request schema, WS2 gate, on-disk
    CSV shape, per-seed counts vs the pin, and the emergent 51/51 record for the two
    None-gate strategies. Counts are per-seed DATA sourced from the pin, never hard-coded.
  * Session load + runtime (needs manifest): all 50 plans cache/validate under the SAME
    generic lookup that serves 2e_K10/2f_slru; select_offsets and a measured invocation
    deliver the pinned per-seed footprint for each of the five; static + prior keyed
    strategies are unaffected.
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

# Match the digest sibling modules (test_contract/test_layers5) set at import so the
# process-global OW_ACTION_IMAGE_DIGEST stays consistent regardless of discovery order.
IMAGE = "sha256:" + "a" * 64
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
INTERIOR_SKELETON = 92

SECONDARY = ("2e_K500", "leaf_freq_K10", "leaf_rand_K10",
             "2f_top102", "learned_markov_102")
# strategies whose frozen plan must equal, page-for-page, the native method's own
# is_resident selection for that seed (2e_K500 keeps the skeleton; the two partials
# rank without page-type knowledge but still select exactly what the native run did).
DIRECT_PARITY = ("2e_K500", "2f_top102", "learned_markov_102")
LEAF_ONLY = ("leaf_freq_K10", "leaf_rand_K10")
# the two None-gate strategies land on an emergent, seed-uniform interior/leaf split.
EMERGENT_SPLIT = ("2f_top102", "learned_markov_102")

# import the generator module by path (it is a script, not a package member)
_spec = importlib.util.spec_from_file_location(
    "build_artifact_manifest", os.path.join(OW, "build_artifact_manifest.py"))
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

# per-seed expected counts + provenance are DATA, read from the frozen pin (single
# source of truth), never hard-coded as universal invariants.
with open(NATIVE_PIN) as _f:
    _PIN = json.load(_f)
_PIN_KEYED = _PIN["keyed_strategy_plans"][WORKLOAD]


def pin_entry(strat, seed):
    return _PIN_KEYED[str(seed)][strat]


def exp_pages(strat, seed):
    return pin_entry(strat, seed)["expected_pages"]


def exp_interior(strat, seed):
    return pin_entry(strat, seed)["expected_interior_pages"]


def exp_leaf(strat, seed):
    return pin_entry(strat, seed)["expected_leaf_pages"]


def have_manifest():
    return os.path.exists(ARTIFACTS) and os.path.exists(_fixture.CANONICAL_DB)


def keyed_csv(strat, seed):
    return os.path.join(KEYED_DIR, "%s_%s_seed%d.csv" % (strat, WORKLOAD, seed))


def native_path(strat, seed):
    """Native source of record for this (strategy, seed), resolved from the pin."""
    return os.path.join(REPO, pin_entry(strat, seed)["native_source"]["path"])


def plan_pages(path):
    with open(path, newline="") as f:
        return {int(r["page_number"]) for r in csv.DictReader(f)}


def native_selection_pages(path):
    with open(path, newline="") as f:
        return {int(r["page_number"]) for r in csv.DictReader(f)
                if int(r["is_resident"]) == 1}


def _interior_offsets():
    with open(os.path.join(OW, "config/plans/interior_pages.csv"), newline="") as f:
        return [int(r["file_offset"]) for r in csv.DictReader(f)]


def interior_skeleton_pages():
    return {o // 4096 + 1 for o in _interior_offsets()}


def full_request(strategy, h, **kw):
    base = dict(request_id="sec-" + strategy, workload=WORKLOAD,
                strategy=strategy, seed=1, first_operation_id=0,
                diagnostic_mode=False, cold_reset=True,
                expected_artifact_manifest_hash=h, pair_id="pair-1",
                repetition_id=0, schedule_position=1, schedule_seed=20260825,
                run_config_sha256="c" * 64, expected_action_image_digest=IMAGE,
                handle_mode="warm")
    base.update(kw)
    return base


# --------------------------------------------------------------------------- L
class TestNativeParity(unittest.TestCase):
    """Section L -- the load-bearing gate. Every frozen secondary plan must be the
    research method's own per-seed selection. No manifest/DB needed."""

    def test_native_sources_present(self):
        for strat in SECONDARY:
            for seed in SEEDS:
                self.assertTrue(os.path.exists(native_path(strat, seed)),
                                native_path(strat, seed))

    def test_direct_parity_plan_equals_native_selection(self):
        # 2e_K500 / 2f_top102 / learned_markov_102: exact page-set equality with the
        # native method's is_resident selection, per seed.
        for strat in DIRECT_PARITY:
            for seed in SEEDS:
                plan = plan_pages(keyed_csv(strat, seed))
                native = native_selection_pages(native_path(strat, seed))
                self.assertEqual(
                    plan, native,
                    "%s seed %d: plan != native residency; diff=%s"
                    % (strat, seed, sorted(plan ^ native)[:20]))
                self.assertEqual(len(plan), exp_pages(strat, seed),
                                 "%s seed %d size" % (strat, seed))

    def test_leaf_freq_equals_hot_leaves(self):
        # leaf_freq_K10 == the top-10 hot leaves = 2e_K10 native residency minus the
        # 92-page interior skeleton (select_pages: "non-interior == top_leaves").
        skeleton = interior_skeleton_pages()
        for seed in SEEDS:
            hot_leaves = native_selection_pages(native_path("leaf_freq_K10", seed)) - skeleton
            self.assertEqual(len(hot_leaves), 10, "seed %d hot-leaf pool" % seed)
            plan = plan_pages(keyed_csv("leaf_freq_K10", seed))
            self.assertEqual(plan, hot_leaves,
                             "leaf_freq_K10 seed %d != top-10 hot leaves" % seed)
            self.assertTrue(plan.isdisjoint(skeleton),
                            "leaf_freq_K10 seed %d touches interior" % seed)

    def test_leaf_rand_is_interior_free_and_contrasts_frequency(self):
        # leaf_rand_K10 is 10 leaves drawn from the non-hot pool: interior-free, and
        # distinct from the frequency top-10 (the ablation contrast). It is NOT a subset
        # of any native residency file, so parity is shape + contrast, not set-equality.
        skeleton = interior_skeleton_pages()
        for seed in SEEDS:
            rand = plan_pages(keyed_csv("leaf_rand_K10", seed))
            freq = plan_pages(keyed_csv("leaf_freq_K10", seed))
            self.assertEqual(len(rand), 10, "leaf_rand_K10 seed %d size" % seed)
            self.assertTrue(rand.isdisjoint(skeleton),
                            "leaf_rand_K10 seed %d touches interior" % seed)
            self.assertNotEqual(rand, freq,
                                "leaf_rand_K10 seed %d equals frequency leaves" % seed)

    def test_plan_and_native_shas_match_pin(self):
        # freeze check: the committed plan + native-source bytes are exactly the pin.
        for strat in SECONDARY:
            for seed in SEEDS:
                e = pin_entry(strat, seed)
                self.assertEqual(gen.sha256_file(keyed_csv(strat, seed)), e["sha256"],
                                 "%s seed %d plan sha" % (strat, seed))
                self.assertEqual(gen.sha256_file(native_path(strat, seed)),
                                 e["native_source"]["sha256"],
                                 "%s seed %d native sha" % (strat, seed))


# --------------------------------------------------------------------------- N
class TestPureInvariants(unittest.TestCase):
    def test_supported_and_keyed_sets(self):
        for strat in SECONDARY:
            self.assertIn(strat, main.SUPPORTED_STRATEGIES, strat)
            self.assertIn(strat, main.KEYED_STRATEGIES, strat)
            # keyed => must NOT carry a static global delivery invariant.
            self.assertNotIn(strat, main.DELIVERY_INVARIANTS, strat)

    def test_request_schema_accepts_each(self):
        for strat in SECONDARY:
            problems = main.validate_request_schema(full_request(strat, "a" * 64))
            self.assertFalse(
                [p for p in problems if "strategy must be one of" in p],
                "%s: %s" % (strat, problems))

    def test_ws2_gate_recognizes_all_five(self):
        import ast
        import re
        with open(GATE_SCRIPT) as f:
            m = re.search(r"impl = (\{[^}]*\})", f.read())
        self.assertIsNotNone(m, "impl set not found in 05_full_matrix.sh")
        impl = ast.literal_eval(m.group(1))
        for strat in SECONDARY:
            self.assertIn(strat, impl, strat)

    def test_csv_shape_and_counts_match_pin(self):
        skeleton = set(_interior_offsets())
        for strat in SECONDARY:
            for seed in SEEDS:
                path = keyed_csv(strat, seed)
                self.assertTrue(os.path.exists(path), path)
                with open(path, newline="") as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), exp_pages(strat, seed),
                                 "%s seed %d rows" % (strat, seed))
                offs = [(int(r["page_number"]), int(r["file_offset"])) for r in rows]
                for pn, fo in offs:
                    self.assertEqual(fo, (pn - 1) * 4096,
                                     "%s seed %d pn=%d" % (strat, seed, pn))
                pns = [pn for pn, _ in offs]
                self.assertEqual(pns, sorted(pns),
                                 "%s seed %d not page-ordered" % (strat, seed))
                self.assertEqual(len(set(pns)), len(pns),
                                 "%s seed %d duplicate page" % (strat, seed))
                file_offs = {fo for _, fo in offs}
                interior = len(file_offs & skeleton)
                self.assertEqual(interior, exp_interior(strat, seed),
                                 "%s seed %d interior" % (strat, seed))
                self.assertEqual(len(file_offs) - interior, exp_leaf(strat, seed),
                                 "%s seed %d leaf" % (strat, seed))

    def test_2e_k500_keeps_full_skeleton(self):
        skeleton = set(_interior_offsets())
        for seed in SEEDS:
            file_offs = {(pn - 1) * 4096 for pn in plan_pages(keyed_csv("2e_K500", seed))}
            self.assertEqual(exp_pages("2e_K500", seed), 592, "seed %d total" % seed)
            self.assertEqual(exp_interior("2e_K500", seed), INTERIOR_SKELETON)
            self.assertEqual(file_offs & skeleton, skeleton,
                             "2e_K500 seed %d interior half != 92-skeleton" % seed)

    def test_leaf_only_gate_class(self):
        for strat in LEAF_ONLY:
            for seed in SEEDS:
                self.assertEqual(exp_pages(strat, seed), 10, "%s seed %d" % (strat, seed))
                self.assertEqual(exp_interior(strat, seed), 0,
                                 "%s seed %d interior must be 0" % (strat, seed))
                self.assertEqual(exp_leaf(strat, seed), 10, "%s seed %d" % (strat, seed))

    def test_emergent_split_is_recorded_51_51_uniform(self):
        # The None-gate strategies (no page-type knowledge) land on exactly 51 interior
        # / 51 leaf for EVERY seed. The pin records this; the gate never imposes it.
        for strat in EMERGENT_SPLIT:
            interiors = {exp_interior(strat, seed) for seed in SEEDS}
            leaves = {exp_leaf(strat, seed) for seed in SEEDS}
            totals = {exp_pages(strat, seed) for seed in SEEDS}
            self.assertEqual(totals, {102}, "%s total must be a fixed 102 budget" % strat)
            self.assertEqual(interiors, {51}, "%s interior not uniform 51" % strat)
            self.assertEqual(leaves, {51}, "%s leaf not uniform 51" % strat)


class TestCrosscheckPinSecondaryFailsClosed(unittest.TestCase):
    """crosscheck_pin pins every secondary seed's sha + per-seed counts and must fail
    closed on tamper. Exercises all three gate classes via KEYED_SPECS."""

    @classmethod
    def setUpClass(cls):
        cls.pin = _PIN
        l5 = cls.pin["strategy_plans"]["layers_5"]
        keyed = cls.pin["keyed_strategy_plans"][WORKLOAD]
        strats = [spec["strategy"] for spec in gen.KEYED_SPECS]
        cls.good_meta = {
            strat: {s: {"sha": keyed[str(s)][strat]["sha256"],
                        "pages": keyed[str(s)][strat]["expected_pages"],
                        "interior": keyed[str(s)][strat]["expected_interior_pages"],
                        "leaf": keyed[str(s)][strat]["expected_leaf_pages"]}
                    for s in SEEDS}
            for strat in strats}
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

    def test_tampered_secondary_sha_fails_closed(self):
        for strat in SECONDARY:
            bad = self._meta_copy()
            bad[strat][1]["sha"] = "0" * 64
            with self.assertRaises(SystemExit, msg=strat):
                self._call(bad)

    def test_tampered_secondary_count_fails_closed(self):
        for strat in SECONDARY:
            bad = self._meta_copy()
            bad[strat][3]["pages"] = bad[strat][3]["pages"] + 1
            with self.assertRaises(SystemExit, msg=strat):
                self._call(bad)

    def test_tampered_secondary_interior_fails_closed(self):
        for strat in SECONDARY:
            bad = self._meta_copy()
            bad[strat][7]["interior"] = bad[strat][7]["interior"] + 1
            with self.assertRaises(SystemExit, msg=strat):
                self._call(bad)


# ----------------------------------------------------------- session (needs manifest)
@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestSessionKeyedLoad(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)

    def test_all_fifty_plans_cache_with_per_seed_counts(self):
        for strat in SECONDARY:
            for seed in SEEDS:
                plan = self.s.strategy_plan(strat, WORKLOAD, seed)
                self.assertIsNotNone(plan, "%s seed %d not cached" % (strat, seed))
                self.assertEqual(len(plan["offsets"]), exp_pages(strat, seed),
                                 "%s seed %d" % (strat, seed))
                interior = sum(1 for o in plan["offsets"]
                               if o in self.s.interior_offset_set)
                self.assertEqual(interior, exp_interior(strat, seed),
                                 "%s seed %d interior" % (strat, seed))
                self.assertEqual(len(plan["offsets"]) - interior, exp_leaf(strat, seed),
                                 "%s seed %d leaf" % (strat, seed))

    def test_generic_lookup_serves_secondary_alongside_prior(self):
        # SAME cache/lookup returns headline + secondary consumers, no per-strategy loader.
        k10 = self.s.strategy_plan("2e_K10", WORKLOAD, 1)
        self.assertIsNotNone(k10)
        self.assertEqual(len(k10["offsets"]), 102)
        for strat in SECONDARY:
            p = self.s.strategy_plan(strat, WORKLOAD, 1)
            self.assertIsNotNone(p, strat)
            self.assertNotEqual(p["plan_sha256"], k10["plan_sha256"], strat)

    def test_lookup_miss_returns_none(self):
        for strat in SECONDARY:
            self.assertIsNone(self.s.strategy_plan(strat, WORKLOAD, 99), strat)
            self.assertIsNone(self.s.strategy_plan(strat, "workload_a", 1), strat)

    def test_per_seed_shas_distinct_where_expected(self):
        # leaf_rand + the direct-parity strategies vary per seed -> 10 distinct shas.
        # learned_markov may collapse to fewer (LOSO models can coincide); leaf_freq
        # tracks the seed-stable hot leaves. So only assert distinctness where the
        # native method is per-seed by construction.
        for strat in ("2e_K500", "2f_top102", "leaf_rand_K10"):
            shas = {self.s.strategy_plan(strat, WORKLOAD, s)["plan_sha256"] for s in SEEDS}
            self.assertEqual(len(shas), 10, "%s per-seed shas not all distinct" % strat)


@unittest.skipUnless(have_manifest(), "live artifacts.json / canonical DB absent")
class TestKeyedSelectOffsets(unittest.TestCase):
    def setUp(self):
        self.s = session_mod.Session(ARTIFACTS, resolve_root=REPO)
        self.s.validate_artifacts()
        self.assertTrue(self.s.validated, self.s.validation_reasons)

    def test_keyed_select_delivers_pinned_footprint(self):
        for strat in SECONDARY:
            for seed in (1, 6, 8):
                offs = main.select_offsets(strat, self.s, WORKLOAD, seed)
                self.assertEqual(len(offs), exp_pages(strat, seed),
                                 "%s seed %d" % (strat, seed))
                interior = sum(1 for o in offs if o in self.s.interior_offset_set)
                self.assertEqual(interior, exp_interior(strat, seed),
                                 "%s seed %d interior" % (strat, seed))

    def test_missing_keyed_plan_fails_closed(self):
        for strat in SECONDARY:
            with self.assertRaises(ValueError):
                main.select_offsets(strat, self.s, WORKLOAD, 99)
            with self.assertRaises(ValueError):
                main.select_offsets(strat, self.s, "workload_a", 1)

    def test_static_and_prior_keyed_unaffected(self):
        self.assertEqual(main.select_offsets("baseline", self.s, WORKLOAD, 1), [])
        self.assertEqual(len(main.select_offsets("2d", self.s, WORKLOAD, 1)), 92)
        self.assertEqual(len(main.select_offsets("2e_K10", self.s, WORKLOAD, 1)), 102)

    def test_delivery_invariants_derive_per_seed(self):
        for strat in SECONDARY:
            for seed in (1, 8):
                inv = main.delivery_invariants_for(strat, self.s, WORKLOAD, seed)
                self.assertEqual(inv, {
                    "selected_page_count": exp_pages(strat, seed),
                    "selected_interior_count": exp_interior(strat, seed),
                    "selected_leaf_count": exp_leaf(strat, seed),
                    "delivered_page_count": exp_pages(strat, seed)},
                    "%s seed %d" % (strat, seed))
            self.assertNotIn(strat, main.DELIVERY_INVARIANTS, strat)


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

    def test_measured_each_secondary_valid(self):
        for strat in SECONDARY:
            r = main.handle(full_request(strat, self.h, seed=1,
                                         request_id="sec-%s" % strat), self.s)
            self.assertIsNone(r.get("error_stage"), r.get("error"))
            self.assertEqual(
                (r["selected_page_count"], r["selected_interior_count"],
                 r["selected_leaf_count"], r["delivered_page_count"]),
                (exp_pages(strat, 1), exp_interior(strat, 1),
                 exp_leaf(strat, 1), exp_pages(strat, 1)), strat)
            self.assertTrue(r["delivery_valid"], strat)
            self.assertTrue(r["measured_valid"], strat)
            self.assertEqual(r["plan_sha256"],
                             self.s.strategy_plan(strat, WORKLOAD, 1)["plan_sha256"],
                             strat)
            # success responses must not emit a top-level null error.
            self.assertNotIn("error", r, strat)

    def test_truncated_delivery_not_measured_valid(self):
        with mock.patch.object(residency.PageMap, "deliver_willneed",
                               return_value=exp_pages("2f_top102", 1) - 1):
            r = main.handle(full_request("2f_top102", self.h, seed=1), self.s)
        self.assertFalse(r["delivery_valid"])
        self.assertFalse(r["measured_valid"])

    def test_prior_strategies_regression(self):
        r10 = main.handle(full_request("2e_K10", self.h, seed=1,
                                       request_id="sec-k10"), self.s)
        self.assertEqual(r10["selected_page_count"], 102)
        self.assertTrue(r10["measured_valid"])
        r2d = main.handle(full_request("2d", self.h, request_id="sec-2d"), self.s)
        self.assertEqual(r2d["selected_interior_count"], 92)
        self.assertTrue(r2d["measured_valid"])


if __name__ == "__main__":
    unittest.main()
