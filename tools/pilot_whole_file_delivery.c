/*
 * Pilot: what do the profile-free whole-file delivery calls actually deliver?
 *
 * For each method, from a cold page cache (POSIX_FADV_DONTNEED, verified empty with
 * mincore), issue the call over the whole database file, time the call itself, then
 * count resident pages with mincore immediately and after 10 ms, 100 ms and 1 s, so an
 * asynchronous call that keeps loading after it returns is not undercounted.
 *
 *   fadvise_whole    one posix_fadvise(WILLNEED) over the whole file
 *   readahead_whole  one readahead(2) over the whole file
 *   readahead_win    readahead(2) in window-sized (read_ahead_kb) chunks
 *   fadvise_win      posix_fadvise(WILLNEED) in window-sized chunks
 *   populate         mmap(MAP_SHARED | MAP_POPULATE) of the whole file
 *
 * Methods are interleaved trial by trial so drift spreads across them. Unprivileged.
 *
 *   cc -O2 -o pilot tools/pilot_whole_file_delivery.c
 *   ./pilot <db> [trials] [window_kb]
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

enum { M_FADV_WHOLE, M_RA_WHOLE, M_RA_WIN, M_FADV_WIN, M_POPULATE, NMETH };
static const char *NAME[NMETH] = {"fadvise_whole", "readahead_whole", "readahead_win",
                                  "fadvise_win", "populate"};
static const int DELAY_MS[] = {0, 10, 100, 1000};
#define NDELAY 4

static int fd;
static size_t size, npages;
static void *probe_map;            /* PROT_READ mapping used only for mincore */
static unsigned char *vec;

static double now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

static size_t resident(void) {
    if (mincore(probe_map, size, vec) != 0) { perror("mincore"); exit(1); }
    size_t n = 0;
    for (size_t i = 0; i < npages; i++) n += vec[i] & 1;
    return n;
}

static int cold_reset(void) {
    for (int k = 0; k < 5; k++) {
        posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED);
        if (resident() == 0) return 0;
        usleep(10000);
    }
    return -1;
}

static int cmp_d(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}
static double median(double *v, int n) {
    qsort(v, n, sizeof *v, cmp_d);
    return n % 2 ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <db> [trials] [window_kb]\n", argv[0]); return 2; }
    int trials = argc > 2 ? atoi(argv[2]) : 5;
    size_t win = (argc > 3 ? (size_t)atoi(argv[3]) : 128) * 1024;

    fd = open(argv[1], O_RDONLY);
    if (fd < 0) { perror("open"); return 1; }
    struct stat st;
    fstat(fd, &st);
    size = st.st_size;
    long pg = sysconf(_SC_PAGESIZE);
    npages = (size + pg - 1) / pg;
    probe_map = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0);
    vec = malloc(npages);
    if (probe_map == MAP_FAILED || !vec) { perror("setup"); return 1; }

    double call_us[NMETH][64], res[NMETH][NDELAY][64];
    for (int t = 0; t < trials; t++) {
        for (int m = 0; m < NMETH; m++) {
            if (cold_reset() != 0) { fprintf(stderr, "cache not cold before %s\n", NAME[m]); return 1; }
            void *pop = NULL;
            int rc = 0;
            double t0 = now_us();
            switch (m) {
            case M_FADV_WHOLE: rc = posix_fadvise(fd, 0, size, POSIX_FADV_WILLNEED); break;
            case M_RA_WHOLE:   rc = (int)readahead(fd, 0, size); break;
            case M_RA_WIN:
                for (size_t off = 0; off < size && rc == 0; off += win) rc = (int)readahead(fd, off, win);
                break;
            case M_FADV_WIN:
                for (size_t off = 0; off < size && rc == 0; off += win)
                    rc = posix_fadvise(fd, off, win, POSIX_FADV_WILLNEED);
                break;
            case M_POPULATE:
                pop = mmap(NULL, size, PROT_READ, MAP_SHARED | MAP_POPULATE, fd, 0);
                rc = pop == MAP_FAILED ? -1 : 0;
                break;
            }
            call_us[m][t] = now_us() - t0;
            if (rc != 0) { fprintf(stderr, "%s returned %d\n", NAME[m], rc); return 1; }
            double waited = 0;
            for (int d = 0; d < NDELAY; d++) {
                double target = DELAY_MS[d] * 1000.0;
                if (target > waited) { usleep((useconds_t)(target - waited)); waited = target; }
                res[m][d][t] = (double)resident();
            }
            if (pop) munmap(pop, size);
        }
    }

    printf("file %s: %zu bytes, %zu pages; window %zu KB; %d trials; medians\n",
           argv[1], size, npages, win / 1024, trials);
    printf("%-16s %12s %10s %10s %10s %10s\n", "method", "call_us", "res@0", "res@10ms",
           "res@100ms", "res@1s");
    for (int m = 0; m < NMETH; m++) {
        printf("%-16s %12.0f", NAME[m], median(call_us[m], trials));
        for (int d = 0; d < NDELAY; d++) printf(" %10.0f", median(res[m][d], trials));
        printf("\n");
    }
    cold_reset();
    return 0;
}
