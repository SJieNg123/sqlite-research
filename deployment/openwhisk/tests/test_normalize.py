#!/usr/bin/env python3
"""Tests for the WK1 OpenWhisk evidence normalizer (analysis/normalize.py).

Two layers:
  * Pure-function unit tests on synthetic mini-campaigns that exercise the exact
    fail-closed gates (pairing, order-from-schedule-position, identity/validity
    rejection) without touching the immutable evidence bundles.
  * Integration checks that read the ACTUAL normalized outputs (if present) and
    assert the campaign/combined counts, the secondary bundle-manifest quirk
    handling, and deterministic byte-stable output.

None of these tests assert anything about which strategy is faster — only about
structural/identity integrity, which is all the normalizer is allowed to encode.
"""
import json
import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_OW_ROOT = _HERE.parents[1]                      # deployment/openwhisk
sys.path.insert(0, str(_OW_ROOT / "analysis"))
import normalize as N                             # noqa: E402

PAGE_SIZE = 4096
AUTH = {
    "run_config_sha256": "a" * 64,
    "artifact_manifest_sha256": "b" * 64,
    "action_image_digest": "sha256:" + "c" * 64,
}
# a run_config dict shaped for collect.classify (same three identities)
FP = "f" * 64


def make_resp(pos, pid_, strategy, seed, handle_mode, rep, counter,
              process_uuid="proc-1", pid_num=1000, db_inode=42,
              overrides=None):
    """A response that PASSES both response_gate.classify_response and
    collect.classify against make_req(...) with the same args."""
    r = {
        "request_id": "%s:%s" % (pid_, strategy),
        "pair_id": pid_,
        "schedule_position": pos,
        "run_config_sha256": AUTH["run_config_sha256"],
        "expected_action_image_digest": AUTH["action_image_digest"],
        "action_image_digest": AUTH["action_image_digest"],
        "artifact_manifest_sha256": AUTH["artifact_manifest_sha256"],
        "workload": "wl", "strategy": strategy, "seed": seed,
        "first_operation_id": 0, "handle_mode": handle_mode,
        "repetition_id": rep, "schedule_seed": 20260804,
        "measured_valid": True, "diagnostic_mode": False,
        "cold_reset_requested": True, "cold_reset_method": "posix_fadvise",
        "cold_reset_succeeded": True, "cold_threshold_passed": True,
        "delivery_valid": True, "oracle_passed": True,
        "oracle_expected_hit": True, "oracle_expected_digest": "dig",
        "query_hit": True, "result_digest": "dig", "sqlite_cache_miss": True,
        "process_uuid": process_uuid, "pid": pid_num,
        "db_device": "259:0", "db_inode": db_inode,
        "db_sha256": "d" * 64, "invocation_counter": counter,
        "selected_page_count": 102, "selected_interior_count": 92,
        "selected_leaf_count": 10, "delivered_page_count": 102,
        "relevant_pages_total": 102,
        "resident_interiors_before_reset": 0,
        "resident_interiors_after_reset": 0,
        "resident_interiors_after_prefetch": 92,
        "trace_sha256": "e" * 64, "plan_sha256": "9" * 64,
        "reset_us": 1.0, "open_us": 2.0, "select_us": 3.0,
        "deliver_us": 4.0, "first_query_us": 5.0, "handler_total_us": 15.0,
        "sqlite_error": None, "error": None, "error_stage": None,
    }
    if overrides:
        r.update(overrides)
    return r


def make_req(pos, pid_, strategy, seed, handle_mode, rep):
    return {
        "request_id": "%s:%s" % (pid_, strategy),
        "pair_id": pid_, "schedule_position": pos,
        "run_config_sha256": AUTH["run_config_sha256"],
        "expected_action_image_digest": AUTH["action_image_digest"],
        "expected_artifact_manifest_hash": AUTH["artifact_manifest_sha256"],
        "workload": "wl", "strategy": strategy, "seed": seed,
        "first_operation_id": 0, "handle_mode": handle_mode,
        "repetition_id": rep, "schedule_seed": 20260804,
        "arm": strategy, "diagnostic_mode": False,
    }


