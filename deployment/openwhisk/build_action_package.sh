#!/usr/bin/env bash
# Package the OpenWhisk action (documented path; does NOT deploy or invoke).
#
# Two supported packaging modes:
#   1. custom image  -- build the Dockerfile (extends a pinned runtime by digest)
#   2. injected source -- a plain action archive (only viable if the 102 MB DB is
#                         mounted, since the action-archive size limit is ~48 MB)
#
# This script builds artifacts and (optionally) the image, then PRINTS the
# immutable image digest to pin. It never runs `wsk` and never invokes the action.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MODE="${1:-package}"     # package | image
IMAGE_TAG="${IMAGE_TAG:-sqlite-coldstart:local}"

echo "== regenerating frozen manifest (after DB is in its final namespace) =="
echo "   run this on the workstation AFTER checkout of the final commit and"
echo "   after the DB is placed at its immutable action path:"
echo "   python3 $HERE/build_artifact_manifest.py --out $HERE/config/artifacts.json"

# flat __main__.py shim so the OpenWhisk python runtime can import main()
cat > "$HERE/__main__.py" <<'PY'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "action"))
from action.main import main  # noqa: E402,F401
PY
echo "wrote $HERE/__main__.py"

case "$MODE" in
  package)
    OUT="${OUT:-$HERE/action_package.zip}"
    ( cd "$HERE" && zip -q -r "$OUT" action config __main__.py \
        -x '*/__pycache__/*' 'config/artifacts.json' )
    echo "wrote $OUT (excludes __pycache__ and the machine-specific artifacts.json)"
    echo "NOTE: DB must be mounted; the archive intentionally omits the 102 MB DB."
    ;;
  image)
    if ! command -v docker >/dev/null; then echo "docker not found"; exit 2; fi
    echo "== building $IMAGE_TAG (pin BASE_RUNTIME digest in the Dockerfile first) =="
    docker build -t "$IMAGE_TAG" "$HERE"
    echo "== resolve the IMMUTABLE digest to pin in run_config.action.image =="
    docker image inspect "$IMAGE_TAG" --format '{{index .RepoDigests 0}}' || \
      echo "(push the image to a registry to obtain an @sha256 digest)"
    ;;
  *)
    echo "usage: $0 [package|image]"; exit 2;;
esac

echo "== NOT deploying or invoking (out of scope for this phase) =="
