#!/usr/bin/env bash
# 01_build_image.sh -- build the custom OpenWhisk action image (no deploy/invoke).
#
# Extends a PINNED OpenWhisk Python base runtime (by @sha256 digest, never a
# mutable tag), verifies every build-context artifact hash, builds the image, and
# records the resulting Docker image id + immutable repository digest. Fails
# closed for measured mode if only a mutable image identity is obtainable.
WS2_HELP='Usage: 01_build_image.sh

Builds the custom action image. Regenerates config/artifacts.json from the frozen
inputs FIRST (never required to pre-exist; git-ignored), verifies it against the
pin, records its sha256, then stages + builds. Requires:
  * 00_preflight PASS for this checkout.
  * OW_BASE_IMAGE_DIGEST=<repo>@sha256:<64hex>  -- COMPLETE pinned base runtime
    reference (repository REQUIRED, e.g. openwhisk/action-python-v3.11@sha256:...);
    a bare @sha256 value or a mutable tag is refused.
  * OW_IMAGE_TAG (optional, default sqlite-coldstart:ws2) -- LOCAL build tag.
  * OW_IMAGE_REPO (optional) -- registry REPOSITORY (untagged, e.g.
    localhost:5000/sqlite-coldstart). If set, a unique immutable-policy execution
    tag <repo>:<git-sha> is pushed and its real registry RepoDigest resolved.

