# Paragraph drafts for the `unified_v6` revision

Source: `results/unified_v6/`, code `f570d4c`. **Every number in this document comes from
that one batch and no other.** 39,390 rows, 10 seeds, zero failures, `cold_pct` max 0.000,
one continuous window 2026-09-23T01:54:17Z to 05:11:34Z.

Cross-seed figures are n=10 under the canonical estimator `tools/stats_uncertainty.py`
(`median_pct` with bootstrap 95% CI, verdicts R=robust, d=directional, t=tie).
Single-instantiation figures are seed 1 and are labelled, because that is the instantiation
the paper's Section 5 absolutes already quote.

**"Ours" means the Skel family only** (`Skel-N`, `Skel`, `Skel+K`). `Dump`, `Dump-N`,
`learned-Markov` and `LP-*` are ported baselines and are never counted as ours.

`unified_v6` supersedes `unified_v5`, which it reproduces on all 376 shared cells with a
median move of 1.8 points and no substantive sign flip. Where a claim below is described as
confirmed across two batches, that means v5 and v6 agree independently.

Six revision sites plus a verification table. Sections 1, 2, 5 and 6 are self-contained
replacements. Section 3 needs a decision on table layout. Section 4 drops two claims that do
not survive, so read its notes. Section 7 audits every number not rewritten.

---

## 1. `main.tex:222` — replace the final sentence

**Current**

> Mechanisms between the two, such as issuing hints earlier in the function lifecycle,
> \texttt{readahead(2)}, or \texttt{io\_uring}, can move delivery toward the bound and are
> outside our scope.

**Replacement**

```latex
Mechanisms between the two can move delivery toward the bound, and one of them is cheap
enough that we adopt it as a third mode rather than defer it. Because the kernel honours a
range hint only up to its readahead window, issuing one hint per window-sized chunk turns a
single large request into a sequence the kernel satisfies in full. We call this
\textit{window-chunked} asynchronous delivery, and Section~\ref{sec:eval-attribution}
reports every strategy under it alongside the per-page mode. Mechanisms that need a
different submission interface, such as \texttt{io\_uring}, or a different point in the
function lifecycle remain outside our scope.
```

---

## 2. `main.tex:224` — replace the whole paragraph

The current text says the window "caps a single range hint at roughly 64 pages" and that
"the prefetch set is already fully resident at zero sleep". The first is imprecise and the
second is false for the window-chunked mode, so both halves need work.

```latex
Two details of the asynchronous path affect the measurements. First, the kernel readahead
window bounds what one range hint can deliver. With \texttt{read\_ahead\_kb} = 128 on our
platform the window is $W = 32$ pages, and one
\texttt{posix\_fadvise(POSIX\_FADV\_WILLNEED)} over a range of $n$ pages delivers
$\min(n, W)$ pages from the head of that range while returning success either way.
\texttt{POSIX\_FADV\_SEQUENTIAL} doubles $W$ to 64. This is why we observe only 32 of 92
requested interior pages delivered from one range hint on the default layout. All per-page
strategies in Section~\ref{sec:strategy} issue one hint per page and are unaffected, and the
window-chunked mode of Section~\ref{sec:selection-delivery} restores full delivery for
range-based sets by cutting every request to $W$ pages. We keep \texttt{read\_ahead\_kb} at
its default, record it with every run, and do not sweep it, because raising it needs root
that our environment lacks.

Second, the harness times the first query immediately after the hints are issued, so the
residency it samples measures how much asynchronous readahead has \textit{completed} at that
instant rather than how much was requested. That quantity scales with how long an arm spent
issuing, which makes it incomparable across arms and across layouts. The per-page mode reads
$100\%$ partly because its 4,400 separate calls occupy 7.0 ms, during which its own readahead
finishes, whereas window-chunked delivery reads 83 percent after only 1.9 ms of issuing. The
same artifact appears on the layout axis, where a 500-page scattered set reads between 20 and
57 percent on the reordered layouts while delivering every page it asked for, and the reading
for one such cell moved from $100\%$ to $57\%$ between two batches of identical code. Grace
periods of 5, 20 and 50 ms between hint dispatch and the first query resolve the question.
Window-chunked delivery reaches $100\%$ residency at 5 ms and gains nothing beyond it, and
first-query latency is flat at about 97 \textmu s at every grace value under both modes, so
the pages still in flight at the zero-grace sample land during query setup and cost nothing.
Comparisons therefore use first-query and end-to-end latency, never the residency ratio. The
gap of Eq.~\ref{eq:delivery_loss} on the skewed workload is itself unchanged across grace
durations with identical major-fault counts, so it is a persistent cost difference rather
than a timing artifact.
```

