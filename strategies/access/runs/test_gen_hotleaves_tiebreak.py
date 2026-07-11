#!/usr/bin/env python3
"""Regression test: gen_hotleaves must be INVARIANT to workload line order.

The old `Counter.most_common(TOPK)` broke frequency ties by insertion order, so on
a tied-count workload (C / C_hit: every leaf ~equally hot) the selected leaves were
the earliest-SEEN leaves -- which trivially included the measured first-op leaf
(first-op leakage). The fix ranks by (-count, pageno). This test shuffles the
workload lines (destroying first-seen order) and asserts the hotset is byte-identical.

Run:  python3 strategies/access/runs/test_gen_hotleaves_tiebreak.py
Exit 0 = pass. Uses the real orig DB + a tied-count workload (C_hit seed 1).
"""
import subprocess, sys, os, random, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / "strategies/access/runs/gen_hotleaves.py"
DB = ROOT / "pipeline/preparation/layout_rewriter/runs/test.db"
CL = ROOT / "pipeline/preparation/layout_rewriter/runs/classify_before.csv"
HOT = ROOT / "strategies/slru/runs/hotpages_c_hit_seed1.csv"
WL = ROOT / "workloads/workload_c_hit_1.txt"
TMP = Path(os.environ.get("CLAUDE_JOB_DIR", "/tmp")) / "tmp"
TMP.mkdir(parents=True, exist_ok=True)


def run(wl, out, k):
    subprocess.run([sys.executable, str(GEN), str(DB), str(CL), str(HOT), str(wl), str(k), str(out)],
                   check=True, capture_output=True, text=True)
    return hashlib.sha256(Path(out).read_bytes()).hexdigest()


def main():
    if not (DB.exists() and HOT.exists() and WL.exists()):
        print("SKIP: fixtures missing (regen C_hit seed 1 first)"); return 0
    lines = WL.read_text().split("\n")
    body = [l for l in lines if l.strip()]
    shuf = TMP / "wl_shuffled.txt"
    rng = random.Random(12345)
    perm = body[:]
    rng.shuffle(perm)
    assert perm != body, "shuffle was a no-op"
    shuf.write_text("\n".join(perm) + "\n")

    failures = []
    for k in (10, 40, 92, 500):
        h_orig = run(WL, TMP / f"ho_orig_K{k}.csv", k)
        h_shuf = run(shuf, TMP / f"ho_shuf_K{k}.csv", k)
        ok = h_orig == h_shuf
        print(f"K={k:<4} orig={h_orig[:12]} shuf={h_shuf[:12]}  {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(k)
    if failures:
        print(f"FAIL: hotset changed under line shuffle for K={failures} "
              f"(tie-break is NOT trace-order-independent)")
        return 1
    print("PASS: hotset is invariant to workload line order (trace-order-independent tie-break)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
