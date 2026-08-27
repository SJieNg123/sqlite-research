# Portability-EXTENSION keyed native provenance

This directory holds the durable native sources of record for the **63 keyed
portability-EXTENSION delivery plans** (21 keyed `(workload, strategy)` cells × seeds
1–3). The ext campaign carries the remaining workstation-proven strategies onto
OpenWhisk under a fourth, INDEPENDENT run-config identity
`portability_ext_run_config_sha256` = `bf504a28…` (schedule_seed `20260828`, 426 pairs /
852 invocations), distinct from and additive to the byte-frozen primary (`022fbeb0…`),
secondary (`441609e6…`), and portability (`64f44c3e…`) identities.

Like every keyed layer, these are **deployment/feasibility + relative-effectiveness**
evidence only: warm paired first-query latency is NOT a strategy-performance estimate
(page-cache carryover was falsified; the effect is positional/order —
`analysis/thesis/threats_to_validity.md`). The runtime never reads these native sources
or the fork — only the frozen delivery plans one directory up, validated against the
manifest and the replay pin.

## Bound inputs (identical to every other keyed layer)

All 63 plans were derived read-only against the byte-identical `test.db`
(sha `2504a6b1…`) and page classifier (sha `6ec6837d…`) — the same frozen inputs as
this repo's replay pin — over the committed 92-page interior skeleton
`deployment/openwhisk/config/plans/interior_pages.csv`.

## Source-of-record vs byproduct (a provenance nuance surfaced, not hidden)

Two origin classes feed the freeze; **durability is always via the committed frozen
copy + SHA in this directory**, regardless of origin:

- **SoR (git-tracked source of record):** all `learned_markov_*` cells and the C / C_hit
  `2f_top14`/`2f_top28`/`2e_K500` cells originate in `strategies/access/runs/` — durable,
  version-controlled research artifacts.
- **byproduct (gitignored results batch):** the YC / YCu / YCh01
  `2f_top14`/`2f_top28`/`2e_K500` cells originate only as gitignored head-to-head results
  hotsets (`results/native_headtohead{,_YCu,_YCh01}/seed{N}/main/work/hotset_*.csv`; the
  SoR carries aggregate-only). The origin is a byproduct; the **frozen copy here + its
  recorded SHA are the durable record**, exactly as the existing portability freeze
  captures its byproduct native sources.

For C `2e_K500` the canonical **post-tie-break-fix** source of record
`strategies/access/runs/hot2e_C_orig_K500_seed{1,2,3}.csv` was used (never the pre-fix
`results/{seeds,unified_v2,main,competitive,ablation}` batches, which are non-canonical
per REPORT §4.7).

## N-budget derivations

- **N=28** (`2f_top28`, `learned_markov_28`): the head-to-head total-page budget for these
  four workloads, applied identically to the ranked (`2f_top`) and the LOSO learned
  (`learned_markov`) competitor so the comparison is budget-controlled.
- **N=14** (`2f_top14`, `learned_markov_14`): the **half-budget sibling** of N=28 — the
  same budget-controlled pairing at half the page budget.

## Gate classes (enforced vs recorded)

- `2e_K500` keeps the 2d skeleton → **enforce** `interior == 92` (set equality against
  `interior_pages.csv`) plus up to 500 hot leaves (`leaf ≤ 500`); total = 92 + leaf.
- `2f_top14` / `2f_top28` rank by frequency with **no page-type intelligence** → only
  `total == N` is enforced; the interior/leaf split is **recorded, not enforced** (an
  emergent split — e.g. 13 interior / 1 leaf at N=14 on YC — would fail-close if the
  skeleton set-equality were forced, which is exactly why it is recorded).
- `learned_markov_14` / `learned_markov_28` are held-out (LOSO) transition models →
  `total == N` enforced, split recorded, and the `.meta.json` carries the `test_seed` /
  `train_seeds` for the leakage gate (test seed ∉ train seeds).

## learned_markov = leave-one-seed-out (LOSO)

Each `learned_markov_N{14,28}` plan for test seed *T* is the top-*N* hotset of a
first-order Markov model trained on the OTHER seeds and evaluated on *T*'s held-out trace
(keyed by test seed). The frozen `.meta.json` records `test_seed=T` and `train_seeds`
(disjoint from *T*) — the ext test's leakage gate asserts `T ∉ train_seeds`.

