# Research Registry

The registry is organized by questions, not documents. Status is evidence status, not
an estimate of completion.

| ID | Question | Method / stop condition | Durable output | Status |
| --- | --- | --- | --- | --- |
| D01 | Can the needed data actually be obtained in the target environment? | Run fixed EN/RU requests on the intended runtime. Stop when usable request receipts and checksums exist, or when a specific provider/runtime limitation is demonstrated. | Request receipts + bounded sample + coverage/checksums | OPEN |
| D02 | What makes a meaningful signal? | Compare raw volume, absolute change, baseline-relative lift, and lifecycle state against real and synthetic counterexamples. Stop when window/threshold decisions are evidence-backed or explicitly unresolved. | Versioned method and tests | PARTIAL |
| D03 | What exactly is one topic? | Inspect page IDs, moves, redirects, Wikidata mapping, and non-1:1 language cases from primary sources. Stop with an identity model that preserves uncertainty and entity changes. | Identity decision/model | OPEN |
| D04 | What already exists? | Perform task-based review of Topviews/Pageviews and a small directly inspected alternative set. Stop when Dayflare's actual differentiation constraints are explicit. | Competitive/task comparison | OPEN |
| D05 | Which visualization supports discovery? | Specify overview/detail/compare/share flows including mobile, keyboard, reduced motion, tables, and legends. Stop when behavior is implementable and testable. | UI/interaction specification | OPEN |
| D06 | Does the pipeline fit Pages and CI? | Verify current provider limits and model requests, storage, transfer, retention, retries, and stale-build recovery. Stop with bounded operating budgets and publication rules. | Architecture/budget decision | OPEN |
| D07 | What is safe and useful to publish as a digest? | Define event/card fields, evidence, timestamps, limitations, and send-reconciliation semantics. Stop at a schema; no live delivery is required. | Digest schema + illustrative examples | OPEN |
| D08 | Is development ready to start? | Convert accepted research into small ordered tasks with user outcome, evidence, dependencies, non-goals, and acceptance checks. Stop when the first engineering milestone is executable. | Engineering-ready backlog + profile-transition decision | OPEN |

## D02 accepted decision slice

From the durable issue #1 result:

- Store/expose magnitude, absolute change, relative lift, and lifecycle state as
  separate inspectable components.
- Do not hide a zero baseline behind an arbitrary user-facing epsilon.
- Discovery eligibility may later use floors, but those floors are not frozen yet.
- Incomplete windows do not compare against complete windows.
- Return-from-quiet is distinct from a first-time flare.
- Seasonal recurrence must not be described as unexpected until a seasonal comparison
  exists.

## D03 provenance warning

Conversation-only D03 analysis is intentionally excluded. Reconstruct D03 from primary
evidence in a fresh bounded unit before recording any decision.
