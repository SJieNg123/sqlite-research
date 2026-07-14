#!/usr/bin/env bash
# gen_ycsb_trace.sh — produce ONE harness-ready workload from real YCSB.
#
#   real YCSB (java Client + BasicDB verbose)  ->  raw load+run logs
#      -> ycsb2trace.py (parse, fail-fast)     ->  <name>.jsonl
#      -> keymap.py (order-preserving dense rowid from the load dump)
#      -> workloads/workload_<key>_1.txt       (integer-key, harness format)
#      -> validate_trace.py (Tier 0)           ->  .validation.json  (fails loud)
#      -> .manifest.json  (gen_workload field names + YCSB provenance)
#
# Usage:
#   gen_ycsb_trace.sh <NAME> <KEY> <YCSB_WORKLOAD> <REQUESTDIST> <INSERTORDER> \
#                     <RECORDCOUNT> <OPERATIONCOUNT> [extra -p props ...]
# Example (headline):
#   gen_ycsb_trace.sh YC-hashed yc workloadc zipfian hashed 600000 80000
set -euo pipefail

NAME="${1:?name}"; KEY="${2:?key}"; WL="${3:?ycsb workload}"; DIST="${4:?requestdistribution}"
IO="${5:?insertorder}"; RC="${6:?recordcount}"; OPS="${7:?operationcount}"; shift 7
EXTRA=("$@")

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
JAVA="$HOME/ycsb-tools/jre/bin/java"
CP="$HOME/ycsb-tools/jars/*"
ZP=19                      # fixed-width keys (verified §3.2b)
ORIG_DB="$ROOT/pipeline/preparation/layout_rewriter/runs/test.db"

RAW="$HERE/raw"; mkdir -p "$RAW"
LOAD_LOG="$RAW/${NAME}_load.log"; RUN_LOG="$RAW/${NAME}_run.log"
JSONL="$HERE/${NAME}.jsonl"
OUT="$ROOT/workloads/workload_${KEY}_1.txt"

common=(-db site.ycsb.BasicDB -threads 1 -p fieldcount=1 -p fieldlength=1
        -p basicdb.verbose=true -p basicdb.simulatedelay=0
        -p insertorder="$IO" -p zeropadding="$ZP")

echo "[1/5] YCSB load (rc=$RC, insertorder=$IO) -> $LOAD_LOG"
"$JAVA" -cp "$CP" site.ycsb.Client -load -P "$HERE/ycsb_workloads/$WL" \
        -p recordcount="$RC" "${common[@]}" "${EXTRA[@]}" > "$LOAD_LOG" 2> "$RAW/${NAME}_load.err"

echo "[2/5] YCSB run  (ops=$OPS, dist=$DIST) -> $RUN_LOG"
"$JAVA" -cp "$CP" site.ycsb.Client -t -P "$HERE/ycsb_workloads/$WL" \
        -p recordcount="$RC" -p operationcount="$OPS" -p requestdistribution="$DIST" \
        "${common[@]}" "${EXTRA[@]}" > "$RUN_LOG" 2> "$RAW/${NAME}_run.err"

echo "[3/5] parse -> $JSONL"
python3 "$HERE/tools/ycsb2trace.py" "$RUN_LOG" "$OPS" --out "$JSONL"

echo "[4/5] keymap (dense rowid from load dump) -> $OUT"
python3 "$HERE/tools/keymap.py" --load "$LOAD_LOG" --trace "$JSONL" --out "$OUT"

echo "[5/5] validate -> ${OUT}.validation.json"
DBARG=(); [ -f "$ORIG_DB" ] && DBARG=(--db "$ORIG_DB" --table items)
PROPS="workload=$WL,requestdistribution=$DIST,insertorder=$IO,recordcount=$RC,operationcount=$OPS,zeropadding=$ZP,fieldcount=1,fieldlength=1${EXTRA:+,$(IFS=' '; echo "${EXTRA[*]}")}"
python3 "$HERE/tools/validate_trace.py" "$OUT" --out "${OUT}.validation.json" \
        --db-max-key "$RC" --parse-losses 0 --label "$NAME" --props "$PROPS" "${DBARG[@]}"

echo "     manifest -> ${OUT}.manifest.json"
YCSB_COMMIT="0.17.0 (Maven Central jars; sha256 in workload_fixed/env/ycsb_env.txt)"
python3 - "$OUT" "$KEY" "$NAME" "$LOAD_LOG" "$RUN_LOG" "$YCSB_COMMIT" "$PROPS" <<'PY'
import sys, json, hashlib, os
out, key, name, load_log, run_log, ycsb_commit, props = sys.argv[1:8]
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
val=json.load(open(out+".validation.json"))
man={
    "workload": name, "registry_key": key, "seed": "trace-is-the-seed (YCSB ThreadLocalRandom)",
    "source": "real YCSB 0.17.0 BasicDB verbose", "ycsb_commit": ycsb_commit,
    "props": props,
    "out": os.path.relpath(out), "n_ops": val["n_ops"], "op_mix": val["op_mix_actual"],
    "hit_only_declared": val["hit_only_declared"],
    "hit_count": val["target_ops"]-val["notfound_count"], "miss_count": val["notfound_count"],
    "notfound_rate": val["notfound_rate"], "unique_key_ratio": val["unique_key_ratio"],
    "measured_skew": val["measured_skew"],
    "generated_min_key": val["generated_min_key"], "generated_max_key": val["generated_max_key"],
    "db_max_key": val["db_max_key"], "first_op": val["first_op"], "first_op_is_read": val["first_op_is_read"],
    "raw_load_sha256": sha(load_log), "raw_run_sha256": sha(run_log),
    "trace_sha256": sha(out), "validation_verdict": val["verdict"],
}
json.dump(man, open(out+".manifest.json","w"), indent=2)
print("   n_ops=%d op_mix=%s notfound=%s top1=%.3f%% verdict=%s" % (
    man["n_ops"], man["op_mix"], man["notfound_rate"],
    (val["measured_skew"]["top1_key_share"] or 0)*100, man["validation_verdict"]))
PY
echo "DONE: $NAME -> $OUT"
