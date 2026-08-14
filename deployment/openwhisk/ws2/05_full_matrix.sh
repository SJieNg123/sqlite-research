#!/usr/bin/env bash
# 05_full_matrix.sh -- safe, matrix-driven sequential executor.
#
# Consumes an EXPLICIT JSON matrix manifest (never a hard-coded matrix), validates
# every workload/strategy/seed/handle_mode against the frozen runtime artifact pin,
# builds a deterministic schedule, and executes it sequentially with resume
# support. It refuses duplicate completed cells and stops on a session break or
# identity mismatch. An explicit implementation gate blocks real invocation until
# full strategy support is in place.
WS2_HELP='Usage: 05_full_matrix.sh --matrix <manifest.json>

Validate + schedule (+ optionally execute) a measured matrix. Requires
04_feasibility PASS. See matrix.example.json for the manifest shape.
Identity inputs:
  OW_ACTION_NAME               (from 02_deploy metadata)
  OW_ARTIFACT_MANIFEST_SHA256  (required for real execution: identity gate)

IMPLEMENTATION GATE: real invocation happens ONLY when WS2_MATRIX_IMPL_READY=1 AND
every requested strategy is one the action implements (baseline, 2d, layers_5, 2e_K10).
Otherwise the stage validates the matrix, writes the schedule, and STOPS
(result=GATED) -- no invocation. (Note: which strategies may appear in a matrix at
all is a separate, stricter gate -- matrix validation above accepts only the
strategy_plans keys of the frozen replay pin.)

Resume: re-running skips a position ONLY when its existing response parses as a
real, identity-matching, non-synthetic handler response. A DRY_RUN placeholder is
discarded and re-invoked; a mismatching/malformed response is a hard stop. PASS
requires every scheduled position to have such a validated real response.
Env: DRY_RUN=1 (validate + schedule; synthetic responses go to an ISOLATED
dryrun_raw/ tree, never the measured raw/, and are never resumable),
WS2_FORCE=1 (rebuild the schedule AND purge any stale synthetic responses).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"

MATRIX=""
while [ $# -gt 0 ]; do
  case "$1" in
    --matrix) MATRIX="${2:-}"; shift 2 ;;
    *) ws2_die "unknown argument: $1 (see --help)" ;;
  esac
done
[ -n "$MATRIX" ] || ws2_die "--matrix <manifest.json> is required (see matrix.example.json)"
[ -f "$MATRIX" ] || ws2_die "matrix manifest not found: $MATRIX"

ws2_begin "05_full_matrix"
# NOTE: no ws2_guard_completed here -- this stage is resumable by design.

# --- gate: feasibility PASS ------------------------------------------------ #
FEAS_DIR="$WS2_RUN_DIR/04_feasibility"
ws2_stage_is_done "$FEAS_DIR" && [ "$(ws2_stage_status_value "$FEAS_DIR")" = PASS ] \
  || ws2_die "04_feasibility has not PASSed for this checkout. Run it first."

DEPLOY_META="$WS2_RUN_DIR/02_deploy/deploy_meta.json"
[ -f "$DEPLOY_META" ] || ws2_die "02_deploy metadata missing ($DEPLOY_META). Run 02_deploy first."
read -r OW_ACTION_NAME IMAGE_DIGEST < <(python3 - "$DEPLOY_META" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
# Bound image identity under the CURRENT key `immutable_image_digest` (the legacy
# `image_digest` key no longer exists in 02_deploy metadata).
print(m.get("action_name","sqlite-coldstart"), m.get("immutable_image_digest",""))
PY
)
# Fail closed BEFORE building/invoking the matrix: this exact digest is stamped as
# every request's expected_action_image_digest and re-checked against each response
# below. DRY_RUN may stand in a placeholder, mirroring MANIFEST_SHA.
if [ -z "$IMAGE_DIGEST" ] && [ "${DRY_RUN:-0}" = 1 ]; then
  IMAGE_DIGEST="dry-run/placeholder@sha256:0000000000000000000000000000000000000000000000000000000000000000"
