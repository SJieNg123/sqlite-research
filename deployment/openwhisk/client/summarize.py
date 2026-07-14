#!/usr/bin/env python3
"""Summarize an OpenWhisk cold-start run under the atomic pairing rules.

Reads ``summary.csv`` from a collected run directory, forms one-to-one
baseline/strategy pairs under the formal pair key, computes each pair's effect on
the requested metric, and aggregates **per-seed first, then across seeds with
equal weight** (unequal valid repetition counts never reweight a seed). It never
mixes workloads, handle modes, first-operation ids, strategies, or
artifact/image/run-config identities, and never uses a local-machine baseline.

Phase 5A.2: runs on dry-run-collected data; reports counts and paired effects
only, no OpenWhisk performance claim.
"""
import argparse
import csv
import json
import os
import statistics

# Observation key: one measured cell (INCLUDES strategy).
OBSERVATION_KEY = ("run_config_sha256", "artifact_manifest_sha256",
                   "action_image_digest", "warm_session_id", "workload", "seed",
                   "first_operation_id", "handle_mode", "pair_id", "strategy")
# Formal pair key: the block a strategy pairs against its baseline (EXCLUDES
# strategy). Identity + session + pair_id must all match between the two arms.
PAIR_KEY = ("run_config_sha256", "artifact_manifest_sha256", "action_image_digest",
            "warm_session_id", "workload", "seed", "first_operation_id",
            "handle_mode", "pair_id")
# Grouping for aggregation (identity + cell shape, NOT seed / session / pair).
AGG_KEY = ("run_config_sha256", "artifact_manifest_sha256", "action_image_digest",
           "workload", "handle_mode", "first_operation_id", "target_strategy")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def metric_value(row, metric):
    """Compute the requested metric for one row, honouring handle-mode scope."""
    fq = _f(row.get("first_query_us"))
    dv = _f(row.get("deliver_us")) or 0.0
    ov = _f(row.get("open_us")) or 0.0
    hm = row.get("handle_mode")
    if metric == "first_query_us":
        return fq
    if metric == "e2e_warm_us":
        return (dv + fq) if (hm == "warm" and fq is not None) else None
    if metric == "e2e_standalone_us":
        return (ov + dv + fq) if (hm == "standalone" and fq is not None) else None
    raise ValueError("unknown metric: %s" % metric)


def load_valid(summary_csv):
    rows = []
    with open(summary_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("valid") in ("True", "true", "1"):
                rows.append(r)
    return rows


def form_pairs(rows):
    """Group valid rows by pair_id and classify each group. Returns
    (valid_pairs, report) where valid_pairs is a list of dicts with baseline/
    target rows, and report counts incomplete/duplicate/session-break."""
    by_pair = {}
    for r in rows:
        by_pair.setdefault(r.get("pair_id"), []).append(r)
    valid, incomplete, duplicate, session_break = [], [], [], []
    for pid, group in by_pair.items():
        base = [r for r in group if r.get("strategy") == "baseline"]
        targ = [r for r in group if r.get("strategy") not in ("baseline", None, "")]
        if len(base) > 1 or len(targ) > 1:
            duplicate.append(pid)
            continue
        if len(base) != 1 or len(targ) != 1:
            incomplete.append(pid)
            continue
        b, t = base[0], targ[0]
        if b.get("warm_session_id") != t.get("warm_session_id"):
            session_break.append(pid)
            continue
        # every pair-key field must match across the two arms
        if any(b.get(k) != t.get(k) for k in PAIR_KEY):
            incomplete.append(pid)
            continue
        valid.append({"pair_id": pid, "baseline": b, "target": t,
                      "target_strategy": t.get("strategy")})
    return valid, {"incomplete_pairs": incomplete, "duplicate_pairs": duplicate,
                   "session_break_pairs": session_break}


def pair_effects(valid_pairs, metric):
    """Per pair: (target_metric - baseline_metric)/baseline_metric*100."""
    out = []
    for p in valid_pairs:
        b = metric_value(p["baseline"], metric)
        t = metric_value(p["target"], metric)
        if b and t is not None and b != 0:
            eff = (t - b) / b * 100.0
            row = {k: p["target"].get(k) for k in AGG_KEY[:-1]}
            row["target_strategy"] = p["target_strategy"]
            row.update({"pair_id": p["pair_id"], "seed": p["target"].get("seed"),
                        "metric": metric, "baseline": b, "target": t,
                        "paired_pct": eff})
            out.append(row)
    return out


def aggregate(effects):
    """Per-seed mean first, then equal-weight mean across seeds, within each
    AGG_KEY group. Unequal per-seed repetition counts do NOT reweight seeds."""
    groups = {}
    for e in effects:
        gk = tuple(e[k] for k in AGG_KEY)
        groups.setdefault(gk, {}).setdefault(e["seed"], []).append(e["paired_pct"])
    out = {}
    for gk, by_seed in groups.items():
        per_seed = {s: statistics.mean(v) for s, v in by_seed.items()}
        seed_means = list(per_seed.values())
        out[" | ".join(str(x) for x in gk)] = {
            "n_seeds": len(per_seed),
            "n_pairs": sum(len(v) for v in by_seed.values()),
            "per_seed_mean_pct": {str(s): round(m, 3) for s, m in per_seed.items()},
            "cross_seed_equal_weight_mean_pct":
                round(statistics.mean(seed_means), 3) if seed_means else None,
        }
    return out


def summarize(run_dir, metric="first_query_us", write=False):
    rows = load_valid(os.path.join(run_dir, "summary.csv"))
    valid_pairs, report = form_pairs(rows)
    effects = pair_effects(valid_pairs, metric)
    agg = aggregate(effects)
    excluded = _excluded(os.path.join(run_dir, "summary.csv"))
    result = {"metric": metric, "n_valid_rows": len(rows),
              "n_valid_pairs": len(valid_pairs), "n_paired_effects": len(effects),
              "incomplete_pairs": len(report["incomplete_pairs"]),
              "duplicate_pairs": len(report["duplicate_pairs"]),
              "session_break_pairs": len(report["session_break_pairs"]),
              "excluded_invocations": excluded, "aggregate": agg}
    if write:
        with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(AGG_KEY) + ["pair_id", "seed",
                               "metric", "baseline", "target", "paired_pct"],
                               extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            for e in effects:
                w.writerow(e)
        with open(os.path.join(run_dir, "summary_result.json"), "w") as f:
            json.dump(result, f, indent=2)
    return result


def _excluded(summary_csv):
    reasons = {}
    with open(summary_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("valid") not in ("True", "true", "1"):
                reasons[r.get("exclusion_reason", "?")] = reasons.get(
                    r.get("exclusion_reason", "?"), 0) + 1
    return reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--metric", default="first_query_us",
                    choices=["first_query_us", "e2e_warm_us", "e2e_standalone_us"])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    print(json.dumps(summarize(a.run_dir, a.metric, a.write), indent=2))


if __name__ == "__main__":
    main()
