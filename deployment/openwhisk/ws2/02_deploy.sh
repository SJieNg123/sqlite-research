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
Concurrency is forced to 1. The image is deployed by immutable @sha256 digest;
an unpinned build is refused unless it was explicitly allowed at build time.

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

read -r IMAGE_TAG REPO_DIGEST ARTIFACTS_SHA < <(python3 - "$BUILD_META" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(m.get("image_tag",""), m.get("repo_digest",""), m.get("artifacts_sha256",""))
PY
)
[ -n "$IMAGE_TAG" ] || ws2_die "build metadata has no image_tag"
[ -n "$ARTIFACTS_SHA" ] || ws2_die "build metadata has no artifacts_sha256 (rebuild with 01_build_image)"
case "$REPO_DIGEST" in
  UNPINNED:*) ws2_die "build recorded an UNPINNED image ($REPO_DIGEST); measured \
deploy requires an immutable @sha256 digest. Rebuild with a push target." ;;
  *@sha256:[0-9a-f]*) : ;;
  *) ws2_die "build metadata repo_digest is not a pinned @sha256 digest: $REPO_DIGEST" ;;
esac

OW_ACTION_NAME="${OW_ACTION_NAME:-sqlite-coldstart}"
OW_ACTION_MEMORY="${OW_ACTION_MEMORY:-512}"
OW_ACTION_TIMEOUT="${OW_ACTION_TIMEOUT:-60000}"
ws2_log "deploy target: action=$OW_ACTION_NAME image=$REPO_DIGEST mem=${OW_ACTION_MEMORY} to=${OW_ACTION_TIMEOUT} concurrency=1"

# wsk args. The image digest is passed twice: --docker pins what OpenWhisk runs,
# and -p OW_ACTION_IMAGE_DIGEST injects the identity the action echoes per request.
# Auth comes from ~/.wskprops (never read/printed here).
build_wsk_cmd() {  # prints the wsk argv, one token per line
  local verb="$1"
  printf '%s\n' wsk action "$verb" "$OW_ACTION_NAME" \
    --docker "$REPO_DIGEST" \
    --memory "$OW_ACTION_MEMORY" \
    --timeout "$OW_ACTION_TIMEOUT" \
    --concurrency 1 \
    -p OW_ACTION_IMAGE_DIGEST "$REPO_DIGEST"
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

printf '{\n  "action_name": "%s",\n  "image_digest": "%s",\n  "artifact_manifest_sha256": "%s",\n  "memory_mb": %s,\n  "timeout_ms": %s,\n  "concurrency": 1,\n  "git_sha": "%s",\n  "utc": "%s"\n}\n' \
  "$OW_ACTION_NAME" "$REPO_DIGEST" "$ARTIFACTS_SHA" "$OW_ACTION_MEMORY" "$OW_ACTION_TIMEOUT" \
  "$WS2_GIT_SHA" "$(ws2_ts)" \
  | ws2_atomic_write "$WS2_STAGEDIR/deploy_meta.json"

ws2_mark_status "$WS2_STAGEDIR" done PASS
ws2_log "DEPLOY OK  action=$OW_ACTION_NAME (metadata redacted -> $WS2_STAGEDIR)"
