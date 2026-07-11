#!/bin/bash
# Regenerate all A/B/C/C_hit hot2e hotsets with the fixed (-count,pageno) tie-break.
# Deterministic (Step B / gen_hotleaves only — no cold-clear). Archives the old
# first-seen-tie-break files to legacy_same_trace_first_seen_tiebreak/ for provenance.
set -uo pipefail
cd /home/u03/sqlite-research-project-sharing || exit 1
AR=strategies/access/runs
SR=strategies/slru/runs
GEN=$AR/gen_hotleaves.py
LEG=$AR/legacy_same_trace_first_seen_tiebreak
mkdir -p "$LEG"
declare -A DB=( [orig]=pipeline/preparation/layout_rewriter/runs/test.db
                [vacuum]=pipeline/preparation/layout_rewriter/runs/test_vacuum.db
                [ta]=pipeline/preparation/layout_rewriter/runs/test_typeaware.db )
declare -A CL=( [orig]=$AR/classify_before.csv [vacuum]=$AR/classify_vacuum.csv [ta]=$AR/classify_after.csv )
declare -A SUF=( [orig]="" [vacuum]="_vacuum" [ta]="_ta" )

regen() {  # $1=W $2=layout $3=K $4=seedspec("" or seed number)
  local W=$1 ly=$2 k=$3 seed=$4
  local ss=""; [ -n "$seed" ] && ss="_seed${seed}"
  local base="$SR/hotpages_$(echo $W|tr A-Z a-z)${SUF[$ly]}${ss}.csv"
  local wl="workloads/workload_$(echo $W|tr A-Z a-z)${seed:+_$seed}.txt"
  [ -n "$seed" ] || wl="workloads/workload_$(echo $W|tr A-Z a-z).txt"
  [ -f "$wl" ] || wl="workloads/workload_$(echo $W|tr A-Z a-z)_1.txt"
  local out="$AR/hot2e_${W}_${ly}_K${k}${ss}.csv"
  [ -f "$base" ] || { echo "  skip (no base): $out"; return; }
  [ -f "$out" ] && cp -n "$out" "$LEG/$(basename $out)"   # archive old once
  python3 "$GEN" "${DB[$ly]}" "${CL[$ly]}" "$base" "$wl" "$k" "$out" >/dev/null 2>&1 \
    && echo "  ok $out" || echo "  FAIL $out"
}

echo "=== regen A/B/C master (all K) + seeds (K10,K500) $(date -u +%FT%TZ) ==="
for W in A B C; do
  for ly in orig vacuum ta; do
    for k in 10 40 50 92 100 500; do regen $W $ly $k ""; done          # master
    for s in 1 2 3 4 5 6 7 8 9 10; do regen $W $ly 10 $s; regen $W $ly 500 $s; done  # seeds
  done
done
echo "=== regen C_hit orig K10/K40/K92/K500 seeds 1..10 (K40/K92 are new) ==="
for k in 10 40 92 500; do for s in 1 2 3 4 5 6 7 8 9 10; do regen C_hit orig $k $s; done; done
echo "=== done $(date -u +%FT%TZ) ==="
