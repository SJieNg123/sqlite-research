#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/prefetch_vacuum/src/prefetch \
  /home/u03/sqlite-research-project-sharing/pipeline/preparation/layout_rewriter/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/pipeline/preparation/layout_rewriter/runs/classify_after.csv \
  perpage >&2
