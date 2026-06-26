#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/classify_before.csv \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hot2e_C_orig_K500.csv \
  0 500 4096 >&2