---

# 2f_top14 (`freqdump`, N=14) — ranked partial, all five workloads

Top-14 pages by access frequency; interior/leaf split recorded (emergent).

| workload | seed | native origin (byproduct?) | durable copy sha | plan sha | total | int | leaf |
|---|---|---|---|---|---|---|---|
| YC (read_zipf) | 1 | `hotset_YC_orig_2f_top14.csv` (byproduct) | `c4aca6e1…11b3` | `b47f4c95…b3f6` | 14 | 13 | 1 |
| YC (read_zipf) | 2 | `hotset_YC_orig_2f_top14.csv` (byproduct) | `c4aca6e1…11b3` | `b47f4c95…b3f6` | 14 | 13 | 1 |
| YC (read_zipf) | 3 | `hotset_YC_orig_2f_top14.csv` (byproduct) | `c4aca6e1…11b3` | `b47f4c95…b3f6` | 14 | 13 | 1 |
| YCu (read_uniform) | 1 | `hotset_YCu_orig_2f_top14.csv` (byproduct) | `a5660bc2…2e16` | `74b2a1b3…0aa2` | 14 | 14 | 0 |
| YCu (read_uniform) | 2 | `hotset_YCu_orig_2f_top14.csv` (byproduct) | `a5660bc2…2e16` | `74b2a1b3…0aa2` | 14 | 14 | 0 |
| YCu (read_uniform) | 3 | `hotset_YCu_orig_2f_top14.csv` (byproduct) | `a5660bc2…2e16` | `74b2a1b3…0aa2` | 14 | 14 | 0 |
| YCh01 (hot_hashed_01) | 1 | `hotset_YCh01_orig_2f_top14.csv` (byproduct) | `d9defadc…0203` | `6bc163bd…91b2` | 14 | 14 | 0 |
| YCh01 (hot_hashed_01) | 2 | `hotset_YCh01_orig_2f_top14.csv` (byproduct) | `d9defadc…0203` | `6bc163bd…91b2` | 14 | 14 | 0 |
| YCh01 (hot_hashed_01) | 3 | `hotset_YCh01_orig_2f_top14.csv` (byproduct) | `d9defadc…0203` | `6bc163bd…91b2` | 14 | 14 | 0 |
| C_hit (read_tail_hit_20k) | 1 | `freqdump_C_hit_orig_N14_seed1.csv` (SoR) | `4237d64e…a4d7` | `27ed80b0…7ab0` | 14 | 3 | 11 |
| C_hit (read_tail_hit_20k) | 2 | `freqdump_C_hit_orig_N14_seed2.csv` (SoR) | `3b9ab2fb…4f4e` | `27ed80b0…7ab0` | 14 | 3 | 11 |
| C_hit (read_tail_hit_20k) | 3 | `freqdump_C_hit_orig_N14_seed3.csv` (SoR) | `0b6ce6e5…b6dd` | `27ed80b0…7ab0` | 14 | 3 | 11 |
| C (read_tail_mixed_20k) | 1 | `freqdump_C_orig_N14_seed1.csv` (SoR) | `db030022…3f6b` | `cb5f462c…635e` | 14 | 2 | 12 |
| C (read_tail_mixed_20k) | 2 | `freqdump_C_orig_N14_seed2.csv` (SoR) | `32622129…e04f` | `cb5f462c…635e` | 14 | 2 | 12 |
| C (read_tail_mixed_20k) | 3 | `freqdump_C_orig_N14_seed3.csv` (SoR) | `fde48212…401d` | `cb5f462c…635e` | 14 | 2 | 12 |

# 2f_top28 (`freqdump`, N=28) — ranked partial, four workloads

Top-28 pages by access frequency; interior/leaf split recorded (emergent).

