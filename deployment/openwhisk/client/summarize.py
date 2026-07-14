#!/usr/bin/env python3
"""Summarize an OpenWhisk cold-start run under the atomic pairing rules.

Reads ``summary.csv`` from a collected run directory and computes paired
strategy-vs-baseline relative improvements WITHIN the same atomic unit
(environment/session, workload, seed, first_operation). It never uses a
local-machine baseline as denominator and never derives a percentage from
cross-seed absolute means (PROTOCOL.md). Cross-seed aggregation is left as an
explicit second step over the per-seed paired values.

Phase 5A: this runs on dry-run-collected data. It reports counts and paired
deltas only; it makes no claim about OpenWhisk performance.
"""
import argparse
import csv
import json
import os
import statistics

# Observation key: identifies one measured cell (INCLUDES strategy).
OBSERVATION_KEY = ("warm_session_id", "workload", "seed", "first_operation_id",
                   "strategy")
# Pairing-block key: the block within which a strategy is paired against its
# baseline (EXCLUDES strategy). A valid denominator shares all of these AND the
# same warm-process session (present in the key), never a local-machine baseline.
PAIR_KEY = ("warm_session_id", "workload", "seed", "first_operation_id")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_valid(summary_csv):
    rows = []
    with open(summary_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("valid") in ("True", "true", "1"):
                rows.append(r)
    return rows


def paired_deltas(rows, metric="first_query_us"):
    """Per atomic unit, compute (strategy - baseline)/baseline*100 for each
    non-baseline strategy, using the same-unit baseline only."""
    baselines = {}
    for r in rows:
        if r["strategy"] == "baseline":
            baselines[tuple(r[k] for k in PAIR_KEY)] = _f(r[metric])
    out = []
    for r in rows:
        if r["strategy"] == "baseline":
            continue
        key = tuple(r[k] for k in PAIR_KEY)
        b = baselines.get(key)
        s = _f(r[metric])
        if b and s is not None and b != 0:
            out.append({"strategy": r["strategy"], "seed": r["seed"],
                        "warm_session_id": r["warm_session_id"],
                        "metric": metric, "baseline": b, "strategy_value": s,
                        "paired_pct": (s - b) / b * 100.0})
    return out


def summarize(run_dir, metric="first_query_us"):
    rows = load_valid(os.path.join(run_dir, "summary.csv"))
    deltas = paired_deltas(rows, metric)
    # per-seed-paired first, then aggregate the paired values (never abs means).
    by_strategy = {}
    for d in deltas:
        by_strategy.setdefault(d["strategy"], []).append(d["paired_pct"])
    agg = {}
    for strat, vals in by_strategy.items():
        agg[strat] = {
            "n_paired": len(vals),
            "mean_paired_pct": statistics.mean(vals) if vals else None,
            "median_paired_pct": statistics.median(vals) if vals else None,
        }
    return {"metric": metric, "n_valid_rows": len(rows),
            "n_paired": len(deltas), "per_strategy": agg}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--metric", default="first_query_us")
    args = ap.parse_args()
    print(json.dumps(summarize(args.run_dir, args.metric), indent=2))


if __name__ == "__main__":
    main()
