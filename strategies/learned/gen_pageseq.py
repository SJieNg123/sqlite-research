#!/usr/bin/env python3
"""Reconstruct the ordered page-access stream (root->interior->leaf per query) for a
workload, OFFLINE from (db + dbstat) -- no harness instrumentation needed.

A read-only point query descends the B-tree deterministically root->interior->leaf.
We map key->leaf via first_rowid ranges (same machinery as gen_hotleaves.py) and
leaf->ancestor pages via the dbstat `path` column (path prefixes = ancestor chain).

Output CSV: op_no,page_number,page_type  (one row per page touched, traversal order;
op_no groups each query's root->interior->leaf triple).

Usage: gen_pageseq.py <db> <classify.csv> <workload.txt> <out_seq.csv>
  (classify is accepted for interface symmetry with the other generators; page types
   here come from dbstat directly.)
"""
import sys, sqlite3, csv, bisect


def _varint(buf, off):
    v = 0
    for i in range(8):
        b = buf[off + i]
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, off + i + 1
    return (v << 8) | buf[off + 8], off + 9


def _first_rowid(pb):
    if pb[0] != 0x0D:                 # 0x0D = table-btree leaf
        return None
    n = (pb[3] << 8) | pb[4]
    if n == 0:
        return None
    cp0 = (pb[8] << 8) | pb[9]
    _, off = _varint(pb, cp0)
    rid, _ = _varint(pb, off)
    return rid


def _ancestor_paths(leafpath):
    """'/001/0dd/' -> ['/', '/001/', '/001/0dd/'] (root .. leaf)."""
    segs = [s for s in leafpath.split('/') if s != '']
    chain, cur = ['/'], ''
    for s in segs:
        cur = cur + '/' + s
        chain.append(cur + '/')
    return chain


def reconstruct(db_path, workload_path):
    """Yield (op_no, page_number, page_type) for each page touched, in traversal order."""
    db = sqlite3.connect(str(db_path))
    db.execute("CREATE VIRTUAL TABLE temp.s USING dbstat(main)")
    rows = list(db.execute("SELECT path,pageno,pagetype FROM temp.s WHERE name='items'"))
    path2pg = {p: pg for p, pg, t in rows}
    pg2type = {pg: t for p, pg, t in rows}

    leaf_first = []
    for p, pg, t in rows:
        if t != 'leaf':
            continue
        data = db.execute("SELECT data FROM sqlite_dbpage WHERE pgno=?", (pg,)).fetchone()[0]
        fr = _first_rowid(data)
        if fr is not None:
            leaf_first.append((fr, pg, p))
    leaf_first.sort()
    firsts = [x[0] for x in leaf_first]

    def chain_for_key(k):
        i = bisect.bisect_right(firsts, k) - 1
        if i < 0:
            return None
        _, pg, lp = leaf_first[i]
        return [path2pg.get(a) for a in _ancestor_paths(lp)]

    op_no = 0
    with open(workload_path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2 or parts[0] not in ('read', 'scan'):
                continue
            try:
                k = int(parts[1])
            except ValueError:
                continue
            chain = chain_for_key(k)
            if not chain:
                continue
            for pg in chain:
                if pg is not None:
                    yield op_no, pg, pg2type.get(pg, '?')
            op_no += 1


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    db, _classify, wl, out = sys.argv[1:]
    n = 0
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['op_no', 'page_number', 'page_type'])
        for op_no, pg, t in reconstruct(db, wl):
            w.writerow([op_no, pg, t])
            n += 1
    print(f"wrote {out}: {n} page accesses", file=sys.stderr)


if __name__ == '__main__':
    main()
