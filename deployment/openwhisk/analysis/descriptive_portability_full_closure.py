#!/usr/bin/env python3
"""Descriptive coverage for the OpenWhisk PORTABILITY-FULL-CLOSURE campaign.

Additive sibling of descriptive_portability_ext.py. Reads the frozen closure normalized
tables and emits three DESCRIPTIVE CSVs + a manifest. Descriptive only: coverage grid,
plan parity, per-workload summary. No speedup, ratio, ranking, winner, or latency
comparison is computed or implied. Native/WK1 remains the primary performance evidence;
this is the FINAL cross-workload cell-coverage closure complement (the 16 last WS_ONLY
cells of the 65-cell canonical matrix). LP is a delivery-mechanism cell here; its
delivery-order cost is analysed separately (lp_delivery_order.py), not as first_query.

Outputs (under --out, default analysis/descriptive/portability_full_closure/):
  portability_full_closure_coverage.csv          one row per executed (block, workload, strategy, seed, handle_mode) cell
  portability_full_closure_plan_parity.csv       one row per executed target plan (parity_type per taxonomy)
  portability_full_closure_workload_summary.csv  one row per workload family
  portability_full_closure_descriptive_manifest.json
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_OW_ROOT / "analysis"))
from normalize import write_csv, _git_sha                          # noqa: E402
from normalize_portability_full_closure import (                   # noqa: E402
    CLOSURE, parity_type, load_freeze_index,
)

SCHEMA_VERSION = 1

WORKLOAD_FAMILY = {
    "native_ycsb_c_read_zipf": "YC",
    "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01",
    "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit",
}
LP_STRATEGIES = CLOSURE["lp_strategies"]


def _read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def build_coverage(pairs):
    grid = defaultdict(lambda: {"n_pairs": 0, "reps": set()})
    for p in pairs:
        key = (p["block_id"], p["workload"], p["paired_target_strategy"],
               p["seed"], p["handle_mode"])
        grid[key]["n_pairs"] += 1
        grid[key]["reps"].add(p["repetition_id"])
    rows = []
    for (block, wl, strat, seed, hm), v in grid.items():
        rows.append({
            "block_id": block,
            "workload_id": wl,
            "workload_family": WORKLOAD_FAMILY.get(wl, "?"),
            "target_strategy": strat,
            "seed": seed,
            "handle_mode": hm,
            "n_pairs": v["n_pairs"],
            "n_repetitions": len(v["reps"]),
        })
    rows.sort(key=lambda r: (r["block_id"], r["workload_id"],
                             r["target_strategy"], int(r["seed"]), r["handle_mode"]))
    return rows


def build_plan_parity(invocations, freeze_idx):
    seen = {}
    for r in invocations:
        strat, wl, seed = r["strategy"], r["workload"], int(r["seed"])
        if strat == "baseline":
            continue
        key = (strat, wl, seed)
        if key in seen:
            continue
        static = strat in CLOSURE["static_strategies"]
        fz = {} if static else freeze_idx.get(key, {})
        loso = fz.get("loso") if not static else None
        recon = "static" if static else fz.get("reconstructed")
        seen[key] = {
            "strategy": strat,
            "workload_id": wl,
            "workload_family": WORKLOAD_FAMILY.get(wl, "?"),
            "seed": seed,
            "plan_sha256": r["plan_sha256"],
            "selected_page_count": r["selected_page_count"],
            "selected_interior_count": r["selected_interior_count"],
            "selected_leaf_count": r["selected_leaf_count"],
            "delivery_method": r.get("delivery_method"),
            "reconstructed": recon,
            "loso_test_seed": (loso.get("test_seed") if loso else ""),
            "parity_type": ("structural_static" if static
                            else parity_type(strat, fz.get("reconstructed", False))),
            "matches_frozen": ("static" if static
                               else (r["plan_sha256"] == fz.get("plan_sha256")
                                     and int(r["selected_page_count"]) == fz.get("pages"))),
        }
    rows = sorted(seen.values(),
                  key=lambda d: (d["strategy"], d["workload_id"], d["seed"]))
    return rows


def build_workload_summary(invocations, pairs):
    by_wl_pairs = defaultdict(list)
    for p in pairs:
        by_wl_pairs[p["workload"]].append(p)
    by_wl_inv = defaultdict(list)
    for r in invocations:
        by_wl_inv[r["workload"]].append(r)
    rows = []
    for wl in sorted(by_wl_pairs, key=lambda w: WORKLOAD_FAMILY.get(w, "z")):
        prs, invs = by_wl_pairs[wl], by_wl_inv[wl]
        strategies = sorted({p["paired_target_strategy"] for p in prs})
        seeds = sorted({int(p["seed"]) for p in prs})
        blocks = sorted({p["block_id"] for p in prs})
        rows.append({
            "workload_id": wl,
            "workload_family": WORKLOAD_FAMILY.get(wl, "?"),
            "n_pairs": len(prs),
            "n_invocations": len(invs),
            "n_baseline_invocations": sum(1 for r in invs if r["strategy"] == "baseline"),
            "n_target_invocations": sum(1 for r in invs if r["strategy"] != "baseline"),
            "target_strategies": ";".join(strategies),
            "n_target_strategies": len(strategies),
            "seeds": ";".join(str(s) for s in seeds),
            "handle_modes": ";".join(sorted({p["handle_mode"] for p in prs})),
            "blocks": ";".join(blocks),
        })
    return rows


def _sha_and_write(path, columns, rows):
    write_csv(path, columns, rows)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run(ow_root, norm_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    repo_root = Path(ow_root).parents[1]
    invocations = _read(os.path.join(norm_dir, "portability_full_closure_normalized_invocations.csv"))
    pairs = _read(os.path.join(norm_dir, "portability_full_closure_normalized_pairs.csv"))
    _, freeze_idx = load_freeze_index(repo_root)

    cov = build_coverage(pairs)
    parity = build_plan_parity(invocations, freeze_idx)
    wsum = build_workload_summary(invocations, pairs)

    cov_cols = ["block_id", "workload_id", "workload_family", "target_strategy",
                "seed", "handle_mode", "n_pairs", "n_repetitions"]
    parity_cols = ["strategy", "workload_id", "workload_family", "seed",
                   "plan_sha256", "selected_page_count", "selected_interior_count",
                   "selected_leaf_count", "delivery_method", "reconstructed",
                   "loso_test_seed", "parity_type", "matches_frozen"]
    wsum_cols = ["workload_id", "workload_family", "n_pairs", "n_invocations",
                 "n_baseline_invocations", "n_target_invocations",
                 "target_strategies", "n_target_strategies", "seeds",
                 "handle_modes", "blocks"]

    cov_sha = _sha_and_write(os.path.join(out_dir, "portability_full_closure_coverage.csv"), cov_cols, cov)
    par_sha = _sha_and_write(os.path.join(out_dir, "portability_full_closure_plan_parity.csv"), parity_cols, parity)
    ws_sha = _sha_and_write(os.path.join(out_dir, "portability_full_closure_workload_summary.csv"), wsum_cols, wsum)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "campaign": "portability_full_closure",
        "campaign_role": "final_16_cell_workstation_matrix_closure_complement",
        "descriptive_only": True,
        "not_a_performance_ranking": True,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator_git_sha": _git_sha(ow_root),
        "inputs": {
            "portability_full_closure_normalized_invocations.csv": len(invocations),
            "portability_full_closure_normalized_pairs.csv": len(pairs),
        },
        "workload_families": WORKLOAD_FAMILY,
        "lp_strategies_delivery_mechanism_only": sorted(LP_STRATEGIES),
        "coverage_cells": len(cov),
        "distinct_target_plans": len(parity),
        "parity_type_counts": dict(Counter(p["parity_type"] for p in parity)),
        "delivery_method_counts": dict(Counter(p["delivery_method"] for p in parity)),
        "workloads": len(wsum),
        "outputs": {
            "portability_full_closure_coverage.csv": {"rows": len(cov), "sha256": cov_sha},
            "portability_full_closure_plan_parity.csv": {"rows": len(parity), "sha256": par_sha},
            "portability_full_closure_workload_summary.csv": {"rows": len(wsum), "sha256": ws_sha},
        },
    }
    with open(os.path.join(out_dir, "portability_full_closure_descriptive_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ow-root", default=str(_OW_ROOT))
    ap.add_argument("--norm", default=str(_OW_ROOT / "analysis" / "normalized" / "portability_full_closure"))
    ap.add_argument("--out", default=str(_OW_ROOT / "analysis" / "descriptive" / "portability_full_closure"))
    a = ap.parse_args()
    m = run(a.ow_root, a.norm, a.out)
    print("portability_full_closure descriptive: %d coverage cells, %d target plans, %d workloads -> %s"
          % (m["coverage_cells"], m["distinct_target_plans"], m["workloads"], a.out))


if __name__ == "__main__":
    main()
