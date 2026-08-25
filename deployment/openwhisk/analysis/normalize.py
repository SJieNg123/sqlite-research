#!/usr/bin/env python3
"""WK1-side normalizer for the completed OpenWhisk YC evidence campaign.

Converts the two immutable WS2 evidence bundles (primary + secondary) into one
canonical, auditable, analysis-ready dataset WITHOUT drawing any performance
conclusion. It preserves every identity, pairing link, execution-order fact,
validity gate, and raw metric, and it FAILS CLOSED if any structural or validity
invariant is violated.

What this module does NOT do (by design): rerun OpenWhisk, regenerate plans,
alter strategy semantics, rank strategies, compute speedups/ratios, "fix"
measurements, or mutate the archived bundles. The tar.gz bundles are read-only
source evidence: they are sha256-verified against their sidecars and streamed
from tar; nothing is ever written back into evidence/.

Reused repo conventions (single source of truth — not re-implemented here):
  * client/collect.py       -- warm_session_id(), classify() validity gates,
                               IDENTITY_MATCH request/response identity.
  * client/summarize.py     -- PAIR_KEY (a pair's two arms must share identity).
  * client/validate_schedule.py -- validate_schedule(), matrix_fingerprint(),
                               expected_counts(): independent schedule re-check
                               and the evidence-derived fingerprint.
  * ws2/response_gate.py     -- classify_response(), is_synthetic() (_dry_run).

Authoritative identity comes from schedule.json / req / resp (which agree), NOT
from 06_collect/bundle_manifest.json (whose secondary copy carries the PRIMARY
run_config_sha256 — a packaging summary mislabel that is preserved, not hidden,
as bundle_manifest_run_config_sha256).

Outputs (under an explicit --out dir, default deployment/openwhisk/analysis/normalized/):
  normalized_invocations.csv   3600 rows, one per formal measured invocation
  normalized_pairs.csv         1800 rows, one per baseline/target pair
  normalization_manifest.json  provenance, identities, counts, output SHAs, notes
  normalization_validation.txt  every fail-closed gate result + order balance
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]                      # deployment/openwhisk
_REPO_ROOT = _HERE.parents[3]                    # repo root
sys.path.insert(0, str(_OW_ROOT / "client"))
sys.path.insert(0, str(_OW_ROOT / "ws2"))
import collect                                   # noqa: E402
import validate_schedule as vs                   # noqa: E402
import response_gate                             # noqa: E402

SCHEMA_VERSION = 1

# ---- campaign registry -----------------------------------------------------
# Evidence dirs + bundle filenames are fixed inputs. The expected *counts* and
# *targets* are declared here as fail-closed gates AND independently rederived
# from each bundle's own schedule contract; both must agree.
CAMPAIGNS = [
    {
        "campaign": "primary",
        "evidence_dir": "evidence/yc_primary/cd0ba770795f",
        "bundle": "ws2_bundle_cd0ba770795f_20260823T145432Z.tar.gz",
        "expected": {"invocations": 1600, "pairs": 800, "baseline": 800,
                     "per_target": 200},
        "expected_targets": {"2d", "layers_5", "2e_K10", "2f_slru"},
        # primary target page counts vary by design (2f_slru dumps the whole DB),
        # so no per-target selected_page_count gate here.
        "expected_selected_page_count": {},
    },
    {
        "campaign": "secondary",
        "evidence_dir": "evidence/yc_secondary/e07bf0dc6543",
        "bundle": "ws2_bundle_e07bf0dc6543_20260825T060047Z.tar.gz",
        "expected": {"invocations": 2000, "pairs": 1000, "baseline": 1000,
                     "per_target": 200},
        "expected_targets": {"2e_K500", "leaf_freq_K10", "leaf_rand_K10",
                             "2f_top102", "learned_markov_102"},
        "expected_selected_page_count": {
            "2e_K500": 592, "leaf_freq_K10": 10, "leaf_rand_K10": 10,
            "2f_top102": 102, "learned_markov_102": 102},
    },
]

# ---- output column schema (category is recorded in the manifest) -----------
# P = provenance, S = raw schedule/request identity, D = derived bookkeeping,
# R = raw response field.
INVOCATION_COLUMNS = [
    # A. source / campaign provenance
    ("campaign", "P"), ("source_bundle_filename", "P"),
    ("source_bundle_sha256", "P"), ("sqlite_research_git_sha", "P"),
    ("schedule_fingerprint", "P"), ("authoritative_run_config_sha256", "P"),
    ("artifact_manifest_sha256", "P"), ("action_image_digest", "P"),
    ("bundle_manifest_run_config_sha256", "P"),
    ("source_request_file", "P"), ("source_response_file", "P"),
    # B. schedule / pair identity
    ("request_id", "S"), ("schedule_position", "S"), ("pair_id", "S"),
    ("repetition_id", "S"), ("arm", "S"), ("workload", "S"), ("seed", "S"),
    ("first_operation_id", "S"), ("handle_mode", "S"), ("strategy", "S"),
    ("paired_target_strategy", "D"),
    # C. execution order within pair
    ("pair_first_strategy", "D"), ("pair_second_strategy", "D"),
    ("position_within_pair", "D"), ("is_first_in_pair", "D"),
    # D. process / session identity
    ("process_uuid", "R"), ("pid", "R"), ("invocation_counter", "R"),
    ("db_device", "R"), ("db_inode", "R"), ("db_sha256", "R"),
    ("warm_session_id", "D"),
    # E. validity / correctness
    ("diagnostic_mode", "R"), ("cold_reset_requested", "R"),
    ("cold_reset_method", "R"), ("cold_reset_succeeded", "R"),
    ("cold_threshold_passed", "R"), ("delivery_valid", "R"),
    ("measured_valid", "R"), ("oracle_expected_hit", "R"),
    ("oracle_expected_digest", "R"), ("oracle_passed", "R"),
    ("sqlite_error", "R"), ("error", "R"), ("error_stage", "R"),
    ("result_digest", "R"), ("query_hit", "R"), ("sqlite_cache_miss", "R"),
    ("resident_interiors_before_reset", "R"),
    ("resident_interiors_after_reset", "R"),
    ("resident_interiors_after_prefetch", "R"), ("relevant_pages_total", "R"),
    # F. prefetch / footprint
    ("selected_page_count", "R"), ("selected_interior_count", "R"),
    ("selected_leaf_count", "R"), ("delivered_page_count", "R"),
    ("trace_sha256", "R"), ("plan_sha256", "R"), ("selected_bytes", "D"),
    # G. timing (RAW; never normalized into ratios here)
    ("reset_us", "R"), ("open_us", "R"), ("select_us", "R"),
    ("deliver_us", "R"), ("first_query_us", "R"), ("handler_total_us", "R"),
]
INVOCATION_FIELDS = [c for c, _ in INVOCATION_COLUMNS]

# raw response fields copied verbatim (category R above)
_RAW_RESPONSE_FIELDS = [c for c, cat in INVOCATION_COLUMNS if cat == "R"]

PAIR_COLUMNS = [
    "campaign", "pair_id", "workload", "seed", "handle_mode",
    "first_operation_id", "repetition_id", "paired_target_strategy",
    "first_strategy", "second_strategy",
    "baseline_schedule_position", "target_schedule_position",
    "baseline_request_id", "target_request_id",
    "same_warm_session", "same_run_config", "same_manifest", "same_image",
    "baseline_first_query_us", "target_first_query_us",
    "baseline_open_us", "target_open_us",
    "baseline_deliver_us", "target_deliver_us",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_sidecar(sidecar_path):
    """Return the hex digest recorded in a `<hex>  <filename>` .sha256 sidecar."""
    with open(sidecar_path) as f:
        return f.read().strip().split()[0]


def _cell(v):
    """Deterministic CSV cell rendering (byte-stable across runs)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _pos_from_name(name):
    base = os.path.basename(name)
    return int(base[len("req_"):-len(".json")]) if base.startswith("req_") \
        else int(base[len("resp_"):-len(".json")])


