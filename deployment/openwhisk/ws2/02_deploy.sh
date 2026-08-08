#!/usr/bin/env bash
# 02_deploy.sh -- create/update the OpenWhisk action (no measurement invoked).
#
# Deploys the built image at concurrency=1 with explicit memory/timeout and
# injects the expected immutable image digest as an action parameter so the
# running process can echo the identity every measured request must match. It
# never invokes the measurement and never prints wsk auth.
WS2_HELP='Usage: 02_deploy.sh

Deploys the action from 01_build_image build metadata. Requires 01 completed.
Config (with defaults):
  OW_ACTION_NAME    (sqlite-coldstart)
  OW_ACTION_MEMORY  (512  MiB)
  OW_ACTION_TIMEOUT (60000 ms)
Concurrency is forced to 1. The action ships the Python sources as a zip (an
image alone yields "Missing main/no code to execute"), is executed by the unique
registry TAG (OpenWhisk does not preserve @sha256 for --docker here), and binds
the immutable RepoDigest as OW_ACTION_IMAGE_DIGEST. An unpinned build (no real
immutable digest) is refused.

Writes action metadata (redacted) under _runs/<sha>/02_deploy/. Never sudo.
Env: DRY_RUN=1 (print the wsk plan, do not deploy), WS2_FORCE=1 (redeploy).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"
[ $# -eq 0 ] || ws2_die "unexpected argument: $1 (see --help)"

ws2_begin "02_deploy"
ws2_guard_completed "$WS2_STAGEDIR"

# --- gate: build metadata -------------------------------------------------- #
BUILD_META="$WS2_RUN_DIR/01_build_image/build_meta.json"
[ -f "$BUILD_META" ] || ws2_die "build metadata missing ($BUILD_META). Run 01_build_image first."

# Distinct identities from build metadata: the registry execution TAG (what
# OpenWhisk runs), the immutable RepoDigest (bound identity), the local image id
# (provenance only, never the execution ref), and the baked-manifest sha256.
read -r EXEC_REF IMMUTABLE_DIGEST IMAGE_ID ARTIFACTS_SHA < <(python3 - "$BUILD_META" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(m.get("execution_image_ref",""), m.get("repo_digest",""),
      m.get("image_id",""), m.get("artifacts_sha256",""))
PY
)
[ -n "$EXEC_REF" ] || ws2_die "build metadata has no execution_image_ref (rebuild with 01_build_image)"
[ -n "$ARTIFACTS_SHA" ] || ws2_die "build metadata has no artifacts_sha256 (rebuild with 01_build_image)"
# Fail closed: a measured deploy must bind a REAL immutable registry digest.
case "$IMMUTABLE_DIGEST" in
  UNPINNED:*) ws2_die "build recorded an UNPINNED image ($IMMUTABLE_DIGEST); measured \
deploy requires an immutable @sha256 registry digest. Rebuild with a push target." ;;
  *@sha256:[0-9a-f]*) : ;;
  *) ws2_die "build metadata repo_digest is not a pinned @sha256 digest: $IMMUTABLE_DIGEST" ;;
esac
# The bound digest MUST name the same repository as the execution tag: OpenWhisk
# runs <repo>:<git-sha> while we bind <repo>@sha256:... as the identity -- a digest
# from a different repository would pin the wrong image. Fail closed on mismatch.
python3 "$WS2_DIR/image_identity.py" same-repo "$EXEC_REF" "$IMMUTABLE_DIGEST" \
  || ws2_die "execution_image_ref ($EXEC_REF) and immutable_image_digest \
($IMMUTABLE_DIGEST) name different repositories; refusing to deploy."

OW_ACTION_NAME="${OW_ACTION_NAME:-sqlite-coldstart}"
OW_ACTION_MEMORY="${OW_ACTION_MEMORY:-512}"
OW_ACTION_TIMEOUT="${OW_ACTION_TIMEOUT:-60000}"
ws2_log "deploy target: action=$OW_ACTION_NAME exec_ref=$EXEC_REF bound_digest=$IMMUTABLE_DIGEST mem=${OW_ACTION_MEMORY} to=${OW_ACTION_TIMEOUT} concurrency=1"

