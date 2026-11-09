# Keep a Wikipedia identity snapshot inspectable after CI artifacts expire

A source-retaining capsule packages one verified collector bundle and an offline
HTML evidence reader. Each card links to the **exact retained JSON response**, not
only a current Wikipedia URL. Original panels, receipts and bodies remain unchanged.
This is the generic offline retention path in #197, not new collection, a
pageview atlas release or a Pages deployment. The existing `m1_retained_identity`
and `m1_real_pair` adapters continue to own their independently pinned historical
evidence. This tool accepts subsequent collector bundles without changing those
pins or duplicating their canonical source bytes.

## Try the labelled fictional example

Python 3.12+; no runtime dependencies or network calls:

```sh
python -m tools.m1_identity_capsule_demo /tmp/dayflare-capsule-example
python -m http.server 8000 --directory /tmp/dayflare-capsule-example/preview
```

Open the local server, or open `preview/index.html` directly in your browser.
There are 20 **fictional** selected identities, 19 retained and one unavailable.
They span five subjects and both editions solely to exercise coverage and layout.
The first-screen warning, source receipt and filename identify synthetic data.
No real observations, moves, changed attention or provider requests are claimed.

The demo deliberately constructs the collector's `reported_retrieval` input shape
to exercise the existing gates. Its underlying panels are still synthetic HTTP-
shaped test fixtures. Never combine them with real panels or use them as a baseline
for a real history report. Marked fixture inputs cannot be relabelled as reported
retrieval by this capsule builder or verifier.

## Pack an actually retained collector bundle

Input is the original directory produced by `tools.m1_collect`, containing:
`panel.json`, `collection-report.json`, `internal-consistency.json`,
`bundle-manifest.json`, and `raw/<project>.<page_id>.json`.
The frozen 24-October metadata-only projection is not this format and is rejected.

```sh
python -m tools.m1_identity_capsule pack retained-collection snapshot.zip \
  --source-revision <exact-40-character-collector-commit> \
  --source-run-url https://github.com/drevendev/Dayflare/actions/runs/<actual-run-id> \
  --evidence-kind reported_retrieval
```

The run URL is optional for genuinely local acquisition; its presence is a
self-reported provenance link, not authentication. Selection date, UTC observation
date, first request start and last request start are recorded separately. Source
receipts contain request-start timestamps, not response-completion timestamps:
`retrieval_completed_at_utc` is explicitly null, and the reader labels that time
unavailable. Request times are sorted as UTC instants, including fractional seconds. A collection spanning midnight
is rejected rather than being labelled as a single-day snapshot. Up to 20 intended
identities are supported; unavailable identities are disclosed, never turned into
zero pageviews or inferred deletions.

The builder freezes the bytes once and validates that frozen copy with the accepted
D03 panel, source-body and complete-bundle gates. This prevents a changing input
directory from substituting bytes after verification. A conservative metadata field
allowlist additionally rejects article text, revisions, images and unreviewed fields.
Legitimate new provider fields require explicit review, not a silent schema waiver.

## Verify, retain and inspect

```sh
python -m tools.m1_identity_capsule verify snapshot.zip \
  --expected-sha256 <independently-recorded-capsule-sha256>
python -m tools.m1_identity_capsule unpack snapshot.zip /tmp/identity-evidence \
  --expected-sha256 <independently-recorded-capsule-sha256>
```

The SHA-256 printed by `pack` is a computed digest, **not independent approval**.
A later reviewer must inspect the source/runtime evidence and retain the approved
pin outside the capsule before adoption. Reading a hash from the same untrusted
archive is not independent verification. Checksums cannot prove that Wikimedia
actually returned supplied bytes; `network_origin_verified` is always false.

The unpacked reader has a coverage table, stable IDs, observed/resolved/missing QIDs,
explicit non-1:1 mapping warnings, per-page exact sources, collection timestamps and
unknown/partial-coverage states. It needs no JavaScript, fonts, images, analytics or
automatic external requests. Keyboard skip links and source disclosures are native
HTML. Per-identity anchors contain the complete source-manifest fingerprint.
A public share URL must use an immutable, reviewed capsule location; this tool does
not provision that URL or advertise a local preview as a public site.

`source/panel.json` is byte-identical to the collector input and remains usable by
[`tools.m1_identity_history`](M1_IDENTITY_HISTORY.md). Two actual observation dates
are still required; this capsule does not backdate a missing first observation or
restore a lost response body. Current metadata does not independently verify events,
resolved QID redirects, cross-edition equivalence or uninterrupted page continuity.

## Storage, failure and recovery contract