def load_page_size(repo_root):
    """Authoritative DB page size from the committed native-YCSB pin."""
    pin = Path(repo_root) / "deployment/openwhisk/config/artifacts.native_ycsb.json"
    with open(pin) as f:
        d = json.load(f)
    return d["database"]["page_size"]


def read_bundle(evidence_dir, bundle_filename):
    """Stream every file this normalizer needs directly from the (verified) tar.

    Returns a dict with parsed schedule/provenance blobs and two position->obj
    maps for requests and responses. The archived tar is never modified.
    """
    tar_path = os.path.join(evidence_dir, bundle_filename)
    want_exact = {
        "identity.json", "05_full_matrix/schedule.json",
        "05_full_matrix/schedule_validation.txt", "05_full_matrix/STATUS",
        "05_full_matrix/raw/.schedule_fingerprint",
        "01_build_image/build_meta.json", "02_deploy/deploy_meta.json",
        "06_collect/bundle_manifest.json", "06_collect/validity_summary.txt",
    }
    out = {"exact": {}, "reqs": {}, "resps": {}, "prefix": None}
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar:
            if not m.isfile():
                continue
            parts = m.name.split("/", 1)
            if len(parts) != 2:
                continue
            prefix, rel = parts
            out["prefix"] = prefix
            if rel in want_exact:
                out["exact"][rel] = tar.extractfile(m).read()
            elif rel.startswith("05_full_matrix/raw/") and rel.endswith(".json"):
                base = os.path.basename(rel)
                if base.startswith("req_"):
                    out["reqs"][_pos_from_name(base)] = json.loads(
                        tar.extractfile(m).read())
                elif base.startswith("resp_"):
                    out["resps"][_pos_from_name(base)] = json.loads(
                        tar.extractfile(m).read())
    return out


