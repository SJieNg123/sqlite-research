#!/usr/bin/env python3
"""Single source of truth for the workstation<->OpenWhisk OUTLIER-REPLICATION campaign.

SIXTH additive campaign; a targeted STABILITY / CONFOUND check, NOT new coverage. It
re-runs, under EXACT baseline-target position balance and STANDALONE handles only, the
six (workload, strategy) cells whose original OpenWhisk<->workstation first-query
effectiveness discrepancy is largest -- the category (1) sign-flips and the category (2)
WS-neutral / OW-side anomalies surfaced by ``analysis/compare_effectiveness.py``:

    C / layers_92     (read_tail_mixed_20k)   -- cat (1) sign-flip, orig low-n / imbalanced
    C / 2d            (read_tail_mixed_20k)   -- cat (1) sign-flip, orig 0/3 target-first
    C / layers_5      (read_tail_mixed_20k)   -- cat (1) WS-neutral, OW strongly negative
    YCh01 / layers_5  (native_ycsb_c_hot_hashed_01) -- cat (2) large layers_5 discrepancy
    YCu / layers_5    (native_ycsb_c_read_uniform)  -- cat (2) large layers_5 discrepancy
    C_hit / 2e_K40    (read_tail_hit_20k)     -- cat (1) sign-flip, orig 2/7 imbalance

WHY THIS EXISTS: the original five formal campaigns assign each pair's AB/BA order by a
per-pair hash coin-flip (build_schedule._order); for small n that yields the very
0/3 and 2/7 imbalances above. This campaign tests whether those discrepancies are STABLE
deployment effects or ARTIFACTS of low n / position imbalance / short-lived execution
state, by re-running the same cells with DETERMINISTICALLY EXACT position balance.

This module is imported by both:
  * ``build_artifact_manifest.py`` -- MERGE the replication invocation plan +
    run_config sha256 additively into the live ``config/artifacts.json`` (NO new keyed
    plans, NO new markers: every strategy is reused, already admissible + implemented);
  * ``tools/write_portability_outlier_replication_pin.py`` -- emit the same two
    top-level identity keys into the frozen replay pin, freezing ALL FIVE prior
    campaign identities byte-unchanged.

REUSE-ONLY. Nothing is frozen or generated here:
  * ``2e_K40`` on read_tail_hit_20k seeds 1,2,3 reuses the AUDITED full-closure keyed
    plans already in ``keyed_strategy_plans`` (frozen by the portability_full_closure
    layer);
  * ``layers_92`` / ``layers_5`` / ``2d`` reuse the committed static strategy artifacts
    (the 92-interior skeleton, the 5-interior prefix, and the 2d skeleton).
So this campaign adds ZERO coverage: all six cells are members of the existing frozen
65-cell canonical portability matrix.

Independent campaign identity: its OWN ``SCHEDULE_SEED_REPL`` (20260830, off the round
marks and distinct from primary 20260804 / secondary 20260825 / portability 20260826 /
portability_ext 20260828 / portability_full_closure 20260829) and its OWN
``portability_outlier_replication_run_config_sha256``. It shares the same image / DB /
classifier / action / cold-reset / oracle / handle semantics as every prior campaign.

INTERPRETATION IS PRE-REGISTERED (see PORTABILITY_OUTLIER_REPLICATION.md and
analysis/analyze_outlier_replication.py). The replication does NOT replace the original
R_ow values; both batches are reported side by side and each cell is classified.
"""
import hashlib
import json

import portability_manifest as PM  # sibling; reused for WORKLOAD_SET + helpers

# workload ids (identical to portability_full_closure_manifest)
YC = "native_ycsb_c_read_zipf"
YCU = "native_ycsb_c_read_uniform"
YCH01 = "native_ycsb_c_hot_hashed_01"
CHIT = "read_tail_hit_20k"
CMIX = "read_tail_mixed_20k"

# Independent campaign identity: a new schedule seed, distinct from every prior
# campaign and off the round marks.
SCHEDULE_SEED_REPL = 20260830

# STANDALONE ONLY -- the workstation<->OpenWhisk effectiveness comparison uses the
# standalone handle, so the formal replication is standalone-only (no warm arm).
HANDLE_MODES_REPL = ["standalone"]
FIRST_OPERATION_IDS = [0]

# Position balance is a HARD scientific requirement of this campaign: every single/
# static cell must be EXACTLY baseline_first == target_first, deterministically (not
# approximately-by-random). The matrix carries "position_balance": "exact"; the schedule
# builder + validator enforce it per cell. Every per-cell rep count MUST be even.
POSITION_BALANCE = "exact"

