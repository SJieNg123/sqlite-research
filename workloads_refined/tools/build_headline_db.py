#!/usr/bin/env python3
"""build_headline_db.py -- build the headline DB (D1/D11), then judge it (§-1.1 + smoke test).

Schema A = testdb_builder's schema MINUS the two CREATE INDEX statements:
  items(id INTEGER PRIMARY KEY, k1 TEXT, k2 TEXT, payload BLOB), dense rowid 1..rows, sorted load,
  NO secondary index -> 20,035 pages, 126 B/row record (k1+k2+payload+header).

Why k1/k2 columns despite D1's fieldcount=1: fieldcount=1 is a YCSB LOG-SIZE knob (§2.2 -- verbose
toString of 10x100B fields would balloon the load log to ~1GB; the trace is value-agnostic, row
size is set by the harness/build), NOT a DB schema declaration. D1's own wording is 'harness row
payload = 126B'. The harness ALSO requires k1/k2 to exist (it prepares an UPDATE/INSERT referencing
them at init, even for read-only workloads) -- so the builder-harness contract needs them. Clarifies
D1/D11 (errata), does not change them. testdb_builder already proved this schema yields 126 B rows.

An unverified builder is worthless (churn disease), so this runs the §-1.1 geometry gate on its own
output. The builder-harness CONTRACT (can the harness even open this DB) is a SEPARATE, un-enumerated
check -- see tests/test_db_smoke.py.
"""
import argparse
import os
import sqlite3
import sys


def build(db, rows):
    con = sqlite3.connect(db)
    con.execute("PRAGMA page_size=4096")
    con.execute("PRAGMA journal_mode=OFF")
    con.executescript("""
        DROP TABLE IF EXISTS items;
        CREATE TABLE items (
          id INTEGER PRIMARY KEY,
          k1 TEXT NOT NULL,
          k2 TEXT NOT NULL,
          payload BLOB NOT NULL
        );
    """)                                                     # NO CREATE INDEX (D11)
    con.execute("BEGIN")
    con.executemany(
        "INSERT INTO items(id, k1, k2, payload) VALUES (?, printf('group_%04d', ?), printf('tag_%06d', ?), randomblob(100))",
        ((i, i % 1000, i) for i in range(1, rows + 1)))      # dense rowid, sorted load; == testdb_builder body
    con.execute("COMMIT")
    con.execute("VACUUM")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--rows", type=int, default=600000)
    a = ap.parse_args()
    build(a.db, a.rows)
    print(f"built {a.db}: {a.rows} rows, schema id/k1/k2/payload, NO index")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import headline_db_gate as g
    r = g.check_headline_geometry(g.measure_headline_geometry(a.db))
    for k in g.EXPECT:
        print(f"  [{'PASS' if r['checks'][k] else 'FAIL'}] {k} = {r['measured'][k]}")
    print(f"  skeleton_contiguity = {r['measured']['skeleton_contiguity']}")
    print(r["verdict"])
    sys.exit(0 if r["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
