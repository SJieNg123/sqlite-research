#!/bin/sh
# Drop OS page cache for test_typeaware.db via posix_fadvise(POSIX_FADV_DONTNEED).
exec /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/evict \
  /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/test_typeaware.db
