#!/usr/bin/env bash
# Regenerate every batch-derived file of the paper from the raw measurements of one unified
# batch, then check every number in paper/main.tex against the result.
#
#   tools/regenerate_paper.sh [batch]          # default unified_v7
#
# What it rebuilds, in order, with the batch's own code:
#   1. results/<batch>/seedNN/<family>/summary.csv   from raw.csv   (run_experiment.aggregate)
#   2. results/<batch>/seedNN/{raw,summary}.csv      family merge   (as tools/run_unified_v7.sh)
#      results/<batch>/summary.csv                   seed merge
#   3. results/<batch>/uncertainty.{csv,md}          tools/stats_uncertainty.py
#   4. results/matched_budget/<batch>.{csv,md}       tools/matched_budget.py; its page-count
#      check reads the matched hotsets, the only work/ files committed (git add -f)
#   5. the data figures in paper/figures/            each figure's script
#   6. every number in the text and tables           tools/paper_refresh.py check + inventory
#
# Every output is a committed file, so after a run `git status` lists exactly what did not
# reproduce. Figure 1 is a conceptual drawing with no data (paper/figures/gen_problem.py
# writes its SVG). Figures 16 and 20 come from their own batches (results/ram_pressure,
# results/lambda/b2), read from their committed tables.
# Needs Python 3 with matplotlib and the Linux Libertine O fonts. Standard library otherwise.
set -euo pipefail
cd "$(dirname "$0")/.."
B=${1:-unified_v7}
D=results/$B
TAG=${B#unified_}
FAMILIES="main lp layout top15 whole"
export SOURCE_DATE_EPOCH=0          # PDF figures carry no build time, so reruns are byte-stable

echo "== 1. per-family summaries from raw.csv ($D)"
python3 - "$D" <<'PY'
import csv, importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("run_experiment", "run_experiment.py")
rx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rx)
n = 0
for raw in sorted(Path(sys.argv[1]).glob("seed[0-9][0-9]/*/raw.csv")):
    with open(raw) as f:
        rx.aggregate(list(csv.DictReader(f)), raw.with_name("summary.csv"))
    n += 1
print(f"   {n} family summaries")
PY

echo "== 2. family and seed merges"
first=1
: > "$D/summary.csv"
for sd in "$D"/seed[0-9][0-9]; do
  for kind in raw summary; do
    { head -1 "$sd/main/$kind.csv"
      for fam in $FAMILIES; do
        [ -f "$sd/$fam/$kind.csv" ] && tail -n +2 "$sd/$fam/$kind.csv"
      done
    } > "$sd/$kind.csv"
  done
  s=$((10#${sd##*seed}))
  if [ $first -eq 1 ]; then { printf 'seed,'; head -1 "$sd/summary.csv"; } >> "$D/summary.csv"; first=0; fi
  tail -n +2 "$sd/summary.csv" | sed "s/^/${s},/" >> "$D/summary.csv"
done

echo "== 3. cross-instance statistics"
python3 tools/stats_uncertainty.py --seeds "$D"/seed[0-9][0-9] \
  --out "$D/uncertainty.csv" --md "$D/uncertainty.md" > /dev/null

echo "== 4. matched-budget comparison"
python3 tools/matched_budget.py "$D" > /dev/null

echo "== 5. figures"
python3 paper/figures/gen_headline.py "$B"
python3 paper/figures/gen_reversal.py "$B"
python3 figures/16_ram_pressure_sweep.py && cp figures/out/16_ram_pressure_sweep.png paper/figures/
python3 figures/20_lambda_residency.py && cp figures/out/20_lambda_residency.png paper/figures/

echo "== 6. every number in paper/main.tex against $B"
python3 tools/paper_refresh.py check "$TAG"
python3 tools/paper_refresh.py inventory "$TAG" | tail -1

echo "== files that did not reproduce (empty = all reproduced)"
git status --short -- results figures
git -C paper status --short -- figures
