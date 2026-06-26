#!/usr/bin/env python3
"""cadence.py — background-warmer prefetch cadence experiment (fig 08); the
`run_experiment.py cadence` subcommand.

Cadence is intrinsically multiprocess (a background prefetcher re-warms while a foreground
probes), but the *measurement* is kept strictly cold-clear: each probe does a full-machine
`/usr/local/sbin/drop-caches`, waits a fixed gap during which the background warmer may fire,
then measures first-query via benchmark_harness with the hardening flags + in-harness
--verify-hotset (cold-advice none, since the drop already happened).

  cadence < gap  -> warmer fires during the gap -> probe hits a warm hotset (low first-q)
  cadence >> gap -> warmer rarely fires in the gap -> probe hits cold cache (high first-q)

Output: results/cadence/cadence_results.csv  (cadence,round,first_q_us,delivery_pct)
"""
import csv, os, signal, statistics, subprocess, sys, time
from pathlib import Path
import run_experiment as R


class _Args:
    cpu = 2; warm_cpu_ms = 10; mem_limit = "none"
_HARNESS_ARGS = _Args()


def add_parser(sub):
    ap = sub.add_parser("cadence", help="background-warmer cadence experiment (multiprocess)",
                        description="Foreground cold-probe vs a background re-warmer at varied cadence.")
    ap.add_argument("--workload", default="A", help="workload key (single)")
    ap.add_argument("--db", default="orig", help="db key (single)")
    ap.add_argument("--cadences", default="1.0,5.0,30.0,never", help="seconds between background re-warms")
    ap.add_argument("--rounds", type=int, default=8, help="probe rounds per cadence")
    ap.add_argument("--gap", type=float, default=3.0, help="seconds between drop-caches and probe")
    ap.add_argument("--outdir", default=str(R.ROOT / "results/cadence"))
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.set_defaults(func=cmd_cadence)


def _start_bg_warmer(db, hotset, cadence_s):
    """Background process: re-warm the hotset every cadence_s seconds (the 'prefetcher')."""
    loop = (f'while true; do WARM_METHOD=fadvise {R.WARMER} {db} {hotset} 4096 '
            f'>/dev/null 2>&1; sleep {cadence_s}; done')
    return subprocess.Popen(["sh", "-c", loop], preexec_fn=os.setsid)


def _probe(db, wl, hotset, recdir, gap):
    """One probe: full drop-caches, gap (warmer may fire), measure first-q (no re-drop)."""
    subprocess.run([R.DROP_CACHES], check=True, timeout=120)
    time.sleep(gap)
    cmd = [str(R.BH), "--db", str(db), "--workload", str(wl),
           "--output", str(recdir / "ops.csv"), "--record-dir", str(recdir),
           "--cold-advice", "none", "--verify-hotset", str(hotset)] + R._harness_hardening(_HARNESS_ARGS)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return R.parse_metrics(r.stderr + "\n" + r.stdout)


def cmd_cadence(args):
    w, layout = args.workload, args.db
    R._check_keys("workload", [w], R.WORKLOADS)
    R._check_keys("db", [layout], R.DBS)
    cadences = [c for c in args.cadences.split(",") if c]
    rounds, gap = args.rounds, args.gap
    out = Path(args.outdir); work = out / "work"
    db = R.resolve_pointer(R.DBS[layout]); wl = R.WORKLOADS[w]

    if args.dry_run:
        print(f"cadence: w={w} db={layout}, cadences={cadences}, {rounds} rounds, gap={gap}s "
              f"(hotset=2f_slru).")
        print(f"  -> {out/'cadence_results.csv'}")
        return 0

    work.mkdir(parents=True, exist_ok=True)
    classify = R.load_classify(layout)
    pages = R.select_pages(R.resolve_strategy("2f_slru"), w, layout, classify)
    hotset = work / "cadence_hotset.csv"
    R.build_hotset(pages, classify, hotset)
    recdir = work / "rec"; recdir.mkdir(exist_ok=True)

    rows = []
    for cad in cadences:
        proc = None
        if cad != "never":
            proc = _start_bg_warmer(db, hotset, cad)
            time.sleep(0.5)
        try:
            for rd in range(rounds):
                m = _probe(db, wl, hotset, recdir, gap)
                fq = m["first_query_us"]; dl = m["delivery_pct"]
                if fq is not None:
                    rows.append((cad, rd, f"{fq:.2f}", "" if dl is None else f"{dl:.1f}"))
                sys.stderr.write(f"[cad={cad} round={rd}] fq={fq} delivery={dl}\n")
        finally:
            if proc:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    out.mkdir(parents=True, exist_ok=True)
    with open(out / "cadence_results.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["cadence", "round", "first_q_us", "delivery_pct"]); wr.writerows(rows)
    # quick summary
    by = {}
    for cad, _, fq, _ in rows:
        by.setdefault(cad, []).append(float(fq))
    for cad in cadences:
        v = by.get(cad, [])
        if v:
            sys.stderr.write(f"  cadence={cad}: median first_q={statistics.median(v):.1f} us (n={len(v)})\n")
    print(f"wrote {out/'cadence_results.csv'} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit("run via: python3 run_experiment.py cadence [options]")
