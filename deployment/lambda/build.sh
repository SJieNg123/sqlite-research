#!/usr/bin/env bash
# Build the AWS Lambda package for the warm-container/cold-data probe.
# Does NOT deploy or invoke anything: it writes build/ and prints what to upload.
#
# The package carries the reference database (test.db, orig layout, the same file
# the local batches and the OpenWhisk campaign use) inside /var/task, which is
# what "a function that carries its reference database" means in the experiment.
# residency.py is copied from the OpenWhisk action rather than duplicated, so the
# mincore primitive has one source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DB="$ROOT/pipeline/preparation/layout_rewriter/runs/test.db"
RES="$ROOT/deployment/openwhisk/action/residency.py"
STAGE="$HERE/build/stage"
OUT="$HERE/build/residency_probe.zip"

rm -rf "$HERE/build"
mkdir -p "$STAGE"
cp "$HERE/lambda_function.py" "$STAGE/"
cp "$RES" "$STAGE/residency.py"
cp "$DB" "$STAGE/test.db"

# Provenance travels inside the package, so code downloaded back from AWS still
# says which commit and which database produced a result.
dirty=$(git -C "$ROOT" status --porcelain -- deployment/lambda "$RES" | head -1)
{
  echo "built_utc   $(date -u +%FT%TZ)"
  echo "git_head    $(git -C "$ROOT" rev-parse --short HEAD)${dirty:+ (uncommitted changes in deployment/lambda or residency.py)}"
  ( cd "$STAGE" && sha256sum lambda_function.py residency.py test.db )
} > "$STAGE/MANIFEST.txt"

chmod 644 "$STAGE"/*
( cd "$STAGE" && zip -q -X "$OUT" lambda_function.py residency.py test.db MANIFEST.txt )
cp "$HERE/deploy.sh" "$HERE/build/"

unz=$(du -cb "$STAGE"/* | tail -1 | cut -f1)
zsz=$(stat -c %s "$OUT")
[ "$unz" -lt $((250 * 1048576)) ] || { echo "!!! unzipped $((unz / 1048576)) MB exceeds Lambda's 250 MB limit"; exit 1; }

echo "wrote $OUT"
echo "  zip       $((zsz / 1048576)) MB  (above the 50 MB console upload limit, so it goes via CloudShell/S3)"
echo "  unzipped  $((unz / 1048576)) MB  (Lambda limit 250 MB)"
sed 's/^/  /' "$STAGE/MANIFEST.txt"
[ -z "$dirty" ] || echo "  NOTE: built from uncommitted files. Commit first if these results will be cited."
echo
echo "Upload build/residency_probe.zip and build/deploy.sh to AWS CloudShell, then see README.md."
