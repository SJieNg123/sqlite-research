#!/usr/bin/env python3
"""Compare first_q across n0 (no prefetch), n92 (layers_92), 2d, 2e_k10 over 11 checkpoints."""
import csv, sys
from pathlib import Path

DIR = Path(__file__).parent
NSWEEP = DIR.parent / "runs_nsweep"

def load(p):
    out = []
    with p.open() as f:
        for row in csv.DictReader(f):
            out.append((row['label'], float(row['first_query_latency_us']),
                        float(row['average_latency_us']),
                        int(row['total_major_page_faults'])))
    return out

sources = [
    ("n0_base",   NSWEEP / "n0/benchmark_summary.csv"),
    ("n92_layers",NSWEEP / "n92/benchmark_summary.csv"),
    ("acc_2d",    DIR / "2d/benchmark_summary.csv"),
    ("acc_2e_k10",DIR / "2e_k10/benchmark_summary.csv"),
]
data = {name: load(p) for name, p in sources}
labels = [r[0] for r in data["n0_base"]]

print(f"{'label':<16} " + " ".join(f"{n:>12s}" for n in data.keys()))
print(f"{'':16} " + " ".join(f"{'first_q_us':>12s}" for _ in data.keys()))
for i, lab in enumerate(labels):
    row = " ".join(f"{data[n][i][1]:>12.2f}" for n in data.keys())
    print(f"{lab:<16} {row}")

print()
print("AVERAGE across checkpoints 1-10 (excludes baseline):")
for name in data.keys():
    avg = sum(r[1] for r in data[name][1:]) / 10
    print(f"  {name:<16} avg_first_q={avg:.2f} us")

# vs n0 baseline
base_avg = sum(r[1] for r in data["n0_base"][1:]) / 10
print()
print(f"DELTA vs n0_base (avg over 10 checkpoints, base={base_avg:.2f}us):")
for name in data.keys():
    if name == "n0_base": continue
    a = sum(r[1] for r in data[name][1:]) / 10
    pct = (a - base_avg) / base_avg * 100
    print(f"  {name:<16} avg={a:.2f}us delta={pct:+.1f}%")

# write summary CSV
with (DIR / "matrix_first_q_us.csv").open("w") as f:
    f.write("label," + ",".join(data.keys()) + "\n")
    for i, lab in enumerate(labels):
        f.write(lab + "," + ",".join(f"{data[n][i][1]:.2f}" for n in data.keys()) + "\n")
print(f"\nwrote {DIR / 'matrix_first_q_us.csv'}")
