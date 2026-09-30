# Lambda batch coldprobe-b2: warm container, cold data (2026-09-29/30)

The advisor's second suggestion on AWS Lambda: a function that carries the
reference database measures, at fixed idle intervals, how much of it is still in
the page cache. **This is the citable batch.** It supersedes the pilot in
`../pilot/`, which could not see data read once and then left alone.

**Finding: warm container, cold data does occur on Lambda, but it is set by
memory capacity, not by idle time.** At 128 MB about 30% of the database is not
cached inside a live, reused environment. It is lost while the database is
first read, not during idle, and stays at that level for the environment's
life. From 256 MB up the whole database stays cached. Idle time alone never
cooled data in a live environment, and an environment idle for 10 minutes or
more was always gone.

## Setup

- Code `deployment/lambda/` at `ec2893d`. The package's `MANIFEST.txt` records
  that commit and the SHA-256 of `test.db` (`2504a6b1...`), the reference
  database every local batch uses.
- Region `ap-southeast-2`, Python 3.12, x86_64, Amazon Linux 2 kernel 5.10.
- 36 functions, one per cell, each on its own fixed-rate schedule, Lambda-side
  and scheduler-side retries both off:
  - `reread` at memory 128, 256, 512, 1024 MB by idle 1, 5, 10, 15, 30, 60 min
  - `once` at the same memory sizes by idle 1, 5, 10 min
- Window 2026-09-29T12:36Z to 2026-09-30T02:22Z, 13.8 h, one deploy at one
  code version. 8,930 records after dropping 29 smoke-test rows, those written
  before the full deploy gave the two smoke-test cells a fresh environment.

## Method

Lambda allows no way to read page-cache residency without touching the data:
seccomp blocks `mincore`, the 5.10 kernel predates `cachestat`, and `/var/task`
is squashfs, which rejects `RWF_NOWAIT`. Residency is therefore timed reads,
with a read under 100 us counted as a hit.

- **`reread`** times the same 100 pages, 1.03 MB apart, at every invocation, so
  it measures data the function keeps using.
- **`once`** times 4 pages per invocation, each in a 1 MB region no probe in
  that environment has touched. squashfs blocks are at most 1 MB and aligned to
  the start of the file, so no read can warm another region, and each region is
  measured at most once. It measures data read once, by the cold-start warming
  read, and then left alone. Its 102 regions last about 24 invocations, so at
  1-minute idle it covers an environment's first 25 minutes and at 5 minutes
  about 2 hours.

### The 100 us threshold, validated at every memory size

A known miss is a cold start's first probe, when nothing is cached. A known hit
is a `reread` sample read 60 s earlier.

| memory | known miss, median | known miss, 5th pct |
|---|---|---|
| 128 MB | **18,986 us** | 844 us |
| 256 MB | 878 us | 749 us |
| 512 MB | 827 us | 740 us |
| 1024 MB | 812 us | 700 us |

Known hits at 128 MB exceed 100 us in 0.18% of 81,900 reads. At 128 MB a miss
is 20 times slower than elsewhere because decompressing a squashfs block is
CPU-bound and Lambda allocates CPU in proportion to memory. So the long reads
seen at 128 MB are real misses, not stalls on cached pages, and the threshold
classifies both cases correctly.

## Results

### Idle time decides whether the environment survives

Share of `reread` invocations that were cold starts:

| memory | 1 min | 5 min | 10 min | 15 min | 30 min | 60 min |
|---|---|---|---|---|---|---|
| 128 | 1% | 4% | **100%** | 100% | 100% | 100% |
| 256 | 1% | 5% | **100%** | 100% | 100% | 100% |
| 512 | 1% | 5% | **100%** | 100% | 100% | 100% |
| 1024 | 1% | 7% | **100%** | 100% | 100% | 100% |

AWS reclaims an idle environment between 5 and 10 minutes, narrowing the
pilot's 5 to 15. At 1 and 5 minutes environments lived a median of about
2 hours and at most 146 minutes at every memory size, and each replacement
followed an ordinary 60 s or 300 s gap: a lifetime cap, not a reaction to
idleness. In reused environments `reread` found 99.89% of its data resident
across 3,887 invocations.

### Memory decides how much of the database stays cached

`once` residency of data read once and then left alone:

| memory | right after the warming read | live, idle 1 min | live, idle 5 min |
|---|---|---|---|
| **128 MB** | **69.9%** | **70.1%** (n=746) | **66.8%** (n=554) |
| 256 MB | 100.0% | 99.8% | 100.0% |
| 512 MB | 100.0% | 99.9% | 99.8% |
| 1024 MB | 100.0% | 100.0% | 100.0% |

At 128 MB the loss is already there immediately after the warming read, so it
happens while the database is first read, not during idle. It does not drain
further as the environment ages:

| 128 MB, idle | invocations 2 to 5 | 6 to 12 | 13 to 25 |
|---|---|---|---|
| 1 min (age about 4, 9, 19 min) | 68.0% | 75.4% | 67.8% |
| 5 min (age about 15, 41, 90 min) | 74.0% | 67.3% | 64.1% |

Differences are within sampling error (n of 96 to 394 per bin).

The guest sees more memory than configured (`MemTotal` 191, 326, 658 and
1,191 MB) and the page cache in use at 128 MB is about 132 MB against about
182 MB elsewhere, 50 MB less, of which about 31 MB is database. The rest is
other cached files.

### Correction to the pilot

The pilot inferred from page-cache size alone that about half the database did
not fit at 128 MB. The direct measurement is about 30%. The page cache is
indeed about 50 MB smaller, but only about 31 MB of that is database.

The pilot also attributed its slow warm reads at 128 MB, over 1.5 ms, to CPU
stalls on cached pages. This batch shows a real miss at 128 MB typically takes
19 ms, so some of those were likely genuine misses. They were 0.1% of reads
either way, so the pilot's conclusion that re-read data stays cached is
unchanged.

### Cold-start cost

Reading the 103 MB database at a cold start takes a median 8.84, 4.38, 2.14 and
1.05 s from 128 to 1024 MB, halving as memory doubles, the same CPU scaling
that makes a single miss 20 times dearer at 128 MB.

## What this means for the paper

The warm-container, cold-data state the paper targets does arise on a
commercial FaaS platform, from a cause the paper's motivation does not name:
a database too large to cache beside the runtime at the function's memory
size. On Lambda it is fixed when the data is first read and persists for the
environment's life, so every request in that environment meets the same
partly cold database. Idle time on its own does not produce it, because an
environment idle long enough to lose data is reclaimed instead.

Small memory settings also raise the price of every miss, to about 19 ms at
128 MB, which strengthens the case for delivering only the pages a request
needs.

## Not tested

- A database much larger than the guest's spare memory at larger sizes, which
  would need `/tmp` or EFS, since the package limit is 250 MB.
- Other regions, ARM, and container-image packaging, whose filesystem differs.
- Query latency, and interior pages separated from leaves.

## Files

- `residency_20260930T021827Z.csv` — all 8,959 records as collected, including
  the 29 smoke-test rows. `lat_us` holds each invocation's raw latencies and
  `regions` the 1 MB regions a `once` probe read.
