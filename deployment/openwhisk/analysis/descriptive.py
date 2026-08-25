#!/usr/bin/env python3
"""WK1 descriptive / cost / order-aware analysis layer over the canonical
OpenWhisk normalization (normalized_invocations.csv + normalized_pairs.csv).

Scope (deliberate): this layer produces machine-readable DESCRIPTIVE tables only.
It computes no speedup, no winner, no ranking, no Pareto frontier, no statistical
test. OpenWhisk here is deployment-feasibility / footprint / mechanism-space
evidence, NOT the thesis's primary performance evidence; the primary controlled
performance evidence remains the native/WK1 experiments.

A documented systematic short-lived execution/storage-state or order effect is
present in the OpenWhisk measurements. This layer is structured so later writing
cannot accidentally misuse the data:
  * baseline context is ALWAYS target-specific (grouped by paired_target_strategy)
    -- baseline rows are never pooled across targets;
  * every timing summary is descriptive (median / p25 / p75), never a corrected
    treatment effect;
  * order is surfaced (order_audit, order_position_descriptives) rather than
    deconfounded; second-position observations are never dropped;
  * the first-position view is emitted ONLY as an explicitly labelled diagnostic,
    never as a causal / corrected / paired estimator;
  * a machine-readable warning marks warm pair-level relative latency as unsuitable
    for headline strategy claims.

Reused conventions: the normalized schema and its identities are authoritative;
the float-guard idiom mirrors client/summarize.py::_f. summarize.py's
pair_effects/aggregate (which compute percentages) are intentionally NOT used.

Outputs (deterministic) under analysis/descriptive/. See main() / the report.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]                       # deployment/openwhisk
_NORM_DIR = _OW_ROOT / "analysis" / "normalized"

SCHEMA_VERSION = 1

# canonical, deterministic orderings ----------------------------------------
STRATEGY_ORDER = ["2d", "layers_5", "2e_K10", "2f_slru", "2e_K500",
                  "leaf_freq_K10", "leaf_rand_K10", "2f_top102",
                  "learned_markov_102"]
STRATEGY_RANK = {s: i for i, s in enumerate(STRATEGY_ORDER)}
HANDLE_MODES = ["warm", "standalone"]
CAMPAIGN_RANK = {"primary": 0, "secondary": 1}

TIMING_FIELDS = ["first_query_us", "deliver_us", "open_us", "select_us",
                 "reset_us", "handler_total_us"]

# per-strategy expected CONSTANT total selected pages (fail-closed if violated).
# 2f_slru is legitimately per-seed (resident working set) -> allowed to vary.
EXPECTED_CONSTANT_PAGES = {
    "2d": 92, "layers_5": 5, "2e_K10": 102, "2e_K500": 592,
    "leaf_freq_K10": 10, "leaf_rand_K10": 10, "2f_top102": 102,
    "learned_markov_102": 102,
}
VARIABLE_FOOTPRINT = {"2f_slru"}   # per-seed resident set; variation is recorded

# strategy family metadata (from repo provenance, not guessed):
#   config/artifacts.native_ycsb.json strategy_plans[*].note and
#   config/plans/keyed/native_source/PROVENANCE.md
STRATEGY_METADATA = {
    "2d": {
        "campaign": "primary", "family": "structural_interior_skeleton",
        "budget_semantics": "fixed full interior skeleton (92 interior pages); workload/seed-independent",
        "page_selection_semantics": "all 92 interior (non-leaf) b-tree pages; set-equality to interior_pages.csv",
        "interior_leaf_split": "imposed_structural", "plan_generation": "offline_frozen_static"},
    "layers_5": {
        "campaign": "primary", "family": "structural_interior_prefix",
        "budget_semantics": "fixed shallow prefix (first 5 interior pages)",
        "page_selection_semantics": "strict prefix of the 92-page 2d skeleton by native (offset,page) order",
        "interior_leaf_split": "imposed_structural", "plan_generation": "offline_frozen_static"},
    "2e_K10": {
        "campaign": "primary", "family": "skeleton_plus_hot_leaves",
        "budget_semantics": "interior skeleton (92) UNION top-K hot leaves, K=10 -> 102 total",
        "page_selection_semantics": "2d skeleton union top-10 frequency-hot leaf pages (leaf half seed-dependent)",
        "interior_leaf_split": "imposed_92_interior_plus_hot_leaves", "plan_generation": "offline_frozen_per_seed"},
    "2f_slru": {
        "campaign": "primary", "family": "resident_working_set_slru",
        "budget_semantics": "entire per-seed resident working set (SLRU); footprint varies per seed",
        "page_selection_semantics": "full SLRU resident set for workload+seed; interior half = 92 skeleton (set-equal every seed), leaf/total per-seed",
        "interior_leaf_split": "interior_92_fixed_leaf_per_seed", "plan_generation": "offline_frozen_per_seed"},
    "2e_K500": {
        "campaign": "secondary", "family": "skeleton_plus_hot_leaves",
        "budget_semantics": "interior skeleton (92) UNION top-K hot leaves, K=500 -> 592 total",
        "page_selection_semantics": "2d skeleton union top-500 frequency-hot leaf pages",
        "interior_leaf_split": "imposed_92_interior_plus_hot_leaves", "plan_generation": "offline_frozen_per_seed"},
    "leaf_freq_K10": {
        "campaign": "secondary", "family": "leaf_only_control",
        "budget_semantics": "leaf-only, 10 pages (frequency arm)",
        "page_selection_semantics": "top-10 frequency-hot leaf pages only; interior skeleton removed",
        "interior_leaf_split": "imposed_leaf_only_interior_0", "plan_generation": "offline_frozen_per_seed"},
    "leaf_rand_K10": {
        "campaign": "secondary", "family": "leaf_only_control",
        "budget_semantics": "leaf-only, 10 pages (random control arm)",
        "page_selection_semantics": "10 random leaf pages via deterministic seeded RNG; interior skeleton omitted",
        "interior_leaf_split": "imposed_leaf_only_interior_0", "plan_generation": "offline_frozen_per_seed"},
    "2f_top102": {
        "campaign": "secondary", "family": "frequency_ranked_total_budget",
        "budget_semantics": "total-page budget-matched to 2e_K10 (N_YC=102)",
        "page_selection_semantics": "top-102 pages by root->leaf traversal frequency; NO page-type knowledge",
        "interior_leaf_split": "emergent_not_imposed_observed_51_interior_51_leaf", "plan_generation": "offline_frozen_per_seed"},
    "learned_markov_102": {
        "campaign": "secondary", "family": "learned_total_budget",
        "budget_semantics": "total-page budget-matched to 2e_K10 (N_YC=102)",
        "page_selection_semantics": "top-102 pages by first-order Markov expected-visit score, held-out LOSO model (train on other 9 seeds); NO page-type knowledge",
        "interior_leaf_split": "emergent_not_imposed_observed_51_interior_51_leaf", "plan_generation": "offline_frozen_per_seed_LOSO"},
}

# matched-budget comparison scaffolding (NO winners computed at this layer)
COMPARISON_GROUPS = {
    "N_YC": 102,
    "N_YC_note": "frozen matched total-page budget for the secondary comparison; "
                 "taken from the 2e_K10 artifact (92 interior + 10 leaf).",
    "layer_note": "semantic comparison scaffolding only -- no winner, score, "
                  "ranking, or Pareto frontier is computed at this descriptive layer.",
    "groups": {
        "A_matched_total_budget_102": {
            "members": ["2f_top102", "learned_markov_102"],
            "matched_on": "selected_page_count == 102",
            "semantics": "total-page budget-matched competitors; interior/leaf split emergent (not page-type-imposed)"},
        "B_leaf_only_controls_10": {
            "members": ["leaf_freq_K10", "leaf_rand_K10"],
            "matched_on": "selected_page_count == 10 and selected_interior_count == 0",
            "semantics": "leaf-only frequency-vs-random ablation"},
        "C_skeleton_hot_leaf_budget_progression": {
            "members": ["2e_K10", "2e_K500"],
            "matched_on": "selected_interior_count == 92 skeleton; hot-leaf budget K=10 vs K=500",
            "semantics": "hot-leaf budget progression on a fixed interior skeleton"},
        "D_structural_references": {
            "members": ["2d", "layers_5"],
            "matched_on": "interior-only structural selection",
            "semantics": "structural reference points (full 92 skeleton vs shallow 5-page prefix)"},
    },
    "ungrouped": {
        "2f_slru": "per-seed resident working-set foil; footprint not total-budget-matched to any group"},
}

METHOD_WARNINGS = {
    "no_naive_warm_paired_headline": True,
    "order_effect_present": True,
    "exact_order_effect_source_resolved": False,
    "first_arm_view_is_diagnostic_only": True,
    "openwhisk_not_primary_native_performance_evidence": True,
    "warm_pairwise_relative_latency_note":
        "warm pair-level relative latency estimates are unsuitable as headline "
        "strategy-performance estimates because of the documented systematic "
        "short-lived execution/storage-state or order effect; exact source is "
        "outside scope and is NOT random noise.",
}


class GateError(Exception):
    """Raised when a fail-closed validation gate is violated."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _f(x):
    """float or None (mirrors summarize.py::_f)."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _pctile(sorted_vals, q):
    """Linear-interpolation percentile (numpy 'linear'/type-7). Deterministic."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    idx = (n - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def describe(values):
    """Descriptive summary of a numeric list: n, median, p25, p75 (primary) and
    mean/std (secondary diagnostics). None-safe; drops None."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return {"n": 0, "median": None, "p25": None, "p75": None,
                "mean": None, "std": None}
    return {
        "n": len(xs),
        "median": _pctile(xs, 0.50),
        "p25": _pctile(xs, 0.25),
        "p75": _pctile(xs, 0.75),
        "mean": statistics.fmean(xs),
        "std": statistics.pstdev(xs) if len(xs) > 1 else 0.0,
    }


def _num(v):
    """Deterministic CSV cell: None->'', bool->true/false, int->str, float->%.4f."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v)) if v.is_integer() and abs(v) < 1e9 else "%.4f" % v
        return "%.4f" % v
    return str(v)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _single_run_config(rows, ctx):
    """Fail closed if a group's rows span >1 authoritative run_config identity."""
    ids = set(r["authoritative_run_config_sha256"] for r in rows)
    if len(ids) > 1:
        raise GateError("group %s mixes run_config identities: %s" % (ctx, sorted(ids)))
    return next(iter(ids)) if ids else None


