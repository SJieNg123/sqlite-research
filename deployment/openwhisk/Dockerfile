# Custom OpenWhisk Python action image for the SQLite cold-start measurement.
#
# Strategy: extend a PINNED official OpenWhisk Python runtime BY DIGEST (never a
# mutable tag) and inject the action package + frozen measurement artifacts. The
# runtime already implements the /init and /run HTTP interface; we only add our
# action module + artifacts, and bake the reference DB / classifier / traces so
# the image is self-contained (the action fails closed on anything but the exact
# frozen bytes).
#
# IMPORTANT (fill before building; do NOT use a mutable tag):
#   openwhisk/action-python-v3.11@sha256:<PIN_THE_RUNTIME_DIGEST_HERE>
# Resolve a concrete digest with:  docker buildx imagetools inspect <image:tag>
# ws2/01_build_image.sh passes the pinned digest via --build-arg BASE_RUNTIME and
# refuses to build an unpinned base.
#
# The final action image itself must then be referenced by IMMUTABLE DIGEST in
# the run config (action.image), not by tag.

ARG BASE_RUNTIME="openwhisk/action-python-v3.11@sha256:REPLACE_WITH_PINNED_DIGEST"
FROM ${BASE_RUNTIME}

# Re-declare after FROM so the value is visible to RUN/LABEL below, and fail the
# build closed unless the base is pinned by @sha256 digest (defense in depth;
# 01_build_image.sh enforces the same on the host side).
ARG BASE_RUNTIME
ARG ARTIFACTS_SHA256="unknown"
RUN case "$BASE_RUNTIME" in \
      *@sha256:*) : ;; \
      *) echo "BASE_RUNTIME must be pinned by @sha256 digest, got: $BASE_RUNTIME" >&2; exit 1 ;; \
    esac

LABEL org.sqlite-coldstart.base_runtime="${BASE_RUNTIME}" \
      org.sqlite-coldstart.artifacts_sha256="${ARTIFACTS_SHA256}"

# Immutable artifact root. The manifest stores repository-relative paths; the
# action resolves them against OW_ARTIFACT_ROOT, so files staged here under their
# repo-relative subpaths resolve to their manifest paths with no path rewriting.
ENV OW_ARTIFACT_ROOT=/action/artifacts \
    OW_ARTIFACT_MANIFEST=/action/artifacts/deployment/openwhisk/config/artifacts.json

# action code (the OpenWhisk python runtime imports /action/__main__.py's main)
COPY action/ /action/action/
COPY __main__.py /action/__main__.py

# manifest + interior (2d) plan CSV live under config/.
COPY config/ /action/artifacts/deployment/openwhisk/config/

# reference DB + classifier + YC seed traces, staged by 01_build_image.sh into
# _image_stage/ preserving their repo-relative subpaths (sha-verified vs the pin).
# Copied at the artifact root so each lands at its manifest path.
COPY _image_stage/ /action/artifacts/

# Build-time fail-closed self-check: every artifact the manifest references must
# exist in the image, or the build fails now rather than at first invocation.
RUN python3 -c "import json,os,sys; root=os.environ['OW_ARTIFACT_ROOT']; m=json.load(open(os.environ['OW_ARTIFACT_MANIFEST'])); ps=[m['database']['path'],m['classifier']['path'],m['interior_page_list']['path']]+([m['strategy_plans']['2d']['path']] if m['strategy_plans']['2d']['path'] else [])+[s['path'] for wl in m['workload_traces'].values() for s in wl['seeds'].values()]; miss=[p for p in ps if not os.path.exists(os.path.join(root,p))]; sys.exit('MISSING in image: %s' % miss) if miss else print('image self-check OK: %d artifact paths present' % len(ps))"

# The image digest is recorded and injected as OW_ACTION_IMAGE_DIGEST at
# deploy time (wsk action create --docker <image@sha256:...>), so the running
# process reports the immutable digest that the request must match.
