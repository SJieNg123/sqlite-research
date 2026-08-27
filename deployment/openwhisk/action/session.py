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
import platform
import re
import subprocess
import threading
import time
import uuid

try:
    from . import oracle, sqlite_bridge
except ImportError:  # pragma: no cover - OpenWhisk flat layout
    import oracle
    import sqlite_bridge

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
        self.os_page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else _PAGE
        # plan offsets cached at process init (off the invocation critical path)
        self.interior_offsets = list(self.manifest["interior_page_list"]["offsets"])
        self.interior_offset_set = set(self.interior_offsets)
        # Generic static-plan cache: any strategy plan carrying an inline frozen
        # offset list (e.g. layers_5) is cached here at init, off the measured
        # critical path. 2d (interior_page_list) and baseline (no prefetch) are
        # handled separately and carry no inline "offsets", so they are excluded.
        self.static_plan_offsets = {
            name: list(plan["offsets"])
            for name, plan in self.manifest.get("strategy_plans", {}).items()
            if isinstance(plan.get("offsets"), list)
        }
        # Generic keyed-plan cache: strategies whose frozen delivery plan varies by
        # (workload, seed) -- e.g. 2e_K10 (resident interiors UNION top-K hot
        # leaves). Parsed offsets are cached here at process init so the measured
        # critical path never parses CSV/JSON. Keyed by (strategy, workload, seed).
        self.keyed_plans = {}
        for wl, seeds in self.manifest.get("keyed_strategy_plans", {}).items():
            for seed_str, strats in seeds.items():
                for strat, plan in strats.items():
                    self.keyed_plans[(strat, wl, str(seed_str))] = {
                        "offsets": list(plan["offsets"]),
                        "interior_offsets": list(plan.get("interior_offsets", [])),
                        "leaf_offsets": list(plan.get("leaf_offsets", [])),
                        "plan_sha256": plan.get("sha256"),
                        "path": plan.get("path"),
                        "expected_pages": plan.get("expected_pages"),
                        "expected_interior_pages": plan.get("expected_interior_pages"),
                        "expected_leaf_pages": plan.get("expected_leaf_pages"),
                    }
        # Authoritative set of workload IDs any keyed plan / trace may address.
        # When the manifest declares "workload_set", it is the closed universe of
        # addressable workloads (the YC campaigns' canonical id plus the
        # portability matrix ids). An empty/absent set means "legacy single
        # workload" -- no gate. Captured at init; enforced fail-closed in
        # validate_artifacts (a keyed plan or trace for an out-of-set workload is
        # a hard validation failure -- no implicit fallback).
        self.workload_set = set(self.manifest.get("workload_set", []))
        # runtime + image identity, captured once
        try:
            self.sqlite_library_version = sqlite_bridge.libversion()
        except Exception:  # pragma: no cover
            self.sqlite_library_version = None
        self.python_version = platform.python_version()
        # Deployment-bound immutable image identity. This is NOT self-observed by
        # the container: OpenWhisk delivers it as an action input parameter
        # (`-p OW_ACTION_IMAGE_DIGEST <digest>` at deploy), which main() binds via
        # bind_deployment_image_digest() before measured validation. The env read
        # is only a convenience default for local runs; in-cluster it is unset.
        self.deployment_image_digest = os.environ.get("OW_ACTION_IMAGE_DIGEST")
        self.warmdb = None

    def _abspath(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.root, rel)

    def bind_deployment_image_digest(self, digest):
        """Bind the deployment-bound immutable image identity. Called by main()
        with the OW_ACTION_IMAGE_DIGEST input parameter OpenWhisk injects at
        invoke time (it is delivered as a param, not an env var). Idempotent: a
        deployment binds one digest for the life of the warm process."""
        self.deployment_image_digest = digest

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

        # inline-offset static strategy plans (e.g. layers_5) validate fail-closed
        r += self._validate_static_plans(page_size, page_count)

        # keyed per-(workload,seed) strategy plans (e.g. 2e_K10) validate fail-closed
        r += self._validate_keyed_plans(page_size, page_count)

        # authoritative workload_set gate + cross-map coverage preflight. When the
        # manifest declares a closed workload universe, EVERY keyed plan and EVERY
        # workload trace must name a workload inside it -- no implicit fallback to
        # the canonical YC id. Fail closed on any out-of-set reference.
        if self.workload_set:
            for (_strat, wl, _seed) in self.keyed_plans:
                if wl not in self.workload_set:
                    r.append("keyed plan workload %s not in workload_set" % wl)
            for wl in m.get("workload_traces", {}):
                if wl not in self.workload_set:
                    r.append("trace workload %s not in workload_set" % wl)
            for wl in m.get("first_query_oracle", {}):
                if wl not in self.workload_set:
                    r.append("oracle workload %s not in workload_set" % wl)

        # every supported workload trace must match its manifest hash
        for wl, wentry in m.get("workload_traces", {}).items():
            for seed, tentry in wentry.get("seeds", {}).items():
                tp = self._abspath(tentry["path"])
                if not os.path.exists(tp):
                    r.append("missing trace %s/%s" % (wl, seed))
                elif sha256_file(tp) != tentry["sha256"]:
                    r.append("trace sha256 mismatch %s/%s" % (wl, seed))

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

    def _validate_static_plans(self, page_size, page_count):
        """Fail-closed validation of every inline-offset static strategy plan
        (e.g. layers_5): the frozen CSV sha matches, the CSV round-trips to the
        manifest's inline offsets under the page formula, the count matches
        expected_pages, and every offset is one of the validated 92 interiors (so
        expected_interior_pages == count and expected_leaf_pages == 0 hold). 2d
        and baseline carry no inline offsets and are validated elsewhere."""
        import csv
        r = []
        for name, plan in self.manifest.get("strategy_plans", {}).items():
            offs = self.static_plan_offsets.get(name)
            if offs is None:
                continue
            path = plan.get("path")
            if not path:
                r.append("%s plan missing path" % name); continue
            ap = self._abspath(path)
            if not os.path.exists(ap):
                r.append("%s plan file missing" % name); continue
            if sha256_file(ap) != plan.get("sha256"):
                r.append("%s plan sha256 mismatch" % name)
            exp = plan.get("expected_pages")
            if exp is not None and len(offs) != exp:
                r.append("%s plan has %d offsets, expected %d" % (name, len(offs), exp))
            if len(set(offs)) != len(offs):
                r.append("%s plan has duplicate offsets" % name)
            # CSV round-trip against inline offsets + page formula
            try:
                file_offs = []
                with open(ap, newline="") as f:
                    for row in csv.DictReader(f):
                        pn = int(row["page_number"]); fo = int(row["file_offset"])
                        if fo != (pn - 1) * page_size:
                            r.append("%s plan offset != (page-1)*page_size" % name); break
                        file_offs.append(fo)
                if file_offs != list(offs):
                    r.append("%s plan offsets != manifest offsets" % name)
            except (OSError, ValueError, KeyError) as e:
                r.append("%s plan unreadable: %s" % (name, e)); continue
            # every offset aligned, within the DB, and an interior of the 92-skeleton
            for off in offs:
                if off % page_size != 0 or not (0 <= off < page_count * page_size):
                    r.append("%s plan offset %d misaligned/out-of-range" % (name, off)); break
                if off not in self.interior_offset_set:
                    r.append("%s plan offset %d is not an interior" % (name, off)); break
            # declared interior/leaf split must be self-consistent (interior_prefix)
            eip = plan.get("expected_interior_pages")
            if eip is not None and eip != len(offs):
                r.append("%s expected_interior_pages != plan length" % name)
            if plan.get("expected_leaf_pages") not in (None, 0):
                r.append("%s expected_leaf_pages must be 0 (interior prefix)" % name)
        return r

    def _validate_keyed_plans(self, page_size, page_count):
        """Fail-closed validation of every keyed per-(workload,seed) strategy plan
        (e.g. 2e_K10). For each: the frozen CSV sha matches the manifest, the CSV
        round-trips to the manifest's inline offsets under the page formula, the
        page/interior/leaf counts match the declared expectations, offsets are
        unique/aligned/within the DB, the interior half is EXACTLY the validated
        92-interior skeleton (set equality), the leaf half is disjoint from it, and
        interior_offsets + leaf_offsets partition offsets. Any disagreement --
        sha, count, duplicate, out-of-range, or type-split -- fails closed."""
        import csv
        r = []
        for wl, seeds in self.manifest.get("keyed_strategy_plans", {}).items():
            for seed_str, strats in seeds.items():
                for strat, plan in strats.items():
                    tag = "%s/%s/%s" % (strat, wl, seed_str)
                    cached = self.keyed_plans.get((strat, wl, str(seed_str)))
                    if cached is None:
                        r.append("%s not cached" % tag); continue
                    offs = cached["offsets"]
                    path = plan.get("path")
                    if not path:
                        r.append("%s plan missing path" % tag); continue
                    ap = self._abspath(path)
                    if not os.path.exists(ap):
                        r.append("%s plan file missing" % tag); continue
                    if sha256_file(ap) != plan.get("sha256"):
                        r.append("%s plan sha256 mismatch" % tag)
                    exp = plan.get("expected_pages")
                    if exp is not None and len(offs) != exp:
                        r.append("%s has %d offsets, expected %d" % (tag, len(offs), exp))
                    if len(set(offs)) != len(offs):
                        r.append("%s has duplicate offsets" % tag)
                    # CSV round-trip against inline offsets + page formula
                    try:
                        file_offs = []
                        with open(ap, newline="") as f:
                            for row in csv.DictReader(f):
                                pn = int(row["page_number"]); fo = int(row["file_offset"])
                                if fo != (pn - 1) * page_size:
                                    r.append("%s offset != (page-1)*page_size" % tag); break
                                file_offs.append(fo)
                        if file_offs != list(offs):
                            r.append("%s plan offsets != manifest offsets" % tag)
                    except (OSError, ValueError, KeyError) as e:
                        r.append("%s plan unreadable: %s" % (tag, e)); continue
                    # aligned + within DB
                    for off in offs:
                        if off % page_size != 0 or not (0 <= off < page_count * page_size):
                            r.append("%s offset %d misaligned/out-of-range" % (tag, off)); break
                    # interior/leaf split via the validated 92-interior skeleton
                    interior_hit = [o for o in offs if o in self.interior_offset_set]
                    leaf_hit = [o for o in offs if o not in self.interior_offset_set]
                    eip = plan.get("expected_interior_pages")
                    elp = plan.get("expected_leaf_pages")
                    if eip is not None and len(interior_hit) != eip:
                        r.append("%s interior count %d != expected %d"
                                 % (tag, len(interior_hit), eip))
                    if elp is not None and len(leaf_hit) != elp:
                        r.append("%s leaf count %d != expected %d"
                                 % (tag, len(leaf_hit), elp))
                    # the interior half must be the FULL 92-interior skeleton
                    if eip == len(self.interior_offset_set) and \
                            set(interior_hit) != self.interior_offset_set:
                        r.append("%s interior half != 92-interior skeleton" % tag)
                    # manifest-declared interior/leaf offset lists must agree
                    if set(plan.get("interior_offsets", interior_hit)) != set(interior_hit):
                        r.append("%s interior_offsets disagree with classification" % tag)
                    if set(plan.get("leaf_offsets", leaf_hit)) != set(leaf_hit):
                        r.append("%s leaf_offsets disagree with classification" % tag)
        return r

    def strategy_plan(self, strategy, workload, seed):
        """Generic keyed-plan lookup: return the cached frozen plan for an exact
        (strategy, workload, seed) request, or None if there is none. The returned
        dict exposes offsets / interior_offsets / leaf_offsets / plan_sha256 /
        expected_pages / expected_interior_pages / expected_leaf_pages. No parsing
        happens here -- offsets were cached at process init."""
        return self.keyed_plans.get((strategy, workload, str(seed)))

    # ------------------------------------------------------------- warm handle
    def pragmas(self):
        return self.manifest.get("sqlite_pragmas",
                                 {"cache_size": 0, "mmap_size": 0})

    def open_warm_handle(self):
        """Open the canonical warm SQLite handle once via the ctypes bridge
        (sqlite3_open_v2 read-only + sqlite3_prepare_v2). prepare_v2 compiles the
        SELECT without stepping, so no data page is faulted at init and the cold
        gate can still reach zero. Requires prior successful validation."""
        if not self.validated:
            raise RuntimeError("refusing warm handle before successful validation")
        if self.warmdb is not None:
            return self.warmdb
        p = self.pragmas()
        self.warmdb = sqlite_bridge.WarmDb(self.db_path,
                                           cache_size=int(p.get("cache_size", 0)),
                                           mmap_size=int(p.get("mmap_size", 0)))
        return self.warmdb

    def close_warm_handle(self):
        if self.warmdb is not None:
            self.warmdb.close()
            self.warmdb = None

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
        return {
            "process_uuid": self.process_uuid,
            "pid": self.pid,
            "process_init_monotonic_ns": self.process_init_monotonic_ns,
            "db_device": self.db_device,
            "db_inode": self.db_inode,
            "db_sha256": self.db_sha256,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "action_image_digest": self.deployment_image_digest,
            "repository_commit": self.manifest.get("repository_commit"),
            "sqlite_library_version": self.sqlite_library_version,
            "python_version": self.python_version,
            "canonical_query": self.manifest.get("canonical_query", oracle.SELECT_SQL),
        }