# ---------------------------------------------------------------------------
# load + source-integrity gates
# ---------------------------------------------------------------------------
def load_inputs(norm_dir):
    norm_dir = Path(norm_dir)
    manifest = json.loads((norm_dir / "normalization_manifest.json").read_text())
    inv_path = norm_dir / "normalized_invocations.csv"
    pair_path = norm_dir / "normalized_pairs.csv"

    # §13: normalized source SHAs must match the normalization manifest
    problems = []
    inv_sha = sha256_file(inv_path)
    pair_sha = sha256_file(pair_path)
    exp_inv = manifest["outputs"]["normalized_invocations.csv"]["sha256"]
    exp_pair = manifest["outputs"]["normalized_pairs.csv"]["sha256"]
    if inv_sha != exp_inv:
        problems.append("normalized_invocations.csv sha %s != manifest %s" % (inv_sha, exp_inv))
    if pair_sha != exp_pair:
        problems.append("normalized_pairs.csv sha %s != manifest %s" % (pair_sha, exp_pair))

    with open(inv_path, newline="") as f:
        inv_rows = list(csv.DictReader(f))
    with open(pair_path, newline="") as f:
        pair_rows = list(csv.DictReader(f))

    # coerce the numeric/bool columns we rely on (schema is authoritative)
    for r in inv_rows:
        r["schedule_position"] = int(r["schedule_position"])
        r["position_within_pair"] = int(r["position_within_pair"]) if r["position_within_pair"] != "" else None
        for c in ("selected_page_count", "selected_interior_count",
                  "selected_leaf_count", "selected_bytes"):
            r[c] = int(r[c]) if r[c] not in ("", None) else None
        for c in TIMING_FIELDS:
            r[c + "_f"] = _f(r[c])

    return {
        "manifest": manifest,
        "manifest_sha": sha256_file(norm_dir / "normalization_manifest.json"),
        "inv_rows": inv_rows, "pair_rows": pair_rows,
        "inv_sha": inv_sha, "pair_sha": pair_sha,
        "problems": problems,
    }


