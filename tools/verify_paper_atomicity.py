#!/usr/bin/env python3
"""Atomic verifier for the paper's quantitative claims (Phase 4).

Reads docs/audits/PAPER_CLAIM_MANIFEST.csv and, for every machine-checkable
claim, re-derives the value directly from the canonical CSV named in the
manifest, then checks it against the displayed value and enforces the atomic
batch rules of results/RESULT_PROVENANCE.md. Qualitative / range / count claims
are scope-checked (source row must exist) but not recomputed.

Standard library only. Exits non-zero if any claim fails.

Usage:
  python3 tools/verify_paper_atomicity.py --manifest docs/audits/PAPER_CLAIM_MANIFEST.csv
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tie-break impact set: cells whose canonical single-inst / cross-seed source is
# the corrected rerun, NOT unified_v2 / results/seeds (RESULT_PROVENANCE 4.2).
CHANGED = {("A", "2e_K500"),
           ("B", "2e_K10"), ("B", "2e_K40"), ("B", "2e_K92"), ("B", "2e_K500"),
           ("C", "2e_K10"), ("C", "2e_K40"), ("C", "2e_K92")}
# C_hit frequency arms superseded by c_hit_v2 (c_hit is leaky for these).
CHIT_CORRECTED = {"2e_K10", "2e_K40", "2e_K92", "2e_K500"}

UNIFIED = "results/unified_v2/matrix/summary.csv"

_CACHE = {}


def load(path):
    p = ROOT / path
    if path in _CACHE:
        return _CACHE[path]
    if not p.exists():
        sys.exit(f"FATAL: canonical source not found: {path}")
    rows = list(csv.DictReader(open(p)))
    _CACHE[path] = rows
    return rows


def parse_filter(spec):
    """'workload=C;db=orig;strategy=2e_K10;arm=async;metric=e2e_warm_us' -> dict."""
    d = {}
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        k, v = part.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def select(path, filt, ignore=("col",)):
    """Return the unique row in `path` matching every key=value in `filt`.
    Keys in `ignore` are not used for matching. Exit on missing/duplicate."""
    keys = {k: v for k, v in filt.items() if k not in ignore}
    hits = []
    for r in load(path):
        if all(str(r.get(k, "")).strip() == v for k, v in keys.items()):
            hits.append(r)
    if len(hits) == 0:
        sys.exit(f"FATAL: no row in {path} matching {keys}")
    if len(hits) > 1:
        sys.exit(f"FATAL: {len(hits)} duplicate rows in {path} matching {keys}")
    return hits[0]


def baseline_filter(filt):
    """Same (workload, db) as the strategy, strategy=baseline, arm=baseline."""
    return {"workload": filt["workload"], "db": filt.get("db", "orig"),
            "strategy": "baseline", "arm": "baseline"}


def rnd(x, rule):
    if rule in ("", "int", "round_int"):
        return round(x)
    if rule.startswith("round"):
        dp = int(rule[5:]) if rule[5:].isdigit() else 1
        return round(x, dp)
    return round(x)


def approx(a, b, tol):
    return abs(a - b) <= tol


def check_atomic(claim):
    """Enforce provenance atomic rules. Return list of violation strings."""
    v = []
    src = claim["canonical_source"]
    base = claim["baseline_source"]
    filt = parse_filter(claim["source_filter"]) if claim["source_filter"] else {}
    w = filt.get("workload", claim["workload"])
    s = filt.get("strategy", claim["strategy"])
    kind_scope = claim["single_or_cross_seed"]

    # 1. changed cell must not come from a superseded batch (unified_v2 single-inst
    #    or results/seeds cross-seed); it must use the corrected rerun.
    if (w, s) in CHANGED and kind_scope in ("single", "cross"):
        if src == UNIFIED or "results/seeds/" in src:
            v.append(f"changed cell ({w},{s}) uses superseded source {src}")
    # 2. C_hit frequency arms must use c_hit_v2, not c_hit
    if src.endswith("c_hit/uncertainty.csv") and s in CHIT_CORRECTED:
        v.append(f"C_hit corrected arm {s} must use c_hit_v2, not c_hit")
    # 3. rel/abs-with-baseline: strategy and baseline must be the SAME batch (file)
    if claim["formula"].startswith("rel") and base and base != src:
        v.append(f"baseline_source {base} != strategy source {src} (cross-batch pairing)")
    # 4. C_hit must be orig only
    if claim["workload"] == "C_hit" and filt.get("db", "orig") != "orig":
        v.append("C_hit claim not on orig layout")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--tol", type=float, default=1.0,
                    help="abs tolerance for recomputed vs displayed (default 1.0)")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(ROOT / args.manifest)))
    n_total = len(rows)
    n_checked = n_scope = n_fail = 0
    fails = []
    # compare-group -> set of (source) for abs claims, to catch cross-batch stacks
    groups = {}

    for c in rows:
        cid = c["claim_id"]
        formula = c["formula"].strip()
        disp = c["displayed_value"].strip()
        src = c["canonical_source"].strip()
        filt_spec = c["source_filter"].strip()

        # atomic checks apply to every claim that names a source
        violations = check_atomic(c) if src else []

        # compare-group tracking (absolute claims sharing a group must share a batch)
        grp = c.get("compare_group", "").strip()
        if grp and formula.startswith("abs"):
            groups.setdefault(grp, set()).add(src)

        if formula in ("manual", "range", "qual", ""):
            # scope-check only: if a source+filter is given, the row must exist
            if src and filt_spec:
                select(src, parse_filter(filt_spec))
            n_scope += 1
            if violations:
                n_fail += 1
                fails.append((cid, "; ".join(violations), disp, "(scope claim)"))
            continue

        filt = parse_filter(filt_spec)
        recomputed = None
        detail = ""

        if formula.startswith("abs:"):
            col = formula.split(":", 1)[1]
            row = select(src, filt)
            recomputed = rnd(float(row[col]), c["rounding_rule"])
            detail = f"{src} [{filt.get('strategy')}/{filt.get('workload')}] {col}={row[col]}"
            ok = approx(recomputed, float(disp.rstrip("%µs ")), args.tol)

        elif formula.startswith("rel:"):
            col = formula.split(":", 1)[1]
            srow = select(src, filt)
            brow = select(c["baseline_source"], baseline_filter(filt))
            b = float(brow[col]); sv = float(srow[col])
            recomputed = rnd((sv - b) / b * 100.0, c["rounding_rule"])
            detail = f"{src} base={b:.1f} strat={sv:.1f}"
            ok = approx(recomputed, float(disp.rstrip("%µs ")), args.tol)

        elif formula == "umean":
            row = select(src, filt)
            recomputed = rnd(float(row["mean_pct"]), c["rounding_rule"])
            detail = f"{src} mean_pct={row['mean_pct']} verdict={row.get('verdict')}"
            ok = approx(recomputed, float(disp.rstrip("%µs ")), args.tol)

        elif formula == "uci":
            row = select(src, filt)
            lo = rnd(float(row["ci_lo"]), c["rounding_rule"])
            hi = rnd(float(row["ci_hi"]), c["rounding_rule"])
            recomputed = f"[{lo}, {hi}]"
            detail = f"{src} ci=[{row['ci_lo']}, {row['ci_hi']}]"
            # displayed like "[-67,-42]" or "[-67, -42]"
            want = disp.replace(" ", "").strip("[]")
            got = f"{lo},{hi}"
            ok = (want == got) or all(
                approx(float(a), float(b), args.tol)
                for a, b in zip(want.split(","), [str(lo), str(hi)]))

        elif formula.startswith("seeds_mean:"):
            # seeds_mean:<glob>:<col> — per-seed paired improvement, then mean.
            _, glob_rel, col = formula.split(":", 2)
            import glob as _glob
            import statistics as _st
            vals = []
            for fp in sorted(_glob.glob(str(ROOT / glob_rel))):
                rr = {(r["workload"], r["db"], r["strategy"], r["arm"]): r
                      for r in csv.DictReader(open(fp))}
                bk = (filt["workload"], filt.get("db", "orig"), "baseline", "baseline")
                sk = (filt["workload"], filt.get("db", "orig"), filt["strategy"], filt.get("arm", "async"))
                if bk in rr and sk in rr:
                    bb = float(rr[bk][col]); ss = float(rr[sk][col])
                    vals.append((ss - bb) / bb * 100.0)
            if not vals:
                sys.exit(f"FATAL: {cid} seeds_mean matched no seeds for {filt}")
            recomputed = rnd(_st.mean(vals), c["rounding_rule"])
            detail = f"{glob_rel} n_seeds={len(vals)} per-seed-paired mean"
            ok = approx(recomputed, float(disp.rstrip("%µs ")), args.tol)
            # criterion 6: seed count must be 10
            if len(vals) != 10:
                violations.append(f"cross-seed n={len(vals)} (expected 10)")

        elif formula.startswith("aging_red:"):
            ck = formula.split(":", 1)[1]
            srow = select(src, {**filt, "checkpoint": ck})
            brow = select(src, {"workload": filt["workload"], "strategy": "baseline",
                                "checkpoint": ck})
            b = float(brow["mean_us"]); sv = float(srow["mean_us"])
            recomputed = rnd((sv - b) / b * 100.0, c["rounding_rule"])
            detail = f"{src} ck{ck} base={b:.1f} strat={sv:.1f}"
            ok = approx(recomputed, float(disp.rstrip("%µs ")), args.tol)

        else:
            sys.exit(f"FATAL: {cid} unknown formula '{formula}'")

        n_checked += 1
        if violations:
            ok = False
        status = "PASS" if ok else "FAIL"
        if not ok:
            n_fail += 1
            fails.append((cid, detail + ("  ATOMIC:" + ";".join(violations) if violations else ""),
                          disp, recomputed))
        print(f"[{status}] {cid:6s} {c['claim_kind']:16s} disp={disp:16s} "
              f"recomputed={str(recomputed):16s} {detail}")

    print("\n" + "=" * 70)
    print(f"claims: {n_total} | recomputed: {n_checked} | scope-checked: {n_scope} | FAIL: {n_fail}")
    if fails:
        print("\nFAILURES:")
        for cid, detail, disp, rc in fails:
            print(f"  {cid}: displayed={disp} recomputed={rc}  {detail}")
        sys.exit(1)
    # cross-batch absolute-stack check
    bad_groups = {g: s for g, s in groups.items() if len(s) > 1}
    if bad_groups:
        print("\nCROSS-BATCH ABSOLUTE GROUPS (absolute claims mixing batches):")
        for g, s in bad_groups.items():
            print(f"  {g}: {sorted(s)}")
        sys.exit(1)
    print("\nALL CLAIMS PASS — paper is atomically consistent with canonical sources.")


if __name__ == "__main__":
    main()
