#!/usr/bin/env python3
"""Outlier-replication analysis contract (SIXTH campaign) -- reports BOTH batches.

This consumes the archived OUTLIER-REPLICATION evidence (the standalone, exactly
position-balanced re-run of the six largest workstation<->OpenWhisk first-query
discrepancies) and reports, PER CELL, the ORIGINAL batch R_ow side by side with the
REPLICATION batch R_ow -- it does NOT replace the original values. Each cell is then
classified against PRE-REGISTERED interpretation rules (documented below and in
deployment/openwhisk/PORTABILITY_OUTLIER_REPLICATION.md), fixed BEFORE any replication
evidence existed. There is NO post-hoc selection of whichever batch looks better.

The six cells (all already in the frozen 65-cell canonical portability matrix; this
campaign adds NO coverage):
    C/layers_92, C/2d, C_hit/2e_K40   -- category (1): original true sign-flips (+WS -> -OW)
    C/layers_5                        -- category (1): WS-neutral but OW strongly negative
    YCh01/layers_5, YCu/layers_5      -- category (2): WS-neutral but OW positive

Original batch (authoritative historical evidence) is read from the existing comparison
table  analysis/comparison/effectiveness_ow_vs_workstation.csv  (R_ws, original R_ow,
original pair count, original AB/BA position split). Replication batch is read from the
archived replication pairs  analysis/normalized/portability_outlier_replication/
portability_outlier_replication_normalized_pairs.csv  (standalone pairs only), using the
SAME per-pair relative reduction R = (baseline_fq - target_fq)/baseline_fq and the SAME
median aggregation as compare_effectiveness.load_ow(). If that evidence file is absent
this script FAILS CLOSED and writes NO rows -- it never fabricates a replication result.

PRE-REGISTERED interpretation bands (from the existing framework; NO new significance
test, NO p-values):
  * NEUTRAL_BAND = 0.10 : |R| < 0.10 is "near zero / neutral" (compare_effectiveness).
  * SIGN_AGREE_BAND = 0.60 : if fewer than 60% of a cell's replication pairs share the
    sign of the cell median, the cell is flagged "execution-sensitive / unstable"
    (a variability descriptor over the balanced pairs, not a significance claim).
PRE-REGISTERED classification (fixed before evidence):
  category (1) sign-flip cells {C/layers_92, C/2d, C_hit/2e_K40}:
    - balanced replication still clearly R_ow <= -0.10 and stable
        -> A. replicated deployment divergence
    - clearly positive (R_ow >= +0.10, i.e. closer to the +WS direction)
        -> B. original batch likely position/state-confounded
    - highly variable (sign-agreement < 0.60) or otherwise near-zero
        -> C. execution-sensitive / unstable
  C/layers_5 (WS-neutral, original OW strongly negative):
    - strongly negative (R_ow <= -0.10) and stable
        -> A. replicated OW-side anomaly despite WS-neutral behavior
    - near zero (|R_ow| < 0.10) or highly variable
        -> B. original negative effect likely batch/state-sensitive
  YCh01/layers_5 & YCu/layers_5 (WS-neutral, original OW positive):
    - clearly positive (R_ow >= +0.10) and stable
        -> A. deployment-specific amplification of a WS-neutral strategy
    - near zero or highly variable
        -> B. prior discrepancy likely batch/state-sensitive

Run:  /home/u03/.cache/coldstart-venv/bin/python analysis/analyze_outlier_replication.py
Output: analysis/comparison/outlier_replication_report.csv (+ a printed table).
This script does NOT run OpenWhisk and does NOT modify any archived evidence.
"""
import csv
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COMPARISON_CSV = (REPO / "deployment/openwhisk/analysis/comparison/"
                  "effectiveness_ow_vs_workstation.csv")
REPL_PAIRS_CSV = (REPO / "deployment/openwhisk/analysis/normalized/"
                  "portability_outlier_replication/"
                  "portability_outlier_replication_normalized_pairs.csv")
OUT_CSV = (REPO / "deployment/openwhisk/analysis/comparison/"
           "outlier_replication_report.csv")

NEUTRAL_BAND = 0.10       # |R| < this => neutral (compare_effectiveness framework)
SIGN_AGREE_BAND = 0.60    # < this fraction sharing the median sign => unstable

WL_MAP = {  # normalized-pairs workload id -> workstation/comparison code
    "native_ycsb_c_read_zipf": "YC",
    "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01",
    "read_tail_mixed_20k": "C",
    "read_tail_hit_20k": "C_hit",
}

# The six replicated cells and their pre-registered family (fixed literal).
#   ws_code, strategy, family
CELLS = [
    ("C", "layers_92", "sign_flip"),
    ("C", "2d", "sign_flip"),
    ("C_hit", "2e_K40", "sign_flip"),
    ("C", "layers_5", "ws_neutral_ow_negative"),
    ("YCh01", "layers_5", "ws_neutral_ow_positive"),
    ("YCu", "layers_5", "ws_neutral_ow_positive"),
]


def sign(x):
    return "+" if x > 0 else ("-" if x < 0 else "0")


