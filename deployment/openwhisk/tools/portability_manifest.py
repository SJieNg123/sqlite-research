#!/usr/bin/env python3
"""Single source of truth for the workstation -> OpenWhisk PORTABILITY layer.

This module is imported by both:

  * ``build_artifact_manifest.py`` -- to MERGE the portability blocks (keyed
    plans with inline offsets, per-workload traces + first-query oracle, the two
    N=28 strategy markers, ``workload_set``, ``portability_invocation_plan``)
    additively into the live ``config/artifacts.json``; and
  * ``tools/write_portability_pin.py`` -- to emit the matching (offset-free)
    entries into the frozen replay pin ``config/artifacts.native_ycsb.json``.

Deriving both from the same functions guarantees the pin and the generated live
manifest agree byte-for-byte on every sha / count, which the builder's extended
``crosscheck`` re-proves at generation time (fail closed).

The ONLY input is the verified freeze report
``config/plans/keyed/portability_freeze_report.json`` (36 plans, produced by
``tools/freeze_portability_plans.py`` and SHA-bound to the frozen ``test.db`` +
classifier). Portability plans "come only from the verified freeze report" -- no
strategy selection or residency measurement happens here; every offset is read
back out of the already-frozen delivery-plan CSVs and re-classified against the
92-interior skeleton for the inline split, then the counts are asserted to equal
the freeze report's recorded values.

Nothing here touches the primary/secondary YC identities (022fbeb0.../441609e6...)
or their invocation plans; the portability identity is independent.
"""
import csv
import hashlib
import json
import os

# ---------------------------------------------------------------- frozen config
# All five portability workload IDs (canonical, registry-idempotent). Sorted so
# the portability_invocation_plan identity is order-stable.
WORKLOAD_SET = [
    "native_ycsb_c_hot_hashed_01",
    "native_ycsb_c_read_uniform",
    "native_ycsb_c_read_zipf",
    "read_tail_hit_20k",
    "read_tail_mixed_20k",
]

# YC is already carried in the canonical manifest blocks (traces + oracle);
# these four are the NEW workloads the portability layer introduces.
NEW_WORKLOADS = [
    "native_ycsb_c_hot_hashed_01",
    "native_ycsb_c_read_uniform",
    "read_tail_hit_20k",
    "read_tail_mixed_20k",
]

PORTABILITY_SEEDS = [1, 2, 3]

TRACE_TEMPLATES = {
    "native_ycsb_c_read_zipf":    "workloads_refined/traces/seeds/workload_YC_%d.txt",
    "native_ycsb_c_read_uniform": "workloads_refined/traces/seeds/workload_YCu_%d.txt",
    "native_ycsb_c_hot_hashed_01": "workloads_refined/traces/seeds/workload_YCh01_%d.txt",
    "read_tail_mixed_20k":        "workloads/workload_c_%d.txt",
    "read_tail_hit_20k":          "workloads/workload_c_hit_%d.txt",
}

# The four rectangular sub-matrices. Each is a strict Cartesian product for the
# schedule validator (client/validate_schedule.py). Targets = strategies minus
# baseline. Pairs = |W|*|S|*|F|*|M|*|R|*|T|.
SCHEDULE_SEED = 20260826
HANDLE_MODES = ["warm", "standalone"]
REPETITIONS = 3
FIRST_OPERATION_IDS = [0]

MATRICES = [
    {"name": "M1",
     "workloads": ["native_ycsb_c_read_uniform", "native_ycsb_c_hot_hashed_01",
                   "read_tail_hit_20k"],
     "strategies": ["baseline", "2e_K10", "2f_slru"],
     "seeds": [1, 2, 3]},
    {"name": "M2",
     "workloads": ["read_tail_mixed_20k"],
     "strategies": ["baseline", "2e_K10", "2f_slru",
                    "leaf_freq_K10", "leaf_rand_K10"],
     "seeds": [1, 2, 3]},
    {"name": "M3",
     "workloads": ["native_ycsb_c_read_zipf"],
     "strategies": ["baseline", "2f_top28", "learned_markov_28"],
     "seeds": [1, 2, 3]},
    {"name": "M4",
     "workloads": ["native_ycsb_c_read_uniform", "native_ycsb_c_hot_hashed_01",
                   "read_tail_mixed_20k"],
     "strategies": ["baseline", "2d"],
     "seeds": [1]},
]

EXPECTED_TOTAL_PAIRS = 234
EXPECTED_TOTAL_INVOCATIONS = 468