def make_campaign(pairs_spec, campaign="primary"):
    """pairs_spec: list of dicts {pair_id, target, seed, handle_mode, rep,
    baseline_first(bool)}. Returns (schedule, reqs, resps) with each arm at a
    unique global schedule_position (1-based, contiguous)."""
    invocations, pairs = [], []
    reqs, resps = {}, {}
    pos = 1
    counter_by_session = {}
    for spec in pairs_spec:
        pid_ = spec["pair_id"]
        tgt = spec["target"]
        seed = spec.get("seed", 1)
        hm = spec.get("handle_mode", "warm")
        rep = spec.get("rep", 0)
        pairs.append({"pair_id": pid_, "workload": "wl", "seed": seed,
                      "first_operation_id": 0, "handle_mode": hm,
                      "repetition_id": rep, "target_strategy": tgt,
                      "order": None})
        arms = (["baseline", tgt] if spec.get("baseline_first", True)
                else [tgt, "baseline"])
        for arm in arms:
            sess = (spec.get("process_uuid", "proc-1"), spec.get("pid_num", 1000),
                    spec.get("db_inode", 42))
            counter_by_session[sess] = counter_by_session.get(sess, 0) + 1
            ctr = counter_by_session[sess]
            invocations.append({
                "request_id": "%s:%s" % (pid_, arm), "pair_id": pid_,
                "schedule_position": pos, "arm": arm, "workload": "wl",
                "strategy": arm, "seed": seed, "first_operation_id": 0,
                "handle_mode": hm, "repetition_id": rep,
                "schedule_seed": 20260804})
            reqs[pos] = make_req(pos, pid_, arm, seed, hm, rep)
            resps[pos] = make_resp(pos, pid_, arm, seed, hm, rep, ctr,
                                   process_uuid=spec.get("process_uuid", "proc-1"),
                                   pid_num=spec.get("pid_num", 1000),
                                   db_inode=spec.get("db_inode", 42),
                                   overrides=spec.get("resp_overrides"))
            pos += 1
    schedule = {"invocations": invocations, "pairs": pairs}
    return schedule, reqs, resps


def build(schedule, reqs, resps, campaign="primary"):
    return N.build_rows(campaign, schedule, reqs, resps, AUTH,
                        AUTH["run_config_sha256"], "bundle.tar.gz", "0" * 64,
                        "gitsha", FP, PAGE_SIZE)


class TestPairingAndOrder(unittest.TestCase):
    def test_baseline_paired_target_strategy(self):
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "2e_K10"}])
        rows, problems = build(sched, reqs, resps)
        self.assertEqual(problems, [])
        base = [r for r in rows if r["strategy"] == "baseline"][0]
        # the baseline row must carry the target it was paired against, not "baseline"
        self.assertEqual(base["paired_target_strategy"], "2e_K10")

    def test_order_from_schedule_position_not_arm_label(self):
        # BA order: target arm executes FIRST (lower schedule_position)
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "2d", "baseline_first": False}])
        rows, problems = build(sched, reqs, resps)
        self.assertEqual(problems, [])
        tgt = [r for r in rows if r["strategy"] == "2d"][0]
        base = [r for r in rows if r["strategy"] == "baseline"][0]
        self.assertTrue(tgt["is_first_in_pair"])
        self.assertFalse(base["is_first_in_pair"])
        self.assertEqual(tgt["position_within_pair"], 1)
        self.assertEqual(base["position_within_pair"], 2)
        # first/second strategy fields agree, derived from position
        self.assertEqual(tgt["pair_first_strategy"], "2d")
        self.assertEqual(tgt["pair_second_strategy"], "baseline")

    def test_second_arm_not_dropped(self):
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "2d", "baseline_first": False}])
        rows, _ = build(sched, reqs, resps)
        # both arms preserved
        self.assertEqual(len(rows), 2)

    def test_exactly_one_baseline_one_target_per_pair(self):
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "2d"}])
        rows, _ = build(sched, reqs, resps)
        pairs, problems = N.derive_pairs(rows)
        self.assertEqual(problems, [])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["paired_target_strategy"], "2d")

    def test_selected_bytes_derivation(self):
        sched, reqs, resps = make_campaign([{"pair_id": "p1", "target": "2d"}])
        rows, _ = build(sched, reqs, resps)
        self.assertEqual(rows[0]["selected_bytes"], 102 * PAGE_SIZE)


