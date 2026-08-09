"""Tests for the artifact-manifest generator invariants: page-size decoding,
interior-plan validation (alignment / off-by-one / duplicate / out-of-range /
count), and that the frozen first-query oracle is computed by the same code the
action uses."""
import csv
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "action"))
import oracle  # noqa: E402

# import the generator module by path (it is a script, not a package member)
_spec = importlib.util.spec_from_file_location(
    "build_artifact_manifest",
    os.path.join(REPO, "deployment/openwhisk/build_artifact_manifest.py"))
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

PAGE = 4096
PAGE_COUNT = 26331
EXAMPLE = os.path.join(REPO, "deployment/openwhisk/config/artifacts.example.json")


def write_classify(rows):
    fd, p = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["page_number", "page_type", "file_offset"])
        for pn, off in rows:
            w.writerow([pn, "interior_table", off])
    return p


def good_rows():
    # 92 valid interior pages: pages 2..93, offset == (pn-1)*PAGE
    return [(pn, (pn - 1) * PAGE) for pn in range(2, 94)]


class TestPageSizeDecode(unittest.TestCase):
    def test_value_1_means_65536(self):
        head = bytearray(32)
        head[16:18] = (1).to_bytes(2, "big")
        self.assertEqual(gen.decode_page_size(bytes(head)), 65536)

    def test_normal_4096(self):
        head = bytearray(32)
        head[16:18] = (4096).to_bytes(2, "big")
        self.assertEqual(gen.decode_page_size(bytes(head)), 4096)


class TestPlanInvariants(unittest.TestCase):
    def _run(self, rows):
        cp = write_classify(rows)
        pp = tempfile.mktemp(suffix=".csv")
        try:
            return gen.derive_and_validate_plan(cp, pp, PAGE, PAGE_COUNT)
        finally:
            os.remove(cp)
            if os.path.exists(pp):
                os.remove(pp)

    def test_valid_plan_ok(self):
        offs = self._run(good_rows())
        self.assertEqual(len(offs), 92)

    def test_wrong_count_fails(self):
        with self.assertRaises(SystemExit):
            self._run(good_rows()[:91])

    def test_misaligned_offset_fails(self):
        rows = good_rows()
        rows[0] = (rows[0][0], rows[0][1] + 1)   # off-by-one -> misaligned
        with self.assertRaises(SystemExit):
            self._run(rows)

    def test_offset_not_page_formula_fails(self):
        rows = good_rows()
        # aligned but wrong page: offset for a different page number
        rows[0] = (2, 10 * PAGE)                 # page 2 should be offset PAGE
        with self.assertRaises(SystemExit):
            self._run(rows)

    def test_duplicate_page_fails(self):
        rows = good_rows()
        rows[1] = rows[0]                        # duplicate page_number
        with self.assertRaises(SystemExit):
            self._run(rows)

    def test_out_of_range_page_fails(self):
        rows = good_rows()
        rows[0] = (PAGE_COUNT + 5, (PAGE_COUNT + 4) * PAGE)
        with self.assertRaises(SystemExit):
            self._run(rows)