# The four rectangular replication sub-matrices (strict Cartesian products). Targets =
# strategies minus baseline; every block anchors on the paired baseline A-arm.
#   Pairs = |W| * |S| * |F| * |M| * reps * |T|   (F=1, M=1 standalone-only).
# Per-block reps: 20 for the single/static cells (-> 10 baseline-first / 10 target-first
# per cell); 6 for C_hit/2e_K40 per seed (-> 3 / 3 per seed).
MATRICES_REPL = [
    {"name": "R1", "workloads": [CMIX],
     "strategies": ["baseline", "layers_92", "2d", "layers_5"],
     "seeds": [1], "reps": 20},                       # 1*1*1*1*20*3 = 60
    {"name": "R2", "workloads": [YCH01],
     "strategies": ["baseline", "layers_5"],
     "seeds": [1], "reps": 20},                       # 1*1*1*1*20*1 = 20
    {"name": "R3", "workloads": [YCU],
     "strategies": ["baseline", "layers_5"],
     "seeds": [1], "reps": 20},                       # 1*1*1*1*20*1 = 20
    {"name": "R4", "workloads": [CHIT],
     "strategies": ["baseline", "2e_K40"],
     "seeds": [1, 2, 3], "reps": 6},                  # 1*3*1*1*6*1 = 18
]

EXPECTED_REPL_PAIRS = 118
EXPECTED_REPL_INVOCATIONS = 236

# The exact six (workload, strategy) cells this campaign replicates. Frozen literal so a
# drift in MATRICES_REPL is caught. Category tag is provenance only (NOT a claim).
REPL_CELLS = [
    (CMIX, "layers_92", "1", "sign_flip"),
    (CMIX, "2d", "1", "sign_flip"),
    (CMIX, "layers_5", "1", "ws_neutral_ow_anomaly"),
    (YCH01, "layers_5", "1", "layers5_discrepancy"),
    (YCU, "layers_5", "1", "layers5_discrepancy"),
    (CHIT, "2e_K40", "1,2,3", "sign_flip"),
]

# Strategies this campaign reuses, and how each is resolved in the frozen pin.
#   static  -> strategy_plans[<strat>] carries inline offsets (no per-seed keyed plan)
#   keyed   -> keyed_strategy_plans[<workload>][<seed>][<strat>] (per-seed frozen plan)
_STATIC_STRATS = ("layers_92", "2d", "layers_5")
_KEYED_STRATS = ("2e_K40",)
BOUND_DB_SHA256 = PM.BOUND_DB_SHA256


# ----------------------------------------------------------------- invocation plan
def portability_outlier_replication_invocation_plan():
    """The independent replication run-config identity source. Pure-literal structure
    from MATRICES_REPL (no offsets/shas), recomputed identically on WK1 and WK2. The
    identity BINDS the standalone-only handle set, the exact-position-balance flag, and
    the schedule seed, so a run under any other handle/balance/seed has a different
    run_config sha256."""
    strat_union = sorted({s for mx in MATRICES_REPL for s in mx["strategies"]})
    wl_union = sorted({w for mx in MATRICES_REPL for w in mx["workloads"]})
    seed_union = sorted({s for mx in MATRICES_REPL for s in mx["seeds"]})
    total_pairs = 0
    matrices = []
    for mx in MATRICES_REPL:
        W = len(mx["workloads"]); S = len(mx["seeds"]); R = int(mx["reps"])
        T = len([s for s in mx["strategies"] if s != "baseline"])
        if R % 2 != 0:
            raise SystemExit("block %s reps=%d must be even for exact position balance"
                             % (mx["name"], R))
        pairs = W * S * len(FIRST_OPERATION_IDS) * len(HANDLE_MODES_REPL) * R * T
        total_pairs += pairs
        matrices.append({
            "name": mx["name"],
            "workloads": list(mx["workloads"]),
            "strategies": list(mx["strategies"]),
            "seeds": list(mx["seeds"]),
            "reps": R,
            "handle_modes": list(HANDLE_MODES_REPL),
            "pairs": pairs,
            # per-CELL (per target x seed) balance: half baseline-first, half target-first
            "per_cell_pairs": W * len(FIRST_OPERATION_IDS) * len(HANDLE_MODES_REPL) * R,
            "per_cell_baseline_first": (W * len(FIRST_OPERATION_IDS)
                                        * len(HANDLE_MODES_REPL) * R) // 2,
            "per_cell_target_first": (W * len(FIRST_OPERATION_IDS)
                                      * len(HANDLE_MODES_REPL) * R) // 2,
        })
    if total_pairs != EXPECTED_REPL_PAIRS:
        raise SystemExit("replication pairs %d != %d" % (total_pairs, EXPECTED_REPL_PAIRS))
    return {
        "kind": "portability_outlier_replication_matrix",
        "purpose": "stability_confound_check_not_coverage",
        "workload_set": wl_union,
        "strategies": strat_union,
        "seeds": seed_union,
        "handle_modes": list(HANDLE_MODES_REPL),        # standalone only
        "first_operation_ids": list(FIRST_OPERATION_IDS),
        "position_balance": POSITION_BALANCE,           # exact, enforced per cell
        "schedule_seed": SCHEDULE_SEED_REPL,
        "concurrency": 1,
        "sequential": True,
        "matrices": matrices,
        "total_pairs": total_pairs,
        "total_invocations": 2 * total_pairs,
    }


