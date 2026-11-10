# Compare dated Wikipedia identity observations

`tools.m1_identity_history` turns two bounded D03 panels into a readable,
version-specific before/after evidence report. It answers **which observed local
identities changed**, not whether pageview histories can be joined.

## Try the working example

From the repository root with Python 3.12 or newer:

```sh
python -m tools.m1_identity_history_demo /tmp/dayflare-identity-history-demo
python -m http.server 8000 --directory /tmp/dayflare-identity-history-demo
```

Open `http://localhost:8000/`. The page is a **synthetic demonstration**, labelled
on its first screen. It shows a move, changed mapping, ambiguous QID collision,
redirect edge, deletion/restoration boundary, unchanged observation and a reused
title with a different ID. It is not newly collected Wikipedia data or a public
Pages release. Use a new output directory on another build; existing output is
never overwritten.

The report works without JavaScript. Its index, keyboard skip link, side-by-side
observations (stacked on mobile), exact evidence disclosures and version-bound
identity anchors are accompanied by `history.json` and `manifest.json`. No remote
fonts, article/image content, analytics or automatic provider requests are used.

## Compare actual retained inputs

```sh
python -m tools.m1_identity_history before-panel.json after-panel.json /tmp/identity-history-reviewed-inputs
```

Both inputs must be **raw** `dayflare.identity-panel.v1` panels, such as retained
`panel.json` files from `tools.m1_collect`; the existing D03 validator remains the
schema authority. Inputs are limited to 256 KiB and 100 observed local IDs each.
Each must have a nonempty set of observations whose latest title dates identify
one common UTC observation day. The second observation day must be later. Mixed
observation days, reversed/same-day inputs and synthetic/real mixtures are rejected,
not silently reinterpreted. Selection time is preserved separately from observation
and per-page retrieval timestamps. Events cannot postdate their snapshot.

The frozen `dayflare.m1.observed-identity-panel.v1` projection dated 24 October is
not the raw D03 schema and is deliberately **not** silently converted. Preserve
its existing JSON/HTML and checksums. Adopt a genuine pair of retained source
panels through later source review before describing this report as measured
coverage. A successful synthetic test or a report generated from supplied metadata
is not a fresh provider retrieval.

## Meaning of the output

- Join only exact `(project, page_id)` pairs. Matching titles, editorial topic tags
  or QIDs never combine IDs or editions. Numeric IDs in different editions differ.
- Preserve both snapshots, all observed/resolved QIDs, redirect edges, title and
  event evidence, source timestamps, exact input SHA-256 and coverage diagnostics.
- A changed title is a changed observation. `move_reported` requires a supplied
  matching old/new-title event inside the observation interval, but is **not** an
  independent verification of that event or of uninterrupted identity continuity.
- A missing/new observation means only that it is absent/present in that selected
  input, not deleted/created or zero attention. Selection and unresolved counts
  remain visible. A reported deletion/restoration boundary cannot be erased by
  dropping the old event from a later panel. Conflicting title histories stay
  explicit; mapping collisions never resolve themselves.
- `pageview_join_allowed` is always `false`. This module does not calculate or
  aggregate attention, stitch a title history or waive D02/D03 research gates.

Output schema: `dayflare.identity-history.v1`; method: `d03-observation-diff.v1`.
`report_id` and all per-identity anchors include a fingerprint of the method and
both exact input byte hashes. Same inputs reproduce identical HTML/JSON/manifests;
a different input cannot silently inherit the old report's identity anchors.
The `reported_retrieval` label still means reported, not authenticated: hashes
prove local byte identity, not provider origin or completeness of an event log.

## Failure, concurrency and acceptance

Validation and rendering finish before output creation. An atomic `mkdir` reserves
a **new** bundle directory; concurrent creation or any existing path is rejected.
The manifest is written last. A storage failure can leave an incomplete new directory
without a manifest, which must never be treated as a complete bundle. No previous
output or publication pointer is modified. Neither CLI publishes anything.

```sh
python -m unittest discover -s tests -p 'test_m1_identity_history.py' -v
python tests/m1/browser_identity_history.py
```

The browser test uses real local HTTP at a `/Dayflare/` subpath, Chromium at
320/390/1280 pixels, JavaScript enabled/disabled, keyboard navigation, disclosure,
exact JSON, version anchors and no overflow/external requests. It retains genuine
screenshots under `evidence/local-m1-browser/`; inspect them before visual acceptance.
A separately installed Chromium can be selected with
`DAYFLARE_BROWSER_EXECUTABLE=/path/to/chromium`. A browser/provider policy denial
must be reported, never bypassed or counted as a passing check.

The existing M1 validation workflow exercises the new unit and browser tests and
retains an explicitly synthetic report artifact. It has read-only contents rights,
no new worker, no provider collection and no Pages deployment.

Related: #19 (stable-ID evidence), #14 (coverage/counterexamples),
[`D03_IDENTITY_MODEL.md`](../research/D03_IDENTITY_MODEL.md),
[`D08_DESCRIPTIVE_DELIVERY.md`](../research/D08_DESCRIPTIVE_DELIVERY.md).
This implements an offline engineering slice, not closure of those broader gates.

## Retain the source evidence before artifacts expire

Use the [source-retaining identity capsule](M1_IDENTITY_CAPSULE.md) to preserve
one collector bundle, including the exact raw bodies, its receipts and a readable
no-JavaScript evidence page. Verification requires an independently recorded
capsule SHA-256 and reruns the accepted source/bundle validators. The returned
`source/panel.json` remains byte-identical and usable by the comparator above.
This does not create a second observation date or authenticate upstream origin.
The accepted Nov 4–5 pair remains owned by `m1_real_pair` and its pinned
repository evidence; the generic capsule neither replaces it nor proves
continuous identity between observations. See #197 for capsule adoption.
