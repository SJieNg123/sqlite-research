"""Batch-derived numbers in paper/main.tex, for tools/paper_refresh.py.

CLAIMS    (id, template): a main.tex snippet whose batch numbers are «expressions». Rendered
          from the current batch it must reproduce the manuscript exactly.
STALE     (id, literal, template): numbers that do not come from the current batch at all
          (older batches); the literal is replaced by the template rendered from the new one.
UNCHANGED (line regex, token regex, reason): numbers that do not come from a unified batch.

Helpers below assert the direction a sentence states ("reduces", "above"), so a value that
changes sign fails loudly instead of being written into the wrong wording.
"""
import math
import re
import statistics

import paper_refresh as P

ABC = ("A", "B", "C")
ALL4 = ("A", "B", "C", "C_hit")


def _standalone(lit):
    """The literal as a whole number: not part of a label (Skel-5, Skel+10, Dump-28, K=10),
    a word, or a longer number (37 vs 7, 1.07 vs 1)."""
    return re.compile(r"(?<![A-Za-z0-9.])(?<![A-Za-z][-+])" + re.escape(lit) + r"(?![0-9A-Za-z])(?!\.[0-9])")


def T(snippet, *subs):
    """Turn a manuscript snippet into a template: each (literal, expr) replaces the next
    standalone occurrence of literal, left to right."""
    out, rest = "", snippet
    for lit, expr in subs:
        m = _standalone(lit).search(rest) if lit[0].isdigit() or lit[0] in "-+" else None
        i = m.start() if m else rest.index(lit)
        out += rest[:i] + "«" + expr + "»"
        rest = rest[i + len(lit):]
    return out + rest


def red(x):
    """A reduction stated as a positive magnitude: x must be negative."""
    assert P.r0(x) < 0, f"expected a reduction, got {x:+.1f}"
    return str(-P.r0(x))


def inc(x):
    """An increase stated as a positive magnitude: x must be positive."""
    assert P.r0(x) > 0, f"expected an increase, got {x:+.1f}"
    return str(P.r0(x))


def same(*vals):
    """One number standing for several cells: they must round alike."""
    assert len(set(vals)) == 1, f"cells differ: {vals}"
    return vals[0]


def pc(x):
    """Integer percent with thousands separator, sign-free: 1339.2 -> 1{,}339."""
    return P.thou(abs(P.r0(x)))


def sgnpct(x):
    """'+31\\%' / '$-$8\\%' as in Table e2e-ac."""
    v = P.r0(x)
    return (f"+{v}" if v > 0 else (f"$-${-v}" if v < 0 else "0")) + "\\%"


def cell(v, w, s, col):
    """Table e2e-ac cell: '644 (+31\\%)'."""
    x = v.s1(w, s, col=col)
    return f"{P.r0(x)} ({sgnpct(100 * (x / v.base1(w) - 1))})"


def fqred(v, w, s):
    """Seed-1 first-query change, percent."""
    return v.e1(w, s, col="fq_median")


def lohi(vals, i):
    vals = [P.r0(x) for x in vals]
    return min(vals) if i == 0 else max(vals)


def open_cells(v):
    """e2e_ext - e2e_warm per Table e2e-ac cell: the warmer's open cost there."""
    return [v.s1(w, s, col="e2e_median") - v.s1(w, s, col="e2e_warm_median")
            for w in ("A", "C") for s in ("layers_5", "2d", "2f_slru")]


MAIN14 = ("layers_5", "layers_92", "2d", "2e_K10", "2e_K500", "2f_top14", "2f_top28",
          "2f_top100", "2f_top500", "2f_slru", "leaf_freq_K10", "leaf_rand_K10",
          "learned_markov_14", "learned_markov_28")


def open_spread(v, workloads):
    """Largest per-instance spread of the warmer's open cost across the family-A strategies."""
    return max(max(vals) - min(vals) for sd in v.seeds for w in workloads
               for vals in [[float(v.seed[(sd, w, "orig", s, "async")]["open_us_median"]) for s in MAIN14]])


def ms(x, nd):
    return P.rd(x / 1000.0, nd)


def sg1(x):
    """Signed one-decimal number for math mode: -0.5 -> '-0.5', 0.9 -> '+0.9'."""
    s = P.rd(x, 1)
    return s if s.startswith("-") else "+" + s


def verdict_word(v, w, s, metric="e2e_warm_us", arm="async"):
    """The Table ablation label: robust increase / decrease, or tie."""
    vd = v.unc[(w, "orig", s, arm, metric)]["verdict"]
    m = v.u(w, s, arm, metric)
    if vd == "robust":
        return "increase" if m > 0 else "decrease"
    if vd == "tie":
        return "tie"
    raise AssertionError(f"{w} {s}: verdict {vd!r} has no label in the table")


def is_tie(v, w, s, metric="e2e_warm_us", arm="async"):
    assert verdict_word(v, w, s, metric, arm) == "tie", f"{w} {s} is no longer a tie"
    return ""


def crosses_zero(v, w, s, metric="first_query_us", arm="async"):
    assert v.ulo(w, s, arm, metric) < 0 < v.uhi(w, s, arm, metric), f"{w} {s} {metric} CI excludes 0"
    return ""


def bimodal(v, w, s, low):
    """Mean per-seed effect of the low (first query misses) or high cluster; the clusters must
    be separated by at least 20 points around -50."""
    eff = [v.e1(w, s, seed=sd) for sd in v.seeds]
    lo, hi = [x for x in eff if x < -50], [x for x in eff if x >= -50]
    assert lo and hi and max(lo) < -60 and min(hi) > -45, f"clusters not separated: {sorted(eff)}"
    return str(-P.r0(statistics.mean(lo if low else hi)))


SMALLWORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
              8: "eight", 9: "nine", 10: "ten"}


def sw(n):
    return SMALLWORDS[n]


def per_seed(v, w, s, arm="async", metric="e2e_warm_us", db="orig"):
    raw = v.unc[(w, db, s, arm, metric)]["per_seed"]
    return [float(x.split("=")[1]) for x in raw.split(";")]


def nsign(v, w, s, arm="async", metric="e2e_warm_us", db="orig"):
    """Instances agreeing in sign with the mean (the 'k' of 'k/10')."""
    return int(v.usign(w, s, arm, metric, db).split("/")[0])


def under(x, ref):
    """Single-instance value that understates (is smaller in magnitude than) ref."""
    assert abs(P.r0(x)) < abs(P.r0(ref)), f"{x:+.1f} does not understate {ref:+.1f}"
    return P.s0(x)


def over(x, ref):
    assert abs(P.r0(x)) > abs(P.r0(ref)), f"{x:+.1f} does not overstate {ref:+.1f}"
    return P.s0(x)


def cross0(v, w, s, arm="async", metric="e2e_warm_us", db="orig"):
    assert v.ulo(w, s, arm, metric, db) < 0 < v.uhi(w, s, arm, metric, db), f"{w} {s} {db} CI excludes 0"
    return ""


def maxgap(v, strategies):
    """Largest |window-chunked - per-page| ten-instance mean over both boundaries."""
    return max(abs(v.u(w, s, "async_win", m) - v.u(w, s, "async", m))
               for w in ALL4 for s in strategies for m in ("e2e_warm_us", "e2e_us"))


S12 = ("layers_5", "layers_92", "2d", "2e_K10", "2e_K500", "2f_top14", "2f_top28", "2f_top100",
       "2f_top500", "2f_slru", "leaf_freq_K10", "leaf_rand_K10")


def keep_dir(v):
    """10x cells whose ten-instance mean keeps its sign against the reference size."""
    return sum((v.u(w, s) > 0) == (v.u(w, s, db="1gb") > 0) for w in ABC for s in S12)


def regress_to_neutral(v):
    """Sign changes that regress at the reference size (CI > 0) and are neutral at 10x."""
    return sum(1 for w in ABC for s in S12
               if (v.u(w, s) > 0) != (v.u(w, s, db="1gb") > 0)
               and v.ulo(w, s) > 0 and v.ulo(w, s, db="1gb") < 0 < v.uhi(w, s, db="1gb"))


def best_layout(v, w, db):
    """Seed-1 warm-process latency of the strategy fastest under the default layout."""
    best = min(S12, key=lambda s: v.s1(w, s))
    return v.s1(w, best, db=db)


def lratio(v, w, s):
    """Mean over instances of clustered/default warm-process latency."""
    return statistics.mean(v.s1(w, s, db="ta", seed=sd) / v.s1(w, s, seed=sd) for sd in v.seeds)


def nslower(v, w, s):
    return sum(v.s1(w, s, db="ta", seed=sd) > v.s1(w, s, seed=sd) for sd in v.seeds)


def overlap(v, w, s1, s2, arm="async_win", metric="e2e_warm_us"):
    """Two cells whose 95% CIs overlap: the sentence calls them level, not ordered."""
    assert v.ulo(w, s1, arm, metric) <= v.uhi(w, s2, arm, metric) and \
        v.ulo(w, s2, arm, metric) <= v.uhi(w, s1, arm, metric), f"{w} {s1} vs {s2}: CIs separate"
    return ""


def of_ten(n):
    """'all ten' or 'nine of ten', for counts over the ten instances."""
    return "all ten" if n == 10 else f"{sw(n)} of ten"


def r2n_500(v):
    """Regress-to-neutral sign changes at 10x, asserting they are all 500-page sets."""
    cells = [s for w in ABC for s in S12
             if (v.u(w, s) > 0) != (v.u(w, s, db="1gb") > 0)
             and v.ulo(w, s) > 0 and v.ulo(w, s, db="1gb") < 0 < v.uhi(w, s, db="1gb")]
    assert cells and set(cells) <= {"2e_K500", "2f_top500"}, f"not all 500-page sets: {cells}"
    return sw(len(cells))


def neutral_same_sign(v, w, s):
    """Regresses at the reference size, neutral at 10x, mean keeps its (positive) sign."""
    assert v.ulo(w, s) > 0 and v.ulo(w, s, db="1gb") < 0 < v.uhi(w, s, db="1gb") \
        and P.r0(v.u(w, s, db="1gb")) > 0, f"{w} {s} is not regress-to-neutral with its sign kept"
    return ""


def count_is(n, expected):
    """A count the sentence states in words ('on all ten instances')."""
    assert n == expected, f"count is {n}, sentence says {expected}"
    return ""


def mb_cells(v, f):
    return [v.mb(w, a, f) for w in ABC for a in ("async", "async_win")]


SMALL = ("layers_5", "2d", "2e_K10", "2f_top14", "2f_top28", "leaf_freq_K10", "leaf_rand_K10",
         "learned_markov_14", "learned_markov_28")       # every set of at most 28 pages


