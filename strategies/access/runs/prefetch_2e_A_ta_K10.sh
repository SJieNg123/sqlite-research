#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/classify_after.csv \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hot2e_A_ta_K10.csv \
  0 10 4096 >&2
