#!/usr/bin/env bash
# gen_de.sh — generate real YCSB workload D (read-latest) & E (scan) traces.
# Mirrors gen_ycsb_trace.sh but passes --insert-base (D/E have 5% insert).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAVA="$HOME/ycsb-tools/jre/bin/java"; CP="$HOME/ycsb-tools/jars/*"
RC=600000; OPS=80000; ZP=19; IB=$((RC+1))   # insert-base = 600001 (reserved rank space, spec §2.5b)
mkdir -p "$HERE/raw" "$HERE/traces"
gen() {
  local NAME=$1 KEY=$2 WL=$3 DIST=$4 IO=$5
  local LOAD="$HERE/raw/${NAME}_load.log" RUN="$HERE/raw/${NAME}_run.log" JSONL="$HERE/${NAME}.jsonl" OUT="$HERE/traces/workload_${NAME}.txt"
  local common=(-db site.ycsb.BasicDB -threads 1 -p fieldcount=1 -p fieldlength=1 -p basicdb.verbose=true
                -p basicdb.simulatedelay=0 -p insertorder="$IO" -p zeropadding=$ZP)
  echo "[$NAME 1/4] load"; "$JAVA" -cp "$CP" site.ycsb.Client -load -P "$HERE/ycsb_workloads/$WL" -p recordcount=$RC "${common[@]}" > "$LOAD" 2> "$HERE/raw/${NAME}_load.err"
  echo "[$NAME 2/4] run ($DIST)"; "$JAVA" -cp "$CP" site.ycsb.Client -t -P "$HERE/ycsb_workloads/$WL" -p recordcount=$RC -p operationcount=$OPS -p requestdistribution=$DIST "${common[@]}" > "$RUN" 2> "$HERE/raw/${NAME}_run.err"
  echo "[$NAME 3/4] parse"; python3 "$HERE/tools/ycsb2trace.py" "$RUN" "$OPS" --workload "$WL" --out "$JSONL"
  echo "[$NAME 4/4] keymap (--insert-base $IB)"; python3 "$HERE/tools/keymap.py" --load "$LOAD" --trace "$JSONL" --out "$OUT" --insert-base $IB
  echo "  -> $OUT  ($(wc -l < "$OUT") ops)  op-mix: $(awk '{print $1}' "$OUT" | sort | uniq -c | tr '\n' ' ')"
}
gen YD yd workloadd latest  ordered
gen YE ye workloade zipfian hashed
echo "DONE"
