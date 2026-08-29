#!/usr/bin/env python3
"""Single source of truth for the workstation<->OpenWhisk YCH01 TWO-CELL FOLLOW-UP campaign.

SEVENTH additive campaign; a targeted SIGN / STABILITY check, NOT new coverage and NOT a
seventh pooled performance estimator. It re-runs, under EXACT baseline-target position
balance and STANDALONE handles only, the ONLY two (workload, strategy) cells that -- after
the sixth (portability_outlier_replication) balanced re-run refreshed the comparison table
-- still have a POSITIVE workstation first-query effect but a NON-POSITIVE OpenWhisk one:

    YCh01 / layers_5   (native_ycsb_c_hot_hashed_01)  -- R_ws +0.025 (neutral+), R_ow -0.243
    YCh01 / 2f_top14   (native_ycsb_c_hot_hashed_01)  -- R_ws +0.214, R_ow -0.019 (near zero)

WHY THIS EXISTS: the previous OpenWhisk value for each of these two cells came from a batch
where the within-pair AB/BA position was not exactly balanced per seed (layers_5: the sixth
balanced batch, 10/10; 2f_top14: the portability_ext batch, small n with position
imbalance). This campaign asks a single narrow question: are the two discrepancies STABLE
under a fresh, independent batch with EXACTLY balanced within-pair position? The previously
observed direction is described ONLY as a pair-position effect / short-lived execution-state
effect / execution-storage-state dependence; NO specific physical mechanism (e.g. page-cache
carryover) is attributed here -- no new direct evidence establishes one. The R_ow = -0.019
2f_top14 value is a near-zero result, NOT a strong harmful effect.

This module is imported by both:
  * ``build_artifact_manifest.py`` -- MERGE the follow-up invocation plan + run_config
    sha256 additively into the live ``config/artifacts.json`` (NO new keyed plans, NO new
    markers: both strategies are reused, already admissible + implemented);
  * ``tools/write_portability_ych01_followup_pin.py`` -- emit the same two top-level
    identity keys into the frozen replay pin, freezing ALL SIX prior campaign identities
    byte-unchanged.

REUSE-ONLY. Nothing is frozen or generated here:
  * ``2f_top14`` on native_ycsb_c_hot_hashed_01 seeds 1,2,3 reuses the AUDITED
    portability_ext keyed plans already in ``keyed_strategy_plans`` (frozen by the
    portability_ext layer; plan_sha256 6bc163bd.., seed-invariant top-14 selection);
  * ``layers_5`` reuses the committed static strategy artifact (the 5-interior prefix).
So this campaign adds ZERO coverage: both cells are members of the existing frozen 65-cell
canonical portability matrix.

Independent campaign identity: its OWN ``SCHEDULE_SEED_FOLLOWUP`` (20260901, off the round
marks and distinct from primary 20260804 / secondary 20260825 / portability 20260826 /
portability_ext 20260828 / portability_full_closure 20260829 / outlier_replication 20260830)
and its OWN ``portability_ych01_followup_run_config_sha256``. It shares the same image / DB /
classifier / action / cold-reset / oracle / handle semantics as every prior campaign.

INTERPRETATION IS PRE-REGISTERED. The follow-up does NOT replace the original OR / ext R_ow
values and does NOT alter the frozen 65/65 coverage or the headline 55-cell comparison; the
prior batches and this one are reported side by side.
"""
import hashlib
import json

import portability_manifest as PM  # sibling; reused for WORKLOAD_SET + helpers

# workload id (identical to portability_ext_manifest)
YCH01 = "native_ycsb_c_hot_hashed_01"

# Independent campaign identity: a new schedule seed, distinct from every prior campaign
# and off the round marks.
SCHEDULE_SEED_FOLLOWUP = 20260901

# STANDALONE ONLY -- the workstation<->OpenWhisk effectiveness comparison uses the
# standalone handle, so the follow-up is standalone-only (no warm arm).
HANDLE_MODES_FOLLOWUP = ["standalone"]
FIRST_OPERATION_IDS = [0]

# Position balance is a HARD scientific requirement of this campaign: every cell must be
# EXACTLY baseline_first == target_first, deterministically (not approximately-by-random).
# The matrix carries "position_balance": "exact"; the schedule builder + validator enforce
# it per cell/seed. Every per-cell rep count MUST be even.
POSITION_BALANCE = "exact"

