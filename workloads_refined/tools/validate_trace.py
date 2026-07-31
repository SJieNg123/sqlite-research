#!/usr/bin/env python3
"""Tier 0 trace validator (spec §5). Runs on the harness-format integer-key trace.

Every workload adjective must map to a NUMBER here (spec §-1.3 / §5.3). This computes the
trace-level checks that guard the two failure modes that bit this project:
  concern #3 (out-of-range not-found)  -> notfound_rate, measured_skew, unique_key_ratio
  concern #2 (churn claim, 0 hot-page movement) -> hotset_jaccard_series
plus op_mix_actual and parse_losses.

Page-level checks (page_count / fill_factor / btree_depth / skeleton_bytes) are DB-global and
computed via Python stdlib `dbstat` (3.46.1, no custom build — README §5.1) when --db is given.
`rightmost_leaf_share` needs a key->page map and is emitted as a deferred status here (run phase).

Emits <out> (JSON). Exits non-zero on a hard violation:
  * declared hit-only but notfound_rate > 0
  * notfound_rate > --max-notfound  (spec §1.1: Tier 2 entry needs <= 1%)
  * parse_losses > 0

Usage:
  validate_trace.py <trace.txt> --out <validation.json> [--db-max-key 600000]
        [--hit-only] [--max-notfound 0.01] [--segments 10] [--parse-losses 0]
        [--db <sqlite.db> --table items] [--label YC-hashed] [--props k=v,...]
"""
import argparse
import collections
import json
import os
import re
import sys

DEFAULT_THRESHOLDS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "validator_thresholds.yaml")


def load_thresholds(path):
    """Read the heuristic thresholds (validator_thresholds.yaml). Leaf names are unique, so a
    flat 'indented key: number' scan suffices (no PyYAML dep, same style as calc_n.py)."""
    t = {}
    for raw in open(path, encoding="utf-8"):
        m = re.match(r"^\s+([a-z0-9_]+):\s*([0-9.]+)", raw.split("#", 1)[0])
        if m:
            t[m.group(1)] = float(m.group(2))
    return t


def _margin(value, threshold, direction):
    """Signed distance to a heuristic threshold, as a fraction of the threshold.
    +ve = comfortably passing, ~0 = knife-edge (the constant is driving the verdict), -ve = fail."""
    if value is None or not threshold:
        return None
    raw = (threshold - value) / threshold if direction == "below" else (value - threshold) / threshold
    return round(raw, 4)

TARGET_OPS = {"read", "scan"}          # ops whose key hits the DB key space


def load_trace(path):
    ops = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            op = parts[0]
            key = int(parts[1])
            scanlen = int(parts[2]) if op == "scan" and len(parts) > 2 else None
            ops.append((op, key, scanlen))
    return ops


