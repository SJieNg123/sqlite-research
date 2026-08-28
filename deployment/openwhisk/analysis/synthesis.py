#!/usr/bin/env python3
"""Thesis-facing OpenWhisk SYNTHESIS layer.

Builds the small set of thesis-ready artifacts (footprint / cost-vector /
matched-budget tables, three deployment-side figures, a claim map, thesis notes,
and a threats-to-validity note) on top of the completed, byte-frozen descriptive
analysis (analysis/descriptive/) -- which itself sits on the canonical
normalization (analysis/normalized/).

Role of OpenWhisk in the thesis (deliberate, encoded here so later writing cannot
drift): OpenWhisk is NOT the primary controlled performance evidence. It provides
(1) deployment feasibility, (2) correctness/provenance, (3) footprint / delivery-
cost evidence, (4) qualitative mechanism-space support, and (5) a deployment-side
ILLUSTRATION of the project's pre-existing cost-accounting thesis ("faster first
queries do not mean faster cold starts", REPORT.md title). OpenWhisk did NOT
discover that relation. The primary mechanism/performance evidence remains the
native/WK1 experiments.

A documented systematic short-lived execution/storage-state or order effect is
present. Therefore this layer: computes NO warm paired speedup/ratio, NO
"corrected" causal estimator, NO first-arm causal estimate, NO winner/ranking/
Pareto frontier, and NO percentage improvement. It reuses the descriptive medians
verbatim (SHA-verified) rather than recomputing latency from raw.

This module reuses descriptive.py helpers/metadata (single source of truth) and
matches its deterministic-output conventions. All inputs are SHA-gated; the layer
fails closed on any integrity or schema violation.
"""
import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_ANALYSIS_DIR = _HERE.parent                          # deployment/openwhisk/analysis
_OW_ROOT = _HERE.parents[1]                           # deployment/openwhisk
sys.path.insert(0, str(_ANALYSIS_DIR))
import descriptive as D                               # noqa: E402  (helpers + metadata)

SCHEMA_VERSION = 1

_NORM_DIR = _ANALYSIS_DIR / "normalized"
_DESC_DIR = _ANALYSIS_DIR / "descriptive"

# descriptive outputs this layer consumes (SHA-verified against the descriptive
# manifest before use)
DESC_INPUTS = [
    "cost_vectors.csv",
    "strategy_metadata.csv",
    "order_position_descriptives.csv",
]

# ---------------------------------------------------------------------------
# cross-workload PORTABILITY campaign (SECOND OpenWhisk role; additive).
# These outputs are produced by the separate portability pipeline
# (normalize_portability.py -> descriptive_portability.py). They are SHA-gated
# here so the thesis campaign framing (3600 strategy-space + 468 portability +
# 852 portability-extension = 4920 formal invocations across four byte-frozen
# campaigns) is machine-checked, NOT prose the writer can drift. The
# primary/secondary strategy-space synthesis above is entirely unaffected: the
# portability chain has its OWN manifests and its own descriptive CSVs, and the
# portability-EXTENSION campaign (below) has yet another separate chain.
# ---------------------------------------------------------------------------
PORT_DESC_DIR = _ANALYSIS_DIR / "descriptive" / "portability"
PORT_NORM_DIR = _ANALYSIS_DIR / "normalized" / "portability"
PORT_DESC_INPUTS = [
    "portability_coverage.csv",
    "portability_plan_parity.csv",
    "portability_workload_summary.csv",
]
# fail-closed shape of the completed single-batch portability campaign
PORT_EXPECTED = {
    "invocations": 468, "pairs": 234,
    "block_pairs": {"block1": 108, "block2": 72, "block3": 36, "block4": 18},
    "workloads": 5,
    "matrix_fingerprint":
        "a3274bc9632ab7aa393f015c00829373a33312d15ff8e6521759255f01eac10e",
    "run_config_sha256":
        "64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947",
}

# ---------------------------------------------------------------------------
# cross-workload PORTABILITY-EXTENSION campaign (FOURTH OpenWhisk campaign;
# additive to primary + secondary + portability). It completes the
# workstation-coverage effectiveness matrix (20 -> 49 comparable cells) by
# running the 29 uncovered (strategy, workload) cells under its OWN byte-frozen
# identity (run_config bf504a28..., schedule_seed 20260828). SHA-gated here so
# the 4920 four-campaign framing is machine-checked, never free prose. The three
# prior campaigns' manifests/identities are untouched.
# ---------------------------------------------------------------------------
PORT_EXT_DESC_DIR = _ANALYSIS_DIR / "descriptive" / "portability_ext"
PORT_EXT_NORM_DIR = _ANALYSIS_DIR / "normalized" / "portability_ext"
PORT_EXT_DESC_INPUTS = [
    "portability_ext_coverage.csv",
    "portability_ext_plan_parity.csv",
    "portability_ext_workload_summary.csv",
]
# fail-closed shape of the completed single-batch portability-extension campaign
PORT_EXT_EXPECTED = {
    "invocations": 852, "pairs": 426,
    "block_pairs": {"block5": 36, "block6": 180, "block7": 90, "block8": 72,
                    "block9": 24, "block10": 18, "block11": 6},
    "workloads": 5,
    "matrix_fingerprint":
        "5ba26fe952104792a9b6803e581627c331884fe1b39b41adb6ebeddb245fe300",
    "run_config_sha256":
        "bf504a28fb0ac3cec3b189a4de1f7b8968a35bbd9866c2ae1d5784ccc3bf77da",
}

# neutral deployment-role labels (from repo provenance / comparison scaffolding);
# descriptive, NOT a ranking.
DEPLOYMENT_ROLE = {
    "2d": "structural interior-skeleton reference",
    "layers_5": "shallow structural-prefix reference",
    "2e_K10": "skeleton + hot-leaf headline (N_YC=102 budget anchor)",
    "2f_slru": "full resident-set upper-footprint foil",
    "2e_K500": "skeleton + deep hot-leaf budget point",
    "leaf_freq_K10": "leaf-only control (frequency arm)",
    "leaf_rand_K10": "leaf-only control (random arm)",
    "2f_top102": "budget-matched frequency-ranked (emergent split)",
    "learned_markov_102": "budget-matched learned LOSO (emergent split)",
}

# machine-readable claim restrictions carried into the synthesis manifest (§15)
CLAIM_RESTRICTIONS = {
    "openwhisk_role": "deployment_complement",
    "native_is_primary_performance_evidence": True,
    "no_naive_warm_pair_speedup": True,
    "no_first_arm_causal_estimate": True,
    "exact_order_effect_source_unresolved": True,
    "no_strategy_winner_claim": True,
    "first_query_us_is_query_phase_not_total_cold_start": True,
    "order_effect_is_not_random_hardware_noise": True,
    "portability_is_execution_binding_not_latency_ranking": True,
    "portability_and_strategy_space_campaigns_not_pooled": True,
    "portability_ext_extends_workload_coverage_not_pooled": True,
    "effectiveness_comparison_is_descriptive_not_causal_equivalence": True,
}

# cost-vector column legend (§5: clearly mark the phases)
COST_VECTOR_LEGEND = {
    "select_us": "online plan-selection phase (per invocation); offline plan/model "
                 "generation is NOT charged here",
    "deliver_us": "page-delivery phase (fetching the selected pages)",
    "first_query_us": "instrumented SQLite first-query phase ONLY -- NOT total "
                      "cold-start latency",
    "open_us": "separately instrumented open/prepare phase (standalone handle)",
    "handler_total_us": "total action handler wall time",
}

# forbidden output-schema tokens: no generated table column may compute a
# speedup/ratio/winner/ranking/score/percentage (§16 fail-closed)
FORBIDDEN_COL_TOKENS = ("speedup", "ratio", "winner", "rank", "score", "pareto",
                        "percent", "pct", "faster", "improvement", "vs_baseline")