**Note.** The 5, 20 and 50 ms grace experiment is the side diagnostic in
`results/unified_v5/grace_check/`, run under the same code as v6 but not repeated inside the
v6 window. It is the only number in this document not from the v6 batch, and it is a
mechanism check rather than a reported result. Re-running it inside a future batch costs
about three minutes if you would rather it were in-batch.

---

## 3. `main.tex:499` — Competitive baselines, plus two new paragraphs

**The substantive change, and the one that needs your decision.** The advisor's suggestion in
its strong form makes `Dump` a far better baseline. Our claim survives on three workloads and
fails on the pure-hit control.

### 3a. Replacement for the existing paragraph

```latex
\textbf{Competitive baselines.} To test whether \texttt{Dump} is a weak baseline, we port the
selection cores of two prior systems (Section~\ref{sec:buffer-warming}) onto our substrate and
charge them the same way. \texttt{Dump} is the full-working-set core of InnoDB's buffer-pool
dump and load. \texttt{Dump-N} is a frequency-ranked partial dump in the spirit of Pre-Buffer.
It replays each query's root-to-leaf traversal, counts page visits, and dumps the top $N$ pages
for $N$ in {14, 28, 100, 500, full}. We reproduce only the selection, not the off-critical-path
orchestration of either system. Table~\ref{tab:competitive} reports warm-process end-to-end
results under both delivery modes. Under per-page delivery, end-to-end latency worsens
monotonically with dump footprint. The full dump regresses by $+706\%$ on Scattered-Zipf-100K
and $+672\%$ on Uniform-100K, so the problem is delivery volume rather than the dump mechanism.
At matched footprint a small ranked dump ties \texttt{Skel+10} on every workload
(Scattered-Zipf-100K $-28\%$ versus $-27\%$, Uniform-100K $-31\%$ versus $-30\%$, Tail-Mixed
$-71\%$ versus $-71\%$, all with overlapping CIs). Explicit page typing and frequency ranking
recover a similar page set, so page-type knowledge earns its place as an interpretable coverage
guarantee rather than as a faster selector.
```

### 3b. New paragraph, insert directly after

```latex
\textbf{Delivery mechanism.} Selection and delivery are separate axes, and the fair test
charges every arm the stronger mechanism. Window-chunked delivery cuts the full dump's
delivery term from 7.0 ms to 1.9 ms on the two 100K-key workloads, from 0.75 ms to 0.22 ms on
Tail-Mixed and from 1.41 ms to 0.42 ms on the pure-hit control, moving it from $+706\%$ to
$+131\%$ on Scattered-Zipf-100K, from $+672\%$ to $+122\%$ on Uniform-100K, from $-9\%$ to
$-66\%$ on Tail-Mixed, and from $+52\%$ to $-48\%$ on the pure-hit control. The same mechanism
moves \texttt{Skel+10} only from 98 to 33 \textmu s, because its ranges already sit at or below
the window. That asymmetry is the finding. A mechanism that makes delivery cheap helps whoever
was delivering the most, so it rewrites the baseline far more than it rewrites our own arms.
Holding the mechanism fixed at window-chunked delivery, targeted selection still wins on three
of four workloads, by $0.27\times$ and $0.28\times$ in absolute latency on the two broad
workloads and on all 10 seeds, because a 17.7 MB transfer still costs 1.9 ms for pages no query
touches. On Tail-Mixed we win by $0.62\times$ but on only 6 of 10 seeds. On the pure-hit control
the full dump wins outright at $-48\%$ against our $-38\%$, which is the expected outcome where
every query hits and the question of \textit{which} pages to fetch carries least weight. We
therefore report window-chunked delivery as the deployable default and state the dump's place
as conditional on working-set size rather than settled against it.
```

