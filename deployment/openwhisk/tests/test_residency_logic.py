"""Unit tests for residency primitives, the efficacy-based reset diagnostics,
and strategy selection."""
import os
import sys
import types
import unittest

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "action"))

import residency  # noqa: E402
import main  # noqa: E402

DB = os.path.join(REPO, "pipeline/preparation/layout_rewriter/runs/test.db")


class TestColdThreshold(unittest.TestCase):
    def test_zero_is_cold(self):
        self.assertTrue(residency.cold_threshold_passed(0))

    def test_nonzero_is_not_cold(self):
        self.assertFalse(residency.cold_threshold_passed(1))
        self.assertFalse(residency.cold_threshold_passed(92))


class TestCountIn(unittest.TestCase):
    def test_counts_resident_offsets(self):
        vec = bytes([1, 0, 1, 0])
        offs = [i * residency.PAGE for i in range(4)]
        self.assertEqual(residency.count_in(vec, offs), 2)

    def test_out_of_range_ignored(self):
        self.assertEqual(residency.count_in(bytes([1]), [0, 999 * residency.PAGE]), 1)


def fake_session(offsets, interior_count=92):
    s = types.SimpleNamespace()
    s.interior_offsets = list(offsets)
    s.interior_offset_set = set(offsets)
    s.manifest = {"interior_page_count": interior_count}
    return s


class TestSelectOffsets(unittest.TestCase):
    def test_baseline_zero(self):
        s = fake_session([10, 20])
        self.assertEqual(main.select_offsets("baseline", s), [])

    def test_2d_all_interiors(self):
        offs = [(p) * residency.PAGE for p in range(1, 93)]
        s = fake_session(offs, 92)
        self.assertEqual(main.select_offsets("2d", s), offs)

    def test_2d_wrong_count_fails(self):
        s = fake_session([10, 20], 92)
        with self.assertRaises(ValueError):
            main.select_offsets("2d", s)

    def test_unsupported_fails(self):
        with self.assertRaises(ValueError):
            main.select_offsets("2f_slru", fake_session([1]))


@unittest.skipUnless(os.path.exists(DB), "reference DB missing")
class TestColdResetDiagnostics(unittest.TestCase):
    def setUp(self):
        # first 92 page offsets as a stand-in interior set for the shape test
        self.interiors = [(p) * residency.PAGE for p in range(1, 93)]

    def test_reset_returns_full_diagnostics(self):
        d = residency.cold_reset_and_verify(DB, self.interiors)
        for k in ("resident_pages_before_reset", "resident_interiors_before_reset",
                  "attempted_methods", "cold_reset_method",
                  "resident_pages_after_reset", "resident_interiors_after_reset",
                  "cold_reset_succeeded", "cold_threshold_passed"):
            self.assertIn(k, d)
        self.assertTrue(d["attempted_methods"])
        for a in d["attempted_methods"]:
            for k in ("method", "rc", "errno", "resident_interiors_after"):
                self.assertIn(k, a)

    def test_chain_stops_when_cold(self):
        d = residency.cold_reset_and_verify(DB, self.interiors)
        # if the final state is cold, the last attempt achieved zero interiors
        if d["cold_threshold_passed"]:
            self.assertEqual(d["attempted_methods"][-1]["resident_interiors_after"], 0)


if __name__ == "__main__":
    unittest.main()