# ---------------------------------------------------------------------------
# claim map (§3): structured so the classifications are machine-checkable
# ---------------------------------------------------------------------------
# each entry: category, claim, classification, support, qualification, reason
CLAIM_MAP = [
    # A. deployment feasibility
    {"category": "A_deployment_feasibility",
     "claim": "All nine page-prefetch strategy families were represented and "
              "executed inside the OpenWhisk/serverless action across 3600 formal "
              "invocations.",
     "classification": "SAFE",
     "support": "normalized/normalization_manifest.json; strategy_metadata.csv",
     "qualification": "",
     "reason": "Direct execution record; feasibility is demonstrated by the runs "
               "themselves, independent of any latency interpretation."},
    # B. validity / correctness
    {"category": "B_validity_correctness",
     "claim": "The 3600 invocations passed the frozen validity gates under two "
              "byte-frozen run-config identities (primary 022fbeb0..., secondary "
              "441609e6...), with 1800 baseline-target pairs.",
     "classification": "SAFE",
     "support": "normalized/normalization_manifest.json",
     "qualification": "",
     "reason": "Recorded gate pass and identity binding; provenance fact, not a "
               "performance claim."},
    # C. footprint differences
    {"category": "C_footprint_differences",
     "claim": "Strategy families produce materially different selected-page "
              "footprints (5 to ~26k pages) and selected bytes.",
     "classification": "SAFE",
     "support": "openwhisk_strategy_footprint.csv",
     "qualification": "",
     "reason": "Footprint is a frozen plan property (deployment-side), unaffected "
               "by the order/state effect."},
    # D. delivery-cost differences
    {"category": "D_delivery_cost_differences",
     "claim": "Strategies with larger selected-page footprints incur larger "
              "deployment page-delivery work (median deliver_us) in this "
              "implementation.",
     "classification": "SAFE",
     "support": "openwhisk_cost_vectors.csv; figure_footprint_vs_delivery",
     "qualification": "Descriptive of this implementation's page-delivery "
                      "mechanism; deliver_us is a delivery-work count, not a "
                      "strategy speedup.",
     "reason": "deliver_us is handle-mode-independent and monotone in footprint "
               "here; it is a deployment cost, not a query-latency effect."},
    # E. first-query descriptive behavior
    {"category": "E_first_query_descriptive",
     "claim": "Selected plans are associated with different median instrumented "
              "SQLite first_query_us values; selected plans can lower the "
              "instrumented first_query_us phase.",
     "classification": "QUALIFIED",
     "support": "openwhisk_cost_vectors.csv; standalone_decomposition.csv",
     "qualification": "OpenWhisk absolute/paired first_query latency is NOT the "
                      "primary controlled estimate because of the documented "
                      "systematic short-lived execution/storage-state or order "
                      "effect; these are descriptive medians, not causal speedups. "
                      "first_query_us is the query phase only, NOT total cold-start "
                      "latency.",
     "reason": "The order/state effect confounds absolute and paired warm latency; "
               "native/WK1 remains the controlled estimate."},
    # F. end-to-end interpretation
    {"category": "F_end_to_end_interpretation",
     "claim": "The deployment results are consistent with the project's "
              "cost-accounting view that reducing first-query latency does not "
              "automatically reduce end-to-end handler cost (e.g. 2f_slru has the "
              "lowest first_query_us but the largest delivery and handler_total).",
     "classification": "QUALIFIED",
     "support": "openwhisk_cost_vectors.csv",
     "qualification": "An ADDITIONAL deployment-side illustration only. The "
                      "causal/mechanism claim is established primarily by the "
                      "native/WK1 experiments and PREDATES OpenWhisk (REPORT.md "
                      "title). OpenWhisk did not discover this relation.",
     "reason": "Section 11 constraint: do not rewrite thesis history."},
    {"category": "F_end_to_end_interpretation",
     "claim": "The OpenWhisk experiment revealed/discovered that faster first "
              "query does not imply faster end-to-end performance.",
     "classification": "DO_NOT_CLAIM",
     "support": "",
     "qualification": "",
     "reason": "The relation was a core research question / thesis before "
               "OpenWhisk (REPORT.md title); attributing discovery to OpenWhisk "
               "would rewrite thesis history."},
    # G. matched-budget selection intelligence
    {"category": "G_matched_budget_selection",
     "claim": "Among the N_YC=102 budget-matched strategies, the frequency-ranked "
              "(2f_top102) and learned-LOSO (learned_markov_102) plans exhibit an "
              "EMERGENT (not page-type-imposed) ~51/51 interior/leaf split.",
     "classification": "SAFE",
     "support": "strategy_metadata.csv",
     "qualification": "",
     "reason": "Recorded provenance fact about the frozen plans (page composition), "
               "not a latency comparison."},
    {"category": "G_matched_budget_selection",
     "claim": "The learned strategy is definitively better/worse than the "
              "frequency strategy based on these OpenWhisk latencies.",
     "classification": "DO_NOT_CLAIM",
     "support": "",
     "qualification": "",
     "reason": "A winner claim over confounded warm latency / non-primary "
               "evidence; matched-budget table reports composition + descriptive "
               "medians only, no winner."},
    # H. leaf-only controls
    {"category": "H_leaf_only_controls",
     "claim": "leaf_freq_K10 and leaf_rand_K10 each select 10 leaf pages with zero "
              "interior pages (leaf-only frequency-vs-random ablation).",
     "classification": "SAFE",
     "support": "openwhisk_strategy_footprint.csv; matched_budget_descriptives.csv",
     "qualification": "",
     "reason": "Frozen plan property (page composition)."},
    {"category": "H_leaf_only_controls",
     "claim": "Frequency leaf selection beats random leaf selection (or vice "
              "versa) in cold-start latency, per these OpenWhisk numbers.",
     "classification": "DO_NOT_CLAIM",
     "support": "",
     "qualification": "",
     "reason": "Winner claim over confounded warm latency; native/WK1 is the "
               "controlled arm for the frequency-vs-random lever."},
    # I. warm paired latency
    {"category": "I_warm_paired_latency",
     "claim": "The warm baseline->target adjacent-pair latency ratio is the causal "
              "speedup of the target strategy.",
     "classification": "DO_NOT_CLAIM",
     "support": "order_position_descriptives.csv (shows the position effect)",
     "qualification": "",
     "reason": "A systematic short-lived execution/storage-state or order effect "
               "makes position, not strategy, dominate adjacent warm pairs."},
    # J. standalone timing
    {"category": "J_standalone_timing",
     "claim": "The standalone decomposition reports median open/select/deliver/"
              "first_query/handler_total per strategy.",
     "classification": "QUALIFIED",
     "support": "standalone_decomposition.csv",
     "qualification": "Descriptive medians only, not a causal effect; open_us is a "
                      "separately instrumented phase and is NOT folded into "
                      "first_query_us.",
     "reason": "Reporting the phase decomposition is safe; interpreting a phase as "
               "a strategy speedup is not."},
    # K. first-arm diagnostic
    {"category": "K_first_arm_diagnostic",
     "claim": "The first-arm (position-1) medians are a corrected / true-cold "
              "treatment effect.",
     "classification": "DO_NOT_CLAIM",
     "support": "first_arm_diagnostic.csv",
     "qualification": "",
     "reason": "AB/BA are not exactly 50/50 and second-position observations are "
               "retained; the first-arm view is a diagnostic, not a deconfounded "
               "estimator -- medians must not be subtracted."},
    # L. cross-workload portability (SECOND OpenWhisk role)
    {"category": "L_cross_workload_portability",
     "claim": "The representative strategy mechanisms were executed and validated "
              "across five workload families (YC, YCu, YCh01, C, C_hit) in a "
              "separate single-batch OpenWhisk campaign of 468 formal invocations "
              "/ 234 baseline-target pairs, with per-plan page-set + offset parity "
              "(exact native, semantic 2e contract, or structural-static) proven "
              "against the frozen keyed contract.",
     "classification": "SAFE",
     "support": "normalized/portability/portability_normalization_manifest.json; "
                "descriptive/portability/portability_plan_parity.csv; "
                "portability_workload_summary.csv",
     "qualification": "Portability = deployment execution / correctness / workload "
                      "+ plan binding across workloads. It is NOT a latency, "
                      "ranking, or warm-speedup result, and the five families are "
                      "representative coverage, not exhaustive.",
     "reason": "Demonstrated by the runs themselves (execution + SHA-bound plan "
               "parity), independent of any latency interpretation; native/WK1 "
               "remains the primary performance evidence."},
    {"category": "L_cross_workload_portability",
     "claim": "The 468 portability, 852 portability-extension, and 3600 "
              "strategy-space invocations jointly estimate a single cross-workload "
              "performance effect (4920 pooled measurements of one quantity).",
     "classification": "DO_NOT_CLAIM",
     "support": "",
     "qualification": "",
     "reason": "The four campaigns answer different questions (strategy-space cost "
               "structure on YC vs. cross-workload deployment portability and its "
               "coverage extension) and are reported separately; they must never be "
               "pooled into one effect estimate, and none is a warm-latency "
               "ranking."},
    # L (fourth campaign): the additive portability-extension campaign
    {"category": "L_cross_workload_portability",
     "claim": "A fourth additive OpenWhisk campaign (portability_ext, run_config "
              "bf504a28...) executed the 29 remaining (strategy, workload) cells as "
              "852 formal invocations / 426 baseline-target pairs under its own "
              "byte-frozen identity, with per-plan page-set + offset parity proven "
              "against the frozen keyed contract, completing the workstation-"
              "coverage matrix to 49 comparable cells.",
     "classification": "SAFE",
     "support": "normalized/portability_ext/portability_ext_normalization_manifest.json; "
                "descriptive/portability_ext/portability_ext_plan_parity.csv",
     "qualification": "Execution / correctness / workload+plan binding only, under a "
                      "distinct frozen identity; NOT a latency, ranking, or warm-"
                      "speedup result, and NOT pooled with the other three campaigns.",
     "reason": "Demonstrated by the runs themselves (execution + SHA-bound plan "
               "parity), independent of any latency interpretation; a fourth "
               "byte-frozen campaign, additive like primary->secondary."},
    # M. effectiveness-portability comparison (descriptive cross-platform)
    {"category": "M_effectiveness_portability",
     "claim": "Across the 49 comparable (strategy, workload) cells, prefetch "
              "strategies that are effective on the workstation stay effective on "
              "OpenWhisk in the DESCRIPTIVE sense of relative first-query reduction "
              "vs each platform's own same-condition baseline (strong strategies "
              "34/35 effective on both; clean-cell rank correlation preserved).",
     "classification": "QUALIFIED",
     "support": "comparison/VERDICT_effectiveness_portability.md; "
                "comparison/effectiveness_ow_vs_workstation.csv; "
                "comparison/ws_provenance.csv",
     "qualification": "Descriptive cross-platform CONSISTENCY of relative reductions "
                      "only (standalone handles; same-batch R). It is NOT a claim of "
                      "equal absolute latency, equal effect size, causal equivalence, "
                      "hardware-independent speedup, or reproduction of the "
                      "workstation performance ranking.",
     "reason": "Relative reductions are the only cross-machine-comparable quantity; "
               "absolute microseconds are not, and OpenWhisk warm latency carries "
               "the order/state effect. Native/WK1 remains the primary controlled "
               "evidence."},
    {"category": "M_effectiveness_portability",
     "claim": "The OpenWhisk and workstation first-query latencies are equal / "
              "OpenWhisk reproduces the workstation absolute speedup for each "
              "strategy.",
     "classification": "DO_NOT_CLAIM",
     "support": "",
     "qualification": "",
     "reason": "Only relative-reduction direction/consistency is comparable across "
               "machines; absolute latency and effect size differ by platform and "
               "are never asserted equal."},
]