# Per-seed delivery-plan entry kind, by the freeze report's `kind` + strategy.
_ENTRY_KIND = {
    "2e_K10": "hot2e_interior_union_leaf",
    "2f_slru": "slru_resident_working_set",
    "2f_top28": "freqdump_ranked_partial",
    "learned_markov_28": "learned_markov_partial",
    "leaf_freq_K10": "leaf_only_frequency",
    "leaf_rand_K10": "leaf_only_random",
}

# New strategy_plans markers (admissibility flags for ws2 05 allowed_strategies).
# Only the two N=28 strategies are new; the rest already have markers.
_NEW_MARKER_KIND = {
    "2f_top28": "freqdump_keyed_per_seed",
    "learned_markov_28": "learned_markov_keyed_per_seed",
}
_NEW_MARKER_NOTE = {
    "2f_top28": ("2f_top28 = the top-28 resident pages by root->leaf traversal "
                 "frequency (total budget-matched to the learned model). Ranks with "
                 "NO page-type knowledge, so the interior/leaf split is EMERGENT "
                 "(observed 26/2 across seeds 1-3), recorded per seed but NOT "
                 "enforced. Portability layer only (workstation->OpenWhisk "
                 "deployment complement); per-seed frozen plans in "
                 "keyed_strategy_plans[native_ycsb_c_read_zipf][<seed>][2f_top28]."),
    "learned_markov_28": ("learned_markov_28 = the top-28 pages of a first-order "
                          "Markov transition model trained leave-one-seed-out (train "
                          "on the other 9 seeds, test on the held-out seed; the test "
                          "seed is never in the training set). Emergent 26/2 "
                          "interior/leaf split recorded per seed, NOT enforced. "
                          "Portability layer only; per-seed frozen plans in "
                          "keyed_strategy_plans[native_ycsb_c_read_zipf][<seed>]"
                          "[learned_markov_28]."),
}

FREEZE_REPORT_REL = "deployment/openwhisk/config/plans/keyed/portability_freeze_report.json"
BOUND_DB_SHA256 = "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1"


# ---------------------------------------------------------------------- helpers
def load_freeze_report(root):
    fp = os.path.join(root, FREEZE_REPORT_REL)
    if not os.path.exists(fp):
        raise SystemExit("missing portability freeze report: %s" % FREEZE_REPORT_REL)
    with open(fp) as f:
        rep = json.load(f)
    if rep.get("bound_db_sha256") != BOUND_DB_SHA256:
        raise SystemExit("freeze report bound_db_sha256 != frozen test.db")
    plans = rep["plans"]
    if len(plans) != 36:
        raise SystemExit("freeze report must have exactly 36 plans, got %d" % len(plans))
    return rep


def _read_plan_offsets(root, plan_rel, page_size):
    """Read a frozen `page_number,file_offset` delivery plan into an offset list
    (order preserved: sorted-by-page as frozen), asserting the page formula."""
    ap = os.path.join(root, plan_rel)
    offs = []
    with open(ap, newline="") as f:
        for row in csv.DictReader(f):
            pn = int(row["page_number"]); fo = int(row["file_offset"])
            if fo != (pn - 1) * page_size:
                raise SystemExit("%s: offset != (page-1)*page_size" % plan_rel)
            offs.append(fo)
    return offs