CLAIMS = [
    # ------------------------------------------------------------------ abstract
    ("abs-fq-dump", T(r"Loading the full working set reduces first-query latency by 80\% to 91\%",
        ("80", "lohi([-fqred(v,w,'2f_slru') for w in ABC],0)"),
        ("91", "lohi([-fqred(v,w,'2f_slru') for w in ABC],1)"))),
    ("abs-dump-x", T(r"by more than $8\times$ on two broad workloads under per-page hints, and by 2.8 to 3.0$\times$ when",
        ("8", "int(min(ratio(v.u(w,'2f_slru')) for w in 'AB'))"),
        ("2.8", "rd(min(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"),
        ("3.0", "rd(max(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"))),
    ("abs-skel", T(r"reduces end-to-end latency by 26\% to 37\% across three read workloads",
        ("26", "lohi([-v.u(w,'2d') for w in ABC],0)"),
        ("37", "lohi([-v.u(w,'2d') for w in ABC],1)"))),
    # -------------------------------------------------------------- introduction
    ("intro-base", T(r"the first point query takes 492 to 1{,}013~\textmu s",
        ("492", "us(min(v.base1(w) for w in ABC))"),
        ("1{,}013", "us(max(v.base1(w) for w in ABC))"))),
    ("intro-headline", T(r"increases end-to-end request latency by a factor of fourteen in this per-page single instance ($4.9\times$ under window-chunked delivery), whereas prefetching 18 B+tree interior pages reduces it by 16\%",
        ("fourteen", "word(r0(v.s1('A','2f_slru')/v.base1('A')))"),
        ("4.9", "rd(v.s1('A','2f_slru','async_win')/v.base1('A'),1)"),
        ("16", "red(v.e1('A','2d'))"))),
    ("contrib-dump-x", T(r"by more than $8\times$ on the two broad workloads under per-page delivery, and by 2.8 to 3.0$\times$ under window-chunked delivery, the stronger form",
        ("8", "int(min(ratio(v.u(w,'2f_slru')) for w in 'AB'))"),
        ("2.8", "rd(min(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"),
        ("3.0", "rd(max(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"))),
    ("contrib-skel", T(r"use at most 72~KB and reduce end-to-end request latency by 26\% to 37\%. Hot leaf",
        ("26", "lohi([-v.u(w,'2d') for w in ABC],0)"),
        ("37", "lohi([-v.u(w,'2d') for w in ABC],1)"))),
    # ------------------------------------------------------------- section 2 / 3
    ("open-var-50", T(r"its median varies by up to §1~\textmu s across prefetch sets within one workload instance",
        ("§1", "us(open_spread(v, ALL4))"))),
    ("lp-ratio", T(r"with shuffled reads 10 to 15$\times$ slower than sorted reads (14.7$\times$, 14.8$\times$, and 10.3$\times$ on the three workloads)",
        ("10", "lohi([v.seedratio(w,'lp_shuf','lp_sorted') for w in ABC],0)"),
        ("15", "lohi([v.seedratio(w,'lp_shuf','lp_sorted') for w in ABC],1)"),
        ("14.7", "rd(v.seedratio('A','lp_shuf','lp_sorted'),1)"),
        ("14.8", "rd(v.seedratio('B','lp_shuf','lp_sorted'),1)"),
        ("10.3", "rd(v.seedratio('C','lp_shuf','lp_sorted'),1)"))),
    ("resid-ratio", T(r"per-page \strat{Dump} reads 100\% because its 4{,}400 calls take 7.0~ms, whereas window-chunked \strat{Dump} reads 84\% after 1.9~ms of issuing",
        ("100", "r0(v.med('A','2f_slru','async','delivery_pct_median'))"),
        ("7.0", "ms(v.med('A','2f_slru','async','deliver_us_median'),1)"),
        ("84", "r0(v.pmed('A','2f_slru','async_win'))"),
        ("1.9", "ms(v.med('A','2f_slru','async_win','deliver_us_median'),1)"))),
    ("tab-strat-k10", T(r"78 to 98~\textmu s per-page, 77 to 96~\textmu s window-chunked ($K=10$)",
        ("78", "lohi([v.med(w,'2e_K10','async','deliver_us_median') for w in ALL4],0)"),
        ("98", "lohi([v.med(w,'2e_K10','async','deliver_us_median') for w in ALL4],1)"),
        ("77", "lohi([v.med(w,'2e_K10','async_win','deliver_us_median',add=('parse_us_median',)) for w in ALL4],0)"),
        ("96", "lohi([v.med(w,'2e_K10','async_win','deliver_us_median',add=('parse_us_median',)) for w in ALL4],1)"))),
    ("tab-strat-dump", T(r"0.75 to 7.0~ms per-page; 0.31 to 2.3~ms window-chunked",
        ("0.75", "ms(min(v.med(w,'2f_slru','async','deliver_us_median') for w in ALL4),2)"),
        ("7.0", "ms(max(v.med(w,'2f_slru','async','deliver_us_median') for w in ALL4),1)"),
        ("0.31", "ms(min(v.med(w,'2f_slru','async_win','deliver_us_median',add=('parse_us_median',)) for w in ALL4),2)"),
        ("2.3", "ms(max(v.med(w,'2f_slru','async_win','deliver_us_median',add=('parse_us_median',)) for w in ALL4),1)"))),
    ("s4-base", T(r"Median cold first-query latency is 492~\textmu s for Scattered-Zipf-100K, 734~\textmu s for Uniform-100K, and 1{,}013~\textmu s for Tail-Mixed",
        ("492", "us(v.base1('A'))"), ("734", "us(v.base1('B'))"), ("1{,}013", "us(v.base1('C'))"))),
    # ---------------------------------------------------------------- section 5
    ("s5-fq", T(r"It reduces cold-query latency by 80\% to 91\%, from baselines of 492 to 1{,}013~\textmu s to 91 to 97~\textmu s. The targeted sets reduce it by 23\% to 83\%",
        ("80", "lohi([-fqred(v,w,'2f_slru') for w in ABC],0)"),
        ("91", "lohi([-fqred(v,w,'2f_slru') for w in ABC],1)"),
        ("492", "us(min(v.base1(w) for w in ABC))"),
        ("1{,}013", "us(max(v.base1(w) for w in ABC))"),
        ("91", "lohi([v.s1(w,'2f_slru',col='fq_median') for w in ABC],0)"),
        ("97", "lohi([v.s1(w,'2f_slru',col='fq_median') for w in ABC],1)"),
        ("23", "lohi([-fqred(v,w,s) for w in ABC for s in ('2d','2e_K10','2f_top14')],0)"),
        ("83", "lohi([-fqred(v,w,s) for w in ABC for s in ('2d','2e_K10','2f_top14')],1)"))),
    ("fig-rev-cap", T(r"\strat{Dump} falls from 1{,}339\% to 391\% above baseline on Scattered-Zipf-100K and from 863\% to 221\% on Uniform-100K in this instance. Bars and labels show one workload instance (seed~1), whose Scattered-Zipf-100K baseline of 492~\textmu s is an outlier against the cross-instance median of 881~\textmu s, so the cross-instance per-page \strat{Dump} figure is 770\%",
        ("1{,}339", "pc(v.e1('A','2f_slru'))"),
        ("391", "pc(v.e1('A','2f_slru','async_win'))"),
        ("863", "pc(v.e1('B','2f_slru'))"),
        ("221", "pc(v.e1('B','2f_slru','async_win'))"),
        ("492", "us(v.base1('A'))"),
        ("881", "us(v.med('A','baseline'))"),
        ("770", "inc(v.u('A','2f_slru'))"))),
    ("s5-dump-dispatch", T(r"The full dump takes about 7~ms on the two 100K workloads, where it contains 17.7~MB, and 0.8~ms on Tail-Mixed",
        ("7", "same(r0(v.s1('A','2f_slru',col='deliver_us_median')/1000), r0(v.s1('B','2f_slru',col='deliver_us_median')/1000))"),
        ("0.8", "ms(v.s1('C','2f_slru',col='deliver_us_median'),1)"))),
    ("s5-reversal", T(r"\strat{Dump} increases warm-process end-to-end latency by 770\% on Scattered-Zipf-100K and 724\% on Uniform-100K (Table~\ref{tab:competitive}), whereas \strat{Skel} reduces it by 27\% and 26\% (Section~\ref{sec:eval-robustness}). Tail-Mixed is the boundary case: its 1.8~MB working set lets \strat{Dump} reduce latency by 9\%, while \strat{Skel} reduces it by 37\%",
        ("770", "inc(v.u('A','2f_slru'))"),
        ("724", "inc(v.u('B','2f_slru'))"),
        ("27", "red(v.u('A','2d'))"),
        ("26", "red(v.u('B','2d'))"),
        ("9", "red(v.u('C','2f_slru'))"),
        ("37", "red(v.u('C','2d'))"))),
    ("s5-delivery", T(r"Window-chunked delivery cuts \strat{Dump}'s dispatch time from 7.0 to 2.3~ms on the two 100K workloads, from 0.75 to 0.31~ms on Tail-Mixed, and from 1.40 to 0.57~ms on Tail-Hit (Table~\ref{tab:competitive}, lower block). \strat{Dump} accordingly moves from 770\% above the no-prefetch baseline to 198\% above it on Scattered-Zipf-100K, from 724\% to 179\% above on Uniform-100K, from 9\% below to 56\% below on Tail-Mixed, and from 72\% above to 24\% below on Tail-Hit. The same mechanism leaves \strat{Skel+10}'s dispatch at 96 against 98~\textmu s because its ranges already fit inside the window, so cheaper delivery rewrites the dump and leaves the precise sets as they were. On the two broad workloads, precise selection still wins under the stronger mechanism, 37\% and 25\% below baseline against 198\% and 179\% above, because dispatching the 17.7~MB working set still costs 2.3~ms for pages the first query never touches. On the two tail workloads, whose working sets are small enough that the chunked transfer is cheap, the chunked full dump reaches the precise sets but does not overtake them: 56\% below baseline for both on Tail-Mixed, and 24\% below against 27\% on Tail-Hit.",
        ("7.0", "same(ms(v.med('A','2f_slru','async','deliver_us_median'),1), ms(v.med('B','2f_slru','async','deliver_us_median'),1))"),
        ("2.3", "same(ms(v.med('A','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),1), ms(v.med('B','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),1))"),
        ("0.75", "ms(v.med('C','2f_slru','async','deliver_us_median'),2)"),
        ("0.31", "ms(v.med('C','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),2)"),
        ("1.40", "ms(v.med('C_hit','2f_slru','async','deliver_us_median'),2)"),
        ("0.57", "ms(v.med('C_hit','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),2)"),
        ("770", "inc(v.u('A','2f_slru'))"),
        ("198", "inc(v.u('A','2f_slru','async_win'))"),
        ("724", "inc(v.u('B','2f_slru'))"),
        ("179", "inc(v.u('B','2f_slru','async_win'))"),
        ("9", "red(v.u('C','2f_slru'))"),
        ("56", "red(v.u('C','2f_slru','async_win'))"),
        ("72", "inc(v.u('C_hit','2f_slru'))"),
        ("24", "red(v.u('C_hit','2f_slru','async_win'))"),
        ("96", "us(v.med('A','2e_K10','async_win','deliver_us_median',add=('parse_us_median',)))"),
        ("98", "us(v.med('A','2e_K10','async','deliver_us_median'))"),
        ("37", "red(v.u('A','2e_K10','async_win'))"),
        ("25", "red(v.u('B','2e_K10','async_win'))"),
        ("198", "inc(v.u('A','2f_slru','async_win'))"),
        ("179", "inc(v.u('B','2f_slru','async_win'))"),
        ("2.3", "same(ms(v.med('A','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),1), ms(v.med('B','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),1))"),
        ("56", "same(red(v.u('C','2e_K10','async_win')), red(v.u('C','2f_slru','async_win')))"),
        ("24", "red(v.u('C_hit','2f_slru','async_win'))"),
        ("27", "red(v.u('C_hit','2e_K10','async_win'))"))),
    ("s5-boundary", T(r"adding the 233~\textmu s open cost changes \strat{Skel} from 16\% below baseline in the warm-process model to 32\% above it in the external-warmer model. On Tail-Mixed, whose cold query is longer, \strat{Skel} remains below baseline under both boundaries, whereas \strat{Dump} no longer improves on the baseline once the open cost is added (+2\%).",
        ("233", "us(v.s1('A','2d',col='e2e_median')-v.s1('A','2d',col='e2e_warm_median'))"),
        ("16", "red(v.e1('A','2d'))"),
        ("32", "inc(v.e1('A','2d',col='e2e_median'))"),
        ("2", "inc(v.e1('C','2f_slru',col='e2e_median'))"))),
    ("s5-open-range", T(r"Across sets, its open-cost median spans §1 to §2~\textmu s in this instance but differs by up to §3~\textmu s in others, and it varies across batches,",
        ("§1", "us(min(open_cells(v)))"), ("§2", "us(max(open_cells(v)))"),
        ("§3", "us(open_spread(v, ('A', 'C')))"))),
    ("tab-e2e-base", T(r"Baseline & 492 & 492 & 1013 & 1013 \\",
        ("492", "r0(v.base1('A'))"), ("492", "r0(v.base1('A'))"),
        ("1013", "r0(v.base1('C'))"), ("1013", "r0(v.base1('C'))"))),
] + [
    (f"tab-e2e-{s}", T(rf"\strat{{{lab}}} & X & X & X & X \\",
        ("X", f"cell(v,'A','{s}','e2e_median')"), ("X", f"cell(v,'A','{s}','e2e_warm_median')"),
        ("X", f"cell(v,'C','{s}','e2e_median')"), ("X", f"cell(v,'C','{s}','e2e_warm_median')")))
    for s, lab in (("layers_5", "Skel-5"), ("2d", "Skel"), ("2f_slru", "Dump"))
] + [
    ("finding-reversal", T(r"by $8\times$ per-page and by $2.8\times$ window-chunked, and wins only",
        ("8", "int(min(ratio(v.u(w,'2f_slru')) for w in 'AB'))"),
        ("2.8", "rd(min(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"))),
    # ---------------------------------------------------------------- section 6
    ("s6-budget", T(r"At 500 pages, the frequency-ranked set makes the two broad workloads 81\% and 41\% slower than baseline; the full dump makes them 770\% and 724\% slower.",
        ("81", "inc(v.u('A','2f_top500'))"), ("41", "inc(v.u('B','2f_top500'))"),
        ("770", "inc(v.u('A','2f_slru'))"), ("724", "inc(v.u('B','2f_slru'))"))),
    ("s6-mechanism", T(r"\strat{Skel+10} is 38\% and 37\% below baseline on Scattered-Zipf-100K and 25\% below under both on Uniform-100K, because a set this small already issues in a few hints. At 500 pages, chunking turns the regression on the broad workloads into a smaller regression (81\% to 40\% above baseline on Scattered-Zipf-100K, 41\% to 34\% above on Uniform-100K) and turns the tail workloads into wins (10\% to 57\% below on Tail-Mixed, 14\% above to 12\% below on Tail-Hit).",
        ("38", "red(v.u('A','2e_K10'))"), ("37", "red(v.u('A','2e_K10','async_win'))"),
        ("25", "same(red(v.u('B','2e_K10')), red(v.u('B','2e_K10','async_win')))"),
        ("81", "inc(v.u('A','2f_top500'))"), ("40", "inc(v.u('A','2f_top500','async_win'))"),
        ("41", "inc(v.u('B','2f_top500'))"), ("34", "inc(v.u('B','2f_top500','async_win'))"),
        ("10", "red(v.u('C','2f_top500'))"), ("57", "red(v.u('C','2f_top500','async_win'))"),
        ("14", "inc(v.u('C_hit','2f_top500'))"), ("12", "red(v.u('C_hit','2f_top500','async_win'))"))),
] + [
    (f"tab-comp-{arm}-{s}", T(rf"\strat{{{lab}}} & {pages} & X & X & X & X \\",
        *[("X", f"ci(v.u('{w}','{s}','{arm}'), v.ulo('{w}','{s}','{arm}'), v.uhi('{w}','{s}','{arm}'))") for w in ALL4]))
    for arm in ("async", "async_win")
    for s, lab, pages in (("2e_K10", "Skel+10", "14--28"), ("2f_top14", "Dump-14", "14"),
                          ("2f_top500", "Dump-500", "500"), ("2f_slru", "Dump", r"$\approx$4400"))
] + [
    ("s6-matched", T(r"averages $-0.5$ to $+0.9$ points of the baseline, and every 95\% CI lies within $[-1,+3]$ under both delivery mechanisms.",
        ("-0.5", "sg1(min(mb_cells(v,'mean_d')))"), ("+0.9", "sg1(max(mb_cells(v,'mean_d')))"),
        ("-1", "math.floor(min(mb_cells(v,'ci_lo')))"), ("+3", "'%+d' % math.ceil(max(mb_cells(v,'ci_hi')))"))),
    ("s6-learned", T(r"the learned selector reduces first-query latency by 38.0\%, 36.8\%, and 65.7\% on the three workloads",
        *[(lit, f"rd(-v.u('{w}','learned_markov_14',metric='first_query_us'),1)") for lit, w in (("38.0", "A"), ("36.8", "B"), ("65.7", "C"))])),
    ("s6-ablation-text", T(r"The four observed interior pages reduce end-to-end latency by 37\%. Ten frequent leaves alone produce a 2\% reduction that is a tie with the baseline, while ten random leaves increase latency by 7\%; both leaf-only first-query intervals cross zero. Combining the frequent leaves with the interior pages yields a 57\% reduction.",
        ("37", "red(v.u('C','2d'))"),
        ("2", "red(v.u('C','leaf_freq_K10')) + is_tie(v,'C','leaf_freq_K10')"),
        ("7", "inc(v.u('C','leaf_rand_K10')) + crosses_zero(v,'C','leaf_rand_K10') + crosses_zero(v,'C','leaf_freq_K10')"),
        ("57", "red(v.u('C','2e_K10'))"))),
] + [
    (f"tab-abl-{s}", T(rf"\strat{{{lab}}} & {pages} & $FQ\%$ $[FL, FH]$ & {e2e}",
        ("FQ", f"s0(v.u('C','{s}',metric='first_query_us'))"),
        ("FL", f"s0(v.ulo('C','{s}',metric='first_query_us'))"),
        ("FH", f"s0(v.uhi('C','{s}',metric='first_query_us'))"),
        *e2e_subs))
    for s, lab, pages, e2e, e2e_subs in (
        ("2d", "Skel", "4", r"$E\%$ $[EL,EH]$ \\",
         [("E", "s0(v.u('C','2d'))"), ("EL", "s0(v.ulo('C','2d'))"), ("EH", "s0(v.uhi('C','2d'))")]),
        ("leaf_rand_K10", "leaf-rand-10", "10", r"$E\%$ (W) \\",
         [("E", "s0(v.u('C','leaf_rand_K10'))"), ("W", "verdict_word(v,'C','leaf_rand_K10')")]),
        ("leaf_freq_K10", "leaf-freq-10", "10", r"$E\%$ (W) \\",
         [("E", "s0(v.u('C','leaf_freq_K10'))"), ("W", "verdict_word(v,'C','leaf_freq_K10')")]),
        ("2e_K10", "Skel+10", "14", r"$E\%$ $[EL,EH]$ \\",
         [("E", "s0(v.u('C','2e_K10'))"), ("EL", "s0(v.ulo('C','2e_K10'))"), ("EH", "s0(v.uhi('C','2e_K10'))")]))
] + [
    ("s6-bimodal", T(r"about 72\% below baseline when the first query misses and about 35\% when it hits, for a mean reduction of 57\%. Tail-Hit removes the misses while retaining an equally sized tail range. In this control, adding ten leaves reduces latency by 29\%, compared with 28\% for interior pages alone and 30\% for a footprint-matched frequency set",
        ("72", "bimodal(v,'C','2e_K10',True)"), ("35", "bimodal(v,'C','2e_K10',False)"),
        ("57", "red(v.u('C','2e_K10'))"),
        ("29", "red(v.u('C_hit','2e_K10'))"), ("28", "red(v.u('C_hit','2d'))"),
        ("30", "red(v.u('C_hit','2f_top14'))"))),
    # ---------------------------------------------------------------- section 7
    ("s7-sampling", T(r"\strat{Skel} reduces warm-process end-to-end latency by 27\% on Scattered-Zipf-100K (95\% CI $[23,31]$), 26\% on Uniform-100K ($[16,33]$), and 37\% on Tail-Mixed ($[34,40]$). The effect appears in 10, 9, and 10 instances, respectively, and \strat{Skel} reduces Tail-Hit by 28\%. \strat{Skel+10} reduces the three workloads by 38\%, 25\%, and 57\% (Table~\ref{tab:competitive}). The single instance in Table~\ref{tab:e2e-ac} and Figure~\ref{fig:reversal} is an instantiation outlier on Scattered-Zipf-100K: its 492~\textmu s baseline is far below the cross-instance median of 881~\textmu s, so its single-instance \strat{Skel+10} change of $-8$\% understates the cross-instance $-38$\%, and its Uniform-100K \strat{Skel-5} change of $-35$\% overstates the cross-instance $-1$\%.",
        ("27", "red(v.u('A','2d'))"), ("23", "red(v.uhi('A','2d'))"), ("31", "red(v.ulo('A','2d'))"),
        ("26", "red(v.u('B','2d'))"), ("16", "red(v.uhi('B','2d'))"), ("33", "red(v.ulo('B','2d'))"),
        ("37", "red(v.u('C','2d'))"), ("34", "red(v.uhi('C','2d'))"), ("40", "red(v.ulo('C','2d'))"),
        ("10", "nsign(v,'A','2d')"), ("9", "nsign(v,'B','2d')"), ("10", "nsign(v,'C','2d')"),
        ("28", "red(v.u('C_hit','2d'))"),
        ("38", "red(v.u('A','2e_K10'))"), ("25", "red(v.u('B','2e_K10'))"), ("57", "red(v.u('C','2e_K10'))"),
        ("492", "us(v.base1('A'))"), ("881", "us(v.med('A','baseline'))"),
        ("-8", "under(v.e1('A','2e_K10'), v.u('A','2e_K10'))"), ("-38", "s0(v.u('A','2e_K10'))"),
        ("-35", "over(v.e1('B','layers_5'), v.u('B','layers_5'))"), ("-1", "s0(v.u('B','layers_5'))"))),
    ("s7-skel5", T(r"\strat{Skel-5} changes latency by $-5$\% on Scattered-Zipf-100K (CI $[-15,5]$) and $-1$\% on Uniform-100K (CI $[-11,7]$), with both intervals crossing zero; eight of ten Uniform-100K instances become slower, with a median change of $+5$\%.",
        ("-5", "s0(v.u('A','layers_5'))"), ("-15", "r0(v.ulo('A','layers_5'))"), ("5", "r0(v.uhi('A','layers_5'))"),
        ("-1", "s0(v.u('B','layers_5'))"), ("-11", "r0(v.ulo('B','layers_5'))"),
        ("7", "str(r0(v.uhi('B','layers_5'))) + cross0(v,'A','layers_5') + cross0(v,'B','layers_5')"),
        ("eight", "sw(sum(x > 0 for x in per_seed(v,'B','layers_5')))"),
        ("+5", "s0(v.u('B','layers_5',field='median_pct'))"))),
    ("s7-chunked", T(r"\strat{Skel} reduces warm-process latency by 26\% on Scattered-Zipf-100K (CI $[22,30]$), 25\% on Uniform-100K ($[14,32]$), and 37\% on Tail-Mixed ($[34,40]$), and \strat{Skel-5} changes it by $-5$\% and $-1$\% on the two 100K workloads. Under both boundaries, every \strat{Skel} and \strat{Skel-5} cell lies within one point of per-page delivery, and every \strat{Skel+10} and \strat{Dump-14} cell within four,",
        *[(lit, expr) for w, (m, lo, hi) in zip("ABC", (("26", "22", "30"), ("25", "14", "32"), ("37", "34", "40")))
          for lit, expr in ((m, f"red(v.u('{w}','2d','async_win'))"), (lo, f"red(v.uhi('{w}','2d','async_win'))"),
                            (hi, f"red(v.ulo('{w}','2d','async_win'))"))],
        ("-5", "s0(v.u('A','layers_5','async_win'))"), ("-1", "s0(v.u('B','layers_5','async_win'))"),
        ("one", "sw(math.ceil(maxgap(v,('2d','layers_5'))))"),
        ("four", "sw(math.ceil(maxgap(v,('layers_5','2d','2e_K10','2f_top14'))))"))),
    ("s7-10x", T(r"28 of 36 workload-strategy cells keep their direction. The observed interior set improves rather than merely holds: \strat{Skel} moves from 27\% to 52\% below baseline on Scattered-Zipf-100K, from 26\% to 52\% below on Uniform-100K, and from 37\% to 50\% below on Tail-Mixed, and \strat{Skel+10} moves from 57\% to 80\% below on Tail-Mixed. This is because the larger database raises the cold baseline, whereas the skeleton's delivery cost grows only $1.07\times$. Of the eight direction changes, five are large-footprint sets that regress at the reference size and become neutral at $10\times$, including \strat{Skel+500} from 81\% above baseline to 3\% below on Scattered-Zipf-100K. The one substantive degradation is \strat{Dump} on Tail-Mixed: its resident working set doubles and its delivery cost grows $2.05\times$, from 749 to 1{,}534~\textmu s, so 9\% below baseline becomes 29\% above. \strat{Skel-92} on Tail-Mixed moves from 21\% below baseline to parity.",
        ("28", "keep_dir(v)"),
        *[(lit, f"red(v.u('{w}','2d'{db}))") for w, a, b in (("A", "27", "52"), ("B", "26", "52"), ("C", "37", "50")) for lit, db in ((a, ""), (b, ",db='1gb'"))],
        ("57", "red(v.u('C','2e_K10'))"), ("80", "red(v.u('C','2e_K10',db='1gb'))"),
        ("1.07", "rd(v.med('C','2d','async','deliver_us_median',db='1gb')/v.med('C','2d','async','deliver_us_median'),2)"),
        ("eight", "sw(36-keep_dir(v))"), ("five", "sw(regress_to_neutral(v))"),
        ("81", "inc(v.u('A','2e_K500'))"), ("3", "red(v.u('A','2e_K500',db='1gb'))"),
        ("2.05", "rd(v.med('C','2f_slru','async','deliver_us_median',db='1gb')/v.med('C','2f_slru','async','deliver_us_median'),2)"),
        ("749", "us(v.med('C','2f_slru','async','deliver_us_median'))"),
        ("1{,}534", "us(v.med('C','2f_slru','async','deliver_us_median',db='1gb'))"),
        ("9", "red(v.u('C','2f_slru'))"), ("29", "inc(v.u('C','2f_slru',db='1gb'))"),
        ("21", "red(v.u('C','layers_92')) + cross0(v,'C','layers_92',db='1gb')"))),
    ("s7-layout", T(r"\strat{Skel+10} is $1.07\times$ slower under the clustered layout on Scattered-Zipf-100K on all ten instances and $1.12\times$ slower on Tail-Mixed on eight of ten. For pure structural selection the sign reverses: \strat{Skel-92} on Tail-Mixed is $0.88\times$, or 12\% faster, under the clustered layout on all ten instances,",
        ("1.07", "rd(lratio(v,'A','2e_K10'),2) + count_is(nslower(v,'A','2e_K10'), 10)"),
        ("1.12", "rd(lratio(v,'C','2e_K10'),2)"), ("eight", "sw(nslower(v,'C','2e_K10'))"),
        ("0.88", "rd(lratio(v,'C','layers_92'),2) + count_is(nslower(v,'C','layers_92'), 0)"),
        ("12", "str(r0(100*(1-lratio(v,'C','layers_92'))))"))),
    # ---------------------------------------------------------------- section 8
    ("s8-dump", T(r"even window-chunked it remains 198\% and 179\% above baseline on the two 17.7~MB working sets, because dispatching it still costs 2.3~ms",
        ("198", "inc(v.u('A','2f_slru','async_win'))"), ("179", "inc(v.u('B','2f_slru','async_win'))"),
        ("2.3", "same(ms(v.med('A','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),1), ms(v.med('B','2f_slru','async_win','deliver_us_median',add=('parse_us_median',)),1))"))),
    ("s8-10x", T(r"the dump's delivery cost on Tail-Mixed grew $2.05\times$ while the observed interior set's delivery cost grew $1.07\times$, which turned the dump's 9\% gain into a 29\% loss",
        ("2.05", "rd(v.med('C','2f_slru','async','deliver_us_median',db='1gb')/v.med('C','2f_slru','async','deliver_us_median'),2)"),
        ("1.07", "rd(v.med('C','2d','async','deliver_us_median',db='1gb')/v.med('C','2d','async','deliver_us_median'),2)"),
        ("9", "red(v.u('C','2f_slru'))"), ("29", "inc(v.u('C','2f_slru',db='1gb'))"))),
    # ---------------------------------------------------------------- conclusion
    ("concl", T(r"The full working-set dump reduces first-query latency by 80\% to 91\%, but increases end-to-end latency by more than $8\times$ on the two broad workloads under per-page delivery, and by 2.8 to 3.0$\times$ under window-chunked delivery. The observed B+tree interior set uses at most 72~KB and reduces end-to-end latency by 26\% to 37\% across all three workloads",
        ("80", "lohi([-fqred(v,w,'2f_slru') for w in ABC],0)"),
        ("91", "lohi([-fqred(v,w,'2f_slru') for w in ABC],1)"),
        ("8", "int(min(ratio(v.u(w,'2f_slru')) for w in 'AB'))"),
        ("2.8", "rd(min(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"),
        ("3.0", "rd(max(ratio(v.u(w,'2f_slru','async_win')) for w in 'AB'),1)"),
        ("26", "lohi([-v.u(w,'2d') for w in ABC],0)"),
        ("37", "lohi([-v.u(w,'2d') for w in ABC],1)"))),
    ("s6-broad", T(r"On Uniform-100K, \strat{Skel} and \strat{Skel+10} end 26\% and 25\% below baseline. On Scattered-Zipf-100K, which has stable Zipfian reuse, the point estimates are 27\% for \strat{Skel} and 38\% for \strat{Skel+10}",
        ("26", "red(v.u('B','2d'))"), ("25", "red(v.u('B','2e_K10'))"),
        ("27", "red(v.u('A','2d'))"), ("38", "red(v.u('A','2e_K10'))"))),
]

