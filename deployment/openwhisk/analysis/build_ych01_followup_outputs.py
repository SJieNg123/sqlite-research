#!/usr/bin/env python3
"""Build the §12 YCH01 TWO-CELL FOLLOW-UP analysis output tree (SEVENTH campaign).

Consumes the archived, normalized, EXACT-position-balanced follow-up pairs (produced by
normalize_portability_ych01_followup.py from the WK2 bundle 26500fe8fe57) and the
AUTHORITATIVE frozen 55-cell workstation<->OpenWhisk comparison + the SIXTH outlier-
replication supplement, and emits a self-contained FOLLOW-UP SUPPLEMENT under
analysis/ych01_followup/. It does NOT:
  * rerun OpenWhisk, or modify any archived evidence;
  * replace the original / sixth R_ow values anywhere (all generations reported side by side);
  * rewrite the frozen 55-cell rho / direction-agreement / strong-strategy synthesis;
  * pool this campaign into any prior estimator (five-campaign 5376/2688 preserved; sixth
    +236/+118 separate; seventh +144/+72 separate; all-archive 5756/2878 is bookkeeping ONLY).

Estimator is byte-for-byte the sixth-campaign estimator: per pair
    R = (baseline_first_query_us - target_first_query_us) / baseline_first_query_us
cell aggregate = median of per-pair R; baseline-first vs target-first split by which arm has
the lower schedule_position; per-seed aggregate = median within seed. NEUTRAL_BAND (0.10) and
SIGN_AGREE_BAND (0.60) reuse the pre-registered outlier-replication framework.

The two cells and their prior-generation reference values (side-by-side, never replaced):
  YCh01/layers_5  R_ws +0.025 (neutral) | historical primary R_ow +0.377 (low-conf, n=3, 1/2)
                  | sixth balanced R_ow -0.243 (bf -0.762 / tf +0.502)
  YCh01/2f_top14  R_ws +0.214 (effective) | historical/current R_ow -0.019 (near zero; NOT
                  strongly harmful) | no sixth campaign (not an outlier cell)

The prior direction is described ONLY as a pair-position / short-lived execution-state /
execution-storage-state effect; no specific physical mechanism (e.g. page-cache carryover) is
attributed. -0.019 is a NEAR-ZERO result. Native/WK1 remains the primary controlled evidence.

Outputs (under analysis/ych01_followup/):
  ych01_followup_cell_comparison.csv     per cell: R_ws + all prior generations + seventh, side by side
  ych01_followup_position_diagnostics.csv per cell: bf/tf/all R, gap, medians, spread, dominance
  ych01_followup_seed_diagnostics.csv    per (cell, seed): R, bf/tf, n, sign-agree
  ych01_followup_summary.json            §7/§8 scientific answers + §11 accounting + do-not-pool
  MANIFEST.json                          identities, source SHAs, provenance, do-not-pool
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
from analyze_outlier_replication import (  # noqa: E402  (pre-registered framework, verbatim)
    sign, NEUTRAL_BAND, SIGN_AGREE_BAND, load_original,
)

REPO = _HERE.parents[3]
OW = REPO / "deployment/openwhisk"
OUT_DIR = OW / "analysis/ych01_followup"
FU_PAIRS_CSV = (OW / "analysis/normalized/portability_ych01_followup/"
                "portability_ych01_followup_normalized_pairs.csv")
FU_NORM_MANIFEST = (OW / "analysis/normalized/portability_ych01_followup/"
                    "portability_ych01_followup_normalization_manifest.json")
SIXTH_POS_CSV = OW / "analysis/outlier_replication/replication_position_diagnostics.csv"
SIXTH_CELL_CSV = OW / "analysis/outlier_replication/replication_cell_comparison.csv"
# Historical primary values only: this follow-up compares its balanced replication
# against the PRE-revision frozen table. It must read the byte-preserved historical
# freeze, never the revised freeze (which already incorporates this campaign's cells).
FROZEN_COMPARISON_CSV = (OW / "analysis/comparison/effectiveness_ow_vs_workstation_historical_freeze.csv")

YCH01 = "native_ycsb_c_hot_hashed_01"

# The two follow-up cells, with descriptive family framing (NOT a magnitude claim).
CELLS = [
    (YCH01, "layers_5", "ws_neutral_ow_originally_positive"),
    (YCH01, "2f_top14", "ws_positive_ow_originally_near_zero"),
]

# Campaign-accounting layers — PRESERVED, never re-derived, never pooled (§11).
FIVE_CAMPAIGN = {"campaigns": 5, "invocations": 5376, "pairs": 2688, "pooled": False}
SIXTH = {"campaign": "portability_outlier_replication", "invocations": 236, "pairs": 118}
SEVENTH = {"campaign": "portability_ych01_followup", "invocations": 144, "pairs": 72}
ALL_ARCHIVE_BOOKKEEPING = {"campaigns": 7, "invocations": 5756, "pairs": 2878,
                           "pooled": False, "is_one_estimator": False}
COVERAGE = {"cells": 65, "of": 65, "followup_adds_coverage_cells": 0}


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


def _med(xs):
    return st.median(xs) if xs else None


def _agree(xs):
    if not xs:
        return 0.0
    p = sum(1 for v in xs if v > 0)
    n = sum(1 for v in xs if v < 0)
    return max(p, n) / len(xs)


def _spread(xs):
    """(true_min, q1, q3, iqr, true_max) of a per-pair R list."""
    v = sorted(xs)
    if len(v) >= 4:
        q = st.quantiles(v, n=4)
        return v[0], q[0], q[2], q[2] - q[0], v[-1]
    return v[0], v[0], v[-1], v[-1] - v[0], v[-1]


def load_followup_detail():
    """Per cell: per-pair R lists (all / baseline-first / target-first / per-seed) + raw
    first_query_us by position. Standalone only (the follow-up is standalone-only)."""
    if not FU_PAIRS_CSV.exists():
        sys.exit("NO follow-up evidence: %s absent — run normalize_portability_ych01_followup "
                 "first." % FU_PAIRS_CSV)
    cells = defaultdict(lambda: {
        "all": [], "bf": [], "tf": [], "seed": defaultdict(list),
        "seed_bf": defaultdict(list), "seed_tf": defaultdict(list),
        "b_fq": [], "t_fq": [], "b_fq_bf": [], "b_fq_tf": [], "t_fq_bf": [], "t_fq_tf": []})
    with open(FU_PAIRS_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("handle_mode") != "standalone":
                continue
            if r["workload"] != YCH01:
                continue
            strat = r["paired_target_strategy"]
            b = float(r["baseline_first_query_us"])
            t = float(r["target_first_query_us"])
            if b <= 0:
                continue
            R = (b - t) / b
            tgt_first = int(r["target_schedule_position"]) < int(r["baseline_schedule_position"])
            c = cells[strat]
            c["all"].append(R)
            c["seed"][r["seed"]].append(R)
            c["b_fq"].append(b)
            c["t_fq"].append(t)
            if tgt_first:
                c["tf"].append(R); c["seed_tf"][r["seed"]].append(R)
                c["b_fq_tf"].append(b); c["t_fq_tf"].append(t)
            else:
                c["bf"].append(R); c["seed_bf"][r["seed"]].append(R)
                c["b_fq_bf"].append(b); c["t_fq_bf"].append(t)
    return cells


def load_sixth_reference():
    """SIXTH balanced replication all/bf/tf R for cells that were outlier cells (layers_5)."""
    ref = {}
    if SIXTH_POS_CSV.exists():
        for r in csv.DictReader(open(SIXTH_POS_CSV)):
            ref[(r["workload"], r["strategy"])] = {
                "all": float(r["all_balanced_R"]),
                "bf": float(r["baseline_first_R"]),
                "tf": float(r["target_first_R"])}
    return ref  # keyed by (family_code, strategy), e.g. ("YCh01", "layers_5")


def load_frozen_reference():
    """Historical primary R_ws / R_ow / ow_pos from the frozen 55-cell comparison."""
    ref = {}
    for r in csv.DictReader(open(FROZEN_COMPARISON_CSV)):
        ref[(r["workload"], r["strategy"])] = r
    return ref


def classify_layers5(all_R, bf_R, tf_R, sixth_all_R):
    """§7 decision tree for YCh01/layers_5 (aggregate + mandatory position subsets)."""
    both_neg = bf_R < 0 and tf_R < 0
    both_pos = bf_R > 0 and tf_R > 0
    subsets_oppose = sign(bf_R) != sign(tf_R)
    sign_shift_vs_sixth = (sixth_all_R is not None and sign(all_R) != sign(sixth_all_R))
    if both_neg:
        return ("C", "both_position_subsets_negative_stronger_reproducible_ow_negative")
    if both_pos:
        return ("D", "both_position_subsets_positive_prior_negative_did_not_reproduce")
    if all_R < 0 and subsets_oppose:
        return ("A", "aggregate_negative_subsets_oppose_persistent_position_or_state_sensitivity")
    if sign_shift_vs_sixth:
        return ("B", "aggregate_sign_or_magnitude_shift_batch_to_batch_execution_state_sensitivity")
    return ("A", "aggregate_negative_position_modulated")


def classify_2f_top14(all_R, bf_R, tf_R, sign_agree):
    """§8 decision tree for YCh01/2f_top14 (near-zero / positive / negative / position)."""
    subsets_oppose = sign(bf_R) != sign(tf_R)
    unstable = sign_agree < SIGN_AGREE_BAND
    if subsets_oppose or unstable:
        return ("D", "position_subsets_disagree_execution_state_or_pair_position_sensitive")
    if abs(all_R) < NEUTRAL_BAND:
        return ("A", "near_zero_again_stable_ow_neutral_despite_ws_positive")
    if all_R >= NEUTRAL_BAND:
        return ("B", "clearly_positive_subsets_agree_prior_near_zero_did_not_reproduce")
    return ("C", "clearly_negative_subsets_agree_reproducible_platform_divergence")


def main_axis(bf_R, tf_R, all_R, sign_agree):
    """stable_effect | pair_position_sensitive | direction_stable_position_magnitude_modulated.

    A truly position-free 'stable_effect' requires the two exactly-balanced position subsets to
    (a) share sign, (b) differ by less than NEUTRAL_BAND (negligible position magnitude gap), and
    (c) carry strong sign-agreement (>=0.75). Same-sign subsets with a non-trivial position gap
    or only borderline sign-agreement are 'direction stable, position magnitude modulated'."""
    if sign(bf_R) != sign(tf_R):
        return "pair_position_sensitive"
    if abs(bf_R - tf_R) < NEUTRAL_BAND and sign_agree >= 0.75:
        return "stable_effect"
    return "direction_stable_position_magnitude_modulated"


def _write_csv(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return _sha256(path)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    detail = load_followup_detail()
    sixth = load_sixth_reference()
    frozen = load_frozen_reference()

    per_cell = {}
    for ws, strat, family in CELLS:
        c = detail.get(strat)
        if c is None:
            sys.exit("follow-up cell %s/%s absent — incomplete batch, refusing." % (ws, strat))
        fam_code = {YCH01: "YCh01"}[ws]
        fr = frozen.get((fam_code, strat))
        if fr is None:
            sys.exit("frozen comparison row missing for %s/%s" % (fam_code, strat))
        s6 = sixth.get((fam_code, strat))
        all_R, bf_R, tf_R = _med(c["all"]), _med(c["bf"]), _med(c["tf"])
        agree = _agree(c["all"])
        per_cell[(ws, strat)] = {
            "family": family, "fam_code": fam_code,
            "R_ws": float(fr["R_ws"]), "hist_R_ow": float(fr["R_ow"]),
            "hist_ow_pos": fr["ow_pos"], "hist_low_conf": fr["low_conf"],
            "hist_n_ow_pairs": fr["n_ow_pairs"],
            "sixth_all": (s6["all"] if s6 else None),
            "sixth_bf": (s6["bf"] if s6 else None),
            "sixth_tf": (s6["tf"] if s6 else None),
            "all": all_R, "bf": bf_R, "tf": tf_R, "agree": agree,
            "n_all": len(c["all"]), "n_bf": len(c["bf"]), "n_tf": len(c["tf"]),
            "b_fq": _med(c["b_fq"]), "t_fq": _med(c["t_fq"]),
            "b_fq_bf": _med(c["b_fq_bf"]), "b_fq_tf": _med(c["b_fq_tf"]),
            "t_fq_bf": _med(c["t_fq_bf"]), "t_fq_tf": _med(c["t_fq_tf"]),
            "pairs_all": sorted(c["all"]),
            "seed": {s: sorted(v) for s, v in c["seed"].items()},
            "seed_bf": {s: v for s, v in c["seed_bf"].items()},
            "seed_tf": {s: v for s, v in c["seed_tf"].items()},
        }
        if strat == "layers_5":
            code, label = classify_layers5(all_R, bf_R, tf_R,
                                           s6["all"] if s6 else None)
        else:
            code, label = classify_2f_top14(all_R, bf_R, tf_R, agree)
        per_cell[(ws, strat)]["code"] = code
        per_cell[(ws, strat)]["label"] = label
        per_cell[(ws, strat)]["axis"] = main_axis(bf_R, tf_R, all_R, agree)

    # ---- 1. ych01_followup_cell_comparison.csv (side-by-side, never replaced) ----------
    comp_fields = ["workload", "strategy", "family", "R_ws",
                   "historical_primary_R_ow", "historical_ow_pos", "historical_low_conf",
                   "sixth_balanced_R_ow", "seventh_R_ow",
                   "seventh_baseline_first_R", "seventh_target_first_R",
                   "sixth_baseline_first_R", "sixth_target_first_R",
                   "seventh_pair_count", "seventh_sign_agree_frac",
                   "seventh_sign", "classification_code", "classification_label",
                   "main_axis"]
    comp_rows = []
    for ws, strat, _f in CELLS:
        p = per_cell[(ws, strat)]
        comp_rows.append({
            "workload": p["fam_code"], "strategy": strat, "family": p["family"],
            "R_ws": "%.4f" % p["R_ws"],
            "historical_primary_R_ow": "%.4f" % p["hist_R_ow"],
            "historical_ow_pos": p["hist_ow_pos"], "historical_low_conf": p["hist_low_conf"],
            "sixth_balanced_R_ow": ("%.4f" % p["sixth_all"]) if p["sixth_all"] is not None else "NA",
            "seventh_R_ow": "%.4f" % p["all"],
            "seventh_baseline_first_R": "%.4f" % p["bf"],
            "seventh_target_first_R": "%.4f" % p["tf"],
            "sixth_baseline_first_R": ("%.4f" % p["sixth_bf"]) if p["sixth_bf"] is not None else "NA",
            "sixth_target_first_R": ("%.4f" % p["sixth_tf"]) if p["sixth_tf"] is not None else "NA",
            "seventh_pair_count": p["n_all"], "seventh_sign_agree_frac": "%.2f" % p["agree"],
            "seventh_sign": sign(p["all"]),
            "classification_code": p["code"], "classification_label": p["label"],
            "main_axis": p["axis"],
        })
    comp_sha = _write_csv(OUT_DIR / "ych01_followup_cell_comparison.csv", comp_fields, comp_rows)

    # ---- 2. ych01_followup_position_diagnostics.csv ------------------------------------
    pos_fields = ["workload", "strategy", "family",
                  "all_R", "baseline_first_R", "target_first_R", "position_gap_bf_minus_tf",
                  "n_baseline_first", "n_target_first",
                  "position_subsets_same_sign", "position_dominates_R",
                  "median_baseline_fq_us", "median_target_fq_us",
                  "baseline_fq_us_when_baseline_first", "baseline_fq_us_when_target_first",
                  "target_fq_us_when_baseline_first", "target_fq_us_when_target_first",
                  "R_min", "R_q1", "R_q3", "R_iqr", "R_max", "sign_agree_frac"]
    pos_rows = []
    for ws, strat, _f in CELLS:
        p = per_cell[(ws, strat)]
        gap = p["bf"] - p["tf"]
        same_sign = sign(p["bf"]) == sign(p["tf"])
        dominates = (not same_sign) or (abs(gap) > abs(p["all"]))
        rmin, q1, q3, iqr, rmax = _spread(p["pairs_all"])
        pos_rows.append({
            "workload": p["fam_code"], "strategy": strat, "family": p["family"],
            "all_R": "%.4f" % p["all"],
            "baseline_first_R": "%.4f" % p["bf"], "target_first_R": "%.4f" % p["tf"],
            "position_gap_bf_minus_tf": "%.4f" % gap,
            "n_baseline_first": p["n_bf"], "n_target_first": p["n_tf"],
            "position_subsets_same_sign": same_sign, "position_dominates_R": dominates,
            "median_baseline_fq_us": "%.3f" % p["b_fq"], "median_target_fq_us": "%.3f" % p["t_fq"],
            "baseline_fq_us_when_baseline_first": "%.3f" % p["b_fq_bf"],
            "baseline_fq_us_when_target_first": "%.3f" % p["b_fq_tf"],
            "target_fq_us_when_baseline_first": "%.3f" % p["t_fq_bf"],
            "target_fq_us_when_target_first": "%.3f" % p["t_fq_tf"],
            "R_min": "%.4f" % rmin, "R_q1": "%.4f" % q1, "R_q3": "%.4f" % q3,
            "R_iqr": "%.4f" % iqr, "R_max": "%.4f" % rmax,
            "sign_agree_frac": "%.2f" % p["agree"],
        })
    pos_sha = _write_csv(OUT_DIR / "ych01_followup_position_diagnostics.csv", pos_fields, pos_rows)

    # ---- 3. ych01_followup_seed_diagnostics.csv ----------------------------------------
    seed_fields = ["workload", "strategy", "seed", "n_pairs", "seed_R",
                   "seed_baseline_first_R", "seed_target_first_R", "seed_sign_agree_frac",
                   "note"]
    seed_rows = []
    for ws, strat, _f in CELLS:
        p = per_cell[(ws, strat)]
        note = "n=12 per seed; do not over-interpret" if strat == "2f_top14" else "single seed (structural static; seed 1)"
        for s in sorted(p["seed"]):
            xs = p["seed"][s]
            bf = p["seed_bf"].get(s, []); tf = p["seed_tf"].get(s, [])
            seed_rows.append({
                "workload": p["fam_code"], "strategy": strat, "seed": s, "n_pairs": len(xs),
                "seed_R": "%.4f" % _med(xs),
                "seed_baseline_first_R": ("%.4f" % _med(bf)) if bf else "NA",
                "seed_target_first_R": ("%.4f" % _med(tf)) if tf else "NA",
                "seed_sign_agree_frac": "%.2f" % _agree(xs), "note": note,
            })
    seed_sha = _write_csv(OUT_DIR / "ych01_followup_seed_diagnostics.csv", seed_fields, seed_rows)

    # ---- 4. ych01_followup_summary.json ------------------------------------------------
    L5 = per_cell[(YCH01, "layers_5")]
    F2 = per_cell[(YCH01, "2f_top14")]
    summary = {
        "campaign": "portability_ych01_followup",
        "campaign_role": "independent_sign_stability_check_two_ych01_cells",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "not_pooled": True, "not_a_performance_ranking": True,
        "does_not_replace_prior_R_ow": True,
        "does_not_alter_frozen_55_cell_comparison": True,
        "estimator": "median of per-pair (baseline_fq - target_fq)/baseline_fq; bf/tf split by "
                     "lower schedule_position; identical to sixth-campaign estimator",
        "mechanism_language": "pair-position / short-lived execution-state / execution-storage-"
                              "state; NO page-cache carryover attributed",
        "cells": {
            "YCh01/layers_5": {
                "R_ws": round(L5["R_ws"], 4),
                "historical_primary_R_ow": round(L5["hist_R_ow"], 4),
                "historical_ow_pos": L5["hist_ow_pos"], "historical_low_conf": L5["hist_low_conf"],
                "sixth_balanced_R_ow": round(L5["sixth_all"], 4),
                "sixth_baseline_first_R": round(L5["sixth_bf"], 4),
                "sixth_target_first_R": round(L5["sixth_tf"], 4),
                "seventh_R_ow": round(L5["all"], 4),
                "seventh_baseline_first_R": round(L5["bf"], 4),
                "seventh_target_first_R": round(L5["tf"], 4),
                "seventh_sign_agree_frac": round(L5["agree"], 2),
                "seventh_pair_count": L5["n_all"],
                "section7_decision": L5["code"],
                "section7_label": L5["label"],
                "main_axis": L5["axis"],
                "negative_behavior_reproduced": (L5["all"] < 0),
                "still_position_sensitive": (sign(L5["bf"]) != sign(L5["tf"]))
                                            or (abs(L5["bf"] - L5["tf"]) > abs(L5["all"])),
                "interpretation": (
                    "Under a fresh independent EXACT-balanced batch the aggregate is negative "
                    "(-0.596) and BOTH position subsets are negative (bf -0.742, tf -0.447), "
                    "unlike the sixth batch whose subsets opposed (bf -0.762, tf +0.502). The "
                    "negative aggregate SIGN is reproduced across two independent balanced batches "
                    "(sixth -0.243, seventh -0.596); the historical primary +0.377 (low-conf, "
                    "n=3 pairs, 1/2 split) does not hold under exact balance. Position still "
                    "modulates MAGNITUDE (bf more negative than tf) but no longer the SIGN. "
                    "R_ws is itself only +0.025 (neutral), so this is an OW-side non-positive "
                    "result for a structurally-neutral 5-page static plan."),
            },
            "YCh01/2f_top14": {
                "R_ws": round(F2["R_ws"], 4),
                "historical_current_R_ow": round(F2["hist_R_ow"], 4),
                "historical_ow_pos": F2["hist_ow_pos"],
                "historical_note": "near zero; NOT strongly harmful",
                "seventh_R_ow": round(F2["all"], 4),
                "seventh_baseline_first_R": round(F2["bf"], 4),
                "seventh_target_first_R": round(F2["tf"], 4),
                "seventh_sign_agree_frac": round(F2["agree"], 2),
                "seventh_pair_count": F2["n_all"],
                "seed_R": {s: round(_med(F2["seed"][s]), 4) for s in sorted(F2["seed"])},
                "section8_decision": F2["code"],
                "section8_label": F2["label"],
                "main_axis": F2["axis"],
                "positive_neutral_or_negative": (
                    "position-dominated: aggregate +0.282 is a cancellation artifact of strongly "
                    "opposed subsets (bf -1.019, tf +0.615), not a stable positive effect"),
                "position_sensitive": (sign(F2["bf"]) != sign(F2["tf"])),
                "seed_sensitive": (max(_med(F2["seed"][s]) for s in F2["seed"])
                                   - min(_med(F2["seed"][s]) for s in F2["seed"])) >= NEUTRAL_BAND,
                "interpretation": (
                    "The seventh batch shows the two exactly-balanced position subsets strongly "
                    "OPPOSE (baseline-first -1.019, target-first +0.615; sign-agree 0.56 < 0.60), "
                    "so the cell is pair-position / execution-state sensitive rather than a clean "
                    "platform divergence. The historical near-zero -0.019 is a position-averaged "
                    "value over a highly position-sensitive cell, not evidence of a stable harmful "
                    "OW effect. Per-seed medians vary (seed1 -0.073, seed2 +0.581, seed3 -0.016) "
                    "but n=12 per seed is too small to read as a seed effect; position dominates."),
            },
        },
        "accounting": {
            "five_campaign_coverage": FIVE_CAMPAIGN,
            "sixth_outlier_replication": SIXTH,
            "seventh_ych01_followup": SEVENTH,
            "all_archive_bookkeeping": ALL_ARCHIVE_BOOKKEEPING,
            "coverage": COVERAGE,
            "never_call_5756_2878_one_estimator": True,
        },
    }
    with open(OUT_DIR / "ych01_followup_summary.json", "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")
    summary_sha = _sha256(OUT_DIR / "ych01_followup_summary.json")

    # ---- 5. MANIFEST.json --------------------------------------------------------------
    norm_manifest = json.load(open(FU_NORM_MANIFEST))
    manifest = {
        "campaign": "portability_ych01_followup",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "builder_git_sha": _git_sha(),
        "role": "SEVENTH campaign follow-up supplement (sign/stability, two YCh01 cells)",
        "does_not_pool": True, "does_not_replace_prior_R_ow": True,
        "does_not_alter_frozen_55_cell_comparison": True,
        "source_normalized_pairs": {
            "path": str(FU_PAIRS_CSV.relative_to(OW)), "sha256": _sha256(FU_PAIRS_CSV)},
        "source_normalization_manifest": {
            "path": str(FU_NORM_MANIFEST.relative_to(OW)), "sha256": _sha256(FU_NORM_MANIFEST)},
        "source_frozen_comparison": {
            "path": str(FROZEN_COMPARISON_CSV.relative_to(OW)),
            "sha256": _sha256(FROZEN_COMPARISON_CSV)},
        "source_sixth_position_diagnostics": {
            "path": str(SIXTH_POS_CSV.relative_to(OW)), "sha256": _sha256(SIXTH_POS_CSV)},
        "authoritative_identity": {
            "source_bundle_sha256": norm_manifest["source_bundle_sha256"],
            "matrix_fingerprint": norm_manifest["matrix_fingerprint"],
            "run_config_sha256": norm_manifest["authoritative_run_config_sha256"],
            "schedule_seed": norm_manifest["schedule_seed"],
            "action_image_digest": norm_manifest["action_image_digest"],
            "execution_git_sha": norm_manifest["sqlite_research_git_sha"],
        },
        "outputs": {
            "ych01_followup_cell_comparison.csv": {"sha256": comp_sha, "rows": len(comp_rows)},
            "ych01_followup_position_diagnostics.csv": {"sha256": pos_sha, "rows": len(pos_rows)},
            "ych01_followup_seed_diagnostics.csv": {"sha256": seed_sha, "rows": len(seed_rows)},
            "ych01_followup_summary.json": {"sha256": summary_sha},
        },
        "accounting": {
            "five_campaign_coverage": FIVE_CAMPAIGN, "sixth": SIXTH, "seventh": SEVENTH,
            "all_archive_bookkeeping": ALL_ARCHIVE_BOOKKEEPING, "coverage": COVERAGE},
    }
    with open(OUT_DIR / "MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    print("ych01_followup outputs written -> %s" % OUT_DIR)
    for ws, strat, _f in CELLS:
        p = per_cell[(ws, strat)]
        print("  %s/%s: seventh R_ow=%+.4f (bf=%+.4f tf=%+.4f, agree=%.2f) -> %s"
              % (p["fam_code"], strat, p["all"], p["bf"], p["tf"], p["agree"], p["code"]))
    return summary, manifest


if __name__ == "__main__":
    main()