# ---------------------------------------------------------------------------
# core (pure) transforms — unit-testable without a tar
# ---------------------------------------------------------------------------
def build_rows(campaign, schedule, reqs, resps, authoritative_ids,
               bundle_manifest_run_config, source_bundle_filename,
               source_bundle_sha256, git_sha, schedule_fingerprint, page_size):
    """Build normalized invocation rows for one campaign.

    reqs/resps are {schedule_position: obj}. Returns (rows, problems). Every
    formal scheduled invocation must have a parseable, identity-matching, valid,
    non-synthetic response bound to the authoritative identity; any deviation is
    a fail-closed problem and the row is still emitted only if fully valid.
    """
    problems = []
    invocations = schedule.get("invocations", [])
    pair_target = {p["pair_id"]: p["target_strategy"]
                   for p in schedule.get("pairs", [])}

    # group scheduled invocations by pair to derive order from schedule_position
    by_pair_positions = defaultdict(list)
    for inv in invocations:
        by_pair_positions[inv["pair_id"]].append(inv["schedule_position"])
    pair_order = {}   # pair_id -> {"first_pos":, "second_pos":}
    for pid, poss in by_pair_positions.items():
        sp = sorted(poss)
        pair_order[pid] = sp

    run_config_expected = {
        "run_config_sha256": authoritative_ids["run_config_sha256"],
        "artifact_manifest_sha256": authoritative_ids["artifact_manifest_sha256"],
        "action_image_digest": authoritative_ids["action_image_digest"],
    }

    seen_request_ids = set()
    prev_counter = {}
    rows = []
    # iterate in schedule order so warm-session counter monotonicity is checked
    # in the order the arms actually executed
    for inv in sorted(invocations, key=lambda i: i["schedule_position"]):
        pos = inv["schedule_position"]
        rid = inv["request_id"]
        req = reqs.get(pos)
        resp = resps.get(pos)
        if req is None:
            problems.append("%s pos %d: missing request file" % (campaign, pos))
            continue
        if resp is None:
            problems.append("%s pos %d: missing response file" % (campaign, pos))
            continue
        if rid in seen_request_ids:
            problems.append("%s pos %d: duplicate request_id %s" % (campaign, pos, rid))
            continue
        seen_request_ids.add(rid)

        # 1) response_gate: real, non-synthetic, identity-matching handler response
        status, reason = response_gate.classify_response(
            req, resp, authoritative_ids["action_image_digest"])
        if status != "valid":
            problems.append("%s pos %d (%s): response_gate=%s (%s)"
                            % (campaign, pos, rid, status, reason))
            continue

        # 2) collect.classify: full validity + identity-vs-run-config gates
        valid, creason = collect.classify(req, resp, prev_counter,
                                           run_config_expected, activation=None)
        if not valid:
            problems.append("%s pos %d (%s): collect.classify invalid (%s)"
                            % (campaign, pos, rid, creason))
            continue
        if resp.get("invocation_counter") is not None:
            prev_counter[collect.warm_session_id(resp)] = resp["invocation_counter"]

        # 3) response identity must equal the authoritative campaign identity
        for k in ("run_config_sha256", "artifact_manifest_sha256",
                  "action_image_digest"):
            if resp.get(k) != authoritative_ids[k]:
                problems.append("%s pos %d (%s): resp %s=%r != authoritative %r"
                                % (campaign, pos, rid, k, resp.get(k),
                                   authoritative_ids[k]))

        # 4) paired_target_strategy from the pair (works for baseline + target)
        pts = pair_target.get(inv["pair_id"])
        if pts is None:
            problems.append("%s pos %d: pair_id %s not in schedule pairs"
                            % (campaign, pos, inv["pair_id"]))
            continue
        if inv["strategy"] != "baseline" and inv["strategy"] != pts:
            problems.append("%s pos %d: target strategy %s != pair target %s"
                            % (campaign, pos, inv["strategy"], pts))

        # 5) order within pair — derived from schedule_position, NOT arm labels
        sp = pair_order[inv["pair_id"]]
        if len(sp) != 2:
            problems.append("%s pair %s has %d arms (expected 2)"
                            % (campaign, inv["pair_id"], len(sp)))
            continue
        is_first = (pos == sp[0])
        position_within_pair = 1 if is_first else 2

        row = {
            "campaign": campaign,
            "source_bundle_filename": source_bundle_filename,
            "source_bundle_sha256": source_bundle_sha256,
            "sqlite_research_git_sha": git_sha,
            "schedule_fingerprint": schedule_fingerprint,
            "authoritative_run_config_sha256": authoritative_ids["run_config_sha256"],
            "artifact_manifest_sha256": authoritative_ids["artifact_manifest_sha256"],
            "action_image_digest": authoritative_ids["action_image_digest"],
            "bundle_manifest_run_config_sha256": bundle_manifest_run_config,
            "source_request_file": "05_full_matrix/raw/req_%06d.json" % pos,
            "source_response_file": "05_full_matrix/raw/resp_%06d.json" % pos,
            "request_id": rid,
            "schedule_position": pos,
            "pair_id": inv["pair_id"],
            "repetition_id": inv.get("repetition_id"),
            "arm": req.get("arm"),
            "workload": inv["workload"],
            "seed": inv["seed"],
            "first_operation_id": inv["first_operation_id"],
            "handle_mode": inv["handle_mode"],
            "strategy": inv["strategy"],
            "paired_target_strategy": pts,
            "pair_first_strategy": None,   # filled after all rows exist
            "pair_second_strategy": None,
            "position_within_pair": position_within_pair,
            "is_first_in_pair": is_first,
            "warm_session_id": collect.warm_session_id(resp),
        }
        # raw response fields verbatim (never renamed / reinterpreted)
        for f in _RAW_RESPONSE_FIELDS:
            row[f] = resp.get(f)
        # single derived footprint field, documented page-size source
        spc = resp.get("selected_page_count")
        row["selected_bytes"] = (spc * page_size
                                 if isinstance(spc, int) and not isinstance(spc, bool)
                                 else None)
        rows.append(row)

    # fill pair_first/second_strategy now that every row's strategy is known
    strat_by_pos = {(r["pair_id"], r["schedule_position"]): r["strategy"] for r in rows}
    for r in rows:
        sp = pair_order[r["pair_id"]]
        r["pair_first_strategy"] = strat_by_pos.get((r["pair_id"], sp[0]))
        r["pair_second_strategy"] = strat_by_pos.get((r["pair_id"], sp[1]))

    return rows, problems


