#!/usr/bin/env python3
"""§-1.1 headline-DB geometry gate -- the signed pass condition for the headline DB.

Run this BEFORE trusting a freshly-built headline DB (Round 2). Under D1 (dense rowid +
sorted load) the physical layout is determined by rows x row-width ONLY, so the new headline
DB must reproduce the OLD DB page-for-page. Write-the-gate-before-you-use-it: an unverified
gate with a wrong tolerance PASSES everything and looks identical to a correct one (that is
the churn disease) -- so tests/test_headline_db_gate.py proves this gate REJECTS bad geometry.

Four checks, but really ONE independent variable + ONE row-width check:
  leaf_pages / depth / skeleton_bytes all follow from the leaf count and QUANTIZE (rows/page
  is an integer), so a wrong row width can hide inside their tolerance. `dbstat_record_bytes`
  does NOT quantize -> it is the only check that actually pins the row width.

  *** LABEL TRAP (this cost the author real time -- the field is named to prevent it): ***
  dbstat_record_bytes = SUM(dbstat.payload) over LEAF pages = the b-tree RECORD (all columns +
  record header), 126 B/row here.  It is NOT sum(length(<a value column>)): that omits the
  record header (and any sibling columns) and returns a value a few % LOW -> a FAIL that lands
  just outside +-1% and looks exactly like a small builder bug. Always query dbstat, not a column.
"""
import argparse
import sqlite3
import sys

# Signed pass condition -- mirrors §-1.1 / D1. The spec is the source of truth; changing a
# value here without re-signing §-1.1 is a governance violation (it is a frozen input).
EXPECT = {
    "leaf_pages":          (20000,    0.05),   # +-5%   (items only)
    "depth":               (3,        0.0),    # exact (canonical depth, D8)
    "skeleton_bytes":      (209920,   0.10),   # ~205 KB, +-10%  (items only)
    "dbstat_record_bytes": (75600000, 0.01),   # 126 B/row x 600k, +-1%  <- THE row-width check
    # page_count sees the WHOLE FILE (one exact number -> catches an extra table, a forgotten
    # VACUUM, or a stray index). For the HEADLINE DB it is items 20034 + sqlite_schema 1 = 20035:
    # "nothing in this file but the tree under study". NOT the old DB's 26331 -- that includes
    # idx_items_k1/k2 (~6296 pages), and reproducing them needs k1/k2 columns, which VIOLATES D1's
    # signed fieldcount=1. The gate protects the signature; it must not force you to break it. (D11)
    "page_count":          (20035,    0.0),    # exact: items 20034 + sqlite_schema 1 (NO secondary indexes)
}


def skeleton_contiguity(interior_pagenos):
    """Physical contiguity of the interior (skeleton) pages -- REPORTED, not gated (it is the
    physical explanation of alpha in §4.5.4: 'a single sequential read of the skeleton' only
    works if those pages are physically adjacent; scattered -> N random reads -> prefetch buys
    little). largest_run/n = fraction obtainable in ONE sequential read. layout_rewriter's whole
    point (orig vs type-aware) is to move this number toward 1."""
    if not interior_pagenos:
        return None
    pn = sorted(interior_pagenos)
    runs, largest, cur = 1, 1, 1
    for i in range(1, len(pn)):
        if pn[i] == pn[i - 1] + 1:
            cur += 1
        else:
            runs += 1
            cur = 1
        largest = max(largest, cur)
    return {"n_interior": len(pn), "largest_run": largest, "n_runs": runs,
            "largest_run_frac": round(largest / len(pn), 4), "span": pn[-1] - pn[0] + 1}


def measure_headline_geometry(db, table="items"):
    con = sqlite3.connect(db)
    ps = con.execute("PRAGMA page_size").fetchone()[0]
    rows = con.execute("SELECT path, pagetype, payload, pageno FROM dbstat WHERE name=?", (table,)).fetchall()
    leaf = [r for r in rows if r[1] == "leaf"]
    intr = [r for r in rows if r[1] == "internal"]
    page_count = con.execute("PRAGMA page_count").fetchone()[0]     # WHOLE FILE, not just items
    con.close()
    return {
        "leaf_pages": len(leaf),
        "depth": max((p.count("/") for p, _, _, _ in rows), default=0),   # D8 canonical
        "skeleton_bytes": len(intr) * ps,
        "dbstat_record_bytes": sum(pl for _, _, pl, _ in leaf),           # b-tree record, NOT a column
        "page_count": page_count,
        "skeleton_contiguity": skeleton_contiguity([r[3] for r in intr]),  # REPORTED (alpha driver), not gated
    }


def check_headline_geometry(measured, expect=EXPECT):
    checks = {}
    for key, (exp, tol) in expect.items():
        m = measured[key]
        checks[key] = (m == exp) if tol == 0 else (exp * (1 - tol) <= m <= exp * (1 + tol))
    return {"verdict": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "measured": measured}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--table", default="items")
    a = ap.parse_args()
    r = check_headline_geometry(measure_headline_geometry(a.db, a.table))
    for k, (exp, tol) in EXPECT.items():
        print(f"  [{'PASS' if r['checks'][k] else 'FAIL'}] {k} = {r['measured'][k]}  "
              f"(expect {exp}{'' if tol == 0 else f' +-{tol*100:.0f}%'})")
    print(r["verdict"])
    sys.exit(0 if r["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
