#!/usr/bin/env python3
"""Build the §12 OUTLIER-REPLICATION analysis output tree (SIXTH campaign).

Consumes the archived, normalized, EXACT-position-balanced replication pairs and the
AUTHORITATIVE frozen 55-cell workstation<->OpenWhisk comparison, and emits a self-
contained REPLICATION SUPPLEMENT under analysis/outlier_replication/. It does NOT:
  * rerun OpenWhisk, or modify any archived evidence;
  * replace the original R_ow values anywhere (both batches are reported side by side);
  * rewrite the frozen 55-cell rho / direction-agreement / strong-strategy synthesis
    (an OPTIONAL, explicitly HYPOTHETICAL sensitivity table is emitted separately);
  * pool this campaign into the five-campaign coverage estimator (5376/2688 preserved).

Pre-registered classification rules, bands, cells and families are imported verbatim
from analyze_outlier_replication.py (fixed before any replication evidence existed).
The headline sensitivity statistics reuse compare_effectiveness.category()/spearman()
so the hypothetical-replacement table mirrors the frozen estimator exactly.

Outputs (under analysis/outlier_replication/):
  replication_cell_comparison.csv       six rows, §6 column set + delta + classification
  replication_position_diagnostics.csv  per cell: baseline-first / target-first / all-
                                         balanced R, position gap, same-sign flag, spread
  replication_seed_diagnostics.csv      per seed (C_hit 1/2/3) + combined, all cells
  replication_summary.json              primary/secondary scientific answers + accounting
  sensitivity_replaced_six.csv          OPTIONAL, HYPOTHETICAL-ONLY (never historical)
  MANIFEST.json                         identities, source SHAs, provenance, do-not-pool
"""
import csv
import hashlib
import json
import statistics as st
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
from analyze_outlier_replication import (  # noqa: E402  (pre-registered, verbatim)
    WL_MAP, CELLS, classify, sign, NEUTRAL_BAND, SIGN_AGREE_BAND,
    COMPARISON_CSV, REPL_PAIRS_CSV, load_original,
)
from compare_effectiveness import category, spearman  # noqa: E402

REPO = _HERE.parents[3]
OW = REPO / "deployment/openwhisk"
OUT_DIR = OW / "analysis/outlier_replication"
NORM_MANIFEST = (OW / "analysis/normalized/portability_outlier_replication/"
                 "portability_outlier_replication_normalization_manifest.json")

# Historical five-campaign coverage totals — PRESERVED, never re-derived here.
FIVE_CAMPAIGN = {"campaigns": 5, "invocations": 5376, "pairs": 2688, "pooled": False}
REPLICATION = {"campaigns": 1, "invocations": 236, "pairs": 118}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha():
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return None


