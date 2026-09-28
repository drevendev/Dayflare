# Dayflare State and Queue

STATE_REVISION: 3
PROJECT_STATUS: ACTIVE
PHASE: RESEARCH
PROFILE: RESEARCH
OPERATING_MODEL: drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10
DEFAULT_BRANCH_BASE: a0c75877c599bccd9dd8c45e530e78f4c0a75e4c
LAST_ORIENTED_AT: 2026-09-28
CURRENT_UNIT: NONE
CURRENT_UNIT_STATUS: IDLE

## Durable evidence already reconciled

### D01

Status: OPEN / BLOCKED ON TARGET-RUNTIME PROBE

Durable source:
https://github.com/drevendev/Dayflare/issues/1#issuecomment-5815917784

Observed result: the earlier chat execution surfaces did not produce a Wikimedia data
sample. This is an execution-surface limitation, not evidence of zero data.

Required next result: run a bounded reproducible probe on the intended GitHub
Actions/runtime path and record endpoint, parameters, retrieval/observation timestamps,
HTTP result, coverage, and SHA-256 for fixed English and Russian samples.

### D02

Status: PARTIAL

Durable source:
https://github.com/drevendev/Dayflare/issues/1#issuecomment-5816960976

Accepted structural decision for method v0:

- keep raw volume, absolute change, baseline-relative lift, and lifecycle state separate;
- do not freeze thresholds until a real mixed-topic D01 sample exists;
- incomplete windows are not silently completed with zeros;
- return-from-quiet is distinct from a first-time flare;
- seasonality remains explicit until a supported comparison rule exists.

### D03

Status: OPEN / NEEDS REVALIDATION

No D03 result is canonical on this branch's base revision. A separately reviewed D03
candidate may exist outside `master`; it is not treated as merged project state here.

### D04

Status: DECIDED / CONSUMER VALIDATION PENDING

Durable source: `research/D04_EXISTING_PRODUCT_REVIEW.md`.

Accepted decision: Dayflare must not claim charts, top lists, multilingual popularity,
redirect views, or shareable URLs as differentiation. The bounded product hypothesis is
lifecycle-state discovery relative to a topic's own history, with transparent identity
and evidence. Uniqueness/usefulness remains unproven until a consumer gate.

## Queue

1. D01 — create and run the smallest reproducible Wikimedia access probe on GitHub
   Actions/runtime infrastructure and persist request receipts.
2. D03 — revalidate the page/title/redirect/move/Wikidata identity model from primary
   evidence and persist a decision.
3. D02 — run method v0 against the real D01 sample and freeze or revise only the
   evidence-supported parameters.
4. D05 — specify overview/detail/compare/share behavior and accessibility constraints,
   making lifecycle-state discovery rather than a decorated top list the primary task.
5. D06 — verify current GitHub Actions/Pages limits and derive request/storage/retention
   budgets plus source-failure recovery.
6. D07 — define a publication-safe digest event/card schema without enabling delivery.
7. D08 — produce an ordered engineering-ready backlog, include the D04 consumer/usefulness
   gate, and decide profile transition.

## Standing review triggers

- Run separate consistency and simplicity reviews after 4-6 substantive production
  units.
- Run divergence review before freezing high-leverage methodology or architecture.
- Run a consumer-perspective review before declaring a public milestone complete.

## Blockers

No project-wide blocker. D01 remains specifically blocked until the intended runtime
executes a real source probe.
