# Custom OpenWhisk Python action image for the SQLite cold-start measurement.
#
# Strategy: extend a PINNED official OpenWhisk Python runtime BY DIGEST (never a
# mutable tag) and inject the action package. The runtime already implements the
# /init and /run HTTP interface; we only add our action module + artifacts.
#
# IMPORTANT (fill before building; do NOT use a mutable tag):
#   openwhisk/action-python-v3.11@sha256:<PIN_THE_RUNTIME_DIGEST_HERE>
# Resolve a concrete digest with:  docker buildx imagetools inspect <image:tag>
#
# The final action image itself must then be referenced by IMMUTABLE DIGEST in
# the run config (action.image), not by tag.

ARG BASE_RUNTIME="openwhisk/action-python-v3.11@sha256:REPLACE_WITH_PINNED_DIGEST"
FROM ${BASE_RUNTIME}

# 102 MB reference DB: bake it in (image-baked mode) OR mount a volume at this
# path (mounted-volume mode) and skip the COPY. Keep the path immutable either
# way; the action pins (device, inode, sha256).
ENV OW_ARTIFACT_ROOT=/action/artifacts \
    OW_ARTIFACT_MANIFEST=/action/artifacts/deployment/openwhisk/config/artifacts.json

# action code (the OpenWhisk python runtime imports /action/__main__.py's main)
COPY action/ /action/action/
COPY __main__.py /action/__main__.py

# artifacts: manifest + interior plan + traces + DB (image-baked mode).
# For mounted-volume mode, comment the DB copy and mount it at the same path.
COPY config/ /action/artifacts/deployment/openwhisk/config/
# COPY --chown=... reference DB + workloads here, or mount them; regenerate the
# real manifest AFTER placing the DB in this namespace (see README / build script).

# The image digest is recorded and injected as OW_ACTION_IMAGE_DIGEST at
# deploy time (wsk action create --docker <image@sha256:...>), so the running
# process reports the immutable digest that the request must match.