# The two rectangular follow-up sub-matrices (strict Cartesian products). Targets =
# strategies minus baseline; every block anchors on the paired baseline A-arm.
#   Pairs = |W| * |seeds| * |F| * |M| * reps * |T|   (F=1, M=1 standalone-only).
# Per-block reps: 36 for YCh01/layers_5 (single seed -> 18 baseline-first / 18 target-first);
# 12 for YCh01/2f_top14 per seed (-> 6 / 6 per seed).
MATRICES_FOLLOWUP = [
    {"name": "Y1", "workloads": [YCH01],
     "strategies": ["baseline", "layers_5"],
     "seeds": [1], "reps": 36},                       # 1*1*1*1*36*1 = 36
    {"name": "Y2", "workloads": [YCH01],
     "strategies": ["baseline", "2f_top14"],
     "seeds": [1, 2, 3], "reps": 12},                 # 1*3*1*1*12*1 = 36
]

EXPECTED_FOLLOWUP_PAIRS = 72
EXPECTED_FOLLOWUP_INVOCATIONS = 144

# The exact two (workload, strategy) cells this campaign follows up. Frozen literal so a
# drift in MATRICES_FOLLOWUP is caught. Tag is provenance only (NOT a claim).
FOLLOWUP_CELLS = [
    (YCH01, "layers_5", "1", "ws_positive_ow_negative"),
    (YCH01, "2f_top14", "1,2,3", "ws_positive_ow_near_zero"),
]

# Strategies this campaign reuses, and how each is resolved in the frozen pin.
#   static  -> strategy_plans[<strat>] carries inline offsets (no per-seed keyed plan)
#   keyed   -> keyed_strategy_plans[<workload>][<seed>][<strat>] (per-seed frozen plan)
_STATIC_STRATS = ("layers_5",)
_KEYED_STRATS = ("2f_top14",)
BOUND_DB_SHA256 = PM.BOUND_DB_SHA256


# ----------------------------------------------------------------- invocation plan
def portability_ych01_followup_invocation_plan():
    """The independent follow-up run-config identity source. Pure-literal structure from
    MATRICES_FOLLOWUP (no offsets/shas), recomputed identically on WK1 and WK2. The identity
    BINDS the standalone-only handle set, the exact-position-balance flag, and the schedule
    seed, so a run under any other handle/balance/seed has a different run_config sha256."""
    strat_union = sorted({s for mx in MATRICES_FOLLOWUP for s in mx["strategies"]})
    wl_union = sorted({w for mx in MATRICES_FOLLOWUP for w in mx["workloads"]})
    seed_union = sorted({s for mx in MATRICES_FOLLOWUP for s in mx["seeds"]})
    total_pairs = 0
    matrices = []
    for mx in MATRICES_FOLLOWUP:
        W = len(mx["workloads"]); S = len(mx["seeds"]); R = int(mx["reps"])
        T = len([s for s in mx["strategies"] if s != "baseline"])
        if R % 2 != 0:
            raise SystemExit("block %s reps=%d must be even for exact position balance"
                             % (mx["name"], R))
        pairs = W * S * len(FIRST_OPERATION_IDS) * len(HANDLE_MODES_FOLLOWUP) * R * T
        total_pairs += pairs
        matrices.append({
            "name": mx["name"],
            "workloads": list(mx["workloads"]),
            "strategies": list(mx["strategies"]),
            "seeds": list(mx["seeds"]),
            "reps": R,
            "handle_modes": list(HANDLE_MODES_FOLLOWUP),
            "pairs": pairs,
            # per-CELL (per target x seed) balance: half baseline-first, half target-first
            "per_cell_pairs": W * len(FIRST_OPERATION_IDS) * len(HANDLE_MODES_FOLLOWUP) * R,
            "per_cell_baseline_first": (W * len(FIRST_OPERATION_IDS)
                                        * len(HANDLE_MODES_FOLLOWUP) * R) // 2,
            "per_cell_target_first": (W * len(FIRST_OPERATION_IDS)
                                      * len(HANDLE_MODES_FOLLOWUP) * R) // 2,
        })
    if total_pairs != EXPECTED_FOLLOWUP_PAIRS:
        raise SystemExit("follow-up pairs %d != %d" % (total_pairs, EXPECTED_FOLLOWUP_PAIRS))
    return {
        "kind": "portability_ych01_followup_matrix",
        "purpose": "sign_stability_check_not_coverage",
        "workload_set": wl_union,
        "strategies": strat_union,
        "seeds": seed_union,
        "handle_modes": list(HANDLE_MODES_FOLLOWUP),    # standalone only
        "first_operation_ids": list(FIRST_OPERATION_IDS),
        "position_balance": POSITION_BALANCE,           # exact, enforced per cell/seed
        "schedule_seed": SCHEDULE_SEED_FOLLOWUP,
        "concurrency": 1,
        "sequential": True,
        "matrices": matrices,
        "total_pairs": total_pairs,
        "total_invocations": 2 * total_pairs,
    }


