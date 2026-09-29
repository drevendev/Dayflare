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

## 2026-09-26 — D03 continuity refinement and reconciliation

- Clarified that `(project, page_id)` is the identity of an extant local page and that
  delete/restore or delete/recreate gaps are explicit continuity boundaries, not
  rename-equivalent events.
- Required continuity across deletion gaps to remain `confirmed`, `ambiguous`, or
  `discontinuous` according to observed evidence; title equality never proves it.
- Reconciled the manifest, state/queue, research registry, and source register so D03
  is consistently recorded as DECIDED with durable primary-source provenance.


## 2026-09-27 — D03 integration/provenance repair

- Added the indexed research-artifact provenance header to
  `research/D03_IDENTITY_MODEL.md`, anchored to the first D03 artifact commit time.
- Refreshed `DEFAULT_BRANCH_BASE` to the current default-branch head
  `555268a49b82960c31e15b0758ef4c5402147374` and advanced state revision 3 -> 4.
- This is a control/provenance repair only; it does not change the accepted D03 identity
  semantics or promote any other research question.

## 2026-09-27 — D03 evidence-contract repair

- Added addressable `F-D03-001` through `F-D03-009` findings with explicit
  `Established`, `Reasoned`, and `Unknown` evidence classes.
- Added `D-D03-001` and linked the accepted layered identity decision to its supporting
  findings.
- Recorded the current MediaWiki deletion/restoration documentation conflict instead of
  silently choosing one source: `Help:Page_ID` / `Manual:Page_table` describe an
  attempt to reclaim the historical ID, while `Manual:Page_undeletion` describes a
  newly created page row/ID.
- The repair does not change the accepted D03 product semantics: delete/restore remains
  an explicit continuity boundary until event-specific evidence establishes continuity.
