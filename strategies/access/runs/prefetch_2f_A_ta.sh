#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/slru/runs/prefetch_slru \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/strategies/access/runs/hotpages_a_ta.csv \
  4096 >&2
