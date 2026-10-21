# Dayflare State and Queue

STATE_REVISION: 7
PROJECT_STATUS: ACTIVE
PHASE: RESEARCH
PROFILE: RESEARCH
OPERATING_MODEL: drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10
RECONCILIATION_BASE: bd95139b26e72aec08f261b929a5d09ccdd4825b
RECONCILED_AT: 2026-10-18

## Next public outcome

A visitor can discover a measured EN/RU Wikipedia change, inspect exact history and
source evidence, compare compatible series and share a version-bound view at a verified
public URL. The first release uses the bounded historical sample and is explicitly stale,
not a live or representative atlas. Native Issues/PRs/checks/deployments own delivery facts.
This file is the single roadmap; linked issues own task acceptance and operation claims.

## Evidence and current gap

- D01 remains SATISFIED: `research/D01_RUNTIME_PROBE.md` preserves the six-request,
  84-observation target-runtime evidence for 1–14 September 2026 and its checksums.
- D02 remains PARTIAL: merged #6 provides the 35-day experiment described in
  `research/D02_RUNTIME_PROBE.md`, 11 August–14 September 2026, six EN/RU series and
  210 requested daily values. Do not repeat that horizon extension. Keep volume,
  absolute change, relative change and lifecycle separate; no validated thresholds.
  Zero baselines have unavailable lift; incomplete windows are not comparable.
  Original method provenance: issue #1 comment 5816960976.
- D03 remains DECIDED in `research/D03_IDENTITY_MODEL.md`: preserve `(project,page_id)`,
  title observations, separate redirects/edges, delete/restore continuity boundaries,
  Dayflare topic IDs and uncertain/non-1:1 observed/resolved Wikidata mappings.
  Do not stitch by title alone or reinterpret editions as populations.
- #10 repaired the public quickstart and obsolete queue. It did not adopt the M0
  interface or data pipeline. Retained local M0 archives and their test counts are
  recovery evidence, not canonical source, hosted checks or a deployed product.
- #11 is independently useful collector/CI work. Its PR does not close #7/#8/#9.
  RESEARCH remains explicit until scoped D08 readiness and source adoption are recorded.

## Ordered roadmap

1. **Collector correctness / #11.** Finish the existing D02 branch into a focused PR,
   then perform later exact-head acceptance. Check numeric boundaries, complete versus
   interrupted/oversized bodies, failure receipts and the universal offline PR checks.
   No Wikimedia retrieval or publication is required for this unit.
2. **Deliver the retained M0 / #7, #8, #9.** Reconcile the existing candidate against
   current master, preserve D01/D03 provenance and newer collector fixes, and adopt it
   through an authorized source PR. Record bounded D08 outcomes/dependencies/non-goals;
   verify real evidence, deterministic builds, keyboard/mobile/error/compare/share flows.
   Later acceptance must precede merge. Do not add unrelated local features or duplicate
   archives instead of delivering the existing product. D07 is deferred, not a gate.
3. **Verified public release / #12.** After source acceptance, build the merged revision,
   use actually authorized Pages capabilities and verify served bytes/version plus the
   real visitor journey. Add a README live URL only after LIVE_VERIFIED. No artifact,
   screenshot or workflow file by itself establishes public deployment.
4. **Reliable complete-window refresh / #13.** Preserve the historical probe; introduce
   explicit rolling-window/lag rules, bounded requests/retries/retention, last-valid
   publication recovery and visible stale state. Depends on the accepted #7 contract
   and #11 guards. Local failure tests may precede the release; live rollout follows #12.
5. **Broader useful coverage and evaluation / #14.** Acquire a bounded selected panel
   spanning both editions and culture/books/games/science/sport; disclose actual coverage.
   Preserve identities and evaluate low/new/renamed/returning/seasonal/automation controls
   before freezing lifecycle windows or labels. Use existing D04/D06 research, not stale
   control-file merges. A 20-identity target is a pilot design, not achieved coverage.

## Scoped blockers and reopening triggers

- **M0 publisher transfer:** the exact historical request-safety refusal is in
  [#7](https://github.com/drevendev/Dayflare/issues/7#issuecomment-6085469418), specifically
  `create_tree` for `tools/publish_m0.py`. It is not a GitHub permission error and is
  not generalized to unrelated code/comments/merges. Resume that denied operation only
  after a confirmed relevant change; no alternate representation/account/endpoint bypass.
- **Administrative maintenance / #5:** current ruleset 24273336 enforces PR-only changes
  and blocks deletion/force-push on master, with zero required approvals. Review-thread
  resolution is not required by the current rule. The account cannot bypass it and has
  push, not admin/maintain. No supported ref-deletion or administration write action is
  available in this inspection. Retain unique branch work; recheck only when capabilities
  or affected heads/consumers change. Do not weaken existing protection.
- **Execution surface:** direct GitHub clone failed DNS resolution in this session;
  connector reads and the #10 merge succeeded. SHA-matched local reconstruction supports
  offline tests, not a claim of network clone, target-runtime retrieval or browser/Pages
  acceptance. Hosted CI is determined from exact-head checks, never inferred from YAML.

No project-wide permission blocker is asserted. Keep blocked operations scoped and
finish independently verifiable delivery. Claims and their completion live in native
issues/PRs; do not add another queue, worker or per-run control surface.

## Review and schedule boundaries

Use separate consistency/simplicity review after 4–6 production units, divergence review
before freezing methodology/architecture, and consumer review before public acceptance.
Maintainer testing is not an external user study. Never approve/merge newly authored
semantic changes in the same session or fabricate self-approval/required-check results.
Ordinary blockers, empty queues and apparent completion do not authorize stopping,
replacing or disabling the existing perpetual hourly worker.
