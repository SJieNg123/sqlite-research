# Keyed native provenance (YCSB-C, seeds 1..10)

This directory holds the durable native sources of record for the keyed
per-(workload,seed) OpenWhisk delivery plans (`2e_K10`, `2f_slru`, and the batch-3
secondary set `2e_K500`, `leaf_freq_K10`, `leaf_rand_K10`, `2f_top102`,
`learned_markov_102`). The runtime
never reads these sources or the fork — only the frozen delivery plans one
directory up, validated against the manifest and the replay pin.

# 2e_K10 native provenance

The `2e_K10_native_ycsb_c_read_zipf_seed{N}.csv` files one directory up are the
frozen OpenWhisk **delivery plans** for the `2e_K10` strategy on the canonical
workload `native_ycsb_c_read_zipf` (YCSB-C). Each is a strict `page_number,file_offset`
plan of the 102 pages the action delivers before the measured first query:
the resident 92-interior 2d skeleton UNION the top-10 hot leaf pages.

`2e_K10` (`hot2e`, K=10) is workload/seed dependent: the interior half is fixed
(the 92-page skeleton, identical across seeds), but the 10 hot leaves are selected
per seed from that seed's access trace. These plans are **derived, never regenerated
on WS2** — the image bakes them and the runtime replays the exact bytes.

## Canonical native source (research method of record)

The plans were derived from `run_experiment.py`'s `hot2e` kind output —
`strategies/access/runs/hot2e_YC_orig_K10_seed{N}.csv` (`page_number,is_resident`,
`is_resident=1` marks selection) — produced in the working fork
`/home/u03/sqlite-research-fork` (branch `ycsb-reproduction-clean`), which uses the
byte-identical `test.db` (sha `2504a6b1…`) and page classifier (sha `6ec6837d…`) as
this repo's frozen replay pin. The derivation asserted, per seed: exactly 102
selected pages, the interior half equal (set equality) to the committed 92-page
skeleton `deployment/openwhisk/config/plans/interior_pages.csv`, and exactly 10 leaf
pages disjoint from the skeleton.

### Per-seed native source SHA256

| seed | native hot2e source                                   | source sha256    | keyed plan sha256 |
|------|-------------------------------------------------------|------------------|-------------------|
| 1    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 2    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 3    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 4    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 5    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 6    | keyed/native_source/hot2e_YC_orig_K10_seed6.csv       | `94da1e7f…b741`  | `6f123144…a77b`   |
| 7    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 8    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 9    | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |
| 10   | strategies/access/runs/hot2e_YC_orig_K10.csv          | `e4d3390e…f102`  | `453e0546…1400`   |

## Seed identity: 9 common + seed 6

For seeds 1–5,7–10 the native selection is **byte-identical** to this repo's already
committed unseeded master `strategies/access/runs/hot2e_YC_orig_K10.csv`
(sha `e4d3390e…f102`) — and to the fork's own per-seed files, which are byte-identical
to that master. Their derived delivery plans therefore share one sha
(`453e0546…1400`). That in-repo master is the durable native reference for those nine.

**Seed 6 is the sole per-seed divergence.** Its hot-leaf set swaps page `24837`
(common) for page `18314`, so its native source is not covered by the in-repo master.
The fork's `hot2e_YC_orig_K10_seed6.csv` (sha `94da1e7f…b741`) is therefore committed
here, at `hot2e_YC_orig_K10_seed6.csv`, as the durable native source of record for
seed 6. Its derived plan sha is `6f123144…a77b`.

These committed native sources back the native-parity test (all 10 seeds: frozen
delivery plan selection == native `is_resident=1` selection, exact set equality).

# 2f_slru native provenance (second keyed consumer)

The `2f_slru_native_ycsb_c_read_zipf_seed{N}.csv` files one directory up are the
frozen OpenWhisk **delivery plans** for the `2f_slru` strategy (SLRU: the entire
resident working set for the given workload+seed, delivered via MADV_WILLNEED
before the measured first query — a first-query foil). Each is a strict
`page_number,file_offset` plan of every page the seed's SLRU run marked resident.

