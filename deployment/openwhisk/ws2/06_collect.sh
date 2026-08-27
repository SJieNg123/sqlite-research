#!/usr/bin/env bash
# 06_collect.sh -- package a self-describing evidence bundle for transfer back to
# Workstation1. Bundles raw requests/responses, an environment report, both Git
# SHAs (sqlite-research + OpenWhisk source repo), the frozen DB/trace/plan/manifest
# hashes, the image digest, run-config SHA, action metadata, and a validity
# summary into a single tar.gz. It never invokes anything.
WS2_HELP='Usage: 06_collect.sh [--openwhisk-sha <SHA>]

Packages the machine-local run tree for this checkout into a tar.gz under
_runs/<sha>/06_collect/. Pulls the OpenWhisk source repo SHA from --openwhisk-sha
/ OW_REPO_SHA, or from the 00_preflight report if present. Auth is never included
(environment capture redacts secrets). Never sudo.
Env: DRY_RUN=1 (list what would be packaged, do not write the tarball).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"

OW_REPO_SHA="${OW_REPO_SHA:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --openwhisk-sha) OW_REPO_SHA="${2:-}"; shift 2 ;;
    *) ws2_die "unknown argument: $1 (see --help)" ;;
  esac
done

ws2_begin "06_collect"
ws2_guard_completed "$WS2_STAGEDIR"

# Recover the OpenWhisk source repo SHA from the preflight report if not supplied.
PRE_REPORT="$WS2_RUN_DIR/00_preflight/preflight_report.txt"
if [ -z "$OW_REPO_SHA" ] && [ -f "$PRE_REPORT" ]; then
  OW_REPO_SHA="$(awk -F': ' '/^openwhisk_repo_sha:/{print $2; exit}' "$PRE_REPORT")"
fi

STAGE="$WS2_STAGEDIR"
MANIFEST="$STAGE/bundle_manifest.json"
VALIDITY="$STAGE/validity_summary.txt"

# --- environment report (redacted) ----------------------------------------- #
ENVREPORT="$STAGE/environment.txt"
if [ -x "$WS2_OW_DIR/client/capture_environment.sh" ] || [ -f "$WS2_OW_DIR/client/capture_environment.sh" ]; then
  ( cd "$WS2_REPO_ROOT" && bash "$WS2_OW_DIR/client/capture_environment.sh" \
      "$WS2_DB_REL" 2>/dev/null ) | ws2_redact | ws2_atomic_write "$ENVREPORT" || \
    printf 'environment capture failed\n' | ws2_atomic_write "$ENVREPORT"
else
  printf 'capture_environment.sh not found\n' | ws2_atomic_write "$ENVREPORT"
fi

# --- validity summary across stages ---------------------------------------- #
{
  printf '# WS2 validity summary\nutc: %s\ngit_sha: %s\n\n' "$(ws2_ts)" "$WS2_GIT_SHA"
  for st in 00_preflight 01_build_image 02_deploy 03_diagnostic 04_feasibility 05_full_matrix; do
    d="$WS2_RUN_DIR/$st"
    if [ -f "$d/STATUS" ]; then
      printf '%-16s %s\n' "$st" "$(ws2_stage_status_value "$d" 2>/dev/null || echo '?')"
    else
      printf '%-16s %s\n' "$st" "not-run"
    fi
  done
} | ws2_atomic_write "$VALIDITY"

# --- bundle manifest (identities) ------------------------------------------ #
DEPLOY_META="$WS2_RUN_DIR/02_deploy/deploy_meta.json"
BUILD_META="$WS2_RUN_DIR/01_build_image/build_meta.json"
SCHED_JSON="$WS2_RUN_DIR/05_full_matrix/schedule.json"
python3 - "$WS2_PIN_JSON" "$WS2_GIT_SHA" "${OW_REPO_SHA:-unknown}" \
        "${BUILD_META:-}" "${DEPLOY_META:-}" "$WS2_EXPECTED_DB_SHA" "${SCHED_JSON:-}" > "$MANIFEST.tmp" <<'PY'