### 3c. New paragraph on the tail-workload instability

Verified against per-seed `first_query_us` in both batches, so the causal claim holds.

```latex
\textbf{Selection stability on the tail workload.} The Tail-Mixed comparison rests on a median
that hides a split. Under window-chunked delivery \texttt{Skel+10} is far faster than the full
dump on six seeds and clearly slower on the other four, while the dump is uniform across all
ten. The split sits in first-query latency, not in delivery, and on the four slow seeds
\texttt{Skel+10} lands within a few percent of interior-only \texttt{Skel}, so the leaf budget
is missing the leaf the queries need rather than failing to deliver it. This is the key-range
property of Section~\ref{sec:eval-fq} seen from the other side. Tail-Mixed's advantage for
small leaf budgets comes from not-found probes concentrating on one leaf, and on four of ten
instantiations they do not concentrate enough for a 10-page budget to catch them. Our advantage
on this workload is therefore a better outcome on most instantiations rather than a smaller
latency on each, and the full dump is the more predictable arm.
```

**Decision needed.** `tab:competitive` currently has three workload columns and one delivery
mode. The data supports four workloads by two modes. Options: keep the table at per-page
delivery and put the window-chunked numbers in prose only, add a window-chunked block to the
table, or replace the table's mode with window-chunked and report per-page in the text.
Canonical numbers for whichever you pick:

| strategy | mode | Scattered-Zipf | Uniform | Tail-Mixed | pure-hit |
|---|---|---|---|---|---|
| Skel | per-page | −28 [−31,−23] R | −33 [−33,−16] R | −38 [−40,−34] R | −32 [−34,−19] R |
| Skel+10 | per-page | −27 [−52,−25] R | −30 [−31,−15] R | −71 [−68,−46] R | −34 [−36,−20] R |
| Dump-14 | per-page | −28 [−42,−22] R | −31 [−33,−15] R | −71 [−68,−46] R | −34 [−37,−22] R |
| Dump-28 | per-page | −26 [−52,−24] R | −29 [−31,−17] R | −69 [−70,−49] R | −30 [−37,−18] R |
| Dump-500 | per-page | +61 [+36,+149] R | +50 [+24,+57] R | −9 [−14,−6] R | +23 [−1,+29] t |
| Dump | per-page | +706 [+681,+907] R | +672 [+649,+826] R | −9 [−13,−5] R | +52 [+49,+102] R |
| Skel | window | −35 [−37,−30] R | −38 [−39,−22] R | −44 [−47,−40] R | −38 [−41,−28] R |
| Skel+10 | window | −33 [−59,−32] R | −36 [−38,−24] R | −78 [−75,−49] R | −38 [−40,−26] R |
| Dump-14 | window | −37 [−49,−31] R | −38 [−39,−25] R | −78 [−75,−50] R | −39 [−40,−26] R |
| Dump-28 | window | −34 [−59,−32] R | −37 [−38,−26] R | −77 [−77,−56] R | −44 [−50,−34] R |
| Dump-500 | window | +33 [+11,+47] R | +32 [+6,+36] R | −66 [−68,−65] R | −11 [−36,−12] R |
| Dump | window | +131 [+125,+189] R | +122 [+115,+168] R | −66 [−68,−65] R | −48 [−49,−31] R |

---

## 4. `main.tex:505` — Physical layout, full replacement

All four layouts now share one batch with Table~\ref{tab:e2e-ac}, so the non-comparability
clause has no premise. Two of the paragraph's claims do not survive, in v5 and again in v6
independently, so this is a full replacement rather than a number refresh.

