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

Each invocation first reads 100 pages spread evenly over the database and
counts those under 100 us as resident. squashfs decompresses whole blocks of up
to 1 MB and caches every page in the block, so the samples sit about 1.03 MB
apart and no read can warm another sample. Every raw latency is kept in
`lat_us`, so the threshold can be re-drawn afterwards.

Probing re-reads every sampled page it finds missing, so each invocation ends
with all samples resident. What the next invocation measures is therefore how
much of the data read at the previous invocation survived one idle interval,
which is the scenario of a function that reads its data and then goes idle. An
environment's first invocation also reads the whole database once, so the
first interval starts from as warm a cache as the memory size allows.

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
3. Smoke-test one cell before the full matrix:
   ```
   chmod +x deploy.sh
   MEMS=1024 IDLES=1 ./deploy.sh deploy
   # wait about 3 minutes
   ./deploy.sh collect
   head -3 residency_*.csv
   ```
   Expect `cold_start` true on the first row, then false with `idle_s` near 60.
4. Full matrix:
   ```
   ./deploy.sh deploy
   ```

The schedules run on AWS, so closing CloudShell does not stop anything.

## Matrix and run length

Default: memory `128 256 512 1024` MB by idle `1 5 15 30 60` minutes, 20
functions running in parallel. Separate functions never share an execution
environment, so the cells do not interfere. The 60-minute cell needs about 10
hours to collect 10 samples, so an overnight run of about 12 hours covers every
cell. Override with `MEMS="..." IDLES="..."`.

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

That is why memory is the second axis. The memory setting sizes the execution
environment, and the page cache competes with the Python runtime for it. At
128 MB the 103 MB database cannot all stay resident alongside the runtime, which
is the setting most likely to produce state C.

Two readings of the CSV follow directly. Across a function's rows sorted by
`ts`, an `env_id` change marks where AWS reclaimed the environment, and the gap
in `ts` across it is how long the environment survived idle. Within one
`env_id`, a falling `resident_pct` is state C.

## Cost

About 3,800 invocations over 12 hours for the default matrix, most under 100 ms,
plus one 103 MB object in S3. This sits inside the Lambda, EventBridge Scheduler
and CloudWatch Logs free-tier allowances.

## Scope

Residency is sampled, 100 pages per invocation, so each figure carries a
sampling error of about 5 points near 50%. It is measured on data the previous
invocation read, not on the whole file. It does not measure query latency, and
it does not separate interior pages from leaves. The method differs from the
`mincore` probe the OpenWhisk campaign uses because Lambda forbids `mincore`,
and absolute numbers from Lambda are a separate batch that is not compared with
the workstation batches.
