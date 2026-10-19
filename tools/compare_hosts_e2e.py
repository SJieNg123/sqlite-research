#!/usr/bin/env python3
"""Does the end-to-end ranking of the workstation hold on the OpenWhisk host? (TODO L453 (1))

Compares results/unified_v7 (workstation) with results/ow_native_e2e (the native run on the
second host) on the four strategies both ran: Skel, Skel+10, Dump-14, Dump, on A, B, C, under
per-page and window-chunked delivery.

For every pair of strategies in a (workload, delivery) cell, the per-instance difference of
their paired effects (points of the same-instance baseline) gets the paper's bootstrap CI
(tools/stats_uncertainty.bootstrap_ci), separately on each host. A pair is ordered on a host
when that CI excludes 0, and tied otherwise. Across the hosts a pair then keeps its order,
is tied on one or both hosts, or reverses. Per-instance effects come from raw.csv through
stats_uncertainty's own functions, so they are the values behind uncertainty.csv, unrounded.
Absolute latency never crosses hosts: the host ratios below are ratios of medians on the
same host's own cells.

  tools/compare_hosts_e2e.py      writes results/ow_native_e2e/host_comparison.{csv,json,md}
"""
import csv
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import stats_uncertainty as su  # noqa: E402

HOSTS = {"workstation": ROOT / "results/unified_v7", "second_host": ROOT / "results/ow_native_e2e"}
OUT = ROOT / "results/ow_native_e2e"
WORKLOADS = ("A", "B", "C")
ARMS = ("async", "async_win")
SETS = {"2d": "Skel", "2e_K10": "Skel+10", "2f_top14": "Dump-14", "2f_slru": "Dump"}
METRICS = ("e2e_warm_us", "first_query_us")


def effects(root):
    """(w, strategy, arm, metric) -> {seed: effect %} for the four sets on orig."""
    eff = {}
    for p in sorted(root.glob("seed[0-9][0-9]/raw.csv")):
        med = su.seed_medians(su.load_seed(p))
        for (w, ly, s, arm), mm in med.items():
            if ly != "orig" or w not in WORKLOADS or s not in SETS or arm not in ARMS:
                continue
            for m in METRICS:
                sv, bv = mm.get(m), su.baseline_value(med, w, ly, m)
                if sv is not None and bv:
                    eff.setdefault((w, s, arm, m), {})[p.parent.name] = (sv - bv) / bv * 100.0
    return eff


def pair(eff, w, arm, m, s1, s2):
    a, b = eff[(w, s1, arm, m)], eff[(w, s2, arm, m)]
    assert a.keys() == b.keys() and len(a) == 10, f"{w} {arm} {m} {s1}/{s2}: not ten paired instances"
    d = [a[k] - b[k] for k in sorted(a)]
    lo, hi = su.bootstrap_ci(d)
    return statistics.mean(d), lo, hi, ("<" if hi < 0 else ">" if lo > 0 else "=")


def summary_medians(root):
    cells = {}
    for p in sorted(root.glob("seed[0-9][0-9]/summary.csv")):
        for r in csv.DictReader(open(p)):
            if r["db"] == "orig":
                cells.setdefault((r["workload"], r["strategy"], r["arm"]), []).append(r)
    return cells


def med(cells, key, col, add=()):
    return statistics.median(float(r[col]) + sum(float(r[c] or 0) for c in add) for r in cells[key])


def main():
    eff = {h: effects(root) for h, root in HOSTS.items()}
    rows, counts = [], {}
    for m in METRICS:
        c = counts.setdefault(m, {"pairs": 0, "same_order": 0, "tie_both": 0, "tie_one": 0, "reversed": 0})
        for w in WORKLOADS:
            for arm in ARMS:
                for s1, s2 in itertools.combinations(SETS, 2):
                    ws, ow = pair(eff["workstation"], w, arm, m, s1, s2), pair(eff["second_host"], w, arm, m, s1, s2)
                    if ws[3] != "=" and ow[3] != "=":
                        outcome = "same_order" if ws[3] == ow[3] else "reversed"
                    else:
                        outcome = "tie_both" if ws[3] == ow[3] == "=" else "tie_one"
                    c["pairs"] += 1
                    c[outcome] += 1
                    rows.append({"metric": m, "workload": w, "arm": arm, "first": SETS[s1], "second": SETS[s2],
                                 "ws_mean_d": round(ws[0], 2), "ws_ci_lo": round(ws[1], 2), "ws_ci_hi": round(ws[2], 2),
                                 "ws_order": ws[3], "ow_mean_d": round(ow[0], 2), "ow_ci_lo": round(ow[1], 2),
                                 "ow_ci_hi": round(ow[2], 2), "ow_order": ow[3], "outcome": outcome})
    with open(OUT / "host_comparison.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    W, O = summary_medians(HOSTS["workstation"]), summary_medians(HOSTS["second_host"])
    base = {w: med(O, (w, "baseline", "baseline"), "fq_median") / med(W, (w, "baseline", "baseline"), "fq_median")
            for w in WORKLOADS}
    disp = {f"{w}/{s}/{a}": med(O, (w, s, a), "deliver_us_median", ("parse_us_median",)) /
            med(W, (w, s, a), "deliver_us_median", ("parse_us_median",))
            for w in WORKLOADS for s in SETS for a in ARMS}
    reversed_pairs = [r for r in rows if r["outcome"] == "reversed"]
    out = {"counts": counts, "reversed": reversed_pairs,
           "baseline_first_query_ratio": {k: round(v, 4) for k, v in base.items()},
           "dispatch_ratio": {k: round(v, 4) for k, v in disp.items()}}
    (OUT / "host_comparison.json").write_text(json.dumps(out, indent=1) + "\n")

    md = ["# Workstation (unified_v7) against the second host (ow_native_e2e)", "",
          "Pairs of Skel, Skel+10, Dump-14, Dump per workload (A, B, C) and delivery (per-page, "
          "window-chunked). A pair is ordered on a host when the bootstrap CI of its paired "
          "difference excludes 0. Written by tools/compare_hosts_e2e.py.", "",
          "| metric | pairs | same order | tie on both | tie on one | reversed |", "|---|---:|---:|---:|---:|---:|"]
    md += [f"| {m} | {c['pairs']} | {c['same_order']} | {c['tie_both']} | {c['tie_one']} | {c['reversed']} |"
           for m, c in counts.items()]
    md += ["", "Reversed pairs (d = first minus second, points of the baseline):", ""]
    md += [f"- {r['metric']} {r['workload']} {r['arm']} {r['first']} vs {r['second']}: workstation "
           f"{r['ws_mean_d']:+.1f} [{r['ws_ci_lo']:+.1f}, {r['ws_ci_hi']:+.1f}], second host "
           f"{r['ow_mean_d']:+.1f} [{r['ow_ci_lo']:+.1f}, {r['ow_ci_hi']:+.1f}]" for r in reversed_pairs] or ["- none"]
    md += ["", f"Second host over workstation, medians over instances on each host: baseline first query "
           f"{min(base.values()):.2f} to {max(base.values()):.2f}, dispatch {min(disp.values()):.2f} to "
           f"{max(disp.values()):.2f}.", ""]
    (OUT / "host_comparison.md").write_text("\n".join(md))
    for m, c in counts.items():
        print(f"{m}: {c}")
    print(f"reversed: {[(r['metric'], r['workload'], r['arm'], r['first'], r['second']) for r in reversed_pairs]}")


if __name__ == "__main__":
    main()
