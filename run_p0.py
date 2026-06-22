#!/usr/bin/env python3
"""
run_p0.py — general P0 cold-start runner (locked spec: IMPLEMENTATION_PIPELINES.md §3).

For every (workload x layout x strategy) cell it runs BOTH arms on the SAME hotset:
  - pread  (oracle)  : WARM_METHOD=pread  -> fq_pread, deterministic upper bound
  - async  (realistic): WARM_METHOD=fadvise -> fq_async + delivery_pct
delivery method is held constant (warmer) so pread vs async differ ONLY in sync/async;
their gap (fq_async - fq_pread) = the async delivery loss.

Each cell:
  benchmark_harness --cold-advice dontneed --drop-caches-script /usr/local/sbin/drop-caches
                    --post-cold-script <tmp deliver.sh>  --verify-hotset <hotset>
harness emits (stderr): first_query_latency_us, avg_latency_us, total_majflt/minflt,
verify_cold_pct, verify_delivery_pct; warmer emits warmer_us (preproc).

Strategy hotsets are normalised to warmer format `page_number,file_offset` by joining
the strategy's selected pages with the layout's classify CSV (warmer reads col2 as offset).

Outputs (under <outdir>, default p0_runs/):
  raw_p0.csv      one row per (workload,db,strategy,arm,rep)
  summary_p0.csv  median/p95/min/stdev per (workload,db,strategy,arm), warmup dropped
  env.txt         the P0_ENV line captured at start

Usage:
  python3 run_p0.py                 # run the full matrix
  python3 run_p0.py --dry-run       # print the plan + one sample command, run nothing
  python3 run_p0.py --list          # list cells and exit
  python3 run_p0.py --workloads A,C --strategies layers_5,2e_K10 --layouts orig,ta
  python3 run_p0.py --pread-reps 3 --async-reps 10 --outdir p0_runs
"""
import argparse
import csv
import os
import re
import shlex
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

# ----------------------------------------------------------------------------- config
ROOT = Path(os.environ.get("P0_ROOT", "/home/u03/sqlite-research-project-sharing"))

BH          = ROOT / "benchmark_harness/benchmark_harness"
WARMER      = ROOT / "prefetch_warmer/src/warmer"
DROP_CACHES = "/usr/local/sbin/drop-caches"
P0_ENV      = ROOT / "p0_env.sh"
PAGE_SIZE   = 4096

DBS = {
    "orig":   ROOT / "layout_rewriter/runs/test.db",
    "vacuum": ROOT / "layout_rewriter/runs/test_vacuum.db",
    "ta":     ROOT / "layout_rewriter/runs/test_typeaware.db",
}
CLASSIFY = {
    "orig":   ROOT / "layout_rewriter/runs/classify_before.csv",
    "vacuum": ROOT / "layout_rewriter/runs/classify_vacuum.csv",
    "ta":     ROOT / "layout_rewriter/runs/classify_after.csv",
}
WORKLOADS = {
    "A": ROOT / "benchmark_harness/workloads/workload_a_zipfian.txt",
    "B": ROOT / "benchmark_harness/workloads/workload_uniform.txt",
    "C": ROOT / "prefetch_churn/workloads/page_churn_benchmark_high.txt",
}
SLRU_SUFFIX = {"orig": "", "vacuum": "_vacuum", "ta": "_ta"}

# Each strategy = a rule that selects page numbers; the runner joins them with
# classify to make a warmer-format hotset. kind dispatches in select_pages().
STRATEGIES = [
    {"name": "layers_5",  "kind": "layers", "n": 5},
    {"name": "layers_92", "kind": "layers", "n": 92},
    {"name": "2d",        "kind": "resident_interior"},
    {"name": "2e_K10",    "kind": "hot2e",  "k": 10},
    {"name": "2e_K500",   "kind": "hot2e",  "k": 500},
    {"name": "2f_slru",   "kind": "slru"},
]

# --------------------------------------------------------------------------- parsing
RE = {
    "first_query_us": re.compile(r"first_query_latency_us=([\d.]+)"),
    "avg_us":         re.compile(r"avg_latency_us=([\d.]+)"),
    "majflt":         re.compile(r"total_majflt=(\d+)"),
    "minflt":         re.compile(r"total_minflt=(\d+)"),
    "cold_pct":       re.compile(r"verify_cold_pct=([\d.]+)"),
    "delivery_pct":   re.compile(r"verify_delivery_pct=([\d.]+)"),
    "preproc_us":     re.compile(r"warmer_us=([\d.]+)"),
}


