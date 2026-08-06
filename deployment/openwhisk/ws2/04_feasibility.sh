#!/usr/bin/env bash
# 04_feasibility.sh -- small paired feasibility batch: baseline vs 2d, canonical
# YCSB-C seed 1, warm handle, 6 deterministic AB/BA pairs, concurrency=1,
# strictly sequential. This is a "does the paired protocol produce valid cells on
# this runtime" check, not the headline matrix.
#
# Requires >=5 valid complete pairs; refuses duplicate pair/cell identities.
WS2_HELP='Usage: 04_feasibility.sh

Runs 6 deterministic baseline/2d pairs (seed 1, warm handle) sequentially and
requires at least 5 valid complete pairs. Requires 03_diagnostic PASS.
Identity inputs:
  OW_ACTION_NAME               (from 02_deploy metadata)
  OW_ARTIFACT_MANIFEST_SHA256  (required: identity gate)
  OW_SCHEDULE_SEED             (default 20260804; deterministic AB/BA order)
Preserves every raw request/response under _runs/<sha>/04_feasibility/raw/.
Env: DRY_RUN=1 (build schedule + requests, synthesize responses, skip the >=5
gate), WS2_FORCE=1 (redo).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"
[ $# -eq 0 ] || ws2_die "unexpected argument: $1 (see --help)"

ws2_begin "04_feasibility"
ws2_guard_completed "$WS2_STAGEDIR"

# --- gate: diagnostic PASS ------------------------------------------------- #
DIAG_DIR="$WS2_RUN_DIR/03_diagnostic"
ws2_stage_is_done "$DIAG_DIR" && [ "$(ws2_stage_status_value "$DIAG_DIR")" = PASS ] \
  || ws2_die "03_diagnostic has not PASSed for this checkout. Run it first."

DEPLOY_META="$WS2_RUN_DIR/02_deploy/deploy_meta.json"
read -r OW_ACTION_NAME IMAGE_DIGEST < <(python3 - "$DEPLOY_META" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(m.get("action_name","sqlite-coldstart"), m.get("image_digest",""))
PY
)
MANIFEST_SHA="${OW_ARTIFACT_MANIFEST_SHA256:-}"
SCHED_SEED="${OW_SCHEDULE_SEED:-20260804}"
if [ -z "$MANIFEST_SHA" ]; then
  [ "${DRY_RUN:-0}" = 1 ] && MANIFEST_SHA="0000000000000000000000000000000000000000000000000000000000000000" \
    || ws2_die "OW_ARTIFACT_MANIFEST_SHA256 is unset (identity gate needs it)."
fi

RUN_CONFIG_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_config_sha256"])' "$WS2_PIN_JSON")"
WORKLOAD_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["representative_workload"]["canonical_workload_id"])' "$WS2_PIN_JSON")"

SCHED="$WS2_STAGEDIR/schedule.json"
RAW="$WS2_STAGEDIR/raw"; mkdir -p "$RAW"

# --- deterministic schedule (6 pairs) -------------------------------------- #
python3 "$WS2_OW_DIR/client/build_schedule.py" \
  --out "$SCHED" \
  --schedule-seed "$SCHED_SEED" \
  --workloads "$WORKLOAD_ID" \
  --seeds 1 \
  --first-ops 0 \
  --handle-modes warm \
  --targets 2d \
  --repetitions 6 \
  --run-config-sha256 "$RUN_CONFIG_SHA" \
  --artifact-manifest-sha256 "$MANIFEST_SHA" \
  --action-image-digest "$IMAGE_DIGEST" >/dev/null
ws2_log "schedule (6 pairs) -> $SCHED"

# --- explode invocations into per-position request files (dedup-checked) --- #
python3 - "$SCHED" "$RAW" <<'PY'
import json, os, sys
sched, raw = sys.argv[1], sys.argv[2]
s = json.load(open(sched))
seen_req, seen_cell = set(), set()
for inv in s["invocations"]:
    rid = inv["request_id"]
    cell = (inv["pair_id"], inv["arm"])
    if rid in seen_req: raise SystemExit("duplicate request_id: %s" % rid)
    if cell in seen_cell: raise SystemExit("duplicate pair/arm cell: %s" % (cell,))
    seen_req.add(rid); seen_cell.add(cell)
    p = os.path.join(raw, "req_%04d.json" % inv["schedule_position"])
    json.dump(inv, open(p, "w"), indent=2, sort_keys=True)
print("exploded %d invocations (%d pairs), no duplicate identities"
      % (len(s["invocations"]), s["counts"]["pairs"]))
PY

# --- sequential invocation (concurrency=1) --------------------------------- #
for req in $(ls "$RAW"/req_*.json | sort); do
  pos="$(basename "$req" .json | sed 's/req_//')"
  resp="$RAW/resp_${pos}.json"
  ws2_log "invoke position $pos (sequential)"
  ws2_invoke "$OW_ACTION_NAME" "$req" "$resp" || ws2_warn "position $pos non-zero; kept for evaluation"
done

if [ "${DRY_RUN:-0}" = 1 ]; then
  ws2_log "DRY_RUN: schedule + requests built, synthetic responses saved; >=5 gate NOT enforced."
  ws2_mark_status "$WS2_STAGEDIR" done DRYRUN
  exit 0
fi

# --- pair validity aggregation --------------------------------------------- #
REPORT="$WS2_STAGEDIR/feasibility_report.txt"
if python3 - "$SCHED" "$RAW" > "$REPORT" 2>&1 <<'PY'; then
import json, os, sys
sched, raw = sys.argv[1], sys.argv[2]
s = json.load(open(sched))
# map request_id -> response
resp = {}
for inv in s["invocations"]:
    p = os.path.join(raw, "resp_%04d.json" % inv["schedule_position"])
    resp[inv["request_id"]] = json.load(open(p)) if os.path.exists(p) else None

def arm_valid(inv, r):
    if not isinstance(r, dict): return False
    # identity of response must match the request cell
    for f in ("workload", "strategy", "seed", "first_operation_id",
              "handle_mode", "pair_id"):
        if r.get(f) != inv.get(f): return False
    return bool(r.get("measured_valid") and r.get("oracle_passed")
               and r.get("cold_threshold_passed") and r.get("delivery_valid"))

by_pair = {}
for inv in s["invocations"]:
    by_pair.setdefault(inv["pair_id"], []).append(inv)

valid_pairs = 0
for pid, arms in sorted(by_pair.items()):
    if len(arms) != 2:
        print("PAIR", pid, "SKIP (not exactly 2 arms)"); continue
    sessions = set()
    ok = True
    for inv in arms:
        r = resp.get(inv["request_id"])
        if not arm_valid(inv, r): ok = False
        if isinstance(r, dict): sessions.add(r.get("warm_session_id"))
    if len(sessions) > 1:
        print("PAIR", pid, "INVALID (session break across arms)"); continue
    print("PAIR", pid, "VALID" if ok else "INVALID")
    if ok: valid_pairs += 1

print("---")
print("valid_complete_pairs:", valid_pairs, "/", len(by_pair))
if valid_pairs >= 5:
    print("VERDICT: PASS"); sys.exit(0)
print("VERDICT: FAIL (need >=5 valid complete pairs)"); sys.exit(1)
PY
  cat "$REPORT" >&2
  ws2_mark_status "$WS2_STAGEDIR" done PASS
  ws2_log "FEASIBILITY PASS -> $REPORT"
else
  cat "$REPORT" >&2
  ws2_mark_status "$WS2_STAGEDIR" done FAIL
  ws2_die "FEASIBILITY FAIL: fewer than 5 valid complete pairs (see $REPORT)."
fi