Records, distinctly: local image id, local build tag, registry execution tag, and
registry RepoDigest under _runs/<sha>/01_build_image/. Never uses sudo.
Env: DRY_RUN=1 (validate + print the build plan, do not build),
WS2_ALLOW_UNPINNED_IMAGE=1 (allow a mutable-only image id -- NON-measured only),
WS2_FORCE=1 (rebuild over a completed stage).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"
[ $# -eq 0 ] || ws2_die "unexpected argument: $1 (see --help)"

ws2_begin "01_build_image"
ws2_guard_completed "$WS2_STAGEDIR"

# --- gate: preflight PASS -------------------------------------------------- #
PRE_DIR="$WS2_RUN_DIR/00_preflight"
ws2_stage_is_done "$PRE_DIR" && [ "$(ws2_stage_status_value "$PRE_DIR")" = PASS ] \
  || ws2_die "00_preflight has not PASSed for this checkout ($PRE_DIR). Run it first."
ws2_log "preflight PASS confirmed"

# --- gate: pinned base-image digest ---------------------------------------- #
# The Dockerfile does `FROM ${BASE_RUNTIME}`, so a COMPLETE pinned reference
# <repo>@sha256:<64hex> is mandatory: a bare `@sha256:...` (empty repository) or a
# mutable tag would build the wrong image (or fail). The predicate lives in
# image_identity.py so it is unit-tested behaviourally rather than as a shell glob.
BASE="${OW_BASE_IMAGE_DIGEST:-}"
[ -n "$BASE" ] || ws2_die "OW_BASE_IMAGE_DIGEST is unset. A complete pinned base \
runtime reference (<repo>@sha256:<64hex>) is mandatory; mutable tags are refused."
ws2_require_cmd python3
python3 "$WS2_DIR/image_identity.py" check-base "$BASE" \
  || ws2_die "OW_BASE_IMAGE_DIGEST must be a COMPLETE pinned reference \
<repo>@sha256:<64hex> with a non-empty repository; a bare @sha256 value or a \
mutable tag is refused. Got: $BASE"
ws2_log "base runtime pinned: $BASE"

# --- generate the live manifest (clean-checkout capable) ------------------- #
# On a fresh WS2 checkout config/artifacts.json is git-ignored and absent. Generate
# it from the frozen inputs BEFORE any validation or staging: the generator derives
# + validates the 2d interior plan and fails closed unless every DB / plan /
# classifier / YC-trace hash matches artifacts.native_ycsb.json. artifacts.json is
# never required to pre-exist and stays git-ignored.
LIVE_MANIFEST="$WS2_OW_DIR/config/artifacts.json"
ws2_require_cmd python3
ws2_log "generating live manifest (native YCSB-C) -> config/artifacts.json"
python3 "$WS2_OW_DIR/build_artifact_manifest.py" --out "$LIVE_MANIFEST" \
  || { ws2_mark_status "$WS2_STAGEDIR" failed FAIL; ws2_die "manifest generation failed \
(missing canonical input or pin cross-check mismatch); refusing to build."; }

# --- verify build-context artifact hashes ---------------------------------- #
# The image bakes config/ (manifest + 2d plan). Verify those exact bytes before
# building so the image can never embed drifted artifacts.
FAILED=0
verify_ctx() { ws2_verify_sha256 "$1" "$2" "$3" || FAILED=$((FAILED+1)); }

# 2d plan + classifier come straight from the pin (single source of truth).
while IFS=$'\t' read -r rel want label; do
  [ -n "$rel" ] || continue
  verify_ctx "$WS2_REPO_ROOT/$rel" "$want" "$label"
done < <(python3 - "$WS2_PIN_JSON" <<'PY'
import json, sys
pin = json.load(open(sys.argv[1]))
print("%s\t%s\t%s" % (pin["strategy_plans"]["2d"]["path"], pin["strategy_plans"]["2d"]["sha256"], "2d_interior_plan"))
print("%s\t%s\t%s" % (pin["classifier"]["path"], pin["classifier"]["sha256"], "classifier"))
PY
)
# test.db bytes that will be baked/mounted must be the pinned identity.
verify_ctx "$WS2_REPO_ROOT/$WS2_DB_REL" "$WS2_EXPECTED_DB_SHA" "test.db (pinned)"
[ "$FAILED" -eq 0 ] || ws2_die "$FAILED build-context artifact hash(es) failed; refusing to build."

# --- verify the GENERATED manifest agrees with the pin -------------------- #
# artifacts.json (just generated above) is baked as-is; re-confirm its
# DB/classifier/2d-plan/trace hashes equal the pin -- defense in depth on top of
# the generator's own cross-check. Its sha256 is the identity the action recomputes
# at runtime and every measured request must match.
python3 - "$LIVE_MANIFEST" "$WS2_PIN_JSON" <<'PY' || ws2_die "generated manifest disagrees with the pin. Refusing to build."
import json, sys
man = json.load(open(sys.argv[1])); pin = json.load(open(sys.argv[2]))
bad = []
def eq(got, want, label):
    if got != want: bad.append("%s: %s != %s" % (label, got, want))
eq(man["database"]["sha256"], pin["database"]["sha256"], "db")
eq(man["classifier"]["sha256"], pin["classifier"]["sha256"], "classifier")
eq(man["strategy_plans"]["2d"]["sha256"], pin["strategy_plans"]["2d"]["sha256"], "2d_plan")
wl = pin["representative_workload"]["canonical_workload_id"]
seeds = man.get("workload_traces", {}).get(wl, {}).get("seeds", {})
for e in pin["representative_workload"]["seed_family"]:
    eq(seeds.get(str(e["seed"]), {}).get("sha256"), e["trace_sha256"], "trace_seed_%s" % e["seed"])
if bad:
    sys.stderr.write("\n".join(bad) + "\n"); sys.exit(1)
PY
ARTIFACTS_SHA="$(ws2_sha256 "$LIVE_MANIFEST")"
ws2_log "live manifest agrees with pin; artifacts_sha256=$ARTIFACTS_SHA"

# --- live-manifest invariant gate (unittest; fail BEFORE any build) -------- #
# The live-manifest invariants (pin <-> the just-generated config/artifacts.json on
# DB / classifier / 2d-plan / denominator) are the checks 00_preflight deliberately
# cannot run (artifacts.json does not exist yet there). Run them now, after
# generation and before staging/build, so a live manifest that disagrees with the
# pin can never reach `docker build`. This runs under DRY_RUN too (artifacts.json is
# already generated above). A SKIP here means artifacts.json vanished -> fail closed.
ws2_require_cmd python3
LIVE_INV="deployment.openwhisk.tests.test_manifest_invariants.TestNativeYcsbLiveManifestAgreement"
LIVE_INV_LOG="$WS2_STAGEDIR/live_manifest_invariants.log"
if ( cd "$WS2_REPO_ROOT" && python3 -m unittest "$LIVE_INV" ) > "$LIVE_INV_LOG" 2>&1; then
  if grep -q 'skipped' "$LIVE_INV_LOG"; then
    ws2_mark_status "$WS2_STAGEDIR" failed FAIL
    ws2_die "live-manifest invariants were SKIPPED (config/artifacts.json missing?); refusing to build (see $LIVE_INV_LOG)."
  fi
  ws2_log "live-manifest invariants PASS ($LIVE_INV)"
else
  ws2_mark_status "$WS2_STAGEDIR" failed FAIL
  ws2_die "live-manifest invariant tests FAILED; refusing to build (see $LIVE_INV_LOG)."
fi

# --- image artifact staging list (DB + classifier + 10 YC traces + the 12 --- #
# portability workload traces) ---------------------------------------------- #
# Each is staged into _image_stage/<repo-rel> so the Dockerfile's
# `COPY _image_stage/ /action/artifacts/` lands it at its manifest path. Paths +
# pinned sha256 come straight from the pin (single source of truth). The four
# portability workloads' traces (4 workloads x seeds 1..3) live OUTSIDE config/,
# so -- like the YC traces -- they must be staged here or the Dockerfile
# build-time self-check (which walks manifest.workload_traces) fails closed.
STAGE_ROOT="$WS2_OW_DIR/_image_stage"
STAGE_LIST="$(python3 - "$WS2_PIN_JSON" "$WS2_DB_REL" "$WS2_EXPECTED_DB_SHA" <<'PY'
import json, sys
pin = json.load(open(sys.argv[1]))
print("%s\t%s" % (sys.argv[2], sys.argv[3]))  # test.db
print("%s\t%s" % (pin["classifier"]["path"], pin["classifier"]["sha256"]))
for e in pin["representative_workload"]["seed_family"]:
    print("%s\t%s" % (e["trace"], e["trace_sha256"]))
# Portability workload traces (the four NEW workloads; YC is already above).
for wl, wentry in pin.get("portability_workload_traces", {}).items():
    for seed, tentry in wentry.get("seeds", {}).items():
        print("%s\t%s" % (tentry["path"], tentry["sha256"]))
PY
)"

