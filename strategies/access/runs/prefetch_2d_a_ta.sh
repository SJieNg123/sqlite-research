#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/classify_after.csv \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hotpages_a_ta.csv \
  0 0 4096 >&2
