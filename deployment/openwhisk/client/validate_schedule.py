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


# --------------------------------------------------------------------------- #
# Block-union campaign schedules (heterogeneous blocks, ONE flattened schedule).
#
# A single formal campaign may need several rectangular blocks with DIFFERENT
# target-strategy sets and seed semantics per workload (a global Cartesian product
# would fabricate scientifically unintended workload x strategy cells). A campaign
# matrix therefore carries an explicit list of blocks; the UNION of the blocks'
# cells is the formal matrix. Each block is internally rectangular; across blocks
# the cell sets must be DISJOINT. The whole union flattens into one ordered
# schedule with one fingerprint. build_schedule.build_campaign_schedule() emits it;
# this module validates it fail-closed with exactly the same rigor as the single
# rectangular validator, plus the cross-block disjointness the union requires.
# --------------------------------------------------------------------------- #
def normalize_block(block, schedule_seed):
    """Canonicalize one heterogeneous block. `strategies` includes baseline (the
    paired A-arm anchor); targets = the non-baseline strategies. baseline is
    mandatory -- a block with no baseline cannot form pairs."""
    strategies = list(block["strategies"])
    if "baseline" not in strategies:
        raise ValueError("block %r strategies must include 'baseline'"
                         % block.get("id"))
    return {
        "id": block.get("id"),
        "schedule_seed": int(schedule_seed),
        "workloads": [normalize_workload_id(w) for w in block["workloads"]],
        "seeds": [int(x) for x in block["seeds"]],
        "first_operation_ids": [int(x) for x in block["first_operation_ids"]],
        "handle_modes": list(block["handle_modes"]),
        "targets": [s for s in strategies if s != "baseline"],
        "repetitions": int(block["repetitions_per_cell"]),
    }


def blocks_from_matrix(matrix):
    """Normalized block contracts, in the matrix's declared (execution) order."""
    seed = matrix["schedule_seed"]
    return [normalize_block(b, seed) for b in matrix["blocks"]]


def block_expected_pairs(bc):
    """Cartesian pair count for one block (product of its axis lengths)."""
    return (len(bc["workloads"]) * len(bc["seeds"])
            * len(bc["first_operation_ids"]) * len(bc["handle_modes"])
            * int(bc["repetitions"]) * len(bc["targets"]))


def block_cells(bc):
    """The exact set of formal pair cells (target, wl, seed, fop, hm, rep) a block
    contributes. A duplicated coordinate collapses here, so |cells| < product
    reveals a malformed (non-rectangular) block."""
    cells = set()
    for wl in bc["workloads"]:
        for seed in bc["seeds"]:
            for fop in bc["first_operation_ids"]:
                for hm in bc["handle_modes"]:
                    for rep in range(int(bc["repetitions"])):
                        for t in bc["targets"]:
                            cells.add((t, wl, seed, fop, hm, rep))
    return cells


