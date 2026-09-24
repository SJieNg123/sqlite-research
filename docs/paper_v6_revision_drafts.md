# Paragraph drafts for the `unified_v6` revision

Source: `results/unified_v6/`, code `f570d4c`. **Every number here comes from that one batch.**
39,390 rows, 10 seeds, zero failures, `cold_pct` max 0.000, one continuous window
2026-09-23T01:54:17Z to 05:11:34Z.

**Estimator, and a correction to the previous version of this file.** The paper's cross-seed
tables state their estimator explicitly: `tab:ablation`, `tab:competitive` and `tab:seeds` all
say "10-seed means with 95% bootstrap CIs", and `tools/stats_uncertainty.py:80` computes
`ci_lo`/`ci_hi` as a percentile bootstrap CI **of the mean**. The first version of this file
quoted `median_pct` and paired it with that CI, so its point estimates and intervals described
different statistics. Everything below now uses **`mean_pct` with its own CI**, which is what
the paper prints. Thirty-one of the forty-eight cells in section 3 moved by five points or
more as a result, and several claims of the form "the paper's number moved" turned out to be
that error rather than a real change. See section 8.

Single-instantiation figures are seed 1, which is what the paper's Section 5 absolutes and the
layout paragraph quote. **"Ours" means the Skel family only** (`Skel-N`, `Skel`, `Skel+K`).
`Dump`, `Dump-N`, `learned-Markov` and `LP-*` are ported baselines.

`unified_v6` supersedes `unified_v5`, reproducing it on all 376 shared cells with a median move
of 1.8 points. Claims described as confirmed across two batches are ones v5 and v6 agree on.

Seven revision sites plus a verification table.

---

## 1. `main.tex:222` — replace the final sentence

**Current**

> Mechanisms between the two, such as issuing hints earlier in the function lifecycle,
> \texttt{readahead(2)}, or \texttt{io\_uring}, can move delivery toward the bound and are
> outside our scope.

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

The current text says the window "caps a single range hint at roughly 64 pages" and that "the
prefetch set is already fully resident at zero sleep". The first is imprecise, the second is
false for the window-chunked mode.

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
finishes, whereas window-chunked delivery reads 84 percent after only 1.9 ms of issuing. The
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

**Note.** The 5, 20 and 50 ms grace experiment lives in `results/unified_v5/grace_check/`, run
under the same code but not repeated inside the v6 window. It is the only number in this
document not from the v6 batch, and it is a mechanism check rather than a reported result.

---

