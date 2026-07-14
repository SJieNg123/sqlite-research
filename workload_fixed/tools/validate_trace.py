#!/usr/bin/env python3
"""Tier 0 trace validator (spec §5). Runs on the harness-format integer-key trace.

Every workload adjective must map to a NUMBER here (spec §-1.3 / §5.3). This computes the
trace-level checks that guard the two failure modes that bit this project:
  concern #3 (out-of-range not-found)  -> notfound_rate, measured_skew, unique_key_ratio
  concern #2 (churn claim, 0 hot-page movement) -> hotset_jaccard_series
plus op_mix_actual and parse_losses.

Page-level checks (page_count / fill_factor / btree_depth / skeleton_bytes) are DB-global and
computed via Python stdlib `dbstat` (3.46.1, no custom build — README §5.1) when --db is given.
`rightmost_leaf_share` needs a key->page map and is emitted as a deferred status here (run phase).

Emits <out> (JSON). Exits non-zero on a hard violation:
  * declared hit-only but notfound_rate > 0
  * notfound_rate > --max-notfound  (spec §1.1: Tier 2 entry needs <= 1%)
  * parse_losses > 0

Usage:
  validate_trace.py <trace.txt> --out <validation.json> [--db-max-key 600000]
        [--hit-only] [--max-notfound 0.01] [--segments 10] [--parse-losses 0]
        [--db <sqlite.db> --table items] [--label YC-hashed] [--props k=v,...]
"""
import argparse
import collections
import json
import sys

TARGET_OPS = {"read", "scan"}          # ops whose key hits the DB key space


def load_trace(path):
    ops = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            op = parts[0]
            key = int(parts[1])
            scanlen = int(parts[2]) if op == "scan" and len(parts) > 2 else None
            ops.append((op, key, scanlen))
    return ops


def measured_skew(targets):
    freq = collections.Counter(targets)
    total = len(targets)
    ranked = freq.most_common()
    top1 = ranked[0][1] / total if total else None
    k1pct = max(1, len(freq) // 100)
    top1pct = sum(c for _, c in ranked[:k1pct]) / total if total else None
    return {"top1_key_share": round(top1, 6) if top1 is not None else None,
            "top1pct_keys_share": round(top1pct, 6) if top1pct is not None else None,
            "distinct_keys": len(freq)}


def hotset_jaccard_series(targets, segments):
    """Split the target stream into `segments` contiguous chunks; per chunk take the top-1%
    hottest keys; report adjacent-chunk Jaccard. Stationary hotspot -> high; moving -> low."""
    if len(targets) < segments * 100:
        return {"status": "n/a (too few targets)", "series": [], "mean": None}
    size = len(targets) // segments
    hotsets = []
    for i in range(segments):
        chunk = targets[i * size:(i + 1) * size]
        freq = collections.Counter(chunk)
        k = max(1, len(freq) // 100)
        hotsets.append({key for key, _ in freq.most_common(k)})
    series = []
    for a, b in zip(hotsets, hotsets[1:]):
        u = len(a | b)
        series.append(round(len(a & b) / u, 4) if u else None)
    vals = [s for s in series if s is not None]
    return {"status": "ok", "segments": segments, "series": series,
            "mean": round(sum(vals) / len(vals), 4) if vals else None}


def db_page_stats(db_path, table):
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        page_size = con.execute("PRAGMA page_size").fetchone()[0]
        page_count = con.execute("PRAGMA page_count").fetchone()[0]
        rows = con.execute(
            "SELECT pagetype, ncell, payload, unused, path FROM dbstat WHERE name=?",
            (table,)).fetchall()
    except sqlite3.OperationalError as e:
        return {"status": f"dbstat unavailable: {e}"}
    finally:
        con.close()
    interior = [r for r in rows if r[0] == "internal"]
    leaf = [r for r in rows if r[0] == "leaf"]
    depth = max((r[4].count("/") for r in rows), default=0)  # dbstat path segment depth
    leaf_fill = None
    if leaf:
        leaf_fill = round(sum(1 - (r[3] / page_size) for r in leaf) / len(leaf), 4)
    return {
        "status": "ok", "page_size": page_size, "page_count": page_count,
        "table_interior_pages": len(interior), "table_leaf_pages": len(leaf),
        "btree_depth": depth, "leaf_fill_factor": leaf_fill,
        "skeleton_bytes": len(interior) * page_size,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out", required=True)
    ap.add_argument("--db-max-key", type=int, default=600000)
    ap.add_argument("--hit-only", action="store_true")
    ap.add_argument("--max-notfound", type=float, default=0.01)
    ap.add_argument("--segments", type=int, default=10)
    ap.add_argument("--parse-losses", type=int, default=0)
    ap.add_argument("--db", default=None)
    ap.add_argument("--table", default="items")
    ap.add_argument("--label", default=None)
    ap.add_argument("--props", default=None)
    args = ap.parse_args()

    ops = load_trace(args.trace)
    op_mix = collections.Counter(op for op, _, _ in ops)
    targets = [k for op, k, _ in ops if op in TARGET_OPS]
    inserts = [k for op, k, _ in ops if op == "insert"]

    # not-found accounting: a read/scan target above the DB's max existing id is a negative
    # lookup. (inserts append past db_max_key legitimately and are excluded.)
    miss = sum(1 for k in targets if k > args.db_max_key)
    notfound_rate = round(miss / len(targets), 6) if targets else None

    report = {
        "label": args.label, "trace": args.trace,
        "n_ops": len(ops),
        "op_mix_actual": dict(op_mix),
        "target_ops": len(targets),
        "unique_key_ratio": round(len(set(targets)) / len(targets), 6) if targets else None,
        "measured_skew": measured_skew(targets),
        "notfound_rate": notfound_rate,
        "notfound_count": miss,
        "db_max_key": args.db_max_key,
        "hit_only_declared": args.hit_only,
        "insert_count": len(inserts),
        "generated_min_key": min(targets) if targets else None,
        "generated_max_key": max(targets) if targets else None,
        "first_op": " ".join(map(str, filter(lambda x: x is not None,
                                             (ops[0][0], ops[0][1], ops[0][2])))) if ops else None,
        "first_op_is_read": ops[0][0] == "read" if ops else None,
        "hotset_jaccard_series": hotset_jaccard_series(targets, args.segments),
        "parse_losses": args.parse_losses,
        "rightmost_leaf_share": {"status": "deferred: needs key->page map (run phase)"},
        "props": args.props,
    }
    if args.db:
        report["db_page_stats"] = db_page_stats(args.db, args.table)

    # ---- hard violations ----
    fails = []
    if args.parse_losses > 0:
        fails.append(f"parse_losses={args.parse_losses} > 0")
    if args.hit_only and miss > 0:
        fails.append(f"hit_only declared but notfound_count={miss}")
    if notfound_rate is not None and notfound_rate > args.max_notfound:
        fails.append(f"notfound_rate={notfound_rate} > max_notfound={args.max_notfound}")
    report["verdict"] = "PASS" if not fails else "FAIL"
    report["violations"] = fails

    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
    sys.stderr.write(f"validate_trace: {report['verdict']} -> {args.out}"
                     + (f"  ({'; '.join(fails)})" if fails else "") + "\n")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