STALE = [
    ("tab-strat-skelN", r"$\approx$68~\textmu s ($N=5$); $\approx$190~\textmu s ($N=92$)",
     r"$\approx$«r0(statistics.median(v.med(w,'layers_5','async','deliver_us_median') for w in ALL4))»~\textmu s ($N=5$); $\approx$«r0(statistics.median(v.med(w,'layers_92','async','deliver_us_median') for w in ALL4))»~\textmu s ($N=92$)"),
    ("tab-strat-skel", r"& 4 to 18 & 68 to 110~\textmu s \\",
     r"& 4 to 18 & «lohi([v.med(w,'2d','async','deliver_us_median') for w in ALL4],0)» to «lohi([v.med(w,'2d','async','deliver_us_median') for w in ALL4],1)»~\textmu s \\"),
    ("tab-strat-k500", r"0.5 to 0.85~ms ($K=500$)",
     r"«ms(min(v.med(w,'2e_K500','async','deliver_us_median') for w in ALL4),2)» to «ms(max(v.med(w,'2e_K500','async','deliver_us_median') for w in ALL4),2)»~ms ($K=500$)"),
    ("s5-small-dispatch", r"Sets of at most 28 pages take 68 to 124~\textmu s to issue. A 500-page set takes 0.5 to 0.85~ms.",
     r"Sets of at most 28 pages take «lohi([v.med(w,s,'async','deliver_us_median') for w in ALL4 for s in SMALL],0)» to «lohi([v.med(w,s,'async','deliver_us_median') for w in ALL4 for s in SMALL],1)»~\textmu s to issue. A 500-page set takes «ms(min(v.med(w,s,'async','deliver_us_median') for w in ALL4 for s in ('2e_K500','2f_top500')),2)» to «ms(max(v.med(w,s,'async','deliver_us_median') for w in ALL4 for s in ('2e_K500','2f_top500')),2)»~ms."),
]

