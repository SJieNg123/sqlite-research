#!/usr/bin/env python3
"""Effectiveness-portability comparison: OpenWhisk (standalone) vs workstation.

Purpose (per the research goal): show that prefetch strategies which are effective
on the workstation are ALSO effective on the simulated serverless platform
(OpenWhisk). The comparison quantity is the RELATIVE first_query reduction versus
each platform's OWN same-condition baseline -- relative reductions are the only
cross-machine-comparable quantity (absolute microseconds are not).

    R = (baseline_first_query_us - strategy_first_query_us) / baseline_first_query_us
        R > 0  => strategy is faster than baseline (effective)
        R ~ 0  => no effect
        R < 0  => strategy is slower (harmful)

Scope: exactly the 20 (workload, strategy) cells that BOTH platforms ran (the
"already comparable" set). OpenWhisk uses STANDALONE handles only -- warm handles
carry a strong positional/order effect that makes warm first_query unusable for
strategy comparison. Standalone still has a mild order effect, so per-cell OW
position balance (target-first vs baseline-first count) is reported; imbalanced,
small-n cells are flagged low-confidence.

This script only READS canonical, already-frozen sources. It does not run, alter,
or reinterpret any OpenWhisk evidence. Nothing here is a headline warm-latency
claim.
"""
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OW = REPO / "deployment/openwhisk/analysis/normalized"
RES = REPO / "results"
OUT_DIR = REPO / "deployment/openwhisk/analysis/comparison"

# OpenWhisk workload_id  <->  workstation workload code
WL_MAP = {
    "native_ycsb_c_read_zipf": "YC",
    "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01",
    "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit",
}

# The 20 comparable cells, keyed by workstation workload code.
COMPARABLE = {
    "YC": ["2d", "2e_K10", "2e_K500", "2f_slru", "2f_top28", "layers_5", "learned_markov_28"],
    "YCu": ["2d", "2e_K10", "2f_slru"],
    "YCh01": ["2d", "2e_K10", "2f_slru"],
    "C": ["2d", "2e_K10", "2f_slru", "leaf_freq_K10", "leaf_rand_K10"],
    "C_hit": ["2e_K10", "2f_slru"],
}

# Workstation canonical source per workload (fq_median col + whether seed is a column).
WS_SOURCES = {
    "YC": ("native_headtohead/summary.csv", True),
    "YCu": ("native_headtohead_YCu/summary.csv", True),
    "YCh01": ("native_headtohead_YCh01/summary.csv", True),
    "C_hit": ("chit_headtohead/summary.csv", True),
    # C: one file per seed, workload col has no seed
    "C": ("ablation_comp_v2/seed{seed:02d}/summary.csv", False),
}

NEUTRAL_BAND = 0.10  # |R| < this => "neutral" (no meaningful effect)


def category(R):
    if R >= NEUTRAL_BAND:
        return "effective"
    if R <= -NEUTRAL_BAND:
        return "harmful"
    return "neutral"


# ---------------------------------------------------------------------------
# OpenWhisk side: median relative reduction from standalone pairs.
# ---------------------------------------------------------------------------
def load_ow():
    """Return {(ws_code, strategy): {R, n, tgt_first, base_first, seeds}}."""
    pair_files = [
        OW / "portability/portability_normalized_pairs.csv",
        OW / "normalized_pairs.csv",
    ]
    per_cell = defaultdict(lambda: {"R": [], "tgt_first": 0, "base_first": 0, "seeds": set()})
    for pf in pair_files:
        with open(pf) as f:
            for row in csv.DictReader(f):
                if row["handle_mode"] != "standalone":
                    continue
                ws = WL_MAP.get(row["workload"])
                strat = row["paired_target_strategy"]
                if ws is None or strat not in COMPARABLE.get(ws, []):
                    continue
                b = float(row["baseline_first_query_us"])
                t = float(row["target_first_query_us"])
                if b <= 0:
                    continue
                cell = per_cell[(ws, strat)]
                cell["R"].append((b - t) / b)
                cell["seeds"].add(row["seed"])
                if int(row["target_schedule_position"]) < int(row["baseline_schedule_position"]):
                    cell["tgt_first"] += 1
                else:
                    cell["base_first"] += 1
    out = {}
    for key, c in per_cell.items():
        out[key] = {
            "R": st.median(c["R"]),
            "n": len(c["R"]),
            "tgt_first": c["tgt_first"],
            "base_first": c["base_first"],
            "n_seeds": len(c["seeds"]),
        }
    return out


# ---------------------------------------------------------------------------
# Workstation side: median-over-seeds relative reduction (arm=async vs same-seed
# baseline).
# ---------------------------------------------------------------------------
def _read_ws_rows(path, seed_in_col, seed_val):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            seed = row["seed"] if seed_in_col else seed_val
            rows.append((seed, row["strategy"], row["arm"], float(row["fq_median"])))
    return rows


