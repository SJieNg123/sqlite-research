#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/classify_before.csv \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hot2e_B_orig_K100.csv \
  0 100 4096 >&2
