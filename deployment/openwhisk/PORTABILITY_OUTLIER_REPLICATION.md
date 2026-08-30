# Portability — OUTLIER-REPLICATION (pre-registered stability / confound check)

> This is a **stability / confound check**, NOT new coverage and NOT a sixth pooled
> performance estimator. It re-runs, under strict conditions, the six
> `(workload, strategy)` cells whose original OpenWhisk↔workstation first-query
> effectiveness discrepancy was largest, to decide whether each discrepancy is a
> **stable deployment effect** or an **artifact** of low n / position imbalance /
> short-lived execution state. **This file is written before any replication evidence
> exists** — the interpretation rules below are fixed in advance so no cell can be
> classified post-hoc by whichever batch looks better.

## Why these six cells (and only these six)

Effectiveness is the relative first-query reduction against the same-condition
baseline, `R = (baseline_fq − target_fq) / baseline_fq`; only this *relative* quantity
is cross-machine comparable (absolute microseconds across the ~4 machine states and the
OpenWhisk container are **not** hardware-equivalent and are never compared as such). The
original five-campaign comparison (`analysis/comparison/effectiveness_ow_vs_workstation.csv`)
found the strategy ranking ports well overall, but six cells disagreed the most between
the workstation and OpenWhisk:

| cell | family | workstation `R_ws` direction | original OpenWhisk `R_ow` direction | why suspicious |
|---|---|---|---|---|
| `C / layers_92` | ① sign-flip | positive (effective) | negative | true sign flip |
| `C / 2d` | ① sign-flip | positive | negative | true sign flip |
| `C_hit / 2e_K40` | ① sign-flip | positive | negative | true sign flip, low n |
| `C / layers_5` | ① WS-neutral, OW negative | ~neutral | strongly negative | OW anomaly despite neutral WS |
| `YCh01 / layers_5` | ② WS-neutral, OW positive | ~neutral | positive | OW-only positive |
| `YCu / layers_5` | ② WS-neutral, OW positive | ~neutral | positive | OW-only positive |

All six are already members of the frozen **65-cell** canonical portability matrix, so
**this campaign adds ZERO coverage — coverage stays 65/65** — and it **reuses every
plan / strategy / DB / trace / action / runtime byte-for-byte** (0 new keyed plans, 0 new
markers). No category-③ (agreement) cells are included; adding well-behaved cells would
not test the confound and would only dilute the check.

## What the original discrepancies could be — and what this controls

The five prior campaigns assigned each pair's baseline/target execution order by an
independent per-pair hash coin-flip. For small per-cell n that produced lopsided splits
(e.g. 0/3, 1/2, 2/7 baseline-first/target-first). Because the first arm of a cold-gated
pair can carry page-cache / execution state that the second arm does not, a lopsided
split can *manufacture* an apparent effectiveness gap that is really a **position
artifact**, not a deployment effect. The replication removes exactly that confound:

- **Exact position balance (hard gate).** `position_balance: "exact"`: the scheduler
  ranks each cell's repetitions by `sha256(seed|cell|rep)` and assigns the lower half
  baseline-first and the upper half target-first, guaranteeing **exactly `reps/2` each**;
  the validator fails closed unless every cell is `baseline_first == target_first`
  (**10/10** for each of the five single/static cells, **3/3** for each `C_hit/2e_K40`
  seed). This is deterministic, not a reliance on random ordering coming out even.
- **Standalone handles only.** Every replication pair is standalone (cold container), so
  the check isolates the cold, deployment-relevant path and does not mix in warm-process
  keep-alive numbers.
- **More pairs per cell.** 20 pairs for each single/static cell (vs the handful in the
  original batch); `C_hit/2e_K40` gets seeds 1, 2, 3 × 6 pairs = 18 to probe seed
  sensitivity.

**Semantics are held fixed.** Same bound `test.db`, same traces, same action, same
strategy selections, same cold-reset/oracle/handle semantics as the original runs.
Strategy semantics are **not** modified to make the batches agree. `C_hit/2e_K40` reuses
the audited full-closure keyed plans (seeds 1, 2, 3); `layers_92`, `2d`, `layers_5` reuse
committed static strategy artifacts. The only genuinely-new mechanism is the exact
position-balance scheduler flag, which is opt-in and leaves the five frozen (flagless)
matrices byte-identical.

## Replication design (one campaign, four blocks, 118 pairs / 236 invocations)

| block | workload | targets (paired against `baseline`) | seeds | reps/cell | AB / BA per cell | pairs | invocations |
|---|---|---|---|---:|---|---:|---:|
| R1 | `C` (read_tail_mixed_20k) | `layers_92`, `2d`, `layers_5` | 1 | 20 | 10 / 10 | 60 | 120 |
| R2 | `YCh01` (native_ycsb_c_hot_hashed_01) | `layers_5` | 1 | 20 | 10 / 10 | 20 | 40 |
| R3 | `YCu` (native_ycsb_c_read_uniform) | `layers_5` | 1 | 20 | 10 / 10 | 20 | 40 |
| R4 | `C_hit` (read_tail_hit_20k) | `2e_K40` | 1, 2, 3 | 6 | 3 / 3 | 18 | 36 |
| **campaign** | | | | | | **118** | **236** |

