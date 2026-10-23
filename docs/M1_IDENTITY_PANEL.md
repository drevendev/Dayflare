# M1 identity evidence: validate, collect, verify

The [D03 identity decision](../research/D03_IDENTITY_MODEL.md) remains authoritative.
This is metadata tooling for #19, not a new pageview method or representative panel.
No included test body establishes a successful Wikimedia retrieval.

## Identity contract

`tools.m1_identity_panel` accepts a curated `dayflare.identity-panel.v1` input:
stable `(project,page_id)` references, Dayflare topic IDs, subject/scope relations,
dated title observations, redirect edges, continuity and uncertain Wikidata mappings.
It emits canonical JSON, coverage counts and a SHA-256. Input order does not change
the output. Limits are 256 KiB, 100 identities, 30 title observations and 30 events
per identity; editions are `en.wikipedia` and `ru.wikipedia` only.

Moves keep local identity; redirects remain separate identities and dated edges.
Same-day cycles and targets outside the panel are unresolved, not merged. Opposite
edges observed on different days do not prove a simultaneous cycle. Deletion/restore
requires ambiguous or discontinuous continuity pending separate adjudication.
Titles never become identity keys. Observed/resolved QIDs remain separate; missing
or non-1:1 mappings and broader/narrower relations do not imply zero attention.
Coverage counts intended/obtained identities by edition and subject, not pageviews.

Python 3.12+; product tools use the standard library:

```sh
python -m tools.m1_identity_panel examples/synthetic_panel.json > /tmp/panel.json
python -m tools.m1_identity_panel examples/synthetic_panel.json > /tmp/panel-again.json
cmp /tmp/panel.json /tmp/panel-again.json
```

All three files under `examples/synthetic_*` are **fictional**. IDs, titles, dates,
QIDs and source URLs are not verified facts. A `reported_retrieval` input instead
requires per-page endpoint, UTC request timestamp, HTTP status, decoded body size
and SHA-256; QID claims require evidence URLs. Structural validation labels it
`reported_not_upstream_verified`, never authenticated provider evidence.

## One-shot collection

`tools.m1_collect` accepts `dayflare.identity-seeds.v1`: `panel_id`, `selected_at`
and 1–30 vetted entries with `page_ref`, `topic_id`, `subject`, `relation`.
Obtain real numeric page IDs independently. **Do not send the fictional example
seed to the live collector.** Run only with a real, reviewed seed file:

```sh
python -m tools.m1_collect path/to/vetted-seeds.json evidence/m1-unique-run
python -m tools.m1_source_verify evidence/m1-unique-run/panel.json evidence/m1-unique-run/raw
python -m tools.m1_bundle_verify evidence/m1-unique-run
```

The destination must not exist. The collector uses exact allow-listed Action API
origins and one-page queries: `action=query`, `format=json`, `formatversion=2`,
`prop=info|pageprops`, `ppprop=wikibase_item`, `pageids=<ID>`. No title discovery,
redirect following, authentication, cookies, article prose or images are requested.
A valid result is one current namespace-0 page with matching ID, dated title and
observed QID. Historical events and resolved QID redirects are not fetched; new
continuity stays ambiguous. Missing/redirected/malformed identities in HTTP 200
are counted unavailable, not zero views. Non-200, timeout, network, content-type,
size or decompression failure aborts; there is no automatic retry or publication.

The entire staged bundle is verified before promotion. Linux uses
`renameat2(RENAME_NOREPLACE)` to avoid replacing even a competing empty directory;
Windows uses its no-replace `os.rename`. Unsupported no-replace platforms fail
closed. Existing targets survive failures. A unique local output directory is
not a rolling publication pointer, Pages deployment or retention policy.

## Transport budgets and representation (#20)

One identified GET at a time; at most 30 calls, ten-second request timeout. Wait two
seconds after ordinary calls and five seconds if the previous Action API call took
more than one second, conservatively including network time. A later independent
attempt must respect provider `Retry-After`. HTTP 429/5xx never causes a retry loop.
The Robot policy's separate 15-minute 5xx rule for other resources is not described
as an Action API rule here.

Request `Accept-Encoding: gzip`; identity fallback is supported, unknown encodings
are rejected. Wire and decoded bodies each have a 1 MiB cap and independent 8 MiB
aggregate caps. Content-Length, when present, must be canonical and match received
wire bytes. A gzip response requires a valid CRC/trailer, exactly one complete
member and no trailing data. Truncation, `IncompleteRead`, oversized inflation and
invalid headers fail closed. Strict JSON/API validation applies even without a
Content-Length header.

`dayflare.identity-collection.v2` makes byte meaning explicit:

| Field | Meaning |
| --- | --- |
| `transferred_bytes` | Received HTTP representation bytes, including discarded 200 responses |
| `decoded_bytes` | All decoded JSON entity bytes |
| `retained_bytes` | Only decoded JSON bodies actually saved under `raw/` |
| `body_representation` | Always `decoded-json-entity` |
| Attempt `wire_bytes`, `wire_sha256`, `content_encoding` | Recorded wire observations; compressed wire bodies are not retained |
| Source `response_bytes`, `body_sha256` | Size/hash of the retained decoded JSON entity |

Old v1 collection receipts are rejected, not silently reinterpreted. Panel schema
v1 and D03 identity semantics are unchanged. Rejected-body and compressed-wire
hashes are diagnostics, not independently rehashable retained source evidence.

## Independent offline gates

A collection contains exactly `panel.json`, `collection-report.json`,
`internal-consistency.json`, `bundle-manifest.json` and the expected `raw/` members.
The manifest lists lengths/hashes of every other file; it excludes itself.
`m1_source_verify` checks exact endpoint/query, body hash/size, strict JSON, page ID,
namespace, UTC retrieval-day title and observed QID. Limits: 1 MiB per body, 8 MiB
combined. It rejects substituted/redirected pages and extra or missing raw members.

`m1_bundle_verify` additionally rejects extra directories, symlinks, changed file
inventories and inconsistent proof/receipt fields even after a manifest is
recomputed. It recomputes intended/obtained edition-subject coverage, ties retained
attempts to page scope, checks unavailable reasons, selection/retrieval chronology
and all wire/entity/retention sums. Arbitrary extra claims are not accepted fields.

These gates prove **internal agreement of supplied files**, not TLS/network origin,
source rights, the truth of a self-consistent forged seed list, real historical
moves, resolved mappings, pageview signals or a public website. Keep real bundles
unpublished until independent origin/rights/retrieval review. The >=20 real-identity
cross-subject panel remains #19/#14; fixtures do not complete it.

## Tests and sources

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -p 'test_m1_*.py' -v
node tests/js_m1_share.cjs
python -m tools.m1_build_preview --check
python -m compileall -q tools tests
```

Test-only HTML/CSS parsers are pinned separately; runtime remains standard-library
Python plus static browser assets. Tests use synthetic injected responses, including
negative integrity/identity/transport/race controls. Normal browser acceptance is
separate in [M1_PREVIEW.md](M1_PREVIEW.md). The bounded phase decision is
[D08](../research/D08_DESCRIPTIVE_DELIVERY.md); research is not wholly complete.

Primary provider policies checked 2026-10-22:
- https://wikitech.wikimedia.org/wiki/Robot_policy
- https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy
- https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits

This source adoption consolidates the retained M1 recovery lineage through
`dayflare-m1-wikimedia-action-api-pacing-UNPUBLISHED.zip` and adds gzip/CI integration
repairs. Git history and native PRs own adoption/review status; old chat test counts
are not current CI receipts. No live Wikimedia success or public deployment is
asserted by this document.
