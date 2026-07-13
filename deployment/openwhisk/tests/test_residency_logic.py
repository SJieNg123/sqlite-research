"""Unit tests for the residency/selection pure logic (no syscalls required)."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))

import residency  # noqa: E402
import main  # noqa: E402


class TestColdThreshold(unittest.TestCase):
    def test_zero_interiors_is_cold(self):
        self.assertTrue(residency.cold_threshold_passed(0))

    def test_any_resident_interior_is_not_cold(self):
        self.assertFalse(residency.cold_threshold_passed(1))
        self.assertFalse(residency.cold_threshold_passed(92))


class TestCountIn(unittest.TestCase):
    def test_counts_only_resident_offsets(self):
        # 4 pages; pages 0 and 2 resident (bit0 set).
        vec = bytes([1, 0, 1, 0])
        offs = [0, residency.PAGE, 2 * residency.PAGE, 3 * residency.PAGE]
        self.assertEqual(residency.count_in(vec, offs), 2)

    def test_out_of_range_offsets_ignored(self):
        vec = bytes([1])
        self.assertEqual(residency.count_in(vec, [0, 999 * residency.PAGE]), 1)


class TestPlanLoading(unittest.TestCase):
    def _plan(self, rows):
        fd, p = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("page_number,file_offset\n")
            for pn, off in rows:
                f.write("%d,%d\n" % (pn, off))
        return p

    def test_loads_offsets_in_order(self):
        p = self._plan([(2, 4096), (3, 8192)])
        try:
            self.assertEqual(main.load_interior_offsets(p), [4096, 8192])
        finally:
            os.remove(p)

    def test_duplicate_page_fails(self):
        p = self._plan([(2, 4096), (2, 4096)])
        try:
            with self.assertRaises(ValueError):
                main.load_interior_offsets(p)
        finally:
            os.remove(p)


class TestSelectPages(unittest.TestCase):
    def test_baseline_selects_zero(self):
        self.assertEqual(main.select_pages("baseline", [1, 2, 3], 3), [])

    def test_2d_selects_all_interiors(self):
        self.assertEqual(main.select_pages("2d", [10, 20, 30], 3), [10, 20, 30])

    def test_2d_wrong_count_fails(self):
        with self.assertRaises(ValueError):
            main.select_pages("2d", [10, 20], 92)

    def test_unsupported_strategy_fails(self):
        with self.assertRaises(ValueError):
            main.select_pages("2f_slru", [1], 1)


if __name__ == "__main__":
    unittest.main()