fi
python3 "$WS2_DIR/image_identity.py" check-base "$IMAGE_DIGEST" \
  || ws2_die "02_deploy metadata has no pinned immutable_image_digest (got: '$IMAGE_DIGEST'). \
Every measured request needs the bound repo@sha256:<64hex> identity; redeploy with 02_deploy."
MANIFEST_SHA="${OW_ARTIFACT_MANIFEST_SHA256:-}"
if [ -z "$MANIFEST_SHA" ]; then
  [ "${DRY_RUN:-0}" = 1 ] && MANIFEST_SHA="0000000000000000000000000000000000000000000000000000000000000000" \
    || ws2_die "OW_ARTIFACT_MANIFEST_SHA256 is unset (identity gate needs it)."
fi

# --- validate the matrix against the frozen runtime artifact pin ----------- #
# Records the freeze of allowed combos; fails closed on any unknown combination.
VALIDATION="$WS2_STAGEDIR/matrix_validation.txt"
if ! python3 - "$WS2_PIN_JSON" "$MATRIX" > "$VALIDATION" 2>&1 <<'PY'; then
import json, sys
pin = json.load(open(sys.argv[1]))
m = json.load(open(sys.argv[2]))

required = ["schedule_seed", "workloads", "strategies", "seeds",
            "handle_modes", "first_operation_ids", "repetitions_per_cell"]
missing = [k for k in required if k not in m]
if missing:
    print("FAIL missing manifest keys:", missing); sys.exit(1)

# Allowed sets come straight from the frozen runtime artifact pin.
allowed_workloads = {pin["representative_workload"]["canonical_workload_id"]}
allowed_strategies = set(pin["strategy_plans"].keys())          # {baseline, 2d}
allowed_seeds = {e["seed"] for e in pin["representative_workload"]["seed_family"]}
allowed_handles = set(pin["invocation_plan"]["handle_modes"])   # {warm, standalone}

def check(name, values, allowed):
    bad = [v for v in values if v not in allowed]
    if bad:
        print("FAIL %s not in runtime artifact pin: %s (allowed: %s)"
              % (name, bad, sorted(allowed)))
        return False
    print("PASS %s: %s" % (name, values))
    return True

ok = True
ok &= check("workloads", m["workloads"], allowed_workloads)
ok &= check("strategies", m["strategies"], allowed_strategies)
ok &= check("seeds", m["seeds"], allowed_seeds)
ok &= check("handle_modes", m["handle_modes"], allowed_handles)
if "baseline" not in m["strategies"]:
    print("FAIL strategies must include 'baseline' (paired arm)"); ok = False
if int(m["repetitions_per_cell"]) < 1:
    print("FAIL repetitions_per_cell must be >= 1"); ok = False
if not ok:
    sys.exit(1)
combos = (len(m["workloads"]) * len(m["seeds"]) * len(m["handle_modes"])
          * len(m["first_operation_ids"]) * (len(m["strategies"]) - 1)
          * int(m["repetitions_per_cell"]))
print("VALID matrix: %d paired cells" % combos)
PY
  cat "$VALIDATION" >&2
  ws2_mark_status "$WS2_STAGEDIR" done FAIL
  ws2_die "matrix validation failed (see $VALIDATION)."
fi
cat "$VALIDATION" >&2

# Extract the flattened, validated fields for build_schedule.
read -r SCHED_SEED WORKLOADS STRATEGIES SEEDS HANDLES FIRSTOPS REPS < <(python3 - "$MATRIX" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
def csv(k): return ",".join(str(x) for x in m[k])
print(m["schedule_seed"], csv("workloads"), csv("strategies"),
      csv("seeds"), csv("handle_modes"), csv("first_operation_ids"),
      m["repetitions_per_cell"])
PY
)