# --------------------------------------------------------------- request checks
def valid_hash_format(h):
    return bool(h) and bool(_HEX64.match(h))


def _is_pos_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def _is_nonneg_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def validate_request_semantics(request, session):
    """Semantic validation against the manifest and pair/identity contract.
    Format checks apply always; the stronger measured-mode identity requirements
    apply unless diagnostic_mode is True. Returns () or a tuple of reasons."""
    r = []
    wl = request.get("workload")
    seed = request.get("seed")
    fop = request.get("first_operation_id")
    if wl not in session.manifest["workload_traces"]:
        r.append("unknown workload: %r" % wl)
    elif str(seed) not in session.manifest["workload_traces"][wl]["seeds"]:
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

    # ---- pair / schedule / run-config / image identity (measured mode) ----
    if not request.get("diagnostic_mode"):
        if not request.get("pair_id"):
            r.append("empty pair_id")
        if not _is_nonneg_int(request.get("repetition_id")):
            r.append("repetition_id must be a non-negative int")
        if not _is_pos_int(request.get("schedule_position")):
            r.append("schedule_position must be a positive int")
        if not valid_hash_format(request.get("run_config_sha256", "")):
            r.append("run_config_sha256 must be 64-hex")
        exp_img = request.get("expected_action_image_digest")
        if not exp_img:
            r.append("empty expected_action_image_digest")
        elif not session.deployment_image_digest:
            r.append("deployment-bound image digest unset (OW_ACTION_IMAGE_DIGEST param not delivered)")
        elif exp_img != session.deployment_image_digest:
            r.append("action image digest mismatch")
    return tuple(r)
