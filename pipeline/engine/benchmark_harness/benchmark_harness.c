/*
 * SQLite cold-start benchmark harness.
 *
 * This runner accepts generated YCSB-style transaction workloads:
 *   read <id>
 *   update <id>
 *   insert <id>
 *   scan <id> <len>
 *   readmodifywrite <id>
 *
 * It uses Linux mmap/mincore/madvise to observe and cool the database file's
 * page-cache residency, then executes each workload transaction through SQLite
 * prepared statements while recording per-operation latency and page faults.
 */

#define _GNU_SOURCE

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <sched.h>
#include <stdarg.h>
#include <sqlite3.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

typedef enum {
    COLD_ADVICE_NONE = 0,
    COLD_ADVICE_COLD,
    COLD_ADVICE_PAGEOUT,
    COLD_ADVICE_DONTNEED
} cold_advice_t;

typedef enum {
    SQLITE_OPEN_BEFORE_COLD = 0,
    SQLITE_OPEN_AFTER_COLD
} sqlite_open_timing_t;

typedef enum {
    SCHEMA_INIT_BEFORE_COLD = 0,
    SCHEMA_INIT_AFTER_COLD
} schema_init_timing_t;

typedef enum {
    OP_READ = 0,
    OP_UPDATE,
    OP_INSERT,
    OP_SCAN,
    OP_READMODIFYWRITE
} op_type_t;

typedef struct {
    op_type_t type;
    uint32_t target_id;
    uint32_t scan_len;
} workload_op_t;

typedef struct {
    workload_op_t *ops;
    size_t count;
    size_t capacity;
} workload_t;

/* How the cache state is reset between the warm phase and the measured query
 * (prereg R1a / R1b). drop_caches is the original protocol and the default. */
typedef enum {
    RESET_DROP_CACHES,      /* madvise + setuid drop_caches helper (unchanged default) */
    RESET_CGROUP_PRESSURE,  /* R1b: natural reclaim inside a memory-capped cgroup */
    RESET_FRESH_PROCESS     /* new process + new connection; OS page cache left as is */
} reset_mode_t;

typedef enum {
    COMPETITOR_STREAM,      /* read() a scratch file once per idle (use-once pages) */
    COMPETITOR_HOT,         /* mmap a scratch file and re-touch it during idle */
    COMPETITOR_NONE
} competitor_t;

#define MMAP_SIZE_DEFAULT (-1)  /* sentinel: map the whole file; explicit 0 = mmap off */

typedef struct {
    const char *db_path;
    const char *output_csv;
    const char *record_dir;
    const char *workload_path;
    int64_t mmap_size;
    const char *drop_caches_script;
    const char *post_cold_script;
    const char *verify_hotset;
    cold_advice_t cold_advice;
    sqlite_open_timing_t sqlite_open_timing;
    schema_init_timing_t schema_init_timing;
    bool debug;
    bool readonly;           /* open DB read-only (clean for read-only TTFQ measurement) */
    bool require_read_first; /* F8: abort if workload op[0] is not a read */
    int  warm_cpu_ms;        /* busy-spin the measuring core this long before op[0] (freq ramp) */
    int  cpu;                /* pin process to this core via sched_setaffinity (-1 = no pin) */
    int64_t cache_size;      /* PRAGMA cache_size (default 0 = no pager retention, F1) */
    size_t pre_cold_ops;     /* run ops[0..N) on the measuring connection before the reset */
    size_t measure_ops;      /* ops in the measured run (0 = through the end of the workload) */
    reset_mode_t reset_mode;
    /* --reset cgroup-pressure (prereg R1b) */
    double pressure_ratio;   /* file budget as a fraction of the DB size; < 0 = unlimited */
    competitor_t competitor;
    size_t invocations;      /* K */
    size_t ops_per_invocation; /* Q */
    double idle_s;           /* T */
    double quiesce_s;        /* competitors stop this long before each idle ends */
    double anon_rate_mibps;
    double stream_turnover;  /* bytes per idle = turnover * ratio * db size */
    double hot_ratio;        /* hot file size = hot_ratio * db size */
    double hot_pages_per_s;
    const char *scratch_dir; /* holds stream.bin and hot.bin */
    int anon_cpu;
    int competitor_cpu;
} options_t;

typedef struct {
    int fd;
    size_t file_size;
    size_t os_page_size;
    size_t os_page_count;
    size_t sqlite_page_size;
    uint32_t sqlite_page_count;
    void *mapping;
} mapped_db_t;

typedef struct {
    sqlite3 *db;
    sqlite3_stmt *read_stmt;
    sqlite3_stmt *update_stmt;
    sqlite3_stmt *insert_stmt;
    sqlite3_stmt *scan_stmt;
    bool opened;
    bool schema_initialized;
} sqlite_ctx_t;

typedef struct {
    uint64_t total_ns;
    uint64_t first_query_ns;
    long total_majflt;
    long total_minflt;
} benchmark_summary_t;

static uint16_t rd_be16(const uint8_t *p) {
    return ((uint16_t)p[0] << 8) | p[1];
}

static void usage(const char *prog) {
    fprintf(stderr,
            "Usage: %s --workload <file> [options]\n"
            "\n"
            "Workload format:\n"
            "  One operation per line:\n"
            "    read <id>\n"
            "    update <id>\n"
            "    insert <id>\n"
            "    scan <id> <len>\n"
            "    readmodifywrite <id>\n"
            "  Blank lines and lines starting with # are ignored.\n"
            "\n"
            "Options:\n"
            "  --db <file>                     SQLite DB path (default: test.db).\n"
            "  --output <file>                 Per-operation CSV output path (default: benchmark_harness_operations.csv).\n"
            "  --record-dir <dir>              Run record directory (default: benchmark_harness_runs).\n"
            "  --workload <file>               Pre-generated workload text file.\n"
            "  --mmap-size <bytes>             PRAGMA mmap_size target (default: file size; 0 = mmap off,\n"
            "                                  pager mode: reads are counted per layer by a VFS shim).\n"
            "  --cache-size <n>                PRAGMA cache_size (default 0; SQLite's own default is -2000).\n"
            "  --pre-cold-ops <n>              Run ops[0..n) on the measuring connection before the reset;\n"
            "                                  the measured run starts at op n (default 0).\n"
            "  --measure-ops <n>               Ops in the measured run (default: through the end).\n"
            "  --reset drop_caches|cgroup-pressure|fresh-process   Default: drop_caches.\n"
            "      cgroup-pressure (prereg R1b; run inside systemd-run --user --scope):\n"
            "      --pressure-ratio <r|inf> --competitor stream|hot|none --invocations <K>\n"
            "      --ops-per-invocation <Q> --idle-s <T> --quiesce-s <s> --anon-rate-mibps <x>\n"
            "      --stream-turnover <u> --hot-ratio <h> --hot-pages-per-s <x> --scratch-dir <dir>\n"
            "      --anon-cpu <n> --competitor-cpu <n>\n"
            "  --drop-caches-script <file>     Run helper after madvise to drop Linux page cache.\n"
            "                                  Recommended: /usr/local/sbin/drop-caches (setuid wrapper).\n"
            "  --post-cold-script <file>       Run helper after cold/drop-caches and before SQLite query setup.\n"
            "  --verify-hotset <file>          Hotset CSV (page_number,is_resident|file_offset). Emits\n"
            "                                  verify_cold_pct (after drop-caches, before prefetch) and\n"
            "                                  verify_delivery_pct (after prefetch, before first query).\n"
            "  --cold-advice none              Do not run madvise/drop-caches; measure current cache state.\n"
            "  --cold-advice cold              Use MADV_COLD only.\n"
            "  --cold-advice pageout           Use MADV_COLD then MADV_PAGEOUT.\n"
            "  --cold-advice dontneed          Use MADV_COLD, MADV_PAGEOUT, then MADV_DONTNEED (default).\n"
            "  --sqlite-open-timing before-cold|after-cold    Default: before-cold.\n"
            "  --schema-init-timing before-cold|after-cold    Default: before-cold.\n"
            "  --readonly                      Open DB read-only (clean for read-only TTFQ measurement).\n"
            "  --require-read-first            Abort if workload op[0] is not a read (F8).\n"
            "  --warm-cpu-ms <ms>              Busy-spin the pinned core this long before op[0] (freq ramp; default 0).\n"
            "  --cpu <n>                       Pin process to core n via sched_setaffinity (default -1 = no pin).\n"
            "  --debug                         Print sync, madvise, drop-caches, and SQLite timing diagnostics.\n",
            prog);
}

static int64_t parse_i64(const char *s, const char *flag) {
    char *end = NULL;
    long long value = strtoll(s, &end, 10);
    if (end == s || *end != '\0') {
        fprintf(stderr, "error: invalid integer for %s: %s\n", flag, s);
        exit(1);
    }
    return (int64_t)value;
}

static int64_t parse_count(const char *s, const char *flag) {   /* >= 0 */
    int64_t v = parse_i64(s, flag);
    if (v < 0) {
        fprintf(stderr, "error: %s must be >= 0 (got %s)\n", flag, s);
        exit(1);
    }
    return v;
}

static double parse_f64(const char *s, const char *flag) {
    char *end = NULL;
    double value = strtod(s, &end);
    if (end == s || *end != '\0') {
        fprintf(stderr, "error: invalid number for %s: %s\n", flag, s);
        exit(1);
    }
    return value;
}

static void trim_whitespace(char *s) {
    char *start = s;
    size_t len;

    while (*start != '\0' && isspace((unsigned char)*start)) {
        ++start;
    }
    if (start != s) {
        memmove(s, start, strlen(start) + 1);
    }

    len = strlen(s);
    while (len > 0 && isspace((unsigned char)s[len - 1])) {
        s[--len] = '\0';
    }
}

