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

This is a DESCRIPTIVE cross-platform consistency check, NOT a causal-equivalence or
absolute-latency claim. OpenWhisk uses STANDALONE handles only -- warm handles carry
a strong positional/order effect that makes warm first_query unusable for strategy
comparison. Standalone still has a mild order effect, so per-cell OW position balance
(target-first vs baseline-first count) is reported; imbalanced, small-n cells are
flagged low-confidence.

Cell set: mechanically = {OW standalone (workload,strategy)} INTERSECT {the same cell
measured on the workstation from its per-cell CANONICAL source}. Nothing is hard-coded
to a target count; the resolved intersection is whatever the data supports.

WORKSTATION PER-CELL PROVENANCE (deterministic, per user directive 2026-08-28):
  YC / YCu / YCh01     -> results/native_headtohead{,_YCu,_YCh01}/summary.csv (per-seed)
  C_hit                -> results/chit_headtohead/summary.csv (per-seed)
  C, ablation scope    -> results/ablation_comp_v2/seed{01..10}/summary.csv (per-seed)
       {2d, leaf_rand_K10, leaf_freq_K10, 2e_K10, 2f_top14, 2f_top28, 2f_slru}
  C / 2e_K500          -> results/unified_v2/matrix/summary.csv (db=orig, single batch)
       tie-break-UNCHANGED main-matrix cell (RESULT_PROVENANCE §4.2/§4.4: corrected
       tie-break set is {2e_K10, 2e_K40, 2e_K92}); NOT ablation, NOT tiebreak_fix.
  C / layers_5         -> results/seeds/seed{01..10}/summary.csv (db=orig, per-seed)
       cross-seed robustness admitted by RESULT_PROVENANCE §4.8 (2d/layers_5/layers_92
       are tie-break-unaffected); layers_5 uses no freq-ranked leaf tie-break.
  C / learned_markov_28-> results/learned_10fold/seed{1..10}/summary.csv (per LOSO fold)
       full 10-fold LOSO closure; each test seed's model trained on the other 9; the
       no-prefetch baseline is measured in the SAME fold. Later additive canonical
       source; documented as superseding single-fold baselines_v2 for learned compare.

Every cell's R is computed strictly WITHIN A BATCH: the strategy (arm=async) and the
no-prefetch baseline are taken from the SAME file + SAME db group + SAME seed/fold.
The provenance table asserts strategy_source == baseline_source for every cell.

This script only READS canonical, already-frozen sources. It does not run, alter, or
reinterpret any OpenWhisk evidence.
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

# C strategies for which results/ablation_comp_v2 is the DECLARED canonical source
# (its C_mixed ablation/competitive scope). Any C cell outside this set is sourced
# from the canonical source for THAT cell (see module docstring) -- C is NOT globally
# sourced from ablation_comp_v2.
ABLATION_SCOPE = {"2d", "leaf_rand_K10", "leaf_freq_K10", "2e_K10",
                  "2f_top14", "2f_top28", "2f_slru"}

DB_CANON = "orig"       # OW is pinned to the orig-layout test.db; compare like-for-like
NEUTRAL_BAND = 0.10     # |R| < this => "neutral" (no meaningful effect)


def category(R):
    if R >= NEUTRAL_BAND:
        return "effective"
    if R <= -NEUTRAL_BAND:
        return "harmful"
    return "neutral"


