#!/usr/bin/env python3
"""Single source of truth for the workstation -> OpenWhisk PORTABILITY-FULL-CLOSURE.

FIFTH additive campaign; additive sibling of ``portability_ext_manifest.py``. Carries
the 37 closure keyed plans that cover the final 16 WS_ONLY cells of the frozen 65-cell
canonical portability matrix. Imported by both:

  * ``build_artifact_manifest.py`` -- MERGE the closure keyed plans + the four NEW
    strategy markers (``2e_K40``, ``2e_K92``, ``lp_sorted``, ``lp_shuf``) + the closure
    invocation plan additively into the live ``config/artifacts.json``; and
  * ``tools/write_portability_full_closure_pin.py`` -- emit the matching (offset-free)
    keyed entries + markers into the frozen replay pin.

Independent campaign identity (its own ``SCHEDULE_SEED_CLOSURE`` +
``portability_full_closure_run_config_sha256``), sharing the same image/DB/classifier.
The four prior campaigns (primary / secondary / portability / portability_ext) are
BYTE-UNTOUCHED; every count here is asserted against the closure freeze report (37
plans) and re-derived from the frozen plan CSVs at generation.

Markers: ``learned_markov_14`` and ``layers_92`` were already made admissible by the
portability_ext layer, so closure adds NO marker for them (session validates each keyed
plan per-ENTRY; the ws2 admit-set only needs the NAME present in strategy_plans). The
FOUR brand-new names ``2e_K40`` / ``2e_K92`` (hot2e keyed, interior==92 set-equality)
and ``lp_sorted`` / ``lp_shuf`` (libprefetch, delivery_method=pread_ordered) get markers.

lp is the ordered-delivery mechanism: the frozen keyed plan's offsets are stored IN
DELIVERY ORDER (lp_sorted = offset-ascending; lp_shuf = offset-sort then
Random(424242).shuffle). ``_read_plan_offsets`` preserves that order, and
``session._validate_keyed_plans`` round-trips it order-sensitively, so the plan_sha256
tie in ``build_portability_full_closure_entries`` proves order byte-for-byte.
"""
import hashlib
import json
import os

import portability_manifest as PM  # sibling; reused for WORKLOAD_SET + file helpers

# ----------------------------------------------------------------- frozen config
WORKLOAD_SET = PM.WORKLOAD_SET
CLOSURE_SEEDS = [1, 2, 3]
HANDLE_MODES = PM.HANDLE_MODES          # ["warm","standalone"]
REPETITIONS = PM.REPETITIONS            # 3
FIRST_OPERATION_IDS = PM.FIRST_OPERATION_IDS  # [0]
# Independent campaign identity: a new schedule seed, distinct from portability
# (20260826) and portability_ext (20260828); off the round marks.
SCHEDULE_SEED_CLOSURE = 20260829
LP_SHUF_SEED = 424242

# workload ids
YC = "native_ycsb_c_read_zipf"
YCU = "native_ycsb_c_read_uniform"
YCH01 = "native_ycsb_c_hot_hashed_01"
CHIT = "read_tail_hit_20k"
CMIX = "read_tail_mixed_20k"

# The six rectangular sub-matrices (strict Cartesian products). Targets = strategies
# minus baseline; every block anchors on the paired baseline A-arm. Keyed blocks run
# their frozen seeds; static/single-inst blocks run seed 1.
# Pairs = |W|*|S|*|F|*|M|*|R|*|T|  (F=1, M=2, R=3).
MATRICES_CLOSURE = [
    {"name": "B12", "workloads": [CMIX],
     "strategies": ["baseline", "2e_K40", "2e_K92"],
     "seeds": [1]},                                                   # 1*1*1*2*3*2 = 12
    {"name": "B13", "workloads": [CHIT],
     "strategies": ["baseline", "2e_K40", "2e_K92"],
     "seeds": [1, 2, 3]},                                             # 1*3*1*2*3*2 = 36
    {"name": "B14", "workloads": [CMIX],
     "strategies": ["baseline", "learned_markov_14"],
     "seeds": [1, 2, 3]},                                             # 1*3*1*2*3*1 = 18
    {"name": "B15", "workloads": [CMIX],
     "strategies": ["baseline", "layers_92"],
     "seeds": [1]},                                                   # 1*1*1*2*3*1 = 6
    {"name": "B16", "workloads": [YC, YCU, YCH01, CHIT],
     "strategies": ["baseline", "lp_sorted", "lp_shuf"],
     "seeds": [1, 2, 3]},                                             # 4*3*1*2*3*2 = 144
    {"name": "B17", "workloads": [CMIX],
     "strategies": ["baseline", "lp_sorted", "lp_shuf"],
     "seeds": [1]},                                                   # 1*1*1*2*3*2 = 12
]

