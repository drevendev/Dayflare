# Source and Evidence Register

Only sources that currently constrain a Dayflare decision or queued research question
belong here. A link is not itself a finding.

| Source | Reviewed | Evidence class/use | Current constraint |
| --- | --- | --- | --- |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html | 2026-09-25 | Primary documentation | Pageview requests are title-addressed; D01 still must prove target-runtime access. |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html | 2026-09-24 | Primary documentation | Client identification/rate guidance applies; API-data licensing does not extend to article text or images. |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html | 2026-09-25 | Primary documentation | Redirects are not counted as destination-page views. |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/troubleshooting.html | 2026-09-24 | Primary documentation | Missing values, load lag, omitted zeros, and ambiguous 404 behavior prevent naive zero-filling. |
| https://www.mediawiki.org/wiki/Manual:Page_ID | 2026-09-25 | Primary documentation | `page_id` is wiki-local and preserved across moves. |
| https://www.mediawiki.org/wiki/Help:Moving_a_page | 2026-09-25 | Primary documentation | Moves normally create an old-title redirect. |
| https://www.mediawiki.org/wiki/Help:Redirects | 2026-09-25 | Primary documentation | Redirects are pages with their own history and identity. |
| https://www.wikidata.org/wiki/Help:Sitelinks | 2026-09-25 | Primary documentation | Sitelink conflicts and redirect handling mean QID mapping is evidence, not guaranteed equivalence. |
| https://www.wikidata.org/wiki/Help:Merge | 2026-09-25 | Primary documentation | Conflicting site links can require multiple items until local pages are reconciled. |
| https://www.wikidata.org/wiki/Help:Redirects | 2026-09-25 | Primary documentation | Merged item identifiers remain resolvable through redirects. |
| https://www.wikidata.org/wiki/Wikidata:Data_access | 2026-09-24 | Primary documentation | Structured identity source; mapping uncertainty remains explicit. |
| https://pageviews.wmcloud.org/topviews/ | 2026-09-24 | Existing product/reference | D04 must compare tasks directly. |
| https://github.com/drevendev/Dayflare/issues/1 | 2026-09-24 | Project anchor | Product purpose, D01-D08 queue, measurement boundaries, and acceptance gates. |
| https://github.com/drevendev/Dayflare/issues/1#issuecomment-5815917784 | 2026-09-24 | Durable project evidence | D01 chat-runtime probe failed to produce a sample; this is not source-zero evidence. |
| https://github.com/drevendev/Dayflare/issues/1#issuecomment-5816960976 | 2026-09-24 | Durable project evidence | D02 method structure and synthetic counterexamples; thresholds remain unfrozen. |

## Evidence rules

- Prefer primary sources for provider semantics and limits.
- Refresh dated provider claims before they become long-lived engineering assumptions.
- Keep established, reasoned, assumed, and unknown claims distinguishable.
- Record source conflicts instead of silently resolving them.
- Do not import copyrighted article text merely because a source is reachable.