def campaign_fingerprint(matrix, ids, invocations):
    """ONE sha256 binding the complete campaign: run-config/manifest/image identity,
    schedule_seed, the normalized block structure, AND the complete ORDERED flattened
    invocation schedule (schedule_position carries the order). Any reordering,
    relabelling, added/removed cell, or identity change diverges the fingerprint."""
    blocks = blocks_from_matrix(matrix)
    block_payload = [{
        "id": b["id"],
        "workloads": sorted(b["workloads"]), "seeds": sorted(b["seeds"]),
        "first_operation_ids": sorted(b["first_operation_ids"]),
        "handle_modes": sorted(b["handle_modes"]), "targets": sorted(b["targets"]),
        "repetitions": int(b["repetitions"]),
    } for b in blocks]
    ordered = [[i["schedule_position"], i["pair_id"], i["arm"], i["workload"],
                i["strategy"], i["seed"], i["first_operation_id"],
                i["handle_mode"], i["repetition_id"]] for i in invocations]
    payload = {
        "campaign": matrix.get("campaign", "portability"),
        "schedule_seed": int(matrix["schedule_seed"]),
        "identity": {k: ids.get(k) for k in _IDENTITY_KEYS},
        "blocks": block_payload,
        "schedule": ordered,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def campaign_expected_counts(matrix):
    """Grand totals a valid campaign must hit (sum over disjoint blocks)."""
    blocks = blocks_from_matrix(matrix)
    pairs = sum(block_expected_pairs(b) for b in blocks)
    return {"pairs": pairs, "invocations": 2 * pairs}


def validate_campaign(schedule, matrix):
    """Return a SORTED list of problems; empty == valid. Fail-closed checks:
    per-block rectangularity, cross-block cell disjointness (no duplicate formal
    cell), exact grand totals, pair integrity (exactly baseline + one target with
    shared non-arm identity), every block cell present exactly once and no cell
    outside any block (no unintended cross-product), and globally unique + contiguous
    request_ids / schedule_positions."""
    problems = []

    def bad(m):
        problems.append(m)

    blocks = blocks_from_matrix(matrix)
    seed = int(matrix["schedule_seed"])
    inv = schedule.get("invocations", [])
    pairs = schedule.get("pairs", [])

    if int(schedule.get("schedule_seed", -1)) != seed:
        bad("schedule_seed mismatch: schedule=%s matrix=%s"
            % (schedule.get("schedule_seed"), seed))

    # -- per-block rectangularity + cross-block disjoint union of formal cells ----
    union = {}  # cell -> owning block id
    for b in blocks:
        cells = block_cells(b)
        exp = block_expected_pairs(b)
        if len(cells) != exp:
            bad("block %s is not rectangular (%d distinct cells != %d product; "
                "duplicate coordinate?)" % (b["id"], len(cells), exp))
        for c in cells:
            if c in union:
                bad("duplicate formal cell across blocks %s and %s: %s"
                    % (union[c], b["id"], c))
            else:
                union[c] = b["id"]
    exp_pairs = sum(block_expected_pairs(b) for b in blocks)
    exp_inv = 2 * exp_pairs

    # -- grand totals -------------------------------------------------------------
    if len(inv) != exp_inv:
        bad("total invocations %d != expected %d" % (len(inv), exp_inv))
    if len(pairs) != exp_pairs:
        bad("total pairs %d != expected %d" % (len(pairs), exp_pairs))

    # -- pair integrity + attribute each pair to exactly one block cell -----------
    by_pair = {}
    for i in inv:
        by_pair.setdefault(i["pair_id"], []).append(i)
    if len(by_pair) != exp_pairs:
        bad("distinct pair_ids %d != expected %d" % (len(by_pair), exp_pairs))
    consumed = {}  # cell -> pair_id
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
        b_arm, t_arm = base[0], tgt[0]
        if t_arm["arm"] != t_arm["strategy"]:
            bad("pair %s target arm label %r != strategy %r"
                % (pid, t_arm["arm"], t_arm["strategy"]))
        for f in _CELL_FIELDS:
            if b_arm.get(f) != t_arm.get(f):
                bad("pair %s arms disagree on %s (baseline=%r target=%r)"
                    % (pid, f, b_arm.get(f), t_arm.get(f)))
        cell = (t_arm["strategy"],) + tuple(t_arm.get(f) for f in _CELL_FIELDS)
        if cell not in union:
            bad("pair %s cell %s belongs to no block (unintended cross-product?)"
                % (pid, cell))
        elif cell in consumed:
            bad("duplicate Cartesian cell %s owned by pairs %s and %s"
                % (cell, consumed[cell], pid))
        else:
            consumed[cell] = pid
    missing = set(union) - set(consumed)
    if missing:
        bad("%d expected block cell(s) missing from schedule, e.g. %s"
            % (len(missing), sorted(missing)[:3]))

    # -- opt-in EXACT position balance (matrix flag position_balance="exact") -----
    # For each balance cell (target x workload x seed x first_op x handle_mode -- i.e.
    # every _CELL_FIELDS coordinate EXCEPT repetition_id), the reps must split EXACTLY
    # half baseline-first / half target-first. This is a HARD gate for the outlier-
    # replication campaign; default (flagless) campaigns skip it and keep the per-pair
    # coin-flip. Read from `pairs` (each carries its AB/BA `order`).
    if matrix.get("position_balance") == "exact":
        bal_fields = tuple(f for f in _CELL_FIELDS if f != "repetition_id")
        ab_ct, ba_ct = Counter(), Counter()
        for p in pairs:
            order = p.get("order", [])
            ck = (p.get("target_strategy"),) + tuple(p.get(f) for f in bal_fields)
            if order and order[0] == "baseline":
                ab_ct[ck] += 1
            else:
                ba_ct[ck] += 1
        for ck in sorted(set(ab_ct) | set(ba_ct)):
            ab, ba = ab_ct[ck], ba_ct[ck]
            if ab != ba:
                bad("position_balance=exact violated at cell %s: baseline_first=%d "
                    "target_first=%d (require equal)" % (ck, ab, ba))

    # -- global request_id / schedule_position uniqueness + contiguity ------------
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


def _validate_campaign_main(schedule, matrix, expect_fp):
    """Validate a block-union campaign schedule + bind its single fingerprint."""
    problems = validate_campaign(schedule, matrix)
    ids = schedule.get("identity", {})
    expected_fp = campaign_fingerprint(matrix, ids, schedule.get("invocations", []))
    stored_fp = schedule.get("matrix_fingerprint")
    if stored_fp is None:
        problems.append("schedule has no matrix_fingerprint (cannot bind to matrix)")
    elif stored_fp != expected_fp:
        problems.append("matrix_fingerprint mismatch: schedule=%s expected=%s "
                        "(schedule was built for a different campaign/identity)"
                        % (stored_fp, expected_fp))
    if expect_fp and stored_fp != expect_fp:
        problems.append("stored fingerprint %s != --expect-fingerprint %s"
                        % (stored_fp, expect_fp))
    if problems:
        print("SCHEDULE INVALID (%d problem(s)):" % len(problems))
        for p in problems:
            print("  FAIL", p)
        sys.exit(1)
    exp = campaign_expected_counts(matrix)
    print("CAMPAIGN SCHEDULE VALID: %d invocations, %d pairs across %d blocks, "
          "single fingerprint=%s"
          % (exp["invocations"], exp["pairs"], len(matrix["blocks"]), stored_fp))


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

    # A block-union campaign matrix validates with the campaign checks + single
    # fingerprint; a flat rectangular matrix keeps the original path untouched.
    if "blocks" in matrix:
        _validate_campaign_main(schedule, matrix, a.expect_fingerprint)
        return

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