| workload | seed | native origin (byproduct?) | durable copy sha | plan sha | total | int | leaf |
|---|---|---|---|---|---|---|---|
| YCu (read_uniform) | 1 | `hotset_YCu_orig_2f_top28.csv` (byproduct) | `38a35feb…dec7` | `cd262561…55c4` | 28 | 28 | 0 |
| YCu (read_uniform) | 2 | `hotset_YCu_orig_2f_top28.csv` (byproduct) | `38a35feb…dec7` | `cd262561…55c4` | 28 | 28 | 0 |
| YCu (read_uniform) | 3 | `hotset_YCu_orig_2f_top28.csv` (byproduct) | `38a35feb…dec7` | `cd262561…55c4` | 28 | 28 | 0 |
| YCh01 (hot_hashed_01) | 1 | `hotset_YCh01_orig_2f_top28.csv` (byproduct) | `4f225cf1…774e` | `2666de8e…3cc6` | 28 | 28 | 0 |
| YCh01 (hot_hashed_01) | 2 | `hotset_YCh01_orig_2f_top28.csv` (byproduct) | `4f225cf1…774e` | `2666de8e…3cc6` | 28 | 28 | 0 |
| YCh01 (hot_hashed_01) | 3 | `hotset_YCh01_orig_2f_top28.csv` (byproduct) | `4f225cf1…774e` | `2666de8e…3cc6` | 28 | 28 | 0 |
| C_hit (read_tail_hit_20k) | 1 | `freqdump_C_hit_orig_N28_seed1.csv` (SoR) | `81d7c7e3…7105` | `5c4caac4…70af` | 28 | 3 | 25 |
| C_hit (read_tail_hit_20k) | 2 | `freqdump_C_hit_orig_N28_seed2.csv` (SoR) | `ab17b9b8…2489` | `5c4caac4…70af` | 28 | 3 | 25 |
| C_hit (read_tail_hit_20k) | 3 | `freqdump_C_hit_orig_N28_seed3.csv` (SoR) | `f521857d…b493` | `5c4caac4…70af` | 28 | 3 | 25 |
| C (read_tail_mixed_20k) | 1 | `freqdump_C_orig_N28_seed1.csv` (SoR) | `5f410176…4d7f` | `8ffdc0fc…dbc7` | 28 | 2 | 26 |
| C (read_tail_mixed_20k) | 2 | `freqdump_C_orig_N28_seed2.csv` (SoR) | `5d143aee…100d` | `8ffdc0fc…dbc7` | 28 | 2 | 26 |
| C (read_tail_mixed_20k) | 3 | `freqdump_C_orig_N28_seed3.csv` (SoR) | `b77748ac…28bd` | `8ffdc0fc…dbc7` | 28 | 2 | 26 |

# 2e_K500 (`hot2e`, K=500) — deep-leaf-union, four workloads

The 92-page skeleton ∪ up to the top-500 hot leaves for the seed; `interior == 92`
enforced (set equality), `leaf ≤ 500` recorded.

| workload | seed | native origin (byproduct?) | durable copy sha | plan sha | total | int | leaf |
|---|---|---|---|---|---|---|---|
| YCu (read_uniform) | 1 | `hotset_YCu_orig_2e_K500.csv` (byproduct) | `0b4676db…d7c6` | `4d19e949…4f10` | 592 | 92 | 500 |
| YCu (read_uniform) | 2 | `hotset_YCu_orig_2e_K500.csv` (byproduct) | `0b4676db…d7c6` | `4d19e949…4f10` | 592 | 92 | 500 |
| YCu (read_uniform) | 3 | `hotset_YCu_orig_2e_K500.csv` (byproduct) | `0b4676db…d7c6` | `4d19e949…4f10` | 592 | 92 | 500 |
| YCh01 (hot_hashed_01) | 1 | `hotset_YCh01_orig_2e_K500.csv` (byproduct) | `900366f3…af4e` | `8e4fde30…460b` | 592 | 92 | 500 |
| YCh01 (hot_hashed_01) | 2 | `hotset_YCh01_orig_2e_K500.csv` (byproduct) | `900366f3…af4e` | `8e4fde30…460b` | 592 | 92 | 500 |
| YCh01 (hot_hashed_01) | 3 | `hotset_YCh01_orig_2e_K500.csv` (byproduct) | `900366f3…af4e` | `8e4fde30…460b` | 592 | 92 | 500 |
| C_hit (read_tail_hit_20k) | 1 | `hot2e_C_hit_orig_K500_seed1.csv` (SoR) | `2befedb4…ee57` | `ed625bb8…a729` | 592 | 92 | 500 |
| C_hit (read_tail_hit_20k) | 2 | `hot2e_C_hit_orig_K500_seed2.csv` (SoR) | `2befedb4…ee57` | `ed625bb8…a729` | 592 | 92 | 500 |
| C_hit (read_tail_hit_20k) | 3 | `hot2e_C_hit_orig_K500_seed3.csv` (SoR) | `2befedb4…ee57` | `ed625bb8…a729` | 592 | 92 | 500 |
| C (read_tail_mixed_20k) | 1 | `hot2e_C_orig_K500_seed1.csv` (SoR) | `6f45e095…7bf8` | `54e2e421…cf0a` | 426 | 92 | 334 |
| C (read_tail_mixed_20k) | 2 | `hot2e_C_orig_K500_seed2.csv` (SoR) | `6f45e095…7bf8` | `54e2e421…cf0a` | 426 | 92 | 334 |
| C (read_tail_mixed_20k) | 3 | `hot2e_C_orig_K500_seed3.csv` (SoR) | `6f45e095…7bf8` | `54e2e421…cf0a` | 426 | 92 | 334 |