Unlike 2e_K10 (a fixed 102 = 92-interior ∪ 10-leaf), **2f_slru's footprint varies
by seed**: the interior half is always the same 92-page skeleton (set equality),
but the resident leaf count differs per seed, so the total and leaf counts are
**per-seed data, not universal invariants** (seed 8 happens to be the whole DB).

## Canonical native source (research method of record)

Derived from `run_experiment.py`'s `slru` kind output —
`strategies/slru/runs/hotpages_yc_seed{N}.csv` (`page_number,is_resident`,
`is_resident=1` marks residency) — produced in the working fork
`/home/u03/sqlite-research-fork` (branch `ycsb-reproduction-clean`), byte-identical
`test.db` (sha `2504a6b1…`) and classifier (sha `6ec6837d…`) as this repo's replay
pin. The in-repo tree carries only the unseeded `strategies/slru/runs/hotpages_yc.csv`
(whole DB); the per-seed native sources are fork-only, so **all ten** are committed
here under `hotpages_yc_seed{N}.csv` as durable sources of record (no seed shares a
master — each is committed explicitly).

### Per-seed 2f_slru footprints + SHA256

| seed | resident (total) | interior | leaf  | native source (this dir)   | plan sha256      |
|------|------------------|----------|-------|----------------------------|------------------|
| 1    | 26325            | 92       | 26233 | hotpages_yc_seed1.csv      | `4144fd36…c6d1`  |
| 2    | 26326            | 92       | 26234 | hotpages_yc_seed2.csv      | `fc125651…7dee`  |
| 3    | 26327            | 92       | 26235 | hotpages_yc_seed3.csv      | `2ce1f428…d8b3`  |
| 4    | 26329            | 92       | 26237 | hotpages_yc_seed4.csv      | `7f36b163…a067`  |
| 5    | 26328            | 92       | 26236 | hotpages_yc_seed5.csv      | `93ae0b33…8e96`  |
| 6    | 26323            | 92       | 26231 | hotpages_yc_seed6.csv      | `55f2c8f6…83db`  |
| 7    | 26328            | 92       | 26236 | hotpages_yc_seed7.csv      | `69384519…48a1`  |
| 8    | 26331 (whole DB) | 92       | 26239 | hotpages_yc_seed8.csv      | `df5cdb85…7abd`  |
| 9    | 26327            | 92       | 26235 | hotpages_yc_seed9.csv      | `b12c1534…c68d`  |
| 10   | 26329            | 92       | 26237 | hotpages_yc_seed10.csv     | `7501acd9…8d4f`  |

All ten plan SHAs are distinct and all ten native-source SHAs are distinct — the
resident set genuinely differs per seed. The interior half equals the committed
92-page skeleton for every seed (set equality); the leaf half is `total − 92`.

These committed native sources back the 2f_slru native-parity test (all 10 seeds:
frozen delivery plan selection == native `is_resident=1` selection, exact set
equality; exact per-seed total/interior/leaf/offsets). The runtime never reads any
native source or the fork — only the frozen delivery plans, validated against the
manifest and the replay pin.

# YC secondary strategies (batch 3): 2e_K500, leaf_freq_K10, leaf_rand_K10, 2f_top102, learned_markov_102

These five keyed strategies characterize the **mechanism space** around the
`2e_K10` headline on the same canonical workload `native_ycsb_c_read_zipf`
(YCSB-C), seeds 1..10. Like `2e_K10`/`2f_slru` they are keyed per (workload,seed),
their delivery plans are **derived, never regenerated on WS2**, and the runtime
replays the exact frozen bytes one directory up. They are deployment/feasibility +
footprint/qualitative evidence, **not** headline warm-latency claims. All were
derived read-only against the working fork's byte-identical `test.db`
(sha `2504a6b1…`) and page classifier (sha `6ec6837d…`) — the same frozen
inputs as this repo's replay pin.

