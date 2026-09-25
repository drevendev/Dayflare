# Research Registry

| ID | Question | Durable output | Status |
| --- | --- | --- | --- |
| D01 | Can required data be obtained in the target runtime? | Request receipts and bounded sample | OPEN |
| D02 | What makes a meaningful attention signal? | Versioned method and tests | PARTIAL |
| D03 | What exactly is one topic? | `research/D03_IDENTITY_MODEL.md` | COMPLETE |
| D04 | What already exists? | Task-based product comparison | OPEN |
| D05 | Which visualization supports discovery? | UI and interaction specification | OPEN |
| D06 | Does the pipeline fit Pages and CI? | Architecture and budget decision | OPEN |
| D07 | What is safe and useful to publish as a digest? | Digest schema and examples | OPEN |
| D08 | Is development ready to start? | Engineering-ready backlog | OPEN |

## D02 accepted decision slice

Keep raw volume, absolute change, baseline-relative lift, and lifecycle state separate.
Thresholds remain unfrozen until D01 supplies real sample evidence.

## D03 accepted decision slice

Local page identity is `(project, page_id)`, while titles are mutable observations.
Redirects remain separate identities with explicit edges and are not silently
aggregated into destination-page views. Dayflare owns a stable internal `topic_id`.
Wikidata identifiers are mapping evidence: preserve the observed identifier and any
currently resolved redirect target separately. Missing, ambiguous, broader/narrower,
and other non-1:1 mappings remain explicit.
