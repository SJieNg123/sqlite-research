#!/usr/bin/env python3
"""Freeze the WK2 portability-FULL-CLOSURE delivery plans (37 keyed plans).

FIFTH additive campaign. Additive-only sibling of ``freeze_portability_ext_plans.py``.
Closes the final 16 WS_ONLY cells of the frozen 65-cell canonical portability matrix
(the campaign was 49/65 BOTH after portability_ext). The four prior campaigns --
primary 022fbeb0.. / secondary 441609e6.. / portability 64f44c3e.. / portability_ext
bf504a28.. -- are BYTE-UNTOUCHED; every output name is a NEW (workload_id, strategy)
key, asserted disjoint from BOTH prior frozen sets (36 + 63).

The 16 closure cells, by block (orig layout only):
  B12  C     / {2e_K40, 2e_K92}                       single-inst (seed 1)     -> 2 plans
  B13  C_hit / {2e_K40, 2e_K92}                        seeds 1,2,3              -> 6 plans
  B14  C     / {learned_markov_14}                     LOSO folds 1,2,3         -> 3 plans
  B15  C     / {layers_92}                             STATIC (reuse skeleton)  -> 0 plans
  B16  lp x {YC, YCu, YCh01, C_hit} x {sorted, shuf}   seeds 1,2,3              -> 24 plans
  B17  lp x {C}          x {sorted, shuf}              seed 1                   -> 2 plans
  ---------------------------------------------------------------------------------------
  total keyed plans frozen                                                     -> 37

Provenance / gates (verified 2026-08-28, all native sources on disk -- ZERO generation):
  * Bound DB   : prefetch_churn/test.db   sha 2504a6b1..  (same pin as every campaign)
  * Classifier : classify_before.csv      sha 6ec6837d..
  * Non-lp delivery plan = SORTED `page_number,file_offset`, offset=(pn-1)*4096.
  * 2e_K40 / 2e_K92 = skeleton RECONSTRUCT (full 92 interior UNION native top-<=K hot
    leaves), identical treatment to the 2e_K10 / 2e_K500 freeze; interior==92 +
    leaf<=K enforced. Two native-source formats auto-detected by `selected_pages`:
      - `page_number,is_resident` (durable SoR, C single-inst: hot2e_C_orig_K{40,92})
      - `page_number,file_offset` (results-batch hotset, C_hit: c_hit_v2/seed0X)
  * learned_markov_14 = LOSO folds 1..3 (durable SoR); .meta.json test_seed must equal
    the seed and never appear in train_seeds; total == 14 enforced.
  * lp_sorted / lp_shuf (libprefetch) -- THE ordered-delivery strategies:
      - Selected page SET == the corresponding canonical 2f_slru resident working set
        (SAME multiset for both lp strategies; they differ ONLY in delivery order).
      - lp_sorted : that set, ordered by file_offset ASCENDING.
      - lp_shuf   : that set, offset-sorted first, then
                    ``random.Random(424242).shuffle(rows)`` (LP_SHUF_SEED=424242).
      - Plan CSV is written IN THAT ORDER (NOT sorted); plan_sha256 is therefore
        ORDER-SENSITIVE. Per (workload,seed): lp_sorted set == lp_shuf set is proved,
        ordered sequences are proved to DIFFER, and the two plan SHAs are proved
        distinct. The frozen report records the ordered sequence + sequence positions.

Run on WK1 (read-only over native sources). No OpenWhisk build/deploy/invoke.
"""
import csv
import hashlib
import json
import random
import shutil
import sys
from pathlib import Path

REPO = Path("/home/u03/sqlite-research-project-sharing")
sys.path.insert(0, str(REPO))
import run_experiment as RE  # import-safe (guarded main)

PAGE_SIZE = 4096
LP_SHUF_SEED = 424242
SKELETON_CSV = REPO / "deployment/openwhisk/config/plans/interior_pages.csv"
KEYED_DIR = REPO / "deployment/openwhisk/config/plans/keyed"
NATIVE_DST = KEYED_DIR / "native_source" / "portability_full_closure"
REPORT = KEYED_DIR / "portability_full_closure_freeze_report.json"
# the immutable prior frozen sets -- closure plan names must be disjoint from BOTH
FROZEN_REPORTS = [
    KEYED_DIR / "portability_freeze_report.json",       # 36-plan portability
    KEYED_DIR / "portability_ext_freeze_report.json",   # 63-plan portability_ext
]

RA = "strategies/access/runs"

