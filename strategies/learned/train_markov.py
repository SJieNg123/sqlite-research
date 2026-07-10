#!/usr/bin/env python3
"""Train a first-order Markov page-transition table + marginal from an ordered page
sequence, and emit ml_static hotsets (= marginal top-N).

Why marginal top-N is the ml_static hotset: at cold start (t=0) there is NO conditioning
context (no query has run), so a transition model can only fall back to the marginal.
Under CROSS-OP transitions (leaf -> next query's root) the chain is ergodic, and an
ergodic chain's stationary distribution equals the marginal (long-run visit frequency).
A root-seeded expected-visit expansion therefore converges to the marginal -> the t=0
collapse to frequency ranking is structural, not a weakness of first-order Markov.
See DESIGN_learned.md.

Artifacts (train-seed + input sha256 recorded for the freeze standard):
  <out_prefix>_marginal.csv   page_number,visits,rank
  <out_prefix>_trans.csv      page_number,succ_page,count,succ_rank   (top-M successors)
  <runs-dir>/learned_<w>_<layout>_N<N>_seed<T>.csv   page_number,is_resident  (marginal top-N)

Usage:
  train_markov.py <seq.csv> <out_prefix> --w A --layout orig --train-seed 2
                  --hotset-n 14,28 [--top-m 8] [--runs-dir strategies/access/runs]
"""
import sys, csv, argparse, hashlib
from collections import Counter, defaultdict
from pathlib import Path


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('seq')
    ap.add_argument('out_prefix')
    ap.add_argument('--w', required=True)
    ap.add_argument('--layout', required=True)
    ap.add_argument('--train-seed', type=int, required=True)
    ap.add_argument('--hotset-n', default='14,28')
    ap.add_argument('--top-m', type=int, default=8)
    ap.add_argument('--runs-dir', default='strategies/access/runs')
    a = ap.parse_args()

    pages = [int(r['page_number']) for r in csv.DictReader(open(a.seq))]
    prov = (f"# train_seed={a.train_seed} seq={a.seq} "
            f"seq_sha256={_sha256(a.seq)} n_pages={len(pages)}")

    # --- marginal (page visit-count ranking) = the static-mode prediction basis ---
    marg = Counter(pages)
    with open(f"{a.out_prefix}_marginal.csv", 'w', newline='') as f:
        f.write(prov + "\n")
        w = csv.writer(f)
        w.writerow(['page_number', 'visits', 'rank'])
        for rank, (pg, c) in enumerate(marg.most_common(), 1):
            w.writerow([pg, c, rank])

    # --- first-order transition table, top-M successors per page (cross-op counted) ---
    trans = defaultdict(Counter)
    for i in range(len(pages) - 1):
        trans[pages[i]][pages[i + 1]] += 1
    with open(f"{a.out_prefix}_trans.csv", 'w', newline='') as f:
        f.write(prov + f" top_m={a.top_m}\n")
        w = csv.writer(f)
        w.writerow(['page_number', 'succ_page', 'count', 'succ_rank'])
        for pg in sorted(trans):
            for r, (sp, c) in enumerate(trans[pg].most_common(a.top_m), 1):
                w.writerow([pg, sp, c, r])

    # --- ml_static hotsets = marginal top-N (t=0 => only the marginal is available) ---
    runs = Path(a.runs_dir)
    runs.mkdir(parents=True, exist_ok=True)
    ranked = [pg for pg, _ in marg.most_common()]
    for N in [int(x) for x in a.hotset_n.split(',') if x]:
        out = runs / f"learned_{a.w}_{a.layout}_N{N}_seed{a.train_seed}.csv"
        top = sorted(ranked[:N])
        with open(out, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['page_number', 'is_resident'])
            for pg in top:
                w.writerow([pg, 1])
        print(f"wrote {out}: marginal top-{N} ({len(top)} pages)", file=sys.stderr)
    print(prov, file=sys.stderr)


if __name__ == '__main__':
    main()
