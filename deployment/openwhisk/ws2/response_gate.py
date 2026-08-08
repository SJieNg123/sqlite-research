#!/usr/bin/env python3
"""Fail-closed response gate for the measured WS2 matrix stage (05_full_matrix).

A DRY_RUN invocation writes a synthetic placeholder response
(`{"_dry_run": true, ...}`) instead of contacting OpenWhisk. Those synthetic
responses must NEVER be mistaken for completed measured evidence: a real run must
not resume over them, and the collect stage must not package them.

This module is the single source of truth for three decisions:

  * `classify_response(req, resp, image_digest)` -- may an existing response file
    stand in for a completed measurement of `req`?  It returns one of:
      - "valid"     : a real handler response whose identity matches the request
                      (and the deployed image digest); safe to resume/skip.
      - "synthetic" : a DRY_RUN placeholder (`_dry_run` truthy); never measured.
      - "malformed" : not a real handler response (e.g. missing `measured_valid`).
      - "mismatch"  : a real-looking response whose identity does not match.
  * `verify_complete(raw_dir, image_digest)` -- every scheduled position has a
    "valid" real response (PASS is never granted just because a resp file exists).
  * synthetic detection (`is_synthetic`, `purge_synthetic`, `scan_synthetic`) --
    used by WS2_FORCE cleanup and by 06_collect's refusal to package DRY_RUN
    output as measured evidence.

The identity fields checked are exactly those the action echoes back from the
request (see action/main.py ECHO_FIELDS + the workload/strategy/seed block and the
top-level request_id), so a genuine handler response matches and a truncated or
foreign one does not.
"""
import glob
import json
import os
import sys

# Request identity fields a real handler response echoes verbatim. A resumable
# response must match the request on every one of these (see action/main.py).
IDENTITY_FIELDS = (
    "request_id", "pair_id", "schedule_position", "run_config_sha256",
    "expected_action_image_digest", "workload", "strategy", "seed",
    "first_operation_id", "handle_mode", "repetition_id", "schedule_seed",
)


def is_synthetic(resp):
    """True iff `resp` is a DRY_RUN synthetic placeholder."""
    return isinstance(resp, dict) and bool(resp.get("_dry_run"))


def classify_response(req, resp, image_digest=None):
    """Classify an existing response against its request.

    Returns (status, reason) where status is one of
    "valid" / "synthetic" / "malformed" / "mismatch". Only "valid" may be
    resumed/counted as a completed measurement.
    """
    if not isinstance(resp, dict):
        return ("malformed", "response is not a JSON object")
    if is_synthetic(resp):
        return ("synthetic",
                "DRY_RUN synthetic placeholder (_dry_run truthy); not a measurement")
    # A real handler response always carries measured_valid (True/False/None). Its
    # absence means this is not a handler response at all (partial write, wrong file).
    if "measured_valid" not in resp:
        return ("malformed",
                "response lacks measured_valid; not a real handler response")
    for f in IDENTITY_FIELDS:
        if resp.get(f) != req.get(f):
            return ("mismatch", "identity mismatch on %s: req=%r resp=%r"
                    % (f, req.get(f), resp.get(f)))
    if image_digest is not None and resp.get("expected_action_image_digest") != image_digest:
        return ("mismatch", "expected_action_image_digest %r does not match deployed image %r"
                % (resp.get("expected_action_image_digest"), image_digest))
    return ("valid", "real handler response; identity matches")


def _load(path):
    """Load JSON; return (obj, None) or (None, reason)."""
    try:
        with open(path) as f:
            return (json.load(f), None)
    except (OSError, ValueError) as e:
        return (None, str(e))


def _positions(raw_dir):
    """Yield (position, req_path, resp_path) for every scheduled request."""
    for req_path in sorted(glob.glob(os.path.join(raw_dir, "req_*.json"))):
        pos = os.path.basename(req_path)[len("req_"):-len(".json")]
        resp_path = os.path.join(raw_dir, "resp_%s.json" % pos)
        yield pos, req_path, resp_path


