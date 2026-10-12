#!/usr/bin/env python3
"""Refresh every batch-derived number in paper/main.tex from one unified batch, atomically.

Each claim in tools/paper_refresh_claims.py is a snippet of main.tex whose numbers are written
as «expressions» over a batch. The tool renders a claim against a batch and compares the
result with the manuscript, character for character:

  validate <old>   every claim rendered from <old> must occur exactly once in main.tex, so
                   each expression is proven to reproduce the number it stands for
  apply <old> <new>
                   replace each <old> rendering with the <new> one (the only edit made)
  check <new>      every claim rendered from <new> must occur exactly once
  residual <old> <new>
                   after apply: no <old> rendering that changed, and no STALE literal, remains
  diff <old> <new> show what apply would change and which entries need new wording
  inventory <tag>  every numeric token in the body is inside an entry or a declared UNCHANGED span

Batches are tags of results/unified_<tag>. Standard library only.
"""
import csv
import glob
import re
import statistics
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEX = ROOT / "paper/main.tex"


# ----------------------------------------------------------------------------- data
class Batch:
    """Read-only view of one unified batch (results/unified_<tag>)."""

    def __init__(self, tag):
        self.tag = tag
        self.dir = ROOT / f"results/unified_{tag}"
        self.unc = {}
        with open(self.dir / "uncertainty.csv") as f:
            for r in csv.DictReader(f):
                self.unc[(r["workload"], r["db"], r["strategy"], r["arm"], r["metric"])] = r
        self.seed = {}                      # (seed, w, db, strategy, arm) -> summary row
        for p in sorted(self.dir.glob("seed[0-9][0-9]/summary.csv")):
            s = int(p.parent.name[4:])
            with open(p) as f:
                for r in csv.DictReader(f):
                    self.seed[(s, r["workload"], r["db"], r["strategy"], r["arm"])] = r
        self.seeds = sorted({k[0] for k in self.seed})
        self.mbud = {}
        mb = ROOT / f"results/matched_budget/unified_{tag}.csv"
        if mb.exists():
            with open(mb) as f:
                for r in csv.DictReader(f):
                    self.mbud[(r["metric"], r["workload"], r["arm"])] = r

    # ten-instance statistics (uncertainty.csv)
    def u(self, w, s, arm="async", metric="e2e_warm_us", db="orig", field="mean_pct"):
        return float(self.unc[(w, db, s, arm, metric)][field])

    def ulo(self, w, s, arm="async", metric="e2e_warm_us", db="orig"):
        return self.u(w, s, arm, metric, db, "ci_lo")

    def uhi(self, w, s, arm="async", metric="e2e_warm_us", db="orig"):
        return self.u(w, s, arm, metric, db, "ci_hi")

    def usign(self, w, s, arm="async", metric="e2e_warm_us", db="orig"):
        """'k/10' sign consistency string from uncertainty.csv."""
        return self.unc[(w, db, s, arm, metric)]["sign_consistency"]

    # one instance (seed 1 unless given)
    def s1(self, w, s, arm="async", col="e2e_warm_median", db="orig", seed=1):
        if s == "baseline":
            arm = "baseline"
        return float(self.seed[(seed, w, db, s, arm)][col])

    def base1(self, w, db="orig", seed=1):
        return self.s1(w, "baseline", col="fq_median", db=db, seed=seed)

    def e1(self, w, s, arm="async", col="e2e_warm_median", db="orig", seed=1):
        """Single-instance change vs the same-seed baseline, percent."""
        return 100.0 * (self.s1(w, s, arm, col, db, seed) / self.base1(w, db, seed) - 1)

    # across instances, median of the per-seed summary medians
    def med(self, w, s, arm="async", col="fq_median", db="orig", add=()):
        vals = []
        for sd in self.seeds:
            r = self.seed[(sd, w, db, s, "baseline" if s == "baseline" else arm)]
            vals.append(float(r[col]) + sum(float(r[c] or 0) for c in add))
        return statistics.median(vals)

    def mb(self, w, arm="async", field="mean_d", metric="e2e_warm_median"):
        return float(self.mbud[(metric, w, arm)][field])

    # pooled raw rows (kept reps of every seed)
    def _raw(self):
        if not hasattr(self, "_rawrows"):
            self._rawrows = []
            for p in sorted(self.dir.glob("seed[0-9][0-9]/raw.csv")):
                s = int(p.parent.name[4:])
                with open(p) as f:
                    for r in csv.DictReader(f):
                        if r["warmup"] == "0":
                            r["seed"] = s
                            self._rawrows.append(r)
        return self._rawrows

    def pmed(self, w, s, arm="async", col="delivery_pct", db="orig"):
        """Median over every kept rep of every seed."""
        return statistics.median(float(r[col]) for r in self._raw()
                                 if r["workload"] == w and r["db"] == db and r["strategy"] == s
                                 and r["arm"] == arm and r[col])

    def seedratio(self, w, num, den, arm="pread", col="deliver_us_median", db="orig"):
        """Mean over seeds of the per-seed ratio of two cells' medians."""
        return statistics.mean(float(self.seed[(sd, w, db, num, arm)][col]) /
                               float(self.seed[(sd, w, db, den, arm)][col]) for sd in self.seeds)


