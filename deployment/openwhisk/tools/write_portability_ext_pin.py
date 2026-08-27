#!/usr/bin/env python3
"""Additively write the PORTABILITY-EXT layer into the frozen replay pin.

Sibling of ``write_portability_pin.py``. Emits, into
``config/artifacts.native_ycsb.json``:
  * keyed_strategy_plans: the 63 ext plans (21 keyed cells x seeds 1-3), offset-free;
  * strategy_plans: the three NEW markers (2f_top14, learned_markov_14, layers_92);
  * portability_ext_invocation_plan + portability_ext_run_config_sha256 (an
    independent campaign identity, schedule_seed 20260828) + note.

Fail-closed guarantees (STRICTER than the portability writer -- it also freezes the
portability identity):
  * primary (022fbeb0..), secondary (441609e6..), AND portability (64f44c3e..)
    invocation plans + run_config shas are asserted byte-unchanged;
  * no existing keyed entry is overwritten -- the 63 ext triples are disjoint from
    the 106 already in the pin (verified: YCu/YCh01 2f_top28/learned_markov_28 were
    never frozen by the portability layer); ``added != 63`` aborts;
  * every entry is derived from the verified ext freeze report via
    ``portability_ext_manifest.py`` (single source of truth).

No new workload traces are written: all five ext workloads x seeds 1-3 already
resolve (the four new workloads via ``portability_workload_traces``, YC via the
primary path). The builder's extended crosscheck re-proves every ext plan against the
generated live manifest afterwards.
"""
import csv
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
import portability_ext_manifest as XE  # noqa: E402

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


def skeleton_offsets():
    offs = []
    with open(os.path.join(ROOT, SKELETON_REL), newline="") as f:
        for row in csv.DictReader(f):
            offs.append(int(row["file_offset"]))
    if len(set(offs)) != 92:
        raise SystemExit("skeleton must be 92 interiors, got %d" % len(set(offs)))
    return offs


def page_count():
    with open(os.path.join(ROOT, DB_REL), "rb") as f:
        head = f.read(32)
    return int.from_bytes(head[28:32], "big")


def main():
    pin_path = os.path.join(ROOT, PIN_REL)
    with open(pin_path) as f:
        pin = json.load(f)

    # Snapshot the immutable primary / secondary / PORTABILITY identities BEFORE edit.
    for req in ("portability_invocation_plan", "portability_run_config_sha256"):
        if req not in pin:
            raise SystemExit("pin missing %s -- run write_portability_pin.py first" % req)
    frozen = {
        "invocation_plan": json.dumps(pin["invocation_plan"], sort_keys=True),
        "run_config_sha256": pin["run_config_sha256"],
        "secondary_invocation_plan": json.dumps(pin["secondary_invocation_plan"], sort_keys=True),
        "secondary_run_config_sha256": pin["secondary_run_config_sha256"],
        "portability_invocation_plan": json.dumps(pin["portability_invocation_plan"], sort_keys=True),
        "portability_run_config_sha256": pin["portability_run_config_sha256"],
    }

    skel = skeleton_offsets()
    iset = set(skel)
    pc = page_count()
    skel_sha = sha256_file(os.path.join(ROOT, SKELETON_REL))
    _live, pin_block, meta = XE.build_portability_ext_entries(ROOT, iset, PAGE_SIZE, pc)
    markers = XE.build_ext_markers(meta, sorted(skel), skel_sha)
    plan = XE.portability_ext_invocation_plan()
    rc_sha = XE.portability_ext_run_config_sha256(plan)

    # every ext workload must already be admissible (no workload_set change)
    for wl in pin_block:
        if wl not in pin.get("workload_set", []):
            raise SystemExit("ext workload %s not in pin workload_set" % wl)

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
    if added != 63:
        raise SystemExit("expected to add 63 ext keyed entries, added %d" % added)

    # ---- merge strategy_plans markers (additive) ----------------------------
    sp = pin["strategy_plans"]
    for strat, marker in markers.items():
        if strat in sp:
            raise SystemExit("marker %s already present in pin" % strat)
        sp[strat] = marker

    # ---- top-level portability-ext identity ---------------------------------
    pin["portability_ext_invocation_plan"] = plan
    pin["portability_ext_run_config_sha256"] = rc_sha
    pin["portability_ext_run_config_sha256_note"] = (
        "Deterministic sha256 over the canonical portability_ext_invocation_plan "
        "(sorted-key compact JSON). Independent identity for the portability-EXTENSION "
        "matrix (426 pairs / 852 invocations across seven rectangular sub-matrices "
        "B5-B11, schedule_seed=%d) covering the 29 (workload,strategy) cells the "
        "workstation ran but the primary/secondary/portability OpenWhisk campaigns did "
        "not. Distinct from primary (022fbeb0..), secondary (441609e6..) and "
        "portability (64f44c3e..) run configs, which are byte-frozen and untouched. "
        "Deployment/feasibility + relative-effectiveness evidence only; warm paired "
        "first-query latency is NOT a strategy-performance estimate "
        "(analysis/thesis/threats_to_validity.md)." % XE.SCHEDULE_SEED_EXT)

    # ---- fail closed: immutable identities unchanged ------------------------
    for k in ("run_config_sha256", "secondary_run_config_sha256",
              "portability_run_config_sha256"):
        if pin[k] != frozen[k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % k)
    for k in ("invocation_plan", "secondary_invocation_plan", "portability_invocation_plan"):
        if json.dumps(pin[k], sort_keys=True) != frozen[k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % k)

    # ---- self-crosscheck before writing -------------------------------------
    problems = XE.crosscheck_ext(pin, meta, ROOT)
    if problems:
        raise SystemExit("ext crosscheck failed:\n  " + "\n  ".join(problems))

    with open(pin_path, "w") as f:
        json.dump(pin, f, indent=2)
        f.write("\n")
    print("pin updated: +%d ext keyed entries, +%d markers, "
          "portability_ext_run_config_sha256=%s" % (added, len(markers), rc_sha))
    print("frozen identities intact: primary=%s secondary=%s portability=%s"
          % (pin["run_config_sha256"][:12], pin["secondary_run_config_sha256"][:12],
             pin["portability_run_config_sha256"][:12]))


if __name__ == "__main__":
    main()
