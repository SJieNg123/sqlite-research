#!/usr/bin/env python3
"""FULL WORKSTATION MATRIX GAP AUDIT (WK1 planning only).

New research objective (2026-08-28): OpenWhisk portability is scored as CELL-FOR-CELL
coverage of the *full canonical workstation* (workload x strategy) matrix in the declared
portability domain. The workstation set is the DENOMINATOR; any canonical workstation cell
in the portability domain that OpenWhisk has not executed is a WS_ONLY coverage gap.

This module is a deterministic transform (CLAUDE.md Rule 5): the canonical-vs-superseded
JUDGEMENTS are encoded explicitly below with their RESULT_PROVENANCE.md citation, and the
set arithmetic (BOTH / WS_ONLY / OW_ONLY) is computed mechanically. It does NOT run
OpenWhisk, does NOT modify REPORT.md, and does NOT generate final comparison results.

Portability domain (declared):
  * workloads  = the 5 OpenWhisk comparison workloads: YC, YCu, YCh01, C(=C_mixed), C_hit
  * layout     = orig ONLY  (OpenWhisk is pinned to the orig test.db image; vacuum/ta are a
                 separate layout-sensitivity axis -> out of scope)
  * strategies = every NON-baseline strategy the workstation CANONICALLY measured on that
                 workload at orig (baseline is the paired anchor, not a strategy cell)

Canonical source resolution (RESULT_PROVENANCE.md sections cited inline). The OW-executed
set is read live from compare_effectiveness.load_ow() so the audit tracks the real code.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compare_effectiveness as CE  # noqa: E402

OUT_DIR = os.path.join(HERE, "comparison")

# ---------------------------------------------------------------------------
# WS_CANONICAL_MATRIX -- one entry per canonical (workload, strategy) cell in the
# portability domain, with its resolved canonical source and seed protocol.
# Fields: source_batch, seed_protocol, plan_kind (static|keyed), rp_cite.
# ---------------------------------------------------------------------------
H2H = "native_headtohead{,_YCu,_YCh01} summary.csv (per-seed, orig)"

# The uniform 12-strategy head-to-head set shared by YC / YCu / YCh01 (RP not-yet-frozen
# later-additive canonical batch; seeds 1-10 per strategy; baseline = anchor, excluded).
H2H_SET = {
    "2d":                ("structural (workload-invariant sel.)", "static"),
    "layers_5":          ("structural skeleton",                  "static"),
    "layers_92":         ("structural skeleton",                  "static"),
    "2e_K10":            ("seeds 1-10 (keyed plan seed)",         "keyed"),
    "2e_K500":           ("seeds 1-10 (keyed plan seed)",         "keyed"),
    "2f_top14":          ("seeds 1-10 (keyed plan seed)",         "keyed"),
    "2f_top28":          ("seeds 1-10 (keyed plan seed)",         "keyed"),
    "2f_slru":           ("seeds 1-10 (SLRU anchor)",             "keyed"),
    "learned_markov_14": ("LOSO 1-10 (train/test fold)",         "keyed"),
    "learned_markov_28": ("LOSO 1-10 (train/test fold)",         "keyed"),
    "lp_sorted":         ("seeds 1-10 (libprefetch trace)",      "keyed"),
    "lp_shuf":           ("seeds 1-10 (libprefetch trace)",      "keyed"),
}

WS = {}  # (wl, strat) -> dict(source_batch, seed_protocol, plan_kind, rp_cite)

for wl in ("YC", "YCu", "YCh01"):
    for strat, (proto, kind) in H2H_SET.items():
        WS[(wl, strat)] = dict(source_batch=H2H, seed_protocol=proto,
                               plan_kind=kind, rp_cite="later-additive head-to-head")

# C_hit: chit_headtohead is canonical head-to-head (11 strat, no layers_5); c_hit_v2 ADDS
# 2e_K40/2e_K92 ("newly measured here", RP sec.4.2 row 35 / rule 68-69) -- NOT superseded by
# chit_headtohead, which never remeasured them -> both remain canonical targets.
CHIT_SET = {
    "2d":                ("chit_headtohead", "structural",                  "static", "chit_headtohead canonical per-seed"),
    "layers_92":         ("chit_headtohead", "structural skeleton",         "static", "chit_headtohead canonical per-seed"),
    "2e_K10":            ("chit_headtohead", "seeds 1-10",                  "keyed",  "chit_headtohead canonical per-seed"),
    "2e_K500":           ("chit_headtohead", "seeds 1-10",                  "keyed",  "chit_headtohead canonical per-seed"),
    "2e_K40":            ("c_hit_v2",        "seeds 1-10",                  "keyed",  "RP 4.2 row35: newly measured in c_hit_v2"),
    "2e_K92":            ("c_hit_v2",        "seeds 1-10",                  "keyed",  "RP 4.2 row35: newly measured in c_hit_v2"),
    "2f_top14":          ("chit_headtohead", "seeds 1-10",                  "keyed",  "chit_headtohead canonical per-seed"),
    "2f_top28":          ("chit_headtohead", "seeds 1-10",                  "keyed",  "chit_headtohead canonical per-seed"),
    "2f_slru":           ("chit_headtohead", "seeds 1-10 (anchor)",         "keyed",  "chit_headtohead canonical per-seed"),
    "learned_markov_14": ("chit_headtohead", "LOSO 1-10",                   "keyed",  "chit_headtohead canonical per-seed"),
    "learned_markov_28": ("chit_headtohead", "LOSO 1-10",                   "keyed",  "chit_headtohead canonical per-seed"),
    "lp_sorted":         ("chit_headtohead", "seeds 1-10",                  "keyed",  "chit_headtohead canonical per-seed"),
    "lp_shuf":           ("chit_headtohead", "seeds 1-10",                  "keyed",  "chit_headtohead canonical per-seed"),
}
for strat, (src, proto, kind, cite) in CHIT_SET.items():
    WS[("C_hit", strat)] = dict(source_batch=src, seed_protocol=proto, plan_kind=kind, rp_cite=cite)

# C (=C_mixed): union of post-fix canonical sources (RP sec.4.2/4.4/4.8). Atomic-cell rule:
# each cell canonical from its best post-tie-break-fix source.
C_SET = {
    "2d":                ("ablation_comp_v2",     "seeds 1-10",              "static", "RP 4.2: C ablation scope post-fix"),
    "layers_5":          ("seeds",                "seeds 1-10",              "static", "RP 4.8: tie-break-unaffected {2d,layers_5,layers_92}"),
    "layers_92":         ("seeds",                "seeds 1-10",              "static", "RP 4.8: tie-break-unaffected"),
    "2e_K10":            ("ablation_comp_v2",     "seeds 1-10",              "keyed",  "RP 4.2: C ablation scope post-fix"),
    "2e_K40":            ("tiebreak_fix/master",  "single-inst (n=10 reps)", "keyed",  "RP 4.2 row32: corrected single-inst C:K40"),
    "2e_K92":            ("tiebreak_fix/master",  "single-inst (n=10 reps)", "keyed",  "RP 4.2 row32: corrected single-inst C:K92"),
    "2e_K500":           ("unified_v2/matrix",    "single-inst (n=10 reps)", "keyed",  "RP 4.4: C 2e_K500 NOT in tie-break changed set -> unchanged cell -> unified_v2"),
    "2f_top14":          ("ablation_comp_v2",     "seeds 1-10",              "keyed",  "RP 4.2: C ablation scope post-fix"),
    "2f_top28":          ("ablation_comp_v2",     "seeds 1-10",              "keyed",  "RP 4.2: C ablation scope post-fix"),
    "2f_slru":           ("ablation_comp_v2",     "seeds 1-10 (anchor)",     "keyed",  "RP 4.2: C ablation scope post-fix"),
    "leaf_freq_K10":     ("ablation_comp_v2",     "seeds 1-10",              "keyed",  "RP 4.2: C ablation scope post-fix"),
    "leaf_rand_K10":     ("ablation_comp_v2",     "seeds 1-10",              "keyed",  "RP 4.2: C ablation scope post-fix"),
    "learned_markov_14": ("learned_10fold",       "LOSO 1-10",               "keyed",  "RP: learned_10fold supersedes single-fold"),
    "learned_markov_28": ("learned_10fold",       "LOSO 1-10",               "keyed",  "RP: learned_10fold supersedes single-fold"),
    "lp_sorted":         ("baselines_v2",         "test seed 1 only",        "keyed",  "RP 4.2: baselines_v2 prior-art (single test seed)"),
    "lp_shuf":           ("baselines_v2",         "test seed 1 only",        "keyed",  "RP 4.2: baselines_v2 prior-art (single test seed)"),
}
for strat, (src, proto, kind, cite) in C_SET.items():
    WS[("C", strat)] = dict(source_batch=src, seed_protocol=proto, plan_kind=kind, rp_cite=cite)

# ---------------------------------------------------------------------------
# OW_EXECUTED_MATRIX -- read live from the analysis module.
# ---------------------------------------------------------------------------
OW_RAW = CE.load_ow()
OW = {(wl, st) for (wl, st) in OW_RAW.keys()}
WS_CELLS = set(WS.keys())

BOTH = WS_CELLS & OW
WS_ONLY = WS_CELLS - OW
OW_ONLY = OW - WS_CELLS

# ---------------------------------------------------------------------------
# PLANNED full-closure target (WK1 planning only). The fifth OpenWhisk campaign
# (portability_full_closure) is DESIGNED to close every WS_ONLY gap. Its planned
# (workload, strategy) cells are DERIVED from the closure matrix (blocks B12-B17),
# NOT hard-coded, so this assertion tracks the real campaign. This is the PLAN, not
# executed coverage: BOTH above stays live from compare_effectiveness.load_ow() and
# only becomes 65 AFTER WK2 evidence is archived + audited (§11). ------------------
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import portability_full_closure_manifest as FC  # noqa: E402

_WID_TO_AUDIT = {
    "native_ycsb_c_read_zipf": "YC",
    "native_ycsb_c_read_uniform": "YCu",
    "native_ycsb_c_hot_hashed_01": "YCh01",
    "read_tail_hit_20k": "C_hit",
    "read_tail_mixed_20k": "C",
}


def planned_closure_target():
    """The (workload, strategy) cells the closure campaign will execute, read from
    FC.MATRICES_CLOSURE (baseline anchor excluded)."""
    cells = set()
    for mx in FC.MATRICES_CLOSURE:
        for wid in mx["workloads"]:
            wl = _WID_TO_AUDIT[wid]
            for st in mx["strategies"]:
                if st != "baseline":
                    cells.add((wl, st))
    return cells


PLANNED_CLOSURE = planned_closure_target()
# The closure campaign is EXECUTED once its evidence is archived and included in
# compare_effectiveness.load_ow() -- at which point every WS_ONLY gap becomes BOTH and
# WS_ONLY is empty. This audit is state-aware and fails loud (CLAUDE.md Rule 12) in BOTH
# states. (§2 recompute is BIDIRECTIONAL: BOTH/WS_ONLY/OW_ONLY are computed mechanically
# above; the expected post-closure shape 65/0/4 is asserted here, not hard-coded upstream.)
CLOSURE_EXECUTED = len(WS_ONLY) == 0
if CLOSURE_EXECUTED:
    # POST-EXECUTION: the 16 closure target cells must now ALL be in the executed BOTH set,
    # the WS matrix must be fully covered, and no WS_ONLY gap may remain.
    _NOT_COVERED = PLANNED_CLOSURE - BOTH
    if _NOT_COVERED:
        sys.exit("closure target cells missing from executed BOTH: %s" % sorted(_NOT_COVERED))
    if BOTH != WS_CELLS:
        sys.exit("post-closure executed BOTH != full 65-cell WS matrix")
    if WS_ONLY:
        sys.exit("post-closure WS_ONLY must be empty: %s" % sorted(WS_ONLY))
else:
    # PRE-EXECUTION (WK1 planning): the campaign must target EXACTLY the current WS_ONLY
    # gap -- no more (would touch a frozen cell), no less (would leave a gap).
    _PLANNED_EXTRA = PLANNED_CLOSURE - WS_ONLY
    _PLANNED_MISSING = WS_ONLY - PLANNED_CLOSURE
    if _PLANNED_EXTRA:
        sys.exit("planned closure targets cells that are not WS_ONLY gaps: %s"
                 % sorted(_PLANNED_EXTRA))
    if _PLANNED_MISSING:
        sys.exit("planned closure leaves WS_ONLY gaps uncovered: %s" % sorted(_PLANNED_MISSING))
    if (BOTH | PLANNED_CLOSURE) != WS_CELLS:
        sys.exit("BOTH union planned-closure != full 65-cell matrix")

# portability class for each WS_ONLY cell (does the mechanism already exist in the OW action?)
OW_ACTION_HAS = {"2d", "2e_K10", "2e_K500", "2f_top14", "2f_top28", "2f_slru",
                 "layers_5", "layers_92", "learned_markov_14", "learned_markov_28",
                 "leaf_freq_K10", "leaf_rand_K10"}  # strategies OW has already dispatched


def portability_class(strat, kind):
    if strat in ("lp_sorted", "lp_shuf"):
        return "MECHANISM-QUESTIONABLE (libprefetch readahead; inject-model portability decision required)"
    if strat in OW_ACTION_HAS:
        if kind == "static":
            return "PORTABLE-STATIC (action supports; no new frozen plan)"
        return "PORTABLE-KEYED (action supports; needs new frozen per-seed plans)"
    return "PORTABLE-KEYED-NEWBUDGET (2e interior-union supported; needs new frozen plans)"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    order = ["YC", "YCu", "YCh01", "C", "C_hit"]

    # ---- workstation_canonical_matrix.csv (one row per canonical target cell) ----
    path1 = os.path.join(OUT_DIR, "workstation_canonical_matrix.csv")
    fields = ["workload", "strategy", "layout", "canonical_source", "seed_protocol",
              "plan_kind", "in_openwhisk", "ow_coverage", "portability_class", "rp_cite"]
    with open(path1, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for wl in order:
            for (cwl, strat) in sorted(WS_CELLS):
                if cwl != wl:
                    continue
                m = WS[(wl, strat)]
                inow = (wl, strat) in OW
                w.writerow(dict(
                    workload=wl, strategy=strat, layout="orig",
                    canonical_source=m["source_batch"], seed_protocol=m["seed_protocol"],
                    plan_kind=m["plan_kind"],
                    in_openwhisk=str(inow),
                    ow_coverage="BOTH" if inow else "WS_ONLY",
                    portability_class=("covered" if inow else portability_class(strat, m["plan_kind"])),
                    rp_cite=m["rp_cite"]))

    # ---- audit summary to stdout ----
    def by_wl(cells):
        d = {}
        for (wl, st) in cells:
            d.setdefault(wl, []).append(st)
        return d

    print("=" * 72)
    print("FULL WORKSTATION MATRIX GAP AUDIT  (portability domain = 5 wl x orig)")
    print("=" * 72)
    print(f"Total canonical WS portability cells : {len(WS_CELLS)}")
    print(f"BOTH (intersection)                  : {len(BOTH)}")
    print(f"WS_ONLY (coverage gaps)              : {len(WS_ONLY)}")
    print(f"OW_ONLY (OW extra, no WS head-to-head): {len(OW_ONLY)}")
    print()
    print("Per-workload  [WS_canon | BOTH | WS_ONLY | OW_ONLY]")
    for wl in order:
        wsn = sum(1 for (w, _) in WS_CELLS if w == wl)
        bn = sum(1 for (w, _) in BOTH if w == wl)
        won = sum(1 for (w, _) in WS_ONLY if w == wl)
        oon = sum(1 for (w, _) in OW_ONLY if w == wl)
        print(f"  {wl:6s}  {wsn:3d} | {bn:3d} | {won:3d} | {oon:3d}")
    print()
    print("COMPLETE WS_ONLY LIST (the gap):")
    for wl in order:
        sts = sorted(st for (w, st) in WS_ONLY if w == wl)
        for st in sts:
            m = WS[(wl, st)]
            print(f"  {wl:6s} {st:20s} [{m['plan_kind']:6s}] {m['seed_protocol']:26s} "
                  f"src={m['source_batch']}")
    print()
    print("OW_ONLY LIST (exclude from WS denominator; no WS head-to-head):")
    for (wl, st) in sorted(OW_ONLY):
        print(f"  {wl:6s} {st}")

    # WS_ONLY breakdown
    print()
    print("WS_ONLY breakdown by strategy family:")
    fam = {}
    for (wl, st) in WS_ONLY:
        fam.setdefault(st, []).append(wl)
    for st in sorted(fam):
        print(f"  {st:20s} x{len(fam[st])}  -> {sorted(fam[st])}")

    print()
    if CLOSURE_EXECUTED:
        print("FULL-CLOSURE CAMPAIGN (portability_full_closure): EXECUTED + INCLUDED")
        print(f"  closure target cells                 : {len(PLANNED_CLOSURE)}")
        print(f"  all closure cells in executed BOTH   : {PLANNED_CLOSURE <= BOTH}")
        print(f"  executed BOTH now                    : {len(BOTH)}/65")
        print(f"  WS_ONLY remaining                    : {len(WS_ONLY)}")
        print(f"  OW_ONLY (reported separately)        : {len(OW_ONLY)}")
        print("  CLAIM: every canonical retained WS workload x strategy cell at orig layout")
        print("         now has OpenWhisk CELL coverage (not protocol/layout/perf equivalence)")
    else:
        print("PLANNED FULL-CLOSURE TARGET (campaign portability_full_closure, WK1 plan):")
        print(f"  planned target cells                 : {len(PLANNED_CLOSURE)}")
        print(f"  == current WS_ONLY gap               : {PLANNED_CLOSURE == WS_ONLY}")
        print(f"  executed BOTH now                    : {len(BOTH)}/65 (unchanged until WK2)")
        print(f"  BOTH u planned-closure               : {len(BOTH | PLANNED_CLOSURE)}/65")
        print(f"  remaining planned WS_ONLY            : {len(WS_ONLY - PLANNED_CLOSURE)}")
    print()
    print(f"wrote {path1}")
    return dict(total=len(WS_CELLS), both=len(BOTH), ws_only=len(WS_ONLY),
                ow_only=len(OW_ONLY), ws_only_cells=sorted(WS_ONLY),
                ow_only_cells=sorted(OW_ONLY),
                planned_closure=sorted(PLANNED_CLOSURE),
                both_union_planned=len(BOTH | PLANNED_CLOSURE))


if __name__ == "__main__":
    main()