static void parse_args(int argc, char **argv, options_t *opts) {
    memset(opts, 0, sizeof(*opts));
    opts->db_path = "test.db";
    opts->output_csv = "benchmark_harness_operations.csv";
    opts->record_dir = "benchmark_harness_runs";
    opts->cold_advice = COLD_ADVICE_DONTNEED;
    opts->sqlite_open_timing = SQLITE_OPEN_BEFORE_COLD;
    opts->schema_init_timing = SCHEMA_INIT_BEFORE_COLD;
    opts->cpu = -1;
    opts->mmap_size = MMAP_SIZE_DEFAULT;
    opts->cache_size = 0;
    opts->reset_mode = RESET_DROP_CACHES;
    opts->pressure_ratio = -1.0;
    opts->competitor = COMPETITOR_STREAM;
    opts->invocations = 5;
    opts->ops_per_invocation = 200;
    opts->idle_s = 60.0;
    opts->quiesce_s = 2.0;
    opts->anon_rate_mibps = 32.0;
    opts->stream_turnover = 1.0;
    opts->hot_ratio = 0.5;
    opts->hot_pages_per_s = 500.0;
    opts->anon_cpu = 12;
    opts->competitor_cpu = 14;

    for (int i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        if (strcmp(arg, "--db") == 0 && i + 1 < argc) {
            opts->db_path = argv[++i];
        } else if (strcmp(arg, "--output") == 0 && i + 1 < argc) {
            opts->output_csv = argv[++i];
        } else if (strcmp(arg, "--record-dir") == 0 && i + 1 < argc) {
            opts->record_dir = argv[++i];
        } else if (strcmp(arg, "--workload") == 0 && i + 1 < argc) {
            opts->workload_path = argv[++i];
        } else if (strcmp(arg, "--mmap-size") == 0 && i + 1 < argc) {
            opts->mmap_size = parse_count(argv[++i], "--mmap-size");
        } else if (strcmp(arg, "--drop-caches-script") == 0 && i + 1 < argc) {
            opts->drop_caches_script = argv[++i];
        } else if (strcmp(arg, "--post-cold-script") == 0 && i + 1 < argc) {
            opts->post_cold_script = argv[++i];
        } else if (strcmp(arg, "--verify-hotset") == 0 && i + 1 < argc) {
            opts->verify_hotset = argv[++i];
        } else if (strcmp(arg, "--cold-advice") == 0 && i + 1 < argc) {
            const char *mode = argv[++i];
            if (strcmp(mode, "none") == 0) {
                opts->cold_advice = COLD_ADVICE_NONE;
            } else if (strcmp(mode, "cold") == 0) {
                opts->cold_advice = COLD_ADVICE_COLD;
            } else if (strcmp(mode, "pageout") == 0) {
                opts->cold_advice = COLD_ADVICE_PAGEOUT;
            } else if (strcmp(mode, "dontneed") == 0) {
                opts->cold_advice = COLD_ADVICE_DONTNEED;
            } else {
                fprintf(stderr, "error: unknown --cold-advice mode: %s\n", mode);
                exit(1);
            }
        } else if (strcmp(arg, "--sqlite-open-timing") == 0 && i + 1 < argc) {
            const char *mode = argv[++i];
            if (strcmp(mode, "before-cold") == 0) {
                opts->sqlite_open_timing = SQLITE_OPEN_BEFORE_COLD;
            } else if (strcmp(mode, "after-cold") == 0) {
                opts->sqlite_open_timing = SQLITE_OPEN_AFTER_COLD;
            } else {
                fprintf(stderr, "error: unknown --sqlite-open-timing mode: %s\n", mode);
                exit(1);
            }
        } else if (strcmp(arg, "--schema-init-timing") == 0 && i + 1 < argc) {
            const char *mode = argv[++i];
            if (strcmp(mode, "before-cold") == 0) {
                opts->schema_init_timing = SCHEMA_INIT_BEFORE_COLD;
            } else if (strcmp(mode, "after-cold") == 0) {
                opts->schema_init_timing = SCHEMA_INIT_AFTER_COLD;
            } else {
                fprintf(stderr, "error: unknown --schema-init-timing mode: %s\n", mode);
                exit(1);
            }
        } else if (strcmp(arg, "--readonly") == 0) {
            opts->readonly = true;
        } else if (strcmp(arg, "--require-read-first") == 0) {
            opts->require_read_first = true;
        } else if (strcmp(arg, "--warm-cpu-ms") == 0 && i + 1 < argc) {
            opts->warm_cpu_ms = (int)parse_i64(argv[++i], "--warm-cpu-ms");
        } else if (strcmp(arg, "--cpu") == 0 && i + 1 < argc) {
            opts->cpu = (int)parse_i64(argv[++i], "--cpu");
        } else if (strcmp(arg, "--cache-size") == 0 && i + 1 < argc) {
            opts->cache_size = parse_i64(argv[++i], "--cache-size");
        } else if (strcmp(arg, "--pre-cold-ops") == 0 && i + 1 < argc) {
            opts->pre_cold_ops = (size_t)parse_count(argv[++i], "--pre-cold-ops");
        } else if (strcmp(arg, "--measure-ops") == 0 && i + 1 < argc) {
            opts->measure_ops = (size_t)parse_count(argv[++i], "--measure-ops");
        } else if (strcmp(arg, "--reset") == 0 && i + 1 < argc) {
            const char *mode = argv[++i];
            if (strcmp(mode, "drop_caches") == 0) {
                opts->reset_mode = RESET_DROP_CACHES;
            } else if (strcmp(mode, "cgroup-pressure") == 0) {
                opts->reset_mode = RESET_CGROUP_PRESSURE;
            } else if (strcmp(mode, "fresh-process") == 0) {
                opts->reset_mode = RESET_FRESH_PROCESS;
            } else {
                fprintf(stderr, "error: unknown --reset mode: %s\n", mode);
                exit(1);
            }
        } else if (strcmp(arg, "--pressure-ratio") == 0 && i + 1 < argc) {
            const char *v = argv[++i];
            opts->pressure_ratio = strcmp(v, "inf") == 0 ? -1.0 : parse_f64(v, "--pressure-ratio");
            if (strcmp(v, "inf") != 0 && (opts->pressure_ratio < 0 || opts->pressure_ratio > 1)) {
                fprintf(stderr, "error: --pressure-ratio must be in [0,1] or inf\n");
                exit(1);
            }
        } else if (strcmp(arg, "--competitor") == 0 && i + 1 < argc) {
            const char *v = argv[++i];
            if (strcmp(v, "stream") == 0) opts->competitor = COMPETITOR_STREAM;
            else if (strcmp(v, "hot") == 0) opts->competitor = COMPETITOR_HOT;
            else if (strcmp(v, "none") == 0) opts->competitor = COMPETITOR_NONE;
            else { fprintf(stderr, "error: unknown --competitor: %s\n", v); exit(1); }
        } else if (strcmp(arg, "--invocations") == 0 && i + 1 < argc) {
            opts->invocations = (size_t)parse_count(argv[++i], "--invocations");
        } else if (strcmp(arg, "--ops-per-invocation") == 0 && i + 1 < argc) {
            opts->ops_per_invocation = (size_t)parse_count(argv[++i], "--ops-per-invocation");
        } else if (strcmp(arg, "--idle-s") == 0 && i + 1 < argc) {
            opts->idle_s = parse_f64(argv[++i], "--idle-s");
        } else if (strcmp(arg, "--quiesce-s") == 0 && i + 1 < argc) {
            opts->quiesce_s = parse_f64(argv[++i], "--quiesce-s");
        } else if (strcmp(arg, "--anon-rate-mibps") == 0 && i + 1 < argc) {
            opts->anon_rate_mibps = parse_f64(argv[++i], "--anon-rate-mibps");
        } else if (strcmp(arg, "--stream-turnover") == 0 && i + 1 < argc) {
            opts->stream_turnover = parse_f64(argv[++i], "--stream-turnover");
        } else if (strcmp(arg, "--hot-ratio") == 0 && i + 1 < argc) {
            opts->hot_ratio = parse_f64(argv[++i], "--hot-ratio");
        } else if (strcmp(arg, "--hot-pages-per-s") == 0 && i + 1 < argc) {
            opts->hot_pages_per_s = parse_f64(argv[++i], "--hot-pages-per-s");
        } else if (strcmp(arg, "--scratch-dir") == 0 && i + 1 < argc) {
            opts->scratch_dir = argv[++i];
        } else if (strcmp(arg, "--anon-cpu") == 0 && i + 1 < argc) {
            opts->anon_cpu = (int)parse_i64(argv[++i], "--anon-cpu");
        } else if (strcmp(arg, "--competitor-cpu") == 0 && i + 1 < argc) {
            opts->competitor_cpu = (int)parse_i64(argv[++i], "--competitor-cpu");
        } else if (strcmp(arg, "--debug") == 0) {
            opts->debug = true;
        } else {
            usage(argv[0]);
            exit(1);
        }
    }

    if (opts->workload_path == NULL) {
        usage(argv[0]);
        exit(1);
    }

    if (opts->sqlite_open_timing == SQLITE_OPEN_AFTER_COLD &&
        opts->schema_init_timing == SCHEMA_INIT_BEFORE_COLD) {
        fprintf(stderr,
                "error: --schema-init-timing before-cold requires --sqlite-open-timing before-cold\n");
        exit(1);
    }
}

static void die_errno(const char *what) {
    perror(what);
    exit(1);
}

static void die_sqlite(sqlite3 *db, const char *what, int rc) {
    fprintf(stderr, "error: %s failed: rc=%d msg=%s\n",
            what, rc, db ? sqlite3_errmsg(db) : "(no db)");
    exit(1);
}

static void emit_line_to(FILE *record, bool echo_stderr, const char *fmt, ...) {
    va_list ap;
    va_list ap_copy;

    va_start(ap, fmt);
    va_copy(ap_copy, ap);
    if (echo_stderr) {
        vfprintf(stderr, fmt, ap);
    }
    if (record != NULL) {
        vfprintf(record, fmt, ap_copy);
        fflush(record);
    }
    va_end(ap_copy);
    va_end(ap);
}

static void emit_line(FILE *record, const char *fmt, ...) {
    va_list ap;
    va_list ap_copy;

    va_start(ap, fmt);
    va_copy(ap_copy, ap);
    vfprintf(stderr, fmt, ap);
    if (record != NULL) {
        vfprintf(record, fmt, ap_copy);
        fflush(record);
    }
    va_end(ap_copy);
    va_end(ap);
}

static void write_record_line(FILE *record, const char *fmt, ...) {
    va_list ap;

    if (record == NULL) {
        return;
    }

    va_start(ap, fmt);
    vfprintf(record, fmt, ap);
    va_end(ap);
    fflush(record);
}

static void exec_sql(sqlite3 *db, const char *sql) {
    char *errmsg = NULL;
    int rc = sqlite3_exec(db, sql, NULL, NULL, &errmsg);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "error: sqlite3_exec failed: %s: %s\n",
                sql, errmsg ? errmsg : "(no message)");
        sqlite3_free(errmsg);
        exit(1);
    }
}

static const char *cold_advice_name(cold_advice_t advice) {
    switch (advice) {
        case COLD_ADVICE_COLD:
            return "cold";
        case COLD_ADVICE_NONE:
            return "none";
        case COLD_ADVICE_PAGEOUT:
            return "pageout";
        case COLD_ADVICE_DONTNEED:
            return "dontneed";
    }
    return "unknown";
}

static FILE *open_run_record(const options_t *opts, char *path_buf,
                             size_t path_buf_size) {
    if (mkdir(opts->record_dir, 0777) != 0 && errno != EEXIST) {
        die_errno("mkdir(record-dir)");
    }

    time_t now = time(NULL);
    struct tm tm_now;
    if (now == (time_t)-1 || localtime_r(&now, &tm_now) == NULL) {
        die_errno("localtime_r");
    }

    char timestamp[32];
    if (strftime(timestamp, sizeof(timestamp), "%Y%m%d-%H%M%S", &tm_now) == 0) {
        fprintf(stderr, "error: failed to format run record timestamp\n");
        exit(1);
    }

    for (unsigned attempt = 0; attempt < 1000; ++attempt) {
        int written;
        if (attempt == 0) {
            written = snprintf(path_buf, path_buf_size, "%s/run-%s-%ld.log",
                               opts->record_dir, timestamp, (long)getpid());
        } else {
            written = snprintf(path_buf, path_buf_size, "%s/run-%s-%ld-%u.log",
                               opts->record_dir, timestamp, (long)getpid(),
                               attempt);
        }
        if (written < 0 || (size_t)written >= path_buf_size) {
            fprintf(stderr, "error: run record path is too long\n");
            exit(1);
        }

        int fd = open(path_buf, O_WRONLY | O_CREAT | O_EXCL, 0666);
        if (fd >= 0) {
            FILE *record = fdopen(fd, "w");
            if (record == NULL) {
                int saved_errno = errno;
                close(fd);
                errno = saved_errno;
                die_errno("fdopen(record)");
            }
            return record;
        }
        if (errno != EEXIST) {
            die_errno("open(record)");
        }
    }

    fprintf(stderr, "error: failed to create unique run record in %s\n",
            opts->record_dir);
    exit(1);
}

static int format_unique_output_path(const char *requested, unsigned attempt,
                                     char *path_buf, size_t path_buf_size) {
    if (attempt == 0) {
        return snprintf(path_buf, path_buf_size, "%s", requested);
    }

    const char *last_slash = strrchr(requested, '/');
    const char *last_backslash = strrchr(requested, '\\');
    const char *last_sep = last_slash;
    if (last_backslash != NULL && (last_sep == NULL || last_backslash > last_sep)) {
        last_sep = last_backslash;
    }

    const char *name_start = last_sep == NULL ? requested : last_sep + 1;
    const char *dot = strrchr(name_start, '.');
    if (dot == NULL || dot == name_start) {
        return snprintf(path_buf, path_buf_size, "%s-%u", requested, attempt);
    }

    size_t prefix_len = (size_t)(dot - requested);
    return snprintf(path_buf, path_buf_size, "%.*s-%u%s",
                    (int)prefix_len, requested, attempt, dot);
}

static FILE *open_unique_output_csv(const char *requested, char *path_buf,
                                    size_t path_buf_size) {
    for (unsigned attempt = 0; attempt < 1000; ++attempt) {
        int written =
            format_unique_output_path(requested, attempt, path_buf, path_buf_size);
        if (written < 0 || (size_t)written >= path_buf_size) {
            fprintf(stderr, "error: output CSV path is too long\n");
            exit(1);
        }

        int fd = open(path_buf, O_WRONLY | O_CREAT | O_EXCL, 0666);
        if (fd >= 0) {
            FILE *out = fdopen(fd, "w");
            if (out == NULL) {
                int saved_errno = errno;
                close(fd);
                errno = saved_errno;
                die_errno("fdopen(output)");
            }
            return out;
        }
        if (errno != EEXIST) {
            die_errno("open(output)");
        }
    }

    fprintf(stderr, "error: failed to create unique output CSV for %s\n",
            requested);
    exit(1);
}

static mapped_db_t map_db_file(const char *db_path) {
    mapped_db_t dbmap;
    memset(&dbmap, 0, sizeof(dbmap));

    long os_page_size_long = sysconf(_SC_PAGESIZE);
    if (os_page_size_long <= 0) {
        die_errno("sysconf(_SC_PAGESIZE)");
    }
    dbmap.os_page_size = (size_t)os_page_size_long;

    dbmap.fd = open(db_path, O_RDONLY);
    if (dbmap.fd < 0) {
        die_errno("open");
    }

    struct stat st;
    if (fstat(dbmap.fd, &st) != 0) {
        die_errno("fstat");
    }
    if (st.st_size < 100) {
        fprintf(stderr, "error: file too small to be a SQLite db\n");
        exit(1);
    }

    dbmap.file_size = (size_t)st.st_size;
    dbmap.os_page_count =
        (dbmap.file_size + dbmap.os_page_size - 1) / dbmap.os_page_size;
    dbmap.mapping = mmap(NULL, dbmap.file_size, PROT_READ, MAP_SHARED, dbmap.fd, 0);
    if (dbmap.mapping == MAP_FAILED) {
        die_errno("mmap");
    }

    const uint8_t *hdr = (const uint8_t *)dbmap.mapping;
    if (memcmp(hdr, "SQLite format 3\0", 16) != 0) {
        fprintf(stderr, "error: not a SQLite database\n");
        exit(1);
    }

    uint16_t raw_page_size = rd_be16(hdr + 16);
    dbmap.sqlite_page_size =
        (raw_page_size == 1) ? 65536u : (size_t)raw_page_size;
    dbmap.sqlite_page_count =
        (uint32_t)((dbmap.file_size + dbmap.sqlite_page_size - 1) /
                   dbmap.sqlite_page_size);

    return dbmap;
}

