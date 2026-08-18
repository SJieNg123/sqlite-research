#!/usr/bin/env python3
"""Fail-closed structural validator for a multi-target baseline/target schedule.

The 05 matrix stage builds a schedule with :mod:`build_schedule` and then MUST
prove -- before any OpenWhisk invocation -- that the schedule is a balanced
combinatorial matrix, not merely that it has the right total request count. A
malformed schedule that relabels or reuses a few target arms while preserving the
grand total (e.g. per-target counts 198/198/198/206 instead of 200/200/200/200)
executes faithfully and passes a naive total-count / response-identity audit, yet
is invalid as a balanced primary matrix. This module rejects exactly that class.

Two orthogonal guards live here:

* :func:`matrix_fingerprint` -- a content hash of the combinatorial contract
  (workloads/seeds/first-ops/handle-modes/targets/repetitions/schedule_seed +
  runtime identity). Binds a persisted ``schedule.json`` to the matrix it was
  built for so a stale/foreign schedule cannot be silently reused on resume.

* :func:`validate_schedule` -- exhaustive per-cell balance + pairing checks. For
  every Cartesian cell (workload, seed, first_operation_id, handle_mode,
  repetition_id, target) there must be exactly one pair_id carrying exactly two
  arms: one baseline and one target. Baseline is a reference arm, never a target.

The generator self-validates with this before writing, and 05 re-validates the
(possibly resumed) schedule before exploding requests. Both fail closed.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "config"))
from workload_registry import normalize_workload_id  # noqa: E402

_IDENTITY_KEYS = ("run_config_sha256", "artifact_manifest_sha256",
                  "action_image_digest")
# Non-arm identity fields shared by a pair's two arms (arm/strategy differ).
_CELL_FIELDS = ("workload", "seed", "first_operation_id", "handle_mode",
                "repetition_id")


def normalized_contract(workloads, seeds, first_ops, handle_modes, targets,
                        repetitions, schedule_seed):
    """Canonicalize the combinatorial contract (targets = NON-baseline strategies).

    Deduplication is intentionally *not* applied: a caller that passes a duplicate
    seed/target is a malformed matrix, and the fingerprint + balance checks must
    diverge rather than silently normalize it away.
    """
    return {
        "schedule_seed": int(schedule_seed),
        "workloads": [normalize_workload_id(w) for w in workloads],
        "seeds": [int(x) for x in seeds],
        "first_operation_ids": [int(x) for x in first_ops],
        "handle_modes": list(handle_modes),
        "targets": [t for t in targets if t != "baseline"],
        "repetitions": int(repetitions),
    }


def contract_from_matrix(matrix):
    """Derive the contract from a 05 matrix manifest (strategies include baseline)."""
    return normalized_contract(
        matrix["workloads"], matrix["seeds"], matrix["first_operation_ids"],
        matrix["handle_modes"],
        [s for s in matrix["strategies"] if s != "baseline"],
        matrix["repetitions_per_cell"], matrix["schedule_seed"])


def matrix_fingerprint(contract, ids):
    """sha256 over the sorted contract + runtime identity. Order-independent so the
    same matrix always fingerprints identically regardless of list ordering."""
    payload = {
        "schedule_seed": int(contract["schedule_seed"]),
        "workloads": sorted(contract["workloads"]),
        "seeds": sorted(contract["seeds"]),
        "first_operation_ids": sorted(contract["first_operation_ids"]),
        "handle_modes": sorted(contract["handle_modes"]),
        "targets": sorted(contract["targets"]),
        "repetitions": int(contract["repetitions"]),
        "identity": {k: ids.get(k) for k in _IDENTITY_KEYS},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def expected_counts(contract):
    """The exact marginal counts a balanced schedule must have."""
    W = len(contract["workloads"]); S = len(contract["seeds"])
    F = len(contract["first_operation_ids"]); M = len(contract["handle_modes"])
    R = int(contract["repetitions"]); T = len(contract["targets"])
    pairs = W * S * F * M * R * T
    return {
        "pairs": pairs,
        "invocations": 2 * pairs,
        "baseline": pairs,
        "per_target": W * S * F * M * R,
        "per_seed": 2 * T * W * F * M * R,
        "per_target_seed": W * F * M * R,
        "per_target_seed_mode": W * F * R,
        "per_target_seed_mode_rep_target_arm": W * F,  # 1 for the canonical matrix
    }


def validate_schedule(schedule, contract):
    """Return a SORTED list of problem strings; empty list == valid.

    Checks (all fail-closed): grand total, baseline total, per-target, per-seed,
    per-(target,seed), per-(target,seed,mode), per-(target,seed,mode,rep) target
    arms; pair integrity (exactly 2 arms, one baseline + one matching target, shared
    non-arm identity); one pair per Cartesian cell; unique request_ids; unique
    contiguous schedule_positions; and schedule_seed agreement.
    """
    problems = []
    exp = expected_counts(contract)
    targets = set(contract["targets"])
    seeds = set(contract["seeds"])
    inv = schedule.get("invocations", [])

    def bad(msg):
        problems.append(msg)

    # -- schedule_seed agreement (AB/BA determinism is bound to this seed) --------
    if int(schedule.get("schedule_seed", -1)) != int(contract["schedule_seed"]):
        bad("schedule_seed mismatch: schedule=%s contract=%s"
            % (schedule.get("schedule_seed"), contract["schedule_seed"]))

    # -- grand totals -------------------------------------------------------------
    if len(inv) != exp["invocations"]:
        bad("total invocations %d != expected %d" % (len(inv), exp["invocations"]))

    strat_counts = Counter(i["strategy"] for i in inv)
    if strat_counts.get("baseline", 0) != exp["baseline"]:
        bad("baseline count %d != expected %d"
            % (strat_counts.get("baseline", 0), exp["baseline"]))

    # -- per-target (no unexpected/missing target strategies) ---------------------
    seen_targets = set(strat_counts) - {"baseline"}
    if seen_targets != targets:
        bad("target strategy set %s != expected %s"
            % (sorted(seen_targets), sorted(targets)))
    for t in sorted(targets):
        if strat_counts.get(t, 0) != exp["per_target"]:
            bad("target %s count %d != expected %d"
                % (t, strat_counts.get(t, 0), exp["per_target"]))

    # -- per-seed -----------------------------------------------------------------
    seed_counts = Counter(i["seed"] for i in inv)
    seen_seeds = set(seed_counts)
    if seen_seeds != seeds:
        bad("seed set %s != expected %s" % (sorted(seen_seeds), sorted(seeds)))
    for s in sorted(seeds):
        if seed_counts.get(s, 0) != exp["per_seed"]:
            bad("seed %s count %d != expected %d"
                % (s, seed_counts.get(s, 0), exp["per_seed"]))

    # -- target-arm marginals at increasing resolution ----------------------------
    # A target arm is any non-baseline arm; its strategy is the pair's target.
    ta = [i for i in inv if i["strategy"] != "baseline"]
    ts = Counter((i["strategy"], i["seed"]) for i in ta)
    for t in sorted(targets):
        for s in sorted(seeds):
            if ts.get((t, s), 0) != exp["per_target_seed"]:
                bad("target x seed (%s, %s) = %d != expected %d"
                    % (t, s, ts.get((t, s), 0), exp["per_target_seed"]))
    tsm = Counter((i["strategy"], i["seed"], i["handle_mode"]) for i in ta)
    for (t, s, m), c in sorted(tsm.items()):
        if c != exp["per_target_seed_mode"]:
            bad("target x seed x mode (%s, %s, %s) = %d != expected %d"
                % (t, s, m, c, exp["per_target_seed_mode"]))
    tsmr = Counter((i["strategy"], i["seed"], i["handle_mode"],
                    i["repetition_id"]) for i in ta)
    for (t, s, m, r), c in sorted(tsmr.items()):
        if c != exp["per_target_seed_mode_rep_target_arm"]:
            bad("target x seed x mode x rep (%s, %s, %s, %s) target arms = %d "
                "!= expected %d"
                % (t, s, m, r, c, exp["per_target_seed_mode_rep_target_arm"]))

    # -- pair integrity -----------------------------------------------------------
    by_pair = {}
    for i in inv:
        by_pair.setdefault(i["pair_id"], []).append(i)
    if len(by_pair) != exp["pairs"]:
        bad("distinct pair_ids %d != expected %d" % (len(by_pair), exp["pairs"]))
    cell_key_owner = {}
    for pid, arms in sorted(by_pair.items()):
        if len(arms) != 2:
            bad("pair %s has %d arms, expected exactly 2" % (pid, len(arms)))
            continue
        base = [a for a in arms if a["strategy"] == "baseline"]
        tgt = [a for a in arms if a["strategy"] != "baseline"]
        if len(base) != 1 or len(tgt) != 1:
            bad("pair %s must have exactly one baseline + one target arm (got "
                "baseline=%d target=%d)" % (pid, len(base), len(tgt)))
            continue
        b, t = base[0], tgt[0]
        if t["strategy"] not in targets:
            bad("pair %s target arm strategy %s is not an expected target"
                % (pid, t["strategy"]))
        if t["arm"] != t["strategy"]:
            bad("pair %s target arm label %r != strategy %r"
                % (pid, t["arm"], t["strategy"]))
        # Randomization is ORDER ONLY: the two arms must agree on every non-arm
        # identity field. A relabelled/reused target arm violates this.
        for f in _CELL_FIELDS:
            if b.get(f) != t.get(f):
                bad("pair %s arms disagree on %s (baseline=%r target=%r)"
                    % (pid, f, b.get(f), t.get(f)))
        # Exactly one pair per Cartesian cell (target + non-arm identity).
        ck = (t["strategy"],) + tuple(t.get(f) for f in _CELL_FIELDS)
        if ck in cell_key_owner:
            bad("duplicate Cartesian cell %s owned by pairs %s and %s"
                % (ck, cell_key_owner[ck], pid))
        else:
            cell_key_owner[ck] = pid

    # Every Cartesian cell must be present exactly once.
    if len(cell_key_owner) != exp["pairs"]:
        bad("distinct Cartesian cells %d != expected %d"
            % (len(cell_key_owner), exp["pairs"]))

    # -- request_id / schedule_position uniqueness + contiguity -------------------
    rids = [i["request_id"] for i in inv]
    if len(set(rids)) != len(rids):
        dup = [r for r, c in Counter(rids).items() if c > 1]
        bad("duplicate request_id(s): %s" % sorted(dup)[:5])
    positions = [i["schedule_position"] for i in inv]
    if len(set(positions)) != len(positions):
        dup = [p for p, c in Counter(positions).items() if c > 1]
        bad("duplicate schedule_position(s): %s" % sorted(dup)[:5])
    elif inv and set(positions) != set(range(1, len(inv) + 1)):
        bad("schedule_positions are not the contiguous range 1..%d" % len(inv))

    return sorted(problems)


def _load(p):
    with open(p) as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(
        description="Fail-closed balance validator for a built schedule.json")
    ap.add_argument("schedule")
    ap.add_argument("matrix")
    ap.add_argument("--expect-fingerprint", default=None,
                    help="if given, the schedule's stored matrix_fingerprint must "
                         "equal the fingerprint derived from the matrix + identity")
    a = ap.parse_args()
    schedule = _load(a.schedule)
    matrix = _load(a.matrix)
    contract = contract_from_matrix(matrix)

    problems = validate_schedule(schedule, contract)

    # Identity binding: the persisted schedule must have been built for THIS matrix.
    ids = schedule.get("identity", {})
    expected_fp = matrix_fingerprint(contract, ids)
    stored_fp = schedule.get("matrix_fingerprint")
    if stored_fp is None:
        problems.append("schedule has no matrix_fingerprint (cannot bind to matrix)")
    elif stored_fp != expected_fp:
        problems.append("matrix_fingerprint mismatch: schedule=%s expected=%s "
                        "(schedule was built for a different matrix/identity)"
                        % (stored_fp, expected_fp))
    if a.expect_fingerprint and stored_fp != a.expect_fingerprint:
        problems.append("stored fingerprint %s != --expect-fingerprint %s"
                        % (stored_fp, a.expect_fingerprint))

    if problems:
        print("SCHEDULE INVALID (%d problem(s)):" % len(problems))
        for p in problems:
            print("  FAIL", p)
        sys.exit(1)
    exp = expected_counts(contract)
    print("SCHEDULE VALID: %d invocations, %d pairs, baseline=%d, %d targets x "
          "%d/target, fingerprint=%s"
          % (exp["invocations"], exp["pairs"], exp["baseline"],
             len(contract["targets"]), exp["per_target"], stored_fp))


if __name__ == "__main__":
    main()
