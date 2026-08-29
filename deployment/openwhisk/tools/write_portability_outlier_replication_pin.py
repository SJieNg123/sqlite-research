#!/usr/bin/env python3
"""Additively write the OUTLIER-REPLICATION campaign identity into the frozen replay pin.

Sibling of ``write_portability_full_closure_pin.py`` but MAXIMALLY minimal: this campaign
is a reuse-only STABILITY / CONFOUND check, so it adds NO keyed plans and NO strategy
markers. It emits ONLY the two top-level identity keys into
``config/artifacts.native_ycsb.json``:
  * portability_outlier_replication_invocation_plan
  * portability_outlier_replication_run_config_sha256  (+ a _note)

Fail-closed guarantees (freezes ALL FIVE prior campaign identities):
  * primary (022fbeb0..), secondary (441609e6..), portability (64f44c3e..),
    portability_ext (bf504a28..) AND portability_full_closure (a5be8f15..) invocation
    plans + run_config shas are asserted byte-unchanged before and after the edit;
  * keyed_strategy_plans and strategy_plans are asserted byte-UNCHANGED (added_keyed==0,
    added_markers==0) -- every strategy this campaign schedules is already admissible and
    already frozen (2e_K40 keyed plans from the full-closure layer; layers_92/2d/layers_5
    static strategy artifacts). The reuse is verified (fail-closed) before writing;
  * the recomputed run_config sha is re-tied via the single-source manifest crosscheck.

No new workload traces are written: all four replication workloads x their seeds already
resolve. This campaign adds ZERO coverage -- coverage stays 65/65.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
import portability_outlier_replication_manifest as OR  # noqa: E402

PIN_REL = "deployment/openwhisk/config/artifacts.native_ycsb.json"

# every prior campaign identity that MUST remain byte-frozen (plan key, run_config key)
FROZEN_IDS = [
    ("invocation_plan", "run_config_sha256"),                       # primary 022fbeb0
    ("secondary_invocation_plan", "secondary_run_config_sha256"),   # secondary 441609e6
    ("portability_invocation_plan", "portability_run_config_sha256"),               # 64f44c3e
    ("portability_ext_invocation_plan", "portability_ext_run_config_sha256"),       # bf504a28
    ("portability_full_closure_invocation_plan",
     "portability_full_closure_run_config_sha256"),                                 # a5be8f15
]


def main():
    pin_path = os.path.join(ROOT, PIN_REL)
    with open(pin_path) as f:
        pin = json.load(f)

    # -- require every prior identity present --------------------------------
    for _plan_k, rc_k in FROZEN_IDS:
        if rc_k not in pin:
            raise SystemExit("pin missing %s -- run the prior pin writers first" % rc_k)

    # -- snapshot ALL FIVE immutable identities + the two reuse tables BEFORE edit
    frozen = {}
    for plan_k, rc_k in FROZEN_IDS:
        frozen[rc_k] = pin[rc_k]
        frozen[plan_k] = json.dumps(pin[plan_k], sort_keys=True)
    ksp_before = json.dumps(pin.get("keyed_strategy_plans", {}), sort_keys=True)
    sp_before = json.dumps(pin.get("strategy_plans", {}), sort_keys=True)

    # -- reuse verification: every scheduled strategy/plan already present --------
    problems = OR.verify_reuse(pin)
    if problems:
        raise SystemExit("reuse verification failed (campaign is reuse-only):\n  "
                         + "\n  ".join(problems))

    plan = OR.portability_outlier_replication_invocation_plan()
    rc_sha = OR.portability_outlier_replication_run_config_sha256(plan)

    # every replication workload must already be admissible (no workload_set change)
    for wl in plan["workload_set"]:
        if wl not in pin.get("workload_set", []):
            raise SystemExit("replication workload %s not in pin workload_set" % wl)

    # -- write ONLY the two top-level identity keys (+ note) ----------------------
    pin["portability_outlier_replication_invocation_plan"] = plan
    pin["portability_outlier_replication_run_config_sha256"] = rc_sha
    pin["portability_outlier_replication_run_config_sha256_note"] = (
        "Deterministic sha256 over the canonical portability_outlier_replication_"
        "invocation_plan (sorted-key compact JSON). Independent identity for the SIXTH "
        "additive campaign: a targeted STABILITY / CONFOUND replication (NOT new coverage) "
        "of the six largest workstation<->OpenWhisk first-query discrepancies -- C/layers_92, "
        "C/2d, C/layers_5, YCh01/layers_5, YCu/layers_5 (each 20 pairs, 10 baseline-first / "
        "10 target-first) and C_hit/2e_K40 (seeds 1,2,3; each 6 pairs, 3/3) -- 118 pairs / "
        "236 invocations, STANDALONE ONLY, schedule_seed=%d, position_balance=exact "
        "(deterministic per-cell balanced AB/BA, not the per-pair coin-flip). Distinct from "
        "primary (022fbeb0..), secondary (441609e6..), portability (64f44c3e..), "
        "portability_ext (bf504a28..) and portability_full_closure (a5be8f15..) run configs, "
        "which are byte-frozen and untouched. REUSE-ONLY: adds NO keyed plans and NO markers "
        "(2e_K40 reuses the audited full-closure keyed plans; layers_92/2d/layers_5 reuse "
        "committed static strategy artifacts), so it adds ZERO coverage -- all six cells are "
        "already members of the frozen 65-cell canonical portability matrix (coverage stays "
        "65/65). Does NOT replace the original R_ow analysis; both batches are reported and "
        "each cell classified (analysis/analyze_outlier_replication.py, "
        "PORTABILITY_OUTLIER_REPLICATION.md)." % OR.SCHEDULE_SEED_REPL)

    # -- fail closed: all five prior identities + both reuse tables unchanged -----
    for plan_k, rc_k in FROZEN_IDS:
        if pin[rc_k] != frozen[rc_k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % rc_k)
        if json.dumps(pin[plan_k], sort_keys=True) != frozen[plan_k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % plan_k)
    if json.dumps(pin.get("keyed_strategy_plans", {}), sort_keys=True) != ksp_before:
        raise SystemExit("FATAL: keyed_strategy_plans changed (campaign must add 0 keyed)")
    if json.dumps(pin.get("strategy_plans", {}), sort_keys=True) != sp_before:
        raise SystemExit("FATAL: strategy_plans changed (campaign must add 0 markers)")

    # -- self-crosscheck before writing ------------------------------------------
    problems = OR.crosscheck_replication(pin)
    if problems:
        raise SystemExit("replication crosscheck failed:\n  " + "\n  ".join(problems))

    with open(pin_path, "w") as f:
        json.dump(pin, f, indent=2)
        f.write("\n")
    print("pin updated: +0 keyed entries, +0 markers, "
          "portability_outlier_replication_run_config_sha256=%s" % rc_sha)
    print("frozen identities intact: primary=%s secondary=%s portability=%s ext=%s "
          "full_closure=%s"
          % (pin["run_config_sha256"][:12], pin["secondary_run_config_sha256"][:12],
             pin["portability_run_config_sha256"][:12],
             pin["portability_ext_run_config_sha256"][:12],
             pin["portability_full_closure_run_config_sha256"][:12]))


if __name__ == "__main__":
    main()