static void unmap_db_file(mapped_db_t *dbmap) {
    if (dbmap->mapping && dbmap->mapping != MAP_FAILED) {
        munmap(dbmap->mapping, dbmap->file_size);
    }
    if (dbmap->fd >= 0) {
        close(dbmap->fd);
    }
}

static void fill_mincore_vec(const mapped_db_t *dbmap, unsigned char *vec) {
    if (mincore(dbmap->mapping, dbmap->file_size, vec) != 0) {
        die_errno("mincore");
    }
}

static size_t count_resident_sqlite_pages(const mapped_db_t *dbmap) {
    unsigned char *vec = calloc(dbmap->os_page_count, sizeof(unsigned char));
    if (vec == NULL) {
        die_errno("calloc");
    }

    fill_mincore_vec(dbmap, vec);

    size_t resident_count = 0;
    for (uint32_t page_no = 1; page_no <= dbmap->sqlite_page_count; ++page_no) {
        uint64_t sqlite_begin =
            (uint64_t)(page_no - 1) * dbmap->sqlite_page_size;
        uint64_t sqlite_end = sqlite_begin + dbmap->sqlite_page_size;
        size_t first_os_page = (size_t)(sqlite_begin / dbmap->os_page_size);
        size_t last_os_page = (size_t)((sqlite_end - 1) / dbmap->os_page_size);
        bool resident = true;

        for (size_t os_idx = first_os_page; os_idx <= last_os_page; ++os_idx) {
            if ((vec[os_idx] & 1U) == 0) {
                resident = false;
                break;
            }
        }
        if (resident) {
            ++resident_count;
        }
    }

    free(vec);
    return resident_count;
}

/* --- Hotset residency verification (--verify-hotset) --- */

/* Load the page numbers that make up a prefetch hotset. Auto-detects format
 * by header: "page_number,is_resident" -> pages with is_resident==1 (access/
 * slru hotpages); otherwise (e.g. "page_number,file_offset") -> all listed
 * pages (warmer hotset). Returns malloc'd array; sets *out_n. Caller frees. */
static uint32_t *load_hotset_pages(const char *path, size_t *out_n) {
    FILE *f = fopen(path, "r");
    if (f == NULL) {
        die_errno("fopen(--verify-hotset)");
    }
    char line[512];
    int header = 1;
    int gate_on_resident = 0;
    size_t cap = 256, n = 0;
    uint32_t *pages = malloc(cap * sizeof(uint32_t));
    if (pages == NULL) {
        die_errno("malloc(hotset)");
    }
    while (fgets(line, sizeof(line), f) != NULL) {
        if (header) {
            header = 0;
            gate_on_resident = (strstr(line, "is_resident") != NULL);
            continue;
        }
        unsigned long pn = 0;
        long col2 = 0;
        int matched = sscanf(line, "%lu,%ld", &pn, &col2);
        if (matched < 1) {
            continue;
        }
        if (gate_on_resident && (matched < 2 || col2 != 1)) {
            continue;  /* access/slru: only is_resident==1 pages are the hotset */
        }
        if (n == cap) {
            cap *= 2;
            uint32_t *np = realloc(pages, cap * sizeof(uint32_t));
            if (np == NULL) {
                die_errno("realloc(hotset)");
            }
            pages = np;
        }
        pages[n++] = (uint32_t)pn;
    }
    fclose(f);
    *out_n = n;
    return pages;
}

/* How many of the given hotset pages are fully resident in the OS page cache. */
static size_t hotset_resident_count(const mapped_db_t *dbmap,
                                    const uint32_t *pages, size_t n) {
    unsigned char *vec = calloc(dbmap->os_page_count, sizeof(unsigned char));
    if (vec == NULL) {
        die_errno("calloc");
    }
    fill_mincore_vec(dbmap, vec);

    size_t resident = 0;
    for (size_t i = 0; i < n; ++i) {
        uint32_t page_no = pages[i];
        if (page_no < 1 || page_no > dbmap->sqlite_page_count) {
            continue;
        }
        uint64_t sqlite_begin =
            (uint64_t)(page_no - 1) * dbmap->sqlite_page_size;
        uint64_t sqlite_end = sqlite_begin + dbmap->sqlite_page_size;
        size_t first_os_page = (size_t)(sqlite_begin / dbmap->os_page_size);
        size_t last_os_page = (size_t)((sqlite_end - 1) / dbmap->os_page_size);
        bool all_resident = true;
        for (size_t os_idx = first_os_page; os_idx <= last_os_page; ++os_idx) {
            if ((vec[os_idx] & 1U) == 0) {
                all_resident = false;
                break;
            }
        }
        if (all_resident) {
            ++resident;
        }
    }
    free(vec);
    return resident;
}

/* Snapshot hotset residency and emit "verify_<label>_pct=..." (stderr + record).
 * One mincore call (~us): negligible perturbation, unlike an external checker. */
static void verify_hotset_residency(const mapped_db_t *dbmap,
                                    const uint32_t *pages, size_t n,
                                    const char *label, FILE *record) {
    if (pages == NULL || n == 0) {
        return;
    }
    size_t resident = hotset_resident_count(dbmap, pages, n);
    double pct = 100.0 * (double)resident / (double)n;
    emit_line(record, "verify_%s_pct=%.1f resident=%zu/%zu\n",
              label, pct, resident, n);
}

static void append_resident_range(uint32_t **starts, uint32_t **ends,
                                  size_t *count, size_t *capacity,
                                  uint32_t start, uint32_t end) {
    if (*count == *capacity) {
        size_t new_capacity = *capacity == 0 ? 16 : *capacity * 2;
        uint32_t *new_starts = malloc(new_capacity * sizeof(uint32_t));
        uint32_t *new_ends = malloc(new_capacity * sizeof(uint32_t));
        if (new_starts == NULL || new_ends == NULL) {
            free(new_starts);
            free(new_ends);
            fprintf(stderr, "error: failed to grow resident range arrays\n");
            exit(1);
        }
        if (*count > 0) {
            memcpy(new_starts, *starts, *count * sizeof(uint32_t));
            memcpy(new_ends, *ends, *count * sizeof(uint32_t));
        }
        free(*starts);
        free(*ends);
        *starts = new_starts;
        *ends = new_ends;
        *capacity = new_capacity;
    }

    (*starts)[*count] = start;
    (*ends)[*count] = end;
    ++(*count);
}

static void report_resident_sqlite_page_distribution(const mapped_db_t *dbmap,
                                                     const char *label,
                                                     FILE *record,
                                                     bool echo_stderr) {
    unsigned char *vec = calloc(dbmap->os_page_count, sizeof(unsigned char));
    if (vec == NULL) {
        die_errno("calloc");
    }

    fill_mincore_vec(dbmap, vec);

    size_t resident_count = 0;
    uint32_t first_resident = 0;
    uint32_t last_resident = 0;
    uint32_t *range_starts = NULL;
    uint32_t *range_ends = NULL;
    size_t range_count = 0;
    size_t range_capacity = 0;
    bool in_run = false;
    uint32_t run_start = 0;
    size_t resident_in_first_1pct = 0;
    size_t resident_in_first_5pct = 0;
    size_t resident_in_first_10pct = 0;
    uint32_t limit_1pct = (dbmap->sqlite_page_count + 99u) / 100u;
    uint32_t limit_5pct = (dbmap->sqlite_page_count + 19u) / 20u;
    uint32_t limit_10pct = (dbmap->sqlite_page_count + 9u) / 10u;

    for (uint32_t page_no = 1; page_no <= dbmap->sqlite_page_count; ++page_no) {
        uint64_t sqlite_begin =
            (uint64_t)(page_no - 1) * dbmap->sqlite_page_size;
        uint64_t sqlite_end = sqlite_begin + dbmap->sqlite_page_size;
        size_t first_os_page = (size_t)(sqlite_begin / dbmap->os_page_size);
        size_t last_os_page = (size_t)((sqlite_end - 1) / dbmap->os_page_size);
        bool resident = true;

        for (size_t os_idx = first_os_page; os_idx <= last_os_page; ++os_idx) {
            if ((vec[os_idx] & 1U) == 0) {
                resident = false;
                break;
            }
        }

        if (resident) {
            ++resident_count;
            if (first_resident == 0) {
                first_resident = page_no;
            }
            last_resident = page_no;
            if (page_no <= limit_1pct) {
                ++resident_in_first_1pct;
            }
            if (page_no <= limit_5pct) {
                ++resident_in_first_5pct;
            }
            if (page_no <= limit_10pct) {
                ++resident_in_first_10pct;
            }
            if (!in_run) {
                in_run = true;
                run_start = page_no;
            }
        } else if (in_run) {
            append_resident_range(&range_starts, &range_ends, &range_count,
                                  &range_capacity, run_start, page_no - 1);
            in_run = false;
        }
    }

    if (in_run) {
        append_resident_range(&range_starts, &range_ends, &range_count,
                              &range_capacity, run_start,
                              dbmap->sqlite_page_count);
    }

    emit_line_to(record, echo_stderr,
                 "%s resident-page distribution: count=%zu first=%" PRIu32
                 " last=%" PRIu32 " first_1%%=%zu first_5%%=%zu first_10%%=%zu\n",
                 label, resident_count, first_resident, last_resident,
                 resident_in_first_1pct, resident_in_first_5pct,
                 resident_in_first_10pct);

    size_t stderr_ranges = range_count < 8 ? range_count : 8;
    for (size_t i = 0; i < range_count; ++i) {
        if (record != NULL) {
            write_record_line(record, "%s resident range[%zu]=%" PRIu32 "-%" PRIu32 "\n",
                              label, i, range_starts[i], range_ends[i]);
        }
        if (echo_stderr && i < stderr_ranges) {
            fprintf(stderr, "%s resident range[%zu]=%" PRIu32 "-%" PRIu32 "\n",
                    label, i, range_starts[i], range_ends[i]);
        }
    }
    if (echo_stderr && range_count > stderr_ranges) {
        fprintf(stderr, "%s resident ranges truncated: total=%zu\n",
                label, range_count);
    }

    free(range_starts);
    free(range_ends);
    free(vec);
}

static void sync_db_pages(const mapped_db_t *dbmap, bool debug) {
    errno = 0;
    if (msync(dbmap->mapping, dbmap->file_size, MS_SYNC) != 0) {
        int saved_errno = errno;
        if (debug) {
            fprintf(stderr,
                    "warn: msync(MS_SYNC) failed: addr=%p len=%zu errno=%d (%s)\n",
                    dbmap->mapping, dbmap->file_size, saved_errno,
                    strerror(saved_errno));
        }
    } else if (debug) {
        fprintf(stderr, "msync(MS_SYNC) succeeded: addr=%p len=%zu\n",
                dbmap->mapping, dbmap->file_size);
    }

    errno = 0;
    if (fsync(dbmap->fd) != 0) {
        int saved_errno = errno;
        if (debug) {
            fprintf(stderr, "warn: fsync(db fd) failed: fd=%d errno=%d (%s)\n",
                    dbmap->fd, saved_errno, strerror(saved_errno));
        }
    } else if (debug) {
        fprintf(stderr, "fsync(db fd) succeeded: fd=%d\n", dbmap->fd);
    }
}

static void run_madvise_step(const mapped_db_t *dbmap, int advice_flag,
                             const char *advice_name, bool debug) {
    uintptr_t addr_value = (uintptr_t)dbmap->mapping;
    size_t addr_mod_page = addr_value % dbmap->os_page_size;
    size_t len_mod_page = dbmap->file_size % dbmap->os_page_size;

    errno = 0;
    if (madvise(dbmap->mapping, dbmap->file_size, advice_flag) != 0) {
        int saved_errno = errno;
        fprintf(stderr,
                "error: madvise(%s) failed: addr=%p len=%zu os_page_size=%zu "
                "addr_mod_page=%zu len_mod_page=%zu errno=%d (%s)\n",
                advice_name, dbmap->mapping, dbmap->file_size,
                dbmap->os_page_size, addr_mod_page, len_mod_page,
                saved_errno, strerror(saved_errno));
        exit(1);
    }

    if (debug) {
        fprintf(stderr,
                "madvise(%s) succeeded: addr=%p len=%zu os_page_size=%zu "
                "addr_mod_page=%zu len_mod_page=%zu\n",
                advice_name, dbmap->mapping, dbmap->file_size,
                dbmap->os_page_size, addr_mod_page, len_mod_page);
    }
}

static void apply_cold_advice(const mapped_db_t *dbmap, cold_advice_t advice,
                              bool debug) {
    if (advice == COLD_ADVICE_NONE) {
        if (debug) {
            fprintf(stderr, "cold advice disabled; skipping madvise steps\n");
        }
        return;
    }

    run_madvise_step(dbmap, MADV_COLD, "MADV_COLD", debug);

    if (advice >= COLD_ADVICE_PAGEOUT) {
#ifdef MADV_PAGEOUT
        run_madvise_step(dbmap, MADV_PAGEOUT, "MADV_PAGEOUT", debug);
#else
        if (debug) {
            fprintf(stderr, "warn: MADV_PAGEOUT unsupported at build time; skipping pageout step\n");
        }
#endif
    }

    if (advice >= COLD_ADVICE_DONTNEED) {
        run_madvise_step(dbmap, MADV_DONTNEED, "MADV_DONTNEED", debug);
    }
}