def measured_skew(targets):
    freq = collections.Counter(targets)
    total = len(targets)
    ranked = freq.most_common()
    top1 = ranked[0][1] / total if total else None
    k1pct = max(1, len(freq) // 100)
    top1pct = sum(c for _, c in ranked[:k1pct]) / total if total else None
    return {"top1_key_share": round(top1, 6) if top1 is not None else None,
            "top1pct_keys_share": round(top1pct, 6) if top1pct is not None else None,
            "distinct_keys": len(freq)}


def hotset_jaccard_series(targets, segments):
    """Split the target stream into `segments` contiguous chunks; per chunk take the top-1%
    hottest keys; report adjacent-chunk Jaccard. Stationary hotspot -> high; moving -> low."""
    if len(targets) < segments * 100:
        return {"status": "n/a (too few targets)", "series": [], "mean": None}
    size = len(targets) // segments
    hotsets = []
    for i in range(segments):
        chunk = targets[i * size:(i + 1) * size]
        freq = collections.Counter(chunk)
        k = max(1, len(freq) // 100)
        hotsets.append({key for key, _ in freq.most_common(k)})
    series = []
    for a, b in zip(hotsets, hotsets[1:]):
        u = len(a | b)
        series.append(round(len(a & b) / u, 4) if u else None)
    vals = [s for s in series if s is not None]
    return {"status": "ok", "segments": segments, "series": series,
            "mean": round(sum(vals) / len(vals), 4) if vals else None}


def hot_key_contiguity(targets):
    """Spatial contiguity of the top-1% hottest keys in rowid space (§5.2; also §3.1's
    insertorder no-op check). hot_span_frac = span(top-1% keys)/span(all keys):
    contiguous (ordered) -> ~0.01; scattered (hashed / ScrambledZipfian) -> ~1.0."""
    if not targets:
        return {"hot_span_frac": None, "n_hot": 0}
    freq = collections.Counter(targets)
    hot = [k for k, _ in freq.most_common(max(1, len(freq) // 100))]
    span = (max(targets) - min(targets)) or 1
    return {"hot_span_frac": round(((max(hot) - min(hot)) or 1) / span, 4), "n_hot": len(hot)}


def per_segment_contiguity(targets, segments):
    """Mean per-time-slice hot_span_frac. A MOVING contiguous hotspot is contiguous WITHIN
    each slice even though its GLOBAL span covers the whole trajectory -- so contiguity for the
    movement precondition MUST be per-segment, not global (global reads 'moving' as 'scattered'
    and false-fails a legit moving hotspot; caught by tests/test_validator_gates.py)."""
    if len(targets) < segments * 100:
        return None
    span = (max(targets) - min(targets)) or 1
    size = len(targets) // segments
    fracs = []
    for i in range(segments):
        freq = collections.Counter(targets[i * size:(i + 1) * size])
        hot = [k for k, _ in freq.most_common(max(1, len(freq) // 100))]
        fracs.append(((max(hot) - min(hot)) or 1) / span)
    return round(sum(fracs) / len(fracs), 4)


def per_segment_concentration(targets, segments):
    """Median per-slice top-1% concentration (x uniform). A moving hotspot is strongly
    concentrated WITHIN each slice even when its GLOBAL concentration is diluted across the
    trajectory -- so layer 1 must look per-segment too, else it false-kills a legit moving
    hotspot (YD); proved by tests/test_validator_gates.py's moving fixture."""
    if len(targets) < segments * 100:
        return None
    size = len(targets) // segments
    ratios = []
    for i in range(segments):
        seg = targets[i * size:(i + 1) * size]
        f = collections.Counter(seg)
        nd = len(f)
        k = max(1, nd // 100)
        ratios.append((sum(c for _, c in f.most_common(k)) / len(seg)) / (k / nd))
    ratios.sort()
    return round(ratios[len(ratios) // 2], 4)


def hotspot_movement(targets, segments, skew, unique_key_ratio, thr):
    """Three-layer, precondition-guarded diagnosis of a MOVING-HOTSPOT claim (§5.2).

    Each layer is a precondition for the next; skipping them is exactly how bad workloads
    slip through (jaccard~=0 and centroid displacement are BOTH meaningless without them):
      layer 1  hotset_present?  repeated keys AND concentration      (else no hotspot at all)
      layer 2  contiguous?      top-1% clustered in rowid space      (else centroid = regression-to-mean noise)
      layer 3  moving?          centroid displacement over segments
    Thresholds are heuristic (validator_thresholds.yaml); we report the MARGIN to each."""
    jac = hotset_jaccard_series(targets, segments)
    n_distinct = skew.get("distinct_keys") or 1
    top1pct = skew.get("top1pct_keys_share")
    uniform_top1pct = max(1, n_distinct // 100) / n_distinct
    conc_ratio = round(top1pct / uniform_top1pct, 4) if (top1pct and uniform_top1pct) else None

    # concentration checked GLOBAL *or* PER-SEGMENT: a moving hotspot dilutes globally but is
    # strongly concentrated per slice -- global-only false-kills YD (test_validator_gates.py).
    seg_conc = per_segment_concentration(targets, segments)
    conc_ok = ((conc_ratio is not None and conc_ratio > thr["min_top1pct_over_uniform"])
               or (seg_conc is not None and seg_conc > thr["min_top1pct_over_uniform"]))
    hotset_present = bool(
        unique_key_ratio is not None and unique_key_ratio < thr["max_unique_key_ratio"]
        and conc_ok)
    cont = hot_key_contiguity(targets)                       # GLOBAL span (for §3.1 no-op reporting)
    seg_span = per_segment_contiguity(targets, segments)     # PER-SLICE span (moving-safe; the gate)
    contiguous = bool(seg_span is not None and seg_span < thr["max_hot_span_frac"])

    disp_frac = None
    if hotset_present and contiguous and jac.get("status") == "ok":
        size = len(targets) // segments
        span = (max(targets) - min(targets)) or 1
        cents = []
        for i in range(segments):
            f = collections.Counter(targets[i * size:(i + 1) * size])
            hot = [k for k, _ in f.most_common(max(1, len(f) // 100))]
            cents.append(sum(hot) / len(hot))
        disp_frac = round((max(cents) - min(cents)) / span, 4)

    interpretable = hotset_present and contiguous
    if not hotset_present:
        note = "movement NOT interpretable: no hotset (near-uniform / sampling-without-replacement)"
    elif not contiguous:
        note = f"movement NOT interpretable: hotset scattered in rowid space (hot_span_frac={cont['hot_span_frac']})"
    else:
        note = "hotset present & contiguous -> displacement interpretable"
    return {
        "hotset_present": hotset_present, "contiguous": contiguous,
        "interpretable": interpretable,
        "hot_span_frac": cont["hot_span_frac"], "per_segment_hot_span_frac": seg_span,
        "concentration_over_uniform": conc_ratio,
        "centroid_displacement_frac": disp_frac,
        "jaccard": jac,
        "margins": {
            "hotset_unique_key_ratio": _margin(unique_key_ratio, thr["max_unique_key_ratio"], "below"),
            "hotset_concentration": _margin(conc_ratio, thr["min_top1pct_over_uniform"], "above"),
            "contiguity": _margin(seg_span, thr["max_hot_span_frac"], "below"),
            "displacement": _margin(disp_frac, thr["min_centroid_displacement_frac"], "above"),
        },
        "note": note,
    }


def db_page_stats(db_path, table):
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        page_size = con.execute("PRAGMA page_size").fetchone()[0]
        page_count = con.execute("PRAGMA page_count").fetchone()[0]
        rows = con.execute(
            "SELECT pagetype, ncell, payload, unused, path FROM dbstat WHERE name=?",
            (table,)).fetchall()
    except sqlite3.OperationalError as e:
        return {"status": f"dbstat unavailable: {e}"}
    finally:
        con.close()
    interior = [r for r in rows if r[0] == "internal"]
    leaf = [r for r in rows if r[0] == "leaf"]
    depth = max((r[4].count("/") for r in rows), default=0)  # dbstat path segment depth
    leaf_fill = None
    if leaf:
        leaf_fill = round(sum(1 - (r[3] / page_size) for r in leaf) / len(leaf), 4)
    return {
        "status": "ok", "page_size": page_size, "page_count": page_count,
        "table_interior_pages": len(interior), "table_leaf_pages": len(leaf),
        "btree_depth": depth, "leaf_fill_factor": leaf_fill,
        "skeleton_bytes": len(interior) * page_size,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out", required=True)
    ap.add_argument("--db-max-key", type=int, default=600000)
    ap.add_argument("--hit-only", action="store_true")
    ap.add_argument("--max-notfound", type=float, default=0.01)
    ap.add_argument("--segments", type=int, default=10)
    ap.add_argument("--parse-losses", type=int, default=0)
    ap.add_argument("--db", default=None)
    ap.add_argument("--table", default="items")
    ap.add_argument("--label", default=None)
    ap.add_argument("--props", default=None)
    ap.add_argument("--claims-moving-hotspot", action="store_true",
                    help="declare that this workload claims a MOVING hotspot (YD/latest/churn); "
                         "enables the precondition-guarded movement gate (§5.2)")
    ap.add_argument("--thresholds", default=DEFAULT_THRESHOLDS,
                    help="heuristic-thresholds YAML (validator_thresholds.yaml); thresholds are "
                         "inputs, not code -- validator reports margins, not just pass/fail")
    args = ap.parse_args()

    ops = load_trace(args.trace)
    op_mix = collections.Counter(op for op, _, _ in ops)   # LINE-level (what's in the trace)
    # RMW workloads emit 2 lines/op (READ+UPDATE); report op-level too so nobody mistakes
    # workloadf's 66/34 read/update *lines* for its actual 50/50 read/rmw *ops* (choice (a)).
    RMW_WORKLOADS = {"workloadf"}
    workload = ""
    if args.props:
        for kv in args.props.split(","):
            if kv.startswith("workload="):
                workload = kv.split("=", 1)[1]
    if workload in RMW_WORKLOADS:
        n_read, n_upd = op_mix.get("read", 0), op_mix.get("update", 0)
        op_mix_ops = {"read": n_read - n_upd, "readmodifywrite": n_upd}
        ycsb_ops = n_read
    else:
        op_mix_ops = dict(op_mix)
        ycsb_ops = len(ops)
    targets = [k for op, k, _ in ops if op in TARGET_OPS]
    inserts = [k for op, k, _ in ops if op == "insert"]

    # not-found accounting: a read/scan target above the DB's max existing id is a negative
    # lookup. (inserts append past db_max_key legitimately and are excluded.)
    miss = sum(1 for k in targets if k > args.db_max_key)
    notfound_rate = round(miss / len(targets), 6) if targets else None

    ukr = round(len(set(targets)) / len(targets), 6) if targets else None
    skew = measured_skew(targets)
    thr = load_thresholds(args.thresholds)
    hotmove = hotspot_movement(targets, args.segments, skew, ukr, thr)

    report = {
        "label": args.label, "trace": args.trace,
        "n_ops": len(ops),
        "trace_lines": len(ops),
        "ycsb_ops": ycsb_ops,
        "op_mix_actual": dict(op_mix),
        "op_mix_ops": op_mix_ops,
        "target_ops": len(targets),
        "unique_key_ratio": ukr,
        "measured_skew": skew,
        "notfound_rate": notfound_rate,
        "notfound_count": miss,
        "db_max_key": args.db_max_key,
        "hit_only_declared": args.hit_only,
        "insert_count": len(inserts),
        "generated_min_key": min(targets) if targets else None,
        "generated_max_key": max(targets) if targets else None,
        "first_op": " ".join(map(str, filter(lambda x: x is not None,
                                             (ops[0][0], ops[0][1], ops[0][2])))) if ops else None,
        "first_op_is_read": ops[0][0] == "read" if ops else None,
        "hotspot_movement": hotmove,
        "thresholds_used": thr,
        "parse_losses": args.parse_losses,
        "rightmost_leaf_share": {"status": "deferred: needs key->page map (run phase)"},
        "props": args.props,
    }
    if args.db:
        report["db_page_stats"] = db_page_stats(args.db, args.table)

    # ---- hard violations ----
    fails = []
    if args.parse_losses > 0:
        fails.append(f"parse_losses={args.parse_losses} > 0")
    if args.hit_only and miss > 0:
        fails.append(f"hit_only declared but notfound_count={miss}")
    if notfound_rate is not None and notfound_rate > args.max_notfound:
        fails.append(f"notfound_rate={notfound_rate} > max_notfound={args.max_notfound}")
    # moving-hotspot gate (§5.2): a claim of a moving hotspot must survive the precondition
    # (a hotset must EXIST) before movement is even interpretable, then must actually move.
    if args.claims_moving_hotspot:
        if not hotmove["hotset_present"]:
            fails.append(
                f"claims moving-hotspot but NO hotset (unique_key_ratio={ukr}, "
                f"concentration_margin={hotmove['margins']['hotset_concentration']}); "
                f"jaccard(mean)={hotmove['jaccard'].get('mean')} non-diagnostic")
        elif not hotmove["contiguous"]:
            fails.append(
                f"claims moving-hotspot but hotset SCATTERED in rowid space "
                f"(hot_span_frac={hotmove['hot_span_frac']} >= {thr['max_hot_span_frac']}); "
                f"no spatial locality to move (centroid would be regression-to-mean noise)")
        elif hotmove["centroid_displacement_frac"] is not None \
                and hotmove["centroid_displacement_frac"] < thr["min_centroid_displacement_frac"]:
            fails.append(
                f"claims moving-hotspot but STATIC (displacement="
                f"{hotmove['centroid_displacement_frac']} < {thr['min_centroid_displacement_frac']})")
    report["verdict"] = "PASS" if not fails else "FAIL"
    report["violations"] = fails

    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
    sys.stderr.write(f"validate_trace: {report['verdict']} -> {args.out}"
                     + (f"  ({'; '.join(fails)})" if fails else "") + "\n")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