# Numbers a single formula cannot reproduce from the current batch: left as they are by the
# refresh and reported for a decision.
PENDING = [
    ("s7-layout-best", r"414 versus 507~\textmu s on Scattered-Zipf-100K, 475 versus 670~\textmu s on Uniform-100K, and 253 versus 302~\textmu s on Tail-Mixed",
     "no one definition gives all three pairs: per-layout minimum gives 414/507, 475/664, 253/253; "
     "the default layout's fastest strategy gives 414/540, 475/670, 253/302"),
    ("s7-layout-floor", r"183 versus 181~\textmu s",
     "not found in unified_v6 under any seed, aggregation, column or layout pair"),
]

ALL = r".+"   # the whole line: used only for lines that hold no unified-batch number

UNCHANGED = [
    # (line regex, span regex, reason). A token is unchanged only if it lies inside a match of
    # the span regex on a line matching the line regex. Whole-line spans (ALL) are reserved for
    # lines read and found to hold no unified-batch number.
    # -- whole lines from other sources
    (r"^\\todo\{", ALL, "advisor's TODO note: records the state it was written in; removed when resolved"),
    (r"^\\textbf\{Occurrence on AWS Lambda", ALL, "Lambda batch coldprobe-b2"),
    (r"^\\caption\{The warm-process, cold-page-cache state on AWS Lambda", ALL, "Lambda batch coldprobe-b2"),
    (r"^The Lambda probe of Section", ALL, "Lambda batch coldprobe-b2"),
    (r"^Lambda offers no direct way to read residency", ALL, "Lambda batch coldprobe-b2"),
    (r"^The reference database illustrates this structural asymmetry", ALL, "database geometry and hotset sizes"),
    (r"^The kernel readahead window bounds", ALL, "kernel constants and database geometry; no batch number"),
    (r"^The workstation has an AMD Ryzen", ALL, "hardware; stated session variation"),
    (r"^The reference database contains 600", ALL, "database definition"),
    (r"lists the three workloads used for end-to-end evaluation", ALL, "workload definitions"),
    (r"^(Scattered-Zipf|Uniform)-100K & ", ALL, "workload table"),
    (r"^Before each workstation measurement, a privileged test harness", ALL, "cold-gate threshold; separate CPU-cache measurement"),
    (r"we also generate ten independent instances", ALL, "statistical method"),
    (r"^Prefetching can shorten the query while delaying", ALL, "statistical method"),
    (r"^The portability experiment runs the same selectors", ALL, "OpenWhisk campaigns"),
    (r"^We apply cgroup \\texttt\{MemoryMax\}", ALL, "results/ram_pressure (separate batch)"),
    (r"^We freeze each profile before eleven aging checkpoints", ALL, "results/aging_v2 (separate batch)"),
    (r"^This experiment compares relative first-query reduction", ALL, "OpenWhisk campaigns"),
    (r"First-query effectiveness on the workstation versus OpenWhisk", ALL, "OpenWhisk campaigns"),
    (r"^(Scattered-Zipf-600K|Uniform-600K|Hotspot-1|Tail-Mixed +&|Tail-Hit +&|\\textbf\{All\})", ALL, "OpenWhisk table"),
    (r"\\includegraphics|\\cmidrule|& \\textbf\{|\\text\{e2e\}", ALL, "figure/table layout; the '2' of 'e2e'"),
    # -- spans inside lines that also hold batch numbers
    (r".", r"128~MB|1\{,\}024~MB|31\\%|19~ms|30\\% uncached", "Lambda batch coldprobe-b2"),
    (r".", r"\d+~KB", "sizes derived from page counts (hotsets, kernel window)"),
    (r".", r"4\{,\}400(-page| calls)|about 4\{,\}400 or 480|\$\\approx\$4400|17\.7~MB|1\.8~MB|18~MB", "Dump set size (hotset)"),
    (r".", r"18 B\+tree|4 to 18|14- to 28-page|5- to 28-page|14 to 28 pages|14 to 28 for \$K=10\$; about 500 for \$K=500\$|\(\$K=(10|500)\$\)|500-page|500 pages|14 and 28 pages|at most 28 pages|set of 5 to 28 pages", "set sizes (hotsets) and budgets"),
    (r".", r"\$N \\in \\\{5,92\\\}\$|\$N \\in \\\{14,28,100,500\\\}\$|\(\$N=(5|92)\$\)|92 interior pages|from 4 to 48", "strategy definitions and hotset sizes"),
    (r".", r"\\strat\{(Skel\+10|Skel\+500|Skel\+K|Skel-5|Skel-92|Skel-N|Dump-14|Dump-28|Dump-500|Dump-N|leaf-freq-10|leaf-rand-10|Skel\+10-static|Skel-92-static)\}", "strategy label"),
    (r".", r"(Scattered-Zipf|Uniform)-100K|100K workloads|Scattered-Zipf-600K|Uniform-600K", "workload name"),
    (r".", r"\$10\\times\$", "the 10x database"),
    (r".", r"1 to 3~\\textmu s", "warm query latency from a separate warm measurement"),
    (r".", r"within 5\\% of the baseline|\$\\pm5\$\\%|less than 5\\% of the baseline|5\\% of the baseline", "pre-registered margin"),
    (r".", r"95\\% (bootstrap|CI|confidence)", "statistical method"),
    (r".", r"ratio about 1\.0", "not from a unified batch (asynchronous lp arms)"),
    (r".", r"5~ms grace period|also reaches 100\\%|about 97~\\textmu s", "results/unified_v5/grace_check; '97' listed in PENDING"),
    (r".", r"at most 32 pages", "kernel window"),
    (r".", r"20 of 28 pages|12 of 14 on Tail-Mixed|28 pages on the two 100K workloads and 14 on Tail-Mixed|hold 15 pages", "pre-registered pairs and hotset overlaps"),
    (r".", r"10\\% to 15\\%", "stated session variation"),
    (r".", r"\\texttt\{readahead\(2\)\}", "system call name"),
    (r".", r"414 versus 507~\\textmu s on Scattered-Zipf-100K, 475 versus 670~\\textmu s on Uniform-100K, and 253 versus 302~\\textmu s|183 versus 181~\\textmu s", "listed in PENDING"),
]


