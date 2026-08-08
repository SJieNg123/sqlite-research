"""Regression tests for the 05_full_matrix DRY_RUN-contamination fix.

The bug: a DRY_RUN wrote synthetic placeholder responses
(`{"_dry_run": true, ...}`) into the SAME measured raw/ directory a real run reads,
and the resume logic skipped any position whose response file merely EXISTED. A
subsequent real run therefore "resumed" over 400 synthetic responses and performed
zero measured invocations while reporting completion.

These tests pin the fail-closed fix, whose logic lives in the shared, tested
`ws2/response_gate.py`:

  * a `_dry_run:true` response is never accepted as a completed measurement,
  * a real, identity-matching response may be resumed,
  * a mismatching / malformed / missing response is never counted as complete,
  * WS2_FORCE purges synthetic responses, and
  * a 400-position matrix cannot report completion from synthetic responses.

The 05/06 script wiring (isolated dry-run tree, resume gated on classification,
completion gate before PASS, collect refusing synthetic evidence) is checked
against the scripts on disk.
"""
import importlib.util
import json
import os
import tempfile
import unittest

import _fixture

REPO = _fixture.REPO
WS2 = os.path.join(REPO, "deployment", "openwhisk", "ws2")
MATRIX = os.path.join(WS2, "05_full_matrix.sh")
COLLECT = os.path.join(WS2, "06_collect.sh")


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "response_gate", os.path.join(WS2, "response_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(p):
    with open(p) as f:
        return f.read()


def _dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f)


GATE = _load_gate()
IMAGE = "localhost:5000/sqlite-coldstart@sha256:" + "a" * 64


def _req(pos=1, strategy="2d", seed=1):
    """A schedule-shaped request carrying every identity field the action echoes."""
    return {
        "request_id": "native_ycsb_c_read_zipf-s%d-f0-warm-r0-2d:%s" % (seed, strategy),
        "pair_id": "native_ycsb_c_read_zipf-s%d-f0-warm-r0-2d" % seed,
        "schedule_position": pos, "run_config_sha256": "c" * 64,
        "expected_action_image_digest": IMAGE, "workload": "native_ycsb_c_read_zipf",
        "strategy": strategy, "seed": seed, "first_operation_id": 0,
        "handle_mode": "warm", "repetition_id": 0, "schedule_seed": 20260804,
    }


def _real_resp(req, measured_valid=False):
    """A real handler response: echoes the request identity + measured_valid."""
    r = {f: req[f] for f in GATE.IDENTITY_FIELDS}
    r["measured_valid"] = measured_valid
    r["warm_session_id"] = "sess-%s" % req["schedule_position"]
    return r


_SYNTHETIC = {"_dry_run": True, "note": "no invocation performed under DRY_RUN=1"}


class TestClassifyResponse(unittest.TestCase):
    def test_synthetic_dry_run_is_never_valid(self):
        status, _ = GATE.classify_response(_req(), dict(_SYNTHETIC), IMAGE)
        self.assertEqual(status, "synthetic")

    def test_valid_identity_matching_response_is_resumable(self):
        req = _req()
        status, _ = GATE.classify_response(req, _real_resp(req), IMAGE)
        self.assertEqual(status, "valid")

    def test_identity_mismatch_is_rejected(self):
        req = _req(seed=1)
        resp = _real_resp(_req(seed=2))          # a response for a different cell
        status, _ = GATE.classify_response(req, resp, IMAGE)
        self.assertEqual(status, "mismatch")

    def test_image_digest_mismatch_is_rejected(self):
        req = _req()
        status, _ = GATE.classify_response(req, _real_resp(req),
                                           "localhost:5000/sqlite-coldstart@sha256:" + "b" * 64)
        self.assertEqual(status, "mismatch")

    def test_missing_measured_valid_is_malformed(self):
        req = _req()
        resp = {f: req[f] for f in GATE.IDENTITY_FIELDS}   # real-ish but no measured_valid
        status, _ = GATE.classify_response(req, resp, IMAGE)
        self.assertEqual(status, "malformed")

    def test_non_dict_is_malformed(self):
        status, _ = GATE.classify_response(_req(), ["not", "a", "dict"], IMAGE)
        self.assertEqual(status, "malformed")


