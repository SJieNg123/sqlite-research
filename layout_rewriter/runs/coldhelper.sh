#!/bin/sh
# coldhelper.sh <db>... — evict each DB from page cache via posix_fadvise.
/home/u03/sqlite-research-project-sharing/layout_rewriter/runs/evict "$@" >&2
