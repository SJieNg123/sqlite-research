#!/usr/bin/env python3
"""Single source of truth for the workstation -> OpenWhisk PORTABILITY-EXTENSION.

Additive sibling of ``portability_manifest.py``. Where that module carries the 36
frozen portability plans (run_config ``64f44c3e..``, 234/468), this one carries the
63 EXT keyed plans + 8 static cells that cover the remaining 29 (workload, strategy)
cells the workstation ran. It is imported by both:

  * ``build_artifact_manifest.py`` -- to MERGE the ext keyed plans + the three NEW
    strategy markers (``2f_top14``, ``learned_markov_14``, ``layers_92``) + the
    ext invocation plan additively into the live ``config/artifacts.json``; and
  * ``tools/write_portability_ext_pin.py`` -- to emit the matching (offset-free)
    keyed entries + markers into the frozen replay pin.

Design mirrors the primary->secondary YC pattern already in the repo: an INDEPENDENT
campaign identity (its own ``SCHEDULE_SEED_EXT`` + ``portability_ext_run_config_sha256``)
sharing the same image/DB/classifier. The 36-plan portability freeze / manifest / pin /
matrix are BYTE-UNTOUCHED; every count here is asserted against the ext freeze report
(63 plans) and re-derived from the frozen plan CSVs at generation.

Reuse note: ``2e_K500`` / ``2f_top28`` / ``learned_markov_28`` are already admissible
strategy NAMES (base KEYED_SPECS + the portability markers). session.py validates each
keyed plan per-ENTRY (never against the marker's declared workload), so running those
names on new workloads (YCu/YCh01/C_hit/C) needs only the per-entry keyed plans -- NOT
new markers. Only ``2f_top14`` / ``learned_markov_14`` (N=14, brand new) and the static
``layers_92`` get new markers.

No strategy selection or residency measurement happens here; the ext freeze report is
the only input.
"""
import csv
import hashlib
import json
import os

import portability_manifest as PM  # sibling; reused for WORKLOAD_SET + file helpers

# ----------------------------------------------------------------- frozen config
WORKLOAD_SET = PM.WORKLOAD_SET          # same closed universe (5 ids)
PORTABILITY_EXT_SEEDS = [1, 2, 3]
HANDLE_MODES = PM.HANDLE_MODES          # ["warm","standalone"]
REPETITIONS = PM.REPETITIONS            # 3
FIRST_OPERATION_IDS = PM.FIRST_OPERATION_IDS  # [0]
# Independent campaign identity: a new schedule seed (off the round marks), distinct
# from the portability 20260826.
SCHEDULE_SEED_EXT = 20260828

# workload ids (readability aliases)
YC = "native_ycsb_c_read_zipf"
YCU = "native_ycsb_c_read_uniform"
YCH01 = "native_ycsb_c_hot_hashed_01"
CHIT = "read_tail_hit_20k"
CMIX = "read_tail_mixed_20k"

# The seven rectangular sub-matrices (strict Cartesian products; the schedule
# validator expands each). Targets = strategies minus baseline; every block anchors
# on the paired baseline A-arm. Keyed blocks run seeds 1-3; static blocks run seed 1.
# Pairs = |W|*|S|*|F|*|M|*|R|*|T|  (F=1, M=2, R=3).
MATRICES_EXT = [
    {"name": "B5", "workloads": [YC],
     "strategies": ["baseline", "2f_top14", "learned_markov_14"],
     "seeds": [1, 2, 3]},                                              # 1*3*1*2*3*2 = 36
    {"name": "B6", "workloads": [YCU, YCH01],
     "strategies": ["baseline", "2e_K500", "2f_top28", "2f_top14",
                    "learned_markov_28", "learned_markov_14"],
     "seeds": [1, 2, 3]},                                              # 2*3*1*2*3*5 = 180
    {"name": "B7", "workloads": [CHIT],
     "strategies": ["baseline", "2e_K500", "2f_top28", "learned_markov_28",
                    "2f_top14", "learned_markov_14"],
     "seeds": [1, 2, 3]},                                              # 1*3*1*2*3*5 = 90
    {"name": "B8", "workloads": [CMIX],
     "strategies": ["baseline", "2f_top14", "2f_top28", "2e_K500",
                    "learned_markov_28"],
     "seeds": [1, 2, 3]},                                              # 1*3*1*2*3*4 = 72
    {"name": "B9", "workloads": [YC, YCU, YCH01, CHIT],
     "strategies": ["baseline", "layers_92"],
     "seeds": [1]},                                                    # 4*1*1*2*3*1 = 24
    {"name": "B10", "workloads": [YCU, YCH01, CMIX],
     "strategies": ["baseline", "layers_5"],
     "seeds": [1]},                                                    # 3*1*1*2*3*1 = 18
    {"name": "B11", "workloads": [CHIT],
     "strategies": ["baseline", "2d"],
     "seeds": [1]},                                                    # 1*1*1*2*3*1 = 6
]

