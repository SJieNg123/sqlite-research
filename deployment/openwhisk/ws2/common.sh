#!/usr/bin/env bash
# common.sh -- shared library for the Workstation2 (WS2) OpenWhisk execution
# workflow. SOURCE this from every ws2 stage script; it is not meant to be run
# standalone (running it directly only prints help).
#
# Design contract (see WS2_RUNBOOK.md):
#   * WS2 executes scripts directly on a machine that already has OpenWhisk and a
#     clone of sqlite-research checked out at an EXACT commit. There is NO remote
#     orchestration here: nothing SSHes anywhere, nothing syncs commits.
#   * Every stage records the exact Git SHA + artifact/image/run identities and
#     writes only to a machine-local, git-ignored results tree.
#   * Fail closed. Never sudo. Never read or print wsk auth. Never touch
#     ~/.wskprops. Never silently overwrite a completed run.
set -euo pipefail

# --------------------------------------------------------------------------- #
# Repository discovery + exact Git identity                                    #
# --------------------------------------------------------------------------- #
WS2_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Discover the repository root and require a real Git checkout.
if ! WS2_REPO_ROOT="$(git -C "$WS2_LIB_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  echo "FATAL: not inside a Git checkout (git rev-parse --show-toplevel failed)." >&2
  echo "       WS2 must run from a clone of sqlite-research checked out at an" >&2
  echo "       exact commit. Aborting." >&2
  exit 1
fi
export WS2_REPO_ROOT
WS2_OW_DIR="$WS2_REPO_ROOT/deployment/openwhisk"
WS2_DIR="$WS2_OW_DIR/ws2"

# Exact Git SHA of the current checkout (never a branch name).
WS2_GIT_SHA="$(git -C "$WS2_REPO_ROOT" rev-parse HEAD)"
WS2_GIT_SHA_SHORT="${WS2_GIT_SHA:0:12}"

# Machine-local, git-ignored results root. All stage output lives here, keyed by
# the exact commit so stages after a checkout deterministically find each other.
WS2_RUN_ROOT="${WS2_RUN_ROOT:-$WS2_DIR/_runs}"
WS2_RUN_DIR="$WS2_RUN_ROOT/$WS2_GIT_SHA_SHORT"

# Pinned frozen inputs (relative to repo root).
WS2_PIN_JSON="$WS2_OW_DIR/config/artifacts.native_ycsb.json"
WS2_NATIVE_MANIFEST="$WS2_REPO_ROOT/NATIVE_YCSB_MANIFEST.json"
WS2_DB_REL="pipeline/preparation/layout_rewriter/runs/test.db"
# The one non-negotiable identity: test.db must be exactly this content.
WS2_EXPECTED_DB_SHA="2504a6b15f4b202b11234549ab1d46e22eb808e0b03a5731236083122237fdd1"

# --------------------------------------------------------------------------- #
# Logging + fail-closed die                                                    #
# --------------------------------------------------------------------------- #
ws2_ts()   { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
ws2_log()  { printf '[%s] %s\n' "$(ws2_ts)" "$*" >&2; }
ws2_warn() { printf '[%s] WARN: %s\n' "$(ws2_ts)" "$*" >&2; }
ws2_die()  { printf '[%s] FATAL: %s\n' "$(ws2_ts)" "$*" >&2; exit 1; }

# Hard guarantee: sudo is forbidden. Shadow it so an accidental call fails closed.
sudo() { ws2_die "sudo is forbidden in WS2 scripts (attempted: sudo $*)"; }

# --------------------------------------------------------------------------- #
# --help handling                                                              #
# --------------------------------------------------------------------------- #
# Each stage sets WS2_HELP="..." before calling ws2_maybe_help "$@".
ws2_maybe_help() {
  local a
  for a in "$@"; do
    case "$a" in
      -h|--help)
        printf '%s\n' "${WS2_HELP:-No help text provided.}"
        exit 0
        ;;
    esac
  done
}

# --------------------------------------------------------------------------- #
# Command / hashing helpers                                                    #
# --------------------------------------------------------------------------- #
ws2_have() { command -v "$1" >/dev/null 2>&1; }
ws2_require_cmd() { ws2_have "$1" || ws2_die "required command not found: $1"; }

ws2_sha256() {  # print sha256 of a file
  local f="$1"
  [ -f "$f" ] || ws2_die "cannot hash missing file: $f"
  if ws2_have sha256sum; then sha256sum "$f" | awk '{print $1}';
  elif ws2_have shasum; then shasum -a 256 "$f" | awk '{print $1}';
  else ws2_die "no sha256sum/shasum available"; fi
}

