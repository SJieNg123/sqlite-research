"""Warm-process session state, fail-closed artifact validation, and the canonical
warm SQLite handle.

Identity is process-local (uuid + pid + monotonic init + counter), never the
OpenWhisk activation id. Before any measured query the frozen artifacts (DB,
classifier, interior plan, per-request trace) must validate byte-for-byte against
the manifest AND the structural invariants must hold; otherwise ``validated`` is
False and the handler refuses measured mode.

The warm handle mirrors ``benchmark_harness.c``: one long-lived connection opened
at process init with ``PRAGMA cache_size=0`` (the OS page cache is the only
cache) and ``PRAGMA mmap_size=<file size>``, with statement reuse via sqlite3's
statement cache. This is the *primary* (warm-process / integrated) mode; a fresh
per-invocation connection is a separate *standalone* mode that additionally pays
open cost.
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid

try:
    from . import oracle
except ImportError:  # pragma: no cover - OpenWhisk flat layout
    import oracle

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PAGE = 4096


def sha256_file(path, _b=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_b), b""):
            h.update(chunk)
    return h.hexdigest()


class Session:
    def __init__(self, manifest_path, resolve_root=None):
        # identity, captured exactly once per process
        self.process_uuid = str(uuid.uuid4())
        self.pid = os.getpid()
        self.process_init_monotonic_ns = time.monotonic_ns()
        self._counter = 0
        self._counter_lock = threading.Lock()
        # process-wide lock serializing the measured critical section
        self.critical_lock = threading.Lock()

        self.manifest_path = manifest_path
        with open(manifest_path, "rb") as f:
            raw = f.read()
        self.artifact_manifest_sha256 = hashlib.sha256(raw).hexdigest()
        self.manifest = json.loads(raw)
        self.root = resolve_root or os.environ.get("OW_ARTIFACT_ROOT") or os.getcwd()

        self.db_path = self._abspath(self.manifest["database"]["path"])
        st = os.stat(self.db_path)
        self.db_device = st.st_dev
        self.db_inode = st.st_ino
        self.db_sha256 = None
        self.validated = False
        self.validation_reasons = ("not_validated",)
        # canonical warm handle (opened by open_warm_handle after validation)
        self.conn = None
        self.os_page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else _PAGE
        # plan offsets cached at process init (off the invocation critical path)
        self.interior_offsets = list(self.manifest["interior_page_list"]["offsets"])
        self.interior_offset_set = set(self.interior_offsets)

    def _abspath(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.root, rel)

    # ------------------------------------------------------------------ validate
    def validate_artifacts(self, expected_manifest_hash=None):
        """Full fail-closed validation. Returns () on success, else a tuple of
        reasons. Sets self.validated accordingly; never raises for a data
        mismatch."""
        r = []
        m = self.manifest

        if expected_manifest_hash is not None:
            if not expected_manifest_hash:
                r.append("empty expected_artifact_manifest_hash")
            elif expected_manifest_hash != self.artifact_manifest_sha256:
                r.append("artifact_manifest_hash mismatch")

        # page-size invariants (OS + SQLite must be 4096)
        if self.os_page_size != _PAGE:
            r.append("os page size %d != 4096" % self.os_page_size)
        if m.get("os_page_size_expected") != _PAGE:
            r.append("manifest os_page_size_expected != 4096")
        if m["database"]["page_size"] != _PAGE:
            r.append("db page_size != 4096")

        db = m["database"]
        try:
            self.db_sha256 = sha256_file(self.db_path)
        except OSError as e:
            r.append("db unreadable: %s" % e)
            self.validated = False
            self.validation_reasons = tuple(r)
            return self.validation_reasons
        if self.db_sha256 != db["sha256"]:
            r.append("db sha256 mismatch")
        if os.path.getsize(self.db_path) != db["byte_size"]:
            r.append("db byte_size mismatch")
        with open(self.db_path, "rb") as f:
            head = f.read(32)
        ps = int.from_bytes(head[16:18], "big")
        page_size = 65536 if ps == 1 else ps
        page_count = int.from_bytes(head[28:32], "big")
        if page_size != db["page_size"]:
            r.append("db header page_size mismatch")
        if page_count != db["page_count"]:
            r.append("db header page_count mismatch")

        # device/inode: current DB must match what init captured; and, when the
        # (real) manifest pins device/inode, it must match those too.
        st = os.stat(self.db_path)
        if (st.st_dev, st.st_ino) != (self.db_device, self.db_inode):
            r.append("db device/inode changed during init")
        if db.get("device") is not None and st.st_dev != db["device"]:
            r.append("db device != manifest")
        if db.get("inode") is not None and st.st_ino != db["inode"]:
            r.append("db inode != manifest")

        # classifier + interior plan hashes
        cl = m.get("classifier")
        if cl and sha256_file(self._abspath(cl["path"])) != cl["sha256"]:
            r.append("classifier sha256 mismatch")
        ipl = m["interior_page_list"]
        if sha256_file(self._abspath(ipl["path"])) != ipl["sha256"]:
            r.append("interior_page_list sha256 mismatch")

        # plan structural invariants (aligned / unique / within DB / count / ==offsets)
        r += self._validate_plan_invariants(page_size, page_count)

        self.validated = not r
        self.validation_reasons = tuple(r) if r else ()
        return self.validation_reasons

    def _validate_plan_invariants(self, page_size, page_count):
        r = []
        m = self.manifest
        offs = self.interior_offsets
        if m.get("interior_page_count") != 92 or m["interior_page_list"]["count"] != 92:
            r.append("interior_page_count != 92")
        if len(offs) != 92:
            r.append("plan does not have 92 offsets")
        if len(set(offs)) != len(offs):
            r.append("duplicate plan offsets")
        for off in offs:
            if off % page_size != 0:
                r.append("plan offset %d not aligned" % off); break
            if not (0 <= off < page_count * page_size):
                r.append("plan offset %d outside DB" % off); break
        # plan file offsets must equal manifest offsets exactly
        try:
            import csv
            file_offs = []
            with open(self._abspath(m["interior_page_list"]["path"]), newline="") as f:
                for row in csv.DictReader(f):
                    pn = int(row["page_number"])
                    fo = int(row["file_offset"])
                    if fo != (pn - 1) * page_size:
                        r.append("plan offset != (page-1)*page_size"); break
                    file_offs.append(fo)
            if sorted(file_offs) != sorted(offs):
                r.append("plan offsets != manifest offsets")
        except (OSError, ValueError, KeyError) as e:
            r.append("plan unreadable: %s" % e)
        return r

    # ------------------------------------------------------------- warm handle
    def open_warm_handle(self):
        """Open the canonical warm SQLite handle once. Requires prior successful
        validation. Applies cache_size=0 + mmap_size (canonical pragmas) and warms
        the read statement (compile only, no data). Safe to call repeatedly."""
        if not self.validated:
            raise RuntimeError("refusing warm handle before successful validation")
        if self.conn is not None:
            return self.conn
        pragmas = self.manifest.get("sqlite_pragmas", {"cache_size": 0,
                                                       "mmap_size": self.manifest["database"]["byte_size"]})
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA cache_size = %d" % int(pragmas.get("cache_size", 0)))
        conn.execute("PRAGMA mmap_size = %d" % int(pragmas.get("mmap_size",
                                                               self.manifest["database"]["byte_size"])))
        # Warm the *statement compilation* only (parse + plan), without stepping
        # the read against real data -- mirroring benchmark_harness.c, which
        # prepares once but first steps at the measured op. EXPLAIN QUERY PLAN
        # compiles the read without a B-tree data descent, so no interior/leaf
        # page is faulted at init and the cold gate can still reach zero.
        conn.execute("EXPLAIN QUERY PLAN " + oracle.READ_SQL, (0,)).fetchall()
        self.conn = conn
        return conn

    def close_warm_handle(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # ----------------------------------------------------------------- helpers
    def next_invocation(self):
        with self._counter_lock:
            self._counter += 1
            return self._counter

    def db_identity_changed(self):
        st = os.stat(self.db_path)
        return (st.st_dev, st.st_ino) != (self.db_device, self.db_inode)

    def oracle_for(self, workload, seed, first_op):
        try:
            return self.manifest["first_query_oracle"][workload][str(seed)][str(first_op)]
        except KeyError:
            return None

    def trace_meta(self, workload, seed):
        try:
            e = self.manifest["workload_traces"][workload]["seeds"][str(seed)]
            return e["path"], e["sha256"]
        except KeyError:
            return None, None

    def identity_fields(self):
        img = self.manifest.get("action_image_digest") or os.environ.get("OW_ACTION_IMAGE_DIGEST")
        return {
            "process_uuid": self.process_uuid,
            "pid": self.pid,
            "process_init_monotonic_ns": self.process_init_monotonic_ns,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "db_sha256": self.db_sha256,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "action_image_digest": img,
        }


# --------------------------------------------------------------- request checks
def valid_hash_format(h):
    return bool(h) and bool(_HEX64.match(h))


def validate_request_semantics(request, session):
    """Semantic validation against the manifest (workload/seed/first_op known,
    booleans well-typed, hash format). Returns () or a tuple of reasons."""
    r = []
    wl = request.get("workload")
    seed = request.get("seed")
    fop = request.get("first_operation_id")
    if wl not in session.manifest["workload_traces"]:
        r.append("unknown workload: %r" % wl)
    else:
        if str(seed) not in session.manifest["workload_traces"][wl]["seeds"]:
            r.append("unknown seed for workload: %r" % seed)
    if fop not in session.manifest.get("supported_first_operation_ids", [0]):
        r.append("unsupported first_operation_id: %r" % fop)
    for b in ("diagnostic_mode", "cold_reset"):
        if not isinstance(request.get(b), bool):
            r.append("%s must be a bool" % b)
    if not request.get("request_id"):
        r.append("empty request_id")
    if not valid_hash_format(request.get("expected_artifact_manifest_hash", "")):
        r.append("expected_artifact_manifest_hash must be 64-hex")
    return tuple(r)
