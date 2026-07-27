#!/usr/bin/env python3
"""§2.7 — v4 YR ρ-sweep geometry gate (D3/D7) + INTEGER-PK WITHOUT ROWID probe.

Runs today, no privilege / no C / no sqlite3 CLI. Answers two questions:

  (1) D7 gate — with the *native* 23B YCSB key, do the 4 sweep points
      W ∈ {101,126,226,326} hit fanout ≈ {33,27,16,12} with overflow_pages == 0?
      Passing this is what unlocks signing D3/D4/D7 (§00).

  (2) INTEGER-PK probe — does  (id INTEGER PRIMARY KEY, v) WITHOUT ROWID  land in
      the SAME low-fanout index-b-tree regime as  (k TEXT PRIMARY KEY, v)  at the
      same row width W?  Mechanism says yes (WITHOUT ROWID interior stores the whole
      row regardless of PK type; the rowid-table 392 regime is the *only* exception).
      If confirmed, YR reuses the headline dense-rowid trace with a `WHERE id=?`
      query → zero harness surgery, and drops the int-vs-text-key confound.

Reuses build()/measure() from build_yr_prototype.py (the tool that measured f=16).
Both variants are built as table `items_yr` in separate DB files so the imported
measure() (which reads name='items_yr') works unchanged.

Usage:
    verify_yr_geometry_v4.py [--rows 200000] [--tol 0.10] [--tmp /tmp]
Exit non-zero if the D7 gate fails, so it can gate D3/D7 signing.
"""
import argparse, os, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_yr_prototype import build, measure   # TEXT builder + dbstat measurer

# D7 sweep: (W total row width, expected native-key fanout)
D7_POINTS = [(101, 33), (126, 27), (226, 16), (326, 12)]
ROWID_TABLE_FANOUT = 392   # the regime INT-PK must NOT collapse into


def build_int(db, rows, vlen):
    """(id INTEGER PRIMARY KEY, v BLOB) WITHOUT ROWID, dense ascending id (sorted load)."""
    con = sqlite3.connect(db)
    con.execute("PRAGMA page_size=4096")
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("DROP TABLE IF EXISTS items_yr")
    con.execute("CREATE TABLE items_yr (id INTEGER PRIMARY KEY, v BLOB) WITHOUT ROWID")
    v = b"v" * vlen
    con.execute("BEGIN")
    con.executemany("INSERT INTO items_yr(id, v) VALUES (?, ?)",
                    ((i, v) for i in range(1, rows + 1)))
    con.execute("COMMIT")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200000)
    ap.add_argument("--tol", type=float, default=0.10, help="±fraction on native-key fanout")
    ap.add_argument("--tmp", default="/tmp")
    a = ap.parse_args()

    print(f"rows={a.rows}  page=4096B   TEXT key=native 23B / INT key=dense integer")
    print(f"target W matched across both variants (TEXT v=W-23, INT v=W-3)\n")
    hdr = (f"{'W':>4} {'exp_f':>5} | {'TEXT f':>7} {'r/leaf':>7} {'ovf':>4} {'gate':>5} "
           f"| {'INT f':>6} {'r/leaf':>7} {'ovf':>4} {'same-regime?':>12}")
    print(hdr)
    print("-" * len(hdr))

    gate_ok = True
    probe_ok = True
    for W, exp in D7_POINTS:
        dt = os.path.join(a.tmp, f"yr_text_W{W}.db")
        di = os.path.join(a.tmp, f"yr_int_W{W}.db")
        build(dt, a.rows, 23, W - 23)      # TEXT PK, native 23B key, total ≈ W
        build_int(di, a.rows, W - 3)       # INT PK, ~3B key, total ≈ W
        mt, mi = measure(dt), measure(di)

        gate = (abs(mt["fanout"] - exp) <= a.tol * exp) and mt["n_ovf"] == 0
        # same regime = INT is an index-b-tree (far from 392) AND ≈ TEXT (±20%)
        same = (mi["n_ovf"] == 0
                and mi["fanout"] < ROWID_TABLE_FANOUT / 4
                and abs(mi["fanout"] - mt["fanout"]) <= 0.20 * mt["fanout"])
        gate_ok &= gate
        probe_ok &= same

        print(f"{W:>4} {exp:>5} | {mt['fanout']:>7.1f} {mt['rows_per_leaf']:>7.1f} "
              f"{mt['n_ovf']:>4} {'PASS' if gate else 'FAIL':>5} "
              f"| {mi['fanout']:>6.1f} {mi['rows_per_leaf']:>7.1f} {mi['n_ovf']:>4} "
              f"{('yes' if same else 'NO'):>12}")
        for p in (dt, di):
            try:
                os.remove(p)
            except OSError:
                pass

    print()
    print(f"[{'PASS' if gate_ok else 'FAIL'}] D7 gate (native-key TEXT sweep hits {{33,27,16,12}}, overflow==0)")
    print(f"[{'PASS' if probe_ok else 'FAIL'}] INTEGER-PK WITHOUT ROWID stays in TEXT's low-fanout regime")
    print(f"       → if PASS: YR can reuse headline trace, WHERE id=?, no harness surgery.")
    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
