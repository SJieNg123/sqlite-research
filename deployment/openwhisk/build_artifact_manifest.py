#!/usr/bin/env python3
"""Freeze the identity + invariants of every measurement artifact into a manifest.

Reuses the repository's canonical inputs (reference DB, page classifier, workload
traces) and records their SHA-256 plus structural invariants so the OpenWhisk
action can fail closed on anything but the exact frozen data. It also:

  * derives + validates the mandatory-interior (2d) skeleton from the classifier;
  * pins the canonical SQLite pragmas (cache_size=0, mmap_size=file size);
  * records a first-query correctness oracle (expected hit + result digest) for
    every supported first operation.

Invariants enforced here (generation aborts on violation):
  - SQLite page size == 4096 and DB page/row facts read from the header/table;
  - every interior file_offset == (page_number-1)*page_size, 4096-aligned,
    unique, within the DB, exactly 92 interior pages;
  - plan offsets == manifest offsets;
  - all workload-A seeds 1..10 present.

No benchmark is run.

Usage:
  python3 deployment/openwhisk/build_artifact_manifest.py --out .../artifacts.json
  python3 deployment/openwhisk/build_artifact_manifest.py --example --out .../artifacts.example.json
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sqlite3
import sys
from datetime import datetime, timezone

import platform  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "action"))
import oracle  # noqa: E402
try:
    import sqlite_bridge  # noqa: E402
    _BRIDGE_SQLITE_VERSION = sqlite_bridge.libversion()
except OSError:  # pragma: no cover - libsqlite3 unavailable
    _BRIDGE_SQLITE_VERSION = None

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_REL = "pipeline/preparation/layout_rewriter/runs/test.db"
CLASSIFY_REL = "pipeline/preparation/layout_rewriter/runs/classify_before.csv"
PLAN_REL = "deployment/openwhisk/config/plans/interior_pages.csv"
WORKLOADS = {"A": "a"}
SEEDS = list(range(1, 11))
EXPECTED_PAGE_SIZE = 4096
EXPECTED_INTERIORS = 92
SUPPORTED_FIRST_OPS = [0]


def sha256_file(path, _b=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_b), b""):
            h.update(chunk)
    return h.hexdigest()


def decode_page_size(head):
    """SQLite header page-size field (offset 16, u16 BE); the value 1 encodes
    65536 (spec), which a naive `x or 65536` would mis-handle."""
    ps = int.from_bytes(head[16:18], "big")
    return 65536 if ps == 1 else ps


def derive_and_validate_plan(classify_path, plan_path, page_size, page_count):
    rows, seen = [], set()
    with open(classify_path, newline="") as f:
        for r in csv.DictReader(f):
            if r["page_type"].startswith("interior"):
                pn = int(r["page_number"])
                off = int(r["file_offset"])
                if pn in seen:
                    sys.exit("duplicate interior page in classifier: %d" % pn)
                seen.add(pn)
                rows.append((pn, off))
    rows.sort()
    # ---- invariants ----
    if len(rows) != EXPECTED_INTERIORS:
        sys.exit("expected %d interior pages, found %d"
                 % (EXPECTED_INTERIORS, len(rows)))
    offs = set()
    for pn, off in rows:
        if not (1 <= pn <= page_count):
            sys.exit("interior page_number %d out of range 1..%d" % (pn, page_count))
        if off != (pn - 1) * page_size:
            sys.exit("interior offset %d != (%d-1)*%d" % (off, pn, page_size))
        if off % page_size != 0:
            sys.exit("interior offset %d not %d-aligned" % (off, page_size))
        if off in offs:
            sys.exit("duplicate interior offset %d" % off)
        if not (0 <= off < page_count * page_size):
            sys.exit("interior offset %d outside DB" % off)
        offs.add(off)
    # ---- write frozen plan + confirm round-trip equality ----
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    with open(plan_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["page_number", "file_offset"])
        w.writerows(rows)
    plan_offsets = []
    with open(plan_path, newline="") as f:
        for r in csv.DictReader(f):
            plan_offsets.append(int(r["file_offset"]))
    manifest_offsets = [off for _, off in rows]
    if plan_offsets != manifest_offsets:
        sys.exit("plan offsets differ from manifest offsets")
    return manifest_offsets


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    except Exception:  # pragma: no cover
        return None


def first_op_key(trace_path, first_op):
    with open(trace_path) as f:
        for i, line in enumerate(f):
            if i == first_op:
                parts = line.split()
                if len(parts) < 2 or parts[0] != "read":
                    sys.exit("unsupported op at %d in %s" % (i, trace_path))
                return int(parts[1])
    sys.exit("first_operation_id %d beyond %s" % (first_op, trace_path))


def build_oracle(db_path):
    """Expected hit + digest for every supported first op of every A seed."""
    conn = sqlite3.connect(db_path)
    out = {}
    for wk, stem in WORKLOADS.items():
        out[wk] = {}
        for s in SEEDS:
            rel = "workloads/workload_%s_%d.txt" % (stem, s)
            tp = os.path.join(ROOT, rel)
            if not os.path.exists(tp):
                conn.close()
                sys.exit("missing required trace for oracle: %s" % rel)
            out[wk][str(s)] = {}
            for fop in SUPPORTED_FIRST_OPS:
                key = first_op_key(tp, fop)
                hit_raw, payload = oracle.run_read_payload(conn, key)
                hit, digest = oracle.digest_payload(hit_raw, payload)
                out[wk][str(s)][str(fop)] = {
                    "key": key, "expected_hit": hit, "expected_digest": digest}
    conn.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--example", action="store_true",
                    help="omit machine-specific device/inode (committed example)")
    args = ap.parse_args()

    db = os.path.join(ROOT, DB_REL)
    classify = os.path.join(ROOT, CLASSIFY_REL)
    plan = os.path.join(ROOT, PLAN_REL)
    for p in (db, classify):
        if not os.path.exists(p):
            sys.exit("missing canonical artifact: %s" % p)

    with open(db, "rb") as f:
        head = f.read(32)
    page_size = decode_page_size(head)
    if page_size != EXPECTED_PAGE_SIZE:
        sys.exit("DB page size %d != %d" % (page_size, EXPECTED_PAGE_SIZE))
    page_count = int.from_bytes(head[28:32], "big")

    conn = sqlite3.connect(db)
    row_count = conn.execute("SELECT count(*) FROM items").fetchone()[0]
    maxid = conn.execute("SELECT max(id) FROM items").fetchone()[0]
    conn.close()

    offsets = derive_and_validate_plan(classify, plan, page_size, page_count)

    # all A seeds required
    traces = {}
    for wk, stem in WORKLOADS.items():
        seedmap = {}
        for s in SEEDS:
            rel = "workloads/workload_%s_%d.txt" % (stem, s)
            ap_ = os.path.join(ROOT, rel)
            if not os.path.exists(ap_):
                sys.exit("missing required workload trace: %s" % rel)
            seedmap[str(s)] = {"path": rel, "sha256": sha256_file(ap_)}
        traces[wk] = {"stem": stem, "seeds": seedmap}

    st = os.stat(db)
    manifest = {
        "schema_version": 2,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository_commit": git_commit(),
        "os_page_size_expected": EXPECTED_PAGE_SIZE,
        "sqlite_page_size_expected": EXPECTED_PAGE_SIZE,
        "runtime": {
            "sqlite_library_version": _BRIDGE_SQLITE_VERSION,
            "python_version": platform.python_version(),
        },
        # Immutable action image digest; filled at deploy (from OW_ACTION_IMAGE_DIGEST
        # or the run config). Null in the committed example.
        "action_image_digest": None if args.example else os.environ.get("OW_ACTION_IMAGE_DIGEST"),
        "canonical_query": oracle.SELECT_SQL,
        "database": {
            "path": DB_REL,
            "sha256": sha256_file(db),
            "byte_size": st.st_size,
            "page_size": page_size,
            "page_count": page_count,
            "row_count": row_count,
            "max_key": maxid,
            "device": None if args.example else st.st_dev,
            "inode": None if args.example else st.st_ino,
        },
        "classifier": {"path": CLASSIFY_REL, "sha256": sha256_file(classify)},
        "interior_page_list": {
            "path": PLAN_REL,
            "sha256": sha256_file(plan),
            "count": EXPECTED_INTERIORS,
            "offsets": offsets,
        },
        "interior_page_count": EXPECTED_INTERIORS,
        # denominator for "relevant page residency %" is the WHOLE DB, not the
        # 92-page interior skeleton (blocker 5).
        "expected_relevant_page_count": page_count,
        # Warm-handle pragmas. cache_size=0 matches benchmark_harness.c (the OS
        # page cache is the only data cache). mmap_size=0 (pager pread path) is a
        # deliberate departure from the C harness default (file size): a
        # persistent SQLite mmap pins the pages it traverses, which blocks
        # non-root re-eviction between invocations on a warm process. Using the
        # pread path keeps no mapping alive, so POSIX_FADV_DONTNEED can re-cold
        # the file before every measured invocation. The canonical file-size
        # value is recorded below for fidelity comparison (it requires root
        # drop_caches to re-cold between invocations).
        "sqlite_pragmas": {"cache_size": 0, "mmap_size": 0},
        "canonical_reference_pragmas": {"cache_size": 0, "mmap_size": st.st_size,
                                        "source": "benchmark_harness.c default"},
        "strategy_plans": {
            "2d": {"path": PLAN_REL, "sha256": sha256_file(plan),
                   "kind": "interior_skeleton", "expected_pages": EXPECTED_INTERIORS},
            "baseline": {"path": None, "sha256": None, "kind": "no_prefetch",
                         "expected_pages": 0},
        },
        "workload_traces": traces,
        "supported_first_operation_ids": SUPPORTED_FIRST_OPS,
        "first_query_oracle": build_oracle(db),
        "notes": ("Interior skeleton (2d) plan derived from the canonical page "
                  "classifier; invariants validated at generation. Paths are "
                  "repository-relative, resolved at runtime against "
                  "OW_ARTIFACT_ROOT. expected_relevant_page_count is the whole-DB "
                  "page count; interior_page_count is the 92-page skeleton."),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("wrote %s (interiors=%d, relevant_denominator=%d, rows=%d, oracle_ops=%d)"
          % (args.out, EXPECTED_INTERIORS, page_count, row_count,
             sum(len(v) for wk in manifest["first_query_oracle"].values()
                 for v in wk.values())))


if __name__ == "__main__":
    main()