# ---------------------------------------------------------------------------
# load + integrity gates
# ---------------------------------------------------------------------------
def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_inputs(desc_dir=_DESC_DIR, norm_dir=_NORM_DIR):
    """Load the descriptive tables, fail-closed on SHA / chain violations."""
    desc_dir = Path(desc_dir)
    norm_dir = Path(norm_dir)
    problems = []

    desc_manifest = json.loads((desc_dir / "analysis_manifest.json").read_text())
    norm_manifest = json.loads((norm_dir / "normalization_manifest.json").read_text())

    # (1) each consumed descriptive CSV must match the descriptive manifest SHA
    desc_shas = {}
    for name in DESC_INPUTS:
        actual = D.sha256_file(desc_dir / name)
        expected = desc_manifest["outputs"].get(name, {}).get("sha256")
        desc_shas[name] = actual
        if expected is None:
            problems.append("descriptive manifest has no sha for %s" % name)
        elif actual != expected:
            problems.append("%s sha %s != descriptive manifest %s"
                            % (name, actual, expected))

    # (2) chain: descriptive manifest's recorded normalized SHAs must match the
    #     normalization manifest's own output SHAs
    ds = desc_manifest.get("source", {})
    ns = norm_manifest.get("outputs", {})
    chain = [
        ("normalized_invocations.csv",
         ds.get("normalized_invocations_sha256"),
         ns.get("normalized_invocations.csv", {}).get("sha256")),
        ("normalized_pairs.csv",
         ds.get("normalized_pairs_sha256"),
         ns.get("normalized_pairs.csv", {}).get("sha256")),
    ]
    for name, in_desc, in_norm in chain:
        if in_desc is None or in_norm is None or in_desc != in_norm:
            problems.append("chain mismatch for %s: descriptive=%s normalization=%s"
                            % (name, in_desc, in_norm))

    data = {
        "desc_dir": desc_dir, "norm_dir": norm_dir,
        "desc_manifest": desc_manifest, "norm_manifest": norm_manifest,
        "desc_shas": desc_shas,
        "cost_vectors": _read_csv(desc_dir / "cost_vectors.csv"),
        "strategy_metadata": _read_csv(desc_dir / "strategy_metadata.csv"),
        "order_position": _read_csv(desc_dir / "order_position_descriptives.csv"),
        "problems": problems,
    }
    return data


def load_portability(port_desc_dir=PORT_DESC_DIR, port_norm_dir=PORT_NORM_DIR):
    """Load + SHA-gate the cross-workload portability campaign facts (§13).

    Fail-closed: the portability descriptive CSVs must match their descriptive
    manifest SHAs; the descriptive manifest's recorded normalized inputs must
    match the portability normalization manifest's own output SHAs; and the
    campaign shape (468/234, block counts, 5 workloads, live fingerprint /
    run-config identity) must be exactly the completed single-batch campaign.
    Returns (facts, problems)."""
    port_desc_dir = Path(port_desc_dir)
    port_norm_dir = Path(port_norm_dir)
    problems = []

    dm_path = port_desc_dir / "portability_descriptive_manifest.json"
    nm_path = port_norm_dir / "portability_normalization_manifest.json"
    if not dm_path.exists() or not nm_path.exists():
        problems.append("portability manifests missing (run normalize_portability.py "
                        "then descriptive_portability.py before synthesis)")
        return None, problems
    desc_m = json.loads(dm_path.read_text())
    norm_m = json.loads(nm_path.read_text())

    # (1) descriptive CSV SHAs
    for name in PORT_DESC_INPUTS:
        actual = D.sha256_file(port_desc_dir / name)
        expected = desc_m["outputs"].get(name, {}).get("sha256")
        if expected is None:
            problems.append("portability descriptive manifest has no sha for %s" % name)
        elif actual != expected:
            problems.append("portability %s sha %s != manifest %s"
                            % (name, actual, expected))

    # (2) chain: descriptive inputs count must match the normalization outputs
    if desc_m.get("inputs", {}).get("portability_normalized_invocations.csv") \
            != norm_m.get("counts", {}).get("invocations"):
        problems.append("portability chain mismatch on invocation count")

    # (3) campaign shape + identity (fail-closed vs the frozen single batch)
    counts = norm_m.get("counts", {})
    if counts.get("invocations") != PORT_EXPECTED["invocations"]:
        problems.append("portability invocations %s != %d"
                        % (counts.get("invocations"), PORT_EXPECTED["invocations"]))
    if counts.get("pairs") != PORT_EXPECTED["pairs"]:
        problems.append("portability pairs %s != %d"
                        % (counts.get("pairs"), PORT_EXPECTED["pairs"]))
    if norm_m.get("block_pairs") != PORT_EXPECTED["block_pairs"]:
        problems.append("portability block_pairs %s != %s"
                        % (norm_m.get("block_pairs"), PORT_EXPECTED["block_pairs"]))
    if norm_m.get("matrix_fingerprint") != PORT_EXPECTED["matrix_fingerprint"]:
        problems.append("portability matrix_fingerprint != frozen a3274bc9...")
    if norm_m.get("authoritative_run_config_sha256") != PORT_EXPECTED["run_config_sha256"]:
        problems.append("portability run_config != frozen 64f44c3e...")
    if not norm_m.get("ok"):
        problems.append("portability normalization manifest ok=false")
    if desc_m.get("workloads") != PORT_EXPECTED["workloads"]:
        problems.append("portability workloads %s != %d"
                        % (desc_m.get("workloads"), PORT_EXPECTED["workloads"]))

    facts = {
        "invocations": counts.get("invocations"),
        "pairs": counts.get("pairs"),
        "block_pairs": norm_m.get("block_pairs"),
        "workloads": desc_m.get("workloads"),
        "workload_families": norm_m.get("workload_families", {}),
        "distinct_target_plans": desc_m.get("distinct_target_plans"),
        "parity_type_counts": desc_m.get("parity_type_counts", {}),
        "matrix_fingerprint": norm_m.get("matrix_fingerprint"),
        "run_config_sha256": norm_m.get("authoritative_run_config_sha256"),
        "artifact_manifest_sha256": norm_m.get("artifact_manifest_sha256"),
        "action_image_digest": norm_m.get("action_image_digest"),
        "source_bundle_sha256": norm_m.get("source_bundle_sha256"),
        "source_bundle_filename": norm_m.get("source_bundle_filename"),
        "sqlite_research_git_sha": norm_m.get("sqlite_research_git_sha"),
        "desc_manifest_sha256": D.sha256_file(dm_path),
        "norm_manifest_sha256": D.sha256_file(nm_path),
        "desc_shas": {n: D.sha256_file(port_desc_dir / n) for n in PORT_DESC_INPUTS},
    }
    return facts, problems


def load_portability_ext(port_desc_dir=PORT_EXT_DESC_DIR,
                         port_norm_dir=PORT_EXT_NORM_DIR):
    """Load + SHA-gate the cross-workload portability-EXTENSION campaign (fourth
    campaign; §19). Mirror of load_portability with the ext filenames/shape.

    Fail-closed: the ext descriptive CSVs must match their descriptive manifest
    SHAs; the descriptive manifest's recorded normalized invocation count must
    match the ext normalization manifest's own count; and the campaign shape
    (852/426, 7 block counts, 5 workloads, live fingerprint 5ba26fe9..., run
    config bf504a28...) must be exactly the completed single-batch ext campaign.
    Returns (facts, problems)."""
    port_desc_dir = Path(port_desc_dir)
    port_norm_dir = Path(port_norm_dir)
    problems = []

    dm_path = port_desc_dir / "portability_ext_descriptive_manifest.json"
    nm_path = port_norm_dir / "portability_ext_normalization_manifest.json"
    if not dm_path.exists() or not nm_path.exists():
        problems.append("portability_ext manifests missing (run "
                        "normalize_portability_ext.py then "
                        "descriptive_portability_ext.py before synthesis)")
        return None, problems
    desc_m = json.loads(dm_path.read_text())
    norm_m = json.loads(nm_path.read_text())

    # (1) descriptive CSV SHAs
    for name in PORT_EXT_DESC_INPUTS:
        actual = D.sha256_file(port_desc_dir / name)
        expected = desc_m["outputs"].get(name, {}).get("sha256")
        if expected is None:
            problems.append("portability_ext descriptive manifest has no sha for %s"
                            % name)
        elif actual != expected:
            problems.append("portability_ext %s sha %s != manifest %s"
                            % (name, actual, expected))

    # (2) chain: descriptive inputs count must match the normalization outputs
    if desc_m.get("inputs", {}).get("portability_ext_normalized_invocations.csv") \
            != norm_m.get("counts", {}).get("invocations"):
        problems.append("portability_ext chain mismatch on invocation count")

    # (3) campaign shape + identity (fail-closed vs the frozen single batch)
    counts = norm_m.get("counts", {})
    if counts.get("invocations") != PORT_EXT_EXPECTED["invocations"]:
        problems.append("portability_ext invocations %s != %d"
                        % (counts.get("invocations"),
                           PORT_EXT_EXPECTED["invocations"]))
    if counts.get("pairs") != PORT_EXT_EXPECTED["pairs"]:
        problems.append("portability_ext pairs %s != %d"
                        % (counts.get("pairs"), PORT_EXT_EXPECTED["pairs"]))
    if norm_m.get("block_pairs") != PORT_EXT_EXPECTED["block_pairs"]:
        problems.append("portability_ext block_pairs %s != %s"
                        % (norm_m.get("block_pairs"),
                           PORT_EXT_EXPECTED["block_pairs"]))
    if norm_m.get("matrix_fingerprint") != PORT_EXT_EXPECTED["matrix_fingerprint"]:
        problems.append("portability_ext matrix_fingerprint != frozen 5ba26fe9...")
    if norm_m.get("authoritative_run_config_sha256") \
            != PORT_EXT_EXPECTED["run_config_sha256"]:
        problems.append("portability_ext run_config != frozen bf504a28...")
    if not norm_m.get("ok"):
        problems.append("portability_ext normalization manifest ok=false")
    if desc_m.get("workloads") != PORT_EXT_EXPECTED["workloads"]:
        problems.append("portability_ext workloads %s != %d"
                        % (desc_m.get("workloads"), PORT_EXT_EXPECTED["workloads"]))

    facts = {
        "invocations": counts.get("invocations"),
        "pairs": counts.get("pairs"),
        "block_pairs": norm_m.get("block_pairs"),
        "workloads": desc_m.get("workloads"),
        "workload_families": norm_m.get("workload_families", {}),
        "distinct_target_plans": desc_m.get("distinct_target_plans"),
        "parity_type_counts": desc_m.get("parity_type_counts", {}),
        "matrix_fingerprint": norm_m.get("matrix_fingerprint"),
        "run_config_sha256": norm_m.get("authoritative_run_config_sha256"),
        "artifact_manifest_sha256": norm_m.get("artifact_manifest_sha256"),
        "action_image_digest": norm_m.get("action_image_digest"),
        "source_bundle_sha256": norm_m.get("source_bundle_sha256"),
        "source_bundle_filename": norm_m.get("source_bundle_filename"),
        "sqlite_research_git_sha": norm_m.get("sqlite_research_git_sha"),
        "desc_manifest_sha256": D.sha256_file(dm_path),
        "norm_manifest_sha256": D.sha256_file(nm_path),
        "desc_shas": {n: D.sha256_file(port_desc_dir / n)
                      for n in PORT_EXT_DESC_INPUTS},
    }
    return facts, problems