# ---------------------------------------------------------------------------
# Workstation per-cell source resolver (deterministic).
# ---------------------------------------------------------------------------
def ws_source_spec(ws, strat):
    """Return the canonical workstation source spec for a (workload, strategy) cell,
    or None if this cell has no designated workstation source.

    A spec is a dict:
      mode         : "seed_col" | "dir_series" | "single_file"
      paths        : list[Path]                (seed_col / single_file)
      tmpl, ns     : template + iterable        (dir_series)
      wl, db       : workload code + db group to filter on
      source       : human path string (== baseline_source; same batch by construction)
      scope        : canonical-scope note
      agg          : aggregation unit label
      reason       : source-rule justification
    """
    if ws in ("YC", "YCu", "YCh01"):
        fname = {"YC": "native_headtohead",
                 "YCu": "native_headtohead_YCu",
                 "YCh01": "native_headtohead_YCh01"}[ws]
        return {
            "mode": "seed_col", "paths": [RES / fname / "summary.csv"],
            "wl": ws, "db": DB_CANON, "source": f"results/{fname}/summary.csv",
            "scope": "native head-to-head (per-seed, db=orig)", "agg": "seed",
            "reason": f"native head-to-head is the canonical per-seed batch for {ws}",
        }
    if ws == "C_hit":
        return {
            "mode": "seed_col", "paths": [RES / "chit_headtohead" / "summary.csv"],
            "wl": "C_hit", "db": DB_CANON, "source": "results/chit_headtohead/summary.csv",
            "scope": "C_hit head-to-head (per-seed, db=orig)", "agg": "seed",
            "reason": "chit_headtohead is the canonical per-seed batch for C_hit",
        }
    if ws == "C":
        if strat in ABLATION_SCOPE:
            return {
                "mode": "dir_series",
                "tmpl": "ablation_comp_v2/seed{n:02d}/summary.csv", "ns": range(1, 11),
                "wl": "C", "db": DB_CANON,
                "source": "results/ablation_comp_v2/seed{01..10}/summary.csv",
                "scope": ("C_mixed ablation/competitive (declared scope: "
                          "2d, leaf_rand_K10, leaf_freq_K10, 2e_K10, 2f_top14, "
                          "2f_top28, 2f_slru)"),
                "agg": "seed",
                "reason": ("ablation_comp_v2 is canonical ONLY for its declared C "
                           "ablation/competitive scope"),
            }
        if strat == "2e_K500":
            return {
                "mode": "single_file", "paths": [RES / "unified_v2/matrix/summary.csv"],
                "wl": "C", "db": DB_CANON,
                "source": "results/unified_v2/matrix/summary.csv",
                "scope": "main-matrix, tie-break-UNCHANGED cell (RESULT_PROVENANCE §4.2/§4.4)",
                "agg": "single_batch(db=orig)",
                "reason": ("C/2e_K500 is NOT in the corrected tie-break set "
                           "{2e_K10, 2e_K40, 2e_K92}; it remains an unchanged main-matrix "
                           "cell whose canonical source is unified_v2 -- NOT ablation, "
                           "NOT tiebreak_fix"),
            }
        if strat == "layers_5":
            return {
                "mode": "dir_series",
                "tmpl": "seeds/seed{n:02d}/summary.csv", "ns": range(1, 11),
                "wl": "C", "db": DB_CANON,
                "source": "results/seeds/seed{01..10}/summary.csv",
                "scope": ("cross-seed robustness (RESULT_PROVENANCE §4.8: 2d/layers_5/"
                          "layers_92 are tie-break-unaffected)"),
                "agg": "seed(db=orig)",
                "reason": ("layers_5 uses no frequency-ranked leaf tie-break; §4.8 "
                           "admits cross-seed robustness for it"),
            }
        if strat == "learned_markov_28":
            return {
                "mode": "dir_series",
                "tmpl": "learned_10fold/seed{n}/summary.csv", "ns": range(1, 11),
                "wl": "C", "db": DB_CANON,
                "source": "results/learned_10fold/seed{1..10}/summary.csv",
                "scope": "full 10-fold LOSO closure (later additive canonical source)",
                "agg": "LOSO_fold",
                "reason": ("learned_10fold: per test-seed model trained on the other 9, "
                           "no-prefetch baseline measured in the SAME fold; supersedes "
                           "single-fold baselines_v2 for the learned comparison"),
            }
    return None


def _batch_R(path, wl, db, strat):
    """From one summary file, filtered to (workload==wl, db==db), return R for `strat`
    computed as (baseline_async_fq - strat_async_fq)/baseline_fq using the baseline and
    strategy rows FROM THIS SAME FILE+db. Returns None if either arm is absent."""
    base = None
    a = None
    try:
        rd = csv.DictReader(open(path))
    except FileNotFoundError:
        return None
    for r in rd:
        if r.get("workload") != wl:
            continue
        if r.get("db") != db:
            continue
        if r.get("arm") == "baseline":
            base = float(r["fq_median"])
        elif r.get("arm") == "async" and r.get("strategy") == strat:
            a = float(r["fq_median"])
    if base is None or a is None or base <= 0:
        return None
    return (base - a) / base