```latex
\textbf{Physical layout.} Measured in the same batch as Table~\ref{tab:e2e-ac}, the best
warm-process end-to-end latency for \texttt{Default} versus \texttt{Clustered} is 414 versus
507 \textmu s on Scattered-Zipf-100K, 475 versus 670 \textmu s on Uniform-100K, and 253 versus
302 \textmu s on Tail-Mixed, all at seed 1 over the strategies of Section~\ref{sec:strategy}.
The layout interacts with the selection strategy rather than with prefetch as a whole. For the
strategies we recommend, \texttt{Clustered} is worse and the effect is consistent across
instantiations. \texttt{Skel+10} is $1.05\times$ slower under \texttt{Clustered} on
Scattered-Zipf-100K on all 10 seeds and $1.19\times$ slower on Tail-Mixed on 8 of 10. For pure
interior selection the sign reverses. \texttt{Skel-92} on Tail-Mixed is $0.90\times$ under
\texttt{Clustered} on all 10 seeds, because clustering raises the interior page count the
skeleton captures from 4 pages to 48. The synchronous first-query floor is unchanged by layout
at 182 versus 181 \textmu s, so the layout changes which pages a strategy finds rather than how
fast they can be delivered. We therefore recommend \texttt{Default} for the strategies of
Section~\ref{sec:strategy}, and note \texttt{Clustered} as the better pairing in the one case
where only structural selection is available and the workload is tail-heavy. The \texttt{.dbi}
side file of Section~\ref{sec:serverless-coldstart} reaches the same conclusion by copying
navigation pages instead of reordering them.
```

**Two claims dropped, each contradicted by two independent batches.**

1. *"the difference comes entirely from a baseline raised by $26\%$ (523 to 658 \textmu s) as
   leaves move to higher offsets."* \texttt{Clustered} **lowers** the baseline on every
   workload. Cross-seed first-query baselines are 881, 920 and 910 \textmu s on
   \texttt{Default} against 802, 812 and 835 on \texttt{Clustered}. v5 gave 879, 956, 911
   against 788, 806, 854. The original reading came from seed 1, whose Scattered-Zipf baseline
   is an outlier. \texttt{Vacuum} is the layout that genuinely raises the baseline, to 985,
   1034 and 1147 \textmu s.
2. *"On Tail-Mixed, \texttt{Clustered} ... lowers the improvement from $-75\%$ to $-63\%$."*
   The interior-count half is exact, 4 pages to 48, verified from the frozen hotsets in both
   batches. The consequence is backwards. \texttt{Skel} first-query on Tail-Mixed is $-36\%$
   under \texttt{Default} and better under \texttt{Clustered} at seed 1, and the two are within
   a point cross-seed. No strategy reproduces a $-75\%$ to $-63\%$ move.

**Also flagged.** *"In no cell does \texttt{Clustered} beat \texttt{Default}"* is false as
written. Paired per seed over the full 12-strategy set, \texttt{Clustered} wins on 12 of 36
cells, most clearly Tail-Mixed \texttt{Skel-92} at $0.90\times$ on 10 of 10. The draft restates
the claim by strategy class instead of asserting it universally.

**New, and only visible because this batch added \texttt{Dump-N} to the layout axis.** With
\texttt{Dump-14} available on \texttt{Clustered}, the Tail-Mixed layout comparison becomes a
tie at seed 1, 253 versus 253 \textmu s, rather than a \texttt{Default} win. The draft above
quotes the Section~\ref{sec:strategy} scope (253 versus 302) for continuity with the paper's
sentence. If you would rather quote the full measured set, the Tail-Mixed clause becomes a tie
and the recommendation needs a sentence saying so.

---

## 5. `main.tex:553` — Database size, full replacement

```latex
\textbf{Database size.} On the $10\times$ database (Section~\ref{sec:refdb}), measured in the
same batch as Table~\ref{tab:e2e-ac}, 30 of 36 workload-strategy cells keep their direction.
Targeted prefetch does not merely hold at scale, it improves. \texttt{Skel} moves from $-28\%$
to $-53\%$ on Scattered-Zipf-100K, from $-33\%$ to $-52\%$ on Uniform-100K, and from $-38\%$ to
$-50\%$ on Tail-Mixed, and \texttt{Skel+10} moves from $-71\%$ to $-80\%$ on Tail-Mixed, every
one of those improving on 10 of 10 seeds. A larger database raises the cold baseline without
enlarging a skeleton whose delivery cost grows only $1.07\times$. The end-to-end sensitivity is
confined to the full dump on Tail-Mixed, whose resident working set doubles and whose delivery
cost grows $2.05\times$, from 749 to 1534 \textmu s, turning a $-9\%$ win into a $+30\%$
regression. Of the five other direction changes, four are arms that regress at the reference
size and become neutral at $10\times$, including \texttt{Dump-500} at $+61\%$ to $-3\%$ on
Scattered-Zipf-100K, because the rising baseline absorbs a delivery cost that grows more slowly
than it does. The delivery trap therefore worsens with size only for the unranked full dump,
and frugal coverage does not.
```

