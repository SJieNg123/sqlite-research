#!/usr/bin/env bash
# 03_diagnostic.sh -- one DIAGNOSTIC invocation to prove the runtime can cold the
# reference DB with non-root eviction. This is the feasibility gate from
# README/PROTOCOL step 3, not a performance measurement.
#
# Canonical YCSB-C, seed 1, baseline, warm handle, cold_reset=true,
# diagnostic_mode=true. Saves the full request + response JSON and fails unless
# the artifact, identity, oracle, and cold-data gates pass -- specifically
# requiring resident_interiors_after_reset == 0.
WS2_HELP='Usage: 03_diagnostic.sh

Single diagnostic invocation (no measurement). Requires 02_deploy completed.
Identity inputs (from prior stages):
  OW_ACTION_NAME               (default sqlite-coldstart)
  artifact_manifest_sha256     (read from 02_deploy metadata; the identity gate
                                needs the sha256 of the baked artifacts.json)
The image digest + manifest sha are read from 02_deploy metadata; workload/seed/
run-config from the frozen pin. Set OW_ARTIFACT_MANIFEST_SHA256 only to OVERRIDE
the metadata value. Writes request+response+gate report under _runs/<sha>/03_diagnostic/.
Env: DRY_RUN=1 (build the request, synthesize a response, skip gate enforcement),
WS2_FORCE=1 (redo).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"
[ $# -eq 0 ] || ws2_die "unexpected argument: $1 (see --help)"

ws2_begin "03_diagnostic"
ws2_guard_completed "$WS2_STAGEDIR"

# --- gate: deploy metadata ------------------------------------------------- #
DEPLOY_META="$WS2_RUN_DIR/02_deploy/deploy_meta.json"
[ -f "$DEPLOY_META" ] || ws2_die "deploy metadata missing ($DEPLOY_META). Run 02_deploy first."
read -r OW_ACTION_NAME IMAGE_DIGEST META_MANIFEST_SHA < <(python3 - "$DEPLOY_META" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(m.get("action_name","sqlite-coldstart"), m.get("immutable_image_digest",""),
      m.get("artifact_manifest_sha256",""))
PY
)
OW_ACTION_NAME="${OW_ACTION_NAME_OVERRIDE:-$OW_ACTION_NAME}"
# Manifest sha comes from 02_deploy metadata; env var is only an optional override.
MANIFEST_SHA="${OW_ARTIFACT_MANIFEST_SHA256:-$META_MANIFEST_SHA}"
if [ -z "$MANIFEST_SHA" ] && [ "${DRY_RUN:-0}" != 1 ]; then
  ws2_die "no artifact_manifest_sha256 in 02_deploy metadata and \
OW_ARTIFACT_MANIFEST_SHA256 unset; the identity gate needs the sha256 of the \
artifacts.json baked into the deployed image."
fi

REQ="$WS2_STAGEDIR/request.json"
RESP="$WS2_STAGEDIR/response.json"

# --- build the diagnostic request from the frozen pin ---------------------- #
python3 - "$WS2_PIN_JSON" "$IMAGE_DIGEST" "${MANIFEST_SHA:-DRYRUN}" "$WS2_RUN_ID" <<'PY' | ws2_atomic_write "$REQ"
import json, sys
pin, image, manifest, run_id = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
p = json.load(open(pin))
req = {
    "request_id": "diag-%s" % run_id,
    "workload": p["representative_workload"]["canonical_workload_id"],
    "strategy": "baseline",
    "seed": 1,
    "first_operation_id": 0,
    "handle_mode": "warm",
    "diagnostic_mode": True,
    "cold_reset": True,
    "pair_id": "",
    "repetition_id": 0,
    "schedule_position": 0,
    "schedule_seed": 0,
    "run_config_sha256": p["run_config_sha256"],
    "expected_artifact_manifest_hash": manifest,
    "expected_action_image_digest": image,
}
print(json.dumps(req, indent=2, sort_keys=True))
PY
ws2_log "diagnostic request -> $REQ"

# --- invoke ---------------------------------------------------------------- #
INVOKE_RC=0
ws2_invoke "$OW_ACTION_NAME" "$REQ" "$RESP" || INVOKE_RC=1

if [ "${DRY_RUN:-0}" = 1 ]; then
  ws2_log "DRY_RUN: request built + synthetic response saved; gates NOT enforced."
  ws2_mark_status "$WS2_STAGEDIR" done DRYRUN
  exit 0
fi

# --- invocation / runtime failure (no evaluable response) ------------------ #
# Distinguish an invoke/runtime failure from a gate failure: if the invocation
# produced no response.json, or one that is not valid JSON, the runtime never
# returned a record to evaluate. Report THAT -- do NOT claim the cold-reset gate
# failed (which would falsely blame the container's eviction path).
if [ "$INVOKE_RC" -ne 0 ] && { [ ! -s "$RESP" ] || ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$RESP" >/dev/null 2>&1; }; then
  ws2_mark_status "$WS2_STAGEDIR" done FAIL
  ws2_die "DIAGNOSTIC FAIL: the invocation did not return an evaluable response \
(runtime/invocation error, see $(basename "${RESP%.json}.stderr")). This is NOT a \
cold-reset gate failure; fix the deploy/runtime and rerun. The cold-data gate was \
never reached."
fi
[ "$INVOKE_RC" -eq 0 ] || ws2_warn "invocation returned non-zero but a response is present; evaluating it."

# --- gate evaluation ------------------------------------------------------- #
REPORT="$WS2_STAGEDIR/gate_report.txt"
if python3 - "$RESP" > "$REPORT" 2>&1 <<'PY'; then
import json, sys
r = json.load(open(sys.argv[1]))
fails = []
def gate(name, ok, detail=""):
    print(("PASS" if ok else "FAIL"), name, detail)
    if not ok: fails.append(name)

stage = r.get("error_stage")
gate("artifact", r.get("error") is None and stage != "artifact_validation",
     "error_stage=%r" % stage)
gate("identity", stage != "identity", "error_stage=%r" % stage)
gate("oracle", r.get("oracle_passed") is True,
     "oracle_passed=%r" % r.get("oracle_passed"))
ri = r.get("resident_interiors_after_reset")
gate("cold_data.resident_interiors_after_reset==0", ri == 0,
     "resident_interiors_after_reset=%r cold_threshold_passed=%r"
     % (ri, r.get("cold_threshold_passed")))
print("---")
if fails:
    print("VERDICT: FAIL", fails); sys.exit(1)
print("VERDICT: PASS"); sys.exit(0)
PY
  cat "$REPORT" >&2
  ws2_mark_status "$WS2_STAGEDIR" done PASS
  ws2_log "DIAGNOSTIC PASS (non-root cold eviction works) -> $REPORT"
else
  cat "$REPORT" >&2
  ws2_mark_status "$WS2_STAGEDIR" done FAIL
  ws2_die "DIAGNOSTIC FAIL: a gate did not pass (see $REPORT). This runtime may keep \
the DB warm; adjust isolation per README step 3, or record it cannot produce cold data."
fi
