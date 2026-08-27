# OpenWhisk Cross-Workload Portability Campaign — Evidence Audit

**Scope.** Independent verification of the completed single-batch OpenWhisk
portability campaign transferred back to WK1. This audit validates *deployment
execution, correctness, workload binding, plan binding, semantic parity,
selected-page footprint, and cost observability*. It does **not** assert latency
agreement, ranking equality, or warm paired speedup. Native/WK1 remains the
primary controlled performance evidence; OpenWhisk is the deployment complement.

**Verdict: ALL GATES PASS. No discrepancies.**

## Authoritative identities

| Identity | Value |
|---|---|
| Evidence bundle | `deployment/openwhisk/evidence/portability/29e1585ce956/ws2_bundle_29e1585ce956_20260827T135734Z.tar.gz` |
| Bundle SHA256 | `a7c9736cc65e29eff7700f2979abb4f5313d3d41c569a1120ccd1e22a28ac7a2` (computed == sidecar == expected) |
| Git SHA | `29e1585ce956d41171a4f2cadbeec76c34c22f62` (git_dirty=false) |
| Campaign | `portability`, schedule_seed `20260826` |
| Live matrix fingerprint | `a3274bc9632ab7aa393f015c00829373a33312d15ff8e6521759255f01eac10e` |
| Portability run_config | `64f44c3e06be421a026aa523ded93010d3a7d3ab8e2cf773e033ec30c0657947` |
| Artifact manifest | `0631a93799f9224a3b7913efa4e71eee3ad04c8c431dd5de1382777e9eacebfb` |
| Action image | `localhost:5000/sqlite-coldstart@sha256:cc3a665b301b1ed05a9be7ccc21e58fe3ca608eaf8483421464ba384bb8ca108` |

The WK1 placeholder fingerprint `e24da162…` (test/image identity artifact) is
**not** the live comparator and appears nowhere in the live schedule.

## Gate results

**§1 Bundle immutability — PASS.** SHA256 `a7c9736c…` matches the computed hash,
the `.sha256` sidecar, and the expected value. The archive is readable (1486
entries). Verified by streaming/temp-extraction outside the canonical evidence
path; the tarball was not modified.

**§2 Single-batch identity — PASS.** All pipeline stages report
`status=done result=PASS` with a uniform `git_sha=29e1585ce956…`. There is exactly
one **formal** campaign schedule (`05_full_matrix/schedule.json`,
`campaign=portability`, block-union structure, 468 invocations) and exactly one
live fingerprint (`a3274bc9…`), present in both the schedule and the raw
`.schedule_fingerprint` marker. The Stage-04 `schedule.json` is a 12-invocation /
6-pair feasibility pre-flight (`campaign=None`, fingerprint `ca8b432b…`) — a
distinct stage, not a second formal matrix. Recomputing the campaign fingerprint
from `(matrix, identity, invocations)` reproduces `a3274bc9…` exactly.

**§3 Matrix shape — PASS.** Exactly 468 requests and 468 responses; 234 complete
baseline–target pairs; 234 baseline + 234 target invocations. Schedule positions
are exactly 1..468. `request_id` is unique (468); no duplicate schedule_position;
no duplicate formal cell (the full per-invocation key `(pair_id, arm)` is unique
468). No missing responses, no malformed JSON, no DRY_RUN responses. Baseline
coordinate sharing (a baseline coordinate anchoring 2–5 targets) is legitimate:
each pair carries its own baseline invocation, distinguished by `pair_id`
(multiplicities 60×2 + 12×4 + 12×3 + 6×5 = 234).

**§4 Logical block counts — PASS.** BLOCK1 = 108 pairs, BLOCK2 = 72, BLOCK3 = 36,
BLOCK4 = 18 (union = 234). No unintended Cartesian cells: the forbidden cells
`2f_top28 × read_tail_mixed_20k` and `2e_K10 × native_ycsb_c_read_zipf` are both
absent, and every executed (target, workload) pair lies inside the explicit
block union.

