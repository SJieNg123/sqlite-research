#!/usr/bin/env python3
"""calc_n.py — compute YR recordcount N from row width W.

Single source of truth = ../yr_sweep.yaml (leaf_pages + W). N is NOT stored
anywhere: it is a *view* — computed on demand as

    N = leaf_pages * rows_per_leaf(W)

where rows_per_leaf is MEASURED by building a small prototype at width W and
reading dbstat (reusing build_yr_prototype). This is the whole point of the
normalization: the spec stores only inputs (W, leaf_pages); every derived value
is recomputed here, never transcribed, so it cannot drift or be copied stale.

Usage:
    calc_n.py --W 226            -> prints N (e.g. 4500000)
    calc_n.py --all              -> prints "W<TAB>N" for every W in the YAML
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_yr_prototype import build, measure   # reuse the measured-geometry tool

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_YAML = os.path.join(HERE, "..", "yr_sweep.yaml")


def _yaml_scalar(path, key):
    """Minimal YAML reader (no PyYAML dep): returns the scalar after 'key:'."""
    for raw in open(path, encoding="utf-8"):
        line = raw.split("#", 1)[0].strip()
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    sys.exit(f"key '{key}' not found in {path}")


def leaf_pages(path):
    return int(_yaml_scalar(path, "leaf_pages"))


def w_list(path):
    raw = _yaml_scalar(path, "W").strip("[]")
    return [int(x) for x in raw.split(",") if x.strip()]


def rows_per_leaf(W, probe_rows, tmp):
    """Measure rows/leaf at row width W (native 23B key + value=W-23)."""
    db = os.path.join(tmp, f"calc_n_W{W}.db")
    build(db, probe_rows, 23, W - 23)      # total row ≈ W (§2.7: INT-PK/TEXT-PK identical)
    m = measure(db)
    try:
        os.remove(db)
    except OSError:
        pass
    return m["rows_per_leaf"]


def calc_n(W, yaml_path, probe_rows, tmp):
    return int(round(leaf_pages(yaml_path) * rows_per_leaf(W, probe_rows, tmp)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--W", type=int, help="row width in bytes")
    ap.add_argument("--all", action="store_true", help="print N for every W in the YAML")
    ap.add_argument("--yaml", default=DEFAULT_YAML)
    ap.add_argument("--probe-rows", type=int, default=200000)
    ap.add_argument("--tmp", default="/tmp")
    a = ap.parse_args()
    if a.all:
        for W in w_list(a.yaml):
            print(f"{W}\t{calc_n(W, a.yaml, a.probe_rows, a.tmp)}")
    elif a.W is not None:
        print(calc_n(a.W, a.yaml, a.probe_rows, a.tmp))
    else:
        ap.error("need --W <bytes> or --all")


if __name__ == "__main__":
    main()
