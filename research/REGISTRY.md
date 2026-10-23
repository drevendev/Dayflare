# Research Registry

The registry is organized by questions, not documents. Status is evidence status, not
an estimate of completion.

| ID | Question | Method / stop condition | Durable output | Status |
| --- | --- | --- | --- | --- |
| D01 | Can the needed data actually be obtained in the target environment? | Run fixed EN/RU requests on the intended runtime. Stop when usable request receipts and checksums exist, or when a specific provider/runtime limitation is demonstrated. | `research/D01_RUNTIME_PROBE.md` | SATISFIED |
| D02 | What makes a meaningful signal? | Compare raw volume, absolute change, baseline-relative lift, and lifecycle state against real and synthetic counterexamples. Stop when window/threshold decisions are evidence-backed or explicitly unresolved. | Versioned method and tests | PARTIAL |
| D03 | What exactly is one topic? | Inspect page IDs, moves, redirects, deletion/restore boundaries, Wikidata mapping, and non-1:1 language cases from primary sources. Stop with an identity model that preserves uncertainty and entity changes. | `research/D03_IDENTITY_MODEL.md` | DECIDED |
| D04 | What already exists? | Perform task-based review of Topviews/Pageviews and a small directly inspected alternative set. Stop when Dayflare's actual differentiation constraints are explicit. | Competitive/task comparison; existing research branch preserved | OPEN |
| D05 | Which visualization supports discovery? | Implement overview/detail/compare/share with mobile, keyboard, reduced motion, exact tables and legends; accept actual visitor execution separately. | `site/README.md`, merged #17; actual HTTP/visual #21/#12 outstanding | PARTIAL |
| D06 | Does the pipeline fit Pages and CI? | Verify provider limits and bound requests, storage, transfer, retention, retries and recovery. Publication must preserve last valid data. | `research/D08_DESCRIPTIVE_DELIVERY.md`; static release builder and bounded M1 tools; provisioning/refresh still open | PARTIAL |
| D07 | What is safe and useful to publish as a digest? | Define event/card fields, evidence, timestamps, limitations and send-reconciliation. No live delivery required. | Digest schema and examples; deferred from descriptive web slice | OPEN |
| D08 | Is the bounded engineering slice ready? | Ordered outcomes, evidence, dependencies, non-goals and acceptance without waiving unresolved measurement/publication gates. | `research/D08_DESCRIPTIVE_DELIVERY.md`; one roadmap in `control/STATE_AND_QUEUE.md` | READY_SCOPED |

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

## D03 accepted decision slice

- Use `(project, page_id)` for the identity of an extant local wiki page; titles remain observations.
- Moves preserve local page identity, while redirect pages remain separate identities plus explicit edges.
- Deletion/restore is a continuity boundary and must not be stitched by title alone.
- Dayflare-owned `topic_id` values sit above local page identities.
- Preserve observed and resolved Wikidata identifiers and keep non-1:1 mapping states explicit.

## 2026-10-22 bounded adoption

D08 adopts the earlier #9 decision (comment 6309721214), now tied to merged #17
and executable source/CI. ENGINEERING is restricted to descriptive historical M0
and offline M1 identity tools. D01/D03 evidence is unchanged; six series over 35 days
do not close D02 or establish representative coverage. No lifecycle or novelty claim
is required to show exact historical observations. D04 research and D07 digest work
remain open; D07 is not a dependency of this web preview. D05 visual acceptance,
D06 authorized publication/refresh, real M1 acquisition and #12 live verification
remain explicit gates. Fixture validation never upgrades data to real evidence.