def validate_source(data):
    """§13 structural source gates over the loaded normalized rows."""
    problems = list(data["problems"])
    inv = data["inv_rows"]
    pairs = data["pair_rows"]
    manifest = data["manifest"]

    if len(inv) != 3600:
        problems.append("invocation count %d != 3600" % len(inv))
    if len(pairs) != 1800:
        problems.append("pair count %d != 1800" % len(pairs))

    known = set(STRATEGY_ORDER) | {"baseline"}
    for r in inv:
        if r["strategy"] not in known:
            problems.append("unknown strategy %r at pos %s" % (r["strategy"], r["schedule_position"]))
        if r["paired_target_strategy"] not in STRATEGY_ORDER:
            problems.append("row pos %s has non-target paired_target_strategy %r"
                            % (r["schedule_position"], r["paired_target_strategy"]))
        if r["strategy"] == "baseline" and not r["paired_target_strategy"]:
            problems.append("baseline pos %s lost paired_target_strategy" % r["schedule_position"])
        if r["position_within_pair"] not in (1, 2):
            problems.append("row pos %s missing position_within_pair" % r["schedule_position"])
        # §13: every analysis row must be a valid normalized formal observation
        if r["measured_valid"] != "true":
            problems.append("row pos %s not measured_valid" % r["schedule_position"])

    # campaign <-> run_config map from the normalization manifest
    camp_rc = {c["campaign"]: c["authoritative_run_config_sha256"]
               for c in manifest["campaigns"]}
    for r in inv:
        if r["authoritative_run_config_sha256"] != camp_rc.get(r["campaign"]):
            problems.append("row pos %s run_config does not match campaign identity" % r["schedule_position"])

    # §13: constant-footprint strategies must not vary
    by_strat_pages = defaultdict(set)
    for r in inv:
        if r["strategy"] in EXPECTED_CONSTANT_PAGES:
            by_strat_pages[r["strategy"]].add(r["selected_page_count"])
    for s, exp in EXPECTED_CONSTANT_PAGES.items():
        vals = by_strat_pages.get(s, set())
        if vals != {exp}:
            problems.append("strategy %s expected constant selected_page_count=%d but saw %s"
                            % (s, exp, sorted(vals)))

    # §13: comparison groups may only reference strategies present in the data
    present = set(r["strategy"] for r in inv)
    for gk, g in COMPARISON_GROUPS["groups"].items():
        for m in g["members"]:
            if m not in present:
                problems.append("comparison group %s references absent strategy %s" % (gk, m))
    for s in COMPARISON_GROUPS["ungrouped"]:
        if s not in present:
            problems.append("ungrouped comparison ref %s absent from data" % s)

    return problems, camp_rc