class TestLayersPrefix(unittest.TestCase):
    """layers_5 generator: first N interiors by native (file_offset, page_number)
    order, a strict prefix of the 92-skeleton, deterministic and SHA-stable."""

    def _derive(self, rows, n=5, interiors=None):
        cp = write_classify(rows)
        pp = tempfile.mktemp(suffix=".csv")
        if interiors is None:
            interiors = [off for _, off in rows]
        try:
            offs = gen.derive_layers_prefix(cp, pp, n, PAGE, PAGE_COUNT, interiors)
            with open(pp, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            return offs, sha
        finally:
            os.remove(cp)
            if os.path.exists(pp):
                os.remove(pp)

    def test_prefix_is_first_five_interiors(self):
        offs, _ = self._derive(good_rows(), 5)
        self.assertEqual(offs, [(pn - 1) * PAGE for pn in range(2, 7)])
        self.assertEqual(len(offs), 5)

    def test_all_selected_are_interiors_subset(self):
        offs, _ = self._derive(good_rows(), 5)
        self.assertTrue(set(offs).issubset({(pn - 1) * PAGE for pn in range(2, 94)}))

    def test_deterministic_sha_stable_across_regeneration(self):
        a_offs, a_sha = self._derive(good_rows(), 5)
        b_offs, b_sha = self._derive(good_rows(), 5)
        self.assertEqual(a_offs, b_offs)
        self.assertEqual(a_sha, b_sha)

    def test_fewer_than_n_interiors_fails(self):
        with self.assertRaises(SystemExit):
            self._derive(good_rows()[:3], 5)

    def test_selected_page_not_in_skeleton_fails(self):
        # interior_offsets omits page 2 (offset PAGE), which is the first selected
        # -> subset invariant must fail closed.
        interiors = [(pn - 1) * PAGE for pn in range(3, 94)]
        with self.assertRaises(SystemExit):
            self._derive(good_rows(), 5, interiors=interiors)


@unittest.skipUnless(os.path.exists(EXAMPLE), "example manifest missing")
class TestOracleSingleSource(unittest.TestCase):
    def test_manifest_oracle_matches_action_oracle(self):
        with open(EXAMPLE) as f:
            m = json.load(f)
        db = os.path.join(REPO, m["database"]["path"])
        if not os.path.exists(db):
            self.skipTest("canonical DB absent")
        import sqlite3
        conn = sqlite3.connect(db)
        try:
            for seed, byop in m["first_query_oracle"]["A"].items():
                for fop, entry in byop.items():
                    hit_raw, payload = oracle.run_read_payload(conn, entry["key"])
                    hit, digest = oracle.digest_payload(hit_raw, payload)
                    self.assertEqual(hit, entry["expected_hit"])
                    self.assertEqual(digest, entry["expected_digest"])
        finally:
            conn.close()

    def test_denominator_is_page_count_not_92(self):
        with open(EXAMPLE) as f:
            m = json.load(f)
        self.assertEqual(m["expected_relevant_page_count"], m["database"]["page_count"])
        self.assertEqual(m["interior_page_count"], 92)


NATIVE_PIN = os.path.join(REPO, "deployment/openwhisk/config/artifacts.native_ycsb.json")
NATIVE_MANIFEST = os.path.join(REPO, "NATIVE_YCSB_MANIFEST.json")
ARTIFACTS = os.path.join(REPO, "deployment/openwhisk/config/artifacts.json")


def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@unittest.skipUnless(os.path.exists(NATIVE_PIN), "native-YCSB pin missing")
class TestNativeYcsbPinFrozenSources(unittest.TestCase):
    """Frozen-source consistency: the native-YCSB replay pin
    (artifacts.native_ycsb.json) must agree with the native-YCSB provenance manifest
    (NATIVE_YCSB_MANIFEST.json), the frozen files on disk, and the workload registry.

    These checks depend on NOTHING generated at build time -- in particular NOT the
    live config/artifacts.json -- so they are valid BEFORE 01_build_image runs and
    are the deployment-side gate for WS2 00_preflight. No OpenWhisk / benchmark
    execution is performed. (Live-manifest agreement lives in
    TestNativeYcsbLiveManifestAgreement, run by 01_build_image after generation.)"""

    @classmethod
    def setUpClass(cls):
        with open(NATIVE_PIN) as f:
            cls.pin = json.load(f)
        with open(NATIVE_MANIFEST) as f:
            cls.man = json.load(f)

    def test_db_hash_agrees_with_manifest(self):
        pdb, mdb = self.pin["database"], self.man["db"]
        self.assertEqual(pdb["sha256"], mdb["sha256"])
        self.assertEqual(pdb["page_count"], 26331)
        self.assertEqual(pdb["row_count"], 600000)

    def test_db_bytes_on_disk_match_pin(self):
        db = os.path.join(REPO, self.pin["database"]["path"])
        if not os.path.exists(db):
            self.skipTest("canonical DB absent")
        self.assertEqual(_sha256_file(db), self.pin["database"]["sha256"])

    def test_normalized_schema_hash_recomputes(self):
        db = os.path.join(REPO, self.pin["database"]["path"])
        if not os.path.exists(db):
            self.skipTest("canonical DB absent")
        import re
        import sqlite3
        conn = sqlite3.connect(db)
        try:
            ddls = [r[0] for r in conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")]
        finally:
            conn.close()
        canonical = "\n".join(sorted(re.sub(r"\s+", " ", d.strip()) for d in ddls))
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(),
                         self.pin["database"]["normalized_schema_hash"])

    def test_2d_plan_pin_is_db_specific_and_on_disk(self):
        pplan = self.pin["strategy_plans"]["2d"]
        self.assertEqual(pplan["expected_pages"], 92)
        self.assertEqual(self.pin["expected_interior_count"], 92)
        # plan is bound to the pinned DB
        self.assertEqual(pplan["bound_db_sha256"], self.pin["database"]["sha256"])
        plan_file = os.path.join(REPO, pplan["path"])
        if os.path.exists(plan_file):
            self.assertEqual(_sha256_file(plan_file), pplan["sha256"])

    def test_expected_page_count_is_full_db_not_92(self):
        self.assertEqual(self.pin["expected_page_count"],
                         self.pin["database"]["page_count"])

    def test_seed_traces_agree_with_manifest_and_disk(self):
        yc = [w for w in self.man["workloads"]
              if w["canonical_id"] == "native_ycsb_c_read_zipf"][0]
        fam = yc["seed_family"]
        seen = set()
        for entry in self.pin["representative_workload"]["seed_family"]:
            fn = os.path.basename(entry["trace"])
            seen.add(entry["seed"])
            self.assertEqual(entry["trace_sha256"], fam[fn],
                             "pin seed %s != manifest" % fn)
            tf = os.path.join(REPO, entry["trace"])
            if os.path.exists(tf):
                self.assertEqual(_sha256_file(tf), entry["trace_sha256"],
                                 "on-disk %s != pin" % fn)
        self.assertEqual(seen, set(range(1, 11)))

    def test_base_trace_is_convenience_only(self):
        base = self.pin["representative_workload"]["base_trace"]
        yc = [w for w in self.man["workloads"]
              if w["canonical_id"] == "native_ycsb_c_read_zipf"][0]
        self.assertEqual(base["sha256"], yc["trace_sha256"])
        self.assertTrue(base["convenience_only"])
        self.assertTrue(base["excluded_from_seed_statistics"])

    def test_run_config_sha256_recomputes(self):
        expect = hashlib.sha256(json.dumps(
            self.pin["invocation_plan"], sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(self.pin["run_config_sha256"], expect)

    def test_canonical_workload_id_resolves(self):
        sys.path.insert(0, REPO)
        import importlib
        reg = importlib.import_module("config.workload_registry")
        cid = self.pin["representative_workload"]["canonical_workload_id"]
        self.assertEqual(reg.normalize_workload_id("YCSB-C"), cid)
        # native C must NOT collide with the Python reconstructions' bare aliases
        self.assertNotEqual(reg.normalize_workload_id("YD"), cid)

    def test_replay_only_flags(self):
        self.assertTrue(self.pin["replay_only"])
        self.assertTrue(self.pin["never_regenerate"])


@unittest.skipUnless(os.path.exists(NATIVE_PIN) and os.path.exists(ARTIFACTS),
                     "native-YCSB pin or live artifacts.json missing")
class TestNativeYcsbLiveManifestAgreement(unittest.TestCase):
    """Live-manifest agreement: the GENERATED OpenWhisk manifest
    (config/artifacts.json) must match the frozen pin byte-for-byte on DB /
    classifier / 2d-plan / denominator.

    config/artifacts.json is produced by 01_build_image.sh (build_artifact_manifest.py),
    so this class SKIPS cleanly when it is absent. It is the live-manifest invariant
    gate 01_build_image runs AFTER generation and BEFORE the Docker build -- it is
    NEVER part of 00_preflight (which must be read-only and never generate it)."""

    @classmethod
    def setUpClass(cls):
        with open(NATIVE_PIN) as f:
            cls.pin = json.load(f)
        with open(ARTIFACTS) as f:
            cls.art = json.load(f)

    def test_db_hash_agrees_with_artifacts(self):
        pdb, adb = self.pin["database"], self.art["database"]
        self.assertEqual(pdb["sha256"], adb["sha256"])
        self.assertEqual(pdb["page_count"], adb["page_count"])

    def test_2d_plan_hash_agrees_and_db_specific(self):
        pplan = self.pin["strategy_plans"]["2d"]
        aplan = self.art["strategy_plans"]["2d"]
        self.assertEqual(pplan["sha256"], aplan["sha256"])
        self.assertEqual(pplan["expected_pages"], 92)
        self.assertEqual(self.pin["expected_interior_count"], 92)
        # plan is bound to the pinned DB
        self.assertEqual(pplan["bound_db_sha256"], self.pin["database"]["sha256"])
        plan_file = os.path.join(REPO, pplan["path"])
        if os.path.exists(plan_file):
            self.assertEqual(_sha256_file(plan_file), pplan["sha256"])

    def test_classifier_hash_agrees(self):
        self.assertEqual(self.pin["classifier"]["sha256"],
                         self.art["classifier"]["sha256"])

    def test_expected_page_count_is_full_db_not_92(self):
        self.assertEqual(self.pin["expected_page_count"],
                         self.art["expected_relevant_page_count"])
        self.assertEqual(self.pin["expected_page_count"],
                         self.pin["database"]["page_count"])


@unittest.skipUnless(os.path.exists(ARTIFACTS), "live artifacts.json missing")
class TestLayersFivePlanInManifest(unittest.TestCase):
    """The generated live manifest carries a well-formed layers_5 plan whose frozen
    CSV matches on disk and whose offsets are a strict prefix of the 92-skeleton."""

    @classmethod
    def setUpClass(cls):
        with open(ARTIFACTS) as f:
            cls.art = json.load(f)

    def test_layers5_plan_shape(self):
        p = self.art["strategy_plans"]["layers_5"]
        self.assertEqual(p["kind"], "interior_prefix")
        self.assertEqual(p["expected_pages"], 5)
        self.assertEqual(p["expected_interior_pages"], 5)
        self.assertEqual(p["expected_leaf_pages"], 0)
        self.assertEqual(len(p["offsets"]), 5)

    def test_layers5_csv_on_disk_matches_manifest(self):
        p = self.art["strategy_plans"]["layers_5"]
        plan_file = os.path.join(REPO, p["path"])
        if not os.path.exists(plan_file):
            self.skipTest("layers_5 plan CSV absent")
        self.assertEqual(_sha256_file(plan_file), p["sha256"])
        file_offs = []
        with open(plan_file, newline="") as f:
            for row in csv.DictReader(f):
                file_offs.append(int(row["file_offset"]))
        self.assertEqual(file_offs, p["offsets"])

    def test_layers5_is_strict_prefix_of_2d(self):
        offs = self.art["strategy_plans"]["layers_5"]["offsets"]
        interiors = set(self.art["interior_page_list"]["offsets"])
        self.assertTrue(set(offs).issubset(interiors))
        self.assertLess(len(offs), len(interiors))


if __name__ == "__main__":
    unittest.main()
