#!/usr/bin/env python3
"""analyze_r1.py — the registered outcome of prereg/R1a.md and prereg/R1b.md.

    python3 -I scripts/analyze_r1.py results/<date>-<git-sha>-<config-hash>  [--out notes/r1-findings.md]

Reads only a results/ directory written by scripts/run_r1.sh (it must hold run_r1.sh,
config.txt and DONE) and the frozen predictions in prereg/design/. Writes the report
(default notes/r1-findings.md) and prints it. Applies each decision rule as registered:

R1a (prereg/R1a.md):
  primary metric, B group, per run: no pager miss on the probe path's interior pages
      (root page and the probe key's second-level page) -> root_reads + interior_reads == 0
  validity: OS cold gate (resident <= 1% of the file after the reset); DB read-only
      (DB sha256 unchanged since config.txt); xRead page fetches == CACHE_MISS delta
  primary check: every B run vs its frozen prediction row, page by page
  decision per workload, N = 1000 only, effective n = 10 instances:
      p = mean over instances of the instance's interior-hit proportion;
      95% percentile bootstrap over instances (10,000 resamples)
      I if CI lower >= 0.95; II if CI upper <= 0.50; otherwise undetermined
R1b (prereg/R1b.md):
  primary metric, per run: resident fraction of the path interior before the probe
  validity: r = inf control path-interior >= 0.95; memcg charge check pass; no oom_kill;
      DB read-only; process CPUs as registered (harness 10, anon 12, competitor 14)
  decision per (arm, workload, level), n = instances, 95% percentile bootstrap:
      S if CI lower >= 0.90; E if CI upper <= 0.50; otherwise undetermined
  conclusion per (arm, workload): highest level (largest r) judged E, or none;
      undetermined levels above it and non-monotone patterns are listed, not smoothed
  sensitivity cells: descriptive only
"""
import argparse
import csv
import hashlib
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRED = REPO / "prereg/design/R1a_probe_predictions.csv"
DB = REPO / "pipeline/preparation/layout_rewriter/runs/test.db"
SMOKE = Path.home() / "verify-runs/sqlite-research"
BOOT = 10_000
RNG_SEED = 20261111
LEVELS = ["1.0", "0.5", "0.25", "0.1"]          # largest budget first
R1A_LO, R1A_HI = 0.95, 0.50
R1B_LO, R1B_HI = 0.90, 0.50
CONTROL_MIN = 0.95
COLD_MAX = 0.01
CPUS = {"harness": "10", "anon": "12", "stream": "14", "hot": "14"}

RE_LAYER = re.compile(r"layer_residency point=(?P<pt>\S+) source=mincore root=(\d+)/(\d+) interior=(\d+)/(\d+) "
                      r"path_interior=(\d+)/(\d+) leaf=(\d+)/(\d+) path_leaf=(\d+)/(\d+)")
RE_MADV = re.compile(r"resident SQLite pages after madvise:\s+(\d+)/(\d+)")
RE_PROBE = re.compile(r"pager_probe op=(\d+) key=(\d+) probe_l2=(\d+) probe_leaf=(\d+) page1_reads=(\d+) "
                      r"source=vfs\+db_status root_reads=(\d+) interior_reads=(\d+) path_interior_reads=(\d+) "
                      r"leaf_reads=(\d+) unmapped_reads=(\d+) partial_reads=(\d+) cache_hit=(-?\d+) cache_miss=(-?\d+)")
RE_FQ = re.compile(r"first_query_latency_us=([\d.]+)")
RE_CHARGE = re.compile(r"cgroup_charge_check=(\w+)")
RE_OOM = re.compile(r"memstat point=\S+ .*?oom_kill=(-?\d+)")
RE_CPUS = re.compile(r"^cpus who=(\w+) pid=\d+ allowed=(\S+)", re.M)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def boot_ci(values):
    rng = random.Random(RNG_SEED)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(BOOT))
    return means[int(0.025 * BOOT)], means[int(0.975 * BOOT) - 1]


def load_run(run_dir):
    """The attempt that finished (.done marks the run; the last attempt is the finished one)."""
    attempts = sorted(run_dir.glob("attempt-*"), key=lambda p: int(p.name.split("-")[1]))
    if not attempts:
        return None
    a = attempts[-1]
    logs = sorted(a.glob("run-*.log"))
    text = logs[0].read_text() if logs else ""
    return {"dir": a, "done": (run_dir / ".done").exists(), "attempts": len(attempts), "text": text}