def load_ws_cell(ws, strat):
    """Compute the workstation R for one cell from its canonical source, strictly
    within-batch. Return {R, n, agg, batches, source, scope, reason} or None."""
    spec = ws_source_spec(ws, strat)
    if spec is None:
        return None
    Rs = []
    if spec["mode"] in ("seed_col",):
        # one file; group by seed; baseline+async share the same seed row-group + db.
        path = spec["paths"][0]
        by_seed = defaultdict(lambda: {"baseline": None, "async": {}})
        try:
            rd = csv.DictReader(open(path))
        except FileNotFoundError:
            return None
        for r in rd:
            if r.get("workload") != spec["wl"] or r.get("db") != spec["db"]:
                continue
            seed = r.get("seed")
            if r.get("arm") == "baseline":
                by_seed[seed]["baseline"] = float(r["fq_median"])
            elif r.get("arm") == "async":
                by_seed[seed]["async"][r.get("strategy")] = float(r["fq_median"])
        for seed, d in by_seed.items():
            b, av = d["baseline"], d["async"].get(strat)
            if b and b > 0 and av is not None:
                Rs.append((b - av) / b)
    elif spec["mode"] == "dir_series":
        for n in spec["ns"]:
            p = RES / spec["tmpl"].format(n=n)
            r = _batch_R(p, spec["wl"], spec["db"], strat)
            if r is not None:
                Rs.append(r)
    elif spec["mode"] == "single_file":
        r = _batch_R(spec["paths"][0], spec["wl"], spec["db"], strat)
        if r is not None:
            Rs.append(r)
    if not Rs:
        return None
    return {"R": st.median(Rs), "n": len(Rs), "agg": spec["agg"],
            "source": spec["source"], "scope": spec["scope"], "reason": spec["reason"]}


# ---------------------------------------------------------------------------
# OpenWhisk side: median relative reduction from standalone pairs (all cells).
# ---------------------------------------------------------------------------
def load_ow():
    """Return {(ws_code, strategy): {R, n, tgt_first, base_first, n_seeds}} for every
    standalone OW cell across all four campaigns' normalized pairs."""
    pair_files = [
        OW / "normalized_pairs.csv",                              # primary + secondary
        OW / "portability/portability_normalized_pairs.csv",      # portability
        OW / "portability_ext/portability_ext_normalized_pairs.csv",  # portability_ext
    ]
    per_cell = defaultdict(lambda: {"R": [], "tgt_first": 0, "base_first": 0, "seeds": set()})
    for pf in pair_files:
        if not pf.exists():
            raise SystemExit(f"missing OW pair file: {pf}")
        with open(pf) as f:
            for row in csv.DictReader(f):
                if row["handle_mode"] != "standalone":
                    continue
                ws = WL_MAP.get(row["workload"])
                if ws is None:
                    continue
                strat = row["paired_target_strategy"]
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
            "R": st.median(c["R"]), "n": len(c["R"]),
            "tgt_first": c["tgt_first"], "base_first": c["base_first"],
            "n_seeds": len(c["seeds"]),
        }
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
WORKLOAD_ORDER = ["YC", "YCu", "YCh01", "C", "C_hit"]


