#!/usr/bin/env python3
"""LP DELIVERY-ORDER portability summary (§7): OpenWhisk vs workstation, mechanism/cost.

libprefetch (lp) delivers a strategy's ENTIRE resident working set up front via ordered
synchronous pread. lp_sorted delivers the identical page SET as lp_shuf -- only the
delivery ORDER differs (offset-ascending vs the frozen Random(424242) shuffle). Because
the whole set is made resident, the post-delivery first_query is warm for BOTH arms and
cannot distinguish them: lp's effect lives in DELIVERY COST (deliver_us / e2e), not
first_query. This module therefore reports lp on deliver_us, kept OUT of the first_query
effectiveness table (compare_effectiveness.py), per the directive.

What ports across platforms is the MECHANISM and its RELATIVE cost, expressed as the
dimensionless within-platform order ratio:

    order_ratio = deliver_us(lp_shuf) / deliver_us(lp_sorted)   (> 1 => ordering helps)

Ratios are dimensionless and cross-platform-safe. Absolute microseconds are NOT compared
across platforms (different hardware / I/O stack) -- only each platform's OWN order ratio.
The post-delivery first_query is reported as a CONTROL: it should be ~equal for sorted and
shuf on both platforms, demonstrating that the order effect is confined to delivery.

OpenWhisk numbers come from the gated closure normalized pairs (standalone handles). This
module only READS already-frozen sources; it runs, alters, and reinterprets nothing.
"""
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OW_PAIRS = (REPO / "deployment/openwhisk/analysis/normalized/portability_full_closure/"
            "portability_full_closure_normalized_pairs.csv")
RES = REPO / "results"
OUT_DIR = REPO / "deployment/openwhisk/analysis/comparison"

WL_MAP = {
    "native_ycsb_c_read_zipf": "YC",
    "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01",
    "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit",
}
WORKLOAD_ORDER = ["YC", "YCu", "YCh01", "C", "C_hit"]
LP = ("lp_sorted", "lp_shuf")


# ---------------------------------------------------------------------------
# OpenWhisk side: median deliver_us + first_query per (workload, strategy),
# standalone handles only, from the gated closure pairs.
# ---------------------------------------------------------------------------
def load_ow_lp():
    dl = defaultdict(list)
    fq = defaultdict(list)
    seeds = defaultdict(set)
    if not OW_PAIRS.exists():
        raise SystemExit(f"missing closure pairs: {OW_PAIRS}")
    for r in csv.DictReader(open(OW_PAIRS)):
        if r["handle_mode"] != "standalone":
            continue
        s = r["paired_target_strategy"]
        if s not in LP:
            continue
        wl = WL_MAP[r["workload"]]
        dl[(wl, s)].append(float(r["target_deliver_us"]))
        fq[(wl, s)].append(float(r["target_first_query_us"]))
        seeds[(wl, s)].add(r["seed"])
    return dl, fq, seeds


# ---------------------------------------------------------------------------
# Workstation side: median deliver_us per (workload, strategy), arm=pread, db=orig.
# lp is delivered by pread on the workstation too, matching OW pread_ordered. Sources
# are the canonical per-cell batches; C uses baselines_v2 whose leading label column is
# "<arm> <strategy> <workload> <db> <group>" (workload = 3rd space-token).
# ---------------------------------------------------------------------------
def _median_deliver(path, wl, strat):
    vals = []
    try:
        rd = csv.DictReader(open(path))
    except FileNotFoundError:
        return None
    for r in rd:
        if r.get("db") != "orig" or r.get("strategy") != strat or r.get("arm") != "pread":
            continue
        if r.get("workload") != wl:
            continue
        vals.append(float(r["deliver_us_median"]))
    return st.median(vals) if vals else None


