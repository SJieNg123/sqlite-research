# §10 Verification results — real YCSB 0.17.0, measured 2026-07-14

Run against real YCSB 0.17.0 (Maven-Central jars) on a portable Temurin-17 JRE, no sudo.
Env: [`../env/ycsb_env.txt`](../env/ycsb_env.txt). Every claim the spec makes about YCSB
internals was tested against the actual jars/source before any parser was written (spec §2.1/§6/§10).

## Core claims — all CONFIRMED

### §3.1 — `insertorder` is a no-op under `requestdistribution=zipfian`  ✅ HOLDS
workloadc, zipfian, recordcount=600000, operationcount=80000, zeropadding=19. Hot-100 keys
mapped to their B-tree rank position (dense rank in the sorted key universe), normalized [0,1):

| arm | deciles covered | rank span | top-1% key share |
|---|---|---|---|
| ordered | 10/10 | 0.973 | 3.75% |
| hashed  | 10/10 | 0.982 | 3.81% |

Both arms scatter hot keys across the whole B-tree ⇒ `insertorder` does not change hot-key
spatial locality under zipfian. **v2's 10-config matrix stands; v1's 16-config is not needed.**
Data: [`s10_1_insertorder_zipfian.json`](s10_1_insertorder_zipfian.json), `uni_*.keys`, `run_*.keys`.

### §10.2 — the spatial-locality axis lives on `hotspot` / `latest`  ✅ CONFIRMED
Same setup, hot-100 deciles covered:

| dist | ordered | hashed |
|---|---|---|
| hotspot (dataFrac=0.01, opnFrac=0.9) | **1/10** (span 0.010) | 10/10 (span 0.945) |
| latest | **1/10** (all at rank≈1.000, the tail) | 10/10 (span 0.997) |

Here `insertorder` has a massive effect — ordered keeps the hot keynums contiguous, so the
hot set is one B-tree region; hashed scatters it. Confirms the spec's redirection of the
spatial axis onto `hotspot`/`latest` (§3.1 fix, §4 matrix).

### §3.2a — `-p zipfianconstant` is a no-op under `requestdistribution=zipfian`  ✅ CONFIRMED
top-1% key share: zipfianconstant=0.99 → 3.87%, =0.50 → 3.71% (unchanged within run-to-run
noise; a honored 0.50 would be far flatter). Source: `CoreWorkload.java:486` builds
`new ScrambledZipfianGenerator(insertstart, insertstart+insertcount+expectednewkeys)` — the
2-arg (min,max) ctor, which delegates to the hardcoded `ZipfianGenerator.ZIPFIAN_CONSTANT`
(`ScrambledZipfianGenerator.java:57-58`, `USED_ZIPFIAN_CONSTANT=0.99`, `ZETAN` precomputed for
`ITEM_COUNT=10^10`). The CLI value is never read for the zipfian keychooser. ⇒ **paper must
cite measured skew, never `zipfianconstant`.** Also note the measured skew (top1≈3.8%) is far
below a pure Zipf(0.99, N=600k) — the ScrambledZipfian rank→hash fold-back flattens it, so
analytic H_N estimates do not apply (spec §3.2 point 2, confirmed).

### §3.2b — `zeropadding=8` + hashed → variable-length keys  ✅ CONFIRMED
Load, workloadc, recordcount=2000, insertorder=hashed: zeropadding=8 produced key digit-lengths
{17: 27, 18: 194, 19: 1779} (variable ⇒ fanout unstable, lexicographic≠numeric); zeropadding=19
→ all 19 digits. **19 is required.**

## Operational corrections applied to README (this environment ≠ spec's assumptions)

1. **`bin/ycsb` does not run here** — it is a Python-2 script (`print >> sys.stderr`), and this
   host has only python3. The lightweight `ycsb-basic-binding-0.17.0.tar.gz` tarball 404s.
   Working invocation is direct: `java -cp "core-0.17.0.jar:HdrHistogram.jar:htrace-core4.jar"
   site.ycsb.Client -load|-t -db site.ycsb.BasicDB -P <workload> …`. **`BasicDB` lives in the
   core jar** (`site.ycsb.BasicDB`), so no separate "basic" binding jar is needed.
2. **YCSB stdout interleaves 3 stream types** — the `***properties***` banner, the BasicDB
   verbose op lines, and the end-of-run measurement export (`[READ], Operations, …`, GC stats).
   The spec's §2.3 parser (`if not m: n_bad+=1` then fail if `n_bad`) would **false-fail on the
   banner/export**. The parser must classify each line as op / known-noise / unknown and fail
   only on *unknown*, while still asserting `#ops == operationcount`. Verbose op grammar:
   `OP usertable user<19digits> [SCAN: <len>] [ <fields> ]` — table token is always `usertable`;
   for SCAN the length precedes the `[`.
3. **`dbstat` needs no custom build** — Python stdlib `sqlite3` (3.46.1) already has the
   `dbstat` vtab. There is **no `sqlite3` CLI** on this host, so the spec's shell
   `sqlite3 … "SELECT … FROM dbstat"` snippet (§5.1) cannot run; the validator is pure-Python.
4. **keymap ground-truth** — instead of re-implementing FNV `Utils.hash` (§2.5), derive the key
   universe from YCSB's own load-phase dump and dense-rank the emitted `user…` strings
   (zeropadding=19 ⇒ lexicographic order == on-disk B-tree order). Removes a reimplementation
   risk; the mapping is provably order-preserving by construction.
