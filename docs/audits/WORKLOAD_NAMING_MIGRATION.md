# Workload Naming Migration (2026-07-23)

## Purpose

The workloads were originally identified by short letters (A, B, C, C\_mixed,
C\_hit, Z) and ad-hoc tags (YD, YE, CHURN). Those letters collide visually with
the *standard* YCSB core workloads A–F and invited the misreading that our
`YD`/`YE` were official YCSB-D/E traces. This migration replaces the identifiers
used in **paper-visible text, figures, captions, tables, and the OpenWhisk
config/schedule loader** with descriptive canonical IDs and display names, while
leaving all measured data and its provenance untouched.

## Canonical registry (single source of truth)

`config/workloads.json`, loaded via `config/workload_registry.py`
(`normalize_workload_id()`, `workload_display_name()`). Every consumer resolves
names through this registry instead of hard-coding the mapping.

| legacy ID(s) | canonical ID | display name | role |
|---|---|---|---|
| A | `read_zipf_scattered_100k` | Scattered-Zipf | controlled read |
| B | `read_uniform_100k` | Uniform-100K | controlled read |
| C, C\_mixed | `read_tail_mixed_20k` | Tail-Mixed | controlled read (~50% not-found, right-boundary probe) |
| C\_hit | `read_tail_hit_20k` | Tail-Hit | controlled read (pure-hit control; removes not-found effect) |
| Z | `read_zipf_concentrated_1k` | Concentrated-Zipf | controlled read (figures only) |
| YD | `py_ycsb_d_latest_aging` | Latest-Aging | deterministic Python reconstruction of YCSB-D semantics |
| YE | `py_ycsb_e_short_scan_aging` | Short-Scan Aging | deterministic Python reconstruction of YCSB-E semantics |
| CHURN (paper "workload D") | `mutation_churn_schedule` | Mixed-Mutation Churn | **mutation schedule, not a measured workload** |

## Immutability guarantee (what did NOT change)

- **No results CSV `workload` column was rewritten.** All files under
  `results/**` keep their legacy IDs (`workload=A/B/C/C_mixed/C_hit/...`).
- **No raw or uncertainty data changed.** No benchmark or OpenWhisk run was
  executed as part of this migration.
- **The atomic verifier still keys on legacy IDs.**
  `tools/verify_paper_atomicity.py` and
  `docs/audits/PAPER_CLAIM_MANIFEST.csv` retain legacy IDs in their
  machine-checked columns (`source_filter=workload=A/B/C`, the `workload`
  column, the `CHANGED`/`CHIT_CORRECTED` constants, and the `C_hit` rule). These
  map directly onto the immutable results CSVs and must not be renamed. The
  manifest gained a **read-only `display_name` column** (derived from the
  registry) for human traceability; every pre-existing column is byte-for-byte
  identical and the verifier still exits 0 (132 claims, 0 FAIL).

Names are therefore normalized **for presentation only**; the data layer is
frozen and the registry bridges legacy ↔ canonical ↔ display on read.

## Changed artifacts

- **Paper** (`paper/main.tex`, submodule commit *"paper: adopt descriptive
  workload names"*): first-occurrence legacy annotations
  (e.g. "Scattered-Zipf (legacy workload A)"), display names throughout body /
  tables / captions, explicit classification (controlled reads vs YCSB
  reconstructions vs mutation schedule), and CHURN reclassified from an
  evaluation "workload D" to a mutation schedule. Tail-Mixed keeps its ~50%
  not-found / right-boundary annotation; Tail-Hit keeps its "control that
  removes the not-found effect" annotation.
- **Figures** 13/14/16/17 resolve titles via
  `figures/plot_utils.py:workload_display_name`; CSV reads stay legacy. Pure
  label regeneration (bar values / CI / ordering / sources unchanged); new md5s
  recorded in [`../figures/FIGURE_SOURCE_MAP.md`](../figures/FIGURE_SOURCE_MAP.md),
  root `figures/out/*.png` byte-identical to `paper/figures/*.png`.
- **OpenWhisk** `deployment/openwhisk/client/build_schedule.py` normalizes
  `--workloads` through the registry (accepts legacy aliases, records canonical
  IDs); default and `config/example.json` now use `read_zipf_scattered_100k`.
  All 73 deployment unit tests pass.

## Verification

- `python3 config/workload_registry.py --selftest` → PASS (both system and venv python).
- `python3 tools/verify_paper_atomicity.py --manifest docs/audits/PAPER_CLAIM_MANIFEST.csv` → exit 0, 132 claims, 0 FAIL.
- `python3 -m unittest discover deployment/openwhisk/tests` → 73 tests OK.
- No file under `results/**` modified (verified via `git status`).
