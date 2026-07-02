#!/usr/bin/env python3
"""churn.py — churn-checkpoint experiment (figs 07 + 12); the `run_experiment.py churn` subcommand.

Measurement is strictly via the shared pipeline (run_experiment.run_baseline / run_one:
full-machine drop-caches + in-harness --verify-hotset + warmer delivery). Churn is applied by
running the harness in WRITE mode (page_churn_write slices) on a writable copy of the DB — that
is DB mutation (setup), not measurement.

Outputs (results/churn/):
  churn_evolution.csv  workload,layout,checkpoint,strategy,first_query_us   (fig 07)
  churn_nsweep.csv     workload,layout,N,first_query_us                     (fig 12, final churned DB)
"""
import csv, shutil, statistics, subprocess, sys
from pathlib import Path
import run_experiment as R

# the base churn stream was renamed to seeded copies (_1.._10) when the 10-seed
# sweep was added; _1 is the original (seed 1), the one results/churn was built
# from. Prefer the unseeded name if it ever exists again, else fall back to _1.
_CHURN_UNSEEDED = R.ROOT / "workloads/workload_churn_write.txt"
CHURN_SRC = _CHURN_UNSEEDED if _CHURN_UNSEEDED.exists() else R.ROOT / "workloads/workload_churn_write_1.txt"
OPS_PER   = 5000
NSWEEP_N  = [1, 2, 3, 5, 8, 13, 21, 34, 46, 64, 92]   # for fig 12 (+ baseline=0)


class _Args:                      # mimic run_experiment argparse for the measurement helpers
    cpu = 2; warm_cpu_ms = 10; mem_limit = "none"
_HARNESS_ARGS = _Args()


def add_parser(sub):
    ap = sub.add_parser("churn", help="churn-checkpoint experiment (DB mutated between measurements)",
                        description="Static t=0 hotset re-measured across churn checkpoints.")
    ap.add_argument("--workload", default="A,B,C", help="workload key(s): comma-list of A,B,C,Z")
    ap.add_argument("--db", default="orig,vacuum,ta", help="db key(s): comma-list of orig,vacuum,ta")
    ap.add_argument("--checkpoints", type=int, default=10, help="churn checkpoints (x OPS_PER mutations each)")
    ap.add_argument("--reps", type=int, default=3, help="measurement reps per checkpoint (median)")
    ap.add_argument("--outdir", default=str(R.ROOT / "results/churn"))
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.set_defaults(func=cmd_churn)


def make_chunks(chunks_dir, n_ckpt):
    chunks_dir.mkdir(parents=True, exist_ok=True)
    lines = [l for l in open(CHURN_SRC).read().splitlines() if l.strip()]
    out = []
    for i in range(n_ckpt):
        seg = lines[i * OPS_PER:(i + 1) * OPS_PER]
        p = chunks_dir / f"churn_chunk_{i}.txt"
        p.write_text("\n".join(seg) + "\n")
        out.append(p)
    return out


def apply_churn(workdb, chunkfile, recdir):
    """Mutate workdb by running a churn slice through the harness in write mode."""
    cmd = [str(R.BH), "--db", str(workdb), "--workload", str(chunkfile),
           "--output", str(recdir / "churn_ops.csv"), "--record-dir", str(recdir),
           "--cold-advice", "none", "--cpu", "2"]   # write mode (no --readonly/--require-read-first)
    subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def _med_fq(fn, reps):
    """Run a measurement <reps> times, return median first_query_us (None if all failed)."""
    vals = []
    for _ in range(reps):
        m = fn()
        if m and m["first_query_us"] is not None:
            vals.append(m["first_query_us"])
    return statistics.median(vals) if vals else None


