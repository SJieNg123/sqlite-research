#!/usr/bin/env python3
"""Freeze the identity of every measurement artifact into a manifest.

Reuses the repository's canonical inputs (the reference DB, the page classifier
CSV, and the workload traces used by ``run_experiment.py``) and records their
SHA-256 so the OpenWhisk action can refuse to run on anything but the exact
frozen data. It also derives the mandatory-interior plan (the "2d" skeleton) from
the classifier and freezes it as ``config/plans/interior_pages.csv``.

This does NOT run any benchmark; it only hashes and describes artifacts.

Usage:
  python3 deployment/openwhisk/build_artifact_manifest.py \
      --out deployment/openwhisk/config/artifacts.json          # real (has dev/inode)
  python3 deployment/openwhisk/build_artifact_manifest.py \
      --example --out deployment/openwhisk/config/artifacts.example.json
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

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_REL = "pipeline/preparation/layout_rewriter/runs/test.db"
CLASSIFY_REL = "pipeline/preparation/layout_rewriter/runs/classify_before.csv"
PLAN_REL = "deployment/openwhisk/config/plans/interior_pages.csv"
WORKLOADS = {"A": "a"}          # request key -> trace filename stem
SEEDS = list(range(1, 11))
PAGE_SIZE = 4096


def sha256_file(path, _b=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_b), b""):
            h.update(chunk)
    return h.hexdigest()


def derive_interior_plan(classify_path, plan_path):
    """Write the frozen interior-page plan from the classifier and return
    (offsets, count). Every interior page appears exactly once."""
    rows = []
    seen = set()
    with open(classify_path, newline="") as f:
        for r in csv.DictReader(f):
            if r["page_type"].startswith("interior"):
                pn = int(r["page_number"])
                if pn in seen:
                    sys.exit("duplicate interior page in classifier: %d" % pn)
                seen.add(pn)
                rows.append((pn, int(r["file_offset"])))
    rows.sort()
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    with open(plan_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["page_number", "file_offset"])
        w.writerows(rows)
    return [off for _, off in rows], len(rows)


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True).strip()
    except Exception:  # pragma: no cover
        return None


def db_facts(db_path):
    with open(db_path, "rb") as f:
        head = f.read(32)
    page_size = int.from_bytes(head[16:18], "big") or 65536
    page_count = int.from_bytes(head[28:32], "big")
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT count(*) FROM items").fetchone()[0]
    maxid = conn.execute("SELECT max(id) FROM items").fetchone()[0]
    conn.close()
    return page_size, page_count, rows, maxid


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

    offsets, interior_count = derive_interior_plan(classify, plan)
    page_size, page_count, rows, maxid = db_facts(db)
    st = os.stat(db)

    traces = {}
    for wk, stem in WORKLOADS.items():
        seedmap = {}
        for s in SEEDS:
            rel = "workloads/workload_%s_%d.txt" % (stem, s)
            ap_ = os.path.join(ROOT, rel)
            if os.path.exists(ap_):
                seedmap[str(s)] = {"path": rel, "sha256": sha256_file(ap_)}
        traces[wk] = {"stem": stem, "seeds": seedmap}

    manifest = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository_commit": git_commit(),
        "database": {
            "path": DB_REL,
            "sha256": sha256_file(db),
            "byte_size": st.st_size,
            "page_size": page_size,
            "page_count": page_count,
            "row_count": rows,
            "max_key": maxid,
            # machine-specific; only in the real (non-example) manifest
            "device": None if args.example else st.st_dev,
            "inode": None if args.example else st.st_ino,
        },
        "interior_page_list": {
            "path": PLAN_REL,
            "sha256": sha256_file(plan),
            "count": interior_count,
            "offsets": offsets,
        },
        "strategy_plans": {
            "2d": {"path": PLAN_REL, "sha256": sha256_file(plan),
                   "kind": "interior_skeleton"},
            "baseline": {"path": None, "sha256": None, "kind": "no_prefetch"},
        },
        "workload_traces": traces,
        "expected_relevant_page_count": interior_count,
        "notes": ("Interior skeleton (2d) plan derived from the canonical page "
                  "classifier; every mandatory interior page listed once. Paths "
                  "are repository-relative and resolved at runtime against "
                  "OW_ARTIFACT_ROOT."),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("wrote %s (interiors=%d, page_count=%d, rows=%d)"
          % (args.out, interior_count, page_count, rows))


if __name__ == "__main__":
    main()
