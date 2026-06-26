#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/slru/runs/prefetch_slru \
  /home/u03/sqlite-research-project-sharing/strategies/slru/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/strategies/slru/runs/hotpages_b_ta.csv \
  4096 >&2
