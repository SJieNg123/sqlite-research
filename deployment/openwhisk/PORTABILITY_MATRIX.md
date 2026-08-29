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

## One single-batch campaign = the union of four logical blocks (schedule_seed = 20260826)

Formal execution is **one** matrix, `ws2/matrix.portability.json`: a block-union
campaign whose `blocks` list holds four heterogeneous rectangular blocks. The UNION
of the explicit blocks is the formal matrix — **no** global Cartesian product is
taken across workloads and strategies (that would fabricate scientifically
unintended workload×strategy cells). Each block is itself a strict Cartesian product;
`baseline` is the paired A-arm anchor in every block, not a target; per-block pairs =
|W|·|S|·|F|·|M|·|R|·|T|, invocations = 2·pairs. All blocks use first_operation_ids
`[0]`, handle_modes `{warm, standalone}`, repetitions 3. The whole campaign runs under
ONE `portability_run_config_sha256`, ONE `schedule_seed`, and ONE campaign fingerprint
over the complete ordered 468-invocation schedule.

| logical block | workloads | targets (non-baseline) | seeds | pairs | invocations |
|---|---|---|---|---:|---:|
| block1 | read_uniform, hot_hashed_01, read_tail_hit_20k | `2e_K10`, `2f_slru` | 1,2,3 | 108 | 216 |
| block2 | read_tail_mixed_20k | `2e_K10`, `2f_slru`, `leaf_freq_K10`, `leaf_rand_K10` | 1,2,3 | 72 | 144 |
| block3 | read_zipf (YC) | `2f_top28`, `learned_markov_28` | 1,2,3 | 36 | 72 |
| block4 | read_uniform, hot_hashed_01, read_tail_mixed_20k | `2d` | 1 (structural) | 18 | 36 |
| **union (one campaign)** | | | | **234** | **468** |

The four `matrix.portability.m{1..4}.json` files remain **only** as readable
logical-block fragments and each flattens cell-for-cell into the block of the same
number; they are **not** units of formal execution. block4 is the static-`2d`
cross-workload deployment check on ONE structural seed identity — its seed axis stays
`[1]` and must never expand to 1,2,3.

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

Then run stage 05 **exactly once** on the single campaign matrix (it validates the
complete 468-invocation schedule, then execution stays behind the implementation gate
until you set `WS2_MATRIX_IMPL_READY=1`):

```bash
cd deployment/openwhisk/ws2

# Validate + schedule the whole campaign (no invocation). Prints one paired-cell
# count: 234 pairs / 468 invocations across 4 blocks, single fingerprint.
bash 05_full_matrix.sh --matrix ./matrix.portability.json

# Execute the ONE campaign. Requires a cooled diagnostic (03) and the implementation
# gate opened. OW_ARTIFACT_MANIFEST_SHA256 is the sha256 of the artifacts.json baked
# into the deployed image (same value used at stage 03). Resume-safe: re-run the same
# command to continue from the last completed schedule position.
export WS2_MATRIX_IMPL_READY=1
export OW_ARTIFACT_MANIFEST_SHA256='<sha256 of the image-baked artifacts.json>'
bash 05_full_matrix.sh --matrix ./matrix.portability.json

# Collect (packages the single campaign run under this checkout as ONE bundle).
bash 06_collect.sh --openwhisk-sha "$(git -C /path/to/openwhisk rev-parse HEAD)"
```

The single stage-05 run stamps `portability_run_config_sha256` on every request
(selected via `run_config_key` in the matrix file) and refuses to run if any
requested strategy — the UNION across all blocks — is absent from
`portability_invocation_plan.strategies`, so a portability strategy can never be
recorded under the frozen primary/secondary identity.

## Portability-EXTENSION campaign (the 29 remaining workstation cells)

A **separate, additive** campaign covers the 29 `(workload, strategy)` cells the
workstation ran but the primary/secondary/portability OpenWhisk campaigns did **not** —
completing the workstation-coverage matrix so the effectiveness comparison can extend to
the full set. It is a fourth independent identity; the portability campaign above is
**byte-untouched**.

| identity | value | invocation plan |
|---|---|---|
| **portability_ext** | `bf504a28…` | `portability_ext_invocation_plan` |

`portability_ext_run_config_sha256` recomputes deterministically over its canonical
`portability_ext_invocation_plan` (sorted-key compact JSON), and is asserted distinct
from primary `022fbeb0…`, secondary `441609e6…`, and portability `64f44c3e…` — all three
of which the ext pin writer re-asserts **byte-unchanged** (guarded by
`test_portability_ext.py`).

