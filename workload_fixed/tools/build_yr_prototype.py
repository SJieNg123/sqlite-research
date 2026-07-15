#!/usr/bin/env python3
"""YR regime-arm geometry prototype (spec v3 §10.3, gate for D3).

Builds a small `WITHOUT ROWID` table with the YR schema (§4.5.1) and measures its
b-tree geometry via dbstat, so the paper's fanout≈38 / 32MB-skeleton extrapolation
(§4.5.2) is validated on real pages BEFORE anyone builds the 1.2GB full DB.

Schema (v3 §4.5.1):
    CREATE TABLE items_yr (k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID
    k = fixed 100B, order-preserving ("user"+19-digit rank, right-padded to 100B)
    v = 126B blob  (leaf payload aligned with the headline row, §3.4 = 126B/row)

Load order = sorted (v3 §3.3 load_order=sorted): keys are generated in rank order,
so the b-tree is built by pure right-append → high leaf fill, matching the old DB's
96.8% signature. This is the headline-comparable physical layout.

Usage:
    build_yr_prototype.py --rows 200000 --db /tmp/yr_proto.db [--keylen 100] [--vlen 126]

Measures (dbstat, no privilege, no sqlite3 CLI needed):
    interior fanout = leaf_pages / L1_interior_pages   (the ρ lever, §3.5)
    rows/leaf, depth, overflow pages, skeleton bytes
Prints a PASS/FAIL against the D3 tolerances (fanout∈[33,43], rows/leaf∈[15,19],
overflow==0). Non-zero exit on FAIL so it can gate step 2.5.
"""
import argparse, sqlite3, sys


def build(db, rows, keylen, vlen):
    con = sqlite3.connect(db)
    con.execute("PRAGMA page_size=4096")          # match the experiment DB
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("DROP TABLE IF EXISTS items_yr")
    con.execute("CREATE TABLE items_yr (k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID")
    base = keylen - 23                            # "user"+19 digits = 23 fixed chars
    if base < 0:
        sys.exit(f"keylen {keylen} < 23 (need room for user+19-digit rank)")
    pad = "x" * base
    v = b"v" * vlen

    def gen():
        # i ascending → keys already in sorted (lexicographic == rank) order → sorted load
        for i in range(rows):
            yield (f"user{i:019d}{pad}", v)

    con.execute("BEGIN")
    con.executemany("INSERT INTO items_yr(k, v) VALUES (?, ?)", gen())
    con.execute("COMMIT")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()


def measure(db):
    con = sqlite3.connect(db)
    ps = con.execute("PRAGMA page_size").fetchone()[0]
    rows = con.execute("SELECT path, pagetype, ncell FROM dbstat WHERE name='items_yr'").fetchall()
    # b-tree level from dbstat path: root='' (level 0), each '/NN' segment = one level down.
    def level(path):
        return 0 if path == "" else path.count("/") + (0 if path.startswith("/") else 1)
    leaf = [r for r in rows if r[1] == "leaf"]
    intr = [r for r in rows if r[1] == "internal"]
    ovf  = [r for r in rows if r[1] == "overflow"]
    # L1 interior = the interior level directly above the leaves = the deepest internal level
    if intr:
        maxlvl = max(level(p) for p, _, _ in intr)
        l1 = [r for r in intr if level(r[0]) == maxlvl]
    else:
        l1 = []
    depth = 1 + max((level(p) for p, _, _ in rows), default=0)  # #levels incl. leaves
    leaf_cells = sum(nc for _, _, nc in leaf)
    n_leaf, n_l1, n_intr = len(leaf), len(l1), len(intr)
    fanout = leaf_cells and n_leaf / n_l1 if n_l1 else 0
    rows_per_leaf = leaf_cells / n_leaf if n_leaf else 0
    skeleton_kb = n_intr * ps / 1024
    con.close()
    return dict(ps=ps, n_leaf=n_leaf, n_l1=n_l1, n_intr=n_intr, n_ovf=len(ovf),
                depth=depth, fanout=fanout, rows_per_leaf=rows_per_leaf,
                skeleton_kb=skeleton_kb, leaf_cells=leaf_cells)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200000)
    ap.add_argument("--db", required=True)
    ap.add_argument("--keylen", type=int, default=100)
    ap.add_argument("--vlen", type=int, default=126)
    a = ap.parse_args()

    build(a.db, a.rows, a.keylen, a.vlen)
    m = measure(a.db)

    print(f"rows={a.rows}  key={a.keylen}B  value={a.vlen}B  page={m['ps']}B")
    print(f"  leaf pages      = {m['n_leaf']}")
    print(f"  L1 interior     = {m['n_l1']}   (all interior = {m['n_intr']})")
    print(f"  rows/leaf       = {m['rows_per_leaf']:.1f}")
    print(f"  interior fanout = {m['fanout']:.1f}   (= leaf / L1-interior)")
    print(f"  depth (levels)  = {m['depth']}")
    print(f"  overflow pages  = {m['n_ovf']}")
    print(f"  skeleton        = {m['skeleton_kb']:.0f} KB")

    # D3 / §10.3 pass conditions
    checks = [
        ("fanout∈[33,43]",   33 <= m["fanout"] <= 43),
        ("rows/leaf∈[15,19]", 15 <= m["rows_per_leaf"] <= 19),
        ("overflow==0",       m["n_ovf"] == 0),
    ]
    print("  ---- D3 gate (§10.3) ----")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    # extrapolate to 5M rows (D3 target geometry, §4.5.2)
    if m["rows_per_leaf"]:
        leaf5m = 5_000_000 / m["rows_per_leaf"]
        intr5m = leaf5m / m["fanout"] if m["fanout"] else 0
        print(f"  ---- extrapolation to 5M rows ----")
        print(f"  leaf≈{leaf5m/1000:.0f}k  L1-interior≈{intr5m/1000:.1f}k  "
              f"skeleton≈{intr5m*m['ps']*1.03/1e6:.0f}MB (incl. upper levels)  "
              f"depth≈{m['depth']+1}  rho_ceiling≈{1/(1+m['fanout'])*100:.2f}%")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