# --- package the action code zip (deterministic) --------------------------- #
# The Docker image supplies the runtime + baked artifacts; the action still needs
# its Python sources or OpenWhisk reports "Missing main". Ship a flat archive
# (main.py -> __main__.py + siblings) deployed with `--main main`.
ACTION_ZIP="$WS2_STAGEDIR/action.zip"
python3 "$WS2_DIR/make_action_zip.py" "$WS2_OW_DIR/action" "$ACTION_ZIP" >/dev/null \
  || ws2_die "failed to build the action code zip ($ACTION_ZIP)"
ws2_log "packaged action code -> $ACTION_ZIP"

# wsk args. Execution is by the registry TAG (--docker EXEC_REF); the immutable
# RepoDigest is bound as the -p OW_ACTION_IMAGE_DIGEST identity the action
# validates per measured request. Auth comes from ~/.wskprops (never read/printed).
build_wsk_cmd() {  # prints the wsk argv, one token per line
  local verb="$1"
  printf '%s\n' wsk action "$verb" "$OW_ACTION_NAME" "$ACTION_ZIP" \
    --docker "$EXEC_REF" \
    --main main \
    --memory "$OW_ACTION_MEMORY" \
    --timeout "$OW_ACTION_TIMEOUT" \
    --concurrency 1 \
    -p OW_ACTION_IMAGE_DIGEST "$IMMUTABLE_DIGEST"
}

if [ "${DRY_RUN:-0}" = 1 ]; then
  ws2_log "DRY_RUN: would deploy with:"
  build_wsk_cmd create | ws2_redact | tr '\n' ' ' | sed 's/$/\n/' >&2
  ws2_log "DRY_RUN: no deploy performed."
  exit 0
fi

ws2_require_cmd wsk
# create if absent, else update -- both idempotent for a redeploy.
if wsk action get "$OW_ACTION_NAME" >/dev/null 2>&1; then
  ws2_warn "action exists; updating (a redeploy starts a NEW warm-process session group)."
  mapfile -t CMD < <(build_wsk_cmd update)
else
  mapfile -t CMD < <(build_wsk_cmd create)
fi

"${CMD[@]}" >/dev/null 2>"$WS2_STAGEDIR/wsk_deploy.stderr" \
  || { ws2_redact < "$WS2_STAGEDIR/wsk_deploy.stderr" >&2; ws2_mark_status "$WS2_STAGEDIR" failed FAIL; ws2_die "wsk deploy failed"; }

# --- save action metadata (redacted) --------------------------------------- #
wsk action get "$OW_ACTION_NAME" 2>/dev/null | ws2_redact \
  | ws2_atomic_write "$WS2_STAGEDIR/action_metadata.json"

# Record the identities with UNAMBIGUOUS names: the execution tag OpenWhisk runs,
# the immutable RepoDigest bound as the action identity, and the local image id
# (provenance only) are three DIFFERENT things and are never conflated.
printf '{\n  "action_name": "%s",\n  "execution_image_ref": "%s",\n  "immutable_image_digest": "%s",\n  "image_id": "%s",\n  "artifact_manifest_sha256": "%s",\n  "memory_mb": %s,\n  "timeout_ms": %s,\n  "concurrency": 1,\n  "git_sha": "%s",\n  "utc": "%s"\n}\n' \
  "$OW_ACTION_NAME" "$EXEC_REF" "$IMMUTABLE_DIGEST" "$IMAGE_ID" "$ARTIFACTS_SHA" \
  "$OW_ACTION_MEMORY" "$OW_ACTION_TIMEOUT" "$WS2_GIT_SHA" "$(ws2_ts)" \
  | ws2_atomic_write "$WS2_STAGEDIR/deploy_meta.json"

ws2_mark_status "$WS2_STAGEDIR" done PASS
ws2_log "DEPLOY OK  action=$OW_ACTION_NAME (metadata redacted -> $WS2_STAGEDIR)"
