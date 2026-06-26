#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/classify_before.csv \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hotpages_b.csv \
  0 0 4096 >&2