def _cv_index(cost_vectors):
    """(strategy, handle_mode) -> row dict (typed)."""
    idx = {}
    for r in cost_vectors:
        idx[(r["strategy"], r["handle_mode"])] = r
    return idx


def _meta_index(strategy_metadata):
    return {r["strategy"]: r for r in strategy_metadata}


def _rng(lo, hi):
    """Footprint cell: exact int when constant, 'lo-hi' string when it varies."""
    lo, hi = int(lo), int(hi)
    return lo if lo == hi else "%d-%d" % (lo, hi)


# ---------------------------------------------------------------------------
# thesis tables
# ---------------------------------------------------------------------------
def build_footprint(data):
    """§4 footprint table: one row per strategy (footprint is handle-mode-
    independent). Exact/invariant values; 2f_slru reported as a range."""
    cv = _cv_index(data["cost_vectors"])
    meta = _meta_index(data["strategy_metadata"])
    rows = []
    problems = []
    for strat in D.STRATEGY_ORDER:
        r = cv.get((strat, "warm")) or cv.get((strat, "standalone"))
        if r is None:
            problems.append("footprint: missing cost-vector row for %s" % strat)
            continue
        pc_min = int(float(r["selected_page_count_min"]))
        pc_max = int(float(r["selected_page_count_max"]))
        by_min = int(float(r["selected_bytes_min"]))
        by_max = int(float(r["selected_bytes_max"]))
        interior = int(float(r["selected_interior_count"]))
        varies = r["footprint_varies"] == "true"
        # constancy invariant (fail-closed): only 2f_slru may vary
        if strat in D.VARIABLE_FOOTPRINT:
            if not varies or pc_min == pc_max:
                problems.append("footprint: %s expected to vary but constant" % strat)
        else:
            if varies or pc_min != pc_max:
                problems.append("footprint: %s expected constant but varies "
                                "(%d-%d)" % (strat, pc_min, pc_max))
            exp = D.EXPECTED_CONSTANT_PAGES.get(strat)
            if exp is not None and pc_min != exp:
                problems.append("footprint: %s selected_pages %d != expected %d"
                                % (strat, pc_min, exp))
        m = meta.get(strat, {})
        rows.append({
            "strategy": strat,
            "family": m.get("family", ""),
            "selected_pages": _rng(pc_min, pc_max),
            "selected_bytes": _rng(by_min, by_max),
            "interior_pages": interior,
            "leaf_pages": _rng(pc_min - interior, pc_max - interior),
            "plan_generation": m.get("plan_generation", ""),
            "deployment_role": DEPLOYMENT_ROLE.get(strat, ""),
        })
    return rows, problems


def build_cost_vectors(data):
    """§5 cost-vector table: strategy x handle_mode, phases kept separate. Medians
    are passed through verbatim from the descriptive layer (no recomputation)."""
    cv = _cv_index(data["cost_vectors"])
    rows = []
    problems = []
    for strat in D.STRATEGY_ORDER:
        for mode in D.HANDLE_MODES:
            r = cv.get((strat, mode))
            if r is None:
                problems.append("cost_vectors: missing %s/%s" % (strat, mode))
                continue
            pc_min = int(float(r["selected_page_count_min"]))
            pc_max = int(float(r["selected_page_count_max"]))
            rows.append({
                "strategy": strat,
                "handle_mode": mode,
                "selected_pages": _rng(pc_min, pc_max),
                "median_select_us": D._f(r["median_select_us"]),
                "median_deliver_us": D._f(r["median_deliver_us"]),
                "median_first_query_us": D._f(r["median_first_query_us"]),
                "median_open_us": D._f(r["median_open_us"]),
                "median_handler_total_us": D._f(r["median_handler_total_us"]),
            })
    return rows, problems


def build_matched_budget(data):
    """§8 matched-budget descriptive table for groups A/B/C/D (no winners).
    Reports page composition + median deliver/first_query per member x mode, and
    marks the emergent-vs-imposed interior/leaf split origin."""
    cv = _cv_index(data["cost_vectors"])
    meta = _meta_index(data["strategy_metadata"])
    groups = D.COMPARISON_GROUPS["groups"]
    order = ["A_matched_total_budget_102", "B_leaf_only_controls_10",
             "C_skeleton_hot_leaf_budget_progression", "D_structural_references"]
    rows = []
    problems = []
    for gname in order:
        members = groups[gname]["members"]
        for strat in sorted(members, key=lambda s: D.STRATEGY_RANK[s]):
            if strat not in D.STRATEGY_ORDER:
                problems.append("matched_budget: group %s references absent "
                                "strategy %s" % (gname, strat))
                continue
            split = meta.get(strat, {}).get("interior_leaf_split", "")
            origin = "emergent" if split.startswith("emergent") else "imposed"
            for mode in D.HANDLE_MODES:
                r = cv.get((strat, mode))
                if r is None:
                    problems.append("matched_budget: missing %s/%s" % (strat, mode))
                    continue
                pc_min = int(float(r["selected_page_count_min"]))
                pc_max = int(float(r["selected_page_count_max"]))
                interior = int(float(r["selected_interior_count"]))
                leaf = int(float(float(r["selected_leaf_count"])))
                rows.append({
                    "group": gname,
                    "strategy": strat,
                    "handle_mode": mode,
                    "selected_pages": _rng(pc_min, pc_max),
                    "selected_interior": interior,
                    "selected_leaf": leaf,
                    "interior_leaf_split_origin": origin,
                    "median_deliver_us": D._f(r["median_deliver_us"]),
                    "median_first_query_us": D._f(r["median_first_query_us"]),
                })
    return rows, problems


# ---------------------------------------------------------------------------
# figure source tables
# ---------------------------------------------------------------------------
def build_fig_footprint_vs_delivery(data):
    """Figure A source: x=selected_page_count, y=delivery median. Delivery is
    handle-mode-independent (same page-delivery work); the plotted y is the
    standalone median and the warm median is carried alongside so nothing is
    hidden. One point per strategy."""
    cv = _cv_index(data["cost_vectors"])
    rows = []
    for strat in D.STRATEGY_ORDER:
        rs = cv[(strat, "standalone")]
        rw = cv[(strat, "warm")]
        pc = D._f(rs["selected_page_count"])   # median (== exact for constant)
        rows.append({
            "strategy": strat,
            "selected_page_count": pc,
            "selected_page_count_min": int(float(rs["selected_page_count_min"])),
            "selected_page_count_max": int(float(rs["selected_page_count_max"])),
            "deliver_us_standalone_median": D._f(rs["median_deliver_us"]),
            "deliver_us_warm_median": D._f(rw["median_deliver_us"]),
            "plotted_x_selected_pages": pc,
            "plotted_y_deliver_us": D._f(rs["median_deliver_us"]),
        })
    return rows


def build_fig_query_vs_delivery(data):
    """Figure B source: x=delivery median, y=first_query median, size~pages.
    Standalone medians are plotted (warm first_query embeds the order effect); the
    warm value is carried alongside. Descriptive, NOT a Pareto frontier."""
    cv = _cv_index(data["cost_vectors"])
    rows = []
    for strat in D.STRATEGY_ORDER:
        rs = cv[(strat, "standalone")]
        rw = cv[(strat, "warm")]
        rows.append({
            "strategy": strat,
            "selected_page_count": D._f(rs["selected_page_count"]),
            "deliver_us_standalone_median": D._f(rs["median_deliver_us"]),
            "first_query_us_standalone_median": D._f(rs["median_first_query_us"]),
            "first_query_us_warm_median": D._f(rw["median_first_query_us"]),
            "plotted_x_deliver_us": D._f(rs["median_deliver_us"]),
            "plotted_y_first_query_us": D._f(rs["median_first_query_us"]),
        })
    return rows


# the 4 primary strategies carry the order-effect illustration compactly
FIG_ORDER_STRATEGIES = ["2d", "layers_5", "2e_K10", "2f_slru"]


def build_fig_order_effect(data):
    """Figure C source: warm first_query_us by role x position for the 4 primary
    strategies. Demonstrates the systematic execution-order effect that motivates
    NOT reading adjacent warm pairs as direct strategy effects."""
    idx = {}
    for r in data["order_position"]:
        if r["handle_mode"] != "warm":
            continue
        idx[(r["target_strategy"], r["role"], int(r["position_within_pair"]))] = r
    rows = []
    for strat in FIG_ORDER_STRATEGIES:
        for role in ("baseline", "target"):
            for pos in (1, 2):
                r = idx.get((strat, role, pos))
                if r is None:
                    continue
                rows.append({
                    "strategy": strat,
                    "handle_mode": "warm",
                    "role": role,
                    "position_within_pair": pos,
                    "n": int(r["n"]),
                    "first_query_us_median": D._f(r["first_query_us_median"]),
                })
    return rows


# ---------------------------------------------------------------------------
# minimal, dependency-free, deterministic SVG rendering
# (matplotlib/numpy are unavailable in this analysis host; SVG is vector,
#  publication-usable, and byte-deterministic -- see the synthesis manifest)
# ---------------------------------------------------------------------------
_W, _H = 900, 560
_ML, _MR, _MT, _MB = 90, 260, 54, 70          # margins (wide right gutter = legend)
_PLOT_W = _W - _ML - _MR
_PLOT_H = _H - _MT - _MB

# colour-blind-safe-ish fixed palette, deterministic per strategy
_PALETTE = {
    "2d": "#1f77b4", "layers_5": "#ff7f0e", "2e_K10": "#2ca02c",
    "2f_slru": "#d62728", "2e_K500": "#9467bd", "leaf_freq_K10": "#8c564b",
    "leaf_rand_K10": "#e377c2", "2f_top102": "#17becf",
    "learned_markov_102": "#bcbd22",
}


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _fmt(v):
    if v == int(v) and abs(v) < 1e9:
        return str(int(v))
    return "%.4g" % v


def _log_ticks(lo, hi):
    """Power-of-ten ticks spanning [lo, hi]."""
    a = math.floor(math.log10(lo))
    b = math.ceil(math.log10(hi))
    return [10 ** e for e in range(int(a), int(b) + 1)]


