# Dayflare State and Queue

STATE_REVISION: 3
PROJECT_STATUS: ACTIVE
PHASE: RESEARCH
PROFILE: RESEARCH
OPERATING_MODEL: drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10
DEFAULT_BRANCH_BASE: a0c75877c599bccd9dd8c45e530e78f4c0a75e4c
LAST_ORIENTED_AT: 2026-09-25
CURRENT_UNIT: NONE
CURRENT_UNIT_STATUS: IDLE

## Durable evidence already reconciled

### D01

Status: OPEN / BLOCKED ON TARGET-RUNTIME PROBE

Durable source:
https://github.com/drevendev/Dayflare/issues/1#issuecomment-5815917784

Required next result: run a bounded reproducible probe on the intended GitHub
Actions/runtime path and record endpoint, parameters, retrieval/observation timestamps,
HTTP result, coverage, and SHA-256 for fixed English and Russian samples.

### D02

Status: PARTIAL

Durable source:
https://github.com/drevendev/Dayflare/issues/1#issuecomment-5816960976

Accepted structural decision: keep raw volume, absolute change, baseline-relative lift,
and lifecycle state separate; do not freeze thresholds until a real D01 sample exists.

### D03

Status: COMPLETE / IDENTITY MODEL v0 DECIDED

Durable artifact:
research/D03_IDENTITY_MODEL.md

Decision summary:
- local page identity is `(project, page_id)`, not title;
- titles are time-varying observations;
- redirects are separate identities plus explicit edges and are not silently
  aggregated into target pageviews;
- Dayflare owns a stable internal `topic_id`;
- Wikidata QIDs are mapping evidence with observed and resolved identifiers preserved;
- missing, ambiguous, broader/narrower, and other non-1:1 mappings remain explicit.

## Queue

1. D01 — create and run the smallest reproducible Wikimedia access probe on GitHub
   Actions/runtime infrastructure and persist request receipts.
2. D02 — run method v0 against the real D01 sample and freeze or revise only the
   evidence-supported parameters.
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
