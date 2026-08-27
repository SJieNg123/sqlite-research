#!/usr/bin/env python3
"""Freeze the WK2 portability-EXTENSION delivery plans (63 keyed plans, seeds 1..3).

Additive-only sibling of ``freeze_portability_plans.py``. Covers the 21 KEYED
(workload, strategy) cells the workstation ran but the existing OpenWhisk campaigns
(primary 022fbeb0.. / secondary 441609e6.. / portability 64f44c3e..) do NOT yet cover.
The 8 STATIC cells (layers_92, layers_5, 2d) carry inline offsets in the action and
are NOT frozen here.

Every output filename is a NEW (workload_id, strategy) key -> the frozen 36-plan
portability set (portability_freeze_report.json) is left byte-untouched; this script
asserts its own plan names are disjoint from that set before writing.

Design of record (verified 2026-08-27, all native sources exist -- ZERO generation):
  * Bound DB   : prefetch_churn/test.db   sha 2504a6b1..  (same pin as portability)
  * Classifier : classify_before.csv      sha 6ec6837d..
  * Delivery plan = sorted `page_number,file_offset`, offset=(pn-1)*4096.
  * Two native-source formats are read through one auto-detecting `selected_pages`:
      - `page_number,is_resident`  (durable SoR: C/C_hit freqdump+hot2e, all learned)
        -> the selected pages are the is_resident==1 rows.
      - `page_number,file_offset`  (results-batch hotsets: YC/YCu/YCh01 2f/2e, which
        have NO durable per-seed SoR) -> every row IS a selected page.
    Byproduct-origin results-hotsets were verified identical to the durable SoR where
    both exist (C/C_hit 2f/2e); the frozen copy + recorded sha is the durable record.
  * 2f_top14 / 2f_top28        : ranked dump as-is, emergent interior/leaf split,
                                 total == 14 / 28 enforced.
  * 2e_K500                    : skeleton RECONSTRUCT (full 92 interior UNION the
                                 native top-<=500 hot leaves), identical treatment to
                                 the 2e_K10 freeze; interior==92 + leaf<=500 enforced.
  * learned_markov_14/28       : LOSO test-seeds 1..3; the .meta.json test_seed must
                                 equal the seed and never appear in train_seeds;
                                 total == 14 / 28 enforced.

Run on WK1 (read-only over native sources). No OpenWhisk build/deploy/invoke.
"""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO = Path("/home/u03/sqlite-research-project-sharing")
sys.path.insert(0, str(REPO))
import run_experiment as RE  # import-safe (guarded main)

PAGE_SIZE = 4096
SKELETON_CSV = REPO / "deployment/openwhisk/config/plans/interior_pages.csv"
KEYED_DIR = REPO / "deployment/openwhisk/config/plans/keyed"
NATIVE_DST = KEYED_DIR / "native_source" / "portability_ext"
REPORT = KEYED_DIR / "portability_ext_freeze_report.json"
FROZEN_REPORT = KEYED_DIR / "portability_freeze_report.json"  # the immutable 36-plan set

RA = "strategies/access/runs"
NHH = "results/native_headtohead"  # YC (seed{1,2,3})

