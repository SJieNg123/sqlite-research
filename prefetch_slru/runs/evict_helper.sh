#!/bin/sh
# Drop OS page cache for test.db via posix_fadvise(POSIX_FADV_DONTNEED).
# Used as --drop-caches-script for benchmark_harness (no sudo needed).
exec /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/evict \
  /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/test.db