# --------------------------------------------------------------------------- rewording
# Sentences whose wording had to change when unified_v7 replaced unified_v6, because a value
# crossed what the old wording asserted (a tie became an order, a count dropped from ten, a
# reduction became an increase). Each replaces its CLAIMS entry; its template now encodes
# the new wording and asserts what that wording claims.
_S5_TAIL_OLD = ("the chunked full dump reaches the precise sets but does not overtake them: "
                "«same(red(v.u('C','2e_K10','async_win')), red(v.u('C','2f_slru','async_win')))»\\% "
                "below baseline for both on Tail-Mixed, and «red(v.u('C_hit','2f_slru','async_win'))»\\% "
                "below against «red(v.u('C_hit','2e_K10','async_win'))»\\% on Tail-Hit.")
_S5_TAIL_NEW = ("the chunked full dump draws level with the precise sets: "
                "«red(v.u('C','2f_slru','async_win'))»\\% below baseline against "
                "«red(v.u('C','2e_K10','async_win'))»\\% on Tail-Mixed, and "
                "«red(v.u('C_hit','2f_slru','async_win'))»\\% against "
                "«red(v.u('C_hit','2e_K10','async_win'))»\\% on Tail-Hit, with overlapping intervals"
                "«overlap(v,'C','2f_slru','2e_K10')»«overlap(v,'C_hit','2f_slru','2e_K10')».")
_OLD = dict(CLAIMS)
assert _OLD["s5-delivery"].count(_S5_TAIL_OLD) == 1

REWORDED = {
    "s5-delivery": _OLD["s5-delivery"].replace(_S5_TAIL_OLD, _S5_TAIL_NEW),
    "s6-mechanism": T(r"\strat{Skel+10} is §1\% and §2\% below baseline on Scattered-Zipf-100K and §3\% and §4\% below on Uniform-100K, because a set this small already issues in a few hints. At 500 pages, chunking turns the regression on the broad workloads into a smaller regression (§5\% to §6\% above baseline on Scattered-Zipf-100K, §7\% to §8\% above on Uniform-100K) and turns the tail workloads into wins (§9\% to §10\% below on Tail-Mixed, §11\% above to §12\% below on Tail-Hit).",
        ("§1", "red(v.u('A','2e_K10'))"), ("§2", "red(v.u('A','2e_K10','async_win'))"),
        ("§3", "red(v.u('B','2e_K10'))"), ("§4", "red(v.u('B','2e_K10','async_win'))"),
        ("§5", "inc(v.u('A','2f_top500'))"), ("§6", "inc(v.u('A','2f_top500','async_win'))"),
        ("§7", "inc(v.u('B','2f_top500'))"), ("§8", "inc(v.u('B','2f_top500','async_win'))"),
        ("§9", "red(v.u('C','2f_top500'))"), ("§10", "red(v.u('C','2f_top500','async_win'))"),
        ("§11", "inc(v.u('C_hit','2f_top500'))"), ("§12", "red(v.u('C_hit','2f_top500','async_win'))")),
    "s6-ablation-text": T(r"The four observed interior pages reduce end-to-end latency by §1\%. Ten frequent leaves alone produce a §2\% reduction that is a tie with the baseline, while ten random leaves increase latency by §3\%; alone, the random and frequent leaves cut the first query by only §4\% and §5\%. Combining the frequent leaves with the interior pages yields a §6\% reduction.",
        ("§1", "red(v.u('C','2d'))"),
        ("§2", "red(v.u('C','leaf_freq_K10')) + is_tie(v,'C','leaf_freq_K10')"),
        ("§3", "inc(v.u('C','leaf_rand_K10'))"),
        ("§4", "red(v.u('C','leaf_rand_K10',metric='first_query_us'))"),
        ("§5", "red(v.u('C','leaf_freq_K10',metric='first_query_us'))"),
        ("§6", "red(v.u('C','2e_K10'))")),
    "s7-10x": T(r"§1 of 36 workload-strategy cells keep their direction. The observed interior set improves rather than merely holds: \strat{Skel} moves from §2\% to §3\% below baseline on Scattered-Zipf-100K, from §4\% to §5\% below on Uniform-100K, and from §6\% to §7\% below on Tail-Mixed, and \strat{Skel+10} moves from §8\% to §9\% below on Tail-Mixed. This is because the larger database raises the cold baseline, whereas the skeleton's delivery cost grows only $§10\times$. Of the §11 direction changes, §12 are 500-page sets that regress at the reference size and become neutral at $10\times$, and \strat{Skel+500} on Scattered-Zipf-100K also becomes neutral without changing sign, from §13\% above baseline to §14\% above. The one substantive degradation is \strat{Dump} on Tail-Mixed: its resident working set doubles and its delivery cost grows $§15\times$, from §16 to §17~\textmu s, so §18\% below baseline becomes §19\% above. \strat{Skel-92} on Tail-Mixed moves from §20\% below baseline to parity.",
        ("§1", "keep_dir(v)"),
        ("§2", "red(v.u('A','2d'))"), ("§3", "red(v.u('A','2d',db='1gb'))"),
        ("§4", "red(v.u('B','2d'))"), ("§5", "red(v.u('B','2d',db='1gb'))"),
        ("§6", "red(v.u('C','2d'))"), ("§7", "red(v.u('C','2d',db='1gb'))"),
        ("§8", "red(v.u('C','2e_K10'))"), ("§9", "red(v.u('C','2e_K10',db='1gb'))"),
        ("§10", "rd(v.med('C','2d','async','deliver_us_median',db='1gb')/v.med('C','2d','async','deliver_us_median'),2)"),
        ("§11", "sw(36-keep_dir(v))"), ("§12", "r2n_500(v)"),
        ("§13", "inc(v.u('A','2e_K500'))"),
        ("§14", "inc(v.u('A','2e_K500',db='1gb')) + neutral_same_sign(v,'A','2e_K500')"),
        ("§15", "rd(v.med('C','2f_slru','async','deliver_us_median',db='1gb')/v.med('C','2f_slru','async','deliver_us_median'),2)"),
        ("§16", "us(v.med('C','2f_slru','async','deliver_us_median'))"),
        ("§17", "us(v.med('C','2f_slru','async','deliver_us_median',db='1gb'))"),
        ("§18", "red(v.u('C','2f_slru'))"), ("§19", "inc(v.u('C','2f_slru',db='1gb'))"),
        ("§20", "red(v.u('C','layers_92')) + cross0(v,'C','layers_92',db='1gb')")),
    "s7-layout": T(r"\strat{Skel+10} is $§1\times$ slower under the clustered layout on Scattered-Zipf-100K on §2 instances and $§3\times$ slower on Tail-Mixed on §4. For pure structural selection the sign reverses: \strat{Skel-92} on Tail-Mixed is $§5\times$, or §6\% faster, under the clustered layout on §7 instances,",
        ("§1", "rd(lratio(v,'A','2e_K10'),2)"), ("§2", "of_ten(nslower(v,'A','2e_K10'))"),
        ("§3", "rd(lratio(v,'C','2e_K10'),2)"), ("§4", "of_ten(nslower(v,'C','2e_K10'))"),
        ("§5", "rd(lratio(v,'C','layers_92'),2)"),
        ("§6", "str(r0(100*(1-lratio(v,'C','layers_92'))))"),
        ("§7", "of_ten(10-nslower(v,'C','layers_92'))")),
}
OLD_LITERAL = {"s8-tail": "on the two tail workloads the chunked dump reaches the precise sets "
                          "but does not beat them."}
CLAIMS = [(cid, REWORDED.get(cid, tpl)) for cid, tpl in CLAIMS] + [
    # the guidance restates the tail comparison in words only; the template asserts it
    ("s8-tail", "on the two tail workloads the chunked dump draws level with the precise sets"
                "«overlap(v,'C','2f_slru','2e_K10')»«overlap(v,'C_hit','2f_slru','2e_K10')».")]


# ------------------------------------------------------------ v7 additions (2026-10-10)
# Sentences that stated what unified_v6 had not measured and unified_v7 has: the matched
# budget on Tail-Hit (Dump-15) and window-chunked delivery at 10x.
def within_margin(v, margin=5.0):
    """Every primary matched-budget CI lies inside +-margin: 'perform the same'."""
    for w in ALL4:
        for a in ("async", "async_win"):
            assert -margin <= v.mb(w, a, "ci_lo") and v.mb(w, a, "ci_hi") <= margin, f"{w} {a} outside margin"
    return ""


def mb4(v, f):
    return [v.mb(w, a, f) for w in ALL4 for a in ("async", "async_win")]


def points(n):
    return "one point" if n == 1 else f"{sw(n)} points"


def regress_pp(v):
    """The dump regresses on Tail-Mixed at 10x under per-page delivery (CI above zero)."""
    assert v.ulo("C", "2f_slru", db="1gb") > 0, "per-page Dump TM 10x no longer regresses"
    return ""


_OLD.update({c: t for c, t in dict(CLAIMS).items() if c in ("s8-10x",) and c not in _OLD})

