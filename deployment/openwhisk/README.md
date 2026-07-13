# OpenWhisk Cold-Start Preflight (Phase 5A)

Offline preparation for measuring SQLite cold-start prefetch inside an OpenWhisk
FaaS runtime. **Nothing here deploys or invokes OpenWhisk.** It packages a
warm-process action wrapper, freezes the measurement artifacts, and ships local
unit/dry tests. The measurement itself is a later phase on a workstation with an
OpenWhisk deployment.

See `PROTOCOL.md` for the measurement boundary, cold/warm definitions, and the
atomic pairing/exclusion rules. Absolute OpenWhisk latencies are a **separate
result batch** and are never directly compared to the local-machine batches.

## Layout

```
deployment/openwhisk/
  README.md                     this file
  PROTOCOL.md                   measurement + atomic/exclusion rules
  build_artifact_manifest.py    freeze DB/plan/trace identity -> config/artifacts.json
  action/
    residency.py                non-root mmap/mincore/madvise primitives (mirror of benchmark_harness.c)
    session.py                  warm-process identity + artifact validation
    main.py                     OpenWhisk handler; baseline + 2d paths
  client/
    collect.py                  invocation collector + session classification (no OpenWhisk in 5A)
    summarize.py                per-seed paired summary under the atomic rules
    capture_environment.sh      workstation env capture with secret redaction
  config/
    artifacts.example.json      committed example manifest (no device/inode)
    example.json                example run configuration (placeholders only)
    plans/interior_pages.csv    frozen mandatory-interior (2d) skeleton, 92 pages
  tests/                        local unit/dry tests (no OpenWhisk)
```

## Reuse of the canonical harness

The action does **not** reimplement the benchmark. It mirrors the exact non-root
primitives of `pipeline/engine/benchmark_harness/benchmark_harness.c`
(`mmap(MAP_SHARED)` + `mincore` residency, `madvise(MADV_DONTNEED)` cold reset,
`madvise(MADV_WILLNEED)` delivery) in Python because an OpenWhisk container must
be a **long-lived warm process** across invocations, which the one-shot C harness
does not model. The reference DB, the page classifier (from which the 2d interior
skeleton is derived), and the workload traces are the same canonical artifacts
`run_experiment.py` uses.

## Workstation prerequisites

- Linux host with an OpenWhisk deployment and the `wsk` CLI configured
  (`~/.wskprops`; keep it out of the repo).
- Python 3.8+ in the action runtime (stdlib + `ctypes` only; no third-party deps).
- The reference DB (~102 MB) reachable at a **fixed immutable path** inside the
  action (custom image layer or mounted volume).
- Ability to set the action to memory/timeout/concurrency below and to invoke
  sequentially.

## Artifact-copy checklist

Copy these to the workstation (unchanged bytes; hashes are enforced):

- [ ] `pipeline/preparation/layout_rewriter/runs/test.db` (reference DB)
- [ ] `deployment/openwhisk/config/plans/interior_pages.csv` (2d skeleton)
- [ ] `workloads/workload_a_{1..10}.txt` (A traces)
- [ ] the whole `deployment/openwhisk/` tree

Then regenerate the **real** manifest on the workstation (records device/inode):

```
python3 deployment/openwhisk/build_artifact_manifest.py \
    --out deployment/openwhisk/config/artifacts.json
```

The action validates DB sha256, page size/count, interior-list hash, and the
requested trace/plan hash at init and per request; any mismatch refuses measured
mode.

## DB storage requirements

- Fixed, immutable path; the action pins `(device, inode, sha256)` at init and
  fails measured mode if any changes.
- The path must allow non-root page eviction to actually cool the cache
  (see feasibility below). A dedicated container memory limit or a non-shared
  file mapping is typically required.

## Custom image vs mounted volume

- **Custom Docker action image** — bake the 102 MB DB and `deployment/openwhisk/`
  into the image. Most reliable when the DB cannot be packaged in a standard
  action archive (48 MB action limit) or when native behaviour must be pinned.
  The image digest is part of the atomic unit; record it.
- **Mounted volume / persistent path** — smaller image; the DB lives on a
  persistent volume at a fixed path. Ensure the mount options permit non-root
  eviction and a stable inode.

An action update or redeploy **invalidates existing warm-process sessions**
(new `process_uuid`); treat every redeploy as a new session group / batch.

## Configuration placeholders

Copy `config/example.json` to `config/run_config.json` and fill:
`run_id`, `action_name`, image digest, `artifact_manifest_sha256`
(from the generated `artifacts.json`), memory/timeout. Keep
`concurrency = 1` and `sequential = true`.

## Deployment commands (EXAMPLES ONLY — do not run in Phase 5A)

```
# build a custom action image (example)
# docker build -t <registry>/sqlite-coldstart:<tag> deployment/openwhisk
# wsk action create sqlite-coldstart --docker <registry>/sqlite-coldstart:<tag> \
#     --memory 512 --timeout 60000 --concurrency 1
# wsk action invoke sqlite-coldstart -r -P config/run_config.json
```

## Secret handling

- Never commit `~/.wskprops`, auth tokens, API keys, or namespace secrets.
- `client/capture_environment.sh` reports credentials only as present/absent and
  redacts secret-looking env vars; still review `environment.txt` before sharing.
- `config/artifacts.json` (real, with device/inode) is git-ignored.

## Next-phase feasibility procedure

1. Deploy the action (custom image or mounted volume) at `concurrency=1`.
2. Run `client/capture_environment.sh > environment.txt`.
3. Invoke once in `diagnostic_mode=true`, `cold_reset=true`, `strategy=baseline`
   and inspect `resident_interiors_after_reset`.
   - If it is **0**, non-root cold eviction works on this runtime → proceed.
   - If it is **> 0**, the runtime keeps the file warm; adjust isolation (container
     memory limit, dedicated volume, private mapping) until the cold gate passes,
     or record that this runtime cannot produce non-root cold data.
4. Only once the cold gate passes, run the sequential baseline/2d batch through
   `client/collect.py` (driver supplies a real `invoke_fn`), then
   `client/summarize.py` for per-seed paired deltas.

> Note: on a shared developer host, non-root `MADV_DONTNEED` may leave the file
> resident (the cold gate fails and invocations are correctly excluded). This is
> expected and is exactly the feasibility question step 3 resolves.