def main():
    ow = load_ow()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Mechanically resolve the intersection: every OW standalone cell that also has a
    # canonical workstation measurement. No target count is assumed.
    resolved, ow_only = [], []
    prov_rows = []
    for (ws, strat) in sorted(ow.keys()):
        wsr = load_ws_cell(ws, strat)
        if wsr is None:
            ow_only.append((ws, strat))
            continue
        o = ow[(ws, strat)]
        # same-batch assertion: by construction baseline and strategy come from the
        # same source file(s)+db group. Assert the recorded baseline_source == source.
        baseline_source = wsr["source"]
        assert baseline_source == wsr["source"], (
            f"batch mismatch for {ws}/{strat}: strat={wsr['source']} base={baseline_source}")
        imbalance = abs(o["tgt_first"] - o["base_first"])
        confounded = (o["n"] <= 3) or (imbalance == o["n"])
        resolved.append({
            "workload": ws, "strategy": strat,
            "R_ws": wsr["R"], "n_ws": wsr["n"], "ws_agg": wsr["agg"],
            "R_ow": o["R"], "n_ow_pairs": o["n"], "n_ow_seeds": o["n_seeds"],
            "ow_pos": f"{o['tgt_first']}/{o['base_first']}",
            "cat_ws": category(wsr["R"]), "cat_ow": category(o["R"]),
            "sign_agree": category(wsr["R"]) == category(o["R"]),
            "abs_diff": abs(o["R"] - wsr["R"]),
            "low_conf": confounded,
        })
        prov_rows.append({
            "workload": ws, "strategy": strat,
            "workstation_source": wsr["source"],
            "workstation_source_scope": wsr["scope"],
            "baseline_source": baseline_source,
            "same_batch": (baseline_source == wsr["source"]),
            "aggregation_unit": wsr["agg"],
            "reason_source_rule": wsr["reason"],
        })

    # ---- provenance table (machine-readable) ----
    prov_path = OUT_DIR / "ws_provenance.csv"
    prov_fields = ["workload", "strategy", "workstation_source",
                   "workstation_source_scope", "baseline_source", "same_batch",
                   "aggregation_unit", "reason_source_rule"]
    with open(prov_path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=prov_fields, lineterminator="\n")
        wtr.writeheader()
        for r in sorted(prov_rows, key=lambda x: (WORKLOAD_ORDER.index(x["workload"]),
                                                  x["strategy"])):
            wtr.writerow(r)

    # ---- per-cell effectiveness table ----
    csv_path = OUT_DIR / "effectiveness_ow_vs_workstation.csv"
    fields = ["workload", "strategy", "R_ws", "n_ws", "ws_agg", "R_ow",
              "n_ow_pairs", "n_ow_seeds", "ow_pos", "cat_ws", "cat_ow",
              "sign_agree", "abs_diff", "low_conf"]
    with open(csv_path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore",
                             lineterminator="\n")
        wtr.writeheader()
        for c in sorted(resolved, key=lambda x: (WORKLOAD_ORDER.index(x["workload"]),
                                                 x["strategy"])):
            row = dict(c)
            for k in ("R_ws", "R_ow", "abs_diff"):
                row[k] = f"{row[k]:.4f}"
            wtr.writerow(row)

    # ---- mechanical count assertions ----
    same_batch_all = all(p["same_batch"] for p in prov_rows)
    n_resolved = len(resolved)

    hi = [c for c in resolved if not c["low_conf"]]

    print("=" * 74)
    print("Effectiveness-portability: OpenWhisk (standalone) vs workstation")
    print("=" * 74)
    print(f"OW standalone cells total           : {len(ow)}")
    print(f"  resolved (OW ∩ workstation canon) : {n_resolved}")
    print(f"  OW-only (no workstation cell)      : {len(ow_only)}  -> {ow_only}")
    print(f"same-batch (strat_source==base_source) for every resolved cell: "
          f"{'YES' if same_batch_all else 'NO'}")
    print(f"provenance table -> {prov_path}")

    # per-workload resolved counts
    print("\nResolved cells per workload:")
    for wsc in WORKLOAD_ORDER:
        cnt = sum(1 for c in resolved if c["workload"] == wsc)
        print(f"  {wsc:6}: {cnt}")

    print(f"\n{'workload':7} {'strategy':18} {'R_ws':>7} {'R_ow':>7} {'|d|':>6} "
          f"{'ws':>9} {'ow':>9} {'agree':>5} {'pos(t/b)':>8} {'ws_n':>4} conf")
    for c in sorted(resolved, key=lambda x: (WORKLOAD_ORDER.index(x["workload"]),
                                             x["strategy"])):
        print(f"{c['workload']:7} {c['strategy']:18} {c['R_ws']:>7.3f} {c['R_ow']:>7.3f} "
              f"{c['abs_diff']:>6.3f} {c['cat_ws']:>9} {c['cat_ow']:>9} "
              f"{'Y' if c['sign_agree'] else 'n':>5} {c['ow_pos']:>8} "
              f"{c['n_ws']:>4} {'LOW' if c['low_conf'] else ''}")

    agree = sum(1 for c in resolved if c["sign_agree"])
    agree_hi = sum(1 for c in hi if c["sign_agree"])
    print(f"\nDirection (category) agreement: {agree}/{n_resolved} all cells; "
          f"{agree_hi}/{len(hi)} high-confidence cells")

    print("\nRank correlation (Spearman R_ws vs R_ow):")
    for wsc in WORKLOAD_ORDER:
        sub = [c for c in resolved if c["workload"] == wsc]
        if len(sub) < 2:
            continue
        rho = spearman([c["R_ws"] for c in sub], [c["R_ow"] for c in sub])
        if rho is not None:
            print(f"  {wsc:6} (n={len(sub)}): rho={rho:.3f}")
    rho_all = spearman([c["R_ws"] for c in resolved], [c["R_ow"] for c in resolved])
    rho_hi = spearman([c["R_ws"] for c in hi], [c["R_ow"] for c in hi])
    print(f"  ALL    (n={n_resolved}): rho={rho_all:.3f}")
    print(f"  HIGH-CONF (n={len(hi)}): rho={rho_hi:.3f}")
    med_abs = st.median([c["abs_diff"] for c in resolved])
    print(f"\nMedian |R_OW - R_WS| across resolved cells: {med_abs:.3f}")
    print(f"Per-cell table -> {csv_path}")


if __name__ == "__main__":
    main()
