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


def _order(schedule_seed, pair_id, target):
    """Deterministic AB/BA order from (schedule_seed, pair_id)."""
    h = hashlib.sha256(("%d|%s" % (schedule_seed, pair_id)).encode()).hexdigest()
    ab = (int(h[:8], 16) & 1) == 0
    return ["baseline", target] if ab else [target, "baseline"]


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
    return {"schema_version": 1, "schedule_seed": schedule_seed, "identity": ids,
            "counts": {"pairs": len(pairs), "invocations": len(invocations)},
            "warmup": warmup, "pairs": pairs, "invocations": invocations}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--schedule-seed", type=int, required=True)
    ap.add_argument("--workloads", default="A")
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
    sched = build_schedule(
        a.workloads.split(","), [int(x) for x in a.seeds.split(",")],
        [int(x) for x in a.first_ops.split(",")], a.handle_modes.split(","),
        a.targets.split(","), a.repetitions, a.schedule_seed, ids)
    with open(a.out, "w") as f:
        json.dump(sched, f, indent=2)
        f.write("\n")
    print("wrote %s (%d pairs, %d invocations)"
          % (a.out, sched["counts"]["pairs"], sched["counts"]["invocations"]))


if __name__ == "__main__":
    main()