# Targets for build_schedule are the non-baseline strategies (baseline is the
# implicit paired arm).
TARGETS="$(python3 - "$MATRIX" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
t = [s for s in m["strategies"] if s != "baseline"]
print(",".join(t) if t else "2d")
PY
)"

RUN_CONFIG_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_config_sha256"])' "$WS2_PIN_JSON")"
SCHED="$WS2_STAGEDIR/schedule.json"
RAW="$WS2_STAGEDIR/raw"; mkdir -p "$RAW"
# DRY_RUN synthetic responses are written HERE, never into the measured raw/ tree,
# so a real run can never resume over them.
DRYRUN_RAW="$WS2_STAGEDIR/dryrun_raw"

# WS2_FORCE: rebuild the schedule (below) AND guarantee no stale DRY_RUN synthetic
# response survives into this real execution -- purge synthetic responses from the
# measured raw/ tree and drop the isolated dry-run tree entirely. Synthetic output
# is never silently preserved.
if [ "${WS2_FORCE:-0}" = 1 ]; then
  python3 "$WS2_DIR/response_gate.py" purge-synthetic "$RAW" >&2
  rm -rf "$DRYRUN_RAW"
fi

# --- deterministic schedule (built once; resume reuses it) ----------------- #
if [ -f "$SCHED" ] && [ "${WS2_FORCE:-0}" != 1 ]; then
  ws2_log "reusing existing schedule (resume): $SCHED"
else
  python3 "$WS2_OW_DIR/client/build_schedule.py" \
    --out "$SCHED" \
    --schedule-seed "$SCHED_SEED" \
    --workloads "$WORKLOADS" \
    --seeds "$SEEDS" \
    --first-ops "$FIRSTOPS" \
    --handle-modes "$HANDLES" \
    --targets "$TARGETS" \
    --repetitions "$REPS" \
    --run-config-sha256 "$RUN_CONFIG_SHA" \
    --artifact-manifest-sha256 "$MANIFEST_SHA" \
    --action-image-digest "$IMAGE_DIGEST" >/dev/null
  ws2_log "schedule built -> $SCHED"
fi

# Explode requests (idempotent; identity de-dup enforced).
python3 - "$SCHED" "$RAW" <<'PY'
import json, os, sys
s = json.load(open(sys.argv[1])); raw = sys.argv[2]
seen = set()
for inv in s["invocations"]:
    cell = (inv["pair_id"], inv["arm"])
    if cell in seen: raise SystemExit("duplicate pair/arm cell in schedule: %s" % (cell,))
    seen.add(cell)
    p = os.path.join(raw, "req_%06d.json" % inv["schedule_position"])
    if not os.path.exists(p):
        json.dump(inv, open(p, "w"), indent=2, sort_keys=True)
print("requests ready: %d invocations" % len(s["invocations"]))
PY

# --- IMPLEMENTATION GATE --------------------------------------------------- #
# The action implements baseline + 2d + layers_5 + 2e_K10 (Batch 2). Any strategy
# outside this set blocks real invocation. Validation + scheduling above have
# already run. Keep this set in sync with action/main.py SUPPORTED_STRATEGIES.
UNSUPPORTED="$(python3 - "$MATRIX" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
impl = {"baseline", "2d", "layers_5", "2e_K10"}
bad = [s for s in m["strategies"] if s not in impl]
print(",".join(bad))
PY
)"
if [ "${WS2_MATRIX_IMPL_READY:-0}" != 1 ] || [ -n "$UNSUPPORTED" ]; then
  {
    echo "IMPLEMENTATION GATE: real matrix invocation is blocked."
    echo "  WS2_MATRIX_IMPL_READY=${WS2_MATRIX_IMPL_READY:-0} (must be 1 to execute)"
    [ -n "$UNSUPPORTED" ] && echo "  unsupported strategies requested: $UNSUPPORTED (action implements baseline,2d,layers_5,2e_K10)"
    echo "  Validated matrix + deterministic schedule are ready at: $SCHED"
    echo "  No invocation performed."
  } | ws2_atomic_write "$WS2_STAGEDIR/gate.txt"
  cat "$WS2_STAGEDIR/gate.txt" >&2
  ws2_mark_status "$WS2_STAGEDIR" done GATED
  ws2_log "05_full_matrix: validated + scheduled, stopped at implementation gate."
  exit 0
