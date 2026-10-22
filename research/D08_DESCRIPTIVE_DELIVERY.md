# D08 — bounded descriptive delivery readiness

Decision date: 2026-10-22. Scope: #9, with #19/#20 source adoption.
Provenance: issue #1; D08 decision in #9 comment 6309721214; merged #15/#16/#17.
This file becomes the file-owned phase decision when its PR is accepted and merged.
Native PR, check and deployment objects remain authoritative for delivery facts.

## Decision and boundaries

Adopt the ENGINEERING profile for the descriptive historical M0 visitor journey
and offline M1 identity tooling. Do not call the whole research programme complete.
The historical six-series source is sufficient to display its exact observations;
it is not sufficient to label rising, returning or fading topics, infer causality,
measure populations, or stitch title histories across snapshots. M1's supplied
viewer is a prominently synthetic engineering fixture, not additional real coverage.

| Gate | Evidence and bounded decision |
| --- | --- |
| D01 | SATISFIED by the existing target-runtime probe and retained provenance. No new retrieval is inferred from a test. |
| D02 | PARTIAL. Display volume, absolute delta and relative lift for complete matched windows; zero baseline remains undefined. Do not freeze lifecycle thresholds or seasonality. |
| D03 | DECIDED; keep its source document unchanged. M0 has no stable page IDs; its series IDs are dataset-local. M1 validates local IDs/edges and uncertainty, not provider authenticity. |
| D04 | OPEN. No novelty claim or dependency on an unperformed competitor study. Preserve the existing research branch for later adoption, not rediscovery. |
| D05 | PARTIAL for source delivery: #17 implements overview/detail/exact tables/comparison/share and controlled-DOM regressions. Unshimmed HTTP and personally inspected mobile/desktop screenshots remain #21/#12. |
| D06 | PARTIAL. Static-only, read-only PR checks and deterministic source-bound bundles are executable. Provisioning, refresh/retention and public served-byte verification remain release gates. |
| D07 | DEFERRED for this slice. No digest, posting credentials or live sends. |
| D08 | READY for this bounded backlog only. Release completion is separate. |

## Ordered executable outcomes

1. **Source and readiness adoption (#9/#19/#20).** Reconcile the retained M1 code,
   tests, synthetic preview and test dependencies onto the accepted M0. Check
   deterministic bytes, bounded transport, identity edge cases and CI inventory;
   review the exact new head in a later session. No same-session approval/merge.
2. **Publication safety (#7).** Preserve validated historical evidence and the last
   valid candidate on failure. Close only with the issue's complete acceptance;
   do not recreate the previously denied publisher under another name.
3. **Verified public M0 (#21/#12).** Build the accepted revision twice, exercise
   actual HTTP navigation at a project subpath, inspect screenshots, provision
   Pages only with supported authorized capabilities, then verify served manifest,
   assets, dataset/method and visitor journey. No live link before this passes.
4. **Complete-window refresh (#18/#13).** Validate lag/window/identity, immutable
   monotonic staging and bounded retention/recovery. Keep prior publication on
   ingestion failure. A separate real target-runtime receipt is required.
5. **Real panel and evaluation (#19/#14).** Retrieve a curated, explicitly biased
   panel spanning both editions and the five subject areas, target >=20 actual
   local identities; report intended/obtained counts separately. Keep lifecycle
   counterexamples and threshold decisions separate from descriptive metrics.

Each linked issue owns detailed acceptance and blockers. This is the phase decision,
not a second task queue; `control/STATE_AND_QUEUE.md` owns ongoing priority.

## Bounded architecture and provider feasibility

No paid service, per-visitor inference or new worker is introduced. M0 verification
bounds each asset to 1 MiB and total responses to 5 MiB; generated release inventory
is exact and an independent manifest pin is required. M1 metadata collection is
one-shot: <=30 curated identities, 10-second request timeout, 1 MiB wire/entity
per response, separate 8 MiB aggregate caps, sequential requests and no automatic
retries. Normal spacing is two seconds; an Action API call taking over one second
is followed by five seconds. HTTP 429/5xx abort rather than trigger a retry loop.
The local immutable collection directory is not a Pages deployment or rolling
publication pointer. #18 owns bounded retention before recurring collection.

Primary provider documentation checked 2026-10-22:
- https://wikitech.wikimedia.org/wiki/Robot_policy — identified, compressed and paced clients.
- https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits — a static release must fit Pages bounds; eligibility does not grant administration rights.

## Acceptance meaning

Executed tests establish only their stated environment. Controlled-DOM tests,
normal local HTTP, hosted CI, DEPLOYED and LIVE_VERIFIED are different receipts.
Local browser restrictions do not authorize bypass. No external participant or
consented user study is represented by a maintainer review. D01/D03 history and
D02 raw provenance are unchanged; missing mappings or failed windows are not zero.
