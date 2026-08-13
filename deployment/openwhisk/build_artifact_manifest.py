#!/usr/bin/env python3
"""Freeze the identity + invariants of every measurement artifact into a manifest.

Reuses the repository's canonical inputs (reference DB, page classifier, workload
traces) and records their SHA-256 plus structural invariants so the OpenWhisk
action can fail closed on anything but the exact frozen data. It also:

  * derives + validates the mandatory-interior (2d) skeleton from the classifier;
  * derives + validates the layers_5 static plan (first 5 interior pages by native
    (file_offset, page_number) order; a strict prefix of the 2d skeleton);
  * pins the canonical SQLite pragmas (cache_size=0, mmap_size=file size);
  * records a first-query correctness oracle (expected hit + result digest) for
    every supported first operation.

Invariants enforced here (generation aborts on violation):
  - SQLite page size == 4096 and DB page/row facts read from the header/table;
  - every interior file_offset == (page_number-1)*page_size, 4096-aligned,
    unique, within the DB, exactly 92 interior pages;
  - plan offsets == manifest offsets;
  - all native YCSB-C seeds 1..10 present;
  - every generated DB/plan/classifier/trace SHA256 matches the frozen replay pin
    (config/artifacts.native_ycsb.json). The live manifest is byte-tied to the pin.

The generated manifest is destined for the action image; device/inode are always
null (the runtime self-pins st_dev/st_ino at process init and only rejects a
change during the session, so host values would be meaningless in-container).

No benchmark is run.

Usage:
  python3 deployment/openwhisk/build_artifact_manifest.py --out .../artifacts.json
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
LAYERS5_PLAN_REL = "deployment/openwhisk/config/plans/layers_5_pages.csv"
PIN_REL = "deployment/openwhisk/config/artifacts.native_ycsb.json"
# The single canonical measured workload for this phase: native YCSB-C read (zipf).
# The manifest keys workload_traces/first_query_oracle on this id; the ws2 diagnostic
# and matrix drive the same id from the frozen pin.
CANONICAL_WORKLOAD_ID = "native_ycsb_c_read_zipf"
YC_TRACE_REL = "workloads_refined/traces/seeds/workload_YC_%d.txt"
SEEDS = list(range(1, 11))
EXPECTED_PAGE_SIZE = 4096
EXPECTED_INTERIORS = 92
LAYERS5_N = 5
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


def derive_layers_prefix(classify_path, plan_path, n, page_size, page_count,
                         interior_offsets):
    """Freeze the layers_N static plan: the first N interior pages by canonical
    native ordering (file_offset, page_number). This mirrors run_experiment.py's
    ``layers`` kind (sort interiors by offset, take the first N) and is a STRICT
    PREFIX of the 92-interior skeleton -- workload/seed/first-op independent, no
    leaf pages. ``interior_offsets`` is the already-validated 92-offset set; each
    selected page must be a member (subset invariant). Writes the plan in the same
    CSV schema as the 2d plan and confirms round-trip equality."""
    rows = []
    with open(classify_path, newline="") as f:
        for r in csv.DictReader(f):
            if r["page_type"].startswith("interior"):
                rows.append((int(r["file_offset"]), int(r["page_number"])))
    rows.sort()  # canonical native order: (file_offset, page_number)
    if len(rows) < n:
        sys.exit("cannot take first %d interiors; only %d present" % (n, len(rows)))
    interior_set = set(interior_offsets)
    out = []  # (page_number, file_offset) -- same schema/order as the 2d plan
    for off, pn in rows[:n]:
        if off != (pn - 1) * page_size:
            sys.exit("layers offset %d != (%d-1)*%d" % (off, pn, page_size))
        if off % page_size != 0:
            sys.exit("layers offset %d not %d-aligned" % (off, page_size))
        if not (0 <= off < page_count * page_size):
            sys.exit("layers offset %d outside DB" % off)
        if off not in interior_set:
            sys.exit("layers offset %d not in validated interior skeleton" % off)
        out.append((pn, off))
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    with open(plan_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["page_number", "file_offset"])
        w.writerows(out)
    plan_offsets = []
    with open(plan_path, newline="") as f:
        for r in csv.DictReader(f):
            plan_offsets.append(int(r["file_offset"]))
    manifest_offsets = [off for _, off in out]
    if plan_offsets != manifest_offsets:
        sys.exit("layers plan offsets differ from manifest offsets")
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
    """Expected hit + digest for every supported first op of every YCSB-C seed."""
    conn = sqlite3.connect(db_path)
    out = {CANONICAL_WORKLOAD_ID: {}}
    for s in SEEDS:
        rel = YC_TRACE_REL % s
        tp = os.path.join(ROOT, rel)
        if not os.path.exists(tp):
            conn.close()
            sys.exit("missing required trace for oracle: %s" % rel)
        out[CANONICAL_WORKLOAD_ID][str(s)] = {}
        for fop in SUPPORTED_FIRST_OPS:
            key = first_op_key(tp, fop)
            hit_raw, payload = oracle.run_read_payload(conn, key)
            hit, digest = oracle.digest_payload(hit_raw, payload)
            out[CANONICAL_WORKLOAD_ID][str(s)][str(fop)] = {
                "key": key, "expected_hit": hit, "expected_digest": digest}
    conn.close()
    return out


def crosscheck_pin(db_sha, plan_sha, classifier_sha, trace_shas,
                   layers5_sha, layers5_offsets):
    """Fail closed unless every generated hash matches the frozen replay pin.
    Ties the live image manifest byte-for-byte to config/artifacts.native_ycsb.json
    (single source of truth for DB / 2d plan / layers_5 plan / classifier / YC trace
    identity)."""
    pin_path = os.path.join(ROOT, PIN_REL)
    if not os.path.exists(pin_path):
        sys.exit("missing frozen native-YCSB pin: %s" % PIN_REL)
    with open(pin_path) as f:
        pin = json.load(f)

    def need(got, want, label):
        if got != want:
            sys.exit("pin mismatch %s: generated %s != pin %s" % (label, got, want))

    need(CANONICAL_WORKLOAD_ID,
         pin["representative_workload"]["canonical_workload_id"], "canonical_workload_id")
    need(db_sha, pin["database"]["sha256"], "db")
    need(plan_sha, pin["strategy_plans"]["2d"]["sha256"], "2d_plan")
    need(classifier_sha, pin["classifier"]["sha256"], "classifier")
    # layers_5 is explicitly pinned (sha + counts + offsets), not only transitively
    # via the classifier sha; the generated plan must match it byte-for-byte.
    l5 = pin["strategy_plans"].get("layers_5")
    if l5 is None:
        sys.exit("pin mismatch layers_5: strategy_plans has no layers_5 entry")
    need(layers5_sha, l5["sha256"], "layers_5_plan")
    need(len(layers5_offsets), l5["expected_pages"], "layers_5_expected_pages")
    need(len(layers5_offsets), l5.get("expected_interior_pages"),
         "layers_5_expected_interior_pages")
    need(0, l5.get("expected_leaf_pages"), "layers_5_expected_leaf_pages")
    need(list(layers5_offsets), list(l5.get("offsets", [])), "layers_5_offsets")
    pin_traces = {str(e["seed"]): e["trace_sha256"]
                  for e in pin["representative_workload"]["seed_family"]}
    for s in SEEDS:
        need(trace_shas[str(s)], pin_traces[str(s)], "trace_seed_%d" % s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--example", action="store_true",
                    help="deprecated no-op: device/inode are always null now "
                         "(image-bound manifest; runtime self-pins). The committed "
                         "workload-A example is a frozen test fixture, not produced here.")
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

    # layers_5 static plan: first 5 interiors (native order), strict prefix of 2d.
    layers5_plan = os.path.join(ROOT, LAYERS5_PLAN_REL)
    layers5_offsets = derive_layers_prefix(classify, layers5_plan, LAYERS5_N,
                                           page_size, page_count, offsets)
    layers5_sha = sha256_file(layers5_plan)

    # all native YCSB-C seeds required
    seedmap = {}
    for s in SEEDS:
        rel = YC_TRACE_REL % s
        ap_ = os.path.join(ROOT, rel)
        if not os.path.exists(ap_):
            sys.exit("missing required workload trace: %s" % rel)
        seedmap[str(s)] = {"path": rel, "sha256": sha256_file(ap_)}
    traces = {CANONICAL_WORKLOAD_ID: {"seeds": seedmap}}

    # Byte-tie the live manifest to the frozen replay pin (fail closed).
    db_sha = sha256_file(db)
    plan_sha = sha256_file(plan)
    classifier_sha = sha256_file(classify)
    crosscheck_pin(db_sha, plan_sha, classifier_sha,
                   {s: seedmap[s]["sha256"] for s in seedmap},
                   layers5_sha, layers5_offsets)

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
        # or the run config). Null until then.
        "action_image_digest": os.environ.get("OW_ACTION_IMAGE_DIGEST"),
        "canonical_query": oracle.SELECT_SQL,
        "database": {
            "path": DB_REL,
            "sha256": db_sha,
            "byte_size": st.st_size,
            "page_size": page_size,
            "page_count": page_count,
            "row_count": row_count,
            "max_key": maxid,
            # Always null: this manifest is image-bound and the runtime self-pins
            # (st_dev, st_ino) at process init; host values are meaningless in-container.
            "device": None,
            "inode": None,
        },
        "classifier": {"path": CLASSIFY_REL, "sha256": classifier_sha},
        "interior_page_list": {
            "path": PLAN_REL,
            "sha256": plan_sha,
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
            "2d": {"path": PLAN_REL, "sha256": plan_sha,
                   "kind": "interior_skeleton", "expected_pages": EXPECTED_INTERIORS},
            "layers_5": {
                "path": LAYERS5_PLAN_REL, "sha256": layers5_sha,
                "kind": "interior_prefix", "expected_pages": LAYERS5_N,
                "expected_interior_pages": LAYERS5_N, "expected_leaf_pages": 0,
                "offsets": layers5_offsets,
                "note": ("first %d interior pages by native (file_offset, "
                         "page_number) order; strict prefix of the 92-interior "
                         "skeleton; workload/seed/first-op independent. "
                         "Transitively pinned via the classifier sha in the "
                         "native-YCSB replay pin." % LAYERS5_N),
            },
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
