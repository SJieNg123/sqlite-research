#!/usr/bin/env python3
"""Re-derive e2e_warm_us in a finished batch so both delivery mechanisms pay for parsing.

The warmer reads the hotset CSV before issuing hints. On the per-page path that read is
interleaved with the hints and lands inside deliver_us; the two-phase (coalesce) arms bill
it to parse_us instead. run_experiment.py computed e2e_warm_us = deliver_us + fq, so the
window-chunked arms were charged about 60 us less than per-page for the same work. It now
adds parse_us; this tool applies the same definition to batches recorded before the fix.

Only the derived column e2e_warm_us changes, and only on rows that carry parse_us. Every
measured column is left as recorded. The rewrite is guarded and idempotent: a row is
updated only if its value still equals deliver_us + first_query_us, skipped if it already
includes parse_us, and the tool stops on anything else. Summaries and the uncertainty
table are then regenerated with the batch's own code path (run_experiment.aggregate,
the family merge of tools/run_unified_v6.sh, tools/stats_uncertainty.py).

Usage: tools/rederive_e2e_warm.py results/unified_v6
"""
import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = ("main", "lp", "layout")
TOL = 0.02   # components are stored rounded to 0.01 us

_spec = importlib.util.spec_from_file_location("run_experiment", ROOT / "run_experiment.py")
rx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rx)


def rederive_raw(path):
    """Rewrite e2e_warm_us in one raw.csv. Returns (updated, already_done)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols, rows = reader.fieldnames, list(reader)
    updated = done = 0
    for r in rows:
        if not r["parse_us"] or not r["e2e_warm_us"]:
            continue
        d, p, fq, old = (float(r[k]) for k in ("deliver_us", "parse_us", "first_query_us", "e2e_warm_us"))
        if abs(old - (d + fq)) <= TOL:
            r["e2e_warm_us"] = rx._fmt(old + p)
            updated += 1
        elif abs(old - (d + p + fq)) <= TOL:
            done += 1
        else:
            raise SystemExit(f"{path}: e2e_warm_us={old} matches neither definition "
                             f"(deliver={d} parse={p} fq={fq}); not touching this batch")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return updated, done


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    batch = Path(sys.argv[1])
    seeds = sorted(p for p in batch.glob("seed[0-9][0-9]") if p.is_dir())
    if not seeds:
        raise SystemExit(f"no seedNN directories under {batch}")

    for seed in seeds:
        # The merged seed raw.csv is rewritten by the same rule as its families, so
        # the two stay identical row for row.
        for path in [seed / fam / "raw.csv" for fam in FAMILIES] + [seed / "raw.csv"]:
            up, done = rederive_raw(path)
            print(f"{path}: {up} rows updated, {done} already included parse_us")
        for fam in FAMILIES:
            with open(seed / fam / "raw.csv", newline="") as f:
                rx.aggregate(list(csv.DictReader(f)), seed / fam / "summary.csv")
        # seed summary = header of main, then the data rows of main, lp, layout
        lines = []
        for k, fam in enumerate(FAMILIES):
            body = (seed / fam / "summary.csv").read_bytes().splitlines(keepends=True)
            lines += body if k == 0 else body[1:]
        (seed / "summary.csv").write_bytes(b"".join(lines))

    # cross-seed summary = 'seed,' + header, then each seed's rows prefixed with its number
    out = []
    for k, seed in enumerate(seeds):
        body = (seed / "summary.csv").read_bytes().splitlines(keepends=True)
        if k == 0:
            out.append(b"seed," + body[0])
        out += [f"{int(seed.name[4:])},".encode() + line for line in body[1:]]
    (batch / "summary.csv").write_bytes(b"".join(out))

    subprocess.run([sys.executable, str(ROOT / "tools/stats_uncertainty.py"),
                    "--seeds", *map(str, seeds),
                    "--out", str(batch / "uncertainty.csv"),
                    "--md", str(batch / "uncertainty.md")], check=True)


if __name__ == "__main__":
    main()