ws2_verify_sha256() {  # ws2_verify_sha256 <file> <expected> [label]
  local f="$1" want="$2" label="${3:-$1}" got
  [ -e "$f" ] || { ws2_warn "MISSING: $label ($f)"; return 1; }
  got="$(ws2_sha256 "$f")"
  if [ "$got" = "$want" ]; then
    ws2_log "OK   sha256 $label"
    return 0
  fi
  ws2_warn "HASH MISMATCH $label"
  ws2_warn "  expected: $want"
  ws2_warn "  actual:   $got"
  return 1
}

# --------------------------------------------------------------------------- #
# Secret redaction                                                             #
# --------------------------------------------------------------------------- #
# Redact anything that looks like an auth token / key / password, plus
# user:secret@host embedded in URLs. Applied to any external command output we
# persist. This NEVER makes it safe to print wsk auth on purpose -- we simply do
# not request it anywhere.
ws2_redact() {
  sed -E \
    -e 's/(AUTH|TOKEN|APIKEY|API_KEY|KEY|SECRET|PASS(WORD)?)([[:space:]]*[=:][[:space:]]*)[^[:space:]]+/\1\3REDACTED/Ig' \
    -e 's#(https?://)[^:@/[:space:]]+:[^@/[:space:]]+@#\1REDACTED:REDACTED@#g' \
    -e 's/[0-9a-fA-F]{8}-[0-9a-fA-F-]{4,}:[A-Za-z0-9]{16,}/REDACTED_WSK_AUTH/g'
}

# --------------------------------------------------------------------------- #
# Atomic writes + completed-run protection                                     #
# --------------------------------------------------------------------------- #
# Read stdin and write it atomically to $1 (temp in the same dir, then mv).
ws2_atomic_write() {
  local dest="$1" tmp
  mkdir -p "$(dirname "$dest")"
  tmp="$(mktemp "${dest}.tmp.XXXXXX")"
  cat > "$tmp"
  mv -f "$tmp" "$dest"
}

ws2_stage_dir() {  # ws2_stage_dir <stage-name> -> prints (and creates) the dir
  local d="$WS2_RUN_DIR/$1"
  mkdir -p "$d"
  printf '%s\n' "$d"
}

ws2_stage_status_file() { printf '%s/STATUS\n' "$1"; }

ws2_stage_is_done() {  # ws2_stage_is_done <stage-dir>
  local sf; sf="$(ws2_stage_status_file "$1")"
  [ -f "$sf" ] && grep -q '^status=done' "$sf"
}

ws2_stage_status_value() {  # prints result= value of a stage (PASS/FAIL/...)
  local sf; sf="$(ws2_stage_status_file "$1")"
  [ -f "$sf" ] || { printf 'MISSING\n'; return 1; }
  awk -F= '/^result=/{print $2; exit}' "$sf"
}

# Refuse to clobber a completed stage unless resuming or forcing.
ws2_guard_completed() {  # ws2_guard_completed <stage-dir>
  local d="$1"
  if ws2_stage_is_done "$d"; then
    if [ "${WS2_FORCE:-0}" = 1 ]; then
      ws2_warn "stage already completed at $d -- WS2_FORCE=1, re-running."
    else
      ws2_die "stage already completed at $d (result=$(ws2_stage_status_value "$d")). \
Refusing to overwrite. Set WS2_FORCE=1 to redo, or use resume where supported."
    fi
  fi
}

ws2_mark_status() {  # ws2_mark_status <stage-dir> <done|failed> <PASS|FAIL|...>
  local d="$1" state="$2" result="$3" sf
  sf="$(ws2_stage_status_file "$d")"
  printf 'status=%s\nresult=%s\ngit_sha=%s\nrun_id=%s\nutc=%s\n' \
    "$state" "$result" "$WS2_GIT_SHA" "${WS2_RUN_ID:-unset}" "$(ws2_ts)" \
    | ws2_atomic_write "$sf"
}

# --------------------------------------------------------------------------- #
# Dirty-tree policy                                                            #
# --------------------------------------------------------------------------- #
ws2_tree_is_dirty() { [ -n "$(git -C "$WS2_REPO_ROOT" status --porcelain)" ]; }

ws2_require_clean_tree() {  # ws2_require_clean_tree [strict|readonly]
  local mode="${1:-strict}"
  ws2_tree_is_dirty || return 0
  if [ "$mode" = readonly ] && [ "${WS2_ALLOW_DIRTY:-0}" = 1 ]; then
    ws2_warn "dirty working tree ALLOWED for this read-only command (WS2_ALLOW_DIRTY=1)."
    return 0
  fi
  ws2_die "dirty working tree; refusing to run against unversioned changes. \
WS2 must run from an exact checkout. (Read-only commands may set WS2_ALLOW_DIRTY=1.)"
}

