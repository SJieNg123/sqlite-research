#!/usr/bin/env python3
"""Measure how stale a *frozen* prefetch hot-list has become on a (churned) DB.

The prefetcher loads a fixed set of page numbers, captured once at t=0 (a
hotpages CSV: `page_number,is_resident`). As the DB is churned, leaf pages can
split and move their rows to other pages, so a key that used to live on a frozen
page may now live somewhere else — the frozen list goes stale.

This reuses the rowid->leaf mapping trick from
`strategies/access/runs/gen_hotleaves.py`: every rowid-table leaf stores its rows
in sorted order, so the page that owns key `k` is the last leaf whose first
rowid <= k (binary search over each leaf's first rowid).

`compute_coverage(db, frozen_csv, workload)` returns, for the read ops in
`workload`:
  - hot_key_coverage   : fraction whose CURRENT leaf page is in the frozen list
  - covered_ops / read_ops
  - frozen_leaves      : frozen pages that are leaves of `items` right now
  - dead_frozen_leaves : frozen leaves no benchmarked key lands on anymore
  - leaf_pages_now     : total `items` leaf pages currently

At t=0 coverage is high (the list was built to cover the hot keys); if churn
splits the hot pages, coverage drops — that drop IS the decay.

Usage (standalone):
  measure_staleness.py <db> <frozen_hotpages.csv> <workload.txt> [max_read_ops]
"""
import sys
import csv
import bisect
import sqlite3


# ---- rowid varint / first-rowid parsing (same format as gen_hotleaves.py) ----
def varint(buf, off):
    v = 0
    for i in range(8):
        b = buf[off + i]
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, off + i + 1
    return (v << 8) | buf[off + 8], off + 9


def first_rowid(page_bytes):
    # 0x0D = table b-tree leaf page; anything else (e.g. page 1 with the file
    # header, interior pages) is skipped.
    if not page_bytes or page_bytes[0] != 0x0D:
        return None
    ncells = (page_bytes[3] << 8) | page_bytes[4]
    if ncells == 0:
        return None
    cp0 = (page_bytes[8] << 8) | page_bytes[9]
    _, off = varint(page_bytes, cp0)
    rid, _ = varint(page_bytes, off)
    return rid


def build_leaf_index(conn, table="items"):
    """Return (firsts, pages, leaf_set) describing the current rowid->leaf map.

    firsts/pages are parallel lists sorted by first rowid; leaf_set is the set of
    all current leaf page numbers for `table`.
    """
    conn.execute("DROP TABLE IF EXISTS temp.dbstat_s")
    conn.execute("CREATE VIRTUAL TABLE temp.dbstat_s USING dbstat(main)")
    leaf_pages = [
        pn
        for (pn,) in conn.execute(
            "SELECT pageno FROM temp.dbstat_s WHERE name=? AND pagetype='leaf'",
            (table,),
        )
    ]
    leaf_set = set(leaf_pages)
    leaf_first = []
    # Single streamed pass over the page store; only parse leaves of `table`.
    for pgno, data in conn.execute("SELECT pgno, data FROM sqlite_dbpage"):
        if pgno in leaf_set:
            fr = first_rowid(data)
            if fr is not None:
                leaf_first.append((fr, pgno))
    leaf_first.sort()
    firsts = [fr for fr, _ in leaf_first]
    pages = [pn for _, pn in leaf_first]
    return firsts, pages, leaf_set


def page_for_key(firsts, pages, k):
    """Leaf page owning key k = last leaf whose first rowid <= k."""
    i = bisect.bisect_right(firsts, k) - 1
    if i < 0:
        return None
    return pages[i]


def load_resident(frozen_csv):
    """Page numbers marked is_resident=1 in a hotpages CSV."""
    resident = set()
    with open(frozen_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                if int(row["is_resident"]) == 1:
                    resident.add(int(row["page_number"]))
            except (KeyError, ValueError):
                continue
    return resident


def compute_coverage(db, frozen_csv, workload, max_read_ops=0, table="items"):
    """Coverage of a workload's read ops by a frozen hotpages list on `db`.

    `db` may be a path or an open sqlite3.Connection. Returns a dict of metrics.
    """
    own = isinstance(db, str)
    conn = sqlite3.connect(db) if own else db
    try:
        firsts, pages, leaf_set = build_leaf_index(conn, table)
    finally:
        if own:
            pass  # keep open until after we read sqlite_dbpage above
    frozen = load_resident(frozen_csv)

    total = 0
    covered = 0
    hit_pages = set()
    with open(workload) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "read":
                try:
                    k = int(parts[1])
                except ValueError:
                    continue
                pg = page_for_key(firsts, pages, k)
                if pg is None:
                    continue
                total += 1
                hit_pages.add(pg)
                if pg in frozen:
                    covered += 1
                if max_read_ops and total >= max_read_ops:
                    break
    if own:
        conn.close()

    frozen_leaves = frozen & leaf_set
    return {
        "hot_key_coverage": (covered / total) if total else 0.0,
        "covered_ops": covered,
        "read_ops": total,
        "frozen_leaves": len(frozen_leaves),
        "dead_frozen_leaves": len(frozen_leaves - hit_pages),
        "leaf_pages_now": len(leaf_set),
    }


# Column order for staleness_summary.csv (used by the churn harness too).
METRIC_FIELDS = [
    "hot_key_coverage",
    "covered_ops",
    "read_ops",
    "frozen_leaves",
    "dead_frozen_leaves",
    "leaf_pages_now",
]


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 1
    db, frozen_csv, workload = argv[1], argv[2], argv[3]
    max_read_ops = int(argv[4]) if len(argv) > 4 else 0
    m = compute_coverage(db, frozen_csv, workload, max_read_ops)
    print(
        f"coverage={m['hot_key_coverage']:.4f} "
        f"({m['covered_ops']}/{m['read_ops']} read ops) "
        f"frozen_leaves={m['frozen_leaves']} "
        f"dead_frozen_leaves={m['dead_frozen_leaves']} "
        f"leaf_pages_now={m['leaf_pages_now']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
