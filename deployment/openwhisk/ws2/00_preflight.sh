#!/usr/bin/env bash
# 00_preflight.sh -- READ-ONLY workstation readiness + frozen-artifact integrity.
#
# Performs NO build, deploy, or invocation. It only checks that this WS2 machine
# and this exact checkout are fit to run the measured stages, and freezes a
# preflight report into the machine-local run tree.
WS2_HELP='Usage: 00_preflight.sh [--openwhisk-sha <SHA>] [--openwhisk-status <text>]

Read-only preflight. Verifies Git identity, wsk namespace access (auth redacted),
non-sudo Docker access, Python, the OpenWhisk source repo SHA/status you supply,
presence + frozen sha256 of every required artifact (DB/classifier/2d plan/
manifests/traces), and the stdlib unit tests. Writes a report under
deployment/openwhisk/ws2/_runs/<sha>/00_preflight/. Never builds/deploys/invokes.

Inputs (OpenWhisk *source repo* identity, supplied by you -- this repo does not
know it): --openwhisk-sha / OW_REPO_SHA, --openwhisk-status / OW_REPO_STATUS.

Env: DRY_RUN=1 (skip the external probes, still report), WS2_ALLOW_DIRTY=1
(permit a dirty tree for this read-only command), WS2_FORCE=1 (redo a completed
preflight).'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
ws2_maybe_help "$@"

OW_REPO_SHA="${OW_REPO_SHA:-}"
OW_REPO_STATUS="${OW_REPO_STATUS:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --openwhisk-sha)    OW_REPO_SHA="${2:-}"; shift 2 ;;
    --openwhisk-status) OW_REPO_STATUS="${2:-}"; shift 2 ;;
    *) ws2_die "unknown argument: $1 (see --help)" ;;
  esac
done

ws2_begin "00_preflight" readonly
ws2_guard_completed "$WS2_STAGEDIR"

REPORT="$WS2_STAGEDIR/preflight_report.txt"
FAILURES=0
: > "$REPORT.building"
r() { printf '%s\n' "$*" >> "$REPORT.building"; }          # report line
fail() { FAILURES=$((FAILURES+1)); ws2_warn "GATE FAIL: $*"; r "FAIL  $*"; }
pass() { ws2_log "ok: $*"; r "PASS  $*"; }

r "# WS2 preflight report"
r "utc: $(ws2_ts)"
r "run_id: $WS2_RUN_ID"

# --- 1. Git identity + clean tree ------------------------------------------ #
r ""
r "## git"
r "sqlite_research_sha: $WS2_GIT_SHA"
if ws2_tree_is_dirty; then
  r "sqlite_research_dirty: yes"
  [ "${WS2_ALLOW_DIRTY:-0}" = 1 ] || [ "${DRY_RUN:-0}" = 1 ] \
    && ws2_warn "tree is dirty (allowed for this read-only run)" \
    || fail "sqlite-research working tree is dirty"
else
  r "sqlite_research_dirty: no"
  pass "sqlite-research tree clean at $WS2_GIT_SHA_SHORT"
fi

# --- 2. OpenWhisk source repo identity (supplied by caller) ---------------- #
r ""
r "## openwhisk_source_repo (supplied by argument/env)"
if [ -n "$OW_REPO_SHA" ]; then
  r "openwhisk_repo_sha: $OW_REPO_SHA"
  r "openwhisk_repo_status: ${OW_REPO_STATUS:-<none supplied>}"
  pass "OpenWhisk source repo SHA recorded"
else
  fail "OpenWhisk source repo SHA not supplied (--openwhisk-sha / OW_REPO_SHA)"
fi

# --- 3. wsk present + namespace access (auth redacted) --------------------- #
r ""
r "## wsk"
if [ "${DRY_RUN:-0}" = 1 ]; then
  r "wsk_check: skipped (DRY_RUN)"
elif ws2_have wsk; then
  r "wsk_present: yes"
  # `wsk namespace list` returns namespace ids, NOT auth. Redact defensively and
  # never call `wsk property get --auth` or dump ~/.wskprops.
  if wsk namespace list 2>/dev/null | ws2_redact > "$WS2_STAGEDIR/wsk_namespace.txt"; then
    if [ -s "$WS2_STAGEDIR/wsk_namespace.txt" ]; then
      pass "wsk can access a namespace (redacted -> wsk_namespace.txt)"
    else
      fail "wsk namespace list returned nothing (no namespace access)"
    fi
  else
    fail "wsk namespace list failed (cannot access namespace)"
  fi
else
  fail "wsk CLI not found"
fi

# --- 4. Docker access WITHOUT sudo ----------------------------------------- #
r ""
r "## docker"
if [ "${DRY_RUN:-0}" = 1 ]; then
  r "docker_check: skipped (DRY_RUN)"
elif ws2_have docker; then
  r "docker_present: yes"
  if docker info >/dev/null 2>&1; then
    pass "docker usable without sudo"
  else
    fail "docker present but not usable as this user without sudo (WS2 never sudo)"
  fi