EXPECTED_CLOSURE_PAIRS = 228
EXPECTED_CLOSURE_INVOCATIONS = 456

# Per-seed delivery-plan entry kind, by strategy. 2e_K40/2e_K92 carry the 92-skeleton
# UNION top-<=K leaves (interior half == skeleton, set-equality gated, mirrors 2e_K500);
# learned_markov_14 ranks without page-type knowledge (emergent split); lp_sorted/lp_shuf
# are ordered pread deliveries of the corresponding 2f_slru resident set.
_ENTRY_KIND_CLOSURE = {
    "2e_K40": "hot2e_interior_union_leaf",
    "2e_K92": "hot2e_interior_union_leaf",
    "learned_markov_14": "learned_markov_partial",
    "lp_sorted": "lp_pread_ordered",
    "lp_shuf": "lp_pread_ordered",
}
# Strategies that carry the FULL 92-interior skeleton (session eip==92 set-equality gate).
_SKELETON_UNION_STRATS = ("2e_K40", "2e_K92")
_LP_STRATS = ("lp_sorted", "lp_shuf")

# Brand-new strategy markers this layer introduces (learned_markov_14 / layers_92 were
# already made admissible by the portability_ext layer).
_NEW_MARKER_KIND = {
    "2e_K40": "hot2e_keyed_per_seed",
    "2e_K92": "hot2e_keyed_per_seed",
    "lp_sorted": "lp_pread_ordered_keyed_per_seed",
    "lp_shuf": "lp_pread_ordered_keyed_per_seed",
}
_NEW_MARKER_NOTE = {
    "2e_K40": ("2e_K40 = resident 92-interior 2d skeleton UNION the native top-<=40 hot "
               "LEAF pages (budget sibling of 2e_K10/2e_K500). Interior half == the full "
               "92-skeleton (set-equality gated like 2e_K500); leaf count <= 40, emergent, "
               "recorded per (workload,seed). Full-closure layer; per-seed frozen plans in "
               "keyed_strategy_plans[<workload>][<seed>][2e_K40]."),
    "2e_K92": ("2e_K92 = resident 92-interior 2d skeleton UNION the native top-<=92 hot "
               "LEAF pages (budget sibling of 2e_K10/2e_K500). Interior half == the full "
               "92-skeleton (set-equality gated); leaf count <= 92, emergent, recorded per "
               "(workload,seed). Full-closure layer; per-seed frozen plans in "
               "keyed_strategy_plans[<workload>][<seed>][2e_K92]."),
    "lp_sorted": ("lp_sorted = libprefetch (lp) ordered delivery: the SAME page set as the "
                  "corresponding canonical 2f_slru resident working set, delivered by a "
                  "SYNCHRONOUS page-sized pread loop in file_offset-ASCENDING order "
                  "(delivery_method=pread_ordered, NOT async MADV_WILLNEED). The plan "
                  "offsets are stored IN DELIVERY ORDER; plan_sha256 is order-sensitive. "
                  "lp's primary quantity is deliver_us / e2e including delivery, NOT "
                  "first_query. Full-closure layer; per-seed ordered plans in "
                  "keyed_strategy_plans[<workload>][<seed>][lp_sorted]."),
    "lp_shuf": ("lp_shuf = libprefetch (lp) ordered delivery: the SAME 2f_slru page set as "
                "lp_sorted, delivered by a synchronous ordered pread loop in a "
                "SEED-SHUFFLED order (offset-sort first, then random.Random(424242)."
                "shuffle; shuffle_seed=424242). Identical unordered page set to lp_sorted, "
                "different ordered sequence -> different order-sensitive plan_sha256. lp's "
                "primary quantity is deliver_us / e2e, NOT first_query. Full-closure layer; "
                "per-seed ordered plans in keyed_strategy_plans[<workload>][<seed>]"
                "[lp_shuf]."),
}