# ---------------------------------------------------------------------------
# table builders (each returns a list of dict rows, deterministically sorted)
# ---------------------------------------------------------------------------
def _footprint(rows):
    """min/max for the 4 footprint dims over a row group."""
    out = {}
    for dim in ("selected_page_count", "selected_interior_count",
                "selected_leaf_count", "selected_bytes"):
        vals = [r[dim] for r in rows if r[dim] is not None]
        out[dim + "_min"] = min(vals) if vals else None
        out[dim + "_max"] = max(vals) if vals else None
    out["footprint_constant"] = all(
        out[d + "_min"] == out[d + "_max"]
        for d in ("selected_page_count", "selected_interior_count",
                  "selected_leaf_count", "selected_bytes"))
    return out


def _target_groups(inv):
    """{(campaign, strategy, handle_mode): rows} for the 9 target strategies."""
    g = defaultdict(list)
    for r in inv:
        if r["strategy"] == "baseline":
            continue
        g[(r["campaign"], r["strategy"], r["handle_mode"])].append(r)
    return g


def build_strategy_descriptives(inv):
    groups = _target_groups(inv)
    rows = []
    for (campaign, strat, hm), rs in groups.items():
        _single_run_config(rs, "strategy_descriptives/%s/%s/%s" % (campaign, strat, hm))
        fp = _footprint(rs)
        row = {"campaign": campaign, "strategy": strat, "handle_mode": hm,
               "n_target_invocations": len(rs),
               "n_seeds": len(set(r["seed"] for r in rs)),
               "footprint_constant": fp["footprint_constant"]}
        for dim in ("selected_page_count", "selected_interior_count",
                    "selected_leaf_count", "selected_bytes"):
            row[dim + "_min"] = fp[dim + "_min"]
            row[dim + "_max"] = fp[dim + "_max"]
        for tf in TIMING_FIELDS:
            d = describe([r[tf + "_f"] for r in rs])
            row[tf + "_median"] = d["median"]
            row[tf + "_p25"] = d["p25"]
            row[tf + "_p75"] = d["p75"]
            row[tf + "_mean"] = d["mean"]
            row[tf + "_std"] = d["std"]
        rows.append(row)
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["strategy"]],
                             HANDLE_MODES.index(r["handle_mode"])))
    return rows