else
  fail "docker not found"
fi

# --- 5. Python ------------------------------------------------------------- #
r ""
r "## python"
if ws2_have python3; then
  r "python_version: $(python3 --version 2>&1)"
  pass "python3 present"
else
  fail "python3 not found"
fi

# --- 6. Frozen artifact presence + hashes ---------------------------------- #
r ""
r "## frozen_artifacts"
[ -f "$WS2_PIN_JSON" ] || fail "native-YCSB pin missing: $WS2_PIN_JSON"
[ -f "$WS2_NATIVE_MANIFEST" ] || fail "native manifest missing: $WS2_NATIVE_MANIFEST"

# test.db must equal the one pinned SHA -- the non-negotiable identity.
if ws2_verify_sha256 "$WS2_REPO_ROOT/$WS2_DB_REL" "$WS2_EXPECTED_DB_SHA" "test.db (pinned)"; then
  pass "test.db sha256 == pinned $WS2_EXPECTED_DB_SHA"
else
  fail "test.db sha256 != pinned value"
fi

# Every other frozen file: read (path, expected sha) straight out of the pin so
# there is a single source of truth and nothing is hard-coded here.
if [ -f "$WS2_PIN_JSON" ]; then
  while IFS=$'\t' read -r rel want label; do
    [ -n "$rel" ] || continue
    if ws2_verify_sha256 "$WS2_REPO_ROOT/$rel" "$want" "$label"; then
      pass "$label sha256 frozen-match"
    else
      fail "$label sha256 mismatch or missing ($rel)"
    fi
  done < <(python3 - "$WS2_PIN_JSON" <<'PY'
import json, sys
pin = json.load(open(sys.argv[1]))
rows = []
rows.append((pin["classifier"]["path"], pin["classifier"]["sha256"], "classifier"))
p2d = pin["strategy_plans"]["2d"]
rows.append((p2d["path"], p2d["sha256"], "2d_interior_plan"))
for e in pin["representative_workload"]["seed_family"]:
    rows.append((e["trace"], e["trace_sha256"], "trace_YC_seed%d" % e["seed"]))
for rel, sha, label in rows:
    print("%s\t%s\t%s" % (rel, sha, label))
PY
  )
fi

# --- 7. stdlib unit tests: BEFORE-BUILD gates only ------------------------- #
# 00_preflight is read-only and runs BEFORE 01 generates config/artifacts.json, so
# it must run ONLY tests that are valid against frozen sources -- never a test that
# needs paper/main.tex (a paper-build concern, not a deployment requirement) or the
# live config/artifacts.json (generated by 01). The live-manifest invariant gate
# (TestNativeYcsbLiveManifestAgreement) runs in 01_build_image AFTER generation.
# Each selector below is a specific class, so unittest collects ONLY these:
#   * workload-registry / native-ID checks    (no paper/main.tex, no live manifest)
#   * generator page-size / plan invariants    (pure logic)
#   * frozen first-query oracle single-source  (committed example, not live)
#   * native-YCSB pin <-> manifest <-> disk    (frozen sources, not live manifest)
r ""
r "## unit_tests (python3 -m unittest, stdlib only; before-build/frozen-source gates)"
run_unittest() {  # run_unittest <module-or-class-selector>
  local mod="$1"
  if [ "${DRY_RUN:-0}" = 1 ]; then r "unittest $mod: skipped (DRY_RUN)"; return 0; fi
  if ( cd "$WS2_REPO_ROOT" && python3 -m unittest "$mod" ) \
        > "$WS2_STAGEDIR/unittest_${mod//./_}.log" 2>&1; then
    pass "unittest $mod"
  else
    fail "unittest $mod (see unittest_${mod//./_}.log)"
  fi
}
run_unittest tests.test_workload_naming.RegistryMapping
run_unittest tests.test_workload_naming.NativeYcsbRegistry
run_unittest deployment.openwhisk.tests.test_manifest_invariants.TestPageSizeDecode
run_unittest deployment.openwhisk.tests.test_manifest_invariants.TestPlanInvariants
run_unittest deployment.openwhisk.tests.test_manifest_invariants.TestOracleSingleSource
run_unittest deployment.openwhisk.tests.test_manifest_invariants.TestNativeYcsbPinFrozenSources

# --- verdict --------------------------------------------------------------- #
r ""
if [ "$FAILURES" -eq 0 ]; then
  r "VERDICT: PASS"
  mv -f "$REPORT.building" "$REPORT"
  ws2_mark_status "$WS2_STAGEDIR" done PASS
  ws2_log "PREFLIGHT PASS -> $REPORT"
  exit 0
else
  r "VERDICT: FAIL ($FAILURES gate(s) failed)"
  mv -f "$REPORT.building" "$REPORT"
  ws2_mark_status "$WS2_STAGEDIR" done FAIL
  ws2_die "PREFLIGHT FAIL: $FAILURES gate(s) failed -> $REPORT"
fi
