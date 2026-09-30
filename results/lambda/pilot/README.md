# Lambda pilot: warm container, cold data (2026-09-26/27)

**Pilot, not a result batch. Do not cite these numbers.** It established the
method and found its blind spot: the `reread` probe keeps its own samples hot,
so it cannot see data read once and then left alone, which is what matters at
128 MB. The citable run is batch `coldprobe-b2`, which repeats every cell here
alongside the new `once` probe in one window at one code version.

**Superseded figure:** this pilot's "about half the database does not fit at
128 MB" was inferred from page-cache size. Batch `coldprobe-b2` measured it
directly at about 30%. See `../b2/README.md`.

The advisor's second suggestion, run on AWS Lambda. A function carrying the
reference database measures, on every invocation, how much of the data it read
at its previous invocation is still in the page cache, at fixed idle intervals.

**Finding: idle time never made data cold inside a live environment.** Across
14 hours and 4,509 invocations, a surviving execution environment always found
its recently read data resident, and an environment idle for 15 minutes or
more was always gone. The one exception to "data goes cold only with the
environment" is capacity, not idleness: at 128 MB the page cache cannot hold
the whole database beside the runtime, and about half of it is likely out of
cache in a live environment, a case the residency probe cannot observe.

## Setup

- Code `deployment/lambda/` at `9ed1091`, package `MANIFEST.txt` records the
  commit and the SHA-256 of `test.db` (`2504a6b1...`), the reference database
  every local batch uses.
- Region `ap-southeast-2`, Python 3.12, x86_64, Amazon Linux 2 kernel 5.10.
- Matrix: memory 128, 256, 512, 1024 MB by idle 1, 5, 15, 30, 60 minutes, one
  function per cell so no cell keeps another warm. Lambda-side and
  scheduler-side retries both off.
- Window 2026-09-26T15:26Z to 2026-09-27T05:41Z. The 17 earlier rows are the
  single-cell smoke test and are excluded.
- Residency is timed reads of 100 pages spaced 1.03 MB apart, because Lambda
  forbids `mincore` (seccomp), lacks `cachestat` (kernel 5.10), and serves
  `/var/task` from squashfs, which rejects `RWF_NOWAIT`. A miss costs 756 us at
  the 5th percentile and 860 us at the median, a hit 2.6 us at the median and
  8.7 us at the 99th percentile, so the 100 us threshold sits far from both.

## Results

| memory | idle | invocations | cold starts | warm | warm `resident_pct` mean / min |
|---|---|---|---|---|---|
| 128 | 1 | 857 | 10 | 847 | 99.8 / 98 |
| 128 | 5 | 172 | 7 | 165 | 99.8 / 97 |
| 256 | 1 | 857 | 11 | 846 | 99.9 / 97 |
| 256 | 5 | 172 | 12 | 160 | 99.9 / 96 |
| 512 | 1 | 855 | 11 | 844 | 99.9 / 96 |
| 512 | 5 | 171 | 8 | 163 | 100.0 / 97 |
| 1024 | 1 | 856 | 10 | 846 | 99.9 / 97 |
| 1024 | 5 | 170 | 8 | 162 | 99.9 / 96 |
| all | 15, 30, 60 | 400 | **400** | 0 | n/a |

Every one of the 476 cold starts read **0.0%** resident before its warming
read, and 99.6 to 100% after it.

### The sub-100% warm readings are timing noise, not cache misses

Of 403,300 sampled reads in warm environments, 395 exceeded 100 us. Only 9 fall
in the 600 to 1,200 us band a real miss occupies, one per invocation at most, in
9 of 4,033 invocations. The rest are stalls of 1 to 39 ms concentrated at
128 MB (106 of the 110 over 1.2 ms), consistent with Lambda allocating CPU in
proportion to memory and throttling the smallest setting. Treated as misses they
would overstate eviction, so warm residency is effectively 100% in every cell.

### Environment lifetime, not idle eviction, is what makes data cold

- At idle 1 and 5 minutes, environments lived a median of about 2 hours and at
  most 147 minutes, then were replaced after an ordinary 60 s or 300 s gap. The
  replacement is a lifetime cap, not a reaction to idleness.
- At idle 15, 30 and 60 minutes, all 400 invocations were cold starts. AWS
  reclaims an idle environment somewhere between 5 and 15 minutes.

### Memory: no pressure at 256 MB and above, a capacity shortfall at 128 MB

The guest sees more memory than the function is configured with: `MemTotal` is
191, 326, 658 and 1,191 MB for 128, 256, 512 and 1,024 MB. The page cache
(`Cached`, median MB at the start of each invocation) shows what that means:

| memory | before the DB read | 2nd invocation | 10th | 20th and later |
|---|---|---|---|---|
| 128 | 87 | 138 | 131 | 130 |
| 256, 512, 1024 | 87 | 181 | 181 | 181 to 182 |

Every environment starts with 87 MB cached. At 256 MB and above, reading the
database takes the cache to 181 MB and it stays there for the environment's
whole life: nothing is evicted. At 128 MB the cache tops out near 138 MB and
settles at 130 MB, about 50 MB short, roughly half the database. The shortfall
appears at the warming read and does not grow with idle time, so it is capacity
eviction, not idle eviction.

**The residency probe cannot see this.** It re-reads its 100 sampled pages at
every invocation, so those pages stay hot, and the table above reports them at
100%. Pages read only by the warming read are the likeliest to go under
memory pressure, and they are exactly the ones the probe never re-reads. At
128 MB a live, warm environment therefore probably holds only part of the
database, a partial form of warm container, cold data driven by capacity rather
than idleness. Confirming it needs a probe that samples pages it has not
previously touched.

### No environment or invocation was killed

- Observed invocation counts match what each schedule fired, within the 1 to 3
  of schedule start-up, in every cell.
- No environment skipped an invocation number. The handler prints its record
  last, so an invocation killed partway would leave a gap. There are none
  across 477 environments.
- Environment lifetimes do not depend on memory: medians of 80 to 126 minutes
  and maxima of 140 to 147 minutes in every setting.

### CPU scales with memory, and it shows in the cold start

The warming read of the 103 MB database takes a median 8.66 s at 128 MB,
4.30 s at 256, 2.12 s at 512 and 1.04 s at 1,024: time halves as memory
doubles. `/var/task` is squashfs, so reading it is decompression, which is
CPU-bound, and Lambda allocates CPU in proportion to memory. The 1 to 39 ms
read stalls concentrated at 128 MB are the same throttling.

## What this means for the paper

On Lambda, idleness does not produce the state the paper's prefetch targets:
a cold page cache coincides with a cold start. Where the database does not fit
beside the runtime, as at 128 MB here, part of it may be cold inside a live
environment, which is the warm-container, cold-data state arising from capacity
rather than idleness. The current probe cannot measure that case. Prefetch therefore pays off
at environment initialization, which on this evidence happens at least every
2.5 hours under constant traffic and on every request after 15 minutes of
idleness.

## Not tested

- Residency of pages the probe has not itself re-read, the case that matters at
  128 MB. A probe that reads each sample only once per environment would show it.
- Idle between 5 and 15 minutes, where the reclaim threshold lies.
- A database larger than the guest's spare memory, the only way this setup
  could produce page-cache pressure. The 1 GB database exceeds Lambda's 250 MB
  package limit and would need `/tmp` or EFS.
- Other regions, ARM, and container-image packaging, which uses a different
  filesystem than squashfs.

## Files

- `residency_20260927T054002Z.csv` — all 4,526 records as collected, including
  the 17 smoke-test rows. `lat_us` holds each invocation's 100 raw latencies.
