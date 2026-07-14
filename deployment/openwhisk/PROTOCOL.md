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

The **primary (warm) mode** implements a genuine warm SQLite handle via a ctypes
bridge to the system `libsqlite3` (`action/sqlite_bridge.py`), mirroring
`benchmark_harness.c` at the C-API level rather than relying on Python's sqlite3
statement cache: `sqlite3_open_v2` (read-only) is called **once at process
init**, `PRAGMA cache_size = 0` is set (the OS page cache is the only data
cache), and the canonical statement `SELECT payload FROM items WHERE id=?1` is
compiled once with `sqlite3_prepare_v2` — which compiles **without stepping**, so
no B-tree data page is faulted at init. Each query is `sqlite3_reset` /
`sqlite3_clear_bindings` / `sqlite3_bind_int64` / `sqlite3_step`, and the timing
boundary wraps `sqlite3_step` alone. Warm mode pays **no** `open_us` on the
critical path — a real reused `sqlite3*` + `sqlite3_stmt*`, not a fresh open with
`open_us` merely excluded. The returned value is the payload blob and the oracle
digests it (`sha256(payload)`).

Before each cold reset the action calls `sqlite3_db_release_memory` to release
reclaimable pager heap so SQLite-held page copies do not defeat the OS eviction,
and it captures `sqlite3_db_status(CACHE_HIT/MISS)` around the query: with
`cache_size = 0`, repeated cold queries show pager **misses**, proving the SQLite
pager cache is not serving the query and the measured latency reflects the OS
page-cache state.

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
- `2d`: `selected_page_count == 92`, `selected_interior_count == 92`,
  `selected_leaf_count == 0`, `delivered_page_count == 92`.
- These exact invariants are checked as `delivery_valid`, which is a required
  conjunct of `measured_valid`; an incomplete 2d delivery is never measured-valid.
- `resident_interiors_after_prefetch` is a separate observed effectiveness field
  (delivery may be partial); it is never conflated with syscall acceptance.

## 6. Pair identity, schedule, and atomic keys

Every measured request carries a pair/identity tuple that the action echoes
verbatim: `pair_id`, `repetition_id`, `schedule_position`, `schedule_seed`,
`run_config_sha256`, `expected_action_image_digest`, `handle_mode`. Measured mode
requires: non-empty `pair_id`; non-negative `repetition_id`; positive
`schedule_position`; 64-hex `run_config_sha256`; a non-empty immutable action
image digest that **exactly matches** the observed running image
(`OW_ACTION_IMAGE_DIGEST`).

`client/build_schedule.py` emits, for each
`(workload, seed, first_operation, handle_mode, repetition_id, target)`, exactly
one `pair_id` with exactly two arms — one baseline, one target — whose AB/BA
order is a deterministic function of `schedule_seed` (reproducible, no RNG). The
full schedule is persisted before any invocation. A warmup-only diagnostic
invocation is emitted first and the driver injects one on every new
`process_uuid`; warmup invocations are never measured.

- **Observation key** (one measured cell, INCLUDES strategy):
  `(run_config_sha256, artifact_manifest_sha256, action_image_digest,
  warm_session_id, workload, seed, first_operation_id, handle_mode, pair_id,
  strategy)`.
- **Formal pair key** (a strategy pairs to its baseline within this block,
  EXCLUDES strategy): `(run_config_sha256, artifact_manifest_sha256,
  action_image_digest, warm_session_id, workload, seed, first_operation_id,
  handle_mode, pair_id)`.

For every `pair_id` the summarizer requires **exactly one baseline and exactly
one target**; it reports duplicate arms, missing arms, and **session-break** pairs
(the two arms carried different `warm_session_id` — the whole pair is invalidated
and neither arm is paired elsewhere).

## 6b. Metrics and aggregation

- `first_query_us` — always.
- `e2e_warm_us = deliver_us + first_query_us` — only when `handle_mode == warm`.
- `e2e_standalone_us = open_us + deliver_us + first_query_us` — only when
  `handle_mode == standalone`.

Aggregation: (1) compute each pair's effect; (2) average repetitions **within
each seed**; (3) average the per-seed estimates across seeds with **equal
weight**. Unequal valid repetition counts never reweight a seed. Never mix
workloads, handle modes, first-operation ids, strategies, or artifact/image/
run-config identities.

## 7. Relative comparison + aggregation

- A strategy pairs against a **baseline in the same pairing block and the same
  warm-process session**. No local-machine baseline is ever a denominator.
- Cross-seed: compute **per-seed paired values first**, then aggregate those;
  never a percentage from cross-seed absolute means.
- Cross-session results are a **separate** sensitivity analysis; absolute values
  are never merged across session identities without explicit hierarchical
  analysis.

## 8. Retention (exclusion) rules

`collect.classify` retains a row only if all hold: the response is a dict; the
request/response identity fields match (`request_id`, workload, strategy, seed,
first_operation_id, handle_mode, pair_id); `diagnostic_mode` is False (diagnostic
rows are never valid for performance); `cold_reset_requested`,
`cold_threshold_passed`, `oracle_passed`, `delivery_valid`, and `measured_valid`
are all True; the response's `artifact_manifest_sha256`, `action_image_digest`,
and `run_config_sha256` equal the run config; process identity present;
`invocation_counter` a positive int strictly increasing within its session; no
action/SQLite/platform error and a successful activation status. Otherwise
`valid = false` with an `exclusion_reason`. Invoke/activation exceptions are
recorded as invalid rows without aborting the run, and duplicate request ids are
rejected.

## 9. Session-change handling and separate batch

Any change in `(process_uuid, pid, db_inode)` — container recycle, redeploy, image
swap — starts a **new session group**; one action version per measured batch. The
OpenWhisk numbers are a **separate result batch**, never written to or merged with
the canonical `results/` tree. **Absolute local-machine and OpenWhisk latencies
are not directly compared**; whether the locally observed strategy *ordering*
carries over is the empirical question this measurement will test.