V7_REWORD = {
    "s7-10x": REWORDED["s7-10x"]
        .replace("«keep_dir(v)» of 36 workload-strategy cells keep their direction.",
                 "On the $10\\times$ database, measured in the same batch as Table~\\ref{tab:e2e-ac}, "
                 "«keep_dir(v)» of 36 workload-strategy cells keep their direction under per-page delivery.")
        .replace("becomes «inc(v.u('C','2f_slru',db='1gb'))»\\% above.",
                 "becomes «inc(v.u('C','2f_slru',db='1gb'))»\\% above. Window-chunked delivery, run at this "
                 "size as well, keeps \\strat{Skel} and \\strat{Skel+10} within "
                 "«points(math.ceil(max(abs(v.u(w,s,'async_win',db='1gb')-v.u(w,s,db='1gb')) for w in ABC for s in ('2d','2e_K10'))))» "
                 "of per-page delivery and removes the degradation: the dump stays "
                 "«red(v.u('C','2f_slru','async_win',db='1gb'))»\\% below baseline on Tail-Mixed, against "
                 "«red(v.u('C','2f_slru','async_win'))»\\% at the reference size."),
    "s8-10x": T(r"growth narrows the margin: at $10\times$ the reference size, the dump's delivery cost on Tail-Mixed grew $§1\times$ while the observed interior set's grew $§2\times$; per-page, this turned the dump's §3\% gain into a §4\% loss, and window-chunked, its gain shrank from §5\% to §6\% (Section~\ref{sec:eval-robustness}).",
        ("§1", "rd(v.med('C','2f_slru','async','deliver_us_median',db='1gb')/v.med('C','2f_slru','async','deliver_us_median'),2)"),
        ("§2", "rd(v.med('C','2d','async','deliver_us_median',db='1gb')/v.med('C','2d','async','deliver_us_median'),2)"),
        ("§3", "red(v.u('C','2f_slru'))"), ("§4", "inc(v.u('C','2f_slru',db='1gb'))"),
        ("§5", "red(v.u('C','2f_slru','async_win'))"), ("§6", "red(v.u('C','2f_slru','async_win',db='1gb'))")),
}
assert V7_REWORD["s7-10x"] != REWORDED["s7-10x"]
V7_NEW = [
    ("s6-matched4", T(r"\strat{Skel+10} holds 28 pages on the two 100K workloads, 14 on Tail-Mixed, and 15 on Tail-Hit in every instance, so we compare it with \strat{Dump-28}, \strat{Dump-14}, and \strat{Dump-15} under a margin of $\pm5$\% of the baseline, fixed before the comparison. Per instance, the warm-process difference \strat{Skel+10} minus \strat{Dump-N} averages $§1$ to $§2$ points of the baseline, and every 95\% CI lies within $[§3,§4]$ under both delivery mechanisms. The two rules converge because visit counts rank the interior pages near the top: the matched sets share 20 of 28 pages on the 100K workloads, 12 of 14 on Tail-Mixed, and 13 of 15 on Tail-Hit.§5",
        ("§1", "sg1(min(mb4(v,'mean_d')))"), ("§2", "sg1(max(mb4(v,'mean_d')))"),
        ("§3", "math.floor(min(mb4(v,'ci_lo')))"), ("§4", "'%+d' % math.ceil(max(mb4(v,'ci_hi')))"),
        ("§5", "within_margin(v)"))),
    ("s7-finding-10x", "whereas the full dump loses delivery under memory pressure and, under per-page delivery, "
                       "regresses on Tail-Mixed at $10\\times$«regress_pp(v)».")]
OLD_LITERAL.update({
    "s6-matched4": "\\strat{Skel+10} holds 28 pages on the two 100K workloads and 14 on Tail-Mixed in every instance, so we compare it with \\strat{Dump-28} and \\strat{Dump-14} under a margin of $\\pm5$\\% of the baseline, fixed before the comparison. Per instance, the warm-process difference \\strat{Skel+10} minus \\strat{Dump-N} averages $-1.4$ to $+0.8$ points of the baseline, and every 95\\% CI lies within $[-3,+2]$ under both delivery mechanisms. The two rules converge because visit counts rank the interior pages near the top: the matched sets share 20 of 28 pages on the 100K workloads and 12 of 14 on Tail-Mixed. Tail-Hit, whose matched set would hold 15 pages, was not tested.",
    "s7-finding-10x": "whereas the full dump loses delivery under memory pressure and regresses on Tail-Mixed at $10\\times$.",
})
CLAIMS = [(c, V7_REWORD.get(c, t)) for c, t in CLAIMS if c != "s6-matched"] + V7_NEW


# ------------------------------------------------- manuscript issues fixed (2026-10-10)
def at_or_below(v, w, sets):
    """'stays at or below baseline': no set is a robust increase, every mean is <= 0."""
    for s in sets:
        assert v.u(w, s) <= 0 and v.ulo(w, s) < 0, f"{w} {s} is above baseline"
    return ""


def win(v, w, s, arm):
    assert v.uhi(w, s, arm) < 0, f"{w} {s} {arm} is not a robust reduction"
    return ""


def tie(v, w, s, arm):
    assert v.ulo(w, s, arm) < 0 < v.uhi(w, s, arm), f"{w} {s} {arm} is not a tie"
    return ""


def best_recommended(v, w, db):
    """Seed-1 warm-process latency of the faster of the recommended sets (Skel, Skel+10)."""
    return min(v.s1(w, s, db=db) for s in ("2d", "2e_K10"))


def clustered_slower(v):
    assert all(best_recommended(v, w, "ta") > best_recommended(v, w, "orig") for w in ABC), \
        "clustering helps a recommended set somewhere"
    return ""


def unchanged_us(a, b, tol=5):
    assert abs(a - b) <= tol, f"{a:.0f} vs {b:.0f} us is a change"
    return ""


_FQ_SEED1 = "lohi([-fqred(v,w,'2f_slru') for w in ABC],{})"
_FQ_TEN = "lohi([-v.u(w,'2f_slru',metric='first_query_us') for w in ABC],{})"
_S6M_TAIL_OLD = ("and turns the tail workloads into wins (§9\\% to §10\\% below on Tail-Mixed, "
                 "§11\\% above to §12\\% below on Tail-Hit).")
FIXED = {
    # abstract and conclusion sit beside ten-instance numbers: use the ten-instance means
    "abs-fq-dump": dict(CLAIMS)["abs-fq-dump"].replace(_FQ_SEED1.format(0), _FQ_TEN.format(0))
                                              .replace(_FQ_SEED1.format(1), _FQ_TEN.format(1)),
    "concl": dict(CLAIMS)["concl"].replace(_FQ_SEED1.format(0), _FQ_TEN.format(0))
                                  .replace(_FQ_SEED1.format(1), _FQ_TEN.format(1)),
    # a page-matched learned set: 28 pages on the 100K workloads, 14 on Tail-Mixed
    "s6-learned": T(r"the learned selector reduces first-query latency by §1\%, §2\%, and §3\% on the three workloads",
        ("§1", "rd(-v.u('A','learned_markov_28',metric='first_query_us'),1)"),
        ("§2", "rd(-v.u('B','learned_markov_28',metric='first_query_us'),1)"),
        ("§3", "rd(-v.u('C','learned_markov_14',metric='first_query_us'),1)")),
}
for _c in ("abs-fq-dump", "concl"):
    assert FIXED[_c] != dict(CLAIMS)[_c]
_s6m = dict(CLAIMS)["s6-mechanism"]
_tail_old = T(_S6M_TAIL_OLD, ("§9", "red(v.u('C','2f_top500'))"), ("§10", "red(v.u('C','2f_top500','async_win'))"),
              ("§11", "inc(v.u('C_hit','2f_top500'))"), ("§12", "red(v.u('C_hit','2f_top500','async_win'))"))
assert _s6m.count(_tail_old) == 1
FIXED["s6-mechanism"] = _s6m.replace(_tail_old, T(
    "and turns Tail-Mixed into a win (§9\\% to §10\\% below), while Tail-Hit moves from §11\\% above baseline to §12\\% below, a tie.",
    ("§9", "red(v.u('C','2f_top500'))"),
    ("§10", "red(v.u('C','2f_top500','async_win')) + win(v,'C','2f_top500','async_win')"),
    ("§11", "inc(v.u('C_hit','2f_top500'))"),
    ("§12", "red(v.u('C_hit','2f_top500','async_win')) + tie(v,'C_hit','2f_top500','async_win')")))
FIXED_NEW = [
    ("s6-tm-large", "Tail-Mixed stays at or below baseline because even its full working set is only 1.8~MB"
                    "«at_or_below(v,'C',('2f_top500','2f_slru'))»."),
    ("s7-layout-best", T(r"the best warm-process end-to-end latency of the recommended sets under the default versus the clustered layout is §1 versus §2~\textmu s on Scattered-Zipf-100K, §3 versus §4~\textmu s on Uniform-100K, and §5 versus §6~\textmu s on Tail-Mixed.§7",
        ("§1", "us(best_recommended(v,'A','orig'))"), ("§2", "us(best_recommended(v,'A','ta'))"),
        ("§3", "us(best_recommended(v,'B','orig'))"), ("§4", "us(best_recommended(v,'B','ta'))"),
        ("§5", "us(best_recommended(v,'C','orig'))"), ("§6", "us(best_recommended(v,'C','ta'))"),
        ("§7", "clustered_slower(v)"))),
    ("s7-layout-floor", T(r"The synchronous first-query floor of \strat{Skel+10} on Tail-Mixed is unchanged by layout, §1 versus §2~\textmu s,",
        ("§1", "us(v.med('C','2e_K10','pread','fq_median'))"),
        ("§2", "us(v.med('C','2e_K10','pread','fq_median',db='ta')) + unchanged_us(v.med('C','2e_K10','pread','fq_median'), v.med('C','2e_K10','pread','fq_median',db='ta'))"))),
]
OLD_LITERAL.update({
    "s6-tm-large": "Tail-Mixed remains below baseline because even its full working set is only 1.8~MB.",
    "s7-layout-best": "the best warm-process end-to-end latency under the default versus the clustered layout is 414 versus 507~\\textmu s on Scattered-Zipf-100K, 475 versus 670~\\textmu s on Uniform-100K, and 253 versus 302~\\textmu s on Tail-Mixed.",
    "s7-layout-floor": "The synchronous first-query floor is unchanged by layout, 183 versus 181~\\textmu s,",
})
CLAIMS = [(c, FIXED.get(c, t)) for c, t in CLAIMS] + FIXED_NEW
PENDING = []
UNCHANGED = [u for u in UNCHANGED if "PENDING" not in u[2] and "ratio about" not in u[1]] + [
    (r".", r"5~ms grace period|also reaches 100\\%|about 100~\\textmu s",
     "results/unified_v5/grace_check: Dump first query 97 to 104 us, median 100, over both modes and sleeps 0/5/20 ms"),
]


# ------------------------------- whole-file baselines and the 10x definition (2026-10-13)
# TODO L200: the two profile-free whole-file baselines that unified_v7 measured (whole_file
# under async_win and populate). TODO L408: the 10x paragraph states what a direction is and
# gives the Skel+500 intervals.
WF = ("async_win", "populate")


def wf_ms(v, arm, i=None):
    """Whole-file dispatch in ms (median over instances, page-list read included) over ALL4."""
    vals = [P.rd(v.med(w, "whole_file", arm, "deliver_us_median", add=("parse_us_median",)) / 1000, 0)
            for w in ALL4]
    return same(*vals) if i is None else (min if i == 0 else max)(vals, key=float)


def wf_x(v, arm, i):
    """Warm-process end-to-end latency as a multiple of the baseline, higher in every instance."""
    for w in ALL4:
        assert v.u(w, "whole_file", arm) > 0 and nsign(v, w, "whole_file", arm) == 10, f"{w} {arm}"
    return lohi([P.ratio(v.u(w, "whole_file", arm)) for w in ALL4], i)


def wf_fq(v, i):
    return lohi([-v.u(w, "whole_file", a, metric="first_query_us") for w in ALL4 for a in WF], i)


def wf_floor(v):
    """'reach the first-query latency of Dump': within one point of per-page Dump everywhere."""
    for w in ALL4:
        for a in WF:
            assert nsign(v, w, "whole_file", a, "first_query_us") == 10, f"{w} {a} first query"
            assert abs(v.u(w, "whole_file", a, metric="first_query_us")
                       - v.u(w, "2f_slru", metric="first_query_us")) <= 1, f"{w} {a} off the Dump floor"
    return ""


def ref_size_only(v):
    assert all(k[1] == "orig" for k in v.unc if k[2] == "whole_file"), "whole_file measured beyond orig"
    return ""


_WF_MS = (("15", "wf_ms(v,'async_win')"), ("102", "wf_ms(v,'populate',0)"), ("103", "wf_ms(v,'populate',1)"))
_WF_X = (("16", "wf_x(v,'async_win',0)"), ("18", "wf_x(v,'async_win',1)"),
         ("111", "wf_x(v,'populate',0)"), ("124", "str(wf_x(v,'populate',1)) + wf_floor(v)"))