# native source of record, per (workload_id, strategy) -> (path template {s}, kind).
# kind selects the gate: "freqdump" (total==N), "hot2e_k500" (reconstruct, i==92,
# l<=500), "learned" (LOSO meta + total==N).
SOURCES = {
    # YC = native_ycsb_c_read_zipf
    "native_ycsb_c_read_zipf": {
        "2f_top14":          (REPO / NHH / "seed{s}/main/work/hotset_YC_orig_2f_top14.csv", "freqdump"),
        "learned_markov_14": (REPO / RA / "learned_markov_YC_orig_N14_test{s}.csv",         "learned"),
    },
    # YCu = native_ycsb_c_read_uniform  (per-seed 2f/2e only exist as results hotsets)
    "native_ycsb_c_read_uniform": {
        "2e_K500":           (REPO / "results/native_headtohead_YCu/seed{s}/main/work/hotset_YCu_orig_2e_K500.csv",  "hot2e_k500"),
        "2f_top28":          (REPO / "results/native_headtohead_YCu/seed{s}/main/work/hotset_YCu_orig_2f_top28.csv", "freqdump"),
        "2f_top14":          (REPO / "results/native_headtohead_YCu/seed{s}/main/work/hotset_YCu_orig_2f_top14.csv", "freqdump"),
        "learned_markov_28": (REPO / RA / "learned_markov_YCu_orig_N28_test{s}.csv", "learned"),
        "learned_markov_14": (REPO / RA / "learned_markov_YCu_orig_N14_test{s}.csv", "learned"),
    },
    # YCh01 = native_ycsb_c_hot_hashed_01
    "native_ycsb_c_hot_hashed_01": {
        "2e_K500":           (REPO / "results/native_headtohead_YCh01/seed{s}/main/work/hotset_YCh01_orig_2e_K500.csv",  "hot2e_k500"),
        "2f_top28":          (REPO / "results/native_headtohead_YCh01/seed{s}/main/work/hotset_YCh01_orig_2f_top28.csv", "freqdump"),
        "2f_top14":          (REPO / "results/native_headtohead_YCh01/seed{s}/main/work/hotset_YCh01_orig_2f_top14.csv", "freqdump"),
        "learned_markov_28": (REPO / RA / "learned_markov_YCh01_orig_N28_test{s}.csv", "learned"),
        "learned_markov_14": (REPO / RA / "learned_markov_YCh01_orig_N14_test{s}.csv", "learned"),
    },
    # C_hit = read_tail_hit_20k  (durable per-seed SoR)
    "read_tail_hit_20k": {
        "2e_K500":           (REPO / RA / "hot2e_C_hit_orig_K500_seed{s}.csv",        "hot2e_k500"),
        "2f_top28":          (REPO / RA / "freqdump_C_hit_orig_N28_seed{s}.csv",      "freqdump"),
        "2f_top14":          (REPO / RA / "freqdump_C_hit_orig_N14_seed{s}.csv",      "freqdump"),
        "learned_markov_28": (REPO / RA / "learned_markov_C_hit_orig_N28_test{s}.csv","learned"),
        "learned_markov_14": (REPO / RA / "learned_markov_C_hit_orig_N14_test{s}.csv","learned"),
    },
    # C = read_tail_mixed_20k  (durable per-seed SoR; 2e_K500 SoR verified == tiebreak_fix)
    "read_tail_mixed_20k": {
        "2f_top14":          (REPO / RA / "freqdump_C_orig_N14_seed{s}.csv",      "freqdump"),
        "2f_top28":          (REPO / RA / "freqdump_C_orig_N28_seed{s}.csv",      "freqdump"),
        "2e_K500":           (REPO / RA / "hot2e_C_orig_K500_seed{s}.csv",        "hot2e_k500"),
        "learned_markov_28": (REPO / RA / "learned_markov_C_orig_N28_test{s}.csv","learned"),
    },
}
SEEDS = (1, 2, 3)

BOUND_DB = REPO / "prefetch_churn/test.db"
EXPECT_DB_SHA = "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1"
EXPECT_CLASSIFY_SHA = "6ec6837dc6a801c28e1cc08e90ccac570ee9a517765c0f6f03ab1b723349cc32"
EXPECT_TOTAL = 63


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_skeleton():
    s = set()
    with open(SKELETON_CSV, newline="") as f:
        for r in csv.reader(f):
            if not r or r[0].lower().startswith("page"):
                continue
            s.add(int(r[0]))
    return s