fi

if [ "${DRY_RUN:-0}" = 1 ]; then
  # Synthetic responses go into an ISOLATED tree, never into the measured raw/, so
  # a later real run cannot mistake them for completed measurements.
  mkdir -p "$DRYRUN_RAW"
  for req in $(ls "$RAW"/req_*.json | sort); do
    pos="$(basename "$req" .json | sed 's/req_//')"
    ws2_invoke "$OW_ACTION_NAME" "$req" "$DRYRUN_RAW/resp_${pos}.json" || true
  done
  ws2_log "DRY_RUN: synthetic responses isolated under $DRYRUN_RAW (never resumable as measured); no result gate."
  ws2_mark_status "$WS2_STAGEDIR" done DRYRUN
  exit 0
fi

# --- client-side pacing + transient-retry configuration -------------------- #
# Apache OpenWhisk Standalone rate-limits to ~60 requests/minute. We pace BETWEEN
# complete pairs (never between a pair's two arms) so the sustained rate stays
# safely under the limit, and we retry TRANSIENT transport/rate-limit failures at
# the SAME schedule position with bounded backoff. Both are client-side controls:
# a shell sleep between invocations never enters the measured action timings
# (first_query_us / deliver_us / open_us are computed inside the handler).
WS2_INTER_PAIR_DELAY_SEC="${WS2_INTER_PAIR_DELAY_SEC:-2.2}"
WS2_MAX_INVOKE_RETRIES="${WS2_MAX_INVOKE_RETRIES:-5}"
WS2_RETRY_BACKOFF_BASE_SEC="${WS2_RETRY_BACKOFF_BASE_SEC:-5}"
WS2_RETRY_BACKOFF_CAP_SEC="${WS2_RETRY_BACKOFF_CAP_SEC:-60}"
LAST_INVOKED_PAIR=""
{
  printf 'inter_pair_delay_sec: %s\n' "$WS2_INTER_PAIR_DELAY_SEC"
  printf 'max_invoke_retries: %s\n' "$WS2_MAX_INVOKE_RETRIES"
  printf 'retry_backoff_base_sec: %s\n' "$WS2_RETRY_BACKOFF_BASE_SEC"
  printf 'retry_backoff_cap_sec: %s\n' "$WS2_RETRY_BACKOFF_CAP_SEC"
  printf 'note: pacing + backoff are client-side and OUTSIDE the measured action; they never enter first_query_us/deliver_us/open_us.\n'
} | ws2_atomic_write "$WS2_STAGEDIR/pacing.txt"
ws2_log "pacing: inter_pair_delay=${WS2_INTER_PAIR_DELAY_SEC}s max_retries=${WS2_MAX_INVOKE_RETRIES} backoff_base=${WS2_RETRY_BACKOFF_BASE_SEC}s cap=${WS2_RETRY_BACKOFF_CAP_SEC}s (client-side, outside measurement)"