Formal execution is **one** matrix, `ws2/matrix.portability_ext.json`: a block-union of
seven heterogeneous blocks (B5–B11), one `schedule_seed = 20260828`, one campaign
fingerprint over the ordered **852-invocation** schedule.

| block | workloads | targets (non-baseline) | seeds | pairs | invocations |
|---|---|---|---|---:|---:|
| block5  | YC | `2f_top14`, `learned_markov_14` | 1,2,3 | 36 | 72 |
| block6  | YCu, YCh01 | `2e_K500`, `2f_top28`, `2f_top14`, `learned_markov_28`, `learned_markov_14` | 1,2,3 | 180 | 360 |
| block7  | C_hit | `2e_K500`, `2f_top28`, `learned_markov_28`, `2f_top14`, `learned_markov_14` | 1,2,3 | 90 | 180 |
| block8  | C (mixed_20k) | `2f_top14`, `2f_top28`, `2e_K500`, `learned_markov_28` | 1,2,3 | 72 | 144 |
| block9  | YC, YCu, YCh01, C_hit | `layers_92` | 1 (structural) | 24 | 48 |
| block10 | YCu, YCh01, C | `layers_5` | 1 (structural) | 18 | 36 |
| block11 | C_hit | `2d` | 1 (structural) | 6 | 12 |
| **union (one campaign)** | | | | **426** | **852** |

21 keyed cells × 3 seeds = **63 frozen delivery plans** (`portability_ext_freeze_report.json`,
provenance in `config/plans/keyed/native_source/portability_ext/PROVENANCE.md`); 8 static
cells (seed 1, inline). C has no N=14 learned cell (block8 carries `learned_markov_28`
only). `layers_92` is the only genuinely new action strategy — the full 92-interior
skeleton (same page content as `2d`, distinct name); `layers_5`/`2d` were already wired.
Blocks 9–11 are structural cross-workload deployment checks: their seed axis stays `[1]`.

**New image identity:** adding the 63 ext plans to the live `artifacts.json` changes its
bytes, so this campaign runs under a **new image identity**; the archived portability
image identity is unaffected (already built + archived).

Run stage 05 **exactly once** on the ext matrix (WK2 only — same Terminal-B flow through
stage 04, same gate `WS2_MATRIX_IMPL_READY=1`):

```bash
cd deployment/openwhisk/ws2
# Validate + schedule (no invocation): 426 pairs / 852 invocations across 7 blocks,
# single fingerprint distinct from the portability campaign.
bash 05_full_matrix.sh --matrix ./matrix.portability_ext.json
# Execute the ONE ext campaign (requires cooled 03 + gate open + the ext image's manifest sha).
export WS2_MATRIX_IMPL_READY=1
export OW_ARTIFACT_MANIFEST_SHA256='<sha256 of the ext image-baked artifacts.json>'
bash 05_full_matrix.sh --matrix ./matrix.portability_ext.json
```

## Portability-FULL-CLOSURE campaign (the final 16 workstation cells)

A **fifth, independent, additive** campaign closes the last 16 `(workload, strategy)`
cells the workstation ran but no OpenWhisk campaign (primary/secondary/portability/
portability_ext) had reached — taking the canonical **65-cell** portability matrix to
**complete cell coverage**. The four prior campaigns above stay **byte-untouched**.

| identity | value | invocation plan |
|---|---|---|
| **portability_full_closure** | `a5be8f15…` | `portability_full_closure_invocation_plan` |

`portability_full_closure_run_config_sha256` recomputes deterministically over its
canonical `portability_full_closure_invocation_plan` (sorted-key compact JSON), and is
asserted distinct from primary `022fbeb0…`, secondary `441609e6…`, portability
`64f44c3e…`, and portability_ext `bf504a28…` — all four of which the closure pin writer
re-asserts **byte-unchanged** (guarded by `test_portability_full_closure.py`).

Formal execution is **one** matrix, `ws2/matrix.portability_full_closure.json`: a
block-union of six heterogeneous blocks (B12–B17), one `schedule_seed = 20260829`, one
campaign fingerprint over the ordered **456-invocation** schedule.

