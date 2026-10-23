# Dayflare Project Manifest

## Identity and canonical scope

- Project: Dayflare, repository `drevendev/Dayflare`.
- Canonical project state: repository-canonical; native GitHub objects own PR/check/merge facts.
- Operating-model source: `drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10`, read-only.
- Current profile: ENGINEERING, bounded by [D08](../research/D08_DESCRIPTIVE_DELIVERY.md).
- Initial product anchor: issue #1; one roadmap: [STATE_AND_QUEUE.md](STATE_AND_QUEUE.md).

## Goal and architecture

Build a broadly useful visual atlas of changing attention in English and Russian
Wikipedia. The journey is overview -> discover a measured change -> topic history
and evidence -> compare -> share. Culture, books, games, science and sport belong
in scope; neither AI news nor games alone define the product.

`scheduled CI -> collect -> validate -> calculate -> versioned static artifacts -> GitHub Pages`

Routine work belongs in reproducible scripts, not per-visitor agents or paid
inference. Failed ingestion must preserve the last valid publication. The current
historical M0 and synthetic M1 preview do not themselves establish a live refresh.

## Authority

The owner authorizes end-to-end Dayflare delivery, subject to current provider
permissions. Verify the authenticated account and permissions before remote writes.
Use PRs and later-session exact-head acceptance. Other repositories are read-only
references, not mutation targets. No parallel Drive controls, new worker, hidden
credentials, protection bypass, paid infrastructure or undisclosed tracking.

## Measurement and source invariants

- Top-N absence is not zero; discovery and full-history retrieval differ.
- Compare equivalent filters and complete windows; unknown remains unavailable.
- Preserve missing history, tiny baselines, moves/redirects, automation and seasons.
- Stable local page IDs, not titles, define extant pages; delete/restore continuity
  requires evidence. Preserve observed/resolved/uncertain Wikidata mappings.
- Volume, absolute change, relative change and return-from-quiet remain distinct.
- Attention is not importance, approval, truth, people or causation. Compare editions,
  not countries/populations. Do not create political persuasion or actor rankings.
- Version method/meaning changes. API access does not license article text or images.
- Observation time, retrieval time and last successful publication are separate.

## Research and scoped engineering

D01 SATISFIED, D02 PARTIAL and D03 DECIDED retain their accepted provenance in
`research/REGISTRY.md`, D01/D02 runtime documents and `research/D03_IDENTITY_MODEL.md`.
The six-series 35-day sample is a bounded experiment, not validated lifecycle or
representative coverage. The retained historical capsule contains no stable page-ID
observations or original raw response bodies; do not silently stitch its titles.

The 2026-10-21 D08 decision in #9 comment 6309721214 is adopted and bounded in the
file-owned D08 decision after #17 source integration. Engineering is ready for the
descriptive historical journey and offline identity tools; D04/D06 research and
D05 public visual acceptance remain partially/openly bounded. D07 digest is deferred.
This transition does not freeze thresholds, declare public acceptance or erase research.

## Completion gates

A public milestone requires reproducible source-bound software/data, explicit source
rights and method versions, failure/stale handling, accessible mobile/keyboard/reduced
motion, exact values/evidence without visual inference, preserved last-valid publication,
consistency/simplicity review, consumer-perspective review and verified served revision.
A maintained public experience needs both useful behavior and presentable UI, not an
empty landing page or hidden scripts. Maintainer review is not an external consented pilot.

COMMITTED, PR_OPENED, MERGED, BUILT, DEPLOYED and LIVE_VERIFIED are distinct. No critical
blocker may be silently waived. Project completion, empty queues, outages or permission
failures never authorize stopping or replacing the permanent hourly worker.
