UNIT_ID: D03
CREATED_BY_RUN: 2026-09-25T19:23:12Z
SOURCE_REVISION: 4
SUPERSEDES: —

# D03 — Topic and Page Identity Model v0

Status: DECIDED
Reviewed: 2026-09-27

## Evidence

Primary sources refreshed or rechecked through 2026-09-27:
- https://www.mediawiki.org/wiki/Help:Page_ID
- https://www.mediawiki.org/wiki/Manual:Page_table
- https://www.mediawiki.org/wiki/Manual:Page_moving
- https://www.mediawiki.org/wiki/Help:Redirects
- https://www.mediawiki.org/wiki/Manual:Page_undeletion
- https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html
- https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
- https://www.wikidata.org/wiki/Help:Sitelinks
- https://www.wikidata.org/wiki/Help:Merge
- https://www.wikidata.org/wiki/Help:Redirects

### Classified findings

**F-D03-001 — Established.** MediaWiki documents `page_id` as unique only within
one wiki and stable across an ordinary page move. Titles therefore are not stable local
identity keys.

Evidence:
- https://www.mediawiki.org/wiki/Help:Page_ID
- https://www.mediawiki.org/wiki/Manual:Page_table
- https://www.mediawiki.org/wiki/Manual:Page_moving

**F-D03-002 — Established.** Redirects are wiki pages rather than aliases that erase
their own page identity. A redirect relationship must therefore be represented
separately from the source and target page identities.

Evidence:
- https://www.mediawiki.org/wiki/Help:Redirects
- https://www.mediawiki.org/wiki/Manual:Page_table

**F-D03-003 — Established.** Wikimedia pageview documentation says redirect requests
are not counted as views of the actual destination page. Redirect traffic must not be
silently folded into the target's observed views.

Evidence:
- https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html

**F-D03-004 — Established source conflict.** Current MediaWiki documentation is not
fully consistent about page IDs across deletion and restoration. `Help:Page_ID` and
`Manual:Page_table` say the historical ID persists in archive data and a restored page
attempts to reclaim it, while `Manual:Page_undeletion` describes restoration as
creating a new `page` row with a new `page.page_id`. The conflict is recorded rather
than resolved by preference.

Evidence:
- https://www.mediawiki.org/wiki/Help:Page_ID
- https://www.mediawiki.org/wiki/Manual:Page_table
- https://www.mediawiki.org/wiki/Manual:Page_undeletion

**F-D03-005 — Reasoned.** Because ordinary moves have stable-ID documentation but
delete/restore has conflicting documentation, deletion/restoration is a continuity
boundary for Dayflare. Title equality or a current page ID alone is insufficient to
stitch observations across that boundary.

Reasoning from: F-D03-001, F-D03-004.

**F-D03-006 — Established.** Wikidata item merges leave the obsolete QID as a redirect
to preserve identifier references; Wikidata redirects exist specifically to provide
stable identifiers.

Evidence:
- https://www.wikidata.org/wiki/Help:Merge
- https://www.wikidata.org/wiki/Help:Redirects

**F-D03-007 — Reasoned.** A QID or sitelink is mapping evidence, not Dayflare's sole
topic identity. Cross-edition page scope can differ and QIDs can later redirect, so
topic relationships need explicit states and historical identifier provenance.

Reasoning from:
- F-D03-006
- https://www.wikidata.org/wiki/Help:Sitelinks
- https://www.wikidata.org/wiki/Help:Merge

**F-D03-008 — Reasoned.** The Analytics pageview API is title-addressed while local
page identity can survive a move. Raw observations therefore need the requested
project/title and request metadata alongside the page-identity evidence used to derive
continuity.

Reasoning from:
- F-D03-001
- https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html

**F-D03-009 — Unknown.** Without event-specific evidence, Dayflare cannot know whether
a particular delete/restore sequence retained or changed the historical local page
identity. That uncertainty must remain explicit instead of being inferred from title
or current-state lookup alone.

Basis: F-D03-004.

## Decision

**D-D03-001 — Adopt a layered identity model.** Dayflare keeps local page identity,
title history, redirects, topic identity, and cross-language mapping as separate
layers. This decision is supported by F-D03-001 through F-D03-009; the conservative
delete/restore rule specifically follows F-D03-004, F-D03-005, and F-D03-009.

### Local page identity

Use `page_ref = (project, page_id)` for the identity of an extant local wiki page.
Titles are mutable observations, not identity keys.

Deletion/undeletion is a continuity boundary, not an ordinary rename. Preserve
delete/restore evidence and mark continuity as `confirmed`, `ambiguous`, or
`discontinuous` according to event-specific evidence. Never stitch continuity across
a deletion gap from title equality or a current ID alone.

### Redirects

A redirect remains a separate page identity and is represented as an explicit edge to
its target when resolvable. Do not silently aggregate redirect pageviews into the
target.

### Topic identity

Dayflare owns a stable internal `topic_id`. A topic is not defined by title or solely
by a Wikidata QID. Page relationships must preserve scope with explicit states such as
equivalent, broader, narrower, related, ambiguous, and missing.

Missing mapping remains missing; it is never interpreted as zero attention. Series or
franchise topics and individual installments do not collapse by title similarity.

### Wikidata mapping

Treat QIDs as mapping evidence. Preserve both `qid_observed` and the currently
`qid_resolved` value when a QID later becomes a redirect after a merge. Do not rewrite
historical provenance.

### Pageview acquisition consequence

Raw observations preserve the requested project/title and request metadata alongside
resolved page identity evidence. Continuity across moves is derived from title/move
evidence, never assumed from the current title alone. Deletion/restore boundaries
require explicit continuity evidence before observations on opposite sides are
combined into one local-page series.

## Required implementation tests

1. A move preserves page identity while title history changes.
2. An old-title redirect remains separate from the moved page.
3. Redirect views are never silently aggregated into the target.
4. A delete/restore or delete/recreate gap is not stitched by title alone; continuity
   state remains explicit until supported by evidence.
5. Supported cross-language mapping does not replace local page identities.
6. Missing/conflicting mapping remains explicit.
7. QID redirects preserve observed and resolved identifiers separately.
8. Broad/narrow cross-language pages are not treated as equivalent.
9. Series/franchise and installment identities do not collapse by title similarity.

## Conclusion

D03 is satisfied for research-phase identity design under D-D03-001. The evidence
classes and the deletion/restoration source conflict are part of the decision record.
Future changes must version this model rather than silently changing stored identity
meaning.