# learned_markov_14 (LOSO, N=14) — held-out transition model, four workloads

Test-seed-keyed top-14 hotset; `total == 14` enforced, split recorded, leakage gated.

| workload | seed | native origin (byproduct?) | durable copy sha | plan sha | total | int | leaf |
|---|---|---|---|---|---|---|---|
| YC (read_zipf) | 1 | `learned_markov_YC_orig_N14_test1.csv` (SoR) | `1e2903e6…af4d` | `b47f4c95…b3f6` | 14 | 13 | 1 |
| YC (read_zipf) | 2 | `learned_markov_YC_orig_N14_test2.csv` (SoR) | `1e2903e6…af4d` | `b47f4c95…b3f6` | 14 | 13 | 1 |
| YC (read_zipf) | 3 | `learned_markov_YC_orig_N14_test3.csv` (SoR) | `1e2903e6…af4d` | `b47f4c95…b3f6` | 14 | 13 | 1 |
| YCu (read_uniform) | 1 | `learned_markov_YCu_orig_N14_test1.csv` (SoR) | `68c48aff…3a2e` | `4c9c6754…01d6` | 14 | 14 | 0 |
| YCu (read_uniform) | 2 | `learned_markov_YCu_orig_N14_test2.csv` (SoR) | `c92b5aaf…f694` | `49cd0216…4957` | 14 | 14 | 0 |
| YCu (read_uniform) | 3 | `learned_markov_YCu_orig_N14_test3.csv` (SoR) | `c4a8e607…755e` | `77664f75…62bb` | 14 | 14 | 0 |
| YCh01 (hot_hashed_01) | 1 | `learned_markov_YCh01_orig_N14_test1.csv` (SoR) | `846b7fa2…b40b` | `a7cad67b…d4a9` | 14 | 14 | 0 |
| YCh01 (hot_hashed_01) | 2 | `learned_markov_YCh01_orig_N14_test2.csv` (SoR) | `846b7fa2…b40b` | `a7cad67b…d4a9` | 14 | 14 | 0 |
| YCh01 (hot_hashed_01) | 3 | `learned_markov_YCh01_orig_N14_test3.csv` (SoR) | `846b7fa2…b40b` | `a7cad67b…d4a9` | 14 | 14 | 0 |
| C_hit (read_tail_hit_20k) | 1 | `learned_markov_C_hit_orig_N14_test1.csv` (SoR) | `cf26d12b…5f57` | `27ed80b0…7ab0` | 14 | 3 | 11 |
| C_hit (read_tail_hit_20k) | 2 | `learned_markov_C_hit_orig_N14_test2.csv` (SoR) | `cf26d12b…5f57` | `27ed80b0…7ab0` | 14 | 3 | 11 |
| C_hit (read_tail_hit_20k) | 3 | `learned_markov_C_hit_orig_N14_test3.csv` (SoR) | `cf26d12b…5f57` | `27ed80b0…7ab0` | 14 | 3 | 11 |

# learned_markov_28 (LOSO, N=28) — held-out transition model, four workloads