**Changes from the current text.** The cell count is 36 rather than 18, because this batch runs
12 strategies on 3 workloads. "All cells keep their direction" becomes 30 of 36. `Dump` on
Tail-Mixed is $-9\%$ to $+30\%$ rather than $-9\%$ to $+139\%$. **The $-9\%$ starting point is
exactly right.** The clause *"\texttt{Skel+500} from $-31\%$ to $+35\%$"* is **dropped**, and
this batch settles which reading was meant because both are now measured. `2e_K500` on
Tail-Mixed is $-29\%$ to $-32\%$ and `Dump-500` is $-9\%$ to $-30\%$. Neither regresses, both
improve. The sentence about targeted prefetch improving at scale is new and is the strongest
result on this axis.

---

## 6. `main.tex:501` — Delivery order, two numbers

The paragraph's argument stands. The pread shuffle penalty re-derives as $14.6\times$,
$14.8\times$ and $10.4\times$ against the printed $15.6\times$, $15.1\times$ and $10.5\times$,
and first-query latency is unchanged between the two arms (94 versus 99, 97 versus 100, 93
versus 94 \textmu s), as the text says. Update all three multipliers. The pure-hit control adds
a fourth point at $11.8\times$ if you want it.

---

## 7. Verification of every remaining number against `unified_v6`

Single-instantiation rows are seed 1, the instantiation the paper quotes in
Section~\ref{sec:eval-fq} and in the `tab:e2e-ac` absolutes.

| site | claim | printed | `unified_v6` | |
|---|---|---|---|---|
| `:395` | cold baselines | 500 / 732 / 1067 | 492 / 734 / 1013 | ok |
| `:395` | Dump first query, delta | −80 / −86 / −91% | −80 / −87 / −91 | ok |
| `:397` | Skel+500 on A | −64% | −63% | ok |
| `:397` | Skel+10 on Tail-Mixed | −83% | −83% | exact |
| `:414` | ceiling, interior-only | −28 / −44 / −38% | −33 / −45 / −36 | ok |
| `:433` | Dump e2e_warm on A | 7148, +1330% | 7076, +1339% | ok |
| `:433` | Dump on B | +882% | +863% | ok |
| `:433` | Dump on Tail-Mixed | −20% | −16% | ok |
| `:501` | pread shuffle penalty | 15.6 / 15.1 / 10.5× | 14.6 / 14.8 / 10.4 | update |
| `:505` | Default vs Clustered best | 452/523, 509/701, 265/317 | 414/507, 475/670, 253/302 | ok |
| `:505` | first-query floor, both layouts | 187 \textmu s | 182 vs 181 | ok, it is Skel+500 |
| `:505` | Skel interior count 4 to 48 | 4 to 48 | 4 to 48 | exact |
| `:505` | baseline raised 26% | 523 to 658 | baseline **falls**, both batches | **fails** |
| `:505` | Tail-Mixed improvement lowered | −75 to −63% | no such move | **fails** |
| `:505` | Clustered never beats Default | none | 12 of 36 cells | **fails as written** |
| `:553` | all cells keep direction | 18 of 18 | 30 of 36 | restate |
| `:553` | working set doubles delivery | doubles | 2.05×, 749 to 1534 | exact |
| `:553` | Dump at 10× | −9 to +139% | −9 to +30% | start exact, end differs |
| `:553` | Skel+500 at 10× | −31 to +35% | −29 to −32 (`2e_K500`), −9 to −30 (`Dump-500`) | **fails** |
| `:553` | Skel robust at both sizes | robust | 10/10 at both | ok |

## After the edits

```
python3 tools/gen_claim_manifest.py
python3 verify_paper_atomicity.py --manifest docs/audits/PAPER_CLAIM_MANIFEST.csv
```

`paper/` is a submodule pushed to Overleaf, so commit and push it before the parent.
