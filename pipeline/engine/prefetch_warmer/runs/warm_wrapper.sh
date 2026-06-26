#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/pipeline/engine/prefetch_warmer/src/warmer /home/u03/sqlite-research-project-sharing/strategies/access/runs/test.db "${WARM_HOTSET:-/home/u03/sqlite-research-project-sharing/pipeline/engine/prefetch_warmer/runs/hotset_internal.csv}" 4096
