#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/strategies/slru/runs/prefetch_layers \
  /home/u03/sqlite-research-project-sharing/strategies/slru/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/strategies/slru/runs/classify_ta.csv \
  5 4096 >&2