EXPECTED_EXT_PAIRS = 426
EXPECTED_EXT_INVOCATIONS = 852

# Per-seed delivery-plan entry kind, by strategy. 2e_K500 carries the 92-skeleton
# UNION top-<=500 leaves (interior half == skeleton, set-equality gated); the 2f/
# learned strategies rank without page-type knowledge (emergent interior/leaf split,
# recorded not enforced).
_ENTRY_KIND_EXT = {
    "2f_top14": "freqdump_ranked_partial",
    "2f_top28": "freqdump_ranked_partial",
    "2e_K500": "hot2e_interior_union_leaf",
    "learned_markov_14": "learned_markov_partial",
    "learned_markov_28": "learned_markov_partial",
}

# Strategies that need a NEW strategy_plans marker (the rest are already admissible).
_NEW_KEYED_MARKER_KIND = {
    "2f_top14": "freqdump_keyed_per_seed",
    "learned_markov_14": "learned_markov_keyed_per_seed",
}
_NEW_KEYED_MARKER_NOTE = {
    "2f_top14": ("2f_top14 = the top-14 resident pages by root->leaf traversal "
                 "frequency (budget sibling of 2f_top28; half the page budget). Ranks "
                 "with NO page-type knowledge, so the interior/leaf split is EMERGENT, "
                 "recorded per (workload,seed) but NOT enforced. Portability-ext layer; "
                 "per-seed frozen plans in keyed_strategy_plans[<workload>][<seed>]"
                 "[2f_top14]."),
    "learned_markov_14": ("learned_markov_14 = the top-14 pages of a first-order Markov "
                          "transition model trained leave-one-seed-out (train on the "
                          "other 9 seeds, test on the held-out seed; the test seed is "
                          "never in the training set). Budget sibling of "
                          "learned_markov_28. Emergent interior/leaf split recorded per "
                          "(workload,seed), NOT enforced. Portability-ext layer; per-seed "
                          "frozen plans in keyed_strategy_plans[<workload>][<seed>]"
                          "[learned_markov_14]."),
}

FREEZE_REPORT_EXT_REL = ("deployment/openwhisk/config/plans/keyed/"
                         "portability_ext_freeze_report.json")
BOUND_DB_SHA256 = PM.BOUND_DB_SHA256
LAYERS92_PLAN_REL = "deployment/openwhisk/config/plans/interior_pages.csv"
EXPECTED_INTERIORS = 92


# ----------------------------------------------------------------------- helpers
def load_ext_freeze_report(root):
    fp = os.path.join(root, FREEZE_REPORT_EXT_REL)
    if not os.path.exists(fp):
        raise SystemExit("missing portability-ext freeze report: %s" % FREEZE_REPORT_EXT_REL)
    with open(fp) as f:
        rep = json.load(f)
    if rep.get("bound_db_sha256") != BOUND_DB_SHA256:
        raise SystemExit("ext freeze report bound_db_sha256 != frozen test.db")
    plans = rep["plans"]
    if len(plans) != 63:
        raise SystemExit("ext freeze report must have exactly 63 plans, got %d" % len(plans))
    return rep


