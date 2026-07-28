#!/usr/bin/env python3
"""YCSB BasicDB verbose log -> op stream (JSONL).

Format conversion ONLY. No key remapping, no key sorting, no filling in not-found
keys here (that would throw away the credibility we just bought). The order-preserving
dense-rowid mapping is a SEPARATE step: tools/keymap.py.

Reality the spec's §2.3 sketch missed: YCSB writes THREE interleaved stream types to
stdout -- the `***properties***` banner, the BasicDB verbose op lines, and the end-of-run
measurement export (`[READ], Operations, ...`, GC stats). A naive `if not m: n_bad+=1`
parser would false-fail on every banner/export line. So we classify each line as
  op  |  known-noise (banner / property / export)  |  UNKNOWN
and fail-fast ONLY on UNKNOWN, while still asserting parsed-op-count == expected.
(measured verbose op grammar, YCSB 0.17.0:  `OP usertable user<19d> [<scanlen>] [ <fields> ]`)

Usage:  ycsb2trace.py <verbose_log> <expected_ops> [--out trace.jsonl]
On success prints a one-line stats summary to stderr and the JSONL to --out (or stdout).
Exit non-zero on any UNKNOWN line or op-count mismatch.
"""
import argparse
import json
import re
import sys

# an op line: verb, the fixed table token `usertable`, a user<digits> key,
# an optional integer scan length (SCAN only), then the ` [ ... ]` field blob.
OP = re.compile(
    r'^(READ|INSERT|UPDATE|SCAN|READMODIFYWRITE|DELETE)\s+'
    r'usertable\s+'
    r'(user\d+)'
    r'(?:\s+(\d+))?'          # scan length (SCAN only)
    r'\s*\[')

# lines we positively recognise as NOT ops (so an unrecognised line is a real error).
NOISE = re.compile(
    r'^\s*$'                                   # blank
    r'|^\*+.*\*+\s*$|^\*{3,}'                   # ***** properties ***** banners
    r'|^"[^"]*"\s*=\s*"[^"]*"\s*$'             # "key"="value" property dump
    r'|^\[[^\]]*\],'                           # [READ], Operations, 8   (measurement export)
    r'|^Command line:|^YCSB Client|^Loading workload|^Starting test'
    r'|^DBWrapper|^\s*$')

SCAN_OPS = {"SCAN"}

# Only workloadf contains readmodifywrite in the headline family (§4). RMW emits TWO
# BasicDB verbose lines (READ then UPDATE, same key) -> the trace has more LINES than
# YCSB OPERATIONS. Design choice (a): keep BOTH lines. The parser transcribes only; it
# must NOT reconstruct "read+update == one rmw" (§2.3 red line — and that rule would
# also silently eat a genuine independent update in workloada). Instead the guard knows,
# per workload, the deterministic initiator-line invariant: every YCSB op emits exactly
# one initiator line (read/rmw->READ, update->UPDATE, insert->INSERT, scan->SCAN); rmw
# adds one follow-up UPDATE. So #ops == #initiators == operationcount.
RMW_WORKLOADS = {"workloadf"}


def op_accounting(ops, workload):
    """Return (#YCSB ops, line-level mix, op-level mix). Structural, per-workload."""
    from collections import Counter
    line_mix = dict(Counter(o["op"] for o in ops))          # physically in the trace
    if workload in RMW_WORKLOADS:
        n_read, n_upd = line_mix.get("read", 0), line_mix.get("update", 0)
        ycsb_ops = n_read                                    # every op starts with a READ
        # all updates here are rmw follow-ups (workloadf has no independent update);
        # pure reads = READ - UPDATE, rmw = UPDATE.
        op_mix = {"read": n_read - n_upd, "readmodifywrite": n_upd}
    else:
        ycsb_ops = len(ops)                                  # 1 line per op
        op_mix = dict(line_mix)
    return ycsb_ops, line_mix, op_mix


def parse(path, expected_ops):
    ops, n_noise, unknown = [], 0, []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            m = OP.match(line)
            if m:
                verb, key, scanlen = m.groups()
                if (verb in SCAN_OPS) != (scanlen is not None):
                    unknown.append((lineno, line))   # scanlen presence must match SCAN
                    continue
                ops.append({"op": verb.lower(), "key": key,
                            "scanlen": int(scanlen) if scanlen is not None else None})
            elif NOISE.match(line):
                n_noise += 1
            else:
                unknown.append((lineno, line))
    return ops, n_noise, unknown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("expected_ops", type=int)
    ap.add_argument("--out", default="-")
    ap.add_argument("--workload", default="",
                    help="YCSB workload name; enables the per-workload op-count guard "
                         "(rmw workloads emit 2 lines/op)")
    args = ap.parse_args()

    ops, n_noise, unknown = parse(args.log, args.expected_ops)
    ycsb_ops, line_mix, op_mix = op_accounting(ops, args.workload)

    # ---- fail-fast: any unknown line, or wrong op count, is fatal (spec §2.3) ----
    if unknown:
        sample = "\n".join(f"  L{ln}: {txt!r}" for ln, txt in unknown[:5])
        raise SystemExit(
            f"FAIL: {len(unknown)} UNKNOWN (unparsable) line(s) — threads>1? format drift?\n"
            f"{sample}")
    # per-workload op-count guard (loud). #YCSB ops must == operationcount.
    guard_ok = (ycsb_ops == args.expected_ops)
    if args.workload in RMW_WORKLOADS:
        guard_ok = guard_ok and (line_mix.get("update", 0) <= line_mix.get("read", 0))
    if not guard_ok:
        raise SystemExit(
            f"FAIL: op-count guard failed (workload={args.workload or '<generic>'}): "
            f"ycsb_ops={ycsb_ops} vs operationcount={args.expected_ops}; "
            f"line_mix={line_mix} (silent op loss / wrong operationcount)")

    out = sys.stdout if args.out == "-" else open(args.out, "w")
    for rec in ops:                                   # choice (a): write ALL lines
        out.write(json.dumps(rec) + "\n")
    if out is not sys.stdout:
        out.close()
    sys.stderr.write(
        f"ycsb2trace: trace_lines={len(ops)} ycsb_ops={ycsb_ops} "
        f"line_mix={line_mix} op_mix={op_mix} noise_lines={n_noise} parse_losses=0 -> {args.out}\n")


if __name__ == "__main__":
    main()
