# Keyed native provenance (YCSB-C, seeds 1..10)

This directory holds the durable native sources of record for the keyed
per-(workload,seed) OpenWhisk delivery plans (`2e_K10`, `2f_slru`). The runtime
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
