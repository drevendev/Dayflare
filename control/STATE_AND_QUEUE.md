# Dayflare State and Queue

STATE_REVISION: 3
PROJECT_STATUS: ACTIVE
PHASE: RESEARCH
PROFILE: RESEARCH
OPERATING_MODEL: drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10
DEFAULT_BRANCH_BASE: a0c75877c599bccd9dd8c45e530e78f4c0a75e4c
LAST_ORIENTED_AT: 2026-09-26
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

Status: DECIDED

Durable source:
`research/D03_IDENTITY_MODEL.md`

Accepted identity decision:

- use `(project, page_id)` for an extant local page and preserve titles as observations;
- moves preserve local page identity; redirects remain separate identities plus edges;
- deletion/restore is a continuity boundary and is never stitched by title alone;
- use Dayflare-owned `topic_id` above local page identities;
- preserve observed/resolved Wikidata identifiers and explicit non-1:1 mapping states.

## Queue

1. D01 — create and run the smallest reproducible Wikimedia access probe on GitHub
   Actions/runtime infrastructure and persist request receipts.
2. D02 — after D01 succeeds, run method v0 against the real sample and freeze or revise
   only the evidence-supported parameters.
3. D04 — task-based comparison with Wikimedia Topviews/Pageviews and a small set of
   directly inspected alternatives.
4. D05 — specify overview/detail/compare/share behavior and accessibility constraints.
5. D06 — verify current GitHub Actions/Pages limits and derive request/storage/retention
   budgets plus source-failure recovery.
6. D07 — define a publication-safe digest event/card schema without enabling delivery.
7. D08 — produce an ordered engineering-ready backlog and decide profile transition.

## Standing review triggers

- Run separate consistency and simplicity reviews after 4-6 substantive production
  units.
- Run divergence review before freezing high-leverage methodology or architecture.
- Run a consumer-perspective review before declaring a public milestone complete.

## Blockers

No project-wide blocker. D01 remains specifically blocked until the intended runtime
executes a real source probe.