class TestVerifyComplete(unittest.TestCase):
    def _write_matrix(self, d, n, resp_kind):
        """Write n req files and, per resp_kind, their response files."""
        for pos in range(1, n + 1):
            req = _req(pos=pos, seed=((pos - 1) % 10) + 1)
            _dump(req, os.path.join(d, "req_%06d.json" % pos))
            if resp_kind == "synthetic":
                _dump(dict(_SYNTHETIC), os.path.join(d, "resp_%06d.json" % pos))
            elif resp_kind == "valid":
                _dump(_real_resp(req), os.path.join(d, "resp_%06d.json" % pos))
            # resp_kind == "missing": write no response

    def test_synthetic_responses_never_report_completion(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_matrix(d, 5, "synthetic")
            bad = GATE.verify_complete(d, IMAGE)
            self.assertEqual(len(bad), 5)
            self.assertTrue(all(status == "synthetic" for _, status, _ in bad))

    def test_all_valid_responses_are_complete(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_matrix(d, 5, "valid")
            self.assertEqual(GATE.verify_complete(d, IMAGE), [])

    def test_missing_response_is_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_matrix(d, 3, "missing")
            bad = GATE.verify_complete(d, IMAGE)
            self.assertEqual(len(bad), 3)
            self.assertTrue(all(status == "missing" for _, status, _ in bad))

    def test_400_position_matrix_cannot_complete_on_synthetic(self):
        # The reported failure mode, at scale: 400 synthetic responses -> not one
        # counts as a completed measurement.
        with tempfile.TemporaryDirectory() as d:
            self._write_matrix(d, 400, "synthetic")
            bad = GATE.verify_complete(d, IMAGE)
            self.assertEqual(len(bad), 400)
        with tempfile.TemporaryDirectory() as d:
            self._write_matrix(d, 400, "valid")
            self.assertEqual(GATE.verify_complete(d, IMAGE), [])


class TestPurgeAndScanSynthetic(unittest.TestCase):
    def test_purge_removes_only_synthetic_responses(self):
        with tempfile.TemporaryDirectory() as d:
            _dump(dict(_SYNTHETIC), os.path.join(d, "resp_000001.json"))
            _dump(_real_resp(_req(pos=2, seed=2)), os.path.join(d, "resp_000002.json"))
            removed = GATE.purge_synthetic(d)
            self.assertEqual([os.path.basename(p) for p in removed], ["resp_000001.json"])
            self.assertFalse(os.path.exists(os.path.join(d, "resp_000001.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "resp_000002.json")))

    def test_scan_finds_synthetic_anywhere_in_tree(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "05_full_matrix", "dryrun_raw")
            os.makedirs(sub)
            _dump(dict(_SYNTHETIC), os.path.join(sub, "resp_000001.json"))
            # a non-response manifest json with no _dry_run must NOT be flagged
            _dump({"action_name": "x"}, os.path.join(d, "deploy_meta.json"))
            found = GATE.scan_synthetic([d])
            self.assertEqual([os.path.basename(p) for p in found], ["resp_000001.json"])

    def test_scan_clean_tree_finds_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            _dump(_real_resp(_req()), os.path.join(d, "resp_000001.json"))
            self.assertEqual(GATE.scan_synthetic([d]), [])


class TestMatrixScriptWiring(unittest.TestCase):
    def setUp(self):
        self.txt = _read(MATRIX)

    def test_dry_run_responses_isolated_from_measured_raw(self):
        # DRY_RUN synthetic responses are written into the isolated dry-run tree,
        # never the measured raw/ directory.
        self.assertIn("DRYRUN_RAW=", self.txt)
        self.assertIn('ws2_invoke "$OW_ACTION_NAME" "$req" "$DRYRUN_RAW/resp_${pos}.json"', self.txt)
        self.assertNotIn('ws2_invoke "$OW_ACTION_NAME" "$req" "$RAW/resp_${pos}.json"', self.txt)

    def test_resume_skip_is_gated_on_classification(self):
        # a position is skipped only after response_gate classifies it valid.
        self.assertIn("response_gate.py", self.txt)
        self.assertIn("classify", self.txt)
        self.assertIn("has a validated real response", self.txt)
        self.assertNotIn("already has a response; skipping", self.txt)

    def test_wsforce_purges_synthetic_responses(self):
        self.assertIn("purge-synthetic", self.txt)

    def test_completion_gate_precedes_pass(self):
        self.assertIn("verify-complete", self.txt)
        self.assertLess(self.txt.index("verify-complete"),
                        self.txt.index('ws2_mark_status "$WS2_STAGEDIR" done PASS'),
                        "the completion gate must run before PASS is granted")


class TestCollectScriptWiring(unittest.TestCase):
    def test_collect_refuses_synthetic_evidence_before_packaging(self):
        txt = _read(COLLECT)
        self.assertIn("scan-synthetic", txt)
        self.assertLess(txt.index("scan-synthetic"), txt.index("tar -czf"),
                        "synthetic scan must run before the tarball is written")


if __name__ == "__main__":
    unittest.main()
