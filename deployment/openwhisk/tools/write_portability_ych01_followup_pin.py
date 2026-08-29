#!/usr/bin/env python3
"""Additively write the YCH01 TWO-CELL FOLLOW-UP campaign identity into the frozen replay pin.

Sibling of ``write_portability_outlier_replication_pin.py`` and MAXIMALLY minimal: this
campaign is a reuse-only SIGN / STABILITY check, so it adds NO keyed plans and NO strategy
markers. It emits ONLY the two top-level identity keys into
``config/artifacts.native_ycsb.json``:
  * portability_ych01_followup_invocation_plan
  * portability_ych01_followup_run_config_sha256  (+ a _note)

Fail-closed guarantees (freezes ALL SIX prior campaign identities):
  * primary (022fbeb0..), secondary (441609e6..), portability (64f44c3e..),
    portability_ext (bf504a28..), portability_full_closure (a5be8f15..) AND
    portability_outlier_replication (a564770a..) invocation plans + run_config shas are
    asserted byte-unchanged before and after the edit;
  * keyed_strategy_plans and strategy_plans are asserted byte-UNCHANGED (added_keyed==0,
    added_markers==0) -- both strategies this campaign schedules are already admissible and
    already frozen (2f_top14 keyed plans from the portability_ext layer; layers_5 static
    strategy artifact). The reuse is verified (fail-closed) before writing;
  * the recomputed run_config sha is re-tied via the single-source manifest crosscheck.

No new workload traces are written: YCh01 x its seeds already resolve. This campaign adds
ZERO coverage -- coverage stays 65/65 and the frozen 55-cell headline comparison is untouched.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
import portability_ych01_followup_manifest as YF  # noqa: E402

PIN_REL = "deployment/openwhisk/config/artifacts.native_ycsb.json"

# every prior campaign identity that MUST remain byte-frozen (plan key, run_config key)
FROZEN_IDS = [
    ("invocation_plan", "run_config_sha256"),                       # primary 022fbeb0
    ("secondary_invocation_plan", "secondary_run_config_sha256"),   # secondary 441609e6
    ("portability_invocation_plan", "portability_run_config_sha256"),               # 64f44c3e
    ("portability_ext_invocation_plan", "portability_ext_run_config_sha256"),       # bf504a28
    ("portability_full_closure_invocation_plan",
     "portability_full_closure_run_config_sha256"),                                 # a5be8f15
    ("portability_outlier_replication_invocation_plan",
     "portability_outlier_replication_run_config_sha256"),                          # a564770a
]


def main():
    pin_path = os.path.join(ROOT, PIN_REL)
    with open(pin_path) as f:
        pin = json.load(f)

    # -- require every prior identity present --------------------------------
    for _plan_k, rc_k in FROZEN_IDS:
        if rc_k not in pin:
            raise SystemExit("pin missing %s -- run the prior pin writers first" % rc_k)

    # -- snapshot ALL SIX immutable identities + the two reuse tables BEFORE edit
    frozen = {}
    for plan_k, rc_k in FROZEN_IDS:
        frozen[rc_k] = pin[rc_k]
        frozen[plan_k] = json.dumps(pin[plan_k], sort_keys=True)
    ksp_before = json.dumps(pin.get("keyed_strategy_plans", {}), sort_keys=True)
    sp_before = json.dumps(pin.get("strategy_plans", {}), sort_keys=True)

    # -- reuse verification: every scheduled strategy/plan already present --------
    problems = YF.verify_reuse(pin)
    if problems:
        raise SystemExit("reuse verification failed (campaign is reuse-only):\n  "
                         + "\n  ".join(problems))

    plan = YF.portability_ych01_followup_invocation_plan()
    rc_sha = YF.portability_ych01_followup_run_config_sha256(plan)

    # every follow-up workload must already be admissible (no workload_set change)
    for wl in plan["workload_set"]:
        if wl not in pin.get("workload_set", []):
            raise SystemExit("follow-up workload %s not in pin workload_set" % wl)

    # -- write ONLY the two top-level identity keys (+ note) ----------------------
    pin["portability_ych01_followup_invocation_plan"] = plan
    pin["portability_ych01_followup_run_config_sha256"] = rc_sha
    pin["portability_ych01_followup_run_config_sha256_note"] = (
        "Deterministic sha256 over the canonical portability_ych01_followup_invocation_plan "
        "(sorted-key compact JSON). Independent identity for the SEVENTH additive campaign: a "
        "targeted SIGN / STABILITY follow-up (NOT new coverage) of the ONLY two cells whose "
        "latest workstation first-query effect is positive but OpenWhisk is non-positive -- "
        "YCh01/layers_5 (36 pairs, 18 baseline-first / 18 target-first) and YCh01/2f_top14 "
        "(seeds 1,2,3; each 12 pairs, 6/6) -- 72 pairs / 144 invocations, STANDALONE ONLY, "
        "schedule_seed=%d, position_balance=exact (deterministic per-cell/per-seed balanced "
        "AB/BA, not the per-pair coin-flip). The previously observed direction is described "
        "only as a pair-position / short-lived execution-state / execution-storage-state "
        "effect; no specific physical mechanism is attributed. Distinct from primary "
        "(022fbeb0..), secondary (441609e6..), portability (64f44c3e..), portability_ext "
        "(bf504a28..), portability_full_closure (a5be8f15..) and portability_outlier_"
        "replication (a564770a..) run configs, which are byte-frozen and untouched. "
        "REUSE-ONLY: adds NO keyed plans and NO markers (2f_top14 reuses the audited "
        "portability_ext keyed plans; layers_5 reuses the committed static strategy "
        "artifact), so it adds ZERO coverage -- both cells are already members of the frozen "
        "65-cell canonical portability matrix (coverage stays 65/65). Does NOT replace the "
        "original R_ow analysis and does NOT alter the frozen 55-cell headline comparison; "
        "the prior batches and this one are reported side by side." % YF.SCHEDULE_SEED_FOLLOWUP)

    # -- fail closed: all six prior identities + both reuse tables unchanged -------
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
    problems = YF.crosscheck_followup(pin)
    if problems:
        raise SystemExit("follow-up crosscheck failed:\n  " + "\n  ".join(problems))

    with open(pin_path, "w") as f:
        json.dump(pin, f, indent=2)
        f.write("\n")
    print("pin updated: +0 keyed entries, +0 markers, "
          "portability_ych01_followup_run_config_sha256=%s" % rc_sha)
    print("frozen identities intact: primary=%s secondary=%s portability=%s ext=%s "
          "full_closure=%s outlier_replication=%s"
          % (pin["run_config_sha256"][:12], pin["secondary_run_config_sha256"][:12],
             pin["portability_run_config_sha256"][:12],
             pin["portability_ext_run_config_sha256"][:12],
             pin["portability_full_closure_run_config_sha256"][:12],
             pin["portability_outlier_replication_run_config_sha256"][:12]))


if __name__ == "__main__":
    main()
