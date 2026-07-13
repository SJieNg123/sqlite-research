"""Warm-process session state and frozen-artifact validation.

An OpenWhisk container is reused across invocations ("warm container, cold
data"). This module holds the per-PROCESS identity that distinguishes one warm
session from another, and validates that the frozen artifacts (DB, interior-page
plan, workload trace) are byte-identical to the manifest before any measured
query runs. The OpenWhisk activation id is deliberately NOT used as process
identity (STEP 6): only a process-local UUID + PID + monotonic init timestamp +
invocation counter identify a warm session.
"""
import hashlib
import json
import os
import threading
import time
import uuid


def sha256_file(path, _bufsize=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class ArtifactMismatch(Exception):
    """Raised when a frozen artifact's hash/identity does not match the manifest;
    the action must refuse to run a measured query."""


class Session:
    """Process-singleton. Construct once at module import; reused every
    invocation within the same warm container."""

    def __init__(self, manifest_path, resolve_root=None):
        # --- identity, captured exactly once per process ---
        self.process_uuid = str(uuid.uuid4())
        self.pid = os.getpid()
        self.process_init_monotonic_ns = time.monotonic_ns()
        self._counter = 0
        self._lock = threading.Lock()

        # --- load + validate the frozen artifact manifest once ---
        self.manifest_path = manifest_path
        with open(manifest_path, "rb") as f:
            raw = f.read()
        self.artifact_manifest_sha256 = sha256_bytes(raw)
        self.manifest = json.loads(raw)
        # Paths in the manifest are repo-relative; resolve against a root the
        # deployment provides (mounted volume or image path), never machine paths
        # baked into the committed example.
        self.root = resolve_root or os.environ.get("OW_ARTIFACT_ROOT") or os.getcwd()

        self.db_path = self._abspath(self.manifest["database"]["path"])
        st = os.stat(self.db_path)
        self.db_device = st.st_dev
        self.db_inode = st.st_ino
        self.db_sha256 = None  # filled lazily by validate_artifacts()
        self._validated = False

    def _abspath(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.root, rel)

    def validate_artifacts(self, expected_manifest_hash=None):
        """Full identity check. Returns () on success or a tuple of human-readable
        mismatch reasons. Never raises for a data mismatch (the caller records it
        and refuses measured mode)."""
        reasons = []
        m = self.manifest
        if expected_manifest_hash and expected_manifest_hash != self.artifact_manifest_sha256:
            reasons.append("artifact_manifest_hash mismatch")

        db = m["database"]
        self.db_sha256 = sha256_file(self.db_path)
        if self.db_sha256 != db["sha256"]:
            reasons.append("db sha256 mismatch")
        if os.path.getsize(self.db_path) != db["byte_size"]:
            reasons.append("db byte_size mismatch")
        # cheap header checks (page size @ off 16 BE u16, page count @ off 28 BE u32)
        with open(self.db_path, "rb") as f:
            head = f.read(32)
        page_size = int.from_bytes(head[16:18], "big")
        if page_size == 1:
            page_size = 65536
        page_count = int.from_bytes(head[28:32], "big")
        if page_size != db["page_size"]:
            reasons.append("db page_size mismatch")
        if page_count != db["page_count"]:
            reasons.append("db page_count mismatch")

        ipl = m["interior_page_list"]
        if sha256_file(self._abspath(ipl["path"])) != ipl["sha256"]:
            reasons.append("interior_page_list sha256 mismatch")

        self._validated = not reasons
        return tuple(reasons)

    def validate_trace_plan(self, trace_rel, trace_sha, plan_rel, plan_sha):
        """Per-request check that the requested trace/plan match the manifest's
        frozen hashes."""
        reasons = []
        if trace_rel is not None:
            if sha256_file(self._abspath(trace_rel)) != trace_sha:
                reasons.append("trace sha256 mismatch")
        if plan_rel is not None:
            if sha256_file(self._abspath(plan_rel)) != plan_sha:
                reasons.append("plan sha256 mismatch")
        return tuple(reasons)

    def next_invocation(self):
        with self._lock:
            self._counter += 1
            return self._counter

    def db_identity_changed(self):
        """True if the DB device/inode changed under us (image swap / remount);
        measured mode must fail in that case."""
        st = os.stat(self.db_path)
        return (st.st_dev, st.st_ino) != (self.db_device, self.db_inode)

    def identity_fields(self):
        return {
            "process_uuid": self.process_uuid,
            "pid": self.pid,
            "process_init_monotonic_ns": self.process_init_monotonic_ns,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "db_sha256": self.db_sha256,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
        }
