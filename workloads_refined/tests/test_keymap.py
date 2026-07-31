#!/usr/bin/env python3
"""Mandatory keymap tests (spec §2.5). If either is red, the mapping scheme is void.

Run: python3 -m pytest tests/test_keymap.py   (or) python3 tests/test_keymap.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import keymap  # noqa: E402


def _load_dump(keys):
    """Write a synthetic YCSB load-phase dump for the given key strings."""
    fd, path = tempfile.mkstemp(suffix=".log")
    with os.fdopen(fd, "w") as fh:
        for k in keys:
            fh.write(f"INSERT usertable {k} [ field0=x ]\n")
    return path


def _keys(nums, width=19):
    return [f"user{n:0{width}d}" for n in nums]


def test_order_preserving():
    # a scrambled input order; fixed-width strings => lexicographic == numeric.
    nums = [42, 7, 999999, 1, 500, 13]
    keys = _keys(nums)
    path = _load_dump(keys)
    try:
        rank, n = keymap.build_rank(path)
    finally:
        os.unlink(path)
    # YCSB-world B-tree order (sorted key strings) must equal our rowid order.
    by_string = sorted(keys)
    by_rowid = sorted(keys, key=lambda k: rank[k])
    assert by_string == by_rowid, "rowid order diverges from string (B-tree) order"


def test_dense_bijection():
    nums = list(range(1000, 0, -1))  # reverse order input
    keys = _keys(nums)
    path = _load_dump(keys)
    try:
        rank, n = keymap.build_rank(path)
    finally:
        os.unlink(path)
    assert n == len(keys)
    assert sorted(rank.values()) == list(range(1, n + 1)), "rowids are not a dense 1..N bijection"


if __name__ == "__main__":
    test_order_preserving()
    test_dense_bijection()
    print("PASS: test_order_preserving, test_dense_bijection")