# Bounded retry/backoff for TRANSIENT invocation errors (rate-limit/transport).
# Retries the SAME position/request identity; never advances or reorders; never
# leaves a completed resp_*.json unless a real handler response was written; keeps
# each transient stderr for provenance. Returns:
#   0 -> a response file was produced (real or handler error envelope; classify it)
#   1 -> a NON-transient invocation failure (leave it to the identity classifier)
#   2 -> transient error persisted after WS2_MAX_INVOKE_RETRIES (caller hard-stops)
ws2_invoke_with_retry() {
  local action="$1" req="$2" resp="$3"
  local err="${resp%.json}.stderr" attempt=1 backoff
  while : ; do
    if ws2_invoke "$action" "$req" "$resp"; then
      return 0
    fi
    # Invocation failed. Transient transport/rate-limit vs a real failure?
    if [ -f "$err" ] && python3 "$WS2_DIR/response_gate.py" is-transient "$err" >/dev/null 2>&1; then
      # Preserve the transient stderr for provenance; never keep a partial resp
      # (no completed response until a real handler response exists).
      cp -f "$err" "${resp%.json}.transient.${attempt}.stderr" 2>/dev/null || true
      rm -f "$resp"
      if [ "$attempt" -ge "$WS2_MAX_INVOKE_RETRIES" ]; then
        ws2_warn "transient invocation error persisted after $attempt attempt(s): $(basename "$req")"
        return 2
      fi
      backoff=$(( WS2_RETRY_BACKOFF_BASE_SEC * (1 << (attempt - 1)) ))
      [ "$backoff" -gt "$WS2_RETRY_BACKOFF_CAP_SEC" ] && backoff="$WS2_RETRY_BACKOFF_CAP_SEC"
      ws2_warn "transient invocation error (attempt $attempt/$WS2_MAX_INVOKE_RETRIES); backing off ${backoff}s and retrying the SAME position."
      sleep "$backoff"
      attempt=$((attempt + 1))
      continue
    fi
    # Non-transient failure: leave any response for the classifier to reject.
    return 1
  done
}

# --- sequential execution with resume + session/identity stop -------------- #
LEDGER="$WS2_STAGEDIR/completed_cells.tsv"; : >> "$LEDGER"
for req in $(ls "$RAW"/req_*.json | sort); do
  pos="$(basename "$req" .json | sed 's/req_//')"
  resp="$RAW/resp_${pos}.json"
  if [ -f "$resp" ]; then
    # Never skip on mere existence: parse + validate the existing response. Only a
    # real, identity-matching, non-synthetic response may be resumed.
    if cls="$(python3 "$WS2_DIR/response_gate.py" classify "$req" "$resp" "$IMAGE_DIGEST" 2>>"$WS2_STAGEDIR/exec_log.txt")"; then
      ws2_log "resume: position $pos has a validated real response ($cls); skipping."
      continue
    else
      rc=$?
      if [ "$rc" = 10 ]; then
        # DRY_RUN synthetic contamination in the measured tree: discard + invoke.
        ws2_warn "position $pos holds a DRY_RUN synthetic response ($cls); discarding and invoking for real."
        rm -f "$resp"
      else
        ws2_warn "position $pos existing response is not a valid resumable measurement ($cls); stopping per protocol."
        ws2_mark_status "$WS2_STAGEDIR" failed FAIL
        ws2_die "stopped: existing response at position $pos failed validation (see exec_log.txt)."
      fi
    fi
  fi
  # Inter-pair pacing (client-side; OUTSIDE the measured action). Keep a pair's two
  # arms adjacent -- pace only when a NEW pair begins, so within-pair adjacency and
  # the frozen AB/BA order are preserved. Applied only before a real invocation.
  cur_pair="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pair_id",""))' "$req")"
  if [ -n "$LAST_INVOKED_PAIR" ] && [ "$cur_pair" != "$LAST_INVOKED_PAIR" ]; then
    ws2_log "inter-pair pacing: sleeping ${WS2_INTER_PAIR_DELAY_SEC}s before pair '$cur_pair' (<=60 req/min)."
    sleep "$WS2_INTER_PAIR_DELAY_SEC"
  fi

  ws2_log "invoke position $pos (sequential)"
  irc=0
  ws2_invoke_with_retry "$OW_ACTION_NAME" "$req" "$resp" || irc=$?
  if [ "$irc" = 2 ]; then
    # TRANSIENT (rate-limit/transport) error, not an identity/session violation.
    # The schedule was NOT advanced and no completed resp_${pos}.json was written.
    ws2_mark_status "$WS2_STAGEDIR" failed FAIL
    ws2_die "stopped: TRANSIENT invocation error (e.g. OpenWhisk rate limit) persisted at position \
$pos after $WS2_MAX_INVOKE_RETRIES retries. This is NOT an identity/session violation. No \
resp_${pos}.json was created; re-run 05 to resume from this exact position."
  fi
  [ "$irc" = 1 ] && ws2_warn "position $pos invocation returned non-zero (non-transient); the classifier will evaluate the response."
  LAST_INVOKED_PAIR="$cur_pair"

  # Per-cell identity + session-break enforcement (stop-the-run on violation).
  if ! python3 - "$req" "$resp" "$IMAGE_DIGEST" "$LEDGER" "$WS2_DIR" >> "$WS2_STAGEDIR/exec_log.txt" 2>&1 <<'PY'; then
