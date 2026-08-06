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
  * OW_BASE_IMAGE_DIGEST=<repo>@sha256:<64hex>  -- pinned base runtime digest.
  * OW_IMAGE_TAG (optional, default sqlite-coldstart:ws2) -- local build tag.
  * OW_IMAGE_REPO (optional) -- push target used only to resolve an immutable
    @sha256 RepoDigest for measured mode.

Records image id + digest under _runs/<sha>/01_build_image/. Never uses sudo.
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
BASE="${OW_BASE_IMAGE_DIGEST:-}"
[ -n "$BASE" ] || ws2_die "OW_BASE_IMAGE_DIGEST is unset. A pinned base runtime \
digest (repo@sha256:...) is mandatory; mutable tags are refused."
case "$BASE" in
  *@sha256:[0-9a-f]*) : ;;
  *) ws2_die "OW_BASE_IMAGE_DIGEST must be pinned by @sha256 digest, got: $BASE" ;;
esac
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

# --- image artifact staging list (DB + classifier + 10 YC traces) --------- #
# Each is staged into _image_stage/<repo-rel> so the Dockerfile's
# `COPY _image_stage/ /action/artifacts/` lands it at its manifest path. Paths +
# pinned sha256 come straight from the pin (single source of truth).
STAGE_ROOT="$WS2_OW_DIR/_image_stage"
STAGE_LIST="$(python3 - "$WS2_PIN_JSON" "$WS2_DB_REL" "$WS2_EXPECTED_DB_SHA" <<'PY'
import json, sys
pin = json.load(open(sys.argv[1]))
print("%s\t%s" % (sys.argv[2], sys.argv[3]))  # test.db
print("%s\t%s" % (pin["classifier"]["path"], pin["classifier"]["sha256"]))
for e in pin["representative_workload"]["seed_family"]:
    print("%s\t%s" % (e["trace"], e["trace_sha256"]))
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

# --- immutable repo digest (measured mode requires it) --------------------- #
REPO_DIGEST="$(docker image inspect "$OW_IMAGE_TAG" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' 2>/dev/null || true)"
if [ -z "$REPO_DIGEST" ] && [ -n "${OW_IMAGE_REPO:-}" ]; then
  ws2_log "no local RepoDigest; pushing to $OW_IMAGE_REPO to obtain an immutable digest ..."
  docker tag "$OW_IMAGE_TAG" "$OW_IMAGE_REPO" && docker push "$OW_IMAGE_REPO" \
    && REPO_DIGEST="$(docker image inspect "$OW_IMAGE_REPO" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' 2>/dev/null || true)"
fi

if [ -z "$REPO_DIGEST" ]; then
  if [ "${WS2_ALLOW_UNPINNED_IMAGE:-0}" = 1 ]; then
    ws2_warn "no immutable @sha256 image digest available; WS2_ALLOW_UNPINNED_IMAGE=1 \
set -> recording NON-MEASURED mutable id only."
    REPO_DIGEST="UNPINNED:$IMAGE_ID"
  else
    ws2_mark_status "$WS2_STAGEDIR" failed FAIL
    ws2_die "only a mutable image identity is available; measured mode requires an \
immutable @sha256 digest. Set OW_IMAGE_REPO to push, or WS2_ALLOW_UNPINNED_IMAGE=1 \
for a non-measured build."
  fi
fi

printf '{\n  "image_tag": "%s",\n  "image_id": "%s",\n  "repo_digest": "%s",\n  "base_runtime": "%s",\n  "artifacts_sha256": "%s",\n  "git_sha": "%s",\n  "utc": "%s"\n}\n' \
  "$OW_IMAGE_TAG" "$IMAGE_ID" "$REPO_DIGEST" "$BASE" "$ARTIFACTS_SHA" "$WS2_GIT_SHA" "$(ws2_ts)" \
  | ws2_atomic_write "$BUILD_META"

ws2_mark_status "$WS2_STAGEDIR" done PASS
ws2_log "BUILD OK  image_id=$IMAGE_ID digest=$REPO_DIGEST artifacts_sha256=$ARTIFACTS_SHA -> $BUILD_META"
