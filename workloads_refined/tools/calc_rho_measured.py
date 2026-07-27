#!/usr/bin/env python3
"""calc_rho_measured.py -- static rho_measured for a dense-rowid DB (no b-tree parsing).

rho_measured is the x-axis of the §4.5.4 regression -- a SIGNED prediction -- so the instrument
is verified where the answer is analytic (tests/test_calc_rho_measured.py: 51/20034 and 2/3).

Dividend of the §2.5 dense-rowid + sorted-load design: the key->page map is EXACT and needs zero
b-tree parsing -- it falls straight out of dbstat:
  1. leaf pages sorted by `path` (lexicographic) == left-to-right key (rowid) order.
  2. cumsum(ncell) -> leaf_i covers rowid [cum_{i-1}+1, cum_i]   (exact, not estimated).
  3. a touched leaf -> every proper prefix of its path is an interior page climbed to reach it
     (ancestors of '/000/005/' are '/' and '/000/').
  4. rho = |interior touched| / (|interior touched| + |leaf touched|).
Also yields rightmost_leaf_share (fraction of queries hitting the max-path leaf) -- the second
half of workload C's -75% mechanism (an over-max key descends to the right edge).

FIRST it verifies the query plan touches ONLY the table's rowid PK (fills `trees_touched`, empty
since day 1): if `WHERE id=?` walks any index, rho's interior set is wrong. Non-zero exit.
"""
import argparse
import bisect
import json
import sqlite3
import sys


def assert_pk_point_query(con, table):
    plan = con.execute(f"EXPLAIN QUERY PLAN SELECT * FROM {table} WHERE id=?", (1,)).fetchall()
    detail = " | ".join(str(r[-1]) for r in plan)
    if "INTEGER PRIMARY KEY" not in detail.upper() or "INDEX" in detail.upper():
        sys.exit(f"FAIL trees_touched: `WHERE id=?` on {table} is not a pure rowid PK lookup.\n"
                 f"  plan: {detail}\n"
                 f"  -> rho's interior set is wrong (an index b-tree is also walked; add its skeleton).")
    return detail


def leaf_boundaries(con, table):
    """[(upper_rowid, leaf_path), ...] sorted by upper_rowid. Dense rowid: leaf path order == key
    order; cumsum(ncell) gives the exact rowid range each leaf covers."""
    leaves = sorted((p, nc) for p, pt, nc in
                    con.execute("SELECT path, pagetype, ncell FROM dbstat WHERE name=?", (table,))
                    if pt == "leaf")
    bnd, cum = [], 0
    for path, ncell in leaves:
        cum += ncell
        bnd.append((cum, path))
    return bnd


def leaf_of(rowid, uppers, paths):
    return paths[bisect.bisect_left(uppers, rowid)]


def ancestors(leaf_path):
    """interior pages climbed to reach a leaf = all proper path prefixes.
    '/000/005/' -> ['/', '/000/']"""
    segs = leaf_path.rstrip("/").split("/")          # '/000/005/' -> ['', '000', '005']
    return ["/" if i == 1 else "/".join(segs[:i]) + "/" for i in range(1, len(segs))]


def calc_rho(db, table, targets):
    con = sqlite3.connect(db)
    assert_pk_point_query(con, table)                # trees_touched gate (non-zero exit on fail)
    bnd = leaf_boundaries(con, table)
    con.close()
    uppers = [b[0] for b in bnd]
    paths = [b[1] for b in bnd]
    rightmost = paths[-1]                             # max path == highest rowids == right edge
    interior, leaf, rm_hits = set(), set(), 0
    for r in targets:
        lp = leaf_of(r, uppers, paths)
        leaf.add(lp)
        interior.update(ancestors(lp))
        if lp == rightmost:
            rm_hits += 1
    n = len(targets)
    return {
        "rho_measured": len(interior) / (len(interior) + len(leaf)) if (interior or leaf) else None,
        "interior_touched": len(interior),
        "leaf_touched": len(leaf),
        "rightmost_leaf_share": rm_hits / n if n else None,
        "n_targets": n,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--table", default="items")
    ap.add_argument("--trace", required=True, help="harness-format trace (op <rowid> ...)")
    a = ap.parse_args()
    targets = []
    for line in open(a.trace, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] in ("read", "scan", "readmodifywrite", "update"):
            targets.append(int(parts[1]))
    print(json.dumps(calc_rho(a.db, a.table, targets), indent=2))


if __name__ == "__main__":
    main()