def build_cost_vectors(inv):
    groups = _target_groups(inv)
    rows = []
    for (campaign, strat, hm), rs in groups.items():
        fp = _footprint(rs)
        meds = {tf: describe([r[tf + "_f"] for r in rs])["median"] for tf in TIMING_FIELDS}
        # single footprint columns: the constant value, or the median when per-seed
        def one(dim):
            if fp[dim + "_min"] == fp[dim + "_max"]:
                return fp[dim + "_min"]
            vals = sorted(r[dim] for r in rs if r[dim] is not None)
            return _pctile(vals, 0.5)
        rows.append({
            "campaign": campaign, "strategy": strat, "handle_mode": hm,
            "selected_page_count": one("selected_page_count"),
            "selected_page_count_min": fp["selected_page_count_min"],
            "selected_page_count_max": fp["selected_page_count_max"],
            "selected_bytes": one("selected_bytes"),
            "selected_bytes_min": fp["selected_bytes_min"],
            "selected_bytes_max": fp["selected_bytes_max"],
            "selected_interior_count": one("selected_interior_count"),
            "selected_leaf_count": one("selected_leaf_count"),
            "footprint_varies": not fp["footprint_constant"],
            "plan_generation": STRATEGY_METADATA[strat]["plan_generation"],
            "median_select_us": meds["select_us"],
            "median_deliver_us": meds["deliver_us"],
            "median_first_query_us": meds["first_query_us"],
            "median_open_us": meds["open_us"],
            "median_handler_total_us": meds["handler_total_us"],
        })
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["strategy"]],
                             HANDLE_MODES.index(r["handle_mode"])))
    return rows


def build_baseline_context(inv):
    """§4: baseline rows grouped by (campaign, paired_target_strategy, handle_mode)
    -- NEVER pooled across targets."""
    g = defaultdict(list)
    for r in inv:
        if r["strategy"] != "baseline":
            continue
        g[(r["campaign"], r["paired_target_strategy"], r["handle_mode"])].append(r)
    rows = []
    for (campaign, tgt, hm), rs in g.items():
        # fail closed if a baseline-context group mixes paired targets
        if len(set(r["paired_target_strategy"] for r in rs)) != 1:
            raise GateError("baseline context %s/%s/%s mixes paired targets" % (campaign, tgt, hm))
        _single_run_config(rs, "baseline_context/%s/%s/%s" % (campaign, tgt, hm))
        row = {"campaign": campaign, "paired_target_strategy": tgt,
               "handle_mode": hm, "n": len(rs)}
        for tf in ("first_query_us", "open_us", "handler_total_us"):
            d = describe([r[tf + "_f"] for r in rs])
            row[tf + "_median"] = d["median"]
            row[tf + "_p25"] = d["p25"]
            row[tf + "_p75"] = d["p75"]
        rows.append(row)
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]],
                             STRATEGY_RANK[r["paired_target_strategy"]],
                             HANDLE_MODES.index(r["handle_mode"])))
    return rows


