#!/usr/bin/env python3
"""Canonical workload registry loader (standard library only).

Single source of truth: config/workloads.json (sibling of this file). This
module exposes the normalization and display helpers that every consumer
(figure scripts, table generators, OpenWhisk config/schedule loader) must use
instead of hard-coding the legacy->display mapping.

Design invariants:
  * Legacy IDs (A, B, C, C_mixed, C_hit, Z, YD, YE, CHURN) are what the
    immutable results CSVs and the verifier's source_filter carry. They are
    NEVER rewritten. This module maps them for presentation only.
  * normalize_workload_id() accepts a legacy alias, a canonical ID, or a
    display name and returns the canonical ID. It fails loud on unknown input.
  * workload_display_name() returns the paper-facing display name.

Usage:
    from workload_registry import normalize_workload_id, workload_display_name
    normalize_workload_id("A")        -> "read_zipf_scattered_100k"
    normalize_workload_id("C_mixed")  -> "read_tail_mixed_20k"
    workload_display_name("A")        -> "Scattered-Zipf"
    workload_display_name("C")        -> "Tail-Mixed"

CLI self-test:
    python3 config/workload_registry.py --selftest
"""
from __future__ import annotations

import json
from pathlib import Path

_REGISTRY_PATH = Path(__file__).resolve().parent / "workloads.json"


def _load():
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    records = data["workloads"]
    by_canonical = {}
    alias_to_canonical = {}       # exact-case aliases + canonical + display
    ci_alias_to_canonical = {}    # lower-cased fallback

    def _register(key, canonical, bucket, ci_bucket):
        if key in bucket and bucket[key] != canonical:
            raise ValueError(
                f"registry alias collision: {key!r} maps to both "
                f"{bucket[key]!r} and {canonical!r}")
        bucket[key] = canonical
        ci_bucket.setdefault(key.lower(), canonical)

    for rec in records:
        canonical = rec["canonical_id"]
        if canonical in by_canonical:
            raise ValueError(f"duplicate canonical_id {canonical!r}")
        by_canonical[canonical] = rec
        _register(canonical, canonical, alias_to_canonical, ci_alias_to_canonical)
        _register(rec["display_name"], canonical, alias_to_canonical, ci_alias_to_canonical)
        for alias in rec.get("legacy_aliases", []):
            _register(alias, canonical, alias_to_canonical, ci_alias_to_canonical)
    return records, by_canonical, alias_to_canonical, ci_alias_to_canonical


_RECORDS, _BY_CANONICAL, _ALIAS, _CI_ALIAS = _load()


def normalize_workload_id(old_or_new_id):
    """Return the canonical workload ID for any legacy alias, canonical ID, or
    display name. Case-insensitive fallback (handles C_hit vs C_HIT). Raises
    KeyError on an unknown identifier (fail loud)."""
    if old_or_new_id is None:
        raise KeyError("workload id is None")
    key = str(old_or_new_id).strip()
    if key in _ALIAS:
        return _ALIAS[key]
    lo = key.lower()
    if lo in _CI_ALIAS:
        return _CI_ALIAS[lo]
    raise KeyError(
        f"unknown workload id {old_or_new_id!r}; "
        f"known aliases include {sorted(_ALIAS)[:8]}...")


def workload_meta(id_):
    """Return the full registry record for a workload (any alias/canonical)."""
    return _BY_CANONICAL[normalize_workload_id(id_)]


def workload_display_name(id_):
    """Return the paper-facing display name for a workload (any alias/canonical)."""
    return workload_meta(id_)["display_name"]


def is_measured(id_):
    """True for measured evaluation workloads, False for mutation schedules."""
    return bool(workload_meta(id_)["is_measured"])


def legacy_aliases(id_):
    """Return the list of legacy aliases for a workload."""
    return list(workload_meta(id_).get("legacy_aliases", []))


def all_records():
    """Return all registry records in registration order."""
    return list(_RECORDS)


def _selftest():
    problems = []
    # every alias resolves back to a record whose aliases contain it (round-trip)
    for rec in _RECORDS:
        canon = rec["canonical_id"]
        for probe in [canon, rec["display_name"], *rec.get("legacy_aliases", [])]:
            got = normalize_workload_id(probe)
            if got != canon:
                problems.append(f"{probe!r} -> {got!r}, expected {canon!r}")
    # spot-check the documented mapping
    expected = {
        "A": ("read_zipf_scattered_100k", "Scattered-Zipf"),
        "B": ("read_uniform_100k", "Uniform-100K"),
        "C": ("read_tail_mixed_20k", "Tail-Mixed"),
        "C_mixed": ("read_tail_mixed_20k", "Tail-Mixed"),
        "C_hit": ("read_tail_hit_20k", "Tail-Hit"),
        "Z": ("read_zipf_concentrated_1k", "Concentrated-Zipf"),
        "YD": ("py_ycsb_d_latest_aging", "Latest-Aging"),
        "YE": ("py_ycsb_e_short_scan_aging", "Short-Scan Aging"),
        "CHURN": ("mutation_churn_schedule", "Mixed-Mutation Churn"),
    }
    for legacy, (canon, disp) in expected.items():
        if normalize_workload_id(legacy) != canon:
            problems.append(f"normalize({legacy!r}) != {canon!r}")
        if workload_display_name(legacy) != disp:
            problems.append(f"display({legacy!r}) != {disp!r}")
    # unknown id must fail loud
    try:
        normalize_workload_id("nope")
        problems.append("unknown id did not raise")
    except KeyError:
        pass
    return problems


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Canonical workload registry")
    ap.add_argument("--selftest", action="store_true", help="validate registry consistency")
    ap.add_argument("--table", action="store_true", help="print legacy->canonical->display table")
    ap.add_argument("--resolve", metavar="ID", help="print canonical id + display name for ID")
    args = ap.parse_args(argv)
    if args.resolve:
        print(f"{args.resolve} -> {normalize_workload_id(args.resolve)} "
              f"({workload_display_name(args.resolve)})")
        return 0
    if args.table or not (args.selftest):
        print(f"{'legacy':22s} {'canonical_id':30s} {'display':22s} kind")
        for rec in _RECORDS:
            print(f"{','.join(rec.get('legacy_aliases', [])):22s} "
                  f"{rec['canonical_id']:30s} {rec['display_name']:22s} {rec['kind']}")
    if args.selftest:
        problems = _selftest()
        if problems:
            print("SELFTEST FAIL:")
            for p in problems:
                print("  " + p)
            return 1
        print("SELFTEST PASS: all aliases resolve; documented mapping verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
