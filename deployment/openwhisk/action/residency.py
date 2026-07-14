"""Non-root page-residency primitives for the OpenWhisk cold-start action.

Mirrors the canonical measurement primitives of
``pipeline/engine/benchmark_harness/benchmark_harness.c`` in Python via ctypes:
``mmap(MAP_SHARED, PROT_READ)`` + ``mincore`` (residency), ``madvise`` /
``posix_fadvise`` (non-root cold reset), ``madvise(MADV_WILLNEED)`` (delivery).

Cold reset is **efficacy-based, not rc-based**: after each candidate hint the
mapping is dropped and a *fresh* mapping is made to re-measure residency with
``mincore``; that residency is the truth. Candidates escalate until zero
mandatory interiors are resident or the list is exhausted. No sudo, drop_caches,
container restart, or reboot is ever used.
"""
import ctypes
import os

PAGE = 4096

PROT_READ = 0x1
MAP_SHARED = 0x1
MADV_DONTNEED = 4
MADV_WILLNEED = 3
MADV_COLD = 20
MADV_PAGEOUT = 21
POSIX_FADV_DONTNEED = 4

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.mmap.restype = ctypes.c_void_p
_libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                       ctypes.c_int, ctypes.c_int, ctypes.c_long]
_libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
_libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
_libc.madvise.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
_libc.posix_fadvise.argtypes = [ctypes.c_int, ctypes.c_long, ctypes.c_long, ctypes.c_int]
MAP_FAILED = ctypes.c_void_p(-1).value


def cold_threshold_passed(resident_interiors_after_reset):
    """Strict cold condition: zero mandatory interior pages resident before any
    prefetch/query. A madvise/fadvise success rc is NOT accepted as eviction;
    only a re-measured mincore residency of zero passes."""
    return resident_interiors_after_reset == 0


def count_in(vec, offsets):
    n = 0
    for off in offsets:
        idx = off // PAGE
        if 0 <= idx < len(vec) and (vec[idx] & 1):
            n += 1
    return n


class PageMap:
    """A fresh read-only MAP_SHARED mapping of the DB plus mincore/madvise over
    it. Constructed per operation because a cold reset must drop and re-establish
    the mapping."""

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
        vec = ctypes.create_string_buffer(self.npages)
        if _libc.mincore(ctypes.c_void_p(self.addr), self.size, vec) != 0:
            err = ctypes.get_errno()
            raise OSError(err, "mincore failed: " + os.strerror(err))
        return vec.raw

    def madvise(self, advice, offset=0, length=None):
        if length is None:
            length = self.size
        ctypes.set_errno(0)
        rc = _libc.madvise(ctypes.c_void_p(self.addr + offset), length, advice)
        return rc, (ctypes.get_errno() if rc != 0 else 0)

    def deliver_willneed(self, offsets):
        """Async per-page prefetch delivery (per-page MADV_WILLNEED). Returns the
        number of hints the kernel accepted (rc==0)."""
        delivered = 0
        for off in offsets:
            rc, _ = self.madvise(MADV_WILLNEED, off, PAGE)
            if rc == 0:
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


# ------------------------------------------------------------ reset orchestration
def _measure(db_path, interior_set):
    """Fresh mapping -> mincore -> (resident_total, resident_interiors); the
    mapping is dropped before returning (mapping lifecycle)."""
    pm = PageMap(db_path)
    try:
        vec = pm.residency_vector()
        return sum(b & 1 for b in vec), count_in(vec, interior_set)
    finally:
        pm.close()


def _apply_madvise(db_path, advice):
    """Apply an madvise hint over the whole file on a FRESH mapping, then drop
    it. Returns (rc, errno)."""
    pm = PageMap(db_path)
    try:
        return pm.madvise(advice)
    finally:
        pm.close()


def _apply_fadvise_dontneed(db_path):
    """Page-aligned POSIX_FADV_DONTNEED over the whole file via a fresh fd."""
    fd = os.open(db_path, os.O_RDONLY)
    try:
        ctypes.set_errno(0)
        rc = _libc.posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)  # 0 len == whole file
        # posix_fadvise returns the errno directly (0 on success)
        return (0, 0) if rc == 0 else (rc, rc)
    finally:
        os.close(fd)


# candidate order: canonical MADV_DONTNEED first, then fd-based fadvise, then the
# stronger reclaim hints. All non-root.
_CANDIDATES = [
    ("MADV_DONTNEED", lambda p: _apply_madvise(p, MADV_DONTNEED)),
    ("POSIX_FADV_DONTNEED", _apply_fadvise_dontneed),
    ("MADV_PAGEOUT", lambda p: _apply_madvise(p, MADV_PAGEOUT)),
    ("MADV_COLD", lambda p: _apply_madvise(p, MADV_COLD)),
]


def cold_reset_and_verify(db_path, interior_offsets):
    """Efficacy-based non-root cold reset. Snapshots residency, then escalates
    candidate hints, re-mapping/mincore-ing after each, until zero interiors are
    resident or candidates are exhausted. Returns a diagnostics dict; the caller
    treats ``cold_threshold_passed`` as the truth."""
    interior_set = set(interior_offsets)
    before_total, before_interiors = _measure(db_path, interior_set)

    attempts = []
    final_total, final_interiors = before_total, before_interiors
    chosen = "none"
    for name, fn in _CANDIDATES:
        rc, errno = fn(db_path)
        post_total, post_interiors = _measure(db_path, interior_set)
        attempts.append({"method": name, "rc": rc, "errno": errno,
                         "resident_interiors_after": post_interiors,
                         "resident_pages_after": post_total})
        final_total, final_interiors, chosen = post_total, post_interiors, name
        if cold_threshold_passed(post_interiors):
            break

    return {
        "resident_pages_before_reset": before_total,
        "resident_interiors_before_reset": before_interiors,
        "attempted_methods": attempts,
        "cold_reset_method": chosen,
        "resident_pages_after_reset": final_total,
        "resident_interiors_after_reset": final_interiors,
        "cold_reset_succeeded": cold_threshold_passed(final_interiors),
        "cold_threshold_passed": cold_threshold_passed(final_interiors),
    }