def verify_complete(raw_dir, image_digest=None):
    """Return a list of (position, status, reason) for every position WITHOUT a
    valid real response. Empty list == complete. A missing response is reported as
    ("missing", ...). This never treats a synthetic/malformed/mismatched response
    as complete."""
    bad = []
    for pos, req_path, resp_path in _positions(raw_dir):
        req, err = _load(req_path)
        if err is not None:
            bad.append((pos, "missing", "request unreadable: %s" % err)); continue
        if not os.path.exists(resp_path):
            bad.append((pos, "missing", "no response file")); continue
        resp, err = _load(resp_path)
        if err is not None:
            bad.append((pos, "malformed", "response unreadable: %s" % err)); continue
        status, reason = classify_response(req, resp, image_digest)
        if status != "valid":
            bad.append((pos, status, reason))
    return bad


def purge_synthetic(dir_path):
    """Remove synthetic (DRY_RUN) resp_*.json files under `dir_path`. Returns the
    list of removed paths. Non-synthetic and non-response files are left intact."""
    removed = []
    for resp_path in sorted(glob.glob(os.path.join(dir_path, "resp_*.json"))):
        resp, err = _load(resp_path)
        if err is None and is_synthetic(resp):
            os.remove(resp_path)
            removed.append(resp_path)
    return removed


def scan_synthetic(paths):
    """Return every *.json file under the given paths (files or dirs, recursive)
    that is a synthetic DRY_RUN placeholder. Used to refuse packaging DRY_RUN
    output as measured evidence."""
    found = []
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                files.extend(os.path.join(root, n) for n in names if n.endswith(".json"))
        elif os.path.isfile(p) and p.endswith(".json"):
            files.append(p)
    for f in sorted(files):
        obj, err = _load(f)
        if err is None and is_synthetic(obj):
            found.append(f)
    return found


# --------------------------------------------------------------------------- #
# CLI: thin wrappers used by 05_full_matrix.sh and 06_collect.sh.             #
#   classify <req> <resp> [image]  -> exit 0 valid / 10 synthetic / 20 other  #
#   verify-complete <raw_dir> [image] -> exit 0 complete / 1 otherwise        #
#   purge-synthetic <dir>          -> remove synthetic resp files (exit 0)     #
#   scan-synthetic <path>...       -> exit 0 none found / 1 if any synthetic   #
# --------------------------------------------------------------------------- #
def _main(argv):
    if not argv:
        print("usage: response_gate.py "
              "{classify|verify-complete|purge-synthetic|scan-synthetic} ...", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "classify":
        if len(rest) < 2:
            print("usage: classify <req.json> <resp.json> [image_digest]", file=sys.stderr)
            return 2
        req, err = _load(rest[0])
        if err is not None:
            print("malformed: request unreadable: %s" % err, file=sys.stderr); return 20
        resp, err = _load(rest[1])
        if err is not None:
            # An unreadable response file is not a completed measurement.
            print("malformed: response unreadable: %s" % err, file=sys.stderr); return 20
        image = rest[2] if len(rest) > 2 else None
        status, reason = classify_response(req, resp, image)
        print("%s: %s" % (status, reason))
        return {"valid": 0, "synthetic": 10}.get(status, 20)

    if cmd == "verify-complete":
        if not rest:
            print("usage: verify-complete <raw_dir> [image_digest]", file=sys.stderr)
            return 2
        image = rest[1] if len(rest) > 1 else None
        bad = verify_complete(rest[0], image)
        if not bad:
            n = sum(1 for _ in _positions(rest[0]))
            print("complete: %d positions each have a validated real response" % n)
            return 0
        for pos, status, reason in bad:
            print("INCOMPLETE position %s: %s (%s)" % (pos, status, reason), file=sys.stderr)
        print("FAIL: %d position(s) without a validated non-synthetic real response"
              % len(bad), file=sys.stderr)
        return 1

    if cmd == "purge-synthetic":
        if not rest:
            print("usage: purge-synthetic <dir>", file=sys.stderr); return 2
        removed = purge_synthetic(rest[0])
        for p in removed:
            print("purged synthetic response: %s" % p, file=sys.stderr)
        print("purged %d synthetic response file(s) from %s" % (len(removed), rest[0]))
        return 0

    if cmd == "scan-synthetic":
        if not rest:
            print("usage: scan-synthetic <path>...", file=sys.stderr); return 2
        found = scan_synthetic(rest)
        for f in found:
            print("SYNTHETIC (_dry_run) response present: %s" % f, file=sys.stderr)
        if found:
            print("FAIL: %d synthetic DRY_RUN response(s) found" % len(found), file=sys.stderr)
            return 1
        print("clean: no synthetic DRY_RUN responses found")
        return 0

    print("unknown command: %s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
