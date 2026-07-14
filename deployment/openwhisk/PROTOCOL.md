# OpenWhisk Cold-Start Measurement Protocol

Authority for how the action measures SQLite cold-start behaviour and how
invocations are retained, paired, and aggregated. Documentation is kept in exact
correspondence with the implementation. **Phase 5A/5A.1 build the mechanism and
gates only; no performance result is produced.**

## 1. Measurement boundary

Each invocation times, with a monotonic clock, only:

| term          | field             | meaning                                                    |
|---------------|-------------------|------------------------------------------------------------|
| cold reset    | `reset_us`        | span of the efficacy-verified non-root eviction            |
| page select   | `select_us`       | choose the plan pages (cached at init; off critical path)  |
| delivery      | `deliver_us`      | per-page `MADV_WILLNEED` prefetch                          |
| cold open     | `open_us`         | fresh-connection open (standalone mode only; 0 in warm)    |
| first query   | `first_query_us`  | the exact requested `read <key>` (step only)               |
| handler total | `handler_total_us`| whole handler span                                         |

Process initialization (container start, module import, artifact validation, and
opening the warm handle) is **excluded** from every term. Deployment models are
composed downstream:

    e2e_warm       = deliver_us + first_query_us            (warm handle, open_us = 0)
    e2e_standalone = open_us + deliver_us + first_query_us  (fresh handle per call)

The plan/trace/oracle metadata is cached at process init, so `select_us` is off
the critical path and is **not** part of `e2e_warm`.

## 2. Warm-process definition and the warm SQLite handle

A *warm process* is one long-lived container process, identified by
`(process_uuid, pid, db_inode)` captured at init — **never** the activation id.
`invocation_counter` increments once per invocation; `warm_session_id` groups a
session.

The **primary (warm) mode** implements a genuine warm SQLite handle, mirroring
`benchmark_harness.c`: the connection is opened **once at process init** and
reused; `PRAGMA cache_size = 0` (the OS page cache is the only data cache); the
read statement is compiled once (via sqlite3's statement cache) and only *stepped*
at the measured query; the timing boundary wraps that step alone. Warm mode pays
**no** `open_us` on the critical path — and it is a real reused handle, not a
fresh open with `open_us` merely excluded.

`mmap_size` departs from the C-harness default (file size) and is set to **0**
(pager `pread` path). A persistent SQLite mmap pins the pages it traverses, which
blocks non-root re-eviction of those pages between invocations on a warm process;
the `pread` path keeps no mapping alive so the file can be re-colded before every
invocation without root. The canonical file-size value is recorded in the
manifest as `canonical_reference_pragmas` for fidelity comparison (it requires
root `drop_caches` to re-cold between invocations, which this non-root protocol
forbids).

The **standalone mode** opens a fresh connection per invocation with the same
pragmas and measures `open_us`; it is reported separately and never conflated
with the warm handle.

## 3. Cold-data definition, efficacy-based reset, residency threshold

*Cold data* means the OS page cache backing the reference DB has been evicted
using **non-root** hints only. Never `sudo`, `drop_caches`, container restart, or
reboot.

Cold reset is **efficacy-based, not rc-based**. Candidates are tried in order —
`MADV_DONTNEED`, page-aligned `POSIX_FADV_DONTNEED`, `MADV_PAGEOUT`, `MADV_COLD` —
and after each the mapping is dropped and a **fresh mapping** is made to
re-measure residency with `mincore`. Escalation stops as soon as zero mandatory
interiors are resident. Each attempt records `{method, rc, errno,
resident_interiors_after, resident_pages_after}` in `attempted_methods`. A
successful advice return code is never accepted as eviction: only the re-measured
`mincore` residency is the truth.

Strict acceptance threshold:

> **zero mandatory interior pages resident before any prefetch/query**
> (`resident_interiors_after_reset == 0` ⇒ `cold_threshold_passed = true`).

Total relevant residency uses the **whole-DB page count** as denominator
(`expected_relevant_page_count`), not the 92-page interior set
(`interior_page_count`).

## 4. Fail-closed gates (in order)

Every gate fails closed with a complete error envelope carrying `error_stage`;
no partial record is emitted that looks valid.

1. `concurrency` — the full measured critical section is serialized by a
   process-wide lock; an overlapping invocation is rejected.
2. `artifact_validation` — the session must have validated the manifest, DB
   (sha256/size/header page-size+count), classifier, and interior plan; and the
   OS page size must be 4096. An unvalidated session runs no measured query.
3. `request` — workload/seed/first-op known to the manifest; booleans well-typed;
   `request_id` non-empty; `expected_artifact_manifest_hash` a 64-hex string.
4. `identity` — DB device/inode unchanged since init; `expected_artifact_manifest_hash`
   non-empty and an exact match of the loaded manifest hash.
5. `cold_reset_required` — measured mode requires `cold_reset = true`;
   `cold_reset = false` is only allowed in `diagnostic_mode` and is never measured.
6. `cold_gate` — if `cold_threshold_passed` is false and not diagnostic, the
   handler returns **before** select/deliver/open/query.
7. `oracle` — the observed `(hit, result_digest)` must equal the frozen
   `first_query_oracle` entry (`oracle_passed`). Correctness is the exact expected
   hit/not-found and digest, **not** a hard-coded `query_hit == 1`.

`measured_valid` (non-diagnostic) is the strict AND of `cold_threshold_passed`,
`oracle_passed`, and no error. In diagnostic mode it is `null` and gates 5/6 are
advisory so residency behaviour can be observed.

## 5. Strategy validity

- `baseline`: `selected_page_count == 0`, `delivered_page_count == 0`.
- `2d`: `selected_page_count == 92`, all interior, `selected_leaf_count == 0`;
  `delivered_page_count` is the accepted `MADV_WILLNEED` count and is recorded.
- `resident_interiors_after_prefetch` is a separate observed field (delivery may
  be partial); it is never conflated with syscall acceptance.

## 6. Atomic keys

- **Observation key** (one measured cell, INCLUDES strategy):
  `(warm_session_id, workload, seed, first_operation_id, strategy)`.
- **Pairing-block key** (block within which a strategy pairs to its baseline,
  EXCLUDES strategy): `(warm_session_id, workload, seed, first_operation_id)`.
- Full atomic comparison unit for absolute values:
  `(OpenWhisk environment, action image digest, process session, workload, seed,
  first_operation, strategy)`. `action_image_digest` is carried in each response
  (or the frozen run config).

## 7. Relative comparison + aggregation

- A strategy pairs against a **baseline in the same pairing block and the same
  warm-process session**. No local-machine baseline is ever a denominator.
- Cross-seed: compute **per-seed paired values first**, then aggregate those;
  never a percentage from cross-seed absolute means.
- Cross-session results are a **separate** sensitivity analysis; absolute values
  are never merged across session identities without explicit hierarchical
  analysis.

## 8. Retention (exclusion) rules

Retain only if all hold: process identity present; `invocation_counter` strictly
increasing within the session; DB device/inode/sha256 unchanged; manifest hash
matched; `cold_threshold_passed`; `oracle_passed`; no action/SQLite error.
Otherwise `valid = false` with an `exclusion_reason`.

## 9. Session-change handling and separate batch

Any change in `(process_uuid, pid, db_inode)` — container recycle, redeploy, image
swap — starts a **new session group**; one action version per measured batch. The
OpenWhisk numbers are a **separate result batch**, never written to or merged with
the canonical `results/` tree. **Absolute local-machine and OpenWhisk latencies
are not directly compared**; whether the locally observed strategy *ordering*
carries over is the empirical question this measurement will test.
