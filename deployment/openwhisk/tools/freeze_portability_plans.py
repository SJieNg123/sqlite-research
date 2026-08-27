#!/usr/bin/env python3
"""Freeze the WK2 portability delivery plans (MINIMAL matrix, seeds 1..3).

Additive-only. Produces the 36 keyed delivery plans + durable native-source
copies + a SHA/count report for the portability matrix (M1..M4). Touches none of
the frozen primary (022fbeb0..) / secondary (441609e6..) YC evidence: every output
filename is a NEW (workload_id, strategy) key.

Design of record (verified 2026-08-27):
  * Bound DB   : prefetch_churn/test.db          sha 2504a6b1..  (pin bound_db_sha256)
  * Classifier : .../classify_before.csv         sha 6ec6837d..  (pin classifier)
  * Delivery plan = sorted `page_number,file_offset`, offset=(pn-1)*4096.
  * 2e_K10 (ALL workloads): RECONSTRUCTED to the OW contract = 92-skeleton UNION the
    per-seed trace-derived top-10 hot leaves (user decision 2026-08-27). For YCu/YCh01
    the native hot2e is already 92u10; for C/C_hit the native hot2e touches only 4/5
    resident interiors, so the skeleton half is lifted to the full 92 (documented as a
    deployment-contract reconstruction, NOT the raw native selection).
  * 2f_slru : whole resident working set as-is (emergent interior count, recorded).
  * 2f_top28 / learned_markov_28 : ranked/learned dump as-is (emergent split, total==28).
    learned_markov_28 uses LOSO test-seeds 1..3; train_seeds must exclude the test seed.
  * leaf_freq_K10 / leaf_rand_K10 (C only): canonical select_pages logic, leaf-only, K=10.

Run on WK1 (read-only over native sources). No OpenWhisk build/deploy/invoke.
"""
import csv
import hashlib
import json
import random
import shutil
import sys
from pathlib import Path

# --- reuse the repo's canonical classifier + resident-page reader --------------
REPO = Path("/home/u03/sqlite-research-project-sharing")
FORK = Path("/home/u03/sqlite-research-fork")
sys.path.insert(0, str(REPO))
import run_experiment as RE  # import-safe (guarded main at line 1032)

PAGE_SIZE = 4096
SKELETON_CSV = REPO / "deployment/openwhisk/config/plans/interior_pages.csv"
KEYED_DIR = REPO / "deployment/openwhisk/config/plans/keyed"
NATIVE_DST = KEYED_DIR / "native_source" / "portability"
REPORT = KEYED_DIR / "portability_freeze_report.json"

# --- native source of record, per (workload_id, strategy). {s} -> seed ---------
RA = "strategies/access/runs"
RS = "strategies/slru/runs"
SOURCES = {
    "native_ycsb_c_read_zipf": {
        "2f_top28":         (REPO / RA / "freqdump_YC_orig_N28_seed{s}.csv",        "resident"),
        "learned_markov_28":(REPO / RA / "learned_markov_YC_orig_N28_test{s}.csv",  "resident_loso"),
    },
    "native_ycsb_c_read_uniform": {
        "2e_K10":  (FORK / RA / "hot2e_YCu_orig_K10_seed{s}.csv",  "hot2e_reconstruct"),
        "2f_slru": (FORK / RS / "hotpages_ycu_seed{s}.csv",        "resident"),
    },
    "native_ycsb_c_hot_hashed_01": {
        "2e_K10":  (FORK / RA / "hot2e_YCh01_orig_K10_seed{s}.csv","hot2e_reconstruct"),
        "2f_slru": (FORK / RS / "hotpages_ych01_seed{s}.csv",      "resident"),
    },
    "read_tail_mixed_20k": {  # C  (native workload key "C")
        "2e_K10":        (REPO / RA / "hot2e_C_orig_K10_seed{s}.csv", "hot2e_reconstruct"),
        "2f_slru":       (REPO / RS / "hotpages_c_seed{s}.csv",       "resident"),
        "leaf_freq_K10": (REPO / RA / "hot2e_C_orig_K10_seed{s}.csv", "leaf_freq"),
        "leaf_rand_K10": (REPO / RA / "hot2e_C_orig_K10_seed{s}.csv", "leaf_rand:C"),
    },
    "read_tail_hit_20k": {  # C_hit
        "2e_K10":  (REPO / RA / "hot2e_C_hit_orig_K10_seed{s}.csv", "hot2e_reconstruct"),
        "2f_slru": (REPO / RS / "hotpages_c_hit_seed{s}.csv",       "resident"),
    },
}
SEEDS = (1, 2, 3)

BOUND_DB = REPO / "prefetch_churn/test.db"
EXPECT_DB_SHA = "2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1"
EXPECT_CLASSIFY_SHA = "6ec6837dc6a801c28e1cc08e90ccac570ee9a517765c0f6f03ab1b723349cc32"


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


def resident(path):
    return RE._resident_pages(path)


