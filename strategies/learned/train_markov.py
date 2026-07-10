#!/usr/bin/env python3
"""Chen-inspired transition-based learned prefetch baseline (first-order Markov).

NOT a reproduction of Chen et al. (ICDE 2021). A lightweight, transparent baseline
that keeps their formulation of database prefetching as *future-page prediction from
historical access traces*, replacing the (unavailable) neural model with a first-order
Markov transition model over page-access episodes. Decision Module, background thread,
and the full neural architecture are NOT reproduced. Only page-access context is used
(no SQL template / request key / tenant features).

Pipeline (all OFFLINE preprocessing; the runtime uses a pre-generated static hotset):
  1. pool per-query EPISODES (START -> root -> interior -> leaf -> END) from the TRAIN
     seeds (transitions built only within an op_no; no cross-query edges).
  2. transition probabilities  P(q|p) = count(p,q) / sum_x count(p,x).
  3. finite-horizon expected-visit expansion from START (horizon = max real-page depth
     + 1); this is a next-page predictor, NOT iterated to a stationary distribution.
  4. emit artifacts + TWO independent hotsets via SEPARATE code paths:
       learned_markov_<w>_<layout>_N<N>_test<T>.csv   <- from *_scores.csv  (this model)
       frequency_<w>_<layout>_N<N>_test<T>.csv        <- from *_marginal.csv (analysis)

Held-out: train seeds and the test seed are disjoint (asserted). Formal evaluation uses
leave-one-seed-out; a single train->test pair is for smoke only.

Usage:
  train_markov.py --db <db> --classify <cl> --w A --layout orig \
      --test-seed 1 --train-seeds 2 3 4 ... --budget 14,28 \
      --workload-pattern 'workloads/workload_a_{s}.txt' \
      --artifact-dir <dir> --runs-dir strategies/access/runs [--reads-only]
"""
import sys, csv, json, argparse, hashlib
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_pageseq as gp

MODEL = "first_order_markov"
MODEL_VERSION = 2
TIE_BREAK = "score_desc_page_asc"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()


def pool_train(db, classify, pattern, train_seeds, reads_only):
    """Pool episodes across train seeds -> transition counts, marginal, max real depth."""
    trans = defaultdict(Counter)          # p -> Counter(q)
    marginal = Counter()                  # real page -> visits
    max_depth = 0
    inputs = {}
    for s in train_seeds:
        wl = pattern.format(s=s)
        inputs[str(s)] = _sha256(wl)
        for _op_no, ep in gp.episodes(db, wl, reads_only=reads_only):
            # ep = [(step,page,type)...] incl START/END; build within-episode transitions
            for i in range(len(ep) - 1):
                p, q = ep[i][1], ep[i + 1][1]
                trans[p][q] += 1
            real = [(step, pg) for step, pg, t in ep if pg not in (gp.START_ID, gp.END_ID)]
            for _step, pg in real:
                marginal[pg] += 1
            if real:
                max_depth = max(max_depth, len(real))     # #real pages root..leaf
    return trans, marginal, max_depth, inputs


def expected_visits(trans, horizon):
    """Finite-horizon expected-visit scores from START (sparse). Real pages only."""
    outsum = {p: sum(c.values()) for p, c in trans.items()}
    v = {gp.START_ID: 1.0}
    scores = defaultdict(float)
    for _step in range(horizon):
        nv = defaultdict(float)
        for p, pv in v.items():
            succ = trans.get(p)
            if not succ:
                continue
            os = outsum[p]
            for q, c in succ.items():
                nv[q] += pv * (c / os)
        v = nv
        for page, prob in v.items():
            if page not in (gp.START_ID, gp.END_ID):
                scores[page] += prob
    return scores, outsum


def _page_types(db, classify):
    import sqlite3
    d = sqlite3.connect(str(db))
    d.execute("CREATE VIRTUAL TABLE temp.s USING dbstat(main)")
    root = d.execute("SELECT rootpage FROM sqlite_master WHERE name='items'").fetchone()[0]
    t = {}
    for pg, pt in d.execute("SELECT pageno,pagetype FROM temp.s WHERE name='items'"):
        t[pg] = 'root' if pg == root else ('interior' if pt != 'leaf' else 'leaf')
    return t


# ---- artifact writers -------------------------------------------------------------
def write_transitions(trans, outsum, path):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['page_number', 'succ_page', 'count', 'prob'])
        for p in sorted(trans):
            os = outsum[p]
            for q, c in sorted(trans[p].items(), key=lambda kv: (-kv[1], kv[0])):
                w.writerow([p, q, c, f"{c/os:.10g}"])


def write_scores(scores, ptypes, path):
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))   # score desc, page asc
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['page_number', 'page_type', 'expected_visit_score', 'rank'])
        for rank, (pg, sc) in enumerate(ranked, 1):
            w.writerow([pg, ptypes.get(pg, '?'), f"{sc:.10g}", rank])


