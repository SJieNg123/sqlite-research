#!/usr/bin/env python3
"""Smoke test for the builder<->harness CONTRACT (§-1.3 fire-test rule).

The gap this fills never had a gate: §-1.1 checks GEOMETRY (leaf/depth/skeleton/record/page_count);
whether the harness can even OPEN the DB is a separate, un-written contract. Do NOT gate it with a
column list -- that is a third copy of the schema (a sticky note that drifts on source change).
Instead: run the actual harness. Opening the DB + a few ops catches a missing column, a wrong
page_size, a permission problem, a prepare failure -- everything, enumerating nothing.

pass <- a good headline-schema DB (id/k1/k2/payload).
fire <- grave B: schema id/payload, NO k1/k2 -- my own misread of fieldcount=1. The harness
        prepares an INSERT referencing k1 at init, so it cannot even open B. Bind the RECIPE, not
        a binary blob: a committed .db is the ultimate sticky note (opaque, un-diffable, gitignored
        by *.db, and it can't drift-check against the schema source). B is two columns -- store HOW
        to make it, right next to the good DB, so both move together if the contract ever changes.

Run: python3 tests/test_db_smoke.py
"""
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "static_experiment", "tools")


def _harness():
    binp = os.path.join(tempfile.gettempdir(), "bh_smoke")
    if not os.path.exists(binp):
        r = subprocess.run(
            ["gcc", "-O2", "-D_GNU_SOURCE", "-I", os.path.join(SRC, "vendor", "sqlite"),
             os.path.join(SRC, "src", "benchmark_harness.c"),
             os.path.join(SRC, "vendor", "sqlite", "sqlite3.c"),
             "-o", binp, "-lpthread", "-ldl", "-lm"], capture_output=True, text=True)
        if r.returncode != 0:
            print("  [skip] cannot build harness (no gcc / source moved):", r.stderr[-160:])
            sys.exit(0)
    return binp


def _run(binp, db):
    trace = tempfile.mktemp(suffix=".txt")
    with open(trace, "w") as f:
        f.write("\n".join(f"read {i}" for i in range(1, 11)) + "\n")
    return subprocess.run(
        [binp, "--db", db, "--workload", trace, "--cold-advice", "none",
         "--output", tempfile.mktemp(suffix=".csv")], capture_output=True, text=True).returncode


def _db(cols_sql, insert_sql):
    db = tempfile.mktemp(suffix=".db")
    con = sqlite3.connect(db)
    con.execute(f"CREATE TABLE items({cols_sql})")
    con.executemany(insert_sql, ((i,) for i in range(1, 201)))
    con.commit()
    con.close()
    return db


def _good_db():
    return _db("id INTEGER PRIMARY KEY, k1 TEXT, k2 TEXT, payload BLOB",
               "INSERT INTO items VALUES(?, 'group_0001', 'tag_000001', randomblob(100))")


def _grave_b_db():
    # Grave B, built from its recipe (not a stored blob): fieldcount=1 misread as a 2-column DB.
    return _db("id INTEGER PRIMARY KEY, payload BLOB",   # NO k1/k2 -- the bug the harness rejects
               "INSERT INTO items VALUES(?, randomblob(100))")


def test_harness_opens_good_db():
    assert _run(_harness(), _good_db()) == 0, "harness must open a good id/k1/k2/payload DB"
    print("  [ok] contract: harness opens id/k1/k2/payload DB + runs ops -> exit 0")


def test_fires_on_missing_columns():
    assert _run(_harness(), _grave_b_db()) != 0, "harness must FAIL on a DB missing k1/k2 (grave B)"
    print("  [ok] fire: harness on grave B (id/payload, no k1/k2) -> non-zero exit")


if __name__ == "__main__":
    test_harness_opens_good_db()
    test_fires_on_missing_columns()
    print("PASS: builder<->harness contract smoke (good DB opens, missing-column grave fires)")
