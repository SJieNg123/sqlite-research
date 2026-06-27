#!/usr/bin/env python3
"""Seedable generator for every workload kind used by the experiment.

Reconstructed to reproduce the distributions of the original committed
workloads (workload_{a,b,c,z}.txt, workload_churn_write.txt). Exact bytes are
not reproduced (original seeds unknown) — the *distribution* is, so that
re-running the matrix under many seeds measures workload sensitivity.

Usage:
    gen_workload.py <type> <seed> <out>
    <type> in {A, B, C, Z, CHURN}

Calibration targets (from the original files, 100k ops each):
    A     Zipf alpha=0.99 over 100000 keys, SCRAMBLED (rank->permuted key)
          ~23k unique, top1 ~7.8%      (scattered hot keys)
    B     uniform [1,100000]            ~63k unique, flat
    C     5 copies of [590000,609999] shuffled  -> 20000 unique, each exactly 5x
    Z     Zipf alpha=0.99 over 1000 keys, NOT scrambled (rank=key)
          1000 unique, top1 ~13%       (low-key hot)
    CHURN repeating 10-op block [rmw,insert,update,update,read,
          rmw,insert,update,scan,read]; inserts sequential from 600001;
          rmw/update/read/scan keys uniform-without-replacement over [1,600000];
          scan count = 128
"""
import sys, bisect, random, collections

N_OPS = 100000

# ---- per-type parameters (calibrated to the original files) ----
A_NKEYS, A_ALPHA = 100000, 0.99        # scrambled high-key zipf
B_LO, B_HI       = 1, 100000           # uniform head
C_LO, C_HI, C_COPIES = 590000, 609999, 5
Z_NKEYS, Z_ALPHA = 1000, 0.99          # low-key zipf, no scramble
CHURN_POOL_LO, CHURN_POOL_HI = 1, 600000
CHURN_INSERT_START = 600001
CHURN_SCAN_COUNT = 128
CHURN_BLOCK = ["readmodifywrite", "insert", "update", "update", "read",
               "readmodifywrite", "insert", "update", "scan", "read"]


def zipf_keys(rng, nkeys, alpha, nops, scramble):
    """Sample nops keys from a Zipf(alpha) over ranks 1..nkeys.

    rank r (1-indexed) has weight 1/r^alpha. If scramble, ranks are mapped to a
    random permutation of [1..nkeys] so the hot keys are scattered (workload A);
    otherwise rank == key (workload Z)."""
    prefix, s = [], 0.0
    for k in range(nkeys):
        s += 1.0 / ((k + 1) ** alpha)
        prefix.append(s)
    total = prefix[-1]
    if scramble:
        perm = list(range(1, nkeys + 1))
        rng.shuffle(perm)
    out = []
    for _ in range(nops):
        rank = bisect.bisect_left(prefix, rng.random() * total)  # 0-indexed rank
        out.append(perm[rank] if scramble else rank + 1)
    return out


def gen(wtype, seed):
    rng = random.Random(seed)
    if wtype == "A":
        keys = zipf_keys(rng, A_NKEYS, A_ALPHA, N_OPS, scramble=True)
        return [f"read {k}" for k in keys]
    if wtype == "Z":
        keys = zipf_keys(rng, Z_NKEYS, Z_ALPHA, N_OPS, scramble=False)
        return [f"read {k}" for k in keys]
    if wtype == "B":
        return [f"read {rng.randint(B_LO, B_HI)}" for _ in range(N_OPS)]
    if wtype == "C":
        pool = list(range(C_LO, C_HI + 1)) * C_COPIES
        rng.shuffle(pool)
        return [f"read {k}" for k in pool]
    if wtype == "CHURN":
        nblocks = N_OPS // len(CHURN_BLOCK)
        # non-insert keys: sample-without-replacement from the pool (matches the
        # all-unique-per-type property of the original)
        n_noninsert = sum(1 for op in CHURN_BLOCK if op != "insert") * nblocks
        pool = rng.sample(range(CHURN_POOL_LO, CHURN_POOL_HI + 1), n_noninsert)
        pi = 0
        ins = CHURN_INSERT_START
        lines = []
        for _ in range(nblocks):
            for op in CHURN_BLOCK:
                if op == "insert":
                    lines.append(f"insert {ins}")
                    ins += 1
                elif op == "scan":
                    lines.append(f"scan {pool[pi]} {CHURN_SCAN_COUNT}")
                    pi += 1
                else:
                    lines.append(f"{op} {pool[pi]}")
                    pi += 1
        return lines
    raise SystemExit(f"unknown type {wtype!r} (want A/B/C/Z/CHURN)")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    wtype, seed, out = sys.argv[1].upper(), int(sys.argv[2]), sys.argv[3]
    lines = gen(wtype, seed)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    # summary for calibration
    rkeys = [int(l.split()[1]) for l in lines if l.startswith("read ")]
    if rkeys:
        c = collections.Counter(rkeys)
        top = c.most_common(20)
        print(f"{wtype} seed={seed} -> {out}: {len(lines)} ops, "
              f"reads={len(rkeys)} unique={len(c)} "
              f"range=[{min(rkeys)},{max(rkeys)}] "
              f"top1={top[0][1]/len(rkeys)*100:.2f}% "
              f"top10={sum(x[1] for x in top[:10])/len(rkeys)*100:.2f}%")
    else:
        oc = collections.Counter(l.split()[0] for l in lines)
        print(f"{wtype} seed={seed} -> {out}: {len(lines)} ops, op-mix={dict(oc)}")


if __name__ == "__main__":
    main()