Capsules are deterministic ZIP_STORED archives: fixed ordering, timestamps and
regular-file modes, at most 26 members, 1 MiB per raw body, 9 MiB source total and
12 MiB whole-archive ceiling. Source JSON receipts have tighter 32/256 KiB bounds.
Unknown paths, duplicate members, traversal, symlinks, encrypted/compressed members,
CRC errors, noncanonical framing, duplicate/nonfinite/excessively nested JSON,
source/receipt mismatches and modified HTML fail closed. No `extractall` is used.

ZIP writes use an fsynced same-directory temporary file followed by an atomic
no-clobber hard link. A competing writer cannot overwrite an accepted ZIP. A file
system without hard-link support fails explicitly, without a weaker overwrite
fallback. Unpacking validates everything before an exclusive destination `mkdir`;
`index.html` is written last. An I/O failure may leave an incomplete NEW directory
without a reader page. Preserve it for diagnosis; never serve it as a complete
capsule or overwrite a previous accepted destination. No publication pointer moves.

For a future dated comparison, retain at most two independently reviewed capsules
in the existing evidence location, plus approval pins/source-run references:
at most 24 MiB capsule storage. Do not duplicate the already retained Nov 4–5
sources. A reviewed PR owns any later adoption or replacement with provenance. This tool does not create a second
queue, retention daemon, writer, automatic pruning rule or new schedule. Before
seven-day CI artifacts expire, adopt genuine accepted evidence through a PR or
retain it in an owner-approved location; uploading a temporary artifact is not
that durable adoption.

## Source rights and policy boundary

Primary references checked 2026-11-09: Wikimedia's [Robot policy](https://wikitech.wikimedia.org/wiki/Robot_policy)
and [Wikidata licensing](https://www.wikidata.org/wiki/Wikidata:Licensing).
The collector's request identification, pacing, gzip and failure policy are
unchanged. This patch makes **no** provider requests. Retained fields are page
identity facts and observed structured identifiers; Wikidata structured data is
CC0, but that does not license Wikipedia article text or images. The metadata-only
allowlist is a content boundary, not an upstream-origin or blanket-licence verifier.

## Verification

```sh
python -m unittest discover -s tests -p 'test_m1_identity_capsule.py' -v
python -m compileall -q tools tests
python tests/m1/browser_identity_capsule.py
```

The native-HTTP Chromium script exercises six journeys per evidence kind
(320/390/1280, JavaScript on/off), exact raw bytes, keyboard disclosure, versioned
anchors, a 404 negative control, no external requests and no page overflow. The existing
read-only M1 workflow runs both the explicitly synthetic example and a real
historical replay; artifact paths and screenshots distinguish them. It adds no
schedule or writer. A successful run retains them for seven days, not indefinitely. Use `DAYFLARE_BROWSER_EXECUTABLE` only to select an installed compatible
browser, never to bypass navigation restrictions. Missing/blocked browser execution
is VISUAL_NOT_VERIFIED; a test file or generated HTML is not visual acceptance.

Full repository CI, personally inspected runtime screenshots, real acquisition,
reviewed two-date comparison and public served-revision verification remain
separate gates. None is implied by a local synthetic round-trip.

## Replay the accepted real baseline, without collecting anything

```sh
python -m tools.m1_retained_identity /tmp/dayflare-accepted-baseline
python tests/m1/check_identity_capsule_real.py \
  /tmp/dayflare-accepted-baseline/source /tmp/dayflare-real-capsule
python tests/m1/browser_identity_capsule.py \
  --real-source /tmp/dayflare-accepted-baseline/source
```

The regression independently pins the source manifest from
[evidence/m1-identity-20261104](../evidence/m1-identity-20261104/README.md), checks
20 retained local identities on 4 November, builds twice byte-identically,
verifies all 24 original source members unchanged, and re-runs the original
bundle verifier after unpacking. It rejects a different source manifest before
creating output. Its capsule checksum identifies the new renderer output; it is
not new approval or evidence of fresh Wikimedia transport. The generated
`preview/index.html` is an offline evidence reader, not the attention atlas.

## Recovery provenance

Adopted from the unpublished local `dayflare-identity-capsule-UNPUBLISHED.zip`
proposal (patch SHA-256
`7a4c99e10dc91a98e02023d370ecbb0f777595cd8ca1aabd714c33f3e0ec7cee`,
base `f80c3b0b9ae29fb0b0d453864b2f7f97fd41cdc6`). The proposal was not a prior PR
or Google Drive import. Reconciled against `ca58a16445f8a62a133494829a33184a88d54262`:
three reused validators match exactly; newer follow-up/real-pair workflow checks
are preserved. Adoption adds a uniform bounded strict-JSON gate on every source
member (including exponent overflow), correct request-start timestamp semantics,
and the independently pinned real-source replay. D01–D03 provenance and source
rights remain unchanged.