def parse_metrics(text):
    out = {}
    for key, rx in RE.items():
        m = rx.search(text)
        out[key] = float(m.group(1)) if m else None
    return out


# ------------------------------------------------------------------- hotset building
def resolve_pointer(path, depth=5):
    """Follow the repo's tiny relative-path 'pointer' CSVs (Windows checkout uses
    text pointers where Linux uses symlinks). Returns the real file path."""
    path = Path(path)
    for _ in range(depth):
        try:
            if path.is_file() and path.stat().st_size < 200:
                txt = path.read_text().strip()
                if "\n" not in txt and (txt.startswith("../") or txt.endswith(".csv")):
                    path = (path.parent / txt).resolve()
                    continue
        except OSError:
            break
        break
    return path


def load_classify(layout):
    """page_number -> (type, file_offset) for a layout."""
    d = {}
    with open(resolve_pointer(CLASSIFY[layout]), newline="") as f:
        for r in csv.DictReader(f):
            d[int(r["page_number"])] = (r["page_type"].strip(), int(r["file_offset"]))
    return d


def _resident_pages(path):
    """page numbers with is_resident==1 from a page_number,is_resident CSV."""
    pages = set()
    with open(resolve_pointer(path), newline="") as f:
        for r in csv.DictReader(f):
            if r.get("is_resident", "0").strip() == "1":
                pages.add(int(r["page_number"]))
    return pages


def select_pages(strat, w, layout, classify):
    """Return the set of page numbers a strategy selects for this cell."""
    kind = strat["kind"]
    if kind == "layers":
        interior = sorted((off, pn) for pn, (t, off) in classify.items()
                          if t.startswith("interior"))
        return {pn for _, pn in interior[: strat["n"]]}
    if kind == "resident_interior":   # 2d: resident interior pages
        src = ROOT / f"prefetch_access/runs/hotpages_{w.lower()}{SLRU_SUFFIX[layout]}.csv"
        res = _resident_pages(src)
        return {pn for pn in res if classify.get(pn, ("", 0))[0].startswith("interior")}
    if kind == "hot2e":               # 2e_K: curated interior + top-K leaves
        src = ROOT / f"prefetch_access/runs/hot2e_{w}_{layout}_K{strat['k']}.csv"
        return _resident_pages(src)
    if kind == "slru":                # 2f: whole resident working set
        src = ROOT / f"prefetch_slru/runs/hotpages_{w.lower()}{SLRU_SUFFIX[layout]}.csv"
        return _resident_pages(src)
    raise ValueError(f"unknown strategy kind: {kind}")


def build_hotset(pages, classify, dest):
    """Write warmer-format hotset (page_number,file_offset) sorted by offset."""
    rows = sorted((classify[pn][1], pn) for pn in pages if pn in classify)
    with open(dest, "w", newline="") as f:
        f.write("page_number,file_offset\n")
        for off, pn in rows:
            f.write(f"{pn},{off}\n")
    return len(rows)


# ------------------------------------------------------------------------- execution
def write_deliver_script(workdir, db, hotset, method):
    """Tiny post-cold-script that warms <hotset> via <method> (paths baked in)."""
    fd, path = tempfile.mkstemp(prefix=f"deliver_{method}_", suffix=".sh", dir=workdir)
    with os.fdopen(fd, "w") as f:
        f.write("#!/bin/sh\n")
        f.write(f'WARM_METHOD={method} exec {shlex.quote(str(WARMER))} '
                f'{shlex.quote(str(db))} {shlex.quote(str(hotset))} {PAGE_SIZE}\n')
    os.chmod(path, 0o755)
    return path


def run_one(db, workload, hotset, method, recdir, use_drop_caches=True):
    """One harness invocation for one arm; returns parsed metrics (or None on failure)."""
    deliver = write_deliver_script(recdir, db, hotset, method)
    cmd = [str(BH), "--db", str(db), "--workload", str(workload),
           "--output", str(Path(recdir) / "ops.csv"),
           "--record-dir", str(recdir),
           "--cold-advice", "dontneed",
           "--post-cold-script", deliver,
           "--verify-hotset", str(hotset)]
    if use_drop_caches:
        cmd += ["--drop-caches-script", DROP_CACHES]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        m = parse_metrics(r.stderr + "\n" + r.stdout)
        if m["first_query_us"] is None:
            sys.stderr.write(f"  WARN no first_query in output:\n{r.stderr[-400:]}\n")
            return None
        return m
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        sys.stderr.write(f"  ERROR {e}\n")
        return None
    finally:
        try:
            os.unlink(deliver)
        except OSError:
            pass


