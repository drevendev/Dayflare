# D03 — Topic and Page Identity Model v0

Status: DECIDED
Reviewed: 2026-09-26

## Evidence

Primary sources reviewed:
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

## Decision

Dayflare keeps local page identity, title history, redirects, topic identity, and
cross-language mapping as separate layers.

### Local page identity

Use `page_ref = (project, page_id)` for the identity of an extant local wiki page.
MediaWiki documents page IDs as wiki-local and preserved across moves. Titles are
mutable observations, not identity keys.

Deletion/undeletion is a continuity boundary, not an ordinary rename. Current MediaWiki
documentation agrees that a move preserves `page_id`, but deletion/restore does not
provide the same guarantee: the historical ID persists in archive data and restoration
may reclaim it, while the undeletion path can create a new page row/ID. Dayflare
therefore never stitches continuity across a deletion gap from title equality or a
current ID alone. Preserve deletion/restore evidence and mark continuity as
`confirmed`, `ambiguous`, or `discontinuous` according to observed evidence.

### Redirects

A redirect remains a separate page identity and is represented as an explicit edge to
its target when resolvable. Do not silently aggregate redirect pageviews into the
target: Wikimedia documents that redirect requests are not counted as views of the
actual destination page.

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

The Analytics pageview API is title-addressed while page IDs survive moves. Raw
observations must therefore preserve the requested project/title and request metadata
alongside resolved page identity evidence. Continuity across moves is derived from
title/move evidence, never assumed from the current title alone. Deletion/restore
boundaries require explicit continuity evidence before observations on opposite sides
are combined into one local-page series.

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

D03 is satisfied for research-phase identity design. Future changes must version this
model rather than silently changing stored identity meaning.