OW_IMAGE_TAG="${OW_IMAGE_TAG:-sqlite-coldstart:ws2}"
BUILD_META="$WS2_STAGEDIR/build_meta.json"

if [ "${DRY_RUN:-0}" = 1 ]; then
  ws2_log "DRY_RUN: config/artifacts.json generated + pin-verified (artifacts_sha256=$ARTIFACTS_SHA)."
  ws2_log "DRY_RUN: build plan validated. Would stage into $STAGE_ROOT/<repo-rel>:"
  while IFS=$'\t' read -r rel _; do [ -n "$rel" ] && ws2_log "  stage $rel"; done <<< "$STAGE_LIST"
  ws2_log "DRY_RUN: would run:"
  ws2_log "  docker build --no-cache --build-arg BASE_RUNTIME=$BASE --build-arg ARTIFACTS_SHA256=$ARTIFACTS_SHA -t $OW_IMAGE_TAG $WS2_OW_DIR"
  if [ -n "${OW_IMAGE_REPO:-}" ]; then
    ws2_log "  then push unique execution tag <repo>:$WS2_GIT_SHA_SHORT (OW_IMAGE_REPO=$OW_IMAGE_REPO) and resolve its exact-repository RepoDigest"
  fi
  ws2_log "DRY_RUN: no image built, no metadata written."
  exit 0
fi

# --- stage image artifacts (verified vs pin) ------------------------------- #
ws2_log "staging image artifacts into $STAGE_ROOT ..."
rm -rf "$STAGE_ROOT"
STAGE_FAILED=0
while IFS=$'\t' read -r rel want; do
  [ -n "$rel" ] || continue
  src="$WS2_REPO_ROOT/$rel"; dst="$STAGE_ROOT/$rel"
  [ -f "$src" ] || { ws2_warn "stage source missing: $rel"; STAGE_FAILED=$((STAGE_FAILED+1)); continue; }
  mkdir -p "$(dirname "$dst")"
  cp -f "$src" "$dst"
  ws2_verify_sha256 "$dst" "$want" "staged $rel" || STAGE_FAILED=$((STAGE_FAILED+1))
done <<< "$STAGE_LIST"
[ "$STAGE_FAILED" -eq 0 ] || { ws2_mark_status "$WS2_STAGEDIR" failed FAIL; ws2_die "$STAGE_FAILED staged artifact(s) failed; refusing to build."; }

# --- build (never sudo) ---------------------------------------------------- #
ws2_require_cmd docker
ws2_log "building $OW_IMAGE_TAG ..."
docker build --no-cache --build-arg BASE_RUNTIME="$BASE" --build-arg ARTIFACTS_SHA256="$ARTIFACTS_SHA" \
  -t "$OW_IMAGE_TAG" "$WS2_OW_DIR" \
  || { ws2_mark_status "$WS2_STAGEDIR" failed FAIL; ws2_die "docker build failed"; }

IMAGE_ID="$(docker image inspect "$OW_IMAGE_TAG" --format '{{.Id}}' 2>/dev/null || true)"
[ -n "$IMAGE_ID" ] || { ws2_mark_status "$WS2_STAGEDIR" failed FAIL; ws2_die "cannot read built image id"; }