def portability_outlier_replication_run_config_sha256(plan):
    blob = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


# ----------------------------------------------------------------- reuse verification
def _keyed_matrix_cells():
    """Every (workload, strategy, seed) the replication schedules that needs a frozen
    keyed plan already present in the pin (static strategies excluded)."""
    cells = set()
    for mx in MATRICES_REPL:
        for strat in mx["strategies"]:
            if strat in _KEYED_STRATS:
                for wl in mx["workloads"]:
                    for s in mx["seeds"]:
                        cells.add((wl, strat, s))
    return cells


def verify_reuse(pin):
    """Fail-closed check that every strategy/cell this campaign schedules is ALREADY
    present in the pin (reuse only). Returns a SORTED list of problems; empty == ok."""
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
                            "(portability_full_closure must be pinned first)"
                            % (strat, wl, seed))
        elif e.get("bound_db_sha256") not in (None, BOUND_DB_SHA256):
            problems.append("reused keyed plan %s/%s/seed%d bound to a different test.db"
                            % (strat, wl, seed))
    return sorted(problems)


def reused_plan_identities(pin):
    """{cell_label: {source, sha256}} for the six replicated cells -- the provenance the
    prep report prints. Static strategies resolve to their strategy_plans entry; keyed
    strategies to their per-seed keyed_strategy_plans entry."""
    sp = pin.get("strategy_plans", {})
    ksp = pin.get("keyed_strategy_plans", {})
    out = {}
    for (wl, strat, seeds, _cat) in REPL_CELLS:
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


def crosscheck_replication(pin):
    """Fail closed unless the pin (a) already carries every reused strategy/plan the
    campaign needs, and (b) carries the replication invocation-plan identity matching the
    recomputed one. Adds NOTHING itself -- proves the reuse-only + identity contract."""
    problems = verify_reuse(pin)
    ip = pin.get("portability_outlier_replication_invocation_plan")
    if ip is None:
        problems.append("pin missing portability_outlier_replication_invocation_plan")
    else:
        want = portability_outlier_replication_invocation_plan()
        if json.dumps(ip, sort_keys=True) != json.dumps(want, sort_keys=True):
            problems.append("pin portability_outlier_replication_invocation_plan != recomputed")
        want_sha = portability_outlier_replication_run_config_sha256(want)
        if pin.get("portability_outlier_replication_run_config_sha256") != want_sha:
            problems.append("pin portability_outlier_replication_run_config_sha256 != recomputed")
    return sorted(problems)


if __name__ == "__main__":
    _plan = portability_outlier_replication_invocation_plan()
    _sha = portability_outlier_replication_run_config_sha256(_plan)
    print("portability_outlier_replication_run_config_sha256 =", _sha)
    print("schedule_seed =", SCHEDULE_SEED_REPL, " handle_modes =", HANDLE_MODES_REPL,
          " position_balance =", POSITION_BALANCE)
    print("total_pairs =", _plan["total_pairs"],
          " total_invocations =", _plan["total_invocations"])
    for mx in _plan["matrices"]:
        print("  %-3s %-28s targets=%s seeds=%s reps=%d pairs=%d (per-cell %d/%d)"
              % (mx["name"], ",".join(mx["workloads"]),
                 [s for s in mx["strategies"] if s != "baseline"],
                 mx["seeds"], mx["reps"], mx["pairs"],
                 mx["per_cell_baseline_first"], mx["per_cell_target_first"]))