WF_NEW = [
    ("tab-wholefile", T(r"\strat{File} & Every page of the database file, window-chunked hints & none & 26{,}331 & 15~ms window-chunked \\"
                        "\n" r"\strat{Populate} & Every page of the database file, synchronous \texttt{mmap(MAP\_POPULATE)} & none & 26{,}331 & 102 to 103~ms \\",
                        *_WF_MS)),
    ("s5-wholefile", T(r"\strat{File} and \strat{Populate} reach the first-query latency of \strat{Dump}, 88\% to 90\% below baseline across instances, because every page the query touches is resident. Loading all 26{,}331 pages costs 15~ms window-chunked and 102 to 103~ms under \texttt{MAP\_POPULATE}, so warm-process end-to-end latency rises 16 to $18\times$ and 111 to $124\times$, respectively, in all ten instances of every workload.",
                       ("88", "str(wf_fq(v,0)) + wf_floor(v)"), ("90", "wf_fq(v,1)"), *_WF_MS, *_WF_X)),
    ("guid-wholefile", T(r"Loading the whole file is no substitute: it matches the dump's first-query latency but raises end-to-end latency 16 to $18\times$ window-chunked and 111 to $124\times$ with \texttt{MAP\_POPULATE}.",
                         *_WF_X)),
    ("lim-wholefile", "The whole-file baselines, including the synchronous \\texttt{MAP\\_POPULATE}, were measured "
                      "at the reference size only.«ref_size_only(v)»"),
]
# what the manuscript said before these baselines were measured
OLD_LITERAL.update({c: "They do not cover a whole-file \\texttt{readahead(2)} call or an eagerly populated "
                       "mapping (\\texttt{MAP\\_POPULATE})." for c, _t in WF_NEW})

_s7 = dict(CLAIMS)["s7-10x"]
_DIR = "keep their direction under per-page delivery."
_K500 = ("«inc(v.u('A','2e_K500'))»\\% above baseline to "
         "«inc(v.u('A','2e_K500',db='1gb')) + neutral_same_sign(v,'A','2e_K500')»\\% above.")
assert _s7.count(_DIR) == 1 and _s7.count(_K500) == 1
WF_REWORD = {"s7-10x": _s7.replace(
    _DIR, "keep their direction, the sign of the ten-instance mean change, under per-page delivery.").replace(
    _K500, "«inc(v.u('A','2e_K500'))»\\% above baseline (95\\% CI $[«r0(v.ulo('A','2e_K500'))»,"
           "«r0(v.uhi('A','2e_K500'))»]$) to «inc(v.u('A','2e_K500',db='1gb')) + neutral_same_sign(v,'A','2e_K500')»"
           "\\% above ($[«r0(v.ulo('A','2e_K500',db='1gb'))»,«r0(v.uhi('A','2e_K500',db='1gb'))»]$).")}
CLAIMS = [(c, WF_REWORD.get(c, t)) for c, t in CLAIMS] + WF_NEW
UNCHANGED += [
    (r"^Two baselines need neither a profile", ALL,
     "results/pilot_whole_file_delivery (32 pages) and database geometry, no batch number"),
]


# ------------------------------------------------------ cache-reset mechanism (2026-10-13)
# TODO L243: the protocol paragraph names the eviction mechanism and says the cold gate
# excluded no repetition. The gate number is the batch's, the rest is harness code.
def cold0(v):
    """'post-reset residency was 0% in every repetition': every kept rep of every seed."""
    vals = [r["cold_pct"] for r in v._raw()]
    assert vals and all(c != "" and float(c) == 0 for c in vals), "a repetition was not fully cold"
    return "0"


RESET_NEW = [
    ("s4-coldgate", "In the unified batch, post-reset residency was «cold0(v)»\\% in every repetition, "
                    "so none was excluded."),
]
OLD_LITERAL.update({"s4-coldgate": "We exclude a cell if post-reset residency exceeds 1\\%, and every "
                                   "reported cell incurs major page faults."})
CLAIMS = CLAIMS + RESET_NEW
_RESET_LINE = r"^Before each workstation measurement, a privileged test harness"
assert sum(u[0] == _RESET_LINE for u in UNCHANGED) == 1
UNCHANGED = [u for u in UNCHANGED if u[0] != _RESET_LINE] + [
    (r"^Before each workstation measurement, the test harness evicts",
     r"writes 3 to|more than 1\\% of the selected pages|below 1\\% of the cold baseline",
     "drop_caches value (harness helper), pre-set cold-gate threshold, separate CPU-cache measurement"),
]


# --------------------------------------------------- Figure reversal re-plot (2026-10-14)
# TODO L279: both rows of the figure are now ten-instance means, so the sentences that quoted
# its seed-1 values quote ten-instance ones, and the caption's statements are asserted.
REV_SETS = ("layers_5", "2d", "2e_K10", "2f_top14", "2e_K500", "2f_top500", "2f_slru")
FLOOR = (("2f_slru", "async"), ("2f_slru", "async_win"), ("whole_file", "async_win"), ("whole_file", "populate"))


def rev_fq(v, w):
    """First-query mean change of every cell the figure draws for workload w."""
    cells = [(s, a) for s in REV_SETS for a in ("async", "async_win")] + [("whole_file", a) for a in WF]
    return {c: v.u(w, c[0], c[1], metric="first_query_us") for c in cells}


def at_floor(v, w, cells):
    fq = rev_fq(v, w)
    lo = min(fq.values())
    for c in cells:
        assert fq[c] - lo <= 1, f"{w} {c} is not at the first-query floor"


def dump_floor(v):
    """'the dump sits at the floor ..., level with the whole-file baselines'."""
    for w in ABC:
        at_floor(v, w, FLOOR)
    return ""


def rev_caption(v):
    for w in ABC:
        assert all(x < 0 for x in rev_fq(v, w).values()), f"{w}: a set does not shorten the first query"
        at_floor(v, w, FLOOR)
    for w in ("A", "B"):
        for s, a in FLOOR:
            assert v.ulo(w, s, a) > 0, f"{w} {s} {a} is not above baseline end to end"
        for s in ("2d", "2e_K10"):
            for a in ("async", "async_win"):
                assert v.uhi(w, s, a) < 0, f"{w} {s} {a} is not below baseline end to end"
    return ""


_TEN_FQ = "lohi([-v.u(w,{s},metric='first_query_us') for w in ABC{f}],{i})"
REV_REWORD = {
    "fig-rev-cap": "Every set shortens the first query, and the full dump and the whole-file baselines bring it "
                   "to its floor. On the two broad workloads their dispatch puts them above the baseline end to "
                   "end under either mechanism, whereas \\strat{Skel} and \\strat{Skel+10} stay below it.«rev_caption(v)»",
    "s5-fq": T(r"the full working-set dump sits at the floor on all three workloads (Figure~\ref{fig:reversal}, top), level with the whole-file baselines.§0 Across instances it reduces cold-query latency by 88\% to 90\%, to 96 to 99~\textmu s. The targeted sets reduce it by 36\% to 65\%",
        ("§0", "dump_floor(v)"),
        ("88", _TEN_FQ.format(s="'2f_slru'", f="", i=0)), ("90", _TEN_FQ.format(s="'2f_slru'", f="", i=1)),
        ("96", "us(min(v.med(w,'2f_slru','async','fq_median') for w in ABC))"),
        ("99", "us(max(v.med(w,'2f_slru','async','fq_median') for w in ABC))"),
        ("36", _TEN_FQ.format(s="s", f=" for s in ('2d','2e_K10','2f_top14')", i=0)),
        ("65", _TEN_FQ.format(s="s", f=" for s in ('2d','2e_K10','2f_top14')", i=1))),
}
_s7s = dict(CLAIMS)["s7-sampling"]
_OUTLIER = _s7s[_s7s.index("The single instance in Table~\\ref{tab:e2e-ac} and Figure~\\ref{fig:reversal}"):]
REV_REWORD["s7-sampling"] = _s7s.replace(_OUTLIER, T(
    r"The single instance in Table~\ref{tab:e2e-ac} is an instantiation outlier on Scattered-Zipf-100K: its 514~\textmu s baseline is far below the cross-instance median of 892~\textmu s, so its \strat{Skel} change of $-12$\% understates the cross-instance $-28$\%.",
    ("514", "us(v.base1('A'))"), ("892", "us(v.med('A','baseline'))"),
    ("-12", "under(v.e1('A','2d'), v.u('A','2d'))"), ("-28", "s0(v.u('A','2d'))")))
assert REV_REWORD["s7-sampling"] != _s7s
OLD_LITERAL.update({
    "fig-rev-cap": "Bars and labels show one workload instance (seed~1)",
    "s5-fq": "It reduces cold-query latency by 81\\% to 91\\%, from baselines of 514 to 1{,}074~\\textmu s to 97 to 99~\\textmu s.",
    "s7-sampling": "and its Uniform-100K \\strat{Skel-5} change of $-36$\\% overstates the cross-instance $-1$\\%.",
})
CLAIMS = [(c, REV_REWORD.get(c, t)) for c, t in CLAIMS]


# ------------------------------------------------------------ artifact paragraph (2026-10-14)
# TODO L283: the batch name and the code commit it ran on, as the batch README records them.
def batch_commit(v):
    m = re.search(r"with the batch code of ([0-9a-f]{7,40})", (v.dir / "README.md").read_text())
    assert m, f"{v.dir}/README.md names no batch code commit"
    return m.group(1)[:7]


ARTIFACT_NEW = [
    ("s4-artifact", "come from one batch, unified\\_«v.tag», measured in one contiguous window with commit "
                    "\\texttt{«batch_commit(v)»} of the artifact."),
]
OLD_LITERAL.update({"s4-artifact": "\n\\todo{Provenance, updated 29 Sep."})
CLAIMS = CLAIMS + ARTIFACT_NEW


# ------------------------------------------------------ Figure portability (2026-10-15)
# TODO L453 (2): the scatter's caption counts OpenWhisk cells, not unified-batch numbers.
UNCHANGED += [
    (r"^\\caption\{First-query effectiveness \$R\$ on the workstation against \$R\$ inside OpenWhisk", ALL,
     "OpenWhisk campaigns (revised-freeze comparison table), no batch number"),
]


# ------------------------------------------------------ second-host native run (2026-10-19)
# TODO L453 (1): these numbers come from results/ow_native_e2e, the native run on the
# OpenWhisk host, through tools/compare_hosts_e2e.py, and not from the unified batch.
import csv  # noqa: E402
import json  # noqa: E402

OW_DIR = P.ROOT / "results/ow_native_e2e"


def _ow_json():
    return json.loads((OW_DIR / "host_comparison.json").read_text())


def _ow_u(w, s, arm="async", metric="e2e_warm_us", field="mean_pct"):
    with open(OW_DIR / "uncertainty.csv") as f:
        for r in csv.DictReader(f):
            if (r["workload"], r["db"], r["strategy"], r["arm"], r["metric"]) == (w, "orig", s, arm, metric):
                return float(r[field])
    raise KeyError(f"ow_native_e2e: no {w} {s} {arm} {metric}")


def ow_count(key, metric="e2e_warm_us"):
    return _ow_json()["counts"][metric][key]


def ow_reversal(host):
    """The single reversed pair: Tail-Mixed, window-chunked, Skel vs Dump, Dump faster on the
    workstation and slower on the second host. Magnitude in points of the baseline."""
    rev = _ow_json()["reversed"]
    assert len(rev) == 1, f"{len(rev)} reversed pairs"
    r = rev[0]
    assert (r["metric"], r["workload"], r["arm"], r["first"], r["second"]) == \
        ("e2e_warm_us", "C", "async_win", "Skel", "Dump"), f"reversed pair is {r}"
    assert r["ws_mean_d"] > 0 > r["ow_mean_d"], "direction of the reversal changed"
    return str(abs(P.r0(r["ws_mean_d" if host == "ws" else "ow_mean_d"])))


def ow_fq_holds():
    assert ow_count("reversed", "first_query_us") == 0, "a first-query pair reverses"
    return ""


def ow_dump_slowest():
    for w in ABC:
        for a in ("async", "async_win"):
            d = _ow_u(w, "2f_slru", a)
            assert all(d > _ow_u(w, s, a) for s in ("2d", "2e_K10", "2f_top14")), f"{w} {a}: Dump not slowest"
    return ""


def ow_dump_x(i):
    return lohi([P.ratio(_ow_u(w, "2f_slru")) for w in ("A", "B")], i)