# --- registry execution tag + immutable RepoDigest ------------------------- #
# Four distinct identities, never conflated:
#   IMAGE_ID   -- local Docker image content id (sha256:...); NOT a registry digest.
#   OW_IMAGE_TAG -- local build tag (mutable; how docker names the local image).
#   EXEC_REF   -- registry execution tag <repo>:<git-sha> (what OpenWhisk runs).
#   REPO_DIGEST -- registry RepoDigest <repo>@sha256:... (immutable content identity
#                  bound as OW_ACTION_IMAGE_DIGEST). Resolved ONLY from a real push;
#                  NEVER fabricated from IMAGE_ID.
EXEC_REF=""
REPO_DIGEST=""
if [ -n "${OW_IMAGE_REPO:-}" ]; then
  # Immutable-policy execution tag: the exact git SHA (unique per commit).
  EXEC_REF="$(python3 "$WS2_DIR/image_identity.py" exec-ref "$OW_IMAGE_REPO" "$WS2_GIT_SHA_SHORT")" \
    || { ws2_mark_status "$WS2_STAGEDIR" failed FAIL; ws2_die "could not derive an execution tag from OW_IMAGE_REPO=$OW_IMAGE_REPO"; }
  ws2_log "pushing immutable execution tag $EXEC_REF ..."
  if docker tag "$OW_IMAGE_TAG" "$EXEC_REF" && docker push "$EXEC_REF" >/dev/null; then
    # Bind the RepoDigest whose repository EXACTLY matches OW_IMAGE_REPO -- NOT
    # docker's first RepoDigests entry, which may be a registry-less alias
    # (name@sha256:...) that drops the host:port and would mis-pin the image.
    RD_JSON="$(docker image inspect "$EXEC_REF" --format '{{json .RepoDigests}}' 2>/dev/null || echo 'null')"
    if REPO_DIGEST="$(python3 "$WS2_DIR/image_identity.py" select-digest "$OW_IMAGE_REPO" "$RD_JSON" 2>"$WS2_STAGEDIR/repodigest_select.err")"; then
      # Confirm the resolved host-qualified digest is really pullable from the registry.
      docker pull "$REPO_DIGEST" >/dev/null 2>&1 \
        || { ws2_warn "resolved RepoDigest did not verify via docker pull: $REPO_DIGEST"; REPO_DIGEST=""; }
    else
      ws2_warn "no unique registry RepoDigest for $OW_IMAGE_REPO ($(cat "$WS2_STAGEDIR/repodigest_select.err" 2>/dev/null))"
      REPO_DIGEST=""
    fi
  else
    ws2_warn "failed to tag/push $EXEC_REF"
  fi
fi

if [ -z "$REPO_DIGEST" ]; then
  if [ "${WS2_ALLOW_UNPINNED_IMAGE:-0}" = 1 ]; then
    # NON-MEASURED build: record a clearly-marked sentinel (never a fake digest)
    # and fall back to the local tag for execution. 02_deploy refuses this.
    ws2_warn "no immutable @sha256 RepoDigest; WS2_ALLOW_UNPINNED_IMAGE=1 set -> \
NON-MEASURED build (execution by local tag, no bound immutable digest)."
    REPO_DIGEST="UNPINNED:$IMAGE_ID"
    [ -n "$EXEC_REF" ] || EXEC_REF="$OW_IMAGE_TAG"
  else
    ws2_mark_status "$WS2_STAGEDIR" failed FAIL
    ws2_die "no immutable @sha256 registry digest available; measured mode requires \
one. Set OW_IMAGE_REPO to push a unique execution tag, or WS2_ALLOW_UNPINNED_IMAGE=1 \
for a non-measured build. The local image id is NOT a substitute for a RepoDigest."
  fi
fi

printf '{\n  "image_id": "%s",\n  "local_image_tag": "%s",\n  "execution_image_ref": "%s",\n  "repo_digest": "%s",\n  "base_runtime": "%s",\n  "artifacts_sha256": "%s",\n  "git_sha": "%s",\n  "utc": "%s"\n}\n' \
  "$IMAGE_ID" "$OW_IMAGE_TAG" "$EXEC_REF" "$REPO_DIGEST" "$BASE" "$ARTIFACTS_SHA" "$WS2_GIT_SHA" "$(ws2_ts)" \
  | ws2_atomic_write "$BUILD_META"

ws2_mark_status "$WS2_STAGEDIR" done PASS
ws2_log "BUILD OK  image_id=$IMAGE_ID exec_ref=$EXEC_REF repo_digest=$REPO_DIGEST artifacts_sha256=$ARTIFACTS_SHA -> $BUILD_META"