static void run_helper_script(const char *script_path, const char *kind,
                              bool debug, FILE *record) {
    pid_t pid;
    int status;

    if (script_path == NULL) {
        return;
    }
    if (script_path[0] == '\0') {
        fprintf(stderr, "error: --%s path must not be empty\n", kind);
        exit(1);
    }

    if (debug) {
        fprintf(stderr, "running %s helper: %s\n", kind, script_path);
    }

    pid = fork();
    if (pid < 0) {
        die_errno("fork(helper-script)");
    }

    if (pid == 0) {
        char *const argv[] = {(char *)script_path, NULL};
        execv(script_path, argv);
        fprintf(stderr, "error: execv(%s) failed: errno=%d (%s)\n",
                script_path, errno, strerror(errno));
        _exit(127);
    }

    if (waitpid(pid, &status, 0) < 0) {
        die_errno("waitpid(helper-script)");
    }

    if (WIFEXITED(status)) {
        int code = WEXITSTATUS(status);
        if (code != 0) {
            fprintf(stderr,
                    "error: %s helper failed with exit code %d: %s\n",
                    kind, code, script_path);
            exit(1);
        }
    } else if (WIFSIGNALED(status)) {
        fprintf(stderr,
                "error: %s helper was killed by signal %d: %s\n",
                kind, WTERMSIG(status), script_path);
        exit(1);
    } else {
        fprintf(stderr, "error: %s helper ended unexpectedly: %s\n",
                kind, script_path);
        exit(1);
    }

    write_record_line(record, "%s_result=success\n", kind);
    if (debug) {
        fprintf(stderr, "%s helper succeeded: %s\n", kind, script_path);
    }
}

static void workload_push(workload_t *workload, workload_op_t op) {
    if (workload->count == workload->capacity) {
        size_t new_capacity = workload->capacity == 0 ? 1024 : workload->capacity * 2;
        workload_op_t *new_ops =
            realloc(workload->ops, new_capacity * sizeof(workload_op_t));
        if (new_ops == NULL) {
            die_errno("realloc(workload)");
        }
        workload->ops = new_ops;
        workload->capacity = new_capacity;
    }
    workload->ops[workload->count++] = op;
}

static const char *op_type_name(op_type_t type) {
    switch (type) {
        case OP_READ:
            return "read";
        case OP_UPDATE:
            return "update";
        case OP_INSERT:
            return "insert";
        case OP_SCAN:
            return "scan";
        case OP_READMODIFYWRITE:
            return "readmodifywrite";
    }
    return "unknown";
}

static workload_t load_workload(const char *path) {
    FILE *fp = fopen(path, "r");
    char line[256];
    size_t lineno = 0;
    workload_t workload;
    memset(&workload, 0, sizeof(workload));

    if (fp == NULL) {
        perror(path);
        exit(1);
    }

    while (fgets(line, sizeof(line), fp) != NULL) {
        char op_text[32];
        unsigned long long id = 0;
        unsigned long long scan_len = 0;
        int parsed;
        workload_op_t op;
        ++lineno;

        trim_whitespace(line);
        if (line[0] == '\0' || line[0] == '#') {
            continue;
        }

        memset(&op, 0, sizeof(op));
        parsed = sscanf(line, "%31s %llu %llu", op_text, &id, &scan_len);
        if (parsed < 2) {
            fprintf(stderr, "error: invalid workload line %zu in %s: %s\n",
                    lineno, path, line);
            exit(1);
        }

        if (strcmp(op_text, "read") == 0) {
            op.type = OP_READ;
        } else if (strcmp(op_text, "update") == 0) {
            op.type = OP_UPDATE;
        } else if (strcmp(op_text, "insert") == 0) {
            op.type = OP_INSERT;
        } else if (strcmp(op_text, "scan") == 0) {
            op.type = OP_SCAN;
            if (parsed != 3 || scan_len == 0 || scan_len > UINT32_MAX) {
                fprintf(stderr,
                        "error: scan requires positive length on line %zu in %s\n",
                        lineno, path);
                exit(1);
            }
            op.scan_len = (uint32_t)scan_len;
        } else if (strcmp(op_text, "readmodifywrite") == 0) {
            op.type = OP_READMODIFYWRITE;
        } else {
            fprintf(stderr,
                    "error: unsupported workload op '%s' on line %zu in %s\n",
                    op_text, lineno, path);
            exit(1);
        }

        if (id > UINT32_MAX) {
            fprintf(stderr, "error: workload id out of range on line %zu in %s\n",
                    lineno, path);
            exit(1);
        }
        op.target_id = (uint32_t)id;
        if (op.type != OP_SCAN && parsed != 2) {
            fprintf(stderr,
                    "error: operation '%s' expects exactly one id on line %zu in %s\n",
                    op_text, lineno, path);
            exit(1);
        }
        workload_push(&workload, op);
    }

    fclose(fp);

    if (workload.count == 0) {
        fprintf(stderr, "error: workload file is empty: %s\n", path);
        exit(1);
    }

    return workload;
}

static void free_workload(workload_t *workload) {
    free(workload->ops);
    workload->ops = NULL;
    workload->count = 0;
    workload->capacity = 0;
}

static void sqlite_open_if_needed(sqlite_ctx_t *ctx, const options_t *opts) {
    if (ctx->opened) {
        return;
    }

    int open_flags = (opts->readonly ? SQLITE_OPEN_READONLY : SQLITE_OPEN_READWRITE)
                     | SQLITE_OPEN_NOMUTEX;
    /* pager mode (mmap off): route reads through the counting VFS shim */
    int rc = sqlite3_open_v2(opts->db_path, &ctx->db, open_flags,
                             opts->mmap_size == 0 ? "count" : NULL);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, "sqlite3_open_v2", rc);
    }

    rc = sqlite3_busy_timeout(ctx->db, 5000);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, "sqlite3_busy_timeout", rc);
    }

    char pragma_sql[256];
    snprintf(pragma_sql, sizeof(pragma_sql), "PRAGMA mmap_size = %" PRId64 ";",
             opts->mmap_size);
    exec_sql(ctx->db, pragma_sql);
    snprintf(pragma_sql, sizeof(pragma_sql), "PRAGMA cache_size = %" PRId64 ";",
             opts->cache_size);
    exec_sql(ctx->db, pragma_sql);
    ctx->opened = true;
}

static void sqlite_init_schema_if_needed(sqlite_ctx_t *ctx) {
    if (ctx->schema_initialized) {
        return;
    }

    int rc = sqlite3_prepare_v2(ctx->db,
                                "SELECT payload FROM items WHERE id = ?1;",
                                -1, &ctx->read_stmt, NULL);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, "sqlite3_prepare_v2(read)", rc);
    }

    rc = sqlite3_prepare_v2(ctx->db,
                            "UPDATE items SET payload = randomblob(100) WHERE id = ?1;",
                            -1, &ctx->update_stmt, NULL);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, "sqlite3_prepare_v2(update)", rc);
    }

    rc = sqlite3_prepare_v2(ctx->db,
                            "INSERT INTO items(id, k1, k2, payload) "
                            "VALUES(?1, printf('group_%04d', ?1 % 1000), "
                            "printf('tag_%06d', ?1), randomblob(100)) "
                            "ON CONFLICT(id) DO UPDATE SET "
                            "k1 = excluded.k1, k2 = excluded.k2, payload = excluded.payload;",
                            -1, &ctx->insert_stmt, NULL);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, "sqlite3_prepare_v2(insert)", rc);
    }

    rc = sqlite3_prepare_v2(ctx->db,
                            "SELECT payload FROM items WHERE id >= ?1 "
                            "ORDER BY id LIMIT ?2;",
                            -1, &ctx->scan_stmt, NULL);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, "sqlite3_prepare_v2(scan)", rc);
    }

    ctx->schema_initialized = true;
}

static void sqlite_close_ctx(sqlite_ctx_t *ctx) {
    if (ctx->read_stmt != NULL) {
        sqlite3_finalize(ctx->read_stmt);
    }
    if (ctx->update_stmt != NULL) {
        sqlite3_finalize(ctx->update_stmt);
    }
    if (ctx->insert_stmt != NULL) {
        sqlite3_finalize(ctx->insert_stmt);
    }
    if (ctx->scan_stmt != NULL) {
        sqlite3_finalize(ctx->scan_stmt);
    }
    if (ctx->db != NULL) {
        sqlite3_close(ctx->db);
    }
}

static uint64_t timespec_diff_ns(const struct timespec *start,
                                 const struct timespec *end) {
    time_t sec = end->tv_sec - start->tv_sec;
    long nsec = end->tv_nsec - start->tv_nsec;
    if (nsec < 0) {
        --sec;
        nsec += 1000000000L;
    }
    return (uint64_t)sec * 1000000000ull + (uint64_t)nsec;
}

static long rusage_delta(long after, long before) {
    return after - before;
}

static void write_csv_header(FILE *out) {
    fprintf(out,
            "op_no,op_type,target_id,rows_returned,bytes_returned,elapsed_ns,"
            "majflt_delta,minflt_delta\n");
}

static void reset_and_bind_id(sqlite_ctx_t *ctx, sqlite3_stmt *stmt,
                              uint32_t target_id, const char *what) {
    int rc;

    sqlite3_reset(stmt);
    sqlite3_clear_bindings(stmt);
    rc = sqlite3_bind_int64(stmt, 1, (sqlite3_int64)target_id);
    if (rc != SQLITE_OK) {
        die_sqlite(ctx->db, what, rc);
    }
}

static void run_select_stmt(sqlite_ctx_t *ctx, sqlite3_stmt *stmt,
                            int *rows_returned, int *bytes_returned,
                            const char *what) {
    int rc;

    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        const void *blob = sqlite3_column_blob(stmt, 0);
        int n = sqlite3_column_bytes(stmt, 0);
        if (blob != NULL || n == 0) {
            *bytes_returned += n;
        }
        ++(*rows_returned);
    }
    if (rc != SQLITE_DONE) {
        die_sqlite(ctx->db, what, rc);
    }
}

/* Pin the process to one core so the freq-warmed core IS the core that runs op[0].
 * Self-pinning (vs an external taskset wrapper) means the guarantee can't be silently
 * lost if the wrapper is missing. No-op for cpu < 0. */
static void pin_to_cpu(int cpu) {
    if (cpu < 0) {
        return;
    }
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof(set), &set) != 0) {
        fprintf(stderr, "warn: sched_setaffinity(cpu=%d) failed: %s\n", cpu, strerror(errno));
    }
}

/* Busy-spin the current (pinned) core for ~ms milliseconds so amd-pstate ramps it to
 * max frequency BEFORE the first timed query. Runs entirely outside the timed region,
 * so it cannot perturb the measurement -- it only removes the freq-ramp bias that
 * otherwise penalises the fastest (best-prefetched) cells most. */
static void spin_warm_cpu(int ms) {
    if (ms <= 0) {
        return;
    }
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    volatile uint64_t acc = 0;
    for (;;) {
        for (int k = 0; k < 100000; ++k) {
            acc += (uint64_t)k * 2654435761u;
        }
        clock_gettime(CLOCK_MONOTONIC, &now);
        long long elapsed_ms = (now.tv_sec - start.tv_sec) * 1000LL +
                               (now.tv_nsec - start.tv_nsec) / 1000000LL;
        if (elapsed_ms >= ms) {
            break;
        }
    }
    (void)acc;
}

/* Called once right after the first measured op, outside its timed region. */
static void (*g_after_first_op)(void) = NULL;