# ------------------------------------------------------------------------ formatting
def r0(x):
    """Round half away from zero to an int (the paper's rounding)."""
    return int(Decimal(repr(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rd(x, nd):
    """Round half away from zero to nd decimals, as a string."""
    q = Decimal(1).scaleb(-nd)
    return str(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def thou(n):
    """Integer with LaTeX thousands separator: 1013 -> 1{,}013."""
    s = f"{n:,}"
    return s.replace(",", "{,}")


def a0(x):
    """Magnitude, rounded: -27.1 -> '27'."""
    return str(abs(r0(x)))


def s0(x):
    """Signed integer for tables: '+81', '-38', '0'."""
    v = r0(x)
    return f"{v:+d}" if v != 0 else "0"


def ci(m, lo, hi):
    return f"\\ci{{{s0(m)}}}{{{s0(lo)},{s0(hi)}}}"


def us(x):
    return thou(r0(x))


def ratio(pct):
    """Percent change -> multiple of baseline: +769.6 -> 8.696."""
    return 1 + pct / 100.0


WORDS = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
         15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen",
         20: "twenty"}


def word(n):
    return WORDS[n]


# -------------------------------------------------------------------------- engine
EXPR = re.compile(r"«(.+?)»")
_MOD = None


def claims_module():
    global _MOD
    if _MOD is None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import paper_refresh_claims as pc
        _MOD = pc
    return _MOD


def render(template, batch):
    env = {k: v for k, v in globals().items() if callable(v)}
    env.update({k: v for k, v in vars(claims_module()).items() if not k.startswith("_")})
    env["v"] = batch
    return EXPR.sub(lambda m: str(eval(m.group(1), env)), template)


def try_render(template, batch):
    try:
        return render(template, batch), None
    except Exception as e:                       # an assert in a helper = wording must change
        return None, f"{type(e).__name__}: {e}"


def cmd_validate(tag):
    """Every CLAIM rendered from <tag>, and every STALE literal, occurs exactly once."""
    pc, b, tex, bad = claims_module(), Batch(tag), TEX.read_text(), 0
    for cid, tpl in pc.CLAIMS:
        s, err = try_render(tpl, b)
        n = tex.count(s) if s is not None else 0
        if err or n != 1:
            bad += 1
            print(f"FAIL {cid}: {err or f'rendered from {tag} occurs {n}x'}\n     {(s or tpl)[:200]}")
    for cid, old, _tpl in pc.STALE:
        if tex.count(old) != 1:
            bad += 1
            print(f"FAIL stale {cid}: literal occurs {tex.count(old)}x\n     {old[:200]}")
    print(f"{len(pc.CLAIMS) + len(pc.STALE) - bad}/{len(pc.CLAIMS) + len(pc.STALE)} entries "
          f"reproduce from unified_{tag}")
    return bad


def cmd_check(tag):
    """After apply: every CLAIM and STALE template rendered from <tag> occurs exactly once."""
    pc, b, tex, bad = claims_module(), Batch(tag), TEX.read_text(), 0
    for cid, tpl in pc.CLAIMS + [(c, t) for c, _o, t in pc.STALE]:
        s, err = try_render(tpl, b)
        n = tex.count(s) if s is not None else 0
        if err or n != 1:
            bad += 1
            print(f"FAIL {cid}: {err or f'rendered from {tag} occurs {n}x'}\n     {(s or tpl)[:200]}")
    total = len(pc.CLAIMS) + len(pc.STALE)
    print(f"{total - bad}/{total} entries match unified_{tag}")
    return bad


def cmd_diff(old, new):
    """Report what apply would change, flagging entries whose new rendering fails."""
    pc, bo, bn = claims_module(), Batch(old), Batch(new)
    for cid, tpl in pc.CLAIMS:
        so, _ = try_render(tpl, bo)
        sn, err = try_render(tpl, bn)
        if err:
            print(f"MANUAL {cid}: {err}")
        elif so != sn:
            print(f"CHANGE {cid}:\n   - {so}\n   + {sn}")
    for cid, old_lit, tpl in pc.STALE:
        sn, err = try_render(tpl, bn)
        print(f"STALE  {cid}:\n   - {old_lit}\n   + {sn if not err else 'MANUAL ' + err}")


def cmd_residual(old, new):
    """After apply: no <old> rendering that differs from its <new> one, and no STALE literal,
    may remain anywhere in main.tex."""
    pc, bo, bn, tex, bad, same = claims_module(), Batch(old), Batch(new), TEX.read_text(), 0, 0
    old_tpl = getattr(pc, "_OLD", {})             # templates as they stood before rewording
    old_lit = getattr(pc, "OLD_LITERAL", {})      # reworded sentences that had no template
    for cid, tpl in pc.CLAIMS:
        so = old_lit[cid] if cid in old_lit else render(old_tpl.get(cid, tpl), bo)
        sn = render(tpl, bn)
        if so == sn:
            same += 1
        elif tex.count(so):
            bad += 1
            print(f"RESIDUAL {cid}: the {old} text is still present\n     {so[:200]}")
    for cid, old_lit, _tpl in pc.STALE:
        if tex.count(old_lit):
            bad += 1
            print(f"RESIDUAL stale {cid}: {old_lit[:200]}")
    print(f"residual {old}: {bad} found; {len(pc.CLAIMS) - same} claims changed, {same} render "
          f"identically in both batches, {len(pc.STALE)} stale literals")
    return bad


def cmd_labels(ref):
    """Strategy labels, refs, cites and LaTeX labels must be unchanged against paper@<ref>:
    the refresh edits numbers, never names."""
    import subprocess
    from collections import Counter
    old = subprocess.run(["git", "-C", str(ROOT / "paper"), "show", f"{ref}:main.tex"],
                         capture_output=True, text=True, check=True).stdout
    new, bad = TEX.read_text(), 0
    for name, rx in (("strategy labels", r"\\strat\{[^}]*\}"), ("refs", r"\\ref\{[^}]*\}"),
                     ("cites", r"\\cite\{[^}]*\}"), ("labels", r"\\label\{[^}]*\}")):
        a, b = Counter(re.findall(rx, old)), Counter(re.findall(rx, new))
        if a != b:
            bad += 1
            print(f"FAIL {name}: {dict((a - b) + (b - a))}")
    print(f"names against paper@{ref}: {'unchanged' if not bad else f'{bad} kinds changed'}")
    return bad


def cmd_apply(old, new):
    if cmd_validate(old):
        sys.exit("refusing to apply: not every entry reproduces the old batch")
    pc, bo, bn, tex = claims_module(), Batch(old), Batch(new), TEX.read_text()
    edits, manual = [], []
    for cid, tpl in pc.CLAIMS:
        so = render(tpl, bo)
        sn, err = try_render(tpl, bn)
        if err:                       # the new value breaks the sentence's wording: leave it
            manual.append((cid, err))
            continue
        edits.append((so, sn))
    for cid, old_lit, tpl in pc.STALE:
        edits.append((old_lit, render(tpl, bn)))
    # locate every edit in the ORIGINAL text first, then splice right to left, so no edit
    # can match text another edit has just written
    spans = []
    for so, sn in edits:
        i = tex.find(so)
        spans.append((i, i + len(so), sn))
    spans.sort()
    for (a, z, _), (a2, _z2, _) in zip(spans, spans[1:]):
        if a2 < z:
            sys.exit(f"overlapping entries at offset {a2}; make the snippets disjoint")
    for a, z, sn in reversed(spans):
        tex = tex[:a] + sn + tex[z:]
    TEX.write_text(tex)
    print(f"applied {len(edits)} entries ({old} -> {new})")
    for cid, err in manual:
        print(f"LEFT FOR REWORDING {cid}: {err}")


TOKEN = re.compile(r"\d[\d{},.]*\d|\d")


def cmd_inventory(tag):
    """Every numeric token in the body is inside a CLAIM/STALE span or inside a span that
    UNCHANGED declares (line regex, span regex, reason)."""
    pc, b, tex = claims_module(), Batch(tag), TEX.read_text()
    spans = []
    for cid, tpl in pc.CLAIMS + [(c, t) for c, _o, t in pc.STALE]:
        s, _ = try_render(tpl, b)
        i = tex.find(s) if s else -1
        if i >= 0:
            spans.append((i, i + len(s)))
    for cid, old, _t in pc.STALE:                 # before apply the literal is what is there
        i = tex.find(old)
        if i >= 0:
            spans.append((i, i + len(old)))
    start, end = tex.index("\\begin{document}"), tex.index("\\end{document}")
    first_line = tex[:start].count("\n") + 1
    pos, uncovered = start, []
    for ln, line in enumerate(tex[start:end].split("\n"), first_line):
        if not line.lstrip().startswith("%"):
            masked = re.sub(r"\\(cite|ref|label|includegraphics|setlength|begin|end|cmidrule|"
                            r"multicolumn)\*?(\[[^\]]*\])?(\{[^}]*\})+",
                            lambda m: " " * len(m.group()), line)
            masked = re.sub(r"p\{[0-9.]+\\(linewidth|textwidth)\}|[0-9.]+\\(linewidth|textwidth|"
                            r"columnwidth)", lambda m: " " * len(m.group()), masked)
            for m in TOKEN.finditer(masked):
                at = pos + m.start()
                if any(a <= at < z for a, z in spans):
                    continue
                # unchanged only if the token lies inside a declared span of a declared line
                if any(re.search(lrx, line) and any(s.start() <= m.start() and m.end() <= s.end()
                                                    for s in re.finditer(srx, line))
                       for lrx, srx, _why in pc.UNCHANGED):
                    continue
                uncovered.append((ln, m.group(), line[max(0, m.start() - 60):m.end() + 25]))
        pos += len(line) + 1
    for ln, tok, ctx in uncovered:
        print(f"L{ln}: {tok!r:10} ...{ctx}...")
    print(f"{len(uncovered)} numeric tokens neither in an entry nor declared unchanged")
    return len(uncovered)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "validate":
        sys.exit(1 if cmd_validate(args[0]) else 0)
    if cmd == "check":
        sys.exit(1 if cmd_check(args[0]) else 0)
    if cmd == "diff":
        cmd_diff(args[0], args[1])
        return
    if cmd == "apply":
        cmd_apply(args[0], args[1])
        return
    if cmd == "residual":
        sys.exit(1 if cmd_residual(args[0], args[1]) else 0)
    if cmd == "labels":
        sys.exit(1 if cmd_labels(args[0]) else 0)
    if cmd == "inventory":
        sys.exit(1 if cmd_inventory(args[0]) else 0)
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
