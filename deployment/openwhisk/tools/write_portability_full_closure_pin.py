#!/usr/bin/env python3
"""Additively write the PORTABILITY-FULL-CLOSURE layer into the frozen replay pin.

Sibling of ``write_portability_ext_pin.py``. Emits, into
``config/artifacts.native_ycsb.json``:
  * keyed_strategy_plans: the 37 closure plans (11 non-lp + 26 lp ORDERED), offset-free;
  * strategy_plans: the four NEW markers (2e_K40, 2e_K92, lp_sorted, lp_shuf);
  * portability_full_closure_invocation_plan + portability_full_closure_run_config_sha256
    (an independent campaign identity, schedule_seed 20260829) + note.

Fail-closed guarantees (freezes ALL FOUR prior campaign identities):
  * primary (022fbeb0..), secondary (441609e6..), portability (64f44c3e..) AND
    portability_ext (bf504a28..) invocation plans + run_config shas are asserted
    byte-unchanged before and after the edit;
  * no existing keyed entry is overwritten -- the 37 closure triples are disjoint from
    everything already in the pin (2e_K40/2e_K92/lp_sorted/lp_shuf are brand-new names;
    C/learned_markov_14 was never frozen -- ext's learned_markov_14 covered only
    YC/YCu/YCh01/C_hit); ``added != 37`` aborts;
  * every entry is derived from the verified closure freeze report via
    ``portability_full_closure_manifest.py`` (single source of truth). lp plan offsets
    are carried IN DELIVERY ORDER; the order-sensitive plan_sha256 is re-tied.

No new workload traces are written: all five closure workloads x seeds 1-3 already
resolve (four via ``portability_workload_traces``, YC via the primary path).
"""
import csv
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _HERE)
import portability_full_closure_manifest as FC  # noqa: E402

PIN_REL = "deployment/openwhisk/config/artifacts.native_ycsb.json"
SKELETON_REL = "deployment/openwhisk/config/plans/interior_pages.csv"
DB_REL = "pipeline/preparation/layout_rewriter/runs/test.db"
PAGE_SIZE = 4096
EXPECT_ADDED = 37


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

    # Snapshot ALL FOUR immutable identities BEFORE edit.
    for req in ("portability_run_config_sha256", "portability_ext_run_config_sha256"):
        if req not in pin:
            raise SystemExit("pin missing %s -- run the prior pin writers first" % req)
    frozen = {
        "invocation_plan": json.dumps(pin["invocation_plan"], sort_keys=True),
        "run_config_sha256": pin["run_config_sha256"],
        "secondary_invocation_plan": json.dumps(pin["secondary_invocation_plan"], sort_keys=True),
        "secondary_run_config_sha256": pin["secondary_run_config_sha256"],
        "portability_invocation_plan": json.dumps(pin["portability_invocation_plan"], sort_keys=True),
        "portability_run_config_sha256": pin["portability_run_config_sha256"],
        "portability_ext_invocation_plan": json.dumps(pin["portability_ext_invocation_plan"], sort_keys=True),
        "portability_ext_run_config_sha256": pin["portability_ext_run_config_sha256"],
    }

    iset = set(skeleton_offsets())
    pc = page_count()
    _live, pin_block, meta = FC.build_portability_full_closure_entries(ROOT, iset, PAGE_SIZE, pc)
    markers = FC.build_closure_markers(meta)
    plan = FC.portability_full_closure_invocation_plan()
    rc_sha = FC.portability_full_closure_run_config_sha256(plan)

    # every closure workload must already be admissible (no workload_set change)
    for wl in pin_block:
        if wl not in pin.get("workload_set", []):
            raise SystemExit("closure workload %s not in pin workload_set" % wl)

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
    if added != EXPECT_ADDED:
        raise SystemExit("expected to add %d closure keyed entries, added %d"
                         % (EXPECT_ADDED, added))

    # ---- merge strategy_plans markers (additive) ----------------------------
    sp = pin["strategy_plans"]
    for strat, marker in markers.items():
        if strat in sp:
            raise SystemExit("marker %s already present in pin" % strat)
        sp[strat] = marker

    # ---- top-level portability-full-closure identity ------------------------
    pin["portability_full_closure_invocation_plan"] = plan
    pin["portability_full_closure_run_config_sha256"] = rc_sha
    pin["portability_full_closure_run_config_sha256_note"] = (
        "Deterministic sha256 over the canonical portability_full_closure_invocation_plan "
        "(sorted-key compact JSON). Independent identity for the FULL-CLOSURE matrix "
        "(228 pairs / 456 invocations across six rectangular sub-matrices B12-B17, "
        "schedule_seed=%d) covering the final 16 WS_ONLY cells of the 65-cell canonical "
        "portability matrix -- the C/C_hit 2e_K40/2e_K92 budget siblings, C/"
        "learned_markov_14, C/layers_92 (static), and the libprefetch lp_sorted/lp_shuf "
        "ordered-delivery arms across YC/YCu/YCh01/C_hit/C. Distinct from primary "
        "(022fbeb0..), secondary (441609e6..), portability (64f44c3e..) and "
        "portability_ext (bf504a28..) run configs, which are byte-frozen and untouched. "
        "lp arms deliver the corresponding 2f_slru resident page set by a synchronous "
        "page-sized pread loop IN LIST ORDER (delivery_method=pread_ordered); lp's "
        "primary quantity is deliver_us / e2e, NOT first_query. This closes CELL "
        "coverage of the matrix; it is not an exact replication of every workstation "
        "seed/repetition protocol (analysis/thesis/threats_to_validity.md)." % FC.SCHEDULE_SEED_CLOSURE)

    # ---- fail closed: all four immutable identities unchanged ---------------
    for k in ("run_config_sha256", "secondary_run_config_sha256",
              "portability_run_config_sha256", "portability_ext_run_config_sha256"):
        if pin[k] != frozen[k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % k)
    for k in ("invocation_plan", "secondary_invocation_plan",
              "portability_invocation_plan", "portability_ext_invocation_plan"):
        if json.dumps(pin[k], sort_keys=True) != frozen[k]:
            raise SystemExit("FATAL: %s changed (must be byte-frozen)" % k)

    # ---- self-crosscheck before writing -------------------------------------
    problems = FC.crosscheck_closure(pin, meta, ROOT)
    if problems:
        raise SystemExit("closure crosscheck failed:\n  " + "\n  ".join(problems))

    with open(pin_path, "w") as f:
        json.dump(pin, f, indent=2)
        f.write("\n")
    print("pin updated: +%d closure keyed entries, +%d markers, "
          "portability_full_closure_run_config_sha256=%s" % (added, len(markers), rc_sha))
    print("frozen identities intact: primary=%s secondary=%s portability=%s ext=%s"
          % (pin["run_config_sha256"][:12], pin["secondary_run_config_sha256"][:12],
             pin["portability_run_config_sha256"][:12],
             pin["portability_ext_run_config_sha256"][:12]))


if __name__ == "__main__":
    main()
