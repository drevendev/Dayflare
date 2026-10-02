# Dayflare State and Queue

STATE_REVISION: 5
PROJECT_STATUS: ACTIVE
PHASE: RESEARCH
PROFILE: RESEARCH
OPERATING_MODEL: drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10
DEFAULT_BRANCH_BASE: 7859486199410e173b388b1b08caacefa6dfef95
LAST_ORIENTED_AT: 2026-09-30
CURRENT_UNIT: NONE
CURRENT_UNIT_STATUS: IDLE

## Durable evidence already reconciled

### D01

Status: SATISFIED / TARGET-RUNTIME ACCESS PROVEN

Durable source:
`research/D01_RUNTIME_PROBE.md`

Observed result: GitHub Actions successfully retrieved the fixed EN/RU Wikimedia
sample for 2026-09-01 through 2026-09-14. Six requested series returned HTTP 200,
all 84 requested daily observations were resolved, and the normalized sample checksum
and per-response checksums are preserved in the durable D01 receipt.

The reusable probe fails closed on structural or semantic mismatch. Missing dates are
normalized to documented omitted zeros only after the response passes series identity,
filter, timestamp, and view-count validation.

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

1. D02 — extend the real probe horizon to at least 35 complete days for method v0,
   then freeze or revise only evidence-supported parameters.
2. D04 — task-based comparison with Wikimedia Topviews/Pageviews and a small set of
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

No project-wide blocker. D02 thresholds remain deliberately unfrozen pending the
expanded real-data horizon and counterexample evaluation.