## N_YC = 102 = 92 interior + 10 leaf (frozen budget)

`2f_top102` and `learned_markov_102` are the **total-page-budget-matched**
competitors to `2e_K10`. The budget `N_YC = 102` is taken directly from the
`2e_K10` artifact (`hot2e_YC_orig_K10`: the 92-page interior 2d skeleton ∪ the
top-10 hot leaves = 102 pages). Budget = **exactly 102**, no approximation.

## Three gate classes (why the interior half is enforced for some, recorded for others)

- `2e_K500` keeps the 2d skeleton → **enforce** `interior == 92` with set
  equality against `interior_pages.csv`, plus up to 500 hot leaves per seed.
- `leaf_freq_K10` / `leaf_rand_K10` are leaf-only → **enforce** `interior == 0`,
  `total == 10`.
- `2f_top102` / `learned_markov_102` rank by frequency / transition score with **no
  page-type knowledge**. Forcing the 92-skeleton set-equality would inject the very
  page-type structure they are defined to lack, so their interior/leaf split is
  **recorded, not enforced**; only `total == 102` is enforced.

## Emergent 51 interior / 51 leaf split (a finding, not an assumption)

Across **all 10 seeds**, both `2f_top102` and `learned_markov_102` land on exactly
**51 interior + 51 leaf** (not 92+10). Had the 92-skeleton set-equality been forced
on them, all 20 plans would have failed closed — which is precisely why their gate
class records the split rather than enforcing it. The manifest marker stores the
per-seed emergent interior/leaf counts; the runtime validates against those recorded
values, never against a hard-coded 92.

## 2e_K500 (`hot2e`, K=500)

