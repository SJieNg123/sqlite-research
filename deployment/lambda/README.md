# Lambda probe: warm container, cold data

The advisor's second suggestion: a function that carries the reference database,
checks with `mincore` on every invocation how much of that database is still in
the page cache, and is invoked at different idle intervals. The question is
whether a **reused** execution environment can still find its data cold.

`build.sh` only packages. Nothing in this directory touches AWS until you run
`deploy.sh` yourself in CloudShell.

## What each invocation records

Before anything reads the file, the handler measures whole-file residency with
the same `residency.py` the OpenWhisk campaign uses. On an environment's first
invocation it then reads the whole database once, so later invocations start
from as warm a cache as the memory size allows and read nothing further.
Residency in a reused environment can therefore only hold or fall, and any fall
is what the idle interval took away.

Three states, told apart by `env_id`, which is generated once per execution
environment:

| state | `cold_start` | `resident_pct` | meaning |
|---|---|---|---|
| A | true | whatever deployment left | new environment, an ordinary cold start |
| B | false | about `resident_after_warm_pct` | warm environment, warm data |
| **C** | **false** | **well below it** | **warm environment, cold data: the phenomenon** |

Each record also carries `idle_s`, `env_age_s`, `mem_mb`, `log_stream` (AWS's own
per-environment id, a cross-check on `env_id`) and `MemTotal`, `MemAvailable`
and `Cached` from `/proc/meminfo`.

## Build (workstation)

```
deployment/lambda/build.sh
```

Writes `build/residency_probe.zip` (handler, `residency.py`, `test.db` and a
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

Residency is whole-file, and invocations after the first issue no queries,
which is what the advisor asked for: it isolates what idle time removes. It does
not measure query latency, and it does not separate interior pages from leaves.
Absolute numbers from Lambda are a separate batch and are not compared with the
workstation batches, the same rule the OpenWhisk campaign follows.