def _sha256_file(root, rel):
    h = hashlib.sha256()
    with open(os.path.join(root, rel), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_portability_entries(root, interior_offset_set, page_size, page_count):
    """Return (live_block, pin_block, meta) where:

      live_block[workload][seed_str][strategy] = full entry WITH inline offsets
      pin_block[workload][seed_str][strategy]  = same entry WITHOUT offsets
      meta[(workload,strategy,seed)]           = {sha,pages,interior,leaf}

    Every count is read back from the frozen plan CSV, re-classified against the
    92-interior skeleton, and asserted equal to the freeze report's recorded
    values (fail closed on any drift)."""
    rep = load_freeze_report(root)
    live = {}
    pin = {}
    meta = {}
    for p in rep["plans"]:
        wl = p["workload_id"]; strat = p["strategy"]; seed = int(p["seed"])
        plan_rel = p["plan_path"]
        plan_sha = p["plan_sha256"]
        if _sha256_file(root, plan_rel) != plan_sha:
            raise SystemExit("%s plan sha256 != freeze report" % plan_rel)
        offs = _read_plan_offsets(root, plan_rel, page_size)
        interior_offs = [o for o in offs if o in interior_offset_set]
        leaf_offs = [o for o in offs if o not in interior_offset_set]
        # aligned + within the DB
        for o in offs:
            if o % page_size != 0 or not (0 <= o < page_count * page_size):
                raise SystemExit("%s offset %d misaligned/out-of-range" % (plan_rel, o))
        # counts must equal the freeze report exactly
        if len(offs) != p["pages"]:
            raise SystemExit("%s pages %d != freeze %d" % (plan_rel, len(offs), p["pages"]))
        if len(interior_offs) != p["interior"]:
            raise SystemExit("%s interior %d != freeze %d"
                             % (plan_rel, len(interior_offs), p["interior"]))
        if len(leaf_offs) != p["leaf"]:
            raise SystemExit("%s leaf %d != freeze %d"
                             % (plan_rel, len(leaf_offs), p["leaf"]))
        if len(set(offs)) != len(offs):
            raise SystemExit("%s has duplicate offsets" % plan_rel)
        pin_entry = {
            "path": plan_rel,
            "sha256": plan_sha,
            "kind": _ENTRY_KIND[strat],
            "expected_pages": p["pages"],
            "expected_interior_pages": p["interior"],
            "expected_leaf_pages": p["leaf"],
            "workload": wl,
            "seed": seed,
            "strategy": strat,
            "bound_db_sha256": BOUND_DB_SHA256,
            "native_source": {
                "path": p["native_source_path"].replace(root.rstrip("/") + "/", ""),
                "sha256": p["native_source_sha256"],
            },
        }
        if p.get("loso") is not None:
            pin_entry["loso"] = p["loso"]
        live_entry = dict(pin_entry)
        live_entry["offsets"] = offs
        live_entry["interior_offsets"] = interior_offs
        live_entry["leaf_offsets"] = leaf_offs
        pin.setdefault(wl, {}).setdefault(str(seed), {})[strat] = pin_entry
        live.setdefault(wl, {}).setdefault(str(seed), {})[strat] = live_entry
        meta[(wl, strat, seed)] = {"sha": plan_sha, "pages": p["pages"],
                                   "interior": p["interior"], "leaf": p["leaf"]}
    return live, pin, meta


def build_new_markers(meta):
    """strategy_plans markers for the two NEW N=28 strategies (YC only).
    Emergent interior split -> per_seed_expected_interior_pages, recorded not
    enforced (mirrors 2f_top102/learned_markov_102)."""
    markers = {}
    for strat in ("2f_top28", "learned_markov_28"):
        per_seed_int = {str(s): meta[("native_ycsb_c_read_zipf", strat, s)]["interior"]
                        for s in PORTABILITY_SEEDS}
        pages = {meta[("native_ycsb_c_read_zipf", strat, s)]["pages"]
                 for s in PORTABILITY_SEEDS}
        if pages != {28}:
            raise SystemExit("%s expected 28 pages every seed, got %s" % (strat, pages))
        markers[strat] = {
            "path": None, "sha256": None, "kind": _NEW_MARKER_KIND[strat],
            "keyed": True, "per_seed": True,
            "workload_dependent": True, "seed_dependent": True,
            "per_seed_expected_interior_pages": per_seed_int,
            "expected_pages": 28,
            "expected_leaf_pages": None,
            "workload": "native_ycsb_c_read_zipf",
            "seeds": list(PORTABILITY_SEEDS),
            "bound_db_sha256": BOUND_DB_SHA256,
            "keyed_plans_ref": "keyed_strategy_plans",
            "note": _NEW_MARKER_NOTE[strat],
        }
    return markers


def build_traces_and_oracle(root, db_path, first_op_key, oracle_mod, sha256_file):
    """Per-workload workload_traces + first_query_oracle for the four NEW
    workloads (seeds 1-3, first op 0). YC already lives in the canonical blocks.
    `first_op_key`, `oracle_mod`, `sha256_file` are injected from the builder so
    this module needs no sqlite import of its own."""
    import sqlite3
    traces = {}
    oracle_out = {}
    conn = sqlite3.connect(db_path)
    try:
        for wl in NEW_WORKLOADS:
            tmpl = TRACE_TEMPLATES[wl]
            seedmap = {}
            oracle_out[wl] = {}
            for s in PORTABILITY_SEEDS:
                rel = tmpl % s
                ap = os.path.join(root, rel)
                if not os.path.exists(ap):
                    raise SystemExit("missing portability trace: %s" % rel)
                seedmap[str(s)] = {"path": rel, "sha256": sha256_file(ap)}
                oracle_out[wl][str(s)] = {}
                for fop in FIRST_OPERATION_IDS:
                    key = first_op_key(ap, fop)
                    hit_raw, payload = oracle_mod.run_read_payload(conn, key)
                    hit, digest = oracle_mod.digest_payload(hit_raw, payload)
                    oracle_out[wl][str(s)][str(fop)] = {
                        "key": key, "expected_hit": hit, "expected_digest": digest}
            traces[wl] = {"seeds": seedmap}
    finally:
        conn.close()
    return traces, oracle_out


def portability_invocation_plan(meta):
    """The independent portability run-config identity source. A pure literal
    structure (no offsets/shas) recomputed identically on WK1 and WK2."""
    strat_union = sorted({s for mx in MATRICES for s in mx["strategies"]})
    total_pairs = 0
    matrices = []
    for mx in MATRICES:
        W = len(mx["workloads"]); S = len(mx["seeds"])
        T = len([s for s in mx["strategies"] if s != "baseline"])
        pairs = W * S * len(FIRST_OPERATION_IDS) * len(HANDLE_MODES) * REPETITIONS * T
        total_pairs += pairs
        matrices.append({
            "name": mx["name"],
            "workloads": list(mx["workloads"]),
            "strategies": list(mx["strategies"]),
            "seeds": list(mx["seeds"]),
            "pairs": pairs,
        })
    if total_pairs != EXPECTED_TOTAL_PAIRS:
        raise SystemExit("portability pairs %d != %d" % (total_pairs, EXPECTED_TOTAL_PAIRS))
    return {
        "kind": "portability_matrix",
        "workload_set": list(WORKLOAD_SET),
        "strategies": strat_union,
        "seeds": list(PORTABILITY_SEEDS),
        "handle_modes": list(HANDLE_MODES),
        "first_operation_ids": list(FIRST_OPERATION_IDS),
        "repetitions": REPETITIONS,
        "schedule_seed": SCHEDULE_SEED,
        "concurrency": 1,
        "sequential": True,
        "matrices": matrices,
        "total_pairs": total_pairs,
        "total_invocations": 2 * total_pairs,
    }


def portability_run_config_sha256(plan):
    blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def crosscheck(pin, live_meta, root):
    """Fail closed unless the frozen pin carries every portability entry the live
    build produced, agreeing on sha + counts, plus workload_set, the two new
    markers, portability_invocation_plan and its recomputed identity."""
    problems = []

    def bad(m):
        problems.append(m)

    if pin.get("workload_set") != WORKLOAD_SET:
        bad("pin workload_set != frozen set")
    pk = pin.get("keyed_strategy_plans", {})
    for (wl, strat, seed), m in sorted(live_meta.items()):
        e = pk.get(wl, {}).get(str(seed), {}).get(strat)
        if e is None:
            bad("pin missing keyed %s/%s/%d" % (strat, wl, seed)); continue
        if e.get("sha256") != m["sha"]:
            bad("pin %s/%s/%d sha mismatch" % (strat, wl, seed))
        if e.get("expected_pages") != m["pages"]:
            bad("pin %s/%s/%d pages mismatch" % (strat, wl, seed))
        if e.get("expected_interior_pages") != m["interior"]:
            bad("pin %s/%s/%d interior mismatch" % (strat, wl, seed))
        if e.get("expected_leaf_pages") != m["leaf"]:
            bad("pin %s/%s/%d leaf mismatch" % (strat, wl, seed))
    sp = pin.get("strategy_plans", {})
    for strat in ("2f_top28", "learned_markov_28"):
        if strat not in sp:
            bad("pin strategy_plans missing %s marker" % strat)
    ip = pin.get("portability_invocation_plan")
    if ip is None:
        bad("pin missing portability_invocation_plan")
    else:
        want = portability_invocation_plan(
            {k: {"interior": v["interior"], "pages": v["pages"]}
             for k, v in live_meta.items()})
        if json.dumps(ip, sort_keys=True) != json.dumps(want, sort_keys=True):
            bad("pin portability_invocation_plan != recomputed")
        want_sha = portability_run_config_sha256(want)
        if pin.get("portability_run_config_sha256") != want_sha:
            bad("pin portability_run_config_sha256 != recomputed")
    return problems
