# Portability matrix (workstation → OpenWhisk deployment complement)

This is a **deployment / feasibility + footprint** complement to the frozen YC
primary (1600 invocations) and secondary (2000 invocations) OpenWhisk campaigns.
It carries the already-frozen native prefetch strategies onto four additional
workloads, plus the two budget-matched ranked competitors on canonical YC, and
proves they deploy, deliver, and validate under the same fail-closed runtime — on
a **new, independent run-config identity**. It adds no new performance claim.

## Claim scope (read before interpreting any number)

- The warm-handle paired **first-query latency is NOT a strategy-performance
  estimate.** The page-cache-carryover explanation was **falsified**; the observed
  warm ordering is a systematic short-lived **positional / order effect**, not
  random hardware fluctuation and not a cache-residency win. See
  [`PAIR_CARRYOVER_AUDIT.md`](PAIR_CARRYOVER_AUDIT.md) and
  [`FULL_STRATEGY_AUDIT.md`](FULL_STRATEGY_AUDIT.md).
- `first_query_us` is the instrumented SQLite first-query phase only — **not**
  total cold-start / end-to-end time.
- What this matrix legitimately shows: the strategies **deploy and deliver
  correctly** across workloads, and their **delivered page footprint** (interior
  skeleton vs leaf union vs whole resident set) behaves as frozen. It does not
  change the cost-accounting thesis ("a faster first query is not a faster
  end-to-end run").
- This scope note lives here, in the OpenWhisk docs — **not** in `REPORT.md`.

## Identity (independent; the frozen campaigns are untouched)

| identity | value | invocation plan |
|---|---|---|
| primary (frozen)   | `022fbeb0…` | `invocation_plan` |
| secondary (frozen) | `441609e6…` | `secondary_invocation_plan` |
| **portability**    | `64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947` | `portability_invocation_plan` |

`portability_run_config_sha256` is `sha256` over the canonical
`portability_invocation_plan` (sorted-key compact JSON) and recomputes
deterministically (guarded by `test_portability_matrix.py`). It is distinct from
both frozen identities; the primary/secondary plans and their run-config SHAs are
asserted **byte-unchanged** by the pin writer and by the test suite.

`workload_set` (authoritative, fail-closed) = the five workload IDs this matrix may
address; `session.py` refuses any keyed plan or trace outside it (no implicit YC
fallback), and `ws2/05_full_matrix.sh` unions it with the canonical YC id for its
workload gate.

## The four rectangular sub-matrices (schedule_seed = 20260826)

Each sub-matrix is a strict Cartesian product (required by
`client/validate_schedule.py`). `baseline` is the paired A-arm anchor, not a
target; pairs = |W|·|S|·|F|·|M|·|R|·|T|, invocations = 2·pairs. All use
first_operation_ids `[0]`, handle_modes `{warm, standalone}`, repetitions 3.

| file | workloads | targets (non-baseline) | seeds | pairs | invocations |
|---|---|---|---|---:|---:|
| `matrix.portability.m1.json` | read_uniform, hot_hashed_01, read_tail_hit_20k | `2e_K10`, `2f_slru` | 1,2,3 | 108 | 216 |
| `matrix.portability.m2.json` | read_tail_mixed_20k | `2e_K10`, `2f_slru`, `leaf_freq_K10`, `leaf_rand_K10` | 1,2,3 | 72 | 144 |
| `matrix.portability.m3.json` | read_zipf (YC) | `2f_top28`, `learned_markov_28` | 1,2,3 | 36 | 72 |
| `matrix.portability.m4.json` | read_uniform, hot_hashed_01, read_tail_mixed_20k | `2d` | 1 | 18 | 36 |
| **total** | | | | **234** | **468** |

Strategy semantics (frozen, source = `portability_freeze_report.json`):

- `2d` — 92-page interior skeleton (static, workload/seed-independent). M4 probes
  it on one seed across three workloads as the cross-workload deployment check.
- `2e_K10` — 92 skeleton ∪ top-10 hot leaves = 102 pages (reconstructed).
- `2f_slru` — whole resident working set; **emergent** interior count per seed
  (92 for read_uniform/hot_hashed_01; 5 for read_tail_hit_20k; 4 for
  read_tail_mixed_20k). Skeleton set-equality is enforced only when the emergent
  interior count is 92; otherwise the split is recorded, not imposed.
- `leaf_freq_K10` / `leaf_rand_K10` — 10 leaves, **0 interiors** (leaf-only
  frequency-vs-random ablation on read_tail_mixed_20k).
- `2f_top28` — top-28-by-frequency ranked dump on YC (emergent 26 interior / 2
  leaf; split recorded, only total==28 enforced).
- `learned_markov_28` — held-out **LOSO** first-order Markov model on YC, budget 28
  (per test-seed, trained on the other nine).

## Exact WK2 commands (run on Workstation2 only — never on WK1)

Follow [`WS2_RUNBOOK.md`](WS2_RUNBOOK.md) Terminal B verbatim through stage 04
(detached checkout of the shipped SHA, `00_preflight` → `01_build_image` →
`02_deploy` → `03_diagnostic` → `04_feasibility`). The image bakes the 36 frozen
delivery-plan CSVs (under `config/plans/keyed/`) and stages the 12 portability
workload traces; the build-time self-check fails closed if any is absent.

Then run stage 05 **once per sub-matrix** (each validates + schedules
independently; execution stays behind the implementation gate until you set
`WS2_MATRIX_IMPL_READY=1`):

```bash
cd deployment/openwhisk/ws2

# Validate + schedule all four (no invocation). Each prints its paired-cell count;
# they must read 108, 72, 36, 18 -> 234 pairs / 468 invocations in total.
for M in m1 m2 m3 m4; do
  bash 05_full_matrix.sh --matrix ./matrix.portability.$M.json
done

# Execute the matrix (each sub-matrix, in order). Requires a cooled diagnostic (03)
# and the implementation gate opened. OW_ARTIFACT_MANIFEST_SHA256 is the sha256 of
# the artifacts.json baked into the deployed image (same value used at stage 03).
export WS2_MATRIX_IMPL_READY=1
export OW_ARTIFACT_MANIFEST_SHA256='<sha256 of the image-baked artifacts.json>'
for M in m1 m2 m3 m4; do
  bash 05_full_matrix.sh --matrix ./matrix.portability.$M.json
done

# Collect (packages every sub-matrix run under this checkout).
bash 06_collect.sh --openwhisk-sha "$(git -C /path/to/openwhisk rev-parse HEAD)"
```

Each stage-05 run stamps `portability_run_config_sha256` on every request
(selected via `run_config_key` in the matrix file) and refuses to run if any
requested strategy is absent from `portability_invocation_plan.strategies` — so a
portability strategy can never be recorded under the frozen primary/secondary
identity.

## What is committed vs machine-local

Committed (shipped from WK1): the four `matrix.portability.m*.json`, the 36 frozen
delivery-plan CSVs + `portability_freeze_report.json`, the extended pin
`config/artifacts.native_ycsb.json`, the runtime/builder/WS2 changes, and this
doc. Machine-local (git-ignored, regenerated on WK2): `config/artifacts.json`,
`ws2/_image_stage/`, `ws2/_runs/**`.
