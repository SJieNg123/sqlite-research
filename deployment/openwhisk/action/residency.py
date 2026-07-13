"""Non-root page-residency primitives for the OpenWhisk cold-start action.

This mirrors the canonical measurement primitives of
``pipeline/engine/benchmark_harness/benchmark_harness.c`` in Python via ctypes so
the same warm-process, no-root mechanism runs inside a long-lived OpenWhisk
runtime:

  * ``mmap(MAP_SHARED, PROT_READ)`` the database file  -> observe file page cache
  * ``mincore``                                        -> per-page residency vector
  * ``madvise(MADV_DONTNEED)`` (fallback COLD/PAGEOUT) -> non-root cold reset
  * ``madvise(MADV_WILLNEED)`` per page                -> async prefetch delivery

It is deliberately NOT a second benchmark: it exposes exactly the syscalls the C
harness uses, and the action layer (``main.py``) composes them. No sudo,
drop_caches, container restart, or reboot is used anywhere.

Pure-logic helpers (``cold_threshold_passed``, ``count_in``) are importable and
unit-testable without mapping a real database.
"""
import ctypes
import os

PAGE = 4096  # OS page size; equals the SQLite page size of the reference DB.

# mmap / madvise constants (Linux x86-64).
PROT_READ = 0x1
MAP_SHARED = 0x1
MADV_DONTNEED = 4
MADV_WILLNEED = 3
MADV_COLD = 20
MADV_PAGEOUT = 21

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.mmap.restype = ctypes.c_void_p
_libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                       ctypes.c_int, ctypes.c_int, ctypes.c_long]
_libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
_libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
_libc.madvise.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
MAP_FAILED = ctypes.c_void_p(-1).value


def cold_threshold_passed(resident_interiors_after_reset):
    """Strict cold condition: zero mandatory interior pages resident before any
    prefetch/query. A successful madvise return code alone is NOT accepted as
    eviction; residency is re-measured and must be zero."""
    return resident_interiors_after_reset == 0


def count_in(vec, offsets):
    """Count how many of the given file offsets map to a resident page in the
    mincore vector (bit 0 == resident). Pure function for unit tests."""
    n = 0
    for off in offsets:
        idx = off // PAGE
        if 0 <= idx < len(vec) and (vec[idx] & 1):
            n += 1
    return n


class PageMap:
    """A read-only MAP_SHARED mapping of the database file plus the mincore /
    madvise operations over it. One instance is created per invocation because a
    cold reset must drop and re-establish the mapping (STEP 7)."""

    def __init__(self, db_path):
        self.db_path = db_path
        self.fd = os.open(db_path, os.O_RDONLY)
        self.size = os.fstat(self.fd).st_size
        self.npages = (self.size + PAGE - 1) // PAGE
        addr = _libc.mmap(None, self.size, PROT_READ, MAP_SHARED, self.fd, 0)
        if addr == MAP_FAILED or addr is None:
            err = ctypes.get_errno()
            os.close(self.fd)
            raise OSError(err, "mmap failed: " + os.strerror(err))
        self.addr = addr

    def residency_vector(self):
        """Return a bytes-like vector, one byte per page; bit0 set == resident."""
        vec = ctypes.create_string_buffer(self.npages)
        if _libc.mincore(ctypes.c_void_p(self.addr), self.size, vec) != 0:
            err = ctypes.get_errno()
            raise OSError(err, "mincore failed: " + os.strerror(err))
        return vec.raw

    def madvise(self, advice, offset=0, length=None):
        if length is None:
            length = self.size
        rc = _libc.madvise(ctypes.c_void_p(self.addr + offset), length, advice)
        return rc == 0

    def cold_reset(self):
        """Non-root eviction hint chain over the whole mapping. Tries the same
        MADV_DONTNEED path the C harness uses, then weaker COLD/PAGEOUT hints.
        Returns the advice label actually issued. Efficacy is VERIFIED separately
        by re-reading residency; this return value is not proof of eviction."""
        if self.madvise(MADV_DONTNEED):
            method = "MADV_DONTNEED"
        elif self.madvise(MADV_PAGEOUT):
            method = "MADV_PAGEOUT"
        elif self.madvise(MADV_COLD):
            method = "MADV_COLD"
        else:
            err = ctypes.get_errno()
            raise OSError(err, "no non-root eviction hint accepted: "
                          + os.strerror(err))
        return method

    def deliver_willneed(self, offsets):
        """Async per-page prefetch delivery, mirroring the warmer's per-page
        MADV_WILLNEED hints. Returns the number of hints accepted."""
        delivered = 0
        for off in offsets:
            if self.madvise(MADV_WILLNEED, off, PAGE):
                delivered += 1
        return delivered

    def close(self):
        if getattr(self, "addr", None):
            _libc.munmap(ctypes.c_void_p(self.addr), self.size)
            self.addr = None
        if getattr(self, "fd", None) is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