def derive_pairs(rows):
    """Fold invocation rows into one structural row per baseline/target pair.

    Returns (pair_rows, problems). Exactly one baseline + one target per pair;
    the two arms may not disagree on any PAIR_KEY identity field. No ratios or
    winners are computed — structural pairing only.
    """
    problems = []
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[(r["campaign"], r["pair_id"])].append(r)

    pair_rows = []
    for (campaign, pid), group in by_pair.items():
        base = [r for r in group if r["strategy"] == "baseline"]
        tgt = [r for r in group if r["strategy"] != "baseline"]
        if len(base) != 1 or len(tgt) != 1:
            problems.append("%s pair %s: baseline=%d target=%d (need exactly 1+1)"
                            % (campaign, pid, len(base), len(tgt)))
            continue
        b, t = base[0], tgt[0]
        # PAIR_KEY identity agreement (reuse summarize.py's definition intent)
        for f in ("workload", "seed", "first_operation_id", "handle_mode",
                  "repetition_id"):
            if b.get(f) != t.get(f):
                problems.append("%s pair %s: arms disagree on %s (%r vs %r)"
                                % (campaign, pid, f, b.get(f), t.get(f)))
        first_strategy = b["strategy"] if b["is_first_in_pair"] else t["strategy"]
        second_strategy = t["strategy"] if b["is_first_in_pair"] else b["strategy"]
        pair_rows.append({
            "campaign": campaign,
            "pair_id": pid,
            "workload": t["workload"],
            "seed": t["seed"],
            "handle_mode": t["handle_mode"],
            "first_operation_id": t["first_operation_id"],
            "repetition_id": t["repetition_id"],
            "paired_target_strategy": t["strategy"],
            "first_strategy": first_strategy,
            "second_strategy": second_strategy,
            "baseline_schedule_position": b["schedule_position"],
            "target_schedule_position": t["schedule_position"],
            "baseline_request_id": b["request_id"],
            "target_request_id": t["request_id"],
            "same_warm_session": b["warm_session_id"] == t["warm_session_id"],
            "same_run_config": (b["authoritative_run_config_sha256"]
                                == t["authoritative_run_config_sha256"]),
            "same_manifest": b["artifact_manifest_sha256"] == t["artifact_manifest_sha256"],
            "same_image": b["action_image_digest"] == t["action_image_digest"],
            "baseline_first_query_us": b["first_query_us"],
            "target_first_query_us": t["first_query_us"],
            "baseline_open_us": b["open_us"],
            "target_open_us": t["open_us"],
            "baseline_deliver_us": b["deliver_us"],
            "target_deliver_us": t["deliver_us"],
        })
    return pair_rows, problems