| block | workloads | targets (non-baseline) | seeds | pairs | invocations |
|---|---|---|---|---:|---:|
| block12 | C (mixed_20k) | `2e_K40`, `2e_K92` | 1 | 12 | 24 |
| block13 | C_hit | `2e_K40`, `2e_K92` | 1,2,3 | 36 | 72 |
| block14 | C (mixed_20k) | `learned_markov_14` (LOSO) | 1,2,3 | 18 | 36 |
| block15 | C (mixed_20k) | `layers_92` | 1 (structural) | 6 | 12 |
| block16 | YC, YCu, YCh01, C_hit | `lp_sorted`, `lp_shuf` | 1,2,3 | 144 | 288 |
| block17 | C (mixed_20k) | `lp_sorted`, `lp_shuf` | 1 | 12 | 24 |
| **union (one campaign)** | | | | **228** | **456** |

The 4 new-name keyed strategies × their cells = **37 frozen delivery plans**
(`portability_full_closure_freeze_report.json`, native sources under
`config/plans/keyed/native_source/portability_full_closure/`): `2e_K40` (4), `2e_K92` (4),
`learned_markov_14` (3, C only — disjoint from the ext learned_markov_14 cells),
`lp_sorted` (13), `lp_shuf` (13). `layers_92` (block15) reuses the already-committed
92-interior skeleton — **static, no new frozen plan**.

`2e_K40`/`2e_K92` are the `2e_K500` reconstruct at smaller leaf budgets: the FULL
92-interior skeleton (set-equality gate, `eip==92`) UNION the native top-≤K hot leaves.

**lp ordered delivery.** `lp_sorted`/`lp_shuf` both deliver the SAME resident page set as
the corresponding canonical `2f_slru` working set; they differ ONLY in the ORDER of a
synchronous page-sized `pread` loop (`delivery_method = "pread_ordered"`, never async
`MADV_WILLNEED`). `lp_sorted` delivers offset-ascending; `lp_shuf` delivers an
offset-sort then `random.Random(424242).shuffle` order. Offsets are frozen **in delivery
order**, so `plan_sha256` is **order-sensitive**: the two arms share an identical
unordered page set but carry different ordered-sequence SHAs. lp's primary quantity is
`deliver_us` / e2e including delivery, **not** first_query.

**Claim boundary.** This closes **cell coverage** of the 65-cell matrix
(every canonical `(workload, strategy)` cell now has an OpenWhisk arm), **not** an exact
replication of every workstation seed/repetition protocol. Executed BOTH stays **49/65**
until WK2 evidence is archived; the closure only makes it *plannable* to 65/65.

**New image identity:** adding the 37 closure plans to the live `artifacts.json` changes
its bytes, so this campaign runs under a **new image identity**; the four archived
campaign image identities are unaffected.

Run stage 05 **exactly once** on the closure matrix (WK2 only — same Terminal-B flow):

```bash
cd deployment/openwhisk/ws2
# Validate + schedule (no invocation): 228 pairs / 456 invocations across 6 blocks,
# single fingerprint distinct from the portability AND portability_ext campaigns.
bash 05_full_matrix.sh --matrix ./matrix.portability_full_closure.json
# Execute the ONE closure campaign (requires cooled 03 + gate open + the closure image's manifest sha).
export WS2_MATRIX_IMPL_READY=1
export OW_ARTIFACT_MANIFEST_SHA256='<sha256 of the closure image-baked artifacts.json>'
bash 05_full_matrix.sh --matrix ./matrix.portability_full_closure.json
```

## Outlier-replication campaign (stability / confound check — NOT new coverage)

A **sixth, independent, additive** campaign is a targeted **stability / confound check**,
not new coverage and not a sixth pooled performance estimator. It re-runs, under **exact
deterministic baseline-target position balance** and **standalone handles only**, the six
`(workload, strategy)` cells whose original OpenWhisk↔workstation first-query discrepancy
is largest: the true sign-flips `C/layers_92`, `C/2d`, `C_hit/2e_K40`, and the WS-neutral
anomalies `C/layers_5` (OW strongly negative), `YCh01/layers_5`, `YCu/layers_5` (OW
positive). All six are already members of the frozen **65-cell** matrix, so **coverage
stays 65/65 and this campaign adds no coverage**; it **reuses every plan/strategy/runtime
byte-for-byte** (0 new keyed plans, 0 new markers). The five prior campaigns stay
**byte-untouched**.

| identity | value | invocation plan |
|---|---|---|
| **portability_outlier_replication** | `a564770a…` | `portability_outlier_replication_invocation_plan` |

