#!/usr/bin/env python3
"""WK1-side normalizer for the completed OpenWhisk PORTABILITY-FULL-CLOSURE campaign.

Additive sibling of normalize_portability.py / normalize_portability_ext.py. The
portability_full_closure campaign is the FIFTH independent OpenWhisk campaign and a
SINGLE-BATCH block-union matrix (228 pairs / 456 invocations, blocks B12-B17) that
executes the FINAL 16 WS_ONLY cells of the 65-cell canonical retained workstation
(workload x strategy) portability matrix at orig layout. After it, every canonical
retained cell has OpenWhisk *cell coverage*.

This is a CELL-COVERAGE / cross-workload PORTABILITY complement: it validates
execution, correctness, workload binding, plan binding, semantic parity, selected-
page footprint, delivery mechanism, and cost observability for those 16 cells. It is
NOT a performance ranking and asserts no latency agreement, ranking equality, layout
completeness, protocol replication, or warm paired speedup. Native/WK1 remains the
primary controlled performance/mechanism evidence.

Design mirrors the sibling normalizers EXACTLY: the frozen primary, secondary,
portability (64f44c3e) and portability_ext (bf504a28) normalized outputs are never
touched; this campaign gets its own separate table under
analysis/normalized/portability_full_closure/. Structural block gates (per-block
rectangularity, cross-block disjoint union, no unintended cell, exact grand totals,
pair integrity, contiguous positions) are delegated to
client/validate_schedule.validate_campaign + the single live campaign_fingerprint.
This module adds: block_id provenance, the per-response validity gate, plan/workload
parity against the frozen keyed contract (portability_full_closure_freeze_report.json),
the POSITIVE 16-cell coverage gate (exact target-cell set equality — the closure
guarantee, replacing the ext forbidden-cell guard), the lp delivery-mechanism gate
(lp_sorted/lp_shuf MUST report delivery_method == "pread_ordered"; every other arm
MUST report "madvise_willneed"), the layers_92 structural-static invariant
(interior==92, leaf==0), the 2e reconstruction skeleton invariant (interior==92),
baseline-zero-prefetch, LOSO carry-through, and the structural-static seed-1-only
rule for layers_92.

Outputs (under --out, default analysis/normalized/portability_full_closure/):
  portability_full_closure_normalized_invocations.csv   456 rows (schema + block_id + delivery_method)
  portability_full_closure_normalized_pairs.csv         228 rows (canonical pair schema + block_id)
  portability_full_closure_normalization_manifest.json  identities, counts, plan-parity, SHAs
  portability_full_closure_normalization_validation.txt every fail-closed gate result
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]                      # deployment/openwhisk
_REPO_ROOT = _HERE.parents[3]                    # repo root
sys.path.insert(0, str(_OW_ROOT / "client"))
sys.path.insert(0, str(_OW_ROOT / "analysis"))
import validate_schedule as vs                   # noqa: E402
from normalize import (                          # noqa: E402
    INVOCATION_COLUMNS, PAIR_COLUMNS,
    sha256_file, parse_sidecar, read_bundle, build_rows, derive_pairs,
    order_balance, write_csv, load_page_size, _git_sha,
)

SCHEMA_VERSION = 1

# ---- portability_full_closure campaign registry (single batch) --------------
CLOSURE = {
    "campaign": "portability_full_closure",
    "evidence_dir": "evidence/portability_full_closure/956cd15b5db3",
    "bundle": "ws2_bundle_956cd15b5db3_20260828T141110Z.tar.gz",
    "matrix_rel": "ws2/matrix.portability_full_closure.json",
    "freeze_report_rel": "config/plans/keyed/portability_full_closure_freeze_report.json",
    "expected": {"invocations": 456, "pairs": 228, "baseline": 228, "target": 228},
    "expected_block_pairs": {"block12": 12, "block13": 36, "block14": 18,
                             "block15": 6, "block16": 144, "block17": 12},
    "expected_run_config_sha256":
        "a5be8f150bc87182d3a158ff580b83a04073a84ff258cde07d78a73e35f60faf",
    # the AUTHORITATIVE live schedule fingerprint from the executed WK2 evidence.
    "expected_matrix_fingerprint":
        "d35708b781f29c0609da6f702b5e11599e10aff5d16a0c5fa1aa0253d079f0ec",
    # these must NOT appear in any closure response (identity isolation): the four
    # prior campaigns primary/secondary/portability/portability_ext.
    "foreign_run_configs": {
        "022fbeb01a8d9d45686e56823eca1e1ef30712f2a13c4a878cb5f7ef0097b5b7",  # primary
        "441609e611a38cb10e1f0a4cfc058991d3b8850d71b83e7092610ee469a58299",  # secondary
        "64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947",  # portability
        "bf504a28fb0ac3cec3b189a4de1f7b8968a35bbd9866c2ae1d5784ccc3bf77da",  # portability_ext
    },
    # POSITIVE coverage gate: the executed target (strategy, workload) cells must
    # equal EXACTLY these 16 WS_ONLY closure cells -- no more, no fewer.
    "expected_target_cells": {
        ("lp_sorted", "native_ycsb_c_read_zipf"), ("lp_shuf", "native_ycsb_c_read_zipf"),
        ("lp_sorted", "native_ycsb_c_read_uniform"), ("lp_shuf", "native_ycsb_c_read_uniform"),
        ("lp_sorted", "native_ycsb_c_hot_hashed_01"), ("lp_shuf", "native_ycsb_c_hot_hashed_01"),
        ("2e_K40", "read_tail_mixed_20k"), ("2e_K92", "read_tail_mixed_20k"),
        ("layers_92", "read_tail_mixed_20k"), ("learned_markov_14", "read_tail_mixed_20k"),
        ("lp_sorted", "read_tail_mixed_20k"), ("lp_shuf", "read_tail_mixed_20k"),
        ("2e_K40", "read_tail_hit_20k"), ("2e_K92", "read_tail_hit_20k"),
        ("lp_sorted", "read_tail_hit_20k"), ("lp_shuf", "read_tail_hit_20k"),
    },
    # structural-static strategies: NOT keyed native plans in the freeze report.
    "static_strategies": {"layers_92"},
    # lp mechanism: synchronous ORDERED pread delivery (never madvise_willneed).
    "lp_strategies": {"lp_sorted", "lp_shuf"},
}

WORKLOAD_FAMILIES = {
    "native_ycsb_c_read_zipf": "YC", "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01", "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit"}


def _closure_columns(columns):
    """Insert block_id after pair_id and delivery_method after delivered_page_count."""
    out = []
    for c in columns:
        out.append(c)
        name = c[0] if isinstance(c, tuple) else c
        if name == "pair_id":
            out.append(("block_id", "S") if isinstance(c, tuple) else "block_id")
        if name == "delivered_page_count":
            out.append(("delivery_method", "R") if isinstance(c, tuple) else "delivery_method")
    return out


FC_INVOCATION_COLUMNS = _closure_columns(INVOCATION_COLUMNS)
FC_INVOCATION_FIELDS = [c for c, _ in FC_INVOCATION_COLUMNS]
FC_PAIR_COLUMNS = _closure_columns(PAIR_COLUMNS)


def parity_type(strategy, reconstructed):
    if strategy in CLOSURE["static_strategies"]:
        return "structural_static"
    return "semantic_contract_reconstruction" if reconstructed else "exact_native_plan"


def load_freeze_index(repo_root):
    """(strategy, workload_id, seed) -> frozen keyed plan record."""
    fr = json.load(open(os.path.join(repo_root, "deployment/openwhisk",
                                     CLOSURE["freeze_report_rel"])))
    idx = {(p["strategy"], p["workload_id"], p["seed"]): p for p in fr["plans"]}
    return fr, idx


def run_gates(rows, pair_rows, schedule, matrix, freeze_idx):
    problems = []
    exp = CLOSURE["expected"]

    n_inv, n_pairs = len(rows), len(pair_rows)
    if n_inv != exp["invocations"]:
        problems.append("invocations %d != %d" % (n_inv, exp["invocations"]))
    if n_pairs != exp["pairs"]:
        problems.append("pairs %d != %d" % (n_pairs, exp["pairs"]))
    sc = Counter(r["strategy"] for r in rows)
    if sc.get("baseline", 0) != exp["baseline"]:
        problems.append("baseline rows %d != %d" % (sc.get("baseline", 0), exp["baseline"]))
    if (n_inv - sc.get("baseline", 0)) != exp["target"]:
        problems.append("target rows %d != %d" % (n_inv - sc.get("baseline", 0), exp["target"]))

    # per-block pair counts (independent of validate_campaign)
    pair_block = {p["pair_id"]: p["block_id"] for p in schedule.get("pairs", [])}
    block_pairs = Counter()
    for pr in pair_rows:
        bid = pair_block.get(pr["pair_id"])
        if bid is None:
            problems.append("pair %s has no block_id" % pr["pair_id"])
        else:
            block_pairs[bid] += 1
    if dict(block_pairs) != CLOSURE["expected_block_pairs"]:
        problems.append("block pair counts %s != %s"
                        % (dict(block_pairs), CLOSURE["expected_block_pairs"]))

    # POSITIVE 16-cell coverage gate: exact target-cell set equality.
    target_cells = {(r["strategy"], r["workload"]) for r in rows if r["strategy"] != "baseline"}
    if target_cells != CLOSURE["expected_target_cells"]:
        missing = CLOSURE["expected_target_cells"] - target_cells
        extra = target_cells - CLOSURE["expected_target_cells"]
        if missing:
            problems.append("closure MISSING target cells: %s" % sorted(missing))
        if extra:
            problems.append("closure UNINTENDED target cells: %s" % sorted(extra))

    # per-row validity + identity isolation + delivery-mechanism gate
    for r in rows:
        pos = r["schedule_position"]
        if r["diagnostic_mode"] is not False:
            problems.append("pos %d diagnostic_mode != false" % pos)
        for f in ("cold_reset_requested", "cold_threshold_passed",
                  "delivery_valid", "measured_valid", "oracle_passed"):
            if r[f] is not True:
                problems.append("pos %d %s != true" % (pos, f))
        if r["error"] or r["error_stage"] or r["sqlite_error"]:
            problems.append("pos %d carries an error field" % pos)
        if r["authoritative_run_config_sha256"] != CLOSURE["expected_run_config_sha256"]:
            problems.append("pos %d run_config != closure a5be8f15" % pos)
        if r["authoritative_run_config_sha256"] in CLOSURE["foreign_run_configs"]:
            problems.append("pos %d run_config leaked a foreign identity" % pos)
        # delivery mechanism: lp => pread_ordered; everything else => madvise_willneed
        dm = r.get("delivery_method")
        if r["strategy"] in CLOSURE["lp_strategies"]:
            if dm != "pread_ordered":
                problems.append("pos %d lp %s delivery_method=%r != pread_ordered"
                                % (pos, r["strategy"], dm))
        else:
            if dm != "madvise_willneed":
                problems.append("pos %d non-lp %s delivery_method=%r != madvise_willneed"
                                % (pos, r["strategy"], dm))

    for field in ("action_image_digest", "artifact_manifest_sha256",
                  "authoritative_run_config_sha256"):
        vals = {r[field] for r in rows}
        if len(vals) != 1:
            problems.append("%s not constant: %s" % (field, sorted(vals)))

    for r in rows:
        strat, wl, seed = r["strategy"], r["workload"], r["seed"]
        if strat == "baseline":
            if r["selected_page_count"] not in (0, None):
                problems.append("baseline pos %d selected_page_count=%r != 0"
                                % (r["schedule_position"], r["selected_page_count"]))
            continue
        if strat in CLOSURE["static_strategies"]:
            if seed != 1:
                problems.append("%s pos %d seed=%s (structural static is seed 1 only)"
                                % (strat, r["schedule_position"], seed))
            if not r["plan_sha256"]:
                problems.append("%s pos %d missing plan_sha256" % (strat, r["schedule_position"]))
            # layers_92 structural invariant: exactly 92 interior, 0 leaf.
            if strat == "layers_92" and (r["selected_interior_count"] != 92
                                         or r["selected_leaf_count"] not in (0, None)):
                problems.append("layers_92 pos %d interior=%r leaf=%r != (92, 0)"
                                % (r["schedule_position"], r["selected_interior_count"],
                                   r["selected_leaf_count"]))
            continue
        fz = freeze_idx.get((strat, wl, seed))
        if fz is None:
            problems.append("pos %d target %s/%s/s%s not in freeze report"
                            % (r["schedule_position"], strat, wl, seed))
            continue
        if r["plan_sha256"] != fz["plan_sha256"]:
            problems.append("pos %d %s plan_sha256 %s != frozen %s"
                            % (r["schedule_position"], strat, r["plan_sha256"], fz["plan_sha256"]))
        for rf, ff in (("selected_page_count", "pages"),
                       ("selected_interior_count", "interior"),
                       ("selected_leaf_count", "leaf")):
            if r[rf] != fz[ff]:
                problems.append("pos %d %s %s=%r != frozen %s=%d"
                                % (r["schedule_position"], strat, rf, r[rf], ff, fz[ff]))
        # 2e reconstruction skeleton invariant: interior==92 (92-page skeleton union).
        if strat in ("2e_K40", "2e_K92") and r["selected_interior_count"] != 92:
            problems.append("pos %d %s interior=%r != 92 (skeleton reconstruction)"
                            % (r["schedule_position"], strat, r["selected_interior_count"]))
        # LOSO leakage: evaluated seed must not appear in its own training set.
        loso = fz.get("loso")
        if isinstance(loso, dict):
            train = loso.get("train_seeds") or loso.get("training_seeds") or []
            if seed in train:
                problems.append("pos %d %s LOSO leak: seed %s in train %s"
                                % (r["schedule_position"], strat, seed, train))

    return problems, dict(block_pairs)


def build_plan_parity(rows, freeze_idx):
    seen = {}
    for r in rows:
        strat, wl, seed = r["strategy"], r["workload"], r["seed"]
        if strat == "baseline":
            continue
        key = (strat, wl, seed)
        if key in seen:
            continue
        if strat in CLOSURE["static_strategies"]:
            seen[key] = {
                "strategy": strat, "workload": wl, "seed": seed,
                "plan_sha256": r["plan_sha256"], "pages": r["selected_page_count"],
                "interior": r["selected_interior_count"], "leaf": r["selected_leaf_count"],
                "delivery_method": r.get("delivery_method"),
                "reconstructed": "static", "loso_test_seed": "",
                "parity_type": parity_type(strat, False),
                "matches_frozen": "static",
            }
            continue
        fz = freeze_idx.get(key, {})
        loso = fz.get("loso")
        seen[key] = {
            "strategy": strat, "workload": wl, "seed": seed,
            "plan_sha256": r["plan_sha256"], "pages": r["selected_page_count"],
            "interior": r["selected_interior_count"], "leaf": r["selected_leaf_count"],
            "delivery_method": r.get("delivery_method"),
            "reconstructed": fz.get("reconstructed"),
            "loso_test_seed": (loso.get("test_seed") if loso else ""),
            "parity_type": parity_type(strat, fz.get("reconstructed", False)),
            "matches_frozen": (r["plan_sha256"] == fz.get("plan_sha256")
                               and r["selected_page_count"] == fz.get("pages")),
        }
    return sorted(seen.values(), key=lambda d: (d["strategy"], d["workload"], d["seed"]))


def normalize(ow_root, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    repo_root = Path(ow_root).parents[1]
    page_size = load_page_size(repo_root)
    problems = []

    evidence_dir = os.path.join(ow_root, CLOSURE["evidence_dir"])
    bundle = CLOSURE["bundle"]
    tar_path = os.path.join(evidence_dir, bundle)
    sidecar = tar_path + ".sha256"

    actual_sha = sha256_file(tar_path)
    sidecar_sha = parse_sidecar(sidecar)
    if actual_sha != sidecar_sha:
        problems.append("bundle sha256 %s != sidecar %s" % (actual_sha, sidecar_sha))

    b = read_bundle(evidence_dir, bundle)
    schedule = json.loads(b["exact"]["05_full_matrix/schedule.json"])
    identity_json = json.loads(b["exact"]["identity.json"])
    bundle_manifest = json.loads(b["exact"]["06_collect/bundle_manifest.json"])
    sched_fp_sidecar = b["exact"]["05_full_matrix/raw/.schedule_fingerprint"].decode().strip()
    status_txt = b["exact"]["05_full_matrix/STATUS"].decode()
    validity_txt = b["exact"]["06_collect/validity_summary.txt"].decode()

    # stage gate: every stage STATUS in the bundle must be PASS.
    status_kv = dict(line.split("=", 1) for line in status_txt.split("\n") if "=" in line)
    if status_kv.get("result") != "PASS":
        problems.append("05_full_matrix STATUS result=%r != PASS" % status_kv.get("result"))
    for line in validity_txt.split("\n"):
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith(("00_", "01_", "02_", "03_", "04_", "05_")):
            if parts[1] != "PASS":
                problems.append("stage %s result=%s != PASS" % (parts[0], parts[1]))

    matrix = json.load(open(os.path.join(ow_root, CLOSURE["matrix_rel"])))
    authoritative_ids = dict(schedule["identity"])

    derived_fp = vs.campaign_fingerprint(matrix, authoritative_ids, schedule["invocations"])
    stored_fp = schedule.get("matrix_fingerprint")
    if derived_fp != stored_fp:
        problems.append("recomputed campaign fingerprint %s != stored %s" % (derived_fp, stored_fp))
    if sched_fp_sidecar != stored_fp:
        problems.append("raw/.schedule_fingerprint %s != schedule.json %s" % (sched_fp_sidecar, stored_fp))
    if stored_fp != CLOSURE["expected_matrix_fingerprint"]:
        problems.append("live fingerprint %s != expected d35708b7..." % stored_fp)

    for pr in vs.validate_campaign(schedule, matrix):
        problems.append("schedule invalid: %s" % pr)

    bm_run_config = bundle_manifest.get("run_config_sha256")
    git_sha = identity_json.get("git_sha")
    rows, rp = build_rows(
        "portability_full_closure", schedule, b["reqs"], b["resps"], authoritative_ids,
        bm_run_config, bundle, actual_sha, git_sha, stored_fp, page_size)
    problems.extend(rp)
    pair_rows, pp = derive_pairs(rows)
    problems.extend(pp)

    # attach block_id (from schedule pairs) and delivery_method (from raw response)
    pair_block = {p["pair_id"]: p["block_id"] for p in schedule.get("pairs", [])}
    for r in rows:
        r["block_id"] = pair_block.get(r["pair_id"])
        resp = b["resps"].get(r["schedule_position"], {})
        r["delivery_method"] = resp.get("delivery_method")
    for pr in pair_rows:
        pr["block_id"] = pair_block.get(pr["pair_id"])

    freeze_report, freeze_idx = load_freeze_index(repo_root)
    gate_problems, block_pairs = run_gates(rows, pair_rows, schedule, matrix, freeze_idx)
    problems.extend(gate_problems)
    plan_parity = build_plan_parity(rows, freeze_idx)

    rows.sort(key=lambda r: r["schedule_position"])
    pair_rows.sort(key=lambda p: min(p["baseline_schedule_position"],
                                     p["target_schedule_position"]))

    inv_path = os.path.join(out_dir, "portability_full_closure_normalized_invocations.csv")
    pair_path = os.path.join(out_dir, "portability_full_closure_normalized_pairs.csv")
    inv_sha = write_csv(inv_path, FC_INVOCATION_FIELDS, rows)
    pair_sha = write_csv(pair_path, FC_PAIR_COLUMNS, pair_rows)

    order_bal = order_balance(rows)
    report = _validation_report(problems, block_pairs, plan_parity, order_bal,
                                actual_sha, sidecar_sha, stored_fp, derived_fp,
                                authoritative_ids, bm_run_config, status_txt,
                                len(rows), len(pair_rows))
    val_path = os.path.join(out_dir, "portability_full_closure_normalization_validation.txt")
    with open(val_path, "w") as f:
        f.write(report)

    ok = not problems
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "campaign": "portability_full_closure",
        "campaign_role": "final_16_cell_workstation_matrix_closure_complement",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "normalizer_git_sha": _git_sha(ow_root),
        "ok": ok,
        "additive_note": (
            "Additive to normalize.py, normalize_portability.py and "
            "normalize_portability_ext.py. The frozen primary/secondary/portability/"
            "portability_ext normalized outputs are untouched; this campaign is a "
            "separate final-closure portability table."),
        "not_a_performance_ranking": True,
        "coverage_claim": (
            "CELL coverage only: OpenWhisk executed all 65 canonical retained "
            "workload x strategy cells at orig layout. NOT protocol replication, "
            "NOT layout completeness, NOT causal performance equivalence."),
        "source_bundle_filename": bundle,
        "source_bundle_sha256": actual_sha,
        "source_bundle_sha256_sidecar": sidecar_sha,
        "sqlite_research_git_sha": git_sha,
        "matrix_fingerprint": stored_fp,
        "matrix_fingerprint_recomputed": derived_fp,
        "authoritative_run_config_sha256": authoritative_ids["run_config_sha256"],
        "artifact_manifest_sha256": authoritative_ids["artifact_manifest_sha256"],
        "action_image_digest": authoritative_ids["action_image_digest"],
        "bundle_manifest_run_config_sha256": bm_run_config,
        "bound_db_sha256": freeze_report["bound_db_sha256"],
        "classifier_sha256": freeze_report["classifier_sha256"],
        "lp_shuf_seed": freeze_report.get("lp_shuf_seed"),
        "status": status_kv,
        "counts": {"invocations": len(rows), "pairs": len(pair_rows),
                   "baseline": sum(1 for r in rows if r["strategy"] == "baseline"),
                   "target": sum(1 for r in rows if r["strategy"] != "baseline")},
        "block_pairs": block_pairs,
        "target_cell_count": len(CLOSURE["expected_target_cells"]),
        "workload_families": WORKLOAD_FAMILIES,
        "parity_type_counts": dict(Counter(p["parity_type"] for p in plan_parity)),
        "delivery_method_counts": dict(Counter(r["delivery_method"] for r in rows)),
        "page_size": page_size,
        "column_categories": {
            "legend": {"P": "provenance", "S": "raw schedule/request identity",
                       "R": "raw response field (verbatim)", "D": "derived bookkeeping"},
            "invocation_columns": {c: cat for c, cat in FC_INVOCATION_COLUMNS},
        },
        "outputs": {
            "portability_full_closure_normalized_invocations.csv": {"rows": len(rows), "sha256": inv_sha},
            "portability_full_closure_normalized_pairs.csv": {"rows": len(pair_rows), "sha256": pair_sha},
            "portability_full_closure_normalization_validation.txt": {
                "sha256": hashlib.sha256(report.encode()).hexdigest()},
        },
        "canonical_row_order": "schedule_position (single batch)",
    }
    man_path = os.path.join(out_dir, "portability_full_closure_normalization_manifest.json")
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return ok, manifest, plan_parity


def _validation_report(problems, block_pairs, plan_parity, order_bal,
                       actual_sha, sidecar_sha, stored_fp, derived_fp,
                       ids, bm_run_config, status_txt, n_inv, n_pairs):
    L = []
    L.append("# OpenWhisk WK1 PORTABILITY-FULL-CLOSURE normalization — validation report")
    L.append("")
    L.append("overall: %s" % ("PASS" if not problems else "FAIL"))
    L.append("role: final 16-cell workstation-matrix closure complement "
             "(CELL coverage only; NOT a performance ranking; native/WK1 remains primary)")
    L.append("")
    L.append("## totals")
    L.append("invocations: %d (expected 456)" % n_inv)
    L.append("pairs: %d (expected 228)" % n_pairs)
    L.append("block_pairs: %s (expected {block12:12, block13:36, block14:18, "
             "block15:6, block16:144, block17:12})"
             % json.dumps(block_pairs, sort_keys=True))
    L.append("")
    L.append("## identity")
    L.append("bundle_sha256: %s (sidecar=%s, match=%s)"
             % (actual_sha, sidecar_sha, actual_sha == sidecar_sha))
    L.append("matrix_fingerprint: %s (recomputed=%s, match=%s)"
             % (stored_fp, derived_fp, stored_fp == derived_fp))
    L.append("run_config_sha256: %s" % ids["run_config_sha256"])
    L.append("artifact_manifest_sha256: %s" % ids["artifact_manifest_sha256"])
    L.append("action_image_digest: %s" % ids["action_image_digest"])
    L.append("bundle_manifest_run_config_sha256: %s" % bm_run_config)
    for line in status_txt.split("\n"):
        if line.strip():
            L.append("status.%s" % line.strip())
    L.append("")
    L.append("## plan parity (per executed target plan; parity_type per taxonomy)")
    for p in plan_parity:
        L.append("%-17s %-30s s%s  pages=%s int=%s leaf=%s  deliver=%s  %s  matches_frozen=%s"
                 % (p["strategy"], p["workload"], p["seed"], p["pages"],
                    p["interior"], p["leaf"], p["delivery_method"],
                    p["parity_type"], p["matches_frozen"]))
    L.append("")
    L.append("## pair-order structural balance (integrity only; NOT performance)")
    for gk in sorted(order_bal, key=lambda k: (k[0], str(k[1]), str(k[2]))):
        c = order_bal[gk]
        L.append("%s | %s | %s : baseline_first=%d target_first=%d"
                 % (gk[0], gk[1], gk[2], c["baseline_first"], c["target_first"]))
    L.append("")
    L.append("## fail-closed problems (%d)" % len(problems))
    if not problems:
        L.append("(none — all gates passed)")
    else:
        for p in problems[:500]:
            L.append("FAIL %s" % p)
    L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ow-root", default=str(_OW_ROOT))
    ap.add_argument("--out", default=str(_OW_ROOT / "analysis" / "normalized" / "portability_full_closure"))
    a = ap.parse_args()
    ok, manifest, _ = normalize(a.ow_root, a.out)
    print("portability_full_closure normalization %s: %d invocations, %d pairs -> %s"
          % ("PASS" if ok else "FAIL", manifest["counts"]["invocations"],
             manifest["counts"]["pairs"], a.out))
    if not ok:
        print("FAILED gates — see portability_full_closure_normalization_validation.txt", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