# ------------------------------------------------------------------------ aggregation
def pctl(data, q):
    """qth percentile (0..100) by linear interpolation; safe for small n."""
    if not data:
        return None
    s = sorted(data)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100.0
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * frac


def aggregate(raw_rows, summary_path):
    groups = {}
    for row in raw_rows:
        if row["warmup"] == "1":
            continue
        key = (row["workload"], row["db"], row["strategy"], row["arm"])
        groups.setdefault(key, []).append(row)
    with open(summary_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["workload", "db", "strategy", "arm", "n", "ra_kb",
                    "fq_median", "fq_p95", "fq_min", "fq_stdev",
                    "delivery_pct_median", "preproc_us_median",
                    "e2e_median", "cold_pct_max"])
        for key, rows in sorted(groups.items()):
            fq = [float(r["first_query_us"]) for r in rows if r["first_query_us"]]
            e2e = [float(r["e2e_us"]) for r in rows if r["e2e_us"]]
            deliv = [float(r["delivery_pct"]) for r in rows if r["delivery_pct"]]
            pre = [float(r["preproc_us"]) for r in rows if r["preproc_us"]]
            cold = [float(r["cold_pct"]) for r in rows if r["cold_pct"]]
            w.writerow([*key, len(fq), rows[0]["ra_kb"],
                        f"{statistics.median(fq):.2f}" if fq else "",
                        f"{pctl(fq, 95):.2f}" if fq else "",
                        f"{min(fq):.2f}" if fq else "",
                        f"{statistics.pstdev(fq):.2f}" if len(fq) > 1 else "0",
                        f"{statistics.median(deliv):.1f}" if deliv else "",
                        f"{statistics.median(pre):.2f}" if pre else "",
                        f"{statistics.median(e2e):.2f}" if e2e else "",
                        f"{max(cold):.1f}" if cold else ""])