Test-seed-keyed top-28 hotset; `total == 28` enforced, split recorded, leakage gated.

| workload | seed | native origin (byproduct?) | durable copy sha | plan sha | total | int | leaf |
|---|---|---|---|---|---|---|---|
| YCu (read_uniform) | 1 | `learned_markov_YCu_orig_N28_test1.csv` (SoR) | `36076c8b…18c8` | `211072e8…cb37` | 28 | 28 | 0 |
| YCu (read_uniform) | 2 | `learned_markov_YCu_orig_N28_test2.csv` (SoR) | `11be573b…8112` | `c4df00f2…7125` | 28 | 28 | 0 |
| YCu (read_uniform) | 3 | `learned_markov_YCu_orig_N28_test3.csv` (SoR) | `d9c05800…723f` | `23f26130…8506` | 28 | 28 | 0 |
| YCh01 (hot_hashed_01) | 1 | `learned_markov_YCh01_orig_N28_test1.csv` (SoR) | `41081610…3a28` | `4cb5ae52…b056` | 28 | 28 | 0 |
| YCh01 (hot_hashed_01) | 2 | `learned_markov_YCh01_orig_N28_test2.csv` (SoR) | `41081610…3a28` | `4cb5ae52…b056` | 28 | 28 | 0 |
| YCh01 (hot_hashed_01) | 3 | `learned_markov_YCh01_orig_N28_test3.csv` (SoR) | `41081610…3a28` | `4cb5ae52…b056` | 28 | 28 | 0 |
| C_hit (read_tail_hit_20k) | 1 | `learned_markov_C_hit_orig_N28_test1.csv` (SoR) | `56e30451…6bc2` | `5c4caac4…70af` | 28 | 3 | 25 |
| C_hit (read_tail_hit_20k) | 2 | `learned_markov_C_hit_orig_N28_test2.csv` (SoR) | `56e30451…6bc2` | `5c4caac4…70af` | 28 | 3 | 25 |
| C_hit (read_tail_hit_20k) | 3 | `learned_markov_C_hit_orig_N28_test3.csv` (SoR) | `56e30451…6bc2` | `5c4caac4…70af` | 28 | 3 | 25 |
| C (read_tail_mixed_20k) | 1 | `learned_markov_C_orig_N28_test1.csv` (SoR) | `7852ee4a…379f` | `8ffdc0fc…dbc7` | 28 | 2 | 26 |
| C (read_tail_mixed_20k) | 2 | `learned_markov_C_orig_N28_test2.csv` (SoR) | `7852ee4a…379f` | `8ffdc0fc…dbc7` | 28 | 2 | 26 |
| C (read_tail_mixed_20k) | 3 | `learned_markov_C_orig_N28_test3.csv` (SoR) | `7852ee4a…379f` | `8ffdc0fc…dbc7` | 28 | 2 | 26 |

---

# Static strategies (no per-seed native source)

The ext campaign's three cross-workload deployment checks are **inline-offset static**
strategies (workload/seed independent) — they carry NO per-seed frozen delivery plan and
have NO native source in this directory:

- **`layers_92`** — the full 92-interior skeleton (`interior_pages.csv`, same page content
  as `2d`, distinct strategy name); B9 × {YC, YCu, YCh01, C_hit}, seed 1.
- **`layers_5`** — the 5-interior prefix (`layers_5_pages.csv`); B10 × {YCu, YCh01, C},
  seed 1.
- **`2d`** — the interior skeleton selection; B11 × {C_hit}, seed 1.

Their offsets are validated in-action against the committed skeleton / prefix CSVs, not
against a frozen per-seed plan. Static blocks keep `seeds = [1]` by construction.

---

These 63 committed native sources + copies back the ext freeze-parity test
(`tests/test_portability_ext.py`): each frozen delivery plan's selection == its recorded
native selection, with exact per-cell total/interior/leaf, plan SHA, and durable
native-copy SHA; `2e_K500` gated on `interior == 92` set-equality + `leaf ≤ 500`;
`2f_top*`/`learned_markov_*` gated on `total == N` with the split recorded; LOSO leakage
gated on `test_seed ∉ train_seeds`. The runtime never reads any native source or the fork
— only the frozen delivery plans, validated against the manifest and the replay pin.