def portability_ych01_followup_run_config_sha256(plan):
    blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


# ----------------------------------------------------------------- reuse verification
def _keyed_matrix_cells():
    """Every (workload, strategy, seed) the follow-up schedules that needs a frozen keyed
    plan already present in the pin (static strategies excluded)."""
    cells = set()
    for mx in MATRICES_FOLLOWUP:
        for strat in mx["strategies"]:
            if strat in _KEYED_STRATS:
                for wl in mx["workloads"]:
                    for s in mx["seeds"]:
                        cells.add((wl, strat, s))
    return cells


def verify_reuse(pin):
    """Fail-closed check that every strategy/cell this campaign schedules is ALREADY present
    in the pin (reuse only). Returns a SORTED list of problems; empty == ok."""
    problems = []
    sp = pin.get("strategy_plans", {})
    for strat in ("baseline",) + _STATIC_STRATS + _KEYED_STRATS:
        if strat not in sp:
            problems.append("reused strategy %s absent from strategy_plans (not admissible)"
                            % strat)
    ksp = pin.get("keyed_strategy_plans", {})
    for (wl, strat, seed) in sorted(_keyed_matrix_cells()):
        e = ksp.get(wl, {}).get(str(seed), {}).get(strat)
        if e is None:
            problems.append("reused keyed plan missing: %s/%s/seed%d "
                            "(portability_ext must be pinned first)"
                            % (strat, wl, seed))
        elif e.get("bound_db_sha256") not in (None, BOUND_DB_SHA256):
            problems.append("reused keyed plan %s/%s/seed%d bound to a different test.db"
                            % (strat, wl, seed))
    return sorted(problems)


def reused_plan_identities(pin):
    """{cell_label: {source, sha256}} for the two followed-up cells -- the provenance the
    prep report prints. layers_5 resolves to its strategy_plans entry; 2f_top14 to its
    per-seed keyed_strategy_plans entry."""
    sp = pin.get("strategy_plans", {})
    ksp = pin.get("keyed_strategy_plans", {})
    out = {}
    for (wl, strat, seeds, _cat) in FOLLOWUP_CELLS:
        if strat in _KEYED_STRATS:
            for seed in seeds.split(","):
                e = ksp.get(wl, {}).get(seed, {}).get(strat, {})
                out["%s/%s/seed%s" % (wl, strat, seed)] = {
                    "source": "keyed_strategy_plans", "path": e.get("path"),
                    "sha256": e.get("sha256")}
        else:
            e = sp.get(strat, {})
            out["%s/%s" % (wl, strat)] = {
                "source": "strategy_plans", "path": e.get("path"),
                "sha256": e.get("sha256")}
    return out


def crosscheck_followup(pin):
    """Fail closed unless the pin (a) already carries every reused strategy/plan the campaign
    needs, and (b) carries the follow-up invocation-plan identity matching the recomputed
    one. Adds NOTHING itself -- proves the reuse-only + identity contract."""
    problems = verify_reuse(pin)
    ip = pin.get("portability_ych01_followup_invocation_plan")
    if ip is None:
        problems.append("pin missing portability_ych01_followup_invocation_plan")
    else:
        want = portability_ych01_followup_invocation_plan()
        if json.dumps(ip, sort_keys=True) != json.dumps(want, sort_keys=True):
            problems.append("pin portability_ych01_followup_invocation_plan != recomputed")
        want_sha = portability_ych01_followup_run_config_sha256(want)
        if pin.get("portability_ych01_followup_run_config_sha256") != want_sha:
            problems.append("pin portability_ych01_followup_run_config_sha256 != recomputed")
    return sorted(problems)


if __name__ == "__main__":
    _plan = portability_ych01_followup_invocation_plan()
    _sha = portability_ych01_followup_run_config_sha256(_plan)
    print("portability_ych01_followup_run_config_sha256 =", _sha)
    print("schedule_seed =", SCHEDULE_SEED_FOLLOWUP, " handle_modes =", HANDLE_MODES_FOLLOWUP,
          " position_balance =", POSITION_BALANCE)
    print("total_pairs =", _plan["total_pairs"],
          " total_invocations =", _plan["total_invocations"])
    for mx in _plan["matrices"]:
        print("  %-3s %-28s targets=%s seeds=%s reps=%d pairs=%d (per-cell %d/%d)"
              % (mx["name"], ",".join(mx["workloads"]),
                 [s for s in mx["strategies"] if s != "baseline"],
                 mx["seeds"], mx["reps"], mx["pairs"],
                 mx["per_cell_baseline_first"], mx["per_cell_target_first"]))
