#!/usr/bin/env python3
"""Tests for the canonical workload naming migration.

Two guarantees:
  1. The registry (config/workload_registry.py) resolves legacy IDs, canonical
     IDs, and display names correctly, with no alias collisions, and classifies
     CHURN as a mutation schedule and YD/YE as YCSB reconstructions.
  2. paper/main.tex (paper-visible text) contains no forbidden legacy tokens.
     Legacy IDs are permitted ONLY in the registry aliases, the loader, the
     immutable CSV filters, historical provenance / audit notes, and unmodified
     legacy scripts -- never in the paper.

Run: python3 -m unittest tests.test_workload_naming   (from repo root)
  or python3 tests/test_workload_naming.py
"""
import re
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "config"))

from workload_registry import (  # noqa: E402
    normalize_workload_id,
    workload_display_name,
    workload_metadata,
    is_measured,
    is_mutation_schedule,
    all_records,
)


class RegistryMapping(unittest.TestCase):
    def test_tail_mixed_aliases_collapse(self):
        # C and C_mixed are two legacy spellings of the one Tail-Mixed workload.
        self.assertEqual(
            normalize_workload_id("C"), normalize_workload_id("C_mixed"))
        self.assertEqual(
            normalize_workload_id("C"), "read_tail_mixed_20k")
        self.assertEqual(workload_display_name("C_mixed"), "Tail-Mixed")

    def test_documented_display_names(self):
        expected = {
            "A": "Scattered-Zipf",
            "B": "Uniform-100K",
            "C": "Tail-Mixed",
            "C_hit": "Tail-Hit",
            "Z": "Concentrated-Zipf",
            "YD": "Latest-Aging",
            "YE": "Short-Scan Aging",
            "CHURN": "Mixed-Mutation Churn",
        }
        for legacy, disp in expected.items():
            self.assertEqual(workload_display_name(legacy), disp)

    def test_no_alias_collision(self):
        # Every alias/canonical/display token resolves to exactly one canonical
        # id; a collision would have raised at import, but assert explicitly.
        seen = {}
        for rec in all_records():
            canon = rec["canonical_id"]
            tokens = [canon, rec["display_name"], *rec.get("legacy_aliases", [])]
            for tok in tokens:
                got = normalize_workload_id(tok)
                self.assertEqual(got, canon, f"{tok!r} -> {got!r}")
                prev = seen.get(tok)
                self.assertIn(prev, (None, canon),
                              f"alias collision on {tok!r}")
                seen[tok] = canon

    def test_churn_is_mutation_schedule(self):
        self.assertTrue(is_mutation_schedule("CHURN"))
        self.assertFalse(is_measured("CHURN"))
        for measured in ("A", "B", "C", "C_hit", "YD", "YE", "Z"):
            self.assertFalse(is_mutation_schedule(measured))
            self.assertTrue(is_measured(measured))

    def test_yd_ye_are_python_reconstructions(self):
        for recon in ("YD", "YE"):
            self.assertEqual(
                workload_metadata(recon)["category"], "ycsb_reconstruction")

    def test_unknown_id_fails_loud(self):
        with self.assertRaises(KeyError):
            normalize_workload_id("not-a-workload")


class PaperHasNoForbiddenTerms(unittest.TestCase):
    # Legacy tokens that must never appear in paper-visible LaTeX. "workload A"
    # style references and the letter IDs collide with the standard YCSB core
    # workloads A-F, which is exactly what the migration removes. The bare
    # "A--F" reference to the *standard* YCSB set is allowed (it is not a
    # "workload X" token and names real YCSB workloads).
    FORBIDDEN = re.compile(
        r"legacy|workload [ABCZ]\b|C\\_mixed|C\\_hit|\bYD\b|\bYE\b|\bCHURN\b")

    def test_main_tex_clean(self):
        tex = _ROOT / "paper" / "main.tex"
        self.assertTrue(tex.exists(), f"missing {tex}")
        hits = []
        for i, line in enumerate(tex.read_text(encoding="utf-8").splitlines(), 1):
            if self.FORBIDDEN.search(line):
                hits.append(f"{i}: {line.strip()[:120]}")
        self.assertEqual(hits, [], "forbidden legacy tokens in paper:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
