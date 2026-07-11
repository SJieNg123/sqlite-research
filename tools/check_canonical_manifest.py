#!/usr/bin/env python3
"""Lightweight validator for results/CANONICAL_RESULTS.yaml (Phase 0 freeze).

Checks structural integrity + provenance-safety invariants only. This is NOT a
claim verifier (that is a later phase). Exits nonzero on any failure.

Run: python3 tools/check_canonical_manifest.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAN = ROOT / "results/CANONICAL_RESULTS.yaml"


def main():
    try:
        import yaml
    except ImportError:
        print("FAIL: PyYAML not available"); return 1
    if not MAN.exists():
        print(f"FAIL: manifest missing: {MAN}"); return 1

    try:
        m = yaml.safe_load(MAN.read_text())
    except yaml.YAMLError as e:
        print(f"FAIL: YAML parse error: {e}"); return 1

    errors = []

    def req(cond, msg):
        if not cond:
            errors.append(msg)

    # 1. required top-level keys
    for k in ("schema_version", "generated", "canonical_sources",
              "replacement_policy", "superseded_cells", "terminology"):
        req(k in m, f"missing top-level key: {k}")
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1

    # 2. generated git commit present
    gc = (m.get("generated") or {}).get("git_commit")
    req(bool(gc) and isinstance(gc, str) and len(gc) >= 7,
        "generated.git_commit missing/short")

    # 3. every canonical source path exists (+ summary/raw csv if named)
    srcs = m["canonical_sources"]
    for name, s in srcs.items():
        p = s.get("path")
        req(p is not None, f"{name}: no path")
        if p:
            req((ROOT / p).exists(), f"{name}: path does not exist: {p}")
        for key in ("summary_csv", "raw_csv", "readme"):
            if s.get(key):
                req((ROOT / s[key]).exists(), f"{name}: {key} missing: {s[key]}")
        # summary_glob: at least one match
        if s.get("summary_glob"):
            req(len(list(ROOT.glob(s["summary_glob"]))) > 0,
                f"{name}: summary_glob matched nothing: {s['summary_glob']}")

    # 4. legacy is canonical:false and prohibited for headlines
    leg = srcs.get("legacy_first_seen_tiebreak")
    req(leg is not None, "no legacy_first_seen_tiebreak source")
    if leg:
        req(leg.get("canonical") is False, "legacy source not canonical:false")
        req(leg.get("prohibited_for_headline_claims") is True,
            "legacy source not prohibited_for_headline_claims")

    # 4b. no canonical:false source appears in the precedence (headline) list
    prec = (m["replacement_policy"].get("precedence") or [])
    false_paths = {s["path"] for s in srcs.values() if s.get("canonical") is False}
    for fp in false_paths:
        req(fp not in prec, f"non-canonical path in precedence: {fp}")

    # 5. atomic replacement rule
    au = m["replacement_policy"].get("atomic_unit")
    req(au == ["workload", "layout", "strategy", "seed"],
        f"replacement_policy.atomic_unit wrong: {au}")
    req(m["replacement_policy"].get("legacy_fallback_allowed") is False,
        "legacy_fallback_allowed must be false")
    req("rule" in m["replacement_policy"], "replacement_policy.rule missing")

    # 6. superseded_cells have explicit selectors (no vague supersession)
    req(isinstance(m["superseded_cells"], list) and m["superseded_cells"],
        "superseded_cells empty")
    for sc in (m["superseded_cells"] or []):
        req(sc.get("source") and sc.get("replaced_by") and sc.get("selector"),
            f"superseded_cells entry lacks source/replaced_by/selector: {sc.get('id')}")
        req(bool(sc.get("reason")), f"superseded_cells entry lacks reason: {sc.get('id')}")

    # 7. C_hit orig-only, no layout-robustness claim
    ch = m["terminology"].get("C_hit", {})
    req(ch.get("evaluated_layouts") == ["orig"], "C_hit not orig-only")
    req(ch.get("claims_layout_robustness") is False,
        "C_hit must not claim layout robustness")
    # corrected sources for C_hit must be orig-only
    for nm in ("pure_hit_control_base", "pure_hit_control_corrected"):
        sc = srcs.get(nm, {}).get("scope", {})
        req(sc.get("layouts") == ["orig"], f"{nm}: not orig-only")

    if errors:
        for e in errors:
            print("FAIL:", e)
        print(f"\n{len(errors)} error(s). Manifest INVALID.")
        return 1
    print("PASS: CANONICAL_RESULTS.yaml structurally valid + provenance-safe.")
    print(f"  sources: {len(srcs)}  superseded rules: {len(m['superseded_cells'])}"
          f"  git_commit: {gc[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
