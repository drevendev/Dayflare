# Research Registry

The registry is organized by questions, not documents. Status is evidence status.

| ID | Question | Method / stop condition | Durable output | Status |
| --- | --- | --- | --- | --- |
| D01 | Can required data be obtained in the target runtime? | Run fixed EN/RU requests in the intended runtime; stop with usable receipts/checksums or a specific runtime/provider limitation. | Request receipts + bounded sample + coverage/checksums | OPEN |
| D02 | What makes a meaningful attention signal? | Compare magnitude, absolute change, relative lift, and lifecycle state against real and synthetic cases; stop when parameters are evidence-backed or explicitly unresolved. | Versioned method and tests | PARTIAL |
| D03 | What exactly is one topic? | Inspect page IDs, moves, redirects, Wikidata mappings, and non-1:1 language cases; stop with an identity model that preserves uncertainty and entity changes. | `research/D03_IDENTITY_MODEL.md` | COMPLETE |
| D04 | What already exists? | Task-based review of Topviews/Pageviews and a small directly inspected alternative set; stop when differentiation constraints are explicit. | Competitive/task comparison | OPEN |
| D05 | Which visualization supports discovery? | Specify overview/detail/compare/share including mobile, keyboard, reduced motion, tables, and legends; stop when behavior is implementable and testable. | UI/interaction specification | OPEN |
| D06 | Does the pipeline fit Pages and CI? | Verify current provider limits and model requests/storage/transfer/retention/retries/stale-build recovery; stop with bounded budgets and publication rules. | Architecture/budget decision | OPEN |
| D07 | What is safe and useful to publish as a digest? | Define event/card fields, evidence, timestamps, limitations, and send-reconciliation semantics; stop at a schema without live delivery. | Digest schema + illustrative examples | OPEN |
| D08 | Is development ready to start? | Convert accepted research into ordered tasks with outcome, evidence, dependencies, non-goals, and acceptance checks; stop when the first engineering milestone is executable. | Engineering-ready backlog + profile-transition decision | OPEN |

## D02 accepted decision slice

Keep raw volume, absolute change, relative lift, and lifecycle state separate. Do not
hide a zero baseline behind an arbitrary user-facing epsilon. Thresholds remain
unfrozen until D01 supplies real sample evidence. Incomplete windows do not compare
against complete windows. Return-from-quiet stays distinct from a first-time flare.
Seasonal recurrence is not called unexpected until a seasonal comparison exists.

## D03 accepted decision slice

Local page identity is `(project, page_id)`; title is mutable observation metadata.
Redirects remain separate identities with explicit edges and are not silently combined
with destination-page views. Dayflare owns a stable internal `topic_id`. Wikidata
identifiers are mapping evidence: preserve the observed identifier and any current
resolved identifier separately. Missing, ambiguous, broader/narrower, related, and
other non-1:1 mappings remain explicit. Identity semantics are versioned.
