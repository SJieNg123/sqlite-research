"""One-shot capability probe: which page-cache residency methods work on Lambda.

mincore returns EPERM inside Lambda, so the residency method has to be chosen
from what the sandbox actually allows. One invocation in a fresh execution
environment answers every question the choice depends on:

  kernel / seccomp   is a syscall filter active, and how new is the kernel
  mincore            on an anonymous page, on /var/task, and on a /tmp copy the
                     function owns (Linux >= 5.2 fakes "all resident" for files
                     the caller neither owns nor may write)
  cachestat          Linux >= 6.5 syscall that counts cached pages of a file
                     without touching them, the ideal method if present
  RWF_NOWAIT         does a cache-only read fail on a miss, and does the failed
                     probe itself start I/O (a second probe that then succeeds
                     means it does, which would make it perturb what it measures)
  timing             pread latency on first and second touch, to see whether a
                     latency threshold separates a cache miss from a hit
"""
import ctypes
import os
import statistics
import time

import residency

PAGE = residency.PAGE
_libc = residency._libc


def _err(e):
    return f"{type(e).__name__}: {e}"


def _mincore_anon():
    _libc.mmap.restype = ctypes.c_void_p
    addr = _libc.mmap(None, PAGE, 0x1 | 0x2, 0x02 | 0x20, -1, 0)  # RW, PRIVATE|ANON
    vec = ctypes.create_string_buffer(1)
    rc = _libc.mincore(ctypes.c_void_p(addr), PAGE, vec)
    err = ctypes.get_errno() if rc else 0
    _libc.munmap(ctypes.c_void_p(addr), PAGE)
    return "ok" if rc == 0 else os.strerror(err)


def _mincore_file(path):
    try:
        with residency.PageMap(path) as pm:
            vec = pm.residency_vector()
            return f"ok {sum(b & 1 for b in vec)}/{pm.npages} resident"
    except OSError as e:
        return _err(e)


def _cachestat(path):
    class Range(ctypes.Structure):
        _fields_ = [("off", ctypes.c_uint64), ("len", ctypes.c_uint64)]

    class Stat(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in
                    ("cache", "dirty", "writeback", "evicted", "recently_evicted")]

    fd = os.open(path, os.O_RDONLY)
    try:
        rng, st = Range(0, 0), Stat()  # len 0 = to end of file
        rc = _libc.syscall(ctypes.c_long(451), fd, ctypes.byref(rng), ctypes.byref(st), 0)
        if rc != 0:
            return os.strerror(ctypes.get_errno())
        return f"ok cache={st.cache} evicted={st.evicted} recently_evicted={st.recently_evicted}"
    finally:
        os.close(fd)


def run(db):
    out = {"kernel": os.uname().release, "uid": os.getuid()}
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(("Seccomp:", "NoNewPrivs:")):
                k, v = line.split(":", 1)
                out[k] = v.strip()
    st = os.stat(db)
    out["db_owner_uid"], out["db_mode"] = st.st_uid, oct(st.st_mode & 0o777)
    best = ""
    with open("/proc/mounts") as f:
        for line in f:
            dev, mnt, fs = line.split()[:3]
            if db.startswith(mnt.rstrip("/") + "/") and len(mnt) > len(best):
                best, out["db_fs"] = mnt, f"{fs} on {mnt}"

    out["mincore_anon"] = _mincore_anon()
    out["mincore_var_task"] = _mincore_file(db)
    tmp = "/tmp/diag_copy.db"
    with open(db, "rb") as s, open(tmp, "wb") as d:
        d.write(s.read(8 << 20))
    out["mincore_tmp_copy_owned"] = _mincore_file(tmp)
    os.remove(tmp)
    out["cachestat_var_task"] = _cachestat(db)

    npages = st.st_size // PAGE
    fd = os.open(db, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)  # no readahead on this fd
        # 32 pages spread over the file, far enough apart that one miss cannot
        # pull a neighbouring sample in. Even indices test RWF_NOWAIT, odd ones timing.
        stride = npages // 32
        pages = [i * stride + stride // 2 for i in range(32)]
        nowait = []
        for p in pages[0::2]:
            first = second = None
            for attempt in (1, 2):
                try:
                    os.preadv(fd, [bytearray(PAGE)], p * PAGE, os.RWF_NOWAIT)
                    r = "hit"
                except BlockingIOError:
                    r = "miss"
                except OSError as e:
                    r = _err(e)
                if attempt == 1:
                    first = r
                    time.sleep(0.05)
                else:
                    second = r
            nowait.append(f"{first}->{second}")
        out["nowait_first_then_second_50ms_later"] = nowait

        t1, t2 = [], []
        for p in pages[1::2]:
            for bucket in (t1, t2):
                t = time.perf_counter_ns()
                os.pread(fd, PAGE, p * PAGE)
                bucket.append(round((time.perf_counter_ns() - t) / 1000, 1))
        out["pread_us_first_touch"] = t1
        out["pread_us_second_touch"] = t2
        out["pread_us_median_first_second"] = [statistics.median(t1), statistics.median(t2)]
    finally:
        os.close(fd)
    print("DIAG " + str(out))
    return out
