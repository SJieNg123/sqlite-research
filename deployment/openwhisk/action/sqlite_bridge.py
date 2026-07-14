"""Canonical SQLite execution bridge (ctypes -> libsqlite3).

Mirrors ``pipeline/engine/benchmark_harness/benchmark_harness.c`` exactly for the
measured path: a single read-only ``sqlite3*`` and a single ``sqlite3_stmt*`` per
warm process, prepared once with ``sqlite3_prepare_v2`` (compile only -- no data
page is faulted at prepare time, unlike executing a warm-up SELECT), then per
query ``sqlite3_reset`` / ``sqlite3_clear_bindings`` / ``sqlite3_bind_int64`` /
``sqlite3_step``. The measured boundary wraps ``sqlite3_step`` alone, the same as
the C harness.

The canonical query is ``SELECT payload FROM items WHERE id=?1`` and the returned
value is the payload blob; the oracle digests that blob.

Uses the system ``libsqlite3`` via ctypes, so no build step is required and the
prepared-statement semantics are the real SQLite ones (not Python's sqlite3
statement cache).
"""
import ctypes
import ctypes.util
import time

SELECT_SQL = b"SELECT payload FROM items WHERE id=?1"

SQLITE_OK = 0
SQLITE_ROW = 100
SQLITE_DONE = 101
SQLITE_OPEN_READONLY = 0x00000001
SQLITE_OPEN_NOMUTEX = 0x00008000
# db_status verbs (sqlite3.h)
SQLITE_DBSTATUS_CACHE_USED = 1
SQLITE_DBSTATUS_CACHE_HIT = 7
SQLITE_DBSTATUS_CACHE_MISS = 8
SQLITE_DBSTATUS_CACHE_SPILL = 12


def _load():
    name = ctypes.util.find_library("sqlite3")
    for cand in ([name] if name else []) + ["libsqlite3.so.0", "libsqlite3.so"]:
        try:
            return ctypes.CDLL(cand)
        except OSError:
            continue
    raise OSError("libsqlite3 not found for ctypes bridge")


_lib = _load()
_lib.sqlite3_libversion.restype = ctypes.c_char_p
_lib.sqlite3_open_v2.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p),
                                 ctypes.c_int, ctypes.c_char_p]
_lib.sqlite3_close_v2.argtypes = [ctypes.c_void_p]
_lib.sqlite3_exec.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
_lib.sqlite3_prepare_v2.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                    ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.POINTER(ctypes.c_char_p)]
_lib.sqlite3_finalize.argtypes = [ctypes.c_void_p]
_lib.sqlite3_reset.argtypes = [ctypes.c_void_p]
_lib.sqlite3_clear_bindings.argtypes = [ctypes.c_void_p]
_lib.sqlite3_bind_int64.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int64]
_lib.sqlite3_step.argtypes = [ctypes.c_void_p]
_lib.sqlite3_column_bytes.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.sqlite3_column_bytes.restype = ctypes.c_int
_lib.sqlite3_column_blob.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.sqlite3_column_blob.restype = ctypes.c_void_p
_lib.sqlite3_db_release_memory.argtypes = [ctypes.c_void_p]
_lib.sqlite3_db_status.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                   ctypes.POINTER(ctypes.c_int),
                                   ctypes.POINTER(ctypes.c_int), ctypes.c_int]
_lib.sqlite3_errmsg.argtypes = [ctypes.c_void_p]
_lib.sqlite3_errmsg.restype = ctypes.c_char_p


def libversion():
    return _lib.sqlite3_libversion().decode()


class SqliteError(Exception):
    pass


class WarmDb:
    """One warm read-only connection + one prepared statement, reused across
    invocations. cache_size/mmap_size mirror the manifest pragmas."""

    def __init__(self, db_path, cache_size=0, mmap_size=0):
        self.db_path = db_path
        self._db = ctypes.c_void_p()
        flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX
        rc = _lib.sqlite3_open_v2(db_path.encode(), ctypes.byref(self._db), flags, None)
        if rc != SQLITE_OK:
            raise SqliteError("sqlite3_open_v2 rc=%d" % rc)
        self._exec("PRAGMA cache_size=%d;" % int(cache_size))
        self._exec("PRAGMA mmap_size=%d;" % int(mmap_size))
        # prepare_v2 compiles the SELECT (parse + codegen); it does NOT step, so
        # no B-tree data page is faulted here -- the first fault is the measured
        # step of the first query.
        self._stmt = ctypes.c_void_p()
        rc = _lib.sqlite3_prepare_v2(self._db, SELECT_SQL, len(SELECT_SQL),
                                     ctypes.byref(self._stmt), None)
        if rc != SQLITE_OK:
            msg = _lib.sqlite3_errmsg(self._db).decode()
            raise SqliteError("sqlite3_prepare_v2 rc=%d: %s" % (rc, msg))

    def _exec(self, sql):
        err = ctypes.c_char_p()
        rc = _lib.sqlite3_exec(self._db, sql.encode(), None, None, ctypes.byref(err))
        if rc != SQLITE_OK:
            raise SqliteError("exec %r rc=%d" % (sql, rc))

    def query(self, key):
        """reset -> clear_bindings -> bind -> (timed) step -> read payload.
        Returns (hit, payload_bytes_or_None, step_us). Matches the C harness's
        measured boundary (step only)."""
        _lib.sqlite3_reset(self._stmt)
        _lib.sqlite3_clear_bindings(self._stmt)
        _lib.sqlite3_bind_int64(self._stmt, 1, key)
        t0 = time.monotonic_ns()
        rc = _lib.sqlite3_step(self._stmt)
        step_us = (time.monotonic_ns() - t0) / 1000.0
        if rc == SQLITE_ROW:
            n = _lib.sqlite3_column_bytes(self._stmt, 0)
            ptr = _lib.sqlite3_column_blob(self._stmt, 0)
            payload = ctypes.string_at(ptr, n) if (ptr and n) else b""
            _lib.sqlite3_reset(self._stmt)
            return 1, payload, step_us
        if rc == SQLITE_DONE:
            _lib.sqlite3_reset(self._stmt)
            return 0, None, step_us
        msg = _lib.sqlite3_errmsg(self._db).decode()
        _lib.sqlite3_reset(self._stmt)
        raise SqliteError("sqlite3_step rc=%d: %s" % (rc, msg))

    def cache_hit_miss(self, reset=True):
        """Return (cache_hit, cache_miss) counters (optionally reset). With
        cache_size=0 the pager retains nothing, so repeated cold queries show
        misses -- proof the SQLite pager cache is not serving the query."""
        def _stat(verb):
            cur = ctypes.c_int(0)
            hi = ctypes.c_int(0)
            _lib.sqlite3_db_status(self._db, verb, ctypes.byref(cur),
                                   ctypes.byref(hi), 1 if reset else 0)
            return cur.value
        return _stat(SQLITE_DBSTATUS_CACHE_HIT), _stat(SQLITE_DBSTATUS_CACHE_MISS)

    def release_memory(self):
        """Release reclaimable heap the pager holds (documented mechanism), so a
        subsequent OS cold reset is not defeated by SQLite-held page copies."""
        return _lib.sqlite3_db_release_memory(self._db)

    def close(self):
        if getattr(self, "_stmt", None):
            _lib.sqlite3_finalize(self._stmt)
            self._stmt = None
        if getattr(self, "_db", None):
            _lib.sqlite3_close_v2(self._db)
            self._db = None