def order_balance(rows):
    """Structural AB/BA counts per (campaign, target, handle_mode). Integrity
    reporting only — never used to infer performance."""
    seen = set()
    counts = defaultdict(lambda: {"baseline_first": 0, "target_first": 0})
    for r in rows:
        key = (r["campaign"], r["pair_id"])
        if key in seen:
            continue
        seen.add(key)
        gk = (r["campaign"], r["paired_target_strategy"], r["handle_mode"])
        if r["pair_first_strategy"] == "baseline":
            counts[gk]["baseline_first"] += 1
        else:
            counts[gk]["target_first"] += 1
    return counts


def run_gates(campaign_cfg, rows, pair_rows):
    """All fail-closed structural + validity + coverage gates for one campaign.
    Returns a list of problem strings (empty == pass)."""
    problems = []
    campaign = campaign_cfg["campaign"]
    exp = campaign_cfg["expected"]

    n_inv = len(rows)
    n_pairs = len(pair_rows)
    if n_inv != exp["invocations"]:
        problems.append("%s invocations %d != expected %d"
                        % (campaign, n_inv, exp["invocations"]))
    if n_pairs != exp["pairs"]:
        problems.append("%s pairs %d != expected %d"
                        % (campaign, n_pairs, exp["pairs"]))

    strat_counts = Counter(r["strategy"] for r in rows)
    if strat_counts.get("baseline", 0) != exp["baseline"]:
        problems.append("%s baseline rows %d != expected %d"
                        % (campaign, strat_counts.get("baseline", 0), exp["baseline"]))
    seen_targets = set(strat_counts) - {"baseline"}
    if seen_targets != campaign_cfg["expected_targets"]:
        problems.append("%s target set %s != expected %s"
                        % (campaign, sorted(seen_targets),
                           sorted(campaign_cfg["expected_targets"])))
    for tgt in sorted(campaign_cfg["expected_targets"]):
        if strat_counts.get(tgt, 0) != exp["per_target"]:
            problems.append("%s target %s rows %d != expected %d"
                            % (campaign, tgt, strat_counts.get(tgt, 0),
                               exp["per_target"]))

    # unique request_id and (campaign, schedule_position)
    rids = [r["request_id"] for r in rows]
    if len(set(rids)) != len(rids):
        problems.append("%s duplicate request_id(s)" % campaign)
    poss = [r["schedule_position"] for r in rows]
    if len(set(poss)) != len(poss):
        problems.append("%s duplicate schedule_position(s)" % campaign)
    elif rows and set(poss) != set(range(1, len(rows) + 1)):
        problems.append("%s schedule_positions not contiguous 1..%d" % (campaign, len(rows)))

    # validity flags on every row
    for r in rows:
        if r["diagnostic_mode"] is not False:
            problems.append("%s pos %d diagnostic_mode != false" % (campaign, r["schedule_position"]))
        for f in ("measured_valid", "oracle_passed", "cold_threshold_passed",
                  "delivery_valid"):
            if r[f] is not True:
                problems.append("%s pos %d %s != true" % (campaign, r["schedule_position"], f))
        if r["error"] or r["error_stage"] or r["sqlite_error"]:
            problems.append("%s pos %d carries an error field" % (campaign, r["schedule_position"]))

    # per-cell balance (target x seed x handle_mode x repetition_id, first_op=0)
    cells = Counter()
    fop_bad = 0
    for r in rows:
        if r["strategy"] == "baseline":
            continue
        if r["first_operation_id"] != 0:
            fop_bad += 1
        cells[(r["strategy"], r["seed"], r["handle_mode"], r["repetition_id"])] += 1
    if fop_bad:
        problems.append("%s %d target rows have first_operation_id != 0" % (campaign, fop_bad))
    for cell, c in cells.items():
        if c != 1:
            problems.append("%s cell %s has %d target arms (expected 1)" % (campaign, cell, c))
    # exactly one pair per Cartesian cell => expected cell count == per_target*targets
    expected_cells = exp["per_target"] * len(campaign_cfg["expected_targets"])
    if len(cells) != expected_cells:
        problems.append("%s distinct target cells %d != expected %d"
                        % (campaign, len(cells), expected_cells))

    # no pair may cross identity / cell boundaries
    for p in pair_rows:
        if not (p["same_warm_session"] and p["same_run_config"]
                and p["same_manifest"] and p["same_image"]):
            problems.append("%s pair %s crosses identity/session boundary"
                            % (campaign, p["pair_id"]))

    # secondary selected_page_count invariants — check ALL relevant rows
    spc_exp = campaign_cfg["expected_selected_page_count"]
    if spc_exp:
        bad = defaultdict(set)
        for r in rows:
            if r["strategy"] in spc_exp and r["selected_page_count"] != spc_exp[r["strategy"]]:
                bad[r["strategy"]].add(r["selected_page_count"])
        for strat, vals in bad.items():
            problems.append("%s %s selected_page_count %s != expected %d"
                            % (campaign, strat, sorted(vals), spc_exp[strat]))

    return problems