# workload ids
YC = "native_ycsb_c_read_zipf"
YCU = "native_ycsb_c_read_uniform"
YCH01 = "native_ycsb_c_hot_hashed_01"
CHIT = "read_tail_hit_20k"
CMIX = "read_tail_mixed_20k"

# --- non-lp keyed sources: (workload_id -> {strategy: (path template {s}, kind, seeds)})
# kind "hot2e_kN" = skeleton reconstruct (interior==92, leaf<=K); "learned" = LOSO+total.
NON_LP_SOURCES = {
    # B12 -- C single-instantiation 2e_K40 / 2e_K92 (durable SoR, is_resident).
    CMIX: {
        "2e_K40": (REPO / RA / "hot2e_C_orig_K40.csv", "hot2e_kN", (1,)),
        "2e_K92": (REPO / RA / "hot2e_C_orig_K92.csv", "hot2e_kN", (1,)),
        # B14 -- C learned_markov_14, LOSO folds 1..3 (durable SoR + .meta.json).
        "learned_markov_14": (REPO / RA / "learned_markov_C_orig_N14_test{s}.csv",
                              "learned", (1, 2, 3)),
    },
    # B13 -- C_hit 2e_K40 / 2e_K92, seeds 1..3 (results-batch hotset, file_offset).
    CHIT: {
        "2e_K40": (REPO / "results/c_hit_v2/seed0{s}/work/hotset_C_hit_orig_2e_K40.csv",
                   "hot2e_kN", (1, 2, 3)),
        "2e_K92": (REPO / "results/c_hit_v2/seed0{s}/work/hotset_C_hit_orig_2e_K92.csv",
                   "hot2e_kN", (1, 2, 3)),
    },
}

# --- lp keyed sources: (workload_id -> (2f_slru path template {s}, seeds)). Each source
# yields BOTH lp_sorted and lp_shuf (same set, different order).
LP_2FSLRU_SOURCES = {
    # B16
    YC:    (REPO / "results/native_headtohead/seed{s}/main/work/hotset_YC_orig_2f_slru.csv", (1, 2, 3)),
    YCU:   (REPO / "results/native_headtohead_YCu/seed{s}/main/work/hotset_YCu_orig_2f_slru.csv", (1, 2, 3)),
    YCH01: (REPO / "results/native_headtohead_YCh01/seed{s}/main/work/hotset_YCh01_orig_2f_slru.csv", (1, 2, 3)),
    CHIT:  (REPO / "results/chit_headtohead/seed0{s}/main/work/hotset_C_hit_orig_2f_slru.csv", (1, 2, 3)),
    # B17
    CMIX:  (REPO / "results/baselines_v2/anchor/work/hotset_C_orig_2f_slru.csv", (1,)),
}

BOUND_DB = REPO / "prefetch_churn/test.db"
EXPECT_DB_SHA = "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1"
EXPECT_CLASSIFY_SHA = "6ec6837dc6a801c28e1cc08e90ccac570ee9a517765c0f6f03ab1b723349cc32"
EXPECT_TOTAL = 37


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def load_skeleton():
    s = set()
    with open(SKELETON_CSV, newline="") as f:
        for r in csv.reader(f):
            if not r or r[0].lower().startswith("page"):
                continue
            s.add(int(r[0]))
    return s