Deep-leaf-union foil: the 92-page skeleton ∪ up to the top-500 hot leaves for the
seed. Interior is the fixed skeleton (set equality); the leaf half is 500 for every
seed here (each seed's trace exposes ≥500 distinct hot leaves), so total = 592.
Native sources are per-seed and committed in this directory
(`hot2e_YC_orig_K500_seed{N}.csv`). Generator (per seed, in the fork):

```
python strategies/access/runs/gen_hotleaves.py test.db classify_before.csv \
  <hotpages_yc_seed{N}.csv> workloads_refined/traces/seeds/workload_YC_{N}.txt \
  500 hot2e_YC_orig_K500_seed{N}.csv
```

| seed | native source | source sha256 | total | int | leaf | plan sha256 |
|------|---------------|---------------|-------|-----|------|-------------|
| 1 | hot2e_YC_orig_K500_seed1.csv | `b3954880…2a53` | 592 | 92 | 500 | `30fad9d5…44f0` |
| 2 | hot2e_YC_orig_K500_seed2.csv | `30063f42…d639` | 592 | 92 | 500 | `8ca95247…dc3c` |
| 3 | hot2e_YC_orig_K500_seed3.csv | `1446997a…c647` | 592 | 92 | 500 | `04b215c1…6674` |
| 4 | hot2e_YC_orig_K500_seed4.csv | `0226e84c…bbd0` | 592 | 92 | 500 | `5ab52a8b…0795` |
| 5 | hot2e_YC_orig_K500_seed5.csv | `2cdb7f02…744f` | 592 | 92 | 500 | `e84ffd66…ba2e` |
| 6 | hot2e_YC_orig_K500_seed6.csv | `e5e78975…8568` | 592 | 92 | 500 | `aced57c1…aebf` |
| 7 | hot2e_YC_orig_K500_seed7.csv | `23acb7b7…b871` | 592 | 92 | 500 | `17608594…45fe` |
| 8 | hot2e_YC_orig_K500_seed8.csv | `03f93d09…44e9` | 592 | 92 | 500 | `0e4d779c…9d61` |
| 9 | hot2e_YC_orig_K500_seed9.csv | `76280c10…fd73` | 592 | 92 | 500 | `aad0bd0b…9945` |
| 10 | hot2e_YC_orig_K500_seed10.csv | `01b5c845…e30d` | 592 | 92 | 500 | `d7be75e4…062c` |

## leaf_freq_K10 (leaf-only, frequency)

The 10 hot leaves alone — the non-interior (`is_resident=1`, not in the 92-skeleton)
pages of the `2e_K10` native source. This isolates the leaf contribution from the
interior skeleton (the `leaf_freq` arm of the leaf-vs-random ablation). No new native
file: the source of record is the committed `2e_K10` native source (the in-repo
master `strategies/access/runs/hot2e_YC_orig_K10.csv` for the nine common seeds, and
`hot2e_YC_orig_K10_seed6.csv` for seed 6). Derivation (matches
`run_experiment_ycsb.select_pages` `leaf_freq`): `{ pn in resident(hot2e) :
not is_interior(pn) }`. The nine common seeds share one plan sha; seed 6 differs
(its hot-leaf set swaps page 24837 for 18314).

| seed | native source | source sha256 | total | int | leaf | plan sha256 |
|------|---------------|---------------|-------|-----|------|-------------|
| 1 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 2 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 3 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 4 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 5 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 6 | hot2e_YC_orig_K10_seed6.csv | `94da1e7f…b741` | 10 | 0 | 10 | `7cb2c43a…12eb` |
| 7 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 8 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 9 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |
| 10 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `99c5488a…d21d` |

## leaf_rand_K10 (leaf-only, random control)

The random control for `leaf_freq_K10`: 10 leaves drawn from the non-hot leaf pool of
the same page-types as the hot leaves, via the exact seeded RNG of
`run_experiment_ycsb.select_pages` `leaf_rand`:
`random.Random(f"leafrand|{seed}|YC|orig|10")` over
`sorted(pn for pn,(type,_) in classify if type in hot_leaf_types and pn not in hot_leaves)`.
The `2e_K10` native source is the provenance anchor (it defines the hot-leaf set to
exclude); the selected pages come from the seeded draw, so **all 10 plan SHAs are
distinct**.

| seed | native source | source sha256 | total | int | leaf | plan sha256 |
|------|---------------|---------------|-------|-----|------|-------------|
| 1 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `26c50765…acff` |
| 2 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `f279b409…c7f6` |
| 3 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `3a87b71b…797e` |
| 4 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `fb91f001…ecb7` |
| 5 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `e1e4998d…0763` |
| 6 | hot2e_YC_orig_K10_seed6.csv | `94da1e7f…b741` | 10 | 0 | 10 | `7a5670fc…9fdd` |
| 7 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `a863cc8d…eeff` |
| 8 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `fa5d1093…3d5f` |
| 9 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `23ef25cb…12d3` |
| 10 | strategies/access/runs/hot2e_YC_orig_K10.csv | `e4d3390e…f102` | 10 | 0 | 10 | `547751fb…b9ea` |

## 2f_top102 (`freqdump`, N=102)

Budget-matched ranked partial dump: the top-102 pages by access frequency from the
seed's already-committed SLRU residency — **no page-type intelligence**, no new DB
residency measurement. Native sources committed here
(`freqdump_YC_orig_N102_seed{N}.csv`). Generator (per seed, in the fork):

```
python strategies/access/runs/gen_freqdump.py test.db classify_before.csv \
  <hotpages_yc_seed{N}.csv> workloads_refined/traces/seeds/workload_YC_{N}.txt \
  102 freqdump_YC_orig_N102_seed{N}.csv
```

| seed | native source | source sha256 | total | int | leaf | plan sha256 |
|------|---------------|---------------|-------|-----|------|-------------|
| 1 | freqdump_YC_orig_N102_seed1.csv | `78870bf6…ece7` | 102 | 51 | 51 | `33a99f2b…3b5b` |
| 2 | freqdump_YC_orig_N102_seed2.csv | `53b265f6…1589` | 102 | 51 | 51 | `cc6891f4…fa6f` |
| 3 | freqdump_YC_orig_N102_seed3.csv | `298fe509…322a` | 102 | 51 | 51 | `f1bc4c5a…d2ef` |
| 4 | freqdump_YC_orig_N102_seed4.csv | `35828a7b…91be` | 102 | 51 | 51 | `3a6d4ba8…9e92` |
| 5 | freqdump_YC_orig_N102_seed5.csv | `bd44ef14…b800` | 102 | 51 | 51 | `34bac36a…1ece` |
| 6 | freqdump_YC_orig_N102_seed6.csv | `14f7d42b…621d` | 102 | 51 | 51 | `75d1582d…e1f7` |
| 7 | freqdump_YC_orig_N102_seed7.csv | `fff42c49…f223` | 102 | 51 | 51 | `fb674cea…a2d6` |
| 8 | freqdump_YC_orig_N102_seed8.csv | `fbeb6fb0…b984` | 102 | 51 | 51 | `a4cbeba6…5e3d` |
| 9 | freqdump_YC_orig_N102_seed9.csv | `982ee2e2…75c2` | 102 | 51 | 51 | `cb9c7684…d6a5` |
| 10 | freqdump_YC_orig_N102_seed10.csv | `522f4a55…7cba` | 102 | 51 | 51 | `46b3c02d…031c` |

## learned_markov_102 (`learned_markov`, N=102, LOSO)

Budget-matched held-out transition model: a first-order Markov model trained on the
other 9 seeds (leave-one-seed-out) and its top-102 hotset taken for the held-out test
seed, trained/tested on the canonical read-zipf pattern. Native sources committed here
(`learned_markov_YC_orig_N102_test{N}.csv` + `.meta.json`). Generator (per test seed
T, in the fork):

```
python strategies/learned/train_markov.py --db test.db --classify classify_before.csv \
  --w YC --layout orig --test-seed T --train-seeds <the other 9> --budget 102 \
  --workload-pattern workloads_refined/traces/seeds/workload_YC_{s}.txt \
  --artifact-dir <scratch> --runs-dir native_source
```

The top-102 hotset is nearly **hold-out invariant**: test seeds 1–5,7–9 produce one
byte-identical N102 hotset, and test seeds 6 and 10 produce a second (identical to
each other) — so the ten plans collapse to two distinct SHAs. The interior/leaf split
is the same emergent 51/51 for every seed.

| seed | native source | source sha256 | total | int | leaf | plan sha256 |
|------|---------------|---------------|-------|-----|------|-------------|
| 1 | learned_markov_YC_orig_N102_test1.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 2 | learned_markov_YC_orig_N102_test2.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 3 | learned_markov_YC_orig_N102_test3.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 4 | learned_markov_YC_orig_N102_test4.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 5 | learned_markov_YC_orig_N102_test5.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 6 | learned_markov_YC_orig_N102_test6.csv | `d103576f…9024` | 102 | 51 | 51 | `db1a98d5…e1d6` |
| 7 | learned_markov_YC_orig_N102_test7.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 8 | learned_markov_YC_orig_N102_test8.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 9 | learned_markov_YC_orig_N102_test9.csv | `d851c128…f44e` | 102 | 51 | 51 | `7776a336…34ba` |
| 10 | learned_markov_YC_orig_N102_test10.csv | `d103576f…9024` | 102 | 51 | 51 | `db1a98d5…e1d6` |

These committed native sources back the secondary native-parity test (all 5
strategies × 10 seeds: frozen delivery plan selection == native selection with exact
per-seed total/interior/leaf/offsets; `2f_top102`/`learned_markov_102` gated on
`total == 102` with the emergent split recorded; `leaf_*` gated on `total == 10`,
`interior == 0`). The runtime never reads any native source or the fork — only the
frozen delivery plans, validated against the manifest and the replay pin.