def build_portability_ext_entries(root, interior_offset_set, page_size, page_count):
    """Return (live_block, pin_block, meta), reading every ext keyed plan back from
    its frozen CSV, re-classifying against the 92-interior skeleton, and asserting
    the counts equal the ext freeze report (fail closed on drift). Structure mirrors
    ``portability_manifest.build_portability_entries``."""
    rep = load_ext_freeze_report(root)
    live, pin, meta = {}, {}, {}
    for p in rep["plans"]:
        wl = p["workload_id"]; strat = p["strategy"]; seed = int(p["seed"])
        plan_rel = p["plan_path"]; plan_sha = p["plan_sha256"]
        if PM._sha256_file(root, plan_rel) != plan_sha:
            raise SystemExit("%s plan sha256 != ext freeze report" % plan_rel)
        offs = PM._read_plan_offsets(root, plan_rel, page_size)
        interior_offs = [o for o in offs if o in interior_offset_set]
        leaf_offs = [o for o in offs if o not in interior_offset_set]
        for o in offs:
            if o % page_size != 0 or not (0 <= o < page_count * page_size):
                raise SystemExit("%s offset %d misaligned/out-of-range" % (plan_rel, o))
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
        # 2e_K500 must carry the FULL 92-interior skeleton (set-equality), matching
        # session.py's eip==92 gate; the ranked/learned strategies do not.
        if strat == "2e_K500":
            if len(interior_offs) != EXPECTED_INTERIORS or set(interior_offs) != set(interior_offset_set):
                raise SystemExit("%s 2e_K500 interior half != 92-skeleton" % plan_rel)
        pin_entry = {
            "path": plan_rel,
            "sha256": plan_sha,
            "kind": _ENTRY_KIND_EXT[strat],
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


def build_ext_markers(meta, interior_offsets, layers92_plan_sha):
    """The three NEW strategy_plans markers.

    2f_top14 / learned_markov_14 -- keyed, N=14, emergent interior/leaf split recorded
    per (workload,seed) but NOT enforced (session validates the per-entry counts).
    layers_92 -- STATIC inline-offset plan == the full 92-interior skeleton
    (interior_pages.csv); distinct NAME from 2d (a different selection rule that
    resolves to the same 92 pages), needed so the effectiveness comparison keys on it.
    ``interior_offsets`` is the already-validated 92-offset list; ``layers92_plan_sha``
    the interior_pages.csv sha."""
    markers = {}
    for strat in ("2f_top14", "learned_markov_14"):
        cells = sorted({(wl, seed) for (wl, st, seed) in meta if st == strat})
        pages = {meta[(wl, strat, seed)]["pages"] for (wl, seed) in cells}
        if pages != {14}:
            raise SystemExit("%s expected 14 pages every cell, got %s" % (strat, pages))
        per = {}
        for (wl, seed) in cells:
            per.setdefault(wl, {})[str(seed)] = meta[(wl, strat, seed)]["interior"]
        markers[strat] = {
            "path": None, "sha256": None, "kind": _NEW_KEYED_MARKER_KIND[strat],
            "keyed": True, "per_seed": True,
            "workload_dependent": True, "seed_dependent": True,
            "expected_pages": 14,
            "expected_leaf_pages": None,
            "per_workload_seed_expected_interior_pages": per,
            "workloads": sorted({wl for wl, _ in cells}),
            "seeds": list(PORTABILITY_EXT_SEEDS),
            "bound_db_sha256": BOUND_DB_SHA256,
            "keyed_plans_ref": "keyed_strategy_plans",
            "note": _NEW_KEYED_MARKER_NOTE[strat],
        }
    # layers_92 static marker (inline offsets == full 92-skeleton)
    if len(interior_offsets) != EXPECTED_INTERIORS:
        raise SystemExit("layers_92 needs the full 92-interior skeleton, got %d"
                         % len(interior_offsets))
    markers["layers_92"] = {
        "path": LAYERS92_PLAN_REL, "sha256": layers92_plan_sha,
        "kind": "interior_full", "expected_pages": EXPECTED_INTERIORS,
        "expected_interior_pages": EXPECTED_INTERIORS, "expected_leaf_pages": 0,
        "offsets": list(interior_offsets),
        "note": ("all 92 interior pages -- the full interior skeleton by the layers "
                 "selection rule (first 92 interiors by native order == every "
                 "interior). Same page set as 2d, distinct strategy name so the "
                 "effectiveness comparison keys on the workstation's layers_92 cell. "
                 "Transitively pinned via the classifier sha in the native-YCSB pin."),
    }
    return markers


def portability_ext_invocation_plan():
    """The independent ext run-config identity source. Pure-literal structure from
    MATRICES_EXT (no offsets/shas), recomputed identically on WK1 and WK2."""
    strat_union = sorted({s for mx in MATRICES_EXT for s in mx["strategies"]})
    total_pairs = 0
    matrices = []
    for mx in MATRICES_EXT:
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
    if total_pairs != EXPECTED_EXT_PAIRS:
        raise SystemExit("ext pairs %d != %d" % (total_pairs, EXPECTED_EXT_PAIRS))
    return {
        "kind": "portability_ext_matrix",
        "workload_set": list(WORKLOAD_SET),
        "strategies": strat_union,
        "seeds": list(PORTABILITY_EXT_SEEDS),
        "handle_modes": list(HANDLE_MODES),
        "first_operation_ids": list(FIRST_OPERATION_IDS),
        "repetitions": REPETITIONS,
        "schedule_seed": SCHEDULE_SEED_EXT,
        "concurrency": 1,
        "sequential": True,
        "matrices": matrices,
        "total_pairs": total_pairs,
        "total_invocations": 2 * total_pairs,
    }


def portability_ext_run_config_sha256(plan):
    blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _keyed_matrix_cells():
    """Every (workload, strategy, seed) the ext matrix requires a frozen keyed plan
    for (i.e. targets whose kind is in _ENTRY_KIND_EXT). Static targets excluded."""
    cells = set()
    for mx in MATRICES_EXT:
        for strat in mx["strategies"]:
            if strat in _ENTRY_KIND_EXT:
                for wl in mx["workloads"]:
                    for s in mx["seeds"]:
                        cells.add((wl, strat, s))
    return cells


def crosscheck_ext(pin, live_meta, root):
    """Fail closed unless the frozen pin carries every ext keyed entry the live build
    produced (sha + counts), the three new markers, and the ext invocation-plan
    identity; and unless every keyed cell the matrix schedules has a frozen plan."""
    problems = []

    def bad(m):
        problems.append(m)

    # every scheduled keyed cell must have a frozen plan (schedule <-> freeze tie)
    have = set(live_meta.keys())
    for cell in sorted(_keyed_matrix_cells()):
        if cell not in have:
            bad("ext matrix cell %s has no frozen keyed plan" % (cell,))

    pk = pin.get("keyed_strategy_plans", {})
    for (wl, strat, seed), m in sorted(live_meta.items()):
        e = pk.get(wl, {}).get(str(seed), {}).get(strat)
        if e is None:
            bad("pin missing ext keyed %s/%s/%d" % (strat, wl, seed)); continue
        if e.get("sha256") != m["sha"]:
            bad("pin ext %s/%s/%d sha mismatch" % (strat, wl, seed))
        if e.get("expected_pages") != m["pages"]:
            bad("pin ext %s/%s/%d pages mismatch" % (strat, wl, seed))
        if e.get("expected_interior_pages") != m["interior"]:
            bad("pin ext %s/%s/%d interior mismatch" % (strat, wl, seed))
        if e.get("expected_leaf_pages") != m["leaf"]:
            bad("pin ext %s/%s/%d leaf mismatch" % (strat, wl, seed))
    sp = pin.get("strategy_plans", {})
    for strat in ("2f_top14", "learned_markov_14", "layers_92"):
        if strat not in sp:
            bad("pin strategy_plans missing %s marker" % strat)
    ip = pin.get("portability_ext_invocation_plan")
    if ip is None:
        bad("pin missing portability_ext_invocation_plan")
    else:
        want = portability_ext_invocation_plan()
        if json.dumps(ip, sort_keys=True) != json.dumps(want, sort_keys=True):
            bad("pin portability_ext_invocation_plan != recomputed")
        want_sha = portability_ext_run_config_sha256(want)
        if pin.get("portability_ext_run_config_sha256") != want_sha:
            bad("pin portability_ext_run_config_sha256 != recomputed")
    return problems
