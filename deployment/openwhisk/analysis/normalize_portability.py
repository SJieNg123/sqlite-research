#!/usr/bin/env python3
"""WK1-side normalizer for the completed OpenWhisk cross-workload PORTABILITY campaign.

Additive sibling of normalize.py. The portability campaign is a SINGLE-BATCH
block-union matrix (234 pairs / 468 invocations) that deploys representative
strategy mechanisms across FIVE workload families (YC, YCu, YCh01, C, C_hit). It
is a DEPLOYMENT / cross-workload PORTABILITY complement — it validates execution,
correctness, workload binding, plan binding, semantic parity, selected-page
footprint, and cost observability. It is NOT a performance ranking and asserts no
latency agreement, ranking equality, or warm paired speedup. Native/WK1 remains
the primary controlled performance evidence.

Because the campaign is a non-rectangular block union (2d only on seed 1, distinct
target sets per block), it does NOT fit normalize.py's rectangular
primary/secondary contract gates. This module therefore gets its own driver +
fail-closed gates + outputs, while REUSING normalize.py's canonical invocation /
pair schema and row builders UNCHANGED. The frozen primary/secondary normalized
outputs (normalized_invocations.csv, normalized_pairs.csv) are never touched.

Structural block gates (per-block rectangularity, cross-block disjoint union, no
unintended cross-product cell, exact grand totals, pair integrity, unique +
contiguous positions) are delegated to client/validate_schedule.validate_campaign
and the single live campaign_fingerprint. This module adds: block_id provenance,
the per-response validity gate, plan/workload parity against the frozen keyed
contract (config/plans/keyed/portability_freeze_report.json), the forbidden-cell
guard, baseline-zero-prefetch, and 2d structural-static (seed 1 only).

Outputs (under --out, default deployment/openwhisk/analysis/normalized/portability/):
  portability_normalized_invocations.csv   468 rows (canonical schema + block_id)
  portability_normalized_pairs.csv         234 rows (canonical pair schema + block_id)
  portability_normalization_manifest.json  identities, counts, plan-parity, SHAs
  portability_normalization_validation.txt every fail-closed gate result
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]                      # deployment/openwhisk
_REPO_ROOT = _HERE.parents[3]                    # repo root
sys.path.insert(0, str(_OW_ROOT / "client"))
sys.path.insert(0, str(_OW_ROOT / "analysis"))
import validate_schedule as vs                   # noqa: E402
# reuse the canonical schema + row builders unchanged
from normalize import (                          # noqa: E402
    INVOCATION_COLUMNS, INVOCATION_FIELDS, PAIR_COLUMNS,
    sha256_file, parse_sidecar, read_bundle, build_rows, derive_pairs,
    order_balance, write_csv, load_page_size, _git_sha,
)

SCHEMA_VERSION = 1

# ---- portability campaign registry (single batch) --------------------------
PORTABILITY = {
    "campaign": "portability",
    "evidence_dir": "evidence/portability/29e1585ce956",
    "bundle": "ws2_bundle_29e1585ce956_20260827T135734Z.tar.gz",
    "matrix_rel": "ws2/matrix.portability.json",
    "freeze_report_rel": "config/plans/keyed/portability_freeze_report.json",
    # fail-closed identity + shape expectations (independently rederived below)
    "expected": {"invocations": 468, "pairs": 234, "baseline": 234, "target": 234},
    "expected_block_pairs": {"block1": 108, "block2": 72, "block3": 36, "block4": 18},
    "expected_run_config_sha256":
        "64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947",
    "expected_matrix_fingerprint":
        "a3274bc9632ab7aa393f015c00829373a33312d15ff8e6521759255f01eac10e",
    # these must NOT appear in any portability response (identity isolation)
    "foreign_run_configs": {
        "022fbeb01a8d9d45686e56823eca1e1ef30712f2a13c4a878cb5f7ef0097b5b7",  # primary
        "441609e611a38cb10e1f0a4cfc058991d3b8850d71b83e7092610ee469a58299",  # secondary
    },
    # deployment-contract cells that must NOT appear (would be unintended product)
    "forbidden_cells": [("2f_top28", "read_tail_mixed_20k"),
                        ("2e_K10", "native_ycsb_c_read_zipf")],
    # 2d is structural-static: it is NOT a keyed native plan in the freeze report
    "static_strategies": {"2d"},
}

# block_id is portability-schedule identity (category S). Insert it right after
# pair_id so the canonical column order is otherwise byte-identical to normalize.py.
def _with_block_id(columns):
    out = []
    for c in columns:
        out.append(c)
        if (isinstance(c, tuple) and c[0] == "pair_id") or c == "pair_id":
            out.append(("block_id", "S") if isinstance(c, tuple) else "block_id")
    return out

PORT_INVOCATION_COLUMNS = _with_block_id(INVOCATION_COLUMNS)
PORT_INVOCATION_FIELDS = [c for c, _ in PORT_INVOCATION_COLUMNS]
PORT_PAIR_COLUMNS = _with_block_id(PAIR_COLUMNS)

# parity_type taxonomy (§8): 2e_K10 reconstructed=True is the canonical 2e
# semantic contract (92-interior skeleton U per-seed top-10 leaves), NOT a
# byte-for-byte raw-native plan. 2d is structural static. Everything else is an
# exact frozen native plan.
def parity_type(strategy, reconstructed):
    if strategy in PORTABILITY["static_strategies"]:
        return "structural_static"
    return "semantic_contract_reconstruction" if reconstructed else "exact_native_plan"


def load_freeze_index(repo_root):
    """(strategy, workload_id, seed) -> frozen keyed plan record."""
    fr = json.load(open(os.path.join(repo_root, "deployment/openwhisk",
                                     PORTABILITY["freeze_report_rel"])))
    idx = {(p["strategy"], p["workload_id"], p["seed"]): p for p in fr["plans"]}
    return fr, idx


# ---------------------------------------------------------------------------
# portability-specific fail-closed gates (structural block gates are delegated
# to validate_schedule.validate_campaign; these add validity + plan parity)
# ---------------------------------------------------------------------------
def run_portability_gates(rows, pair_rows, schedule, matrix, freeze_idx):
    problems = []
    exp = PORTABILITY["expected"]

    # 1) grand totals
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

    # 2) block_id assignment + per-block pair counts (108/72/36/18)
    pair_block = {p["pair_id"]: p["block_id"] for p in schedule.get("pairs", [])}
    block_pairs = Counter()
    for pr in pair_rows:
        bid = pair_block.get(pr["pair_id"])
        if bid is None:
            problems.append("pair %s has no block_id" % pr["pair_id"])
        else:
            block_pairs[bid] += 1
    if dict(block_pairs) != PORTABILITY["expected_block_pairs"]:
        problems.append("block pair counts %s != %s"
                        % (dict(block_pairs), PORTABILITY["expected_block_pairs"]))

    # 3) forbidden (unintended) cells absent
    target_wl = {(r["strategy"], r["workload"]) for r in rows if r["strategy"] != "baseline"}
    for cell in PORTABILITY["forbidden_cells"]:
        if cell in target_wl:
            problems.append("FORBIDDEN cell present: %s" % (cell,))

    # 4) per-response validity gates + identity isolation
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
        if r["authoritative_run_config_sha256"] != PORTABILITY["expected_run_config_sha256"]:
            problems.append("pos %d run_config != portability 64f44c3e" % pos)
        if r["authoritative_run_config_sha256"] in PORTABILITY["foreign_run_configs"]:
            problems.append("pos %d run_config leaked a foreign identity" % pos)

    # 5) constant image / manifest / run_config across the whole campaign
    for field in ("action_image_digest", "artifact_manifest_sha256",
                  "authoritative_run_config_sha256"):
        vals = {r[field] for r in rows}
        if len(vals) != 1:
            problems.append("%s not constant: %s" % (field, sorted(vals)))

    # 6) plan / workload parity vs the frozen keyed contract (§7) + baseline zero
    for r in rows:
        strat, wl, seed = r["strategy"], r["workload"], r["seed"]
        if strat == "baseline":
            if r["selected_page_count"] not in (0, None):
                problems.append("baseline pos %d selected_page_count=%r != 0"
                                % (r["schedule_position"], r["selected_page_count"]))
            continue
        if strat in PORTABILITY["static_strategies"]:
            if seed != 1:
                problems.append("2d pos %d seed=%s (structural static is seed 1 only)"
                                % (r["schedule_position"], seed))
            if not r["plan_sha256"]:
                problems.append("2d pos %d missing plan_sha256" % r["schedule_position"])
            continue
        fz = freeze_idx.get((strat, wl, seed))
        if fz is None:
            problems.append("pos %d target %s/%s/s%s not in freeze report"
                            % (r["schedule_position"], strat, wl, seed))
            continue
        # plan_sha256 is the content hash of the page_number,file_offset plan, so a
        # match proves the selected page SET + offset mapping, not merely the count.
        if r["plan_sha256"] != fz["plan_sha256"]:
            problems.append("pos %d %s plan_sha256 %s != frozen %s"
                            % (r["schedule_position"], strat, r["plan_sha256"], fz["plan_sha256"]))
        for rf, ff in (("selected_page_count", "pages"),
                       ("selected_interior_count", "interior"),
                       ("selected_leaf_count", "leaf")):
            if r[rf] != fz[ff]:
                problems.append("pos %d %s %s=%r != frozen %s=%d"
                                % (r["schedule_position"], strat, rf, r[rf], ff, fz[ff]))

    return problems, dict(block_pairs)


def build_plan_parity(rows, freeze_idx):
    """One parity record per distinct (strategy, workload, seed) target plan
    actually executed. Descriptive; carries parity_type + reconstruction flag."""
    seen = {}
    for r in rows:
        strat, wl, seed = r["strategy"], r["workload"], r["seed"]
        if strat == "baseline":
            continue
        key = (strat, wl, seed)
        if key in seen:
            continue
        if strat in PORTABILITY["static_strategies"]:
            seen[key] = {
                "strategy": strat, "workload": wl, "seed": seed,
                "plan_sha256": r["plan_sha256"], "pages": r["selected_page_count"],
                "interior": r["selected_interior_count"], "leaf": r["selected_leaf_count"],
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
            "reconstructed": fz.get("reconstructed"),
            "loso_test_seed": (loso.get("test_seed") if loso else ""),
            "parity_type": parity_type(strat, fz.get("reconstructed", False)),
            "matches_frozen": (r["plan_sha256"] == fz.get("plan_sha256")
                               and r["selected_page_count"] == fz.get("pages")),
        }
    return sorted(seen.values(), key=lambda d: (d["strategy"], d["workload"], d["seed"]))


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def normalize_portability(ow_root, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    repo_root = Path(ow_root).parents[1]
    page_size = load_page_size(repo_root)
    problems = []

    evidence_dir = os.path.join(ow_root, PORTABILITY["evidence_dir"])
    bundle = PORTABILITY["bundle"]
    tar_path = os.path.join(evidence_dir, bundle)
    sidecar = tar_path + ".sha256"

    # 1) sha256-verify the immutable bundle before reading it
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

    matrix = json.load(open(os.path.join(ow_root, PORTABILITY["matrix_rel"])))
    authoritative_ids = dict(schedule["identity"])

    # 2) single live campaign fingerprint (identity+seed+blocks+ordered schedule)
    derived_fp = vs.campaign_fingerprint(matrix, authoritative_ids, schedule["invocations"])
    stored_fp = schedule.get("matrix_fingerprint")
    if derived_fp != stored_fp:
        problems.append("recomputed campaign fingerprint %s != stored %s" % (derived_fp, stored_fp))
    if sched_fp_sidecar != stored_fp:
        problems.append("raw/.schedule_fingerprint %s != schedule.json %s" % (sched_fp_sidecar, stored_fp))
    if stored_fp != PORTABILITY["expected_matrix_fingerprint"]:
        problems.append("live fingerprint %s != expected a3274bc9..." % stored_fp)

    # 3) delegate the structural block gates to validate_campaign
    for pr in vs.validate_campaign(schedule, matrix):
        problems.append("schedule invalid: %s" % pr)

    # 4) canonical rows + pairs (reused builders, unchanged)
    bm_run_config = bundle_manifest.get("run_config_sha256")
    git_sha = identity_json.get("git_sha")
    rows, rp = build_rows(
        "portability", schedule, b["reqs"], b["resps"], authoritative_ids,
        bm_run_config, bundle, actual_sha, git_sha, stored_fp, page_size)
    problems.extend(rp)
    pair_rows, pp = derive_pairs(rows)
    problems.extend(pp)

    # 5) attach block_id provenance to every row + pair
    pair_block = {p["pair_id"]: p["block_id"] for p in schedule.get("pairs", [])}
    for r in rows:
        r["block_id"] = pair_block.get(r["pair_id"])
    for pr in pair_rows:
        pr["block_id"] = pair_block.get(pr["pair_id"])

    # 6) portability-specific gates + plan parity
    freeze_report, freeze_idx = load_freeze_index(repo_root)
    gate_problems, block_pairs = run_portability_gates(
        rows, pair_rows, schedule, matrix, freeze_idx)
    problems.extend(gate_problems)
    plan_parity = build_plan_parity(rows, freeze_idx)

    # deterministic order: schedule_position (campaign is a single batch)
    rows.sort(key=lambda r: r["schedule_position"])
    pair_rows.sort(key=lambda p: min(p["baseline_schedule_position"],
                                     p["target_schedule_position"]))

    inv_path = os.path.join(out_dir, "portability_normalized_invocations.csv")
    pair_path = os.path.join(out_dir, "portability_normalized_pairs.csv")
    inv_sha = write_csv(inv_path, PORT_INVOCATION_FIELDS, rows)
    pair_sha = write_csv(pair_path, PORT_PAIR_COLUMNS, pair_rows)

    order_bal = order_balance(rows)
    report = _validation_report(problems, block_pairs, plan_parity, order_bal,
                                actual_sha, sidecar_sha, stored_fp, derived_fp,
                                authoritative_ids, bm_run_config, status_txt,
                                len(rows), len(pair_rows))
    val_path = os.path.join(out_dir, "portability_normalization_validation.txt")
    with open(val_path, "w") as f:
        f.write(report)

    ok = not problems
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "campaign": "portability",
        "campaign_role": "cross_workload_deployment_portability_complement",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "normalizer_git_sha": _git_sha(ow_root),
        "ok": ok,
        "additive_note": (
            "Additive to normalize.py. The frozen primary/secondary normalized "
            "outputs are untouched; this campaign is a separate portability table."),
        "not_a_performance_ranking": True,
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
        "status": dict(line.split("=", 1) for line in status_txt.split("\n") if "=" in line),
        "counts": {"invocations": len(rows), "pairs": len(pair_rows),
                   "baseline": sum(1 for r in rows if r["strategy"] == "baseline"),
                   "target": sum(1 for r in rows if r["strategy"] != "baseline")},
        "block_pairs": block_pairs,
        "workload_families": {
            "native_ycsb_c_read_zipf": "YC", "native_ycsb_c_read_uniform": "YCu",
            "native_ycsb_c_hot_hashed_01": "YCh01", "read_tail_mixed_20k": "C",
            "read_tail_hit_20k": "C_hit"},
        "parity_type_counts": dict(Counter(p["parity_type"] for p in plan_parity)),
        "page_size": page_size,
        "column_categories": {
            "legend": {"P": "provenance", "S": "raw schedule/request identity",
                       "R": "raw response field (verbatim)", "D": "derived bookkeeping"},
            "invocation_columns": {c: cat for c, cat in PORT_INVOCATION_COLUMNS},
        },
        "outputs": {
            "portability_normalized_invocations.csv": {"rows": len(rows), "sha256": inv_sha},
            "portability_normalized_pairs.csv": {"rows": len(pair_rows), "sha256": pair_sha},
            "portability_normalization_validation.txt": {
                "sha256": hashlib.sha256(report.encode()).hexdigest()},
        },
        "canonical_row_order": "schedule_position (single batch)",
    }
    man_path = os.path.join(out_dir, "portability_normalization_manifest.json")
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return ok, manifest, plan_parity


def _validation_report(problems, block_pairs, plan_parity, order_bal,
                       actual_sha, sidecar_sha, stored_fp, derived_fp,
                       ids, bm_run_config, status_txt, n_inv, n_pairs):
    L = []
    L.append("# OpenWhisk WK1 PORTABILITY normalization — validation report")
    L.append("")
    L.append("overall: %s" % ("PASS" if not problems else "FAIL"))
    L.append("role: cross-workload deployment portability complement "
             "(NOT a performance ranking; native/WK1 remains primary)")
    L.append("")
    L.append("## totals")
    L.append("invocations: %d (expected 468)" % n_inv)
    L.append("pairs: %d (expected 234)" % n_pairs)
    L.append("block_pairs: %s (expected {block1:108, block2:72, block3:36, block4:18})"
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
    L.append("## plan parity (per executed target plan; parity_type per §8)")
    for p in plan_parity:
        L.append("%-17s %-30s s%s  pages=%s int=%s leaf=%s  %s  matches_frozen=%s"
                 % (p["strategy"], p["workload"], p["seed"], p["pages"],
                    p["interior"], p["leaf"], p["parity_type"], p["matches_frozen"]))
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
    ap.add_argument("--out", default=str(_OW_ROOT / "analysis" / "normalized" / "portability"))
    a = ap.parse_args()
    ok, manifest, _ = normalize_portability(a.ow_root, a.out)
    print("portability normalization %s: %d invocations, %d pairs -> %s"
          % ("PASS" if ok else "FAIL", manifest["counts"]["invocations"],
             manifest["counts"]["pairs"], a.out))
    if not ok:
        print("FAILED gates — see portability_normalization_validation.txt", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
