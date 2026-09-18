/*
 * warmer — stateless cold-start prefetch warmer (Level 1).
 *
 * Reads a hotset CSV (page_number,file_offset) and pulls those pages into the
 * OS page cache BEFORE SQLite opens the DB. Run as the harness post-cold-script
 * (separate process, its own fd) so there is no lock conflict (F1) and no second
 * data copy (F4): the scratch buffer is read-and-discard, only the OS page cache
 * is warmed; SQLite's later reads hit it naturally.
 *
 *   warmer <db> <hotset.csv> <page_size>
 *
 * env:
 *   WARM_MODE     = warm (default) | off        (off = baseline; same binary)
 *   WARM_METHOD   = pread (default) | fadvise    (pread guarantees residency;
 *                                                 fadvise is best-effort hint)
 *   WARM_DELIVERY = perpage (default) | split | coalesce
 *   WARM_CHUNK_PAGES = 0 (default, uncapped) | N   (coalesce only: split a merged
 *                     range into hints of at most N pages)
 *   WARM_FADV_SEQ    = 0 (default) | 1             (issue POSIX_FADV_SEQUENTIAL on
 *                     the fd first; the non-root way to ask for a wider window)
 *
 * WARM_DELIVERY decomposes what deliver_us actually pays for. The three modes
 * request the SAME pages and differ only in how the request is issued:
 *
 *   perpage   the original single pass: parse a CSV line, immediately issue one
 *             4096-byte hint/read for it. Parsing and syscalls are interleaved and
 *             therefore inseparable, so parse_us is not reported. This path is kept
 *             byte-for-byte as it was, because every published batch used it.
 *   split     two phases: parse the whole CSV into an offset array, then issue the
 *             same one-hint-per-page loop. Same syscall count as perpage; the only
 *             difference is that parse_us is now separated out of deliver_us.
 *   coalesce  two phases, but offset-adjacent pages are merged into ranges and each
 *             range costs ONE syscall over its whole length. Same bytes, far fewer
 *             calls. Merge logic follows legacy/prefetch_vacuum/src/prefetch.c.
 *
 * Caveat for coalesce: a range hint is not a promise. Measured on this host, one
 * POSIX_FADV_WILLNEED over a range delivers exactly one readahead window from the
 * START of that range (read_ahead_kb=128 -> 32 pages) and silently ignores the rest,
 * however long the range is, while still returning 0. warmed_pages therefore counts
 * what was ASKED for, not what arrived; under fadvise those differ by two orders of
 * magnitude. Always pair it with an independent mincore check.
 *
 * WARM_CHUNK_PAGES exists because of that: capping a range at the window size turns
 * one ignored hint into ceil(len/N) honoured ones, which is the middle ground between
 * 4416 per-page calls and 1 useless call.
 *
 * Prints to stderr:  warmer_us=<f> open_us=<f> deliver_us=<f> [parse_us=<f>]
 *                    warmed_pages=<n> [ranges=<n>] method=<m> mode=<m> delivery=<d>
 * parse_us and ranges are omitted where they are not meaningful, rather than being
 * reported as zero.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>

/* Upper bound on one pread in coalesce mode; a merged range can be many MB. */
#define PREAD_CHUNK_BYTES (1u << 20)

static long long now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

static int cmp_ll(const void *a, const void *b) {
    long long x = *(const long long *)a, y = *(const long long *)b;
    return (x > y) - (x < y);
}

