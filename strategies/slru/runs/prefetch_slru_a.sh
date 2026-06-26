#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/slru/runs/prefetch_slru \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hotpages_a.csv \
  4096 >&2