static benchmark_summary_t run_benchmark(sqlite_ctx_t *ctx,
                                         const workload_t *workload,
                                         size_t start, size_t count,
                                         FILE *out) {
    benchmark_summary_t summary;
    memset(&summary, 0, sizeof(summary));

    for (size_t i = start; i < start + count; ++i) {
        const workload_op_t *op = &workload->ops[i];
        int rc;
        int rows_returned = 0;
        int bytes_returned = 0;
        struct rusage ru_before;
        struct rusage ru_after;
        struct timespec ts_before;
        struct timespec ts_after;
        const char *op_name = op_type_name(op->type);

        if (getrusage(RUSAGE_SELF, &ru_before) != 0) {
            die_errno("getrusage(before)");
        }
        if (clock_gettime(CLOCK_MONOTONIC, &ts_before) != 0) {
            die_errno("clock_gettime(before)");
        }

        switch (op->type) {
            case OP_READ:
                reset_and_bind_id(ctx, ctx->read_stmt, op->target_id,
                                  "sqlite3_bind_int64(read)");
                run_select_stmt(ctx, ctx->read_stmt, &rows_returned,
                                &bytes_returned, "sqlite3_step(read)");
                break;
            case OP_UPDATE:
                reset_and_bind_id(ctx, ctx->update_stmt, op->target_id,
                                  "sqlite3_bind_int64(update)");
                rc = sqlite3_step(ctx->update_stmt);
                if (rc != SQLITE_DONE) {
                    die_sqlite(ctx->db, "sqlite3_step(update)", rc);
                }
                rows_returned = sqlite3_changes(ctx->db);
                break;
            case OP_INSERT:
                reset_and_bind_id(ctx, ctx->insert_stmt, op->target_id,
                                  "sqlite3_bind_int64(insert)");
                rc = sqlite3_step(ctx->insert_stmt);
                if (rc != SQLITE_DONE) {
                    die_sqlite(ctx->db, "sqlite3_step(insert)", rc);
                }
                rows_returned = sqlite3_changes(ctx->db);
                break;
            case OP_SCAN:
                reset_and_bind_id(ctx, ctx->scan_stmt, op->target_id,
                                  "sqlite3_bind_int64(scan id)");
                rc = sqlite3_bind_int64(ctx->scan_stmt, 2,
                                        (sqlite3_int64)op->scan_len);
                if (rc != SQLITE_OK) {
                    die_sqlite(ctx->db, "sqlite3_bind_int64(scan len)", rc);
                }
                run_select_stmt(ctx, ctx->scan_stmt, &rows_returned,
                                &bytes_returned, "sqlite3_step(scan)");
                break;
            case OP_READMODIFYWRITE:
                reset_and_bind_id(ctx, ctx->read_stmt, op->target_id,
                                  "sqlite3_bind_int64(rmw read)");
                run_select_stmt(ctx, ctx->read_stmt, &rows_returned,
                                &bytes_returned, "sqlite3_step(rmw read)");
                reset_and_bind_id(ctx, ctx->update_stmt, op->target_id,
                                  "sqlite3_bind_int64(rmw update)");
                rc = sqlite3_step(ctx->update_stmt);
                if (rc != SQLITE_DONE) {
                    die_sqlite(ctx->db, "sqlite3_step(rmw update)", rc);
                }
                break;
        }

        if (clock_gettime(CLOCK_MONOTONIC, &ts_after) != 0) {
            die_errno("clock_gettime(after)");
        }
        if (getrusage(RUSAGE_SELF, &ru_after) != 0) {
            die_errno("getrusage(after)");
        }

        uint64_t elapsed_ns = timespec_diff_ns(&ts_before, &ts_after);
        long majflt_delta = rusage_delta(ru_after.ru_majflt, ru_before.ru_majflt);
        long minflt_delta = rusage_delta(ru_after.ru_minflt, ru_before.ru_minflt);

        if (i == start) {
            summary.first_query_ns = elapsed_ns;
        }
        summary.total_ns += elapsed_ns;
        summary.total_majflt += majflt_delta;
        summary.total_minflt += minflt_delta;

        fprintf(out, "%zu,%s,%" PRIu32 ",%d,%d,%" PRIu64 ",%ld,%ld\n",
                i + 1, op_name, op->target_id, rows_returned, bytes_returned,
                elapsed_ns, majflt_delta, minflt_delta);
        if (i == start && g_after_first_op != NULL) {
            g_after_first_op();
        }
    }

    return summary;
}

/* ============================================================================
 * R1 extensions (prereg/R1a.md, prereg/R1b.md). With every new flag at its
 * default nothing new runs between the reset and the measured query (the
 * layer map, memstat and residency snapshots happen before the reset and after
 * the run), so the timed path and its surroundings are the original ones.
 * ========================================================================== */

static const char *reset_mode_name(reset_mode_t m) {
    switch (m) {
        case RESET_DROP_CACHES: return "drop_caches";
        case RESET_CGROUP_PRESSURE: return "cgroup-pressure";
        case RESET_FRESH_PROCESS: return "fresh-process";
    }
    return "?";
}

/* ---- page layers: root = sqlite_schema.rootpage, interior, leaf (= everything else) ---- */

enum { LAYER_LEAF = 0, LAYER_ROOT = 1, LAYER_INTERIOR = 2 };

typedef struct {          /* parsed intkey (table) interior page */
    uint32_t n;
    int64_t *keys;        /* key[i] = largest rowid in child[i] */
    uint32_t *child;
    uint32_t right;
} tbl_node_t;

typedef struct {
    bool ok;
    uint32_t npages;
    uint8_t *layer;       /* [1..npages] */
    uint8_t *on_path;     /* [1..npages] root/interior pages on a workload rowid's path */
    tbl_node_t *node;     /* [1..npages] */
    uint32_t items_root;
    uint32_t n_layer[3];
    uint32_t n_path;      /* root/interior pages on a workload path (on_path == 1) */
    uint32_t n_path_leaf; /* leaf pages on a workload path (on_path == 2) */
} layer_map_t;

static layer_map_t g_lm;

static uint32_t rd_be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

static int64_t rd_varint(const uint8_t *p) {
    uint64_t v = 0;
    for (int k = 0; k < 9; ++k) {
        if (k == 8) {
            return (int64_t)((v << 8) | p[k]);
        }
        v = (v << 7) | (p[k] & 0x7F);
        if (p[k] < 0x80) {
            break;
        }
    }
    return (int64_t)v;
}

/* O_DIRECT so classifying pages never changes page-cache residency. */
static bool read_page_direct(int fd, uint8_t *buf, size_t psz, uint32_t pg) {
    return pread(fd, buf, psz, (off_t)(pg - 1) * (off_t)psz) == (ssize_t)psz;
}

static bool page_is_interior(uint8_t type) {
    return type == 2 || type == 5;
}

/* Walk every B-tree from its root (reading root and interior pages only:
 * B-trees are balanced, so once a page's first child is a leaf all its
 * children are), then mark the root/interior pages on the path of every
 * rowid the workload touches in the items table. */
static void lm_build(const char *db_path, const mapped_db_t *dbmap,
                     const workload_t *wl, FILE *record) {
    const char *why = NULL;
    uint32_t np = dbmap->sqlite_page_count;
    size_t psz = dbmap->sqlite_page_size;
    uint32_t roots[512];
    size_t nroots = 0;
    sqlite3 *db = NULL;
    sqlite3_stmt *st = NULL;
    uint8_t *buf = NULL, *buf2 = NULL;
    uint32_t *stack = NULL;
    int fd = -1;

    memset(&g_lm, 0, sizeof(g_lm));
    if (sqlite3_open_v2(db_path, &db, SQLITE_OPEN_READONLY, NULL) != SQLITE_OK ||
        sqlite3_prepare_v2(db, "SELECT rootpage, type = 'table' AND name = 'items' "
                               "FROM sqlite_schema WHERE rootpage > 0", -1, &st, NULL) != SQLITE_OK) {
        why = "sqlite_schema query failed";
        goto done;
    }
    while (sqlite3_step(st) == SQLITE_ROW && nroots < 512) {
        uint32_t r = (uint32_t)sqlite3_column_int64(st, 0);
        if (r >= 2 && r <= np) {
            roots[nroots++] = r;
            if (sqlite3_column_int(st, 1)) {
                g_lm.items_root = r;
            }
        }
    }
    fd = open(db_path, O_RDONLY | O_DIRECT);
    if (fd < 0 || posix_memalign((void **)&buf, 4096, psz) != 0 ||
        posix_memalign((void **)&buf2, 4096, psz) != 0) {
        why = "O_DIRECT open failed";
        goto done;
    }
    g_lm.npages = np;
    g_lm.layer = calloc((size_t)np + 1, 1);
    g_lm.on_path = calloc((size_t)np + 1, 1);
    g_lm.node = calloc((size_t)np + 1, sizeof(tbl_node_t));
    stack = malloc(((size_t)np + 1) * sizeof(uint32_t));
    if (!g_lm.layer || !g_lm.on_path || !g_lm.node || !stack) {
        die_errno("calloc(layer map)");
    }
    size_t sp = 0;
    for (size_t r = 0; r < nroots; ++r) {
        g_lm.layer[roots[r]] = LAYER_ROOT;
        stack[sp++] = roots[r];
    }
    while (sp > 0) {
        uint32_t pg = stack[--sp];
        if (!read_page_direct(fd, buf, psz, pg)) {
            why = "pread(O_DIRECT) failed";
            goto done;
        }
        const uint8_t *h = buf + (pg == 1 ? 100 : 0);
        if (!page_is_interior(h[0])) {
            continue;
        }
        if (g_lm.layer[pg] != LAYER_ROOT) {
            g_lm.layer[pg] = LAYER_INTERIOR;
        }
        uint32_t n = rd_be16(h + 3);
        uint32_t right = rd_be32(h + 8);
        tbl_node_t *node = &g_lm.node[pg];
        node->n = n;
        node->right = right;
        node->child = malloc(((size_t)n + 1) * sizeof(uint32_t));
        node->keys = malloc(((size_t)n + 1) * sizeof(int64_t));
        if (!node->child || !node->keys) {
            die_errno("malloc(node)");
        }
        for (uint32_t c = 0; c < n; ++c) {
            uint16_t off = rd_be16(h + 12 + 2 * c);
            node->child[c] = rd_be32(buf + off);
            node->keys[c] = h[0] == 5 ? rd_varint(buf + off + 4) : 0;
        }
        node->child[n] = right;
        if (h[0] != 5) {          /* index pages: keep children, drop keys */
            node->n = n;
        }
        uint32_t first = n > 0 ? node->child[0] : right;
        if (first < 1 || first > np || !read_page_direct(fd, buf2, psz, first)) {
            why = "bad child pointer";
            goto done;
        }
        if (page_is_interior(buf2[0])) {   /* children are interior: walk them */
            for (uint32_t c = 0; c <= n; ++c) {
                uint32_t ch = node->child[c];
                if (ch >= 1 && ch <= np && sp < np) {
                    stack[sp++] = ch;
                }
            }
        }
    }
    for (uint32_t pg = 1; pg <= np; ++pg) {
        g_lm.n_layer[g_lm.layer[pg]]++;
    }
    if (g_lm.items_root != 0) {
        for (size_t i = 0; i < wl->count; ++i) {
            op_type_t t = wl->ops[i].type;
            if (t != OP_READ && t != OP_UPDATE && t != OP_READMODIFYWRITE) {
                continue;
            }
            int64_t key = wl->ops[i].target_id;
            uint32_t pg = g_lm.items_root;
            while (pg >= 1 && pg <= np && g_lm.layer[pg] != LAYER_LEAF) {
                const tbl_node_t *node = &g_lm.node[pg];
                g_lm.on_path[pg] = 1;
                uint32_t lo = 0, hi = node->n;       /* first c with key <= keys[c] */
                while (lo < hi) {
                    uint32_t mid = (lo + hi) / 2;
                    if (key <= node->keys[mid]) hi = mid; else lo = mid + 1;
                }
                pg = node->child[lo];
            }
            if (pg >= 1 && pg <= np) {
                g_lm.on_path[pg] = 2;
            }
        }
        for (uint32_t pg = 1; pg <= np; ++pg) {
            g_lm.n_path += g_lm.on_path[pg] == 1;
            g_lm.n_path_leaf += g_lm.on_path[pg] == 2;
        }
    }
    g_lm.ok = true;
done:
    if (st) sqlite3_finalize(st);
    if (db) sqlite3_close(db);
    if (fd >= 0) close(fd);
    free(buf);
    free(buf2);
    free(stack);
    if (g_lm.ok) {
        write_record_line(record,
                          "layer_map roots=%u interior=%u leaf=%u path_interior=%u path_leaf=%u "
                          "items_root=%u (page 1 counts as leaf; path_* = union over the workload)\n",
                          g_lm.n_layer[LAYER_ROOT], g_lm.n_layer[LAYER_INTERIOR],
                          g_lm.n_layer[LAYER_LEAF], g_lm.n_path, g_lm.n_path_leaf, g_lm.items_root);
    } else {
        emit_line(record, "layer_map unavailable: %s\n", why ? why : "?");
    }
}

/* Path of one rowid in the items table: last interior page and leaf. */
static void lm_probe_path(int64_t key, uint32_t *l2, uint32_t *leaf) {
    *l2 = *leaf = 0;
    uint32_t pg = g_lm.items_root;
    while (g_lm.ok && pg >= 1 && pg <= g_lm.npages && g_lm.layer[pg] != LAYER_LEAF) {
        const tbl_node_t *node = &g_lm.node[pg];
        uint32_t lo = 0, hi = node->n;
        while (lo < hi) {
            uint32_t mid = (lo + hi) / 2;
            if (key <= node->keys[mid]) hi = mid; else lo = mid + 1;
        }
        *l2 = pg;
        pg = node->child[lo];
    }
    *leaf = pg;
}

/* Residency of the R1b hot competitor's file, mapped read-only by the parent. */
static void *g_hot_map;
static size_t g_hot_bytes;

/* OS page-cache residency per layer (mincore through the harness's own mapping,
 * which exists in every mode, independent of PRAGMA mmap_size). */