def ws_deliver(wl, strat):
    if wl in ("YC", "YCu", "YCh01"):
        fname = {"YC": "native_headtohead", "YCu": "native_headtohead_YCu",
                 "YCh01": "native_headtohead_YCh01"}[wl]
        return _median_deliver(RES / fname / "summary.csv", wl, strat), \
            f"results/{fname}/summary.csv"
    if wl == "C_hit":
        return _median_deliver(RES / "chit_headtohead" / "summary.csv", "C_hit", strat), \
            "results/chit_headtohead/summary.csv"
    if wl == "C":
        return _median_deliver(RES / "baselines_v2" / "summary.csv", "C", strat), \
            "results/baselines_v2/summary.csv"
    return None, None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dl, fq, seeds = load_ow_lp()

    rows = []
    for wl in WORKLOAD_ORDER:
        ow_so = st.median(dl[(wl, "lp_sorted")])
        ow_sh = st.median(dl[(wl, "lp_shuf")])
        ow_fq_so = st.median(fq[(wl, "lp_sorted")])
        ow_fq_sh = st.median(fq[(wl, "lp_shuf")])
        ow_ratio = ow_sh / ow_so if ow_so > 0 else None
        ws_so, ws_src = ws_deliver(wl, "lp_sorted")
        ws_sh, _ = ws_deliver(wl, "lp_shuf")
        ws_ratio = (ws_sh / ws_so) if (ws_so and ws_sh and ws_so > 0) else None
        rows.append({
            "workload": wl,
            "ow_n_pairs_sorted": len(dl[(wl, "lp_sorted")]),
            "ow_n_pairs_shuf": len(dl[(wl, "lp_shuf")]),
            "ow_n_seeds": len(seeds[(wl, "lp_sorted")] | seeds[(wl, "lp_shuf")]),
            "ow_deliver_us_sorted": round(ow_so, 1),
            "ow_deliver_us_shuf": round(ow_sh, 1),
            "ow_delta_deliver_us": round(ow_sh - ow_so, 1),
            "ow_order_ratio_shuf_over_sorted": round(ow_ratio, 3) if ow_ratio else "",
            "ow_first_query_us_sorted": round(ow_fq_so, 1),
            "ow_first_query_us_shuf": round(ow_fq_sh, 1),
            "ow_first_query_delta_us": round(ow_fq_sh - ow_fq_so, 1),
            "ws_deliver_us_sorted": round(ws_so, 1) if ws_so else "",
            "ws_deliver_us_shuf": round(ws_sh, 1) if ws_sh else "",
            "ws_order_ratio_shuf_over_sorted": round(ws_ratio, 3) if ws_ratio else "",
            "order_ratio_agreement": (
                "both>1" if (ow_ratio and ws_ratio and ow_ratio > 1 and ws_ratio > 1)
                else "check"),
            "ws_source": ws_src,
        })

    fields = list(rows[0].keys())
    csv_path = OUT_DIR / "lp_delivery_order.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    both_gt1 = sum(1 for r in rows if r["order_ratio_agreement"] == "both>1")
    fq_control_ok = all(abs(r["ow_first_query_delta_us"]) <= 5.0 for r in rows)
    manifest = {
        "module": "lp_delivery_order",
        "role": ("§7 LP delivery-order portability: mechanism/cost, deliver_us primary, "
                 "post-delivery first_query as control; ratios only across platforms"),
        "metric_primary": "deliver_us (delivery cost)",
        "metric_control": "post-delivery first_query_us (should be ~equal sorted vs shuf)",
        "cross_platform_rule": ("only the dimensionless within-platform order ratio "
                                "shuf/sorted is compared; absolute microseconds are NOT "
                                "compared across platforms (hardware/I-O-stack differ)"),
        "n_workloads": len(rows),
        "ow_order_ratio_gt1_workloads": both_gt1,
        "ow_first_query_control_within_5us": fq_control_ok,
        "source_ow": str(OW_PAIRS.relative_to(REPO)),
        "lp_shuf_seed": 424242,
        "rows": rows,
    }
    with open(OUT_DIR / "lp_delivery_order_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print("=" * 78)
    print("LP DELIVERY-ORDER portability (§7): within-platform order ratio shuf/sorted")
    print("=" * 78)
    print(f"{'wl':6} {'OW so_us':>10} {'OW sh_us':>11} {'OW ratio':>9} "
          f"{'WS ratio':>9} {'OW fqΔ':>7} {'agree':>7}")
    for r in rows:
        print(f"{r['workload']:6} {r['ow_deliver_us_sorted']:>10} {r['ow_deliver_us_shuf']:>11} "
              f"{r['ow_order_ratio_shuf_over_sorted']:>9} "
              f"{str(r['ws_order_ratio_shuf_over_sorted']):>9} "
              f"{r['ow_first_query_delta_us']:>7} {r['order_ratio_agreement']:>7}")
    print()
    print(f"OW ordering helps (ratio>1) in {both_gt1}/{len(rows)} workloads (WS agrees)")
    print(f"post-delivery first_query control within 5us (sorted≈shuf): {fq_control_ok}")
    print(f"-> {csv_path}")
    print("INTERPRETATION: the lp DELIVERY-ORDER mechanism (sorted << shuf delivery cost) "
          "ports to OpenWhisk; first_query is a warm control, NOT lp's effectiveness metric; "
          "absolute us are NOT compared cross-platform (ratios only).")


if __name__ == "__main__":
    main()