def _svg_scatter(points, xlabel, ylabel, title, subtitle, logx, logy,
                 size_by=False):
    """points: list of dict(strategy, x, y, [size]). Returns SVG string."""
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    xlo, xhi = min(xs), max(xs)
    ylo, yhi = min(ys), max(ys)

    def mapx(x):
        if logx:
            lo, hi = math.log10(xlo * 0.8), math.log10(xhi * 1.25)
            t = (math.log10(x) - lo) / (hi - lo)
        else:
            lo, hi = xlo - 0.05 * (xhi - xlo or 1), xhi + 0.05 * (xhi - xlo or 1)
            t = (x - lo) / (hi - lo)
        return _ML + t * _PLOT_W

    def mapy(y):
        if logy:
            lo, hi = math.log10(ylo * 0.8), math.log10(yhi * 1.25)
            t = (math.log10(y) - lo) / (hi - lo)
        else:
            lo, hi = ylo - 0.05 * (yhi - ylo or 1), yhi + 0.05 * (yhi - ylo or 1)
            t = (y - lo) / (hi - lo)
        return _MT + (1 - t) * _PLOT_H

    out = []
    out.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
               'viewBox="0 0 %d %d" font-family="Helvetica,Arial,sans-serif">'
               % (_W, _H, _W, _H))
    out.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (_W, _H))
    out.append('<text x="%d" y="24" font-size="17" font-weight="bold">%s</text>'
               % (_ML, _esc(title)))
    out.append('<text x="%d" y="43" font-size="12" fill="#555">%s</text>'
               % (_ML, _esc(subtitle)))
    # plot frame
    out.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" '
               'stroke="#333" stroke-width="1"/>'
               % (_ML, _MT, _PLOT_W, _PLOT_H))
    # x ticks
    xt = _log_ticks(xlo, xhi) if logx else _lin_ticks(xlo, xhi)
    for t in xt:
        if t < (xlo * 0.8 if logx else xlo) or t > (xhi * 1.25 if logx else xhi):
            continue
        px = mapx(t)
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#e0e0e0"/>'
                   % (px, _MT, px, _MT + _PLOT_H))
        out.append('<text x="%.1f" y="%d" font-size="11" text-anchor="middle">%s</text>'
                   % (px, _MT + _PLOT_H + 18, _esc(_fmt(t))))
    # y ticks
    yt = _log_ticks(ylo, yhi) if logy else _lin_ticks(ylo, yhi)
    for t in yt:
        if t < (ylo * 0.8 if logy else ylo) or t > (yhi * 1.25 if logy else yhi):
            continue
        py = mapy(t)
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e0e0e0"/>'
                   % (_ML, py, _ML + _PLOT_W, py))
        out.append('<text x="%d" y="%.1f" font-size="11" text-anchor="end">%s</text>'
                   % (_ML - 8, py + 4, _esc(_fmt(t))))
    # axis labels
    out.append('<text x="%d" y="%d" font-size="13" text-anchor="middle">%s</text>'
               % (_ML + _PLOT_W // 2, _H - 24, _esc(xlabel)))
    out.append('<text x="22" y="%d" font-size="13" text-anchor="middle" '
               'transform="rotate(-90 22 %d)">%s</text>'
               % (_MT + _PLOT_H // 2, _MT + _PLOT_H // 2, _esc(ylabel)))
    # points + legend
    ly = _MT + 6
    for p in points:
        col = _PALETTE.get(p["strategy"], "#000")
        r = 6.0
        if size_by:
            r = 4.0 + 3.0 * math.log10(max(p.get("size", 1), 1) + 1)
        cx, cy = mapx(p["x"]), mapy(p["y"])
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" '
                   'fill-opacity="0.75" stroke="#222" stroke-width="0.6"/>'
                   % (cx, cy, r, col))
        # legend row
        out.append('<circle cx="%d" cy="%.1f" r="5" fill="%s" stroke="#222" '
                   'stroke-width="0.6"/>' % (_ML + _PLOT_W + 22, ly, col))
        out.append('<text x="%d" y="%.1f" font-size="11">%s  (x=%s, y=%s)</text>'
                   % (_ML + _PLOT_W + 32, ly + 4, _esc(p["strategy"]),
                      _esc(_fmt(p["x"])), _esc(_fmt(p["y"]))))
        ly += 19
    out.append('</svg>\n')
    return "\n".join(out)


def _lin_ticks(lo, hi):
    """~5 round linear ticks."""
    span = hi - lo or 1.0
    raw = span / 5.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + step:
        ticks.append(round(t, 6))
        t += step
    return ticks


def _svg_grouped_bars(rows, title, subtitle):
    """rows: figure-C order-effect rows. Grouped bars: per strategy, 4 bars
    (baseline-p1, baseline-p2, target-p1, target-p2). Linear y."""
    strategies = FIG_ORDER_STRATEGIES
    series = [("baseline", 1), ("baseline", 2), ("target", 1), ("target", 2)]
    labels = {("baseline", 1): "baseline pos1", ("baseline", 2): "baseline pos2",
              ("target", 1): "target pos1", ("target", 2): "target pos2"}
    colors = {("baseline", 1): "#08519c", ("baseline", 2): "#9ecae1",
              ("target", 1): "#a63603", ("target", 2): "#fdae6b"}
    val = {}
    for r in rows:
        val[(r["strategy"], r["role"], r["position_within_pair"])] = \
            r["first_query_us_median"]
    ymax = max(val.values()) * 1.1

    ml, mr, mt, mb = 80, 220, 54, 70
    pw, ph = _W - ml - mr, _H - mt - mb

    def mapy(y):
        return mt + (1 - y / ymax) * ph

    out = []
    out.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
               'viewBox="0 0 %d %d" font-family="Helvetica,Arial,sans-serif">'
               % (_W, _H, _W, _H))
    out.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (_W, _H))
    out.append('<text x="%d" y="24" font-size="17" font-weight="bold">%s</text>'
               % (ml, _esc(title)))
    out.append('<text x="%d" y="43" font-size="12" fill="#555">%s</text>'
               % (ml, _esc(subtitle)))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" '
               'stroke="#333"/>' % (ml, mt, pw, ph))
    for t in _lin_ticks(0, ymax):
        if t < 0 or t > ymax:
            continue
        py = mapy(t)
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e0e0e0"/>'
                   % (ml, py, ml + pw, py))
        out.append('<text x="%d" y="%.1f" font-size="11" text-anchor="end">%s</text>'
                   % (ml - 8, py + 4, _esc(_fmt(t))))
    gw = pw / len(strategies)
    bw = gw / (len(series) + 1)
    for gi, strat in enumerate(strategies):
        gx = ml + gi * gw
        out.append('<text x="%.1f" y="%d" font-size="12" text-anchor="middle" '
                   'font-weight="bold">%s</text>'
                   % (gx + gw / 2, mt + ph + 18, _esc(strat)))
        for si, key in enumerate(series):
            v = val.get((strat, key[0], key[1]))
            if v is None:
                continue
            bx = gx + (si + 0.5) * bw
            by = mapy(v)
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                       'fill="%s"/>'
                       % (bx, by, bw * 0.9, mt + ph - by, colors[key]))
    # legend
    ly = mt + 6
    out.append('<text x="%d" y="%.1f" font-size="12" fill="#555">'
               'warm first_query_us (median)</text>' % (ml + pw + 20, ly))
    ly += 22
    for key in series:
        out.append('<rect x="%d" y="%.1f" width="12" height="12" fill="%s"/>'
                   % (ml + pw + 20, ly - 10, colors[key]))
        out.append('<text x="%d" y="%.1f" font-size="11">%s</text>'
                   % (ml + pw + 38, ly, _esc(labels[key])))
        ly += 20
    ly += 6
    out.append('<text x="%d" y="%.1f" font-size="10" fill="#777">'
               'position dominates role/strategy:</text>' % (ml + pw + 20, ly))
    ly += 15
    out.append('<text x="%d" y="%.1f" font-size="10" fill="#777">'
               'systematic order/state effect.</text>' % (ml + pw + 20, ly))
    out.append('<text x="%d" y="%d" font-size="13" text-anchor="middle">'
               'strategy (primary campaign)</text>' % (ml + pw // 2, _H - 24))
    out.append('<text x="22" y="%d" font-size="13" text-anchor="middle" '
               'transform="rotate(-90 22 %d)">warm first_query_us (us)</text>'
               % (mt + ph // 2, mt + ph // 2))
    out.append('</svg>\n')
    return "\n".join(out)


# ---------------------------------------------------------------------------
# markdown / prose renderers
# ---------------------------------------------------------------------------
def render_footprint_md(rows):
    hdr = ("strategy", "family", "selected_pages", "selected_bytes",
           "interior_pages", "leaf_pages", "plan_generation", "deployment_role")
    lines = [
        "# OpenWhisk thesis table 1 -- deployment / strategy footprint",
        "",
        "Selected-page footprint of the nine target strategies as executed inside "
        "the OpenWhisk action. Footprint is a frozen plan property and is "
        "handle-mode-independent. `2f_slru` is a per-seed resident working set and "
        "is reported as a range. **No ranking is implied.**",
        "",
        "| " + " | ".join(hdr) + " |",
        "|" + "|".join(["---"] * len(hdr)) + "|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(D._num(r[c]) for c in hdr) + " |")
    lines += [
        "",
        "Source: `openwhisk_strategy_footprint.csv` (derived from the SHA-verified "
        "descriptive `cost_vectors.csv` + `strategy_metadata.csv`).",
        "",
    ]
    return "\n".join(lines)


CLAIM_MAP_MD_HEADER = """# OpenWhisk thesis claim map

Every proposed OpenWhisk-facing statement is classified **SAFE**, **QUALIFIED**,
or **DO_NOT_CLAIM**. OpenWhisk is a deployment complement, not the primary
controlled performance evidence; the systematic short-lived execution/storage-state
or order effect (exact source outside scope) is why warm paired latency is never a
headline. This map is machine-checked by `test_synthesis.py`.

"""


def render_claim_map_md():
    lines = [CLAIM_MAP_MD_HEADER]
    cats = []
    for e in CLAIM_MAP:
        if e["category"] not in cats:
            cats.append(e["category"])
    for cat in cats:
        lines.append("## %s\n" % cat)
        lines.append("| classification | claim | support | qualification | reason |")
        lines.append("|---|---|---|---|---|")
        for e in CLAIM_MAP:
            if e["category"] != cat:
                continue
            lines.append("| **%s** | %s | %s | %s | %s |" % (
                e["classification"],
                _md_cell(e["claim"]), _md_cell(e["support"] or "--"),
                _md_cell(e["qualification"] or "--"), _md_cell(e["reason"])))
        lines.append("")
    return "\n".join(lines)


def _md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_thesis_notes_md(port, port_ext):
    """Four-campaign thesis notes (§13/§19). Role A = the YC strategy-space
    campaign (3600 inv = primary 1600 + secondary 2000). Role B = cross-workload
    portability, spanning TWO byte-frozen campaigns: `port` (468 inv) and its
    additive coverage extension `port_ext` (852 inv). Counts come from the
    SHA-gated portability + portability_ext manifests so the 4920 four-campaign
    total is machine-checked, never free prose."""
    fam = port["workload_families"]
    fam_line = ", ".join("%s (%s)" % (code, wl) for wl, code in sorted(
        fam.items(), key=lambda kv: kv[1])) if fam else \
        "YC, YCu, YCh01, C, C_hit"
    pt = port["parity_type_counts"]
    pte = port_ext["parity_type_counts"]
    total_inv = 3600 + (port["invocations"] or 0) + (port_ext["invocations"] or 0)
    return THESIS_NOTES_TMPL.format(
        total_inv=total_inv,
        port_inv=port["invocations"], port_pairs=port["pairs"],
        n_workloads=port["workloads"], fam_line=fam_line,
        n_plans=port["distinct_target_plans"],
        exact=pt.get("exact_native_plan", 0),
        semantic=pt.get("semantic_contract_reconstruction", 0),
        static=pt.get("structural_static", 0),
        port_fp=port["matrix_fingerprint"][:8],
        port_rc=port["run_config_sha256"][:8],
        bundle_sha=port["source_bundle_sha256"][:12],
        port_ext_inv=port_ext["invocations"], port_ext_pairs=port_ext["pairs"],
        n_plans_ext=port_ext["distinct_target_plans"],
        exact_ext=pte.get("exact_native_plan", 0),
        semantic_ext=pte.get("semantic_contract_reconstruction", 0),
        static_ext=pte.get("structural_static", 0),
        port_ext_fp=port_ext["matrix_fingerprint"][:8],
        port_ext_rc=port_ext["run_config_sha256"][:8],
        bundle_ext_sha=(port_ext["source_bundle_sha256"] or "0" * 64)[:12],
        tail=THESIS_NOTES_TAIL)


THESIS_NOTES_TMPL = """# OpenWhisk thesis notes (deployment complement)

Concise, thesis-ready notes for later integration. Descriptive only; no speedup,
winner, ranking, Pareto frontier, percentage, or significance is asserted here.

## Purpose

OpenWhisk was used to test whether the project's page-prefetch strategies can be
**represented and executed inside a real serverless/FaaS deployment**, and to
observe the deployment-side cost structure (footprint, page-delivery work, and the
instrumented query phase) that the strategies imply. It is a **deployment
complement** to the controlled native/WK1 experiments, not a replacement for them.

## Four OpenWhisk campaigns (do not pool)

Across the completed OpenWhisk evaluation, **{total_inv} formal invocations** were
executed across **four byte-frozen campaigns**: **3600** in the **YC deployment /
strategy-space campaign** (primary 1600 + secondary 2000), **{port_inv}** in the
**cross-workload portability campaign**, and **{port_ext_inv}** in the additive
**cross-workload portability-extension campaign** (which completes the
workstation-coverage effectiveness matrix). These span two ROLES answering DIFFERENT
questions -- the strategy-space cost structure on one canonical workload, and
cross-workload deployment portability of representative mechanisms. They are reported
separately and **must not be pooled into a single effect estimate**, and none is a
warm-latency ranking.

## Experimental coverage (Role A -- YC strategy-space campaign)

- 9 target strategy families (primary: 2d, layers_5, 2e_K10, 2f_slru; secondary:
  2e_K500, leaf_freq_K10, leaf_rand_K10, 2f_top102, learned_markov_102).
- 3600 formal invocations; 1800 baseline-target pairs.
- Canonical YC workload (`native_ycsb_c_read_zipf`), 10 seeds.
- Two handle modes: warm (keep-alive process) and standalone (fresh process).
- Two byte-frozen run-config identities (primary `022fbeb0...`, secondary
  `441609e6...`); all invocations passed the frozen validity gates.

## Cross-workload portability (Role B -- second OpenWhisk role)

- A single-batch, block-union campaign: **{port_inv} formal invocations /
  {port_pairs} baseline-target pairs**, one live matrix fingerprint
  (`{port_fp}...`), one run-config identity (`{port_rc}...`), bundle
  `{bundle_sha}...`.
- **{n_workloads} representative workload families**: {fam_line}.
- {n_plans} distinct executed target plans, each with proven page-set + offset
  parity against the frozen keyed contract: {exact} exact-native-plan,
  {semantic} semantic-2e-contract-reconstruction, {static} structural-static.
- Every invocation passed the same frozen validity gates (cold reset, delivery,
  oracle, measured-valid) as Role A.
- Portability here means **deployment execution + correctness + workload/plan
  binding across workloads** -- NOT a latency comparison, ranking, or warm
  speedup. The five families are **representative** coverage, not exhaustive.

## Cross-workload portability extension (Role B -- fourth campaign)

- An additive single-batch, block-union campaign completing the
  workstation-coverage matrix: **{port_ext_inv} formal invocations /
  {port_ext_pairs} baseline-target pairs** (7 blocks), one live matrix
  fingerprint (`{port_ext_fp}...`), its OWN run-config identity
  (`{port_ext_rc}...`), bundle `{bundle_ext_sha}...` -- distinct from the three
  prior campaigns, which are byte-unchanged.
- {n_plans_ext} distinct executed target plans across the same {n_workloads}
  families, each with proven page-set + offset parity against the frozen keyed
  contract: {exact_ext} exact-native-plan, {semantic_ext}
  semantic-2e-contract-reconstruction, {static_ext} structural-static.
- It runs the 29 previously-uncovered (strategy, workload) cells, taking the
  workstation-vs-OpenWhisk comparable-cell coverage from 20 to **49 cells**. The
  effectiveness comparison over those 49 cells is a **descriptive cross-platform
  consistency** check of relative first-query reductions (standalone handles),
  **not** an absolute-latency, causal-equivalence, or ranking-reproduction claim.
- Like the other three campaigns it passed the same frozen validity gates and is
  **never pooled** into a single effect estimate.

## Deployment feasibility
{tail}"""


# tail (Role-A prose) appended verbatim after the two-role framing above
THESIS_NOTES_TAIL = """
Every strategy family -- structural skeletons, skeleton+hot-leaf unions, leaf-only
controls, a full resident working set, and the two budget-matched ranked/learned
plans -- was expressed as a frozen delivery plan and executed by the OpenWhisk
action under the same validity gates. This establishes that the strategy space is
**deployable**, not merely a native-benchmark construct.

## Footprint and delivery cost

Footprint spans three orders of magnitude (5 pages for layers_5 to ~26k pages for
2f_slru). Deployment page-delivery work (`deliver_us`) grows with footprint: from
~36 us (layers_5) to ~103 ms (2f_slru). Delivery work is handle-mode-independent
(the same pages are fetched); this is a **deployment cost vector**, reported per
phase and never collapsed to a single score. Offline plan/model generation is
**not** charged per invocation -- only the online select/deliver/query phases are.

Cost-vector column legend (`openwhisk_cost_vectors.csv`):
- `select_us`  -- online plan-selection phase (offline generation not charged).
- `deliver_us` -- page-delivery phase (fetching the selected pages).
- `first_query_us` -- instrumented SQLite **first-query phase only** (NOT total
  cold-start latency).
- `open_us` -- separately instrumented open/prepare phase.
- `handler_total_us` -- total action handler wall time.

## Query-phase metric

`first_query_us` measures only the first SQLite query after page delivery. It is
**not** total cold-start latency and **not** a strategy speedup. Across strategies,
`deliver_us` and `first_query_us` vary largely independently (2f_slru has the
smallest `first_query_us` but by far the largest `deliver_us` and
`handler_total_us`). That independence is the point: **query latency alone is an
incomplete deployment metric**.

## Relationship to the native results

The **native/WK1 experiments are the primary controlled performance/mechanism
evidence.** The OpenWhisk deployment complements them: it shows the strategies run
in a serverless setting and reproduces the same qualitative cost structure. It does
not, and is not used to, establish causal strategy performance on its own.

## Measurement limitation

A systematic short-lived execution/storage-state or order effect is present in the
OpenWhisk timings: within a warm baseline-target pair, the first-executed arm
(position 1) shows much larger `first_query_us` than the second, regardless of
which strategy occupies which position. The exact lower-level source was not
resolved and is outside current scope. Consequently, **adjacent warm pair ratios
are not used as strategy-performance estimates**, and the first-arm view is a
diagnostic only.

## What we do NOT claim

- No causal warm paired-speedup estimate for any strategy.
- No resolved hardware root cause for the order/state effect (and it is **not**
  random hardware noise; the page-cache-carryover explanation was specifically
  investigated and falsified).
- No claim that OpenWhisk alone establishes the optimal strategy, or that the
  learned plan beats the frequency plan (or vice versa).
- No claim that the first-arm diagnostic is a corrected treatment effect.
- No claim that OpenWhisk *discovered* the faster-first-query-vs-end-to-end
  relation -- that is a pre-existing core thesis result (REPORT.md title).
"""


def render_threats_md(port, port_ext):
    """Threats note with the portability paragraphs filled from gated facts (§16/
    §19). Covers both the portability campaign and its additive extension."""
    return THREATS_MD_TMPL.format(
        port_inv=port["invocations"], port_pairs=port["pairs"],
        n_workloads=port["workloads"],
        port_ext_inv=port_ext["invocations"], port_ext_pairs=port_ext["pairs"])


THREATS_MD_TMPL = """# OpenWhisk threats to validity (deployment complement)

Cold-page state was reset and validated before each measured invocation: the cold
gate confirmed zero resident database pages after reset (the page-cache-carryover
hypothesis was specifically investigated and **falsified**). Nevertheless, a
systematic short-lived execution/storage-state or order effect remained: within a
warm baseline-target pair, the first-executed arm exhibits materially larger
`first_query_us` than the second arm, independently of which strategy occupies each
position. The exact lower-level source of this effect was outside the scope of this
work and is **not** attributed to any specific hardware cause (it is not random
hardware fluctuation, and not an asserted NVMe/C-state/page-cache-carryover cause).

Because of this effect, **warm adjacent-pair latency ratios are not used as primary
strategy-performance estimates**, and the first-position ("first-arm") view is
reported only as a diagnostic, never as a deconfounded or corrected treatment
effect. The primary controlled performance and mechanism evidence for the project
remains the native/WK1 experiments.

This limitation is bounded. It does **not** invalidate:
- execution correctness (3600 invocations passed the frozen validity gates);
- plan identity (frozen per-seed delivery plans, SHA-bound to the manifest);
- footprint measurements (selected pages / bytes / interior / leaf composition);
- delivery-count / delivery-cost measurements (`deliver_us`, delivered pages);
- deployment feasibility (all nine strategy families executed in OpenWhisk).

It **does** restrict interpretation of warm paired first-query latency as a direct,
causal strategy effect. No stronger invalidation is claimed, and no stronger
preservation than the items above is claimed.

## Cross-workload portability campaign (second role)

A separate single-batch campaign ({port_inv} formal invocations / {port_pairs}
baseline-target pairs across {n_workloads} representative workload families) tested
**cross-workload deployment portability**: whether the representative strategy
mechanisms execute correctly and bind to the right per-workload plan under the same
frozen validity gates. Two threats bound its interpretation:

- **The same order/state effect applies.** The portability campaign shares the warm
  handle mode and therefore the same positional effect. Its purpose is execution +
  correctness + plan/workload binding, **not** latency; portability warm timings are
  **not** used as a cross-workload speedup or ranking, and no portability latency
  claim is made.
- **Five families are representative, not exhaustive.** The workloads (YC, YCu,
  YCh01, C, C_hit) are chosen coverage points; portability is demonstrated **for
  these families**, not proven for every possible workload. Per-plan page-set +
  offset parity against the frozen keyed contract is what is established.

An additive **portability-extension campaign** ({port_ext_inv} formal invocations /
{port_ext_pairs} baseline-target pairs, its own byte-frozen identity) completed the
workstation-coverage matrix by running the remaining (strategy, workload) cells. It
shares the same two threats above (order/state effect; representative families) and
the same interpretation bounds. The effectiveness comparison built on top of it
(workstation vs OpenWhisk over 49 comparable cells) reports **relative** first-query
reductions only -- a descriptive cross-platform consistency check, **not** a claim of
equal absolute latency, equal effect size, causal equivalence, or reproduction of the
workstation ranking.

The strategy-space, portability, and portability-extension campaigns answer different
questions and are **never pooled** into a single effect. Native/WK1 remains the
primary controlled performance evidence for all of them.
"""


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def _forbidden_columns(columns):
    """Flag any column that COMPUTES a comparison/score. Match whole
    underscore/non-alphanumeric-delimited segments (so 'plan_generation' does not
    trip on the 'ratio' inside 'generation'); 'vs_baseline' is checked as a phrase."""
    import re
    bad = []
    for c in columns:
        cl = c.lower()
        segs = set(re.split(r"[^a-z0-9]+", cl))
        if segs & set(FORBIDDEN_COL_TOKENS) or "vs_baseline" in cl:
            bad.append(c)
    return bad


def run(desc_dir=_DESC_DIR, norm_dir=_NORM_DIR, out_dir=None):
    desc_dir = Path(desc_dir)
    norm_dir = Path(norm_dir)
    out_dir = Path(out_dir) if out_dir else (_ANALYSIS_DIR / "thesis")
    out_dir.mkdir(parents=True, exist_ok=True)

    data = load_inputs(desc_dir, norm_dir)
    problems = list(data["problems"])

    footprint, p = build_footprint(data);            problems += p
    cost_vectors, p = build_cost_vectors(data);      problems += p
    matched, p = build_matched_budget(data);         problems += p
    fig_a = build_fig_footprint_vs_delivery(data)
    fig_b = build_fig_query_vs_delivery(data)
    fig_c = build_fig_order_effect(data)

    # ---- structural / coverage gates (§16) --------------------------------
    if len(footprint) != 9:
        problems.append("footprint rows %d != 9" % len(footprint))
    if len(cost_vectors) != 18:
        problems.append("cost_vectors rows %d != 18" % len(cost_vectors))
    if len(matched) != 16:
        problems.append("matched_budget rows %d != 16" % len(matched))
    covered = {r["strategy"] for r in footprint}
    for s in D.STRATEGY_ORDER:
        if s not in covered:
            problems.append("footprint missing strategy %s" % s)
    # no forbidden columns anywhere
    for name, rows in (("footprint", footprint), ("cost_vectors", cost_vectors),
                       ("matched_budget", matched), ("fig_a", fig_a),
                       ("fig_b", fig_b), ("fig_c", fig_c)):
        if rows:
            bad = _forbidden_columns(rows[0].keys())
            if bad:
                problems.append("%s has forbidden columns %s" % (name, bad))
    # claim-map classification gate
    valid_cls = {"SAFE", "QUALIFIED", "DO_NOT_CLAIM"}
    for e in CLAIM_MAP:
        if e["classification"] not in valid_cls:
            problems.append("claim_map bad classification %s" % e["classification"])
    cls_index = {(e["category"], e["classification"]) for e in CLAIM_MAP}
    if ("I_warm_paired_latency", "DO_NOT_CLAIM") not in cls_index:
        problems.append("claim_map missing DO_NOT_CLAIM warm paired latency")
    if ("K_first_arm_diagnostic", "DO_NOT_CLAIM") not in cls_index:
        problems.append("claim_map missing DO_NOT_CLAIM first-arm diagnostic")
    if ("G_matched_budget_selection", "DO_NOT_CLAIM") not in cls_index:
        problems.append("claim_map missing DO_NOT_CLAIM learned-vs-frequency winner")
    # the E first-query claim must carry the order-effect qualification
    e_claims = [e for e in CLAIM_MAP if e["category"] == "E_first_query_descriptive"]
    if not e_claims or "order" not in e_claims[0]["qualification"].lower():
        problems.append("claim_map E first-query claim lacks order-effect qualifier")
    # machine-readable restriction flags present and correctly valued
    for k, v in (("openwhisk_role", "deployment_complement"),
                 ("native_is_primary_performance_evidence", True),
                 ("no_naive_warm_pair_speedup", True),
                 ("no_first_arm_causal_estimate", True),
                 ("exact_order_effect_source_unresolved", True),
                 ("no_strategy_winner_claim", True)):
        if CLAIM_RESTRICTIONS.get(k) != v:
            problems.append("restriction %s != %r" % (k, v))

    # ---- SECOND role: cross-workload portability facts (SHA-gated, §13) -----
    port, pp = load_portability()
    problems += pp
    # the two-role framing must carry the L claim category (SAFE + DO_NOT_CLAIM)
    if ("L_cross_workload_portability", "SAFE") not in cls_index:
        problems.append("claim_map missing SAFE cross-workload portability")
    if ("L_cross_workload_portability", "DO_NOT_CLAIM") not in cls_index:
        problems.append("claim_map missing DO_NOT_CLAIM portability-pooling guard")
    for k, v in (("portability_is_execution_binding_not_latency_ranking", True),
                 ("portability_and_strategy_space_campaigns_not_pooled", True)):
        if CLAIM_RESTRICTIONS.get(k) != v:
            problems.append("restriction %s != %r" % (k, v))

    # ---- FOURTH campaign: portability-extension facts (SHA-gated, §19) ------
    port_ext, ppe = load_portability_ext()
    problems += ppe
    # the four-campaign framing must carry the fourth-campaign SAFE row and the
    # descriptive effectiveness-portability category (QUALIFIED + DO_NOT_CLAIM)
    if ("M_effectiveness_portability", "QUALIFIED") not in cls_index:
        problems.append("claim_map missing QUALIFIED effectiveness-portability")
    if ("M_effectiveness_portability", "DO_NOT_CLAIM") not in cls_index:
        problems.append("claim_map missing DO_NOT_CLAIM effectiveness-equivalence guard")
    for k, v in (("portability_ext_extends_workload_coverage_not_pooled", True),
                 ("effectiveness_comparison_is_descriptive_not_causal_equivalence", True)):
        if CLAIM_RESTRICTIONS.get(k) != v:
            problems.append("restriction %s != %r" % (k, v))

    ok = not problems

    # ---- write tables ------------------------------------------------------
    out_shas = {}
    out_shas["openwhisk_strategy_footprint.csv"] = D.write_csv(
        out_dir / "openwhisk_strategy_footprint.csv", D._cols(footprint), footprint)
    (out_dir / "openwhisk_strategy_footprint.md").write_text(
        render_footprint_md(footprint))
    out_shas["openwhisk_strategy_footprint.md"] = D.sha256_file(
        out_dir / "openwhisk_strategy_footprint.md")
    out_shas["openwhisk_cost_vectors.csv"] = D.write_csv(
        out_dir / "openwhisk_cost_vectors.csv", D._cols(cost_vectors), cost_vectors)
    out_shas["matched_budget_descriptives.csv"] = D.write_csv(
        out_dir / "matched_budget_descriptives.csv", D._cols(matched), matched)

    # ---- write figure sources + SVGs --------------------------------------
    out_shas["figure_source_footprint_vs_delivery.csv"] = D.write_csv(
        out_dir / "figure_source_footprint_vs_delivery.csv", D._cols(fig_a), fig_a)
    out_shas["figure_source_query_vs_delivery.csv"] = D.write_csv(
        out_dir / "figure_source_query_vs_delivery.csv", D._cols(fig_b), fig_b)
    out_shas["figure_source_order_effect.csv"] = D.write_csv(
        out_dir / "figure_source_order_effect.csv", D._cols(fig_c), fig_c)

    svg_a = _svg_scatter(
        [{"strategy": r["strategy"], "x": r["plotted_x_selected_pages"],
          "y": r["plotted_y_deliver_us"]} for r in fig_a],
        "selected pages (log)", "median deliver_us (log)",
        "Figure A -- footprint vs deployment delivery cost",
        "deployment-side; delivery work rises with prefetch footprint; no winner "
        "framing", logx=True, logy=True)
    svg_b = _svg_scatter(
        [{"strategy": r["strategy"], "x": r["plotted_x_deliver_us"],
          "y": r["plotted_y_first_query_us"], "size": r["selected_page_count"]}
         for r in fig_b],
        "median deliver_us (log)", "median first_query_us, query phase (log)",
        "Figure B -- delivery vs query-phase (descriptive, NOT a Pareto frontier)",
        "standalone medians; marker size ~ selected pages; query latency alone is "
        "incomplete", logx=True, logy=True, size_by=True)
    svg_c = _svg_grouped_bars(
        fig_c, "Figure C -- warm order/position effect (validity diagnostic)",
        "position 1 >> position 2 regardless of role/strategy; motivates NOT using "
        "warm pair ratios")

    for fname, svg in (("figure_footprint_vs_delivery.svg", svg_a),
                       ("figure_query_vs_delivery.svg", svg_b),
                       ("figure_order_effect_diagnostic.svg", svg_c)):
        (out_dir / fname).write_text(svg)
        out_shas[fname] = D.sha256_file(out_dir / fname)

    # ---- write prose docs --------------------------------------------------
    (out_dir / "claim_map.md").write_text(render_claim_map_md())
    out_shas["claim_map.md"] = D.sha256_file(out_dir / "claim_map.md")
    # portability facts render the two-role notes/threats; on a fail-closed miss
    # (port is None) fall back to the frozen expected shape so the docs still
    # write (ok is already False), never a crash.
    port_facts = port if port is not None else {
        "invocations": PORT_EXPECTED["invocations"],
        "pairs": PORT_EXPECTED["pairs"],
        "block_pairs": PORT_EXPECTED["block_pairs"],
        "workloads": PORT_EXPECTED["workloads"],
        "workload_families": {}, "distinct_target_plans": 0,
        "parity_type_counts": {}, "matrix_fingerprint": PORT_EXPECTED["matrix_fingerprint"],
        "run_config_sha256": PORT_EXPECTED["run_config_sha256"],
        "source_bundle_sha256": "0" * 64,
    }
    port_ext_facts = port_ext if port_ext is not None else {
        "invocations": PORT_EXT_EXPECTED["invocations"],
        "pairs": PORT_EXT_EXPECTED["pairs"],
        "block_pairs": PORT_EXT_EXPECTED["block_pairs"],
        "workloads": PORT_EXT_EXPECTED["workloads"],
        "workload_families": {}, "distinct_target_plans": 0,
        "parity_type_counts": {},
        "matrix_fingerprint": PORT_EXT_EXPECTED["matrix_fingerprint"],
        "run_config_sha256": PORT_EXT_EXPECTED["run_config_sha256"],
        "source_bundle_sha256": "0" * 64,
    }
    (out_dir / "openwhisk_thesis_notes.md").write_text(
        render_thesis_notes_md(port_facts, port_ext_facts))
    out_shas["openwhisk_thesis_notes.md"] = D.sha256_file(
        out_dir / "openwhisk_thesis_notes.md")
    (out_dir / "threats_to_validity.md").write_text(
        render_threats_md(port_facts, port_ext_facts))
    out_shas["threats_to_validity.md"] = D.sha256_file(
        out_dir / "threats_to_validity.md")

    # ---- validation report -------------------------------------------------
    dm = data["desc_manifest"]
    vlines = [
        "# OpenWhisk thesis synthesis -- validation report", "",
        "overall: %s" % ("PASS" if ok else "FAIL"), "",
        "## source integrity (SHA-verified, fail-closed)",
        "descriptive analysis_manifest git sha: %s"
        % dm.get("analysis_script_git_sha"),
        "normalized_invocations.csv sha256: %s"
        % dm["source"]["normalized_invocations_sha256"],
        "normalized_pairs.csv sha256: %s" % dm["source"]["normalized_pairs_sha256"],
    ]
    for name in DESC_INPUTS:
        vlines.append("descriptive %s sha256: %s" % (name, data["desc_shas"][name]))
    vlines += ["", "## generated table row counts",
               "openwhisk_strategy_footprint.csv: %d" % len(footprint),
               "openwhisk_cost_vectors.csv: %d" % len(cost_vectors),
               "matched_budget_descriptives.csv: %d" % len(matched),
               "figure_source_footprint_vs_delivery.csv: %d" % len(fig_a),
               "figure_source_query_vs_delivery.csv: %d" % len(fig_b),
               "figure_source_order_effect.csv: %d" % len(fig_c),
               "", "## machine-readable claim restrictions"]
    for k, v in sorted(CLAIM_RESTRICTIONS.items()):
        vlines.append("%s = %s" % (k, json.dumps(v)))
    vlines += ["", "## figure formats",
               "svg + figure-source csv emitted (deterministic, dependency-free).",
               "matplotlib PNG/PDF NOT produced here: matplotlib/numpy unavailable "
               "in this analysis host; SVG is vector and publication-usable.",
               "", "## fail-closed problems (%d)" % len(problems)]
    vlines += ["(none)"] if not problems else ["FAIL %s" % p for p in problems]
    vlines.append("")
    (out_dir / "synthesis_validation.txt").write_text("\n".join(vlines) + "\n")
    out_shas["synthesis_validation.txt"] = D.sha256_file(
        out_dir / "synthesis_validation.txt")

    # ---- manifest ----------------------------------------------------------
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "synthesis_script_git_sha": D._git_sha(),
        "ok": ok,
        "purpose": "thesis-facing OpenWhisk synthesis (deployment complement): "
                   "footprint / cost-vector / matched-budget tables + deployment-"
                   "side figures + claim map. No speedup, winner, ranking, Pareto, "
                   "percentage, or significance.",
        "openwhisk_role": "deployment complement to the primary native/WK1 "
                          "controlled performance and mechanism evidence.",
        "source": {
            "normalization_manifest_sha256": D.sha256_file(
                norm_dir / "normalization_manifest.json"),
            "descriptive_analysis_manifest_sha256": D.sha256_file(
                desc_dir / "analysis_manifest.json"),
            "descriptive_analysis_script_git_sha": dm.get("analysis_script_git_sha"),
            "normalized_invocations_sha256":
                dm["source"]["normalized_invocations_sha256"],
            "normalized_pairs_sha256": dm["source"]["normalized_pairs_sha256"],
            "descriptive_inputs": {n: data["desc_shas"][n] for n in DESC_INPUTS},
        },
        "portability_source": {
            # §13 two-role chain: the portability campaign feeds the thesis notes
            # + threats docs, so its provenance is recorded here for audit
            # traceability (SHA-gated in load_portability, fail-closed).
            "portability_present": port is not None,
            "normalization_manifest_sha256": port_facts.get("norm_manifest_sha256"),
            "descriptive_manifest_sha256": port_facts.get("desc_manifest_sha256"),
            "source_bundle_sha256": port_facts.get("source_bundle_sha256"),
            "source_bundle_filename": port_facts.get("source_bundle_filename"),
            "matrix_fingerprint": port_facts.get("matrix_fingerprint"),
            "run_config_sha256": port_facts.get("run_config_sha256"),
            "descriptive_inputs": port_facts.get("desc_shas", {}),
        },
        "portability_ext_source": {
            # §19 fourth campaign: the additive portability-extension chain feeds
            # the four-campaign thesis notes + threats docs; provenance recorded
            # here (SHA-gated in load_portability_ext, fail-closed).
            "portability_ext_present": port_ext is not None,
            "normalization_manifest_sha256":
                port_ext_facts.get("norm_manifest_sha256"),
            "descriptive_manifest_sha256":
                port_ext_facts.get("desc_manifest_sha256"),
            "source_bundle_sha256": port_ext_facts.get("source_bundle_sha256"),
            "source_bundle_filename": port_ext_facts.get("source_bundle_filename"),
            "matrix_fingerprint": port_ext_facts.get("matrix_fingerprint"),
            "run_config_sha256": port_ext_facts.get("run_config_sha256"),
            "descriptive_inputs": port_ext_facts.get("desc_shas", {}),
        },
        "two_role_summary": {
            "strategy_space_formal_invocations": 3600,
            "portability_formal_invocations": port_facts.get("invocations"),
            "portability_ext_formal_invocations": port_ext_facts.get("invocations"),
            "total_formal_invocations": 3600
                + (port_facts.get("invocations") or 0)
                + (port_ext_facts.get("invocations") or 0),
            "campaigns": 4,
            "pooled": False,
            "note": "3600 strategy-space (primary 1600 + secondary 2000) + 468 "
                    "portability + 852 portability-ext = 4920 formal invocations "
                    "across four byte-frozen campaigns answering different "
                    "questions (two roles: strategy-space cost structure, and "
                    "cross-workload deployment portability + its coverage "
                    "extension); NOT pooled into a single effect estimate.",
        },
        "outputs": {k: {"sha256": v} for k, v in sorted(out_shas.items())},
        "figures": {
            "figure_footprint_vs_delivery.svg":
                "figure_source_footprint_vs_delivery.csv",
            "figure_query_vs_delivery.svg":
                "figure_source_query_vs_delivery.csv",
            "figure_order_effect_diagnostic.svg":
                "figure_source_order_effect.csv",
        },
        "figure_formats": ["svg", "csv"],
        "png_pdf_not_produced_reason":
            "matplotlib/numpy unavailable in analysis host; SVG is vector, "
            "publication-usable, and byte-deterministic.",
        "cost_vector_legend": COST_VECTOR_LEGEND,
        "claim_restrictions": CLAIM_RESTRICTIONS,
        "claim_map_counts": {
            cls: sum(1 for e in CLAIM_MAP if e["classification"] == cls)
            for cls in ("SAFE", "QUALIFIED", "DO_NOT_CLAIM")},
        "N_YC": D.COMPARISON_GROUPS["N_YC"],
        "strategy_coverage": D.STRATEGY_ORDER,
    }
    (out_dir / "synthesis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    return ok, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desc-dir", default=str(_DESC_DIR))
    ap.add_argument("--norm-dir", default=str(_NORM_DIR))
    ap.add_argument("--out", default=str(_ANALYSIS_DIR / "thesis"))
    a = ap.parse_args()
    ok, manifest = run(a.desc_dir, a.norm_dir, a.out)
    print("openwhisk thesis synthesis %s: %d artifacts -> %s"
          % ("PASS" if ok else "FAIL", len(manifest["outputs"]), a.out))
    if not ok:
        print("FAILED gates -- see synthesis_validation.txt", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
