# OpenWhisk Cold-Start Measurement Protocol

This protocol defines how the OpenWhisk action measures SQLite cold-start
behaviour and how invocations are retained, paired, and aggregated. It is the
authority for the next (measurement) phase. **Phase 5A implements the mechanism
and gates only; it produces no performance result.**

## 1. Measurement boundary

Each invocation measures, with a monotonic high-resolution clock, only:

| term              | field             | meaning                                              |
|-------------------|-------------------|------------------------------------------------------|
| cold reset        | `reset_us`        | non-root eviction hint over the DB mapping           |
| page selection    | `select_us`       | load the frozen plan and choose pages                |
| delivery          | `deliver_us`      | per-page `MADV_WILLNEED` prefetch                    |
| cold file open    | `open_us`         | opening the SQLite connection for the query          |
| first query       | `first_query_us`  | the exact requested `read <key>`                     |
| handler total     | `handler_total_us`| whole handler span                                   |

Process initialization time (container start, module import, artifact
validation) is **excluded** from every term above; it happens once per warm
process, before any invocation is timed. The two deployment models are composed
downstream, exactly as in the local study:

    e2e_warm       = deliver_us + first_query_us          (handle already open)
    e2e_standalone = open_us + deliver_us + first_query_us (cold open paid)

## 2. Warm-process definition

A *warm process* is one long-lived OpenWhisk container process. It is identified
by `(process_uuid, pid, db_inode)` captured at process init — **never** by the
OpenWhisk activation id. `invocation_counter` increments once per invocation
inside that process. A `warm_session_id` groups invocations sharing that triple.

## 3. Cold-data definition and residency acceptance threshold

*Cold data* means the OS page cache backing the reference DB has been evicted for
this measurement, achieved with **non-root** hints only (`MADV_DONTNEED`, with
`MADV_PAGEOUT`/`MADV_COLD` fallbacks). Never `sudo`, `drop_caches`, container
restart, or host reboot.

A successful `madvise` return code is **not** accepted as eviction. Residency is
re-measured with `mincore` after the reset. The strict acceptance threshold is:

> **zero mandatory interior pages resident before any prefetch/query**
> (`resident_interiors_after_reset == 0` ⇒ `cold_threshold_passed = true`).

Total relevant-page residency is also reported. If the filesystem/runtime cannot
evict non-root (the pages stay resident), the invocation is **excluded** with a
diagnostic reason — it is never silently accepted as warm.

## 4. Atomic comparison unit

    (OpenWhisk environment, action image digest, process session,
     workload, seed, first_operation, strategy)

Absolute latencies are only ever compared inside a single such unit.

## 5. Relative comparison rules

- A strategy is paired against a **baseline from the same OpenWhisk
  run/configuration**, the same workload and seed, the same first operation, the
  same warm-process session where possible, and the same cold-verification
  criteria.
- **No local-machine baseline is ever used as a denominator** for an OpenWhisk
  strategy.
- Cross-seed aggregation computes **per-seed paired values first**, then
  aggregates those paired values. A percentage is never derived from cross-seed
  absolute means.

## 6. Retention (exclusion) rules

An invocation is retained only if **all** hold:

1. expected process UUID/PID session present (`process_uuid` non-empty);
2. `invocation_counter` strictly increases within its session;
3. DB `device`/`inode`/`sha256` unchanged from the manifest;
4. `expected_artifact_manifest_hash` matches;
5. `cold_threshold_passed` is true (zero resident mandatory interiors pre-query);
6. `query_hit == 1` with a correct `result_digest`;
7. no action/platform/SQLite error.

Otherwise the collector records `valid = false` with an `exclusion_reason`.

## 7. Session-change handling

Any change in `(process_uuid, pid, db_inode)` — a container recycle, an action
redeploy, or an image swap — starts a **new session group**. Absolute values are
never merged across session identities without an explicit hierarchical
analysis. One action version is used per measured batch.

## 8. Separate result batch

The OpenWhisk numbers are a **separate result batch**. They are not written to
the canonical `results/` tree used by the local study and are not merged into it.
**Absolute local-machine and OpenWhisk latencies are not directly compared**; only
same-batch paired relative effects are meaningful across the two environments.
Whether the locally observed *ordering* of strategies carries over to a FaaS
runtime is the empirical question this measurement will test.