def ow_half():
    """'a cold miss costs about half as much': baseline first-query ratio within 0.45 to 0.55."""
    assert all(0.45 <= x <= 0.55 for x in _ow_json()["baseline_first_query_ratio"].values()), "not about half"
    return ""


def ow_dispatch(i):
    v = _ow_json()["dispatch_ratio"].values()
    return P.rd(min(v) if i == 0 else max(v), 1)


def ow_skel(w):
    """Skel's end-to-end change on the second host: within noise on A and B, a reduction on C."""
    lo, hi = _ow_u(w, "2d", field="ci_lo"), _ow_u(w, "2d", field="ci_hi")
    if w == "C":
        assert hi < 0, "Skel on Tail-Mixed is not a robust reduction on the second host"
    else:
        assert lo < 0 < hi, f"Skel on {w} is not within noise on the second host"
    return str(P.r0(_ow_u(w, "2d")))


def ow_broad_noise():
    """'the interior-page gain on the two broad workloads falls within noise'."""
    ow_skel("A"), ow_skel("B")
    return ""


NATIVE_NEW = [
    ("s7-native", T(r"Of the 36 strategy pairs, six per workload and delivery mechanism, 20 keep a significant order on both hosts, 15 are ties on at least one host, and one reverses: on Tail-Mixed, window-chunked \strat{Dump} is faster than \strat{Skel} by 16 points of the baseline on the workstation but slower by 62 points on the second host. The first-query order holds without a reversal.§0 \strat{Dump} is the slowest strategy end to end in every workload and mechanism on the second host, at 31 to $34\times$ the baseline under per-page delivery on the broad workloads,§1 so the reversal of Section~\ref{sec:evaluation} is stronger there. The size of the precise sets' gain does not transfer. A cold miss on the second host costs about half as much,§2 while dispatch costs 1.1 to 2.1 times as much, so \strat{Skel} changes end-to-end latency by $-6$\% and $-7$\% on the two broad workloads, within noise, and by $-22$\% on Tail-Mixed, whose cold query is longer.",
        ("36", "ow_count('pairs')"), ("20", "ow_count('same_order')"),
        ("15", "ow_count('tie_both') + ow_count('tie_one')"),
        ("16", "ow_reversal('ws')"), ("62", "ow_reversal('ow')"), ("§0", "ow_fq_holds()"),
        ("31", "ow_dump_x(0)"), ("34", "ow_dump_x(1)"), ("§1", "ow_dump_slowest()"), ("§2", "ow_half()"),
        ("1.1", "ow_dispatch(0)"), ("2.1", "ow_dispatch(1)"),
        ("-6", "ow_skel('A')"), ("-7", "ow_skel('B')"), ("-22", "ow_skel('C')"))),
    ("abs-host", "A cold miss there costs half as much, so the interior-page gain on the two broad workloads falls "
                 "within noise.«ow_half() + ow_broad_noise()»"),
]
OLD_LITERAL.update({
    "s7-native": "Because each OpenWhisk invocation opens a fresh handle, this experiment does not show that the "
                 "end-to-end strategy ranking transfers.",
    "abs-host": "Apache OpenWhisk tests on a second host confirm the first-query benefit; they do not test the "
                "end-to-end ranking.",
})
CLAIMS = CLAIMS + NATIVE_NEW


# ------------------------------------------- hotset sizes and the grace check (2026-10-19)
# The atomic check found sizes that no claim verified: Tail-Mixed's working set read 1.8 MB
# (v7: 467 to 483 pages, 1.9 MB in the paper's convention of 4 KB per page over 1000), one
# 18 MB beside four 17.7 MB, and Skel+500's "about 500" (338 pages on Tail-Mixed). They are
# now rendered from the batch's own hotsets. The grace-period sentence now comes from
# results/grace_check_v7 (run with the v7 code) instead of results/unified_v5/grace_check.
def _pages(v, w, s):
    fs = sorted(v.dir.glob(f"seed[0-9][0-9]/main/work/hotset_{w}_orig_{s}.csv"))
    assert len(fs) == 10, f"{v.tag} {w} {s}: {len(fs)} hotset files"
    return statistics.median(sum(1 for _ in open(f)) - 1 for f in fs)


def mb(v, ws):
    """Working-set size (median over instances, pages x 4 KB / 1000), one value for all of ws."""
    return same(*[P.rd(_pages(v, w, "2f_slru") * 4 / 1000, 1) for w in ws])


def k500_about(v):
    for w in ("A", "B"):
        assert abs(_pages(v, w, "2e_K500") - 500) <= 25, f"Skel+500 on {w} is not about 500 pages"
    return "500"


def k500_tm(v):
    return str(P.r0(_pages(v, "C", "2e_K500")))


GRACE = P.ROOT / "results/grace_check_v7"


def _grace(ms):
    with open(GRACE / f"sleep{ms}ms/summary.csv") as f:
        return list(csv.DictReader(f))


def grace_ms():
    assert (GRACE / "sleep5ms/summary.csv").exists(), "no 5 ms grace run"
    return "5"


def grace_reach():
    """'with a 5 ms grace period the chunked mode also reaches 100%'."""
    vals = [float(r["delivery_pct_median"]) for r in _grace(5) if r["arm"] == "async_win"]
    assert vals and all(x >= 99.5 for x in vals), f"chunked delivery at 5 ms: {vals}"
    return "100"


def grace_fq():
    """'first-query latency is flat at about 100 us under both modes at every grace period'."""
    fq = [float(r["fq_median"]) for ms in (0, 5, 20) for r in _grace(ms)]
    assert len(fq) == 12 and all(90 <= x <= 110 for x in fq), f"first query not about 100 us: {fq}"
    return "100"


_MB = {"17.7~MB": "«mb(v,'AB')»~MB", "1.8~MB": "«mb(v,'C')»~MB"}


def _mbify(t):
    for lit, expr in _MB.items():
        t = t.replace(lit, expr)
    return t


SIZE_NEW = [
    ("tab-k500-size", T(r"about 500 for $K=500$ (338 on Tail-Mixed)", ("500", "k500_about(v)"), ("338", "k500_tm(v)"))),
    ("s3-same-ws", "For the same «mb(v,'AB')»~MB working set,"),
    ("s5-tm-ws", "on Tail-Mixed, where it contains «mb(v,'C')»~MB."),
    ("s7-ram-dump", "The «mb(v,'AB')»~MB full dump falls"),
    ("s7-ram-tm", "Tail-Mixed is not measured on this axis because its «mb(v,'C')»~MB working set"),
    ("s3-grace", T(r"with a 5~ms grace period between dispatch and query, the chunked mode also reaches 100\%, and first-query latency is flat at about 100~\textmu s under both modes at every grace period",
                   ("5", "grace_ms()"), ("100", "grace_reach()"), ("100", "grace_fq()"))),
]
OLD_LITERAL.update({"tab-k500-size": "14 to 28 for $K=10$; about 500 for $K=500$ &",
                    "s3-same-ws": "For the same 18~MB working set,",
                    "s5-tm-ws": "on Tail-Mixed, where it contains 1.8~MB.",
                    "s7-ram-tm": "Tail-Mixed is not measured on this axis because its 1.8~MB working set"})
CLAIMS = [(c, _mbify(t)) for c, t in CLAIMS] + SIZE_NEW
UNCHANGED = [(lrx, r"4\{,\}400(-page| calls)|about 4\{,\}400 or 480|\$\\approx\$4400", why)
             if why == "Dump set size (hotset)" else (lrx, srx, why)
             for lrx, srx, why in UNCHANGED if "unified_v5/grace_check" not in why]


# ------------------------------------------- Tables 3 to 5 regenerated from raw (2026-10-20)
# Table 3 (one instance, absolute us) became Figure boundary, Table 4 became Table matched, and
# Table 5 gained CIs and a Tail-Hit block. The two tables are now written from raw.csv by
# paper/tables/gen_tables.py, so their cell claims go. Sentences that cited the removed tables
# now cite the figure, and the boundary paragraph states ten-instance values.
B4 = ("layers_5", "2d", "2e_K10", "2f_slru")


def shift(v, i):
    """Points of the baseline that the external-warmer boundary adds, over the dumbbell sets."""
    return lohi([v.u(w, s, metric="e2e_us") - v.u(w, s) for w in ALL4 for s in B4], i)


def noise(v, w, s, metric):
    assert v.ulo(w, s, metric=metric) < 0 < v.uhi(w, s, metric=metric), f"{w} {s} {metric} is not within noise"
    return ""


def same_order(v):
    """'the open cost does not change the order among strategies' (means, every workload)."""
    for w in ALL4:
        warm = sorted(B4, key=lambda s: v.u(w, s))
        ext = sorted(B4, key=lambda s: v.u(w, s, metric="e2e_us"))
        assert warm == ext, f"{w}: order changes between the boundaries"
    return ""


def open_range(v, i):
    """Open-cost median per (instance, workload, set) over the dumbbell sets, per-page."""
    cells = {}
    for r in v._raw():
        if r["db"] == "orig" and r["arm"] == "async" and r["open_us"] and r["strategy"] in B4 and r["workload"] in ALL4:
            cells.setdefault((r["seed"], r["workload"], r["strategy"]), []).append(float(r["open_us"]))
    return lohi([statistics.median(x) for x in cells.values()], i)


_GONE = ("s5-boundary", "s5-open-range")
_REFS = (("(Table~\\ref{tab:competitive}, lower block)", "(Figure~\\ref{fig:reversal})"),
         ("(Table~\\ref{tab:competitive})", "(Figure~\\ref{fig:reversal})"),
         ("measured in the same batch as Table~\\ref{tab:e2e-ac},", "measured in the same batch as Figure~\\ref{fig:reversal},"),
         ("fixed before the comparison.", "fixed before the comparison (Table~\\ref{tab:matched})."))


def _retarget(cid, t):
    for old, new in _REFS:
        t = t.replace(old, new)
    if cid == "s7-sampling":
        cut = t.index("The single instance in Table~\\ref{tab:e2e-ac}")
        t = t[:cut] + ("The baselines quoted in Section~\\ref{sec:methodology} come from one instance, an instantiation outlier on "
                       "Scattered-Zipf-100K: its «us(v.base1('A'))»~\\textmu s baseline is far below the cross-instance median of "
                       "«us(v.med('A','baseline'))»~\\textmu s.")
    return t


TABLES_NEW = [
    ("s5-boundary-ten", T(r"Adding the database-open cost shifts every set by 22 to 25 points of the baseline, so across instances \strat{Skel} on Scattered-Zipf-100K moves from 28\% below baseline in the warm-process model to 3\% below, within noise, in the external-warmer model. On Tail-Mixed, whose cold query is longer, \strat{Skel} remains 14\% below baseline, whereas \strat{Dump} moves from 6\% below to 17\% above. Thus, in the cost model the open cost does not change the order among strategies,§0 but it can make no prefetch the better choice. The open cost is an uncontrolled term: its median ranges from 125 to 234~\textmu s across instances and sets",
        ("22", "shift(v,0)"), ("25", "shift(v,1)"), ("28", "red(v.u('A','2d'))"),
        ("3", "red(v.u('A','2d',metric='e2e_us')) + noise(v,'A','2d','e2e_us')"),
        ("14", "red(v.u('C','2d',metric='e2e_us'))"), ("6", "red(v.u('C','2f_slru'))"),
        ("17", "inc(v.u('C','2f_slru',metric='e2e_us'))"), ("§0", "same_order(v)"),
        ("125", "open_range(v,0)"), ("234", "open_range(v,1)"))),
]
OLD_LITERAL.update({"s5-boundary-ten": "In one Scattered-Zipf-100K instance, adding the"})
CLAIMS = [(c, _retarget(c, t)) for c, t in CLAIMS
          if not c.startswith(("tab-e2e-", "tab-comp-", "tab-abl-")) and c not in _GONE] + TABLES_NEW
UNCHANGED += [
    (r"^\\caption\{The deployment boundary\.", ALL, "figure caption, no batch number"),
    (r"^\\caption\{Matched budgets:", ALL, "table caption: margin, workload names, no batch number"),
]
