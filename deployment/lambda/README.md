# Lambda probe: warm container, cold data

The advisor's second suggestion: a function that carries the reference database,
checks with `mincore` on every invocation how much of that database is still in
the page cache, and is invoked at different idle intervals. The question is
whether a **reused** execution environment can still find its data cold.

`build.sh` only packages. Nothing in this directory touches AWS until you run
`deploy.sh` yourself in CloudShell.

## What each invocation records

Lambda leaves no way to read page-cache residency without touching the data.
`diag.py` established this on the live runtime: seccomp blocks `mincore`
outright, the 5.10 kernel predates `cachestat`, and `/var/task` is squashfs,
which rejects `RWF_NOWAIT`. So residency is measured by **timing reads**, which
separate cleanly there: a miss costs about 650 to 970 us, a hit 3 to 6 us.

Two probe modes run as separate functions in the same batch, so they never
share an execution environment:

- **`reread`** times the same 100 pages, spread evenly about 1.03 MB apart, at
  every invocation. Probing re-reads any page it finds missing, so each
  invocation measures how much of the data read at the previous invocation
  survived one idle interval: data the function keeps using.
- **`once`** times 4 pages per invocation, each in a 1 MB region that no probe
  in this environment has touched before. squashfs blocks are at most 1 MB and
  aligned to the start of the file, so a read in one region cannot warm
  another. Every region is measured at most once per environment, in an order
  seeded by `env_id`, so the result is how much of the data read only by the
  cold-start warming read is still cached: data the function read once and left
  alone. The 102 regions last about 24 invocations, after which the record
  carries no sample rather than a reused one. The pilot showed `reread` cannot
  see this case, and that at 128 MB about half the database does not fit.

Every raw latency is kept (`lat_us`, and `regions` in `once` mode), so the
100 us threshold can be re-drawn afterwards.

An environment's first invocation also reads the whole database once, then
probes again (`resident_after_warm_pct`). In `once` mode that second probe is
the direct measure of how much of the database the page cache can hold at the
function's memory size.

Three states, told apart by `env_id`, which is generated once per execution
environment:

| state | `cold_start` | `resident_pct` | meaning |
|---|---|---|---|
| A | true | whatever deployment left | new environment, an ordinary cold start |
| B | false | near 100 | warm environment, warm data |
| **C** | **false** | **well below 100** | **warm environment, cold data: the phenomenon** |

Each record also carries `idle_s`, `env_age_s`, `mem_mb`, `log_stream` (AWS's own
per-environment id, a cross-check on `env_id`) and `MemTotal`, `MemAvailable`
and `Cached` from `/proc/meminfo`.

## Build (workstation)

```
deployment/lambda/build.sh
```

Writes `build/residency_probe.zip` (handler, `diag.py`, `residency.py` for
`diag.py`, `test.db` and a
`MANIFEST.txt` with the git commit and SHA-256 of each file) and copies
`deploy.sh` beside it. The zip is above the console's 50 MB direct-upload limit,
so it goes through CloudShell.

## Deploy (AWS CloudShell)

1. In the console, pick the region first, then open CloudShell from the top bar.
2. **Actions → Upload file**: `build/residency_probe.zip`, then `build/deploy.sh`.
3. If an earlier batch is still running, remove it first so it stops
   invoking. The pilot used the prefix `coldprobe`:
   ```
   chmod +x deploy.sh
   PREFIX=coldprobe ./deploy.sh teardown
   ```
4. Smoke-test one cell of each mode before the full matrix:
   ```
   MEMS=128 IDLES=1 ONCE_IDLES=1 ./deploy.sh deploy
   # wait about 3 minutes
   ./deploy.sh collect
   head -3 residency_*.csv
   ```
   Expect `cold_start` true on each function's first row, then false with
   `idle_s` near 60. `once` rows carry 4 samples and a `regions` list.
5. Full matrix, which also updates the two smoke-test cells:
   ```
   ./deploy.sh deploy
   ```

The schedules run on AWS, so closing CloudShell does not stop anything. The
batch starts when the full deploy finishes: rows written before then belong to
the smoke test and are dropped in analysis.

## Matrix and run length

Default: memory `128 256 512 1024` MB, with `reread` at idle `1 5 10 15 30 60`
minutes and `once` at idle `1 5 10`: 24 + 12 = 36 functions running in
parallel. `once` stops at 10 minutes because from 15 up every invocation is a
cold start, so there is no live environment to hold data in. Idle 10 sits in
the 5 to 15 minute gap where the pilot found environments being reclaimed.
Override with `MEMS`, `IDLES` and `ONCE_IDLES`.

All cells must run in **one batch**: one deploy, one code version, one window.
`PREFIX` names the batch (default `coldprobe-b2`) and every resource and log
group carries it, so `collect` can never mix two batches. The 60-minute cell
needs about 10 hours for 10 samples, so run about 14 hours.

## Collect and stop

```
./deploy.sh collect     # -> residency_<utc>.csv, then Actions -> Download file
./deploy.sh diag        # re-run the runtime capability probe on one function
./deploy.sh stop        # delete the schedules: nothing is invoked any more
./deploy.sh teardown    # also delete functions, roles and bucket
```

`collect` reads CloudWatch Logs, so it works before and after `teardown`.
`teardown` keeps the log groups for that reason. Delete them in the CloudWatch
console once the CSV is safely downloaded.

## What to expect

Lambda freezes an execution environment between invocations rather than letting
it run, so without memory pressure the page cache may well survive untouched
until AWS reclaims the whole environment. That would show up as state B until
`env_id` changes, and never as state C. A null result at 1024 MB is therefore
informative, not a failure: it would mean cold data in a warm environment comes
from memory pressure, not from idle time.

Memory was the second axis on the expectation that a small setting would force
the page cache out. The run refuted that: the guest sees more memory than the
function is configured with (191 MB of `MemTotal` at 128 MB). At 256 MB and
above the database stays fully cached. At 128 MB about 50 MB of it does not fit,
and because the probe keeps re-reading its own samples it cannot see which
pages went. See `results/lambda/pilot/README.md`.

Two readings of the CSV follow directly. Across a function's rows sorted by
`ts`, an `env_id` change marks where AWS reclaimed the environment, and the gap
in `ts` across it is how long the environment survived idle. Within one
`env_id`, a falling `resident_pct` is state C.

## Cost

About 9,000 invocations over 14 hours for the default matrix, most under
100 ms, plus one 103 MB object in S3. This sits inside the Lambda, EventBridge Scheduler
and CloudWatch Logs free-tier allowances.

## Scope

Residency is sampled. A `reread` figure rests on 100 pages, about 5 points of
sampling error near 50%. A `once` figure rests on 4, so it is only meaningful
pooled across invocations and environments, which the analysis does. It does not measure query latency, and
it does not separate interior pages from leaves. The method differs from the
`mincore` probe the OpenWhisk campaign uses because Lambda forbids `mincore`,
and absolute numbers from Lambda are a separate batch that is not compared with
the workstation batches.
