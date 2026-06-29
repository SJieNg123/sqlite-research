#!/usr/bin/env python3
"""Build a frequency-ranked PARTIAL-dump hotset (competitive baseline 2f_topN).

Motivation (review RR1 / S4): 2f_slru dumps the *entire* resident working set
(~4400 pages); 2e_K10 delivers ~14-28. To tell "targeted mechanism beats dump
mechanism" apart from "ranked-partial beats unranked-full", we need a TUNED dump:
rank the resident working set by *access frequency* and dump only the top-N — the
InnoDB `innodb_buffer_pool_dump_pct` analog. Crucially this ranking uses NO
page-type knowledge; it counts how often each page is actually touched.

Access frequency = how many workload reads touch the page. We replay each read's
B+tree root->leaf traversal (interior pages on the path + the target leaf) and
tally per-page hits, then keep the top-N pages that are in the resident set.

Output: page_number,is_resident (hotpages-style; is_resident=1 for the chosen
top-N, 0 for the rest of the resident set) — consumed by run_experiment.py's
`freqdump` strategy kind exactly like the 2e hot2e files.

Usage: gen_freqdump.py <db> <classify.csv> <resident_hotpages.csv> <workload.txt> <top_N> <out.csv>
"""
import sys, sqlite3, csv
from collections import Counter

if len(sys.argv) != 7:
    print(__doc__); sys.exit(1)
DB, CLASSIFY, HOT, WL, TOPN, OUT = sys.argv[1:]
TOPN = int(TOPN)

def varint(buf, off):
    v = 0
    for i in range(8):
        b = buf[off+i]
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, off+i+1
    return (v << 8) | buf[off+8], off+9

db = sqlite3.connect(DB)
root = db.execute("SELECT rootpage FROM sqlite_master WHERE name='items'").fetchone()[0]

# ---- page byte cache + interior decode (table b-tree only; rowid = key) ----
_page = {}
def page_bytes(pn):
    if pn not in _page:
        _page[pn] = db.execute("SELECT data FROM sqlite_dbpage WHERE pgno=?", (pn,)).fetchone()[0]
    return _page[pn]

_interior = {}
def interior(pn):
    """Return (cells=[(sep_key,left_child)...], rightmost) for an interior table page,
    or None if pn is a leaf."""
    if pn in _interior:
        return _interior[pn]
    data = page_bytes(pn)
    base = 100 if pn == 1 else 0      # page 1 carries the 100-byte file header
    flag = data[base]
    if flag == 0x0D:                  # leaf table -> not interior
        _interior[pn] = None
        return None
    if flag != 0x05:                  # not a table b-tree interior page
        _interior[pn] = None
        return None
    ncell = (data[base+3] << 8) | data[base+4]
    right = int.from_bytes(data[base+8:base+12], "big")
    cps = base + 12
    cells = []
    for i in range(ncell):
        cp = (data[cps+2*i] << 8) | data[cps+2*i+1]
        left = int.from_bytes(data[cp:cp+4], "big")
        key, _ = varint(data, cp+4)
        cells.append((key, left))
    _interior[pn] = (cells, right)
    return _interior[pn]

def path_for_key(k):
    """Pages visited from root down to the leaf for rowid k (interiors + leaf)."""
    pn = root
    path = []
    for _ in range(8):                # depth guard
        path.append(pn)
        node = interior(pn)
        if node is None:              # reached a leaf
            return path
        cells, right = node
        child = right
        for sep, left in cells:       # cells are in ascending key order
            if k <= sep:
                child = left
                break
        pn = child
    return path

# ---- 1) resident working set (what 2f_slru would dump) ----
resident = set()
with open(HOT) as f:
    for r in csv.DictReader(f):
        if r.get("is_resident", "0").strip() == "1":
            resident.add(int(r["page_number"]))

# ---- 2) replay reads, tally per-page traversal frequency ----
cnt = Counter()
nreads = 0
with open(WL) as f:
    for line in f:
        p = line.split()
        if len(p) >= 2 and p[0] == "read":
            try:
                k = int(p[1])
            except ValueError:
                continue
            nreads += 1
            for pn in path_for_key(k):
                if pn in resident:    # a partial dump only dumps from the working set
                    cnt[pn] += 1

# ---- 3) rank resident pages by frequency (desc), deterministic tie-break (page asc) ----
ranked = sorted(resident, key=lambda pn: (-cnt[pn], pn))
top = set(ranked[:TOPN])

# ---- 4) emit hotpages-style CSV ----
with open(OUT, "w") as f:
    f.write("page_number,is_resident\n")
    for pn in sorted(resident):
        f.write(f"{pn},{1 if pn in top else 0}\n")

touched = sum(1 for pn in resident if cnt[pn] > 0)
covered = sum(cnt[pn] for pn in top)
print(f"{OUT}: reads={nreads} resident={len(resident)} touched={touched} "
      f"top{TOPN}={len(top)} cover={covered}/{sum(cnt.values())} "
      f"({100*covered/max(1,sum(cnt.values())):.1f}% of path-hits)", file=sys.stderr)
