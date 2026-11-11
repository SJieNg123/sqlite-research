"""Design-time simulation for prereg R1a: no benchmark, no cache manipulation.

Walk the items table B-tree to map rowid -> (level-2 interior page, leaf page).
Each read op touches page 1, the root (page 2), its level-2 interior page and
its leaf. A pager with SQLite's default cache_size=-2000 is modelled as an LRU
of C pages.

  summary  DB WL_DIR            sliding-window hit rates over every probe
                                position (the table in R1a.md)
  predict  DB WL_DIR OUT.csv    the registered runs: for each workload, seed
                                1..10 and N, replay ops[0:N] into an empty LRU
                                and predict the probe ops[N]

Usage: python3 -I pager_lru_sim.py {summary|predict} DB WL_DIR [OUT.csv]
"""
import bisect, collections, csv, struct, sys
from pathlib import Path

PS = 4096
ROOT = 2
CAPACITIES = (483, 450)       # pager pages for cache_size=-2000; 450 = sensitivity
REGISTERED_N = (0, 1, 10, 100, 1000)


class Tree:
    def __init__(self, db):
        self.f = open(db, "rb")
        cells, right = self._interior(ROOT)
        self.l2_keys = [k for _, k in cells]
        self.l2_pages = [c for c, _ in cells] + [right]
        self.leaf_index = {}
        for l2 in self.l2_pages:
            cells, right = self._interior(l2)
            self.leaf_index[l2] = ([k for _, k in cells], [c for c, _ in cells] + [right])

    def _interior(self, pg):
        self.f.seek((pg - 1) * PS)
        b = self.f.read(PS)
        assert b[0] == 5, (pg, b[0])
        n = struct.unpack(">H", b[3:5])[0]
        right = struct.unpack(">I", b[8:12])[0]
        cells = []
        for k in range(n):
            p = struct.unpack(">H", b[12 + 2 * k:14 + 2 * k])[0]
            child = struct.unpack(">I", b[p:p + 4])[0]
            cells.append((child, _varint(b, p + 4)))
        return cells, right

    def path(self, rowid):
        l2 = self.l2_pages[bisect.bisect_left(self.l2_keys, rowid)]
        keys, leaves = self.leaf_index[l2]
        return l2, leaves[bisect.bisect_left(keys, rowid)]


def _varint(b, i):
    v = 0
    for k in range(9):
        c = b[i + k]
        if k == 8:
            return (v << 8) | c
        v = (v << 7) | (c & 0x7F)
        if c < 0x80:
            return v


def ops(wl_dir, w, seed):
    p = Path(wl_dir) / f"workload_{w}_{seed}.txt"
    return [int(line.split()[1]) for line in p.read_text().split("\n") if line.startswith("read ")]


class LRU:
    def __init__(self, cap):
        self.cap, self.d = cap, collections.OrderedDict()

    def touch(self, pg):
        self.d.pop(pg, None)
        self.d[pg] = True
        if len(self.d) > self.cap:
            self.d.popitem(last=False)


def touched(tree, key):
    l2, leaf = tree.path(key)
    return (1, ROOT, l2, leaf)


def summary(tree, wl_dir):
    """Sliding window: a page counts as cached at probe i if it is in the LRU
    and was last touched within the previous N ops. Conservative: pages from
    before the window still occupy LRU slots."""
    Ns = [0, 1, 10, 100, 1000, 10000]
    for w in "abc":
        streams = [ops(wl_dir, w, s) for s in range(1, 11)]
        paths = [tree.path(k) for s in streams for k in s]
        print(f"== workload {w.upper()}: {len(paths)} reads, "
              f"level-2 pages touched {len({p[0] for p in paths})}/{len(tree.l2_pages)}, "
              f"distinct leaves {len({p[1] for p in paths})}")
        for C in sorted(CAPACITIES):
            row = []
            for N in Ns:
                fr = []
                for keys in streams:
                    if N == 0:
                        fr.append((0.0, 0.0)); continue
                    lru, last, hr, hl, tot = LRU(C), {}, 0, 0, 0
                    for i, k in enumerate(keys):
                        pages = touched(tree, k)
                        if i >= N:
                            tot += 1
                            hr += ROOT in lru.d and i - last[ROOT] <= N
                            hl += pages[2] in lru.d and i - last[pages[2]] <= N
                        for pg in pages:
                            lru.touch(pg); last[pg] = i
                    fr.append((hr / tot, hl / tot))
                r = sum(x[0] for x in fr) / len(fr)
                l = sum(x[1] for x in fr) / len(fr)
                lo = min(x[1] for x in fr)
                row.append(f"N={N}: root {r:.3f} L2 {l:.3f} (min seed {lo:.3f})")
            print(f"  C={C}: " + " | ".join(row))


def predict(tree, wl_dir, out):
    """One row per registered run cell: probe = ops[N] after warm-up ops[0:N]."""
    cols = ["workload", "seed", "N", "probe_op_index", "probe_key", "probe_l2_page",
            "probe_leaf_page", "pred_page1_hit", "pred_root_hit", "pred_l2_hit",
            "pred_leaf_hit", "pred_interior_hit", "pred_page_misses", "capacity_sensitive"]
    rows = []
    for w in "abc":
        for seed in range(1, 11):
            keys = ops(wl_dir, w, seed)
            for N in REGISTERED_N:
                preds = []
                for C in CAPACITIES:
                    lru = LRU(C)
                    for k in keys[:N]:
                        for pg in touched(tree, k):
                            lru.touch(pg)
                    preds.append(tuple(pg in lru.d for pg in touched(tree, keys[N])))
                p1, root, l2, leaf = preds[0]
                _, _, l2_page, leaf_page = touched(tree, keys[N])
                rows.append({
                    "workload": w.upper(), "seed": seed, "N": N, "probe_op_index": N,
                    "probe_key": keys[N], "probe_l2_page": l2_page, "probe_leaf_page": leaf_page,
                    "pred_page1_hit": int(p1), "pred_root_hit": int(root),
                    "pred_l2_hit": int(l2), "pred_leaf_hit": int(leaf),
                    "pred_interior_hit": int(root and l2),
                    "pred_page_misses": sum(not x for x in preds[0]),
                    "capacity_sensitive": int(preds[0] != preds[1]),
                })
    with open(out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader(); wr.writerows(rows)
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["workload"], r["N"])].append(r["pred_interior_hit"])
    for (w, N), v in sorted(by.items()):
        print(f"{w} N={N:5}: predicted interior hit {sum(v)}/{len(v)}")
    print(f"capacity-sensitive rows: {sum(r['capacity_sensitive'] for r in rows)}/{len(rows)}")


def main():
    mode, db, wl_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    tree = Tree(db)
    if mode == "summary":
        summary(tree, wl_dir)
    elif mode == "predict":
        predict(tree, wl_dir, sys.argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