## 3. `main.tex:499` — Competitive baselines, plus one new paragraph

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
monotonically with dump footprint. The full dump regresses by $+770\%$ on Scattered-Zipf-100K
and $+724\%$ on Uniform-100K, so the problem is delivery volume rather than the dump mechanism.
At matched footprint a small ranked dump ties \texttt{Skel+10} on every workload
(Scattered-Zipf-100K $-31\%$ versus $-38\%$, Uniform-100K $-26\%$ versus $-25\%$, Tail-Mixed
$-57\%$ versus $-57\%$, all with overlapping CIs). Explicit page typing and frequency ranking
recover a similar page set, so page-type knowledge earns its place as an interpretable coverage
guarantee rather than as a faster selector.
```

### 3b. New paragraph, insert directly after

**This is where the estimator correction changes a conclusion.** Under the mean, window-chunked
`Dump` beats our best on **both** tail workloads, not just the pure-hit control.

```latex
\textbf{Delivery mechanism.} Selection and delivery are separate axes, and the fair test
charges every arm the stronger mechanism. Window-chunked delivery cuts the full dump's delivery
term from 7.0 ms to 1.9 ms on the two 100K-key workloads, from 0.76 ms to 0.22 ms on Tail-Mixed
and from 1.40 ms to 0.42 ms on the pure-hit control, moving it from $+770\%$ to $+150\%$ on
Scattered-Zipf-100K, from $+724\%$ to $+137\%$ on Uniform-100K, from $-9\%$ to $-66\%$ on
Tail-Mixed, and from $+72\%$ to $-41\%$ on the pure-hit control. The same mechanism moves
\texttt{Skel+10} only from 98 to 33 \textmu s, because its ranges already sit at or below the
window. That asymmetry is the finding. A mechanism that makes delivery cheap helps whoever was
delivering the most, so it rewrites the baseline far more than it rewrites our own arms. The
consequence is a split verdict. On the two broad workloads targeted selection still wins by a
wide margin under the same mechanism, $-45\%$ and $-33\%$ against $+150\%$ and $+137\%$, because
a 17.7 MB transfer still costs 1.9 ms for pages no query touches. On the two tail workloads,
whose working sets are small enough that the transfer is cheap once chunked, the full dump
overtakes us, $-66\%$ against our $-62\%$ on Tail-Mixed and $-41\%$ against our $-35\%$ on the
pure-hit control. We therefore report window-chunked delivery as the deployable default, and we
state the scope of the targeted-prefetch claim as workloads whose working set is large relative
to what a cold start can afford to transfer.
```

### 3c. Do not add a new bimodality paragraph

The previous version of this file drafted one. It is unnecessary: `main.tex:497` **already
describes the Tail-Mixed bimodality** and gets it right. That paragraph needs a number refresh
only, which is site 7 below.

### Canonical numbers for `tab:competitive`

`mean_pct [95% CI of the mean]`, n=10, R=robust, d=directional, t=tie.

| strategy | mode | Scattered-Zipf | Uniform | Tail-Mixed | pure-hit |
|---|---|---|---|---|---|
| Skel | per-page | −27 [−31,−23] R | −26 [−33,−16] R | −37 [−40,−34] R | −28 [−34,−19] R |
| Skel+10 | per-page | −38 [−52,−25] R | −25 [−31,−15] R | −57 [−68,−46] R | −29 [−36,−20] R |
| Dump-14 | per-page | −31 [−42,−22] R | −26 [−33,−15] R | −57 [−68,−46] R | −30 [−37,−22] R |
| Dump-28 | per-page | −37 [−52,−24] R | −25 [−31,−17] R | −59 [−70,−49] R | −29 [−37,−18] R |
| Dump-500 | per-page | +81 [+36,+149] R | +41 [+24,+57] R | −10 [−14,−6] R | +14 [−1,+29] t |
| Dump | per-page | +770 [+681,+907] R | +724 [+649,+826] R | −9 [−13,−5] R | +72 [+49,+102] R |
| Skel | window | −34 [−37,−30] R | −33 [−39,−22] R | −43 [−47,−40] R | −35 [−41,−28] R |
| Skel+10 | window | −45 [−59,−32] R | −32 [−38,−24] R | −62 [−75,−49] R | −34 [−40,−26] R |
| Dump-14 | window | −39 [−49,−31] R | −33 [−39,−25] R | −62 [−75,−50] R | −34 [−40,−26] R |
| Dump-28 | window | −45 [−59,−32] R | −33 [−38,−26] R | −67 [−77,−56] R | −43 [−50,−34] R |
| Dump-500 | window | +29 [+11,+47] R | +22 [+6,+36] R | −66 [−68,−65] R | −24 [−36,−12] R |
| Dump | window | +150 [+125,+189] R | +137 [+115,+168] R | −66 [−68,−65] R | −41 [−49,−31] R |

---

## 4. `main.tex:505` — Physical layout, full replacement

All four layouts now share one batch with Table~\ref{tab:e2e-ac}, so the non-comparability
clause has no premise. Absolutes below are seed 1, as the paragraph already quotes.

```latex
\textbf{Physical layout.} Measured in the same batch as Table~\ref{tab:e2e-ac}, the best
warm-process end-to-end latency for \texttt{Default} versus \texttt{Clustered} is 414 versus
507 \textmu s on Scattered-Zipf-100K, 475 versus 670 \textmu s on Uniform-100K, and 253 versus
302 \textmu s on Tail-Mixed. The layout interacts with the selection strategy rather than with
prefetch as a whole. For the strategies we recommend, \texttt{Clustered} is worse and the effect
is consistent across instantiations. \texttt{Skel+10} is $1.07\times$ slower under
\texttt{Clustered} on Scattered-Zipf-100K on all 10 seeds and $1.12\times$ slower on Tail-Mixed
on 8 of 10. For pure interior selection the sign reverses. \texttt{Skel-92} on Tail-Mixed is
$0.88\times$ under \texttt{Clustered} on all 10 seeds, because clustering raises the interior
page count the skeleton captures from 4 pages to 48. The synchronous first-query floor is
unchanged by layout at 183 versus 181 \textmu s, so the layout changes which pages a strategy
finds rather than how fast they can be delivered. We therefore recommend \texttt{Default} for
the strategies of Section~\ref{sec:strategy}, and note \texttt{Clustered} as the better pairing
in the one case where only structural selection is available and the workload is tail-heavy.
The \texttt{.dbi} side file of Section~\ref{sec:serverless-coldstart} reaches the same
conclusion by copying navigation pages instead of reordering them.
```

**Two claims dropped.**

1. *"the difference comes entirely from a baseline raised by $26\%$ (523 to 658 \textmu s)."*
   There is no systematic rise. The \texttt{Clustered} baseline is higher than \texttt{Default}
   on 5 of 10 seeds on Scattered-Zipf-100K, 5 of 10 on Uniform-100K and 2 of 10 on Tail-Mixed,
   which is a coin flip on two workloads and a fall on the third. Cross-seed means are 844, 884
   and 935 \textmu s on \texttt{Default} against 873, 852 and 873 on \texttt{Clustered}. The
   original $+26\%$ came from seed 1 alone. `vacuum` is the layout that does raise the baseline,
   to 962, 1039 and 1089 \textmu s.
2. *"On Tail-Mixed, \texttt{Clustered} ... lowers the improvement from $-75\%$ to $-63\%$."* The
   interior-count half is exact, 4 pages to 48, verified from the frozen hotsets in both
   batches. The consequence is backwards: no strategy reproduces that move.

**Also flagged.** *"In no cell does \texttt{Clustered} beat \texttt{Default}"* is false as
written. Paired per seed over the 12-strategy set, \texttt{Clustered} wins on 12 of 36 cells,
most clearly Tail-Mixed \texttt{Skel-92} at $0.88\times$ on 10 of 10.

---

## 5. `main.tex:553` — Database size, full replacement

```latex
\textbf{Database size.} On the $10\times$ database (Section~\ref{sec:refdb}), measured in the
same batch as Table~\ref{tab:e2e-ac}, 28 of 36 workload-strategy cells keep their direction.
Targeted prefetch does not merely hold at scale, it improves. \texttt{Skel} moves from $-27\%$
to $-52\%$ on Scattered-Zipf-100K, from $-26\%$ to $-52\%$ on Uniform-100K, and from $-37\%$ to
$-50\%$ on Tail-Mixed, and \texttt{Skel+10} moves from $-57\%$ to $-80\%$ on Tail-Mixed. A
larger database raises the cold baseline without enlarging a skeleton whose delivery cost grows
only $1.07\times$. Of the eight direction changes, five are large-footprint arms that regress at
the reference size and become neutral at $10\times$, including \texttt{Skel+500} at $+81\%$ to
$-3\%$ on Scattered-Zipf-100K, because the rising baseline absorbs a delivery cost that grows
more slowly than it does. The one substantive degradation is the full dump on Tail-Mixed, whose
resident working set doubles and whose delivery cost grows $2.05\times$, from 749 to 1534
\textmu s, turning a $-9\%$ win into a $+29\%$ regression. \texttt{Skel-92} on Tail-Mixed also
loses its win, from $-21\%$ to parity. The delivery trap therefore worsens with size for the
unranked full dump, and frugal coverage does not.
```

**Changes.** Cell count is 36 rather than 18. "All cells keep their direction" becomes 28 of 36.
`Dump` on Tail-Mixed is $-9\%$ to $+29\%$ rather than $-9\%$ to $+139\%$, and **the $-9\%$
starting point is exactly right**. The clause *"\texttt{Skel+500} from $-31\%$ to $+35\%$"* is
**dropped**, and this batch settles which arm was meant because both are now measured at
$10\times$: `2e_K500` on Tail-Mixed is $-32\%$ to $-32\%$ and `Dump-500` is $-10\%$ to $-19\%$.
Neither regresses. The sentence about targeted prefetch improving at scale is new.

---

## 6. `main.tex:501` — Delivery order, three numbers

The argument stands. The pread shuffle penalty re-derives as $14.7\times$, $14.8\times$ and
$10.3\times$ against the printed $15.6\times$, $15.1\times$ and $10.5\times$, and first-query
latency is unchanged between the arms. Update all three. The pure-hit control adds a fourth
point at $11.8\times$ if you want it.

---

## 7. `main.tex:497` — Why the Tail-Mixed result is narrow, numbers only

This paragraph is **correct as written**, including its bimodality account, which v6 reproduces
closely. Only the four figures move, each by about two points, and the structure and conclusion
stay. Replace:

- Tail-Mixed \texttt{Skel+10} bimodal regimes: $-71\%$ and $-32\%$ for a mean of $-55\%$
  becomes **$-72\%$ and $-35\%$ for a mean of $-57\%$** (6 seeds in the not-found regime, 4 in
  the hit regime).
- Tail-Hit \texttt{Skel+10} $-27\%$ becomes **$-29\%$**.
- Tail-Hit \texttt{Skel} $-28.5\%$ becomes **$-28\%$**.
- Tail-Hit footprint-matched frequency dump $-30.6\%$ becomes **$-30\%$**.

All four are robust with CIs excluding zero, and the three Tail-Hit arms still overlap, so
"once the not-found concentration is removed, leaf frequency adds nothing beyond the skeleton"
holds unchanged.

---

## 8. Verification, and what the estimator fix undid

Single-instantiation rows are seed 1.

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
| `:497` | Tail-Mixed / Tail-Hit set | −55 / −27 / −28.5 / −30.6 | −57 / −29 / −28 / −30 | ok, site 7 |
| `:499` | Dump on A, cross-seed | +767% | **+770%** | ok |
| `:499` | Dump on B, cross-seed | +722% | **+724%** | ok |
| `:501` | pread shuffle penalty | 15.6 / 15.1 / 10.5× | 14.7 / 14.8 / 10.3 | update |
| `:505` | Default vs Clustered best | 452/523, 509/701, 265/317 | 414/507, 475/670, 253/302 | ok |
| `:505` | first-query floor, both layouts | 187 \textmu s | 183 vs 181 | ok, it is Skel+500 |
| `:505` | Skel interior count 4 to 48 | 4 to 48 | 4 to 48 | exact |
| `:505` | baseline raised 26% | 523 to 658 | no systematic rise | **fails** |
| `:505` | Tail-Mixed improvement lowered | −75 to −63% | no such move | **fails** |
| `:505` | Clustered never beats Default | none | 12 of 36 cells | **fails as written** |
| `:553` | all cells keep direction | 18 of 18 | 28 of 36 | restate |
| `:553` | working set doubles delivery | doubles | 2.05×, 749 to 1534 | exact |
| `:553` | Dump at 10× | −9 to +139% | −9 to +29% | start exact, end differs |
| `:553` | Skel+500 at 10× | −31 to +35% | −32 to −32, or −10 to −19 | **fails** |

**Undone by the estimator fix.** The previous version of this file reported these as moves. They
are not. `tab:competitive` `Dump` on Scattered-Zipf-100K and Uniform-100K reproduce to within
three points, and `main.tex:497` reproduces to within two. The genuine failures are the three
layout claims at `:505` and the `Skel+500` clause at `:553`, all of which fail under either
estimator and all of which v5 and v6 agree on.

## After the edits

```
python3 tools/gen_claim_manifest.py
python3 verify_paper_atomicity.py --manifest docs/audits/PAPER_CLAIM_MANIFEST.csv
```

`paper/` is a submodule pushed to Overleaf, so commit and push it before the parent.