import json, os, sys
sys.path.insert(0, sys.argv[5])           # WS2_DIR -> shared response_gate
from response_gate import classify_response
req = json.load(open(sys.argv[1]))
resp_path = sys.argv[2]
if not os.path.exists(resp_path):
    # No evaluable response: an invocation/runtime error, NOT an identity/session
    # violation (a transient one would have been retried/handled above).
    print("STOP: no response for %s (invocation/runtime error, not identity/session)"
          % req.get("request_id")); sys.exit(1)
try:
    resp = json.load(open(resp_path))
except ValueError as e:
    print("STOP: response for %s is not valid JSON (invocation/runtime error): %s"
          % (req.get("request_id"), e)); sys.exit(1)
image = sys.argv[3]; ledger = sys.argv[4]

# A completed cell requires a real handler response whose identity matches the
# request AND the deployed image digest (rejects synthetic/malformed/foreign).
status, reason = classify_response(req, resp, image)
if status != "valid":
    print("STOP: %s (%s)" % (reason, status)); sys.exit(1)

# Warm-session protocol: the real response's process identity is `process_uuid`
# (session.identity_fields()). Reject a completed cell reappearing under a
# different warm process. Observation key INCLUDES strategy.
key = "\t".join(str(req.get(k)) for k in
                ("run_config_sha256", "workload", "seed", "first_operation_id",
                 "handle_mode", "pair_id", "strategy"))
proc = resp.get("process_uuid")
if not proc:
    print("STOP: real response for %s lacks process_uuid (warm-session identity missing)"
          % req.get("request_id")); sys.exit(1)
proc = str(proc)
seen = {}
if os.path.exists(ledger):
    for line in open(ledger):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2:
            seen[parts[0]] = parts[1]
if key in seen and seen[key] != proc:
    print("STOP: duplicate completed cell with different process_uuid (session break): %s" % key)
    sys.exit(1)
with open(ledger, "a") as f:
    f.write("%s\t%s\n" % (key, proc))
print("OK", req["request_id"], "process_uuid", proc)
PY
    ws2_warn "identity/session violation at position $pos; stopping per protocol."
    ws2_mark_status "$WS2_STAGEDIR" failed FAIL
    ws2_die "stopped at position $pos: response failed identity/session validation \
(see exec_log.txt for the exact STOP reason: identity mismatch, session break, or an \
unrecoverable invocation error)."
  fi
done

# --- completion gate ------------------------------------------------------- #
# PASS is never granted merely because resp_*.json files exist. Every scheduled
# position must have a validated, non-synthetic, identity-matching real response.
if ! python3 "$WS2_DIR/response_gate.py" verify-complete "$RAW" "$IMAGE_DIGEST" \
      >> "$WS2_STAGEDIR/exec_log.txt" 2>&1; then
  ws2_mark_status "$WS2_STAGEDIR" failed FAIL
  ws2_die "completion gate failed: not every position has a validated non-synthetic real response (see exec_log.txt)."
fi

ws2_mark_status "$WS2_STAGEDIR" done PASS
ws2_log "05_full_matrix executed sequentially; raw responses in $RAW."
