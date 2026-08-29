#!/usr/bin/env python3
"""Build an atomic, randomized baseline/strategy invocation schedule.

For each (workload, seed, first_operation, handle_mode, repetition_id, target
strategy) this emits exactly one ``pair_id`` containing exactly two arms — one
baseline and one target — whose order (AB or BA) is a deterministic function of a
frozen ``schedule_seed`` (no RNG, so the schedule is reproducible and
resume-safe). The complete schedule is persisted before any invocation.

Pairing atomicity is enforced downstream: if the process session changes between
a pair's two arms, the whole pair is invalidated and neither arm is paired
elsewhere (see summarize.py / PROTOCOL). A warmup-only diagnostic invocation is
emitted first, and the driver must also inject one whenever a new
``process_uuid`` appears; warmup invocations are never measured.

No OpenWhisk is invoked here; this only writes ``schedule.json``.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

# Canonical workload registry (config/workload_registry.py). We normalize the
# workload IDs supplied on the command line so new schedules record canonical IDs
# and accept both legacy aliases (A/B/C) and canonical names. The pure
# build_schedule() function is left untouched so it records whatever it is given.
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "config"))
from workload_registry import normalize_workload_id  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_schedule import (  # noqa: E402
    normalized_contract, matrix_fingerprint, validate_schedule,
    blocks_from_matrix, campaign_fingerprint, validate_campaign)


def _order(schedule_seed, pair_id, target):
    """Deterministic AB/BA order from (schedule_seed, pair_id)."""
    h = hashlib.sha256(("%d|%s" % (schedule_seed, pair_id)).encode()).hexdigest()
    ab = (int(h[:8], 16) & 1) == 0
    return ["baseline", target] if ab else [target, "baseline"]


def _balanced_cell_orders(schedule_seed, wl, seed, fop, hm, target, reps):
    """EXACT baseline-target position balance for one cell's `reps` repetitions.

    Opt-in path (matrix flag ``position_balance: "exact"``): instead of the per-pair
    coin-flip in ``_order`` -- which for small n can land 0/3 or 2/7 baseline-first --
    this ranks the cell's reps by a deterministic ``sha256(seed|cell|rep)`` and assigns
    the lower half AB (baseline-first) and the upper half BA (target-first), so the cell
    is GUARANTEED exactly ``reps/2`` each. The schedule_seed still selects WHICH reps are
    AB (order only), but can no longer perturb the count. Requires an even ``reps``."""
    if reps % 2 != 0:
        raise ValueError(
            "position_balance=exact needs an even repetitions_per_cell; got %d for "
            "cell %s-s%d-f%d-%s-%s" % (reps, wl, seed, fop, hm, target))
    key = "%d|%s-s%d-f%d-%s-%s" % (schedule_seed, wl, seed, fop, hm, target)
    ranked = sorted(range(reps),
                    key=lambda r: hashlib.sha256(
                        ("%s-r%d" % (key, r)).encode()).hexdigest())
    ab_reps = set(ranked[: reps // 2])
    return {r: (["baseline", target] if r in ab_reps else [target, "baseline"])
            for r in range(reps)}


def _invocation(pair_id, arm, strategy, pos, combo, ids, schedule_seed):
    wl, seed, fop, hm, rep = combo
    return {
        "request_id": "%s:%s" % (pair_id, arm),
        "pair_id": pair_id, "schedule_position": pos, "arm": arm,
        "workload": wl, "strategy": strategy, "seed": seed,
        "first_operation_id": fop, "handle_mode": hm, "repetition_id": rep,
        "schedule_seed": schedule_seed,
        "run_config_sha256": ids["run_config_sha256"],
        "expected_artifact_manifest_hash": ids["artifact_manifest_sha256"],
        "expected_action_image_digest": ids["action_image_digest"],
        "diagnostic_mode": False, "cold_reset": True,
    }


def build_schedule(workloads, seeds, first_ops, handle_modes, targets,
                   repetitions, schedule_seed, ids):
    """Return the full schedule dict. `ids` carries run_config_sha256,
    artifact_manifest_sha256, action_image_digest."""
    pairs, invocations = [], []
    pos = 0
    for wl in workloads:
        for seed in seeds:
            for fop in first_ops:
                for hm in handle_modes:
                    for rep in range(repetitions):
                        for target in targets:
                            pair_id = "%s-s%d-f%d-%s-r%d-%s" % (wl, seed, fop, hm, rep, target)
                            order = _order(schedule_seed, pair_id, target)
                            pairs.append({"pair_id": pair_id, "workload": wl,
                                          "seed": seed, "first_operation_id": fop,
                                          "handle_mode": hm, "repetition_id": rep,
                                          "target_strategy": target, "order": order})
                            combo = (wl, seed, fop, hm, rep)
                            for arm in order:
                                pos += 1
                                strategy = "baseline" if arm == "baseline" else target
                                invocations.append(_invocation(
                                    pair_id, arm, strategy, pos, combo, ids, schedule_seed))
    warmup = {"request_id": "warmup-0", "diagnostic_mode": True, "cold_reset": True,
              "workload": workloads[0], "strategy": "baseline", "seed": seeds[0],
              "first_operation_id": first_ops[0], "handle_mode": handle_modes[0],
              "pair_id": "", "repetition_id": 0, "schedule_position": 0,
              "schedule_seed": schedule_seed,
              "run_config_sha256": ids["run_config_sha256"],
              "expected_artifact_manifest_hash": ids["artifact_manifest_sha256"],
              "expected_action_image_digest": ids["action_image_digest"],
              "note": "warmup-only; never measured; driver repeats on each new process_uuid"}
    contract = normalized_contract(workloads, seeds, first_ops, handle_modes,
                                   targets, repetitions, schedule_seed)
    sched = {"schema_version": 2, "schedule_seed": schedule_seed, "identity": ids,
             "matrix_fingerprint": matrix_fingerprint(contract, ids),
             "contract": contract,
             "counts": {"pairs": len(pairs), "invocations": len(invocations)},
             "warmup": warmup, "pairs": pairs, "invocations": invocations}
    # Fail closed: a generator that ever emits an imbalanced schedule must abort
    # here, before the schedule is persisted or any request is invoked.
    problems = validate_schedule(sched, contract)
    if problems:
        raise ValueError("build_schedule produced an INVALID schedule:\n  "
                         + "\n  ".join(problems))
    return sched


def build_campaign_schedule(matrix, ids):
    """Flatten a block-union campaign matrix into ONE ordered schedule.

    Emits every block's cells (a strict per-block Cartesian product) into a single
    invocation list with globally contiguous schedule_positions and one campaign
    fingerprint over the complete ordered schedule. The UNION of the explicit blocks
    is the formal matrix -- no global cross-product is taken, so heterogeneous
    per-workload target sets never fabricate unintended cells. Self-validates
    fail-closed (per-block rectangularity, cross-block disjointness, exact totals)
    before returning; a malformed union aborts here, before persistence."""
    schedule_seed = int(matrix["schedule_seed"])
    # Opt-in exact position balance (default path is byte-identical when the flag is
    # absent): when set, each cell's AB/BA orders are precomputed balanced per cell.
    balanced = matrix.get("position_balance") == "exact"
    blocks = blocks_from_matrix(matrix)
    pairs, invocations = [], []
    pos = 0
    for b in blocks:
        reps = int(b["repetitions"])
        for wl in b["workloads"]:
            for seed in b["seeds"]:
                for fop in b["first_operation_ids"]:
                    for hm in b["handle_modes"]:
                        cell_orders = ({t: _balanced_cell_orders(
                            schedule_seed, wl, seed, fop, hm, t, reps)
                            for t in b["targets"]} if balanced else None)
                        for rep in range(reps):
                            for target in b["targets"]:
                                pair_id = "%s-s%d-f%d-%s-r%d-%s" % (
                                    wl, seed, fop, hm, rep, target)
                                order = (cell_orders[target][rep] if balanced
                                         else _order(schedule_seed, pair_id, target))
                                pairs.append({
                                    "pair_id": pair_id, "workload": wl, "seed": seed,
                                    "first_operation_id": fop, "handle_mode": hm,
                                    "repetition_id": rep, "target_strategy": target,
                                    "order": order, "block_id": b["id"]})
                                combo = (wl, seed, fop, hm, rep)
                                for arm in order:
                                    pos += 1
                                    strategy = ("baseline" if arm == "baseline"
                                                else target)
                                    invocations.append(_invocation(
                                        pair_id, arm, strategy, pos, combo, ids,
                                        schedule_seed))
    first = blocks[0]
    warmup = {"request_id": "warmup-0", "diagnostic_mode": True, "cold_reset": True,
              "workload": first["workloads"][0], "strategy": "baseline",
              "seed": first["seeds"][0], "first_operation_id": first["first_operation_ids"][0],
              "handle_mode": first["handle_modes"][0], "pair_id": "",
              "repetition_id": 0, "schedule_position": 0, "schedule_seed": schedule_seed,
              "run_config_sha256": ids["run_config_sha256"],
              "expected_artifact_manifest_hash": ids["artifact_manifest_sha256"],
              "expected_action_image_digest": ids["action_image_digest"],
              "note": "warmup-only; never measured; driver repeats on each new process_uuid"}
    sched = {
        "schema_version": 3, "campaign": matrix.get("campaign", "portability"),
        "schedule_seed": schedule_seed, "identity": ids,
        "matrix_fingerprint": campaign_fingerprint(matrix, ids, invocations),
        "blocks": [{"id": b["id"], "workloads": b["workloads"], "seeds": b["seeds"],
                    "first_operation_ids": b["first_operation_ids"],
                    "handle_modes": b["handle_modes"], "targets": b["targets"],
                    "repetitions": int(b["repetitions"])} for b in blocks],
        "counts": {"pairs": len(pairs), "invocations": len(invocations)},
        "warmup": warmup, "pairs": pairs, "invocations": invocations}
    problems = validate_campaign(sched, matrix)
    if problems:
        raise ValueError("build_campaign_schedule produced an INVALID schedule:\n  "
                         + "\n  ".join(problems))
    return sched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--matrix", default=None,
                    help="a block-union campaign matrix JSON (with a 'blocks' list). "
                         "When given, the flat --workloads/--seeds/... axes are "
                         "ignored and ONE campaign schedule is built from the blocks.")
    ap.add_argument("--schedule-seed", type=int, required=False)
    ap.add_argument("--workloads", default="read_zipf_scattered_100k",
                    help="comma list of canonical workload IDs or legacy aliases (A/B/C ...); "
                         "normalized to canonical IDs via config/workload_registry.py")
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--first-ops", default="0")
    ap.add_argument("--handle-modes", default="warm")
    ap.add_argument("--targets", default="2d")
    ap.add_argument("--repetitions", type=int, default=10)
    ap.add_argument("--run-config-sha256", required=True)
    ap.add_argument("--artifact-manifest-sha256", required=True)
    ap.add_argument("--action-image-digest", required=True)
    a = ap.parse_args()
    ids = {"run_config_sha256": a.run_config_sha256,
           "artifact_manifest_sha256": a.artifact_manifest_sha256,
           "action_image_digest": a.action_image_digest}
    if a.matrix:
        # Block-union campaign: seed + axes come from the matrix file; the flat
        # --workloads/--seeds/... arguments are ignored.
        with open(a.matrix) as f:
            matrix = json.load(f)
        if "blocks" not in matrix:
            sys.exit("--matrix %s has no 'blocks' list (not a campaign matrix)" % a.matrix)
        sched = build_campaign_schedule(matrix, ids)
    else:
        if a.schedule_seed is None:
            sys.exit("--schedule-seed is required for a flat (non-campaign) matrix")
        workloads = [normalize_workload_id(w) for w in a.workloads.split(",")]
        sched = build_schedule(
            workloads, [int(x) for x in a.seeds.split(",")],
            [int(x) for x in a.first_ops.split(",")], a.handle_modes.split(","),
            a.targets.split(","), a.repetitions, a.schedule_seed, ids)
    with open(a.out, "w") as f:
        json.dump(sched, f, indent=2)
        f.write("\n")
    print("wrote %s (%d pairs, %d invocations)"
          % (a.out, sched["counts"]["pairs"], sched["counts"]["invocations"]))


if __name__ == "__main__":
    main()