static void report_layers(const mapped_db_t *dbmap, const char *point, FILE *record) {
    if (!g_lm.ok) {
        return;
    }
    unsigned char *vec = calloc(dbmap->os_page_count, 1);
    if (vec == NULL) {
        die_errno("calloc");
    }
    fill_mincore_vec(dbmap, vec);
    uint32_t res[3] = {0, 0, 0}, path_res = 0, path_leaf_res = 0;
    for (uint32_t pg = 1; pg <= g_lm.npages; ++pg) {
        uint64_t b = (uint64_t)(pg - 1) * dbmap->sqlite_page_size;
        uint64_t e = b + dbmap->sqlite_page_size;
        bool resident = true;
        for (size_t o = (size_t)(b / dbmap->os_page_size);
             o <= (size_t)((e - 1) / dbmap->os_page_size); ++o) {
            if ((vec[o] & 1U) == 0) { resident = false; break; }
        }
        if (resident) {
            res[g_lm.layer[pg]]++;
            path_res += g_lm.on_path[pg] == 1;
            path_leaf_res += g_lm.on_path[pg] == 2;
        }
    }
    free(vec);
    char hot[64] = "";
    if (g_hot_map != NULL) {
        size_t hp = g_hot_bytes / 4096, hr = 0;
        unsigned char *hv = calloc(hp, 1);
        if (hv != NULL && mincore(g_hot_map, g_hot_bytes, hv) == 0) {
            for (size_t i = 0; i < hp; ++i) hr += hv[i] & 1U;
            snprintf(hot, sizeof(hot), " hot_file=%zu/%zu", hr, hp);
        }
        free(hv);
    }
    emit_line(record,
              "layer_residency point=%s source=mincore root=%u/%u interior=%u/%u "
              "path_interior=%u/%u leaf=%u/%u path_leaf=%u/%u%s\n",
              point, res[LAYER_ROOT], g_lm.n_layer[LAYER_ROOT],
              res[LAYER_INTERIOR], g_lm.n_layer[LAYER_INTERIOR],
              path_res, g_lm.n_path, res[LAYER_LEAF], g_lm.n_layer[LAYER_LEAF],
              path_leaf_res, g_lm.n_path_leaf, hot);
}

/* ---- memory.stat of this process's cgroup, one CSV row per checkpoint ---- */

static char g_cg_dir[1024];
static FILE *g_memstat_csv;

static bool cgroup_dir(void) {
    if (g_cg_dir[0]) {
        return true;
    }
    FILE *f = fopen("/proc/self/cgroup", "r");
    char line[1024];
    while (f && fgets(line, sizeof(line), f)) {
        if (strncmp(line, "0::", 3) == 0) {
            line[strcspn(line, "\n")] = '\0';
            snprintf(g_cg_dir, sizeof(g_cg_dir), "/sys/fs/cgroup%s", line + 3);
        }
    }
    if (f) fclose(f);
    return g_cg_dir[0] != '\0';
}

static long long cg_read_ll(const char *name) {   /* -1: missing; "max" -> -2 */
    char path[1200], v[64];
    snprintf(path, sizeof(path), "%s/%s", g_cg_dir, name);
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    long long r = -1;
    if (fgets(v, sizeof(v), f)) r = strncmp(v, "max", 3) == 0 ? -2 : atoll(v);
    fclose(f);
    return r;
}

static bool cg_write(const char *name, long long value) {
    char path[1200];
    snprintf(path, sizeof(path), "%s/%s", g_cg_dir, name);
    FILE *f = fopen(path, "w");
    if (!f) return false;
    bool ok = fprintf(f, "%lld\n", value) > 0;
    return fclose(f) == 0 && ok;
}

static long long kv_lookup(const char *buf, const char *key) {
    size_t kl = strlen(key);
    for (const char *p = buf; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
        if (strncmp(p, key, kl) == 0 && p[kl] == ' ') return atoll(p + kl + 1);
    }
    return -1;
}

static void cg_read_text(const char *name, char *buf, size_t n) {
    char path[1200];
    snprintf(path, sizeof(path), "%s/%s", g_cg_dir, name);
    buf[0] = '\0';
    FILE *f = fopen(path, "r");
    if (!f) return;
    size_t got = fread(buf, 1, n - 1, f);
    buf[got] = '\0';
    fclose(f);
}

static void memstat_open(const char *record_path) {
    char path[4200];
    snprintf(path, sizeof(path), "%s", record_path);
    char *dot = strrchr(path, '.');
    if (dot && strcmp(dot, ".log") == 0) *dot = '\0';
    strncat(path, ".memstat.csv", sizeof(path) - strlen(path) - 1);
    g_memstat_csv = fopen(path, "w");
    if (g_memstat_csv) {
        fprintf(g_memstat_csv, "point,cgroup,file_bytes,file_pages,file_mapped,active_file,"
                "inactive_file,anon,workingset_refault_file,workingset_activate_file,"
                "pgscan,pgsteal,memory_current,memory_max,events_high,events_max,oom,oom_kill\n");
    }
}

static long long g_last_file_bytes = -1;

static void record_memstat(const char *point, FILE *record) {
    if (!cgroup_dir()) {
        emit_line(record, "memstat point=%s unavailable (no cgroup v2)\n", point);
        return;
    }
    static char st[16384], ev[1024];
    cg_read_text("memory.stat", st, sizeof(st));
    cg_read_text("memory.events", ev, sizeof(ev));
    long long file = kv_lookup(st, "file");
    g_last_file_bytes = file;
    long long cur = cg_read_ll("memory.current"), max = cg_read_ll("memory.max");
    long long oom = kv_lookup(ev, "oom"), oom_kill = kv_lookup(ev, "oom_kill");
    long long ev_high = kv_lookup(ev, "high"), ev_max = kv_lookup(ev, "max");
    if (g_memstat_csv) {
        fprintf(g_memstat_csv, "%s,%s,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld\n",
                point, g_cg_dir, file, file >= 0 ? file / 4096 : -1, kv_lookup(st, "file_mapped"),
                kv_lookup(st, "active_file"), kv_lookup(st, "inactive_file"), kv_lookup(st, "anon"),
                kv_lookup(st, "workingset_refault_file"), kv_lookup(st, "workingset_activate_file"),
                kv_lookup(st, "pgscan"), kv_lookup(st, "pgsteal"), cur, max, ev_high, ev_max, oom, oom_kill);
        fflush(g_memstat_csv);
    }
    write_record_line(record, "memstat point=%s file_pages=%lld anon=%lld memory_current=%lld "
                              "memory_max=%lld events_high=%lld events_max=%lld oom_kill=%lld\n",
                      point, file >= 0 ? file / 4096 : -1, kv_lookup(st, "anon"), cur, max,
                      ev_high, ev_max, oom_kill);
}

/* ---- pager mode: a VFS shim that counts whole-page reads of the main DB per layer ---- */

enum { RD_LEAF = 0, RD_ROOT = 1, RD_INTERIOR = 2, RD_UNMAPPED, RD_PARTIAL, RD_PATH, RD_PAGE1, RD_N };

typedef struct {
    sqlite3_file base;
    sqlite3_file *real;
    int main_db;
} cnt_file_t;

static sqlite3_vfs g_cnt_vfs;
static sqlite3_vfs *g_real_vfs;
static sqlite3_io_methods g_cnt_io;
static size_t g_cnt_psz;
static uint64_t g_rd[RD_N];

#define REAL(f) (((cnt_file_t *)(f))->real)

static int cntClose(sqlite3_file *f) { return REAL(f)->pMethods->xClose(REAL(f)); }
static int cntRead(sqlite3_file *f, void *b, int n, sqlite3_int64 off) {
    cnt_file_t *p = (cnt_file_t *)f;
    if (p->main_db) {
        if ((size_t)n == g_cnt_psz && off % (sqlite3_int64)g_cnt_psz == 0) {
            uint32_t pg = (uint32_t)(off / (sqlite3_int64)g_cnt_psz) + 1;
            if (pg == 1) {
                g_rd[RD_PAGE1]++;   /* page 1 is its own entry in R1a's per-row check */
            } else if (g_lm.ok && pg <= g_lm.npages) {
                g_rd[g_lm.layer[pg]]++;
                g_rd[RD_PATH] += g_lm.on_path[pg] == 1;
            } else {
                g_rd[RD_UNMAPPED]++;
            }
        } else {
            g_rd[RD_PARTIAL]++;   /* e.g. the 16-byte change-counter read at offset 24 */
        }
    }
    return p->real->pMethods->xRead(p->real, b, n, off);
}
static int cntWrite(sqlite3_file *f, const void *b, int n, sqlite3_int64 o) { return REAL(f)->pMethods->xWrite(REAL(f), b, n, o); }
static int cntTruncate(sqlite3_file *f, sqlite3_int64 s) { return REAL(f)->pMethods->xTruncate(REAL(f), s); }
static int cntSync(sqlite3_file *f, int fl) { return REAL(f)->pMethods->xSync(REAL(f), fl); }
static int cntFileSize(sqlite3_file *f, sqlite3_int64 *s) { return REAL(f)->pMethods->xFileSize(REAL(f), s); }
static int cntLock(sqlite3_file *f, int l) { return REAL(f)->pMethods->xLock(REAL(f), l); }
static int cntUnlock(sqlite3_file *f, int l) { return REAL(f)->pMethods->xUnlock(REAL(f), l); }
static int cntCheckReservedLock(sqlite3_file *f, int *r) { return REAL(f)->pMethods->xCheckReservedLock(REAL(f), r); }
static int cntFileControl(sqlite3_file *f, int op, void *a) { return REAL(f)->pMethods->xFileControl(REAL(f), op, a); }
static int cntSectorSize(sqlite3_file *f) { return REAL(f)->pMethods->xSectorSize(REAL(f)); }
static int cntDeviceCharacteristics(sqlite3_file *f) { return REAL(f)->pMethods->xDeviceCharacteristics(REAL(f)); }
static int cntShmMap(sqlite3_file *f, int i, int sz, int ex, void volatile **pp) { return REAL(f)->pMethods->xShmMap(REAL(f), i, sz, ex, pp); }
static int cntShmLock(sqlite3_file *f, int o, int n, int fl) { return REAL(f)->pMethods->xShmLock(REAL(f), o, n, fl); }
static void cntShmBarrier(sqlite3_file *f) { REAL(f)->pMethods->xShmBarrier(REAL(f)); }
static int cntShmUnmap(sqlite3_file *f, int d) { return REAL(f)->pMethods->xShmUnmap(REAL(f), d); }
static int cntFetch(sqlite3_file *f, sqlite3_int64 o, int n, void **pp) { return REAL(f)->pMethods->xFetch(REAL(f), o, n, pp); }
static int cntUnfetch(sqlite3_file *f, sqlite3_int64 o, void *p) { return REAL(f)->pMethods->xUnfetch(REAL(f), o, p); }

static int cntOpen(sqlite3_vfs *vfs, const char *name, sqlite3_file *f, int flags, int *out) {
    (void)vfs;
    cnt_file_t *p = (cnt_file_t *)f;
    p->real = (sqlite3_file *)&p[1];
    p->main_db = (flags & SQLITE_OPEN_MAIN_DB) != 0;
    int rc = g_real_vfs->xOpen(g_real_vfs, name, p->real, flags, out);
    if (p->real->pMethods) {
        g_cnt_io.iVersion = p->real->pMethods->iVersion;
        p->base.pMethods = &g_cnt_io;
    } else {
        p->base.pMethods = NULL;
    }
    return rc;
}
static int cntDelete(sqlite3_vfs *v, const char *z, int s) { (void)v; return g_real_vfs->xDelete(g_real_vfs, z, s); }
static int cntAccess(sqlite3_vfs *v, const char *z, int fl, int *r) { (void)v; return g_real_vfs->xAccess(g_real_vfs, z, fl, r); }
static int cntFullPathname(sqlite3_vfs *v, const char *z, int n, char *o) { (void)v; return g_real_vfs->xFullPathname(g_real_vfs, z, n, o); }

static void count_vfs_register(size_t page_size) {
    g_real_vfs = sqlite3_vfs_find(NULL);
    if (g_real_vfs == NULL) {
        fprintf(stderr, "error: no default SQLite VFS\n");
        exit(1);
    }
    g_cnt_psz = page_size;
    g_cnt_vfs = *g_real_vfs;
    g_cnt_vfs.zName = "count";
    g_cnt_vfs.pNext = NULL;
    g_cnt_vfs.szOsFile = (int)sizeof(cnt_file_t) + g_real_vfs->szOsFile;
    g_cnt_vfs.xOpen = cntOpen;
    g_cnt_vfs.xDelete = cntDelete;
    g_cnt_vfs.xAccess = cntAccess;
    g_cnt_vfs.xFullPathname = cntFullPathname;
    g_cnt_io = (sqlite3_io_methods){
        3, cntClose, cntRead, cntWrite, cntTruncate, cntSync, cntFileSize, cntLock, cntUnlock,
        cntCheckReservedLock, cntFileControl, cntSectorSize, cntDeviceCharacteristics,
        cntShmMap, cntShmLock, cntShmBarrier, cntShmUnmap, cntFetch, cntUnfetch};
    if (sqlite3_vfs_register(&g_cnt_vfs, 0) != SQLITE_OK) {
        fprintf(stderr, "error: sqlite3_vfs_register(count) failed\n");
        exit(1);
    }
}

