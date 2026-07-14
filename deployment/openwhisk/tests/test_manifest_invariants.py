"""Tests for the artifact-manifest generator invariants: page-size decoding,
interior-plan validation (alignment / off-by-one / duplicate / out-of-range /
count), and that the frozen first-query oracle is computed by the same code the
action uses."""
import csv
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


@unittest.skipUnless(os.path.exists(EXAMPLE), "example manifest missing")
class TestOracleSingleSource(unittest.TestCase):
    def test_manifest_oracle_matches_action_oracle(self):
        with open(EXAMPLE) as f:
            m = json.load(f)
        db = os.path.join(REPO, m["database"]["path"])
        import sqlite3
        conn = sqlite3.connect(db)
        try:
            for seed, byop in m["first_query_oracle"]["A"].items():
                for fop, entry in byop.items():
                    hit, digest = oracle.digest_row(oracle.run_read(conn, entry["key"]))
                    self.assertEqual(hit, entry["expected_hit"])
                    self.assertEqual(digest, entry["expected_digest"])
        finally:
            conn.close()

    def test_denominator_is_page_count_not_92(self):
        with open(EXAMPLE) as f:
            m = json.load(f)
        self.assertEqual(m["expected_relevant_page_count"], m["database"]["page_count"])
        self.assertEqual(m["interior_page_count"], 92)


if __name__ == "__main__":
    unittest.main()
