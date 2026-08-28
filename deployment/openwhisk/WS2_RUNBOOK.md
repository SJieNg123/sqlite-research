# WS2 Runbook — portable OpenWhisk execution from an exact Git commit

This runbook describes the **two-machine, two-terminal** workflow for running the
OpenWhisk cold-start measurement. It is deliberately *portable* and *decoupled*:

- **Workstation1 (WS1)** — has Claude Code; this is where sqlite-research is
  developed, tested, committed, and pushed.
- **Workstation2 (WS2)** — has an OpenWhisk deployment, Docker, `wsk`, and a
  clone of sqlite-research. This is where the `ws2/` scripts run.

You (the human) drive both machines yourself through two independent local
VS Code SSH sessions.

> **Hard boundaries (by design):**
> - WS1 **never** SSHes to WS2. There is no remote orchestration, no `remote.env`,
>   no `run_remote.sh`, no `sync_commit.sh`. The only channel between the machines
>   is **Git** (a pushed commit) one way, and a **tar.gz bundle** the other way.
> - WS2 checks out an **exact commit SHA** and runs the scripts locally.
> - Nothing here uses `sudo`, reads/prints `wsk` auth, or touches `~/.wskprops`.

---

## The loop at a glance

```
WS1 (dev)                                WS2 (OpenWhisk)
─────────                                ───────────────
edit / test                              (idle)
git commit                               ...
git push origin main   ── Git ─────────▶ git fetch origin
git rev-parse HEAD  ──(copy the SHA)──▶  git checkout --detach <SHA>
                                         bash ws2/00_preflight.sh ...
                                         bash ws2/01_build_image.sh
                                         ...
                                         bash ws2/06_collect.sh
(receive bundle)   ◀── scp tar.gz ─────  ws2_bundle_<sha>_<ts>.tar.gz
inspect results
```

---

## Terminal A — Workstation1 (development machine)

Do all of this in the sqlite-research checkout on WS1.

```bash
# 1. See what you're about to lock in.
git status

# 2. Run the stdlib tests that WS2 will also gate on (no pytest needed).
python3 -m unittest tests.test_workload_naming
python3 -m unittest deployment.openwhisk.tests.test_manifest_invariants

# 3. Commit and push (only when you're satisfied; approval-gated in this repo).
git add -- <the files you intend to ship>
git commit -m "…"
git push origin main

# 4. Print the EXACT commit SHA to hand to WS2.
git rev-parse HEAD
```

Expected output of step 4 is a full 40-hex SHA, e.g.:

```
e0aa26ab54cc6a49685aa3c90b5bef20e0c5812f
```

Copy that SHA. That is the only thing WS2 needs from you.

> WS1 does not run any `ws2/` script and does not connect to WS2. Its job ends at
> "pushed commit + SHA on the clipboard."

---

## Terminal B — Workstation2 (OpenWhisk machine)

Paste the SHA from WS1 into a shell variable and check it out **detached** so WS2
is pinned to the exact bytes WS1 shipped.

```bash
cd /path/to/sqlite-research          # WS2's own clone

# 1. Fetch the pushed history (this is the ONLY cross-machine pull).
git fetch origin

# 2. Refuse to proceed with a dirty tree — WS2 must run pristine bytes.
#    (The scripts also enforce this; this is the manual pre-check.)
test -z "$(git status --porcelain)" || { echo "DIRTY TREE — clean it first"; }

# 3. Check out the EXACT commit, detached (no branch, no drift).
EXACT_SHA=e0aa26ab54cc6a49685aa3c90b5bef20e0c5812f      # ← paste WS1's SHA
git checkout --detach "$EXACT_SHA"

# 4. Verify HEAD is exactly what WS1 shipped.
git rev-parse HEAD
#   → must print $EXACT_SHA, character for character.
git status
#   → "HEAD detached at e0aa26a" and "nothing to commit, working tree clean"
```

Then run the `ws2/` stages **in order**. Each stage gates on the previous one and
writes only to the machine-local, git-ignored tree
`deployment/openwhisk/ws2/_runs/<short-sha>/`.