def selected_pages(path):
    """Auto-detect native-source format and return the selected page-number set.

    `page_number,is_resident`  -> rows with is_resident==1 (SoR files).
    `page_number,file_offset`  -> every row (results-batch hotsets already ARE the
                                  selection; file_offset carries no residency flag)."""
    with open(RE.resolve_pointer(path), newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return set()
    cols = rows[0].keys()
    if "is_resident" in cols:
        return {int(r["page_number"]) for r in rows if r.get("is_resident", "0").strip() == "1"}
    if "file_offset" in cols:
        return {int(r["page_number"]) for r in rows}
    raise SystemExit(f"{path}: unrecognized native-source columns {list(cols)}")


def strat_budget(strat):
    """N from a ranked/learned strategy name suffix (2f_top14 -> 14, ..._28 -> 28)."""
    return int(strat.rsplit("_", 1)[-1].lstrip("topN")) if strat.startswith("2f_top") \
        else int(strat.rsplit("_", 1)[-1])


def write_plan(pages, dst):
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_number", "file_offset"])
        for pn in sorted(pages):
            w.writerow([pn, (pn - 1) * PAGE_SIZE])


def load_frozen_plan_names():
    """Basenames of the immutable 36-plan portability set -- ext names must be disjoint."""
    if not FROZEN_REPORT.exists():
        return set()
    rep = json.loads(FROZEN_REPORT.read_text())
    return {Path(p["plan_path"]).name for p in rep["plans"]}


def main():
    # --- identity gates (same as the portability freeze) -----------------------
    assert sha256(BOUND_DB) == EXPECT_DB_SHA, "bound test.db sha mismatch"
    classify = RE.load_classify("orig")
    classify_path = RE.resolve_pointer(RE.CLASSIFY["orig"])
    assert sha256(classify_path) == EXPECT_CLASSIFY_SHA, "classifier sha mismatch"
    skeleton = load_skeleton()
    assert len(skeleton) == 92, f"skeleton size {len(skeleton)} != 92"
    interior_from_classify = {pn for pn, (t, _o) in classify.items() if t.startswith("interior")}
    assert interior_from_classify == skeleton, "classifier interior set != frozen 92-skeleton"
    is_interior = lambda pn: pn in skeleton

    frozen_names = load_frozen_plan_names()
    NATIVE_DST.mkdir(parents=True, exist_ok=True)
    report = {"bound_db_sha256": EXPECT_DB_SHA, "classifier_sha256": EXPECT_CLASSIFY_SHA,
              "seeds": list(SEEDS), "plans": []}
    made = set()

    for wid, strats in SOURCES.items():
        for strat, (tmpl, kind) in strats.items():
            for s in SEEDS:
                src = Path(str(tmpl).format(s=s))
                assert src.exists(), f"missing native source: {src}"
                src_sha = sha256(src)

                reconstructed = False
                loso = None
                if kind == "freqdump":
                    pages = selected_pages(src)
                elif kind == "learned":
                    pages = selected_pages(src)
                    meta = json.loads(Path(str(src).replace(".csv", ".meta.json")).read_text())
                    loso = {"test_seed": meta["test_seed"], "train_seeds": meta["train_seeds"]}
                    assert s == meta["test_seed"], f"{src}: test_seed {meta['test_seed']} != {s}"
                    assert s not in meta["train_seeds"], f"LOSO leak: {s} in {meta['train_seeds']}"
                elif kind == "hot2e_k500":
                    raw = selected_pages(src)
                    leaves = {pn for pn in raw if not is_interior(pn)}
                    pages = set(skeleton) | leaves
                    reconstructed = True
                else:
                    raise ValueError(f"unknown kind {kind}")

                inter = len(pages & skeleton)
                leaf = len(pages - skeleton)
                total = len(pages)

                # --- per-strategy contract gates ---------------------------------
                if strat in ("2f_top14", "2f_top28", "learned_markov_14", "learned_markov_28"):
                    want = strat_budget(strat)
                    assert total == want, f"{wid}/{strat}/s{s}: total {total} != {want}"
                elif strat == "2e_K500":
                    assert inter == 92, f"{wid}/{strat}/s{s}: interior {inter} != 92"
                    assert leaf <= 500, f"{wid}/{strat}/s{s}: leaf {leaf} > 500"
                    assert total == inter + leaf
                else:
                    raise ValueError(f"unexpected strategy {strat}")

                plan_name = f"{strat}_{wid}_seed{s}.csv"
                assert plan_name not in frozen_names, \
                    f"ext plan name collides with frozen 36-set: {plan_name}"
                assert plan_name not in made, f"duplicate plan name {plan_name}"
                made.add(plan_name)
                plan_path = KEYED_DIR / plan_name
                write_plan(pages, plan_path)

                ns_dst = NATIVE_DST / src.name
                if ns_dst.exists() and sha256(ns_dst) != src_sha:
                    raise SystemExit(f"native_source name collision with different bytes: {src.name}")
                shutil.copyfile(src, ns_dst)

                report["plans"].append({
                    "workload_id": wid, "strategy": strat, "seed": s,
                    "kind": kind, "reconstructed": reconstructed, "loso": loso,
                    "plan_path": str(plan_path.relative_to(REPO)),
                    "plan_sha256": sha256(plan_path),
                    "pages": total, "interior": inter, "leaf": leaf,
                    "native_source_path": str(src),
                    "native_source_sha256": src_sha,
                    "native_source_copy": str(ns_dst.relative_to(REPO)),
                })

    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True))
    n = len(report["plans"])
    print(f"froze {n} EXT delivery plans -> {KEYED_DIR}")
    print(f"native-source copies -> {NATIVE_DST}")
    print(f"report -> {REPORT.relative_to(REPO)}")
    for p in report["plans"]:
        print(f"  {p['workload_id']:<28} {p['strategy']:<18} s{p['seed']}  "
              f"n={p['pages']:<5} i={p['interior']:<3} l={p['leaf']:<5} "
              f"{'RECON ' if p['reconstructed'] else ''}{p['plan_sha256'][:12]}")
    assert n == EXPECT_TOTAL, f"expected {EXPECT_TOTAL} plans, got {n}"
    print(f"\nOK: {n} ext plans, all contract gates passed.")


if __name__ == "__main__":
    main()
