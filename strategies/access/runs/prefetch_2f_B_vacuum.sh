#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/slru/runs/prefetch_slru \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test_vacuum.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hotpages_b_vacuum.csv \
  4096 >&2
