# OpenWhisk threats to validity (deployment complement)

Cold-page state was reset and validated before each measured invocation: the cold
gate confirmed zero resident database pages after reset (the page-cache-carryover
hypothesis was specifically investigated and **falsified**). Nevertheless, a
systematic short-lived execution/storage-state or order effect remained: within a
warm baseline-target pair, the first-executed arm exhibits materially larger
`first_query_us` than the second arm, independently of which strategy occupies each
position. The exact lower-level source of this effect was outside the scope of this
work and is **not** attributed to any specific hardware cause (it is not random
hardware fluctuation, and not an asserted NVMe/C-state/page-cache-carryover cause).

Because of this effect, **warm adjacent-pair latency ratios are not used as primary
strategy-performance estimates**, and the first-position ("first-arm") view is
reported only as a diagnostic, never as a deconfounded or corrected treatment
effect. The primary controlled performance and mechanism evidence for the project
remains the native/WK1 experiments.

This limitation is bounded. It does **not** invalidate:
- execution correctness (3600 invocations passed the frozen validity gates);
- plan identity (frozen per-seed delivery plans, SHA-bound to the manifest);
- footprint measurements (selected pages / bytes / interior / leaf composition);
- delivery-count / delivery-cost measurements (`deliver_us`, delivered pages);
- deployment feasibility (all nine strategy families executed in OpenWhisk).

It **does** restrict interpretation of warm paired first-query latency as a direct,
causal strategy effect. No stronger invalidation is claimed, and no stronger
preservation than the items above is claimed.

## Cross-workload portability campaign (second role)

A separate single-batch campaign (468 formal invocations / 234
baseline-target pairs across 5 representative workload families) tested
**cross-workload deployment portability**: whether the representative strategy
mechanisms execute correctly and bind to the right per-workload plan under the same
frozen validity gates. Two threats bound its interpretation:

- **The same order/state effect applies.** The portability campaign shares the warm
  handle mode and therefore the same positional effect. Its purpose is execution +
  correctness + plan/workload binding, **not** latency; portability warm timings are
  **not** used as a cross-workload speedup or ranking, and no portability latency
  claim is made.
- **Five families are representative, not exhaustive.** The workloads (YC, YCu,
  YCh01, C, C_hit) are chosen coverage points; portability is demonstrated **for
  these families**, not proven for every possible workload. Per-plan page-set +
  offset parity against the frozen keyed contract is what is established.

The portability campaign and the strategy-space campaign answer different questions
and are **never pooled** into a single effect. Native/WK1 remains the primary
controlled performance evidence for both.