int main(int argc, char *argv[]) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s <db> <hotset.csv> <page_size>\n", argv[0]);
        return 2;
    }
    const char *db = argv[1];
    const char *hotset = argv[2];
    int page_size = atoi(argv[3]);
    if (page_size <= 0) page_size = 4096;

    const char *mode = getenv("WARM_MODE");
    const char *method = getenv("WARM_METHOD");
    const char *delivery = getenv("WARM_DELIVERY");
    int do_warm = !(mode && strcmp(mode, "off") == 0);
    int use_pread = !(method && strcmp(method, "fadvise") == 0);

    const char *chunk_env = getenv("WARM_CHUNK_PAGES");
    const char *seq_env = getenv("WARM_FADV_SEQ");
    long long chunk_pages = chunk_env ? atoll(chunk_env) : 0;   /* 0 = uncapped */
    if (chunk_pages < 0) chunk_pages = 0;
    int fadv_seq = (seq_env && strcmp(seq_env, "1") == 0);

    /* 0 = perpage (default, unchanged), 1 = split, 2 = coalesce */
    int deliv = 0;
    if (delivery && *delivery) {
        if (strcmp(delivery, "split") == 0)         deliv = 1;
        else if (strcmp(delivery, "coalesce") == 0) deliv = 2;
        else if (strcmp(delivery, "perpage") != 0) {
            fprintf(stderr, "warmer: unknown WARM_DELIVERY=%s (perpage|split|coalesce)\n", delivery);
            return 2;
        }
    }

    long long t0 = now_ns();
    int warmed = 0;
    long long ranges = 0;
    long long t_parse_done = -1;
    /* Split the preprocessing wall-clock into two terms so e2e can be reported under
     * both deployment models:
     *   open_us    = cold open(db)+fopen(hotset)+malloc setup. A warm / in-app process
     *                does NOT re-pay this (its DB handle is already open) -> exclude it
     *                for the "warm process, cold data" model.
     *   deliver_us = page-list iterate + per-page pread/fadvise loop = what an integrated
     *                prefetch actually costs (~ static prefetch_elapsed).
     *   warmer_us  = open_us + deliver_us = the standalone-warmer total (unchanged).
     * Measurement semantics are unchanged; we only add two timestamps + two stderr fields. */
    long long t_open_done = t0;

    if (do_warm) {
        int fd = open(db, O_RDONLY);
        if (fd < 0) { perror("open db"); return 1; }
        FILE *f = fopen(hotset, "r");
        if (!f) { perror("fopen hotset"); close(fd); return 1; }

        /* Optional: ask for a wider per-hint readahead window. This is the only
         * non-root lever on read_ahead_kb, so it is what makes a negative bulk
         * result airtight rather than an artifact of the host's 128 KB cap. */
        if (fadv_seq && posix_fadvise(fd, 0, 0, POSIX_FADV_SEQUENTIAL) != 0) {
            fprintf(stderr, "warmer: POSIX_FADV_SEQUENTIAL failed\n");
            fclose(f); close(fd); return 1;
        }

        /* read-and-discard scratch (F4: not a data cache). Only a coalesced pread
         * needs more than one page; every other path keeps the original size. */
        size_t scratch_sz = (deliv == 2 && use_pread) ? PREAD_CHUNK_BYTES : (size_t)page_size;
        unsigned char *scratch = malloc(scratch_sz);
        if (!scratch) { fclose(f); close(fd); return 1; }

        t_open_done = now_ns();                            /* end of open/setup term */

        if (deliv == 0) {
            /* Original single pass -- unchanged. Do not "tidy" this: every batch in
             * results/ was measured by exactly this loop. */
            char line[256];
            int header = 1;
            while (fgets(line, sizeof line, f)) {
                if (header) { header = 0; continue; }      /* skip CSV header */
                long long pn; long long off;
                if (sscanf(line, "%lld,%lld", &pn, &off) != 2) continue;
                if (use_pread) {
                    if (pread(fd, scratch, page_size, off) >= 0) warmed++;
                } else {
                    if (posix_fadvise(fd, off, page_size, POSIX_FADV_WILLNEED) == 0) warmed++;
                }
            }
        } else {
            /* Phase 1: parse the whole hotset before issuing anything, so the CSV
             * cost lands in parse_us instead of hiding inside deliver_us. */
            long long *offs = NULL;
            size_t n = 0, cap = 0;
            char line[256];
            int header = 1;
            while (fgets(line, sizeof line, f)) {
                if (header) { header = 0; continue; }
                long long pn; long long off;
                if (sscanf(line, "%lld,%lld", &pn, &off) != 2) continue;
                if (n == cap) {
                    size_t ncap = cap ? cap * 2 : 1024;
                    long long *tmp = realloc(offs, ncap * sizeof *offs);
                    if (!tmp) { free(offs); free(scratch); fclose(f); close(fd); return 1; }
                    offs = tmp; cap = ncap;
                }
                offs[n++] = off;
            }
            t_parse_done = now_ns();

            /* Phase 2: issue. */
            if (deliv == 1) {
                for (size_t i = 0; i < n; i++) {
                    if (use_pread) {
                        if (pread(fd, scratch, page_size, offs[i]) >= 0) warmed++;
                    } else {
                        if (posix_fadvise(fd, offs[i], page_size, POSIX_FADV_WILLNEED) == 0) warmed++;
                    }
                }
            } else if (n > 0) {
                /* Merge offset-adjacent pages into ranges, one syscall per range.
                 * build_hotset() already emits ascending offsets; the sort is a guard. */
                qsort(offs, n, sizeof *offs, cmp_ll);
                long long rstart = offs[0];
                long long rend   = offs[0] + page_size;
                for (size_t i = 1; i <= n; i++) {
                    if (i < n && offs[i] == rend) { rend += page_size; continue; }
                    if (i < n && offs[i] < rend) continue;   /* duplicate offset */
                    long long len = rend - rstart;
                    /* One issued call covers at most step_max bytes. pread is bounded by
                     * the scratch buffer; fadvise is unbounded unless WARM_CHUNK_PAGES
                     * asks otherwise. ranges counts calls actually issued. */
                    long long cap = chunk_pages * (long long)page_size;
                    long long step_max = use_pread ? (long long)PREAD_CHUNK_BYTES : len;
                    if (cap > 0 && step_max > cap) step_max = cap;
                    if (step_max <= 0) step_max = len;
                    long long done = 0;
                    while (done < len) {
                        long long want = len - done;
                        if (want > step_max) want = step_max;
                        if (use_pread) {
                            if (pread(fd, scratch, (size_t)want, rstart + done) < 0) break;
                        } else {
                            if (posix_fadvise(fd, rstart + done, want, POSIX_FADV_WILLNEED) != 0) break;
                        }
                        warmed += (int)(want / page_size);
                        ranges++;
                        done += want;
                    }
                    if (i < n) { rstart = offs[i]; rend = offs[i] + page_size; }
                }
            }
            free(offs);
        }
        free(scratch);
        fclose(f);
        close(fd);
    }

    long long t1 = now_ns();

    /* Two-phase modes bill parsing separately, so deliver_us there is issue-only.
     * perpage cannot separate them, so its deliver_us keeps the original meaning
     * (parse + issue) and no parse_us is printed. */
    int split_timing = (t_parse_done >= 0);
    double parse_us   = split_timing ? (t_parse_done - t_open_done) / 1000.0 : 0.0;
    double deliver_us = split_timing ? (t1 - t_parse_done) / 1000.0
                                     : (t1 - t_open_done) / 1000.0;

    char parse_field[64] = "";
    char range_field[64] = "";
    char knob_field[64]  = "";
    if (split_timing) snprintf(parse_field, sizeof parse_field, " parse_us=%.2f", parse_us);
    if (deliv == 2)   snprintf(range_field, sizeof range_field, " ranges=%lld", ranges);
    /* Appended last, and only when non-default, so every existing parser keeps matching. */
    if (chunk_pages > 0 || fadv_seq)
        snprintf(knob_field, sizeof knob_field, " chunk_pages=%lld fadv_seq=%d",
                 chunk_pages, fadv_seq);

    fprintf(stderr, "warmer_us=%.2f open_us=%.2f deliver_us=%.2f%s warmed_pages=%d%s "
                    "method=%s mode=%s delivery=%s%s\n",
            (t1 - t0) / 1000.0, (t_open_done - t0) / 1000.0, deliver_us, parse_field,
            warmed, range_field,
            use_pread ? "pread" : "fadvise",
            do_warm ? "warm" : "off",
            deliv == 0 ? "perpage" : (deliv == 1 ? "split" : "coalesce"),
            knob_field);
    return 0;
}
