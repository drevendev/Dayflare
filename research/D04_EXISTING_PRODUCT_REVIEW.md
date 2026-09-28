# D04 — Existing-product review and differentiation constraint

UNIT_ID: D04  
STATUS: DECIDED / CONSUMER VALIDATION PENDING  
PROFILE: RESEARCH  
REVIEWED_AT: 2026-09-28  
BASE_REVISION: master@555268a49b82960c31e15b0758ef4c5402147374

## Question

What already exists for Wikipedia attention discovery, comparison, and sharing, and what
must Dayflare *not* claim as differentiation?

This is a bounded task-based review, not a comprehensive market survey. It directly
inspects Wikimedia Pageviews Analysis plus two public alternatives that overlap the
proposed product journey.

## Findings

| ID | Class | Finding | Basis |
| --- | --- | --- | --- |
| F-D04-001 | Established | Wikimedia Pageviews Analysis is an actively deployed first-party-adjacent baseline. The live service reports version 2026.09.25 and exposes Pageviews, Langviews, Topviews, Redirect Views, and related tools. Pageviews supports comparison of up to 10 pages, platform/agent filters, optional redirect inclusion, permalink behavior, and CSV/JSON/PNG export. | https://pageviews.wmcloud.org/ ; https://meta.wikimedia.org/wiki/Pageviews_Analysis |
| F-D04-002 | Established | WikiRank already presents multilingual Wikipedia popularity and topical rankings, including dated daily rankings and per-language positions for the same topic. Therefore “multilingual popularity/ranking” is not a defensible Dayflare novelty claim by itself. | https://www.wikirank.net/ ; https://wikirank.net/top/en/2026-06-20 ; https://wikirank.net/en/2026 |
| F-D04-003 | Established (product observation) | GlobalHotword already presents English-Wikipedia daily trending topics with ranking history plus news/search-interest context. The sampled live homepage is pinned to a 2026-05-12 snapshot, and sampled topic pages expose empty numeric rank fields, so this review does not treat its explanatory text as validated causality or its freshness as guaranteed. | https://globalhotword.com/ ; https://www.globalhotword.com/trend/Billboard_Hot_100 ; https://www.globalhotword.com/trend/Global_biodiversity |
| F-D04-004 | Reasoned | A product that only adds prettier pageview charts, top lists, page comparison, language comparison, redirect inspection, or a shareable URL would substantially duplicate observed existing capabilities. | F-D04-001..003 |
| F-D04-005 | Reasoned | The strongest bounded Dayflare differentiation hypothesis is lifecycle-state discovery relative to a topic’s own history — flare, return-from-quiet, and fade — combined with explicit identity continuity, exact inspectable evidence, edition comparison, and a reproducible shareable view. | Issue #1 product purpose + D02 structural decision + F-D04-001..004 |
| F-D04-006 | Unknown | This bundle is not established as unique in the wider market and has not been validated with users. “Unique” and “better” remain prohibited claims until a broader evidence need or the usefulness gate justifies them. | No user study or comprehensive competitor survey has been run. |

## Task comparison

| User task | Pageviews Analysis | WikiRank | GlobalHotword | Dayflare implication |
| --- | --- | --- | --- | --- |
| Inspect exact pageview history | Strong | Secondary | Secondary | Must match basic inspectability; not differentiation. |
| Compare several pages | Strong (up to 10 in Pageviews) | Ranking-oriented | Limited | Not differentiation. |
| Compare language editions | Strong through Langviews | Strong ranking view | English-only observed | Edition comparison is required hygiene, not novelty. |
| Discover what is popular now | Strong through Topviews | Strong daily rankings | Core experience | A top list alone is insufficient. |
| Inspect redirects | Dedicated Redirect Views | Not central | Not central | Needed for truthful identity/traffic handling, not a headline claim. |
| Share a precise view | Permalink/export support exists | Public URL | Public topic URLs | Shareability is required baseline behavior. |
| Discover lifecycle change vs own history | Not observed as the primary journey in this bounded review | Not observed as primary | Some rank-history language, but top-list/rank based | Keep as the main Dayflare hypothesis, not a proven uniqueness claim. |
| Preserve explicit identity/provenance boundaries | Partial tool-specific support | Not established here | Not established here | Make evidence/identity transparency a product requirement. |

## Decision D-D04-001

Adopt a **differentiation constraint**, not a uniqueness claim.

Dayflare should be designed around:

1. automatic discovery of lifecycle-state changes relative to each topic’s own history;
2. return-from-quiet as distinct from first-time flare;
3. stable topic identity and explicit redirect/move/mapping provenance;
4. exact values and methodology visible from every discovery;
5. comparison across Wikipedia editions without treating editions as countries;
6. a precise, reproducible shareable evidence view.

Do **not** market “Wikipedia trends”, “top pages”, “multilingual popularity”, “pageview
charts”, “redirect-aware views”, or “shareable links” as unique capabilities.

Supporting findings: F-D04-001, F-D04-002, F-D04-003, F-D04-004, F-D04-005,
F-D04-006.

## Consequences

- D05 should make lifecycle-state discovery the overview’s central task rather than
  reproducing a ranked Topviews table with decoration.
- D08 must include a consumer/usefulness gate before any public uniqueness language.
- Explanations of *why* a topic changed remain outside the attention metric unless
  independently evidenced; competitor contextual copy is not causal proof.
- Static snapshots, last-valid-publication behavior, and explicit stale/update state
  remain useful reliability properties, but this review does not claim competitors are
  unreliable.

## Non-goals

- No exhaustive competitor census.
- No market-size or traffic estimate.
- No causal validation of news/search context shown by third-party products.
- No change to D02 thresholds or D03 identity semantics.