**§5 Validity gates (all 468 responses) — PASS.** Every response satisfies
`diagnostic_mode==false`, `cold_reset_requested==true`, `cold_threshold_passed==true`,
`delivery_valid==true`, `oracle_passed==true`, `measured_valid==true`, with no
`sqlite_error`, no `error_stage`, and no top-level `error`. Request↔response
identity matches on all seven fields (`request_id`, `workload`, `strategy`, `seed`,
`handle_mode`, `first_operation_id`, `pair_id`). The action image digest, artifact
manifest hash, and run_config are constant across all 468 responses.

**§6 Run-config binding — PASS.** All 468 responses bind the portability run_config
`64f44c3e…`. The primary (`022fbeb0…`) and secondary (`441609e6…`) run_configs
are distinct and appear in no response — no identity leakage.

**§7 Plan / workload parity — PASS.** The 36 frozen keyed delivery plans were
content-hash verified: each `plan_sha256` equals `sha256` of the actual
`page_number,file_offset` delivery CSV. All 216 keyed target responses match the
frozen contract on `plan_sha256` **and** `selected_page_count` **and**
`selected_interior_count` **and** `selected_leaf_count` for their
`(strategy, workload, seed)` — because `plan_sha256` is the content hash of the
page/offset plan, a match proves the *selected page set and offset mapping*, not
merely the count. The 18 static `2d` targets (seed 1 only) carry the constant
structural skeleton plan (`37ed5e46…`, 92 interior / 0 leaf). All 234 baseline
invocations deliver zero prefetch pages (`selected_page_count == 0`). Bound DB
`2504a6b1…` and classifier `6ec6837d…` are constant.

**§8 2e_K10 provenance classification — PASS.** For C/C_hit/YCu/YCh01, `2e_K10`
plans carry `reconstructed=true`, `pages=102 (interior=92, leaf=10)`. This is the
approved **semantic/mechanism portability under the canonical 2e contract**
(92-interior skeleton ∪ per-seed top-10 leaves), classified as
`semantic_contract_reconstruction` — **not** byte-for-byte raw-native plan
replication. Provenance is not homogenized with the other strategies.

**§9 Special cells — PASS.**
- `2f_top28` (YC): exact `N=28` frozen parity plan (interior 26 / leaf 2),
  `reconstructed=false` → `exact_native_plan`.
- `learned_markov_28` (YC): exact `N=28`, LOSO clean — each test seed is excluded
  from its own `train_seeds` (seed 1 trains on 2..10, etc.). Plans for test-seeds
  1 and 2 converge to the `2f_top28` seed-3 page set (the documented
  learned≈2f-topN convergence); seed 3 is distinct.
- `leaf_freq_K10` / `leaf_rand_K10` (C): 10 leaf / 0 interior. `leaf_freq` is
  seed-stable (identical `4b2683b4…` across seeds 1–3); `leaf_rand` is
  seed-dependent (distinct sha per seed) — the expected frequency-vs-RNG contrast.
- `2f_slru`: per-workload/per-seed emergent footprint preserved and **not** forced
  to 92 interiors (interior 92/92/5/4 and pages ranging 26 296…26 328 / 916…921 /
  467…483 across YCh01/YCu/C_hit/C).
- `2d`: structural static, seed 1 only, 18 invocations, no accidental seed
  expansion.

## Portability verdict (§10)

The campaign validates, across five workload families (YC, YCu, YCh01, C, C_hit)
and representative mechanism families (interior-skeleton reconstruction, exact
ranked/leaf native plans, LOSO-learned model, full SLRU footprint, structural
static), that representative strategy mechanisms evaluated natively were
successfully **deployed and validated in OpenWhisk** with workload/plan
identities, correctness gates, selected-page footprints, and delivery
observability preserved. The pass criterion is deployment execution and
correctness — **not** latency agreement, ranking equality, warm paired speedup,
or first-arm causal estimates. Native/WK1 remains the primary controlled
performance evidence.

## Reproduction

The gate checks above are regenerated by the descriptive generator (emits
`portability_coverage.csv`, `portability_plan_parity.csv`,
`portability_workload_summary.csv`) and the portability audit tests in
`deployment/openwhisk/tests/`. Inputs: the immutable bundle
(`…29e1585ce956…tar.gz`) and the frozen keyed contract
(`config/plans/keyed/portability_freeze_report.json`).