class TestFailClosed(unittest.TestCase):
    def test_duplicate_request_id_rejected(self):
        sched, reqs, resps = make_campaign([{"pair_id": "p1", "target": "2d"}])
        # force both arms to share a request_id
        for pos in reqs:
            reqs[pos]["request_id"] = "dup"
            resps[pos]["request_id"] = "dup"
        for inv in sched["invocations"]:
            inv["request_id"] = "dup"
        rows, problems = build(sched, reqs, resps)
        self.assertTrue(any("duplicate request_id" in p for p in problems))

    def test_missing_response_rejected(self):
        sched, reqs, resps = make_campaign([{"pair_id": "p1", "target": "2d"}])
        del resps[2]                       # drop the second arm's response
        rows, problems = build(sched, reqs, resps)
        self.assertTrue(any("missing response" in p for p in problems))

    def test_invalid_response_flag_rejected(self):
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "2d",
              "resp_overrides": {"measured_valid": False}}])
        rows, problems = build(sched, reqs, resps)
        self.assertTrue(any("collect.classify invalid" in p for p in problems))
        # the invalid arm is not emitted as a clean row
        self.assertLess(len(rows), 2)

    def test_synthetic_dry_run_rejected(self):
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "2d",
              "resp_overrides": {"_dry_run": True}}])
        rows, problems = build(sched, reqs, resps)
        self.assertTrue(any("response_gate=synthetic" in p for p in problems))

    def test_cross_identity_pairing_rejected(self):
        # two arms of one pair disagree on seed -> derive_pairs must complain
        sched, reqs, resps = make_campaign([{"pair_id": "p1", "target": "2d"}])
        rows, _ = build(sched, reqs, resps)
        # mutate one row's seed after the fact
        rows[0]["seed"] = 999
        pairs, problems = N.derive_pairs(rows)
        self.assertTrue(any("disagree on seed" in p for p in problems))

    def test_selected_page_invariant_gate(self):
        # a secondary-style campaign cfg with an exact selected_page_count gate
        cfg = {"campaign": "secondary",
               "expected": {"invocations": 2, "pairs": 1, "baseline": 1,
                            "per_target": 1},
               "expected_targets": {"leaf_freq_K10"},
               "expected_selected_page_count": {"leaf_freq_K10": 10}}
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "leaf_freq_K10"}], campaign="secondary")
        rows, _ = N.build_rows(
            "secondary", sched, reqs, resps, AUTH, AUTH["run_config_sha256"],
            "b.tgz", "0" * 64, "g", FP, PAGE_SIZE)
        pairs, _ = N.derive_pairs(rows)
        # rows carry selected_page_count=102 from the fixture, gate expects 10
        problems = N.run_gates(cfg, rows, pairs)
        self.assertTrue(any("selected_page_count" in p for p in problems))

    def test_clean_small_campaign_passes_gates(self):
        cfg = {"campaign": "secondary",
               "expected": {"invocations": 2, "pairs": 1, "baseline": 1,
                            "per_target": 1},
               "expected_targets": {"leaf_freq_K10"},
               "expected_selected_page_count": {"leaf_freq_K10": 10}}
        sched, reqs, resps = make_campaign(
            [{"pair_id": "p1", "target": "leaf_freq_K10",
              "resp_overrides": {"selected_page_count": 10,
                                 "selected_leaf_count": 10,
                                 "selected_interior_count": 0}}],
            campaign="secondary")
        rows, prob1 = N.build_rows(
            "secondary", sched, reqs, resps, AUTH, AUTH["run_config_sha256"],
            "b.tgz", "0" * 64, "g", FP, PAGE_SIZE)
        pairs, prob2 = N.derive_pairs(rows)
        problems = N.run_gates(cfg, rows, pairs)
        self.assertEqual(prob1, [])
        self.assertEqual(prob2, [])
        self.assertEqual(problems, [])


# --------------------------------------------------------------------------
# Integration checks against the actual generated artifacts (skipped if absent)
# --------------------------------------------------------------------------
OUT = _OW_ROOT / "analysis" / "normalized"
MANIFEST = OUT / "normalization_manifest.json"


@unittest.skipUnless(MANIFEST.exists(),
                     "run analysis/normalize.py first to generate outputs")
class TestGeneratedOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.man = json.loads(MANIFEST.read_text())

    def test_combined_counts(self):
        c = self.man["combined"]
        self.assertEqual(c["invocations"], 3600)
        self.assertEqual(c["pairs"], 1800)
        self.assertEqual(c["baseline"], 1800)
        self.assertEqual(c["target"], 1800)

    def test_per_campaign_counts(self):
        by = {c["campaign"]: c for c in self.man["campaigns"]}
        self.assertEqual(by["primary"]["invocations"], 1600)
        self.assertEqual(by["primary"]["pairs"], 800)
        self.assertEqual(by["secondary"]["invocations"], 2000)
        self.assertEqual(by["secondary"]["pairs"], 1000)

    def test_secondary_bundle_manifest_quirk_not_authoritative(self):
        by = {c["campaign"]: c for c in self.man["campaigns"]}
        sec = by["secondary"]
        # the packaging summary carries the PRIMARY run_config; the normalizer
        # must NOT let it override the authoritative (schedule-derived) identity
        self.assertFalse(sec["bundle_manifest_run_config_matches_authoritative"])
        self.assertEqual(
            sec["authoritative_run_config_sha256"],
            "441609e611a38cb10e1f0a4cfc058991d3b8850d71b83e7092610ee469a58299")
        self.assertEqual(
            sec["bundle_manifest_run_config_sha256"],
            "022fbeb01a8d9d45686e56823eca1e1ef30712f2a13c4a878cb5f7ef0097b5b7")

    def test_primary_fingerprint_is_evidence_derived_not_stale(self):
        by = {c["campaign"]: c for c in self.man["campaigns"]}
        prim = by["primary"]
        # recomputed fingerprint must equal the stored one, and must NOT be the
        # stale historical d08266ca... value
        self.assertEqual(prim["schedule_fingerprint"],
                         prim["schedule_fingerprint_recomputed"])
        self.assertNotEqual(prim["schedule_fingerprint"][:8], "d08266ca")

    def test_ok_flag(self):
        self.assertTrue(self.man["ok"])

    def test_deterministic_rerun_bytes(self):
        # rerun into a temp dir and compare data-file SHAs to the manifest
        import tempfile
        import normalize as NN
        with tempfile.TemporaryDirectory() as tmp:
            ok, man2 = NN.normalize(str(_OW_ROOT), tmp)
            self.assertTrue(ok)
            for fn in ("normalized_invocations.csv", "normalized_pairs.csv"):
                self.assertEqual(self.man["outputs"][fn]["sha256"],
                                 man2["outputs"][fn]["sha256"],
                                 "%s not byte-stable across runs" % fn)


if __name__ == "__main__":
    unittest.main()
