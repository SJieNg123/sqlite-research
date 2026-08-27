#!/usr/bin/env python3
"""Additively write the PORTABILITY layer into the frozen replay pin.

Emits, into ``config/artifacts.native_ycsb.json``:
  * keyed_strategy_plans: the four NEW workloads (seeds 1-3) + the two N=28
    strategies on the canonical YC workload (seeds 1-3), all offset-free;
  * strategy_plans: the 2f_top28 / learned_markov_28 admissibility markers;
  * workload_set, portability_workload_traces (per-workload trace path+sha),
    portability_invocation_plan + portability_run_config_sha256 (independent
    identity), and their notes.

Fail-closed guarantees enforced here:
  * the primary/secondary invocation plans and their run_config identities
    (022fbeb0.../441609e6...) are asserted byte-unchanged;
  * no existing keyed entry is overwritten (only new (workload,seed,strategy)
    triples are added);
  * every entry is derived from the verified freeze report via
    tools/portability_manifest.py (single source of truth).

All entries are re-proven against the generated live manifest by the builder's
extended crosscheck; running the builder after this must succeed.
"""
import csv
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
import portability_manifest as PM  # noqa: E402

PIN_REL = "deployment/openwhisk/config/artifacts.native_ycsb.json"
SKELETON_REL = "deployment/openwhisk/config/plans/interior_pages.csv"
DB_REL = "pipeline/preparation/layout_rewriter/runs/test.db"
PAGE_SIZE = 4096


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def skeleton_offset_set():
    offs = set()
    with open(os.path.join(ROOT, SKELETON_REL), newline="") as f:
        for row in csv.DictReader(f):
            offs.add(int(row["file_offset"]))
    if len(offs) != 92:
        raise SystemExit("skeleton must be 92 interiors, got %d" % len(offs))
    return offs


def page_count():
    with open(os.path.join(ROOT, DB_REL), "rb") as f:
        head = f.read(32)
    return int.from_bytes(head[28:32], "big")


def main():
    pin_path = os.path.join(ROOT, PIN_REL)
    with open(pin_path) as f:
        pin = json.load(f)

    # Snapshot the immutable primary/secondary identities BEFORE any edit.
    frozen = {
        "invocation_plan": json.dumps(pin["invocation_plan"], sort_keys=True),
        "run_config_sha256": pin["run_config_sha256"],
        "secondary_invocation_plan": json.dumps(pin["secondary_invocation_plan"], sort_keys=True),
        "secondary_run_config_sha256": pin["secondary_run_config_sha256"],
    }

    iset = skeleton_offset_set()
    pc = page_count()
    _live, pin_block, meta = PM.build_portability_entries(ROOT, iset, PAGE_SIZE, pc)
    markers = PM.build_new_markers(meta)
    plan = PM.portability_invocation_plan(meta)
    rc_sha = PM.portability_run_config_sha256(plan)

    # ---- merge keyed_strategy_plans (additive; never overwrite) -------------
    ksp = pin.setdefault("keyed_strategy_plans", {})
    added = 0
    for wl, seeds in pin_block.items():
        wdst = ksp.setdefault(wl, {})
        for seed_str, strats in seeds.items():
            sdst = wdst.setdefault(seed_str, {})
            for strat, entry in strats.items():
                if strat in sdst:
                    raise SystemExit("refusing to overwrite existing keyed %s/%s/%s"
                                     % (strat, wl, seed_str))
                sdst[strat] = entry
                added += 1
    if added != 36:
        raise SystemExit("expected to add 36 keyed entries, added %d" % added)

    # ---- merge strategy_plans markers (additive) ----------------------------
    sp = pin["strategy_plans"]
    for strat, marker in markers.items():
        if strat in sp:
            raise SystemExit("marker %s already present in pin" % strat)
        sp[strat] = marker

    # ---- per-workload trace provenance (new workloads only) -----------------
    port_traces = {}
    for wl in PM.NEW_WORKLOADS:
        tmpl = PM.TRACE_TEMPLATES[wl]
        seedmap = {}
        for s in PM.PORTABILITY_SEEDS:
            rel = tmpl % s
            seedmap[str(s)] = {"path": rel, "sha256": sha256_file(os.path.join(ROOT, rel))}
        port_traces[wl] = {"seeds": seedmap}

    # ---- top-level portability blocks ---------------------------------------
    pin["workload_set"] = list(PM.WORKLOAD_SET)
    pin["workload_set_note"] = ("Authoritative set of workload IDs the portability "
                                "matrix (deployment complement) may address. ws2 05 "
                                "unions this with the canonical id for its workload "
                                "gate; session.py refuses any keyed plan for a "
                                "workload outside this set. Additive to the primary/"
                                "secondary YC campaigns, which are unaffected.")
    pin["portability_workload_traces"] = port_traces
    pin["portability_invocation_plan"] = plan
    pin["portability_run_config_sha256"] = rc_sha
    pin["portability_run_config_sha256_note"] = (
        "Deterministic sha256 over the canonical portability_invocation_plan "
        "(sorted-key compact JSON). Independent identity for the workstation->"
        "OpenWhisk portability matrix (234 pairs / 468 invocations across 4 "
        "rectangular sub-matrices, schedule_seed=%d). Distinct from the primary "
        "(022fbeb0...) and secondary (441609e6...) YC run configs, which are "
        "byte-frozen and untouched. Deployment/feasibility + footprint evidence "
        "only; warm paired first-query latency is NOT a strategy-performance "
        "estimate (see analysis/thesis/threats_to_validity.md)." % PM.SCHEDULE_SEED)

    # ---- fail closed: immutable identities unchanged ------------------------
    for k in ("run_config_sha256", "secondary_run_config_sha256"):
        if pin[k] != frozen[k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % k)
    if json.dumps(pin["invocation_plan"], sort_keys=True) != frozen["invocation_plan"]:
        raise SystemExit("FATAL: invocation_plan changed (must be byte-frozen)")
    if json.dumps(pin["secondary_invocation_plan"], sort_keys=True) != frozen["secondary_invocation_plan"]:
        raise SystemExit("FATAL: secondary_invocation_plan changed (must be byte-frozen)")

    # ---- self-crosscheck before writing -------------------------------------
    problems = PM.crosscheck(pin, meta, ROOT)
    if problems:
        raise SystemExit("crosscheck failed:\n  " + "\n  ".join(problems))

    with open(pin_path, "w") as f:
        json.dump(pin, f, indent=2)
        f.write("\n")
    print("pin updated: +%d keyed entries, +%d markers, workload_set=%d, "
          "portability_run_config_sha256=%s"
          % (added, len(markers), len(PM.WORKLOAD_SET), rc_sha))
    print("frozen identities intact: run_config_sha256=%s secondary=%s"
          % (pin["run_config_sha256"][:12], pin["secondary_run_config_sha256"][:12]))


if __name__ == "__main__":
    main()
