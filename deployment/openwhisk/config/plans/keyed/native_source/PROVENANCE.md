# Keyed 2e_K10 native provenance (YCSB-C, seeds 1..10)

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
The runtime never reads any of these native sources or the fork — only the frozen
delivery plans, validated against the manifest and the replay pin.