def write_marginal(marginal, ptypes, path):
    ranked = sorted(marginal.items(), key=lambda kv: (-kv[1], kv[0]))
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['page_number', 'page_type', 'visits', 'rank'])
        for rank, (pg, c) in enumerate(ranked, 1):
            w.writerow([pg, ptypes.get(pg, '?'), c, rank])


# ---- hotset emitters: TWO INDEPENDENT code paths (gate #4) -------------------------
def hotset_from_scores(scores_csv, N):
    """learned_markov hotset: top-N real pages by expected_visit_score (this model)."""
    rows = list(csv.DictReader(open(scores_csv)))
    rows.sort(key=lambda r: (-float(r['expected_visit_score']), int(r['page_number'])))
    return [int(r['page_number']) for r in rows[:N]]


def hotset_from_marginal(marginal_csv, N):
    """frequency hotset: top-N real pages by visit count (independent analysis baseline)."""
    rows = list(csv.DictReader(open(marginal_csv)))
    rows.sort(key=lambda r: (-int(r['visits']), int(r['page_number'])))
    return [int(r['page_number']) for r in rows[:N]]


def _write_hotset(pages, dest):
    with open(dest, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['page_number', 'is_resident'])
        for pg in sorted(pages):
            assert pg >= 0, "special token leaked into hotset"
            w.writerow([pg, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True); ap.add_argument('--classify', required=True)
    ap.add_argument('--w', required=True); ap.add_argument('--layout', required=True)
    ap.add_argument('--test-seed', type=int, required=True)
    ap.add_argument('--train-seeds', type=int, nargs='+', required=True)
    ap.add_argument('--budget', default='14,28')
    ap.add_argument('--workload-pattern', required=True)
    ap.add_argument('--artifact-dir', required=True)
    ap.add_argument('--runs-dir', default='strategies/access/runs')
    ap.add_argument('--reads-only', action='store_true')
    a = ap.parse_args()

    # --- hard no-leakage assertions ---
    assert a.test_seed not in a.train_seeds, \
        f"LEAKAGE: test_seed {a.test_seed} in train_seeds {a.train_seeds}"
    assert len(a.train_seeds) >= 1, "need >=1 train seed"

    art = Path(a.artifact_dir); art.mkdir(parents=True, exist_ok=True)
    runs = Path(a.runs_dir); runs.mkdir(parents=True, exist_ok=True)
    stem = f"{a.w}_{a.layout}_test{a.test_seed}"

    trans, marginal, max_depth, inputs = pool_train(
        a.db, a.classify, a.workload_pattern, a.train_seeds, a.reads_only)
    horizon = max_depth + 1
    scores, outsum = expected_visits(trans, horizon)
    ptypes = _page_types(a.db, a.classify)

    tr_csv = art / f"{stem}_transitions.csv"
    sc_csv = art / f"{stem}_scores.csv"
    mg_csv = art / f"{stem}_marginal.csv"
    write_transitions(trans, outsum, tr_csv)
    write_scores(scores, ptypes, sc_csv)
    write_marginal(marginal, ptypes, mg_csv)

    budgets = [int(x) for x in a.budget.split(',') if x]
    for N in budgets:
        lm = hotset_from_scores(sc_csv, N)                 # <- scores path
        fq = hotset_from_marginal(mg_csv, N)               # <- marginal path (separate)
        _write_hotset(lm, runs / f"learned_markov_{a.w}_{a.layout}_N{N}_test{a.test_seed}.csv")
        _write_hotset(fq, runs / f"frequency_{a.w}_{a.layout}_N{N}_test{a.test_seed}.csv")

    meta = {
        "model": MODEL, "model_version": MODEL_VERSION,
        "workload": a.w, "layout": a.layout,
        "train_seeds": sorted(a.train_seeds), "test_seed": a.test_seed,
        "horizon": horizon, "max_real_depth": max_depth,
        "budget_pages": budgets, "tie_break": TIE_BREAK,
        "reads_only": a.reads_only, "input_sha256": inputs,
        "artifacts": {"transitions": tr_csv.name, "scores": sc_csv.name, "marginal": mg_csv.name},
    }
    meta_path = art / f"{stem}_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    # also drop a sidecar next to each hotset so select_pages can verify no-leakage
    for N in budgets:
        (runs / f"learned_markov_{a.w}_{a.layout}_N{N}_test{a.test_seed}.meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n")

    sys.stderr.write(f"[{stem}] horizon={horizon} train={sorted(a.train_seeds)} "
                     f"budgets={budgets} -> {runs}/learned_markov_{a.w}_{a.layout}_N*_test{a.test_seed}.csv\n")


if __name__ == '__main__':
    main()