```bash
cd deployment/openwhisk/ws2

# 0. Read-only readiness + frozen-artifact integrity. No build/deploy/invoke.
#    Supply the OpenWhisk SOURCE-REPO SHA (WS2's OpenWhisk install), not this repo's.
bash 00_preflight.sh --openwhisk-sha "$(git -C /path/to/openwhisk rev-parse HEAD)" \
                     --openwhisk-status "clean"

# 1. Build the custom action image (needs a pinned base-runtime digest).
export OW_BASE_IMAGE_DIGEST='openwhisk/action-python-v3.11@sha256:<64hex>'
export OW_IMAGE_REPO='<registry>/sqlite-coldstart:ws2'   # to obtain an immutable digest
bash 01_build_image.sh

# 2. Deploy the action at concurrency=1 with explicit memory/timeout.
bash 02_deploy.sh

# 3. One diagnostic invocation — proves non-root cold eviction works.
export OW_ARTIFACT_MANIFEST_SHA256='<sha256 of the artifacts.json baked in the image>'
bash 03_diagnostic.sh

# 4. Small paired feasibility batch (6 baseline/2d pairs; needs ≥5 valid).
bash 04_feasibility.sh

# 5. Full matrix — validated + scheduled now; execution is behind an impl gate.
bash 05_full_matrix.sh --matrix ./matrix.example.json     # copy+edit for the real matrix
#    For the workstation→OpenWhisk portability campaign (234 pairs / 468 invocations,
#    independent identity), run stage 05 EXACTLY ONCE on the single-batch matrix
#    ./matrix.portability.json (a block-union of four logical blocks, one campaign
#    fingerprint) — NOT once per fragment — see PORTABILITY_MATRIX.md.
#    For the portability-EXTENSION campaign (426 pairs / 852 invocations, schedule_seed
#    20260828, fourth independent identity portability_ext bf504a28…), run stage 05
#    EXACTLY ONCE on ./matrix.portability_ext.json (a block-union of seven blocks B5–B11).
#    It bakes 63 extra keyed CSVs, so it runs under a NEW image identity — the archived
#    portability image is untouched. See PORTABILITY_MATRIX.md § Portability-EXTENSION.
#    For the portability-FULL-CLOSURE campaign (228 pairs / 456 invocations, schedule_seed
#    20260829, fifth independent identity portability_full_closure a5be8f15…), run stage 05
#    EXACTLY ONCE on ./matrix.portability_full_closure.json (a block-union of six blocks
#    B12–B17). It closes the final 16 canonical cells (65/65 plannable coverage) and bakes
#    37 extra keyed CSVs (incl. lp_sorted/lp_shuf ordered pread delivery), so it runs under
#    a NEW image identity — all four prior images are untouched. lp arms deliver the same
#    page set in different pread ORDER; their primary quantity is deliver_us, not
#    first_query. See PORTABILITY_MATRIX.md § Portability-FULL-CLOSURE.

# 6. Package everything for transfer back to WS1.
bash 06_collect.sh --openwhisk-sha "$(git -C /path/to/openwhisk rev-parse HEAD)"
```

Every script supports `--help`. Every script honours `DRY_RUN=1` where it means
anything (build/deploy/invoke are skipped; validation and scheduling still run).

---

## What each stage produces (all under `ws2/_runs/<short-sha>/`)

| Stage | Dir | Key outputs | Gate to pass |
|-------|-----|-------------|--------------|
| 00 | `00_preflight/` | `preflight_report.txt`, redacted `wsk_namespace.txt`, unittest logs | all checks PASS; `test.db` sha == pinned |
| 01 | `01_build_image/` | `build_meta.json` (image id + immutable digest) | preflight PASS; pinned base digest; ctx hashes |
| 02 | `02_deploy/` | `deploy_meta.json`, redacted `action_metadata.json` | build meta present; digest pinned |
| 03 | `03_diagnostic/` | `request.json`, `response.json`, `gate_report.txt` | `resident_interiors_after_reset == 0` + artifact/identity/oracle |
| 04 | `04_feasibility/` | `schedule.json`, `raw/req_*.json`,`raw/resp_*.json`, `feasibility_report.txt` | ≥5 valid complete pairs |
| 05 | `05_full_matrix/` | `matrix_validation.txt`, `schedule.json`, `raw/*`, `completed_cells.tsv` | matrix valid; impl gate; identity/session |
| 06 | `06_collect/` | `bundle_manifest.json`, `validity_summary.txt`, `environment.txt`, `ws2_bundle_<sha>_<ts>.tar.gz(.sha256)` | tar built |

The `<short-sha>` keys every stage to the checkout, so after `git checkout
--detach <SHA>` the stages deterministically find each other's outputs.

---

## Machine-local vs committed files

