# Dayflare State and Queue

STATE_REVISION: 8
PROJECT_STATUS: ACTIVE
PHASE: RESEARCH
PROFILE: RESEARCH
OPERATING_MODEL: drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10
RECONCILIATION_BASE: 8a859f862f555e43f0aed519e2d42b64cd96a64b
RECONCILED_AT: 2026-10-19

## Next public outcome

A visitor can discover a measured EN/RU Wikipedia change, inspect exact history and
source evidence, compare compatible series and share a version-bound view at a verified
public URL. The first milestone is explicitly historical, not live or representative.
This is the single roadmap; native issues/PRs/checks/deployments own task and delivery facts.

## Evidence and current gap

- D01 remains SATISFIED in `research/D01_RUNTIME_PROBE.md`: six requests and 84 daily
  observations for 1–14 September 2026, with target-runtime provenance preserved.
- D02 remains PARTIAL. Merged #6 provides the fixed 35-day collector. Retained
  `evidence/d02-20261018` holds the exact 210 normalized observations and receipt from
  run 39112409117. The validator recomputes their metrics, not raw HTTP body hashes.
  The original archive and repacked capsule have separately identified digests.
  Keep volume, absolute change, relative change and lifecycle separate. Thresholds
  remain unfrozen; zero baselines and incomplete windows are not fabricated values.
  Original method provenance remains issue #1 comment 5816960976.
- D03 remains DECIDED in `research/D03_IDENTITY_MODEL.md`: `(project,page_id)`, title
  observations, separate redirects/edges, delete/restore boundaries, Dayflare topic IDs
  and uncertain/non-1:1 observed/resolved Wikidata mappings. The historical D02 capsule
  contains no page-ID observations; it is not evidence for cross-snapshot stitching.
- #10 repaired the quickstart, not the atlas. #15 implements #11 and was corrected at
  the reconciliation base after fresh review found premature HTTP EOF could be falsely
  treated as a complete response. Earlier exact-head acceptance does not cover that fix.
- Full M0 source/UI/publication is still outstanding. Read-only evidence adoption does
  not complete #7/#8/#9, switch profiles or establish a public milestone. Keep RESEARCH
  until the bounded D08 decision and its permitted source slice are recorded together.

## Ordered roadmap: five outcomes

1. **Accept collector correction / #11, #15.** Later review the exact head, framing and
   numeric boundaries, current base, discussions and real checks. Merge normally only
   after acceptance; the correction's production session must not merge it. Do not
   regenerate the already-delivered 35-day probe or count old green checks as current.
2. **Adopt retained evidence / #7.** Accept the data-only capsule, provenance, read-only
   validator and real-fixture regressions. Acceptance: a cold checkout validates all
   210 observations offline; missing/corrupt files fail; source/member/calculation hashes
   agree. This PR is stacked on #15: merge #15 first, retarget to master and recheck the
   exact diff/base before acceptance. Remaining snapshot/build/publisher work stays open.
3. **Finish the actual M0 journey / #7, #8, #9.** Reconcile existing source rather than
   redesigning it; preserve D01/D03 and newer collector fixes. Record the bounded D08
   decision and unknown lifecycle/mapping states. Key implementation task: put the real
   retained-snapshot browser checks into read-only CI, including widths 320/390/1280,
   keyboard-only discovery/detail/compare/share, no-JavaScript tables, invalid data,
   retry, empty filters, version mismatch and focus recovery. Store bounded failure
   screenshots; no forced actions or removed assertions to hide failures. This depends
   on permitted M0 source adoption, not on Pages administration or another developer.
4. **Verified public release / #12.** After source acceptance, produce two identical
   builds, use authorized Pages provisioning/deployment, verify served bytes and HTTP
   representation against the release manifest, then inspect the actual visitor journey.
   Add the live README URL and genuine screenshot only after LIVE_VERIFIED. Record
   MERGED, BUILT, DEPLOYED and LIVE_VERIFIED separately. A workflow/artifact is not a site.
5. **Fresh, durable and broader observations / #13, #14.** Adopt the retained rolling
   window/identity work after deduplication. Key task: retain immutable version-addressed
   snapshots so old shares restore the intended dataset or show explicit unavailable
   recovery, never silently use current data. Define a byte/day retention budget and
   test expiry, schema mismatch and concurrent promotion while preserving last-valid
   output. Prove one bounded target-runtime refresh with lag/retry/identity receipts.
   Then acquire the planned 20-identity EN/RU culture/books/games/science/sport panel;
   report actual versus intended coverage. Evaluate low/new/renamed/returning/seasonal
   and automation controls before any lifecycle threshold or label is frozen.

D04/D06 branches preserve useful research: adopt only relevant evidence, not obsolete
control files. D07 digest delivery and a topic basket are deferred, not web-preview gates.
Do not replace source delivery with further local-only features or duplicate archives.

## Scoped blockers and reopening triggers

- **M0 publisher:** #7 comment 6085469418 records the historical request-safety refusal
  for `create_tree` / `tools/publish_m0.py`. That transfer was not retried or repackaged
  in this cleanup. No new proof that the specific restriction cleared is claimed.
  Source evidence adoption is not a replacement publisher or a route around the refusal.
- **Maintenance / #5:** retain the 2026-10-18 ruleset inspection as dated evidence;
  master was PR-only with deletion/force-push restrictions and zero required approvals,
  but conversation resolution was not required. Current account has push, not admin or
  maintain. Apply stronger compatible rules or delete proven-redundant refs only through
  supported authorized operations and fresh head/preservation/consumer checks. No new
  blanket assertion that master is unprotected, and no permission/token workaround.
- **Execution:** direct clone failed DNS in the cleanup environment; connector-backed
  source reads/writes work. Offline reconstruction is not a network clone, live source
  acquisition or browser/Pages verification. Tests must report their actual context.

Claims and exact blockers live in native issues/PRs. A tool success is not a blanket
capability guarantee; stop dependent writes on denial and choose independent useful work.

## Review and schedule boundaries

Use separate consistency/simplicity review after 4–6 production units, divergence review
before freezing methodology/architecture, and consumer review before public acceptance.
Maintainer testing is not an external user study. Never approve/merge newly authored
semantic changes in the same session or fabricate check results. Ordinary blockers,
empty queues and apparent completion do not authorize stopping, replacing or disabling
the existing perpetual hourly worker. No parallel queue, worker or Drive control plane.
