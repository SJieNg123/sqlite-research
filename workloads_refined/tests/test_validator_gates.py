#!/usr/bin/env python3
"""Fire tests for the Tier-0 gates (§-1.3 fire-test rule).

A gate with no test proving it FIRES is treated as non-existent. And a gate must be shown NOT
to false-fire on a good input -- a gate that rejects everything passes every failure test (that
is exactly the moving-hotspot bug these tests caught). So each gate is exercised on BOTH its
failure path(s) AND, where a good input exists, its pass path.

Test fixtures are NOT experiment data: they carry KNOWN CORRECT ANSWERS to verify the tool.
That is why synthetic fixtures are legitimate here and OUTSIDE §2.3's red line -- that rule
forbids fabricating traces for the EXPERIMENT, not for testing the validator. (You cannot use
a real trace like YD to test the gate: you do not know what YD *should* score -- that is what
the gate is for.) The strongest fixtures are the graves: the real workload_c / workload_churn
that actually bit this project.

Run: python3 tests/test_validator_gates.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
WL = os.path.join(HERE, "..", "..", "workloads")
FIX = os.path.join(HERE, "fixtures")   # FROZEN graves (retire-proof; §1.3 retires the workloads/ copies)
sys.path.insert(0, TOOLS)
import validate_trace as vt  # noqa: E402

THR = vt.load_thresholds(vt.DEFAULT_THRESHOLDS)
N, SEG = 600_000, 10


# ---------------- gate 1: moving-hotspot (§5.2) -- 3 fail paths + 1 PASS path ----------------
def _diag(targets):
    return vt.hotspot_movement(targets, SEG, vt.measured_skew(targets),
                               len(set(targets)) / len(targets), THR)


def _diag_path(path):
    ops = vt.load_trace(path)
    return _diag([k for op, k, _ in ops if op in vt.TARGET_OPS])


def _move_pass(d):
    return bool(d["hotset_present"] and d["contiguous"]
               and d["centroid_displacement_frac"] is not None
               and d["centroid_displacement_frac"] >= THR["min_centroid_displacement_frac"])


def _block(hot):     # ~80% ops to the hot set (interleaved) + sparse uniform background
    return list(hot) * 80 + list(range(0, N, 30))


def test_moving_hotspot_gate():
    # synthetic fixtures with KNOWN answers -- this is how you test a gate: you know the truth.
    moving = sum((_block(range(i * (N // SEG), i * (N // SEG) + 1000)) for i in range(SEG)), [])
    static = _block(range(300_000, 301_000)) * SEG
    uniform = list(range(N))
    assert _move_pass(_diag(moving)) is True,  "PASS path: a moving hotspot must pass (else the gate kills YD)"
    assert _move_pass(_diag(static)) is False, "fail: a static hotspot is not moving"
    assert _diag(uniform)["hotset_present"] is False, "fail: uniform has no hotset"
    # the FROZEN grave + real fixed hotspots (strongest fixtures: they actually bit us)
    assert _diag_path(os.path.join(FIX, "grave_churn_no_hotset.txt"))["hotset_present"] is False, "grave churn: no hotset"
    dh = _diag_path(os.path.join(WL, "workload_ych_hashed_010_1.txt"))
    assert dh["hotset_present"] and not dh["contiguous"], "YC-h/hashed: scattered in rowid space"
    do = _diag_path(os.path.join(WL, "workload_ych_ordered_010_1.txt"))
    assert do["hotset_present"] and do["contiguous"] and not _move_pass(do), "YC-h/ordered: static"
    print("  [ok] moving-hotspot: fires on no-hotset/scattered/static, PASSES a moving hotspot")


# ---------------- verdict-level fire tests (run the tool, assert it FAILS) ----------------
def _run(tool, *args):
    return subprocess.run([sys.executable, os.path.join(TOOLS, tool), *args],
                          capture_output=True, text=True)


def test_notfound_gate_grave_C():
    out = tempfile.mktemp(suffix=".json")
    p = _run("validate_trace.py", os.path.join(FIX, "grave_c_notfound.txt"), "--out", out, "--db-max-key", "600000")
    rep = json.load(open(out))
    assert p.returncode != 0 and rep["verdict"] == "FAIL", "not-found gate must FIRE on grave C"
    assert 0.35 < rep["notfound_rate"] < 0.65, f"grave C notfound {rep['notfound_rate']} not ~0.5"
    print(f"  [ok] not-found: grave C -> FAIL (notfound={rep['notfound_rate']})")


def test_parse_losses_gate():
    log = tempfile.mktemp(suffix=".log")
    with open(log, "w") as f:
        f.write("READ usertable user0000000000000000001 [ f=x ]\n")
        f.write("### garbage: not an op, not known-noise -> must NOT be silently dropped ###\n")
    p = _run("ycsb2trace.py", log, "2", "--workload", "workloadc")
    assert p.returncode != 0, "parse gate must FIRE on an unparseable line (non-zero exit)"
    print("  [ok] parse-losses: garbage line -> non-zero exit (no silent op loss)")


if __name__ == "__main__":
    test_moving_hotspot_gate()
    test_notfound_gate_grave_C()
    test_parse_losses_gate()
    print("PASS: all gate fire tests (moving-hotspot 3-fail+1-pass, not-found grave C, parse-losses)")