def build_order_audit(pair_rows):
    """§5: AB/BA structural counts per campaign x target x handle_mode."""
    g = defaultdict(lambda: {"n_pairs": 0, "baseline_first_count": 0,
                             "target_first_count": 0})
    for p in pair_rows:
        gk = (p["campaign"], p["paired_target_strategy"], p["handle_mode"])
        g[gk]["n_pairs"] += 1
        if p["first_strategy"] == "baseline":
            g[gk]["baseline_first_count"] += 1
        else:
            g[gk]["target_first_count"] += 1
    rows = [{"campaign": c, "target_strategy": s, "handle_mode": hm, **v}
            for (c, s, hm), v in g.items()]
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["target_strategy"]],
                             HANDLE_MODES.index(r["handle_mode"])))
    return rows


def build_order_position_descriptives(inv):
    """§5: raw first_query_us by role (baseline/target) x position (1/2), per
    campaign x target x handle_mode. Second-position rows are RETAINED."""
    g = defaultdict(list)
    for r in inv:
        role = "baseline" if r["strategy"] == "baseline" else "target"
        gk = (r["campaign"], r["paired_target_strategy"], r["handle_mode"],
              role, r["position_within_pair"])
        g[gk].append(r)
    rows = []
    for (campaign, tgt, hm, role, pos), rs in g.items():
        d = describe([r["first_query_us_f"] for r in rs])
        rows.append({"campaign": campaign, "target_strategy": tgt, "handle_mode": hm,
                     "role": role, "position_within_pair": pos, "n": d["n"],
                     "first_query_us_median": d["median"],
                     "first_query_us_p25": d["p25"], "first_query_us_p75": d["p75"]})
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["target_strategy"]],
                             HANDLE_MODES.index(r["handle_mode"]),
                             0 if r["role"] == "baseline" else 1, r["position_within_pair"]))
    return rows


def build_first_arm_diagnostic(inv):
    """§6: DIAGNOSTIC-only view of position_within_pair == 1, split by role.
    NOT a paired/causal estimator; AB/BA is not exactly 50/50 so medians must
    not be subtracted."""
    g = defaultdict(list)
    for r in inv:
        if r["position_within_pair"] != 1:
            continue
        role = "baseline" if r["strategy"] == "baseline" else "target"
        g[(r["campaign"], r["paired_target_strategy"], r["handle_mode"], role)].append(r)
    rows = []
    for (campaign, tgt, hm, role), rs in g.items():
        d = describe([r["first_query_us_f"] for r in rs])
        rows.append({"view": "first_arm_diagnostic", "campaign": campaign,
                     "target_strategy": tgt, "handle_mode": hm, "role": role,
                     "n": d["n"], "first_query_us_median": d["median"],
                     "first_query_us_p25": d["p25"], "first_query_us_p75": d["p75"]})
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["target_strategy"]],
                             HANDLE_MODES.index(r["handle_mode"]),
                             0 if r["role"] == "baseline" else 1))
    return rows


def build_standalone_decomposition(inv):
    """§7: raw median/IQR timing decomposition for handle_mode == standalone."""
    fields = ["open_us", "select_us", "deliver_us", "first_query_us", "handler_total_us"]
    g = defaultdict(list)
    for r in inv:
        if r["handle_mode"] != "standalone" or r["strategy"] == "baseline":
            continue
        g[(r["campaign"], r["strategy"])].append(r)
    rows = []
    for (campaign, strat), rs in g.items():
        row = {"campaign": campaign, "strategy": strat, "handle_mode": "standalone",
               "n": len(rs)}
        for tf in fields:
            d = describe([r[tf + "_f"] for r in rs])
            row[tf + "_median"] = d["median"]
            row[tf + "_p25"] = d["p25"]
            row[tf + "_p75"] = d["p75"]
        rows.append(row)
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["strategy"]]))
    return rows


