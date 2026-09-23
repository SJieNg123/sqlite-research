# Paragraph drafts for the `unified_v5` revision

Source: `results/unified_v5/`, commit `a475133`, code `fea7c51`. **Every number in this
document comes from that one batch and no other.** Cross-seed figures are n=10 under the
canonical estimator `tools/stats_uncertainty.py` (`median_pct` with bootstrap 95% CI).
Single-instantiation figures are seed 1 and are labelled as such, because that is the
instantiation the paper's Section~5 absolutes already quote.

Six revision sites plus a verification table. Sections 1, 2, 5 and 6 are self-contained
replacements. Section 3 needs a decision on table layout. Section 4 drops two claims that do
not survive the cross-seed check, so read its notes before using it. Section 7 is the audit of
every number I did not rewrite.

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
second is now false for the window-chunked mode, so both halves need work.

**Replacement**

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
issuing, which makes it incomparable across modes. The per-page mode reads $100\%$ partly
because its 4,400 separate calls occupy 6.8 ms, during which its own readahead finishes,
whereas window-chunked delivery reads 68 to 88 percent after only 2.0 ms of issuing. Grace
periods of 5, 20 and 50 ms between hint dispatch and the first query resolve the question.
Window-chunked delivery reaches $100\%$ residency at 5 ms and gains nothing beyond it, and
first-query latency is flat at about 100 \textmu s at every grace value under both modes, so
the pages still in flight at the zero-grace sample land during query setup and cost nothing.
Comparisons between the two modes therefore use first-query and end-to-end latency, never the
residency ratio. The gap of Eq.~\ref{eq:delivery_loss} on the skewed workload is itself
unchanged across grace durations with identical major-fault counts, so it is a persistent
cost difference rather than a timing artifact.
```

---

## 3. `main.tex:499` — Competitive baselines, plus two new paragraphs

**This is the substantive change and the one that needs your decision.** The advisor's
suggestion, in its strong form, makes `Dump` a much better baseline. Our claim survives on
the two broad workloads and does not survive on the pure-hit control.

### 3a. Replacement for the existing paragraph

Setup sentences unchanged, numbers refreshed to `unified_v5` under the per-page mode, and the
stale "pre-fix first-op leakage" aside dropped because that comparison is now a clean tie.

```latex
\textbf{Competitive baselines.} To test whether \texttt{Dump} is a weak baseline, we port the
selection cores of two prior systems (Section~\ref{sec:buffer-warming}) onto our substrate and
charge them the same way. \texttt{Dump} is the full-working-set core of InnoDB's buffer-pool
dump and load. \texttt{Dump-N} is a frequency-ranked partial dump in the spirit of Pre-Buffer.
It replays each query's root-to-leaf traversal, counts page visits, and dumps the top $N$ pages
for $N$ in {14, 28, 100, 500, full}. We reproduce only the selection, not the off-critical-path
orchestration of either system. Table~\ref{tab:competitive} reports warm-process end-to-end
results under both delivery modes. Under per-page delivery, end-to-end latency worsens
monotonically with dump footprint. The full dump regresses by $+720\%$ on Scattered-Zipf-100K
and $+652\%$ on Uniform-100K, so the problem is delivery volume rather than the dump mechanism.
At matched footprint a small ranked dump ties \texttt{Skel+10} on every workload
(Scattered-Zipf-100K $-27\%$ versus $-29\%$, Uniform-100K $-33\%$ versus $-29\%$, Tail-Mixed
$-67\%$ versus $-67\%$, all with overlapping CIs). Explicit page typing and frequency ranking
recover a similar page set, so page-type knowledge earns its place as an interpretable coverage
guarantee rather than as a faster selector.
```

### 3b. New paragraph, insert directly after

```latex
\textbf{Delivery mechanism.} Selection and delivery are separate axes, and the fair test
charges every arm the stronger mechanism. Window-chunked delivery cuts the full dump's
delivery term from 7.1 ms to 2.0 ms on the two 100K-key workloads and from 0.79 ms to 0.22 ms
on Tail-Mixed, moving it from $+720\%$ to $+147\%$ on Scattered-Zipf-100K, from $+652\%$ to
$+122\%$ on Uniform-100K, from $-4\%$ to $-66\%$ on Tail-Mixed, and from $+57\%$ to $-47\%$ on
the pure-hit control. The same mechanism moves \texttt{Skel+10} only from 101 to 36 \textmu s,
because its ranges already sit at or below the window. That asymmetry is the finding. A
mechanism that makes delivery cheap helps whoever was delivering the most, so it rewrites the
baseline far more than it rewrites our own arms. Holding the mechanism fixed at window-chunked
delivery, targeted selection still wins on the two broad workloads by about $4\times$ in
absolute latency ($-39\%$ versus $+147\%$ and $-38\%$ versus $+122\%$), because a 17.7 MB
transfer still costs 2 ms for pages no query touches. On Tail-Mixed our margin narrows from
$3.1\times$ to $1.6\times$. On the pure-hit control the full dump wins outright, $-47\%$
against $-44\%$ for the best targeted arm, which is the expected outcome where every query
hits and the question of \textit{which} pages to fetch carries least weight. We therefore
report window-chunked delivery as the deployable default and state the dump's place as
conditional on working-set size rather than settled against it.
```

### 3c. New paragraph on the tail-workload instability

Verified against per-seed `first_query_us`, so the causal claim holds.

```latex
\textbf{Selection stability on the tail workload.} The Tail-Mixed comparison rests on a median
that hides a split. Under window-chunked delivery \texttt{Skel+10} measures 194 to 197 \textmu s
on six seeds and 580 to 658 \textmu s on the other four, while the full dump measures 308 to
371 \textmu s on all ten. The split sits in first-query latency, not in delivery, and on the
four slow seeds \texttt{Skel+10} lands within 3 percent of interior-only \texttt{Skel}, so the
leaf budget is missing the leaf the queries need rather than failing to deliver it. This is the
key-range property of Section~\ref{sec:eval-fq} seen from the other side. Tail-Mixed's
advantage for small leaf budgets comes from not-found probes concentrating on one leaf, and on
four of ten instantiations they do not concentrate enough for a 10-page budget to catch them.
Raising the budget to 28 pages recovers one of the four. Our advantage on this workload is
therefore a better outcome on most instantiations rather than a smaller latency on each, and
the full dump is the more predictable arm.
```

**Decision needed.** `tab:competitive` currently has three workload columns and one delivery
mode. The v5 data supports four workloads by two modes. Options:

1. Keep the table at per-page delivery, add the window-chunked numbers as the new
   paragraph 3b only. Smallest change, keeps the table readable, buries the strongest
   baseline in prose.
2. Add a window-chunked block to the table, four workloads by six strategies. Most honest,
   roughly doubles the table.
3. Replace the table's delivery mode with window-chunked and report per-page in the text.
   Cleanest forward-looking framing, but breaks continuity with Tables 3 and 4.

Canonical numbers for whichever you pick are below.

| strategy | mode | Scattered-Zipf-100K | Uniform-100K | Tail-Mixed | pure-hit |
|---|---|---|---|---|---|
| Skel | per-page | −27 [−31,−22] | −32 [−33,−17] | −35 [−38,−34] | −31 [−33,−18] |
| Skel+10 | per-page | −29 [−52,−26] | −29 [−31,−15] | −67 [−66,−42] | −33 [−35,−19] |
| Dump-14 | per-page | −27 [−41,−23] | −33 [−33,−18] | −67 [−66,−45] | −34 [−36,−21] |
| Dump-28 | per-page | −27 [−51,−24] | −31 [−32,−18] | −66 [−67,−48] | −30 [−37,−18] |
| Dump-500 | per-page | +65 [+41,+130] | +47 [+28,+61] | −5 [−10,+1] tie | +31 [+3,+32] |
| Dump | per-page | +720 [+684,+904] | +652 [+643,+830] | −4 [−10,+1] dir. | +57 [+53,+104] |
| Skel | window | −35 [−38,−32] | −40 [−41,−26] | −42 [−46,−40] | −39 [−41,−28] |
| Skel+10 | window | −39 [−60,−35] | −38 [−40,−24] | −77 [−74,−49] | −39 [−40,−25] |
| Dump-14 | window | −35 [−49,−31] | −41 [−41,−27] | −77 [−74,−50] | −39 [−40,−24] |
| Dump-28 | window | −38 [−59,−34] | −38 [−39,−26] | −76 [−76,−56] | −44 [−51,−34] |
| Dump-500 | window | +33 [+12,+48] | +28 [+9,+38] | −66 [−67,−62] | −10 [−34,−11] |
| Dump | window | +147 [+130,+193] | +122 [+119,+172] | −66 [−67,−62] | −47 [−49,−31] |

Every cell is `robust` except the two marked on the per-page Tail-Mixed Dump rows.

---

## 4. `main.tex:505` — Physical layout, full replacement

`orig`, `vacuum`, `ta` and `1gb` are now in the same batch as Table~\ref{tab:e2e-ac}, so the
non-comparability clause has no premise. Re-deriving the rest of the paragraph from
`unified_v5` invalidates two of its claims, so this is a full replacement rather than a
number refresh. See the verification table in section 7.

```latex
\textbf{Physical layout.} Measured in the same batch as Table~\ref{tab:e2e-ac}, the best
warm-process end-to-end latency for \texttt{Default} versus \texttt{Clustered} is 442 versus
512 \textmu s on Scattered-Zipf-100K, 481 versus 671 \textmu s on Uniform-100K, and 256 versus
304 \textmu s on Tail-Mixed. The layout interacts with the selection strategy rather than with
prefetch as a whole. For the strategies we recommend, \texttt{Clustered} is worse and the
effect is consistent across instantiations. \texttt{Skel+10} is $1.08\times$ slower under
\texttt{Clustered} on Scattered-Zipf-100K on 10 of 10 seeds and $1.15\times$ slower on
Tail-Mixed on 8 of 10. For pure interior selection the sign reverses. \texttt{Skel-92} on
Tail-Mixed is $0.90\times$ under \texttt{Clustered} on 10 of 10 seeds, because clustering
raises the interior page count the skeleton captures from 4 pages to 48. The synchronous
first-query floor is unchanged by layout at 186 versus 183 \textmu s, so the layout changes
which pages a strategy finds rather than how fast they can be delivered. We therefore
recommend \texttt{Default} for the strategies of Section~\ref{sec:strategy}, and note
\texttt{Clustered} as the better pairing in the one case where only structural selection is
available and the workload is tail-heavy. The \texttt{.dbi} side file of
Section~\ref{sec:serverless-coldstart} reaches the same conclusion by copying navigation pages
instead of reordering them.
```

**Two claims dropped, both because they do not survive the cross-seed check.**

1. *"the difference comes entirely from a baseline raised by $26\%$ (523 to 658 \textmu s) as
   leaves move to higher offsets."* At seed 1 the Scattered-Zipf baseline does rise, 498 to 671
   \textmu s, which is $+35\%$. Across all ten seeds it **falls**, 879 to 788 \textmu s, and the
   Clustered baseline is higher on only 4 of 10 seeds. On Uniform-100K it is 956 to 806 and on
   Tail-Mixed 911 to 854, both lower. The original reading came from seed 1, which is also the
   instantiation whose Scattered-Zipf baseline is an outlier at 498 \textmu s against 828 to
   1024 on the other nine. `vacuum` is the layout that genuinely raises the baseline, to 1000,
   1044 and 1152 \textmu s.
2. *"On Tail-Mixed, \texttt{Clustered} ... lowers the improvement from $-75\%$ to $-63\%$."*
   The interior-count half of that sentence is exact, 4 pages to 48, verified from the frozen
   hotsets. The consequence is backwards. \texttt{Skel} first-query on Tail-Mixed is $-44\%$
   under Default and $-45\%$ under Clustered cross-seed, and $-39\%$ versus $-48\%$ at seed 1,
   so the larger interior set helps slightly. No strategy reproduces a $-75\%$ to $-63\%$ move.

**Also flagged.** The claim *"In no cell does \texttt{Clustered} beat \texttt{Default}"* is
false as written. Paired per seed, Clustered wins on 6 of 24 cells, most clearly
Tail-Mixed \texttt{Skel-92} at $0.90\times$ on 10 of 10 seeds. It survives if you scope it to
access-pattern strategies, where the only counterexample is Scattered-Zipf \texttt{Skel+500}
at $0.96\times$ on 7 of 10, which is marginal. The draft above restates the claim by strategy
class instead of asserting it universally.

---

## 5. `main.tex:553` — Database size, full replacement

```latex
\textbf{Database size.} On the $10\times$ database (Section~\ref{sec:refdb}), measured in the
same batch as Table~\ref{tab:e2e-ac}, 22 of 24 workload-strategy cells keep their direction.
Targeted prefetch does not merely hold at scale, it improves. \texttt{Skel} moves from $-27\%$
to $-52\%$ on Scattered-Zipf-100K, from $-32\%$ to $-51\%$ on Uniform-100K, and from $-35\%$ to
$-50\%$ on Tail-Mixed, and \texttt{Skel+10} moves from $-67\%$ to $-80\%$ on Tail-Mixed, every
one of those improving on 10 of 10 seeds. A larger database raises the cold baseline without
enlarging a skeleton whose delivery cost grows only $1.08\times$. The end-to-end sensitivity is
confined to dump-style strategies on Tail-Mixed, whose resident working set doubles and whose
delivery cost grows $2.07\times$, from 785 to 1622 \textmu s. \texttt{Dump} is the one
substantive direction change, from $-4\%$ to $+32\%$. The other is \texttt{Skel-5}, which sits
within a few percent of zero at both sizes and is robust at neither. The delivery trap
therefore worsens with size and frugal coverage does not.
```

**Changes from the current text.** The cell count is 24 rather than 18, because this batch runs
8 strategies on 3 workloads including the two ablation controls. "All cells keep their
direction" becomes 22 of 24. `Dump` on Tail-Mixed is $-4\%$ to $+32\%$ rather than $-9\%$ to
$+139\%$, same direction and a smaller magnitude. The clause *"\texttt{Skel+500} from $-31\%$
to $+35\%$"* is **dropped**, because `2e_K500` on Tail-Mixed measures $-28\%$ at both sizes
with no regression at all. The sentence about targeted prefetch improving at scale is new and
is the strongest result on this axis.

**One coverage gap.** `2f_topN` (the `Dump-N` family) was not run outside `orig`, so if the
paper's "Skel+500" in this sentence actually meant `Dump-500`, that cell cannot be checked in
this batch and would need a separate run.

---

## 6. `main.tex:501` — Delivery order, two numbers

The paragraph's argument stands. The pread shuffle penalty re-derives as $15.6\times$,
$15.2\times$ and $10.2\times$ against the printed $15.6\times$, $15.1\times$ and $10.5\times$,
and first-query latency is unchanged between the two arms (97 versus 103, 98 versus 102, 95
versus 96 \textmu s), as the text says. Change `$15.1\times$` to `$15.2\times$` and
`$10.5\times$` to `$10.2\times$`. The pure-hit control adds a fourth point at $11.5\times$ if
you want it.

---

## 7. Verification of every remaining number against `unified_v5`

Single-instantiation rows are seed 1, which is the instantiation the paper quotes in
Sections~\ref{sec:eval-fq} and the `tab:e2e-ac` absolutes.

| site | claim | printed | `unified_v5` | |
|---|---|---|---|---|
| `:395` | cold baselines | 500 / 732 / 1067 | 498 / 743 / 1070 | ok |
| `:395` | Dump first query, absolute | 99 / 100 / 94 \textmu s | 98 / 97 / 94 | ok |
| `:395` | Dump first query, delta | $-80$ / $-86$ / $-91\%$ | $-80$ / $-87$ / $-91$ | ok |
| `:397` | interior skeleton on A | $-27$ to $-28\%$ | Skel $-28$, Skel-92 $-23$ | ok |
| `:397` | Skel+500 on A | $-64\%$ | $-64\%$ | exact |
| `:397` | Uniform interior cap / Dump | $-44\%$ / $-86\%$ | $-45\%$ / $-87\%$ | ok |
| `:397` | Skel+10 on Tail-Mixed | $-83\%$ | $-83\%$ | exact |
| `:414` | ceiling table | $-28$ / $-44$ / $-38\%$ | $-28$ / $-45$ / $-39$ | ok |
| `:433` | Dump e2e_warm on A | 7148, $+1330\%$ | 7145, $+1335\%$ | ok |
| `:433` | Dump on B | $+882\%$ | $+873\%$ | ok |
| `:433` | Dump on Tail-Mixed | $-20\%$ | $-19\%$ | ok |
| `:501` | pread shuffle penalty | 15.6 / 15.1 / 10.5$\times$ | 15.6 / 15.2 / 10.2 | minor edit |
| `:505` | Default vs Clustered best | 452/523, 509/701, 265/317 | 442/512, 481/671, 256/304 | ok |
| `:505` | first-query floor, both layouts | 187 \textmu s | 186 vs 183 | ok, it is Skel+500 |
| `:505` | Skel interior count 4 to 48 | 4 to 48 | 4 to 48 | exact |
| `:505` | Skel-92 first query, A | $-32$ vs $-30\%$ | seed1 $-23$ vs $-33$, x-seed $-36$ vs $-31$ | **sign reverses** |
| `:505` | baseline raised $26\%$ | 523 to 658 | seed1 $+35\%$, x-seed $-10\%$ | **fails** |
| `:505` | Tail-Mixed improvement lowered | $-75$ to $-63\%$ | $-44$ vs $-45\%$ | **fails** |
| `:505` | Clustered never beats Default | none | 6 of 24 cells | **fails as written** |
| `:553` | all cells keep direction | 18 of 18 | 22 of 24 | restate |
| `:553` | working set doubles delivery | doubles | $2.07\times$, 785 to 1622 | exact |
| `:553` | Dump at $10\times$ | $-9$ to $+139\%$ | $-4$ to $+32\%$ | direction ok |
| `:553` | Skel+500 at $10\times$ | $-31$ to $+35\%$ | $-28$ to $-28\%$ | **fails** |
| `:553` | Skel robust at both sizes | robust | 10/10 at both | ok |

Everything above is `results/unified_v5`, commit `a475133`, code `fea7c51`. No number in this
document comes from any other batch.

## After the edits

```
python3 tools/gen_claim_manifest.py
python3 verify_paper_atomicity.py --manifest docs/audits/PAPER_CLAIM_MANIFEST.csv
```

`paper/` is a submodule pushed to Overleaf, so commit and push it before the parent.