# --------------------------------------------------------------------------- #
# Stage bootstrap                                                              #
# --------------------------------------------------------------------------- #
# ws2_begin <stage-name> [strict|readonly]
#   - assigns WS2_STAGE / WS2_STAGEDIR / WS2_RUN_ID
#   - enforces the dirty-tree policy (downgraded to a warning under DRY_RUN)
#   - writes an idempotent identity record for this checkout
ws2_begin() {
  WS2_STAGE="$1"
  local mode="${2:-strict}"
  WS2_RUN_ID="$(ws2_ts | tr -d ':-')-$WS2_GIT_SHA_SHORT"

  if [ "${DRY_RUN:-0}" = 1 ]; then
    ws2_tree_is_dirty && ws2_warn "DRY_RUN=1: dirty-tree enforcement downgraded to a warning."
  else
    ws2_require_clean_tree "$mode"
  fi

  WS2_STAGEDIR="$(ws2_stage_dir "$WS2_STAGE")"
  ws2_write_identity
  ws2_log "stage=$WS2_STAGE git=$WS2_GIT_SHA_SHORT run_id=$WS2_RUN_ID dry_run=${DRY_RUN:-0}"
  ws2_log "stage_dir=$WS2_STAGEDIR"
}

ws2_write_identity() {
  local f="$WS2_RUN_DIR/identity.json"
  mkdir -p "$WS2_RUN_DIR"
  printf '{\n  "git_sha": "%s",\n  "git_dirty": %s,\n  "utc": "%s",\n  "repo_root": "%s"\n}\n' \
    "$WS2_GIT_SHA" \
    "$(ws2_tree_is_dirty && echo true || echo false)" \
    "$(ws2_ts)" "$WS2_REPO_ROOT" \
    | ws2_atomic_write "$f"
}

# --------------------------------------------------------------------------- #
# Single-shot OpenWhisk invocation (blocking, result JSON preserved)           #
# --------------------------------------------------------------------------- #
# ws2_invoke <action-name> <request.json> <response.json>
#   Reads a JSON object of action parameters from <request.json>, invokes the
#   action once (blocking, -r result), and writes the raw response JSON to
#   <response.json>. Never prints auth (wsk reads ~/.wskprops itself). Under
#   DRY_RUN it writes a synthetic response and does NOT contact OpenWhisk.
ws2_invoke() {
  local action="$1" req="$2" resp="$3"
  [ -f "$req" ] || ws2_die "ws2_invoke: request file missing: $req"
  if [ "${DRY_RUN:-0}" = 1 ]; then
    ws2_log "DRY_RUN: would invoke action=$action with $(basename "$req")"
    printf '{"_dry_run": true, "note": "no invocation performed under DRY_RUN=1"}\n' \
      | ws2_atomic_write "$resp"
    return 0
  fi
  ws2_require_cmd wsk
  # Build -p key value pairs from the request JSON (values re-encoded as JSON).
  local args=(); local kv
  while IFS= read -r kv; do args+=("$kv"); done < <(python3 - "$req" <<'PY'
import json, sys
for k, v in json.load(open(sys.argv[1])).items():
    print("-p"); print(k)
    print(v if isinstance(v, str) else json.dumps(v))
PY
  )
  local err="${resp%.json}.stderr"
  if wsk action invoke "$action" -r -b "${args[@]}" \
        > "$resp.raw" 2> "$err"; then
    ws2_redact < "$err" > "$err.red" && mv -f "$err.red" "$err"
    mv -f "$resp.raw" "$resp"
    return 0
  else
    ws2_redact < "$err" > "$err.red" && mv -f "$err.red" "$err"
    [ -s "$resp.raw" ] && mv -f "$resp.raw" "$resp" || rm -f "$resp.raw"
    ws2_warn "wsk invoke returned non-zero (see $(basename "$err"))"
    return 1
  fi
}

# Convenience: run a real (side-effecting) command, or just echo it under DRY_RUN.
ws2_run() {
  if [ "${DRY_RUN:-0}" = 1 ]; then
    ws2_log "DRY_RUN: would run: $*"
    return 0
  fi
  "$@"
}

# If someone executes common.sh directly, just show what it is.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  cat <<EOF
common.sh -- shared library for the WS2 OpenWhisk workflow. Source it, do not run it.
  repo_root : $WS2_REPO_ROOT
  git_sha   : $WS2_GIT_SHA
  run_root  : $WS2_RUN_ROOT (machine-local, git-ignored)
See deployment/openwhisk/WS2_RUNBOOK.md for the two-terminal workflow.
EOF
fi
