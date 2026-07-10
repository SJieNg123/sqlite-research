#!/usr/bin/env python3
"""Reconstruct a per-query EPISODIC page-access sequence for a workload, OFFLINE from
(db + dbstat) -- no harness instrumentation.

Each query is an independent episode delimited by synthetic START/END tokens:

    START -> root -> interior(s) -> leaf -> END          (point lookup)

Transitions are built ONLY within one op_no (one query); we never join
`leaf_of_query_i -> root_of_query_{i+1}`. The special tokens use negative synthetic
IDs (START=-1, END=-2) so they never collide with real SQLite page numbers, and they
are excluded from any hotset downstream.

Output CSV columns:  op_no,step,page_number,page_type
  step 0        = START (page -1)
  step 1..k     = real pages, root -> ... -> leaf (types root/interior/leaf)
  step k+1      = END   (page -2)

Supported ops: point `read` (-> episode). `scan` (workload E, range query) is NOT a
3-page episode and is NOT supported here -> the tool FAILS LOUDLY. Write ops
(insert/update/readmodifywrite) are training-irrelevant for read-page prediction and
are rejected unless --reads-only is given (then they are counted and skipped, never
silently reinterpreted).

Usage:
  gen_pageseq.py <db> <classify.csv> <workload.txt> <out_seq.csv> [--reads-only]
  (classify accepted for interface symmetry; page types come from dbstat.)
"""
import sys, sqlite3, csv, bisect, argparse

START_ID, END_ID = -1, -2
SUPPORTED = {"read"}                       # point lookups only
WRITE_OPS = {"insert", "update", "readmodifywrite"}


def _varint(buf, off):
    v = 0
    for i in range(8):
        b = buf[off + i]
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, off + i + 1
    return (v << 8) | buf[off + 8], off + 9


def _first_rowid(pb):
    if pb[0] != 0x0D:
        return None
    n = (pb[3] << 8) | pb[4]
    if n == 0:
        return None
    cp0 = (pb[8] << 8) | pb[9]
    _, off = _varint(pb, cp0)
    rid, _ = _varint(pb, off)
    return rid


def _ancestor_paths(leafpath):
    segs = [s for s in leafpath.split('/') if s != '']
    chain, cur = ['/'], ''
    for s in segs:
        cur = cur + '/' + s
        chain.append(cur + '/')
    return chain


def _norm_type(t):
    # dbstat pagetype is 'internal'/'leaf'; label root separately downstream.
    return 'interior' if t != 'leaf' else 'leaf'


def build_index(db_path):
    db = sqlite3.connect(str(db_path))
    db.execute("CREATE VIRTUAL TABLE temp.s USING dbstat(main)")
    rows = list(db.execute("SELECT path,pageno,pagetype FROM temp.s WHERE name='items'"))
    root = db.execute("SELECT rootpage FROM sqlite_master WHERE name='items'").fetchone()[0]
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
    return root, path2pg, pg2type, leaf_first


def episodes(db_path, workload_path, reads_only=False):
    """Yield lists of (step, page_number, page_type) per query episode (incl START/END).
    Raises ValueError on an unsupported op (scan / writes unless reads_only)."""
    root, path2pg, pg2type, leaf_first = build_index(db_path)
    firsts = [x[0] for x in leaf_first]

    def chain_for_key(k):
        i = bisect.bisect_right(firsts, k) - 1
        if i < 0:
            return None
        _, pg, lp = leaf_first[i]
        return [path2pg.get(a) for a in _ancestor_paths(lp)]

    op_no = 0
    skipped_writes = 0
    with open(workload_path) as f:
        for lineno, line in enumerate(f, 1):
            parts = line.split()
            if not parts:
                continue
            op = parts[0]
            if op == "scan":
                raise ValueError(
                    f"unsupported op 'scan' at line {lineno}: workload E (range scan) needs "
                    f"true range-query page-sequence reconstruction, not a 3-page episode. "
                    f"learned_markov x E is N/A until that is implemented.")
            if op in WRITE_OPS:
                if reads_only:
                    skipped_writes += 1
                    continue
                raise ValueError(
                    f"unsupported op '{op}' at line {lineno}: this is a write. Read-page "
                    f"prediction ignores writes -- pass --reads-only to train on the read "
                    f"subset of a mixed workload (e.g. YCSB D).")
            if op not in SUPPORTED:
                raise ValueError(f"unsupported op '{op}' at line {lineno}")
            if len(parts) < 2:
                continue
            try:
                k = int(parts[1])
            except ValueError:
                continue
            chain = chain_for_key(k)
            if chain is None:
                continue
            real = [(pg, ('root' if pg == root else _norm_type(pg2type.get(pg, '?'))))
                    for pg in chain if pg is not None]
            # --- hard validation: a point episode must contain root and a leaf, ordered ---
            if not real or real[0][0] != root:
                raise ValueError(f"episode {op_no} (key {k}) does not start at root {root}: {real}")
            if real[-1][1] != 'leaf':
                raise ValueError(f"episode {op_no} (key {k}) does not end at a leaf: {real}")
            ep = [(0, START_ID, 'START')]
            for step, (pg, t) in enumerate(real, 1):
                ep.append((step, pg, t))
            ep.append((len(real) + 1, END_ID, 'END'))
            yield op_no, ep
            op_no += 1
    if skipped_writes:
        sys.stderr.write(f"  reads-only: skipped {skipped_writes} write ops\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('db'); ap.add_argument('classify'); ap.add_argument('workload')
    ap.add_argument('out'); ap.add_argument('--reads-only', action='store_true')
    a = ap.parse_args()
    n_ep = n_rows = 0
    with open(a.out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['op_no', 'step', 'page_number', 'page_type'])
        for op_no, ep in episodes(a.db, a.workload, a.reads_only):
            for step, pg, t in ep:
                w.writerow([op_no, step, pg, t])
                n_rows += 1
            n_ep += 1
    sys.stderr.write(f"wrote {a.out}: {n_ep} episodes, {n_rows} rows "
                     f"(incl START/END tokens {START_ID}/{END_ID})\n")


if __name__ == '__main__':
    main()
