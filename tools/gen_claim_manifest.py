#!/usr/bin/env python3
"""Generate docs/audits/PAPER_CLAIM_MANIFEST.csv (Phase 4).

Displayed values are transcribed from paper/main.tex (the source of truth for
what is PRINTED); the verifier independently recomputes from the canonical CSVs.
Machine-checkable result claims carry a `formula` + `source_filter`; structural /
cited / qualitative claims are documented (formula=manual/qual).
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/audits/PAPER_CLAIM_MANIFEST.csv"

COLS = ["claim_id", "tex_line_or_section", "quoted_claim", "claim_kind", "workload",
        "layout", "strategy", "metric", "deployment_model", "single_or_cross_seed",
        "aggregation", "displayed_value", "canonical_source", "baseline_source",
        "anchor_source", "source_filter", "source_raw_value", "formula",
        "rounding_rule", "atomic_status", "narrative_scope_status", "action",
        "notes", "compare_group"]

UNI = "results/unified_v2/matrix/summary.csv"
TB = "results/tiebreak_fix/master_summary.csv"
ABL = "results/ablation_comp_v2/uncertainty.csv"
COMP = "results/competitive/uncertainty.csv"
CHIT = "results/c_hit/uncertainty.csv"
CHIT2 = "results/c_hit_v2/uncertainty.csv"
TBU = "results/tiebreak_fix/uncertainty.csv"
SEEDS = "results/seeds/seed*/summary.csv"
TBSEEDS = "results/tiebreak_fix/seeds/seed*/summary.csv"
AGE = "results/aging_v2/aging_ci.csv"

rows = []
_n = [0]


def add(line, quote, kind, w, ly, s, metric, dep, scope, agg, disp, src, base, anchor,
        filt, raw, formula, rnd, atomic, narr, action, notes, grp=""):
    _n[0] += 1
    rows.append({
        "claim_id": f"Q{_n[0]:03d}", "tex_line_or_section": line, "quoted_claim": quote,
        "claim_kind": kind, "workload": w, "layout": ly, "strategy": s, "metric": metric,
        "deployment_model": dep, "single_or_cross_seed": scope, "aggregation": agg,
        "displayed_value": disp, "canonical_source": src, "baseline_source": base,
        "anchor_source": anchor, "source_filter": filt, "source_raw_value": raw,
        "formula": formula, "rounding_rule": rnd, "atomic_status": atomic,
        "narrative_scope_status": narr, "action": action, "notes": notes, "compare_group": grp})


def sf(w, s, arm="async", db="orig", metric=None):
    f = f"workload={w};db={db};strategy={s};arm={arm}"
    if metric:
        f += f";metric={metric}"
    return f


# ---- machine-checkable result claims ----------------------------------------
# baseline first-query (unified_v2), appears in §2/§3/§7/§8, tab:e2e-ac header
for w, disp in [("A", "523"), ("B", "749"), ("C_mixed", "1087")]:
    ww = "C" if w == "C_mixed" else w
    add("101,212,241,448,454,518", f"baseline first-query {disp} us", "abs_latency",
        w, "orig", "baseline", "first_query", "n/a", "single", "median", disp,
        UNI, UNI, "n/a", sf(ww, "baseline", "baseline"), "fq_median", "abs:fq_median",
        "int", "OK", "unaffected main-matrix", "verified", "canonical baseline")

# 2f_slru first-query abs + reduction
for w, absv, red in [("A", "108", "-79"), ("B", "107", "-86"), ("C_mixed", "102", "-91")]:
    ww = "C" if w == "C_mixed" else w
    add("454", f"2f_slru first-query {absv} us", "abs_latency", w, "orig", "2f_slru",
        "first_query", "n/a", "single", "median", absv, UNI, UNI, "n/a",
        sf(ww, "2f_slru"), "fq_median", "abs:fq_median", "int", "OK",
        "unaffected", "verified", "")
    add("454,467,478", f"2f_slru first-query reduction {red}%", "rel_improvement", w,
        "orig", "2f_slru", "first_query", "n/a", "single", "paired-vs-same-batch-baseline",
        red, UNI, UNI, "n/a", sf(ww, "2f_slru"), "fq_median", "rel:fq_median", "int",
        "OK", "-79 to -91 span", "verified", "")

# first-query ceilings (2d interior), unaffected
for w, disp in [("A", "-30"), ("B", "-44"), ("C_mixed", "-39")]:
    ww = "C" if w == "C_mixed" else w
    add("456,467", f"interior-only first-query ceiling {disp}%", "rel_improvement", w,
        "orig", "2d", "first_query", "n/a", "single", "paired", disp, UNI, UNI, "n/a",
        sf(ww, "2d"), "fq_median", "rel:fq_median", "int", "OK", "ceiling", "verified", "")

# A 2e_K500 first-query -64 (CHANGED -> tiebreak); C 2e_K10 first-query -83 (CHANGED)
add("456,467", "2e_K500 first-query -64% (A)", "rel_improvement", "A", "orig", "2e_K500",
    "first_query", "n/a", "single", "paired", "-64", TB, TB, "n/a", sf("A", "2e_K500"),
    "fq_median", "rel:fq_median", "int", "OK", "changed->tiebreak", "verified", "")
add("456,469,485", "2e_K10 first-query -83% (C_mixed)", "rel_improvement", "C_mixed", "orig",
    "2e_K10", "first_query", "n/a", "single", "paired", "-83", TB, TB, "n/a",
    sf("C", "2e_K10"), "fq_median", "rel:fq_median", "int", "OK", "changed->tiebreak",
    "verified", "")

# ---- tab:e2e-ac (unified_v2 single batch, compare_group=e2e-ac) --------------
E2E = [("A", "layers_5", "679", "+30", "453", "-14"),
       ("A", "2d", "678", "+30", "452", "-14"),
       ("A", "2f_slru", "7552", "+1343", "7324", "+1300"),
       ("C", "layers_5", "1352", "+24", "1120", "+3"),
       ("C", "2d", "969", "-11", "735", "-32"),
       ("C", "2f_slru", "1196", "+10", "962", "-12")]
for w, s, sstd, pstd, swarm, pwarm in E2E:
    wl = "C_mixed" if w == "C" else w
    add("521-524", f"tab:e2e-ac {w} {s} std {sstd} ({pstd}%)", "abs_latency", wl, "orig", s,
        "e2e_std", "standalone", "single", "median", sstd, UNI, UNI, "n/a", sf(w, s),
        "e2e_median", "abs:e2e_median", "int", "OK", "unaffected single-batch", "verified",
        "", "e2e-ac")
    add("521-524", f"tab:e2e-ac {w} {s} std {pstd}%", "rel_improvement", wl, "orig", s,
        "e2e_std", "standalone", "single", "paired", pstd, UNI, UNI, "n/a", sf(w, s),
        "e2e_median", "rel:e2e_median", "int", "OK", "", "verified", "", "")
    add("521-524", f"tab:e2e-ac {w} {s} warm {swarm} ({pwarm}%)", "abs_latency", wl, "orig", s,
        "e2e_warm", "warm-process", "single", "median", swarm, UNI, UNI, "n/a", sf(w, s),
        "e2e_warm_median", "abs:e2e_warm_median", "int", "OK", "unaffected single-batch",
        "verified", "", "e2e-ac")
    add("521-524", f"tab:e2e-ac {w} {s} warm {pwarm}%", "rel_improvement", wl, "orig", s,
        "e2e_warm", "warm-process", "single", "paired", pwarm, UNI, UNI, "n/a", sf(w, s),
        "e2e_warm_median", "rel:e2e_warm_median", "int", "OK", "", "verified", "", "")

# ---- tab:corrected-arms (tiebreak single batch, compare_group=corrected-arms)
add("537", "A 2e_K500 corrected 512->1079 +111%", "abs_latency", "A", "orig", "2e_K500",
    "e2e_warm", "warm-process", "single", "median", "1079", TB, TB, "n/a", sf("A", "2e_K500"),
    "e2e_warm_median", "abs:e2e_warm_median", "int", "OK", "corrected same-batch", "verified",
    "", "corrected-arms")
add("537", "A 2e_K500 corrected +111%", "rel_improvement", "A", "orig", "2e_K500", "e2e_warm",
    "warm-process", "single", "paired", "+111", TB, TB, "n/a", sf("A", "2e_K500"),
    "e2e_warm_median", "rel:e2e_warm_median", "int", "OK", "over-provisioned leaf", "verified", "")
add("538,548", "C_mixed 2e_K10 corrected 1071->265 -75%", "abs_latency", "C_mixed", "orig",
    "2e_K10", "e2e_warm", "warm-process", "single", "median", "265", TB, TB, "n/a",
    sf("C", "2e_K10"), "e2e_warm_median", "abs:e2e_warm_median", "int", "OK",
    "corrected same-batch; single-inst", "verified", "seed-1 scoped", "corrected-arms")
add("538,548", "C_mixed 2e_K10 corrected -75% single-inst", "rel_improvement", "C_mixed",
    "orig", "2e_K10", "e2e_warm", "warm-process", "single", "paired", "-75", TB, TB, "n/a",
    sf("C", "2e_K10"), "e2e_warm_median", "rel:e2e_warm_median", "int", "single-inst only",
    "OK", "verified", "cross-seed -55 separate")

# ---- tab:ablation (ablation_comp_v2, C_mixed x orig) ------------------------
ABLROWS = [("2d", "-43", "-46", "-41", "-36"),
           ("leaf_rand_K10", "-1", "-2", "1", "7"),
           ("leaf_freq_K10", "-11", "-22", "0", "-3"),
           ("2e_K10", "-63", "-75", "-51", "-55")]
for s, fq, lo, hi, warm in ABLROWS:
    add("583-586", f"ablation {s} fq {fq}% [{lo},{hi}]", "conf_interval", "C_mixed", "orig", s,
        "first_query", "n/a", "cross", "10-seed bootstrap", fq, ABL, ABL, "n/a",
        sf("C", s, metric="first_query_us"), "mean_pct", "umean", "int", "OK",
        "C_mixed ablation", "verified", "")
    add("583-586", f"ablation {s} fq CI [{lo},{hi}]", "conf_interval", "C_mixed", "orig", s,
        "first_query", "n/a", "cross", "10-seed bootstrap", f"[{lo},{hi}]", ABL, ABL, "n/a",
        sf("C", s, metric="first_query_us"), "ci", "uci", "int", "OK", "", "verified", "")
    add("583-586", f"ablation {s} warm {warm}%", "rel_improvement", "C_mixed", "orig", s,
        "e2e_warm", "warm-process", "cross", "10-seed bootstrap", warm, ABL, ABL, "n/a",
        sf("C", s, metric="e2e_warm_us"), "mean_pct", "umean", "int", "OK", "", "verified", "")

# ---- tab:competitive --------------------------------------------------------
# A/B columns: results/competitive; C column: ablation_comp_v2 (except 2f_top500 = competitive)
COMPROWS = [
    ("2e_K10", [("A", COMP, "-38", "-53", "-25"), ("B", COMP, "-24", "-31", "-12"), ("C", ABL, "-55", "-67", "-42")]),
    ("2f_top14", [("A", COMP, "-33", "-43", "-24"), ("B", COMP, "-27", "-34", "-16"), ("C", ABL, "-55", "-67", "-43")]),
    ("2f_top500", [("A", COMP, "81", "34", "151"), ("B", COMP, "44", "28", "60"), ("C", COMP, "-13", "-17", "-8")]),
    ("2f_slru", [("A", COMP, "762", "674", "899"), ("B", COMP, "730", "644", "848"), ("C", ABL, "-7", "-12", "-2")]),
]
for s, cells in COMPROWS:
    for w, src, mean, lo, hi in cells:
        wl = "C_mixed" if w == "C" else w
        add("618-621", f"competitive {s} {w} {mean}% [{lo},{hi}]", "conf_interval", wl, "orig",
            s, "e2e_warm", "warm-process", "cross", "10-seed bootstrap", mean, src, src, "n/a",
            sf(w, s, metric="e2e_warm_us"), "mean_pct", "umean", "int",
            "A/B independent batch relative-only; C corrected", "OK", "verified",
            "per-row source split")
        add("618-621", f"competitive {s} {w} CI [{lo},{hi}]", "conf_interval", wl, "orig", s,
            "e2e_warm", "warm-process", "cross", "10-seed bootstrap", f"[{lo},{hi}]", src, src,
            "n/a", sf(w, s, metric="e2e_warm_us"), "ci", "uci", "int", "OK", "", "verified", "")

# ---- tab:seeds single-workload column --------------------------------------
# single-inst: unaffected -> unified; changed (B 2e_K10, C 2e_K10) -> tiebreak
SEEDS_SINGLE = [("C", "2e_K10", "-75", TB), ("C", "2d", "-32", UNI), ("A", "2e_K10", "-11", UNI),
                ("A", "2d", "-14", UNI), ("B", "2d", "-32", UNI), ("B", "2e_K10", "-30", TB),
                ("A", "layers_5", "-14", UNI), ("B", "layers_5", "-34", UNI)]
# Phase 4 fix: B 2e_K10 single-workload was -29 (superseded unified); corrected to
# -30 (tiebreak) since B 2e_K10 is a changed cell. Now matches the paper.
for w, s, disp, src in SEEDS_SINGLE:
    wl = "C_mixed" if w == "C" else w
    note = "changed->tiebreak (Phase4 fix -29->-30)" if src == TB and s == "2e_K10" else (
        "changed->tiebreak" if src == TB else "unaffected unified")
    add("645-652", f"tab:seeds {w} {s} single-workload {disp}%", "rel_improvement", wl, "orig",
        s, "e2e_warm", "warm-process", "single", "paired", disp, src, src, "n/a", sf(w, s),
        "e2e_warm_median", "rel:e2e_warm_median", "int", "OK", "single-inst column", "verified",
        note)

# ---- tab:seeds cross-seed means (per-seed paired aggregation) ----------------
# changed -> tiebreak seeds; unaffected -> results/seeds
SEEDS_CROSS = [("C", "2e_K10", "-55", TBSEEDS, "changed"), ("C", "2d", "-36", SEEDS, "unaff"),
               ("A", "2e_K10", "-36", SEEDS, "unaff"), ("A", "2d", "-25", SEEDS, "unaff"),
               ("B", "2d", "-25", SEEDS, "unaff"), ("B", "2e_K10", "-25", TBSEEDS, "changed"),
               ("A", "layers_5", "-5", SEEDS, "unaff"), ("B", "layers_5", "-1", SEEDS, "unaff")]
for w, s, disp, glob, tag in SEEDS_CROSS:
    wl = "C_mixed" if w == "C" else w
    add("645-652", f"tab:seeds {w} {s} cross-seed mean {disp}%", "rel_improvement", wl, "orig",
        s, "e2e_warm", "warm-process", "cross", "per-seed paired 10-seed mean", disp, glob, glob,
        "n/a", sf(w, s), "e2e_warm_median", f"seeds_mean:{glob}:e2e_warm_median", "int", "OK",
        "cross-seed column; per-seed paired", "verified", tag)

# cross-seed CIs that HAVE a canonical uncertainty file (tiebreak / ablation_comp_v2)
add("645", "tab:seeds C 2e_K10 cross CI [-67,-43]", "conf_interval", "C_mixed", "orig",
    "2e_K10", "e2e_warm", "warm-process", "cross", "bootstrap 95% CI", "[-67,-43]", TBU, TBU,
    "n/a", sf("C", "2e_K10", metric="e2e_warm_us"), "ci", "uci", "int", "OK", "", "verified", "")
add("650", "tab:seeds B 2e_K10 cross CI [-32,-15]", "conf_interval", "B", "orig", "2e_K10",
    "e2e_warm", "warm-process", "cross", "bootstrap 95% CI", "[-32,-15]", TBU, TBU, "n/a",
    sf("B", "2e_K10", metric="e2e_warm_us"), "ci", "uci", "int", "OK", "", "verified", "")

# ---- C_hit control ---------------------------------------------------------
add("606", "C_hit 2e_K10 ~-27%", "rel_improvement", "C_hit", "orig", "2e_K10", "e2e_warm",
    "warm-process", "cross", "10-seed bootstrap", "-27", CHIT2, CHIT2, "n/a",
    sf("C_hit", "2e_K10", metric="e2e_warm_us"), "mean_pct", "umean", "int", "OK",
    "C_hit corrected -> c_hit_v2; orig-only", "verified", "")
add("606", "C_hit 2d -28.5%", "rel_improvement", "C_hit", "orig", "2d", "e2e_warm",
    "warm-process", "cross", "10-seed bootstrap", "-28.5", CHIT, CHIT, "n/a",
    sf("C_hit", "2d", metric="e2e_warm_us"), "mean_pct", "umean", "round1", "OK",
    "C_hit unaffected -> c_hit; orig-only", "verified", "")
add("606", "C_hit 2f_top14 -30.6%", "rel_improvement", "C_hit", "orig", "2f_top14", "e2e_warm",
    "warm-process", "cross", "10-seed bootstrap", "-30.6", CHIT, CHIT, "n/a",
    sf("C_hit", "2f_top14", metric="e2e_warm_us"), "mean_pct", "umean", "round1", "OK",
    "orig-only", "verified", "")
add("606", "C_hit learned -29.0%", "rel_improvement", "C_hit", "orig", "learned_markov_14",
    "e2e_warm", "warm-process", "cross", "10-seed bootstrap", "-29.0", CHIT, CHIT, "n/a",
    sf("C_hit", "learned_markov_14", metric="e2e_warm_us"), "mean_pct", "umean", "round1", "OK",
    "orig-only", "verified", "")

# ---- aging (aging_v2) ------------------------------------------------------
for w, s, ck, disp in [("YD", "2e_K10_static", "0", "-50"), ("YD", "2e_K10_static", "10", "-33"),
                       ("YD", "layers_92_static", "0", "-53"), ("YD", "layers_92_static", "10", "-53"),
                       ("YE", "2e_K10_static", "0", "-53"), ("YE", "2e_K10_static", "10", "-55"),
                       ("YE", "layers_92_static", "0", "-53"), ("YE", "layers_92_static", "10", "-51")]:
    add("674", f"aging {w} {s} ck{ck} {disp}% vs baseline", "rel_improvement", w, "orig", s,
        "first_query", "n/a", "cross", "10-seed mean vs same-ck baseline", disp, AGE, AGE, "n/a",
        f"workload={w};strategy={s}", "mean_us", f"aging_red:{ck}", "int", "OK",
        "stationarity-dependent", "verified", "")

# ---- layout comparison (line 630) ------------------------------------------
add("630", "layout A orig 2d 452 us", "abs_latency", "A", "orig", "2d", "e2e_warm",
    "warm-process", "single", "median", "452", UNI, UNI, "n/a", sf("A", "2d"),
    "e2e_warm_median", "abs:e2e_warm_median", "int", "OK", "same-batch per-workload pair",
    "verified", "")
add("630", "layout B orig 2d 509 us", "abs_latency", "B", "orig", "2d", "e2e_warm",
    "warm-process", "single", "median", "509", UNI, UNI, "n/a", sf("B", "2d"),
    "e2e_warm_median", "abs:e2e_warm_median", "int", "OK", "", "verified", "")
add("630", "layout C_mixed orig 2e_K10 265 us", "abs_latency", "C_mixed", "orig", "2e_K10",
    "e2e_warm", "warm-process", "single", "median", "265", TB, TB, "n/a", sf("C", "2e_K10"),
    "e2e_warm_median", "abs:e2e_warm_median", "int", "OK", "corrected batch", "verified", "")

# ---- documented (structural / cited / qualitative / range) ------------------
# These are inventoried for completeness; not recomputed from our result CSVs.
DOC = [
    ("52,121,129,718", "2d warm e2e roughly 25-30% (headline range)", "range", "all", "2d",
     "e2e_warm", "summary of tab:seeds/C_hit A-25 B-25 Chit-28.5", "derived from cross-seed"),
    ("52,718", "2f_slru deliver 0.8 to 7 ms", "range", "all", "2f_slru", "deliver",
     "tab:overhead deliver range", "range"),
    ("52", "A -25% to -36% skew bonus", "range", "A", "2d/2e_K10", "e2e_warm",
     "tab:seeds A 2d -25, 2e_K10 -36", "derived"),
    ("206,208,359,422", "92 interior pages (51 table + 41 index), 368 KB, 0.35%", "count_footprint",
     "n/a", "interior", "n/a", "fixed DB structure (classify_pages)", "structural"),
    ("206,422", "600,000 rows, 102 MB, 4 KB pages, 26,239 leaf", "count_footprint", "n/a",
     "n/a", "n/a", "fixed reference DB", "structural"),
    ("373,385,608", "hotset sizes ~112 KB K10, ~2 MB K500, 17.7 MB / 1.8 MB 2f_slru",
     "count_footprint", "n/a", "2e_K/2f_slru", "n/a", "measured footprint (strategy design)",
     "structural"),
    ("444", "workload A Zipfian alpha=0.99; 100,000 ops; 600,000 keys", "workload_property",
     "A", "n/a", "n/a", "gen_workload.py config", "workload-property"),
    ("436,444,456,606,718", "C_mixed ~50% not-found (upper half beyond max id)",
     "workload_property", "C_mixed", "n/a", "n/a", "C_mixed key-range definition", "scope-critical"),
    ("505,509", "open canonical median ~230 us; tab:overhead 193-222 independent batch",
     "abs_latency", "n/a", "open", "open", "raw.csv per-rep median 231.6 (Phase 2.6)",
     "verified-elsewhere"),
    ("606", "C_mixed 2e_K10 bimodal ~-70% miss / ~-31% hit", "qualitative_compare", "C_mixed",
     "2e_K10", "e2e_warm", "per-seed bimodality (ablation_comp_v2 per_seed)", "qualitative"),
    ("624,610", "2e_K10 and 2f_top14 statistically indistinguishable on C", "qualitative_compare",
     "C_mixed", "2e_K10/2f_top14", "e2e_warm", "overlapping CIs (ablation_comp_v2)", "qualitative"),
    ("157,161", "libprefetch up to 20x scans, 4.9x GIMP, ~500 LOC (cited)", "ratio", "n/a",
     "libprefetch", "n/a", "VanDeBogart+09 (cited)", "cited"),
    ("89,93,147,173", "related-work cited magnitudes (trillion DBs, 76-87%, 79% TLB)",
     "workload_property", "n/a", "n/a", "n/a", "cited prior work", "cited"),
    ("672,277", "churn 50k mutations: within-batch checkpoint flatness under a stationary read hotspot; C 2e_K10 ~82-89us vs ~580us baseline are PRE-FIX diagnostic absolute values, not a corrected 2e_K10 magnitude; allowed conclusion = checkpoint flatness only",
     "qualitative_compare", "D", "2e_K10", "first_query",
     "churn batch predates the trace-order-independent tie-break fix; within-batch flatness only; NOT a corrected selector effect magnitude",
     "prefix-diagnostic-within-batch"),
    ("676", "cadence 1s/5s -> 26/29 us; 30s/never -> 281-305 us", "abs_latency", "n/a",
     "shared_cadence", "first_query", "results/cadence (multiprocess axis)", "other-axis"),
    ("663,668", "RAM sweep: targeted <=2MB 100% delivery; 2f_slru collapses (seed-1)",
     "figure_stmt", "A_B", "2f_slru/targeted", "delivery_pct", "results/ram_pressure seed-1",
     "seed-1-scoped"),
    ("678", "size 1GiB: 2f_slru -9->+139, 2e_K500 -31->+35; 2e_K10 -70/-68 PRE-FIX diagnostic",
     "rel_improvement", "C", "2f_slru/2e_K500/2e_K10", "e2e_warm",
     "results size batch; 2e_K10 magnitude pre-fix", "diagnostic-labeled"),
    ("720", "novelty: to our knowledge first to quantify first-query vs end-to-end trade-off in SQLite serverless cold starts at OS-syscall granularity (hedged; internal pending-literature parenthetical removed from paper)",
     "qualitative_compare", "n/a", "n/a", "n/a",
     "hedged novelty claim; no measured superiority; literature-review limitation retained in internal audit docs only, not stated as a TODO in paper text",
     "hedged-novelty"),
    ("125,129,720", "FaaS deployment-compatibility: application-layer only, standard OS interfaces, no root / no kernel / no SQLite modification, therefore compatible with FaaS execution constraints",
     "qualitative_compare", "n/a", "n/a", "n/a",
     "mechanism / deployment-compatibility claim only; does NOT imply a measured OpenWhisk/production-FaaS deployment result",
     "deployment-compatibility-not-measured"),
    ("706", "limitation: direct FaaS-runtime validation is not included in the current evaluation; an OpenWhisk deployment is the immediate next experiment for testing whether the locally observed strategy ordering carries over",
     "qualitative_compare", "n/a", "n/a", "n/a",
     "current-state limitation; no FaaS-runtime / OpenWhisk result exists yet; 'immediate next' now stated once in Limitations",
     "openwhisk-pending"),
    ("706", "cross-platform scope: the cost-accounting methodology is intended to transfer to platforms sharing the same warm-process, cold-data model; whether the relative ordering of strategies carries over is an untested empirical question that the OpenWhisk validation will test",
     "qualitative_compare", "n/a", "n/a", "n/a",
     "the prior 'relative ordering of strategies are portable across platforms' claim was REMOVED; ordering portability is NOT asserted as established",
     "ordering-portability-untested"),
]
for line, quote, kind, w, s, metric, raw, atomic in DOC:
    add(line, quote, kind, w, "orig", s, metric, "n/a", "n/a", "n/a", "(see quote)",
        "n/a", "n/a", "n/a", "", raw, "manual", "n/a", atomic, "OK", "documented",
        "inventoried; not recomputed from result CSVs")


with open(OUT, "w", newline="") as f:
    wcsv = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
    wcsv.writeheader()
    for r in rows:
        wcsv.writerow(r)
print(f"wrote {OUT} with {len(rows)} claims")