def cmd_churn(args):
    workloads = [x for x in args.workload.split(",") if x]
    layouts   = [x for x in args.db.split(",") if x]
    R._check_keys("workload", workloads, R.WORKLOADS)
    R._check_keys("db", layouts, R.DBS)
    n_ckpt, reps = args.checkpoints, args.reps
    out = Path(args.outdir)
    workdir = out / "work"

    if args.dry_run:
        print(f"churn: {workloads} x {layouts}, {n_ckpt} checkpoints x {OPS_PER} ops, "
              f"{reps} reps/ckpt; nsweep N={NSWEEP_N} on the final churned DB.")
        print(f"  -> {out/'churn_evolution.csv'} + {out/'churn_nsweep.csv'}")
        return 0

    workdir.mkdir(parents=True, exist_ok=True)
    chunks = make_chunks(workdir / "chunks", n_ckpt)
    evo_rows, nsweep_rows = [], []   # evo: (w,layout,ckpt,strategy,fq); nsweep: (w,layout,N,fq)
    for layout in layouts:
        db0 = R.resolve_pointer(R.DBS[layout])
        classify = R.load_classify(layout)
        for w in workloads:
            wl = R.WORKLOADS[w]
            workdb = workdir / f"churn_{w}_{layout}.db"
            shutil.copy2(db0, workdb)
            recdir = workdir / f"rec_{w}_{layout}"; recdir.mkdir(exist_ok=True)
            # static t=0 hotsets: 2e is workload-dependent; layers_92 is structural
            hot_2e = workdir / f"static_2e_{w}_{layout}.csv"
            R.build_hotset(R.select_pages(R.resolve_strategy("2e_K10"), w, layout, classify), classify, hot_2e)
            hot_l92 = workdir / f"static_l92_{w}_{layout}.csv"
            R.build_hotset(R.select_pages(R.resolve_strategy("layers_92"), w, layout, classify), classify, hot_l92)

            for ck in range(n_ckpt + 1):
                base = _med_fq(lambda: R.run_baseline(workdb, wl, recdir, _HARNESS_ARGS, verify_hotset=hot_2e), reps)
                s2e  = _med_fq(lambda: R.run_one(workdb, wl, hot_2e,  "fadvise", recdir, _HARNESS_ARGS), reps)
                sl92 = _med_fq(lambda: R.run_one(workdb, wl, hot_l92, "fadvise", recdir, _HARNESS_ARGS), reps)
                for strat, v in [("baseline", base), ("2e_K10_static", s2e), ("layers_92_static", sl92)]:
                    if v is not None:
                        evo_rows.append((w, layout, ck, strat, f"{v:.2f}"))
                sys.stderr.write(f"[ckpt {ck}/{n_ckpt}] {w}/{layout}: base={base} 2e={s2e} l92={sl92}\n")
                if ck < n_ckpt:
                    apply_churn(workdb, chunks[ck], recdir)

            # fig 12: layers_N sweep on the FINAL churned DB (static t=0 layers hotsets)
            nbase = _med_fq(lambda: R.run_baseline(workdb, wl, recdir, _HARNESS_ARGS, verify_hotset=hot_l92), reps)
            if nbase is not None:
                nsweep_rows.append((w, layout, 0, f"{nbase:.2f}"))
            for N in NSWEEP_N:
                hs = workdir / f"churn_layers_{w}_{layout}_{N}.csv"
                R.build_hotset(R.select_pages(R.resolve_strategy(f"layers_{N}"), w, layout, classify), classify, hs)
                v = _med_fq(lambda hs=hs: R.run_one(workdb, wl, hs, "fadvise", recdir, _HARNESS_ARGS), reps)
                if v is not None:
                    nsweep_rows.append((w, layout, N, f"{v:.2f}"))
                sys.stderr.write(f"[churn-nsweep] {w}/{layout} N={N}: {v}\n")

    out.mkdir(parents=True, exist_ok=True)
    with open(out / "churn_evolution.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["workload", "layout", "checkpoint", "strategy", "first_query_us"])
        wr.writerows(evo_rows)
    with open(out / "churn_nsweep.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["workload", "layout", "N", "first_query_us"])
        wr.writerows(nsweep_rows)
    print(f"wrote {out/'churn_evolution.csv'} ({len(evo_rows)}) + {out/'churn_nsweep.csv'} ({len(nsweep_rows)})")
    return 0


if __name__ == "__main__":
    sys.exit("run via: python3 run_experiment.py churn [options]")
