#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test_vacuum.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/classify_vacuum.csv \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hot2e_C_vacuum_K10.csv \
  0 10 4096 >&2