def leaf_rand_C(hot2e_path, seed, classify, is_interior):
    """Exact reproduction of run_experiment.select_pages 'leaf_rand', w=C layout=orig K=10."""
    res = resident(hot2e_path)
    top_leaves = {pn for pn in res if not is_interior(pn)}
    top_types = {classify[pn][0] for pn in top_leaves if pn in classify}
    pool = sorted(pn for pn, (t, _o) in classify.items()
                  if t in top_types and pn not in top_leaves)
    rng = random.Random(f"leafrand|{seed}|C|orig|{len(top_leaves)}")
    return set(rng.sample(pool, min(len(top_leaves), len(pool)))), top_leaves


def write_plan(pages, dst):
    rows = sorted(pages)
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_number", "file_offset"])
        for pn in rows:
            w.writerow([pn, (pn - 1) * PAGE_SIZE])


def main():
    # --- identity gates --------------------------------------------------------
    assert sha256(BOUND_DB) == EXPECT_DB_SHA, "bound test.db sha mismatch"
    classify = RE.load_classify("orig")
    classify_path = RE.resolve_pointer(RE.CLASSIFY["orig"])
    assert sha256(classify_path) == EXPECT_CLASSIFY_SHA, "classifier sha mismatch"
    skeleton = load_skeleton()
    assert len(skeleton) == 92, f"skeleton size {len(skeleton)} != 92"
    interior_from_classify = {pn for pn, (t, _o) in classify.items() if t.startswith("interior")}
    assert interior_from_classify == skeleton, "classifier interior set != frozen 92-skeleton"
    is_interior = lambda pn: pn in skeleton

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
                if kind in ("resident", "resident_loso"):
                    pages = resident(src)
                    if kind == "resident_loso":
                        meta = json.loads(Path(str(src).replace(".csv", ".meta.json")).read_text())
                        loso = {"test_seed": meta["test_seed"], "train_seeds": meta["train_seeds"]}
                        assert s == meta["test_seed"], f"{src}: test_seed {meta['test_seed']} != {s}"
                        assert s not in meta["train_seeds"], f"LOSO leak: {s} in {meta['train_seeds']}"
                elif kind == "hot2e_reconstruct":
                    res = resident(src)
                    leaves = {pn for pn in res if not is_interior(pn)}
                    pages = set(skeleton) | leaves
                    reconstructed = True
                elif kind == "leaf_freq":
                    res = resident(src)
                    pages = {pn for pn in res if not is_interior(pn)}
                elif kind == "leaf_rand:C":
                    pages, top_leaves = leaf_rand_C(src, s, classify, is_interior)
                    assert pages.isdisjoint(top_leaves), "leaf_rand overlaps hot leaves"
                else:
                    raise ValueError(f"unknown kind {kind}")

                inter = len(pages & skeleton)
                leaf = len(pages - skeleton)
                total = len(pages)

                # --- per-strategy contract gates ---------------------------------
                if strat == "2e_K10":
                    assert (inter, leaf, total) == (92, 10, 102), f"{wid}/{strat}/s{s}: {inter}/{leaf}/{total}"
                elif strat in ("2f_top28", "learned_markov_28"):
                    assert total == 28, f"{wid}/{strat}/s{s}: total {total} != 28"
                elif strat in ("leaf_freq_K10", "leaf_rand_K10"):
                    assert (inter, leaf, total) == (0, 10, 10), f"{wid}/{strat}/s{s}: {inter}/{leaf}/{total}"
                elif strat == "2f_slru":
                    assert total > 0, f"{wid}/{strat}/s{s}: empty"
                else:
                    raise ValueError(f"unexpected strategy {strat}")

                plan_name = f"{strat}_{wid}_seed{s}.csv"
                plan_path = KEYED_DIR / plan_name
                assert plan_name not in made, f"duplicate plan name {plan_name}"
                made.add(plan_name)
                write_plan(pages, plan_path)

                ns_name = f"{src.name}"
                ns_dst = NATIVE_DST / ns_name
                # source basenames are unique across trees except none collide here; assert
                if ns_dst.exists() and sha256(ns_dst) != src_sha:
                    raise SystemExit(f"native_source name collision with different bytes: {ns_name}")
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
    print(f"froze {n} delivery plans -> {KEYED_DIR}")
    print(f"native-source copies -> {NATIVE_DST}")
    print(f"report -> {REPORT.relative_to(REPO)}")
    # summary table
    for p in report["plans"]:
        print(f"  {p['workload_id']:<28} {p['strategy']:<18} s{p['seed']}  "
              f"n={p['pages']:<5} i={p['interior']:<3} l={p['leaf']:<5} "
              f"{'RECON ' if p['reconstructed'] else ''}{p['plan_sha256'][:12]}")
    assert n == 36, f"expected 36 plans, got {n}"
    print(f"\nOK: {n} plans, all contract gates passed.")


if __name__ == "__main__":
    main()
