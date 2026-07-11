#!/usr/bin/env python3
"""Seedable generator for every workload kind used by the experiment.

Reconstructed to reproduce the distributions of the original committed
workloads (workload_{a,b,c,z}.txt, workload_churn_write.txt). Exact bytes are
not reproduced (original seeds unknown) — the *distribution* is, so that
re-running the matrix under many seeds measures workload sensitivity.

Usage:
    gen_workload.py <type> <seed> <out>
    <type> in {A, B, C, C_HIT, Z, CHURN, YD, YE}

Calibration targets (from the original files, 100k ops each):
    A     Zipf alpha=0.99 over 100000 keys, SCRAMBLED (rank->permuted key)
          ~23k unique, top1 ~7.8%      (scattered hot keys)
    B     uniform [1,100000]            ~63k unique, flat
    C     5 copies of [590000,609999] shuffled  -> 20000 unique, each exactly 5x.
          NOTE: [590000,609999] straddles the DB's max id (600000), so ~50% of the
          keys (600001..609999) are OUT-OF-RANGE not-found lookups. C is therefore a
          MIXED tail-boundary workload (50% existing hits + 50% negative lookups),
          NOT pure newly-added-data reads. Every negative lookup descends the B+tree
          right edge to the rightmost real leaf, concentrating traffic there.
    C_HIT 5 copies of [580001,600000] shuffled  -> 20000 unique, each exactly 5x.
          Pure-hit control for C: SAME 20k key-space size, uniform, tail-region
          locality, but ALL keys exist (max 600000 == db max) -> zero not-found
          artifact. Isolates whether frequency-aware prefetch still helps once the
          unintended negative-lookup right-edge concentration is removed.
    Z     Zipf alpha=0.99 over 1000 keys, NOT scrambled (rank=key)
          1000 unique, top1 ~13%       (low-key hot)
    CHURN repeating 10-op block [rmw,insert,update,update,read,
          rmw,insert,update,scan,read]; inserts sequential from 600001;
          rmw/update/read/scan keys uniform-without-replacement over [1,600000];
          scan count = 128

YCSB core workloads (write-containing; the insert stream ages the DB -- run these
through the churn/aging path, not the read-only `run` matrix). Both force op[0] to
be a `read` so a read-only TTFQ probe derived from them passes --require-read-first:
    YD    read-latest: 95% read + 5% insert, requestdistribution=latest.
          dataset [1..600000] (the DB row count), inserts append 600001.. (grow
          cur_max); each read draws a Zipf(alpha=0.99) rank over the CURRENT item
          count and maps rank 0 -> newest key (cur_max) -> hot set rides the tail.
    YE    short-ranges: 95% scan + 5% insert, requestdistribution=zipfian.
          scan start = scrambled Zipf(alpha=0.99) over [1..600000] (scattered hot
          starts, like A); scan length uniform [1,100]; inserts append 600001..
"""
import sys, bisect, random, collections

N_OPS = 100000

# ---- per-type parameters (calibrated to the original files) ----
A_NKEYS, A_ALPHA = 100000, 0.99        # scrambled high-key zipf
B_LO, B_HI       = 1, 100000           # uniform head
C_LO, C_HI, C_COPIES = 590000, 609999, 5
C_HIT_LO, C_HIT_HI, C_HIT_COPIES = 580001, 600000, 5   # pure-hit tail control (all keys exist)
Z_NKEYS, Z_ALPHA = 1000, 0.99          # low-key zipf, no scramble
# The experiment DB (items) holds a DENSE id space 1..600000. A read of id>DB_MAX_KEY
# is a not-found (negative) lookup. HIT_ONLY workloads are asserted to contain no such
# keys, so their measured first-query behaviour can't be attributed to a right-edge
# not-found concentration artifact (see the C vs C_HIT control).
DB_MAX_KEY = 600000
HIT_ONLY = {"C_HIT"}
CHURN_POOL_LO, CHURN_POOL_HI = 1, 600000
CHURN_INSERT_START = 600001
CHURN_SCAN_COUNT = 128
CHURN_BLOCK = ["readmodifywrite", "insert", "update", "update", "read",
               "readmodifywrite", "insert", "update", "scan", "read"]
# ---- YCSB D/E (read-latest / short-ranges) ----
# The experiment DB (items) holds a DENSE id space 1..600000. Inserts must start
# PAST the current max id (like CHURN's 600001) or the harness upsert
# `INSERT ... ON CONFLICT(id) DO UPDATE` just rewrites existing rows and the DB
# never grows -- which would defeat the whole point of route-1 aging.
YCSB_RECORDCOUNT = 600000       # initial dataset size = the DB's actual row count
YCSB_INSERT_START = 600001      # appended inserts start past max id (grow the DB)
YCSB_INSERT_FRAC = 0.05         # insertproportion (D and E)
YCSB_ALPHA = 0.99              # request-distribution skew (matches A/Z)
YE_MAXSCAN = 100               # maxscanlength (scanlengthdistribution=uniform)