def load_ws():
    """Return {(ws_code, strategy): {R, n_seeds}} using per-seed async-vs-baseline."""
    out = {}
    for ws, (tmpl, seed_in_col) in WS_SOURCES.items():
        # collect (seed -> {baseline_fq, strategy->async_fq})
        by_seed = defaultdict(lambda: {"baseline": None, "async": {}})
        if seed_in_col:
            rows = _read_ws_rows(RES / tmpl, True, None)
            for seed, strat, arm, fq in rows:
                if arm == "baseline":
                    by_seed[seed]["baseline"] = fq
                elif arm == "async":
                    by_seed[seed]["async"][strat] = fq
        else:
            for s in range(1, 11):
                p = RES / tmpl.format(seed=s)
                if not p.exists():
                    continue
                for seed, strat, arm, fq in _read_ws_rows(p, False, str(s)):
                    if arm == "baseline":
                        by_seed[str(s)]["baseline"] = fq
                    elif arm == "async":
                        by_seed[str(s)]["async"][strat] = fq
        for strat in COMPARABLE[ws]:
            Rs = []
            for seed, d in by_seed.items():
                base = d["baseline"]
                a = d["async"].get(strat)
                if base and base > 0 and a is not None:
                    Rs.append((base - a) / base)
            if Rs:
                out[(ws, strat)] = {"R": st.median(Rs), "n_seeds": len(Rs)}
    return out


# ---------------------------------------------------------------------------
# Spearman rank correlation (no scipy; tie-aware via average ranks).
# ---------------------------------------------------------------------------
def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 2:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ---------------------------------------------------------------------------
def main():
    ow = load_ow()
    ws = load_ws()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cells = []
    for wsc in ["YC", "YCu", "YCh01", "C", "C_hit"]:
        for strat in COMPARABLE[wsc]:
            key = (wsc, strat)
            if key not in ow or key not in ws:
                cells.append({"workload": wsc, "strategy": strat, "status": "MISSING",
                              "ow": ow.get(key), "ws": ws.get(key)})
                continue
            o, w = ow[key], ws[key]
            imbalance = abs(o["tgt_first"] - o["base_first"])
            confounded = (o["n"] <= 3) or (imbalance == o["n"])  # all one side
            cells.append({
                "workload": wsc, "strategy": strat, "status": "OK",
                "R_ws": w["R"], "n_ws_seeds": w["n_seeds"],
                "R_ow": o["R"], "n_ow_pairs": o["n"], "n_ow_seeds": o["n_seeds"],
                "ow_pos": f"{o['tgt_first']}/{o['base_first']}",
                "cat_ws": category(w["R"]), "cat_ow": category(o["R"]),
                "sign_agree": category(w["R"]) == category(o["R"]),
                "abs_diff": abs(o["R"] - w["R"]),
                "low_conf": confounded,
            })

    # write per-cell CSV
    csv_path = OUT_DIR / "effectiveness_ow_vs_workstation.csv"
    fields = ["workload", "strategy", "status", "R_ws", "n_ws_seeds", "R_ow",
              "n_ow_pairs", "n_ow_seeds", "ow_pos", "cat_ws", "cat_ow",
              "sign_agree", "abs_diff", "low_conf"]
    with open(csv_path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        wtr.writeheader()
        for c in cells:
            if c["status"] == "OK":
                row = dict(c)
                for k in ("R_ws", "R_ow", "abs_diff"):
                    row[k] = f"{row[k]:.4f}"
                wtr.writerow(row)
            else:
                wtr.writerow({"workload": c["workload"], "strategy": c["strategy"],
                              "status": "MISSING"})

    ok = [c for c in cells if c["status"] == "OK"]
    hi = [c for c in ok if not c["low_conf"]]

    # console report
    print(f"Comparable cells resolved: {len(ok)}/20  (missing: {20 - len(ok)})")
    print(f"\n{'workload':7} {'strategy':18} {'R_ws':>7} {'R_ow':>7} {'|d|':>6} "
          f"{'ws':>9} {'ow':>9} {'agree':>5} {'pos(t/b)':>8} conf")
    for c in ok:
        print(f"{c['workload']:7} {c['strategy']:18} {c['R_ws']:>7.3f} {c['R_ow']:>7.3f} "
              f"{c['abs_diff']:>6.3f} {c['cat_ws']:>9} {c['cat_ow']:>9} "
              f"{'Y' if c['sign_agree'] else 'n':>5} {c['ow_pos']:>8} "
              f"{'LOW' if c['low_conf'] else ''}")

    agree = sum(1 for c in ok if c["sign_agree"])
    agree_hi = sum(1 for c in hi if c["sign_agree"])
    print(f"\nDirection (category) agreement: {agree}/{len(ok)} all cells; "
          f"{agree_hi}/{len(hi)} high-confidence cells")

    # per-workload + overall Spearman
    print("\nRank correlation (Spearman R_ws vs R_ow):")
    for wsc in ["YC", "C"]:  # only workloads with >=4 comparable cells rank meaningfully
        sub = [c for c in ok if c["workload"] == wsc]
        rho = spearman([c["R_ws"] for c in sub], [c["R_ow"] for c in sub])
        print(f"  {wsc:5} (n={len(sub)}): rho={rho:.3f}" if rho is not None else f"  {wsc}: n/a")
    rho_all = spearman([c["R_ws"] for c in ok], [c["R_ow"] for c in ok])
    rho_hi = spearman([c["R_ws"] for c in hi], [c["R_ow"] for c in hi])
    print(f"  ALL   (n={len(ok)}): rho={rho_all:.3f}")
    print(f"  HIGH-CONF (n={len(hi)}): rho={rho_hi:.3f}")
    print(f"\nPer-cell table -> {csv_path}")


if __name__ == "__main__":
    main()