Independent identity (does not touch the five prior campaigns):

| identity | value |
|---|---|
| run_config `portability_outlier_replication_run_config_sha256` | `a564770a…` |
| `schedule_seed` | `20260830` |
| matrix | `ws2/matrix.portability_outlier_replication.json` |

## Pre-registered interpretation rules (fixed BEFORE evidence)

Bands come from the existing comparison framework — **no new significance test, no
p-values**, only descriptive bands over the balanced pairs:

- `NEUTRAL_BAND = 0.10` — `|R_ow| < 0.10` is "near zero / neutral".
- `SIGN_AGREE_BAND = 0.60` — if fewer than 60% of a cell's balanced replication pairs
  share the sign of the cell median, the cell is **unstable** (a variability descriptor,
  not a significance claim).

The analysis (`analysis/analyze_outlier_replication.py`) reports **both** the original
`R_ow` and the replication `R_ow` side by side — this campaign's own artifact **never
replaces** the original value in place — and classifies each cell:

**Family ① — true sign-flip cells** (`C/layers_92`, `C/2d`, `C_hit/2e_K40`):
- replication `R_ow ≤ −0.10` and stable → **A. replicated deployment divergence**
  (the strategy really is counter-effective on OpenWhisk for this cell).
- replication `R_ow ≥ +0.10` and stable → **B. original batch likely
  position/state-confounded** (balancing position recovered the workstation direction).
- unstable (sign-agreement < 0.60) or near-zero → **C. execution-sensitive / unstable**
  (the effect is not a robust deployment property).

**`C/layers_5`** (WS-neutral, original OW strongly negative):
- `R_ow ≤ −0.10` and stable → **A. replicated OW-side anomaly despite WS-neutral behavior**.
- near-zero or unstable → **B. original negative effect likely batch/state-sensitive**.

**`YCh01/layers_5` & `YCu/layers_5`** (WS-neutral, original OW positive):
- `R_ow ≥ +0.10` and stable → **A. deployment-specific amplification of a WS-neutral strategy**.
- near-zero or unstable → **B. prior discrepancy likely batch/state-sensitive**.

There is **no post-hoc selection** of whichever batch looks better: every cell is
reported with both `R_ow` values, the original and replication position splits, the
replication sign-agreement fraction, and its pre-registered class.

> **One-time revised freeze (revision `ow-eff-revision-2026-08-30`).** This campaign's own
> artifact keeps the side-by-side format above. Separately — as a single, pre-registered,
> deliberate revision of the *paper-facing* frozen comparison table — five of these balanced
> cells (`C/layers_92`, `C/2d`, `C_hit/2e_K40`, `C/layers_5`, `YCu/layers_5`) are ADOPTED as
> the authoritative per-cell estimate in
> `analysis/comparison/effectiveness_ow_vs_workstation_revised_freeze.csv`. (The `YCh01/layers_5`
> cell listed above is superseded there by the **seventh** campaign, not this sixth one, per
> precedence seventh > sixth > historical.) The historical table is preserved byte-identically
> (`effectiveness_ow_vs_workstation_historical_freeze.csv`) and every superseded cell is recorded
> in `effectiveness_freeze_revision.json`; coverage stays 65/65 and the campaigns are still
> never pooled. The pre-registered class labels above are unchanged by the revision.

## What this campaign does NOT do

- It does **not** change the 65/65 coverage claim or the 5376/2688 five-campaign
  accounting; those hold until replication evidence exists and even then this batch is
  reported **separately**, never pooled into a sixth performance estimator.
- It does **not** modify any of the five frozen campaign identities (primary
  `022fbeb0…`, secondary `441609e6…`, portability `64f44c3e…`, portability_ext
  `bf504a28…`, portability_full_closure `a5be8f15…`) — the pin writer re-asserts all
  five byte-unchanged.
- It does **not** re-interpret OpenWhisk as primary performance evidence; warm paired
  first-query is not a strategy-performance estimate, and absolute OW vs workstation
  microseconds are never compared as hardware-equivalent.

## Run (WK2 — this WK1 prep does NOT invoke OpenWhisk)

```bash
cd deployment/openwhisk/ws2
bash 05_full_matrix.sh --matrix ./matrix.portability_outlier_replication.json
```

Then normalize the archived evidence into
`analysis/normalized/portability_outlier_replication/portability_outlier_replication_normalized_pairs.csv`
and run:

```bash
/home/u03/.cache/coldstart-venv/bin/python \
  deployment/openwhisk/analysis/analyze_outlier_replication.py
```

which writes `analysis/comparison/outlier_replication_report.csv` (both batches per
cell + classification). Until that evidence file exists the analysis **fails closed**
and writes no rows.