**Committed (tracked in Git, shipped from WS1):**
- `deployment/openwhisk/ws2/*.sh` (the stage scripts + `common.sh`)
- `deployment/openwhisk/ws2/matrix.example.json` (an *example* — not the final matrix)
- `deployment/openwhisk/WS2_RUNBOOK.md` (this file)

**Machine-local, git-ignored (never committed — added to
`deployment/openwhisk/.gitignore`):**
- `deployment/openwhisk/ws2/_runs/**` — all requests/responses/reports/metadata/
  schedules/ledgers for every checkout
- `deployment/openwhisk/ws2/*.tar.gz` and `*.tar.gz.sha256` — collected bundles
- (already ignored elsewhere) `config/artifacts.json`, `config/run_config.json`,
  `config/environment.txt`, `*.db`

The generated real manifest `deployment/openwhisk/config/artifacts.json` (with
device/inode) is regenerated on WS2 after the DB is in its final action namespace
and stays git-ignored; only `artifacts.example.json` / `artifacts.native_ycsb.json`
are committed.

---

## Transferring the bundle back to WS1

The bundle is a plain tar.gz; move it however you normally move files (this repo
does **not** provide a sync script by design). For example, from WS1:

```bash
# From Workstation1, pull the artifact (WS1→WS2 read is fine; WS2 never reaches WS1).
scp ws2host:/path/to/sqlite-research/deployment/openwhisk/ws2/_runs/<sha>/06_collect/ws2_bundle_*.tar.gz .
scp ws2host:/path/to/.../ws2_bundle_*.tar.gz.sha256 .
sha256sum -c ws2_bundle_*.tar.gz.sha256
tar -tzf ws2_bundle_*.tar.gz          # inspect before extracting
```

The bundle records both Git SHAs, all frozen artifact hashes, the image digest,
the run-config SHA, action metadata, and a per-stage validity summary, so it is
self-describing on WS1 without any WS2 state.

---

## Recovery procedures

**Preflight FAIL.** Read `_runs/<sha>/00_preflight/preflight_report.txt`; each
`FAIL` line names the gate. Common causes: `test.db` sha ≠ pinned (wrong/rebuilt
DB — restore the frozen file), `wsk` cannot reach a namespace (fix `~/.wskprops`
yourself; the script never touches it), Docker needs sudo (fix group membership —
WS2 never sudo). Fix, then re-run (use `WS2_FORCE=1` to redo a completed stage).

**Diagnostic FAIL with `resident_interiors_after_reset > 0`.** The runtime keeps
the DB warm; non-root eviction did not cool it. Adjust isolation (container memory
limit, dedicated volume, private mapping) per `README.md` step 3, redeploy (02),
and re-run 03. If it cannot be made to cool, record that this runtime cannot
produce non-root cold data — that is a valid finding, not a script bug.

**Redeploy mid-run.** Any redeploy (02) starts a **new warm-process session
group** (new `process_uuid`). Treat it as a new batch: the `05` executor stops if
a completed cell reappears under a different session. Start a fresh run
(new checkout or `WS2_FORCE=1`) rather than mixing sessions.

**Resume `05` after an interruption.** Just re-run the same
`05_full_matrix.sh --matrix <same file>`. It reuses the persisted `schedule.json`
and skips positions whose `raw/resp_*.json` already exist. Duplicate completed
cells with a different identity are a hard stop (protects atomic pairing).

**Dirty tree.** Every non-read-only stage refuses to run against uncommitted
changes. Either commit/stash on WS2 (don't — WS2 should mirror WS1), or more
correctly `git checkout --detach <SHA>` again to restore pristine bytes. The
read-only preflight can be forced past a dirty tree with `WS2_ALLOW_DIRTY=1` for
inspection only.

---

## Safety properties (enforced by `common.sh` in every stage)

- `set -euo pipefail`; **fail closed** — a failed gate aborts, never a partial "OK".
- **No `sudo`** (the function is shadowed to abort if ever called).
- **No credentials**: `wsk` reads `~/.wskprops` itself; scripts never read or
  print auth, and all external output is passed through a secret-redaction filter.
- **No silent overwrite**: a completed stage refuses to clobber itself
  (`WS2_FORCE=1` to override); `05` is explicitly resumable.
- **Atomic writes**: outputs are written to a temp file and `mv`'d into place.
- **Exact identities recorded**: Git SHA, artifact hashes, image digest, and
  run-config SHA are captured at every stage and packaged by `06`.