def layer(text, point):
    for m in RE_LAYER.finditer(text):
        if m.group("pt") == point:
            g = list(map(int, m.groups()[1:]))
            return {"root": g[0:2], "interior": g[2:4], "path_interior": g[4:6], "leaf": g[6:8], "path_leaf": g[8:10]}
    return None


def cold_fraction(text):
    lay = layer(text, "after-reset")
    if lay:
        res = lay["root"][0] + lay["interior"][0] + lay["leaf"][0]
        tot = lay["root"][1] + lay["interior"][1] + lay["leaf"][1]
        return res / tot, "after-reset layer_residency"
    m = RE_MADV.search(text)
    if m:
        return int(m.group(1)) / int(m.group(2)), "resident after madvise (default path)"
    return None, "no residency line"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir", type=Path)
    ap.add_argument("--out", type=Path, default=REPO / "notes/r1-findings.md")
    args = ap.parse_args()
    R = args.results_dir.resolve()
    for need in ("run_r1.sh", "config.txt", "DONE"):
        if not (R / need).exists():
            sys.exit(f"analyze_r1: {R} lacks {need}: only complete run_r1.sh output is analysed")
    config = (R / "config.txt").read_text()
    db_sha_cfg = re.search(r"^test\.db ([0-9a-f]{64})", config, re.M).group(1)
    pred_sha_cfg = re.search(r"^prereg/design/R1a_probe_predictions\.csv ([0-9a-f]{64})", config, re.M).group(1)
    if sha256(PRED) != pred_sha_cfg:
        sys.exit("analyze_r1: prereg/design/R1a_probe_predictions.csv differs from the copy hashed in config.txt")
    db_unchanged = sha256(DB) == db_sha_cfg

    out = []
    w = out.append
    w("# R1 findings: registered outcome of prereg/R1a.md and prereg/R1b.md\n")
    w(f"Generated by `python3 -I scripts/analyze_r1.py {R.relative_to(REPO)}` from that directory only.")
    w(f"Input: `{R.relative_to(REPO)}` ({(R / 'DONE').read_text().strip().splitlines()[0]}); "
      f"config hash and git sha in `config.txt`. Bootstrap: percentile, {BOOT:,} resamples over instances, "
      f"random seed {RNG_SEED}.\n")
    w(f"DB read-only check: sha256 of test.db now {'equals' if db_unchanged else 'DIFFERS FROM'} the value in "
      f"config.txt{'' if db_unchanged else ' -> every run is void'}.\n")

    # ------------------------------------------------------------------ R1a
    preds = {(r["workload"], int(r["seed"]), int(r["N"])): r for r in csv.DictReader(open(PRED))}
    a_runs = {}
    for d in sorted((R / "R1a").iterdir()):
        m = re.fullmatch(r"([BC])-([ABC])-s(\d+)-N(\d+)-r(\d+)", d.name)
        if m:
            g, wl, s, N, rep = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))
            a_runs[(g, wl, s, N, rep)] = load_run(d)
    voids = defaultdict(lambda: defaultdict(int))     # cell -> reason -> count
    void_runs = defaultdict(int)                      # cell -> void runs
    cells_total = defaultdict(int)
    mism = []
    agree = defaultdict(lambda: [0, 0])               # (wl, N) -> [agree, total]
    hit = defaultdict(list)                           # (wl, seed) -> [0/1] at N=1000, valid B runs
    rep_values = defaultdict(set)                     # (wl, seed, N) -> observed signatures over reps
    fq = defaultdict(lambda: defaultdict(list))       # (g, wl, seed) -> [first query us] N=1000 valid
    for (g, wl, s, N, rep), run in sorted(a_runs.items()):
        cell = f"R1a {g} {wl} N={N}"
        cells_total[cell] += 1
        if run is None or not run["done"]:
            voids[cell]["not finished"] += 1
            void_runs[cell] += 1
            continue
        t = run["text"]
        reasons = []
        if not db_unchanged:
            reasons.append("DB changed")
        frac, src = cold_fraction(t)
        if frac is None or frac > COLD_MAX:
            reasons.append(f"cold gate: {frac:.3f} of file resident after reset ({src})" if frac is not None else "cold gate: no residency line")
        pp = RE_PROBE.search(t) if g == "B" else None
        if g == "B":
            if pp is None:
                reasons.append("no pager_probe line")
            else:
                v = list(map(int, pp.groups()))
                fetches = v[4] + v[5] + v[6] + v[8] + v[9]
                if fetches != v[12]:
                    reasons.append(f"xRead fetches {fetches} != CACHE_MISS {v[12]}")
        void_runs[cell] += bool(reasons)
        for r in reasons:
            voids[cell][re.sub(r"[\d.]+ of file", "x of file", r)] += 1
        if g == "B" and pp is not None:
            v = list(map(int, pp.groups()))
            obs = {"page1": v[4] == 0, "root": v[5] == 0, "l2": v[6] == 0, "leaf": v[8] == 0}
            pr = preds[(wl, s, N)]
            want = {"page1": pr["pred_page1_hit"] == "1", "root": pr["pred_root_hit"] == "1",
                    "l2": pr["pred_l2_hit"] == "1", "leaf": pr["pred_leaf_hit"] == "1"}
            rep_values[(wl, s, N)].add(tuple(sorted(obs.items())))
            ok = True
            for page, page_no in (("page1", 1), ("root", 2), ("l2", int(pr["probe_l2_page"])), ("leaf", int(pr["probe_leaf_page"]))):
                if obs[page] != want[page]:
                    ok = False
                    cause = ("schema init on the measuring connection (before-cold) puts page 1 in the pager; "
                             "the simulation starts every N=0 probe with an empty pager"
                             if page == "page1" and N == 0 and obs[page] else "unexplained: investigate")
                    mism.append((wl, s, N, rep, page, page_no, "hit" if want[page] else "miss",
                                 "hit" if obs[page] else "miss", cause))
            if int(pr["probe_key"]) != v[1] or int(pr["probe_l2_page"]) != v[2] or int(pr["probe_leaf_page"]) != v[3]:
                ok = False
                mism.append((wl, s, N, rep, "probe identity", 0, f"key {pr['probe_key']} l2 {pr['probe_l2_page']} leaf {pr['probe_leaf_page']}",
                             f"key {v[1]} l2 {v[2]} leaf {v[3]}", "unexplained: investigate"))
            agree[(wl, N)][0] += ok
            agree[(wl, N)][1] += 1
            if N == 1000 and not reasons:
                hit[(wl, s)].append(1 if v[5] + v[6] == 0 else 0)
        if N == 1000 and not reasons:
            fq[(g, wl, s)]["fq"].append(float(RE_FQ.search(t).group(1)))

    w("## R1a: pager residency of the probe path under SQLite defaults (B group)\n")
    w("### Primary check: B runs vs frozen predictions (`prereg/design/R1a_probe_predictions.csv`)\n")
    w("| workload | N | runs agreeing page by page | runs |")
    w("|---|---|---|---|")
    for (wl, N), (a, n) in sorted(agree.items()):
        w(f"| {wl} | {N} | {a} | {n} |")
    w(f"\nMismatches: {len(mism)} (every one listed; a mismatch does not change the decision).\n")
    if mism:
        w("| workload | seed | N | rep | page | page no. | predicted | observed | cause |")
        w("|---|---|---|---|---|---|---|---|---|")
        for m in mism:
            w("| " + " | ".join(map(str, m)) + " |")
    unstable = [(k, len(v)) for k, v in rep_values.items() if len(v) > 1]
    w(f"\nCells whose repeated runs disagree with each other: {len(unstable)}"
      + ("" if not unstable else " -> " + ", ".join(f"{k[0]} s{k[1]} N={k[2]}" for k, _ in unstable)) + "\n")
    w("### Decision (N = 1000 only; rule: I if CI lower >= 0.95, II if CI upper <= 0.50, else undetermined)\n")
    w("| workload | effective n (instances) | p | 95% CI | decision |")
    w("|---|---|---|---|---|")
    for wl in "ABC":
        inst = [statistics.fmean(hit[(wl, s)]) for s in range(1, 11) if hit.get((wl, s))]
        if not inst:
            w(f"| {wl} | 0 | - | - | undetermined (no valid runs) |")
            continue
        lo, hi = boot_ci(inst)
        dec = "I (interior in pager)" if lo >= R1A_LO else "II (interior not in pager)" if hi <= R1A_HI else "undetermined"
        w(f"| {wl} | {len(inst)} | {statistics.fmean(inst):.3f} | [{lo:.3f}, {hi:.3f}] | {dec} |")

    # ------------------------------------------------------------------ R1b
    b_runs = {}
    for d in sorted((R / "R1b").iterdir()):
        m = re.fullmatch(r"(stream|hot|sens-\w+)-([ABC])-r([\d.]+|inf)-s(\d+)", d.name)
        if m:
            b_runs[(m.group(1), m.group(2), m.group(3), int(m.group(4)))] = load_run(d)
    res = defaultdict(dict)                           # (arm, wl, lv) -> seed -> path interior fraction
    fqb = defaultdict(dict)
    oom_counts = defaultdict(int)
    charge = defaultdict(lambda: defaultdict(int))
    for (arm, wl, lv, s), run in sorted(b_runs.items()):
        cell = f"R1b {arm} {wl} r={lv}"
        cells_total[cell] += 1
        if run is None or not run["done"]:
            voids[cell]["not finished"] += 1
            void_runs[cell] += 1
            continue
        t = run["text"]
        reasons = []
        if not db_unchanged:
            reasons.append("DB changed")
        ch = RE_CHARGE.search(t)
        charge[cell][ch.group(1) if ch else "missing"] += 1
        if not ch or ch.group(1) != "pass":
            reasons.append("memcg charge check not pass")
        ooms = [int(x) for x in RE_OOM.findall(t)]
        if ooms and max(ooms) > 0:
            oom_counts[cell] += 1
            reasons.append("oom_kill")
        cpus = dict(RE_CPUS.findall(t))
        expect = {"harness": CPUS["harness"]}
        if lv != "inf":
            expect["anon"] = CPUS["anon"]
            expect["hot" if arm == "hot" else "stream"] = CPUS["hot" if arm == "hot" else "stream"]
        for who, c in expect.items():
            if cpus.get(who) != c:
                reasons.append(f"cpus {who}={cpus.get(who)} (registered {c})")
        lay = layer(t, "after-reset")
        if lay is None:
            reasons.append("no before-probe residency")
        else:
            frac = lay["path_interior"][0] / lay["path_interior"][1]
            if lv == "inf" and frac < CONTROL_MIN:
                reasons.append(f"control path interior < {CONTROL_MIN}")
        void_runs[cell] += bool(reasons)
        for r in reasons:
            voids[cell][r] += 1
        if not reasons:
            res[(arm, wl, lv)][s] = lay["path_interior"][0] / lay["path_interior"][1]
            fqb[(arm, wl, lv)][s] = float(RE_FQ.search(t).group(1))

    w("\n## R1b: path-interior residency under natural cgroup pressure (C config)\n")
    w("Rule per (arm, workload, level): S if CI lower >= 0.90, E if CI upper <= 0.50, else undetermined. "
      "r = inf is the control and is not judged.\n")
    w("| arm | workload | level | n | mean | 95% CI | decision |")
    w("|---|---|---|---|---|---|---|")
    verdict = {}
    for arm, wls in (("stream", "ABC"), ("hot", "A")):
        for wl in wls:
            for lv in LEVELS:
                vals = list(res[(arm, wl, lv)].values())
                if not vals:
                    verdict[(arm, wl, lv)] = "undetermined"
                    w(f"| {arm} | {wl} | {lv} | 0 | - | - | undetermined (no valid runs) |")
                    continue
                lo, hi = boot_ci(vals)
                dec = "S" if lo >= R1B_LO else "E" if hi <= R1B_HI else "undetermined"
                verdict[(arm, wl, lv)] = dec
                w(f"| {arm} | {wl} | {lv} | {len(vals)} | {statistics.fmean(vals):.3f} | [{lo:.3f}, {hi:.3f}] | {dec} |")
    w("\n### Conclusion per arm and workload (highest level judged E, or none)\n")
    for arm, wls in (("stream", "ABC"), ("hot", "A")):
        for wl in wls:
            seq = [verdict[(arm, wl, lv)] for lv in LEVELS]
            e_levels = [lv for lv, d in zip(LEVELS, seq) if d == "E"]
            if not e_levels:
                txt = "none"
            else:
                top = e_levels[0]
                above = [lv for lv in LEVELS[:LEVELS.index(top)] if verdict[(arm, wl, lv)] == "undetermined"]
                txt = f"{top}x" + (f"; undetermined above it: {', '.join(above)}" if above else "")
            first_e = next((i for i, d in enumerate(seq) if d == "E"), None)
            mono = first_e is None or all(d == "E" for d in seq[first_e:])
            w(f"- {arm}, {wl}: highest level turning cold = {txt}. Per level (1.0, 0.5, 0.25, 0.1): "
              f"{', '.join(seq)}{'' if mono else ' (non-monotone, listed as is)'}")

    # ------------------------------------------------------------------ voids
    w("\n## Void counts, OOM and charge checks (every cell)\n")
    w("| cell | runs | void | reasons | OOM-killed runs | charge check |")
    w("|---|---|---|---|---|---|")
    for cell in sorted(cells_total):
        vs = voids.get(cell, {})
        nvoid_text = "; ".join(f"{k}: {v}" for k, v in sorted(vs.items())) or "-"
        nvoid = void_runs.get(cell, 0)
        ch = "; ".join(f"{k} {v}" for k, v in sorted(charge.get(cell, {}).items())) or "n/a"
        w(f"| {cell} | {cells_total[cell]} | {nvoid} | {nvoid_text} | {oom_counts.get(cell, 0) if cell.startswith('R1b') else 'n/a'} | {ch} |")
    w("\n(`void` counts runs; a void run can carry more than one reason, so reason counts can add up to more.)\n")

    # ------------------------------------------------------------------ smoke
    smoke = sorted(p.name for p in SMOKE.glob("r1[ab]-*")) if SMOKE.exists() else []
    w("## Smoke runs\n")
    w(f"One smoke run per registered cell (seed 1, one run each: {sum(n.startswith('r1a-') for n in smoke)} R1a and "
      f"{sum(n.startswith('r1b-') for n in smoke)} R1b directories under `{SMOKE}`) preceded the registered runs, "
      f"after the prereg commit and with the same harness build, through `.claude/skills/verify/verify.sh harness`. "
      f"They are excluded: this report reads only `{R.relative_to(REPO)}`.\n")

    # ------------------------------------------------------------------ not registered
    w("## Open observations (NOT REGISTERED: descriptive, no decision attached)\n")
    w("Secondary metrics named in the preregs, reported without a rule:\n")
    for wl in "ABC":
        pairs = [statistics.fmean(fq[("B", wl, s)]["fq"]) - statistics.fmean(fq[("C", wl, s)]["fq"])
                 for s in range(1, 11) if fq[("B", wl, s)]["fq"] and fq[("C", wl, s)]["fq"]]
        if pairs:
            lo, hi = boot_ci(pairs)
            w(f"- R1a {wl}: first query B minus C, paired by instance (valid runs only): mean {statistics.fmean(pairs):.1f} us, "
              f"95% CI [{lo:.1f}, {hi:.1f}], n = {len(pairs)}")
        else:
            w(f"- R1a {wl}: B minus C first query not computable (no instance with valid runs in both groups)")
    for (arm, wl, lv), d in sorted(fqb.items()):
        if lv == "inf" or arm.startswith("sens"):
            continue
        ctrl = fqb.get(("stream", wl, "inf"), {})
        pairs = [d[s] - ctrl[s] for s in d if s in ctrl]
        if pairs:
            lo, hi = boot_ci(pairs)
            w(f"- R1b {arm} {wl} r={lv}: first query minus r=inf, paired: mean {statistics.fmean(pairs):.1f} us, "
              f"95% CI [{lo:.1f}, {hi:.1f}], n = {len(pairs)}")
    for (arm, wl, lv), vals in sorted(res.items()):
        if arm.startswith("sens"):
            v = list(vals.values())
            w(f"- sensitivity {arm} {wl} r={lv}: path interior mean {statistics.fmean(v):.3f} over n = {len(v)}")

    text = "\n".join(out) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
