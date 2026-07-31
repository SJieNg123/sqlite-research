#!/usr/bin/env python3
"""Fire test for calc_rho_measured -- the §4.5.4 regression x-axis instrument.

Every answer here is ANALYTIC (derived from the reference DB's known page counts), so a wrong
number means the TOOL is wrong, with no second explanation:
  full_coverage -> touches all 51 interior + all 19983 leaf -> rho = 51/20034
  single_key    -> root + 1 interior + 1 leaf               -> rho = 2/3  (also cross-checks depth=3)
  boundary      -> cumsum[0] in leaf_0, cumsum[0]+1 in leaf_1 (guards the off-by-one that would
                   silently mis-assign edge keys and DESTROY rightmost_leaf_share -- C's -75% half)

Run: python3 tests/test_calc_rho_measured.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import calc_rho_measured as c  # noqa: E402

OLD_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "pipeline", "preparation", "layout_rewriter", "runs", "test.db")
N = 600_000


def test_full_coverage():
    r = c.calc_rho(OLD_DB, "items", list(range(1, N + 1)))
    assert (r["interior_touched"], r["leaf_touched"]) == (51, 19983), r
    assert abs(r["rho_measured"] - 51 / 20034) < 1e-12, r["rho_measured"]
    print(f"  [ok] full-coverage: rho = 51/20034 = {r['rho_measured']:.6f}")


def test_single_key():
    r = c.calc_rho(OLD_DB, "items", [12345] * 80000)
    # one leaf reached via root + one L1 interior -> 2 interior, 1 leaf -> rho = 2/3
    assert (r["interior_touched"], r["leaf_touched"]) == (2, 1), r
    assert abs(r["rho_measured"] - 2 / 3) < 1e-12, r["rho_measured"]
    # cross-check with D8: 2 interior levels above the leaf <=> depth = 3
    print(f"  [ok] single-key: rho = 2/3 = {r['rho_measured']:.4f}  (implies depth=3)")


def test_leaf_boundary():
    con = sqlite3.connect(OLD_DB)
    bnd = c.leaf_boundaries(con, "items")
    con.close()
    uppers = [b[0] for b in bnd]
    paths = [b[1] for b in bnd]
    c0 = uppers[0]                     # last rowid of leaf_0
    assert c.leaf_of(c0, uppers, paths) == paths[0], "cumsum[0] must land in leaf_0"
    assert c.leaf_of(c0 + 1, uppers, paths) == paths[1], "cumsum[0]+1 must land in leaf_1 (off-by-one!)"
    print(f"  [ok] boundary: rowid {c0}->leaf_0, {c0 + 1}->leaf_1 (no off-by-one)")


def test_trees_touched_gate():
    # calc_rho must refuse a DB where the query would walk an index (rho numerator wrong).
    # here we just confirm the reference DB PASSES the gate (SEARCH ... INTEGER PRIMARY KEY).
    con = sqlite3.connect(OLD_DB)
    detail = c.assert_pk_point_query(con, "items")
    con.close()
    assert "INTEGER PRIMARY KEY" in detail.upper(), detail
    print(f"  [ok] trees_touched: items WHERE id=? -> {detail}")


if __name__ == "__main__":
    test_trees_touched_gate()
    test_full_coverage()
    test_single_key()
    test_leaf_boundary()
    print("PASS: calc_rho_measured (trees_touched, full-coverage 51/20034, single-key 2/3, boundary)")