def classify(family, repl_R, sign_agree_frac):
    """Pre-registered classification -> (code, label). code in {A, B, C}."""
    unstable = sign_agree_frac < SIGN_AGREE_BAND
    if family == "sign_flip":
        if repl_R <= -NEUTRAL_BAND and not unstable:
            return "A", "replicated_deployment_divergence"
        if repl_R >= NEUTRAL_BAND and not unstable:
            return "B", "original_batch_likely_position_or_state_confounded"
        return "C", "execution_sensitive_unstable"
    if family == "ws_neutral_ow_negative":
        if repl_R <= -NEUTRAL_BAND and not unstable:
            return "A", "replicated_ow_side_anomaly_despite_ws_neutral"
        return "B", "original_negative_effect_likely_batch_or_state_sensitive"
    if family == "ws_neutral_ow_positive":
        if repl_R >= NEUTRAL_BAND and not unstable:
            return "A", "deployment_specific_amplification_of_ws_neutral_strategy"
        return "B", "prior_discrepancy_likely_batch_or_state_sensitive"
    raise ValueError("unknown family %r" % family)


def load_original():
    """{(ws, strat): row} from the authoritative comparison table (unchanged)."""
    if not COMPARISON_CSV.exists():
        sys.exit("missing comparison table: %s (run compare_effectiveness.py)" % COMPARISON_CSV)
    out = {}
    with open(COMPARISON_CSV) as f:
        for r in csv.DictReader(f):
            out[(r["workload"], r["strategy"])] = r
    return out


def load_replication():
    """{(ws, strat): {R, n, base_first, tgt_first, seeds, per_pair}} from the archived
    replication pairs (standalone only). Median aggregation, identical to load_ow().
    FAILS CLOSED (returns None) if the evidence file does not exist yet."""
    if not REPL_PAIRS_CSV.exists():
        return None
    per_cell = {}
    with open(REPL_PAIRS_CSV) as f:
        for row in csv.DictReader(f):
            if row.get("handle_mode") != "standalone":
                continue
            ws = WL_MAP.get(row["workload"])
            if ws is None:
                continue
            strat = row["paired_target_strategy"]
            b = float(row["baseline_first_query_us"])
            t = float(row["target_first_query_us"])
            if b <= 0:
                continue
            c = per_cell.setdefault((ws, strat),
                                    {"R": [], "base_first": 0, "tgt_first": 0, "seeds": set()})
            c["R"].append((b - t) / b)
            c["seeds"].add(row["seed"])
            if int(row["target_schedule_position"]) < int(row["baseline_schedule_position"]):
                c["tgt_first"] += 1
            else:
                c["base_first"] += 1
    out = {}
    for key, c in per_cell.items():
        med = st.median(c["R"])
        pos = sum(1 for r in c["R"] if r > 0)
        neg = sum(1 for r in c["R"] if r < 0)
        agree = (max(pos, neg) / len(c["R"])) if c["R"] else 0.0
        out[key] = {"R": med, "n": len(c["R"]), "base_first": c["base_first"],
                    "tgt_first": c["tgt_first"], "n_seeds": len(c["seeds"]),
                    "sign_agree_frac": agree}
    return out


def main():
    orig = load_original()
    repl = load_replication()
    if repl is None:
        sys.exit("NO replication evidence yet: %s does not exist.\n"
                 "Run the WK2 outlier-replication matrix + normalize pipeline first; "
                 "this contract writes NO rows before evidence exists." % REPL_PAIRS_CSV)

    fields = ["workload", "strategy", "family", "R_ws",
              "original_R_ow", "replication_R_ow",
              "original_abs_gap", "replication_abs_gap",
              "original_pair_count", "replication_pair_count",
              "original_baseline_first", "original_target_first",
              "replication_baseline_first", "replication_target_first",
              "original_sign", "replication_sign",
              "replication_sign_agree_frac", "classification", "classification_label"]
    rows = []
    for ws, strat, family in CELLS:
        o = orig.get((ws, strat))
        if o is None:
            sys.exit("original comparison row missing for %s/%s" % (ws, strat))
        r = repl.get((ws, strat))
        if r is None:
            sys.exit("replication evidence present but cell %s/%s absent -- incomplete "
                     "replication batch; refusing to classify." % (ws, strat))
        R_ws = float(o["R_ws"])
        oR = float(o["R_ow"])
        # original AB/BA split: comparison ow_pos is "tgt_first/base_first"
        o_tgt, o_base = (int(x) for x in o["ow_pos"].split("/"))
        code, label = classify(family, r["R"], r["sign_agree_frac"])
        rows.append({
            "workload": ws, "strategy": strat, "family": family,
            "R_ws": "%.4f" % R_ws,
            "original_R_ow": "%.4f" % oR, "replication_R_ow": "%.4f" % r["R"],
            "original_abs_gap": "%.4f" % abs(oR - R_ws),
            "replication_abs_gap": "%.4f" % abs(r["R"] - R_ws),
            "original_pair_count": o["n_ow_pairs"], "replication_pair_count": r["n"],
            "original_baseline_first": o_base, "original_target_first": o_tgt,
            "replication_baseline_first": r["base_first"],
            "replication_target_first": r["tgt_first"],
            "original_sign": sign(oR), "replication_sign": sign(r["R"]),
            "replication_sign_agree_frac": "%.2f" % r["sign_agree_frac"],
            "classification": code, "classification_label": label,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    print("Outlier-replication: original vs replication R_ow (both reported, no swap)")
    print("=" * 78)
    for r in rows:
        print("%-6s %-9s  R_ws=%+s  orig_R_ow=%+s (bal %s/%s)  repl_R_ow=%+s (bal %s/%s)  "
              "[%s] %s" % (
                  r["workload"], r["strategy"], r["R_ws"], r["original_R_ow"],
                  r["original_baseline_first"], r["original_target_first"],
                  r["replication_R_ow"], r["replication_baseline_first"],
                  r["replication_target_first"], r["classification"],
                  r["classification_label"]))
    print("=" * 78)
    print("wrote %s" % OUT_CSV)


if __name__ == "__main__":
    main()