# ---------------------------------------------------------------------------
# per-campaign driver (verifies bundle, derives evidence identity/fingerprint)
# ---------------------------------------------------------------------------
def normalize_campaign(campaign_cfg, ow_root, page_size):
    """Verify + read one bundle and return
    (rows, pair_rows, problems, provenance)."""
    campaign = campaign_cfg["campaign"]
    evidence_dir = os.path.join(ow_root, campaign_cfg["evidence_dir"])
    bundle = campaign_cfg["bundle"]
    tar_path = os.path.join(evidence_dir, bundle)
    sidecar = tar_path + ".sha256"

    problems = []
    # 1) sha256-verify the immutable source bundle BEFORE reading it
    actual_sha = sha256_file(tar_path)
    sidecar_sha = parse_sidecar(sidecar)
    if actual_sha != sidecar_sha:
        problems.append("%s bundle sha256 %s != sidecar %s"
                        % (campaign, actual_sha, sidecar_sha))
        return [], [], problems, {"source_bundle_sha256": actual_sha}

    b = read_bundle(evidence_dir, bundle)
    schedule = json.loads(b["exact"]["05_full_matrix/schedule.json"])
    identity_json = json.loads(b["exact"]["identity.json"])
    bundle_manifest = json.loads(b["exact"]["06_collect/bundle_manifest.json"])
    sched_fp_sidecar = b["exact"]["05_full_matrix/raw/.schedule_fingerprint"].decode().strip()
    status_txt = b["exact"]["05_full_matrix/STATUS"].decode()

    # 2) authoritative identity + evidence-derived fingerprint
    authoritative_ids = dict(schedule["identity"])
    contract = schedule["contract"]
    derived_fp = vs.matrix_fingerprint(contract, authoritative_ids)
    stored_fp = schedule.get("matrix_fingerprint")
    if derived_fp != stored_fp:
        problems.append("%s recomputed matrix_fingerprint %s != stored %s"
                        % (campaign, derived_fp, stored_fp))
    if sched_fp_sidecar != stored_fp:
        problems.append("%s raw/.schedule_fingerprint %s != schedule.json %s"
                        % (campaign, sched_fp_sidecar, stored_fp))
    schedule_fingerprint = stored_fp

    # 3) independent structural re-validation of the schedule itself
    for pr in vs.validate_schedule(schedule, contract):
        problems.append("%s schedule invalid: %s" % (campaign, pr))

    # bundle_manifest run_config (may be the primary-pin mislabel on secondary)
    bm_run_config = bundle_manifest.get("run_config_sha256")

    git_sha = identity_json.get("git_sha")

    rows, rp = build_rows(
        campaign, schedule, b["reqs"], b["resps"], authoritative_ids,
        bm_run_config, bundle, actual_sha, git_sha, schedule_fingerprint,
        page_size)
    problems.extend(rp)

    pair_rows, pp = derive_pairs(rows)
    problems.extend(pp)

    problems.extend(run_gates(campaign_cfg, rows, pair_rows))

    provenance = {
        "campaign": campaign,
        "source_bundle_filename": bundle,
        "source_bundle_sha256": actual_sha,
        "source_bundle_sha256_sidecar": sidecar_sha,
        "sqlite_research_git_sha": git_sha,
        "schedule_fingerprint": schedule_fingerprint,
        "schedule_fingerprint_recomputed": derived_fp,
        "authoritative_run_config_sha256": authoritative_ids["run_config_sha256"],
        "artifact_manifest_sha256": authoritative_ids["artifact_manifest_sha256"],
        "action_image_digest": authoritative_ids["action_image_digest"],
        "bundle_manifest_run_config_sha256": bm_run_config,
        "bundle_manifest_run_config_matches_authoritative":
            bm_run_config == authoritative_ids["run_config_sha256"],
        "status": dict(line.split("=", 1) for line in status_txt.split("\n")
                       if "=" in line),
        "invocations": len(rows),
        "pairs": len(pair_rows),
    }
    return rows, pair_rows, problems, provenance