def _zipf_prefix(nkeys, alpha):
    """Cumulative weights prefix[r] = sum_{i<=r} 1/(i+1)^alpha, for Zipf sampling
    over ranks 0..nkeys-1 via bisect. Sampling can be bounded to a sub-window
    [0,cap) by using prefix[cap-1] as the running total (see YD's growing keyspace)."""
    prefix, s = [], 0.0
    for k in range(nkeys):
        s += 1.0 / ((k + 1) ** alpha)
        prefix.append(s)
    return prefix


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
    if wtype == "C_HIT":
        pool = list(range(C_HIT_LO, C_HIT_HI + 1)) * C_HIT_COPIES
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
    if wtype == "YD":
        # read-latest: reads ride the tail of a growing keyspace. Precompute the
        # Zipf prefix once over the largest possible item count (recordcount + at
        # most N_OPS inserts); each read samples a rank over the CURRENT window
        # [0,cur_max) and maps rank 0 -> newest key. op[0] is forced to a read.
        prefix = _zipf_prefix(YCSB_RECORDCOUNT + N_OPS, YCSB_ALPHA)
        cur_max = YCSB_RECORDCOUNT
        nxt = YCSB_INSERT_START
        lines = []
        for i in range(N_OPS):
            if i > 0 and rng.random() < YCSB_INSERT_FRAC:
                lines.append(f"insert {nxt}")
                nxt += 1
                cur_max += 1
            else:
                u = rng.random() * prefix[cur_max - 1]
                rank0 = bisect.bisect_left(prefix, u, 0, cur_max)   # 0..cur_max-1
                key = cur_max - rank0                               # rank0=0 -> newest
                lines.append(f"read {key}")
        return lines
    if wtype == "YE":
        # short-ranges: scattered Zipf scan starts over the initial keyspace
        # (like A), scan length uniform [1,YE_MAXSCAN]; 5% inserts grow the DB.
        # op[0] is forced to a read (of a scan start) for the read-only probe.
        starts = zipf_keys(rng, YCSB_RECORDCOUNT, YCSB_ALPHA, N_OPS, scramble=True)
        nxt = YCSB_INSERT_START
        si = 0
        lines = []
        for i in range(N_OPS):
            if i == 0:
                lines.append(f"read {starts[si]}"); si += 1
            elif rng.random() < YCSB_INSERT_FRAC:
                lines.append(f"insert {nxt}"); nxt += 1
            else:
                lines.append(f"scan {starts[si]} {rng.randint(1, YE_MAXSCAN)}"); si += 1
        return lines
    raise SystemExit(f"unknown type {wtype!r} (want A/B/C/C_HIT/Z/CHURN/YD/YE)")


def write_manifest(out, wtype, seed, lines):
    """Emit a sidecar <out>.manifest.json recording hit/miss accounting against the
    DB's key space, so a workload's semantics can never silently drift from its actual
    query behaviour again. For HIT_ONLY types, hard-assert no key exceeds DB_MAX_KEY."""
    import json
    tgt = [int(l.split()[1]) for l in lines if l.split()[0] in ("read", "scan")]
    hit = sum(1 for k in tgt if k <= DB_MAX_KEY)
    miss = len(tgt) - hit
    gmin = min(tgt) if tgt else None
    gmax = max(tgt) if tgt else None
    if wtype in HIT_ONLY and gmax is not None and gmax > DB_MAX_KEY:
        raise SystemExit(
            f"ASSERTION FAILED: {wtype} declared expected_hit_only but "
            f"max_generated_key={gmax} > db_max_key={DB_MAX_KEY} "
            f"(would introduce not-found lookups)")
    manifest = {
        "workload": wtype, "seed": seed, "out": out, "n_ops": len(lines),
        "hit_only_declared": wtype in HIT_ONLY,
        "hit_count": hit, "miss_count": miss,
        "hit_ratio": round(hit / len(tgt), 6) if tgt else None,
        "generated_min_key": gmin, "generated_max_key": gmax,
        "db_max_key": DB_MAX_KEY,
        "first_op": lines[0] if lines else None,
        "first_op_is_hit": (int(lines[0].split()[1]) <= DB_MAX_KEY)
                           if lines and lines[0].split()[0] in ("read", "scan") else None,
    }
    with open(out + ".manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    wtype, seed, out = sys.argv[1].upper(), int(sys.argv[2]), sys.argv[3]
    lines = gen(wtype, seed)
    man = write_manifest(out, wtype, seed, lines)   # asserts BEFORE writing the trace
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    # summary for calibration (op-mix always; key stats over read+scan targets)
    oc = collections.Counter(l.split()[0] for l in lines)
    print(f"{wtype} seed={seed} -> {out}: {len(lines)} ops, op-mix={dict(oc)}")
    tgt = [int(l.split()[1]) for l in lines if l.split()[0] in ("read", "scan")]
    if tgt:
        c = collections.Counter(tgt)
        top = c.most_common(20)
        print(f"    read/scan targets={len(tgt)} unique={len(c)} "
              f"range=[{min(tgt)},{max(tgt)}] "
              f"top1={top[0][1]/len(tgt)*100:.2f}% "
              f"top10={sum(x[1] for x in top[:10])/len(tgt)*100:.2f}%")
        print(f"    hit={man['hit_count']} miss={man['miss_count']} "
              f"hit_ratio={man['hit_ratio']} first_op={man['first_op']!r} "
              f"(hit={man['first_op_is_hit']})  db_max_key={DB_MAX_KEY}")


if __name__ == "__main__":
    main()