typedef struct {
    uint64_t rd[RD_N];
    int cache_hit, cache_miss;
} pager_snap_t;

static sqlite3 *g_probe_db;
static pager_snap_t g_probe_before, g_probe_after;
static bool g_probe_taken;

static void pager_snapshot(pager_snap_t *s) {
    int hw;
    memcpy(s->rd, g_rd, sizeof(g_rd));
    sqlite3_db_status(g_probe_db, SQLITE_DBSTATUS_CACHE_HIT, &s->cache_hit, &hw, 0);
    sqlite3_db_status(g_probe_db, SQLITE_DBSTATUS_CACHE_MISS, &s->cache_miss, &hw, 0);
}

static void probe_after_first_op(void) {
    pager_snapshot(&g_probe_after);
    g_probe_taken = true;
}

/* ---- R1b competitors: forked children driven by a shared state word ---- */

enum { COMP_IDLE = 0, COMP_ACTIVE = 1, COMP_EXIT = 2 };
static volatile int *g_comp_state;
static pid_t g_comp_pid[2];
static int g_ncomp;

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static void sleep_s(double s) {
    if (s <= 0) return;
    struct timespec ts = {(time_t)s, (long)((s - (double)(time_t)s) * 1e9)};
    while (nanosleep(&ts, &ts) != 0 && errno == EINTR) {}
}

static void comp_wait_for(int want) {
    while (*g_comp_state != want && *g_comp_state != COMP_EXIT) sleep_s(0.005);
    if (*g_comp_state == COMP_EXIT) _exit(0);
}

/* Grow anonymous memory to `target` bytes at `rate` MiB/s during the first idle,
 * then hold it untouched until the run ends (swap=0: a fixed budget cut). */
static void anon_competitor(size_t target, double rate_mibps) {
    comp_wait_for(COMP_ACTIVE);
    const size_t chunk = (size_t)1 << 20;
    double t0 = now_s();
    for (size_t done = 0; done < target; done += chunk) {
        char *b = malloc(chunk);
        if (b == NULL) _exit(3);
        memset(b, 0xA5, chunk);
        sleep_s(t0 + (double)(done + chunk) / (rate_mibps * 1048576.0) - now_s());
    }
    while (*g_comp_state != COMP_EXIT) sleep_s(0.05);
    _exit(0);
}

/* Read `per_idle` bytes of a scratch file with read(), paced over each active window. */
static void stream_competitor(const char *path, size_t per_idle, double active_s) {
    int fd = open(path, O_RDONLY);
    struct stat sb;
    if (fd < 0 || fstat(fd, &sb) != 0 || sb.st_size <= 0) _exit(4);
    char *b = malloc((size_t)1 << 20);
    if (b == NULL) _exit(3);
    off_t off = 0;
    for (;;) {
        comp_wait_for(COMP_ACTIVE);
        double t0 = now_s();
        for (size_t done = 0; done < per_idle && *g_comp_state == COMP_ACTIVE;) {
            size_t want = per_idle - done < ((size_t)1 << 20) ? per_idle - done : ((size_t)1 << 20);
            if (off >= sb.st_size) off = 0;
            ssize_t got = pread(fd, b, want, off);
            if (got <= 0) { off = 0; continue; }
            off += got;
            done += (size_t)got;
            sleep_s(t0 + active_s * (double)done / (double)per_idle - now_s());
        }
        comp_wait_for(COMP_IDLE);
    }
}

/* mmap a scratch file and touch random pages at `pps` pages/s while active. */
static void hot_competitor(const char *path, size_t bytes, double pps) {
    int fd = open(path, O_RDONLY);
    struct stat sb;
    if (fd < 0 || fstat(fd, &sb) != 0 || (size_t)sb.st_size < bytes) _exit(4);
    volatile uint8_t *m = mmap(NULL, bytes, PROT_READ, MAP_SHARED, fd, 0);
    if (m == MAP_FAILED) _exit(5);
    size_t npg = bytes / 4096;
    uint64_t x = 88172645463325252ULL;
    double carry = 0;
    for (;;) {
        comp_wait_for(COMP_ACTIVE);
        while (*g_comp_state == COMP_ACTIVE) {
            carry += pps / 100.0;
            for (; carry >= 1.0; carry -= 1.0) {
                x ^= x << 13; x ^= x >> 7; x ^= x << 17;
                (void)m[(x % npg) * 4096];
            }
            sleep_s(0.01);
        }
    }
}

static void record_cpus(const char *who, pid_t pid, FILE *record) {
    char path[64], line[256];
    snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid);
    FILE *f = fopen(path, "r");
    while (f && fgets(line, sizeof(line), f)) {
        if (strncmp(line, "Cpus_allowed_list:", 18) == 0) {
            line[strcspn(line, "\n")] = '\0';
            write_record_line(record, "cpus who=%s pid=%ld allowed=%s\n", who, (long)pid, line + 18 + strspn(line + 18, " \t"));
        }
    }
    if (f) fclose(f);
}

static pid_t spawn_competitor(int cpu, int kind, const options_t *o, size_t db_size) {
    pid_t pid = fork();
    if (pid < 0) die_errno("fork(competitor)");
    if (pid > 0) return pid;
    pin_to_cpu(cpu);
    char path[4096];
    double r = o->pressure_ratio;
    if (kind == 0) {
        anon_competitor((size_t)((1.0 - r) * (double)db_size) + ((size_t)16 << 20), o->anon_rate_mibps);
    } else if (kind == 1) {
        snprintf(path, sizeof(path), "%s/stream.bin", o->scratch_dir);
        stream_competitor(path, (size_t)(o->stream_turnover * r * (double)db_size),
                          o->idle_s - o->quiesce_s);
    } else {
        snprintf(path, sizeof(path), "%s/hot.bin", o->scratch_dir);
        hot_competitor(path, (size_t)(o->hot_ratio * (double)db_size) / 4096 * 4096, o->hot_pages_per_s);
    }
    _exit(0);
}

static void competitors_stop(void) {
    if (g_comp_state == NULL) return;
    *g_comp_state = COMP_EXIT;
    for (int i = 0; i < g_ncomp; ++i) {
        int st;
        waitpid(g_comp_pid[i], &st, 0);
    }
    g_ncomp = 0;
}

/* --reset cgroup-pressure (prereg R1b). Returns the index of the probe op. */
static size_t cgroup_pressure_reset(const options_t *o, const mapped_db_t *dbmap,
                                    sqlite_ctx_t *ctx, const workload_t *wl,
                                    FILE *record, FILE *devnull) {
    const long long S = (long long)dbmap->file_size;
    const bool limited = o->pressure_ratio >= 0;
    const size_t K = o->invocations, Q = o->ops_per_invocation;

    if (!cgroup_dir() || cg_read_ll("memory.max") == -1) {
        fprintf(stderr, "error: --reset cgroup-pressure needs a cgroup v2 memory controller "
                        "(run under: systemd-run --user --scope -p MemorySwapMax=0 --)\n");
        exit(1);
    }
    if (o->drop_caches_script == NULL) {
        fprintf(stderr, "error: --reset cgroup-pressure needs --drop-caches-script for the setup drop\n");
        exit(1);
    }
    if (limited && o->competitor != COMPETITOR_NONE && o->scratch_dir == NULL) {
        fprintf(stderr, "error: --competitor stream|hot needs --scratch-dir\n");
        exit(1);
    }
    if (K * Q >= wl->count) {
        fprintf(stderr, "error: invocations * ops-per-invocation exceeds the workload\n");
        exit(1);
    }
    write_record_line(record, "cgroup_pressure ratio=%s%.3f competitor=%s K=%zu Q=%zu idle_s=%.1f "
                              "quiesce_s=%.1f anon_rate_mibps=%.1f stream_turnover=%.2f hot_ratio=%.2f "
                              "hot_pages_per_s=%.0f cgroup=%s\n",
                      limited ? "" : "inf/", limited ? o->pressure_ratio : 0.0,
                      o->competitor == COMPETITOR_STREAM ? "stream" :
                      o->competitor == COMPETITOR_HOT ? "hot" : "none",
                      K, Q, o->idle_s, o->quiesce_s, o->anon_rate_mibps, o->stream_turnover,
                      o->hot_ratio, o->hot_pages_per_s, g_cg_dir);

    /* setup only: uncharge any DB page another cgroup holds, so init charges them here */
    run_helper_script(o->drop_caches_script, "setup_drop_caches", o->debug, record);

    if (limited) {
        g_comp_state = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
        if (g_comp_state == MAP_FAILED) die_errno("mmap(competitor state)");
        *g_comp_state = COMP_IDLE;
        fflush(record);
        fflush(stdout);
        fflush(stderr);
        g_comp_pid[g_ncomp++] = spawn_competitor(o->anon_cpu, 0, o, (size_t)S);
        if (o->competitor != COMPETITOR_NONE) {
            g_comp_pid[g_ncomp++] = spawn_competitor(o->competitor_cpu,
                                                     o->competitor == COMPETITOR_STREAM ? 1 : 2, o, (size_t)S);
        }
        sleep_s(0.2);
        record_cpus("anon", g_comp_pid[0], record);
        if (g_ncomp > 1) {
            record_cpus(o->competitor == COMPETITOR_STREAM ? "stream" : "hot", g_comp_pid[1], record);
        }
        if (o->competitor == COMPETITOR_HOT) {   /* parent mapping, only for mincore */
            char hp[4096];
            snprintf(hp, sizeof(hp), "%s/hot.bin", o->scratch_dir);
            int hfd = open(hp, O_RDONLY);
            g_hot_bytes = (size_t)(o->hot_ratio * (double)S) / 4096 * 4096;
            g_hot_map = hfd >= 0 ? mmap(NULL, g_hot_bytes, PROT_READ, MAP_SHARED, hfd, 0) : MAP_FAILED;
            if (g_hot_map == MAP_FAILED) g_hot_map = NULL;
            if (hfd >= 0) close(hfd);
        }
        long long base = cg_read_ll("memory.current");
        long long cap = base + S + (16LL << 20);
        cg_write("memory.swap.max", 0);
        if (!cg_write("memory.max", cap)) {
            competitors_stop();
            die_errno("write memory.max");
        }
        write_record_line(record, "cgroup_limits m_base=%lld memory_max=%lld file_budget=%lld anon_target=%lld\n",
                          base, cap, (long long)(o->pressure_ratio * (double)S),
                          (long long)((1.0 - o->pressure_ratio) * (double)S) + (16LL << 20));
    }
    record_memstat("m_base", record);
    report_layers(dbmap, "m_base", record);

    /* init: read the whole file once through the harness mapping (Lambda's first full read) */
    volatile uint8_t sink = 0;
    for (size_t off = 0; off < dbmap->file_size; off += dbmap->os_page_size) {
        sink ^= ((const volatile uint8_t *)dbmap->mapping)[off];
    }
    (void)sink;
    record_memstat("after-init", record);
    report_layers(dbmap, "after-init", record);
    emit_line(record, "cgroup_charge_check=%s file_bytes=%lld need=%lld\n",
              g_last_file_bytes >= (long long)(0.9 * (double)S) ? "pass" : "FAIL",
              g_last_file_bytes, (long long)(0.9 * (double)S));

    char point[32];
    for (size_t k = 0; k < K; ++k) {
        run_benchmark(ctx, wl, k * Q, Q, devnull);
        if (g_comp_state != NULL) {
            *g_comp_state = COMP_ACTIVE;
            sleep_s(o->idle_s - o->quiesce_s);
            *g_comp_state = COMP_IDLE;
            sleep_s(o->quiesce_s);
        } else {
            sleep_s(o->idle_s);
        }
        snprintf(point, sizeof(point), "idle-%zu", k + 1);
        record_memstat(point, record);
        report_layers(dbmap, point, record);
    }
    return K * Q;
}

/* --reset fresh-process: the measured query runs in a new process with a new
 * connection (empty pager); the OS page cache is left as the warm phase left it.
 * Returns only in the child; the parent exits with the child's status. */
static void fresh_process_fork(sqlite_ctx_t *ctx, const options_t *o, FILE *record, FILE *out) {
    fflush(record);
    fflush(out);
    fflush(stdout);
    fflush(stderr);
    if (g_memstat_csv) fflush(g_memstat_csv);
    pid_t pid = fork();
    if (pid < 0) die_errno("fork(fresh-process)");
    if (pid > 0) {
        int st;
        if (waitpid(pid, &st, 0) < 0) die_errno("waitpid");
        _exit(WIFEXITED(st) ? WEXITSTATUS(st) : 1);
    }
    /* child: abandon the parent's connection (never close it across fork) */
    memset(ctx, 0, sizeof(*ctx));
    sqlite_open_if_needed(ctx, o);
    sqlite_init_schema_if_needed(ctx);
    emit_line(record, "fresh_process child_pid=%ld: cold advice and drop script not applied, "
                      "page cache left as the warm phase left it\n", (long)getpid());
}

