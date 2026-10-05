# Pilot: what the profile-free whole-file delivery calls deliver (2026-10-05)

**Pilot for method choice, not a result batch.** It decides which whole-file baselines
unified_v7 measures for the TODO at `paper/main.tex` (readahead(2) and MAP_POPULATE). Its
call times are one machine state and are not quoted beside batch numbers; the delivered page
counts are what it establishes.

**Finding: one readahead(2) over the whole file delivers 32 pages, exactly like one
whole-file posix_fadvise(WILLNEED). It is not synchronous.** On Linux 6.17, readahead(2)
issues the same WILLNEED readahead, and that path caps one request at
max(read_ahead_kb, max_sectors_kb) = 128 KB = 32 pages, so the rest of the 103 MB request is
dropped while the call still succeeds. The only profile-free ways to deliver the whole file
are window-sized chunks (823 calls, about 12.5 ms to issue) or MAP_POPULATE (about 98 ms,
synchronous).

## Method

`tools/pilot_whole_file_delivery.c`, unprivileged. For each method, from a cold page cache
(`POSIX_FADV_DONTNEED`, verified empty with `mincore` before every trial), issue the call over
the whole reference database (`test.db`, 26,331 pages, the file every local batch uses), time
the call, then count resident pages with `mincore` immediately and after 10 ms, 100 ms and 1 s,
so an asynchronous call that keeps loading after it returns is not undercounted. Methods are
interleaved trial by trial. Ten trials, medians. `output.txt` is the run as recorded,
with the environment.

## Result (`output.txt`)

| method | call | resident at return | resident after 1 s |
|---|---|---|---|
| one `posix_fadvise(WILLNEED)`, whole file | 44 us | 0 | **32** |
| one `readahead(2)`, whole file | 51 us | 0 | **32** |
| `readahead(2)` in 32-page chunks (823 calls) | 14.4 ms | 25,424 (97%) | 26,331 |
| `posix_fadvise(WILLNEED)` in 32-page chunks | 12.6 ms | 22,064 (84%) | 26,331 |
| `mmap(MAP_SHARED \| MAP_POPULATE)` | 98.1 ms | 26,331 | 26,331 |

Two earlier runs (5 and 10 trials) gave the same page counts and call times within 3%.

At this size the chunked hints are asynchronous in name only: issuing 823 window-sized requests
fills the device queue, so most of the file is resident when the last call returns.

## What it decides for unified_v7

- readahead(2) gets no arm. The paper states that it shares the WILLNEED path and its 32-page
  cap, citing this pilot.
- Whole-file window-chunked delivery: a whole-file strategy (all 26,331 pages, no profile)
  under the existing `async_win` arm.
- MAP_POPULATE: a new warmer method and arm.