def build_warm_decomposition(inv):
    """§8: raw median/IQR decomposition for handle_mode == warm, with the pair
    position breakdown RETAINED."""
    fields = ["select_us", "deliver_us", "first_query_us", "handler_total_us"]
    g = defaultdict(list)
    for r in inv:
        if r["handle_mode"] != "warm" or r["strategy"] == "baseline":
            continue
        g[(r["campaign"], r["strategy"], r["position_within_pair"])].append(r)
    rows = []
    for (campaign, strat, pos), rs in g.items():
        row = {"campaign": campaign, "strategy": strat, "handle_mode": "warm",
               "position_within_pair": pos, "n": len(rs)}
        for tf in fields:
            d = describe([r[tf + "_f"] for r in rs])
            row[tf + "_median"] = d["median"]
            row[tf + "_p25"] = d["p25"]
            row[tf + "_p75"] = d["p75"]
        rows.append(row)
    rows.sort(key=lambda r: (CAMPAIGN_RANK[r["campaign"]], STRATEGY_RANK[r["strategy"]],
                             r["position_within_pair"]))
    return rows


def build_strategy_metadata():
    rows = []
    for s in STRATEGY_ORDER:
        m = STRATEGY_METADATA[s]
        rows.append({"strategy": s, "campaign": m["campaign"], "family": m["family"],
                     "budget_semantics": m["budget_semantics"],
                     "page_selection_semantics": m["page_selection_semantics"],
                     "interior_leaf_split": m["interior_leaf_split"],
                     "plan_generation": m["plan_generation"]})
    return rows


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------
def write_csv(path, columns, rows):
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for r in rows:
        w.writerow([_num(r.get(c)) for c in columns])
    data = buf.getvalue().encode()
    with open(path, "wb") as f:
        f.write(data)
    return sha256_bytes(data)


def _cols(rows):
    """Column order = insertion order of the first row's keys (deterministic)."""
    return list(rows[0].keys()) if rows else []


def _git_sha():
    try:
        head = _OW_ROOT.parents[1] / ".git" / "HEAD"
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            return (_OW_ROOT.parents[1] / ".git" / ref[5:]).read_text().strip()
        return ref
    except OSError:
        return None


