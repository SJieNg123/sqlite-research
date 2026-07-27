#!/usr/bin/env python3
"""Fire test for the §-1.1 headline-DB gate (§-1.3 fire-test rule).

pass path <- the REAL old DB (test.db): the thing the gate should say 'yes' to, and the thing
             Round 2's headline DB must reproduce page-for-page.
fail paths <- out-of-tolerance geometry.
definition test <- dbstat_record_bytes = 60,000,000 (the value you get if you wrongly query
             sum(length(payload COLUMN)) instead of the b-tree record) MUST fail. This is the
             only test that catches the GATE being mis-implemented rather than the builder being
             wrong -- and the author already walked that exact wrong path once, so it is real.

Run: python3 tests/test_headline_db_gate.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import headline_db_gate as g  # noqa: E402

# ground truth = the FROZEN dbstat snapshot of the reference old DB (in git; the live test.db is
# untracked and could vanish). The gate is the ruler; this snapshot is its answer key. Round 2's
# BUILDER-BUILT DB is judged against this -- never the reverse (that was the circularity).
GROUND_TRUTH = json.load(open(os.path.join(HERE, "fixtures", "old_db_geometry.json")))
GT = {k: GROUND_TRUTH[k] for k in
      ("leaf_pages", "depth", "skeleton_bytes", "dbstat_record_bytes", "page_count")}


def test_pass_on_frozen_old_db():
    r = g.check_headline_geometry(GT)
    assert r["verdict"] == "PASS", f"frozen old-DB ground truth must PASS the signed §-1.1 gate: {r['checks']}"
    print(f"  [ok] pass path: frozen old-DB snapshot -> PASS  {GT}")


def _verdict_with(**override):
    m = dict(GT)
    m.update(override)
    return g.check_headline_geometry(m)["verdict"]


def test_fires_on_bad_leaf():
    assert _verdict_with(leaf_pages=25000) == "FAIL", "leaf=25k must FAIL"
    print("  [ok] fail path: leaf_pages=25000 -> FAIL")


def test_fires_on_bad_record_bytes():
    assert _verdict_with(dbstat_record_bytes=80_000_000) == "FAIL", "record=80M must FAIL"
    print("  [ok] fail path: dbstat_record_bytes=80,000,000 -> FAIL")


def test_catches_own_misimplementation():
    # 60,000,000 = sum(length(payload COLUMN)) = the WRONG query (100 B/row, header + k1 + k2
    # omitted). The gate MUST fail it -- else whoever implements the gate as length(value) reads
    # a ~few-% low number, blames the builder, and burns days. This asserts the DEFINITION.
    assert _verdict_with(dbstat_record_bytes=60_000_000) == "FAIL", \
        "60M (value-column query) must FAIL -- the gate must catch its own misimplementation"
    print("  [ok] definition test: record=60,000,000 (value-column query) -> FAIL")


if __name__ == "__main__":
    test_pass_on_frozen_old_db()
    test_fires_on_bad_leaf()
    test_fires_on_bad_record_bytes()
    test_catches_own_misimplementation()
    print("PASS: §-1.1 gate passes the old DB, fires on bad geometry, and catches its own misimpl")
