#!/usr/bin/env python3
"""Aggregate B × access-pattern × churn × {static t=0 hot for 2d / 2e_k10 / 2e_k50}.
Compares decay vs baseline (n0) and against layers_5/layers_92 (n5/n92) from runs_nsweep_b/."""
import csv, statistics
from pathlib import Path

DIR = Path(__file__).parent
NSB = DIR.parent / "runs_nsweep_b"

def load(p):
    out = []
    with p.open() as f:
        for row in csv.DictReader(f):
            out.append((row['label'], float(row['first_query_latency_us']),
                        float(row['average_latency_us']),
                        int(row['total_major_page_faults'])))
    return out

sources = [
    ("n0_base",       NSB / "n0/benchmark_summary.csv"),
    ("n5_layers",     NSB / "n5/benchmark_summary.csv"),
    ("n92_layers",    NSB / "n92/benchmark_summary.csv"),
    ("2d_static",     DIR / "2d_static/benchmark_summary.csv"),
    ("2e_k10_static", DIR / "2e_k10_static/benchmark_summary.csv"),
    ("2e_k50_static", DIR / "2e_k50_static/benchmark_summary.csv"),
]
data = {name: load(p) for name, p in sources}
labels = [r[0] for r in data["n0_base"]]

print(f"{'checkpoint':<18} " + " ".join(f"{n:>14s}" for n in data.keys()))
for i, lab in enumerate(labels):
    row = " ".join(f"{data[n][i][1]:>14.2f}" for n in data.keys())
    print(f"{lab:<18} {row}")

print("\n=== AVG over 10 churn checkpoints (excl baseline) ===")
avgs = {}
for n in data.keys():
    a = statistics.mean(r[1] for r in data[n][1:])
    avgs[n] = a
    print(f"  {n:<16} avg_first_q={a:>8.2f} us")

base = avgs["n0_base"]
print(f"\n=== DELTA vs n0_base (base={base:.2f} us) ===")
for n in data.keys():
    if n == "n0_base": continue
    pct = (avgs[n] - base) / base * 100
    print(f"  {n:<16} avg={avgs[n]:>8.2f}us delta={pct:+6.1f}%")

print("\n=== DECAY: ck001 vs ck010 (static-hotpages drift over 50k churn ops) ===")
for n in data.keys():
    first = data[n][1][1]
    last = data[n][10][1]
    drift_pct = (last - first) / first * 100 if first > 0 else 0
    print(f"  {n:<16} ck001={first:>8.2f}us ck010={last:>8.2f}us drift={drift_pct:+6.1f}%")

with (DIR / "matrix_first_q_us.csv").open("w") as f:
    f.write("checkpoint," + ",".join(data.keys()) + "\n")
    for i, lab in enumerate(labels):
        f.write(lab + "," + ",".join(f"{data[n][i][1]:.2f}" for n in data.keys()) + "\n")
print(f"\nwrote {DIR/'matrix_first_q_us.csv'}")