# ---------------------------------------------------------------------------
# output writers
# ---------------------------------------------------------------------------
def write_csv(path, columns, rows):
    """Write rows deterministically; return the file's sha256."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for r in rows:
        w.writerow([_cell(r.get(c)) for c in columns])
    data = buf.getvalue().encode()
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def build_validation_report(all_problems, per_campaign, combined, order_bal):
    lines = []
    lines.append("# OpenWhisk WK1 normalization — validation report")
    lines.append("")
    overall = "PASS" if not all_problems else "FAIL"
    lines.append("overall: %s" % overall)
    lines.append("")
    lines.append("## combined totals")
    lines.append("invocation_rows: %d (expected 3600)" % combined["invocations"])
    lines.append("pair_rows: %d (expected 1800)" % combined["pairs"])
    lines.append("baseline_rows: %d (expected 1800)" % combined["baseline"])
    lines.append("target_rows: %d (expected 1800)" % combined["target"])
    lines.append("")
    for cp in per_campaign:
        lines.append("## campaign: %s" % cp["campaign"])
        lines.append("invocations: %d" % cp["invocations"])
        lines.append("pairs: %d" % cp["pairs"])
        lines.append("per_target_counts: %s"
                     % json.dumps(cp["per_target_counts"], sort_keys=True))
        lines.append("bundle_sha256: %s" % cp["source_bundle_sha256"])
        lines.append("schedule_fingerprint: %s" % cp["schedule_fingerprint"])
        lines.append("authoritative_run_config_sha256: %s"
                     % cp["authoritative_run_config_sha256"])
        lines.append("bundle_manifest_run_config_sha256: %s (matches_authoritative=%s)"
                     % (cp["bundle_manifest_run_config_sha256"],
                        cp["bundle_manifest_run_config_matches_authoritative"]))
        lines.append("")
    lines.append("## pair-order structural balance (integrity only; NOT performance)")
    for gk in sorted(order_bal, key=lambda k: (k[0], str(k[1]), str(k[2]))):
        c = order_bal[gk]
        lines.append("%s | %s | %s : baseline_first=%d target_first=%d"
                     % (gk[0], gk[1], gk[2], c["baseline_first"], c["target_first"]))
    lines.append("")
    lines.append("## fail-closed problems (%d)" % len(all_problems))
    if not all_problems:
        lines.append("(none — all gates passed)")
    else:
        for p in all_problems[:500]:
            lines.append("FAIL %s" % p)
        if len(all_problems) > 500:
            lines.append("... (%d more)" % (len(all_problems) - 500))
    lines.append("")
    return "\n".join(lines) + "\n"


def normalize(ow_root, out_dir):
    """Full pipeline. Returns (ok, manifest_dict). Writes 4 output files."""
    os.makedirs(out_dir, exist_ok=True)
    page_size = load_page_size(Path(ow_root).parents[1])

    all_rows, all_pairs, all_problems, per_campaign_prov = [], [], [], []
    for cfg in CAMPAIGNS:
        rows, pairs, problems, prov = normalize_campaign(cfg, ow_root, page_size)
        all_rows.extend(rows)
        all_pairs.extend(pairs)
        all_problems.extend(problems)
        prov["per_target_counts"] = {
            t: sum(1 for r in rows if r["strategy"] == t)
            for t in sorted(cfg["expected_targets"])}
        per_campaign_prov.append(prov)

    # deterministic ordering: campaign (primary<secondary) then schedule_position
    camp_rank = {c["campaign"]: i for i, c in enumerate(CAMPAIGNS)}
    all_rows.sort(key=lambda r: (camp_rank[r["campaign"]], r["schedule_position"]))
    # pair rows: campaign then the earliest (baseline/target) schedule_position
    all_pairs.sort(key=lambda p: (camp_rank[p["campaign"]],
                                  min(p["baseline_schedule_position"],
                                      p["target_schedule_position"])))

    combined = {
        "invocations": len(all_rows),
        "pairs": len(all_pairs),
        "baseline": sum(1 for r in all_rows if r["strategy"] == "baseline"),
        "target": sum(1 for r in all_rows if r["strategy"] != "baseline"),
    }
    # combined fail-closed gates
    if combined["invocations"] != 3600:
        all_problems.append("combined invocations %d != 3600" % combined["invocations"])
    if combined["pairs"] != 1800:
        all_problems.append("combined pairs %d != 1800" % combined["pairs"])
    if combined["baseline"] != 1800:
        all_problems.append("combined baseline %d != 1800" % combined["baseline"])
    if combined["target"] != 1800:
        all_problems.append("combined target %d != 1800" % combined["target"])
    # unique (campaign, schedule_position) across the combined set
    keys = [(r["campaign"], r["schedule_position"]) for r in all_rows]
    if len(set(keys)) != len(keys):
        all_problems.append("combined duplicate (campaign, schedule_position)")

    order_bal = order_balance(all_rows)

    inv_path = os.path.join(out_dir, "normalized_invocations.csv")
    pair_path = os.path.join(out_dir, "normalized_pairs.csv")
    inv_sha = write_csv(inv_path, INVOCATION_FIELDS, all_rows)
    pair_sha = write_csv(pair_path, PAIR_COLUMNS, all_pairs)

    report = build_validation_report(all_problems, per_campaign_prov, combined,
                                     order_bal)
    val_path = os.path.join(out_dir, "normalization_validation.txt")
    with open(val_path, "w") as f:
        f.write(report)

    ok = not all_problems
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "normalizer_git_sha": _git_sha(ow_root),
        "ok": ok,
        "campaigns": per_campaign_prov,
        "combined": combined,
        "page_size": page_size,
        "page_size_source": "deployment/openwhisk/config/artifacts.native_ycsb.json:database.page_size",
        "column_categories": {
            "legend": {"P": "provenance", "S": "raw schedule/request identity",
                       "R": "raw response field (verbatim, never reinterpreted)",
                       "D": "derived bookkeeping"},
            "invocation_columns": {c: cat for c, cat in INVOCATION_COLUMNS},
        },
        "outputs": {
            "normalized_invocations.csv": {"rows": len(all_rows), "sha256": inv_sha},
            "normalized_pairs.csv": {"rows": len(all_pairs), "sha256": pair_sha},
            "normalization_validation.txt": {
                "sha256": hashlib.sha256(report.encode()).hexdigest()},
        },
        "canonical_row_order": "campaign (primary<secondary), then schedule_position",
        "known_provenance_notes": [
            "The secondary 06_collect/bundle_manifest.json records the PRIMARY "
            "run_config_sha256 (022fbeb0...). This is a packaging summary "
            "mislabel only; it is preserved verbatim as "
            "bundle_manifest_run_config_sha256 and NOT used as authority.",
            "authoritative_run_config_sha256 is taken from schedule.json / "
            "req_*.json / resp_*.json, which agree; secondary resolves to "
            "441609e6... and primary to 022fbeb0....",
            "The historical expected PRIMARY schedule fingerprint 'd08266ca...' "
            "is stale/incorrect and is NOT used. The primary schedule "
            "fingerprint is derived from evidence (schedule.json, "
            "schedule_validation.txt, raw/.schedule_fingerprint, and a "
            "recomputation via matrix_fingerprint).",
        ],
    }
    man_path = os.path.join(out_dir, "normalization_manifest.json")
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return ok, manifest


def _git_sha(ow_root):
    try:
        head = Path(ow_root).parents[1] / ".git" / "HEAD"
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            return (Path(ow_root).parents[1] / ".git" / ref[5:]).read_text().strip()
        return ref
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ow-root", default=str(_OW_ROOT),
                    help="deployment/openwhisk root (default: this file's)")
    ap.add_argument("--out", default=str(_OW_ROOT / "analysis" / "normalized"))
    a = ap.parse_args()
    ok, manifest = normalize(a.ow_root, a.out)
    print("normalization %s: %d invocations, %d pairs -> %s"
          % ("PASS" if ok else "FAIL", manifest["combined"]["invocations"],
             manifest["combined"]["pairs"], a.out))
    if not ok:
        print("FAILED gates — see normalization_validation.txt", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
