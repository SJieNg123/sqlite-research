#!/usr/bin/env python3
"""WK1-side normalizer for the OpenWhisk YCH01 TWO-CELL FOLLOW-UP campaign.

Additive sibling of normalize_portability{,_ext,_full_closure,_outlier_replication}.py. The
portability_ych01_followup campaign is the SEVENTH independent OpenWhisk campaign and a
targeted SIGN / STABILITY check -- NOT new coverage and NOT a seventh pooled performance
estimator. It re-runs, under EXACT position balance (18 baseline-first / 18 target-first for
the single static cell; 6 / 6 per 2f_top14 seed) and STANDALONE handles only, the ONLY two
workstation<->OpenWhisk cells whose LATEST workstation first-query effect is positive but
OpenWhisk is non-positive:

    YCh01 / layers_5   (native_ycsb_c_hot_hashed_01)  -- R_ws +0.025 (neutral+), R_ow -0.243
    YCh01 / 2f_top14   (native_ycsb_c_hot_hashed_01)  -- R_ws +0.214, R_ow -0.019 (near zero)

Its purpose is to test whether those two discrepancies are STABLE under a fresh independent
batch with exactly balanced within-pair position. The previously observed direction is
described ONLY as a pair-position / short-lived execution-state / execution-storage-state
effect; NO specific physical mechanism is attributed, and the -0.019 2f_top14 value is a
NEAR-ZERO result, NOT a strong harmful effect. This module asserts structural gates only; it
does NOT compute or assert any effectiveness magnitude, and does NOT replace the original
OR / ext R_ow values. Native/WK1 remains the primary controlled performance/mechanism evidence.

Design mirrors the sibling normalizers EXACTLY: the frozen primary, secondary, portability
(64f44c3e), portability_ext (bf504a28), portability_full_closure (a5be8f15) and
portability_outlier_replication (a564770a) normalized outputs are never touched; this
campaign gets its own separate table under analysis/normalized/portability_ych01_followup/.
Structural block gates are delegated to client/validate_schedule.validate_campaign + the
single live campaign_fingerprint. This module adds: block_id provenance, the per-response
validity gate, plan/workload parity for the keyed 2f_top14 cell against the frozen
portability_ext report, the POSITIVE exact two-cell coverage gate, the delivery-mechanism
gate (every arm MUST report "madvise_willneed"; this campaign has no lp cell), baseline-zero-
prefetch, the static seed-1-only rule, and -- the scientific point of the campaign -- the
EXACT PER-CELL / PER-SEED POSITION-BALANCE hard gate.

The evidence bundle for this campaign is produced on WK2. Until then the three post-run
identity fields (evidence_dir, bundle, expected_matrix_fingerprint) are None and normalize()
FAILS LOUD if invoked -- it is authored on WK1 but only runs once WK2 evidence exists.

Outputs (under --out, default analysis/normalized/portability_ych01_followup/):
  portability_ych01_followup_normalized_invocations.csv  144 rows (+block_id +delivery_method)
  portability_ych01_followup_normalized_pairs.csv         72 rows (+block_id)
  portability_ych01_followup_normalization_manifest.json  identities, counts, parity, balance, SHAs
  portability_ych01_followup_normalization_validation.txt every fail-closed gate result
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
from normalize import (                          # noqa: E402
    INVOCATION_COLUMNS, PAIR_COLUMNS,
    sha256_file, parse_sidecar, read_bundle, build_rows, derive_pairs,
    order_balance, write_csv, load_page_size, _git_sha,
)

SCHEMA_VERSION = 1

# workload id
YCH01 = "native_ycsb_c_hot_hashed_01"

# ---- portability_ych01_followup campaign registry (single batch) -------------
FU = {
    "campaign": "portability_ych01_followup",
    # POST-WK2 fields: filled from the produced evidence bundle after the matrix runs.
    # Left None on WK1 so normalize() fails loud rather than silently normalizing nothing.
    "evidence_dir": None,     # e.g. "evidence/portability_ych01_followup/<evidence_hash>"
    "bundle": None,           # e.g. "ws2_bundle_<hash>_<ts>.tar.gz"
    "expected_matrix_fingerprint": None,  # depends on the WK2 image identity
    "matrix_rel": "ws2/matrix.portability_ych01_followup.json",
    # the keyed 2f_top14 plans reuse the AUDITED portability_ext freeze report.
    "keyed_freeze_report_rel": "config/plans/keyed/portability_ext_freeze_report.json",
    "expected": {"invocations": 144, "pairs": 72, "baseline": 72, "target": 72},
    "expected_block_pairs": {"Y1": 36, "Y2": 36},
    "expected_run_config_sha256":
        "7a3cc45d7fac26e90315b3e16cec320c48210da475d42819b8253ec53ab60437",
    "expected_schedule_seed": 20260901,
    # identity isolation: NONE of the six prior campaigns may appear in any response.
    "foreign_run_configs": {
        "022fbeb01a8d9d45686e56823eca1e1ef30712f2a13c4a878cb5f7ef0097b5b7",  # primary
        "441609e611a38cb10e1f0a4cfc058991d3b8850d71b83e7092610ee469a58299",  # secondary
        "64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947",  # portability
        "bf504a28fb0ac3cec3b189a4de1f7b8968a35bbd9866c2ae1d5784ccc3bf77da",  # portability_ext
        "a5be8f150bc87182d3a158ff580b83a04073a84ff258cde07d78a73e35f60faf",  # full_closure
        "a564770aa39a33485a95afe6e49d95d9143ef70ffe88640673cf40bc7a3ed46b",  # outlier_replication
    },
    # POSITIVE exact two-cell coverage gate: executed target (strategy, workload) cells must
    # equal EXACTLY these two -- no more, no fewer.
    "expected_target_cells": {
        ("layers_5", YCH01),
        ("2f_top14", YCH01),
    },
    # structural-static strategies: NOT keyed native plans (inline structural offsets).
    "static_strategies": {"layers_5"},
    "keyed_strategies": {"2f_top14"},
    # exact position balance: the scientific point of this follow-up.
    #   (strategy, workload, seed) -> (baseline_first, target_first) required.
    "expected_position_balance": {
        ("layers_5", YCH01, 1): (18, 18),
        ("2f_top14", YCH01, 1): (6, 6),
        ("2f_top14", YCH01, 2): (6, 6),
        ("2f_top14", YCH01, 3): (6, 6),
    },
}

WORKLOAD_FAMILIES = {
    "native_ycsb_c_read_zipf": "YC", "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01", "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit"}


def _fu_columns(columns):
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


FU_INVOCATION_COLUMNS = _fu_columns(INVOCATION_COLUMNS)
FU_INVOCATION_FIELDS = [c for c, _ in FU_INVOCATION_COLUMNS]
FU_PAIR_COLUMNS = _fu_columns(PAIR_COLUMNS)


def parity_type(strategy, reconstructed):
    if strategy in FU["static_strategies"]:
        return "structural_static"
    return "semantic_contract_reconstruction" if reconstructed else "exact_native_plan"


def load_keyed_freeze_index(repo_root):
    """(strategy, workload_id, seed) -> frozen keyed plan record (portability_ext report)."""
    fr = json.load(open(os.path.join(repo_root, "deployment/openwhisk",
                                     FU["keyed_freeze_report_rel"])))
    idx = {(p["strategy"], p["workload_id"], p["seed"]): p for p in fr["plans"]}
    return fr, idx


def cell_position_balance(rows):
    """(strategy, workload, seed) -> {baseline_first, target_first}, one count per pair."""
    seen = set()
    bal = defaultdict(lambda: {"baseline_first": 0, "target_first": 0})
    for r in rows:
        if r["strategy"] == "baseline":
            continue
        key = (r["campaign"], r["pair_id"])
        if key in seen:
            continue
        seen.add(key)
        cell = (r["strategy"], r["workload"], r["seed"])
        if r["pair_first_strategy"] == "baseline":
            bal[cell]["baseline_first"] += 1
        else:
            bal[cell]["target_first"] += 1
    return bal


def run_gates(rows, pair_rows, schedule, matrix, keyed_idx):
    problems = []
    exp = FU["expected"]

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

    # handle-mode gate: STANDALONE ONLY (no warm arm in this follow-up).
    hm = {r["handle_mode"] for r in rows}
    if hm != {"standalone"}:
        problems.append("handle modes %s != {standalone} (follow-up is standalone only)" % sorted(hm))

    # schedule_seed gate.
    if schedule.get("schedule_seed") != FU["expected_schedule_seed"]:
        problems.append("schedule_seed %r != %d"
                        % (schedule.get("schedule_seed"), FU["expected_schedule_seed"]))

    # per-block pair counts (independent of validate_campaign)
    pair_block = {p["pair_id"]: p["block_id"] for p in schedule.get("pairs", [])}
    block_pairs = Counter()
    for pr in pair_rows:
        bid = pair_block.get(pr["pair_id"])
        if bid is None:
            problems.append("pair %s has no block_id" % pr["pair_id"])
        else:
            block_pairs[bid] += 1
    if dict(block_pairs) != FU["expected_block_pairs"]:
        problems.append("block pair counts %s != %s"
                        % (dict(block_pairs), FU["expected_block_pairs"]))

    # POSITIVE exact two-cell coverage gate.
    target_cells = {(r["strategy"], r["workload"]) for r in rows if r["strategy"] != "baseline"}
    if target_cells != FU["expected_target_cells"]:
        missing = FU["expected_target_cells"] - target_cells
        extra = target_cells - FU["expected_target_cells"]
        if missing:
            problems.append("follow-up MISSING target cells: %s" % sorted(missing))
        if extra:
            problems.append("follow-up UNINTENDED target cells: %s" % sorted(extra))

    # EXACT PER-CELL / PER-SEED POSITION-BALANCE hard gate (scientific point).
    bal = cell_position_balance(rows)
    got_balance = {k: (v["baseline_first"], v["target_first"]) for k, v in bal.items()}
    for cell, want in FU["expected_position_balance"].items():
        got = got_balance.get(cell)
        if got != want:
            problems.append("position balance %s = %s != required %s"
                            % ("/".join(map(str, cell)), got, want))
    for cell in got_balance:
        if cell not in FU["expected_position_balance"]:
            problems.append("unexpected balanced cell %s" % ("/".join(map(str, cell))))

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
        if r["authoritative_run_config_sha256"] != FU["expected_run_config_sha256"]:
            problems.append("pos %d run_config != follow-up 7a3cc45d" % pos)
        if r["authoritative_run_config_sha256"] in FU["foreign_run_configs"]:
            problems.append("pos %d run_config leaked a foreign identity" % pos)
        # delivery mechanism: every arm madvise_willneed (no lp cell here).
        dm = r.get("delivery_method")
        if dm != "madvise_willneed":
            problems.append("pos %d %s delivery_method=%r != madvise_willneed"
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
        if strat in FU["static_strategies"]:
            if seed != 1:
                problems.append("%s pos %d seed=%s (structural static is seed 1 only)"
                                % (strat, r["schedule_position"], seed))
            if not r["plan_sha256"]:
                problems.append("%s pos %d missing plan_sha256" % (strat, r["schedule_position"]))
            continue
        # keyed 2f_top14: parity against the frozen portability_ext report. NOT a 92-page
        # skeleton reconstruction -- it is a 14-page freqdump-ranked partial (interior==14),
        # so only exact-value parity is asserted (no interior==92 invariant).
        fz = keyed_idx.get((strat, wl, seed))
        if fz is None:
            problems.append("pos %d target %s/%s/s%s not in portability_ext freeze report"
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

    return problems, dict(block_pairs), got_balance


def build_plan_parity(rows, keyed_idx):
    seen = {}
    for r in rows:
        strat, wl, seed = r["strategy"], r["workload"], r["seed"]
        if strat == "baseline":
            continue
        key = (strat, wl, seed)
        if key in seen:
            continue
        if strat in FU["static_strategies"]:
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
        fz = keyed_idx.get(key, {})
        seen[key] = {
            "strategy": strat, "workload": wl, "seed": seed,
            "plan_sha256": r["plan_sha256"], "pages": r["selected_page_count"],
            "interior": r["selected_interior_count"], "leaf": r["selected_leaf_count"],
            "delivery_method": r.get("delivery_method"),
            "reconstructed": fz.get("reconstructed"),
            "loso_test_seed": "",
            "parity_type": parity_type(strat, fz.get("reconstructed", False)),
            "matches_frozen": (r["plan_sha256"] == fz.get("plan_sha256")
                               and r["selected_page_count"] == fz.get("pages")),
        }
    return sorted(seen.values(), key=lambda d: (d["strategy"], d["workload"], d["seed"]))


def normalize(ow_root, out_dir):
    if FU["evidence_dir"] is None or FU["bundle"] is None \
            or FU["expected_matrix_fingerprint"] is None:
        raise SystemExit(
            "portability_ych01_followup evidence not wired yet: fill FU['evidence_dir'], "
            "FU['bundle'] and FU['expected_matrix_fingerprint'] from the WK2 bundle before "
            "normalizing (this normalizer is authored on WK1; it runs after WK2 produces the "
            "evidence).")
    os.makedirs(out_dir, exist_ok=True)
    repo_root = Path(ow_root).parents[1]
    page_size = load_page_size(repo_root)
    problems = []

    evidence_dir = os.path.join(ow_root, FU["evidence_dir"])
    bundle = FU["bundle"]
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

    matrix = json.load(open(os.path.join(ow_root, FU["matrix_rel"])))
    authoritative_ids = dict(schedule["identity"])

    derived_fp = vs.campaign_fingerprint(matrix, authoritative_ids, schedule["invocations"])
    stored_fp = schedule.get("matrix_fingerprint")
    if derived_fp != stored_fp:
        problems.append("recomputed campaign fingerprint %s != stored %s" % (derived_fp, stored_fp))
    if sched_fp_sidecar != stored_fp:
        problems.append("raw/.schedule_fingerprint %s != schedule.json %s" % (sched_fp_sidecar, stored_fp))
    if stored_fp != FU["expected_matrix_fingerprint"]:
        problems.append("live fingerprint %s != expected %s" % (stored_fp, FU["expected_matrix_fingerprint"]))

    for pr in vs.validate_campaign(schedule, matrix):
        problems.append("schedule invalid: %s" % pr)

    bm_run_config = bundle_manifest.get("run_config_sha256")
    git_sha = identity_json.get("git_sha")
    rows, rp = build_rows(
        "portability_ych01_followup", schedule, b["reqs"], b["resps"], authoritative_ids,
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

    keyed_report, keyed_idx = load_keyed_freeze_index(repo_root)
    gate_problems, block_pairs, got_balance = run_gates(rows, pair_rows, schedule, matrix, keyed_idx)
    problems.extend(gate_problems)
    plan_parity = build_plan_parity(rows, keyed_idx)

    rows.sort(key=lambda r: r["schedule_position"])
    pair_rows.sort(key=lambda p: min(p["baseline_schedule_position"],
                                     p["target_schedule_position"]))

    inv_path = os.path.join(out_dir, "portability_ych01_followup_normalized_invocations.csv")
    pair_path = os.path.join(out_dir, "portability_ych01_followup_normalized_pairs.csv")
    inv_sha = write_csv(inv_path, FU_INVOCATION_FIELDS, rows)
    pair_sha = write_csv(pair_path, FU_PAIR_COLUMNS, pair_rows)

    order_bal = order_balance(rows)
    report = _validation_report(problems, block_pairs, got_balance, plan_parity, order_bal,
                                actual_sha, sidecar_sha, stored_fp, derived_fp,
                                authoritative_ids, bm_run_config, status_txt,
                                len(rows), len(pair_rows))
    val_path = os.path.join(out_dir, "portability_ych01_followup_normalization_validation.txt")
    with open(val_path, "w") as f:
        f.write(report)

    ok = not problems
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "campaign": "portability_ych01_followup",
        "campaign_role": "independent_sign_stability_check_two_ych01_cells",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "normalizer_git_sha": _git_sha(ow_root),
        "ok": ok,
        "additive_note": (
            "Additive to normalize.py and the five prior portability normalizers. The frozen "
            "primary/secondary/portability/portability_ext/portability_full_closure/"
            "portability_outlier_replication normalized outputs are untouched; this campaign "
            "is a separate follow-up table and is NOT pooled into the five-campaign coverage "
            "synthesis and does NOT alter the frozen 55-cell headline comparison."),
        "not_a_performance_ranking": True,
        "not_pooled": True,
        "followup_claim": (
            "Independent EXACT-BALANCED re-run of the two YCh01 cells whose LATEST workstation "
            "first-query effect is positive but OpenWhisk is non-positive (layers_5, 2f_top14), "
            "to test whether the divergence is stable under a fresh independent batch with exact "
            "within-pair position balance. The prior direction is described only as a pair-"
            "position / short-lived execution-state / execution-storage-state effect; no specific "
            "physical mechanism is attributed and -0.019 is a near-zero, not strongly harmful, "
            "result. Does NOT replace the original R_ow values and does NOT alter the frozen "
            "65/65 coverage or the 55-cell comparison."),
        "source_bundle_filename": bundle,
        "source_bundle_sha256": actual_sha,
        "source_bundle_sha256_sidecar": sidecar_sha,
        "sqlite_research_git_sha": git_sha,
        "matrix_fingerprint": stored_fp,
        "matrix_fingerprint_recomputed": derived_fp,
        "schedule_seed": schedule.get("schedule_seed"),
        "authoritative_run_config_sha256": authoritative_ids["run_config_sha256"],
        "artifact_manifest_sha256": authoritative_ids["artifact_manifest_sha256"],
        "action_image_digest": authoritative_ids["action_image_digest"],
        "bundle_manifest_run_config_sha256": bm_run_config,
        "bundle_manifest_run_config_note": (
            "Known 06_collect packaging quirk: bundle_manifest top-level run_config_sha256 "
            "summarizes the pin PRIMARY (022fbeb0); the AUTHORITATIVE stamped identity is the "
            "schedule/requests/responses run_config 7a3cc45d. Archive not edited."),
        "keyed_freeze_report": FU["keyed_freeze_report_rel"],
        "bound_db_sha256": keyed_report.get("bound_db_sha256"),
        "classifier_sha256": keyed_report.get("classifier_sha256"),
        "status": status_kv,
        "counts": {"invocations": len(rows), "pairs": len(pair_rows),
                   "baseline": sum(1 for r in rows if r["strategy"] == "baseline"),
                   "target": sum(1 for r in rows if r["strategy"] != "baseline")},
        "block_pairs": block_pairs,
        "position_balance": {"/".join(map(str, k)): {"baseline_first": v[0], "target_first": v[1]}
                             for k, v in sorted(got_balance.items())},
        "target_cell_count": len(FU["expected_target_cells"]),
        "workload_families": WORKLOAD_FAMILIES,
        "parity_type_counts": dict(Counter(p["parity_type"] for p in plan_parity)),
        "delivery_method_counts": dict(Counter(r["delivery_method"] for r in rows)),
        "page_size": page_size,
        "column_categories": {
            "legend": {"P": "provenance", "S": "raw schedule/request identity",
                       "R": "raw response field (verbatim)", "D": "derived bookkeeping"},
            "invocation_columns": {c: cat for c, cat in FU_INVOCATION_COLUMNS},
        },
        "outputs": {
            "portability_ych01_followup_normalized_invocations.csv": {"rows": len(rows), "sha256": inv_sha},
            "portability_ych01_followup_normalized_pairs.csv": {"rows": len(pair_rows), "sha256": pair_sha},
            "portability_ych01_followup_normalization_validation.txt": {
                "sha256": hashlib.sha256(report.encode()).hexdigest()},
        },
        "canonical_row_order": "schedule_position (single batch)",
    }
    man_path = os.path.join(out_dir, "portability_ych01_followup_normalization_manifest.json")
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return ok, manifest, plan_parity


def _validation_report(problems, block_pairs, got_balance, plan_parity, order_bal,
                       actual_sha, sidecar_sha, stored_fp, derived_fp,
                       ids, bm_run_config, status_txt, n_inv, n_pairs):
    L = []
    L.append("# OpenWhisk WK1 YCH01 TWO-CELL FOLLOW-UP normalization — validation report")
    L.append("")
    L.append("overall: %s" % ("PASS" if not problems else "FAIL"))
    L.append("role: independent sign / stability check of two YCh01 cells "
             "(NOT a performance ranking; NOT pooled; does not alter the 55-cell comparison; "
             "native/WK1 remains primary)")
    L.append("")
    L.append("## totals")
    L.append("invocations: %d (expected 144)" % n_inv)
    L.append("pairs: %d (expected 72)" % n_pairs)
    L.append("block_pairs: %s (expected {Y1:36, Y2:36})"
             % json.dumps(block_pairs, sort_keys=True))
    L.append("")
    L.append("## exact per-cell / per-seed position balance (the scientific point)")
    for cell in sorted(got_balance):
        bf, tf = got_balance[cell]
        want = FU["expected_position_balance"].get(cell)
        L.append("%-10s %-28s s%s : baseline_first=%d target_first=%d  required=%s  %s"
                 % (cell[0], cell[1], cell[2], bf, tf, want,
                    "OK" if (bf, tf) == want else "MISMATCH"))
    L.append("")
    L.append("## identity")
    L.append("bundle_sha256: %s (sidecar=%s, match=%s)"
             % (actual_sha, sidecar_sha, actual_sha == sidecar_sha))
    L.append("matrix_fingerprint: %s (recomputed=%s, match=%s)"
             % (stored_fp, derived_fp, stored_fp == derived_fp))
    L.append("run_config_sha256: %s" % ids["run_config_sha256"])
    L.append("artifact_manifest_sha256: %s" % ids["artifact_manifest_sha256"])
    L.append("action_image_digest: %s" % ids["action_image_digest"])
    L.append("bundle_manifest_run_config_sha256: %s (packaging quirk: pin-primary summary; "
             "authoritative identity is the stamped schedule/response run_config)" % bm_run_config)
    for line in status_txt.split("\n"):
        if line.strip():
            L.append("status.%s" % line.strip())
    L.append("")
    L.append("## plan parity (per executed target plan; parity_type per taxonomy)")
    for p in plan_parity:
        L.append("%-10s %-28s s%s  pages=%s int=%s leaf=%s  deliver=%s  %s  matches_frozen=%s"
                 % (p["strategy"], p["workload"], p["seed"], p["pages"],
                    p["interior"], p["leaf"], p["delivery_method"],
                    p["parity_type"], p["matches_frozen"]))
    L.append("")
    L.append("## pair-order structural balance by target strategy (integrity only)")
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
    ap.add_argument("--out", default=str(_OW_ROOT / "analysis" / "normalized"
                                         / "portability_ych01_followup"))
    a = ap.parse_args()
    ok, manifest, _ = normalize(a.ow_root, a.out)
    print("portability_ych01_followup normalization %s: %d invocations, %d pairs -> %s"
          % ("PASS" if ok else "FAIL", manifest["counts"]["invocations"],
             manifest["counts"]["pairs"], a.out))
    if not ok:
        print("FAILED gates — see portability_ych01_followup_normalization_validation.txt",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
