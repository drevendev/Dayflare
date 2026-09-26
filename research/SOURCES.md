# Source and Evidence Register

Only sources that currently constrain a Dayflare decision or queued research question
belong here. A link is not itself a finding.

| Source | Reviewed | Evidence class/use | Current constraint |
| --- | --- | --- | --- |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html | 2026-09-24 | Primary documentation | Defines Pageviews endpoint shapes; actual Dayflare access still requires D01 runtime evidence. |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html | 2026-09-24 | Primary documentation | Client identification/rate guidance applies; API-data licensing must not be generalized to article text/images. |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html | 2026-09-24 | Primary documentation | Request-count semantics, redirect caveats, and automated-traffic categories constrain comparisons. |
| https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/troubleshooting.html | 2026-09-24 | Primary documentation | Missing values, data lag, omitted zeros, and ambiguous 404 behavior prevent naive zero-filling. |
| https://www.mediawiki.org/wiki/Help:Page_ID | 2026-09-26 | Primary documentation | Page IDs are wiki-local identifiers; titles are not stable identity keys. |
| https://www.mediawiki.org/wiki/Manual:Page_moving | 2026-09-26 | Primary documentation | Moves preserve the moved page identity while titles change. |
| https://www.mediawiki.org/wiki/Manual:Page_undeletion | 2026-09-26 | Primary documentation | Delete/restore is not treated as rename-equivalent continuity; Dayflare preserves an explicit continuity boundary. |
| https://www.mediawiki.org/wiki/Help:Redirects | 2026-09-26 | Primary documentation | Redirects remain distinct local pages and are modeled as explicit edges. |
| https://www.wikidata.org/wiki/Help:Sitelinks | 2026-09-26 | Primary documentation | Sitelinks provide mapping evidence without replacing local page identity. |
| https://www.wikidata.org/wiki/Help:Merge | 2026-09-26 | Primary documentation | Item merges can redirect obsolete QIDs; historical observed identifiers must remain preserved. |
| https://www.wikidata.org/wiki/Help:Redirects | 2026-09-26 | Primary documentation | Resolved QIDs may differ from historically observed QIDs; both are retained. |
| https://pageviews.wmcloud.org/topviews/ | 2026-09-24 | Existing product/reference | D04 must compare tasks directly; its existence prevents unsupported novelty claims. |
| https://github.com/drevendev/Dayflare/issues/1 | 2026-09-24 | Owner/project bootstrap anchor | Product purpose, D01-D08 queue, measurement boundaries, and initial acceptance gates. |
| https://github.com/drevendev/Dayflare/issues/1#issuecomment-5815917784 | 2026-09-24 | Durable project evidence | D01 chat-runtime probe failed to produce a sample; this is not source-zero evidence. |
| https://github.com/drevendev/Dayflare/issues/1#issuecomment-5816960976 | 2026-09-24 | Durable project evidence | D02 method structure and synthetic counterexamples; thresholds remain unfrozen. |

## Evidence rules

- Primary sources are preferred for provider semantics and limits.
- Every dated provider claim must be refreshed before it becomes a long-lived
  engineering assumption.
- Established, reasoned, assumed, and unknown claims stay distinguishable.
- A source conflict is recorded rather than silently resolved by preference.
- No copyrighted article text is imported merely because a source is reachable.