def load_replication_detail():
    """Per cell: all / baseline-first / target-first / per-seed pair R lists (standalone)."""
    if not REPL_PAIRS_CSV.exists():
        sys.exit("NO replication evidence: %s absent — run WK2 + normalize first." % REPL_PAIRS_CSV)
    cells = defaultdict(lambda: {"all": [], "bf": [], "tf": [], "seed": defaultdict(list)})
    with open(REPL_PAIRS_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("handle_mode") != "standalone":
                continue
            ws = WL_MAP.get(r["workload"])
            if ws is None:
                continue
            strat = r["paired_target_strategy"]
            b = float(r["baseline_first_query_us"])
            t = float(r["target_first_query_us"])
            if b <= 0:
                continue
            R = (b - t) / b
            tgt_first = int(r["target_schedule_position"]) < int(r["baseline_schedule_position"])
            c = cells[(ws, strat)]
            c["all"].append(R)
            (c["tf"] if tgt_first else c["bf"]).append(R)
            c["seed"][r["seed"]].append(R)
    return cells


def _agree(xs):
    if not xs:
        return 0.0
    p = sum(1 for v in xs if v > 0)
    n = sum(1 for v in xs if v < 0)
    return max(p, n) / len(xs)


def _med(xs):
    return st.median(xs) if xs else None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    orig = load_original()
    detail = load_replication_detail()

    # ---- 1. replication_cell_comparison.csv (§6) ----------------------------
    comp_fields = ["workload", "strategy", "family", "R_ws",
                   "original_R_ow", "replication_R_ow",
                   "original_abs_gap", "replication_abs_gap",
                   "delta_replication_vs_original",
                   "original_pair_count", "replication_pair_count",
                   "original_baseline_first", "original_target_first",
                   "replication_baseline_first", "replication_target_first",
                   "original_sign", "replication_sign",
                   "replication_sign_agree_frac",
                   "classification", "classification_label"]
    comp_rows = []
    per_cell = {}
    for ws, strat, family in CELLS:
        o = orig.get((ws, strat))
        if o is None:
            sys.exit("original comparison row missing for %s/%s" % (ws, strat))
        c = detail.get((ws, strat))
        if c is None:
            sys.exit("replication cell %s/%s absent — incomplete batch, refusing." % (ws, strat))
        R_ws = float(o["R_ws"])
        oR = float(o["R_ow"])
        rR = _med(c["all"])
        agree = _agree(c["all"])
        o_tgt, o_base = (int(x) for x in o["ow_pos"].split("/"))
        n_bf, n_tf = len(c["bf"]), len(c["tf"])
        code, label = classify(family, rR, agree)
        per_cell[(ws, strat)] = {"family": family, "R_ws": R_ws, "oR": oR, "rR": rR,
                                 "agree": agree, "code": code, "label": label,
                                 "bf": c["bf"], "tf": c["tf"], "all": c["all"],
                                 "seed": c["seed"]}
        comp_rows.append({
            "workload": ws, "strategy": strat, "family": family,
            "R_ws": "%.4f" % R_ws,
            "original_R_ow": "%.4f" % oR, "replication_R_ow": "%.4f" % rR,
            "original_abs_gap": "%.4f" % abs(oR - R_ws),
            "replication_abs_gap": "%.4f" % abs(rR - R_ws),
            "delta_replication_vs_original": "%.4f" % (rR - oR),
            "original_pair_count": o["n_ow_pairs"], "replication_pair_count": len(c["all"]),
            "original_baseline_first": o_base, "original_target_first": o_tgt,
            "replication_baseline_first": n_bf, "replication_target_first": n_tf,
            "original_sign": sign(oR), "replication_sign": sign(rR),
            "replication_sign_agree_frac": "%.2f" % agree,
            "classification": code, "classification_label": label,
        })
    _write_csv(OUT_DIR / "replication_cell_comparison.csv", comp_fields, comp_rows)

    # ---- 2. replication_position_diagnostics.csv (§9) -----------------------
    pos_fields = ["workload", "strategy", "family",
                  "all_balanced_R", "baseline_first_R", "target_first_R",
                  "position_gap_bf_minus_tf", "n_baseline_first", "n_target_first",
                  "position_subsets_same_sign", "position_dominates_R",
                  "spread_min", "spread_max", "spread_iqr", "sign_agree_frac"]
    pos_rows = []
    for ws, strat, family in CELLS:
        pc = per_cell[(ws, strat)]
        bfR, tfR, allR = _med(pc["bf"]), _med(pc["tf"]), pc["rR"]
        gap = bfR - tfR
        same_sign = (sign(bfR) == sign(tfR))
        # position dominates when the two exactly-balanced subsets disagree in sign,
        # i.e. the combined R is an artifact-cancellation average, not a stable effect.
        dominates = (not same_sign) or (abs(gap) > abs(allR))
        allv = sorted(pc["all"])
        q = st.quantiles(allv, n=4) if len(allv) >= 4 else [allv[0], _med(allv), allv[-1]]
        pos_rows.append({
            "workload": ws, "strategy": strat, "family": family,
            "all_balanced_R": "%.4f" % allR,
            "baseline_first_R": "%.4f" % bfR, "target_first_R": "%.4f" % tfR,
            "position_gap_bf_minus_tf": "%.4f" % gap,
            "n_baseline_first": len(pc["bf"]), "n_target_first": len(pc["tf"]),
            "position_subsets_same_sign": same_sign,
            "position_dominates_R": dominates,
            "spread_min": "%.4f" % allv[0], "spread_max": "%.4f" % allv[-1],
            "spread_iqr": "%.4f" % (q[-1] - q[0]),
            "sign_agree_frac": "%.2f" % pc["agree"],
        })
    _write_csv(OUT_DIR / "replication_position_diagnostics.csv", pos_fields, pos_rows)

    # ---- 3. replication_seed_diagnostics.csv (§9) ---------------------------
    seed_fields = ["workload", "strategy", "family", "seed_scope",
                   "R", "n_pairs", "sign_agree_frac"]
    seed_rows = []
    for ws, strat, family in CELLS:
        pc = per_cell[(ws, strat)]
        for s in sorted(pc["seed"]):
            xs = pc["seed"][s]
            seed_rows.append({
                "workload": ws, "strategy": strat, "family": family,
                "seed_scope": "seed%s" % s, "R": "%.4f" % _med(xs),
                "n_pairs": len(xs), "sign_agree_frac": "%.2f" % _agree(xs)})
        seed_rows.append({
            "workload": ws, "strategy": strat, "family": family,
            "seed_scope": "combined", "R": "%.4f" % pc["rR"],
            "n_pairs": len(pc["all"]), "sign_agree_frac": "%.2f" % pc["agree"]})
    _write_csv(OUT_DIR / "replication_seed_diagnostics.csv", seed_fields, seed_rows)

    # ---- 4. optional HYPOTHETICAL sensitivity table (§10) -------------------
    sens = _sensitivity(per_cell)
    sens_fields = ["scenario", "rho_all", "rho_high_conf", "n_all", "n_high_conf",
                   "direction_agreement_all", "direction_agreement_high_conf",
                   "median_abs_gap", "note"]
    _write_csv(OUT_DIR / "sensitivity_replaced_six.csv", sens_fields, sens["rows"])

    # ---- 5. replication_summary.json (§7/§8/§9/§11) -------------------------
    summary = _summary(per_cell, sens)
    (OUT_DIR / "replication_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")

    # ---- 6. MANIFEST.json ---------------------------------------------------
    norm_manifest = json.loads(NORM_MANIFEST.read_text()) if NORM_MANIFEST.exists() else {}
    outputs = {}
    for name in ("replication_cell_comparison.csv", "replication_position_diagnostics.csv",
                 "replication_seed_diagnostics.csv", "replication_summary.json",
                 "sensitivity_replaced_six.csv"):
        p = OUT_DIR / name
        outputs[name] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
    manifest = {
        "campaign": "portability_outlier_replication",
        "role": "replication_supplement_not_a_coverage_estimator_not_pooled",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator_git_sha": _git_sha(),
        "does_not_replace_original_R_ow": True,
        "does_not_rewrite_55cell_synthesis": True,
        "does_not_pool_into_five_campaign_estimator": True,
        "source_normalized_pairs": str(REPL_PAIRS_CSV.relative_to(REPO)),
        "source_normalized_pairs_sha256": _sha256(REPL_PAIRS_CSV),
        "source_comparison_table": str(COMPARISON_CSV.relative_to(REPO)),
        "source_comparison_table_sha256": _sha256(COMPARISON_CSV),
        "execution_identity": {
            "sqlite_research_git_sha": norm_manifest.get("sqlite_research_git_sha"),
            "authoritative_run_config_sha256": norm_manifest.get("authoritative_run_config_sha256"),
            "matrix_fingerprint": norm_manifest.get("matrix_fingerprint"),
            "schedule_seed": norm_manifest.get("schedule_seed"),
            "action_image_digest": norm_manifest.get("action_image_digest"),
            "artifact_manifest_sha256": norm_manifest.get("artifact_manifest_sha256"),
            "source_bundle_sha256": norm_manifest.get("source_bundle_sha256"),
        },
        "campaign_accounting": {
            "five_campaign_coverage_PRESERVED": FIVE_CAMPAIGN,
            "replication_SEPARATE": REPLICATION,
            "all_archived_campaigns_bookkeeping_only": {
                "campaigns": 6, "invocations": 5612, "pairs": 2806,
                "note": "bookkeeping union only; NOT one estimator; NOT pooled"},
        },
        "pre_registered_bands": {"NEUTRAL_BAND": NEUTRAL_BAND,
                                 "SIGN_AGREE_BAND": SIGN_AGREE_BAND,
                                 "note": "descriptive classification aids, NOT significance thresholds"},
        "outputs": outputs,
    }
    (OUT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    _print_console(comp_rows, pos_rows, summary)


def _sensitivity(per_cell):
    """OPTIONAL hypothetical: recompute rho / agreement / median-gap over the full
    comparison table with the six original R_ow replaced by replication R_ow. Labelled
    hypothetical-only; NEVER the historical estimator."""
    rows_all = list(csv.DictReader(open(COMPARISON_CSV)))
    repl_map = {(ws, strat): pc["rR"] for (ws, strat), pc in per_cell.items()}

    def stats(replace):
        xs, ys, hi_xs, hi_ys, agree, hi_agree, gaps = [], [], [], [], 0, 0, []
        n_hi = 0
        for r in rows_all:
            key = (r["workload"], r["strategy"])
            R_ws = float(r["R_ws"])
            R_ow = float(r["R_ow"])
            if replace and key in repl_map:
                R_ow = repl_map[key]
            xs.append(R_ws); ys.append(R_ow)
            gaps.append(abs(R_ow - R_ws))
            a = category(R_ws) == category(R_ow)
            if a:
                agree += 1
            low = r.get("low_conf", "").strip().lower() in ("1", "true", "yes")
            if not low:
                n_hi += 1
                hi_xs.append(R_ws); hi_ys.append(R_ow)
                if a:
                    hi_agree += 1
        return {"rho_all": spearman(xs, ys), "rho_hi": spearman(hi_xs, hi_ys),
                "n_all": len(xs), "n_hi": n_hi, "agree": agree, "hi_agree": hi_agree,
                "med_gap": st.median(gaps)}
    orig_s = stats(False)
    repl_s = stats(True)
    rows = []
    for label, s, note in (
            ("frozen_original_HISTORICAL", orig_s,
             "authoritative frozen 55-cell estimator — unchanged, canonical"),
            ("hypothetical_six_replaced_SENSITIVITY_ONLY", repl_s,
             "HYPOTHETICAL what-if; NOT historical; six original R_ow swapped for balanced replication R_ow")):
        rows.append({
            "scenario": label,
            "rho_all": "%.3f" % s["rho_all"] if s["rho_all"] is not None else "",
            "rho_high_conf": "%.3f" % s["rho_hi"] if s["rho_hi"] is not None else "",
            "n_all": s["n_all"], "n_high_conf": s["n_hi"],
            "direction_agreement_all": "%d/%d" % (s["agree"], s["n_all"]),
            "direction_agreement_high_conf": "%d/%d" % (s["hi_agree"], s["n_hi"]),
            "median_abs_gap": "%.4f" % s["med_gap"], "note": note})
    return {"rows": rows, "orig": orig_s, "repl": repl_s}


def _summary(per_cell, sens):
    def cell(ws, strat):
        pc = per_cell[(ws, strat)]
        return {
            "R_ws": round(pc["R_ws"], 4), "original_R_ow": round(pc["oR"], 4),
            "replication_R_ow": round(pc["rR"], 4),
            "original_sign": sign(pc["oR"]), "replication_sign": sign(pc["rR"]),
            "baseline_first_R": round(_med(pc["bf"]), 4),
            "target_first_R": round(_med(pc["tf"]), 4),
            "position_gap": round(_med(pc["bf"]) - _med(pc["tf"]), 4),
            "position_subsets_same_sign": sign(_med(pc["bf"])) == sign(_med(pc["tf"])),
            "sign_agree_frac": round(pc["agree"], 2),
            "classification": pc["code"], "classification_label": pc["label"]}
    sign_flip = [("C", "layers_92"), ("C", "2d"), ("C_hit", "2e_K40")]
    reproduced = [f"{w}/{s}" for (w, s) in sign_flip
                  if per_cell[(w, s)]["rR"] <= -NEUTRAL_BAND]
    disappeared = [f"{w}/{s}" for (w, s) in sign_flip
                   if per_cell[(w, s)]["rR"] >= NEUTRAL_BAND]
    # execution-sensitive: exactly-balanced subsets still disagree in sign.
    exec_sensitive = [f"{w}/{s}" for (w, s, _f) in CELLS
                      if sign(_med(per_cell[(w, s)]["bf"])) != sign(_med(per_cell[(w, s)]["tf"]))]
    return {
        "campaign": "portability_outlier_replication",
        "not_a_performance_ranking": True, "not_pooled": True,
        "does_not_replace_original_R_ow": True,
        "pre_registered_bands": {"NEUTRAL_BAND": NEUTRAL_BAND, "SIGN_AGREE_BAND": SIGN_AGREE_BAND,
                                 "note": "descriptive aids only, NOT significance thresholds; raw R always reported"},
        "cells": {f"{w}/{s}": cell(w, s) for (w, s, _f) in CELLS},
        "primary_sign_flip_findings": {
            "original_sign_flips_reproduced_as_negative": reproduced,
            "original_sign_flips_that_disappeared_after_balancing": disappeared,
            "interpretation": (
                "Under EXACT 10/10 position balance, none of the three original sign-flips "
                "reproduced as negative; all moved positive toward the workstation sign, so "
                "the original OpenWhisk negatives are position/batch-state confounded "
                "(classification B), consistent with within-pair page-cache carryover."),
        },
        "layers_5_findings": {
            "C/layers_5": cell("C", "layers_5"),
            "YCh01/layers_5": cell("YCh01", "layers_5"),
            "YCu/layers_5": cell("YCu", "layers_5"),
            "interpretation": (
                "The original OW anomalies did not reproduce under balance: C/layers_5's "
                "strong negative became positive; YCh01/layers_5 flipped to negative and "
                "YCu/layers_5 stayed positive but both are unstable (sign-agreement < 0.60). "
                "All classify B (batch/state-sensitive)."),
        },
        "execution_sensitivity_note": {
            "cells_whose_balanced_subsets_still_disagree_in_sign": exec_sensitive,
            "interpretation": (
                "Even at exact balance the baseline-first and target-first subsets disagree "
                "in sign for these cells (position gap up to ~1.4), so their combined R is an "
                "artifact-cancellation average rather than a clean strategy effect. Only "
                "C_hit/2e_K40 and C/layers_5 have same-signed subsets."),
        },
        "campaign_accounting": {
            "five_campaign_coverage_PRESERVED": FIVE_CAMPAIGN,
            "replication_SEPARATE": REPLICATION,
            "all_archived_bookkeeping_only": {"campaigns": 6, "invocations": 5612,
                                              "pairs": 2806, "pooled": False},
        },
        "sensitivity_hypothetical_only": {
            "frozen_rho_all": round(sens["orig"]["rho_all"], 3) if sens["orig"]["rho_all"] else None,
            "hypothetical_rho_all_if_six_replaced": round(sens["repl"]["rho_all"], 3) if sens["repl"]["rho_all"] else None,
            "label": "HYPOTHETICAL sensitivity only; the frozen 55-cell synthesis is unchanged",
        },
    }


def _write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _print_console(comp_rows, pos_rows, summary):
    print("OUTLIER-REPLICATION supplement — six cells (original vs balanced replication)")
    print("=" * 92)
    for r in comp_rows:
        print("%-6s %-9s R_ws=%+7s  orig_R_ow=%+7s  repl_R_ow=%+7s  |old_gap|=%s |new_gap|=%s  [%s]"
              % (r["workload"], r["strategy"], r["R_ws"], r["original_R_ow"],
                 r["replication_R_ow"], r["original_abs_gap"], r["replication_abs_gap"],
                 r["classification"]))
    print("-" * 92)
    print("position diagnostics (exact 10/10 or 3/3 balance):")
    for r in pos_rows:
        print("  %-6s %-9s all=%+7s  base_first=%+7s  tgt_first=%+7s  gap=%+7s  same_sign=%s  pos_dominates=%s"
              % (r["workload"], r["strategy"], r["all_balanced_R"], r["baseline_first_R"],
                 r["target_first_R"], r["position_gap_bf_minus_tf"],
                 r["position_subsets_same_sign"], r["position_dominates_R"]))
    print("=" * 92)
    pf = summary["primary_sign_flip_findings"]
    print("sign-flips reproduced negative:", pf["original_sign_flips_reproduced_as_negative"] or "NONE")
    print("sign-flips disappeared after balancing:", pf["original_sign_flips_that_disappeared_after_balancing"])
    print("execution-sensitive (balanced subsets disagree in sign):",
          summary["execution_sensitivity_note"]["cells_whose_balanced_subsets_still_disagree_in_sign"])
    print("wrote ->", OUT_DIR)


if __name__ == "__main__":
    main()
