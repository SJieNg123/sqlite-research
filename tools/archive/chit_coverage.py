#!/usr/bin/env python3
"""C_hit 10-fold offline coverage (mirrors results/loso/coverage.csv for the control).

For each test seed s (1..10): does the FIRST-op leaf of workload_c_hit_s land in the
strategy's selected hotset? Plus per-seed hit/miss (all hits for C_hit by construction)
and hotset precision (selected leaves that are actually touched by the workload).

Arms: learned_markov_N14 (LOSO, test=s), frequency_N14 (LOSO twin), 2e_K10 (seed s),
      2f_top14 (freqdump, seed s).

Usage: tools/chit_coverage.py [--w C_hit] [--out results/loso/coverage_c_hit.csv]
"""
import sys, csv, argparse, bisect
sys.path.insert(0, "strategies/learned")
from gen_pageseq import build_index, _ancestor_paths  # noqa: E402

ROOT = "."
DB = "pipeline/preparation/layout_rewriter/runs/test.db"
DB_MAX_KEY = 600000


def load_hotset_pages(path):
    """Selected hotset = rows with is_resident==1 (matches run_experiment._resident_pages).
    Files that omit the column (all-selected, e.g. learned) count every row."""
    try:
        with open(path) as f:
            return [int(row["page_number"]) for row in csv.DictReader(f)
                    if row.get("is_resident", "1").strip() == "1"]
    except FileNotFoundError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", default="C_hit")
    ap.add_argument("--wl-pattern", default="workloads/workload_c_hit_{s}.txt")
    ap.add_argument("--layout", default="orig")
    ap.add_argument("--budget", type=int, default=14)
    ap.add_argument("--out", default="results/loso/coverage_c_hit.csv")
    a = ap.parse_args()

    root, path2pg, pg2type, leaf_first = build_index(DB)
    firsts = [x[0] for x in leaf_first]

    def leaf_of(k):
        i = bisect.bisect_right(firsts, k) - 1
        if i < 0:
            return None
        _, pg, _lp = leaf_first[i]
        return pg

    AR = "strategies/access/runs"
    arms = {
        "learned_markov": f"{AR}/learned_markov_{a.w}_{a.layout}_N{a.budget}_test{{s}}.csv",
        "frequency":      f"{AR}/frequency_{a.w}_{a.layout}_N{a.budget}_test{{s}}.csv",
        "2e_K10":         f"{AR}/hot2e_{a.w}_{a.layout}_K10_seed{{s}}.csv",
        "2f_top14":       f"{AR}/freqdump_{a.w}_{a.layout}_N{a.budget}_seed{{s}}.csv",
    }

    rows = []
    for s in range(1, 11):
        wl = a.wl_pattern.format(s=s)
        lines = [l for l in open(wl).read().split("\n") if l.strip()]
        first_key = int(lines[0].split()[1])
        first_leaf = leaf_of(first_key)
        first_hit = first_key <= DB_MAX_KEY
        # leaves actually touched by the full workload (unique)
        used_leaves = set()
        for l in lines:
            p = l.split()
            if p[0] == "read":
                lf = leaf_of(int(p[1]))
                if lf is not None:
                    used_leaves.add(lf)
        for arm, patt in arms.items():
            pages = load_hotset_pages(patt.format(s=s))
            if pages is None:
                rows.append([a.w, arm, s, first_key, "HIT" if first_hit else "MISS",
                             first_leaf, "NA", "NA", "NA", "NA"])
                continue
            sel_leaves = [pg for pg in pages if pg2type.get(pg) == "leaf"]
            covered = int(first_leaf in set(pages))
            n_sel = len(sel_leaves)
            used_in_sel = sum(1 for pg in sel_leaves if pg in used_leaves)
            prec = round(used_in_sel / n_sel * 100) if n_sel else 0
            rows.append([a.w, arm, s, first_key, "HIT" if first_hit else "MISS",
                         first_leaf, n_sel, covered, 100, prec])

    hdr = ["workload", "arm", "test_seed", "first_op_key", "first_op_hitmiss",
           "first_op_leaf", "n_sel_leaves", "first_op_covered", "hot_leaf_used_pct",
           "precision_pct"]
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(rows)

    # summary to stdout
    print(f"wrote {a.out}  ({len(rows)} rows)")
    for arm in arms:
        ar = [r for r in rows if r[1] == arm and r[7] != "NA"]
        if not ar:
            print(f"  {arm:16s}: (no hotsets found)")
            continue
        cov = sum(r[7] for r in ar)
        prec = sum(r[9] for r in ar) / len(ar)
        hit_cov = sum(r[7] for r in ar if r[4] == "HIT")
        print(f"  {arm:16s}: first_op_covered {cov}/{len(ar)}  "
              f"(all-HIT workload)  mean_precision {prec:.0f}%")


if __name__ == "__main__":
    main()
