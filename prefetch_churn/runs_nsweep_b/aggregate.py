#!/usr/bin/env python3
"""Aggregate N-sweep × Workload B × churn. Reports first_q per checkpoint
and avg across checkpoints 1..10 (excluding baseline)."""
import csv, statistics
from pathlib import Path

DIR = Path(__file__).parent
NS = [0, 1, 5, 10, 20, 46, 92]

def load(n):
    p = DIR / f"n{n}" / "benchmark_summary.csv"
    if not p.exists(): return None
    out = []
    with p.open() as f:
        for row in csv.DictReader(f):
            out.append((row['label'], float(row['first_query_latency_us']),
                        float(row['average_latency_us']),
                        int(row['total_major_page_faults'])))
    return out

data = {n: load(n) for n in NS}
labels = [r[0] for r in data[0]]

print("=== Workload B × churn — first_query_latency_us (per checkpoint) ===")
print(f"{'checkpoint':<18} " + " ".join(f"{'N='+str(n):>10s}" for n in NS))
for i, lab in enumerate(labels):
    row = " ".join(f"{data[n][i][1]:>10.2f}" for n in NS)
    print(f"{lab:<18} {row}")

print("\n=== AVG over 10 churn checkpoints (excl baseline) ===")
avgs = {}
for n in NS:
    avg = statistics.mean(r[1] for r in data[n][1:])
    avgs[n] = avg
    print(f"  N={n:<3} avg_first_q={avg:>8.2f} us")

base = avgs[0]
print(f"\n=== DELTA vs N=0 baseline (base={base:.2f} us) ===")
for n in NS:
    if n == 0: continue
    pct = (avgs[n] - base) / base * 100
    print(f"  N={n:<3} delta={pct:+6.1f}%  ({avgs[n]:>8.2f} us)")

with (DIR / "matrix_first_q_us.csv").open("w") as f:
    f.write("checkpoint," + ",".join(f"N{n}" for n in NS) + "\n")
    for i, lab in enumerate(labels):
        f.write(lab + "," + ",".join(f"{data[n][i][1]:.2f}" for n in NS) + "\n")
print(f"\nwrote {DIR/'matrix_first_q_us.csv'}")