# ------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="General P0 cold-start runner (two-arm).")
    ap.add_argument("--workloads", default="A,B,C")
    ap.add_argument("--layouts", default="orig,vacuum,ta")
    ap.add_argument("--strategies", default=",".join(s["name"] for s in STRATEGIES))
    ap.add_argument("--pread-reps", type=int, default=3)
    ap.add_argument("--async-reps", type=int, default=10)
    ap.add_argument("--outdir", default=str(ROOT / "p0_runs"))
    ap.add_argument("--ra-kb", type=int, default=128, help="read_ahead_kb to pin via p0_env.sh")
    ap.add_argument("--no-pin-env", action="store_true", help="skip p0_env.sh (still records)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan + sample cmd, run nothing")
    ap.add_argument("--list", action="store_true", help="list cells and exit")
    args = ap.parse_args()

    wls = [x for x in args.workloads.split(",") if x]
    layouts = [x for x in args.layouts.split(",") if x]
    want = set(args.strategies.split(","))
    strats = [s for s in STRATEGIES if s["name"] in want]
    cells = [(w, ly, s) for w in wls for ly in layouts for s in strats]

    if args.list:
        for w, ly, s in cells:
            print(f"{w:2} {ly:6} {s['name']}")
        print(f"\n{len(cells)} cells x 2 arms; "
              f"pread {args.pread_reps} reps, async {args.async_reps} reps (+1 warmup each)")
        return

    outdir = Path(args.outdir)
    workdir = outdir / "work"
    if not args.dry_run:
        workdir.mkdir(parents=True, exist_ok=True)

    # capture / pin environment once
    env_line = "P0_ENV (not captured: dry-run)"
    ra_kb = args.ra_kb
    if not args.dry_run:
        try:
            ev = os.environ.copy()
            ev["RA_KB"] = str(args.ra_kb)
            cmd = ["sh", str(P0_ENV)] if args.no_pin_env else ["sh", str(P0_ENV), str(DBS[layouts[0]])]
            r = subprocess.run(cmd, capture_output=True, text=True, env=ev, timeout=60)
            for ln in (r.stdout + r.stderr).splitlines():
                if ln.startswith("P0_ENV"):
                    env_line = ln
            (outdir / "env.txt").write_text(env_line + "\n")
            m = re.search(r"ra_kb=(\d+)", env_line)
            if m:
                ra_kb = int(m.group(1))
        except (subprocess.SubprocessError, OSError) as e:
            sys.stderr.write(f"p0_env.sh failed ({e}); recording ra_kb={args.ra_kb} unpinned\n")
        sys.stderr.write(env_line + "\n")

    # pre-build hotsets per cell (frozen inputs; reused across reps/arms)
    hotsets = {}
    for w, ly, s in cells:
        classify = load_classify(ly)
        pages = select_pages(s, w, ly, classify)
        if args.dry_run:
            hotsets[(w, ly, s["name"])] = (None, len(pages))
            continue
        dest = workdir / f"hotset_{w}_{ly}_{s['name']}.csv"
        npg = build_hotset(pages, classify, dest)
        hotsets[(w, ly, s["name"])] = (dest, npg)

    if args.dry_run:
        print(env_line)
        print(f"\n{len(cells)} cells x 2 arms. plan:")
        for w, ly, s in cells:
            _, npg = hotsets[(w, ly, s["name"])]
            print(f"  {w} {ly:6} {s['name']:10} hotset={npg} pages  arms=[pread,async]")
        w, ly, s = cells[0]
        print("\nsample command (async arm, one rep):")
        print(f"  {BH} --db {DBS[ly]} --workload {WORKLOADS[w]} \\")
        print(f"    --cold-advice dontneed --drop-caches-script {DROP_CACHES} \\")
        print(f"    --post-cold-script <tmp: WARM_METHOD=fadvise warmer DB hotset {PAGE_SIZE}> \\")
        print(f"    --verify-hotset <hotset_{w}_{ly}_{s['name']}.csv>")
        print(f"\nreps: pread {args.pread_reps}+1warmup, async {args.async_reps}+1warmup, rep-major.")
        return

    arms = [("pread", args.pread_reps), ("async", args.async_reps)]
    max_keep = max(args.pread_reps, args.async_reps)
    raw_rows = []
    raw_path = outdir / "raw_p0.csv"
    cols = ["workload", "db", "strategy", "arm", "ra_kb", "rep", "warmup",
            "cold_pct", "delivery_pct", "first_query_us", "preproc_us",
            "e2e_us", "avg_us", "majflt", "minflt"]
    rawf = open(raw_path, "w", newline="")
    rw = csv.DictWriter(rawf, fieldnames=cols)
    rw.writeheader()

    # rep-major: outer rep, inner cells -> spreads slow machine drift across cells
    for rep in range(1, 1 + max_keep + 1):   # rep 1 = warmup (dropped in aggregate)
        warmup = "1" if rep == 1 else "0"
        for w, ly, s in cells:
            hotset, npg = hotsets[(w, ly, s["name"])]
            db, wl = DBS[ly], WORKLOADS[w]
            recdir = workdir / f"rec_{w}_{ly}_{s['name']}"
            recdir.mkdir(exist_ok=True)
            for arm, keep in arms:
                if rep > 1 + keep:
                    continue
                method = "pread" if arm == "pread" else "fadvise"
                m = run_one(db, wl, hotset, method, recdir)
                if m is None:
                    continue
                preproc = m["preproc_us"]
                fq = m["first_query_us"]
                e2e = (preproc + fq) if (preproc is not None and fq is not None) else None
                row = {"workload": w, "db": ly, "strategy": s["name"], "arm": arm,
                       "ra_kb": ra_kb, "rep": rep, "warmup": warmup,
                       "cold_pct": _fmt(m["cold_pct"]), "delivery_pct": _fmt(m["delivery_pct"]),
                       "first_query_us": _fmt(fq), "preproc_us": _fmt(preproc),
                       "e2e_us": _fmt(e2e), "avg_us": _fmt(m["avg_us"]),
                       "majflt": _fmt(m["majflt"]), "minflt": _fmt(m["minflt"])}
                rw.writerow(row)
                rawf.flush()
                raw_rows.append(row)
                sys.stderr.write(
                    f"[rep{rep} {'warm' if warmup=='1' else 'keep'}] {w} {ly} "
                    f"{s['name']} {arm}: fq={fq} delivery={m['delivery_pct']} cold={m['cold_pct']}\n")
    rawf.close()

    aggregate(raw_rows, outdir / "summary_p0.csv")
    sys.stderr.write(f"\ndone. raw={raw_path}  summary={outdir/'summary_p0.csv'}\n")


def _fmt(x):
    return "" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x))


if __name__ == "__main__":
    main()
