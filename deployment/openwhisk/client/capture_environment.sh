#!/usr/bin/env bash
# Capture the workstation measurement environment for one OpenWhisk run.
#
# Writes a plaintext environment record to stdout (redirect to environment.txt).
# It NEVER prints credentials: wsk auth, API keys, namespace secrets, and
# credential files are redacted or reported only as "present/absent". Safe to
# commit the resulting file only after a manual secret review.
#
# Usage: deployment/openwhisk/client/capture_environment.sh [DB_PATH] > environment.txt
set -u

DB_PATH="${1:-pipeline/preparation/layout_rewriter/runs/test.db}"

section() { printf '\n## %s\n' "$1"; }
have()    { command -v "$1" >/dev/null 2>&1; }

printf '# OpenWhisk cold-start environment capture\n'
printf 'utc: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

section "repository"
if have git; then
  printf 'git_commit: %s\n' "$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  printf 'git_dirty: %s\n' "$([ -n "$(git status --porcelain 2>/dev/null)" ] && echo yes || echo no)"
fi

section "openwhisk"
if have wsk; then
  printf 'wsk_cli_version: %s\n' "$(wsk property get --cliversion 2>/dev/null | awk -F'\t' '{print $NF}')"
  # API build/version only; NEVER dump `wsk property get` wholesale (it contains AUTH).
  printf 'wsk_api_build: %s\n' "$(wsk property get --apibuild 2>/dev/null | awk -F'\t' '{print $NF}')"
  # credential presence only, never the value:
  if wsk property get --auth >/dev/null 2>&1; then printf 'wsk_auth: present (redacted)\n'; else printf 'wsk_auth: absent\n'; fi
else
  printf 'wsk_cli: absent\n'
fi
[ -f "${WHISK_PROPS:-$HOME/.wskprops}" ] && printf 'wskprops_file: present (redacted)\n' || printf 'wskprops_file: absent\n'

section "action_config (fill from run_config.json)"
printf 'action_memory_mb: %s\n' "${OW_ACTION_MEMORY_MB:-UNSET}"
printf 'action_timeout_ms: %s\n' "${OW_ACTION_TIMEOUT_MS:-UNSET}"
printf 'action_concurrency: %s\n' "${OW_ACTION_CONCURRENCY:-UNSET}"
printf 'action_image_digest: %s\n' "${OW_ACTION_IMAGE_DIGEST:-UNSET}"

section "host"
printf 'uname: %s\n' "$(uname -a)"
printf 'kernel: %s\n' "$(uname -r)"
if [ -r /proc/cpuinfo ]; then
  printf 'cpu_model: %s\n' "$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo | sed 's/^ //')"
  printf 'cpu_count: %s\n' "$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)"
fi
if have free; then printf 'memory: %s\n' "$(free -h | awk '/Mem:/{print $2}')"; fi

section "storage / db path"
if [ -e "$DB_PATH" ]; then
  printf 'db_path: %s\n' "$DB_PATH"
  printf 'db_device_inode: %s\n' "$(stat -c '%d:%i' "$DB_PATH" 2>/dev/null)"
  printf 'db_size_bytes: %s\n' "$(stat -c '%s' "$DB_PATH" 2>/dev/null)"
  if have findmnt; then
    printf 'db_mount: %s\n' "$(findmnt -no SOURCE,FSTYPE,OPTIONS -T "$DB_PATH" 2>/dev/null)"
  fi
  if have lsblk; then
    src="$(findmnt -no SOURCE -T "$DB_PATH" 2>/dev/null)"
    [ -n "$src" ] && printf 'storage_device: %s\n' "$(lsblk -no NAME,MODEL "$src" 2>/dev/null | head -1)"
  fi
else
  printf 'db_path: MISSING (%s)\n' "$DB_PATH"
fi

section "container engine"
for eng in docker podman; do
  if have "$eng"; then printf '%s_version: %s\n' "$eng" "$($eng --version 2>/dev/null)"; fi
done

section "placement (fill manually if distributed)"
printf 'controller_host: %s\n' "${OW_CONTROLLER_HOST:-UNSET}"
printf 'invoker_host: %s\n' "${OW_INVOKER_HOST:-UNSET}"
printf 'client_host: %s\n' "$(hostname 2>/dev/null)"

section "environment variables (secrets redacted)"
# Print only a safe allowlist; redact anything that looks like a secret.
env | grep -E '^(OW_|WHISK_|OPENWHISK_)' \
    | sed -E 's/(AUTH|TOKEN|KEY|SECRET|PASS(WORD)?)=.*/\1=REDACTED/I' \
    | grep -viE 'auth=|token=|apikey|api_key|secret|password' \
    || printf '(none)\n'

printf '\n# NOTE: review this file for secrets before committing.\n'