int main(int argc, char **argv) {
    options_t opts;
    sqlite_ctx_t sqlite_ctx;
    mapped_db_t dbmap;
    workload_t workload;
    benchmark_summary_t summary;
    FILE *record;
    FILE *out;
    char record_path[4096];
    char output_path[4096];

    parse_args(argc, argv, &opts);
    pin_to_cpu(opts.cpu);   /* pin before any measurement so spin + op[0] share one core */
    memset(&sqlite_ctx, 0, sizeof(sqlite_ctx));
    record = open_run_record(&opts, record_path, sizeof(record_path));

    workload = load_workload(opts.workload_path);
    /* F8: first_query_latency_us is only a clean TTFQ if op[0] is a read. */
    if (workload.count > 0 && workload.ops[0].type != OP_READ) {
        fprintf(stderr,
                "%s: workload op[0] is '%s', not 'read' -- first_query_latency_us is NOT a "
                "clean TTFQ (F8 violated)\n",
                opts.require_read_first ? "error" : "warning",
                op_type_name(workload.ops[0].type));
        if (opts.require_read_first) {
            exit(1);
        }
    }
    dbmap = map_db_file(opts.db_path);
    if (opts.mmap_size < 0) {          /* default sentinel: map the whole file */
        opts.mmap_size = (int64_t)dbmap.file_size;
    }
    const bool pager_mode = opts.mmap_size == 0;
    /* any new flag away from its default: R1 instrumentation may run around the reset */
    const bool r1_active = pager_mode || opts.cache_size != 0 || opts.pre_cold_ops > 0 ||
                           opts.measure_ops > 0 || opts.reset_mode != RESET_DROP_CACHES;
    if ((opts.pre_cold_ops > 0 || opts.reset_mode == RESET_CGROUP_PRESSURE) &&
        (opts.sqlite_open_timing == SQLITE_OPEN_AFTER_COLD ||
         opts.schema_init_timing == SCHEMA_INIT_AFTER_COLD)) {
        fprintf(stderr, "error: --pre-cold-ops and --reset cgroup-pressure warm the measuring "
                        "connection, so they need before-cold open and schema init\n");
        exit(1);
    }
    if (opts.idle_s < opts.quiesce_s) {
        fprintf(stderr, "error: --idle-s must be >= --quiesce-s\n");
        exit(1);
    }
    if (pager_mode) {
        count_vfs_register(dbmap.sqlite_page_size);
    }
    if (opts.reset_mode == RESET_CGROUP_PRESSURE && opts.pre_cold_ops > 0) {
        fprintf(stderr, "error: --pre-cold-ops does not apply to --reset cgroup-pressure "
                        "(its warm phase is --invocations x --ops-per-invocation)\n");
        exit(1);
    }
    if (opts.pre_cold_ops >= workload.count && workload.count > 0) {
        fprintf(stderr, "error: --pre-cold-ops must be below the workload length\n");
        exit(1);
    }
    FILE *devnull = fopen("/dev/null", "w");
    if (devnull == NULL) {
        die_errno("fopen(/dev/null)");
    }
    uint32_t *hotset_pages = NULL;
    size_t hotset_n = 0;
    if (opts.verify_hotset != NULL) {
        hotset_pages = load_hotset_pages(opts.verify_hotset, &hotset_n);
    }
    out = open_unique_output_csv(opts.output_csv, output_path,
                                 sizeof(output_path));

    if (opts.sqlite_open_timing == SQLITE_OPEN_BEFORE_COLD) {
        sqlite_open_if_needed(&sqlite_ctx, &opts);
    }
    if (opts.schema_init_timing == SCHEMA_INIT_BEFORE_COLD) {
        if (!sqlite_ctx.opened) {
            sqlite_open_if_needed(&sqlite_ctx, &opts);
        }
        sqlite_init_schema_if_needed(&sqlite_ctx);
    }

    write_record_line(record, "benchmark_harness run record\n");
    write_record_line(record, "record_path=%s\n", record_path);
    write_record_line(record, "db=%s\n", opts.db_path);
    write_record_line(record, "workload=%s\n", opts.workload_path);
    write_record_line(record, "output=%s\n", output_path);
    write_record_line(record, "cold_advice=%s\n",
                      cold_advice_name(opts.cold_advice));
    write_record_line(record, "drop_caches_script=%s\n",
                      opts.drop_caches_script != NULL ?
                      opts.drop_caches_script : "(none)");
    write_record_line(record, "post_cold_script=%s\n",
                      opts.post_cold_script != NULL ?
                      opts.post_cold_script : "(none)");
    write_record_line(record, "verify_hotset=%s\n",
                      opts.verify_hotset != NULL ?
                      opts.verify_hotset : "(none)");
    write_record_line(record, "sqlite_open_timing=%s\n",
                      opts.sqlite_open_timing == SQLITE_OPEN_BEFORE_COLD ?
                      "before-cold" : "after-cold");
    write_record_line(record, "schema_init_timing=%s\n",
                      opts.schema_init_timing == SCHEMA_INIT_BEFORE_COLD ?
                      "before-cold" : "after-cold");
    write_record_line(record,
                      "cache_size=%" PRId64 " reset=%s pre_cold_ops=%zu measure_ops=%zu "
                      "pager_mode=%d\n",
                      opts.cache_size, reset_mode_name(opts.reset_mode),
                      opts.pre_cold_ops, opts.measure_ops, pager_mode ? 1 : 0);
    write_record_line(record,
                      "file_size=%zu sqlite_page_size=%zu sqlite_pages=%" PRIu32
                      " mmap_size=%" PRId64 " workload_ops=%zu\n\n",
                      dbmap.file_size, dbmap.sqlite_page_size,
                      dbmap.sqlite_page_count, opts.mmap_size, workload.count);
    fprintf(stderr, "benchmark record: %s\n", record_path);

    if (opts.debug) {
        fprintf(stderr,
                "db=%s workload=%s file_size=%zu sqlite_page_size=%zu sqlite_pages=%" PRIu32
                " mmap_size=%" PRId64 " workload_ops=%zu output=%s\n",
                opts.db_path, opts.workload_path, dbmap.file_size,
                dbmap.sqlite_page_size, dbmap.sqlite_page_count, opts.mmap_size,
                workload.count, output_path);
        fprintf(stderr,
                "sqlite_open_timing=%s schema_init_timing=%s\n",
                opts.sqlite_open_timing == SQLITE_OPEN_BEFORE_COLD ? "before-cold" : "after-cold",
                opts.schema_init_timing == SCHEMA_INIT_BEFORE_COLD ? "before-cold" : "after-cold");
    }

    lm_build(opts.db_path, &dbmap, &workload, record);
    if (r1_active && !g_lm.ok) {   /* never emit layer counts that cannot be attributed */
        fprintf(stderr, "error: page layer map unavailable; R1 flags need it\n");
        exit(1);
    }
    record_cpus("harness", getpid(), record);
    memstat_open(record_path);
    record_memstat("start", record);
    report_layers(&dbmap, "start", record);

    size_t start = 0;
    if (opts.pre_cold_ops > 0) {        /* warm the measuring connection (R1a) */
        run_benchmark(&sqlite_ctx, &workload, 0, opts.pre_cold_ops, devnull);
        start = opts.pre_cold_ops;
        report_layers(&dbmap, "after-warmup", record);
    }

    size_t resident_before_cold = count_resident_sqlite_pages(&dbmap);
    emit_line(record, "resident SQLite pages before madvise: %zu/%" PRIu32 "\n",
              resident_before_cold, dbmap.sqlite_page_count);
    report_resident_sqlite_page_distribution(&dbmap, "before madvise", record,
                                             true);

    if (opts.reset_mode == RESET_DROP_CACHES) {
        sync_db_pages(&dbmap, opts.debug);
        apply_cold_advice(&dbmap, opts.cold_advice, opts.debug);
        run_helper_script(opts.drop_caches_script, "drop_caches_script",
                          opts.debug, record);
    } else if (opts.reset_mode == RESET_FRESH_PROCESS) {
        fresh_process_fork(&sqlite_ctx, &opts, record, out);
    } else {
        start = cgroup_pressure_reset(&opts, &dbmap, &sqlite_ctx, &workload, record, devnull);
    }
    /* (1) cold check: hotset should be ~0% resident now (after evict, pre-prefetch). */
    verify_hotset_residency(&dbmap, hotset_pages, hotset_n, "cold", record);
    /* R1 runs only: before the post-cold script, so delivery timing is untouched;
     * with every new flag at its default nothing is added after the reset. */
    if (r1_active) {
        report_layers(&dbmap, "after-reset", record);
        record_memstat("after-reset", record);
    }
    run_helper_script(opts.post_cold_script, "post_cold_script",
                      opts.debug, record);

    if (opts.sqlite_open_timing == SQLITE_OPEN_AFTER_COLD) {
        sqlite_close_ctx(&sqlite_ctx);
        memset(&sqlite_ctx, 0, sizeof(sqlite_ctx));
        sqlite_open_if_needed(&sqlite_ctx, &opts);
    }
    if (opts.schema_init_timing == SCHEMA_INIT_AFTER_COLD) {
        if (!sqlite_ctx.opened) {
            sqlite_open_if_needed(&sqlite_ctx, &opts);
        }
        sqlite_init_schema_if_needed(&sqlite_ctx);
    } else if (!sqlite_ctx.schema_initialized) {
        sqlite_init_schema_if_needed(&sqlite_ctx);
    }

    size_t resident_after_cold = count_resident_sqlite_pages(&dbmap);
    emit_line(record, "resident SQLite pages after madvise:  %zu/%" PRIu32 "\n",
              resident_after_cold, dbmap.sqlite_page_count);
    report_resident_sqlite_page_distribution(&dbmap, "after madvise", record,
                                             true);

    /* (2) delivery check: hotset residency immediately before the first query
     * (~us mincore, so async readahead gets no meaningful extra time to land). */
    verify_hotset_residency(&dbmap, hotset_pages, hotset_n, "delivery", record);

    if (start > 0 && workload.ops[start].type != OP_READ) {   /* F8 on the probe op */
        fprintf(stderr, "%s: probe op[%zu] is '%s', not 'read' -- first_query_latency_us is NOT a "
                        "clean TTFQ (F8 violated)\n", opts.require_read_first ? "error" : "warning",
                start, op_type_name(workload.ops[start].type));
        if (opts.require_read_first) {
            exit(1);
        }
    }
    if (pager_mode) {                   /* per-layer pager misses of the probe op */
        g_probe_db = sqlite_ctx.db;
        pager_snapshot(&g_probe_before);
        g_after_first_op = probe_after_first_op;
    }

    spin_warm_cpu(opts.warm_cpu_ms);   /* ramp the pinned core to max freq before op[0] */

    size_t count = workload.count - start;
    if (opts.measure_ops > 0 && opts.measure_ops < count) {
        count = opts.measure_ops;
    }
    write_csv_header(out);
    summary = run_benchmark(&sqlite_ctx, &workload, start, count, out);

    fclose(out);

    emit_line(record,
              "ops=%zu avg_latency_us=%.2f total_majflt=%ld total_minflt=%ld "
              "first_query_latency_us=%.2f\n",
              count,
              (double)summary.total_ns / (double)count / 1000.0,
              summary.total_majflt, summary.total_minflt,
              (double)summary.first_query_ns / 1000.0);

    size_t resident_after_run = count_resident_sqlite_pages(&dbmap);
    emit_line(record, "resident SQLite pages after run:      %zu/%" PRIu32 "\n",
              resident_after_run, dbmap.sqlite_page_count);
    report_resident_sqlite_page_distribution(&dbmap, "after run", record,
                                             false);

    report_layers(&dbmap, "after-run", record);
    record_memstat("after-run", record);
    if (pager_mode && g_probe_taken) {
        const uint64_t *a = g_probe_after.rd, *b = g_probe_before.rd;
        uint32_t pl2, pleaf;
        lm_probe_path(workload.ops[start].target_id, &pl2, &pleaf);
        emit_line(record,
                  "pager_probe op=%zu key=%" PRIu32 " probe_l2=%u probe_leaf=%u page1_reads=%" PRIu64
                  " source=vfs+db_status root_reads=%" PRIu64
                  " interior_reads=%" PRIu64 " path_interior_reads=%" PRIu64
                  " leaf_reads=%" PRIu64 " unmapped_reads=%" PRIu64 " partial_reads=%" PRIu64
                  " cache_hit=%d cache_miss=%d\n",
                  start, workload.ops[start].target_id, pl2, pleaf, a[RD_PAGE1] - b[RD_PAGE1],
                  a[RD_ROOT] - b[RD_ROOT], a[RD_INTERIOR] - b[RD_INTERIOR],
                  a[RD_PATH] - b[RD_PATH], a[RD_LEAF] - b[RD_LEAF],
                  a[RD_UNMAPPED] - b[RD_UNMAPPED], a[RD_PARTIAL] - b[RD_PARTIAL],
                  g_probe_after.cache_hit - g_probe_before.cache_hit,
                  g_probe_after.cache_miss - g_probe_before.cache_miss);
    }
    competitors_stop();
    if (g_hot_map != NULL) munmap(g_hot_map, g_hot_bytes);
    if (g_memstat_csv) fclose(g_memstat_csv);
    fclose(devnull);

    sqlite_close_ctx(&sqlite_ctx);
    unmap_db_file(&dbmap);
    free_workload(&workload);
    free(hotset_pages);
    fclose(record);
    return 0;
}