import json, os, sys
pin_path, git_sha, ow_sha, build_meta, deploy_meta, db_sha, sched_path = sys.argv[1:8]
pin = json.load(open(pin_path))
def load(p): return json.load(open(p)) if p and os.path.exists(p) else {}
b, d = load(build_meta), load(deploy_meta)
out = {
    "sqlite_research_git_sha": git_sha,
    "openwhisk_source_repo_sha": ow_sha,
    "db": {"path": pin["database"]["path"], "sha256": db_sha,
           "page_count": pin["database"]["page_count"]},
    "classifier_sha256": pin["classifier"]["sha256"],
    "plan_2d_sha256": pin["strategy_plans"]["2d"]["sha256"],
    "native_manifest": pin.get("provenance", {}).get("manifest"),
    "run_config_sha256": pin["run_config_sha256"],
    "seed_traces": {str(e["seed"]): e["trace_sha256"]
                    for e in pin["representative_workload"]["seed_family"]},
    "image": {"repo_digest": b.get("repo_digest"), "image_id": b.get("image_id"),
              "base_runtime": b.get("base_runtime")},
    "action": {"name": d.get("action_name"), "image_digest": d.get("immutable_image_digest"),
               "memory_mb": d.get("memory_mb"), "timeout_ms": d.get("timeout_ms"),
               "concurrency": d.get("concurrency")},
}
# Self-describe the ONE Stage-05 schedule that this bundle packages: the single
# campaign (or flat) fingerprint, the run_config identity ACTUALLY stamped on every
# request (schedule.identity, not necessarily the pin's primary run_config_sha256),
# and the paired counts. A block-union campaign also records its per-block summary.
# This is what binds the raw evidence tree to one fingerprint in one bundle.
s = load(sched_path)
if s:
    sch = {
        "schema_version": s.get("schema_version"),
        "campaign": s.get("campaign"),
        "schedule_seed": s.get("schedule_seed"),
        "matrix_fingerprint": s.get("matrix_fingerprint"),
        "run_config_sha256": (s.get("identity") or {}).get("run_config_sha256"),
        "counts": s.get("counts"),
    }
    if "blocks" in s:
        sch["blocks"] = [{"id": bl.get("id"),
                          "pairs": (len(bl.get("workloads", [])) * len(bl.get("seeds", []))
                                    * len(bl.get("first_operation_ids", []))
                                    * len(bl.get("handle_modes", []))
                                    * len(bl.get("targets", [])) * int(bl.get("repetitions", 0)))}
                         for bl in s["blocks"]]
    out["schedule"] = sch
print(json.dumps(out, indent=2, sort_keys=True))
PY
mv -f "$MANIFEST.tmp" "$MANIFEST"

# --- refuse to package synthetic DRY_RUN output as measured evidence ------- #
# A DRY_RUN response (`_dry_run: true`) is a placeholder, not a measurement. If any
# survives in the run tree, the bundle would misrepresent synthetic output as real
# evidence -- fail closed (in DRY_RUN listing mode too, so the contamination is loud).
SYNSCAN="$STAGE/synthetic_scan.txt"
if ! python3 "$WS2_DIR/response_gate.py" scan-synthetic \
      "$WS2_RUN_DIR/03_diagnostic" "$WS2_RUN_DIR/04_feasibility" "$WS2_RUN_DIR/05_full_matrix" \
      > "$SYNSCAN" 2>&1; then
  cat "$SYNSCAN" >&2
  ws2_mark_status "$STAGE" failed FAIL
  ws2_die "refusing to package: DRY_RUN synthetic (_dry_run:true) responses found in the run tree; \
they are not measured evidence. Re-run the measured stages (WS2_FORCE=1) and collect again."
fi

# --- package -------------------------------------------------------------- #
TARBALL="$STAGE/ws2_bundle_${WS2_GIT_SHA_SHORT}_$(ws2_ts | tr -d ':-').tar.gz"
# Collect the machine-local run tree for this checkout, excluding this stage's own
# in-progress tarballs. Paths are relative to the run root for a clean archive.
INCLUDE=(identity.json 00_preflight 01_build_image 02_deploy 03_diagnostic 04_feasibility 05_full_matrix)
COLLECT=()
for i in "${INCLUDE[@]}"; do [ -e "$WS2_RUN_DIR/$i" ] && COLLECT+=("$WS2_GIT_SHA_SHORT/$i"); done
COLLECT+=("$WS2_GIT_SHA_SHORT/06_collect/bundle_manifest.json"
          "$WS2_GIT_SHA_SHORT/06_collect/validity_summary.txt"
          "$WS2_GIT_SHA_SHORT/06_collect/environment.txt")

if [ "${DRY_RUN:-0}" = 1 ]; then
  ws2_log "DRY_RUN: would package these paths (root $WS2_RUN_ROOT):"
  printf '  %s\n' "${COLLECT[@]}" >&2
  ws2_log "DRY_RUN: no tarball written."
  ws2_mark_status "$STAGE" done DRYRUN
  exit 0
fi

ws2_require_cmd tar
tar -czf "$TARBALL" -C "$WS2_RUN_ROOT" "${COLLECT[@]}" \
  || { ws2_mark_status "$STAGE" failed FAIL; ws2_die "tar failed"; }
BUNDLE_SHA="$(ws2_sha256 "$TARBALL")"
printf '%s  %s\n' "$BUNDLE_SHA" "$(basename "$TARBALL")" | ws2_atomic_write "$TARBALL.sha256"

ws2_mark_status "$STAGE" done PASS
ws2_log "COLLECT OK -> $TARBALL"
ws2_log "sha256: $BUNDLE_SHA"
ws2_log "Transfer this tar.gz (and its .sha256) back to Workstation1."
