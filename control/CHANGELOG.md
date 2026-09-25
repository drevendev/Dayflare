# Dayflare Changelog and Decisions

This file records changes to project meaning and canonical control state. Git history
records file edits; this log records why those edits matter.

## 2026-09-24 — Repository bootstrap

- Initial base commit `a0c75877c599bccd9dd8c45e530e78f4c0a75e4c` established
  `master` and a minimal README.
- No runtime, data collector, deployment, or validated coverage was claimed.

## 2026-09-24 — Canonical controls proposed

- Declared GitHub/repository state as the sole canonical mutable project state.
- Pinned the operating-model source to
  `drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10`.
- Adopted issue #1 plus its durable comments as bootstrap provenance rather than an
  equal mutable control plane.
- Reconciled D01 as OPEN and D02 as PARTIAL from their durable issue comments.
- Explicitly left D03 OPEN because no durable D03 result is present in GitHub.
- Declared D01 runtime verification the first queued production/research unit after
  these controls merge.

## 2026-09-25 — D03 identity model v0 decided

- Revalidated D03 from current MediaWiki, Wikimedia Analytics, and Wikidata primary
  documentation.
- Adopted `(project, page_id)` as local page identity; titles remain time-varying
  observations.
- Kept redirects as separate page identities plus explicit edges and prohibited
  silent redirect-view aggregation into targets.
- Introduced a Dayflare-owned stable `topic_id` and explicit non-1:1 mapping states.
- Required preservation of observed and currently resolved Wikidata identifiers.
- Recorded implementation tests for moves, redirects, identifier merges,
  missing/conflicting mappings, and broad/narrow cross-language cases.
