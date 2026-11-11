# T210 VLDB revision

Goal: answer the 5 points in the T210 review (cos/briefings/2026-11-05-sqlite-paper-vldb-review/).

## Measurement protocol (do not change)

- Paired baseline, 10 workload instances, bootstrap CI, pre-registered margin.
- Every benchmark runs through scripts/bench_lock.sh (flock). Never run two at once.
- Results are append-only: results/<date>-<git-sha>-<config-hash>/. Never overwrite or delete.

## Integrity

- Before a new experiment, write prereg/<id>.md (hypothesis, metric, margin, decision rule) and commit it.
- Never edit a committed prereg file; add a new one with the reason.
- Report every outcome, including null and negative ones.
- Numbers in main.tex come only from generated macro files. Never type a number by hand.
- Log non-trivial decisions with /pstack:show-me-your-work.

## Safety

- Ask before any AWS deploy, any command that costs money, and any git push.
- Do not run heavy builds or parallel agents while a benchmark is running.
