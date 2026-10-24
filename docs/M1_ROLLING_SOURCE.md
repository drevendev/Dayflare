# M1: bounded retained-body Wikipedia pageview collection

Issue #13 / #18, following merged rolling gate #27 and monotonic local stage #28. This is one **new executable data-collection/evidence slice**, **not** proof of a live target-runtime fetch, identity continuity, automated refresh, or a public release. The historical six-series M0 capsule is unchanged.

## Input and commands

A human-verified curated seed is required. Never send fictional test seeds to Wikimedia. Example *shape only* (replace every identity/title/selection with independently checked real values before a live run):

```json
{"schema_version":"dayflare.rolling-pageview-seeds.v1","selected_at":"2026-10-24","method_version":"v0-empirical-35d","provider_lag_days":2,"pages":[{"project":"en.wikipedia","page_id":1234,"title":"VERIFIED_TITLE","subject":"science"}]}
```

`page_id` is a **supplied identity claim**, not recovered from this title-based Analytics endpoint. The example ID/title pairing is deliberately NOT an asserted real Wikipedia identity. Independently review a real seed, including title history and redirects, before any public identity-stable interpretation. The pageview endpoint cannot establish a move-safe per-page-ID history; do not present cross-title continuity as measured.

From repo root with Python >=3.12:

```sh
python -m unittest discover -s tests -p 'test_rolling_pageview_source.py' -v
python -m tools.rolling_pageview_source collect path/to/reviewed-seeds.json evidence/local-unique-run
python -m tools.rolling_pageview_source verify evidence/local-unique-run
# After verifying provenance and rights separately, stage a LOCAL candidate only:
python -m tools.rolling_pageview_source stage evidence/local-unique-run local-rolling-stage
```

No command publishes to `master`, Pages, the M0 site, or another remote. `collect` fails if the target directory already exists; it does not delete or overwrite an earlier evidence run. New data do not silently supplant the historic M0 observations. A separately authorized CI refresh/publisher and live visitor verification remain #13/#12.

## Bounded behavior

`collect` selects the 35 consecutive UTC dates ending three days before invocation for `provider_lag_days=2` (in general today minus `lag+1` days). This is a **conservative local allowance**, not a sourced freshness guarantee. It sends at most **30 sequential** GET requests to `wikimedia.org`'s allow-listed daily `per-article` Analytics endpoint. Each is `all-access/user`, includes a clear User-Agent, has a 12-second timeout and two seconds spacing, follows **no** redirects, and has **no** automatic retry. A 429/503 reports `Retry-After` where provided, aborts the whole candidate and requires a later controlled attempt respecting the provider's guidance. Provider policy and capacity must be rechecked before real execution. A UTC-day rollover aborts rather than mixing distinct rolling windows.

The 1 MiB per-response limit applies to both transferred representation and decoded JSON, with 8 MiB combined limits; gzip requires one complete member and a good CRC. Content-Length, when provided, must match actual transferred bytes. JSON must be UTF-8 without duplicate keys or nonfinite values. All 35 dates, filters, supplied titles and edition must match; missing/duplicate days are **not** zero. No top-N candidate is inferred. A failed or incomplete call leaves the earlier accepted pointer and any existing site unchanged.

The output is a unique directory containing canonical `candidate.json`, `source-receipt.json`, `seeds.json`, and exactly one `raw/<project>.<page_id>.json` decoded response body per requested page. `verify` recomputes all daily values from retained bytes and checks every byte length, hash, source URL, seed/receipt/candidate relation, source inventory, dates and filters. Original compressed wire bytes are **not** retained; their reported hash and count are transport observations only. Source hashes bind retained decoded JSON entities.

The reported successful HTTPS retrieval is evidence from the executing runtime, **not independent cryptographic proof of remote provenance**. A self-consistent synthetic bundle is still forgeable. Explicit `synthetic_injected_not_upstream_evidence` labels are used in injected regression tests. `stage` calls the existing immutable monotonic local stage only after offline bundle consistency verification, and the resulting pointer remains `LOCAL_CANDIDATE_ONLY_NOT_PUBLISHED` with its original self-reported provenance label.

## Acceptance and limitations

The local 13 synthetic regression tests exercise complete EN/RU 35-day history including reported zero, 429/503/no partial output, malformed/gapped/mismatched/nonfinite records, gzip errors, duplicate JSON, forged candidate values, unexpected/symlink bodies and unique destination. They are **not a live retrieval receipt**. Before D01/D08 publication acceptance, execute a *separate* real bounded target-runtime run, retain and inspect endpoints/status/timestamps/bytes, verify actual title-to-page-ID mappings and continuity, independently confirm rights/source, and apply the existing stage gate. New presentation coverage and live freshness remain unavailable until reviewed and deployed.

Primary source reference checked 2026-10-24: [Wikimedia Analytics page-metrics examples](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/examples/page-metrics.html), [API access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html), [pageview concepts](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html). Wikimedia measurements represent request-based attention, not unique people, importance, approval or causes; `agent=user` does not guarantee verified human traffic. Dataset license cannot be extended to article prose or imagery.

## Avoid duplicate title-scoped Analytics requests (#13 / #19)

The seed validator rejects two distinct numeric page IDs that would issue the same
edition/article request. Wikimedia Pageviews is **title-scoped**, not page-ID-scoped;
spaces and underscores in article titles are the same outbound URL representation.
The seed is invalid before network access, rather than treating identical requested
histories as separate independently measured topics. The same title in distinct
language editions remains valid; unrelated titles in one edition remain valid.

This guard does **not** prove historical page-ID/title continuity, authenticate
upstream receipts, or establish new public coverage. Independently validated
identity history and complete windows remain requirements for publishing real M1.
