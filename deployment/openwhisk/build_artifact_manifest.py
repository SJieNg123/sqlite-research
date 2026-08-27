#!/usr/bin/env python3
"""Freeze the identity + invariants of every measurement artifact into a manifest.

Reuses the repository's canonical inputs (reference DB, page classifier, workload
traces) and records their SHA-256 plus structural invariants so the OpenWhisk
action can fail closed on anything but the exact frozen data. It also:

  * derives + validates the mandatory-interior (2d) skeleton from the classifier;
  * derives + validates the layers_5 static plan (first 5 interior pages by native
    (file_offset, page_number) order; a strict prefix of the 2d skeleton);
  * reads + validates the keyed per-(workload,seed) delivery plans for every keyed
    strategy in KEYED_SPECS (2e_K10 = 92-interior skeleton UNION top-10 hot leaves,
    fixed 102; 2f_slru = the whole resident working set, per-seed footprint). Each
    plan's interior half always equals the 92-page skeleton (set equality); totals/
    leaves may vary per seed. These are committed frozen artifacts -- never
    regenerated here;
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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
import portability_manifest as PM  # noqa: E402
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

# Keyed (per workload+seed) strategy plans. Each keyed strategy freezes a
# per-(workload,seed) delivery plan whose interior half is ALWAYS the 92-page 2d
# skeleton (set equality, enforced for every seed) but whose total/leaf footprint
# may vary per seed. These CSVs are committed, hash-pinned artifacts derived from
# the canonical native research method (see config/plans/keyed/native_source/
# PROVENANCE.md); the generator READS and validates them, never regenerating the
# research method. A spec's expected_pages/expected_leaf of None means "derive per
# seed from the plan" (do not enforce a universal count).
KEYED_EXPECTED_INTERIOR = EXPECTED_INTERIORS  # 92-page skeleton, fixed for all keyed plans

# 2e_K10 native source of record per seed (committed, durable): the 9 common seeds
# share this repo's in-repo unseeded master; seed 6 diverges (fork-only) and its
# native source is committed under keyed/native_source/.
NATIVE_MASTER_REL = "strategies/access/runs/hot2e_YC_orig_K10.csv"
SEED6_NATIVE_REL = ("deployment/openwhisk/config/plans/keyed/native_source/"
                    "hot2e_YC_orig_K10_seed6.csv")


def _hot2e_native_rel(seed):
    return SEED6_NATIVE_REL if seed == 6 else NATIVE_MASTER_REL


def _slru_native_rel(seed):
    # 2f_slru per-seed resident-set sources are fork-only (in-repo has only the
    # unseeded whole-DB hotpages_yc.csv), so all ten are committed here.
    return ("deployment/openwhisk/config/plans/keyed/native_source/"
            "hotpages_yc_seed%d.csv" % seed)


# --- secondary strategy native sources of record (committed per seed) ---
def _hot2e_k500_native_rel(seed):
    return ("deployment/openwhisk/config/plans/keyed/native_source/"
            "hot2e_YC_orig_K500_seed%d.csv" % seed)


def _freqdump_native_rel(seed):
    return ("deployment/openwhisk/config/plans/keyed/native_source/"
            "freqdump_YC_orig_N102_seed%d.csv" % seed)


def _markov_native_rel(seed):
    # LOSO test-seed model hotset (trained on the other 9 seeds).
    return ("deployment/openwhisk/config/plans/keyed/native_source/"
            "learned_markov_YC_orig_N102_test%d.csv" % seed)


KEYED_SPECS = [
    {
        "strategy": "2e_K10",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "2e_K10_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "hot2e_interior_union_leaf",
        "marker_kind": "hot2e_keyed_per_seed",
        "expected_pages": 102,   # fixed across seeds
        "expected_leaf": 10,     # fixed across seeds
        "expected_interior": EXPECTED_INTERIORS,  # full 92-skeleton (set-equality)
        "native_source_rel": _hot2e_native_rel,
        "marker_note": ("2e_K10 = resident 92-interior 2d skeleton UNION top-10 hot "
                        "leaf pages; leaf half is seed-dependent. Per-seed frozen "
                        "plans in keyed_strategy_plans[%s][<seed>][2e_K10]."
                        % CANONICAL_WORKLOAD_ID),
    },
    {
        "strategy": "2f_slru",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "2f_slru_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "slru_resident_working_set",
        "marker_kind": "slru_keyed_per_seed",
        "expected_pages": None,  # per-seed (whole resident working set)
        "expected_leaf": None,   # per-seed = total - 92
        "expected_interior": EXPECTED_INTERIORS,  # full 92-skeleton (set-equality)
        "native_source_rel": _slru_native_rel,
        "marker_note": ("2f_slru = the entire resident working set (SLRU) for the "
                        "workload+seed, delivered before the measured first query "
                        "(first-query foil). Interior half is the 92-page skeleton; "
                        "total/leaf footprint is per-seed (seed 8 = whole DB). "
                        "Per-seed frozen plans in "
                        "keyed_strategy_plans[%s][<seed>][2f_slru]."
                        % CANONICAL_WORKLOAD_ID),
    },
    # --- YC SECONDARY strategies (mechanism-space characterization around 2e_K10;
    # NOT headline warm-latency claims -- see the interpretation note). N_YC=102 =
    # 92 interior + 10 leaf, frozen from the 2e_K10 artifact. Three interior gate
    # classes: 92 (full skeleton, set-equality), 0 (leaf-only), None (emergent split
    # for rank-by-frequency/score strategies, recorded per seed but not enforced). ---
    {
        "strategy": "2e_K500",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "2e_K500_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "hot2e_interior_union_leaf",
        "marker_kind": "hot2e_keyed_per_seed",
        "expected_pages": None,  # per-seed (92 skeleton + top-500 leaves; here 592)
        "expected_leaf": None,   # per-seed = total - 92
        "expected_interior": EXPECTED_INTERIORS,  # full 92-skeleton (set-equality)
        "native_source_rel": _hot2e_k500_native_rel,
        "marker_note": ("2e_K500 = resident 92-interior 2d skeleton UNION top-500 hot "
                        "leaf pages (deep leaf union; K=500 vs 2e_K10's K=10). Leaf "
                        "half is seed-dependent. Per-seed frozen plans in "
                        "keyed_strategy_plans[%s][<seed>][2e_K500]."
                        % CANONICAL_WORKLOAD_ID),
    },
    {
        "strategy": "leaf_freq_K10",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "leaf_freq_K10_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "leaf_only_frequency",
        "marker_kind": "leaf_keyed_per_seed",
        "expected_pages": 10,    # fixed across seeds
        "expected_leaf": 10,     # fixed across seeds
        "expected_interior": 0,  # leaf-only ablation (interior skeleton omitted)
        "native_source_rel": _hot2e_native_rel,  # top-10 hot leaves OF the 2e_K10 source
        "marker_note": ("leaf_freq_K10 = the top-10 hot LEAF pages only -- the leaf "
                        "half of 2e_K10 with the interior skeleton removed (frequency "
                        "arm of the leaf-only ablation). Per-seed frozen plans in "
                        "keyed_strategy_plans[%s][<seed>][leaf_freq_K10]."
                        % CANONICAL_WORKLOAD_ID),
    },
    {
        "strategy": "leaf_rand_K10",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "leaf_rand_K10_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "leaf_only_random",
        "marker_kind": "leaf_keyed_per_seed",
        "expected_pages": 10,    # fixed across seeds
        "expected_leaf": 10,     # fixed across seeds
        "expected_interior": 0,  # leaf-only ablation (interior skeleton omitted)
        "native_source_rel": _hot2e_native_rel,  # defines the excluded-hot-leaf pool
        "marker_note": ("leaf_rand_K10 = 10 RANDOM leaf pages of the same leaf "
                        "type(s) as the top-10 hot leaves, drawn by a deterministic "
                        "seeded RNG (random arm of the leaf-only ablation; interior "
                        "skeleton omitted). Per-seed frozen plans in "
                        "keyed_strategy_plans[%s][<seed>][leaf_rand_K10]."
                        % CANONICAL_WORKLOAD_ID),
    },
    {
        "strategy": "2f_top102",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "2f_top102_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "freqdump_ranked_partial",
        "marker_kind": "freqdump_keyed_per_seed",
        "expected_pages": 102,      # budget-matched to 2e_K10 (exact)
        "expected_leaf": None,      # emergent
        "expected_interior": None,  # EMERGENT split (ranks with no page-type knowledge)
        "native_source_rel": _freqdump_native_rel,
        "marker_note": ("2f_top102 = the top-102 resident pages by root->leaf "
                        "traversal frequency (total budget-matched to 2e_K10's 102). "
                        "Ranks with NO page-type knowledge, so the interior/leaf "
                        "split is EMERGENT (observed 51/51 across seeds), recorded "
                        "per seed but NOT enforced. Per-seed frozen plans in "
                        "keyed_strategy_plans[%s][<seed>][2f_top102]."
                        % CANONICAL_WORKLOAD_ID),
    },
    {
        "strategy": "learned_markov_102",
        "plan_rel": ("deployment/openwhisk/config/plans/keyed/"
                     "learned_markov_102_native_ycsb_c_read_zipf_seed%d.csv"),
        "kind": "learned_markov_partial",
        "marker_kind": "learned_markov_keyed_per_seed",
        "expected_pages": 102,      # budget-matched to 2e_K10 (exact)
        "expected_leaf": None,      # emergent
        "expected_interior": None,  # EMERGENT split (ranks by transition score)
        "native_source_rel": _markov_native_rel,
        "marker_note": ("learned_markov_102 = the top-102 pages by first-order Markov "
                        "expected-visit score from a HELD-OUT (LOSO) transition model "
                        "trained on the other 9 seeds (budget-matched to 102). Ranks "
                        "by transition score with no page-type knowledge, so the "
                        "interior/leaf split is EMERGENT (observed 51/51 across "
                        "seeds), recorded per seed but NOT enforced. Per-seed frozen "
                        "plans in keyed_strategy_plans[%s][<seed>][learned_markov_102]."
                        % CANONICAL_WORKLOAD_ID),
    },
]


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


def read_keyed_plan(csv_path, page_size, page_count, interior_offsets,
                    expected_pages=None, expected_leaf=None,
                    expected_interior=KEYED_EXPECTED_INTERIOR):
    """Read and validate a committed keyed delivery plan (page_number,file_offset).
    The plan is NOT regenerated here; it is the frozen native selection. Fails
    closed unless: every offset == (page-1)*page_size, aligned, within the DB, and
    unique; the interior half equals (set equality) the validated 92-interior
    skeleton (ALWAYS enforced). ``expected_pages``/``expected_leaf`` of None means
    the count is per-seed data and is derived rather than enforced against a
    universal invariant; when given, the total/leaf count must match exactly.
    Returns (offsets, interior_offsets_sorted, leaf_offsets) in CSV (page) order
    for offsets/leaves."""
    interior_set = set(interior_offsets)
    offs, seen = [], set()
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            pn = int(r["page_number"]); fo = int(r["file_offset"])
            if fo != (pn - 1) * page_size:
                sys.exit("keyed plan offset %d != (%d-1)*%d in %s"
                         % (fo, pn, page_size, csv_path))
            if fo % page_size != 0:
                sys.exit("keyed plan offset %d not %d-aligned in %s"
                         % (fo, page_size, csv_path))
            if not (0 <= fo < page_count * page_size):
                sys.exit("keyed plan offset %d outside DB in %s" % (fo, csv_path))
            if fo in seen:
                sys.exit("duplicate keyed plan offset %d in %s" % (fo, csv_path))
            seen.add(fo); offs.append(fo)
    if expected_pages is not None and len(offs) != expected_pages:
        sys.exit("keyed plan %s has %d pages, expected %d"
                 % (csv_path, len(offs), expected_pages))
    interior_hit = [o for o in offs if o in interior_set]
    leaf = [o for o in offs if o not in interior_set]
    # 3-class interior gate. ``expected_interior`` is one of:
    #   92 (EXPECTED_INTERIORS) -> the plan carries the full interior skeleton:
    #       enforce BOTH the count and set-equality with the 92-page skeleton
    #       (2e_K10, 2e_K500, 2f_slru);
    #   0 -> a leaf-only plan: enforce zero interiors (leaf_freq_K10, leaf_rand_K10);
    #   None -> an emergent split (2f_top102, learned_markov_102 rank by frequency /
    #       transition score with no page-type knowledge): record the interior half,
    #       do NOT force a count or the skeleton (forcing either would inject the very
    #       page-type structure these strategies are defined to lack).
    if expected_interior is not None:
        if len(interior_hit) != expected_interior:
            sys.exit("keyed plan %s has %d interiors, expected %d"
                     % (csv_path, len(interior_hit), expected_interior))
        if expected_interior == EXPECTED_INTERIORS and set(interior_hit) != interior_set:
            sys.exit("keyed plan %s interior half != 92-interior skeleton" % csv_path)
    if expected_leaf is not None and len(leaf) != expected_leaf:
        sys.exit("keyed plan %s has %d leaves, expected %d"
                 % (csv_path, len(leaf), expected_leaf))
    return offs, sorted(interior_hit), leaf


def build_keyed_strategy_plans(page_size, page_count, interior_offsets, db_sha):
    """Read + validate every committed keyed seed plan for every strategy in
    KEYED_SPECS and return the generic keyed_strategy_plans[workload][seed][strategy]
    manifest block plus a nested per-seed meta map keyed_meta[strategy][seed] =
    {sha, pages, interior, leaf} (for the pin cross-check). Counts are the actual
    per-seed derived values, so strategies whose footprint varies per seed (2f_slru)
    are pinned as per-seed data rather than a universal invariant."""
    block = {CANONICAL_WORKLOAD_ID: {}}
    meta = {}
    for spec in KEYED_SPECS:
        strat = spec["strategy"]
        meta[strat] = {}
        for s in SEEDS:
            rel = spec["plan_rel"] % s
            ap = os.path.join(ROOT, rel)
            if not os.path.exists(ap):
                sys.exit("missing committed keyed %s plan: %s" % (strat, rel))
            offs, interior_offs, leaf_offs = read_keyed_plan(
                ap, page_size, page_count, interior_offsets,
                expected_pages=spec["expected_pages"],
                expected_leaf=spec["expected_leaf"],
                expected_interior=spec["expected_interior"])
            plan_sha = sha256_file(ap)
            pages, interior, leaf = len(offs), len(interior_offs), len(leaf_offs)
            meta[strat][s] = {"sha": plan_sha, "pages": pages,
                              "interior": interior, "leaf": leaf}
            nrel = spec["native_source_rel"](s)
            nap = os.path.join(ROOT, nrel)
            if not os.path.exists(nap):
                sys.exit("missing committed native source of record: %s" % nrel)
            block[CANONICAL_WORKLOAD_ID].setdefault(str(s), {})[strat] = {
                "path": rel,
                "sha256": plan_sha,
                "kind": spec["kind"],
                "expected_pages": pages,
                "expected_interior_pages": interior,
                "expected_leaf_pages": leaf,
                "offsets": offs,
                "interior_offsets": interior_offs,
                "leaf_offsets": leaf_offs,
                "bound_db_sha256": db_sha,
                "workload": CANONICAL_WORKLOAD_ID,
                "seed": s,
                "strategy": strat,
                "native_source": {"path": nrel, "sha256": sha256_file(nap)},
            }
    return block, meta


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
                   layers5_sha, layers5_offsets, keyed_meta):
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
    # keyed plans: for every keyed strategy, each seed's frozen delivery-plan sha +
    # per-seed counts are pinned explicitly, and the strategy must appear in
    # strategy_plans so the ws2 matrix validation gate (allowed_strategies =
    # pin.strategy_plans.keys()) widens. Counts are per-seed data (2f_slru varies by
    # seed), so the pin carries the exact per-seed values, not one universal count.
    pin_keyed = pin.get("keyed_strategy_plans", {}).get(CANONICAL_WORKLOAD_ID)
    if pin_keyed is None:
        sys.exit("pin mismatch: no keyed_strategy_plans for %s" % CANONICAL_WORKLOAD_ID)
    for spec in KEYED_SPECS:
        strat = spec["strategy"]
        if strat not in pin.get("strategy_plans", {}):
            sys.exit("pin mismatch: strategy_plans has no %s marker" % strat)
        for s in SEEDS:
            entry = pin_keyed.get(str(s), {}).get(strat)
            if entry is None:
                sys.exit("pin mismatch: no keyed %s plan for seed %d" % (strat, s))
            m = keyed_meta[strat][s]
            need(m["sha"], entry["sha256"], "keyed_%s_seed_%d" % (strat, s))
            need(m["pages"], entry["expected_pages"],
                 "keyed_%s_seed_%d_pages" % (strat, s))
            need(m["interior"], entry["expected_interior_pages"],
                 "keyed_%s_seed_%d_interior" % (strat, s))
            need(m["leaf"], entry["expected_leaf_pages"],
                 "keyed_%s_seed_%d_leaf" % (strat, s))


def crosscheck_portability(port_meta, port_traces, port_plan, port_run_config_sha256):
    """Fail closed unless the frozen pin carries every portability entry, marker,
    trace, and the portability invocation-plan identity the live build produced.
    The pin was written from the SAME freeze report (tools/write_portability_pin.py
    via tools/portability_manifest.py), so this proves generation<->pin agreement."""
    pin_path = os.path.join(ROOT, PIN_REL)
    with open(pin_path) as f:
        pin = json.load(f)
    problems = PM.crosscheck(pin, port_meta, ROOT)
    # per-workload trace provenance must match the pin byte-for-byte
    pin_pt = pin.get("portability_workload_traces", {})
    for wl, block in port_traces.items():
        for seed_str, e in block["seeds"].items():
            pe = pin_pt.get(wl, {}).get("seeds", {}).get(seed_str)
            if pe is None:
                problems.append("pin missing portability trace %s/%s" % (wl, seed_str))
            elif pe.get("sha256") != e["sha256"]:
                problems.append("pin portability trace %s/%s sha mismatch" % (wl, seed_str))
    if pin.get("portability_run_config_sha256") != port_run_config_sha256:
        problems.append("pin portability_run_config_sha256 != generated")
    if problems:
        sys.exit("portability pin mismatch:\n  " + "\n  ".join(problems))


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

    db_sha = sha256_file(db)
    plan_sha = sha256_file(plan)
    classifier_sha = sha256_file(classify)

    # keyed per-seed plans for every keyed strategy (read + validate committed
    # frozen selections); keyed_meta carries per-seed sha + counts for the pin gate.
    keyed_block, keyed_meta = build_keyed_strategy_plans(
        page_size, page_count, offsets, db_sha)

    # keyed strategy_plans markers (one per keyed strategy) -- present so the ws2
    # matrix validation allowed set (pin.strategy_plans.keys()) widens; carry NO
    # inline offsets (excluded from the static-plan cache). Fixed-footprint
    # strategies record a single expected count; per-seed strategies record the
    # per-seed count maps.
    keyed_markers = {}
    for spec in KEYED_SPECS:
        strat = spec["strategy"]
        marker = {
            "path": None, "sha256": None, "kind": spec["marker_kind"],
            "keyed": True, "per_seed": True,
            "workload_dependent": True, "seed_dependent": True,
            "workload": CANONICAL_WORKLOAD_ID, "seeds": SEEDS,
            "keyed_plans_ref": "keyed_strategy_plans",
            "note": spec["marker_note"],
        }
        # interior footprint declaration: a fixed count for full-skeleton (92) and
        # leaf-only (0) strategies; per-seed data for emergent-split strategies
        # (2f_top102/learned_markov_102), which rank without page-type knowledge.
        if spec["expected_interior"] is not None:
            marker["expected_interior_pages"] = spec["expected_interior"]
        else:
            marker["per_seed_expected_interior_pages"] = {
                str(s): keyed_meta[strat][s]["interior"] for s in SEEDS}
        if spec["expected_pages"] is not None:
            marker["expected_pages"] = spec["expected_pages"]
            marker["expected_leaf_pages"] = spec["expected_leaf"]
        else:
            marker["per_seed_expected_pages"] = {
                str(s): keyed_meta[strat][s]["pages"] for s in SEEDS}
            marker["per_seed_expected_leaf_pages"] = {
                str(s): keyed_meta[strat][s]["leaf"] for s in SEEDS}
        keyed_markers[strat] = marker

    # ---- PORTABILITY layer (additive; workstation->OpenWhisk deployment
    # complement). Driven entirely by the verified freeze report via
    # tools/portability_manifest.py. Merges four NEW workloads (+ the two N=28
    # strategies on YC) into keyed plans / traces / oracle without disturbing the
    # canonical YC blocks. The primary/secondary run-config identities are
    # untouched (they live only in the pin's invocation plans). -------------- #
    port_live, _port_pin, port_meta = PM.build_portability_entries(
        ROOT, set(offsets), page_size, page_count)
    port_markers = PM.build_new_markers(port_meta)
    port_traces, port_oracle = PM.build_traces_and_oracle(
        ROOT, db, first_op_key, oracle, sha256_file)
    port_plan = PM.portability_invocation_plan(port_meta)
    port_run_config_sha256 = PM.portability_run_config_sha256(port_plan)

    for wl, seeds in port_live.items():
        wdst = keyed_block.setdefault(wl, {})
        for seed_str, strats in seeds.items():
            sdst = wdst.setdefault(seed_str, {})
            for strat, entry in strats.items():
                if strat in sdst:
                    sys.exit("portability keyed collision %s/%s/%s" % (strat, wl, seed_str))
                sdst[strat] = entry
    for strat, marker in port_markers.items():
        if strat in keyed_markers:
            sys.exit("portability marker collision %s" % strat)
        keyed_markers[strat] = marker
    for wl, block in port_traces.items():
        if wl in traces:
            sys.exit("portability trace collision %s" % wl)
        traces[wl] = block
    oracle_block = build_oracle(db)
    for wl, block in port_oracle.items():
        if wl in oracle_block:
            sys.exit("portability oracle collision %s" % wl)
        oracle_block[wl] = block

    # Byte-tie the live manifest to the frozen replay pin (fail closed).
    crosscheck_pin(db_sha, plan_sha, classifier_sha,
                   {s: seedmap[s]["sha256"] for s in seedmap},
                   layers5_sha, layers5_offsets, keyed_meta)
    crosscheck_portability(port_meta, port_traces, port_plan, port_run_config_sha256)

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
            # Keyed per-(workload,seed) strategy markers (2e_K10, 2f_slru) are
            # merged in below via keyed_markers -- each carries NO inline offsets
            # (excluded from the static-plan cache); the per-seed plans live in
            # keyed_strategy_plans. Present so they are members of
            # strategy_plans.keys() -- the ws2 matrix validation allowed set.
        },
        "keyed_strategy_plans": keyed_block,
        "workload_traces": traces,
        "supported_first_operation_ids": SUPPORTED_FIRST_OPS,
        "first_query_oracle": oracle_block,
        "workload_set": list(PM.WORKLOAD_SET),
        "portability_invocation_plan": port_plan,
        "portability_run_config_sha256": port_run_config_sha256,
        "notes": ("Interior skeleton (2d) plan derived from the canonical page "
                  "classifier; invariants validated at generation. Paths are "
                  "repository-relative, resolved at runtime against "
                  "OW_ARTIFACT_ROOT. expected_relevant_page_count is the whole-DB "
                  "page count; interior_page_count is the 92-page skeleton."),
    }

    manifest["strategy_plans"].update(keyed_markers)

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