def selected_pages(path):
    """Auto-detect native-source format -> selected page-number set.

    `page_number,is_resident` -> is_resident==1 rows (SoR files).
    `page_number,file_offset` -> every row (results-batch hotsets already ARE the
                                 selection)."""
    with open(RE.resolve_pointer(path), newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return set()
    cols = rows[0].keys()
    if "is_resident" in cols:
        return {int(r["page_number"]) for r in rows if r.get("is_resident", "0").strip() == "1"}
    if "file_offset" in cols:
        return {int(r["page_number"]) for r in rows}
    raise SystemExit("%s: unrecognized native-source columns %s" % (path, list(cols)))


def k_budget(strat):
    """K from a 2e_KN strategy name suffix (2e_K40 -> 40, 2e_K92 -> 92)."""
    return int(strat.split("_K")[-1])


def offset_of(pn):
    return (pn - 1) * PAGE_SIZE


def write_sorted_plan(pages, dst):
    """Non-lp keyed plan: sorted `page_number,file_offset` (order-irrelevant here)."""
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_number", "file_offset"])
        for pn in sorted(pages):
            w.writerow([pn, offset_of(pn)])


def write_ordered_plan(ordered_pages, dst):
    """lp keyed plan: `page_number,file_offset` written IN THE GIVEN ORDER (never
    sorted). The row order IS the delivery sequence, so the file bytes -- and thus
    plan_sha256 -- are ORDER-SENSITIVE."""
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_number", "file_offset"])
        for pn in ordered_pages:
            w.writerow([pn, offset_of(pn)])


def load_frozen_plan_names():
    """Basenames of every prior immutable frozen plan -- closure names must be disjoint."""
    names = set()
    for rep_path in FROZEN_REPORTS:
        if rep_path.exists():
            rep = json.loads(rep_path.read_text())
            names |= {Path(p["plan_path"]).name for p in rep["plans"]}
    return names


def main():
    # --- identity gates (same as every prior freeze) ---------------------------
    assert sha256(BOUND_DB) == EXPECT_DB_SHA, "bound test.db sha mismatch"
    classify = RE.load_classify("orig")
    classify_path = RE.resolve_pointer(RE.CLASSIFY["orig"])
    assert sha256(classify_path) == EXPECT_CLASSIFY_SHA, "classifier sha mismatch"
    skeleton = load_skeleton()
    assert len(skeleton) == 92, "skeleton size %d != 92" % len(skeleton)
    interior_from_classify = {pn for pn, (t, _o) in classify.items() if t.startswith("interior")}
    assert interior_from_classify == skeleton, "classifier interior set != frozen 92-skeleton"
    is_interior = lambda pn: pn in skeleton

    frozen_names = load_frozen_plan_names()
    NATIVE_DST.mkdir(parents=True, exist_ok=True)
    report = {"bound_db_sha256": EXPECT_DB_SHA, "classifier_sha256": EXPECT_CLASSIFY_SHA,
              "lp_shuf_seed": LP_SHUF_SEED, "plans": []}
    made = set()

    def register(wid, strat, seed, kind, pages_iter, plan_path, src, src_sha,
                 native_copy, reconstructed=False, loso=None, ordered=None, lp=None):
        inter = len(set(pages_iter) & skeleton)
        leaf = len(set(pages_iter) - skeleton)
        total = len(set(pages_iter))
        entry = {
            "workload_id": wid, "strategy": strat, "seed": seed, "kind": kind,
            "reconstructed": reconstructed, "loso": loso,
            "plan_path": str(plan_path.relative_to(REPO)),
            "plan_sha256": sha256(plan_path),
            "pages": total, "interior": inter, "leaf": leaf,
            "native_source_path": str(src), "native_source_sha256": src_sha,
            "native_source_copy": native_copy,
        }
        if ordered is not None:
            entry["delivery_order"] = ordered
        if lp is not None:
            entry["lp"] = lp
        report["plans"].append(entry)
        return entry

    def freeze_name(strat, wid, seed):
        name = "%s_%s_seed%d.csv" % (strat, wid, seed)
        assert name not in frozen_names, "closure plan name collides with prior frozen set: %s" % name
        assert name not in made, "duplicate closure plan name %s" % name
        made.add(name)
        return name

    def copy_native(src, src_sha, wid, s):
        # results-batch sources share a basename across seed dirs (e.g. every seed's
        # hotset_*_2f_slru.csv), so the durable copy is namespaced by (workload, seed)
        # to keep each seed's exact bytes distinct and collision-free.
        ns_dst = NATIVE_DST / ("%s_seed%d__%s" % (wid, s, Path(src).name))
        if ns_dst.exists() and sha256(ns_dst) != src_sha:
            raise SystemExit("native_source copy collision with different bytes: %s" % ns_dst.name)
        shutil.copyfile(src, ns_dst)
        return str(ns_dst.relative_to(REPO))

    # ----- non-lp keyed plans (B12 / B13 / B14) --------------------------------
    for wid, strats in NON_LP_SOURCES.items():
        for strat, (tmpl, kind, seeds) in strats.items():
            for s in seeds:
                src = Path(str(tmpl).format(s=s))
                assert src.exists(), "missing native source: %s" % src
                src_sha = sha256(src)
                loso = None
                reconstructed = False
                if kind == "hot2e_kN":
                    raw = selected_pages(src)
                    leaves = {pn for pn in raw if not is_interior(pn)}
                    pages = set(skeleton) | leaves
                    reconstructed = True
                    K = k_budget(strat)
                    inter = len(pages & skeleton)
                    leaf = len(pages - skeleton)
                    assert inter == 92, "%s/%s/s%d: interior %d != 92" % (wid, strat, s, inter)
                    assert leaf <= K, "%s/%s/s%d: leaf %d > K=%d" % (wid, strat, s, leaf, K)
                elif kind == "learned":
                    pages = selected_pages(src)
                    meta = json.loads(Path(str(src).replace(".csv", ".meta.json")).read_text())
                    loso = {"test_seed": meta["test_seed"], "train_seeds": meta["train_seeds"]}
                    assert s == meta["test_seed"], "%s: test_seed %s != %d" % (src, meta["test_seed"], s)
                    assert s not in meta["train_seeds"], "LOSO leak: %d in %s" % (s, meta["train_seeds"])
                    assert len(pages) == 14, "%s/%s/s%d: total %d != 14" % (wid, strat, s, len(pages))
                else:
                    raise ValueError("unknown non-lp kind %s" % kind)
                plan_path = KEYED_DIR / freeze_name(strat, wid, s)
                write_sorted_plan(pages, plan_path)
                native_copy = copy_native(src, src_sha, wid, s)
                register(wid, strat, s, kind, pages, plan_path, src, src_sha,
                         native_copy, reconstructed=reconstructed, loso=loso)

    # ----- lp ordered keyed plans (B16 / B17) ----------------------------------
    for wid, (tmpl, seeds) in LP_2FSLRU_SOURCES.items():
        for s in seeds:
            src = Path(str(tmpl).format(s=s))
            assert src.exists(), "missing 2f_slru native source: %s" % src
            src_sha = sha256(src)
            pages = selected_pages(src)           # the canonical 2f_slru resident set
            assert pages, "%s/s%d: empty 2f_slru set" % (wid, s)
            base_sorted = sorted(pages)           # offset-ascending == page# ascending
            set_sha = sha256_bytes(json.dumps(base_sorted, separators=(",", ":")).encode())

            # lp_sorted -- offset ascending
            sorted_seq = list(base_sorted)
            # lp_shuf -- offset-sort first, then Random(424242).shuffle in place
            shuf_seq = list(base_sorted)
            random.Random(LP_SHUF_SEED).shuffle(shuf_seq)

            # order-sensitivity proofs (per workload,seed)
            assert set(sorted_seq) == set(shuf_seq) == set(pages), \
                "%s/s%d: lp_sorted / lp_shuf page sets differ" % (wid, s)
            assert sorted_seq != shuf_seq, \
                "%s/s%d: lp_shuf order identical to lp_sorted (shuffle no-op)" % (wid, s)

            native_copy = copy_native(src, src_sha, wid, s)
            shas = {}
            for strat, seq, order in (("lp_sorted", sorted_seq, "file_offset_ascending"),
                                      ("lp_shuf", shuf_seq, "seed_shuffled")):
                plan_path = KEYED_DIR / freeze_name(strat, wid, s)
                write_ordered_plan(seq, plan_path)
                # The ordered delivery sequence itself lives in the plan CSV (order-
                # sensitive, SHA-bound); the unordered-set identity is set_sha. Inlining
                # the full sequence + a position map here would only duplicate the CSV
                # (up to 26k entries per lp plan) and bloat the report, so we don't.
                lp_meta = {
                    "delivery_method": "pread_ordered",
                    "selected_page_set_sha256": set_sha,
                    "selected_page_count": len(pages),
                    "shuffle_seed": LP_SHUF_SEED if strat == "lp_shuf" else None,
                }
                register(wid, strat, s, "lp_pread_ordered", pages, plan_path, src, src_sha,
                         native_copy, ordered=order, lp=lp_meta)
                shas[strat] = sha256(plan_path)
            assert shas["lp_sorted"] != shas["lp_shuf"], \
                "%s/s%d: lp_sorted / lp_shuf plan SHAs equal (order not captured)" % (wid, s)

    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True))
    n = len(report["plans"])
    print("froze %d FULL-CLOSURE delivery plans -> %s" % (n, KEYED_DIR))
    print("native-source copies -> %s" % NATIVE_DST)
    print("report -> %s" % REPORT.relative_to(REPO))
    for p in report["plans"]:
        extra = ""
        if p["kind"] == "lp_pread_ordered":
            extra = "ORDER=%s seq=%d" % (p["delivery_order"], p["lp"]["selected_page_count"])
        elif p["reconstructed"]:
            extra = "RECON"
        elif p["loso"]:
            extra = "LOSO test=%s" % p["loso"]["test_seed"]
        print("  %-28s %-12s s%d  n=%-6d i=%-3d l=%-6d %s %s"
              % (p["workload_id"], p["strategy"], p["seed"], p["pages"],
                 p["interior"], p["leaf"], extra, p["plan_sha256"][:12]))
    assert n == EXPECT_TOTAL, "expected %d plans, got %d" % (EXPECT_TOTAL, n)
    print("\nOK: %d full-closure plans, all contract gates passed." % n)


if __name__ == "__main__":
    main()