def run(norm_dir=_NORM_DIR, out_dir=None):
    """Full descriptive layer. Returns (ok, manifest). Raises GateError only on
    an internal grouping invariant; count/identity gates are collected and cause
    ok=False with a validation report."""
    out_dir = Path(out_dir or (_OW_ROOT / "analysis" / "descriptive"))
    os.makedirs(out_dir, exist_ok=True)

    data = load_inputs(norm_dir)
    problems, camp_rc = validate_source(data)
    inv, pairs = data["inv_rows"], data["pair_rows"]

    tables = {
        "strategy_descriptives.csv": build_strategy_descriptives(inv),
        "cost_vectors.csv": build_cost_vectors(inv),
        "baseline_context.csv": build_baseline_context(inv),
        "order_audit.csv": build_order_audit(pairs),
        "order_position_descriptives.csv": build_order_position_descriptives(inv),
        "first_arm_diagnostic.csv": build_first_arm_diagnostic(inv),
        "standalone_decomposition.csv": build_standalone_decomposition(inv),
        "warm_decomposition.csv": build_warm_decomposition(inv),
        "strategy_metadata.csv": build_strategy_metadata(),
    }

    # group-count gates (structural expectations for the 9-target / 2-mode design)
    if len(tables["strategy_descriptives.csv"]) != 18:
        problems.append("strategy_descriptives rows %d != 18" % len(tables["strategy_descriptives.csv"]))
    if len(tables["baseline_context.csv"]) != 18:
        problems.append("baseline_context rows %d != 18" % len(tables["baseline_context.csv"]))
    if len(tables["order_audit.csv"]) != 18:
        problems.append("order_audit rows %d != 18" % len(tables["order_audit.csv"]))
    # order_audit pair totals must sum to 1800 and AB+BA == n_pairs each
    tot = 0
    for r in tables["order_audit.csv"]:
        if r["baseline_first_count"] + r["target_first_count"] != r["n_pairs"]:
            problems.append("order_audit %s AB+BA != n_pairs" % r["target_strategy"])
        tot += r["n_pairs"]
    if tot != 1800:
        problems.append("order_audit total pairs %d != 1800" % tot)

    out_shas = {}
    for fname, rows in tables.items():
        out_shas[fname] = write_csv(out_dir / fname, _cols(rows), rows)

    (out_dir / "comparison_groups.json").write_text(
        json.dumps(COMPARISON_GROUPS, indent=2, sort_keys=True) + "\n")
    out_shas["comparison_groups.json"] = sha256_file(out_dir / "comparison_groups.json")

    ok = not problems

    # validation report
    vlines = ["# OpenWhisk descriptive analysis -- validation report", "",
              "overall: %s" % ("PASS" if ok else "FAIL"), "",
              "source normalized_invocations.csv sha256: %s" % data["inv_sha"],
              "source normalized_pairs.csv sha256: %s" % data["pair_sha"],
              "source normalization_manifest.json sha256: %s" % data["manifest_sha"],
              "invocations: %d (expected 3600)" % len(inv),
              "pairs: %d (expected 1800)" % len(pairs), "",
              "## table row counts"]
    for fname, rows in tables.items():
        vlines.append("%s: %d rows" % (fname, len(rows)))
    vlines += ["", "## methodological warnings"]
    for k, v in METHOD_WARNINGS.items():
        vlines.append("%s = %s" % (k, json.dumps(v)))
    vlines += ["", "## fail-closed problems (%d)" % len(problems)]
    vlines += ["(none)"] if not problems else ["FAIL %s" % p for p in problems]
    vlines.append("")
    (out_dir / "analysis_validation.txt").write_text("\n".join(vlines) + "\n")
    out_shas["analysis_validation.txt"] = sha256_file(out_dir / "analysis_validation.txt")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "analysis_script_git_sha": _git_sha(),
        "ok": ok,
        "purpose": "descriptive / cost / order-aware analysis layer over the "
                   "OpenWhisk normalization; NOT primary performance evidence and "
                   "NOT a source of speedups, winners, rankings, or significance.",
        "source": {
            "normalization_manifest_sha256": data["manifest_sha"],
            "normalized_invocations_sha256": data["inv_sha"],
            "normalized_pairs_sha256": data["pair_sha"],
            "invocation_rows": len(inv), "pair_rows": len(pairs),
            "campaign_run_config": camp_rc,
        },
        "outputs": {k: {"sha256": v} for k, v in sorted(out_shas.items())},
        "group_counts": {k: len(v) for k, v in tables.items()},
        "strategy_coverage": STRATEGY_ORDER,
        "expected_constant_selected_page_count": EXPECTED_CONSTANT_PAGES,
        "variable_footprint_strategies": sorted(VARIABLE_FOOTPRINT),
        "cost_vector_dimensions": [
            "selected_page_count", "selected_bytes", "selected_interior_count",
            "selected_leaf_count", "median_select_us", "median_deliver_us",
            "median_first_query_us", "median_open_us", "median_handler_total_us"],
        "cost_vector_note": "no single universal score is defined; strategies are "
                            "NOT ranked. Offline plan/model generation is NOT charged "
                            "per invocation (plan_generation=offline_frozen*); only "
                            "online select_us/deliver_us/etc. are per-invocation costs.",
        "comparison_groups": COMPARISON_GROUPS,
        "methodological_warnings": METHOD_WARNINGS,
    }
    (out_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    return ok, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--norm-dir", default=str(_NORM_DIR))
    ap.add_argument("--out", default=str(_OW_ROOT / "analysis" / "descriptive"))
    a = ap.parse_args()
    ok, manifest = run(a.norm_dir, a.out)
    print("descriptive analysis %s: %d tables -> %s"
          % ("PASS" if ok else "FAIL", len(manifest["group_counts"]), a.out))
    if not ok:
        print("FAILED gates -- see analysis_validation.txt", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
