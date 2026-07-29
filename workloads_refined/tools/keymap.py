#!/usr/bin/env python3
"""Order-preserving dense rowid keymap: YCSB string keys -> harness integer keys.

Why this exists: the C benchmark harness parses `%llu` integer keys; YCSB emits
`user<19-digit>` string keys. We must map string->int WITHOUT changing which keys are
B-tree neighbours, or we change the research object (see README §2.5).

Ground truth, not a re-implemented hash (README §2.5 improvement): the mapping is derived
from YCSB's OWN load-phase dump. The load phase emits every one of the `recordcount` keys as
`INSERT usertable user… `. Because `zeropadding=19` makes keys fixed-width, lexicographic
order of those strings == numeric order == on-disk B-tree order. So:

    rowid(key) = 1-indexed rank of key in sorted(all load keys)         # dense 1..N

is provably order-preserving (by construction) and needs no FNV `Utils.hash` re-implementation.
This matches the existing DB's dense `id INTEGER PRIMARY KEY` space 1..recordcount, so a
no-insert workload maps straight onto the current `orig` DB with zero rebuild and 0 not-found.

Insert-bearing workloads (YD/YE): keys appended past the universe have no load-phase rank.
This module rejects them unless --insert-base is given (spec §2.5 option (b): reserve rank
space). For the read-only headline (YC) there are no inserts.

Usage:
    keymap.py --load <load.log> --trace <run.jsonl> --out <trace.txt> [--insert-base N]

Emits harness format: `read <id>` / `update <id>` / `insert <id>` / `readmodifywrite <id>`
/ `scan <startid> <len>`.
"""
import argparse
import json
import re
import sys

INSERT_LINE = re.compile(r'^INSERT\s+usertable\s+(user\d+)\s')
OP_OUT = {"read": "read", "update": "update", "insert": "insert",
          "readmodifywrite": "readmodifywrite", "scan": "scan", "delete": "delete"}


def build_rank(load_log):
    """Return {key_string: rowid} with rowid a dense 1..N rank in sorted key order."""
    keys = []
    with open(load_log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = INSERT_LINE.match(line)
            if m:
                keys.append(m.group(1))
    if not keys:
        raise SystemExit(f"FAIL: no INSERT lines found in load dump {load_log!r}")
    if len(set(keys)) != len(keys):
        raise SystemExit(f"FAIL: load dump has duplicate keys ({len(keys)-len(set(keys))} dup)")
    # fixed-width keys: lexicographic sort == B-tree order. rowid 1..N.
    return {k: i for i, k in enumerate(sorted(keys), start=1)}, len(keys)


def map_trace(rank, n_universe, trace_jsonl, insert_base):
    lines = []
    next_insert = insert_base if insert_base is not None else n_universe + 1
    with open(trace_jsonl, encoding="utf-8") as fh:
        for rec in map(json.loads, fh):
            op, key, scanlen = rec["op"], rec["key"], rec.get("scanlen")
            if op == "insert":
                if key in rank:
                    rid = rank[key]                      # re-insert of an existing key (upsert)
                else:
                    rid = next_insert                    # appended new key
                    rank[key] = rid
                    next_insert += 1
                lines.append(f"insert {rid}")
                continue
            if key not in rank:
                raise SystemExit(
                    f"FAIL: key {key!r} ({op}) not in load universe and not an insert. "
                    f"Insert-bearing workload? pass --insert-base (spec §2.5).")
            rid = rank[key]
            if op == "scan":
                if not scanlen or scanlen < 1:
                    raise SystemExit(f"FAIL: scan with bad length {scanlen!r} for key {key!r}")
                lines.append(f"scan {rid} {scanlen}")
            else:
                lines.append(f"{OP_OUT[op]} {rid}")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", required=True, help="YCSB load-phase verbose dump (the universe)")
    ap.add_argument("--trace", required=True, help="run-phase op stream (JSONL from ycsb2trace)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--insert-base", type=int, default=None,
                    help="rowid for the first appended insert (default N+1). Required if the "
                         "trace contains inserts of new keys.")
    args = ap.parse_args()

    rank, n = build_rank(args.load)
    lines = map_trace(rank, n, args.trace, args.insert_base)
    if lines and lines[0].split()[0] != "read":
        sys.stderr.write("WARN: op[0] is not a read; run/aging probes require a read first op.\n")
    with open(args.out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    sys.stderr.write(f"keymap: universe={n} ops={len(lines)} -> {args.out}\n")


if __name__ == "__main__":
    main()