`portability_outlier_replication_run_config_sha256` recomputes deterministically over its
canonical `portability_outlier_replication_invocation_plan` (sorted-key compact JSON), and
is asserted distinct from primary `022fbeb0…`, secondary `441609e6…`, portability
`64f44c3e…`, portability_ext `bf504a28…`, and portability_full_closure `a5be8f15…` — all
five of which the replication pin writer re-asserts **byte-unchanged** (guarded by
`test_portability_outlier_replication.py`).

Formal execution is **one** matrix, `ws2/matrix.portability_outlier_replication.json`: a
block-union of four blocks (R1–R4), one `schedule_seed = 20260830`, `position_balance =
"exact"`, one campaign fingerprint over the ordered **236-invocation** schedule.

| block | workloads | targets (non-baseline) | seeds | reps | pairs | invocations |
|---|---|---|---|---:|---:|---:|
| R1 | C (mixed_20k) | `layers_92`, `2d`, `layers_5` | 1 | 20 | 60 | 120 |
| R2 | YCh01 | `layers_5` | 1 | 20 | 20 | 40 |
| R3 | YCu | `layers_5` | 1 | 20 | 20 | 40 |
| R4 | C_hit | `2e_K40` | 1,2,3 | 6 | 18 | 36 |
| **union (one campaign)** | | | | | **118** | **236** |

**Exact position balance is a hard gate.** Unlike the five prior campaigns (per-pair hash
coin-flip, which for small n produced the very 0/3, 1/2, 2/7 baseline/target-first splits
that confound the original discrepancies), this campaign sets `position_balance: "exact"`:
`build_schedule.build_campaign_schedule` ranks each cell's reps by
`sha256(seed|cell|rep)` and assigns the lower half baseline-first, the upper half
target-first, **guaranteeing exactly `reps/2` each**; `validate_schedule.validate_campaign`
fails closed unless every cell is `baseline_first == target_first` — **10/10** for each
single/static cell, **3/3** for each `C_hit/2e_K40` seed. The flag is opt-in: the five
frozen (flagless) matrices build **byte-identically** (their fingerprints are re-asserted
by the existing tests). `2e_K40` reuses the audited full-closure keyed plans;
`layers_92`/`2d`/`layers_5` reuse committed static strategy artifacts — **no re-freeze**.

Interpretation is **pre-registered** (`PORTABILITY_OUTLIER_REPLICATION.md`): the
replication does **not** replace the original `R_ow`; `analysis/analyze_outlier_replication.py`
reports **both** batches side by side and classifies each cell (reproduced deployment
divergence / original position-or-state-confounded / execution-sensitive), fixed before
any evidence existed and failing closed until the archived evidence exists.

```bash
cd deployment/openwhisk/ws2
# Validate + schedule (no invocation): 118 pairs / 236 invocations across 4 blocks,
# STANDALONE only, exact 10/10 & 3/3 position balance, fingerprint distinct from all five
# prior campaigns.
bash 05_full_matrix.sh --matrix ./matrix.portability_outlier_replication.json
# Execute the ONE replication campaign (requires cooled 03 + gate open + the image's manifest sha).
export WS2_MATRIX_IMPL_READY=1
export OW_ARTIFACT_MANIFEST_SHA256='<sha256 of the replication image-baked artifacts.json>'
bash 05_full_matrix.sh --matrix ./matrix.portability_outlier_replication.json
```

## What is committed vs machine-local

Committed (shipped from WK1): the single-batch `matrix.portability.json` (the formal
execution unit) plus the four `matrix.portability.m*.json` readable fragments, the 36
frozen delivery-plan CSVs + `portability_freeze_report.json`, the extended pin
`config/artifacts.native_ycsb.json`, the runtime/builder/WS2 changes, and this
doc; **the portability-EXTENSION artifacts**: `matrix.portability_ext.json`, the 63
ext delivery-plan CSVs + native-source copies + `portability_ext_freeze_report.json` +
its `PROVENANCE.md`, and `test_portability_ext.py`; **and the portability-FULL-CLOSURE
artifacts**: `matrix.portability_full_closure.json`, the 37 closure delivery-plan CSVs +
native-source copies + `portability_full_closure_freeze_report.json`, and
`test_portability_full_closure.py`. Machine-local (git-ignored,
regenerated on WK2): `config/artifacts.json`, `ws2/_image_stage/`, `ws2/_runs/**`.