FREEZE_REPORT_CLOSURE_REL = ("deployment/openwhisk/config/plans/keyed/"
                             "portability_full_closure_freeze_report.json")
BOUND_DB_SHA256 = PM.BOUND_DB_SHA256
EXPECTED_INTERIORS = 92


# ----------------------------------------------------------------------- helpers
def load_closure_freeze_report(root):
    fp = os.path.join(root, FREEZE_REPORT_CLOSURE_REL)
    if not os.path.exists(fp):
        raise SystemExit("missing full-closure freeze report: %s" % FREEZE_REPORT_CLOSURE_REL)
    with open(fp) as f:
        rep = json.load(f)
    if rep.get("bound_db_sha256") != BOUND_DB_SHA256:
        raise SystemExit("closure freeze report bound_db_sha256 != frozen test.db")
    plans = rep["plans"]
    if len(plans) != 37:
        raise SystemExit("closure freeze report must have exactly 37 plans, got %d" % len(plans))
    return rep


def build_portability_full_closure_entries(root, interior_offset_set, page_size, page_count):
    """Return (live_block, pin_block, meta), reading every closure keyed plan back from
    its frozen CSV, re-classifying against the 92-interior skeleton, and asserting the
    counts equal the closure freeze report (fail closed on drift). For lp strategies the
    plan_sha256 tie proves the ORDERED sequence byte-for-byte (order-sensitive)."""
    rep = load_closure_freeze_report(root)
    live, pin, meta = {}, {}, {}
    for p in rep["plans"]:
        wl = p["workload_id"]; strat = p["strategy"]; seed = int(p["seed"])
        plan_rel = p["plan_path"]; plan_sha = p["plan_sha256"]
        if strat not in _ENTRY_KIND_CLOSURE:
            raise SystemExit("%s: unexpected closure strategy %s" % (plan_rel, strat))
        if PM._sha256_file(root, plan_rel) != plan_sha:
            raise SystemExit("%s plan sha256 != closure freeze report (order-sensitive)" % plan_rel)
        offs = PM._read_plan_offsets(root, plan_rel, page_size)  # order preserved
        interior_offs = [o for o in offs if o in interior_offset_set]
        leaf_offs = [o for o in offs if o not in interior_offset_set]
        for o in offs:
            if o % page_size != 0 or not (0 <= o < page_count * page_size):
                raise SystemExit("%s offset %d misaligned/out-of-range" % (plan_rel, o))
        if len(offs) != p["pages"]:
            raise SystemExit("%s pages %d != freeze %d" % (plan_rel, len(offs), p["pages"]))
        if len(interior_offs) != p["interior"]:
            raise SystemExit("%s interior %d != freeze %d" % (plan_rel, len(interior_offs), p["interior"]))
        if len(leaf_offs) != p["leaf"]:
            raise SystemExit("%s leaf %d != freeze %d" % (plan_rel, len(leaf_offs), p["leaf"]))
        if len(set(offs)) != len(offs):
            raise SystemExit("%s has duplicate offsets" % plan_rel)
        # 2e_K40/2e_K92 must carry the FULL 92-interior skeleton (set-equality), matching
        # session.py's eip==92 gate.
        if strat in _SKELETON_UNION_STRATS:
            if len(interior_offs) != EXPECTED_INTERIORS or set(interior_offs) != set(interior_offset_set):
                raise SystemExit("%s %s interior half != 92-skeleton" % (plan_rel, strat))
        pin_entry = {
            "path": plan_rel,
            "sha256": plan_sha,
            "kind": _ENTRY_KIND_CLOSURE[strat],
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
        # lp entries carry the ordered-delivery provenance (order-sensitive identity).
        if strat in _LP_STRATS:
            lp = p.get("lp") or {}
            if p.get("delivery_order") is None:
                raise SystemExit("%s lp entry missing delivery_order" % plan_rel)
            pin_entry["delivery_method"] = "pread_ordered"
            pin_entry["delivery_order"] = p["delivery_order"]
            pin_entry["shuffle_seed"] = LP_SHUF_SEED if strat == "lp_shuf" else None
            pin_entry["selected_page_set_sha256"] = lp.get("selected_page_set_sha256")
        live_entry = dict(pin_entry)
        live_entry["offsets"] = offs                     # IN DELIVERY ORDER
        live_entry["interior_offsets"] = interior_offs
        live_entry["leaf_offsets"] = leaf_offs
        pin.setdefault(wl, {}).setdefault(str(seed), {})[strat] = pin_entry
        live.setdefault(wl, {}).setdefault(str(seed), {})[strat] = live_entry
        m = {"sha": plan_sha, "pages": p["pages"], "interior": p["interior"], "leaf": p["leaf"]}
        if strat in _LP_STRATS:
            m["delivery_order"] = p["delivery_order"]
        meta[(wl, strat, seed)] = m
    return live, pin, meta


def _per_ws_map(meta, strat, field):
    """{workload: {seed_str: meta_field}} for one strategy across its closure cells."""
    out = {}
    for (wl, st, seed), m in meta.items():
        if st == strat:
            out.setdefault(wl, {})[str(seed)] = m[field]
    return out


def build_closure_markers(meta):
    """The four NEW strategy_plans markers (2e_K40, 2e_K92, lp_sorted, lp_shuf). Each is
    keyed/per-seed with NO inline offsets (excluded from the static-plan cache); present
    so the ws2 matrix allowed-set (pin.strategy_plans.keys()) admits the name. session.py
    validates each per-(workload,seed) plan against ITS OWN expected counts, so these
    per-cell maps are provenance, not the validation authority."""
    markers = {}
    for strat in _NEW_MARKER_KIND:
        cells = sorted({(wl, seed) for (wl, st, seed) in meta if st == strat})
        if not cells:
            raise SystemExit("closure marker %s has no frozen cells" % strat)
        marker = {
            "path": None, "sha256": None, "kind": _NEW_MARKER_KIND[strat],
            "keyed": True, "per_seed": True,
            "workload_dependent": True, "seed_dependent": True,
            "workloads": sorted({wl for wl, _ in cells}),
            "seeds": sorted({seed for _, seed in cells}),
            "per_workload_seed_expected_pages": _per_ws_map(meta, strat, "pages"),
            "per_workload_seed_expected_interior_pages": _per_ws_map(meta, strat, "interior"),
            "per_workload_seed_expected_leaf_pages": _per_ws_map(meta, strat, "leaf"),
            "bound_db_sha256": BOUND_DB_SHA256,
            "keyed_plans_ref": "keyed_strategy_plans",
            "note": _NEW_MARKER_NOTE[strat],
        }
        if strat in _SKELETON_UNION_STRATS:
            # interior half is always the full 92-skeleton (session eip==92 gate).
            marker["expected_interior_pages"] = EXPECTED_INTERIORS
        if strat in _LP_STRATS:
            marker["delivery_method"] = "pread_ordered"
            marker["delivery_order"] = ("file_offset_ascending" if strat == "lp_sorted"
                                        else "seed_shuffled")
            if strat == "lp_shuf":
                marker["shuffle_seed"] = LP_SHUF_SEED
        markers[strat] = marker
    return markers


def portability_full_closure_invocation_plan():
    """The independent closure run-config identity source. Pure-literal structure from
    MATRICES_CLOSURE (no offsets/shas), recomputed identically on WK1 and WK2."""
    strat_union = sorted({s for mx in MATRICES_CLOSURE for s in mx["strategies"]})
    total_pairs = 0
    matrices = []
    for mx in MATRICES_CLOSURE:
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
    if total_pairs != EXPECTED_CLOSURE_PAIRS:
        raise SystemExit("closure pairs %d != %d" % (total_pairs, EXPECTED_CLOSURE_PAIRS))
    return {
        "kind": "portability_full_closure_matrix",
        "workload_set": list(WORKLOAD_SET),
        "strategies": strat_union,
        "seeds": list(CLOSURE_SEEDS),
        "handle_modes": list(HANDLE_MODES),
        "first_operation_ids": list(FIRST_OPERATION_IDS),
        "repetitions": REPETITIONS,
        "schedule_seed": SCHEDULE_SEED_CLOSURE,
        "concurrency": 1,
        "sequential": True,
        "matrices": matrices,
        "total_pairs": total_pairs,
        "total_invocations": 2 * total_pairs,
    }


def portability_full_closure_run_config_sha256(plan):
    blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _keyed_matrix_cells():
    """Every (workload, strategy, seed) the closure matrix needs a frozen keyed plan for
    (targets whose kind is in _ENTRY_KIND_CLOSURE). Static targets (layers_92) excluded."""
    cells = set()
    for mx in MATRICES_CLOSURE:
        for strat in mx["strategies"]:
            if strat in _ENTRY_KIND_CLOSURE:
                for wl in mx["workloads"]:
                    for s in mx["seeds"]:
                        cells.add((wl, strat, s))
    return cells


def crosscheck_closure(pin, live_meta, root):
    """Fail closed unless the frozen pin carries every closure keyed entry the live build
    produced (sha + counts + lp order), the four new markers, and the closure
    invocation-plan identity; and unless every keyed cell the matrix schedules has a
    frozen plan."""
    problems = []

    def bad(m):
        problems.append(m)

    have = set(live_meta.keys())
    for cell in sorted(_keyed_matrix_cells()):
        if cell not in have:
            bad("closure matrix cell %s has no frozen keyed plan" % (cell,))

    pk = pin.get("keyed_strategy_plans", {})
    for (wl, strat, seed), m in sorted(live_meta.items()):
        e = pk.get(wl, {}).get(str(seed), {}).get(strat)
        if e is None:
            bad("pin missing closure keyed %s/%s/%d" % (strat, wl, seed)); continue
        if e.get("sha256") != m["sha"]:
            bad("pin closure %s/%s/%d sha mismatch" % (strat, wl, seed))
        if e.get("expected_pages") != m["pages"]:
            bad("pin closure %s/%s/%d pages mismatch" % (strat, wl, seed))
        if e.get("expected_interior_pages") != m["interior"]:
            bad("pin closure %s/%s/%d interior mismatch" % (strat, wl, seed))
        if e.get("expected_leaf_pages") != m["leaf"]:
            bad("pin closure %s/%s/%d leaf mismatch" % (strat, wl, seed))
        if strat in _LP_STRATS:
            if e.get("delivery_method") != "pread_ordered":
                bad("pin closure %s/%s/%d delivery_method != pread_ordered" % (strat, wl, seed))
            if e.get("delivery_order") != m.get("delivery_order"):
                bad("pin closure %s/%s/%d delivery_order mismatch" % (strat, wl, seed))
    sp = pin.get("strategy_plans", {})
    for strat in _NEW_MARKER_KIND:
        if strat not in sp:
            bad("pin strategy_plans missing %s marker" % strat)
    ip = pin.get("portability_full_closure_invocation_plan")
    if ip is None:
        bad("pin missing portability_full_closure_invocation_plan")
    else:
        want = portability_full_closure_invocation_plan()
        if json.dumps(ip, sort_keys=True) != json.dumps(want, sort_keys=True):
            bad("pin portability_full_closure_invocation_plan != recomputed")
        want_sha = portability_full_closure_run_config_sha256(want)
        if pin.get("portability_full_closure_run_config_sha256") != want_sha:
            bad("pin portability_full_closure_run_config_sha256 != recomputed")
    return problems
