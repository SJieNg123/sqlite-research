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
every requested strategy is one the action implements (baseline, 2d). Otherwise
the stage validates the matrix, writes the schedule, and STOPS (result=GATED) --
no invocation.

Resume: re-running skips positions whose raw response already exists; a completed
cell that reappears with a different identity is a hard stop.
Env: DRY_RUN=1 (validate + schedule, synthesize responses, no gate on results),
WS2_FORCE=1 (rebuild the schedule from scratch).'

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
# The action implements baseline + 2d only. Until full strategy support lands,
# real invocation is blocked. Validation + scheduling above have already run.
UNSUPPORTED="$(python3 - "$MATRIX" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
impl = {"baseline", "2d"}
bad = [s for s in m["strategies"] if s not in impl]
print(",".join(bad))
PY
)"
if [ "${WS2_MATRIX_IMPL_READY:-0}" != 1 ] || [ -n "$UNSUPPORTED" ]; then
  {
    echo "IMPLEMENTATION GATE: real matrix invocation is blocked."
    echo "  WS2_MATRIX_IMPL_READY=${WS2_MATRIX_IMPL_READY:-0} (must be 1 to execute)"
    [ -n "$UNSUPPORTED" ] && echo "  unsupported strategies requested: $UNSUPPORTED (action implements baseline,2d)"
    echo "  Validated matrix + deterministic schedule are ready at: $SCHED"
    echo "  No invocation performed."
  } | ws2_atomic_write "$WS2_STAGEDIR/gate.txt"
  cat "$WS2_STAGEDIR/gate.txt" >&2
  ws2_mark_status "$WS2_STAGEDIR" done GATED
  ws2_log "05_full_matrix: validated + scheduled, stopped at implementation gate."
  exit 0
fi

if [ "${DRY_RUN:-0}" = 1 ]; then
  for req in $(ls "$RAW"/req_*.json | sort); do
    pos="$(basename "$req" .json | sed 's/req_//')"
    ws2_invoke "$OW_ACTION_NAME" "$req" "$RAW/resp_${pos}.json" || true
  done
  ws2_log "DRY_RUN: schedule executed with synthetic responses; no result gate."
  ws2_mark_status "$WS2_STAGEDIR" done DRYRUN
  exit 0
fi

# --- sequential execution with resume + session/identity stop -------------- #
LEDGER="$WS2_STAGEDIR/completed_cells.tsv"; : >> "$LEDGER"
for req in $(ls "$RAW"/req_*.json | sort); do
  pos="$(basename "$req" .json | sed 's/req_//')"
  resp="$RAW/resp_${pos}.json"
  if [ -f "$resp" ]; then
    ws2_log "resume: position $pos already has a response; skipping."
    continue
  fi
  ws2_log "invoke position $pos (sequential)"
  ws2_invoke "$OW_ACTION_NAME" "$req" "$resp" || ws2_warn "position $pos non-zero; kept"

  # Per-cell identity + session-break enforcement (stop-the-run on violation).
  if ! python3 - "$req" "$resp" "$IMAGE_DIGEST" "$LEDGER" >> "$WS2_STAGEDIR/exec_log.txt" 2>&1 <<'PY'; then
import json, os, sys
req = json.load(open(sys.argv[1]))
resp = json.load(open(sys.argv[2])) if os.path.exists(sys.argv[2]) else {}
image = sys.argv[3]; ledger = sys.argv[4]

if not isinstance(resp, dict):
    print("STOP: non-dict response for", req["request_id"]); sys.exit(1)

# Identity: response echo must match request cell + the deployed image digest.
for f in ("workload", "strategy", "seed", "first_operation_id",
          "handle_mode", "pair_id"):
    if resp.get(f) != req.get(f):
        print("STOP: identity mismatch on %s: req=%r resp=%r"
              % (f, req.get(f), resp.get(f))); sys.exit(1)
rid = resp.get("action_image_digest")
if rid not in (None, image):
    print("STOP: action_image_digest mismatch: %r != %r" % (rid, image)); sys.exit(1)

# Observation key (INCLUDES strategy). Reject a completed cell reappearing with a
# different response identity.
key = "\t".join(str(req.get(k)) for k in
                ("run_config_sha256", "workload", "seed", "first_operation_id",
                 "handle_mode", "pair_id", "strategy"))
sess = str(resp.get("warm_session_id"))
seen = {}
if os.path.exists(ledger):
    for line in open(ledger):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2:
            seen[parts[0]] = parts[1]
if key in seen and seen[key] != sess:
    print("STOP: duplicate completed cell with different session: %s" % key); sys.exit(1)
with open(ledger, "a") as f:
    f.write("%s\t%s\n" % (key, sess))
print("OK", req["request_id"], "session", sess)
PY
    ws2_warn "identity/session violation at position $pos; stopping per protocol."
    ws2_mark_status "$WS2_STAGEDIR" failed FAIL
    ws2_die "stopped: identity mismatch or session break (see exec_log.txt)."
  fi
done

ws2_mark_status "$WS2_STAGEDIR" done PASS
ws2_log "05_full_matrix executed sequentially; raw responses in $RAW."
